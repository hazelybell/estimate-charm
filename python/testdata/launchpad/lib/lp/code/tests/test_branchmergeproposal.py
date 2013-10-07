# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for methods of BranchMergeProposal."""


from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.code.interfaces.linkedbranch import ICanHasLinkedBranch
from lp.code.tests.test_branch import PermissionTest
from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.soyuz.interfaces.archivepermission import IArchivePermissionSet
from lp.testing import (
    run_with_login,
    with_celebrity_logged_in,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestEditMergeProposal(PermissionTest):
    """Test who can edit branchmergeproposals."""

    layer = DatabaseFunctionalLayer

    def makePackageProposal(self):
        branch = self.factory.makePackageBranch()
        # Make sure the (distroseries, pocket) combination used allows us to
        # upload to it.
        pocket = PackagePublishingPocket.RELEASE
        sourcepackage = branch.sourcepackage
        suite_sourcepackage = sourcepackage.getSuiteSourcePackage(pocket)
        registrant = self.factory.makePerson()
        run_with_login(
            suite_sourcepackage.distribution.owner,
            ICanHasLinkedBranch(suite_sourcepackage).setBranch,
            branch, registrant)
        source_branch = self.factory.makePackageBranch(
            sourcepackage=branch.sourcepackage)
        proposal = source_branch.addLandingTarget(
            source_branch.registrant, branch)
        return proposal

    def test_package_merge_proposal_with_no_upload_permission(self):
        # If you can't upload the package and have no other relationship
        # to the proposal or branches then you can't edit the proposal.
        person = self.factory.makePerson()
        proposal = self.makePackageProposal()

        # Person is not allowed to edit the branch presently.
        self.assertCannotEdit(person, proposal.target_branch)
        # And so isn't allowed to edit the merge proposal
        self.assertCannotEdit(person, proposal)

    def test_package_upload_permissions_grant_merge_proposal_edit(self):
        # If you can upload to the package then you can edit merge
        # proposals against the official branch.
        person = self.factory.makePerson()
        proposal = self.makePackageProposal()

        permission_set = getUtility(IArchivePermissionSet)
        # Only admins or techboard members can add permissions normally. That
        # restriction isn't relevant to these tests.
        permission_set = removeSecurityProxy(permission_set)
        # Now give 'person' permission to upload to 'package'.
        archive = (
            proposal.target_branch.distroseries.distribution.main_archive)
        package = proposal.target_branch.sourcepackage
        spn = package.sourcepackagename
        permission_set.newPackageUploader(archive, person, spn)

        # Now person can edit the branch on the basis of the upload
        # permissions granted above.
        self.assertCanEdit(person, proposal.target_branch)
        # And that means they can edit the proposal too
        self.assertCanEdit(person, proposal)


class TestViewMergeProposal(PermissionTest):

    layer = DatabaseFunctionalLayer

    @with_celebrity_logged_in('admin')
    def assertBranchAccessRequired(self, attr):
        person = self.factory.makePerson()
        prereq = self.factory.makeBranch()
        proposal = self.factory.makeBranchMergeProposal(
            prerequisite_branch=prereq)
        self.assertCanView(person, proposal)
        getattr(proposal, attr).setPrivate(
            True, getUtility(IPersonSet).getByName('admins'))
        self.assertCannotView(person, proposal)

    def test_source_branch_access_required(self):
        self.assertBranchAccessRequired('source_branch')

    def test_target_branch_access_required(self):
        self.assertBranchAccessRequired('target_branch')

    def test_prerequisite_branch_access_required(self):
        self.assertBranchAccessRequired('prerequisite_branch')
