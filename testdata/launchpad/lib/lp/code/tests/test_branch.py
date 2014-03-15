# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for methods of Branch and BranchSet."""

from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.code.enums import (
    BranchSubscriptionDiffSize,
    BranchSubscriptionNotificationLevel,
    CodeReviewNotificationLevel,
    )
from lp.code.interfaces.codehosting import SUPPORTED_SCHEMES
from lp.code.tests.helpers import make_official_package_branch
from lp.services.webapp.authorization import check_permission
from lp.soyuz.interfaces.archivepermission import IArchivePermissionSet
from lp.testing import (
    run_with_login,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class PermissionTest(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def assertPermission(self, can_access, person, secure_object, permission):
        """Assert that 'person' can or cannot access 'secure_object'.

        :param can_access: Whether or not the person can access the object.
        :param person: The `IPerson` who is trying to access the object.
        :param secure_object: The secured object.
        :param permission: The Launchpad permission that 'person' is trying to
            access 'secure_object' with.
        """
        self.assertEqual(
            can_access,
            run_with_login(
                person, check_permission, permission, secure_object))

    def assertAuthenticatedView(self, branch, person, can_access):
        """Can 'branch' be accessed by 'person'?

        :param branch: The `IBranch` we're curious about.
        :param person: The `IPerson` trying to access it.
        :param can_access: Whether we expect 'person' be able to access it.
        """
        self.assertPermission(can_access, person, branch, 'launchpad.View')

    def assertUnauthenticatedView(self, branch, can_access):
        """Can 'branch' be accessed anonymously?

        :param branch: The `IBranch` we're curious about.
        :param can_access: Whether we expect to access it anonymously.
        """
        self.assertAuthenticatedView(branch, None, can_access)

    def assertCanView(self, person, secured_object):
        """Assert 'person' can view 'secured_object'."""
        self.assertPermission(True, person, secured_object, 'launchpad.View')

    def assertCannotView(self, person, secured_object):
        """Assert 'person' cannot view 'secured_object'."""
        self.assertPermission(False, person, secured_object, 'launchpad.View')

    def assertCanEdit(self, person, secured_object):
        """Assert 'person' can edit 'secured_object'.

        That is, assert 'person' has 'launchpad.Edit' permissions on
        'secured_object'.

        :param person: An `IPerson`. None means anonymous.
        :param secured_object: An object, secured through the Zope security
            layer.
        """
        self.assertPermission(True, person, secured_object, 'launchpad.Edit')

    def assertCannotEdit(self, person, secured_object):
        """Assert 'person' cannot edit 'secured_object'.

        That is, assert 'person' does not have 'launchpad.Edit' permissions on
        'secured_object'.

        :param person: An `IPerson`. None means anonymous.
        :param secured_object: An object, secured through the Zope security
            layer.
        """
        self.assertPermission(False, person, secured_object, 'launchpad.Edit')


class TestAccessBranch(PermissionTest):

    def test_publicBranchUnauthenticated(self):
        # Public branches can be accessed without authentication.
        branch = self.factory.makeAnyBranch()
        self.assertUnauthenticatedView(branch, True)

    def test_publicBranchArbitraryUser(self):
        # Public branches can be accessed by anyone.
        branch = self.factory.makeAnyBranch()
        person = self.factory.makePerson()
        self.assertAuthenticatedView(branch, person, True)

    def test_privateBranchUnauthenticated(self):
        # Private branches cannot be accessed without authentication.
        branch = self.factory.makeAnyBranch(
            information_type=InformationType.USERDATA)
        self.assertUnauthenticatedView(branch, False)

    def test_privateBranchOwner(self):
        # The owner of a branch can always access it.
        owner = self.factory.makePerson()
        branch = self.factory.makeAnyBranch(
            owner=owner, information_type=InformationType.USERDATA)
        self.assertAuthenticatedView(branch, owner, True)

    def test_privateBranchOwnerMember(self):
        # Any member of the team that owns the branch can access it.
        team_owner = self.factory.makePerson()
        team = self.factory.makeTeam(team_owner)
        person = self.factory.makePerson()
        removeSecurityProxy(team).addMember(person, team_owner)
        branch = self.factory.makeAnyBranch(
            owner=team, information_type=InformationType.USERDATA)
        self.assertAuthenticatedView(branch, person, True)

    def test_privateBranchAdmins(self):
        # Launchpad admins can access any branch.
        celebs = getUtility(ILaunchpadCelebrities)
        branch = self.factory.makeAnyBranch(
            information_type=InformationType.USERDATA)
        self.assertAuthenticatedView(branch, celebs.admin.teamowner, True)

    def test_privateBranchSubscriber(self):
        # If you are subscribed to a branch, you can access it.
        branch = self.factory.makeAnyBranch(
            information_type=InformationType.USERDATA)
        person = self.factory.makePerson()
        removeSecurityProxy(branch).subscribe(
            person, BranchSubscriptionNotificationLevel.NOEMAIL,
            BranchSubscriptionDiffSize.NODIFF,
            CodeReviewNotificationLevel.NOEMAIL, person)
        self.assertAuthenticatedView(branch, person, True)

    def test_privateBranchAnyoneElse(self):
        # In general, you can't access a private branch.
        branch = self.factory.makeAnyBranch(
            information_type=InformationType.USERDATA)
        person = self.factory.makePerson()
        self.assertAuthenticatedView(branch, person, False)

    def test_stackedOnPrivateBranchUnauthenticated(self):
        # If a branch is stacked on a private branch, then you cannot access
        # it when unauthenticated.
        stacked_on_branch = self.factory.makeAnyBranch(
            information_type=InformationType.USERDATA)
        stacked_branch = self.factory.makeAnyBranch(
            stacked_on=stacked_on_branch)
        self.assertUnauthenticatedView(stacked_branch, False)

    def test_stackedOnPrivateBranchAuthenticated(self):
        # If a branch is stacked on a private branch, you can only access it
        # if you can access both branches.
        stacked_on_branch = self.factory.makeAnyBranch(
            information_type=InformationType.USERDATA)
        stacked_branch = self.factory.makeAnyBranch(
            stacked_on=stacked_on_branch)
        person = self.factory.makePerson()
        self.assertAuthenticatedView(stacked_branch, person, False)

    def test_manyLevelsOfStackingUnauthenticated(self):
        # If a branch is stacked on a branch stacked on a private branch, you
        # still can't access it when unauthenticated.
        stacked_on_branch = self.factory.makeAnyBranch(
            information_type=InformationType.USERDATA)
        branch_a = self.factory.makeAnyBranch(stacked_on=stacked_on_branch)
        branch_b = self.factory.makeAnyBranch(stacked_on=branch_a)
        self.assertUnauthenticatedView(branch_b, False)

    def test_manyLevelsOfStackingAuthenticated(self):
        # If a branch is stacked on a branch stacked on a private branch, you
        # still can't access it when unauthenticated.
        stacked_on_branch = self.factory.makeAnyBranch(
            information_type=InformationType.USERDATA)
        branch_a = self.factory.makeAnyBranch(stacked_on=stacked_on_branch)
        branch_b = self.factory.makeAnyBranch(stacked_on=branch_a)
        person = self.factory.makePerson()
        self.assertAuthenticatedView(branch_b, person, False)

    def test_loopedPublicStackedOn(self):
        # It's possible, although nonsensical, for branch stackings to form a
        # loop. e.g., branch A is stacked on branch B is stacked on branch A.
        # If all of these branches are public, then we want anyone to be able
        # to access it / them.
        stacked_branch = self.factory.makeAnyBranch()
        removeSecurityProxy(stacked_branch).stacked_on = stacked_branch
        person = self.factory.makePerson()
        self.assertAuthenticatedView(stacked_branch, person, True)

    def test_loopedPrivateStackedOn(self):
        # It's possible, although nonsensical, for branch stackings to form a
        # loop. e.g., branch A is stacked on branch B is stacked on branch A.
        # If all of these branches are private, then only people who can
        # access all of them can get to them.
        stacked_branch = self.factory.makeAnyBranch(
            information_type=InformationType.USERDATA)
        removeSecurityProxy(stacked_branch).stacked_on = stacked_branch
        person = self.factory.makePerson()
        self.assertAuthenticatedView(stacked_branch, person, False)

    def test_loopedPublicStackedOnUnauthenticated(self):
        # It's possible, although nonsensical, for branch stackings to form a
        # loop. e.g., branch A is stacked on branch B is stacked on branch A.
        # If all of these branches are public, then you can get them without
        # being logged in.
        stacked_branch = self.factory.makeAnyBranch()
        removeSecurityProxy(stacked_branch).stacked_on = stacked_branch
        self.assertUnauthenticatedView(stacked_branch, True)


class TestWriteToBranch(PermissionTest):
    """Test who can write to branches."""

    def test_owner_can_write(self):
        # The owner of a branch can write to the branch.
        branch = self.factory.makeAnyBranch()
        self.assertCanEdit(branch.owner, branch)

    def test_random_person_cannot_write(self):
        # Arbitrary logged in people cannot write to branches.
        branch = self.factory.makeAnyBranch()
        person = self.factory.makePerson()
        self.assertCannotEdit(person, branch)

    def test_member_of_owning_team_can_write(self):
        # Members of the team that owns a branch can write to the branch.
        team = self.factory.makeTeam()
        person = self.factory.makePerson()
        removeSecurityProxy(team).addMember(person, team.teamowner)
        branch = self.factory.makeAnyBranch(owner=team)
        self.assertCanEdit(person, branch)

    def test_vcs_imports_members_can_edit_import_branch(self):
        # Even if a branch isn't owned by vcs-imports, vcs-imports members can
        # edit it if it has a code import associated with it.
        person = self.factory.makePerson()
        branch = self.factory.makeCodeImport().branch
        vcs_imports = getUtility(ILaunchpadCelebrities).vcs_imports
        removeSecurityProxy(vcs_imports).addMember(
            person, vcs_imports.teamowner)
        self.assertCanEdit(person, branch)

    def makeOfficialPackageBranch(self):
        """Make a branch linked to the pocket of a source package."""
        return make_official_package_branch(self.factory)

    def test_owner_can_write_to_official_package_branch(self):
        # The owner of an official package branch can write to it, just like a
        # regular person.
        branch = self.makeOfficialPackageBranch()
        self.assertCanEdit(branch.owner, branch)

    def assertCanUpload(self, person, spn, archive, component,
                        strict_component=True, distroseries=None):
        """Assert that 'person' can upload 'spn' to 'archive'."""
        # For now, just check that doesn't raise an exception.
        if distroseries is None:
            distroseries = archive.distribution.currentseries
        self.assertIs(
            None,
            archive.verifyUpload(
                person, spn, component, distroseries,
                strict_component=strict_component))

    def test_package_upload_permissions_grant_branch_edit(self):
        # If you can upload to the package, then you are also allowed to write
        # to the branch.

        permission_set = getUtility(IArchivePermissionSet)
        # Only admins or techboard members can add permissions normally. That
        # restriction isn't relevant to these tests.
        permission_set = removeSecurityProxy(permission_set)
        branch = self.makeOfficialPackageBranch()
        package = branch.sourcepackage
        person = self.factory.makePerson()

        # Person is not allowed to edit the branch presently.
        self.assertCannotEdit(person, branch)

        # Now give 'person' permission to upload to 'package'.
        archive = branch.distroseries.distribution.main_archive
        spn = package.sourcepackagename
        permission_set.newPackageUploader(archive, person, spn)
        # Make sure person *is* authorised to upload the source package
        # targeted by the branch at hand.
        self.assertCanUpload(person, spn, archive, None)

        # Now person can edit the branch on the basis of the upload
        # permissions granted above.
        self.assertCanEdit(person, branch)

    def test_arbitrary_person_cannot_edit(self):
        # Arbitrary people cannot edit branches, you have to be someone
        # special.
        branch = self.factory.makeAnyBranch()
        person = self.factory.makePerson()
        self.assertCannotEdit(person, branch)

    def test_code_import_registrant_can_edit(self):
        # It used to be the case that all import branches were owned by the
        # special, restricted team ~vcs-imports. This made a lot of work for
        # the Launchpad development team, since they needed to delete and
        # rename import branches whenever people wanted it. To reduce this
        # work a little, whoever registered of a code import branch is allowed
        # to edit the branch, even if they aren't one of the owners.
        registrant = self.factory.makePerson()
        code_import = self.factory.makeCodeImport(registrant=registrant)
        branch = code_import.branch
        removeSecurityProxy(branch).setOwner(
            getUtility(ILaunchpadCelebrities).vcs_imports,
            getUtility(ILaunchpadCelebrities).vcs_imports)
        self.assertCanEdit(registrant, branch)


class TestComposePublicURL(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestComposePublicURL, self).setUp('admin@canonical.com')

    def test_composePublicURL_accepts_supported_schemes(self):
        # composePublicURL accepts all schemes that PublicCodehostingAPI
        # supports.
        branch = self.factory.makeAnyBranch()

        url_pattern = '%%s://bazaar.launchpad.dev/~%s/%s/%s' % (
            branch.owner.name, branch.product.name, branch.name)
        for scheme in SUPPORTED_SCHEMES:
            public_url = branch.composePublicURL(scheme)
            self.assertEqual(url_pattern % scheme, public_url)

        # sftp support is also grandfathered in.
        sftp_url = branch.composePublicURL('sftp')
        self.assertEqual(url_pattern % 'sftp', sftp_url)

    def test_composePublicURL_default_http(self):
        # The default scheme for composePublicURL is http.
        branch = self.factory.makeAnyBranch()
        prefix = 'http://'
        public_url = branch.composePublicURL()
        self.assertEqual(prefix, public_url[:len(prefix)])

    def test_composePublicURL_unknown_scheme(self):
        # Schemes that aren't known to be supported are not accepted.
        branch = self.factory.makeAnyBranch()
        self.assertRaises(AssertionError, branch.composePublicURL, 'irc')

    def test_composePublicURL_http_private(self):
        # Private branches don't have public http URLs.
        branch = self.factory.makeAnyBranch(
            information_type=InformationType.USERDATA)
        self.assertRaises(AssertionError, branch.composePublicURL, 'http')

    def test_composePublicURL_no_https(self):
        # There's no https support.  If there were, it should probably
        # not work for private branches.
        branch = self.factory.makeAnyBranch()
        self.assertRaises(AssertionError, branch.composePublicURL, 'https')
