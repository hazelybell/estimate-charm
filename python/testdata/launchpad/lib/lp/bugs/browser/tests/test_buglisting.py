# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

import os

from soupmatchers import (
    HTMLContains,
    Tag,
    )
from zope.component import getUtility

from lp.app.enums import InformationType
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.services.features.testing import FeatureFixture
from lp.services.webapp.publisher import canonical_url
from lp.testing import (
    BrowserTestCase,
    login_person,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.pages import (
    extract_text,
    find_main_content,
    find_tag_by_id,
    find_tags_by_class,
    )
from lp.testing.views import (
    create_initialized_view,
    create_view,
    )


class TestBugTaskSearchListingPage(BrowserTestCase):

    layer = DatabaseFunctionalLayer

    def _makeDistributionSourcePackage(self):
        distro = self.factory.makeDistribution('test-distro')
        return self.factory.makeDistributionSourcePackage('test-dsp', distro)

    def test_distributionsourcepackage_unknown_bugtracker_message(self):
        # A DistributionSourcePackage whose Distro does not use
        # Launchpad for bug tracking should explain that.
        dsp = self._makeDistributionSourcePackage()
        url = canonical_url(dsp, rootsite='bugs')
        browser = self.getUserBrowser(url)
        top_portlet = find_tags_by_class(
            browser.contents, 'top-portlet')
        self.assertTrue(len(top_portlet) > 0,
                        "Tag with class=top-portlet not found")
        self.assertTextMatchesExpressionIgnoreWhitespace("""
            test-dsp in Test-distro does not use Launchpad for bug tracking.
            Getting started with bug tracking in Launchpad.""",
            extract_text(top_portlet[0]))

    def test_distributionsourcepackage_unknown_bugtracker_no_button(self):
        # A DistributionSourcePackage whose Distro does not use
        # Launchpad for bug tracking should not show the "Report a bug"
        # button.
        dsp = self._makeDistributionSourcePackage()
        url = canonical_url(dsp, rootsite='bugs')
        browser = self.getUserBrowser(url)
        self.assertIs(None, find_tag_by_id(browser.contents, 'involvement'),
                      "Involvement portlet with Report-a-bug button should "
                      "not be shown")

    def test_distributionsourcepackage_unknown_bugtracker_no_filters(self):
        # A DistributionSourcePackage whose Distro does not use
        # Launchpad for bug tracking should not show links to "New
        # bugs", "Open bugs", etc.
        dsp = self._makeDistributionSourcePackage()
        url = canonical_url(dsp, rootsite='bugs')
        browser = self.getUserBrowser(url)
        self.assertIs(None,
                      find_tag_by_id(browser.contents, 'portlet-bugfilters'),
                      "portlet-bugfilters should not be shown.")

    def test_distributionsourcepackage_unknown_bugtracker_no_tags(self):
        # A DistributionSourcePackage whose Distro does not use
        # Launchpad for bug tracking should not show links to search by
        # bug tags.
        dsp = self._makeDistributionSourcePackage()
        url = canonical_url(dsp, rootsite='bugs')
        browser = self.getUserBrowser(url)
        self.assertIs(None, find_tag_by_id(browser.contents, 'portlet-tags'),
                      "portlet-tags should not be shown.")

    def _makeSourcePackage(self):
        distro = self.factory.makeDistribution('test-distro')
        self.factory.makeDistroSeries(distribution=distro, name='test-series')
        return self.factory.makeSourcePackage('test-sp', distro.currentseries)

    def test_sourcepackage_unknown_bugtracker_message(self):
        # A SourcePackage whose Distro does not use
        # Launchpad for bug tracking should explain that.
        sp = self._makeSourcePackage()
        url = canonical_url(sp, rootsite='bugs')
        browser = self.getUserBrowser(url)
        top_portlet = find_tags_by_class(
            browser.contents, 'top-portlet')
        self.assertTrue(len(top_portlet) > 0,
                        "Tag with class=top-portlet not found")
        self.assertTextMatchesExpressionIgnoreWhitespace("""
            test-sp in Test-distro Test-series does not
            use Launchpad for bug tracking.
            Getting started with bug tracking in Launchpad.""",
            extract_text(top_portlet[0]))

    def test_sourcepackage_unknown_bugtracker_no_button(self):
        # A SourcePackage whose Distro does not use Launchpad for bug
        # tracking should not show the "Report a bug" button.
        sp = self._makeSourcePackage()
        url = canonical_url(sp, rootsite='bugs')
        browser = self.getUserBrowser(url)
        self.assertIs(None, find_tag_by_id(browser.contents, 'involvement'),
                      "Involvement portlet with Report-a-bug button should "
                      "not be shown")

    def test_sourcepackage_unknown_bugtracker_no_filters(self):
        # A SourcePackage whose Distro does not use Launchpad for bug
        # tracking should not show links to "New bugs", "Open bugs",
        # etc.
        sp = self._makeSourcePackage()
        url = canonical_url(sp, rootsite='bugs')
        browser = self.getUserBrowser(url)
        self.assertIs(None,
                      find_tag_by_id(browser.contents, 'portlet-bugfilters'),
                      "portlet-bugfilters should not be shown.")

    def test_sourcepackage_unknown_bugtracker_no_tags(self):
        # A SourcePackage whose Distro does not use Launchpad for bug
        # tracking should not show links to search by bug tags.
        sp = self._makeSourcePackage()
        url = canonical_url(sp, rootsite='bugs')
        browser = self.getUserBrowser(url)
        self.assertIs(None,
                      find_tag_by_id(browser.contents, 'portlet-tags'),
                      "portlet-tags should not be shown.")

    def test_search_components_error(self):
        # Searching for using components for bug targets that are not a distro
        # or distroseries will report an error, but not OOPS.  See bug
        # 838957.
        product = self.factory.makeProduct()
        form = {
            'search': 'Search',
            'field.component': 1,
            'field.component-empty-marker': 1}
        with person_logged_in(product.owner):
            view = create_initialized_view(product, '+bugs', form=form)
        response = view.request.response
        self.assertEqual(1, len(response.notifications))
        expected = (
            "Search by component requires a context with "
            "a distribution or distroseries.")
        self.assertEqual(expected, response.notifications[0].message)
        self.assertEqual(
            canonical_url(product, rootsite='bugs', view_name='+bugs'),
            response.getHeader('Location'))

    def test_non_batch_template(self):
        # The correct template is used for non batch requests.
        product = self.factory.makeProduct()
        form = {'search': 'Search'}
        view = create_view(product, '+bugs', form=form)
        self.assertEqual(
            'buglisting-default.pt', os.path.basename(view.template.filename))

    def test_batch_template(self):
        # The correct template is used for batch requests.
        product = self.factory.makeProduct()
        form = {'search': 'Search'}
        view = create_view(
            product, '+bugs', form=form, query_string='batch_request=True')
        self.assertEqual(
            view.bugtask_table_template.filename, view.template.filename)

    def test_search_batch_request(self):
        # A search request with a 'batch_request' query parameter causes the
        # view to just render the next batch of results.
        product = self.factory.makeProduct()
        form = {'search': 'Search'}
        view = create_initialized_view(
            product, '+bugs', form=form, query_string='batch_request=True')
        content = view()
        self.assertIsNone(find_main_content(content))
        self.assertIsNotNone(
            find_tag_by_id(content, 'bugs-batch-links-upper'))

    def test_ajax_batch_navigation_feature_flag(self):
        # The Javascript to wire up the ajax batch navigation behavior is
        # correctly hidden behind a feature flag.
        product = self.factory.makeProduct()
        form = {'search': 'Search'}
        with person_logged_in(product.owner):
            product.official_malone = True
        flags = {u"ajax.batch_navigator.enabled": u"true"}
        with FeatureFixture(flags):
            view = create_initialized_view(product, '+bugs', form=form)
            self.assertTrue(
                'Y.lp.app.batchnavigator.BatchNavigatorHooks' in view())
        view = create_initialized_view(product, '+bugs', form=form)
        self.assertFalse(
            'Y.lp.app.batchnavigator.BatchNavigatorHooks' in view())

    def test_search_macro_title(self):
        # The title text is displayed for the macro `simple-search-form`.
        product = self.factory.makeProduct(
            displayname='Test Product', official_malone=True)
        view = create_initialized_view(product, '+bugs')
        self.assertEqual(
            'Search bugs in Test Product', view.search_macro_title)

        # The title is shown.
        form_title_matches = Tag(
            'Search form title', 'h3', text=view.search_macro_title)
        view = create_initialized_view(product, '+bugs')
        self.assertThat(view.render(), HTMLContains(form_title_matches))

    def test_search_macro_div_node_with_css_class(self):
        # The <div> enclosing the search form in the macro
        # `simple-search-form` has the CSS class "dynamic_bug_listing".
        product = self.factory.makeProduct(
            displayname='Test Product', official_malone=True)
        attributes = {
            'id': 'bugs-search-form',
            'class': 'dynamic_bug_listing',
            }
        search_div_with_class_attribute_matches = Tag(
            'Main search div', tag_type='div', attrs=attributes)
        view = create_initialized_view(product, '+bugs')
        self.assertThat(
            view.render(),
            HTMLContains(search_div_with_class_attribute_matches))

    def test_search_macro_css_for_form_node(self):
        # The <form> node has the CSS classes
        # "primary search dynamic_bug_listing".
        product = self.factory.makeProduct(
            displayname='Test Product', official_malone=True)
        attributes = {
            'name': 'search',
            'class': 'primary search dynamic_bug_listing',
            }
        search_form_matches = Tag(
            'Search form CSS classes', tag_type='form', attrs=attributes)
        view = create_initialized_view(product, '+bugs')
        self.assertThat(view.render(), HTMLContains(search_form_matches))


class BugTargetTestCase(TestCaseWithFactory):
    """Test helpers for setting up `IBugTarget` tests."""

    def _makeBugTargetProduct(self, bug_tracker=None, packaging=False,
                              product_name=None):
        """Return a product that may use Launchpad or an external bug tracker.

        bug_tracker may be None, 'launchpad', or 'external'.
        """
        product = self.factory.makeProduct(name=product_name)
        if bug_tracker is not None:
            with person_logged_in(product.owner):
                if bug_tracker == 'launchpad':
                    product.official_malone = True
                else:
                    product.bugtracker = self.factory.makeBugTracker()
        if packaging:
            self.factory.makePackagingLink(
                productseries=product.development_focus, in_ubuntu=True)
        return product


class TestBugTaskSearchListingViewProduct(BugTargetTestCase):

    layer = DatabaseFunctionalLayer

    def test_external_bugtracker_is_none(self):
        bug_target = self._makeBugTargetProduct()
        view = create_initialized_view(bug_target, '+bugs')
        self.assertEqual(None, view.external_bugtracker)

    def test_external_bugtracker(self):
        bug_target = self._makeBugTargetProduct(bug_tracker='external')
        view = create_initialized_view(bug_target, '+bugs')
        self.assertEqual(bug_target.bugtracker, view.external_bugtracker)

    def test_has_bugtracker_is_false(self):
        bug_target = self.factory.makeProduct()
        view = create_initialized_view(bug_target, '+bugs')
        self.assertEqual(False, view.has_bugtracker)

    def test_has_bugtracker_external_is_true(self):
        bug_target = self._makeBugTargetProduct(bug_tracker='external')
        user = self.factory.makePerson()
        view = create_initialized_view(bug_target, '+bugs', principal=user)
        self.assertEqual(True, view.has_bugtracker)
        markup = view.render()
        self.assertIsNone(find_tag_by_id(markup, 'bugs-search-form'))
        self.assertIsNone(find_tag_by_id(markup, 'bugs-table-listings'))

    def test_has_bugtracker_launchpad_is_true(self):
        bug_target = self._makeBugTargetProduct(bug_tracker='launchpad')
        view = create_initialized_view(bug_target, '+bugs')
        self.assertEqual(True, view.has_bugtracker)

    def test_product_without_packaging_also_in_ubuntu_is_none(self):
        bug_target = self._makeBugTargetProduct(bug_tracker='launchpad')
        login_person(bug_target.owner)
        view = create_initialized_view(
            bug_target, '+bugs', principal=bug_target.owner)
        self.assertEqual(None, find_tag_by_id(view(), 'also-in-ubuntu'))

    def test_product_with_packaging_also_in_ubuntu(self):
        bug_target = self._makeBugTargetProduct(
            bug_tracker='launchpad', packaging=True)
        login_person(bug_target.owner)
        view = create_initialized_view(
            bug_target, '+bugs', principal=bug_target.owner)
        content = find_tag_by_id(view.render(), 'also-in-ubuntu')
        link = canonical_url(
            bug_target.ubuntu_packages[0], force_local_path=True)
        self.assertEqual(link, content.a['href'])

    def test_product_index_title(self):
        bug_target = self._makeBugTargetProduct(
            bug_tracker='launchpad', product_name="testproduct")
        view = create_initialized_view(bug_target, '+bugs')
        self.assertEqual(u'Bugs : Testproduct', view.page_title)

    def test_ask_question_does_not_use_launchpad(self):
        bug_target = self._makeBugTargetProduct(
            bug_tracker='launchpad', packaging=True)
        login_person(bug_target.owner)
        bug_target.official_answers = False
        view = create_initialized_view(
            bug_target, '+bugs', principal=bug_target.owner)
        self.assertEqual(None, view.addquestion_url)

    def test_ask_question_uses_launchpad(self):
        bug_target = self._makeBugTargetProduct(
            bug_tracker='launchpad', packaging=True)
        login_person(bug_target.owner)
        bug_target.official_answers = True
        view = create_initialized_view(
            bug_target, '+bugs', principal=bug_target.owner)
        url = canonical_url(
            bug_target, rootsite='answers', view_name='+addquestion')
        self.assertEqual(url, view.addquestion_url)

    def test_upstream_project(self):
        # BugTaskSearchListingView.upstream_project and
        # BugTaskSearchListingView.upstream_launchpad_project are
        # None for all bug targets except SourcePackages
        # and DistributionSourcePackages.
        bug_target = self._makeBugTargetProduct(
            bug_tracker='launchpad', packaging=True)
        view = create_initialized_view(
            bug_target, '+bugs', principal=bug_target.owner)
        self.assertIs(None, view.upstream_project)
        self.assertIs(None, view.upstream_launchpad_project)


class TestBugTaskSearchListingViewDSP(BugTargetTestCase):

    layer = DatabaseFunctionalLayer

    def _getBugTarget(self, obj):
        """Return the `IBugTarget` under test.

        Return the object that was passed. Sub-classes can redefine
        this method.
        """
        return obj

    def test_package_with_upstream_launchpad_project(self):
        upstream_project = self._makeBugTargetProduct(
            bug_tracker='launchpad', packaging=True)
        login_person(upstream_project.owner)
        bug_target = self._getBugTarget(
            upstream_project.distrosourcepackages[0])
        view = create_initialized_view(
            bug_target, '+bugs', principal=upstream_project.owner)
        self.assertEqual(upstream_project, view.upstream_launchpad_project)
        self.assertEqual(upstream_project, view.upstream_project)
        content = find_tag_by_id(view.render(), 'also-in-upstream')
        link = canonical_url(upstream_project, rootsite='bugs')
        self.assertEqual(link, content.a['href'])

    def test_package_with_upstream_nonlaunchpad_project(self):
        upstream_project = self._makeBugTargetProduct(packaging=True)
        login_person(upstream_project.owner)
        bug_target = self._getBugTarget(
            upstream_project.distrosourcepackages[0])
        view = create_initialized_view(
            bug_target, '+bugs', principal=upstream_project.owner)
        self.assertEqual(None, view.upstream_launchpad_project)
        self.assertEqual(upstream_project, view.upstream_project)
        self.assertEqual(None, find_tag_by_id(view(), 'also-in-upstream'))

    def test_package_without_upstream_project(self):
        observer = self.factory.makePerson()
        dsp = self.factory.makeDistributionSourcePackage(
            'test-dsp', distribution=getUtility(ILaunchpadCelebrities).ubuntu)
        bug_target = self._getBugTarget(dsp)
        login_person(observer)
        view = create_initialized_view(
            bug_target, '+bugs', principal=observer)
        self.assertEqual(None, view.upstream_launchpad_project)
        self.assertEqual(None, view.upstream_project)
        self.assertEqual(None, find_tag_by_id(view(), 'also-in-upstream'))

    def test_filter_by_upstream_target(self):
        # If an upstream target is specified is the query parameters,
        # the corresponding flag in BugTaskSearchParams is set.
        upstream_project = self._makeBugTargetProduct(
            bug_tracker='launchpad', packaging=True)
        bug_target = self._getBugTarget(
            upstream_project.distrosourcepackages[0])
        form = {
            'search': 'Search',
            'advanced': 1,
            'field.upstream_target': upstream_project.name,
            }
        view = create_initialized_view(bug_target, '+bugs', form=form)
        search_params = view.buildSearchParams()
        self.assertEqual(upstream_project, search_params.upstream_target)


class TestBugTaskSearchListingViewSP(TestBugTaskSearchListingViewDSP):

        def _getBugTarget(self, dsp):
            """Return the current `ISourcePackage` for the dsp."""
            return dsp.development_version


class TestPersonBugListing(BrowserTestCase):
    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestPersonBugListing, self).setUp()
        self.user = self.factory.makePerson()
        self.private_product_owner = self.factory.makePerson()
        self.private_product = self.factory.makeProduct(
            owner=self.private_product_owner,
            information_type=InformationType.PROPRIETARY)

    def test_grant_for_bug_with_task_for_private_product(self):
        # A person's own bug page is correctly rendered when the person
        # is subscribed to a bug with a task for a propritary product.
        with person_logged_in(self.private_product_owner):
            bug = self.factory.makeBug(
                target=self.private_product, owner=self.private_product_owner)
            bug.subscribe(self.user, subscribed_by=self.private_product_owner)
        url = canonical_url(self.user, rootsite='bugs')
        # Just ensure that no exception occurs when the page is rendered.
        self.getUserBrowser(url, user=self.user)

    def test_grant_for_bug_with_task_for_private_product_series(self):
        # A person's own bug page is correctly rendered when the person
        # is subscribed to a bug with a task for a propritary product series.
        with person_logged_in(self.private_product_owner):
            series = self.factory.makeProductSeries(
                product=self.private_product)
            bug = self.factory.makeBug(
                target=self.private_product, series=series,
                owner=self.private_product_owner)
            bug.subscribe(self.user, subscribed_by=self.private_product_owner)
        url = canonical_url(self.user, rootsite='bugs')
        # Just ensure that no exception occurs when the page is rendered.
        self.getUserBrowser(url, user=self.user)

    def test_grant_for_bug_with_task_for_private_product_and_milestone(self):
        # A person's own bug page is correctly rendered when the person
        # is subscribed to a bug with a task for a propritary product and
        # a milestone.
        with person_logged_in(self.private_product_owner):
            milestone = self.factory.makeMilestone(
                product=self.private_product)
            bug = self.factory.makeBug(
                target=self.private_product, milestone=milestone,
                owner=self.private_product_owner)
            bug.subscribe(self.user, subscribed_by=self.private_product_owner)
        url = canonical_url(self.user, rootsite='bugs')
        # Just ensure that no exception occurs when the page is rendered.
        self.getUserBrowser(url, user=self.user)
