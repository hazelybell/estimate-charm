# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for TestSubscriptionView."""

__metaclass__ = type

from lp.bugs.browser.bugtarget import TargetSubscriptionView
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.deprecated import LaunchpadFormHarness
from lp.testing.layers import LaunchpadFunctionalLayer
from lp.testing.views import create_view


class TargetSubscriptionViewTestCase(TestCaseWithFactory):
    """Tests for the TargetSubscriptionView."""

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TargetSubscriptionViewTestCase, self).setUp()
        self.product = self.factory.makeProduct(
            name='widgetsrus', displayname='Widgets R Us')
        self.subscriber = self.factory.makePerson()

    def test_form_initializes(self):
        # It's a start.
        with person_logged_in(self.subscriber):
            self.product.addBugSubscription(
                self.subscriber, self.subscriber)
            harness = LaunchpadFormHarness(
                self.product, TargetSubscriptionView)
            harness.view.initialize()

    def test_does_not_redirect(self):
        # +subscriptions on the bugs facet does not redirect.
        with person_logged_in(self.subscriber):
            view = create_view(
                self.product, name='+subscriptions', rootsite='bugs')
            view.initialize()
            self.assertFalse(view._isRedirected())

    def test_redirects(self):
        # +subscriptions on anything but the bugs facet redirects.
        with person_logged_in(self.subscriber):
            view = create_view(
                self.product, name='+subscriptions', rootsite='code')
            view.initialize()
            self.assertTrue(view._isRedirected())
