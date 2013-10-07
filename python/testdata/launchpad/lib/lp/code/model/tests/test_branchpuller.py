# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the branch puller model code."""

__metaclass__ = type

from datetime import (
    datetime,
    timedelta,
    )

import pytz
import transaction
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.code.enums import BranchType
from lp.code.interfaces.branchpuller import IBranchPuller
from lp.services.database.constants import UTC_NOW
from lp.testing import (
    login_person,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestMirroringForImportedBranches(TestCaseWithFactory):
    """Tests for mirroring methods of a branch."""

    layer = DatabaseFunctionalLayer

    branch_type = BranchType.IMPORTED

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.branch_puller = getUtility(IBranchPuller)
        # The absolute minimum value for any time field set to 'now'.
        self._now_minimum = self.getNow()

    def assertInFuture(self, time, delta):
        """Assert that 'time' is set (roughly) to 'now' + 'delta'.

        We do not want to assert that 'time' is exactly 'delta' in the future
        as this assertion is executing after whatever changed the value of
        'time'.
        """
        now_maximum = self.getNow()
        self.assertBetween(
            self._now_minimum + delta, time, now_maximum + delta)

    def getNow(self):
        """Return a datetime representing 'now' in UTC."""
        return datetime.now(pytz.timezone('UTC'))

    def makeAnyBranch(self):
        return self.factory.makeAnyBranch(branch_type=self.branch_type)

    def test_requestMirror(self):
        """requestMirror sets the mirror request time to 'now'."""
        branch = self.makeAnyBranch()
        branch.requestMirror()
        self.assertSqlAttributeEqualsDate(branch, 'next_mirror_time', UTC_NOW)

    def test_requestMirror_doesnt_demote_branch(self):
        # requestMirror() sets the mirror request time to 'now' unless
        # next_mirror_time is already in the past, i.e. calling
        # requestMirror() doesn't move the branch backwards in the queue of
        # branches that need mirroring.
        branch = self.makeAnyBranch()
        past_time = datetime.now(pytz.UTC) - timedelta(days=1)
        removeSecurityProxy(branch).next_mirror_time = past_time
        branch.requestMirror()
        self.assertEqual(branch.next_mirror_time, past_time)

    def test_requestMirror_can_promote_branch(self):
        # requestMirror() sets the mirror request time to 'now' if
        # next_mirror_time is set and in the future.
        branch = self.makeAnyBranch()
        future_time = datetime.now(pytz.UTC) + timedelta(days=1)
        removeSecurityProxy(branch).next_mirror_time = future_time
        branch.requestMirror()
        self.assertSqlAttributeEqualsDate(branch, 'next_mirror_time', UTC_NOW)

    def test_mirroringResetsMirrorRequest(self):
        """Mirroring branches resets their mirror request times."""
        branch = self.makeAnyBranch()
        branch.requestMirror()
        transaction.commit()
        branch.startMirroring()
        removeSecurityProxy(branch).branchChanged(
            '', 'rev1', None, None, None)
        self.assertEqual(None, branch.next_mirror_time)

    def test_mirrorFailureResetsMirrorRequest(self):
        """If a branch fails to mirror then update failures but don't mirror
        again until asked.
        """
        branch = self.makeAnyBranch()
        branch.requestMirror()
        branch.startMirroring()
        branch.mirrorFailed('No particular reason')
        self.assertEqual(1, branch.mirror_failures)
        self.assertEqual(None, branch.next_mirror_time)


class TestMirroringForMirroredBranches(TestMirroringForImportedBranches):

    branch_type = BranchType.MIRRORED

    def setUp(self):
        TestMirroringForImportedBranches.setUp(self)
        branch_puller = getUtility(IBranchPuller)
        self.increment = branch_puller.MIRROR_TIME_INCREMENT
        self.max_failures = branch_puller.MAXIMUM_MIRROR_FAILURES

    def test_mirrorFailureResetsMirrorRequest(self):
        """If a branch fails to mirror then mirror again later."""
        branch = self.makeAnyBranch()
        branch.requestMirror()
        branch.startMirroring()
        branch.mirrorFailed('No particular reason')
        self.assertEqual(1, branch.mirror_failures)
        self.assertInFuture(branch.next_mirror_time, self.increment)

    def test_mirrorFailureBacksOffExponentially(self):
        """If a branch repeatedly fails to mirror then back off exponentially.
        """
        branch = self.makeAnyBranch()
        num_failures = 3
        for i in range(num_failures):
            branch.requestMirror()
            branch.startMirroring()
            branch.mirrorFailed('No particular reason')
        self.assertEqual(num_failures, branch.mirror_failures)
        self.assertInFuture(
            branch.next_mirror_time,
            (self.increment * 2 ** (num_failures - 1)))

    def test_repeatedMirrorFailuresDisablesMirroring(self):
        """If a branch's mirror failures exceed the maximum, disable
        mirroring.
        """
        branch = self.makeAnyBranch()
        for i in range(self.max_failures):
            branch.requestMirror()
            branch.startMirroring()
            branch.mirrorFailed('No particular reason')
        self.assertEqual(self.max_failures, branch.mirror_failures)
        self.assertEqual(None, branch.next_mirror_time)

    def test_mirroringResetsMirrorRequest(self):
        """Mirroring 'mirrored' branches sets their mirror request time to six
        hours in the future.
        """
        branch = self.makeAnyBranch()
        branch.requestMirror()
        transaction.commit()
        branch.startMirroring()
        removeSecurityProxy(branch).branchChanged(
            '', 'rev1', None, None, None)
        self.assertInFuture(branch.next_mirror_time, self.increment)
        self.assertEqual(0, branch.mirror_failures)


class AcquireBranchToPullTests:
    """Tests for acquiring branches to pull.

    The tests apply to branches accessed directly or through an XML-RPC style
    endpoint -- implement `assertNoBranchIsAcquired`, `assertBranchIsAcquired`
    and `startMirroring` as appropriate.
    """

    def assertNoBranchIsAcquired(self, *branch_types):
        """Assert that there is no branch to pull.

        :param branch_types: A list of branch types to pass to
            acquireBranchToPull.  Passing none means consider all types of
            branch.
        """
        raise NotImplementedError(self.assertNoBranchIsAcquired)

    def assertBranchIsAcquired(self, branch, *branch_types):
        """Assert that ``branch`` is the next branch to be pulled.

        :param branch_types: A list of branch types to pass to
            acquireBranchToPull.  Passing none means consider all types of
            branch.
        """
        raise NotImplementedError(self.assertBranchIsAcquired)

    def startMirroring(self, branch):
        """Mark that ``branch`` has begun mirroring."""
        raise NotImplementedError(self.startMirroring)

    def test_empty(self):
        # If there is no branch that needs pulling, acquireBranchToPull
        # returns None.
        self.assertNoBranchIsAcquired()

    def test_simple(self):
        # If there is one branch that needs mirroring, acquireBranchToPull
        # returns that.
        branch = self.factory.makeAnyBranch(branch_type=BranchType.MIRRORED)
        branch.requestMirror()
        self.assertBranchIsAcquired(branch)

    def test_remote_branch_not_acquired(self):
        # On a few occasions a branch type that is mirrored has been
        # converted, with non-NULL next_mirror_time, to a remote branch, which
        # is not mirrored.  These branches should not be returned.
        branch = self.factory.makeAnyBranch(branch_type=BranchType.MIRRORED)
        branch.requestMirror()
        removeSecurityProxy(branch).branch_type = BranchType.REMOTE
        self.assertNoBranchIsAcquired()

    def test_private(self):
        # If there is a private branch that needs mirroring,
        # acquireBranchToPull returns that.
        branch = self.factory.makeAnyBranch(
            branch_type=BranchType.MIRRORED,
            information_type=InformationType.USERDATA)
        removeSecurityProxy(branch).requestMirror()
        self.assertBranchIsAcquired(branch)

    def test_no_inprogress(self):
        # If a branch is being mirrored, it is not returned.
        branch = self.factory.makeAnyBranch(branch_type=BranchType.MIRRORED)
        branch.requestMirror()
        self.startMirroring(branch)
        self.assertNoBranchIsAcquired()

    def test_first_requested_returned(self):
        # If two branches are to be mirrored, the one that was requested first
        # is returned.
        first_branch = self.factory.makeAnyBranch(
            branch_type=BranchType.MIRRORED)
        # You can only request a mirror now, so to pretend that we requested
        # it some time ago, we cheat with removeSecurityProxy().
        first_branch.requestMirror()
        naked_first_branch = removeSecurityProxy(first_branch)
        naked_first_branch.next_mirror_time -= timedelta(seconds=100)
        second_branch = self.factory.makeAnyBranch(
            branch_type=BranchType.MIRRORED)
        second_branch.requestMirror()
        naked_second_branch = removeSecurityProxy(second_branch)
        naked_second_branch.next_mirror_time -= timedelta(seconds=50)
        self.assertBranchIsAcquired(naked_first_branch)

    def test_type_filter_mirrrored_returns_mirrored(self):
        branch = self.factory.makeAnyBranch(branch_type=BranchType.MIRRORED)
        branch.requestMirror()
        self.assertBranchIsAcquired(branch, BranchType.MIRRORED)

    def test_type_filter_imported_does_not_return_mirrored(self):
        branch = self.factory.makeAnyBranch(branch_type=BranchType.MIRRORED)
        branch.requestMirror()
        self.assertNoBranchIsAcquired(BranchType.IMPORTED)

    def test_type_filter_mirrored_imported_returns_mirrored(self):
        branch = self.factory.makeAnyBranch(branch_type=BranchType.MIRRORED)
        branch.requestMirror()
        self.assertBranchIsAcquired(
            branch, BranchType.MIRRORED, BranchType.IMPORTED)

    def test_type_filter_mirrored_imported_returns_imported(self):
        branch = self.factory.makeAnyBranch(branch_type=BranchType.IMPORTED)
        branch.requestMirror()
        self.assertBranchIsAcquired(
            branch, BranchType.MIRRORED, BranchType.IMPORTED)


class TestAcquireBranchToPullDirectly(TestCaseWithFactory,
                                      AcquireBranchToPullTests):
    """Direct tests for `IBranchPuller.acquireBranchToPull`."""

    layer = DatabaseFunctionalLayer

    def assertNoBranchIsAcquired(self, *branch_types):
        """See `AcquireBranchToPullTests`."""
        acquired_branch = getUtility(IBranchPuller).acquireBranchToPull(
            *branch_types)
        self.assertEqual(None, acquired_branch)

    def assertBranchIsAcquired(self, branch, *branch_types):
        """See `AcquireBranchToPullTests`."""
        acquired_branch = getUtility(IBranchPuller).acquireBranchToPull(
            *branch_types)
        login_person(removeSecurityProxy(branch).owner)
        self.assertEqual(branch, acquired_branch)
        self.assertIsNot(None, acquired_branch.last_mirror_attempt)
        self.assertIs(None, acquired_branch.next_mirror_time)

    def startMirroring(self, branch):
        """See `AcquireBranchToPullTests`."""
        branch.startMirroring()
