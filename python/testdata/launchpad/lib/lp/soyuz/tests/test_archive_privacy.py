# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test Archive privacy features."""

from zope.security.interfaces import Unauthorized

from lp.soyuz.interfaces.archive import CannotSwitchPrivacy
from lp.soyuz.tests.test_publishing import SoyuzTestPublisher
from lp.testing import (
    celebrity_logged_in,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadZopelessLayer,
    )


class TestArchivePrivacy(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_no_subscription(self):
        # You cannot access private PPAs without a subscription.
        ppa = self.factory.makeArchive(private=True)
        non_subscriber = self.factory.makePerson()
        with person_logged_in(non_subscriber):
            self.assertRaises(Unauthorized, getattr, ppa, 'description')

    def test_subscription(self):
        # Once you have a subscription, you can access private PPAs.
        ppa = self.factory.makeArchive(private=True, description="Foo")
        subscriber = self.factory.makePerson()
        with person_logged_in(ppa.owner):
            ppa.newSubscription(subscriber, ppa.owner)
        with person_logged_in(subscriber):
            self.assertEqual(ppa.description, "Foo")

    def test_owner_changing_privacy(self):
        ppa = self.factory.makeArchive()
        with person_logged_in(ppa.owner):
            self.assertRaises(Unauthorized, setattr, ppa, 'private', True)

    def test_owner_with_commercial_subscription_changing_privacy(self):
        ppa = self.factory.makeArchive()
        self.factory.grantCommercialSubscription(ppa.owner)
        with person_logged_in(ppa.owner):
            # XXX: jml 2012-06-11: We actually want this to be allowed, but I
            # can't think of any way to grant this without also granting other
            # attributes that have launchpad.Admin.
            self.assertRaises(Unauthorized, setattr, ppa, 'private', True)

    def test_admin_changing_privacy(self):
        ppa = self.factory.makeArchive()
        with celebrity_logged_in('admin'):
            ppa.private = True
        self.assertEqual(True, ppa.private)

    def test_commercial_admin_changing_privacy(self):
        ppa = self.factory.makeArchive()
        with celebrity_logged_in('commercial_admin'):
            ppa.private = True
        self.assertEqual(True, ppa.private)


class TestPrivacySwitching(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def test_switch_privacy_no_pubs_succeeds(self):
        # Changing the privacy is fine if there are no publishing
        # records.
        public_ppa = self.factory.makeArchive()
        public_ppa.private = True
        self.assertTrue(public_ppa.private)

        private_ppa = self.factory.makeArchive(private=True)
        private_ppa.private = False
        self.assertFalse(private_ppa.private)

    def test_switch_privacy_with_pubs_fails(self):
        # Changing the privacy is not possible when the archive already
        # has published sources.
        public_ppa = self.factory.makeArchive(private=False)
        publisher = SoyuzTestPublisher()
        publisher.prepareBreezyAutotest()

        private_ppa = self.factory.makeArchive(private=True)
        publisher.getPubSource(archive=public_ppa)
        publisher.getPubSource(archive=private_ppa)

        self.assertRaises(
            CannotSwitchPrivacy, setattr, public_ppa, 'private', True)

        self.assertRaises(
            CannotSwitchPrivacy, setattr, private_ppa, 'private', False)

    def test_buildd_secret_was_generated(self):
        public_ppa = self.factory.makeArchive()
        public_ppa.private = True
        self.assertNotEqual(public_ppa.buildd_secret, None)

    def test_discard_buildd_was_discarded(self):
        private_ppa = self.factory.makeArchive(private=True)
        private_ppa.private = False
        self.assertEqual(private_ppa.buildd_secret, None)
