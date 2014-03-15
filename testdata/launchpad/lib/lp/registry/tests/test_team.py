# Copyright 2010-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for PersonSet."""

__metaclass__ = type

import transaction
from zope.component import getUtility
from zope.interface.exceptions import Invalid
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.registry.enums import (
    EXCLUSIVE_TEAM_POLICY,
    INCLUSIVE_TEAM_POLICY,
    PersonTransferJobType,
    PersonVisibility,
    TeamMembershipPolicy,
    TeamMembershipRenewalPolicy,
    )
from lp.registry.errors import (
    JoinNotAllowed,
    TeamMembershipPolicyError,
    )
from lp.registry.interfaces.mailinglist import MailingListStatus
from lp.registry.interfaces.person import (
    IPersonSet,
    ITeamPublic,
    )
from lp.registry.interfaces.teammembership import TeamMembershipStatus
from lp.registry.model.persontransferjob import PersonTransferJob
from lp.services.database.interfaces import IMasterStore
from lp.services.identity.interfaces.emailaddress import IEmailAddressSet
from lp.services.identity.model.emailaddress import EmailAddress
from lp.soyuz.enums import ArchiveStatus
from lp.testing import (
    login_celebrity,
    login_person,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    FunctionalLayer,
    )


class TestTeamContactAddress(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def getAllEmailAddresses(self):
        transaction.commit()
        all_addresses = self.store.find(
            EmailAddress, EmailAddress.personID == self.team.id)
        return [address for address in all_addresses.order_by('email')]

    def createMailingListAndGetAddress(self):
        mailing_list = self.factory.makeMailingList(
            self.team, self.team.teamowner)
        return getUtility(IEmailAddressSet).getByEmail(
                mailing_list.address)

    def setUp(self):
        super(TestTeamContactAddress, self).setUp()

        self.team = self.factory.makeTeam(name='alpha')
        self.address = self.factory.makeEmail('team@noplace.org', self.team)
        self.store = IMasterStore(self.address)

    def test_setContactAddress_from_none(self):
        self.team.setContactAddress(self.address)
        self.assertEqual(self.address, self.team.preferredemail)
        self.assertEqual([self.address], self.getAllEmailAddresses())

    def test_setContactAddress_to_none(self):
        self.team.setContactAddress(self.address)
        self.team.setContactAddress(None)
        self.assertEqual(None, self.team.preferredemail)
        self.assertEqual([], self.getAllEmailAddresses())

    def test_setContactAddress_to_new_address(self):
        self.team.setContactAddress(self.address)
        new_address = self.factory.makeEmail('new@noplace.org', self.team)
        self.team.setContactAddress(new_address)
        self.assertEqual(new_address, self.team.preferredemail)
        self.assertEqual([new_address], self.getAllEmailAddresses())

    def test_setContactAddress_to_mailing_list(self):
        self.team.setContactAddress(self.address)
        list_address = self.createMailingListAndGetAddress()
        self.team.setContactAddress(list_address)
        self.assertEqual(list_address, self.team.preferredemail)
        self.assertEqual([list_address], self.getAllEmailAddresses())

    def test_setContactAddress_from_mailing_list(self):
        list_address = self.createMailingListAndGetAddress()
        self.team.setContactAddress(list_address)
        new_address = self.factory.makeEmail('new@noplace.org', self.team)
        self.team.setContactAddress(new_address)
        self.assertEqual(new_address, self.team.preferredemail)
        self.assertEqual(
            [list_address, new_address], self.getAllEmailAddresses())

    def test_setContactAddress_from_mailing_list_to_none(self):
        list_address = self.createMailingListAndGetAddress()
        self.team.setContactAddress(list_address)
        self.team.setContactAddress(None)
        self.assertEqual(None, self.team.preferredemail)
        self.assertEqual([list_address], self.getAllEmailAddresses())

    def test_setContactAddress_with_purged_mailing_list_to_none(self):
        # Purging a mailing list will delete the list address, but this was
        # not always the case. The address will be deleted if it still exists.
        self.createMailingListAndGetAddress()
        naked_mailing_list = removeSecurityProxy(self.team.mailing_list)
        naked_mailing_list.status = MailingListStatus.PURGED
        self.team.setContactAddress(None)
        self.assertEqual(None, self.team.preferredemail)
        self.assertEqual([], self.getAllEmailAddresses())

    def test_setContactAddress_after_purged_mailing_list_and_rename(self):
        # This is the rare case where a list is purged for a team rename,
        # then the contact address is set/unset sometime afterwards.
        # The old mailing list address belongs the team, but not the list.
        # 1. Create then purge a mailing list.
        self.createMailingListAndGetAddress()
        mailing_list = self.team.mailing_list
        mailing_list.deactivate()
        mailing_list.transitionToStatus(MailingListStatus.INACTIVE)
        mailing_list.purge()
        transaction.commit()
        # 2. Rename the team.
        login_celebrity('admin')
        self.team.name = 'beta'
        login_person(self.team.teamowner)
        # 3. Set the contact address.
        self.team.setContactAddress(None)
        self.assertEqual(None, self.team.preferredemail)
        self.assertEqual([], self.getAllEmailAddresses())


class TestTeamGetTeamAdminsEmailAddresses(TestCaseWithFactory):
    """Test the rules of IPerson.getTeamAdminsEmailAddresses()."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestTeamGetTeamAdminsEmailAddresses, self).setUp()
        self.team = self.factory.makeTeam(name='finch')
        login_celebrity('admin')

    def test_admin_is_user(self):
        # The team owner is a user and admin who provides the email address.
        email = self.team.teamowner.preferredemail.email
        self.assertEqual([email], self.team.getTeamAdminsEmailAddresses())

    def test_no_admins(self):
        # A team without admins has no email addresses.
        self.team.teamowner.leave(self.team)
        self.assertEqual([], self.team.getTeamAdminsEmailAddresses())

    def test_admins_are_users_with_preferred_email_addresses(self):
        # The team's admins are users, and they provide the email addresses.
        admin = self.factory.makePerson()
        self.team.addMember(admin, self.team.teamowner)
        for membership in self.team.member_memberships:
            membership.setStatus(
                TeamMembershipStatus.ADMIN, self.team.teamowner)
        email_1 = self.team.teamowner.preferredemail.email
        email_2 = admin.preferredemail.email
        self.assertEqual(
            [email_1, email_2], self.team.getTeamAdminsEmailAddresses())

    def setUpAdminingTeam(self, team):
        """Return a new team set as the admin of the provided team."""
        admin_team = self.factory.makeTeam()
        admin_member = self.factory.makePerson()
        admin_team.addMember(admin_member, admin_team.teamowner)
        team.addMember(
            admin_team, team.teamowner, force_team_add=True)
        for membership in team.member_memberships:
            membership.setStatus(
                TeamMembershipStatus.ADMIN, admin_team.teamowner)
        approved_member = self.factory.makePerson()
        team.addMember(approved_member, team.teamowner)
        team.teamowner.leave(team)
        return admin_team

    def test_admins_are_teams_with_preferred_email_addresses(self):
        # The team's admin is a team with a contact address.
        admin_team = self.setUpAdminingTeam(self.team)
        admin_team.setContactAddress(
            self.factory.makeEmail('team@eg.dom', admin_team))
        self.assertEqual(
            ['team@eg.dom'], self.team.getTeamAdminsEmailAddresses())

    def test_admins_are_teams_without_preferred_email_addresses(self):
        # The team's admin is a team without a contact address.
        # The admin team members provide the email addresses.
        admin_team = self.setUpAdminingTeam(self.team)
        emails = sorted(
            m.preferredemail.email for m in admin_team.activemembers)
        self.assertEqual(
            emails, self.team.getTeamAdminsEmailAddresses())


class TestDefaultRenewalPeriodIsRequiredForSomeTeams(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestDefaultRenewalPeriodIsRequiredForSomeTeams, self).setUp()
        self.team = self.factory.makeTeam()
        login_person(self.team.teamowner)

    def assertInvalid(self, policy, period):
        self.team.renewal_policy = policy
        self.team.defaultrenewalperiod = period
        self.assertRaises(Invalid, ITeamPublic.validateInvariants, self.team)

    def assertValid(self, policy, period):
        self.team.renewal_policy = policy
        self.team.defaultrenewalperiod = period
        ITeamPublic.validateInvariants(self.team)

    def test_policy_ondemand_period_none(self):
        # Ondemand policy cannot have a none day period.
        self.assertInvalid(
            TeamMembershipRenewalPolicy.ONDEMAND, None)

    def test_policy_none_period_none(self):
        # None policy can have a None day period.
        self.assertValid(
            TeamMembershipRenewalPolicy.NONE, None)

    def test_policy_requres_period_below_minimum(self):
        # Ondemand policy cannot have a zero day period.
        self.assertInvalid(
            TeamMembershipRenewalPolicy.ONDEMAND, 0)

    def test_policy_requres_period_minimum(self):
        # Ondemand policy can have a 1 day period.
        self.assertValid(
            TeamMembershipRenewalPolicy.ONDEMAND, 1)

    def test_policy_requres_period_maximum(self):
        # Ondemand policy cannot have a 3650 day max value.
        self.assertValid(
            TeamMembershipRenewalPolicy.ONDEMAND, 3650)

    def test_policy_requres_period_over_maximum(self):
        # Ondemand policy cannot have a 3650 day max value.
        self.assertInvalid(
            TeamMembershipRenewalPolicy.ONDEMAND, 3651)


class TestDefaultMembershipPeriod(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestDefaultMembershipPeriod, self).setUp()
        self.team = self.factory.makeTeam()
        login_person(self.team.teamowner)

    def test_default_membership_period_over_maximum(self):
        self.assertRaises(
            Invalid, ITeamPublic['defaultmembershipperiod'].validate, 3651)

    def test_default_membership_period_none(self):
        ITeamPublic['defaultmembershipperiod'].validate(None)

    def test_default_membership_period_zero(self):
        ITeamPublic['defaultmembershipperiod'].validate(0)

    def test_default_membership_period_maximum(self):
        ITeamPublic['defaultmembershipperiod'].validate(3650)


class TestTeamMembershipPolicyError(TestCaseWithFactory):
    """Test `TeamMembershipPolicyError` messages."""

    layer = FunctionalLayer

    def test_default_message(self):
        error = TeamMembershipPolicyError()
        self.assertEqual('Team Membership Policy Error', error.message)

    def test_str(self):
        # The string is the error message.
        error = TeamMembershipPolicyError('a message')
        self.assertEqual('a message', str(error))

    def test_doc(self):
        # The doc() method returns the message.  It is called when rendering
        # an error in the UI. eg structure error.
        error = TeamMembershipPolicyError('a message')
        self.assertEqual('a message', error.doc())


class TeamMembershipPolicyBase(TestCaseWithFactory):
    """`TeamMembershipPolicyChoice` base test class."""

    layer = DatabaseFunctionalLayer
    POLICY = None

    def setUpTeams(self, other_policy=None):
        if other_policy is None:
            other_policy = self.POLICY
        self.team = self.factory.makeTeam(membership_policy=self.POLICY)
        self.other_team = self.factory.makeTeam(
            membership_policy=other_policy, owner=self.team.teamowner)
        self.field = ITeamPublic['membership_policy'].bind(self.team)
        login_person(self.team.teamowner)


class TestTeamMembershipPolicyChoiceCommon(TeamMembershipPolicyBase):
    """Test `TeamMembershipPolicyChoice` constraints."""

    # Any policy will work here, so we'll just pick one.
    POLICY = TeamMembershipPolicy.MODERATED

    def test___getTeam_with_team(self):
        # _getTeam returns the context team for team updates.
        self.setUpTeams()
        self.assertEqual(self.team, self.field._getTeam())

    def test___getTeam_with_person_set(self):
        # _getTeam returns the context person set for team creation.
        person_set = getUtility(IPersonSet)
        field = ITeamPublic['membership_policy'].bind(person_set)
        self.assertEqual(None, field._getTeam())


class TestTeamMembershipPolicyChoiceModerated(TeamMembershipPolicyBase):
    """Test `TeamMembershipPolicyChoice` Moderated constraints."""

    POLICY = TeamMembershipPolicy.MODERATED

    def test_closed_team_with_closed_super_team_cannot_become_open(self):
        # The team cannot compromise the membership of the super team
        # by becoming open. The user must remove his team from the super team
        # first.
        self.setUpTeams()
        self.other_team.addMember(self.team, self.team.teamowner)
        self.assertFalse(
            self.field.constraint(TeamMembershipPolicy.OPEN))
        self.assertRaises(
            TeamMembershipPolicyError, self.field.validate,
            TeamMembershipPolicy.OPEN)

    def test_closed_team_with_open_super_team_can_become_open(self):
        # The team can become open if its super teams are open.
        self.setUpTeams(other_policy=TeamMembershipPolicy.OPEN)
        self.other_team.addMember(self.team, self.team.teamowner)
        self.assertTrue(
            self.field.constraint(TeamMembershipPolicy.OPEN))
        self.assertEqual(
            None, self.field.validate(TeamMembershipPolicy.OPEN))

    def test_closed_team_can_change_to_another_closed_policy(self):
        # A exclusive team can change between the two exclusive polcies.
        self.setUpTeams()
        self.team.addMember(self.other_team, self.team.teamowner)
        super_team = self.factory.makeTeam(
            membership_policy=TeamMembershipPolicy.MODERATED,
            owner=self.team.teamowner)
        super_team.addMember(self.team, self.team.teamowner)
        self.assertTrue(
            self.field.constraint(TeamMembershipPolicy.RESTRICTED))
        self.assertEqual(
            None, self.field.validate(TeamMembershipPolicy.RESTRICTED))

    def test_closed_team_with_active_ppas_cannot_become_open(self):
        # The team cannot become open if it has PPA because it compromises the
        # the control of who can upload.
        self.setUpTeams()
        self.team.createPPA()
        self.assertFalse(
            self.field.constraint(TeamMembershipPolicy.OPEN))
        self.assertRaises(
            TeamMembershipPolicyError, self.field.validate,
            TeamMembershipPolicy.OPEN)

    def test_closed_team_without_active_ppas_can_become_open(self):
        # The team can become if it has deleted PPAs.
        self.setUpTeams(other_policy=TeamMembershipPolicy.MODERATED)
        ppa = self.team.createPPA()
        ppa.delete(self.team.teamowner)
        removeSecurityProxy(ppa).status = ArchiveStatus.DELETED
        self.assertTrue(
            self.field.constraint(TeamMembershipPolicy.OPEN))
        self.assertEqual(
            None, self.field.validate(TeamMembershipPolicy.OPEN))

    def test_closed_team_with_series_branch_cannot_become_open(self):
        # The team cannot become open if it has a branch linked to
        # a product series.
        self.setUpTeams()
        series = self.factory.makeProductSeries()
        branch = self.factory.makeProductBranch(
            product=series.product, owner=self.team)
        with person_logged_in(series.product.owner):
            series.branch = branch
        self.assertFalse(
            self.field.constraint(TeamMembershipPolicy.OPEN))
        self.assertRaises(
            TeamMembershipPolicyError, self.field.validate,
            TeamMembershipPolicy.OPEN)

    def test_closed_team_without_a_series_branch_can_become_open(self):
        # The team can become open if does not have a branch linked to
        # a product series.
        self.setUpTeams()
        series = self.factory.makeProductSeries()
        self.factory.makeProductBranch(product=series.product, owner=self.team)
        self.assertTrue(
            self.field.constraint(TeamMembershipPolicy.OPEN))
        self.assertEqual(
            None, self.field.validate(TeamMembershipPolicy.OPEN))

    def test_closed_team_with_private_bugs_cannot_become_open(self):
        # The team cannot become open if it is subscribed to private bugs.
        self.setUpTeams()
        bug = self.factory.makeBug(
            owner=self.team.teamowner,
            information_type=InformationType.USERDATA)
        with person_logged_in(self.team.teamowner):
            bug.subscribe(self.team, self.team.teamowner)
        self.assertFalse(
            self.field.constraint(TeamMembershipPolicy.OPEN))
        self.assertRaises(
            TeamMembershipPolicyError, self.field.validate,
            TeamMembershipPolicy.OPEN)

    def test_closed_team_with_private_bugs_assigned_cannot_become_open(self):
        # The team cannot become open if it is assigned private bugs.
        self.setUpTeams()
        bug = self.factory.makeBug(
            owner=self.team.teamowner,
            information_type=InformationType.USERDATA)
        with person_logged_in(self.team.teamowner):
            bug.default_bugtask.transitionToAssignee(self.team)
        self.assertFalse(
            self.field.constraint(TeamMembershipPolicy.OPEN))
        self.assertRaises(
            TeamMembershipPolicyError, self.field.validate,
            TeamMembershipPolicy.OPEN)

    def test_closed_team_owning_a_pillar_cannot_become_open(self):
        # The team cannot become open if it owns a pillar.
        self.setUpTeams()
        self.factory.makeProduct(owner=self.team)
        self.assertFalse(
            self.field.constraint(TeamMembershipPolicy.OPEN))
        self.assertRaises(
            TeamMembershipPolicyError, self.field.validate,
            TeamMembershipPolicy.OPEN)


class TestTeamMembershipPolicyChoiceRestrcted(
                                   TestTeamMembershipPolicyChoiceModerated):
    """Test `TeamMembershipPolicyChoice` Restricted constraints."""

    POLICY = TeamMembershipPolicy.RESTRICTED


class TestTeamMembershipPolicyChoiceOpen(TeamMembershipPolicyBase):
    """Test `TeamMembershipPolicyChoice` Open constraints."""

    POLICY = TeamMembershipPolicy.OPEN

    def test_open_team_with_open_sub_team_cannot_become_closed(self):
        # The team cannot become closed if its membership will be
        # compromised by an open subteam. The user must remove the subteam
        # first
        self.setUpTeams()
        self.team.addMember(self.other_team, self.team.teamowner)
        self.assertFalse(
            self.field.constraint(TeamMembershipPolicy.MODERATED))
        self.assertRaises(
            TeamMembershipPolicyError, self.field.validate,
            TeamMembershipPolicy.MODERATED)

    def test_open_team_with_closed_sub_team_can_become_closed(self):
        # The team can become closed.
        self.setUpTeams(other_policy=TeamMembershipPolicy.MODERATED)
        self.team.addMember(self.other_team, self.team.teamowner)
        self.assertTrue(
            self.field.constraint(TeamMembershipPolicy.MODERATED))
        self.assertEqual(
            None, self.field.validate(TeamMembershipPolicy.MODERATED))


class TestTeamMembershipPolicyChoiceDelegated(
                                        TestTeamMembershipPolicyChoiceOpen):
    """Test `TeamMembershipPolicyChoice` Delegated constraints."""

    POLICY = TeamMembershipPolicy.DELEGATED


class TestTeamMembershipPolicyValidator(TestCaseWithFactory):
    # Test that the membership policy storm validator stops bad transitions.

    layer = DatabaseFunctionalLayer

    def test_illegal_transition_to_open_subscription(self):
        # Check that TeamMembershipPolicyError is raised when an attempt is
        # made to set an illegal open membership policy on a team.
        team = self.factory.makeTeam(
            membership_policy=TeamMembershipPolicy.RESTRICTED)
        with person_logged_in(team.teamowner):
            team.createPPA()
        for policy in INCLUSIVE_TEAM_POLICY:
            self.assertRaises(
                TeamMembershipPolicyError,
                removeSecurityProxy(team).__setattr__,
                "membership_policy", policy)

    def test_illegal_transition_to_closed_subscription(self):
        # Check that TeamMembershipPolicyError is raised when an attempt is
        # made to set an illegal closed membership policy on a team.
        team = self.factory.makeTeam()
        other_team = self.factory.makeTeam(
            owner=team.teamowner,
            membership_policy=TeamMembershipPolicy.OPEN)
        with person_logged_in(team.teamowner):
            team.addMember(
                other_team, team.teamowner, force_team_add=True)

        for policy in EXCLUSIVE_TEAM_POLICY:
            self.assertRaises(
                TeamMembershipPolicyError,
                removeSecurityProxy(team).__setattr__,
                "membership_policy", policy)


class TestVisibilityConsistencyWarning(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestVisibilityConsistencyWarning, self).setUp()
        self.team = self.factory.makeTeam()
        login_celebrity('admin')

    def test_no_warning_for_PersonTransferJob(self):
        # An entry in the PersonTransferJob table does not cause a warning.
        member = self.factory.makePerson()
        metadata = ('some', 'arbitrary', 'metadata')
        PersonTransferJob(
            member, self.team,
            PersonTransferJobType.MEMBERSHIP_NOTIFICATION, metadata)
        self.assertEqual(
            None,
            self.team.visibilityConsistencyWarning(PersonVisibility.PRIVATE))


class TestPersonJoinTeam(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_join_restricted_team_error(self):
        # Calling join with a Restricted team raises an error.
        team = self.factory.makeTeam(
            membership_policy=TeamMembershipPolicy.RESTRICTED)
        user = self.factory.makePerson()
        login_person(user)
        self.assertRaises(JoinNotAllowed, user.join, team, user)

    def test_join_moderated_team_proposed(self):
        # Joining a Moderated team creates a Proposed TeamMembership.
        team = self.factory.makeTeam(
            membership_policy=TeamMembershipPolicy.MODERATED)
        user = self.factory.makePerson()
        login_person(user)
        user.join(team, user)
        users = list(team.proposedmembers)
        self.assertEqual(1, len(users))
        self.assertEqual(user, users[0])

    def test_join_delegated_team_proposed(self):
        # Joining a Delegated team creates a Proposed TeamMembership.
        team = self.factory.makeTeam(
            membership_policy=TeamMembershipPolicy.DELEGATED)
        user = self.factory.makePerson()
        login_person(user)
        user.join(team, user)
        users = list(team.proposedmembers)
        self.assertEqual(1, len(users))
        self.assertEqual(user, users[0])

    def test_join_open_team_appoved(self):
        # Joining an Open team creates an Approved TeamMembership.
        team = self.factory.makeTeam(
            membership_policy=TeamMembershipPolicy.OPEN)
        user = self.factory.makePerson()
        login_person(user)
        user.join(team, user)
        members = list(team.approvedmembers)
        self.assertEqual(1, len(members))
        self.assertEqual(user, members[0])
