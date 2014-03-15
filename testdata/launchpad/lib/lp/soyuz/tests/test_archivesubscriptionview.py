# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for ArchiveSubscribersView."""

__metaclass__ = type

from soupmatchers import (
    HTMLContains,
    Tag,
    )
from zope.component import getUtility

from lp.registry.interfaces.person import IPersonSet
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import LaunchpadFunctionalLayer
from lp.testing.views import create_initialized_view


class TestArchiveSubscribersView(TestCaseWithFactory):
    """Tests for ArchiveSubscribersView."""

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestArchiveSubscribersView, self).setUp()
        self.p3a_owner = self.factory.makePerson()
        admin = getUtility(IPersonSet).getByEmail('admin@canonical.com')
        with person_logged_in(admin):
            self.private_ppa = self.factory.makeArchive(
                owner=self.p3a_owner, private=True, name='p3a')
        with person_logged_in(self.p3a_owner):
            for count in range(3):
                subscriber = self.factory.makePerson()
                self.private_ppa.newSubscription(subscriber, self.p3a_owner)

    def test_has_batch_navigation(self):
        # The page has the usual batch navigation links.
        with person_logged_in(self.p3a_owner):
            view = create_initialized_view(
                self.private_ppa, '+subscriptions', principal=self.p3a_owner)
            html = view.render()
        has_batch_navigation = HTMLContains(
            Tag('batch navigation links', 'td',
                attrs={'class': 'batch-navigation-links'}, count=2))
        self.assertThat(html, has_batch_navigation)
