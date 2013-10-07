# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for TestP3APackages."""

__metaclass__ = type
__all__ = [
    'TestP3APackages',
    'TestPPAPackages',
    ]

import re

from BeautifulSoup import BeautifulSoup
import soupmatchers
from testtools.matchers import (
    Equals,
    LessThan,
    Not,
    )
from zope.component import getUtility
from zope.security.interfaces import Unauthorized
from zope.security.proxy import removeSecurityProxy

from lp.app.utilities.celebrities import ILaunchpadCelebrities
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.services.webapp import canonical_url
from lp.services.webapp.authentication import LaunchpadPrincipal
from lp.soyuz.browser.archive import ArchiveNavigationMenu
from lp.soyuz.enums import PackagePublishingStatus
from lp.soyuz.interfaces.packagecopyjob import IPlainPackageCopyJobSource
from lp.testing import (
    celebrity_logged_in,
    login,
    login_person,
    person_logged_in,
    record_two_runs,
    TestCaseWithFactory,
    )
from lp.testing._webservice import QueryCollector
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    )
from lp.testing.matchers import HasQueryCount
from lp.testing.pages import get_feedback_messages
from lp.testing.sampledata import ADMIN_EMAIL
from lp.testing.views import create_initialized_view


class TestP3APackages(TestCaseWithFactory):
    """P3A archive pages are rendered correctly."""

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestP3APackages, self).setUp()
        self.private_ppa = self.factory.makeArchive(description='Foo')
        login('admin@canonical.com')
        self.private_ppa.private = True
        self.joe = self.factory.makePerson(name='joe')
        self.fred = self.factory.makePerson(name='fred')
        self.mary = self.factory.makePerson(name='mary')
        login_person(self.private_ppa.owner)
        self.private_ppa.newSubscription(self.joe, self.private_ppa.owner)
        self.private_ppa.newComponentUploader(self.mary, 'main')

    def test_packages_unauthorized(self):
        """A person with no subscription will not be able to view +packages
        """
        login_person(self.fred)
        self.assertRaises(
            Unauthorized, create_initialized_view, self.private_ppa,
            "+packages")

    def test_packages_authorized_for_commercial_admin_with_subscription(self):
        # A commercial admin should always be able to see +packages even
        # if they have a subscription.
        login('admin@canonical.com')
        admins = getUtility(ILaunchpadCelebrities).commercial_admin
        admins.addMember(self.joe, admins)
        login_person(self.joe)
        view = create_initialized_view(self.private_ppa, "+packages")
        menu = ArchiveNavigationMenu(view)
        self.assertTrue(menu.packages().enabled)

    def test_packages_authorized(self):
        """A person with launchpad.{Append,Edit} will be able to do so"""
        login_person(self.private_ppa.owner)
        view = create_initialized_view(self.private_ppa, "+packages")
        menu = ArchiveNavigationMenu(view)
        self.assertTrue(menu.packages().enabled)

    def test_packages_uploader(self):
        """A person with launchpad.Append will also be able to do so"""
        login_person(self.mary)
        view = create_initialized_view(self.private_ppa, "+packages")
        menu = ArchiveNavigationMenu(view)
        self.assertTrue(menu.packages().enabled)

    def test_packages_link_subscriber(self):
        login_person(self.joe)
        view = create_initialized_view(self.private_ppa, "+index")
        menu = ArchiveNavigationMenu(view)
        self.assertFalse(menu.packages().enabled)


class TestPPAPackages(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def getPackagesView(self, query_string=None):
        ppa = self.factory.makeArchive()
        return create_initialized_view(
            ppa, "+packages", query_string=query_string)

    def assertNotifications(self, ppa, notification, person=None):
        # Assert that while requesting a 'ppa' page as 'person', the
        # 'notification' appears.
        if person is not None:
            login_person(ppa.owner)
            principal = LaunchpadPrincipal(
                ppa.owner.account.id, ppa.owner.displayname,
                ppa.owner.displayname, ppa.owner)
        else:
            principal = None
        page = create_initialized_view(
            ppa, "+packages", principal=principal).render()
        notifications = get_feedback_messages(page)
        self.assertIn(notification, notifications)

    def test_warning_for_disabled_publishing(self):
        # Ensure that a notification is shown when archive.publish
        # is False.
        ppa = self.factory.makeArchive()
        removeSecurityProxy(ppa).publish = False
        self.assertNotifications(
            ppa,
            "Publishing has been disabled for this archive. (re-enable "
            "publishing)",
            person=ppa.owner)

    def test_warning_for_disabled_publishing_with_private_ppa(self):
        # Ensure that a notification is shown when archive.publish
        # is False warning that builds won't get dispatched.
        ppa = self.factory.makeArchive(private=True)
        removeSecurityProxy(ppa).publish = False
        self.assertNotifications(
            ppa,
            "Publishing has been disabled for this archive. (re-enable "
            "publishing) Since this archive is private, no builds are being "
            "dispatched.",
            person=ppa.owner)

    def test_warning_for_disabled_publishing_with_anonymous_user(self):
        # The warning notification doesn't mention the Change details
        # page.
        ppa = self.factory.makeArchive()
        removeSecurityProxy(ppa).publish = False
        self.assertNotifications(
            ppa, 'Publishing has been disabled for this archive.')

    def test_ppa_packages_menu_is_enabled(self):
        joe = self.factory.makePerson()
        ppa = self.factory.makeArchive()
        login_person(joe)
        view = create_initialized_view(ppa, "+index")
        menu = ArchiveNavigationMenu(view)
        self.assertTrue(menu.packages().enabled)

    def test_specified_name_filter_works(self):
        view = self.getPackagesView('field.name_filter=blah')
        self.assertEquals('blah', view.specified_name_filter)

    def test_specified_name_filter_returns_none_on_omission(self):
        view = self.getPackagesView()
        self.assertIs(None, view.specified_name_filter)

    def test_specified_name_filter_returns_none_on_empty_filter(self):
        view = self.getPackagesView('field.name_filter=')
        self.assertIs(None, view.specified_name_filter)

    def test_source_query_counts(self):
        query_baseline = 43
        # Assess the baseline.
        collector = QueryCollector()
        collector.register()
        self.addCleanup(collector.unregister)
        ppa = self.factory.makeArchive()
        viewer = self.factory.makePerson()
        browser = self.getUserBrowser(user=viewer)
        with person_logged_in(viewer):
            # The baseline has one package, because otherwise the
            # short-circuit prevents the packages iteration happening at
            # all and we're not actually measuring scaling
            # appropriately.
            self.factory.makeSourcePackagePublishingHistory(archive=ppa)
            url = canonical_url(ppa) + "/+packages"
        browser.open(url)
        self.assertThat(collector, HasQueryCount(LessThan(query_baseline)))
        expected_count = collector.count
        # We scale with 1 query per distro series because of
        # getCurrentSourceReleases.
        expected_count += 1
        # We need a fuzz of one because if the test is the first to run a
        # credentials lookup is done as well (and accrued to the collector).
        expected_count += 1
        # Use all new objects - avoids caching issues invalidating the
        # gathered metrics.
        login(ADMIN_EMAIL)
        ppa = self.factory.makeArchive()
        viewer = self.factory.makePerson()
        browser = self.getUserBrowser(user=viewer)
        with person_logged_in(viewer):
            for i in range(2):
                pkg = self.factory.makeSourcePackagePublishingHistory(
                    archive=ppa)
                self.factory.makeSourcePackagePublishingHistory(archive=ppa,
                    distroseries=pkg.distroseries)
            url = canonical_url(ppa) + "/+packages"
        browser.open(url)
        self.assertThat(collector, HasQueryCount(LessThan(expected_count)))

    def test_binary_query_counts(self):
        query_baseline = 40
        # Assess the baseline.
        collector = QueryCollector()
        collector.register()
        self.addCleanup(collector.unregister)
        ppa = self.factory.makeArchive()
        viewer = self.factory.makePerson()
        browser = self.getUserBrowser(user=viewer)
        with person_logged_in(viewer):
            # The baseline has one package, because otherwise the
            # short-circuit prevents the packages iteration happening at
            # all and we're not actually measuring scaling
            # appropriately.
            pkg = self.factory.makeBinaryPackagePublishingHistory(
                archive=ppa)
            url = canonical_url(ppa) + "/+packages"
        browser.open(url)
        self.assertThat(collector, HasQueryCount(LessThan(query_baseline)))
        expected_count = collector.count
        # Use all new objects - avoids caching issues invalidating the
        # gathered metrics.
        login(ADMIN_EMAIL)
        ppa = self.factory.makeArchive()
        viewer = self.factory.makePerson()
        browser = self.getUserBrowser(user=viewer)
        with person_logged_in(viewer):
            for i in range(3):
                pkg = self.factory.makeBinaryPackagePublishingHistory(
                    archive=ppa, distroarchseries=pkg.distroarchseries)
            url = canonical_url(ppa) + "/+packages"
        browser.open(url)
        self.assertThat(collector, HasQueryCount(Equals(expected_count)))


class TestPPAPackagesJobNotifications(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestPPAPackagesJobNotifications, self).setUp()
        self.ws_version = 'devel'
        self.person = self.factory.makePerson()
        self.archive = self.factory.makeArchive(owner=self.person)

    def makeJob(self, package_name, failed=False):
        distroseries = self.factory.makeDistroSeries()
        source_archive = self.factory.makeArchive(distroseries.distribution)
        requester = self.factory.makePerson()
        source = getUtility(IPlainPackageCopyJobSource)
        job = source.create(
            package_name=package_name, source_archive=source_archive,
            target_archive=self.archive, target_distroseries=distroseries,
            target_pocket=PackagePublishingPocket.RELEASE,
            package_version="1.0-1", include_binaries=True,
            requester=requester)
        job.start()
        if failed:
            job.fail()
        return job

    def getPackagesView(self, query_string=None):
        ppa = self.factory.makeArchive()
        return create_initialized_view(
            ppa, "+packages", query_string=query_string)

    def test_job_notifications_display_failed(self):
        job = self.makeJob('package_1', failed=True)
        # Manually poke an error message.
        removeSecurityProxy(job).extendMetadata(
            {'error_message': 'Job failed!'})
        with person_logged_in(self.archive.owner):
            view = create_initialized_view(
                self.archive, "+packages", principal=self.archive.owner)
            html = view.render()
        packages_matches = soupmatchers.HTMLContains(
            # Check the main title.
            soupmatchers.Tag(
                'job summary', 'a',
                text=re.compile('Copying.*'),
                attrs={'class': re.compile('job-summary')}),
            # Check the link to the source archive.
            soupmatchers.Tag(
                'copied from', 'a',
                text=job.source_archive.displayname,
                attrs={'class': re.compile('copied-from')}),
            # Check the presence of the link to remove the notification.
            soupmatchers.Tag(
                'no remove notification link', 'a',
                text=re.compile('\s*Remove notification\s*'),
                attrs={'class': re.compile('remove-notification')}),
            # Check the presence of the error message.
            soupmatchers.Tag(
                'job error msg', 'div',
                text='Job failed!',
                attrs={'class': re.compile('job-failed-error-msg')}),
            )
        self.assertThat(html, packages_matches)

    def test_job_notifications_display_in_progress_not_allowed(self):
        other_person = self.factory.makePerson()
        self.makeJob('package_1', failed=True)
        with person_logged_in(other_person):
            view = create_initialized_view(
                self.archive, "+packages", principal=other_person)
            html = view.render()
        packages_not_matches = soupmatchers.HTMLContains(
            # Check the absence of the link remove the notification.
            soupmatchers.Tag(
                'no remove notification link', 'a',
                text=re.compile('\s*Remove notification\s*'),
                attrs={'class': re.compile('remove-notification')}),
            )
        self.assertThat(html, Not(packages_not_matches))

    def test_job_notifications_display_in_progress(self):
        job = self.makeJob('package_1', failed=False)
        with person_logged_in(self.archive.owner):
            view = create_initialized_view(
                self.archive, "+packages", principal=self.archive.owner)
            html = view.render()
        packages_matches = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                'job summary', 'a',
                text=re.compile('Copying.*'),
                attrs={'class': re.compile('job-summary')}),
            soupmatchers.Tag(
                'copied from', 'a',
                text=job.source_archive.displayname,
                attrs={'class': re.compile('copied-from')}),
            )
        packages_not_matches = soupmatchers.HTMLContains(
            # Check the absence of the link remove the notification.
            soupmatchers.Tag(
                'remove notification link', 'a',
                text=re.compile('\s*Remove notification\s*'),
                attrs={'class': re.compile('remove-notification')}),
            )
        self.assertThat(html, packages_matches)
        self.assertThat(html, Not(packages_not_matches))

    def test_job_notifications_display_multiple(self):
        job1 = self.makeJob('package_1')
        job2 = self.makeJob('package_2', failed=True)
        job3 = self.makeJob('package_3')
        with person_logged_in(self.archive.owner):
            view = create_initialized_view(
                self.archive, "+packages", principal=self.archive.owner)
            html = view.render()
        packages_matches = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                'job1', 'div',
                attrs={'class': 'pending-job', 'job_id': job1.id}),
            soupmatchers.Tag(
                'job2', 'div',
                attrs={'class': 'pending-job', 'job_id': job2.id}),
            soupmatchers.Tag(
                'job3', 'div',
                attrs={'class': 'pending-job', 'job_id': job3.id}),
            )
        self.assertThat(html, packages_matches)
        self.assertEquals(
            [], BeautifulSoup(html).findAll(
                'span', text=re.compile('Showing 5 of .')))

    def test_job_notifications_display_multiple_is_capped(self):
        jobs = [self.makeJob('package%d' % i) for i in range(7)]
        with person_logged_in(self.archive.owner):
            view = create_initialized_view(
                self.archive, "+packages", principal=self.archive.owner)
            soup = BeautifulSoup(view.render())
        self.assertEquals([],
            soup.findAll(
                'div', attrs={'class': 'pending-job', 'job_id': jobs[-1].id}))
        self.assertEquals(
            [u'Showing 5 of 7'],
            soup.findAll('span', text=re.compile('Showing 5 of .')))

    def test_job_notifications_display_owner_is_team(self):
        team = self.factory.makeTeam()
        removeSecurityProxy(self.archive).owner = team
        job = self.makeJob('package_1', failed=False)
        with person_logged_in(self.archive.owner):
            view = create_initialized_view(
                self.archive, "+packages", principal=self.archive.owner)
            html = view.render()
        packages_matches = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                'copied by', 'a',
                text=job.job.requester.displayname,
                attrs={'class': re.compile('copied-by')}),
            )
        self.assertThat(html, packages_matches)


class TestP3APackagesQueryCount(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestP3APackagesQueryCount, self).setUp()
        self.team = self.factory.makeTeam()
        login_person(self.team.teamowner)
        self.person = self.factory.makePerson()

        self.private_ppa = self.factory.makeArchive(
            owner=self.team, private=True)
        self.private_ppa.newSubscription(
            self.person, registrant=self.team.teamowner)

    def createPackage(self):
        with celebrity_logged_in('admin'):
            pkg = self.factory.makeBinaryPackagePublishingHistory(
                status=PackagePublishingStatus.PUBLISHED,
                archive=self.private_ppa)
        return pkg

    def test_ppa_index_queries_count(self):
        def ppa_index_render():
            with person_logged_in(self.team.teamowner):
                view = create_initialized_view(
                    self.private_ppa, '+index', principal=self.team.teamowner)
                view.page_title = "title"
                view.render()
        recorder1, recorder2 = record_two_runs(
            ppa_index_render, self.createPackage, 2, 3)

        self.assertThat(
            recorder2, HasQueryCount(LessThan(recorder1.count + 2)))
