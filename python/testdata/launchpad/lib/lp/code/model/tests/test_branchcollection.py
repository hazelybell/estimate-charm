# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for branch collections."""

__metaclass__ = type

from datetime import (
    datetime,
    timedelta,
    )
from operator import attrgetter

import pytz
from storm.store import (
    EmptyResultSet,
    Store,
    )
from testtools.matchers import Equals
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.app.interfaces.services import IService
from lp.code.enums import (
    BranchLifecycleStatus,
    BranchMergeProposalStatus,
    BranchSubscriptionDiffSize,
    BranchSubscriptionNotificationLevel,
    BranchType,
    CodeReviewNotificationLevel,
    )
from lp.code.interfaces.branch import DEFAULT_BRANCH_STATUS_IN_LISTING
from lp.code.interfaces.branchcollection import (
    IAllBranches,
    IBranchCollection,
    )
from lp.code.interfaces.codehosting import LAUNCHPAD_SERVICES
from lp.code.model.branch import Branch
from lp.code.model.branchcollection import GenericBranchCollection
from lp.code.tests.helpers import remove_all_sample_data_branches
from lp.registry.enums import PersonVisibility
from lp.registry.interfaces.person import TeamMembershipPolicy
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.services.database.interfaces import IStore
from lp.services.webapp.publisher import canonical_url
from lp.testing import (
    person_logged_in,
    run_with_login,
    StormStatementRecorder,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    )
from lp.testing.matchers import HasQueryCount


class TestBranchCollectionAdaptation(TestCaseWithFactory):
    """Check that certain objects can be adapted to a branch collection."""

    layer = DatabaseFunctionalLayer

    def assertCollection(self, target):
        self.assertIsNot(None, IBranchCollection(target, None))

    def test_product(self):
        # A product can be adapted to a branch collection.
        self.assertCollection(self.factory.makeProduct())

    def test_project(self):
        # A project can be adapted to a branch collection.
        self.assertCollection(self.factory.makeProject())

    def test_person(self):
        # A person can be adapted to a branch collection.
        self.assertCollection(self.factory.makePerson())

    def test_distribution(self):
        # A distribution can be adapted to a branch collection.
        self.assertCollection(self.factory.makeDistribution())

    def test_distro_series(self):
        # A distro series can be adapted to a branch collection.
        self.assertCollection(self.factory.makeDistroSeries())

    def test_source_package(self):
        # A source package can be adapted to a branch collection.
        self.assertCollection(self.factory.makeSourcePackage())

    def test_distribution_source_package(self):
        # A distribution source pakcage can be adapted to a branch collection.
        self.assertCollection(self.factory.makeDistributionSourcePackage())


class TestGenericBranchCollection(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestGenericBranchCollection, self).setUp()
        remove_all_sample_data_branches()
        self.store = IStore(Branch)

    def test_provides_branchcollection(self):
        # `GenericBranchCollection` provides the `IBranchCollection`
        # interface.
        self.assertProvides(
            GenericBranchCollection(self.store), IBranchCollection)

    def test_getBranches_no_filter_no_branches(self):
        # If no filter is specified, then the collection is of all branches in
        # Launchpad. By default, there are no branches.
        collection = GenericBranchCollection(self.store)
        self.assertEqual([], list(collection.getBranches()))

    def test_getBranches_no_filter(self):
        # If no filter is specified, then the collection is of all branches in
        # Launchpad.
        collection = GenericBranchCollection(self.store)
        branch = self.factory.makeAnyBranch()
        self.assertEqual([branch], list(collection.getBranches()))

    def test_getBranches_product_filter(self):
        # If the specified filter is for the branches of a particular product,
        # then the collection contains only branches of that product.
        branch = self.factory.makeProductBranch()
        self.factory.makeAnyBranch()
        collection = GenericBranchCollection(
            self.store, [Branch.product == branch.product])
        self.assertEqual([branch], list(collection.getBranches()))

    def test_getBranches_caches_viewers(self):
        # getBranches() caches the user as a known viewer so that
        # branch.visibleByUser() does not have to hit the database.
        collection = GenericBranchCollection(self.store)
        owner = self.factory.makePerson()
        product = self.factory.makeProduct()
        branch = self.factory.makeProductBranch(
            owner=owner, product=product,
            information_type=InformationType.USERDATA)
        someone = self.factory.makePerson()
        with person_logged_in(owner):
            getUtility(IService, 'sharing').ensureAccessGrants(
                [someone], owner, branches=[branch], ignore_permissions=True)
        [branch] = list(collection.visibleByUser(someone).getBranches())
        with StormStatementRecorder() as recorder:
            self.assertTrue(branch.visibleByUser(someone))
            self.assertThat(recorder, HasQueryCount(Equals(0)))

    def test_getBranchIds(self):
        branch = self.factory.makeProductBranch()
        self.factory.makeAnyBranch()
        collection = GenericBranchCollection(
            self.store, [Branch.product == branch.product])
        self.assertEqual([branch.id], list(collection.getBranchIds()))

    def test_count(self):
        # The 'count' property of a collection is the number of elements in
        # the collection.
        collection = GenericBranchCollection(self.store)
        self.assertEqual(0, collection.count())
        for i in range(3):
            self.factory.makeAnyBranch()
        self.assertEqual(3, collection.count())

    def test_count_respects_filter(self):
        # If a collection is a subset of all possible branches, then the count
        # will be the size of that subset. That is, 'count' respects any
        # filters that are applied.
        branch = self.factory.makeProductBranch()
        self.factory.makeAnyBranch()
        collection = GenericBranchCollection(
            self.store, [Branch.product == branch.product])
        self.assertEqual(1, collection.count())

    def test_preloadVisibleStackedOnBranches_visible_private_branches(self):
        person = self.factory.makePerson()
        branch_number = 2
        depth = 3
        # Create private branches person can see.
        branches = []
        for i in range(branch_number):
            branches.append(
                self.factory.makeStackedOnBranchChain(
                    owner=person, depth=depth,
                    information_type=InformationType.USERDATA))
        with person_logged_in(person):
            all_branches = (
                GenericBranchCollection.preloadVisibleStackedOnBranches(
                    branches, person))
        self.assertEqual(len(all_branches), branch_number * depth)

    def test_preloadVisibleStackedOnBranches_anon_public_branches(self):
        branch_number = 2
        depth = 3
        # Create public branches.
        branches = []
        for i in range(branch_number):
            branches.append(
                self.factory.makeStackedOnBranchChain(depth=depth))
        all_branches = (
            GenericBranchCollection.preloadVisibleStackedOnBranches(branches))
        self.assertEqual(len(all_branches), branch_number * depth)

    def test_preloadVisibleStackedOnBranches_non_anon_public_branches(self):
        person = self.factory.makePerson()
        branch_number = 2
        depth = 3
        # Create public branches.
        branches = []
        for i in range(branch_number):
            branches.append(
                self.factory.makeStackedOnBranchChain(
                    owner=person, depth=depth))
        with person_logged_in(person):
            all_branches = (
                GenericBranchCollection.preloadVisibleStackedOnBranches(
                    branches, person))
        self.assertEqual(len(all_branches), branch_number * depth)


class TestBranchCollectionFilters(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        remove_all_sample_data_branches()
        self.all_branches = getUtility(IAllBranches)

    def test_order_by_product_name(self):
        # The result of getBranches() can be ordered by `Product.name`, no
        # matter what filters are applied.
        aardvark = self.factory.makeProduct(name='aardvark')
        badger = self.factory.makeProduct(name='badger')
        branch_a = self.factory.makeProductBranch(product=aardvark)
        branch_b = self.factory.makeProductBranch(product=badger)
        branch_c = self.factory.makePersonalBranch()
        self.assertEqual(
            sorted([branch_a, branch_b, branch_c]),
            sorted(self.all_branches.getBranches()
                 .order_by(Branch.target_suffix)))

    def test_count_respects_visibleByUser_filter(self):
        # IBranchCollection.count() returns the number of branches that
        # getBranches() yields, even when the visibleByUser filter is applied.
        branch = self.factory.makeAnyBranch()
        self.factory.makeAnyBranch(information_type=InformationType.USERDATA)
        collection = self.all_branches.visibleByUser(branch.owner)
        self.assertEqual(1, collection.getBranches().count())
        self.assertEqual(1, len(list(collection.getBranches())))
        self.assertEqual(1, collection.count())

    def test_ownedBy(self):
        # 'ownedBy' returns a new collection restricted to branches owned by
        # the given person.
        branch = self.factory.makeAnyBranch()
        self.factory.makeAnyBranch()
        collection = self.all_branches.ownedBy(branch.owner)
        self.assertEqual([branch], list(collection.getBranches()))

    def test_ownedByTeamMember(self):
        # 'ownedBy' returns a new collection restricted to branches owned by
        # any team of which the given person is a member.
        person = self.factory.makePerson()
        team = self.factory.makeTeam(members=[person])
        branch = self.factory.makeAnyBranch(owner=team)
        self.factory.makeAnyBranch()
        collection = self.all_branches.ownedByTeamMember(person)
        self.assertEqual([branch], list(collection.getBranches()))

    def test_in_product(self):
        # 'inProduct' returns a new collection restricted to branches in the
        # given product.
        #
        # NOTE: JonathanLange 2009-02-11: Maybe this should be a more generic
        # method called 'onTarget' that takes a person (for junk), package or
        # product.
        branch = self.factory.makeProductBranch()
        self.factory.makeProductBranch()
        self.factory.makeAnyBranch()
        collection = self.all_branches.inProduct(branch.product)
        self.assertEqual([branch], list(collection.getBranches()))

    def test_inProject(self):
        # 'inProject' returns a new collection restricted to branches in the
        # given project.
        branch = self.factory.makeProductBranch()
        self.factory.makeProductBranch()
        self.factory.makeAnyBranch()
        project = self.factory.makeProject()
        removeSecurityProxy(branch.product).project = project
        collection = self.all_branches.inProject(project)
        self.assertEqual([branch], list(collection.getBranches()))

    def test_isExclusive(self):
        # 'isExclusive' is restricted to branches owned by exclusive
        # teams and users.
        user = self.factory.makePerson()
        team = self.factory.makeTeam(
            membership_policy=TeamMembershipPolicy.RESTRICTED)
        other_team = self.factory.makeTeam(
            membership_policy=TeamMembershipPolicy.OPEN)
        team_branch = self.factory.makeAnyBranch(owner=team)
        user_branch = self.factory.makeAnyBranch(owner=user)
        self.factory.makeAnyBranch(owner=other_team)
        collection = self.all_branches.isExclusive()
        self.assertContentEqual(
            [team_branch, user_branch], list(collection.getBranches()))

    def test_inProduct_and_isExclusive(self):
        # 'inProduct' and 'isExclusive' can combine to form a collection that
        # is restricted to branches of a particular product owned exclusive
        # teams and users.
        team = self.factory.makeTeam(
            membership_policy=TeamMembershipPolicy.RESTRICTED)
        other_team = self.factory.makeTeam(
            membership_policy=TeamMembershipPolicy.OPEN)
        product = self.factory.makeProduct()
        branch = self.factory.makeProductBranch(product=product, owner=team)
        self.factory.makeAnyBranch(owner=team)
        self.factory.makeProductBranch(product=product, owner=other_team)
        collection = self.all_branches.inProduct(product).isExclusive()
        self.assertEqual([branch], list(collection.getBranches()))
        collection = self.all_branches.isExclusive().inProduct(product)
        self.assertEqual([branch], list(collection.getBranches()))

    def test_isSeries(self):
        # 'isSeries' is restricted to branches linked to product series.
        series = self.factory.makeProductSeries()
        branch = self.factory.makeAnyBranch(product=series.product)
        with person_logged_in(series.product.owner):
            series.branch = branch
        self.factory.makeAnyBranch(product=series.product)
        collection = self.all_branches.isSeries()
        self.assertContentEqual([branch], list(collection.getBranches()))

    def test_ownedBy_and_isSeries(self):
        # 'ownedBy' and 'inSeries' can combine to form a collection that is
        # restricted to branches linked to product series owned by a particular
        # person.
        person = self.factory.makePerson()
        series = self.factory.makeProductSeries()
        branch = self.factory.makeProductBranch(
            product=series.product, owner=person)
        with person_logged_in(series.product.owner):
            series.branch = branch
        self.factory.makeAnyBranch(owner=person)
        self.factory.makeProductBranch(product=series.product)
        collection = self.all_branches.isSeries().ownedBy(person)
        self.assertEqual([branch], list(collection.getBranches()))
        collection = self.all_branches.ownedBy(person).isSeries()
        self.assertEqual([branch], list(collection.getBranches()))

    def test_ownedBy_and_inProduct(self):
        # 'ownedBy' and 'inProduct' can combine to form a collection that is
        # restricted to branches of a particular product owned by a particular
        # person.
        person = self.factory.makePerson()
        product = self.factory.makeProduct()
        branch = self.factory.makeProductBranch(product=product, owner=person)
        self.factory.makeAnyBranch(owner=person)
        self.factory.makeProductBranch(product=product)
        collection = self.all_branches.inProduct(product).ownedBy(person)
        self.assertEqual([branch], list(collection.getBranches()))
        collection = self.all_branches.ownedBy(person).inProduct(product)
        self.assertEqual([branch], list(collection.getBranches()))

    def test_ownedBy_and_isPrivate(self):
        # 'ownedBy' and 'isPrivate' can combine to form a collection that is
        # restricted to private branches owned by a particular person.
        person = self.factory.makePerson()
        product = self.factory.makeProduct()
        branch = self.factory.makeProductBranch(
            product=product, owner=person,
            information_type=InformationType.USERDATA)
        self.factory.makeAnyBranch(owner=person)
        self.factory.makeProductBranch(product=product)
        collection = self.all_branches.isPrivate().ownedBy(person)
        self.assertEqual([branch], list(collection.getBranches()))
        collection = self.all_branches.ownedBy(person).isPrivate()
        self.assertEqual([branch], list(collection.getBranches()))

    def test_ownedByTeamMember_and_inProduct(self):
        # 'ownedBy' and 'inProduct' can combine to form a collection that is
        # restricted to branches of a particular product owned by a particular
        # person or team of which the person is a member.
        person = self.factory.makePerson()
        team = self.factory.makeTeam(members=[person])
        product = self.factory.makeProduct()
        branch = self.factory.makeProductBranch(product=product, owner=person)
        branch2 = self.factory.makeProductBranch(product=product, owner=team)
        self.factory.makeAnyBranch(owner=person)
        self.factory.makeProductBranch(product=product)
        product_branches = self.all_branches.inProduct(product)
        collection = product_branches.ownedByTeamMember(person)
        self.assertContentEqual([branch, branch2], collection.getBranches())
        person_branches = self.all_branches.ownedByTeamMember(person)
        collection = person_branches.inProduct(product)
        self.assertContentEqual([branch, branch2], collection.getBranches())

    def test_in_source_package(self):
        # 'inSourcePackage' returns a new collection that only has branches in
        # the given source package.
        branch = self.factory.makePackageBranch()
        self.factory.makePackageBranch()
        self.factory.makeAnyBranch()
        collection = self.all_branches.inSourcePackage(branch.sourcepackage)
        self.assertEqual([branch], list(collection.getBranches()))

    def test_in_distribution(self):
        # 'inDistribution' returns a new collection that only has branches
        # that are source package branches associated with distribution series
        # for the distribution specified.
        series_one = self.factory.makeDistroSeries()
        distro = series_one.distribution
        series_two = self.factory.makeDistroSeries(distribution=distro)
        # Make two branches in the same distribution, but different series and
        # source packages.
        branch = self.factory.makePackageBranch(distroseries=series_one)
        branch2 = self.factory.makePackageBranch(distroseries=series_two)
        # Another branch in a different distribution.
        self.factory.makePackageBranch()
        # And a product branch.
        self.factory.makeProductBranch()
        collection = self.all_branches.inDistribution(distro)
        self.assertEqual(
            sorted([branch, branch2]), sorted(collection.getBranches()))

    def test_in_distro_series(self):
        # 'inDistroSeries' returns a new collection that only has branches
        # that are source package branches associated with the distribution
        # series specified.
        series_one = self.factory.makeDistroSeries()
        series_two = self.factory.makeDistroSeries(
            distribution=series_one.distribution)
        # Make two branches in the same distroseries, but different source
        # packages.
        branch = self.factory.makePackageBranch(distroseries=series_one)
        branch2 = self.factory.makePackageBranch(distroseries=series_one)
        # Another branch in a different series.
        self.factory.makePackageBranch(distroseries=series_two)
        # And a product branch.
        self.factory.makeProductBranch()
        collection = self.all_branches.inDistroSeries(series_one)
        self.assertEqual(
            sorted([branch, branch2]), sorted(collection.getBranches()))

    def _makeOffical(self, branch, pocket):
        registrant = branch.sourcepackage.distribution.owner
        with person_logged_in(registrant):
            branch.sourcepackage.setBranch(pocket, branch, registrant)

    def test_official_branches(self):
        # `officialBranches` returns a new collection that only has branches
        # that have been officially linked to a source package.
        branch1 = self.factory.makePackageBranch()
        self._makeOffical(branch1, PackagePublishingPocket.RELEASE)
        branch2 = self.factory.makePackageBranch()
        self._makeOffical(branch2, PackagePublishingPocket.BACKPORTS)
        self.factory.makePackageBranch()
        self.factory.makePackageBranch()
        collection = self.all_branches.officialBranches()
        self.assertEqual(
            sorted([branch1, branch2]), sorted(collection.getBranches()))

    def test_official_branches_pocket(self):
        # If passed a pocket, `officialBranches` returns a new collection that
        # only has branches that have been officially linked to a source
        # package in that pocket.
        branch1 = self.factory.makePackageBranch()
        self._makeOffical(branch1, PackagePublishingPocket.RELEASE)
        branch2 = self.factory.makePackageBranch()
        self._makeOffical(branch2, PackagePublishingPocket.BACKPORTS)
        self.factory.makePackageBranch()
        self.factory.makePackageBranch()
        collection = self.all_branches.officialBranches(
            PackagePublishingPocket.BACKPORTS)
        self.assertEqual(
            sorted([branch2]), sorted(collection.getBranches()))

    def test_in_distribution_source_package(self):
        # 'inDistributionSourcePackage' returns a new collection that only has
        # branches for the source package across any distroseries of the
        # distribution.
        series_one = self.factory.makeDistroSeries()
        series_two = self.factory.makeDistroSeries(
            distribution=series_one.distribution)
        package = self.factory.makeSourcePackageName()
        sourcepackage_one = self.factory.makeSourcePackage(
            sourcepackagename=package, distroseries=series_one)
        sourcepackage_two = self.factory.makeSourcePackage(
            sourcepackagename=package, distroseries=series_two)
        sourcepackage_other_distro = self.factory.makeSourcePackage(
            sourcepackagename=package)
        branch = self.factory.makePackageBranch(
            sourcepackage=sourcepackage_one)
        branch2 = self.factory.makePackageBranch(
            sourcepackage=sourcepackage_two)
        self.factory.makePackageBranch(
            sourcepackage=sourcepackage_other_distro)
        self.factory.makePackageBranch()
        self.factory.makeAnyBranch()
        distro_source_package = self.factory.makeDistributionSourcePackage(
            sourcepackagename=package, distribution=series_one.distribution)
        collection = self.all_branches.inDistributionSourcePackage(
            distro_source_package)
        self.assertEqual(
            sorted([branch, branch2]), sorted(collection.getBranches()))

    def test_withLifecycleStatus(self):
        # 'withLifecycleStatus' returns a new collection that only has
        # branches with the given lifecycle statuses.
        branch1 = self.factory.makeAnyBranch(
            lifecycle_status=BranchLifecycleStatus.DEVELOPMENT)
        self.factory.makeAnyBranch(
            lifecycle_status=BranchLifecycleStatus.ABANDONED)
        branch3 = self.factory.makeAnyBranch(
            lifecycle_status=BranchLifecycleStatus.MATURE)
        branch4 = self.factory.makeAnyBranch(
            lifecycle_status=BranchLifecycleStatus.DEVELOPMENT)
        collection = self.all_branches.withLifecycleStatus(
            BranchLifecycleStatus.DEVELOPMENT,
            BranchLifecycleStatus.MATURE)
        self.assertEqual(
            sorted([branch1, branch3, branch4]),
            sorted(collection.getBranches()))

    def test_withIds(self):
        # 'withIds' returns a new collection that only has branches with the
        # given ids.
        branch1 = self.factory.makeAnyBranch()
        branch2 = self.factory.makeAnyBranch()
        self.factory.makeAnyBranch()
        ids = [branch1.id, branch2.id]
        collection = self.all_branches.withIds(*ids)
        self.assertEqual(
            sorted([branch1, branch2]),
            sorted(collection.getBranches()))

    def test_registeredBy(self):
        # 'registeredBy' returns a new collection that only has branches that
        # were registered by the given user.
        registrant = self.factory.makePerson()
        branch = self.factory.makeAnyBranch(
            owner=registrant, registrant=registrant)
        removeSecurityProxy(branch).owner = self.factory.makePerson()
        self.factory.makeAnyBranch()
        collection = self.all_branches.registeredBy(registrant)
        self.assertEqual([branch], list(collection.getBranches()))

    def test_subscribedBy(self):
        # 'subscribedBy' returns a new collection that only has branches that
        # the given user is subscribed to.
        branch = self.factory.makeAnyBranch()
        subscriber = self.factory.makePerson()
        branch.subscribe(
            subscriber, BranchSubscriptionNotificationLevel.NOEMAIL,
            BranchSubscriptionDiffSize.NODIFF,
            CodeReviewNotificationLevel.NOEMAIL,
            subscriber)
        collection = self.all_branches.subscribedBy(subscriber)
        self.assertEqual([branch], list(collection.getBranches()))

    def test_withBranchType(self):
        hosted_branch1 = self.factory.makeAnyBranch(
            branch_type=BranchType.HOSTED)
        hosted_branch2 = self.factory.makeAnyBranch(
            branch_type=BranchType.HOSTED)
        mirrored_branch = self.factory.makeAnyBranch(
            branch_type=BranchType.MIRRORED)
        self.factory.makeAnyBranch(
            branch_type=BranchType.IMPORTED)
        branches = self.all_branches.withBranchType(
            BranchType.HOSTED, BranchType.MIRRORED)
        self.assertEqual(
            sorted([hosted_branch1, hosted_branch2, mirrored_branch]),
            sorted(branches.getBranches()))

    def test_scanned(self):
        scanned_branch = self.factory.makeAnyBranch()
        self.factory.makeRevisionsForBranch(scanned_branch)
        # This branch isn't scanned (no revision associated).
        self.factory.makeAnyBranch()
        branches = self.all_branches.scanned()
        self.assertEqual([scanned_branch], list(branches.getBranches()))

    def test_modifiedSince(self):
        # Only branches modified since the time specified will be returned.
        old_branch = self.factory.makeAnyBranch()
        old_branch.date_last_modified = datetime(2008, 1, 1, tzinfo=pytz.UTC)
        new_branch = self.factory.makeAnyBranch()
        new_branch.date_last_modified = datetime(2009, 1, 1, tzinfo=pytz.UTC)
        branches = self.all_branches.modifiedSince(
            datetime(2008, 6, 1, tzinfo=pytz.UTC))
        self.assertEqual([new_branch], list(branches.getBranches()))

    def test_scannedSince(self):
        # Only branches scanned since the time specified will be returned.
        old_branch = self.factory.makeAnyBranch()
        removeSecurityProxy(old_branch).last_scanned = (
            datetime(2008, 1, 1, tzinfo=pytz.UTC))
        new_branch = self.factory.makeAnyBranch()
        removeSecurityProxy(new_branch).last_scanned = (
            datetime(2009, 1, 1, tzinfo=pytz.UTC))
        branches = self.all_branches.scannedSince(
            datetime(2008, 6, 1, tzinfo=pytz.UTC))
        self.assertEqual([new_branch], list(branches.getBranches()))

    def test_targetedBy(self):
        # Only branches that are merge targets are returned.
        target_branch = self.factory.makeProductBranch()
        registrant = self.factory.makePerson()
        self.factory.makeBranchMergeProposal(
            target_branch=target_branch, registrant=registrant)
        # And another not registered by registrant.
        self.factory.makeBranchMergeProposal()
        branches = self.all_branches.targetedBy(registrant)
        self.assertEqual([target_branch], list(branches.getBranches()))

    def test_targetedBy_since(self):
        # Ignore proposals created before 'since'.
        all_branches = self.all_branches
        bmp = self.factory.makeBranchMergeProposal()
        date_created = self.factory.getUniqueDate()
        removeSecurityProxy(bmp).date_created = date_created
        registrant = bmp.registrant
        branches = all_branches.targetedBy(registrant, since=date_created)
        self.assertEqual([bmp.target_branch], list(branches.getBranches()))
        since = self.factory.getUniqueDate()
        branches = all_branches.targetedBy(registrant, since=since)
        self.assertEqual([], list(branches.getBranches()))

    def test_linkedToBugs(self):
        # BranchCollection.linkedToBugs() returns all the branches linked
        # to a given set of bugs.
        all_branches = self.all_branches
        bug = self.factory.makeBug()
        linked_branch = self.factory.makeBranch()
        unlinked_branch = self.factory.makeBranch()
        with person_logged_in(linked_branch.owner):
            bug.linkBranch(linked_branch, linked_branch.owner)
        branches = all_branches.linkedToBugs([bug])
        self.assertContentEqual([linked_branch], branches.getBranches())
        self.assertNotIn(unlinked_branch, list(branches.getBranches()))


class TestGenericBranchCollectionVisibleFilter(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        remove_all_sample_data_branches()
        self.public_branch = self.factory.makeAnyBranch(name='public')
        # We make private branch by stacking a public branch on top of a
        # private one.
        self.private_stacked_on_branch = self.factory.makeAnyBranch(
            information_type=InformationType.USERDATA)
        self.public_stacked_on_branch = self.factory.makeAnyBranch(
            stacked_on=self.private_stacked_on_branch)
        self.private_branch1 = self.factory.makeAnyBranch(
            stacked_on=self.public_stacked_on_branch, name='private1')
        self.private_branch2 = self.factory.makeAnyBranch(
            name='private2', information_type=InformationType.USERDATA)
        self.all_branches = getUtility(IAllBranches)

    def test_all_branches(self):
        # Without the visibleByUser filter, all branches are in the
        # collection.
        self.assertEqual(
            sorted([self.public_branch, self.private_branch1,
                 self.private_branch2, self.public_stacked_on_branch,
                 self.private_stacked_on_branch]),
            sorted(self.all_branches.getBranches()))

    def test_anonymous_sees_only_public(self):
        # Anonymous users can see only public branches.
        branches = self.all_branches.visibleByUser(None)
        self.assertEqual([self.public_branch], list(branches.getBranches()))

    def test_visibility_then_product(self):
        # We can apply other filters after applying the visibleByUser filter.
        # Create another public branch.
        self.factory.makeAnyBranch()
        branches = self.all_branches.visibleByUser(None).inProduct(
            self.public_branch.product).getBranches()
        self.assertEqual([self.public_branch], list(branches))

    def test_random_person_sees_only_public(self):
        # Logged in users with no special permissions can see only public
        # branches.
        person = self.factory.makePerson()
        branches = self.all_branches.visibleByUser(person)
        self.assertEqual([self.public_branch], list(branches.getBranches()))

    def test_owner_sees_own_branches(self):
        # Users can always see the branches that they own, as well as public
        # branches.
        owner = removeSecurityProxy(self.private_branch1).owner
        branches = self.all_branches.visibleByUser(owner)
        self.assertEqual(
            sorted([self.public_branch, self.private_branch1]),
            sorted(branches.getBranches()))

    def test_launchpad_services_sees_all(self):
        # The LAUNCHPAD_SERVICES special user sees *everything*.
        branches = self.all_branches.visibleByUser(LAUNCHPAD_SERVICES)
        self.assertEqual(
            sorted(self.all_branches.getBranches()),
            sorted(branches.getBranches()))

    def test_admins_see_all(self):
        # Launchpad administrators see *everything*.
        admin = self.factory.makePerson()
        admin_team = removeSecurityProxy(
            getUtility(ILaunchpadCelebrities).admin)
        admin_team.addMember(admin, admin_team.teamowner)
        branches = self.all_branches.visibleByUser(admin)
        self.assertEqual(
            sorted(self.all_branches.getBranches()),
            sorted(branches.getBranches()))

    def test_subscribers_can_see_branches(self):
        # A person subscribed to a branch can see it, even if it's private.
        subscriber = self.factory.makePerson()
        removeSecurityProxy(self.private_branch1).subscribe(
            subscriber, BranchSubscriptionNotificationLevel.NOEMAIL,
            BranchSubscriptionDiffSize.NODIFF,
            CodeReviewNotificationLevel.NOEMAIL,
            subscriber)
        branches = self.all_branches.visibleByUser(subscriber)
        self.assertEqual(
            sorted([self.public_branch, self.private_branch1]),
            sorted(branches.getBranches()))

    def test_subscribed_team_members_can_see_branches(self):
        # A person in a team that is subscribed to a branch can see that
        # branch, even if it's private.
        team_owner = self.factory.makePerson()
        team = self.factory.makeTeam(
            membership_policy=TeamMembershipPolicy.MODERATED,
            owner=team_owner)
        private_branch = self.factory.makeAnyBranch(
            information_type=InformationType.USERDATA)
        # Subscribe the team.
        removeSecurityProxy(private_branch).subscribe(
            team, BranchSubscriptionNotificationLevel.NOEMAIL,
            BranchSubscriptionDiffSize.NODIFF,
            CodeReviewNotificationLevel.NOEMAIL,
            team_owner)
        # Members of the team can see the private branch that the team is
        # subscribed to.
        branches = self.all_branches.visibleByUser(team_owner)
        self.assertEqual(
            sorted([self.public_branch, private_branch]),
            sorted(branches.getBranches()))

    def test_private_teams_see_own_private_junk_branches(self):
        # Private teams are given an acess grant to see their private +junk
        # branches.
        team_owner = self.factory.makePerson()
        team = self.factory.makeTeam(
            visibility=PersonVisibility.PRIVATE,
            membership_policy=TeamMembershipPolicy.MODERATED,
            owner=team_owner)
        with person_logged_in(team_owner):
            personal_branch = self.factory.makePersonalBranch(
                owner=team,
                information_type=InformationType.USERDATA)
            # The team is automatically subscribed to the branch since they are
            # the owner. We want to unsubscribe them so that they lose access
            # conferred via subscription and rely instead on the APG.
            personal_branch.unsubscribe(team, team_owner, True)
            # Make another junk branch the team can't see.
            self.factory.makePersonalBranch(
                information_type=InformationType.USERDATA)
            branches = self.all_branches.visibleByUser(team)
        self.assertEqual(
            sorted([self.public_branch, personal_branch]),
            sorted(branches.getBranches()))


class TestExtendedBranchRevisionDetails(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        remove_all_sample_data_branches()
        self.all_branches = getUtility(IAllBranches)

    def test_empty_revisions(self):
        person = self.factory.makePerson()
        rev_details = self.all_branches.getExtendedRevisionDetails(person, [])
        self.assertEqual([], rev_details)
        rev_details = self.all_branches.getExtendedRevisionDetails(
            person, None)
        self.assertEqual([], rev_details)

    def _makeBranchRevisions(self, merge_proposals, branch):
        expected_rev_details = []
        with person_logged_in(branch.owner):
            self.factory.makeRevisionsForBranch(branch, 3)
            branch_revisions = branch.revision_history
            for x in range(0, 3):
                branch_revision = branch_revisions[x]
                rev_info = {
                    'revision': branch_revision,
                    'linked_bugtasks': None,
                    'merge_proposal': None,
                    }
                if x < len(merge_proposals):
                    merge_proposals[x].markAsMerged(
                            branch_revision.sequence)
                    rev_info['merge_proposal'] = merge_proposals[x]
                expected_rev_details.append(rev_info)
        return expected_rev_details, branch_revisions

    def test_some_revisions_with_no_bugs(self):
        branch = self.factory.makeBranch()
        merge_proposals = [
            self.factory.makeBranchMergeProposal(target_branch=branch)
            for x in range(0, 2)]

        expected_rev_details, branch_revisions = (
            self._makeBranchRevisions(merge_proposals, branch))

        result = self.all_branches.getExtendedRevisionDetails(
            branch.owner, branch_revisions)
        self.assertEqual(sorted(expected_rev_details), sorted(result))

    def test_some_revisions_with_bugs(self):
        branch = self.factory.makeBranch()
        merge_proposals = [
            self.factory.makeBranchMergeProposal(target_branch=branch)
            for x in range(0, 2)]

        expected_rev_details, branch_revisions = (
            self._makeBranchRevisions(merge_proposals, branch))

        linked_bugtasks = []
        with person_logged_in(branch.owner):
            for x in range(0, 2):
                bug = self.factory.makeBug()
                merge_proposals[0].source_branch.linkBug(bug, branch.owner)
                linked_bugtasks.append(bug.default_bugtask)
        expected_rev_details[0]['linked_bugtasks'] = linked_bugtasks
        result = self.all_branches.getExtendedRevisionDetails(
            branch.owner, branch_revisions)
        self.assertEqual(sorted(expected_rev_details), sorted(result))

    def test_some_revisions_with_private_bugs(self):
        branch = self.factory.makeBranch()
        merge_proposals = [
            self.factory.makeBranchMergeProposal(target_branch=branch)
            for x in range(0, 2)]

        expected_rev_details, branch_revisions = (
            self._makeBranchRevisions(merge_proposals, branch))

        linked_bugtasks = []
        with person_logged_in(branch.owner):
            for x in range(0, 4):
                information_type = InformationType.PUBLIC
                if x % 2:
                    information_type = InformationType.USERDATA
                bug = self.factory.makeBug(
                    owner=branch.owner, information_type=information_type)
                merge_proposals[0].source_branch.linkBug(bug, branch.owner)
                if information_type == InformationType.PUBLIC:
                    linked_bugtasks.append(bug.default_bugtask)
        expected_rev_details[0]['linked_bugtasks'] = linked_bugtasks

        person = self.factory.makePerson()
        result = self.all_branches.getExtendedRevisionDetails(
            person, branch_revisions)
        self.assertEqual(sorted(expected_rev_details), sorted(result))


class TestBranchMergeProposals(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        remove_all_sample_data_branches()
        self.all_branches = getUtility(IAllBranches)

    def test_empty_branch_merge_proposals(self):
        proposals = self.all_branches.getMergeProposals()
        self.assertEqual([], list(proposals))

    def test_empty_branches_shortcut(self):
        # If you explicitly pass an empty collection of branches,
        # the method shortcuts and gives you an empty result set.  In this
        # way, for_branches=None (the default) has a very different behavior
        # than for_branches=[]: the first is no restriction, while the second
        # excludes everything.
        self.factory.makeBranchMergeProposal()
        proposals = self.all_branches.getMergeProposals(for_branches=[])
        self.assertEqual([], list(proposals))
        self.assertIsInstance(proposals, EmptyResultSet)

    def test_empty_revisions_shortcut(self):
        # If you explicitly pass an empty collection of revision numbers,
        # the method shortcuts and gives you an empty result set.  In this
        # way, merged_revnos=None (the default) has a very different behavior
        # than merged_revnos=[]: the first is no restriction, while the second
        # excludes everything.
        self.factory.makeBranchMergeProposal()
        proposals = self.all_branches.getMergeProposals(merged_revnos=[])
        self.assertEqual([], list(proposals))
        self.assertIsInstance(proposals, EmptyResultSet)

    def test_some_branch_merge_proposals(self):
        mp = self.factory.makeBranchMergeProposal()
        proposals = self.all_branches.getMergeProposals()
        self.assertEqual([mp], list(proposals))

    def test_just_owned_branch_merge_proposals(self):
        # If the collection only includes branches owned by a person, the
        # getMergeProposals() will only return merge proposals for source
        # branches that are owned by that person.
        person = self.factory.makePerson()
        product = self.factory.makeProduct()
        branch1 = self.factory.makeProductBranch(
            product=product, owner=person)
        branch2 = self.factory.makeProductBranch(
            product=product, owner=person)
        branch3 = self.factory.makeProductBranch(product=product)
        self.factory.makeProductBranch(product=product)
        target = self.factory.makeProductBranch(product=product)
        mp1 = self.factory.makeBranchMergeProposal(
            target_branch=target, source_branch=branch1)
        mp2 = self.factory.makeBranchMergeProposal(
            target_branch=target, source_branch=branch2)
        self.factory.makeBranchMergeProposal(
            target_branch=target, source_branch=branch3)
        collection = self.all_branches.ownedBy(person)
        proposals = collection.getMergeProposals()
        self.assertEqual(sorted([mp1, mp2]), sorted(proposals))

    def test_preloading_for_previewdiff(self):
        product = self.factory.makeProduct()
        target = self.factory.makeBranch(product=product)
        owner = self.factory.makePerson()
        branch1 = self.factory.makeBranch(product=product, owner=owner)
        branch2 = self.factory.makeBranch(product=product, owner=owner)
        bmp1 = self.factory.makeBranchMergeProposal(
            target_branch=target, source_branch=branch1)
        bmp2 = self.factory.makeBranchMergeProposal(
            target_branch=target, source_branch=branch2)
        old_date = datetime.now(pytz.UTC) - timedelta(hours=1)
        self.factory.makePreviewDiff(
            merge_proposal=bmp1, date_created=old_date)
        previewdiff1 = self.factory.makePreviewDiff(merge_proposal=bmp1)
        self.factory.makePreviewDiff(
            merge_proposal=bmp2, date_created=old_date)
        previewdiff2 = self.factory.makePreviewDiff(merge_proposal=bmp2)
        Store.of(bmp1).flush()
        Store.of(bmp1).invalidate()
        collection = self.all_branches.ownedBy(owner)
        [pre_bmp1, pre_bmp2] = sorted(
            collection.getMergeProposals(eager_load=True),
            key=attrgetter('id'))
        with StormStatementRecorder() as recorder:
            self.assertEqual(
                removeSecurityProxy(pre_bmp1.preview_diff).id, previewdiff1.id)
            self.assertEqual(
                removeSecurityProxy(pre_bmp2.preview_diff).id, previewdiff2.id)
        self.assertThat(recorder, HasQueryCount(Equals(0)))

    def test_merge_proposals_in_product(self):
        mp1 = self.factory.makeBranchMergeProposal()
        self.factory.makeBranchMergeProposal()
        product = mp1.source_branch.product
        collection = self.all_branches.inProduct(product)
        proposals = collection.getMergeProposals()
        self.assertEqual([mp1], list(proposals))

    def test_merge_proposals_merging_revno(self):
        """Specifying merged_revnos selects the correct merge proposals."""
        target = self.factory.makeBranch()
        mp1 = self.factory.makeBranchMergeProposal(target_branch=target)
        mp2 = self.factory.makeBranchMergeProposal(target_branch=target)
        mp3 = self.factory.makeBranchMergeProposal(target_branch=target)
        with person_logged_in(target.owner):
            mp1.markAsMerged(123)
            mp2.markAsMerged(123)
            mp3.markAsMerged(321)
        collection = self.all_branches
        result = collection.getMergeProposals(
            target_branch=target, merged_revnos=[123])
        self.assertEqual(sorted([mp1, mp2]), sorted(result))
        result = collection.getMergeProposals(
            target_branch=target, merged_revnos=[123, 321])
        self.assertEqual(sorted([mp1, mp2, mp3]), sorted(result))

    def test_target_branch_private(self):
        # The target branch must be in the branch collection, as must the
        # source branch.
        registrant = self.factory.makePerson()
        mp1 = self.factory.makeBranchMergeProposal(registrant=registrant)
        removeSecurityProxy(mp1.target_branch).transitionToInformationType(
            InformationType.USERDATA, registrant, verify_policy=False)
        collection = self.all_branches.visibleByUser(None)
        proposals = collection.getMergeProposals()
        self.assertEqual([], list(proposals))

    def test_status_restriction(self):
        mp1 = self.factory.makeBranchMergeProposal(
            set_state=BranchMergeProposalStatus.WORK_IN_PROGRESS)
        mp2 = self.factory.makeBranchMergeProposal(
            set_state=BranchMergeProposalStatus.NEEDS_REVIEW)
        self.factory.makeBranchMergeProposal(
            set_state=BranchMergeProposalStatus.CODE_APPROVED)
        proposals = self.all_branches.getMergeProposals(
            [BranchMergeProposalStatus.WORK_IN_PROGRESS,
             BranchMergeProposalStatus.NEEDS_REVIEW])
        self.assertEqual(sorted([mp1, mp2]), sorted(proposals))

    def test_status_restriction_with_product_filter(self):
        # getMergeProposals returns the merge proposals with a particular
        # status that are _inside_ the branch collection. mp1 is in the
        # product with NEEDS_REVIEW, mp2 is outside of the product and mp3 has
        # an excluded status.
        mp1 = self.factory.makeBranchMergeProposal(
            set_state=BranchMergeProposalStatus.NEEDS_REVIEW)
        self.factory.makeBranchMergeProposal(
            set_state=BranchMergeProposalStatus.NEEDS_REVIEW)
        product = mp1.source_branch.product
        branch1 = self.factory.makeProductBranch(product=product)
        branch2 = self.factory.makeProductBranch(product=product)
        self.factory.makeBranchMergeProposal(
            target_branch=branch1, source_branch=branch2,
            set_state=BranchMergeProposalStatus.CODE_APPROVED)
        collection = self.all_branches.inProduct(product)
        proposals = collection.getMergeProposals(
            [BranchMergeProposalStatus.NEEDS_REVIEW])
        self.assertEqual([mp1], list(proposals))

    def test_specifying_target_branch(self):
        # If the target_branch is specified, only merge proposals where that
        # branch is the target are returned.
        mp1 = self.factory.makeBranchMergeProposal()
        self.factory.makeBranchMergeProposal()
        proposals = self.all_branches.getMergeProposals(
            target_branch=mp1.target_branch)
        self.assertEqual([mp1], list(proposals))


class TestBranchMergeProposalsForReviewer(TestCaseWithFactory):
    """Tests for IBranchCollection.getProposalsForReviewer()."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        # Use the admin user as we don't care about who can and can't call
        # nominate reviewer in this test.
        TestCaseWithFactory.setUp(self, 'admin@canonical.com')
        remove_all_sample_data_branches()
        self.all_branches = getUtility(IAllBranches)

    def test_getProposalsForReviewer(self):
        reviewer = self.factory.makePerson()
        proposal = self.factory.makeBranchMergeProposal()
        proposal.nominateReviewer(reviewer, reviewer)
        self.factory.makeBranchMergeProposal()
        proposals = self.all_branches.getMergeProposalsForReviewer(reviewer)
        self.assertEqual([proposal], list(proposals))

    def test_getProposalsForReviewer_filter_status(self):
        reviewer = self.factory.makePerson()
        proposal1 = self.factory.makeBranchMergeProposal(
            set_state=BranchMergeProposalStatus.NEEDS_REVIEW)
        proposal1.nominateReviewer(reviewer, reviewer)
        proposal2 = self.factory.makeBranchMergeProposal(
            set_state=BranchMergeProposalStatus.WORK_IN_PROGRESS)
        proposal2.nominateReviewer(reviewer, reviewer)
        proposals = self.all_branches.getMergeProposalsForReviewer(
            reviewer, [BranchMergeProposalStatus.NEEDS_REVIEW])
        self.assertEqual([proposal1], list(proposals))

    def test_getProposalsForReviewer_anonymous(self):
        # Don't include proposals if the target branch is private for
        # anonymous views.
        reviewer = self.factory.makePerson()
        target_branch = self.factory.makeAnyBranch(
            information_type=InformationType.USERDATA)
        proposal = self.factory.makeBranchMergeProposal(
            target_branch=target_branch)
        proposal.nominateReviewer(reviewer, reviewer)
        proposals = self.all_branches.visibleByUser(
            None).getMergeProposalsForReviewer(reviewer)
        self.assertEqual([], list(proposals))

    def test_getProposalsForReviewer_anonymous_source_private(self):
        # Don't include proposals if the source branch is private for
        # anonymous views.
        reviewer = self.factory.makePerson()
        product = self.factory.makeProduct()
        source_branch = self.factory.makeProductBranch(
            product=product, information_type=InformationType.USERDATA)
        target_branch = self.factory.makeProductBranch(product=product)
        proposal = self.factory.makeBranchMergeProposal(
            source_branch=source_branch, target_branch=target_branch)
        proposal.nominateReviewer(reviewer, reviewer)
        proposals = self.all_branches.visibleByUser(
            None).getMergeProposalsForReviewer(reviewer)
        self.assertEqual([], list(proposals))

    def test_getProposalsForReviewer_for_product(self):
        reviewer = self.factory.makePerson()
        proposal = self.factory.makeBranchMergeProposal()
        proposal.nominateReviewer(reviewer, reviewer)
        proposal2 = self.factory.makeBranchMergeProposal()
        proposal2.nominateReviewer(reviewer, reviewer)
        proposals = self.all_branches.inProduct(
            proposal.source_branch.product).getMergeProposalsForReviewer(
            reviewer)
        self.assertEqual([proposal], list(proposals))


class TestSearch(TestCaseWithFactory):
    """Tests for IBranchCollection.search()."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        remove_all_sample_data_branches()
        self.collection = getUtility(IAllBranches)

    def test_exact_match_unique_name(self):
        # If you search for a unique name of a branch that exists, you'll get
        # a single result with a branch with that branch name.
        branch = self.factory.makeAnyBranch()
        self.factory.makeAnyBranch()
        search_results = self.collection.search(branch.unique_name)
        self.assertEqual([branch], list(search_results))

    def test_unique_name_match_not_in_collection(self):
        # If you search for a unique name of a branch that does not exist,
        # you'll get an empty result set.
        branch = self.factory.makeAnyBranch()
        collection = self.collection.inProduct(self.factory.makeProduct())
        search_results = collection.search(branch.unique_name)
        self.assertEqual([], list(search_results))

    def test_exact_match_remote_url(self):
        # If you search for the remote URL of a branch, and there's a branch
        # with that URL, you'll get a single result with a branch with that
        # branch name.
        branch = self.factory.makeAnyBranch(branch_type=BranchType.MIRRORED)
        self.factory.makeAnyBranch()
        search_results = self.collection.search(branch.url)
        self.assertEqual([branch], list(search_results))

    def test_exact_match_launchpad_url(self):
        # If you search for the Launchpad URL of a branch, and there is a
        # branch with that URL, then you get a single result with that branch.
        branch = self.factory.makeAnyBranch()
        self.factory.makeAnyBranch()
        search_results = self.collection.search(branch.codebrowse_url())
        self.assertEqual([branch], list(search_results))

    def test_exact_match_with_lp_colon_url(self):
        branch = self.factory.makeBranch()
        lp_name = 'lp://dev/' + branch.unique_name
        search_results = self.collection.search(lp_name)
        self.assertEqual([branch], list(search_results))

    def test_exact_match_full_url(self):
        branch = self.factory.makeBranch()
        url = canonical_url(branch)
        self.assertEqual([branch], list(self.collection.search(url)))

    def test_exact_match_bad_url(self):
        search_results = self.collection.search('http:hahafail')
        self.assertEqual([], list(search_results))

    def test_exact_match_bzr_identity(self):
        # If you search for the bzr identity of a branch, then you get a
        # single result with that branch.
        branch = self.factory.makeAnyBranch()
        self.factory.makeAnyBranch()
        search_results = self.collection.search(branch.bzr_identity)
        self.assertEqual([branch], list(search_results))

    def test_exact_match_bzr_identity_development_focus(self):
        # If you search for the development focus and it is set, you get a
        # single result with the development focus branch.
        fooix = self.factory.makeProduct(name='fooix')
        branch = self.factory.makeProductBranch(product=fooix)
        run_with_login(
            fooix.owner, setattr, fooix.development_focus, 'branch', branch)
        self.factory.makeAnyBranch()
        search_results = self.collection.search('lp://dev/fooix')
        self.assertEqual([branch], list(search_results))

    def test_bad_match_bzr_identity_development_focus(self):
        # If you search for the development focus for a project where one
        # isn't set, you get an empty search result.
        fooix = self.factory.makeProduct(name='fooix')
        self.factory.makeProductBranch(product=fooix)
        self.factory.makeAnyBranch()
        search_results = self.collection.search('lp://dev/fooix')
        self.assertEqual([], list(search_results))

    def test_bad_match_bzr_identity_no_project(self):
        # If you search for the development focus for a project where one
        # isn't set, you get an empty search result.
        self.factory.makeAnyBranch()
        search_results = self.collection.search('lp://dev/fooix')
        self.assertEqual([], list(search_results))

    def test_exact_match_url_trailing_slash(self):
        # Sometimes, users are inconsiderately unaware of our arbitrary
        # database restrictions and will put trailing slashes on their search
        # queries. Rather bravely, we refuse to explode in this case.
        branch = self.factory.makeAnyBranch()
        self.factory.makeAnyBranch()
        search_results = self.collection.search(branch.codebrowse_url() + '/')
        self.assertEqual([branch], list(search_results))

    def test_match_exact_branch_name(self):
        # search returns all branches with the same name as the search term.
        branch1 = self.factory.makeAnyBranch(name='foo')
        branch2 = self.factory.makeAnyBranch(name='foo')
        self.factory.makeAnyBranch()
        search_results = self.collection.search('foo')
        self.assertEqual(sorted([branch1, branch2]), sorted(search_results))

    def test_match_against_unique_name(self):
        branch = self.factory.makeAnyBranch(name='fooa')
        search_term = branch.product.name + '/foo'
        search_results = self.collection.search(search_term)
        self.assertEqual([branch], list(search_results))

    def test_match_sub_branch_name(self):
        # search returns all branches which have a name of which the search
        # term is a substring.
        branch1 = self.factory.makeAnyBranch(name='afoo')
        branch2 = self.factory.makeAnyBranch(name='foob')
        self.factory.makeAnyBranch()
        search_results = self.collection.search('foo')
        self.assertEqual(sorted([branch1, branch2]), sorted(search_results))

    def test_match_ignores_case(self):
        branch = self.factory.makeAnyBranch(name='foobar')
        search_results = self.collection.search('FOOBAR')
        self.assertEqual([branch], list(search_results))

    def test_dont_match_product_if_in_product(self):
        # If the container is restricted to the product, then we don't match
        # the product name.
        product = self.factory.makeProduct('foo')
        branch1 = self.factory.makeProductBranch(product=product, name='foo')
        self.factory.makeProductBranch(product=product, name='bar')
        search_results = self.collection.inProduct(product).search('foo')
        self.assertEqual([branch1], list(search_results))


class TestGetTeamsWithBranches(TestCaseWithFactory):
    """Test the BranchCollection.getTeamsWithBranches method."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.all_branches = getUtility(IAllBranches)

    def test_no_teams(self):
        # If the user is not a member of any teams, there are no results, even
        # if the person owns a branch themselves.
        person = self.factory.makePerson()
        self.factory.makeAnyBranch(owner=person)
        teams = list(self.all_branches.getTeamsWithBranches(person))
        self.assertEqual([], teams)

    def test_team_branches(self):
        # Return the teams that the user is in, that have branches.
        person = self.factory.makePerson()
        team = self.factory.makeTeam(owner=person)
        self.factory.makeBranch(owner=team)
        # Make another team that person is in that has no branches.
        self.factory.makeTeam(owner=person)
        teams = list(self.all_branches.getTeamsWithBranches(person))
        self.assertEqual([team], teams)

    def test_respects_restrictions(self):
        # Create a team with branches on a product, and another branch in a
        # different namespace owned by a different team that the person is a
        # member of.  Restricting the collection will return just the teams
        # that have branches in that restricted collection.
        person = self.factory.makePerson()
        team1 = self.factory.makeTeam(owner=person)
        branch = self.factory.makeProductBranch(owner=team1)
        # Make another team that person is in that owns a branch in a
        # different namespace to the namespace of the branch owned by team1.
        team2 = self.factory.makeTeam(owner=person)
        self.factory.makeAnyBranch(owner=team2)
        collection = self.all_branches.inProduct(branch.product)
        teams = list(collection.getTeamsWithBranches(person))
        self.assertEqual([team1], teams)


class TestBranchCollectionOwnerCounts(TestCaseWithFactory):
    """Test IBranchCollection.ownerCounts."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        remove_all_sample_data_branches()
        self.all_branches = getUtility(IAllBranches)

    def test_no_branches(self):
        # If there are no branches, we should get zero counts for both.
        person_count, team_count = self.all_branches.ownerCounts()
        self.assertEqual(0, person_count)
        self.assertEqual(0, team_count)

    def test_individual_branch_owners(self):
        # Branches owned by an individual are returned as the first part of
        # the tuple.
        self.factory.makeAnyBranch()
        self.factory.makeAnyBranch()
        person_count, team_count = self.all_branches.ownerCounts()
        self.assertEqual(2, person_count)
        self.assertEqual(0, team_count)

    def test_team_branch_owners(self):
        # Branches owned by teams are returned as the second part of the
        # tuple.
        self.factory.makeAnyBranch(owner=self.factory.makeTeam())
        self.factory.makeAnyBranch(owner=self.factory.makeTeam())
        person_count, team_count = self.all_branches.ownerCounts()
        self.assertEqual(0, person_count)
        self.assertEqual(2, team_count)

    def test_multiple_branches_owned_counted_once(self):
        # Confirming that a person that owns multiple branches only gets
        # counted once.
        individual = self.factory.makePerson()
        team = self.factory.makeTeam()
        for owner in [individual, individual, team, team]:
            self.factory.makeAnyBranch(owner=owner)
        person_count, team_count = self.all_branches.ownerCounts()
        self.assertEqual(1, person_count)
        self.assertEqual(1, team_count)

    def test_counts_limited_by_collection(self):
        # For collections that are constrained in some way, we only get counts
        # for the constrained collection.
        b1 = self.factory.makeProductBranch()
        product = b1.product
        self.factory.makeProductBranch(
            product=product, lifecycle_status=BranchLifecycleStatus.MERGED)
        self.factory.makeAnyBranch()
        collection = self.all_branches.inProduct(product).withLifecycleStatus(
            *DEFAULT_BRANCH_STATUS_IN_LISTING)
        person_count, team_count = collection.ownerCounts()
        self.assertEqual(1, person_count)
