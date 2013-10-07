# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the product view classes and templates."""

__metaclass__ = type

from datetime import (
    datetime,
    timedelta,
    )

from mechanize import LinkNotFoundError
import pytz
from zope.component import getUtility

from lp.app.enums import (
    InformationType,
    ServiceUsage,
    )
from lp.code.enums import BranchType
from lp.code.interfaces.revision import IRevisionSet
from lp.code.publisher import CodeLayer
from lp.registry.enums import BranchSharingPolicy
from lp.services.webapp import canonical_url
from lp.testing import (
    ANONYMOUS,
    BrowserTestCase,
    login,
    login_person,
    logout,
    person_logged_in,
    TestCaseWithFactory,
    time_counter,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.pages import (
    extract_text,
    find_tag_by_id,
    )
from lp.testing.views import (
    create_initialized_view,
    create_view,
    )


class ProductTestBase(TestCaseWithFactory):
    """Common methods for tests herein."""
    layer = DatabaseFunctionalLayer

    def makeProductAndDevelopmentFocusBranch(self, **branch_args):
        """Make a product that has a development focus branch and return both.
        """
        email = self.factory.getUniqueEmailAddress()
        owner = self.factory.makePerson(email=email)
        product = self.factory.makeProduct(owner=owner)
        branch = self.factory.makeProductBranch(
            product=product, **branch_args)
        login(email)
        product.development_focus.branch = branch
        return product, branch


class TestProductCodeIndexView(ProductTestBase):
    """Tests for the product code home page."""

    def getBranchSummaryBrowseLinkForProduct(self, product):
        """Get the 'browse code' link from the product's code home.

        :raises Something: if the branch is not found.
        """
        browser = self.getUserBrowser(canonical_url(product, rootsite='code'))
        return browser.getLink('browse the source code')

    def assertProductBranchSummaryDoesNotHaveBrowseLink(self, product):
        """Assert there is not a browse code link on the product's code home.
        """
        try:
            self.getBranchSummaryBrowseLinkForProduct(product)
        except LinkNotFoundError:
            pass
        else:
            self.fail("Browse link present when it should not have been.")

    def test_browseable_branch_has_link(self):
        # If the product's development focus branch is browseable, there is a
        # 'browse code' link.
        product, branch = self.makeProductAndDevelopmentFocusBranch()
        branch.updateScannedDetails(self.factory.makeRevision(), 1)
        self.assertTrue(branch.code_is_browseable)

        link = self.getBranchSummaryBrowseLinkForProduct(product)
        login(ANONYMOUS)
        self.assertEqual(link.url, branch.browse_source_url)

    def test_unbrowseable_branch_does_not_have_link(self):
        # If the product's development focus branch is not browseable, there
        # is not a 'browse code' link.
        product, branch = self.makeProductAndDevelopmentFocusBranch()
        self.assertFalse(branch.code_is_browseable)

        self.assertProductBranchSummaryDoesNotHaveBrowseLink(product)

    def test_product_code_page_visible_with_private_dev_focus(self):
        # If a user cannot see the product's development focus branch but can
        # see at least one branch for the product they can still see the
        # +code-index page.
        product, branch = self.makeProductAndDevelopmentFocusBranch(
            information_type=InformationType.USERDATA)
        self.factory.makeProductBranch(product=product)
        # This is just "assertNotRaises"
        self.getUserBrowser(canonical_url(product, rootsite='code'))

    def test_initial_branches_contains_dev_focus_branch(self):
        product, branch = self.makeProductAndDevelopmentFocusBranch()
        view = create_initialized_view(
            product, '+code-index', rootsite='code')
        self.assertIn(branch, view.initial_branches)

    def test_initial_branches_does_not_contain_private_dev_focus_branch(self):
        product, branch = self.makeProductAndDevelopmentFocusBranch(
            information_type=InformationType.USERDATA)
        login(ANONYMOUS)
        view = create_initialized_view(
            product, '+code-index', rootsite='code')
        self.assertNotIn(branch, view.initial_branches)

    def test_committer_count_with_revision_authors(self):
        # Test that the code pathing for calling committer_count with
        # valid revision authors is truly tested.
        self.factory.makePerson(email='cthulu@example.com')
        product, branch = self.makeProductAndDevelopmentFocusBranch()
        date_generator = time_counter(
            datetime.now(pytz.UTC) - timedelta(days=30),
            timedelta(days=1))
        self.factory.makeRevisionsForBranch(
            branch, author='cthulu@example.com',
            date_generator=date_generator)
        getUtility(IRevisionSet).updateRevisionCacheForBranch(branch)

        view = create_initialized_view(product, '+code-index',
                                       rootsite='code')
        self.assertEqual(view.committer_count, 1)

    def test_committers_count_private_branch(self):
        # Test that calling committer_count will return the proper value
        # for a private branch.
        fsm = self.factory.makePerson(email='flyingpasta@example.com')
        product, branch = self.makeProductAndDevelopmentFocusBranch(
            owner=fsm, information_type=InformationType.USERDATA)
        date_generator = time_counter(
            datetime.now(pytz.UTC) - timedelta(days=30),
            timedelta(days=1))
        login_person(fsm)
        self.factory.makeRevisionsForBranch(
            branch, author='flyingpasta@example.com',
            date_generator=date_generator)
        getUtility(IRevisionSet).updateRevisionCacheForBranch(branch)

        view = create_initialized_view(product, '+code-index',
                                       rootsite='code', principal=fsm)
        self.assertEqual(view.committer_count, 1)

        commit_section = find_tag_by_id(view.render(), 'commits')
        self.assertIsNot(None, commit_section)

    def test_committers_count_private_branch_non_subscriber(self):
        # Test that calling committer_count will return the proper value
        # for a private branch.
        fsm = self.factory.makePerson(email='flyingpasta@example.com')
        product, branch = self.makeProductAndDevelopmentFocusBranch(
            owner=fsm, information_type=InformationType.USERDATA)
        date_generator = time_counter(
            datetime.now(pytz.UTC) - timedelta(days=30),
            timedelta(days=1))
        login_person(fsm)
        self.factory.makeRevisionsForBranch(
            branch, author='flyingpasta@example.com',
            date_generator=date_generator)
        getUtility(IRevisionSet).updateRevisionCacheForBranch(branch)

        observer = self.factory.makePerson()
        login_person(observer)
        view = create_initialized_view(product, '+code-index',
                                       rootsite='code', principal=observer)
        self.assertEqual(view.branch_count, 0)
        self.assertEqual(view.committer_count, 1)
        commit_section = find_tag_by_id(view.render(), 'commits')
        self.assertIs(None, commit_section)

    def test_initial_branches_contains_push_instructions(self):
        product, branch = self.makeProductAndDevelopmentFocusBranch()
        view = create_initialized_view(
            product, '+code-index', rootsite='code', principal=product.owner)
        content = view()
        self.assertIn('bzr push lp:~', content)

    def test_product_code_index_with_private_imported_branch(self):
        # Product:+code-index will not crash if the devfoocs is a private
        # imported branch.
        product, branch = self.makeProductAndDevelopmentFocusBranch(
            information_type=InformationType.USERDATA,
            branch_type=BranchType.IMPORTED)
        user = self.factory.makePerson()
        with person_logged_in(user):
            view = create_initialized_view(
                product, '+code-index', rootsite='code', principal=user)
            html = view()
        expected = 'There are no branches for %s' % product.displayname
        self.assertIn(expected, html)


class TestProductCodeIndexServiceUsages(ProductTestBase, BrowserTestCase):
    """Tests for the product code page, especially the usage messasges."""

    def test_external_imported(self):
        # A product with an imported development focus branch should say so,
        # and should display the upstream information along with the LP info.
        product = self.factory.makeProduct()
        code_import = self.factory.makeProductCodeImport(
            svn_branch_url='http://svn.example.org/branch')
        login_person(product.owner)
        product.development_focus.branch = code_import.branch
        self.assertEqual(ServiceUsage.EXTERNAL, product.codehosting_usage)
        product_url = canonical_url(product, rootsite='code')
        logout()
        browser = self.getUserBrowser(product_url)
        login(ANONYMOUS)
        content = find_tag_by_id(browser.contents, 'external')
        text = extract_text(content)
        expected = ("%(product_title)s hosts its code at %(branch_url)s. "
            "Launchpad imports the master branch and you can create "
            "branches from it." % dict(
                product_title=product.title,
                branch_url=code_import.url))
        self.assertTextMatchesExpressionIgnoreWhitespace(expected, text)

    def test_external_mirrored(self):
        # A mirrored branch says code is hosted externally, and displays
        # upstream data.
        product, branch = self.makeProductAndDevelopmentFocusBranch(
            branch_type=BranchType.MIRRORED,
            url="http://example.com/mybranch")
        self.assertEqual(ServiceUsage.EXTERNAL, product.codehosting_usage)
        browser = self.getUserBrowser(canonical_url(product, rootsite='code'))
        login(ANONYMOUS)
        content = find_tag_by_id(browser.contents, 'external')
        text = extract_text(content)
        expected = ("%(product_title)s hosts its code at %(branch_url)s.  "
                    "Launchpad has a mirror of the master branch "
                    "and you can create branches from it." % dict(
                        product_title=product.title,
                        branch_url=branch.url))
        self.assertTextMatchesExpressionIgnoreWhitespace(expected, text)

        # The code page should set not robots to noindex, nofollow.
        meta_string = '<meta name="robots" content="noindex,nofollow" />'
        self.assertNotIn(meta_string, browser.contents)

    def test_external_remote(self):
        # A remote branch says code is hosted externally, and displays
        # upstream data.
        product, branch = self.makeProductAndDevelopmentFocusBranch(
            branch_type=BranchType.REMOTE, url="http://example.com/mybranch")
        self.assertEqual(ServiceUsage.EXTERNAL, product.codehosting_usage)
        browser = self.getUserBrowser(canonical_url(product, rootsite='code'))
        login(ANONYMOUS)
        content = find_tag_by_id(browser.contents, 'external')
        text = extract_text(content)
        expected = ("%(product_title)s hosts its code at %(branch_url)s.  "
                    "Launchpad does not have a copy of the remote "
                    "branch." % dict(
                        product_title=product.title,
                        branch_url=branch.url))
        self.assertTextMatchesExpressionIgnoreWhitespace(expected, text)

        # The code page does not set robots to noindex, nofollow.
        meta_string = '<meta name="robots" content="noindex,nofollow" />'
        self.assertNotIn(meta_string, browser.contents)

    def test_unknown(self):
        # A product with no branches should tell the user that Launchpad
        # doesn't know where the code is hosted.
        product = self.factory.makeProduct()
        self.assertEqual(ServiceUsage.UNKNOWN, product.codehosting_usage)
        browser = self.getUserBrowser(canonical_url(product, rootsite='code'))
        login(ANONYMOUS)
        content = find_tag_by_id(browser.contents, 'unknown')
        text = extract_text(content)
        expected = (
            "Launchpad does not know where %(product_title)s "
            "hosts its code.*" %
            dict(product_title=product.title))
        self.assertTextMatchesExpressionIgnoreWhitespace(expected, text)

        # The code page sets robots to noindex, nofollow.
        meta_string = '<meta name="robots" content="noindex,nofollow" />'
        self.assertIn(meta_string, browser.contents)

    def test_on_launchpad(self):
        # A product that hosts its code on Launchpad just shows the branches.
        product, branch = self.makeProductAndDevelopmentFocusBranch()
        self.assertEqual(ServiceUsage.LAUNCHPAD, product.codehosting_usage)
        browser = self.getUserBrowser(canonical_url(product, rootsite='code'))
        login(ANONYMOUS)
        text = extract_text(find_tag_by_id(
            browser.contents, 'branch-count-summary'))
        expected = ("%s has 1 active branch owned by 1"
                    " person." % product.displayname)
        self.assertTextMatchesExpressionIgnoreWhitespace(expected, text)

        # The code page does not set robots to noindex, nofollow.
        meta_string = '<meta name="robots" content="noindex,nofollow" />'
        self.assertNotIn(meta_string, browser.contents)

    def test_view_mirror_location(self):
        # Mirrors show the correct upstream url as the mirror location.
        url = "http://example.com/mybranch"
        product, branch = self.makeProductAndDevelopmentFocusBranch(
            branch_type=BranchType.MIRRORED, url=url)
        view = create_initialized_view(product, '+code-index', rootsite='code')
        self.assertEqual(url, view.mirror_location)


class TestProductBranchesViewPortlets(ProductTestBase, BrowserTestCase):
    """Tests for the portlets."""

    def test_portlet_not_shown_for_UNKNOWN(self):
        # If the BranchUsage is UNKNOWN then the portlets are not shown.
        product = self.factory.makeProduct()
        self.assertEqual(ServiceUsage.UNKNOWN, product.codehosting_usage)
        browser = self.getUserBrowser(canonical_url(product, rootsite='code'))
        contents = browser.contents
        self.assertIs(None, find_tag_by_id(contents, 'branch-portlet'))
        self.assertIs(None, find_tag_by_id(contents, 'privacy'))
        self.assertIs(None, find_tag_by_id(contents, 'involvement'))
        self.assertIs(None, find_tag_by_id(
            contents, 'portlet-product-codestatistics'))

    def test_portlets_shown_for_HOSTED(self):
        # If the BranchUsage is HOSTED then the portlets are shown.
        product, branch = self.makeProductAndDevelopmentFocusBranch()
        self.assertEqual(ServiceUsage.LAUNCHPAD, product.codehosting_usage)
        browser = self.getUserBrowser(canonical_url(product, rootsite='code'))
        contents = browser.contents
        self.assertIsNot(None, find_tag_by_id(contents, 'branch-portlet'))
        self.assertIsNot(None, find_tag_by_id(contents, 'privacy'))
        self.assertIsNot(None, find_tag_by_id(contents, 'involvement'))
        self.assertIsNot(None, find_tag_by_id(
            contents, 'portlet-product-codestatistics'))

    def test_portlets_shown_for_EXTERNAL(self):
        # If the BranchUsage is EXTERNAL then the portlets are shown.
        url = "http://example.com/mybranch"
        product, branch = self.makeProductAndDevelopmentFocusBranch(
            branch_type=BranchType.MIRRORED, url=url)
        browser = self.getUserBrowser(canonical_url(product, rootsite='code'))
        contents = browser.contents
        self.assertIsNot(None, find_tag_by_id(contents, 'branch-portlet'))
        self.assertIsNot(None, find_tag_by_id(contents, 'privacy'))
        self.assertIsNot(None, find_tag_by_id(contents, 'involvement'))
        self.assertIsNot(None, find_tag_by_id(
            contents, 'portlet-product-codestatistics'))

    def test_is_private(self):
        product = self.factory.makeProduct(
            branch_sharing_policy=BranchSharingPolicy.PROPRIETARY)
        branch = self.factory.makeProductBranch(
            product=product, owner=product.owner)
        login_person(product.owner)
        product.development_focus.branch = branch
        view = create_initialized_view(
            product, '+code-index', rootsite='code',
            principal=product.owner)
        text = extract_text(find_tag_by_id(view.render(), 'privacy'))
        expected = (
            "New branches for %(name)s are Proprietary.*"
            % dict(name=product.displayname))
        self.assertTextMatchesExpressionIgnoreWhitespace(expected, text)

    def test_is_public(self):
        product = self.factory.makeProduct()
        product_displayname = product.displayname
        branch = self.factory.makeProductBranch(product=product)
        login_person(product.owner)
        product.development_focus.branch = branch
        browser = self.getUserBrowser(canonical_url(product, rootsite='code'))
        text = extract_text(find_tag_by_id(browser.contents, 'privacy'))
        expected = (
            "New branches for %(name)s are Public.*"
            % dict(name=product_displayname))
        self.assertTextMatchesExpressionIgnoreWhitespace(expected, text)


class TestCanConfigureBranches(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_cannot_configure_branches_product_no_edit_permission(self):
        product = self.factory.makeProduct()
        view = create_view(product, '+branches', layer=CodeLayer)
        self.assertEqual(False, view.can_configure_branches())

    def test_can_configure_branches_product_with_edit_permission(self):
        product = self.factory.makeProduct()
        login_person(product.owner)
        view = create_view(product, '+branches', layer=CodeLayer)
        self.assertTrue(view.can_configure_branches())
