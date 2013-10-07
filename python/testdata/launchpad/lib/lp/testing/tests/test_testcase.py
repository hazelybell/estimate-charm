# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests relating to the Launchpad TestCase classes here."""

__metaclass__ = type

import logging
from StringIO import StringIO
import sys

import oops_datedir_repo.serializer_rfc822
from storm.store import Store
from zope.component import getUtility

from lp.code.interfaces.branch import IBranchSet
from lp.services.webapp import errorlog
from lp.testing import (
    record_statements,
    TestCase,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    FunctionalLayer,
    )


class TestRecordStatements(TestCaseWithFactory):
    """Test the statement recorder."""

    layer = DatabaseFunctionalLayer

    def test_counter_positive(self):
        # The base TestCase setUp adds a statement counter.
        branch, statements = record_statements(self.factory.makeBranch)
        self.assertTrue(len(statements) > 0)

    def test_store_invalidation_counts(self):
        # When creating objects with the factory, they stay in the storm
        # cache, sometimes we want to confirm that no more queries are
        # happening, so we need to clear the cache to avoid getting cached
        # objects where there would normally be queries.
        branch = self.factory.makeBranch()
        store = Store.of(branch)

        # Make sure everything is in the database.
        store.flush()
        # Reset the store to clear the cache (not just invalidate).
        store.reset()
        branch = getUtility(IBranchSet).getByUniqueName(branch.unique_name)
        self.assertStatementCount(1, getattr, branch, "owner")


class TestCaptureOops(TestCaseWithFactory):
    # Note that this tests the testcase specific functionality; see
    # test_fixture for tests of the CaptureOops fixture.

    layer = FunctionalLayer

    def trigger_oops(self):
        try:
            raise AssertionError("Exception to get a traceback.")
        except AssertionError:
            errorlog.globalErrorUtility.raising(sys.exc_info())

    def test_no_oops_gives_no_details(self):
        self.assertEqual(0, len(self.oopses))
        self.attachOopses()
        self.assertEqual(
            0, len([a for a in self.getDetails() if "oops" in a]))

    def test_one_oops_gives_one_detail(self):
        self.assertEqual(0, len(self.oopses))
        self.trigger_oops()
        self.attachOopses()
        self.assertEqual(
            ["oops-0"], [a for a in self.getDetails() if "oops" in a])

    def xxxtest_two_oops_gives_two_details(self):
        # XXX sinzui 2011-12-26: bug=908799: This test intermittently
        # fails because there is only one oops.
        self.assertEqual(0, len(self.oopses))
        self.trigger_oops()
        self.trigger_oops()
        self.attachOopses()
        self.assertEqual(
            ["oops-0", "oops-1"],
            sorted([a for a in self.getDetails() if "oops" in a]))

    def test_oops_content(self):
        self.assertEqual(0, len(self.oopses))
        self.trigger_oops()
        self.attachOopses()
        content = StringIO()
        content.writelines(self.getDetails()['oops-0'].iter_bytes())
        content.seek(0)
        # Safety net: ensure that no autocasts have occured even on Python 2.6
        # which is slightly better.
        self.assertIsInstance(content.getvalue(), str)
        # In tests it should be rfc822 for easy reading.
        from_details = oops_datedir_repo.serializer_rfc822.read(content)
        # Compare with the in-memory model (but only a select key, because the
        # rfc822 serializer is lossy).
        oops_report = self.oopses[0]
        self.assertEqual(from_details['id'], oops_report['id'])


class TestRemoveLoggingHandlers(TestCase):

    def setUp(self):
        self.logger = logging.getLogger()
        # Add 2 handlers.
        self.logger.addHandler(logging.Handler())
        self.logger.addHandler(logging.Handler())
        # `TestCase.setUp()` removes the handlers just added.
        super(TestRemoveLoggingHandlers, self).setUp()

    def test_handlers_list_is_empty(self):
        # Ensure `TestCase.setUp()` correctly removed all logging handlers.
        self.assertEqual(0, len(self.logger.handlers))
