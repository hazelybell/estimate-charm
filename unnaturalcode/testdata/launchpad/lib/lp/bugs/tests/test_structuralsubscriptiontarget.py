# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test harness for running tests against IStructuralsubscriptionTarget
implementations.
"""
__metaclass__ = type

import unittest

from storm.expr import compile as compile_storm
from zope.component import getUtility
from zope.security.interfaces import Unauthorized
from zope.security.proxy import (
    ProxyFactory,
    removeSecurityProxy,
    )

from lp.bugs.interfaces.bug import CreateBugParams
from lp.bugs.interfaces.structuralsubscription import (
    IStructuralSubscriptionTarget,
    IStructuralSubscriptionTargetHelper,
    )
from lp.bugs.model.structuralsubscription import (
    get_structural_subscriptions_for_target,
    StructuralSubscription,
    )
from lp.bugs.tests.test_bugtarget import bugtarget_filebug
from lp.registry.errors import (
    DeleteSubscriptionError,
    UserCannotSubscribePerson,
    )
from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.interfaces.product import IProductSet
from lp.services.webapp.interfaces import ILaunchBag
from lp.testing import (
    ANONYMOUS,
    login,
    login_celebrity,
    login_person,
    person_logged_in,
    TestCaseWithFactory,
    verifyObject,
    )
from lp.testing.factory import is_security_proxied_or_harmless
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    LaunchpadZopelessLayer,
    )
from lp.testing.matchers import Provides
from lp.testing.systemdocs import (
    LayeredDocFileSuite,
    setUp,
    tearDown,
    )


class RestrictedStructuralSubscriptionTestBase:
    """Tests suitable for a target that restricts structural subscriptions."""

    def setUp(self):
        super(RestrictedStructuralSubscriptionTestBase, self).setUp()
        self.ordinary_subscriber = self.factory.makePerson()
        self.bug_supervisor_subscriber = self.factory.makePerson()
        self.team_owner = self.factory.makePerson()
        self.team = self.factory.makeTeam(owner=self.team_owner)

    def test_target_implements_structural_subscription_target(self):
        self.assertTrue(verifyObject(IStructuralSubscriptionTarget,
                                     self.target))

    def test_anonymous_cannot_subscribe_anyone(self):
        # only authenticated users can create structural subscriptions
        login(ANONYMOUS)
        self.assertRaises(Unauthorized, getattr, self.target,
                          'addBugSubscription')

    def test_person_structural_subscription_by_other_person(self):
        # a person can not subscribe someone else willy nilly
        login_person(self.ordinary_subscriber)
        self.assertRaises(UserCannotSubscribePerson,
            self.target.addBugSubscription,
            self.team_owner, self.ordinary_subscriber)

    def test_team_structural_subscription_by_non_team_member(self):
        # a person not related to a team cannot subscribe it
        login_person(self.ordinary_subscriber)
        self.assertRaises(UserCannotSubscribePerson,
            self.target.addBugSubscription,
            self.team, self.ordinary_subscriber)

    def test_admin_can_subscribe_anyone(self):
        # a launchpad admin can create a structural subscription for
        # anyone
        admin = login_celebrity('admin')
        self.assertIsInstance(
            self.target.addBugSubscription(self.ordinary_subscriber, admin),
            StructuralSubscription)

    def test_secondary_structural_subscription(self):
        # creating a structural subscription a 2nd time returns the
        # first structural subscription
        login_person(self.bug_supervisor_subscriber)
        subscription1 = self.target.addBugSubscription(
            self.bug_supervisor_subscriber, self.bug_supervisor_subscriber)
        subscription2 = self.target.addBugSubscription(
            self.bug_supervisor_subscriber, self.bug_supervisor_subscriber)
        self.assertIs(subscription1.id, subscription2.id)

    def test_remove_structural_subscription(self):
        # an unprivileged user cannot unsubscribe a team
        login_person(self.ordinary_subscriber)
        self.assertRaises(UserCannotSubscribePerson,
            self.target.removeBugSubscription,
            self.team, self.ordinary_subscriber)

    def test_remove_nonexistant_structural_subscription(self):
        # removing a nonexistant subscription raises a
        # DeleteSubscriptionError
        login_person(self.ordinary_subscriber)
        self.assertRaises(DeleteSubscriptionError,
            self.target.removeBugSubscription,
            self.ordinary_subscriber, self.ordinary_subscriber)


class UnrestrictedStructuralSubscriptionTestBase(
    RestrictedStructuralSubscriptionTestBase):
    """
    Tests suitable for a target that does not restrict structural
    subscriptions.
    """

    def test_structural_subscription_by_ordinary_user(self):
        # ordinary users can subscribe themselves
        login_person(self.ordinary_subscriber)
        self.assertIsInstance(
            self.target.addBugSubscription(
                self.ordinary_subscriber, self.ordinary_subscriber),
            StructuralSubscription)

    def test_remove_structural_subscription_by_ordinary_user(self):
        # ordinary users can unsubscribe themselves
        login_person(self.ordinary_subscriber)
        self.assertIsInstance(
            self.target.addBugSubscription(
                self.ordinary_subscriber, self.ordinary_subscriber),
            StructuralSubscription)
        self.assertEqual(
            self.target.removeBugSubscription(
                self.ordinary_subscriber, self.ordinary_subscriber),
            None)

    def test_team_structural_subscription_by_team_owner(self):
        # team owners can subscribe their team
        login_person(self.team_owner)
        self.assertIsInstance(
            self.target.addBugSubscription(
                self.team, self.team_owner),
            StructuralSubscription)

    def test_remove_team_structural_subscription_by_team_owner(self):
        # team owners can unsubscribe their team
        login_person(self.team_owner)
        self.assertIsInstance(
            self.target.addBugSubscription(
                self.team, self.team_owner),
            StructuralSubscription)
        self.assertEqual(
            self.target.removeBugSubscription(
                self.team, self.team_owner),
            None)


class TestStructuralSubscriptionForDistro(
    RestrictedStructuralSubscriptionTestBase, TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestStructuralSubscriptionForDistro, self).setUp()
        self.target = self.factory.makeDistribution()
        naked_distro = removeSecurityProxy(self.target)
        naked_distro.bug_supervisor = self.bug_supervisor_subscriber

    def test_distribution_subscription_by_ordinary_user(self):
        # ordinary users can not subscribe themselves to a distribution
        login_person(self.ordinary_subscriber)
        self.assertRaises(UserCannotSubscribePerson,
            self.target.addBugSubscription,
            self.ordinary_subscriber, self.ordinary_subscriber)

    def test_team_distribution_structural_subscription_by_team_owner(self):
        # team owners cannot subscribe their team to a distribution
        login_person(self.team_owner)
        self.assertRaises(UserCannotSubscribePerson,
            self.target.addBugSubscription,
            self.team, self.team_owner)

    def test_distribution_subscription_by_bug_supervisor(self):
        # bug supervisor can subscribe themselves
        login_person(self.bug_supervisor_subscriber)
        self.assertIsInstance(
            self.target.addBugSubscription(
                    self.bug_supervisor_subscriber,
                    self.bug_supervisor_subscriber),
            StructuralSubscription)

    def test_distribution_subscription_by_bug_supervisor_team(self):
        # team admins can subscribe team if team is bug supervisor
        removeSecurityProxy(self.target).bug_supervisor = self.team
        login_person(self.team_owner)
        self.assertIsInstance(
                self.target.addBugSubscription(self.team, self.team_owner),
                    StructuralSubscription)

    def test_distribution_unsubscription_by_bug_supervisor_team(self):
        # team admins can unsubscribe team if team is bug supervisor
        removeSecurityProxy(self.target).bug_supervisor = self.team
        login_person(self.team_owner)
        self.assertIsInstance(
                self.target.addBugSubscription(self.team, self.team_owner),
                    StructuralSubscription)
        self.assertEqual(
                self.target.removeBugSubscription(self.team, self.team_owner),
                    None)

    def test_distribution_subscription_without_bug_supervisor(self):
        # for a distribution without a bug supervisor anyone can
        # subscribe
        removeSecurityProxy(self.target).bug_supervisor = None
        login_person(self.ordinary_subscriber)
        self.assertIsInstance(
            self.target.addBugSubscription(
                self.ordinary_subscriber, self.ordinary_subscriber),
            StructuralSubscription)


class TestStructuralSubscriptionForProduct(
    UnrestrictedStructuralSubscriptionTestBase, TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestStructuralSubscriptionForProduct, self).setUp()
        self.target = self.factory.makeProduct()


class TestStructuralSubscriptionForDistroSourcePackage(
    UnrestrictedStructuralSubscriptionTestBase, TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestStructuralSubscriptionForDistroSourcePackage, self).setUp()
        self.target = self.factory.makeDistributionSourcePackage()
        self.target = ProxyFactory(self.target)


class TestStructuralSubscriptionForMilestone(
    UnrestrictedStructuralSubscriptionTestBase, TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestStructuralSubscriptionForMilestone, self).setUp()
        self.target = self.factory.makeMilestone()
        self.target = ProxyFactory(self.target)


class TestStructuralSubscriptionForDistroSeries(
    UnrestrictedStructuralSubscriptionTestBase, TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestStructuralSubscriptionForDistroSeries, self).setUp()
        self.target = self.factory.makeDistroSeries()
        self.target = ProxyFactory(self.target)


class TestStructuralSubscriptionForProjectGroup(
    UnrestrictedStructuralSubscriptionTestBase, TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestStructuralSubscriptionForProjectGroup, self).setUp()
        self.target = self.factory.makeProject()
        self.target = ProxyFactory(self.target)


class TestStructuralSubscriptionForProductSeries(
    UnrestrictedStructuralSubscriptionTestBase, TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestStructuralSubscriptionForProductSeries, self).setUp()
        self.target = self.factory.makeProductSeries()
        self.target = ProxyFactory(self.target)


class TestStructuralSubscriptionTargetHelper(TestCaseWithFactory):
    """Tests for implementations of `IStructuralSubscriptionTargetHelper`."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestStructuralSubscriptionTargetHelper, self).setUp()
        self.person = self.factory.makePerson()
        login_person(self.person)

    def test_distribution_series(self):
        target = self.factory.makeDistroSeries()
        helper = IStructuralSubscriptionTargetHelper(target)
        self.assertThat(helper, Provides(IStructuralSubscriptionTargetHelper))
        self.assertEqual("distribution series", helper.target_type_display)
        self.assertEqual(target, helper.target)
        self.assertEqual(target.distribution, helper.target_parent)
        self.assertEqual({"distroseries": target}, helper.target_arguments)
        self.assertEqual(target.distribution, helper.pillar)
        self.assertEqual(
            u"StructuralSubscription.distroseries = ?",
            compile_storm(helper.join))

    def test_project_group(self):
        target = self.factory.makeProject(owner=self.person)
        helper = IStructuralSubscriptionTargetHelper(target)
        self.assertThat(helper, Provides(IStructuralSubscriptionTargetHelper))
        self.assertEqual("project group", helper.target_type_display)
        self.assertEqual(target, helper.target)
        self.assertEqual(None, helper.target_parent)
        self.assertEqual(target, helper.pillar)
        self.assertEqual({"project": target}, helper.target_arguments)
        self.assertEqual(
            u"StructuralSubscription.project = ?",
            compile_storm(helper.join))

    def test_distribution_source_package(self):
        target = self.factory.makeDistributionSourcePackage()
        helper = IStructuralSubscriptionTargetHelper(target)
        self.assertThat(helper, Provides(IStructuralSubscriptionTargetHelper))
        self.assertEqual("package", helper.target_type_display)
        self.assertEqual(target, helper.target)
        self.assertEqual(target.distribution, helper.target_parent)
        self.assertThat(
            helper.target_parent, Provides(IStructuralSubscriptionTarget))
        self.assertEqual(target.distribution, helper.pillar)
        self.assertEqual(
            {"distribution": target.distribution,
             "sourcepackagename": target.sourcepackagename},
            helper.target_arguments)
        self.assertEqual(
            u"StructuralSubscription.distribution = ? AND "
            u"StructuralSubscription.sourcepackagename = ?",
            compile_storm(helper.join))

    def test_milestone(self):
        target = self.factory.makeMilestone()
        helper = IStructuralSubscriptionTargetHelper(target)
        self.assertThat(helper, Provides(IStructuralSubscriptionTargetHelper))
        self.assertEqual("milestone", helper.target_type_display)
        self.assertEqual(target, helper.target)
        self.assertEqual(target.target, helper.target_parent)
        self.assertThat(
            helper.target_parent, Provides(IStructuralSubscriptionTarget))
        self.assertEqual(target.target, helper.pillar)
        self.assertEqual({"milestone": target}, helper.target_arguments)
        self.assertEqual(
            u"StructuralSubscription.milestone = ?",
            compile_storm(helper.join))

    def test_product(self):
        target = self.factory.makeProduct(owner=self.person)
        helper = IStructuralSubscriptionTargetHelper(target)
        self.assertThat(helper, Provides(IStructuralSubscriptionTargetHelper))
        self.assertEqual("project", helper.target_type_display)
        self.assertEqual(target, helper.target)
        self.assertEqual(None, helper.target_parent)
        self.assertEqual(target, helper.pillar)
        self.assertEqual({"product": target}, helper.target_arguments)
        self.assertEqual(
            u"StructuralSubscription.product = ?",
            compile_storm(helper.join))

    def test_product_in_group(self):
        project = self.factory.makeProject(owner=self.person)
        target = self.factory.makeProduct(project=project)
        helper = IStructuralSubscriptionTargetHelper(target)
        self.assertThat(helper, Provides(IStructuralSubscriptionTargetHelper))
        self.assertEqual("project", helper.target_type_display)
        self.assertEqual(target, helper.target)
        self.assertEqual(project, helper.target_parent)
        self.assertEqual(target, helper.pillar)
        self.assertEqual({"product": target}, helper.target_arguments)
        self.assertEqual(
            u"StructuralSubscription.product = ? OR "
            "StructuralSubscription.project = ?",
            compile_storm(helper.join))

    def test_product_series(self):
        target = self.factory.makeProductSeries(owner=self.person)
        helper = IStructuralSubscriptionTargetHelper(target)
        self.assertThat(helper, Provides(IStructuralSubscriptionTargetHelper))
        self.assertEqual("project series", helper.target_type_display)
        self.assertEqual(target, helper.target)
        self.assertEqual(target.product, helper.target_parent)
        self.assertThat(
            helper.target_parent, Provides(IStructuralSubscriptionTarget))
        self.assertEqual(target.product, helper.pillar)
        self.assertEqual({"productseries": target}, helper.target_arguments)
        self.assertEqual(
            u"StructuralSubscription.productseries = ?",
            compile_storm(helper.join))

    def test_distribution(self):
        target = self.factory.makeDistribution(owner=self.person)
        helper = IStructuralSubscriptionTargetHelper(target)
        self.assertThat(helper, Provides(IStructuralSubscriptionTargetHelper))
        self.assertEqual(target, helper.target)
        self.assertEqual("distribution", helper.target_type_display)
        self.assertEqual(None, helper.target_parent)
        self.assertEqual(target, helper.pillar)
        self.assertEqual(
            {"distribution": target,
             "sourcepackagename": None},
            helper.target_arguments)
        self.assertEqual(
            u"StructuralSubscription.distribution = ? AND "
            u"StructuralSubscription.sourcepackagename IS NULL",
            compile_storm(helper.join))


class TestGetAllStructuralSubscriptionsForTarget(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestGetAllStructuralSubscriptionsForTarget, self).setUp()
        self.subscriber = self.factory.makePerson()
        self.team = self.factory.makeTeam(members=[self.subscriber])
        login_person(self.subscriber)
        self.product = self.factory.makeProduct()
        self.milestone = self.factory.makeMilestone(product=self.product)

    def getSubscriptions(self):
        subscriptions = get_structural_subscriptions_for_target(
            self.product, self.subscriber)
        self.assertTrue(is_security_proxied_or_harmless(subscriptions))
        return subscriptions

    def test_no_subscriptions(self):
        subscriptions = self.getSubscriptions()
        self.assertEqual([], list(subscriptions))

    def test_self_subscription(self):
        sub = self.product.addBugSubscription(
            self.subscriber, self.subscriber)
        subscriptions = self.getSubscriptions()
        self.assertEqual([sub], list(subscriptions))

    def test_team_subscription(self):
        with person_logged_in(self.team.teamowner):
            sub = self.product.addBugSubscription(
                self.team, self.team.teamowner)
        subscriptions = self.getSubscriptions()
        self.assertEqual([sub], list(subscriptions))

    def test_both_subscriptions(self):
        self_sub = self.product.addBugSubscription(
            self.subscriber, self.subscriber)
        with person_logged_in(self.team.teamowner):
            team_sub = self.product.addBugSubscription(
                self.team, self.team.teamowner)
        subscriptions = self.getSubscriptions()
        self.assertEqual(set([self_sub, team_sub]), set(subscriptions))

    def test_subscribed_to_project_group(self):
        # If a user is subscribed to a project group, calls to
        # get_structural_subscriptions_for_target made against the
        # products in that group will return the group-level
        # subscription along with any subscriptions to the product.
        project = self.factory.makeProject()
        product = self.factory.makeProduct(project=project)
        project_sub = project.addBugSubscription(
            self.subscriber, self.subscriber)
        subscriptions = get_structural_subscriptions_for_target(
            product, self.subscriber)
        self.assertEqual(set([project_sub]), set(subscriptions))


def distributionSourcePackageSetUp(test):
    setUp(test)
    ubuntu = getUtility(IDistributionSet).getByName('ubuntu')
    test.globs['target'] = ubuntu.getSourcePackage('evolution')
    test.globs['other_target'] = ubuntu.getSourcePackage('pmount')
    test.globs['filebug'] = bugtarget_filebug


def productSetUp(test):
    setUp(test)
    test.globs['target'] = getUtility(IProductSet).getByName('firefox')
    test.globs['filebug'] = bugtarget_filebug


def distributionSetUp(test):
    setUp(test)
    test.globs['target'] = getUtility(IDistributionSet).getByName('ubuntu')
    test.globs['filebug'] = bugtarget_filebug


def milestone_filebug(milestone, summary, status=None):
    bug = bugtarget_filebug(milestone.target, summary, status=status)
    bug.bugtasks[0].milestone = milestone
    return bug


def milestoneSetUp(test):
    setUp(test)
    firefox = getUtility(IProductSet).getByName('firefox')
    test.globs['target'] = firefox.getMilestone('1.0')
    test.globs['filebug'] = milestone_filebug


def distroseries_sourcepackage_filebug(distroseries, summary, status=None):
    params = CreateBugParams(
        getUtility(ILaunchBag).user, summary, comment=summary, status=status,
        target=distroseries.distribution.getSourcePackage('alsa-utils'))
    bug = distroseries.distribution.createBug(params)
    nomination = bug.addNomination(
        distroseries.distribution.owner, distroseries)
    nomination.approve(distroseries.distribution.owner)
    return bug


def distroSeriesSourcePackageSetUp(test):
    setUp(test)
    test.globs['target'] = (
        getUtility(IDistributionSet).getByName('ubuntu').getSeries('hoary'))
    test.globs['filebug'] = distroseries_sourcepackage_filebug


def test_suite():
    """Return the `IStructuralSubscriptionTarget` TestSuite."""
    suite = unittest.TestSuite()
    suite.addTest(unittest.TestLoader().loadTestsFromName(__name__))

    setUpMethods = [
        distributionSourcePackageSetUp,
        productSetUp,
        distributionSetUp,
        milestoneSetUp,
        distroSeriesSourcePackageSetUp,
        ]

    testname = 'structural-subscription-target.txt'
    for setUpMethod in setUpMethods:
        id_ext = "%s-%s" % (testname, setUpMethod.func_name)
        test = LayeredDocFileSuite(
            testname,
            id_extensions=[id_ext],
            setUp=setUpMethod, tearDown=tearDown,
            layer=LaunchpadFunctionalLayer)
        suite.addTest(test)

    return suite
