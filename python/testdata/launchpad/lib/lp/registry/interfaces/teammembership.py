# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Team membership interfaces."""

__metaclass__ = type

__all__ = [
    'ACTIVE_STATES',
    'CyclicalTeamMembershipError',
    'DAYS_BEFORE_EXPIRATION_WARNING_IS_SENT',
    'IJoinTeamEvent',
    'ITeamInvitationEvent',
    'ITeamMembership',
    'ITeamMembershipSet',
    'ITeamParticipation',
    'TeamMembershipStatus',
    ]

from lazr.enum import (
    DBEnumeratedType,
    DBItem,
    )
from lazr.restful.declarations import (
    call_with,
    export_as_webservice_entry,
    export_write_operation,
    exported,
    operation_parameters,
    REQUEST_USER,
    )
from lazr.restful.fields import Reference
from lazr.restful.interface import copy_field
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Bool,
    Choice,
    Datetime,
    Int,
    Text,
    )

from lp import _

# One week before a membership expires we send a notification to the member,
# either inviting him to renew his own membership or asking him to get a team
# admin to do so, depending on the team's renewal policy.
DAYS_BEFORE_EXPIRATION_WARNING_IS_SENT = 7


class TeamMembershipStatus(DBEnumeratedType):
    """TeamMembership Status

    According to the policies specified by each team, the membership status of
    a given member can be one of multiple different statuses. More information
    can be found in the TeamMembership spec.
    """

    PROPOSED = DBItem(1, """
        Proposed

        You are a proposed member of this team. To become an active member
        your subscription has to be approved by one of the team's
        administrators.
        """)

    APPROVED = DBItem(2, """
        Approved

        You are an active member of this team.
        """)

    ADMIN = DBItem(3, """
        Administrator

        You are an administrator of this team.
        """)

    DEACTIVATED = DBItem(4, """
        Deactivated

        Your subscription to this team has been deactivated.
        """)

    EXPIRED = DBItem(5, """
        Expired

        Your subscription to this team is expired.
        """)

    DECLINED = DBItem(6, """
        Declined

        Your proposed subscription to this team has been declined.
        """)

    INVITED = DBItem(7, """
        Invited

        You have been invited as a member of this team. In order to become an
        actual member, you have to accept the invitation.
        """)

    INVITATION_DECLINED = DBItem(8, """
        Invitation declined

        You have been invited as a member of this team but the invitation has
        been declined.
        """)


ACTIVE_STATES = [TeamMembershipStatus.ADMIN, TeamMembershipStatus.APPROVED]


class ITeamMembership(Interface):
    """TeamMembership for Users.

    This table includes *direct* team members only.  Indirect memberships are
    handled by the TeamParticipation table.
    """
    export_as_webservice_entry()

    id = Int(title=_('ID'), required=True, readonly=True)
    team = exported(
        Reference(title=_("Team"), required=True, readonly=True,
                  schema=Interface))  # Specified in interfaces/person.py.
    person = exported(
        Reference(title=_("Member"), required=True, readonly=True,
                  schema=Interface),  # Specified in interfaces/person.py.
        exported_as='member')
    proposed_by = Attribute(_('Proponent'))
    reviewed_by = Attribute(
        _("The team admin who approved/rejected the member."))
    acknowledged_by = Attribute(
        _('The person (usually the member or someone acting on his behalf) '
          'that acknowledged (accepted/declined) a membership invitation.'))
    last_changed_by = exported(
        Reference(title=_('Last person who change this'),
                  required=False, readonly=True,
                  schema=Interface))  # Specified in interfaces/person.py.

    datejoined = exported(
        Datetime(title=_("Date joined"), required=False, readonly=True,
                 description=_("The date in which this membership was made "
                               "active for the first time.")),
        exported_as='date_joined')
    dateexpires = exported(
        Datetime(title=_("Date expires"), required=False, readonly=True),
        exported_as='date_expires')
    date_created = Datetime(
        title=_("Date created"), required=False, readonly=True,
        description=_("The date in which this membership was created."))
    date_proposed = Datetime(
        title=_("Date proposed"), required=False, readonly=True,
        description=_("The date in which this membership was proposed."))
    date_acknowledged = Datetime(
        title=_("Date acknowledged"), required=False, readonly=True,
        description=_("The date in which this membership was acknowledged by "
                      "the member (or someone acting on their behalf)."))
    date_reviewed = Datetime(
        title=_("Date reviewed"), required=False, readonly=True,
        description=_("The date in which this membership was approved/"
                      "rejected by one of the team's admins."))
    date_last_changed = Datetime(
        title=_("Date last changed"), required=False, readonly=True,
        description=_("The date in which this membership was last changed."))

    last_change_comment = exported(
        Text(title=_("Comment on the last change"), required=False,
             readonly=True))
    proponent_comment = Text(
        title=_("Proponent comment"), required=False, readonly=True)
    acknowledger_comment = Text(
        title=_("Acknowledger comment"), required=False, readonly=True)
    reviewer_comment = Text(
        title=_("Reviewer comment"), required=False, readonly=True)
    status = exported(
        Choice(title=_("The state of this membership"), required=True,
               readonly=True, vocabulary=TeamMembershipStatus))

    def isExpired():
        """Return True if this membership's status is EXPIRED."""

    def canChangeExpirationDate(person):
        """Can the given person change this membership's expiration date?

        A membership's expiration date can be changed by the team owner, by a
        Launchpad admin or by a team admin. In the latter case, though, the
        expiration date can only be changed if the admin is not changing his
        own membership.
        """

    @call_with(user=REQUEST_USER)
    @operation_parameters(date=copy_field(dateexpires))
    @export_write_operation()
    def setExpirationDate(date, user):
        """Set this membership's expiration date.

        The given date must be None or in the future and the given user must
        be allowed to change this membership's expiration date as per the
        rules defined in canChangeExpirationDate().
        """

    def canBeRenewedByMember():
        """Can this membership be renewed by the member himself?

        A membership can be renewed if the team's renewal policy is ONDEMAND,
        the membership itself is active (status = [ADMIN|APPROVED]) and it's
        set to expire in less than DAYS_BEFORE_EXPIRATION_WARNING_IS_SENT
        days.
        """

    def sendSelfRenewalNotification():
        """Send an email to the team admins notifying that this membership
        has been renewed by the member himself.

        This method must not be called if the team's renewal policy is not
        ONDEMAND.
        """

    def sendExpirationWarningEmail():
        """Send the member an email warning that the membership will expire.

        This method cannot be called for memberships without an expiration
        date. Emails are not sent to members if their membership has already
        expired or if the member is no longer active.

        :raises AssertionError: if the member has no expiration date of the
            team or if the TeamMembershipRenewalPolicy is AUTOMATIC.
        """

    @call_with(user=REQUEST_USER)
    @operation_parameters(
        status=copy_field(status),
        comment=copy_field(reviewer_comment),
        silent=Bool(title=_("Do not send notifications of status change.  "
                            "For use by Launchpad administrators only."),
                            required=False, default=False))
    @export_write_operation()
    def setStatus(status, user, comment=None, silent=False):
        """Set the status of this membership.

        The user and comment are stored in last_changed_by and
        last_change_comment and may also be stored in proposed_by
        (and proponent_comment), reviewed_by (and reviewer_comment) or
        acknowledged_by (and acknowledger_comment), depending on the state
        transition.

        The given status must be different than the current status.

        Return True if the status got changed, otherwise False.
        """


class ITeamMembershipSet(Interface):
    """A Set for TeamMembership objects."""

    def handleMembershipsExpiringToday(reviewer):
        """Expire or renew the memberships flagged to expire today.

        If the team's renewal policy is AUTOMATIC, renew the membership
        (keeping the same status) and send a notification to the member and
        team admins. Otherwise flag the membership as expired.
        """

    def getMembershipsToExpire(when=None):
        """Return all TeamMemberships that should be expired.

        If when is None, we use datetime.now().

        A TeamMembership should be expired when its expiry date is prior or
        equal to :when: and its status is either ADMIN or APPROVED.
        """

    def new(person, team, status, user, dateexpires=None, comment=None):
        """Create and return a TeamMembership for the given person and team.

        :param status: The TeamMembership's status. Must be one of APPROVED,
            PROPOSED or ADMIN. If the status is APPROVED or ADMIN, this method
            will also take care of filling the TeamParticipation table.
        :param user: The person whose action triggered this membership's
            creation.
        :param dateexpires: The date in which the membership should expire.
        :param comment: The rationale for this membership's creation.
        """

    def getByPersonAndTeam(person, team):
        """Return the TeamMembership object for the given person and team.

        If the given person or team is None, there will obviously be no
        TeamMembership and I'll return None.
        """

    def deactivateActiveMemberships(team, comment, reviewer):
        """Deactivate all team members in ACTIVE_STATES.

        This is a convenience method used before teams are deleted.

        :param team: The team to deactivate.
        :param comment: An explanation for the deactivation.
        :param reviewer: The user doing the deactivation.
        """


class ITeamParticipation(Interface):
    """A TeamParticipation.

    A TeamParticipation object represents a person being a member of a team.
    Please note that because a team is also a person in Launchpad, we can
    have a TeamParticipation object representing a team that is a member of
    another team. We can also have an object that represents a person being a
    member of itself.
    """

    id = Int(title=_('ID'), required=True, readonly=True)
    team = Reference(
        title=_("The team"), required=True, readonly=True,
        schema=Interface)  # Specified in interfaces/person.py.
    person = Reference(
        title=_("The member"), required=True, readonly=True,
        schema=Interface)  # Specified in interfaces/person.py.


class CyclicalTeamMembershipError(Exception):
    """A change resulting in a team membership cycle was attempted.

    Two teams cannot be members of each other and there cannot be
    any cyclical relationships.  So if A is a member of B and B is
    a member of C then attempting to make C a member of A will
    result in this error being raised.
    """


class IJoinTeamEvent(Interface):
    """A person/team joined (or tried to join) a team."""

    person = Attribute("The person/team who joined the team.")
    team = Attribute("The team.")


class ITeamInvitationEvent(Interface):
    """A new person/team has been invited to a team."""

    member = Attribute("The person/team who was invited.")
    team = Attribute("The team.")
