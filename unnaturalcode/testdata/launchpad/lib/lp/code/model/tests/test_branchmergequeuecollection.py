# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for branch merge queue collections."""

__metaclass__ = type

from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.code.interfaces.branchmergequeuecollection import (
    IAllBranchMergeQueues,
    IBranchMergeQueueCollection,
    )
from lp.code.interfaces.codehosting import LAUNCHPAD_SERVICES
from lp.code.model.branchmergequeue import BranchMergeQueue
from lp.code.model.branchmergequeuecollection import (
    GenericBranchMergeQueueCollection,
    )
from lp.services.database.interfaces import IMasterStore
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


class TestGenericBranchMergeQueueCollection(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.store = IMasterStore(BranchMergeQueue)

    def test_provides_branchmergequeuecollection(self):
        # `GenericBranchMergeQueueCollection`
        # provides the `IBranchMergeQueueCollection` interface.
        self.assertProvides(
            GenericBranchMergeQueueCollection(self.store),
            IBranchMergeQueueCollection)

    def test_getMergeQueues_no_filter_no_queues(self):
        # If no filter is specified, then the collection is of all branches
        # merge queues. By default, there are no branch merge queues.
        collection = GenericBranchMergeQueueCollection(self.store)
        self.assertEqual([], list(collection.getMergeQueues()))

    def test_getMergeQueues_no_filter(self):
        # If no filter is specified, then the collection is of all branch
        # merge queues.
        collection = GenericBranchMergeQueueCollection(self.store)
        queue = self.factory.makeBranchMergeQueue()
        self.assertEqual([queue], list(collection.getMergeQueues()))

    def test_count(self):
        # The 'count' property of a collection is the number of elements in
        # the collection.
        collection = GenericBranchMergeQueueCollection(self.store)
        self.assertEqual(0, collection.count())
        for i in range(3):
            self.factory.makeBranchMergeQueue()
        self.assertEqual(3, collection.count())

    def test_count_respects_filter(self):
        # If a collection is a subset of all possible queues, then the count
        # will be the size of that subset. That is, 'count' respects any
        # filters that are applied.
        person = self.factory.makePerson()
        self.factory.makeBranchMergeQueue(owner=person)
        self.factory.makeAnyBranch()
        collection = GenericBranchMergeQueueCollection(
            self.store, [BranchMergeQueue.owner == person])
        self.assertEqual(1, collection.count())


class TestBranchMergeQueueCollectionFilters(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.all_queues = getUtility(IAllBranchMergeQueues)

    def test_count_respects_visibleByUser_filter(self):
        # IBranchMergeQueueCollection.count() returns the number of queues
        # that getMergeQueues() yields, even when the visibleByUser filter is
        # applied.
        branch = self.factory.makeAnyBranch(
            information_type=InformationType.USERDATA)
        naked_branch = removeSecurityProxy(branch)
        self.factory.makeBranchMergeQueue(branches=[naked_branch])
        branch2 = self.factory.makeAnyBranch(
            information_type=InformationType.USERDATA)
        naked_branch2 = removeSecurityProxy(branch2)
        self.factory.makeBranchMergeQueue(branches=[naked_branch2])
        collection = self.all_queues.visibleByUser(naked_branch.owner)
        self.assertEqual(1, len(collection.getMergeQueues()))
        self.assertEqual(1, collection.count())

    def test_ownedBy(self):
        # 'ownedBy' returns a new collection restricted to queues owned by
        # the given person.
        queue = self.factory.makeBranchMergeQueue()
        self.factory.makeBranchMergeQueue()
        collection = self.all_queues.ownedBy(queue.owner)
        self.assertEqual([queue], collection.getMergeQueues())


class TestGenericBranchMergeQueueCollectionVisibleFilter(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        public_branch = self.factory.makeAnyBranch(name='public')
        self.queue_with_public_branch = self.factory.makeBranchMergeQueue(
            branches=[removeSecurityProxy(public_branch)])
        private_branch1 = self.factory.makeAnyBranch(
            name='private1', information_type=InformationType.USERDATA)
        naked_private_branch1 = removeSecurityProxy(private_branch1)
        self.private_branch1_owner = naked_private_branch1.owner
        self.queue1_with_private_branch = self.factory.makeBranchMergeQueue(
            branches=[naked_private_branch1])
        private_branch2 = self.factory.makeAnyBranch(
            name='private2', information_type=InformationType.USERDATA)
        self.queue2_with_private_branch = self.factory.makeBranchMergeQueue(
            branches=[removeSecurityProxy(private_branch2)])
        self.all_queues = getUtility(IAllBranchMergeQueues)

    def test_all_queues(self):
        # Without the visibleByUser filter, all queues are in the
        # collection.
        self.assertEqual(
            sorted([self.queue_with_public_branch,
                    self.queue1_with_private_branch,
                    self.queue2_with_private_branch]),
            sorted(self.all_queues.getMergeQueues()))

    def test_anonymous_sees_only_public(self):
        # Anonymous users can see only queues with public branches.
        queues = self.all_queues.visibleByUser(None)
        self.assertEqual([self.queue_with_public_branch],
                         list(queues.getMergeQueues()))

    def test_random_person_sees_only_public(self):
        # Logged in users with no special permissions can see only queues with
        # public branches.
        person = self.factory.makePerson()
        queues = self.all_queues.visibleByUser(person)
        self.assertEqual([self.queue_with_public_branch],
                         list(queues.getMergeQueues()))

    def test_owner_sees_own_branches(self):
        # Users can always see the queues with branches that they own, as well
        # as queues with public branches.
        queues = self.all_queues.visibleByUser(self.private_branch1_owner)
        self.assertEqual(
            sorted([self.queue_with_public_branch,
                    self.queue1_with_private_branch]),
            sorted(queues.getMergeQueues()))

    def test_owner_member_sees_own_queues(self):
        # Members of teams that own queues can see queues owned by those
        # teams, as well as public branches.
        team_owner = self.factory.makePerson()
        team = self.factory.makeTeam(team_owner)
        private_branch = self.factory.makeAnyBranch(
            owner=team, name='team',
            information_type=InformationType.USERDATA)
        queue_with_private_branch = self.factory.makeBranchMergeQueue(
            branches=[removeSecurityProxy(private_branch)])
        queues = self.all_queues.visibleByUser(team_owner)
        self.assertEqual(
            sorted([self.queue_with_public_branch,
                    queue_with_private_branch]),
            sorted(queues.getMergeQueues()))

    def test_launchpad_services_sees_all(self):
        # The LAUNCHPAD_SERVICES special user sees *everything*.
        queues = self.all_queues.visibleByUser(LAUNCHPAD_SERVICES)
        self.assertEqual(
            sorted(self.all_queues.getMergeQueues()),
            sorted(queues.getMergeQueues()))

    def test_admins_see_all(self):
        # Launchpad administrators see *everything*.
        admin = self.factory.makePerson()
        admin_team = removeSecurityProxy(
            getUtility(ILaunchpadCelebrities).admin)
        admin_team.addMember(admin, admin_team.teamowner)
        queues = self.all_queues.visibleByUser(admin)
        self.assertEqual(
            sorted(self.all_queues.getMergeQueues()),
            sorted(queues.getMergeQueues()))
