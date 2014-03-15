# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for source package publication listing."""

__metaclass__ = type

import soupmatchers
from testtools.matchers import (
    Contains,
    MatchesAll,
    )
from zope.app.testing.functional import HTTPCaller
from zope.component import getUtility
from zope.publisher.interfaces import NotFound
from zope.security.interfaces import Unauthorized

from lp.registry.interfaces.person import IPersonSet
from lp.services.webapp.publisher import (
    canonical_url,
    RedirectionView,
    )
from lp.soyuz.browser.publishing import (
    SourcePackagePublishingHistoryNavigation,
    )
from lp.soyuz.enums import PackagePublishingStatus
from lp.soyuz.interfaces.archive import ArchivePurpose
from lp.soyuz.tests.test_publishing import SoyuzTestPublisher
from lp.testing import (
    BrowserTestCase,
    FakeLaunchpadRequest,
    logout,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import LaunchpadFunctionalLayer
from lp.testing.sampledata import ADMIN_EMAIL


class TestSourcePublicationListingExtra(BrowserTestCase):
    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestSourcePublicationListingExtra, self).setUp()
        self.admin = getUtility(IPersonSet).getByEmail(ADMIN_EMAIL)
        # Create everything we need to create builds, such as a
        # DistroArchSeries and a builder.
        self.processor = self.factory.makeProcessor()
        self.distroseries = self.factory.makeDistroSeries()
        self.das = self.factory.makeDistroArchSeries(
            distroseries=self.distroseries, processor=self.processor,
            supports_virtualized=True)
        self.archive = self.factory.makeArchive(
            distribution=self.distroseries.distribution)
        with person_logged_in(self.admin):
            self.publisher = SoyuzTestPublisher()
            self.publisher.prepareBreezyAutotest()
            self.distroseries.nominatedarchindep = self.das
            self.publisher.addFakeChroots(distroseries=self.distroseries)
            self.builder = self.factory.makeBuilder(processor=self.processor)

    def test_view_with_source_package_recipe(self):
        # When a SourcePackageRelease is linked to a
        # SourcePackageRecipeBuild, the view shows which recipe was
        # responsible for creating the SPR.
        sprb = self.factory.makeSourcePackageRecipeBuild(
            archive=self.archive)
        recipe = sprb.recipe
        requester = sprb.requester
        spph = self.publisher.getPubSource(
            archive=self.archive, status=PackagePublishingStatus.PUBLISHED)
        spph.sourcepackagerelease.source_package_recipe_build = sprb
        recipe_link_matches = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                'link to build', 'a', attrs={'href': canonical_url(sprb)},
                text='Built'),
            soupmatchers.Tag(
                'recipe name', 'a', attrs={'href': canonical_url(recipe)},
                text=recipe.name),
            soupmatchers.Tag(
                'requester', 'a',
                attrs={
                    'href': canonical_url(requester)},
                text=requester.displayname))
        browser = self.getViewBrowser(spph, '+listing-archive-extra')
        self.assertThat(browser.contents, recipe_link_matches)

    def test_view_without_source_package_recipe(self):
        # And if a SourcePackageRelease is not linked, there is no sign of it
        # in the view.
        spph = self.publisher.getPubSource(
            archive=self.archive, status=PackagePublishingStatus.PUBLISHED)
        browser = self.getViewBrowser(spph, '+listing-archive-extra')
        self.assertNotIn('Built by recipe', browser.contents)

    def test_view_with_deleted_source_package_recipe(self):
        # If a SourcePackageRelease is linked to a deleted recipe, the text
        # 'deleted recipe' is displayed, rather than a link.
        sprb = self.factory.makeSourcePackageRecipeBuild(
            archive=self.archive)
        recipe = sprb.recipe
        requester = sprb.requester
        spph = self.publisher.getPubSource(
            archive=self.archive, status=PackagePublishingStatus.PUBLISHED)
        spph.sourcepackagerelease.source_package_recipe_build = sprb
        with person_logged_in(recipe.owner):
            recipe.destroySelf()
        recipe_link_matches = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                'link to build', 'a',
                attrs={'href': canonical_url(sprb)},
                text='Built'),
            soupmatchers.Tag(
                'requester', 'a',
                attrs={
                    'href': canonical_url(requester)},
                text=requester.displayname))
        browser = self.getViewBrowser(spph, '+listing-archive-extra')
        self.assertThat(browser.contents, recipe_link_matches)
        self.assertIn('deleted recipe', browser.contents)


class TestSourcePackagePublishingHistoryNavigation(TestCaseWithFactory):
    layer = LaunchpadFunctionalLayer

    def traverse(self, spph, segments):
        req = FakeLaunchpadRequest([], segments[1:])
        nav = SourcePackagePublishingHistoryNavigation(spph, req)
        return nav.publishTraverse(req, segments[0])

    def makeSPPHWithChangelog(self, archive=None):
        lfa = self.factory.makeLibraryFileAlias(
            filename='changelog',
            restricted=(archive is not None and archive.private))
        spr = self.factory.makeSourcePackageRelease(changelog=lfa)
        return self.factory.makeSourcePackagePublishingHistory(
            archive=archive,
            sourcepackagerelease=spr)

    def test_changelog(self):
        # SPPH.SPR.changelog is accessible at +files/changelog.
        spph = self.makeSPPHWithChangelog()
        view = self.traverse(spph, ['+files', 'changelog'])
        self.assertIsInstance(view, RedirectionView)
        self.assertEqual(
            spph.sourcepackagerelease.changelog.http_url, view.target)

    def test_private_changelog(self):
        # Private changelogs are inaccessible to anonymous users.
        archive = self.factory.makeArchive(
            purpose=ArchivePurpose.PPA, private=True)
        spph = self.makeSPPHWithChangelog(archive=archive)

        # A normal user can't traverse to the changelog.
        self.assertRaises(
            Unauthorized, self.traverse, spph, ['+files', 'changelog'])

        # But the archive owner gets a librarian URL with a token.
        with person_logged_in(archive.owner):
            view = self.traverse(spph, ['+files', 'changelog'])
        self.assertThat(view.target, Contains('?token='))

    def test_unhandled_name(self):
        # Unhandled names raise a NotFound.
        spph = self.factory.makeSourcePackagePublishingHistory()
        self.assertRaises(
            NotFound, self.traverse, spph, ['+files', 'not-changelog'])

    def test_registered(self):
        # The Navigation is registered and traversable over HTTP.
        spph = self.makeSPPHWithChangelog()
        lfa_url = spph.sourcepackagerelease.changelog.http_url
        redir_url = (
            canonical_url(spph, path_only_if_possible=True)
            + '/+files/changelog')
        logout()
        response = str(HTTPCaller()("GET %s HTTP/1.1\n\n" % redir_url))
        self.assertThat(
            response,
            MatchesAll(
                Contains("HTTP/1.1 303 See Other"),
                Contains("Location: %s" % lfa_url)))
