# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for Twisted XML-RPC support."""

__metaclass__ = type

from twisted.python.failure import Failure

from lp.services.twistedsupport import extract_result
from lp.services.twistedsupport.xmlrpc import (
    BlockingProxy,
    DeferredBlockingProxy,
    trap_fault,
    )
from lp.services.xmlrpc import LaunchpadFault
from lp.testing import TestCase


class TestFaultOne(LaunchpadFault):
    """An arbitrary subclass of `LaunchpadFault`.

    This class and `TestFaultTwo` are a pair of distinct `LaunchpadFault`
    subclasses to use in tests.
    """

    error_code = 1001
    msg_template = "Fault one."


class TestFaultTwo(LaunchpadFault):
    """Another arbitrary subclass of `LaunchpadFault`.

    This class and `TestFaultOne` are a pair of distinct `LaunchpadFault`
    subclasses to use in tests.
    """

    error_code = 1002
    msg_template = "Fault two."


class TestTrapFault(TestCase):
    """Tests for `trap_fault`."""

    def makeFailure(self, exception_factory, *args, **kwargs):
        """Make a `Failure` from the given exception factory."""
        try:
            raise exception_factory(*args, **kwargs)
        except:
            return Failure()

    def assertRaisesFailure(self, failure, function, *args, **kwargs):
        try:
            function(*args, **kwargs)
        except Failure as raised_failure:
            self.assertEqual(failure, raised_failure)

    def test_raises_non_faults(self):
        # trap_fault re-raises any failures it gets that aren't faults.
        failure = self.makeFailure(RuntimeError, 'example failure')
        self.assertRaisesFailure(failure, trap_fault, failure, TestFaultOne)

    def test_raises_faults_with_wrong_code(self):
        # trap_fault re-raises any failures it gets that are faults but have
        # the wrong fault code.
        failure = self.makeFailure(TestFaultOne)
        self.assertRaisesFailure(failure, trap_fault, failure, TestFaultTwo)

    def test_raises_faults_if_no_codes_given(self):
        # If trap_fault is not given any fault codes, it re-raises the fault
        # failure.
        failure = self.makeFailure(TestFaultOne)
        self.assertRaisesFailure(failure, trap_fault, failure)

    def test_returns_fault_if_code_matches(self):
        # trap_fault returns the Fault inside the Failure if the fault code
        # matches what's given.
        failure = self.makeFailure(TestFaultOne)
        fault = trap_fault(failure, TestFaultOne)
        self.assertEqual(TestFaultOne.error_code, fault.faultCode)
        self.assertEqual(TestFaultOne.msg_template, fault.faultString)

    def test_returns_fault_if_code_matches_one_of_set(self):
        # trap_fault returns the Fault inside the Failure if the fault code
        # matches even one of the given fault codes.
        failure = self.makeFailure(TestFaultOne)
        fault = trap_fault(failure, TestFaultOne, TestFaultTwo)
        self.assertEqual(TestFaultOne.error_code, fault.faultCode)
        self.assertEqual(TestFaultOne.msg_template, fault.faultString)


class TestBlockingProxy(TestCase):

    def test_callRemote_calls_attribute(self):
        class ExampleProxy:
            def ok(self, a, b, c=None):
                return (c, b, a)
        proxy = BlockingProxy(ExampleProxy())
        result = proxy.callRemote('ok', 2, 3, c=8)
        self.assertEqual((8, 3, 2), result)

    def test_callRemote_reraises_attribute(self):
        class ExampleProxy:
            def not_ok(self, a, b, c=None):
                raise RuntimeError((c, b, a))
        proxy = BlockingProxy(ExampleProxy())
        error = self.assertRaises(
            RuntimeError, proxy.callRemote, 'not_ok', 2, 3, c=8)
        self.assertEqual(str(error), str((8, 3, 2)))


class TestDeferredBlockingProxy(TestCase):

    def test_callRemote_calls_attribute(self):
        class ExampleProxy:
            def ok(self, a, b, c=None):
                return (c, b, a)
        proxy = DeferredBlockingProxy(ExampleProxy())
        d = proxy.callRemote('ok', 2, 3, c=8)
        result = extract_result(d)
        self.assertEqual((8, 3, 2), result)

    def test_callRemote_traps_failure(self):
        class ExampleProxy:
            def not_ok(self, a, b, c=None):
                raise RuntimeError((c, b, a))
        proxy = DeferredBlockingProxy(ExampleProxy())
        d = proxy.callRemote('not_ok', 2, 3, c=8)
        error = self.assertRaises(RuntimeError, extract_result, d)
        self.assertEqual(str(error), str((8, 3, 2)))
