# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'disable_oops_handler',
    'LaunchpadCronScript',
    'LaunchpadScript',
    'LaunchpadScriptFailure',
    'LOCK_PATH',
    'SilentLaunchpadScriptFailure',
    ]

from ConfigParser import SafeConfigParser
from contextlib import contextmanager
from cProfile import Profile
import datetime
import logging
from optparse import OptionParser
import os.path
import sys
from urllib2 import (
    HTTPError,
    URLError,
    urlopen,
    )

from contrib.glock import (
    GlobalLock,
    LockAlreadyAcquired,
    )
import pytz
import transaction
from zope.component import getUtility

from lp.services import scripts
from lp.services.config import (
    config,
    dbconfig,
    )
from lp.services.database.postgresql import ConnectionString
from lp.services.features import (
    get_relevant_feature_controller,
    install_feature_controller,
    make_script_feature_controller,
    )
from lp.services.mail.sendmail import set_immediate_mail_delivery
from lp.services.scripts.interfaces.scriptactivity import IScriptActivitySet
from lp.services.scripts.logger import OopsHandler
from lp.services.utils import total_seconds
from lp.services.webapp.errorlog import globalErrorUtility
from lp.services.webapp.interaction import (
    ANONYMOUS,
    setupInteractionByEmail,
    )


LOCK_PATH = "/var/lock/"
UTC = pytz.UTC


class LaunchpadScriptFailure(Exception):
    """Something bad happened and the script is going away.

    When you raise LaunchpadScriptFailure inside your main() method, we
    do two things:

        - log an error with the stringified exception
        - sys.exit(1)

    Releasing the lock happens as a side-effect of the exit.

    Note that the sys.exit return value of 1 is defined as
    LaunchpadScriptFailure.exit_status. If you want a different value
    subclass LaunchpadScriptFailure and redefine it.
    """
    exit_status = 1


class SilentLaunchpadScriptFailure(Exception):
    """A LaunchpadScriptFailure that doesn't log an error."""

    def __init__(self, exit_status=1):
        Exception.__init__(self, exit_status)
        self.exit_status = exit_status
    exit_status = 1


def log_unhandled_exception_and_exit(func):
    """Decorator that logs unhandled exceptions via the logging module.

    Exceptions are reraised except at the top level. ie. exceptions are
    only propagated to the outermost decorated method. At the top level,
    an exception causes the script to terminate.

    Only for methods of `LaunchpadScript` and subclasses. Not thread safe,
    which is fine as the decorated LaunchpadScript methods are only
    invoked from the main thread.
    """

    def log_unhandled_exceptions_func(self, *args, **kw):
        try:
            self._log_unhandled_exceptions_level += 1
            return func(self, *args, **kw)
        except Exception:
            if self._log_unhandled_exceptions_level == 1:
                # self.logger is setup in LaunchpadScript.__init__() so
                # we can use it.
                self.logger.exception("Unhandled exception")
                sys.exit(1)
            else:
                raise
        finally:
            self._log_unhandled_exceptions_level -= 1
    return log_unhandled_exceptions_func


class LaunchpadScript:
    """A base class for runnable scripts and cronscripts.

    Inherit from this base class to simplify the setup work that your
    script needs to do.

    What you define:
        - main()
        - add_my_options(), if you have any
        - usage and description, if you want output for --help

    What you call:
        - lock_and_run()

    If you are picky:
        - lock_or_die()
        - run()
        - unlock()
        - build_options()

    What you get:
        - self.logger
        - self.txn
        - self.parser (the OptionParser)
        - self.options (the parsed options)

    "Give me convenience or give me death."
    """
    lock = None
    txn = None
    usage = None
    description = None
    lockfilepath = None
    loglevel = logging.INFO

    # State for the log_unhandled_exceptions decorator.
    _log_unhandled_exceptions_level = 0

    def __init__(self, name=None, dbuser=None, test_args=None, logger=None):
        """Construct new LaunchpadScript.

        Name is a short name for this script; it will be used to
        assemble a lock filename and to identify the logger object.

        Use dbuser to specify the user to connect to the database; if
        not supplied a default will be used.

        Specify test_args when you want to override sys.argv.  This is
        useful in test scripts.

        :param logger: Use this logger, instead of initializing global
            logging.
        """
        if name is None:
            self._name = self.__class__.__name__.lower()
        else:
            self._name = name

        self._dbuser = dbuser
        self.logger = logger

        # The construction of the option parser is a bit roundabout, but
        # at least it's isolated here. First we build the parser, then
        # we add options that our logger object uses, then call our
        # option-parsing hook, and finally pull out and store the
        # supplied options and args.
        if self.description is None:
            description = self.__doc__
        else:
            description = self.description
        self.parser = OptionParser(usage=self.usage,
                                   description=description)

        if logger is None:
            scripts.logger_options(self.parser, default=self.loglevel)
            self.parser.add_option(
                '--profile', dest='profile', metavar='FILE', help=(
                        "Run the script under the profiler and save the "
                        "profiling stats in FILE."))
        else:
            scripts.dummy_logger_options(self.parser)

        self.add_my_options()
        self.options, self.args = self.parser.parse_args(args=test_args)

        # Enable subclasses to easily override these __init__()
        # arguments using command-line arguments.
        self.handle_options()

    def handle_options(self):
        if self.logger is None:
            self.logger = scripts.logger(self.options, self.name)

    @property
    def name(self):
        """Enable subclasses to override with command-line arguments."""
        return self._name

    @property
    def dbuser(self):
        """Enable subclasses to override with command-line arguments."""
        return self._dbuser

    #
    # Hooks that we expect users to redefine.
    #
    def main(self):
        """Define the meat of your script here. Must be defined.

        Raise LaunchpadScriptFailure if you encounter an error condition
        that makes it impossible for you to proceed; sys.exit(1) will be
        invoked in that situation.
        """
        raise NotImplementedError

    def add_my_options(self):
        """Optionally customize this hook to define your own options.

        This method should contain only a set of lines that follow the
        template:

            self.parser.add_option("-f", "--foo", dest="foo",
                default="foobar-makes-the-world-go-round",
                help="You are joking, right?")
        """

    #
    # Convenience or death
    #
    @log_unhandled_exception_and_exit
    def login(self, user=ANONYMOUS):
        """Super-convenience method that avoids the import."""
        setupInteractionByEmail(user)

    #
    # Locking and running methods. Users only call these explicitly if
    # they really want to control the run-and-locking semantics of the
    # script carefully.
    #
    @property
    def lockfilename(self):
        """Return lockfilename.

        May be overridden in targeted scripts in order to have more specific
        lockfilename.
        """
        return "launchpad-%s.lock" % self.name

    @property
    def lockfilepath(self):
        return os.path.join(LOCK_PATH, self.lockfilename)

    def setup_lock(self):
        """Create lockfile.

        Note that this will create a lockfile even if you don't actually
        use it. GlobalLock.__del__ is meant to clean it up though.
        """
        self.lock = GlobalLock(self.lockfilepath, logger=self.logger)

    @log_unhandled_exception_and_exit
    def lock_or_die(self, blocking=False):
        """Attempt to lock, and sys.exit(1) if the lock's already taken.

        Say blocking=True if you want to block on the lock being
        available.
        """
        self.setup_lock()
        try:
            self.lock.acquire(blocking=blocking)
        except LockAlreadyAcquired:
            self.logger.info('Lockfile %s in use' % self.lockfilepath)
            sys.exit(1)

    @log_unhandled_exception_and_exit
    def unlock(self, skip_delete=False):
        """Release the lock. Do this before going home.

        If you skip_delete, we won't try to delete the lock when it's
        freed. This is useful if you have moved the directory in which
        the lockfile resides.
        """
        self.lock.release(skip_delete=skip_delete)

    @log_unhandled_exception_and_exit
    def run(self, use_web_security=False, isolation=None):
        """Actually run the script, executing zcml and initZopeless."""

        if isolation is None:
            isolation = 'read_committed'
        self._init_zca(use_web_security=use_web_security)
        self._init_db(isolation=isolation)

        # XXX wgrant 2011-09-24 bug=29744: initZopeless used to do this.
        # Should be called directly by scripts that actually need it.
        set_immediate_mail_delivery(True)

        date_started = datetime.datetime.now(UTC)
        profiler = None
        if self.options.profile:
            profiler = Profile()

        original_feature_controller = get_relevant_feature_controller()
        install_feature_controller(make_script_feature_controller(self.name))
        try:
            if profiler:
                profiler.runcall(self.main)
            else:
                self.main()
        except LaunchpadScriptFailure as e:
            self.logger.error(str(e))
            sys.exit(e.exit_status)
        except SilentLaunchpadScriptFailure as e:
            sys.exit(e.exit_status)
        else:
            date_completed = datetime.datetime.now(UTC)
            self.record_activity(date_started, date_completed)
        finally:
            install_feature_controller(original_feature_controller)
        if profiler:
            profiler.dump_stats(self.options.profile)

    def _init_zca(self, use_web_security):
        """Initialize the ZCA, this can be overridden for testing purposes."""
        scripts.execute_zcml_for_scripts(use_web_security=use_web_security)

    def _init_db(self, isolation):
        """Initialize the database transaction.

        Can be overridden for testing purposes.
        """
        dbuser = self.dbuser
        if dbuser is None:
            connstr = ConnectionString(dbconfig.main_master)
            dbuser = connstr.user or dbconfig.dbuser
        dbconfig.override(dbuser=dbuser, isolation_level=isolation)
        self.txn = transaction

    def record_activity(self, date_started, date_completed):
        """Hook to record script activity."""

    #
    # Make things happen
    #
    @log_unhandled_exception_and_exit
    def lock_and_run(self, blocking=False, skip_delete=False,
                     use_web_security=False,
                     isolation='read_committed'):
        """Call lock_or_die(), and then run() the script.

        Will die with sys.exit(1) if the locking call fails.
        """
        self.lock_or_die(blocking=blocking)
        try:
            self.run(use_web_security=use_web_security, isolation=isolation)
        finally:
            self.unlock(skip_delete=skip_delete)


class LaunchpadCronScript(LaunchpadScript):
    """Logs successful script runs in the database."""

    def __init__(self, name=None, dbuser=None, test_args=None, logger=None):
        super(LaunchpadCronScript, self).__init__(
            name, dbuser, test_args=test_args, logger=logger)

        # self.name is used instead of the name argument, since it may have
        # have been overridden by command-line parameters or by
        # overriding the name property.
        enabled = cronscript_enabled(
            config.canonical.cron_control_url, self.name, self.logger)
        if not enabled:
            sys.exit(0)

        # Configure the IErrorReportingUtility we use with defaults.
        # Scripts can override this if they want.
        globalErrorUtility.configure()

        # WARN and higher log messages should generate OOPS reports.
        # self.name is used instead of the name argument, since it may have
        # have been overridden by command-line parameters or by
        # overriding the name property.
        oops_hdlr = OopsHandler(self.name, logger=self.logger)
        logging.getLogger().addHandler(oops_hdlr)

    def get_last_activity(self):
        """Return the last activity, if any."""
        return getUtility(IScriptActivitySet).getLastActivity(self.name)

    @log_unhandled_exception_and_exit
    def record_activity(self, date_started, date_completed):
        """Record the successful completion of the script."""
        self.txn.begin()
        self.login(ANONYMOUS)
        getUtility(IScriptActivitySet).recordSuccess(
            name=self.name,
            date_started=date_started,
            date_completed=date_completed)
        self.txn.commit()
        # date_started is recorded *after* the lock is acquired and we've
        # initialized Zope components and the database.  Thus this time is
        # only for the script proper, rather than total execution time.
        seconds_taken = total_seconds(date_completed - date_started)
        self.logger.debug(
            "%s ran in %ss (excl. load & lock)" % (self.name, seconds_taken))


@contextmanager
def disable_oops_handler(logger):
    oops_handlers = []
    for handler in logger.handlers:
        if isinstance(handler, OopsHandler):
            oops_handlers.append(handler)
            logger.removeHandler(handler)
    yield
    for handler in oops_handlers:
        logger.addHandler(handler)


def cronscript_enabled(control_url, name, log):
    """Return True if the cronscript is enabled."""
    try:
        # Timeout of 5 seconds should be fine on the LAN. We don't want
        # the default as it is too long for scripts being run every 60
        # seconds.
        control_fp = urlopen(control_url, timeout=5)
    # Yuck. API makes it hard to catch 'does not exist'.
    except HTTPError as error:
        if error.code == 404:
            log.debug("Cronscript control file not found at %s", control_url)
            return True
        log.exception("Error loading %s" % control_url)
        return True
    except URLError as error:
        if getattr(error.reason, 'errno', None) == 2:
            log.debug("Cronscript control file not found at %s", control_url)
            return True
        log.exception("Error loading %s" % control_url)
        return True
    except Exception:
        log.exception("Error loading %s" % control_url)
        return True

    cron_config = SafeConfigParser({'enabled': str(True)})

    # Try reading the config file. If it fails, we log the
    # traceback and continue on using the defaults.
    try:
        cron_config.readfp(control_fp)
    except:
        log.exception("Error parsing %s", control_url)

    if cron_config.has_option(name, 'enabled'):
        section = name
    else:
        section = 'DEFAULT'

    try:
        enabled = cron_config.getboolean(section, 'enabled')
    except:
        log.exception(
            "Failed to load value from %s section of %s",
            section, control_url)
        enabled = True

    if enabled:
        log.debug("Enabled by %s section", section)
    else:
        log.info("Disabled by %s section", section)

    return enabled
