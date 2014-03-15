# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Library functions for use in all scripts.

"""
__metaclass__ = type

__all__ = [
    'db_options',
    'dummy_logger_options',
    'execute_zcml_for_scripts',
    'log',
    'logger',
    'logger_options',
    ]

import atexit
import os
import sys
import threading

from zope.configuration.config import ConfigurationMachine
from zope.security.management import setSecurityPolicy
import zope.sendmail.delivery
import zope.site.hooks

from lp.services.config import config
from lp.services.database.postgresql import ConnectionString
# these are intentional re-exports, apparently, used by *many* files.
from lp.services.scripts.logger import (
    dummy_logger_options,
    log,
    logger,
    logger_options,
    )
from lp.services.webapp.authorization import (
    LaunchpadPermissiveSecurityPolicy,
    LaunchpadSecurityPolicy,
    )
from lp.services.webapp.interaction import (
    ANONYMOUS,
    setupInteractionByEmail,
    )


def execute_zcml_for_scripts(use_web_security=False):
    """Execute the zcml rooted at launchpad/script.zcml

    If use_web_security is True, the same security policy as the web
    application uses will be used. Otherwise everything protected by a
    permission is allowed, and everything else denied.
    """

    # When in testing mode, prevent some cases of erroneous layer usage.
    # But we don't want to import that module in production usage, thus
    # the conditional block.
    if 'lp.testing.layers' in sys.modules:
        from lp.testing.layers import (
                FunctionalLayer, BaseLayer, ZopelessLayer)
        assert not FunctionalLayer.isSetUp, \
                'Setting up Zopeless CA when Zopefull CA is already running'
        assert not BaseLayer.isSetUp or ZopelessLayer.isSetUp, """
                execute_zcml_for_scripts should not be called from tests.
                Instead, your test should use the Zopeless layer.
            """

    if config.isTestRunner():
        scriptzcmlfilename = 'script-testing.zcml'
    else:
        scriptzcmlfilename = 'script.zcml'

    scriptzcmlfilename = os.path.abspath(
        os.path.join(config.root, 'zcml', scriptzcmlfilename))

    from zope.configuration import xmlconfig

    # Hook up custom component architecture calls
    zope.site.hooks.setHooks()

    # Load server-independent site config
    context = ConfigurationMachine()
    xmlconfig.registerCommonDirectives(context)
    context = xmlconfig.file(
        scriptzcmlfilename, execute=True, context=context)

    if use_web_security:
        setSecurityPolicy(LaunchpadSecurityPolicy)
    else:
        setSecurityPolicy(LaunchpadPermissiveSecurityPolicy)

    # Register atexit handler to kill off mail delivery daemon threads, and
    # thus avoid spew at exit.  See:
    # http://mail.python.org/pipermail/python-list/2003-October/192044.html
    # http://mail.python.org/pipermail/python-dev/2003-September/038151.html
    # http://mail.python.org/pipermail/python-dev/2003-September/038153.html

    def kill_queue_processor_threads():
        for thread in threading.enumerate():
            if isinstance(
                thread, zope.sendmail.delivery.QueueProcessorThread):
                thread.stop()
                thread.join(30)
                if thread.isAlive():
                    raise RuntimeError(
                        "QueueProcessorThread did not shut down")
    atexit.register(kill_queue_processor_threads)

    # This is a convenient hack to set up a zope interaction, before we get
    # the proper API for having a principal / user running in scripts.
    setupInteractionByEmail(ANONYMOUS)


def db_options(parser):
    """Add and handle default database connection options on the command line

    Adds -d (--database), -H (--host), -p (--port) and -U (--user)

    Parsed options provide dbname, dbhost and dbuser attributes.

    Generally, scripts will not need this and should instead pull their
    connection details from launchpad.config.config. The database setup and
    maintenance tools cannot do this however.

    dbname and dbhost are also propagated to config.database.dbname and
    config.database.dbhost. This ensures that all systems will be using
    the requested connection details.

    Ensure that command line options propagate to where we say they do

    >>> from optparse import OptionParser
    >>> parser = OptionParser()
    >>> db_options(parser)
    >>> options, args = parser.parse_args(
    ...     ['--dbname=foo', '--host=bar', '--user=baz', '--port=6432'])
    >>> options.dbname
    'foo'
    >>> options.dbhost
    'bar'
    >>> options.dbuser
    'baz'
    >>> options.dbport
    6432
    >>> config.database.rw_main_master
    'dbname=foo user=baz host=bar port=6432'
    >>> config.database.rw_main_slave
    'dbname=foo user=baz host=bar port=6432'

    Make sure that the default user is None

    >>> parser = OptionParser()
    >>> db_options(parser)
    >>> options, args = parser.parse_args([])
    >>> print options.dbuser
    None
    """
    conn_string = ConnectionString(config.database.rw_main_master)

    def update_db_config(**kw):
        connection_string_keys = [
            'rw_main_master',
            'rw_main_slave',
            ]
        config_data = ["[database]"]
        for con_str_key in connection_string_keys:
            con_str = ConnectionString(getattr(config.database, con_str_key))
            for kwarg, kwval in kw.items():
                setattr(con_str, kwarg, kwval)
            config_data.append("%s: %s" % (con_str_key, str(con_str)))
        config.push('update_db_config', '\n'.join(config_data))

    def dbname_callback(option, opt_str, value, parser):
        parser.values.dbname = value
        update_db_config(dbname=value)

    parser.add_option(
            "-d", "--dbname", action="callback", callback=dbname_callback,
            type="string", dest="dbname", default=conn_string.dbname,
            help="PostgreSQL database to connect to."
            )

    def dbhost_callback(options, opt_str, value, parser):
        parser.values.dbhost = value
        update_db_config(host=value)

    parser.add_option(
             "-H", "--host", action="callback", callback=dbhost_callback,
             type="string", dest="dbhost", default=conn_string.host,
             help="Hostname or IP address of PostgreSQL server."
             )

    def dbport_callback(options, opt_str, value, parser):
        value = int(value)
        parser.values.dbport = value
        update_db_config(port=value)

    parser.add_option(
        "-p", "--port", action="callback", callback=dbport_callback,
        type=int, dest="dbport", default=conn_string.port,
        help="Port PostgreSQL server is listening on."
        )

    def dbuser_callback(options, opt_str, value, parser):
        parser.values.dbuser = value
        update_db_config(user=value)

    parser.add_option(
             "-U", "--user", action="callback", callback=dbuser_callback,
             type="string", dest="dbuser", default=None,
             help="PostgreSQL user to connect as."
             )
