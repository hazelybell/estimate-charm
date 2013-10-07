# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for things found directly in `lp.services.twistedsupport`."""

__metaclass__ = type

from testtools.deferredruntest import (
    assert_fails_with,
    AsynchronousDeferredRunTest,
    )
from twisted.internet import defer
from twisted.internet.task import Clock

from lp.services.twistedsupport import (
    cancel_on_timeout,
    extract_result,
    )
from lp.testing import TestCase


class TestExtractResult(TestCase):
    """Tests for `lp.services.twistedsupport.extract_result`."""

    def test_success(self):
        # extract_result on a Deferred that has a result returns the result.
        val = self.factory.getUniqueString()
        deferred = defer.succeed(val)
        self.assertEqual(val, extract_result(deferred))

    def test_failure(self):
        # extract_result on a Deferred that has an error raises the failing
        # exception.
        deferred = defer.fail(RuntimeError())
        self.assertRaises(RuntimeError, extract_result, deferred)

    def test_not_fired(self):
        # extract_result on a Deferred that has not fired raises
        # AssertionError (extract_result is only supposed to be used when you
        # _know_ that the API you're using is really synchronous, despite
        # returning deferreds).
        deferred = defer.Deferred()
        self.assertRaises(AssertionError, extract_result, deferred)


class TestCancelOnTimeout(TestCase):
    """Tests for lp.services.twistedsupport.cancel_on_timeout."""

    run_tests_with = AsynchronousDeferredRunTest

    def test_deferred_is_cancelled(self):
        clock = Clock()
        d = cancel_on_timeout(defer.Deferred(), 1, clock)
        clock.advance(2)
        return assert_fails_with(d, defer.CancelledError)

    def test_deferred_is_not_cancelled(self):
        clock = Clock()
        d = cancel_on_timeout(defer.succeed("frobnicle"), 1, clock)
        clock.advance(2)
        def result(value):
            self.assertEqual(value, "frobnicle")
            self.assertEqual([], clock.getDelayedCalls())
        return d.addCallback(result)
