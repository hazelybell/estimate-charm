#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""
Apply all outstanding schema patches to an existing launchpad database
"""

__metaclass__ = type

import _pythonpath

import glob
from optparse import OptionParser
import os.path
import re
from textwrap import dedent

from bzrlib.branch import Branch
from bzrlib.errors import NotBranchError

from lp.services.database.sqlbase import (
    connect,
    sqlvalues,
    )
from lp.services.scripts import (
    db_options,
    logger,
    logger_options,
    )
from lp.services.utils import total_seconds


SCHEMA_DIR = os.path.dirname(__file__)


def main(con=None):
    if con is None:
        con = connect()

    patches = get_patchlist(con)

    log.info("Applying patches.")
    apply_patches_normal(con)

    report_patch_times(con, patches)

    # Commit changes
    if options.commit:
        log.debug("Committing changes")
        con.commit()

    return 0


# When we apply a number of patches in a transaction, they all end up
# with the same start_time (the transaction start time). This SQL fixes
# that up by setting the patch start time to the previous patches end
# time when there are patches that share identical start times. The
# FIX_PATCH_TIMES_PRE_SQL stores the start time of patch application,
# which is probably not the same as the transaction timestamp because we
# have to apply trusted.sql before applying patches (in addition to
# other preamble time such as Slony-I grabbing locks).
# FIX_PATCH_TIMES_POST_SQL does the repair work.
FIX_PATCH_TIMES_PRE_SQL = dedent("""\
    CREATE TEMPORARY TABLE _start_time AS (
        SELECT statement_timestamp() AT TIME ZONE 'UTC' AS start_time);
    """)
FIX_PATCH_TIMES_POST_SQL = dedent("""\
    UPDATE LaunchpadDatabaseRevision
    SET start_time = prev_end_time
    FROM (
        SELECT
            LDR1.major, LDR1.minor, LDR1.patch,
            max(LDR2.end_time) AS prev_end_time
        FROM
            LaunchpadDatabaseRevision AS LDR1,
            LaunchpadDatabaseRevision AS LDR2
        WHERE
            (LDR1.major, LDR1.minor, LDR1.patch)
                > (LDR2.major, LDR2.minor, LDR2.patch)
            AND LDR1.start_time = LDR2.start_time
        GROUP BY LDR1.major, LDR1.minor, LDR1.patch
        ) AS PrevTime
    WHERE
        LaunchpadDatabaseRevision.major = PrevTime.major
        AND LaunchpadDatabaseRevision.minor = PrevTime.minor
        AND LaunchpadDatabaseRevision.patch = PrevTime.patch
        AND LaunchpadDatabaseRevision.start_time <> prev_end_time;

    UPDATE LaunchpadDatabaseRevision
    SET
        start_time=_start_time.start_time,
        branch_nick = %s,
        revno = %s,
        revid = %s
    FROM _start_time
    WHERE
        LaunchpadDatabaseRevision.start_time
            = transaction_timestamp() AT TIME ZONE 'UTC';
    """)


def report_patch_times(con, todays_patches):
    """Report how long it took to apply the given patches."""
    cur = con.cursor()

    todays_patches = [patch_tuple for patch_tuple, patch_file
        in todays_patches]

    cur.execute("""
        SELECT
            major, minor, patch, start_time, end_time - start_time AS db_time
        FROM LaunchpadDatabaseRevision
        WHERE start_time > CURRENT_TIMESTAMP AT TIME ZONE 'UTC'
            - CAST('1 month' AS interval)
        ORDER BY major, minor, patch
        """)
    for major, minor, patch, start_time, db_time in cur.fetchall():
        if (major, minor, patch) in todays_patches:
            continue
        db_time = total_seconds(db_time)
        start_time = start_time.strftime('%Y-%m-%d')
        log.info(
            "%d-%02d-%d applied %s in %0.1f seconds"
            % (major, minor, patch, start_time, db_time))

    for major, minor, patch in todays_patches:
        cur.execute("""
            SELECT end_time - start_time AS db_time
            FROM LaunchpadDatabaseRevision
            WHERE major = %s AND minor = %s AND patch = %s
            """, (major, minor, patch))
        db_time = cur.fetchone()[0]
        # Patches before 2208-01-1 don't have timing information.
        # Ignore this. We can remove this code the next time we
        # create a new database baseline, as all patches will have
        # timing information.
        if db_time is None:
            log.debug('%d-%d-%d no application time', major, minor, patch)
            continue
        log.info(
            "%d-%02d-%d applied just now in %0.1f seconds",
            major, minor, patch, total_seconds(db_time))


def apply_patches_normal(con):
    """Update a non replicated database."""
    # trusted.sql contains all our stored procedures, which may
    # be required for patches to apply correctly so must be run first.
    apply_other(con, 'trusted.sql')

    # Prepare to repair patch timestamps if necessary.
    cur = con.cursor()
    cur.execute(FIX_PATCH_TIMES_PRE_SQL)

    # Apply the patches
    patches = get_patchlist(con)
    for (major, minor, patch), patch_file in patches:
        apply_patch(con, major, minor, patch, patch_file)

    # Repair patch timestamps if necessary.
    cur.execute(
        FIX_PATCH_TIMES_POST_SQL % sqlvalues(*get_bzr_details()))

    # Update comments.
    apply_comments(con)


def get_patchlist(con):
    """Return a patches that need to be applied to the connected database
    in [((major, minor, patch), patch_file)] format.
    """
    dbpatches = applied_patches(con)

    # Generate a list of all patches we might want to apply
    patches = []
    all_patch_files = glob.glob(
        os.path.join(SCHEMA_DIR, 'patch-????-??-?.sql'))
    all_patch_files.sort()
    for patch_file in all_patch_files:
        m = re.search('patch-(\d+)-(\d+)-(\d).sql$', patch_file)
        if m is None:
            log.fatal('Invalid patch filename %s' % repr(patch_file))
            raise SystemExit(1)

        major, minor, patch = [int(i) for i in m.groups()]
        if (major, minor, patch) in dbpatches:
            continue  # This patch has already been applied
        log.debug("Found patch %d.%d.%d -- %s" % (
            major, minor, patch, patch_file
            ))
        patches.append(((major, minor, patch), patch_file))
    return patches


def applied_patches(con):
    """Return a list of all patches that have been applied to the database.
    """
    cur = con.cursor()
    cur.execute("SELECT major, minor, patch FROM LaunchpadDatabaseRevision")
    return [tuple(row) for row in cur.fetchall()]


def apply_patch(con, major, minor, patch, patch_file):
    apply_other(con, patch_file, no_commit=True)

    # Ensure the patch updated LaunchpadDatabaseRevision. We could do this
    # automatically and avoid the boilerplate, but then we would lose the
    # ability to easily apply the patches manually.
    if (major, minor, patch) not in applied_patches(con):
        log.fatal("%s failed to update LaunchpadDatabaseRevision correctly"
                % patch_file)
        raise SystemExit(2)

    # Commit changes if we allow partial updates.
    if options.commit and options.partial:
        log.debug("Committing changes")
        con.commit()


def apply_other(con, script, no_commit=False):
    log.info("Applying %s" % script)
    cur = con.cursor()
    path = os.path.join(os.path.dirname(__file__), script)
    sql = open(path).read()
    if not sql.rstrip().endswith(';'):
        # This is important because patches are concatenated together
        # into a single script when we apply them to a replicated
        # environment.
        log.fatal(
            "Last non-whitespace character of %s must be a semicolon", script)
        raise SystemExit(3)
    cur.execute(sql)

    if not no_commit and options.commit and options.partial:
        log.debug("Committing changes")
        con.commit()


def apply_comments(con):
    if options.comments:
        apply_other(con, 'comments.sql')
    else:
        log.debug("Skipping comments.sql per command line settings")


_bzr_details_cache = None


def get_bzr_details():
    """Return (branch_nick, revno, revision_id) of this Bazaar branch.

    Returns (None, None, None) if the tree this code is running from
    is not a Bazaar branch.
    """
    global _bzr_details_cache
    if _bzr_details_cache is None:
        try:
            branch = Branch.open_containing(SCHEMA_DIR)[0]
            revno, revision_id = branch.last_revision_info()
            branch_nick = branch.get_config().get_nickname()
        except NotBranchError:
            log.warning("Not a Bazaar branch - branch details unavailable")
            revision_id, revno, branch_nick = None, None, None
        _bzr_details_cache = (branch_nick, revno, revision_id)
    return _bzr_details_cache


if __name__ == '__main__':
    parser = OptionParser()
    db_options(parser)
    logger_options(parser)
    parser.add_option(
        "-n", "--dry-run", dest="commit", default=True,
        action="store_false", help="Don't actually commit changes")
    parser.add_option(
        "--partial", dest="partial", default=False,
        action="store_true", help="Commit after applying each patch")
    parser.add_option(
        "--skip-comments", dest="comments", default=True,
        action="store_false", help="Skip applying comments.sql")
    (options, args) = parser.parse_args()

    if args:
        parser.error("Too many arguments")

    log = logger(options)
    main()
