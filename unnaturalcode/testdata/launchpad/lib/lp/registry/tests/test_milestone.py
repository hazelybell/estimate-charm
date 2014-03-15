# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Milestone related test helper."""

__metaclass__ = type

from operator import attrgetter
import unittest

from storm.exceptions import NoneError
from zope.component import getUtility
from zope.security.checker import (
    CheckerPublic,
    getChecker,
    )
from zope.security.interfaces import Unauthorized

from lp.app.enums import InformationType
from lp.app.errors import NotFoundError
from lp.app.interfaces.informationtype import IInformationType
from lp.app.interfaces.services import IService
from lp.registry.enums import (
    SharingPermission,
    SpecificationSharingPolicy,
    )
from lp.registry.errors import ProprietaryProduct
from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.interfaces.milestone import (
    IHasMilestones,
    IMilestoneSet,
    )
from lp.registry.interfaces.product import IProductSet
from lp.testing import (
    ANONYMOUS,
    login,
    logout,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    )
from lp.testing.matchers import DoesNotSnapshot


class MilestoneTest(unittest.TestCase):
    """Milestone tests."""

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        login(ANONYMOUS)

    def tearDown(self):
        logout()

    def testMilestoneSetIterator(self):
        """Test of MilestoneSet.__iter__()."""
        all_milestones_ids = set(
            milestone.id for milestone in getUtility(IMilestoneSet))
        self.assertEqual(all_milestones_ids,
                         set((1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)))

    def testMilestoneSetGet(self):
        """Test of MilestoneSet.get()"""
        milestone_set = getUtility(IMilestoneSet)
        self.assertEqual(milestone_set.get(1).id, 1)
        self.assertRaises(NotFoundError, milestone_set.get, 100000)

    def testMilestoneSetGetIDs(self):
        """Test of MilestoneSet.getByIds()"""
        milestone_set = getUtility(IMilestoneSet)
        milestones = milestone_set.getByIds([1, 3])
        ids = sorted(map(attrgetter('id'), milestones))
        self.assertEqual([1, 3], ids)

    def testMilestoneSetGetByIDs_ignores_missing(self):
        milestone_set = getUtility(IMilestoneSet)
        self.assertEqual([], list(milestone_set.getByIds([100000])))

    def testMilestoneSetGetByNameAndProduct(self):
        """Test of MilestoneSet.getByNameAndProduct()"""
        firefox = getUtility(IProductSet).getByName('firefox')
        milestone_set = getUtility(IMilestoneSet)
        milestone = milestone_set.getByNameAndProduct('1.0', firefox)
        self.assertEqual(milestone.name, '1.0')
        self.assertEqual(milestone.target, firefox)

        marker = object()
        milestone = milestone_set.getByNameAndProduct(
            'does not exist', firefox, default=marker)
        self.assertEqual(milestone, marker)

    def testMilestoneSetGetByNameAndDistribution(self):
        """Test of MilestoneSet.getByNameAndDistribution()"""
        debian = getUtility(IDistributionSet).getByName('debian')
        milestone_set = getUtility(IMilestoneSet)
        milestone = milestone_set.getByNameAndDistribution('3.1', debian)
        self.assertEqual(milestone.name, '3.1')
        self.assertEqual(milestone.target, debian)

        marker = object()
        milestone = milestone_set.getByNameAndDistribution(
            'does not exist', debian, default=marker)
        self.assertEqual(milestone, marker)

    def testMilestoneSetGetVisibleMilestones(self):
        all_visible_milestones_ids = [
            milestone.id
            for milestone in getUtility(IMilestoneSet).getVisibleMilestones()]
        self.assertEqual(
            all_visible_milestones_ids,
            [1, 2, 3])


class MilestoneSecurityAdaperTestCase(TestCaseWithFactory):
    """A TestCase for the security adapter of milestones."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(MilestoneSecurityAdaperTestCase, self).setUp()
        self.public_product = self.factory.makeProduct()
        self.public_milestone = self.factory.makeMilestone(
            product=self.public_product)
        self.proprietary_product_owner = self.factory.makePerson()
        self.proprietary_product = self.factory.makeProduct(
            owner=self.proprietary_product_owner,
            information_type=InformationType.PROPRIETARY)
        self.proprietary_milestone = self.factory.makeMilestone(
            product=self.proprietary_product)

    expected_get_permissions = {
        CheckerPublic: set((
            'id', 'checkAuthenticated', 'checkUnauthenticated',
            'userCanView',
            )),
        'launchpad.LimitedView': set((
            'displayname', 'name', 'target',  'title',)),
        'launchpad.View': set((
            'active', 'bug_subscriptions', 'bugtasks', 'code_name',
            'dateexpected', 'distribution', 'distroseries',
            '_getOfficialTagClause', 'getBugSummaryContextWhereClause',
            'getBugTaskWeightFunction', 'getSpecifications',
            'getSubscription', 'getSubscriptions', 'getTags', 'getTagsData',
            'getUsedBugTagsWithOpenCounts', 'official_bug_tags',
            'parent_subscription_target', 'product', 'product_release',
            'productseries', 'searchTasks', 'series_target',
            'summary', 'target_type_display', 'all_specifications',
            'userCanAlterBugSubscription', 'userCanAlterSubscription',
            'userHasBugSubscriptions',
            )),
        'launchpad.AnyAllowedPerson': set((
            'addBugSubscription', 'addBugSubscriptionFilter',
            'addSubscription', 'removeBugSubscription',
            )),
        'launchpad.Edit': set((
            'closeBugsAndBlueprints', 'createProductRelease',
            'destroySelf', 'setTags',
            )),
        }

    def test_get_permissions(self):
        milestone = self.factory.makeMilestone()
        checker = getChecker(milestone)
        self.checkPermissions(
            self.expected_get_permissions, checker.get_permissions, 'get')

    expected_set_permissions = {
        'launchpad.Edit': set((
            'active', 'code_name', 'dateexpected', 'distroseries', 'name',
            'product_release', 'productseries', 'summary',
            )),
        }

    def test_set_permissions(self):
        milestone = self.factory.makeMilestone()
        checker = getChecker(milestone)
        self.checkPermissions(
            self.expected_set_permissions, checker.set_permissions, 'set')

    def assertAccessAuthorized(self, attribute_names, obj):
        # Try to access the given attributes of obj. No exception
        # should be raised.
        for name in attribute_names:
            # class Milestone does not implement all attributes defined by
            # class IMilestone. AttributeErrors caused by attempts to
            # access these attribues are not relevant here: We simply
            # want to be sure that no Unauthorized error is raised.
            try:
                getattr(obj, name)
            except AttributeError:
                pass

    def assertAccessUnauthorized(self, attribute_names, obj):
        # Try to access the given attributes of obj. Unauthorized
        # should be raised.
        for name in attribute_names:
            self.assertRaises(Unauthorized, getattr, obj, name)

    def assertChangeAuthorized(self, attribute_names, obj):
        # Try to changes the given attributes of obj. Unauthorized
        # should be raised.
        for name in attribute_names:
            # Not all attributes declared in configure.zcml to be
            # settable actually exist. Attempts to set them raises
            # an AttributeError. Setting an Attribute to None may not
            # be allowed.
            #
            # Both errors can be ignored here: This method intends only
            # to prove that Unauthorized is not raised.
            try:
                setattr(obj, name, None)
            except (AttributeError, NoneError):
                pass

    def assertChangeUnauthorized(self, attribute_names, obj):
        # Try to changes the given attributes of obj. Unauthorized
        # should be raised.
        for name in attribute_names:
            self.assertRaises(Unauthorized, setattr, obj, name, None)

    def test_access_for_anonymous(self):
        # Anonymous users have access to public attributes of
        # milestones for private and public products.
        with person_logged_in(ANONYMOUS):
            self.assertAccessAuthorized(
                self.expected_get_permissions[CheckerPublic],
                self.public_milestone)
            self.assertAccessAuthorized(
                self.expected_get_permissions[CheckerPublic],
                self.proprietary_milestone)

            # They have access to attributes requiring the permission
            # launchpad.View or launchpad.LimitedView of milestones for
            # public products...
            self.assertAccessAuthorized(
                self.expected_get_permissions['launchpad.View'],
                self.public_milestone)
            self.assertAccessAuthorized(
                self.expected_get_permissions['launchpad.LimitedView'],
                self.public_milestone)

            # ...but not to the same attributes of milestones for private
            # products.
            self.assertAccessUnauthorized(
                self.expected_get_permissions['launchpad.View'],
                self.proprietary_milestone)
            self.assertAccessUnauthorized(
                self.expected_get_permissions['launchpad.LimitedView'],
                self.proprietary_milestone)

            # They cannot access other attributes.
            for permission, names in self.expected_get_permissions.items():
                if permission in (CheckerPublic, 'launchpad.View',
                                  'launchpad.LimitedView'):
                    continue
                self.assertAccessUnauthorized(names, self.public_milestone)
                self.assertAccessUnauthorized(
                    names, self.proprietary_milestone)

            # They cannot change any attributes.
            for permission, names in self.expected_set_permissions.items():
                self.assertChangeUnauthorized(names, self.public_milestone)
                self.assertChangeUnauthorized(
                    names, self.proprietary_milestone)

    def test_access_for_ordinary_user(self):
        # Regular users have to public attributes of milestones for
        # private and public products.
        user = self.factory.makePerson()
        with person_logged_in(user):
            self.assertAccessAuthorized(
                self.expected_get_permissions[CheckerPublic],
                self.public_milestone)
            self.assertAccessAuthorized(
                self.expected_get_permissions[CheckerPublic],
                self.proprietary_milestone)

            # They have access to attributes requiring the permission
            # launchpad.View, launchpad.LimitedView or
            # launchpad.AnyAllowedPerson of milestones for public
            # products...
            self.assertAccessAuthorized(
                self.expected_get_permissions['launchpad.View'],
                self.public_milestone)
            self.assertAccessAuthorized(
                self.expected_get_permissions['launchpad.LimitedView'],
                self.public_milestone)
            self.assertAccessAuthorized(
                self.expected_get_permissions['launchpad.AnyAllowedPerson'],
                self.public_milestone)

            # ...but not to the same attributes of milestones for private
            # products.
            self.assertAccessUnauthorized(
                self.expected_get_permissions['launchpad.View'],
                self.proprietary_milestone)
            self.assertAccessUnauthorized(
                self.expected_get_permissions['launchpad.LimitedView'],
                self.proprietary_milestone)
            self.assertAccessUnauthorized(
                self.expected_get_permissions['launchpad.AnyAllowedPerson'],
                self.proprietary_milestone)

            # They cannot access other attributes.
            for permission, names in self.expected_get_permissions.items():
                if permission in (
                    CheckerPublic, 'launchpad.View', 'launchpad.LimitedView',
                    'launchpad.AnyAllowedPerson'):
                    continue
                self.assertAccessUnauthorized(names, self.public_milestone)
                self.assertAccessUnauthorized(
                    names, self.proprietary_milestone)

            # They cannot change attributes.
            for permission, names in self.expected_set_permissions.items():
                self.assertChangeUnauthorized(names, self.public_milestone)
                self.assertChangeUnauthorized(
                    names, self.proprietary_milestone)

    def test_access_for_user_with_grant_for_private_product(self):
        # Users with a policy grant for a private product have access
        # to most attributes of the private product.
        user = self.factory.makePerson()
        with person_logged_in(self.proprietary_product_owner):
            bug = self.factory.makeBug(
                target=self.proprietary_product,
                owner=self.proprietary_product_owner)
            bug.subscribe(user, subscribed_by=self.proprietary_product_owner)

        with person_logged_in(user):
            self.assertAccessAuthorized(
                self.expected_get_permissions[CheckerPublic],
                self.proprietary_milestone)

            # They have access to attributes requiring the permission
            # launchpad.LimitedView of milestones for the private
            # product.
            self.assertAccessAuthorized(
                self.expected_get_permissions['launchpad.LimitedView'],
                self.proprietary_milestone)

            # They cannot access other attributes.
            for permission, names in self.expected_get_permissions.items():
                if permission in (
                    CheckerPublic, 'launchpad.LimitedView'):
                    continue
                self.assertAccessUnauthorized(
                    names, self.proprietary_milestone)

            # They cannot change attributes.
            for names in self.expected_set_permissions.values():
                self.assertChangeUnauthorized(
                    names, self.proprietary_milestone)

    def test_access_for_user_with_artifact_grant_for_private_product(self):
        # Users with an artifact grant for a private product have access
        # to attributes requiring the permission launchpad.LimitedView of
        # milestones for the private product.
        user = self.factory.makePerson()
        with person_logged_in(self.proprietary_product_owner):
            getUtility(IService, 'sharing').sharePillarInformation(
                self.proprietary_product, user, self.proprietary_product_owner,
                {InformationType.PROPRIETARY: SharingPermission.ALL})

        with person_logged_in(user):
            self.assertAccessAuthorized(
                self.expected_get_permissions[CheckerPublic],
                self.proprietary_milestone)

            # They have access to attributes requiring the permission
            # launchpad.View, launchpad.LimitedView or
            # launchpad.AnyAllowedPerson of milestones for the private
            # product.
            self.assertAccessAuthorized(
                self.expected_get_permissions['launchpad.View'],
                self.proprietary_milestone)
            self.assertAccessAuthorized(
                self.expected_get_permissions['launchpad.LimitedView'],
                self.proprietary_milestone)
            self.assertAccessAuthorized(
                self.expected_get_permissions['launchpad.AnyAllowedPerson'],
                self.proprietary_milestone)

            # They cannot access other attributes.
            for permission, names in self.expected_get_permissions.items():
                if permission in (
                    CheckerPublic, 'launchpad.View', 'launchpad.LimitedView',
                    'launchpad.AnyAllowedPerson'):
                    continue
                self.assertAccessUnauthorized(
                    names, self.proprietary_milestone)

            # They cannot change attributes.
            for names in self.expected_set_permissions.values():
                self.assertChangeUnauthorized(
                    names, self.proprietary_milestone)

    def test_access_for_product_owner(self):
        # The owner of a private product can access all attributes.
        with person_logged_in(self.proprietary_product_owner):
            for names in self.expected_get_permissions.values():
                self.assertAccessAuthorized(names, self.proprietary_milestone)

            # They can change attributes.
            for permission, names in self.expected_set_permissions.items():
                self.assertChangeAuthorized(names, self.proprietary_milestone)


class HasMilestonesSnapshotTestCase(TestCaseWithFactory):
    """A TestCase for snapshots of pillars with milestones."""

    layer = DatabaseFunctionalLayer

    def check_skipped(self, target):
        """Asserts that fields marked doNotSnapshot are skipped."""
        skipped = [
            'milestones',
            'all_milestones',
            ]
        self.assertThat(target, DoesNotSnapshot(skipped, IHasMilestones))

    def test_product(self):
        product = self.factory.makeProduct()
        self.check_skipped(product)

    def test_distribution(self):
        distribution = self.factory.makeDistribution()
        self.check_skipped(distribution)

    def test_distroseries(self):
        distroseries = self.factory.makeDistroSeries()
        self.check_skipped(distroseries)

    def test_projectgroup(self):
        projectgroup = self.factory.makeProject()
        self.check_skipped(projectgroup)


class MilestoneBugTaskSpecificationTest(TestCaseWithFactory):
    """Test cases for retrieving bugtasks and specifications for a milestone.
    """

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(MilestoneBugTaskSpecificationTest, self).setUp()
        self.owner = self.factory.makePerson()
        self.product = self.factory.makeProduct(name="product1")
        self.milestone = self.factory.makeMilestone(product=self.product)

    def _make_bug(self, **kwargs):
        milestone = kwargs.pop('milestone', None)
        bugtask = self.factory.makeBugTask(**kwargs)
        bugtask.milestone = milestone
        return bugtask

    def _create_items(self, num, factory, **kwargs):
        items = []
        with person_logged_in(self.owner):
            for n in xrange(num):
                items.append(factory(**kwargs))
        return items

    def test_bugtask_retrieval(self):
        # Ensure that all bugtasks on a milestone can be retrieved.
        bugtasks = self._create_items(
            5, self._make_bug,
            milestone=self.milestone,
            owner=self.owner,
            target=self.product,
            )
        self.assertContentEqual(bugtasks, self.milestone.bugtasks(self.owner))

    def test_specification_retrieval(self):
        # Ensure that all specifications on a milestone can be retrieved.
        specifications = self._create_items(
            5, self.factory.makeSpecification,
            milestone=self.milestone,
            owner=self.owner,
            product=self.product,
            )
        self.assertContentEqual(specifications,
                                self.milestone.getSpecifications(None))


class MilestonesContainsPartialSpecifications(TestCaseWithFactory):
    """Milestones list specifications with some workitems targeted to it."""

    layer = DatabaseFunctionalLayer

    def _create_milestones_on_target(self, **kwargs):
        """Create a milestone on a target with work targeted to it.

        Target should be specified using either product or distribution
        argument which is directly passed into makeMilestone call.
        """
        other_milestone = self.factory.makeMilestone(**kwargs)
        target_milestone = self.factory.makeMilestone(**kwargs)
        specification = self.factory.makeSpecification(
            milestone=other_milestone, **kwargs)
        # Create two workitems to ensure this doesn't cause
        # two specifications to be returned.
        self.factory.makeSpecificationWorkItem(
            specification=specification, milestone=target_milestone)
        self.factory.makeSpecificationWorkItem(
            specification=specification, milestone=target_milestone)
        return specification, target_milestone

    def test_milestones_on_product(self):
        spec, target_milestone = self._create_milestones_on_target(
            product=self.factory.makeProduct())
        self.assertContentEqual([spec],
                                target_milestone.getSpecifications(None))

    def test_milestones_on_distribution(self):
        spec, target_milestone = self._create_milestones_on_target(
            distribution=self.factory.makeDistribution())
        self.assertContentEqual([spec],
                                target_milestone.getSpecifications(None))

    def test_milestones_on_project(self):
        # A Project (Project Group) milestone contains all specifications
        # targetted to contained Products (Projects) for milestones of
        # a certain name.
        projectgroup = self.factory.makeProject()
        product = self.factory.makeProduct(project=projectgroup)
        spec, target_milestone = self._create_milestones_on_target(
            product=product)
        milestone = projectgroup.getMilestone(name=target_milestone.name)
        self.assertContentEqual([spec], milestone.getSpecifications(None))

    def makeMixedMilestone(self):
        projectgroup = self.factory.makeProject()
        owner = self.factory.makePerson()
        public_product = self.factory.makeProduct(project=projectgroup)
        public_milestone = self.factory.makeMilestone(product=public_product)
        product = self.factory.makeProduct(
            owner=owner, information_type=InformationType.PROPRIETARY,
            project=projectgroup)
        target_milestone = self.factory.makeMilestone(
            product=product, name=public_milestone.name)
        milestone = projectgroup.getMilestone(name=public_milestone.name)
        return milestone, target_milestone, owner

    def test_getSpecifications_milestone_privacy(self):
        # Ensure getSpecifications respects milestone privacy.
        # This looks wrong, because the specification is actually public, and
        # we don't normally hide specifications based on the visibility of
        # their products.  But we're not trying to hide the specification.
        # We're hiding the fact that this specification is associated with
        # a proprietary Product milestone.  We create a proprietary product
        # because that's the only way to get a proprietary milestone.
        milestone, target_milestone, owner = self.makeMixedMilestone()
        with person_logged_in(owner):
            spec = self.factory.makeSpecification(milestone=target_milestone)
        self.assertContentEqual([],
                                milestone.getSpecifications(None))
        self.assertContentEqual([spec],
                                milestone.getSpecifications(owner))

    def test_getSpecifications_specification_privacy(self):
        # Only specifications visible to the specified user are listed.
        owner = self.factory.makePerson()
        enum = SpecificationSharingPolicy
        product = self.factory.makeProduct(
            owner=owner, specification_sharing_policy=enum.PROPRIETARY)
        milestone = self.factory.makeMilestone(product=product)
        specification = self.factory.makeSpecification(
            information_type=InformationType.PROPRIETARY,
            milestone=milestone)
        self.assertIn(
            specification, list(milestone.getSpecifications(owner)))
        self.assertNotIn(
            specification, list(milestone.getSpecifications(None)))

    def test_milestones_with_deleted_workitems(self):
        # Deleted work items do not cause the specification to show up
        # in the milestone page.
        milestone = self.factory.makeMilestone(
            product=self.factory.makeProduct())
        specification = self.factory.makeSpecification(
            product=milestone.product)
        self.factory.makeSpecificationWorkItem(
            specification=specification, milestone=milestone, deleted=True)
        self.assertContentEqual([], milestone.getSpecifications(None))


class TestMilestoneInformationType(TestCaseWithFactory):
    """Tests for information_type and Milestone."""

    layer = DatabaseFunctionalLayer

    def test_information_type_from_product(self):
        # Milestones should inherit information_type from its product."""
        owner = self.factory.makePerson()
        information_type = InformationType.PROPRIETARY
        product = self.factory.makeProduct(
            owner=owner, information_type=information_type)
        milestone = self.factory.makeMilestone(product=product)
        with person_logged_in(owner):
            self.assertEqual(
                IInformationType(milestone).information_type,
                information_type)


class ProjectMilestoneSecurityAdaperTestCase(TestCaseWithFactory):
    """A TestCase for the security adapter of IProjectGroupMilestone."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(ProjectMilestoneSecurityAdaperTestCase, self).setUp()
        project_group = self.factory.makeProject()
        public_product = self.factory.makeProduct(project=project_group)
        self.factory.makeMilestone(
            product=public_product, name='public-milestone')
        self.proprietary_product_owner = self.factory.makePerson()
        self.proprietary_product = self.factory.makeProduct(
            project=project_group,
            owner=self.proprietary_product_owner,
            information_type=InformationType.PROPRIETARY)
        self.factory.makeMilestone(
            product=self.proprietary_product, name='proprietary-milestone')
        with person_logged_in(self.proprietary_product_owner):
            milestone_1, milestone_2 = project_group.milestones
            if milestone_1.name == 'public-milestone':
                self.public_projectgroup_milestone = milestone_1
                self.proprietary_projectgroup_milestone = milestone_2
            else:
                self.public_projectgroup_milestone = milestone_2
                self.proprietary_projectgroup_milestone = milestone_1

    expected_get_permissions = {
        'launchpad.View': set((
            '_getOfficialTagClause', 'active', 'addBugSubscription',
            'addBugSubscriptionFilter', 'addSubscription',
            'bug_subscriptions', 'bugtasks', 'closeBugsAndBlueprints',
            'code_name', 'createProductRelease', 'dateexpected',
            'destroySelf', 'displayname', 'distribution', 'distroseries',
            'getBugTaskWeightFunction', 'getSpecifications',
            'getSubscription', 'getSubscriptions', 'all_specifications',
            'getUsedBugTagsWithOpenCounts', 'id', 'name',
            'official_bug_tags', 'parent_subscription_target', 'product',
            'product_release', 'productseries', 'removeBugSubscription',
            'searchTasks', 'series_target', 'summary', 'target',
            'target_type_display', 'title', 'userCanAlterBugSubscription',
            'userCanAlterSubscription', 'userHasBugSubscriptions')),
        }

    def test_get_permissions(self):
        checker = getChecker(self.public_projectgroup_milestone)
        self.checkPermissions(
            self.expected_get_permissions, checker.get_permissions, 'get')

    # Project milestones are read-only objects, so no set permissions.
    expected_set_permissions = {
        }

    def test_set_permissions(self):
        checker = getChecker(self.public_projectgroup_milestone)
        self.checkPermissions(
            self.expected_set_permissions, checker.set_permissions, 'set')

    def assertAccessAuthorized(self, attribute_names, obj):
        # Try to access the given attributes of obj. No exception
        # should be raised.
        for name in attribute_names:
            # class Milestone does not implement all attributes defined by
            # class IMilestone. AttributeErrors caused by attempts to
            # access these attribues are not relevant here: We simply
            # want to be sure that no Unauthorized error is raised.
            try:
                getattr(obj, name)
            except AttributeError:
                pass

    def assertAccessUnauthorized(self, attribute_names, obj):
        # Try to access the given attributes of obj. Unauthorized
        # should be raised.
        for name in attribute_names:
            self.assertRaises(Unauthorized, getattr, obj, name)

    def test_access_for_anonymous(self):
        # Anonymous users have access to public project group milestones.
        with person_logged_in(ANONYMOUS):
            self.assertAccessAuthorized(
                self.expected_get_permissions['launchpad.View'],
                self.public_projectgroup_milestone)

            # ...but not to private project group milestones.
            self.assertAccessUnauthorized(
                self.expected_get_permissions['launchpad.View'],
                self.proprietary_projectgroup_milestone)

    def test_access_for_ordinary_user(self):
        # Regular users have to public project group milestones.
        user = self.factory.makePerson()
        with person_logged_in(user):
            self.assertAccessAuthorized(
                self.expected_get_permissions['launchpad.View'],
                self.public_projectgroup_milestone)

            # ...but not to private project group milestones.
            self.assertAccessUnauthorized(
                self.expected_get_permissions['launchpad.View'],
                self.proprietary_projectgroup_milestone)

    def test_access_for_user_with_grant_for_private_product(self):
        # Users with a policy grant for a private product have access
        # to private project group milestones.
        user = self.factory.makePerson()
        with person_logged_in(self.proprietary_product_owner):
            getUtility(IService, 'sharing').sharePillarInformation(
                self.proprietary_product, user, self.proprietary_product_owner,
                {InformationType.PROPRIETARY: SharingPermission.ALL})

        with person_logged_in(user):
            self.assertAccessAuthorized(
                self.expected_get_permissions['launchpad.View'],
                self.proprietary_projectgroup_milestone)

    def test_access_for_product_owner(self):
        # The owner of a private product can access a rpivate project group
        # milestone.
        with person_logged_in(self.proprietary_product_owner):
            self.assertAccessAuthorized(
                self.expected_get_permissions['launchpad.View'],
                self.proprietary_projectgroup_milestone)
