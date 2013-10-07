# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the logging system of the sshserver."""

__metaclass__ = type

import codecs
import logging
from logging.handlers import WatchedFileHandler
import os
from StringIO import StringIO
import sys
import tempfile

from bzrlib.tests import TestCase as BzrTestCase
import zope.component.event

from lp.services.sshserver.accesslog import LoggingManager
from lp.testing import TestCase


class LoggingManagerMixin:

    _log_count = 0

    def makeLogger(self, name=None):
        if name is None:
            self._log_count += 1
            name = '%s-%s' % (self.id().split('.')[-1], self._log_count)
        return logging.getLogger(name)

    def installLoggingManager(self, main_log=None, access_log=None,
                              access_log_path=None):
        if main_log is None:
            main_log = self.makeLogger()
        if access_log is None:
            access_log = self.makeLogger()
        if access_log_path is None:
            fd, access_log_path = tempfile.mkstemp()
            os.close(fd)
            self.addCleanup(os.unlink, access_log_path)
        manager = LoggingManager(main_log, access_log, access_log_path)
        manager.setUp()
        self.addCleanup(manager.tearDown)
        return manager


class TestLoggingBazaarInteraction(BzrTestCase, LoggingManagerMixin):

    def setUp(self):
        BzrTestCase.setUp(self)

        # Trap stderr.
        self._real_stderr = sys.stderr
        sys.stderr = codecs.getwriter('utf8')(StringIO())

    def tearDown(self):
        sys.stderr = self._real_stderr
        BzrTestCase.tearDown(self)

    def test_leaves_bzr_handlers_unchanged(self):
        # Bazaar's log handling is untouched by logging setup.
        root_handlers = logging.getLogger('').handlers
        bzr_handlers = logging.getLogger('bzr').handlers

        self.installLoggingManager()

        self.assertEqual(root_handlers, logging.getLogger('').handlers)
        self.assertEqual(bzr_handlers, logging.getLogger('bzr').handlers)

    def test_log_doesnt_go_to_stderr(self):
        # Once logging setup is called, any messages logged to the
        # SSH server logger should *not* be logged to stderr. If they are,
        # they will appear on the user's terminal.
        log = self.makeLogger()
        self.installLoggingManager(log)

        # Make sure that a logged message does not go to stderr.
        log.info('Hello hello')
        self.assertEqual(sys.stderr.getvalue(), '')


class TestLoggingManager(TestCase, LoggingManagerMixin):

    def test_main_log_handlers(self):
        # There needs to be at least one handler for the root logger. If there
        # isn't, we'll get constant errors complaining about the lack of
        # logging handlers.
        log = self.makeLogger()
        self.assertEqual([], log.handlers)
        self.installLoggingManager(log)
        self.assertNotEqual([], log.handlers)

    def _get_handlers(self):
        registrations = (
            zope.component.getGlobalSiteManager().registeredHandlers())
        return [
            registration.factory
            for registration in registrations]

    def test_set_up_registers_event_handler(self):
        manager = self.installLoggingManager()
        self.assertIn(manager._log_event, self._get_handlers())

    def test_teardown_restores_event_handlers(self):
        handlers = self._get_handlers()
        manager = self.installLoggingManager()
        manager.tearDown()
        self.assertEqual(handlers, self._get_handlers())

    def test_teardown_restores_level(self):
        log = self.makeLogger()
        old_level = log.level
        manager = self.installLoggingManager(log)
        manager.tearDown()
        self.assertEqual(old_level, log.level)

    def test_teardown_restores_main_log_handlers(self):
        # tearDown restores log handlers for the main logger.
        log = self.makeLogger()
        handlers = list(log.handlers)
        manager = self.installLoggingManager(log)
        manager.tearDown()
        self.assertEqual(handlers, log.handlers)

    def test_teardown_restores_access_log_handlers(self):
        # tearDown restores log handlers for the access logger.
        log = self.makeLogger()
        handlers = list(log.handlers)
        manager = self.installLoggingManager(access_log=log)
        manager.tearDown()
        self.assertEqual(handlers, log.handlers)

    def test_access_handlers(self):
        # The logging setup installs a rotatable log handler that logs output
        # to the SSH server access log.
        directory = self.makeTemporaryDirectory()
        access_log = self.makeLogger()
        access_log_path = os.path.join(directory, 'access.log')
        self.installLoggingManager(
            access_log=access_log,
            access_log_path=access_log_path)
        [handler] = access_log.handlers
        self.assertIsInstance(handler, WatchedFileHandler)
        self.assertEqual(access_log_path, handler.baseFilename)
