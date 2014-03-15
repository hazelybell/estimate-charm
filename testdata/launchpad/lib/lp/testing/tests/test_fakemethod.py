# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from unittest import TestCase

from lp.testing.fakemethod import FakeMethod


class RealActualClass:
    """A class that's hard to test."""

    doing_impossible_stuff = False
    doing_possible_stuff = False

    def impossibleMethod(self):
        """A method that you can't afford to invoke in your test.

        This is the method you're going to want to avoid calling.  The
        way to do that is to replace this method with a fake method.
        """
        self.doing_impossible_stuff = True
        raise AssertionError("Trying to do impossible stuff.")

    def testableMethod(self):
        """This part of the class logic that you do want to exercise."""
        self.doing_possible_stuff = True

    def doComplicatedThings(self, argument):
        """This is the top-level method you want to test.

        Unfortunately this invokes impossibleMethod, making it hard.
        """
        self.impossibleMethod()
        self.testableMethod()
        return argument


class CustomException(Exception):
    """Some specific error that you want raised."""


class TestFakeMethod(TestCase):
    def test_fakeMethod(self):
        # A class that you're testing can continue normally despite some
        # of its methods being stubbed.
        thing = RealActualClass()
        thing.impossibleMethod = FakeMethod()

        result = thing.doComplicatedThings(99)

        self.assertEqual(99, result)
        self.assertFalse(thing.doing_impossible_stuff)
        self.assertTrue(thing.doing_possible_stuff)

    def test_raiseFailure(self):
        # A FakeMethod can raise an exception you specify.
        ouch = CustomException("Ouch!")
        func = FakeMethod(failure=ouch)
        self.assertRaises(CustomException, func)

    def test_returnResult(self):
        # A FakeMethod can return a value you specify.
        value = "Fixed return value."
        func = FakeMethod(result=value)
        self.assertEqual(value, func())

    def test_countCalls(self):
        # A FakeMethod counts the number of times it's been invoked.
        func = FakeMethod()
        for count in xrange(3):
            self.assertEqual(count, func.call_count)
            func()
            self.assertEqual(count + 1, func.call_count)

    def test_takeArguments(self):
        # A FakeMethod invocation accepts any arguments it gets.
        func = FakeMethod()
        func()
        func(1)
        func(2, kwarg=3)
        self.assertEqual(3, func.call_count)
