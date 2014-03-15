# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the PersonalArchiveSubscription components and view."""

__metaclass__ = type

from lp.app.interfaces.launchpad import IPrivacy
from lp.soyuz.browser.archivesubscription import PersonalArchiveSubscription
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestSomething(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_personal_archive_subscription_adapts_to_privacy(self):
        owner = self.factory.makePerson(name='archiveowner')
        subscriber = self.factory.makePerson(name='subscriber')
        pppa = self.factory.makeArchive(
            owner=owner, private=True, name='pppa')
        with person_logged_in(owner):
            pppa.newSubscription(subscriber, owner)
        pas = PersonalArchiveSubscription(subscriber, pppa)
        privacy = IPrivacy(pas)
        self.assertTrue(privacy.private)
