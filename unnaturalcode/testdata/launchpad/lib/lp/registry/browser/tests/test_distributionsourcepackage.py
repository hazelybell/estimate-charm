# Copyright 2010-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test distributionsourcepackage views."""

__metaclass__ = type

import re

import soupmatchers
from zope.component import getUtility

from lp.app.enums import ServiceUsage
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.services.webapp import canonical_url
from lp.soyuz.enums import PackagePublishingStatus
from lp.soyuz.interfaces.archive import ArchivePurpose
from lp.testing import (
    celebrity_logged_in,
    person_logged_in,
    test_tales,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    )
from lp.testing.matchers import (
    BrowsesWithQueryLimit,
    IsConfiguredBatchNavigator,
    )
from lp.testing.views import (
    create_initialized_view,
    create_view,
    )


class TestDistributionSourcePackageFormatterAPI(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_link(self):
        self.factory.makeSourcePackageName('mouse')
        ubuntu = getUtility(ILaunchpadCelebrities).ubuntu
        dsp = ubuntu.getSourcePackage('mouse')
        markup = (
            u'<a href="/ubuntu/+source/mouse" class="sprite package-source">'
            u'mouse in Ubuntu</a>')
        self.assertEqual(markup, test_tales('dsp/fmt:link', dsp=dsp))


class TestDistributionSourcePackageChangelogView(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def test_packagediff_query_count(self):
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PRIMARY)
        spph = self.factory.makeSourcePackagePublishingHistory(
            archive=archive)
        dsp = archive.distribution.getSourcePackage(
            spph.sourcepackagerelease.sourcepackagename)
        changelog_browses_under_limit = BrowsesWithQueryLimit(
            32, self.factory.makePerson(), '+changelog')
        self.assertThat(dsp, changelog_browses_under_limit)
        with celebrity_logged_in('admin'):
            for i in range(5):
                self.factory.makePackageDiff(
                    to_source=spph.sourcepackagerelease)
        self.assertThat(dsp, changelog_browses_under_limit)


class TestDistributionSourcePackagePublishingHistoryView(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def test_publishinghistory_query_count(self):
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PRIMARY)
        spph = self.factory.makeSourcePackagePublishingHistory(
            archive=archive)
        spn = spph.sourcepackagerelease.sourcepackagename
        dsp = archive.distribution.getSourcePackage(spn)
        publishinghistory_browses_under_limit = BrowsesWithQueryLimit(
            27, self.factory.makePerson(), "+publishinghistory")
        self.assertThat(dsp, publishinghistory_browses_under_limit)
        with person_logged_in(archive.owner):
            copy_source_archive = self.factory.makeArchive()
            copy_spph = self.factory.makeSourcePackagePublishingHistory(
                archive=copy_source_archive, sourcepackagename=spn)
            copy_spph.copyTo(
                spph.distroseries, spph.pocket, archive,
                creator=self.factory.makePerson(),
                sponsor=self.factory.makePerson())
            delete_spph = self.factory.makeSourcePackagePublishingHistory(
                archive=archive, sourcepackagename=spn)
            delete_spph.requestDeletion(self.factory.makePerson())
        # This is a lot of extra queries per publication, and should be
        # ratcheted down over time; but it at least ensures that we don't
        # make matters any worse.
        publishinghistory_browses_under_limit.query_limit += 7
        self.assertThat(dsp, publishinghistory_browses_under_limit)

    def test_show_sponsor(self):
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PRIMARY)
        ppa = self.factory.makeArchive()
        spph = self.factory.makeSourcePackagePublishingHistory(archive=ppa)
        creator = self.factory.makePerson()
        sponsor = self.factory.makePerson()
        copied_spph = spph.copyTo(
            spph.distroseries, spph.pocket, archive, creator=creator,
            sponsor=sponsor)
        html = create_initialized_view(copied_spph, "+record-details").render()
        record_matches = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                "copy summary", "li", text=re.compile("sponsored by")),
            soupmatchers.Tag(
                "copy creator", "a", text=creator.displayname,
                attrs={
                    "href": "/~%s" % creator.name,
                    "class": "sprite person",
                    }),
            soupmatchers.Tag(
                "copy sponsor", "a", text=sponsor.displayname,
                attrs={
                    "href": "/~%s" % sponsor.name,
                    "class": "sprite person",
                    }),
            )
        self.assertThat(html, record_matches)

    def test_is_batched(self):
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PRIMARY)
        spn = self.factory.makeSourcePackageName()
        component = self.factory.makeComponent()
        section = self.factory.makeSection()
        dsp = archive.distribution.getSourcePackage(spn)
        statuses = (
            ([PackagePublishingStatus.SUPERSEDED] * 5)
            + [PackagePublishingStatus.PUBLISHED])
        for status in statuses:
            self.factory.makeSourcePackagePublishingHistory(
                archive=archive, sourcepackagename=spn, component=component,
                distroseries=archive.distribution.currentseries,
                section_name=section.name, status=status)
        view = create_initialized_view(dsp, "+publishinghistory")
        self.assertThat(
            view.batchnav, IsConfiguredBatchNavigator('result', 'results'))

        base_url = canonical_url(dsp) + '/+publishinghistory'
        browser = self.getUserBrowser(base_url)
        self.assertIn("<td>Published</td>", browser.contents)
        self.assertIn("<td>Superseded</td>", browser.contents)
        browser.getLink("Next").click()
        self.assertNotIn("<td>Published</td>", browser.contents)
        self.assertIn("<td>Superseded</td>", browser.contents)


class TestDistributionSourceView(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestDistributionSourceView, self).setUp()
        self.factory.makeSourcePackageName('mouse')
        distro = self.factory.makeDistribution()
        self.dsp = distro.getSourcePackage('mouse')

    def test_bugs_answers_usage_none(self):
        # The dict values are all False.
        view = create_view(self.dsp, '+index')
        self.assertFalse(view.bugs_answers_usage['uses_bugs'])
        self.assertFalse(view.bugs_answers_usage['uses_answers'])
        self.assertFalse(view.bugs_answers_usage['uses_both'])
        self.assertFalse(view.bugs_answers_usage['uses_either'])

    def test_bugs_answers_usage_bugs(self):
        # The dict values are True for bugs and either.
        with celebrity_logged_in('admin'):
            self.dsp.distribution.official_malone = True
        view = create_view(self.dsp, '+index')
        self.assertTrue(view.bugs_answers_usage['uses_bugs'])
        self.assertFalse(view.bugs_answers_usage['uses_answers'])
        self.assertFalse(view.bugs_answers_usage['uses_both'])
        self.assertTrue(view.bugs_answers_usage['uses_either'])

    def test_bugs_answers_usage_answers(self):
        # The dict values are True for answers and either.
        with celebrity_logged_in('admin'):
            self.dsp.distribution.answers_usage = ServiceUsage.LAUNCHPAD
        view = create_view(self.dsp, '+index')
        self.assertFalse(view.bugs_answers_usage['uses_bugs'])
        self.assertTrue(view.bugs_answers_usage['uses_answers'])
        self.assertFalse(view.bugs_answers_usage['uses_both'])
        self.assertIs(True, view.bugs_answers_usage['uses_either'])

    def test_bugs_answers_usage_both(self):
        # The dict values are all True.
        with celebrity_logged_in('admin'):
            self.dsp.distribution.official_malone = True
            self.dsp.distribution.answers_usage = ServiceUsage.LAUNCHPAD
        view = create_view(self.dsp, '+index')
        self.assertTrue(view.bugs_answers_usage['uses_bugs'])
        self.assertTrue(view.bugs_answers_usage['uses_answers'])
        self.assertTrue(view.bugs_answers_usage['uses_both'])
        self.assertTrue(view.bugs_answers_usage['uses_either'])

    def test_new_bugtasks_count(self):
        self.factory.makeBugTask(target=self.dsp)
        view = create_view(self.dsp, '+index')
        self.assertEqual(1, view.new_bugtasks_count)
