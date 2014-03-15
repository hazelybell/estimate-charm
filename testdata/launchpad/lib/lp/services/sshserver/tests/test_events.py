# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the logging events."""

__metaclass__ = type

import logging

from zope.component import (
    adapter,
    getGlobalSiteManager,
    provideHandler,
    )
# This non-standard import is necessary to hook up the event system.
import zope.component.event
from zope.event import notify

from lp.services.sshserver.events import (
    ILoggingEvent,
    LoggingEvent,
    )
from lp.testing import TestCase


class ListHandler(logging.Handler):
    """Logging handler that just appends records to a list.

    This handler isn't intended to be used by production code -- memory leak
    city! -- instead it's useful for unit tests that want to make sure the
    right events are being logged.
    """

    def __init__(self, logging_list):
        """Construct a `ListHandler`.

        :param logging_list: A list that will be appended to. The handler
             mutates this list.
        """
        logging.Handler.__init__(self)
        self._list = logging_list

    def emit(self, record):
        """Append 'record' to the list."""
        self._list.append(record)


class TestLoggingEvent(TestCase):

    def assertLogs(self, records, function, *args, **kwargs):
        """Assert 'function' logs 'records' when run with the given args."""
        logged_events = []
        handler = ListHandler(logged_events)
        self.logger.addHandler(handler)
        result = function(*args, **kwargs)
        self.logger.removeHandler(handler)
        self.assertEqual(
            [(record.levelno, record.getMessage())
             for record in logged_events], records)
        return result

    def assertEventLogs(self, record, logging_event):
        self.assertLogs([record], notify, logging_event)

    def setUp(self):
        TestCase.setUp(self)
        logger = logging.getLogger(self.factory.getUniqueString())
        logger.setLevel(logging.DEBUG)
        self.logger = logger

        @adapter(ILoggingEvent)
        def _log_event(event):
            logger.log(event.level, event.message)

        provideHandler(_log_event)
        self.addCleanup(getGlobalSiteManager().unregisterHandler, _log_event)

    def test_level(self):
        event = LoggingEvent(logging.CRITICAL, "foo")
        self.assertEventLogs((logging.CRITICAL, 'foo'), event)

    def test_formatting(self):
        event = LoggingEvent(logging.DEBUG, "foo: %(name)s", name="bar")
        self.assertEventLogs((logging.DEBUG, 'foo: bar'), event)

    def test_subclass(self):
        class SomeEvent(LoggingEvent):
            template = "%(something)s happened."
            level = logging.INFO
        self.assertEventLogs(
            (logging.INFO, 'foo happened.'), SomeEvent(something='foo'))
