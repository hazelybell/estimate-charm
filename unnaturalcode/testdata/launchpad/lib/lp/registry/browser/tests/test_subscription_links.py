# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for subscription links."""

__metaclass__ = type

import unittest

from BeautifulSoup import BeautifulSoup
from fixtures import FakeLogger
from zope.component import getUtility

from lp.bugs.browser.structuralsubscription import (
    StructuralSubscriptionMenuMixin,
    )
from lp.registry.interfaces.person import IPersonSet
from lp.registry.model.milestone import ProjectMilestone
from lp.services.webapp.interaction import ANONYMOUS
from lp.services.webapp.interfaces import ILaunchBag
from lp.services.webapp.publisher import canonical_url
from lp.testing import (
    BrowserTestCase,
    celebrity_logged_in,
    extract_lp_cache,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.pages import first_tag_by_class
from lp.testing.sampledata import ADMIN_EMAIL
from lp.testing.views import create_initialized_view


class _TestResultsMixin:
    """Mixin to provide common result checking helper methods."""

    @property
    def old_link(self):
        return first_tag_by_class(
            self.contents, 'menu-link-subscribe')

    @property
    def new_subscribe_link(self):
        return first_tag_by_class(
            self.contents, 'menu-link-subscribe_to_bug_mail')

    @property
    def new_edit_link(self):
        return first_tag_by_class(
            self.contents, 'menu-link-edit_bug_mail')

    def assertLinksMissing(self):
        self.assertEqual(
            None, self.old_link,
            "Found unexpected link: %s" % self.old_link)
        self.assertEqual(
            None, self.new_subscribe_link,
            "Found unexpected link: %s" % self.new_subscribe_link)
        self.assertEqual(
            None, self.new_edit_link,
            "Found unexpected link: %s" % self.new_edit_link)

    def assertLinksPresent(self):
        self.assertNotEqual(
            None, self.new_subscribe_link,
            "Expected subscribe_to_bug_mail link missing")
        self.assertNotEqual(
            None, self.new_edit_link,
            "Expected edit_bug_mail link missing")
        # Ensure the LP.cache has been populated.
        cache = extract_lp_cache(self.contents)
        self.assertIn('administratedTeams', cache)
        # Ensure the call to setup the subscription is in the HTML.
        # Only check for the presence of setup's configuration step; more
        # detailed checking is needlessly brittle.

        # A yuixhr test is required to ensure that the call actually
        # succeeded, by checking the link class for 'js-action'.
        setup = ('{content_box: "#structural-subscription-content-box"});')
        self.assertTrue(setup in self.contents)


class _TestStructSubs(TestCaseWithFactory, _TestResultsMixin):
    """Test structural subscriptions base class."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(_TestStructSubs, self).setUp()
        self.regular_user = self.factory.makePerson()
        # Use a FakeLogger fixture to prevent Memcached warnings to be
        # printed to stdout while browsing pages.
        self.useFixture(FakeLogger())

    def _create_scenario(self, user):
        with person_logged_in(user):
            view = self.create_view(user)
            self.contents = view.render()

    def create_view(self, user):
        return create_initialized_view(
            self.target, self.view, principal=user,
            rootsite=self.rootsite, current_request=False)

    def test_subscribe_link_owner(self):
        # Test the subscription link.
        self._create_scenario(self.target.owner)
        self.assertLinksPresent()

    def test_subscribe_link_user(self):
        self._create_scenario(self.regular_user)
        self.assertLinksPresent()

    def test_subscribe_link_anonymous(self):
        self._create_scenario(ANONYMOUS)
        # The subscribe link is not shown to anonymous.
        self.assertLinksMissing()


class ProductView(_TestStructSubs):
    """Test structural subscriptions on the product view."""

    rootsite = None
    view = '+index'

    def setUp(self):
        super(ProductView, self).setUp()
        self.target = self.factory.makeProduct(official_malone=True)


class ProductBugs(ProductView):
    """Test structural subscriptions on the product bugs view."""

    rootsite = 'bugs'
    view = '+bugs'


class ProjectGroupView(_TestStructSubs):
    """Test structural subscriptions on the project group view."""

    rootsite = None
    view = '+index'

    def setUp(self):
        super(ProjectGroupView, self).setUp()
        self.target = self.factory.makeProject()
        self.factory.makeProduct(
            project=self.target, official_malone=True)


class ProjectGroupMilestone(TestCaseWithFactory):
    """Make sure that projects' "virtual" milestones don't break things."""

    layer = DatabaseFunctionalLayer

    def test_for_bug_778689(self):
        with person_logged_in(self.factory.makePerson()):
            # Project groups have "virtual" milestones that aren't stored in
            # the database directly (they're inherited from the contained
            # products).  Viewing one of those group milestones would generate
            # an OOPS because adapting the milestone to
            # IStructuralSubscriptionTargetHelper would attempt to look them
            # up in the database, raising an exception.
            project = self.factory.makeProject()
            product = self.factory.makeProduct(project=project)
            mixin = StructuralSubscriptionMenuMixin()
            mixin.context = ProjectMilestone(
                project, '11.04', None, True, product)
            # Before bug 778689 was fixed, this would raise an exception.
            mixin._enabled


class ProjectGroupBugs(ProjectGroupView):
    """Test structural subscriptions on the project group bugs view."""

    rootsite = 'bugs'
    view = '+bugs'


class ProductSeriesView(_TestStructSubs):
    """Test structural subscriptions on the product series view."""

    rootsite = None
    view = '+index'

    def setUp(self):
        super(ProductSeriesView, self).setUp()
        product = self.factory.makeProduct(official_malone=True)
        self.target = self.factory.makeProductSeries(product=product)


class ProductSeriesBugs(ProductSeriesView):
    """Test structural subscriptions on the product series bugs view."""

    rootsite = 'bugs'
    view = '+bugs'

    def setUp(self):
        super(ProductSeriesBugs, self).setUp()
        with person_logged_in(self.target.product.owner):
            self.target.product.official_malone = True


class DistributionSourcePackageView(_TestStructSubs):
    """Test structural subscriptions on the distro src pkg view."""

    rootsite = None
    view = '+index'

    def setUp(self):
        super(DistributionSourcePackageView, self).setUp()
        distro = self.factory.makeDistribution()
        with person_logged_in(distro.owner):
            distro.official_malone = True
        self.target = self.factory.makeDistributionSourcePackage(
            distribution=distro)
        self.regular_user = self.factory.makePerson()

    # DistributionSourcePackages do not have owners.
    test_subscribe_link_owner = None


class DistributionSourcePackageBugs(DistributionSourcePackageView):
    """Test structural subscriptions on the distro src pkg bugs view."""

    rootsite = 'bugs'
    view = '+bugs'


class DistroView(BrowserTestCase, _TestResultsMixin):
    """Test structural subscriptions on the distribution view.

    Distributions are special.  They are IStructuralSubscriptionTargets but
    have complicated rules to ensure Ubuntu users don't subscribe and become
    overwhelmed with email.  If a distro does not have a bug supervisor set,
    then anyone can create a structural subscription for themselves.  If the
    bug supervisor is set, then only people in the bug supervisor team can
    subscribe themselves.  Admins can subscribe anyone.
    """

    layer = DatabaseFunctionalLayer
    rootsite = None
    view = '+index'

    def setUp(self):
        super(DistroView, self).setUp()
        self.target = self.factory.makeDistribution()
        with person_logged_in(self.target.owner):
            self.target.official_malone = True
        self.regular_user = self.factory.makePerson()
        # Use a FakeLogger fixture to prevent Memcached warnings to be
        # printed to stdout while browsing pages.
        self.useFixture(FakeLogger())

    def _create_scenario(self, user):
        with person_logged_in(user):
            logged_in_user = getUtility(ILaunchBag).user
            no_login = logged_in_user is None
            browser = self.getViewBrowser(
                self.target, view_name=self.view,
                rootsite=self.rootsite,
                no_login=no_login,
                user=logged_in_user)
            self.contents = browser.contents

    @property
    def old_link(self):
        href = canonical_url(
            self.target, rootsite=self.rootsite,
            view_name='+subscribe')
        soup = BeautifulSoup(self.contents)
        return soup.find('a', href=href)

    def test_subscribe_link_owner(self):
        self._create_scenario(self.target.owner)
        self.assertLinksPresent()

    def test_subscribe_link_user_no_bug_super(self):
        self._create_scenario(self.regular_user)
        self.assertLinksPresent()

    def test_subscribe_link_user_with_bug_super(self):
        with celebrity_logged_in('admin'):
            self.target.bug_supervisor = self.factory.makePerson()
        self._create_scenario(self.regular_user)
        self.assertLinksMissing()

    def test_subscribe_link_anonymous(self):
        self._create_scenario(ANONYMOUS)
        self.assertLinksMissing()

    def test_subscribe_link_bug_super(self):
        with celebrity_logged_in('admin'):
            self.target.bug_supervisor = self.regular_user
        self._create_scenario(self.regular_user)
        self.assertLinksPresent()

    def test_subscribe_link_admin(self):
        admin = getUtility(IPersonSet).getByEmail(ADMIN_EMAIL)
        self._create_scenario(admin)
        self.assertLinksPresent()


class DistroBugs(DistroView):
    """Test structural subscriptions on the distro bugs view."""

    rootsite = 'bugs'
    view = '+bugs'

    def test_subscribe_link_owner(self):
        self._create_scenario(self.target.owner)
        self.assertLinksPresent()

    def test_subscribe_link_user_no_bug_super(self):
        self._create_scenario(self.regular_user)
        self.assertLinksPresent()

    def test_subscribe_link_user_with_bug_super(self):
        with celebrity_logged_in('admin'):
            self.target.bug_supervisor = self.factory.makePerson()
        self._create_scenario(self.regular_user)
        self.assertLinksMissing()

    def test_subscribe_link_anonymous(self):
        self._create_scenario(ANONYMOUS)
        self.assertLinksMissing()

    def test_subscribe_link_bug_super(self):
        with celebrity_logged_in('admin'):
            self.target.bug_supervisor = self.regular_user
        self._create_scenario(self.regular_user)
        self.assertLinksPresent()

    def test_subscribe_link_admin(self):
        from lp.testing.sampledata import ADMIN_EMAIL
        admin = getUtility(IPersonSet).getByEmail(ADMIN_EMAIL)
        self._create_scenario(admin)
        self.assertLinksPresent()


class DistroMilestoneView(DistroView):
    """Test structural subscriptions on the distro milestones."""

    def setUp(self):
        super(DistroMilestoneView, self).setUp()
        self.distro = self.target
        self.target = self.factory.makeMilestone(distribution=self.distro)

    def test_subscribe_link_owner(self):
        self._create_scenario(self.distro.owner)
        self.assertLinksPresent()

    def test_subscribe_link_user_no_bug_super(self):
        self._create_scenario(self.regular_user)
        self.assertLinksPresent()

    def test_subscribe_link_user_with_bug_super(self):
        with celebrity_logged_in('admin'):
            self.distro.bug_supervisor = self.factory.makePerson()
        self._create_scenario(self.regular_user)
        self.assertLinksPresent()

    def test_subscribe_link_anonymous(self):
        self._create_scenario(ANONYMOUS)
        self.assertLinksMissing()

    def test_subscribe_link_bug_super(self):
        with celebrity_logged_in('admin'):
            self.distro.bug_supervisor = self.regular_user
        self._create_scenario(self.regular_user)
        self.assertLinksPresent()

    def test_subscribe_link_admin(self):
        from lp.testing.sampledata import ADMIN_EMAIL
        admin = getUtility(IPersonSet).getByEmail(ADMIN_EMAIL)
        self._create_scenario(admin)
        self.assertLinksPresent()


class ProductMilestoneView(DistroView):
    """Test structural subscriptions on the product milestones."""

    def setUp(self):
        super(ProductMilestoneView, self).setUp()
        self.product = self.factory.makeProduct()
        with person_logged_in(self.product.owner):
            self.product.official_malone = True
        self.regular_user = self.factory.makePerson()
        self.target = self.factory.makeMilestone(product=self.product)

    def test_subscribe_link_owner(self):
        self._create_scenario(self.product.owner)
        self.assertLinksPresent()

    # There are no special bug supervisor rules for products.
    test_subscribe_link_user_no_bug_super = None
    test_subscribe_link_user_with_bug_super = None
    test_subscribe_link_bug_super = None

    def test_subscribe_link_anonymous(self):
        self._create_scenario(ANONYMOUS)
        self.assertLinksMissing()

    def test_subscribe_link_admin(self):
        from lp.testing.sampledata import ADMIN_EMAIL
        admin = getUtility(IPersonSet).getByEmail(ADMIN_EMAIL)
        self._create_scenario(admin)
        self.assertLinksPresent()


class ProductSeriesMilestoneView(ProductMilestoneView):
    """Test structural subscriptions on the product series milestones."""

    def setUp(self):
        super(ProductSeriesMilestoneView, self).setUp()
        self.productseries = self.factory.makeProductSeries()
        with person_logged_in(self.productseries.product.owner):
            self.productseries.product.official_malone = True
        self.regular_user = self.factory.makePerson()
        self.target = self.factory.makeMilestone(
            productseries=self.productseries)


# Tests for when the IStructuralSubscriptionTarget does not use Launchpad for
# bug tracking.  In those cases the links should not be shown.
class _DoesNotUseLP(ProductView):
    """Test structural subscriptions on the product view."""

    def setUp(self):
        super(_DoesNotUseLP, self).setUp()
        self.target = self.factory.makeProduct(official_malone=False)

    def test_subscribe_link_owner(self):
        # Test the new subscription link.
        self._create_scenario(self.target.owner)
        self.assertLinksMissing()

    def test_subscribe_link_user(self):
        self._create_scenario(self.regular_user)
        self.assertLinksMissing()

    def test_subscribe_link_anonymous(self):
        self._create_scenario(ANONYMOUS)
        # The subscribe link is not shown to anonymous.
        self.assertLinksMissing()


class ProductDoesNotUseLPView(_DoesNotUseLP):

    def test_subscribe_link_no_bugtracker_parent_bugtracker(self):
        # If there is no bugtracker, do not render links, even if the
        # parent has a bugtracker (see bug 770287).
        project = self.factory.makeProject()
        with person_logged_in(self.target.owner):
            self.target.project = project
        self.factory.makeProduct(project=project, official_malone=True)
        self._create_scenario(self.regular_user)
        self.assertLinksMissing()


class ProductDoesNotUseLPBugs(ProductDoesNotUseLPView):
    """Test structural subscriptions on the product bugs view."""

    rootsite = 'bugs'
    view = '+bugs'


class ProjectGroupDoesNotUseLPView(_DoesNotUseLP):
    """Test structural subscriptions on the project group view."""

    rootsite = None
    view = '+index'

    def setUp(self):
        super(ProjectGroupDoesNotUseLPView, self).setUp()
        self.target = self.factory.makeProject()
        self.factory.makeProduct(
            project=self.target, official_malone=False)


class ProjectGroupDoesNotUseLPBugs(ProductDoesNotUseLPBugs):
    """Test structural subscriptions on the project group bugs view."""

    rootsite = 'bugs'
    view = '+bugs'

    def setUp(self):
        super(ProjectGroupDoesNotUseLPBugs, self).setUp()
        self.target = self.factory.makeProject()
        self.factory.makeProduct(
            project=self.target, official_malone=False)

    test_subscribe_link_no_bugtracker_parent_bugtracker = None


class ProductSeriesDoesNotUseLPView(_DoesNotUseLP):

    def setUp(self):
        super(ProductSeriesDoesNotUseLPView, self).setUp()
        product = self.factory.makeProduct(official_malone=False)
        self.target = self.factory.makeProductSeries(product=product)


class ProductSeriesDoesNotUseLPBugs(_DoesNotUseLP):

    def setUp(self):
        super(ProductSeriesDoesNotUseLPBugs, self).setUp()
        product = self.factory.makeProduct(official_malone=False)
        self.target = self.factory.makeProductSeries(product=product)


class DistributionSourcePackageDoesNotUseLPView(_DoesNotUseLP):
    """Test structural subscriptions on the distro src pkg view."""

    def setUp(self):
        super(DistributionSourcePackageDoesNotUseLPView, self).setUp()
        distro = self.factory.makeDistribution()
        self.target = self.factory.makeDistributionSourcePackage(
            distribution=distro)
        self.regular_user = self.factory.makePerson()

    # DistributionSourcePackages do not have owners.
    test_subscribe_link_owner = None


class DistributionSourcePackageDoesNotUseLPBugs(ProductDoesNotUseLPBugs):
    """Test structural subscriptions on the distro src pkg bugs view."""

    view = '+bugs'

    # DistributionSourcePackages do not have owners.
    test_subscribe_link_owner = None


class DistroDoesNotUseLPView(DistroView):

    def setUp(self):
        super(DistroDoesNotUseLPView, self).setUp()
        self.target = self.factory.makeDistribution()
        self.regular_user = self.factory.makePerson()

    def test_subscribe_link_admin(self):
        admin = getUtility(IPersonSet).getByEmail(ADMIN_EMAIL)
        self._create_scenario(admin)
        self.assertLinksMissing()

    def test_subscribe_link_bug_super(self):
        with celebrity_logged_in('admin'):
            self.target.bug_supervisor = self.regular_user
        self._create_scenario(self.regular_user)
        self.assertLinksMissing()

    def test_subscribe_link_user_no_bug_super(self):
        self._create_scenario(self.regular_user)
        self.assertLinksMissing()

    def test_subscribe_link_owner(self):
        # Test the new subscription link.
        self._create_scenario(self.target.owner)
        self.assertLinksMissing()

    def test_subscribe_link_user(self):
        self._create_scenario(self.regular_user)
        self.assertLinksMissing()

    def test_subscribe_link_anonymous(self):
        self._create_scenario(ANONYMOUS)
        # The subscribe link is not shown to anonymous.
        self.assertLinksMissing()


class DistroDoesNotUseLPBugs(DistroDoesNotUseLPView):
    rootsite = 'bugs'
    view = '+bugs'


class DistroMilestoneDoesNotUseLPView(DistroMilestoneView):

    def setUp(self):
        super(DistroMilestoneDoesNotUseLPView, self).setUp()
        with person_logged_in(self.distro.owner):
            self.distro.official_malone = False

    def test_subscribe_link_admin(self):
        admin = getUtility(IPersonSet).getByEmail(ADMIN_EMAIL)
        self._create_scenario(admin)
        self.assertLinksMissing()

    def test_subscribe_link_bug_super(self):
        with celebrity_logged_in('admin'):
            self.distro.bug_supervisor = self.regular_user
        self._create_scenario(self.regular_user)
        self.assertLinksMissing()

    def test_subscribe_link_user_no_bug_super(self):
        self._create_scenario(self.regular_user)
        self.assertLinksMissing()

    def test_subscribe_link_owner(self):
        # Test the new subscription link.
        self._create_scenario(self.distro.owner)
        self.assertLinksMissing()

    def test_subscribe_link_user(self):
        self._create_scenario(self.regular_user)
        self.assertLinksMissing()

    def test_subscribe_link_anonymous(self):
        self._create_scenario(ANONYMOUS)
        # The subscribe link is not shown to anonymous.
        self.assertLinksMissing()

    def test_subscribe_link_user_with_bug_super(self):
        with celebrity_logged_in('admin'):
            self.distro.bug_supervisor = self.factory.makePerson()
        self._create_scenario(self.regular_user)
        self.assertLinksMissing()


class ProductMilestoneDoesNotUseLPView(ProductMilestoneView):

    def setUp(self):
        super(ProductMilestoneDoesNotUseLPView, self).setUp()
        self.product = self.factory.makeProduct()
        with person_logged_in(self.product.owner):
            self.product.official_malone = False
        self.target = self.factory.makeMilestone(
            name='1.0', product=self.product)
        self.regular_user = self.factory.makePerson()

    def test_subscribe_link_admin(self):
        from lp.testing.sampledata import ADMIN_EMAIL
        admin = getUtility(IPersonSet).getByEmail(ADMIN_EMAIL)
        self._create_scenario(admin)
        self.assertLinksMissing()

    def test_subscribe_link_owner(self):
        self._create_scenario(self.product.owner)
        self.assertLinksMissing()


class CustomTestLoader(unittest.TestLoader):
    """A test loader that avoids running tests from a base class."""

    def getTestCaseNames(self, testCaseClass):
        # If we're asked about which tests to run for _TestStructSubs, reply
        # with an empty list.
        if testCaseClass is _TestStructSubs:
            return []
        else:
            return super(CustomTestLoader, self).getTestCaseNames(
                testCaseClass)


def test_suite():
    """Return the `IStructuralSubscriptionTarget` TestSuite."""
    return CustomTestLoader().loadTestsFromName(__name__)
