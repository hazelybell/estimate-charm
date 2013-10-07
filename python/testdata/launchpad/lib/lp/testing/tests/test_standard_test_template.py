# Copyright 2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""XXX: Module docstring goes here."""

__metaclass__ = type

# or TestCaseWithFactory
from lp.testing import TestCase
from lp.testing.layers import DatabaseFunctionalLayer


class TestSomething(TestCase):
    # XXX: Sample test class.  Replace with your own test class(es).

    # XXX: layer--see lib/lp/testing/layers.py
    # Get the simplest layer that your test will work on. For unit tests
    # requiring no resources, this is BaseLayer.
    layer = DatabaseFunctionalLayer

    # XXX: Sample test.  Replace with your own test methods.
    def test_baseline(self):

        # XXX: Assertions take expected value first, actual value second.
        self.assertEqual(4, 2 + 2)
