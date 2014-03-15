#!/usr/bin/python -S
# Copyright 2011-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Full update process."""

import _pythonpath

from datetime import datetime
from optparse import OptionParser
import sys

import psycopg2

from dbcontroller import DBController
from lp.services.scripts import (
    logger,
    logger_options,
    )
from preflight import (
    KillConnectionsPreflight,
    NoConnectionCheckPreflight,
    SYSTEM_USERS,
    )
import security  # security.py script
import upgrade  # upgrade.py script


def run_upgrade(options, log, master_con):
    """Invoke upgrade.py in-process.

    It would be easier to just invoke the script, but this way we save
    several seconds of overhead as the component architecture loads up.
    """
    # Fake expected command line arguments and global log
    upgrade.options = options
    upgrade.log = log
    # upgrade.py doesn't commit, because we are sharing the transaction
    # with security.py. We want schema updates and security changes
    # applied in the same transaction.
    options.commit = False
    options.partial = False
    options.comments = False  # Saves about 1s. Apply comments manually.
    # Invoke the database schema upgrade process.
    try:
        return upgrade.main(master_con)
    except Exception:
        log.exception('Unhandled exception')
        return 1
    except SystemExit as x:
        log.fatal("upgrade.py failed [%s]", x)


def run_security(options, log, master_con):
    """Invoke security.py in-process.

    It would be easier to just invoke the script, but this way we save
    several seconds of overhead as the component architecture loads up.
    """
    # Fake expected command line arguments and global log
    options.dryrun = False
    options.revoke = True
    options.owner = 'postgres'
    security.options = options
    security.log = log
    # Invoke the database security reset process.
    try:
        return security.main(options, master_con)
    except Exception:
        log.exception('Unhandled exception')
        return 1
    except SystemExit as x:
        log.fatal("security.py failed [%s]", x)


def main():
    parser = OptionParser()
    parser.add_option(
        '--pgbouncer', dest='pgbouncer',
        default='host=localhost port=6432 user=pgbouncer',
        metavar='CONN_STR',
        help="libpq connection string to administer pgbouncer")
    parser.add_option(
        '--dbname', dest='dbname', default='launchpad_prod', metavar='DBNAME',
        help='Database name we are updating.')
    parser.add_option(
        '--dbuser', dest='dbuser', default='postgres', metavar='USERNAME',
        help='Connect as USERNAME to databases')

    logger_options(parser, milliseconds=True)
    (options, args) = parser.parse_args()
    if args:
        parser.error("Too many arguments")

    # In case we are connected as a non-standard superuser, ensure we
    # don't kill our own connections.
    SYSTEM_USERS.add(options.dbuser)

    log = logger(options)

    controller = DBController(
        log, options.pgbouncer, options.dbname, options.dbuser)

    try:
        # Master connection, not running in autocommit to allow us to
        # rollback changes on failure.
        master_con = psycopg2.connect(str(controller.master))
    except Exception, x:
        log.fatal("Unable to open connection to master db (%s)", str(x))
        return 94

    # Preflight checks. Confirm as best we can that the upgrade will
    # work unattended. Here we ignore open connections, as they
    # will shortly be killed.
    controller.ensure_replication_enabled()
    if not NoConnectionCheckPreflight(log, controller).check_all():
        return 99

    #
    # Start the actual upgrade. Failures beyond this point need to
    # generate informative messages to help with recovery.
    #

    # status flags
    upgrade_run = False
    security_run = False
    replication_paused = False
    master_disabled = False
    slaves_disabled = False
    outage_start = None

    try:
        # Pause replication.
        replication_paused = controller.pause_replication()
        if not replication_paused:
            return 93

        # Start the outage clock.
        log.info("Outage starts.")
        outage_start = datetime.now()

        # Disable access and kill connections to the master database.
        master_disabled = controller.disable_master()
        if not master_disabled:
            return 95

        if not KillConnectionsPreflight(
            log, controller,
            replication_paused=replication_paused).check_all():
            return 100

        log.info("Preflight check succeeded. Starting upgrade.")
        # Does not commit master_con, even on success.
        upgrade_rc = run_upgrade(options, log, master_con)
        upgrade_run = (upgrade_rc == 0)
        if not upgrade_run:
            return upgrade_rc
        log.info("Database patches applied.")

        # Commits master_con on success.
        security_rc = run_security(options, log, master_con)
        security_run = (security_rc == 0)
        if not security_run:
            return security_rc

        master_disabled = not controller.enable_master()
        if master_disabled:
            log.warn("Outage ongoing until pgbouncer bounced.")
            return 96
        else:
            log.info("Outage complete. %s", datetime.now() - outage_start)

        slaves_disabled = controller.disable_slaves()

        # Resume replication.
        replication_paused = not controller.resume_replication()
        if replication_paused:
            log.error(
                "Failed to resume replication. Run pg_xlog_replay_pause() "
                "on all slaves to manually resume.")
        else:
            if controller.sync():
                log.info('Slaves in sync. Updates replicated.')
            else:
                log.error(
                    'Slaves failed to sync. Updates may not be replicated.')

        if slaves_disabled:
            slaves_disabled = not controller.enable_slaves()
            if slaves_disabled:
                log.warn(
                    "Failed to enable slave databases in pgbouncer. "
                    "Now running in master-only mode.")

        # We will start seeing connections as soon as pgbouncer is
        # reenabled, so ignore them here.
        if not NoConnectionCheckPreflight(log, controller).check_all():
            return 101

        log.info("All good. All done.")
        return 0

    finally:
        if not security_run:
            log.warning("Rolling back all schema and security changes.")
            master_con.rollback()

        # Recovery if necessary.
        if master_disabled:
            if controller.enable_master():
                log.warning(
                    "Master reenabled despite earlier failures. "
                    "Outage over %s, but we have problems",
                    str(datetime.now() - outage_start))
            else:
                log.warning(
                    "Master is still disabled in pgbouncer. Outage ongoing.")

        if replication_paused:
            controller.resume_replication()

        if slaves_disabled:
            controller.enable_slaves()


if __name__ == '__main__':
    sys.exit(main())
