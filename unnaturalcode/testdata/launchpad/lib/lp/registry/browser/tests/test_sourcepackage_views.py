# Copyright 2010-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for SourcePackage view code."""

__metaclass__ = type

import cgi
import urllib

from soupmatchers import (
    HTMLContains,
    Tag,
    )
from testtools.matchers import Not
from testtools.testcase import ExpectedException
from zope.component import getUtility
from zope.interface import implements
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.registry.browser.sourcepackage import (
    get_register_upstream_url,
    PackageUpstreamTracking,
    SourcePackageOverviewMenu,
    )
from lp.registry.interfaces.distribution import IDistribution
from lp.registry.interfaces.distroseries import (
    IDistroSeries,
    IDistroSeriesSet,
    )
from lp.registry.interfaces.sourcepackage import ISourcePackage
from lp.soyuz.tests.test_publishing import SoyuzTestPublisher
from lp.testing import (
    BrowserTestCase,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.pages import find_tag_by_id
from lp.testing.views import create_initialized_view


class TestSourcePackageViewHelpers(TestCaseWithFactory):
    """Tests for SourcePackage view helper functions."""

    layer = DatabaseFunctionalLayer

    def _makePublishedSourcePackage(self):
        test_publisher = SoyuzTestPublisher()
        test_data = test_publisher.makeSourcePackageSummaryData()
        source_package_name = (
            test_data['source_package'].sourcepackagename.name)
        distroseries_id = test_data['distroseries'].id
        test_publisher.updateDistroSeriesPackageCache(
            test_data['distroseries'])

        # updateDistroSeriesPackageCache reconnects the db, so the
        # objects need to be reloaded.
        distroseries = getUtility(IDistroSeriesSet).get(distroseries_id)
        return distroseries.getSourcePackage(source_package_name)

    def assertInQueryString(self, url, field, value):
        base, query = urllib.splitquery(url)
        params = cgi.parse_qsl(query)
        self.assertTrue((field, value) in params)

    def test_get_register_upstream_url_fields(self):
        distroseries = self.factory.makeDistroSeries(
            distribution=self.factory.makeDistribution(name='zoobuntu'),
            name='walrus')
        source_package = self.factory.makeSourcePackage(
            distroseries=distroseries,
            sourcepackagename='python-super-package')
        url = get_register_upstream_url(source_package)
        base, query = urllib.splitquery(url)
        self.assertEqual('/projects/+new', base)
        params = cgi.parse_qsl(query)
        expected_params = [
            ('_return_url',
             'http://launchpad.dev/zoobuntu/walrus/'
             '+source/python-super-package'),
            ('field.__visited_steps__', 'projectaddstep1'),
            ('field.actions.continue', 'Continue'),
            ('field.displayname', 'Python Super Package'),
            ('field.distroseries', 'zoobuntu/walrus'),
            ('field.name', 'python-super-package'),
            ('field.source_package_name', 'python-super-package'),
            ('field.title', 'Python Super Package'),
            ]
        self.assertEqual(expected_params, params)

    def test_get_register_upstream_url_displayname(self):
        # The sourcepackagename 'python-super-package' is split on
        # the hyphens, and each word is capitalized.
        distroseries = self.factory.makeDistroSeries(
            distribution=self.factory.makeDistribution(name='zoobuntu'),
            name='walrus')
        source_package = self.factory.makeSourcePackage(
            distroseries=distroseries,
            sourcepackagename='python-super-package')
        url = get_register_upstream_url(source_package)
        self.assertInQueryString(
            url, 'field.displayname', 'Python Super Package')

    def test_get_register_upstream_url_summary(self):
        source_package = self._makePublishedSourcePackage()
        url = get_register_upstream_url(source_package)
        self.assertInQueryString(
            url, 'field.summary',
            'summary for flubber-bin\nsummary for flubber-lib')

    def test_get_register_upstream_url_summary_duplicates(self):

        class Faker:
            # Fakes attributes easily.
            def __init__(self, **kw):
                self.__dict__.update(kw)

        class FakeSourcePackage(Faker):
            # Interface necessary for canonical_url() call in
            # get_register_upstream_url().
            implements(ISourcePackage)

        class FakeDistroSeries(Faker):
            implements(IDistroSeries)

        class FakeDistribution(Faker):
            implements(IDistribution)

        releases = Faker(sample_binary_packages=[
            Faker(summary='summary for foo'),
            Faker(summary='summary for bar'),
            Faker(summary='summary for baz'),
            Faker(summary='summary for baz'),
            ])
        source_package = FakeSourcePackage(
            name='foo',
            sourcepackagename=Faker(name='foo'),
            distroseries=FakeDistroSeries(
                name='walrus',
                distribution=FakeDistribution(name='zoobuntu')),
            releases=[releases],
            currentrelease=Faker(homepage=None),
            )
        url = get_register_upstream_url(source_package)
        self.assertInQueryString(
            url, 'field.summary',
            'summary for bar\nsummary for baz\nsummary for foo')

    def test_get_register_upstream_url_homepage(self):
        source_package = self._makePublishedSourcePackage()
        # SourcePackageReleases cannot be modified by users.
        removeSecurityProxy(
            source_package.currentrelease).homepage = 'http://eg.dom/bonkers'
        url = get_register_upstream_url(source_package)
        self.assertInQueryString(
            url, 'field.homepageurl', 'http://eg.dom/bonkers')


class TestSourcePackageView(BrowserTestCase):

    layer = DatabaseFunctionalLayer

    def test_register_upstream_forbids_proprietary(self):
        # Cannot specify information_type if registering for sourcepackage.
        sourcepackage = self.factory.makeSourcePackage()
        browser = self.getViewBrowser(sourcepackage)
        browser.getControl("Register the upstream project").click()
        browser.getControl("Link to Upstream Project").click()
        browser.getControl("Summary").value = "summary"
        browser.getControl("Continue").click()
        t = Tag('info_type', 'input', attrs={'name': 'field.information_type'})
        self.assertThat(browser.contents, Not(HTMLContains(t)))

    def test_link_upstream_handles_initial_proprietary(self):
        # Proprietary product is not listed as an option.
        owner = self.factory.makePerson()
        sourcepackage = self.factory.makeSourcePackage()
        product_name = sourcepackage.name
        product_displayname = self.factory.getUniqueString()
        self.factory.makeProduct(
            name=product_name, owner=owner,
            information_type=InformationType.PROPRIETARY,
            displayname=product_displayname)
        browser = self.getViewBrowser(sourcepackage, user=owner)
        with ExpectedException(LookupError):
            browser.getControl(product_displayname)

    def test_link_upstream_handles_proprietary(self):
        # Proprietary products produce an 'invalid value' error.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(owner=owner)
        product_name = product.name
        product_displayname = product.displayname
        sourcepackage = self.factory.makeSourcePackage(
            sourcepackagename=product_name)
        with person_logged_in(None):
            browser = self.getViewBrowser(sourcepackage, user=owner)
            with person_logged_in(owner):
                product.information_type = InformationType.PROPRIETARY
            browser.getControl(product_displayname).click()
            browser.getControl("Link to Upstream Project").click()
        error = Tag(
            'error', 'div', attrs={'class': 'message'},
            text='Invalid value')
        self.assertThat(browser.contents, HTMLContains(error))
        self.assertNotIn(
            'The project %s was linked to this source package.' %
            str(product_displayname), browser.contents)


class TestSourcePackageUpstreamConnectionsView(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestSourcePackageUpstreamConnectionsView, self).setUp()
        productseries = self.factory.makeProductSeries(name='1.0')
        self.milestone = self.factory.makeMilestone(
            product=productseries.product, productseries=productseries)
        distroseries = self.factory.makeDistroSeries()
        self.source_package = self.factory.makeSourcePackage(
            distroseries=distroseries, sourcepackagename='fnord')
        self.factory.makeSourcePackagePublishingHistory(
            sourcepackagename=self.source_package.sourcepackagename,
            distroseries=distroseries, version='1.5-0ubuntu1')
        self.source_package.setPackaging(
            productseries, productseries.product.owner)

    def makeUpstreamRelease(self, version):
        with person_logged_in(self.milestone.productseries.product.owner):
            self.milestone.name = version
            self.factory.makeProductRelease(self.milestone)

    def assertId(self, view, id_):
        element = find_tag_by_id(view.render(), id_)
        self.assertTrue(element is not None)

    def test_current_release_tracking_none(self):
        view = create_initialized_view(
            self.source_package, name='+upstream-connections')
        self.assertEqual(
            PackageUpstreamTracking.NONE, view.current_release_tracking)
        self.assertId(view, 'no-upstream-version')

    def test_current_release_tracking_current(self):
        self.makeUpstreamRelease('1.5')
        view = create_initialized_view(
            self.source_package, name='+upstream-connections')
        self.assertEqual(
            PackageUpstreamTracking.CURRENT, view.current_release_tracking)
        self.assertId(view, 'current-upstream-version')

    def test_current_release_tracking_older(self):
        self.makeUpstreamRelease('1.4')
        view = create_initialized_view(
            self.source_package, name='+upstream-connections')
        self.assertEqual(
            PackageUpstreamTracking.OLDER, view.current_release_tracking)
        self.assertId(view, 'older-upstream-version')

    def test_current_release_tracking_newer(self):
        self.makeUpstreamRelease('1.6')
        view = create_initialized_view(
            self.source_package, name='+upstream-connections')
        self.assertEqual(
            PackageUpstreamTracking.NEWER, view.current_release_tracking)
        self.assertId(view, 'newer-upstream-version')


class TestSourcePackagePackagingLinks(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def makeSourcePackageOverviewMenu(self, with_packaging, karma=None):
        sourcepackage = self.factory.makeSourcePackage()
        registrant = self.factory.makePerson()
        if with_packaging:
            self.factory.makePackagingLink(
                sourcepackagename=sourcepackage.sourcepackagename,
                distroseries=sourcepackage.distroseries, owner=registrant)
        user = self.factory.makePerson(karma=karma)
        with person_logged_in(user):
            menu = SourcePackageOverviewMenu(sourcepackage)
        return menu, user

    def test_edit_packaging_link__enabled_without_packaging(self):
        # If no packging exists, the edit_packaging link is always
        # enabled.
        menu, user = self.makeSourcePackageOverviewMenu(False, None)
        with person_logged_in(user):
            self.assertTrue(menu.edit_packaging().enabled)

    def test_set_upstrem_link__enabled_without_packaging(self):
        # If no packging exists, the set_upstream link is always
        # enabled.
        menu, user = self.makeSourcePackageOverviewMenu(False, None)
        with person_logged_in(user):
            self.assertTrue(menu.set_upstream().enabled)

    def test_remove_packaging_link__enabled_without_packaging(self):
        # If no packging exists, the remove_packaging link is always
        # enabled.
        menu, user = self.makeSourcePackageOverviewMenu(False, None)
        with person_logged_in(user):
            self.assertTrue(menu.remove_packaging().enabled)

    def test_edit_packaging_link__enabled_with_packaging_non_probation(self):
        # If a packging exists, the edit_packaging link is enabled
        # for the non-probationary users.
        menu, user = self.makeSourcePackageOverviewMenu(True, 100)
        with person_logged_in(user):
            self.assertTrue(menu.edit_packaging().enabled)

    def test_set_upstrem_link__enabled_with_packaging_non_probation(self):
        # If a packging exists, the set_upstream link is enabled
        # for the non-probationary users.
        menu, user = self.makeSourcePackageOverviewMenu(True, 100)
        with person_logged_in(user):
            self.assertTrue(menu.set_upstream().enabled)

    def test_remove_packaging_link__enabled_with_packaging_non_probation(self):
        # If a packging exists, the remove_packaging link is enabled
        # for the non-probationary users.
        menu, user = self.makeSourcePackageOverviewMenu(True, 100)
        with person_logged_in(user):
            self.assertTrue(menu.remove_packaging().enabled)

    def test_edit_packaging_link__enabled_with_packaging_probation(self):
        # If a packging exists, the edit_packaging link is not enabled
        # for probationary users.
        menu, user = self.makeSourcePackageOverviewMenu(True, None)
        with person_logged_in(user):
            self.assertFalse(menu.edit_packaging().enabled)

    def test_set_upstrem_link__enabled_with_packaging_probation(self):
        # If a packging exists, the set_upstream link is not enabled
        # for probationary users.
        menu, user = self.makeSourcePackageOverviewMenu(True, None)
        with person_logged_in(user):
            self.assertFalse(menu.set_upstream().enabled)

    def test_remove_packaging_link__enabled_with_packaging_probation(self):
        # If a packging exists, the remove_packaging link is not enabled
        # for probationary users.
        menu, user = self.makeSourcePackageOverviewMenu(True, None)
        with person_logged_in(user):
            self.assertFalse(menu.remove_packaging().enabled)


class TestSourcePackageChangeUpstreamView(BrowserTestCase):

    layer = DatabaseFunctionalLayer

    def test_error_on_proprietary_product(self):
        """Packaging cannot be created for PROPRIETARY products"""
        product_owner = self.factory.makePerson()
        product_name = 'proprietary-product'
        self.factory.makeProduct(
            name=product_name, owner=product_owner,
            information_type=InformationType.PROPRIETARY)
        ubuntu_series = self.factory.makeUbuntuDistroSeries()
        sp = self.factory.makeSourcePackage(distroseries=ubuntu_series)
        browser = self.getViewBrowser(
            sp, '+edit-packaging', user=product_owner)
        browser.getControl('Project').value = product_name
        browser.getControl('Continue').click()
        self.assertIn(
            'Only Public projects can be packaged, not Proprietary.',
            browser.contents)

    def test_error_on_proprietary_productseries(self):
        """Packaging cannot be created for PROPRIETARY productseries"""
        product_owner = self.factory.makePerson()
        product_name = 'proprietary-product'
        product = self.factory.makeProduct(
            name=product_name, owner=product_owner)
        series = self.factory.makeProductSeries(product=product)
        series_displayname = series.displayname
        ubuntu_series = self.factory.makeUbuntuDistroSeries()
        sp = self.factory.makeSourcePackage(distroseries=ubuntu_series)
        browser = self.getViewBrowser(
            sp, '+edit-packaging', user=product_owner)
        browser.getControl('Project').value = product_name
        browser.getControl('Continue').click()
        with person_logged_in(product_owner):
            product.information_type = InformationType.PROPRIETARY
        browser.getControl(series_displayname).selected = True
        browser.getControl('Change').click()
        self.assertIn(
            'Only Public projects can be packaged, not Proprietary.',
            browser.contents)
