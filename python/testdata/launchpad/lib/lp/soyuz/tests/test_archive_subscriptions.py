# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test Archive features."""

from urlparse import urljoin

from storm.store import Store
from testtools.matchers import Equals
from zope.security.interfaces import Unauthorized
from zope.security.proxy import removeSecurityProxy

from lp.buildmaster.enums import BuildStatus
from lp.registry.interfaces.person import PersonVisibility
from lp.services.webapp.authorization import check_permission
from lp.services.webapp.publisher import canonical_url
from lp.soyuz.enums import PackagePublishingStatus
from lp.testing import (
    BrowserTestCase,
    login_person,
    person_logged_in,
    StormStatementRecorder,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.mail_helpers import pop_notifications
from lp.testing.matchers import HasQueryCount
from lp.testing.pages import (
    find_tag_by_id,
    setupBrowserForUser,
    )
from lp.testing.views import create_initialized_view


class TestArchiveSubscriptions(TestCaseWithFactory):
    """Edge-case tests for private PPA subscribers.

    See also lib/lp/soyuz/stories/ppa/xx-private-ppa-subscription-stories.txt
    """

    layer = DatabaseFunctionalLayer

    def setUp(self):
        """Create a test archive."""
        super(TestArchiveSubscriptions, self).setUp()
        self.owner = self.factory.makePerson()
        self.private_team = self.factory.makeTeam(
            visibility=PersonVisibility.PRIVATE,
            name="subscribertest", owner=self.owner)
        login_person(self.owner)
        self.archive = self.factory.makeArchive(
            private=True, owner=self.private_team)
        self.subscriber = self.factory.makePerson()

    def test_subscriber_can_access_private_team_ppa(self):
        # As per bug 597783, we need to make sure a subscriber can see
        # a private team's PPA after they have been given a subscription.
        # This is essentially allowing access for the subscriber to see
        # the private team.
        def get_name():
            return self.archive.owner.name

        # Before a subscription, accessing the team name will raise.
        login_person(self.subscriber)
        self.assertRaises(Unauthorized, get_name)

        login_person(self.owner)
        self.archive.newSubscription(
            self.subscriber, registrant=self.archive.owner)

        # When a subscription exists, it's fine.
        login_person(self.subscriber)
        self.assertEqual(self.archive.owner.name, "subscribertest")

    def test_subscriber_can_browse_private_team_ppa(self):
        # As per bug 597783, we need to make sure a subscriber can see
        # a private team's PPA after they have been given a subscription.
        # This test ensures the subscriber can correctly load the PPA's view,
        # thus ensuring that all attributes necessary to render the view have
        # the necessary security permissions.

        # Before a subscription, accessing the view name will raise.
        login_person(self.subscriber)
        self.assertRaises(
            Unauthorized, create_initialized_view,
            self.archive, '+index', principal=self.subscriber)

        login_person(self.owner)
        self.archive.newSubscription(
            self.subscriber, registrant=self.archive.owner)

        # When a subscription exists, it's fine.
        login_person(self.subscriber)
        view = create_initialized_view(
            self.archive, '+index', principal=self.subscriber)
        self.assertIn(self.archive.displayname, view.render())

    def test_new_subscription_sends_email(self):
        # Creating a new subscription sends an email to all members
        # of the person or team subscribed.
        self.assertEqual(0, len(pop_notifications()))

        self.archive.newSubscription(
            self.subscriber, registrant=self.archive.owner)

        notifications = pop_notifications()
        self.assertEqual(1, len(notifications))
        self.assertEqual(
            self.subscriber.preferredemail.email, notifications[0]['to'])

    def test_new_commercial_subscription_no_email(self):
        # As per bug 611568, an email is not sent for
        # suppress_subscription_notifications PPAs.
        self.archive.suppress_subscription_notifications = True

        self.archive.newSubscription(
            self.subscriber, registrant=self.archive.owner)

        self.assertEqual(0, len(pop_notifications()))

    def test_permission_for_subscriber(self):
        self.archive.newSubscription(
            self.subscriber, registrant=self.archive.owner)
        with person_logged_in(self.subscriber):
            self.assertTrue(
                check_permission('launchpad.SubscriberView', self.archive))
            self.assertFalse(check_permission('launchpad.View', self.archive))


class PrivateArtifactsViewTestCase(BrowserTestCase):
    """ Tests that private team archives can be viewed."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        """Create a test archive."""
        super(PrivateArtifactsViewTestCase, self).setUp()
        self.owner = self.factory.makePerson()
        self.private_team = self.factory.makeTeam(
            visibility=PersonVisibility.PRIVATE,
            name="subscribertest", owner=self.owner)
        with person_logged_in(self.owner):
            self.archive = self.factory.makeArchive(
                private=True, owner=self.private_team)
        spph = self.factory.makeSourcePackagePublishingHistory(
            archive=self.archive, status=PackagePublishingStatus.PUBLISHED)
        spr = removeSecurityProxy(spph).sourcepackagerelease
        self.factory.makeBinaryPackageBuild(
            source_package_release=spr, archive=self.archive,
            status=BuildStatus.FAILEDTOBUILD)
        self.subscriber = self.factory.makePerson()

    def test_traverse_view_private_team_archive_subscriber(self):
        # A subscriber can traverse and view the archive.
        with person_logged_in(self.owner):
            self.archive.newSubscription(
                self.subscriber, registrant=self.archive.owner)
        with person_logged_in(self.subscriber):
            url = canonical_url(self.archive)
        browser = setupBrowserForUser(self.subscriber)
        browser.open(url)
        content = find_tag_by_id(browser.contents, 'document')
        self.assertIsNotNone(find_tag_by_id(content, 'ppa-install'))

    def test_unauthorized_subscriber_for_plus_packages(self):
        with person_logged_in(self.owner):
            self.archive.newSubscription(
                self.subscriber, registrant=self.archive.owner)
        with person_logged_in(self.subscriber):
            url = urljoin(canonical_url(self.archive), '+packages')
        browser = setupBrowserForUser(self.subscriber)
        self.assertRaises(Unauthorized, browser.open, url)


class PersonArchiveSubscriptions(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_query_count(self):
        subscriber = self.factory.makePerson()
        for x in range(10):
            archive = self.factory.makeArchive(private=True)
            with person_logged_in(archive.owner):
                if x >= 5:
                    team = self.factory.makeTeam(members=[subscriber])
                    archive.newSubscription(team, archive.owner)
                else:
                    archive.newSubscription(subscriber, archive.owner)
        Store.of(subscriber).flush()
        Store.of(subscriber).invalidate()
        with person_logged_in(subscriber):
            with StormStatementRecorder() as recorder:
                view = create_initialized_view(
                    subscriber, '+archivesubscriptions', principal=subscriber)
                view.render()
        self.assertThat(recorder, HasQueryCount(Equals(9)))
