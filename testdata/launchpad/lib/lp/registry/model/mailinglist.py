# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'HeldMessageDetails',
    'MailingList',
    'MailingListSet',
    'MailingListSubscription',
    'MessageApproval',
    'MessageApprovalSet',
    ]


import collections
import operator
from socket import getfqdn
from string import Template

from lazr.lifecycle.event import (
    ObjectCreatedEvent,
    ObjectModifiedEvent,
    )
from lazr.lifecycle.snapshot import Snapshot
from sqlobject import (
    ForeignKey,
    StringCol,
    )
from storm.expr import (
    And,
    Join,
    Or,
    )
from storm.info import ClassAlias
from storm.store import Store
from zope.component import (
    getUtility,
    queryAdapter,
    )
from zope.event import notify
from zope.interface import (
    implements,
    providedBy,
    )
from zope.security.proxy import removeSecurityProxy

from lp import _
from lp.registry.interfaces.mailinglist import (
    CannotChangeSubscription,
    CannotSubscribe,
    CannotUnsubscribe,
    IHeldMessageDetails,
    IMailingList,
    IMailingListSet,
    IMailingListSubscription,
    IMessageApproval,
    IMessageApprovalSet,
    MailingListStatus,
    PostedMessageStatus,
    PURGE_STATES,
    UnsafeToPurge,
    )
from lp.registry.interfaces.person import validate_public_person
from lp.registry.model.person import Person
from lp.registry.model.teammembership import TeamParticipation
from lp.services.config import config
from lp.services.database.constants import (
    DEFAULT,
    UTC_NOW,
    )
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.decoratedresultset import DecoratedResultSet
from lp.services.database.enumcol import EnumCol
from lp.services.database.interfaces import (
    IMasterStore,
    IStore,
    )
from lp.services.database.sqlbase import (
    SQLBase,
    sqlvalues,
    )
from lp.services.identity.interfaces.account import AccountStatus
from lp.services.identity.interfaces.emailaddress import (
    EmailAddressStatus,
    IEmailAddressSet,
    )
from lp.services.identity.model.account import Account
from lp.services.identity.model.emailaddress import EmailAddress
from lp.services.messages.model.message import Message
from lp.services.privacy.interfaces import IObjectPrivacy
from lp.services.propertycache import cachedproperty


EMAIL_ADDRESS_STATUSES = (
    EmailAddressStatus.VALIDATED,
    EmailAddressStatus.PREFERRED)
MESSAGE_APPROVAL_STATUSES = (
    PostedMessageStatus.APPROVED,
    PostedMessageStatus.APPROVAL_PENDING)


class MessageApproval(SQLBase):
    """A held message."""

    implements(IMessageApproval)

    message = ForeignKey(
        dbName='message', foreignKey='Message',
        notNull=True)

    posted_by = ForeignKey(
        dbName='posted_by', foreignKey='Person',
        storm_validator=validate_public_person,
        notNull=True)

    posted_message = ForeignKey(
        dbName='posted_message', foreignKey='LibraryFileAlias',
        notNull=True)

    posted_date = UtcDateTimeCol(notNull=True, default=UTC_NOW)

    mailing_list = ForeignKey(
        dbName='mailing_list', foreignKey='MailingList',
        notNull=True)

    status = EnumCol(enum=PostedMessageStatus,
                     default=PostedMessageStatus.NEW,
                     notNull=True)

    disposed_by = ForeignKey(
        dbName='disposed_by', foreignKey='Person',
        storm_validator=validate_public_person,
        default=None)

    disposal_date = UtcDateTimeCol(default=None)

    @property
    def message_id(self):
        """See `IMessageApproval`."""
        return self.message.rfc822msgid

    def approve(self, reviewer):
        """See `IMessageApproval`."""
        self.disposed_by = reviewer
        self.disposal_date = UTC_NOW
        self.status = PostedMessageStatus.APPROVAL_PENDING

    def reject(self, reviewer):
        """See `IMessageApproval`."""
        self.disposed_by = reviewer
        self.disposal_date = UTC_NOW
        self.status = PostedMessageStatus.REJECTION_PENDING

    def discard(self, reviewer):
        """See `IMessageApproval`."""
        self.disposed_by = reviewer
        self.disposal_date = UTC_NOW
        self.status = PostedMessageStatus.DISCARD_PENDING

    def acknowledge(self):
        """See `IMessageApproval`."""
        if self.status == PostedMessageStatus.APPROVAL_PENDING:
            self.status = PostedMessageStatus.APPROVED
        elif self.status == PostedMessageStatus.REJECTION_PENDING:
            self.status = PostedMessageStatus.REJECTED
        elif self.status == PostedMessageStatus.DISCARD_PENDING:
            self.status = PostedMessageStatus.DISCARDED
        else:
            raise AssertionError('Not an acknowledgeable state: %s' %
                                 self.status)


class MailingList(SQLBase):
    """The mailing list for a team.

    Teams may have at most one mailing list, and a mailing list is associated
    with exactly one team.  This table manages the state changes that a team
    mailing list can go through, and it contains information that will be used
    to instruct Mailman how to create, delete, and modify mailing lists (via
    XMLRPC).
    """

    implements(IMailingList)

    team = ForeignKey(
        dbName='team', foreignKey='Person',
        notNull=True)

    registrant = ForeignKey(
        dbName='registrant', foreignKey='Person',
        storm_validator=validate_public_person, notNull=True)

    date_registered = UtcDateTimeCol(notNull=True, default=DEFAULT)

    reviewer = ForeignKey(
        dbName='reviewer', foreignKey='Person',
        storm_validator=validate_public_person, default=None)

    date_reviewed = UtcDateTimeCol(notNull=False, default=None)

    date_activated = UtcDateTimeCol(notNull=False, default=None)

    status = EnumCol(enum=MailingListStatus,
                     default=MailingListStatus.APPROVED,
                     notNull=True)

    # Use a trailing underscore because SQLObject/importfascist doesn't like
    # the typical leading underscore.
    welcome_message_ = StringCol(default=None, dbName='welcome_message')

    @property
    def address(self):
        """See `IMailingList`."""
        if config.mailman.build_host_name:
            host_name = config.mailman.build_host_name
        else:
            host_name = getfqdn()
        return '%s@%s' % (self.team.name, host_name)

    @property
    def archive_url(self):
        """See `IMailingList`."""
        # These represent states that can occur at or after a mailing list has
        # been activated.  Once it's been activated, a mailing list could have
        # an archive.
        if self.status not in [MailingListStatus.ACTIVE,
                               MailingListStatus.INACTIVE,
                               MailingListStatus.MODIFIED,
                               MailingListStatus.UPDATING,
                               MailingListStatus.DEACTIVATING,
                               MailingListStatus.MOD_FAILED]:
            return None
        # There could be an archive, return its url.
        template = Template(config.mailman.archive_url_template)
        return template.safe_substitute(team_name=self.team.name)

    def __repr__(self):
        return '<MailingList for team "%s"; status=%s; address=%s at %#x>' % (
            self.team.name, self.status.name, self.address, id(self))

    def startConstructing(self):
        """See `IMailingList`."""
        assert self.status == MailingListStatus.APPROVED, (
            'Only approved mailing lists may be constructed')
        self.status = MailingListStatus.CONSTRUCTING

    def startUpdating(self):
        """See `IMailingList`."""
        assert self.status == MailingListStatus.MODIFIED, (
            'Only modified mailing lists may be updated')
        self.status = MailingListStatus.UPDATING

    def transitionToStatus(self, target_state):
        """See `IMailingList`."""
        # State: From CONSTRUCTING to either ACTIVE or FAILED
        if self.status == MailingListStatus.CONSTRUCTING:
            assert target_state in (MailingListStatus.ACTIVE,
                                    MailingListStatus.FAILED), (
                'target_state result must be active or failed')
        # State: From UPDATING to either ACTIVE or MOD_FAILED
        elif self.status == MailingListStatus.UPDATING:
            assert target_state in (MailingListStatus.ACTIVE,
                                    MailingListStatus.MOD_FAILED), (
                'target_state result must be active or mod_failed')
        # State: From DEACTIVATING to INACTIVE or MOD_FAILED
        elif self.status == MailingListStatus.DEACTIVATING:
            assert target_state in (MailingListStatus.INACTIVE,
                                    MailingListStatus.MOD_FAILED), (
                'target_state result must be inactive or mod_failed')
        else:
            raise AssertionError(
                'Not a valid state transition: %s -> %s'
                % (self.status, target_state))
        self.status = target_state
        if target_state == MailingListStatus.ACTIVE:
            self._setAndNotifyDateActivated()
            email_set = getUtility(IEmailAddressSet)
            email = email_set.getByEmail(self.address)
            if email is None:
                email = email_set.new(self.address, self.team)
            if email.status in [EmailAddressStatus.NEW,
                                EmailAddressStatus.OLD]:
                # Without this conditional, if the mailing list is the
                # contact method
                # (email.status==EmailAddressStatus.PREFERRED), and a
                # user changes the mailing list configuration, then
                # when the list status goes back to ACTIVE the email
                # will go from PREFERRED to VALIDATED and the list
                # will stop being the contact method.
                # We also need to remove the email's security proxy because
                # this method will be called via the internal XMLRPC rather
                # than as a response to a user action.
                removeSecurityProxy(email).status = (
                    EmailAddressStatus.VALIDATED)
            assert email.personID == self.teamID, (
                "Email already associated with another team.")

    def _setAndNotifyDateActivated(self):
        """Set the date_activated field and fire a
        SQLObjectModified event.

        The date_activated field is only set once - repeated calls
        will not change the field's value.

        Similarly, the modification event only fires the first time
        that the field is set.
        """
        if self.date_activated is not None:
            return

        old_mailinglist = Snapshot(self, providing=providedBy(self))
        self.date_activated = UTC_NOW
        notify(ObjectModifiedEvent(
                self,
                object_before_modification=old_mailinglist,
                edited_fields=['date_activated']))

    def deactivate(self):
        """See `IMailingList`."""
        assert self.status == MailingListStatus.ACTIVE, (
            'Only active mailing lists may be deactivated')
        self.status = MailingListStatus.DEACTIVATING
        email = getUtility(IEmailAddressSet).getByEmail(self.address)
        if email is not None and self.team.preferredemail is not None:
            if email.id == self.team.preferredemail.id:
                self.team.setContactAddress(None)
        assert email.personID == self.teamID, 'Incorrectly linked email.'
        # Anyone with permission to deactivate a list can also set the
        # email address status to NEW.
        removeSecurityProxy(email).status = EmailAddressStatus.NEW

    def reactivate(self):
        """See `IMailingList`."""
        assert self.status == MailingListStatus.INACTIVE, (
            'Only inactive mailing lists may be reactivated')
        self.status = MailingListStatus.APPROVED

    @property
    def is_public(self):
        """See `IMailingList`."""
        return not queryAdapter(self.team, IObjectPrivacy).is_private

    @property
    def is_usable(self):
        """See `IMailingList`."""
        return self.status in [MailingListStatus.ACTIVE,
                               MailingListStatus.MODIFIED,
                               MailingListStatus.UPDATING,
                               MailingListStatus.MOD_FAILED]

    def _get_welcome_message(self):
        return self.welcome_message_

    def _set_welcome_message(self, text):
        if self.status == MailingListStatus.REGISTERED:
            # Do nothing because the status does not change.  When setting the
            # welcome_message on a newly registered mailing list the XMLRPC
            # layer will essentially tell Mailman to initialize this attribute
            # at list construction time.  It is enough to just set the
            # database attribute to properly notify Mailman what to do.
            pass
        elif self.is_usable:
            # Transition the status to MODIFIED so that the XMLRPC layer knows
            # that it has to inform Mailman that a mailing list attribute has
            # been changed on an active list.
            self.status = MailingListStatus.MODIFIED
        else:
            raise AssertionError('Only usable mailing lists may be modified')
        self.welcome_message_ = text

    welcome_message = property(_get_welcome_message, _set_welcome_message)

    def getSubscription(self, person):
        """See `IMailingList`."""
        return MailingListSubscription.selectOneBy(person=person,
                                                   mailing_list=self)

    def getSubscribers(self):
        """See `IMailingList`."""
        store = Store.of(self)
        results = store.find(Person,
                             TeamParticipation.person == Person.id,
                             TeamParticipation.team == self.team,
                             MailingListSubscription.person == Person.id,
                             MailingListSubscription.mailing_list == self)
        return results.order_by(Person.displayname, Person.name)

    def subscribe(self, person, address=None):
        """See `IMailingList`."""
        if not self.is_usable:
            raise CannotSubscribe('Mailing list is not usable: %s' %
                                  self.team.displayname)
        if person.is_team:
            raise CannotSubscribe('Teams cannot be mailing list members: %s' %
                                  person.displayname)
        if address is not None and address.personID != person.id:
            raise CannotSubscribe('%s does not own the email address: %s' %
                                  (person.displayname, address.email))
        subscription = self.getSubscription(person)
        if subscription is not None:
            raise CannotSubscribe('%s is already subscribed to list %s' %
                                  (person.displayname, self.team.displayname))
        # Add the subscription for this person to this mailing list.
        MailingListSubscription(
            person=person,
            mailing_list=self,
            email_address=address)

    def unsubscribe(self, person):
        """See `IMailingList`."""
        subscription = self.getSubscription(person)
        if subscription is None:
            raise CannotUnsubscribe(
                '%s is not a member of the mailing list: %s' %
                (person.displayname, self.team.displayname))
        subscription.destroySelf()

    def changeAddress(self, person, address):
        """See `IMailingList`."""
        subscription = self.getSubscription(person)
        if subscription is None:
            raise CannotChangeSubscription(
                '%s is not a member of the mailing list: %s' %
                (person.displayname, self.team.displayname))
        if address is not None and address.personID != person.id:
            raise CannotChangeSubscription(
                '%s does not own the email address: %s' %
                (person.displayname, address.email))
        if address is None:
            subscription.email_address = None
        else:
            subscription.email_addressID = address.id

    def holdMessage(self, message):
        """See `IMailingList`."""
        held_message = MessageApproval(message=message,
                                       posted_by=message.owner,
                                       posted_message=message.raw,
                                       posted_date=message.datecreated,
                                       mailing_list=self)
        notify(ObjectCreatedEvent(held_message))
        return held_message

    def getReviewableMessages(self, message_id_filter=None):
        """See `IMailingList`."""
        store = Store.of(self)
        clauses = [
            MessageApproval.mailing_listID == self.id,
            MessageApproval.status == PostedMessageStatus.NEW,
            MessageApproval.messageID == Message.id,
            MessageApproval.posted_byID == Person.id
            ]
        if message_id_filter is not None:
            clauses.append(Message.rfc822msgid.is_in(message_id_filter))
        results = store.find(
            (MessageApproval, Message, Person), *clauses)
        results.order_by(MessageApproval.posted_date, Message.rfc822msgid)
        return DecoratedResultSet(results, operator.itemgetter(0))

    def purge(self):
        """See `IMailingList`."""
        # At first glance, it would seem that we could use
        # transitionToStatus(), but it actually doesn't quite match the
        # semantics we want.  For example, if we try to purge an active
        # mailing list we really want an UnsafeToPurge exception instead of an
        # AssertionError.  Fitting that in to transitionToStatus()'s logic is
        # a bit tortured, so just do it here.
        if self.status in PURGE_STATES:
            self.status = MailingListStatus.PURGED
            email = getUtility(IEmailAddressSet).getByEmail(self.address)
            if email is not None:
                removeSecurityProxy(email).destroySelf()
        else:
            assert self.status != MailingListStatus.PURGED, 'Already purged'
            raise UnsafeToPurge(self)


class MailingListSet:
    implements(IMailingListSet)

    title = _('Team mailing lists')

    def new(self, team, registrant=None):
        """See `IMailingListSet`."""
        if not team.is_team:
            raise ValueError('Cannot register a list for a user.')
        if registrant is None:
            registrant = team.teamowner
        else:
            # Check to make sure that registrant is a team owner or admin.
            # This gets tricky because an admin can be a team, and if the
            # registrant is a member of that team, they are by definition an
            # administrator of the team we're creating the mailing list for.
            # So you can't just do "registrant in
            # team.getDirectAdministrators()".  It's okay to use .inTeam() for
            # all cases because a person is always a member of himself.
            for admin in team.getDirectAdministrators():
                if registrant.inTeam(admin):
                    break
            else:
                raise ValueError(
                    'registrant is not a team owner or administrator')
        # See if the mailing list already exists.  If so, it must be in the
        # purged state for us to be able to recreate it.
        existing_list = self.get(team.name)
        if existing_list is None:
            # We have no record for the mailing list, so just create it.
            return MailingList(team=team, registrant=registrant,
                               date_registered=UTC_NOW)
        else:
            if existing_list.status != MailingListStatus.PURGED:
                raise ValueError(
                    'Mailing list for team "%s" already exists' % team.name)
            if existing_list.team != team:
                raise ValueError('Team mismatch.')
            # It's in the PURGED state, so just tweak the existing record.
            existing_list.registrant = registrant
            existing_list.date_registered = UTC_NOW
            existing_list.reviewer = None
            existing_list.date_reviewed = None
            existing_list.date_activated = None
            # This is a little wacky, but it's this way for historical
            # purposes.  When mailing lists required approval before being
            # created, it was okay to change the welcome message while in the
            # REGISTERED state.  Now that we don't use REGISTERED any more,
            # resurrecting a purged mailing list means setting it directly to
            # the APPROVED state, but we're not allowed to change the welcome
            # message in that state because it will get us out of sync with
            # Mailman.  We really don't want to change _set_welcome_message()
            # because that will have other consequences, so set to REGISTERED
            # just long enough to set the welcome message, then set to
            # APPROVED.  Mailman will catch up correctly.
            existing_list.status = MailingListStatus.REGISTERED
            existing_list.welcome_message = None
            existing_list.status = MailingListStatus.APPROVED
            return existing_list

    def get(self, team_name):
        """See `IMailingListSet`."""
        assert isinstance(team_name, basestring), (
            'team_name must be a string, not %s' % type(team_name))
        return MailingList.selectOne("""
            MailingList.team = Person.id
            AND Person.name = %s
            AND Person.teamowner IS NOT NULL
            """ % sqlvalues(team_name),
            clauseTables=['Person'])

    def _getTeamIdsAndMailingListIds(self, team_names):
        """Return a tuple of team and mailing list Ids for the team names."""
        store = IStore(MailingList)
        tables = (
            Person,
            Join(MailingList, MailingList.team == Person.id))
        results = set(store.using(*tables).find(
            (Person.id, MailingList.id),
            And(Person.name.is_in(team_names),
                Person.teamowner != None)))
        team_ids = [result[0] for result in results]
        list_ids = [result[1] for result in results]
        return team_ids, list_ids

    def getSubscribedAddresses(self, team_names):
        """See `IMailingListSet`."""
        store = IStore(MailingList)
        Team = ClassAlias(Person)
        tables = (
            EmailAddress,
            Join(Person, Person.id == EmailAddress.personID),
            Join(Account, Account.id == Person.accountID),
            Join(TeamParticipation, TeamParticipation.personID == Person.id),
            Join(
                MailingListSubscription,
                MailingListSubscription.personID == Person.id),
            Join(
                MailingList,
                MailingList.id == MailingListSubscription.mailing_listID),
            Join(Team, Team.id == MailingList.teamID),
            )
        team_ids, list_ids = self._getTeamIdsAndMailingListIds(team_names)
        preferred = store.using(*tables).find(
            (EmailAddress.email, Person.displayname, Team.name),
            And(MailingListSubscription.mailing_listID.is_in(list_ids),
                TeamParticipation.teamID.is_in(team_ids),
                MailingList.teamID == TeamParticipation.teamID,
                MailingList.status != MailingListStatus.INACTIVE,
                Account.status == AccountStatus.ACTIVE,
                Or(
                    And(MailingListSubscription.email_addressID == None,
                        EmailAddress.status == EmailAddressStatus.PREFERRED),
                    EmailAddress.id ==
                        MailingListSubscription.email_addressID),
                ))
        # Sort by team name.
        by_team = collections.defaultdict(set)
        for email, display_name, team_name in preferred:
            assert team_name in team_names, (
                'Unexpected team name in results: %s' % team_name)
            value = (display_name, email.lower())
            by_team[team_name].add(value)
        # Turn the results into a mapping of lists.
        results = {}
        for team_name, address_set in by_team.items():
            results[team_name] = list(address_set)
        return results

    def getSenderAddresses(self, team_names):
        """See `IMailingListSet`."""
        store = IStore(MailingList)
        # First, we need to find all the members of all the mailing lists for
        # the given teams.  Find all of their validated and preferred email
        # addresses of those team members.  Every one of those email addresses
        # are allowed to post to the mailing list.
        Team = ClassAlias(Person)
        tables = (
            Person,
            Join(Account, Account.id == Person.accountID),
            Join(EmailAddress, EmailAddress.personID == Person.id),
            Join(TeamParticipation, TeamParticipation.personID == Person.id),
            Join(MailingList, MailingList.teamID == TeamParticipation.teamID),
            Join(Team, Team.id == MailingList.teamID),
            )
        team_ids, list_ids = self._getTeamIdsAndMailingListIds(team_names)
        team_members = store.using(*tables).find(
            (Team.name, Person.displayname, EmailAddress.email),
            And(TeamParticipation.teamID.is_in(team_ids),
                MailingList.status != MailingListStatus.INACTIVE,
                Person.teamowner == None,
                EmailAddress.status.is_in(EMAIL_ADDRESS_STATUSES),
                Account.status == AccountStatus.ACTIVE,
                ))
        # Second, find all of the email addresses for all of the people who
        # have been explicitly approved for posting to the team mailing lists.
        # This occurs as part of first post moderation, but since they've
        # already been approved for the specific list, we don't need to wait
        # for three global approvals.
        tables = (
            Person,
            Join(Account, Account.id == Person.accountID),
            Join(EmailAddress, EmailAddress.personID == Person.id),
            Join(MessageApproval, MessageApproval.posted_byID == Person.id),
            Join(MailingList,
                     MailingList.id == MessageApproval.mailing_listID),
            Join(Team, Team.id == MailingList.teamID),
            )
        approved_posters = store.using(*tables).find(
            (Team.name, Person.displayname, EmailAddress.email),
            And(MessageApproval.mailing_listID.is_in(list_ids),
                MessageApproval.status.is_in(MESSAGE_APPROVAL_STATUSES),
                EmailAddress.status.is_in(EMAIL_ADDRESS_STATUSES),
                Account.status == AccountStatus.ACTIVE,
                ))
        # Sort allowed posters by team/mailing list.
        by_team = collections.defaultdict(set)
        all_posters = team_members.union(approved_posters)
        for team_name, person_displayname, email in all_posters:
            assert team_name in team_names, (
                'Unexpected team name in results: %s' % team_name)
            value = (person_displayname, email.lower())
            by_team[team_name].add(value)
        # Turn the results into a mapping of lists.
        results = {}
        for team_name, address_set in by_team.items():
            results[team_name] = list(address_set)
        return results

    @property
    def approved_lists(self):
        """See `IMailingListSet`."""
        return MailingList.selectBy(status=MailingListStatus.APPROVED)

    @property
    def active_lists(self):
        """See `IMailingListSet`."""
        return MailingList.selectBy(status=MailingListStatus.ACTIVE)

    @property
    def modified_lists(self):
        """See `IMailingListSet`."""
        return MailingList.selectBy(status=MailingListStatus.MODIFIED)

    @property
    def deactivated_lists(self):
        """See `IMailingListSet`."""
        return MailingList.selectBy(status=MailingListStatus.DEACTIVATING)

    @property
    def unsynchronized_lists(self):
        """See `IMailingListSet`."""
        return MailingList.select('status IN %s' % sqlvalues(
            (MailingListStatus.CONSTRUCTING, MailingListStatus.UPDATING)))


class MailingListSubscription(SQLBase):
    """A mailing list subscription."""

    implements(IMailingListSubscription)

    person = ForeignKey(
        dbName='person', foreignKey='Person',
        storm_validator=validate_public_person,
        notNull=True)

    mailing_list = ForeignKey(
        dbName='mailing_list', foreignKey='MailingList',
        notNull=True)

    date_joined = UtcDateTimeCol(notNull=True, default=UTC_NOW)

    email_address = ForeignKey(dbName='email_address',
                               foreignKey='EmailAddress')

    @property
    def subscribed_address(self):
        """See `IMailingListSubscription`."""
        if self.email_address is None:
            # Use the person's preferred email address.
            return self.person.preferredemail
        else:
            # Use the subscribed email address.
            return self.email_address


class MessageApprovalSet:
    """Sets of held messages."""

    implements(IMessageApprovalSet)

    def getMessageByMessageID(self, message_id):
        """See `IMessageApprovalSet`."""
        return MessageApproval.selectOne("""
            MessageApproval.message = Message.id AND
            Message.rfc822msgid = %s
            """ % sqlvalues(message_id),
            distinct=True, clauseTables=['Message'])

    def getHeldMessagesWithStatus(self, status):
        """See `IMessageApprovalSet`."""
        # Use the master store as the messages will also be acknowledged and
        # we want to make sure we are acknowledging the same messages that we
        # iterate over.
        return IMasterStore(MessageApproval).find(
            (Message.rfc822msgid, Person.name),
            MessageApproval.status == status,
            MessageApproval.message == Message.id,
            MessageApproval.mailing_list == MailingList.id,
            MailingList.team == Person.id)

    def acknowledgeMessagesWithStatus(self, status):
        """See `IMessageApprovalSet`."""
        transitions = {
            PostedMessageStatus.APPROVAL_PENDING:
                PostedMessageStatus.APPROVED,
            PostedMessageStatus.REJECTION_PENDING:
                PostedMessageStatus.REJECTED,
            PostedMessageStatus.DISCARD_PENDING:
                PostedMessageStatus.DISCARDED,
            }
        try:
            next_state = transitions[status]
        except KeyError:
            raise AssertionError(
                'Not an acknowledgeable state: %s' % status)
        approvals = IMasterStore(MessageApproval).find(
            MessageApproval, MessageApproval.status == status)
        approvals.set(status=next_state)


class HeldMessageDetails:
    """Details about a held message."""

    implements(IHeldMessageDetails)

    def __init__(self, message_approval):
        self.message_approval = message_approval
        self.message = message_approval.message
        self.message_id = message_approval.message_id
        self.subject = self.message.subject
        self.date = self.message.datecreated
        self.author = self.message_approval.posted_by

    @cachedproperty
    def body(self):
        """See `IHeldMessageDetails`."""
        return self.message.text_contents
