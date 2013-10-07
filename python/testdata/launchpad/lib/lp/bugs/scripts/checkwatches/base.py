# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Common classes and functions for the checkwatches system."""

__metaclass__ = type
__all__ = [
    'WorkingBase',
    'commit_before',
    'with_interaction',
    ]

from contextlib import contextmanager
from functools import wraps
import sys

from zope.component import getUtility
from zope.security.management import (
    endInteraction,
    queryInteraction,
    )

from lp.bugs.externalbugtracker import BugWatchUpdateWarning
from lp.services.database.isolation import check_no_transaction
from lp.services.limitedlist import LimitedList
from lp.services.webapp.adapter import (
    clear_request_started,
    get_request_start_time,
    set_request_started,
    )
from lp.services.webapp.errorlog import (
    ErrorReportingUtility,
    ScriptRequest,
    )
from lp.services.webapp.interaction import setupInteraction
from lp.services.webapp.interfaces import IPlacelessAuthUtility

# For OOPS reporting keep up to this number of SQL statements.
MAX_SQL_STATEMENTS_LOGGED = 10000


def report_oops(message=None, properties=None, info=None,
                transaction_manager=None):
    """Record an oops for the current exception.

    This must only be called while handling an exception.

    Searches for 'URL', 'url', or 'baseurl' properties, in order of
    preference, to use as the linked URL of the OOPS report.

    :param message: custom explanatory error message. Do not use
        str(exception) to fill in this parameter, it should only be
        set when a human readable error has been explicitly generated.

    :param properties: Properties to record in the OOPS report.
    :type properties: An iterable of (name, value) tuples.

    :param info: Exception info.
    :type info: The return value of `sys.exc_info()`.

    :param transaction_manager: A transaction manager. If specified,
        further commit() calls will be logged.
    """
    # Get the current exception info first of all.
    if info is None:
        info = sys.exc_info()

    # Collect properties to report.
    if properties is None:
        properties = []
    else:
        properties = list(properties)

    if message is not None:
        properties.append(('error-explanation', message))

    # Find a candidate for the request URL.
    def find_url():
        for name in 'URL', 'url', 'baseurl':
            for key, value in properties:
                if key == name:
                    return value
        return None
    url = find_url()

    # Create the dummy request object.
    request = ScriptRequest(properties, url)
    error_utility = ErrorReportingUtility()
    error_utility.configure(section_name='checkwatches')
    error_utility.raising(info, request)
    return request


def report_warning(message, properties=None, info=None,
                   transaction_manager=None):
    """Create and report a warning as an OOPS.

    If no exception info is passed in this will create a generic
    `BugWatchUpdateWarning` to record.

    :param message: See `report_oops`.
    :param properties: See `report_oops`.
    :param info: See `report_oops`.
    :param transaction_manager: See `report_oops`.
    """
    if info is None:
        # Raise and catch the exception so that sys.exc_info will
        # return our warning.
        try:
            raise BugWatchUpdateWarning(message)
        except BugWatchUpdateWarning:
            return report_oops(message, properties)
    else:
        return report_oops(message, properties, info, transaction_manager)


class WorkingBase:
    """A base class for writing a long-running process."""

    def init(self, login, transaction_manager, logger):
        self._login = login
        self._principal = (
            getUtility(IPlacelessAuthUtility).getPrincipalByLogin(
                self._login))
        self._transaction_manager = transaction_manager
        self.logger = logger

    def initFromParent(self, parent):
        self._login = parent._login
        self._principal = parent._principal
        self._transaction_manager = parent._transaction_manager
        self.logger = parent.logger

    @property
    @contextmanager
    def interaction(self):
        """Context manager for interaction as the given user.

        If an interaction is already in progress this is a no-op,
        otherwise it sets up an interaction on entry and ends it on
        exit.
        """
        if queryInteraction() is None:
            setupInteraction(self._principal, login=self._login)
            try:
                yield
            finally:
                endInteraction()
        else:
            yield

    @property
    @contextmanager
    def transaction(self):
        """Context manager to ring-fence database activity.

        Ensures that no transaction is in progress on entry, and
        commits on a successful exit. Exceptions are propagated once
        the transaction has been aborted.

        This intentionally cannot be nested. Keep it simple.
        """
        check_no_transaction()
        try:
            yield self._transaction_manager
        except:
            self._transaction_manager.abort()
            # Let the exception propagate.
            raise
        else:
            self._transaction_manager.commit()

    def _statement_logging_start(self):
        """Start logging SQL statements and other database activity."""
        set_request_started(
            request_statements=LimitedList(MAX_SQL_STATEMENTS_LOGGED),
            txn=self._transaction_manager, enable_timeout=False)

    def _statement_logging_stop(self):
        """Stop logging SQL statements."""
        clear_request_started()

    def _statement_logging_reset(self):
        """Reset the SQL statement log, if enabled."""
        if get_request_start_time() is not None:
            self._statement_logging_stop()
            self._statement_logging_start()

    @property
    @contextmanager
    def statement_logging(self):
        """Context manager to start and stop SQL statement logging.

        It does this by (mis)using the webapp statement logging
        machinery.
        """
        self._statement_logging_start()
        try:
            yield
        finally:
            self._statement_logging_stop()

    def warning(self, message, properties=None, info=None):
        """Record a warning."""
        oops_info = report_warning(
            message, properties, info, self._transaction_manager)
        # Also put it in the log.
        self.logger.warning("%s (%s)" % (message, oops_info.oopsid))
        # Reset statement logging, if enabled.
        self._statement_logging_reset()
        # Return the OOPS ID so that we can use it in
        # BugWatchActivity.
        return oops_info.oopsid

    def error(self, message, properties=None, info=None):
        """Record an error."""
        oops_info = report_oops(
            message, properties, info, self._transaction_manager)
        # Also put it in the log.
        self.logger.info("%s (%s)" % (message, oops_info.oopsid))
        # Reset statement logging, if enabled.
        self._statement_logging_reset()
        # Return the OOPS ID so that we can use it in
        # BugWatchActivity.
        return oops_info.oopsid


def with_interaction(func):
    """Wrap a method to ensure that it runs within an interaction.

    If an interaction is already set up, this simply calls the
    function. If no interaction exists, it will set one up, call the
    function, then end the interaction.

    This is intended to make sure the right thing happens whether or not
    the function is run in a different thread.

    It's intended for use with `WorkingBase`, which provides an
    `interaction` property; this is the hook that's required.
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        with self.interaction:
            return func(self, *args, **kwargs)
    return wrapper


def commit_before(func):
    """Wrap a method to commit any in-progress transactions.

    This is chiefly intended for use with public-facing methods, so
    that callers do not need to be responsible for committing before
    calling them.

    It's intended for use with `WorkingBase`, which provides a
    `_transaction_manager` property; this is the hook that's required.
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        self._transaction_manager.commit()
        return func(self, *args, **kwargs)
    return wrapper
