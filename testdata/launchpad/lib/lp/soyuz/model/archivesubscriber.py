# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Database class for table ArchiveSubscriber."""

__metaclass__ = type

__all__ = [
    'ArchiveSubscriber',
    ]

from operator import itemgetter

import pytz
from storm.expr import (
    And,
    Desc,
    Join,
    LeftJoin,
    )
from storm.locals import (
    DateTime,
    Int,
    Reference,
    Store,
    Storm,
    Unicode,
    )
from storm.store import EmptyResultSet
from zope.component import getUtility
from zope.interface import implements

from lp.registry.interfaces.person import validate_person
from lp.registry.model.person import Person
from lp.registry.model.teammembership import TeamParticipation
from lp.services.database.constants import UTC_NOW
from lp.services.database.decoratedresultset import DecoratedResultSet
from lp.services.database.enumcol import DBEnum
from lp.services.identity.interfaces.emailaddress import EmailAddressStatus
from lp.services.identity.model.emailaddress import EmailAddress
from lp.soyuz.enums import ArchiveSubscriberStatus
from lp.soyuz.interfaces.archiveauthtoken import IArchiveAuthTokenSet
from lp.soyuz.interfaces.archivesubscriber import IArchiveSubscriber
from lp.soyuz.model.archiveauthtoken import ArchiveAuthToken


class ArchiveSubscriber(Storm):
    """See `IArchiveSubscriber`."""
    implements(IArchiveSubscriber)
    __storm_table__ = 'ArchiveSubscriber'

    id = Int(primary=True)

    archive_id = Int(name='archive', allow_none=False)
    archive = Reference(archive_id, 'Archive.id')

    registrant_id = Int(name='registrant', allow_none=False)
    registrant = Reference(registrant_id, 'Person.id')

    date_created = DateTime(
        name='date_created', allow_none=False, tzinfo=pytz.UTC)

    subscriber_id = Int(
        name='subscriber', allow_none=False,
        validator=validate_person)
    subscriber = Reference(subscriber_id, 'Person.id')

    date_expires = DateTime(
        name='date_expires', allow_none=True, tzinfo=pytz.UTC)

    status = DBEnum(
        name='status', allow_none=False,
        enum=ArchiveSubscriberStatus)

    description = Unicode(name='description', allow_none=True)

    date_cancelled = DateTime(
        name='date_cancelled', allow_none=True, tzinfo=pytz.UTC)

    cancelled_by_id = Int(name='cancelled_by', allow_none=True)
    cancelled_by = Reference(cancelled_by_id, 'Person.id')

    @property
    def displayname(self):
        """See `IArchiveSubscriber`."""
        return "%s's access to %s" % (
            self.subscriber.displayname, self.archive.displayname)

    def cancel(self, cancelled_by):
        """See `IArchiveSubscriber`."""
        self.date_cancelled = UTC_NOW
        self.cancelled_by = cancelled_by
        self.status = ArchiveSubscriberStatus.CANCELLED

    def getNonActiveSubscribers(self):
        """See `IArchiveSubscriber`."""
        store = Store.of(self)
        if self.subscriber.is_team:

            # We get all the people who already have active tokens for
            # this archive (for example, through separate subscriptions).
            auth_token = LeftJoin(
                ArchiveAuthToken,
                And(ArchiveAuthToken.person_id == Person.id,
                    ArchiveAuthToken.archive_id == self.archive_id,
                    ArchiveAuthToken.date_deactivated == None))

            team_participation = Join(
                TeamParticipation,
                TeamParticipation.personID == Person.id)

            # Only return people with preferred email address set.
            preferred_email = Join(
                EmailAddress, EmailAddress.personID == Person.id)

            # We want to get all participants who are themselves
            # individuals, not teams:
            non_active_subscribers = store.using(
                Person, team_participation, preferred_email, auth_token).find(
                (Person, EmailAddress),
                EmailAddress.status == EmailAddressStatus.PREFERRED,
                TeamParticipation.teamID == self.subscriber_id,
                Person.teamowner == None,
                # There is no existing archive auth token.
                ArchiveAuthToken.person_id == None)
            non_active_subscribers.order_by(Person.name)
            return non_active_subscribers
        else:
            # Subscriber is not a team.
            token_set = getUtility(IArchiveAuthTokenSet)
            if token_set.getActiveTokenForArchiveAndPerson(
                self.archive, self.subscriber) is not None:
                # There are active tokens, so return an empty result
                # set.
                return EmptyResultSet()

            # Otherwise return a result set containing only the
            # subscriber and their preferred email address.
            return store.find(
                (Person, EmailAddress),
                Person.id == self.subscriber_id,
                EmailAddress.personID == Person.id,
                EmailAddress.status == EmailAddressStatus.PREFERRED)


class ArchiveSubscriberSet:
    """See `IArchiveSubscriberSet`."""

    def _getBySubscriber(self, subscriber, archive, current_only,
                         with_active_tokens):
        """Return all the subscriptions for a person.

        :param subscriber: An `IPerson` for whom to return all
            `ArchiveSubscriber` records.
        :param archive: An optional `IArchive` which restricts
            the results to that particular archive.
        :param current_only: Whether the result should only include current
            subscriptions (which is the default).
        :param with_active_tokens: Indicates whether the tokens for the given
            subscribers subscriptions should be included in the resultset.
            By default the tokens are not included in the resultset.
^       """
        # Grab the extra Storm expressions, for this query,
        # depending on the params:
        extra_exprs = self._getExprsForSubscriptionQueries(
            archive, current_only)
        origin = [
            ArchiveSubscriber,
            Join(
                TeamParticipation,
                TeamParticipation.teamID == ArchiveSubscriber.subscriber_id)]

        if with_active_tokens:
            result_row = (ArchiveSubscriber, ArchiveAuthToken)
            # We need a left join with ArchiveSubscriber as
            # the origin:
            origin.append(
                LeftJoin(
                    ArchiveAuthToken,
                    And(
                        ArchiveAuthToken.archive_id ==
                            ArchiveSubscriber.archive_id,
                        ArchiveAuthToken.person_id == subscriber.id,
                        ArchiveAuthToken.date_deactivated == None)))
        else:
            result_row = ArchiveSubscriber

        # Set the main expression to find all the subscriptions for
        # which the subscriber is a direct subscriber OR is a member
        # of a subscribed team.
        # Note: the subscription to the owner itself will also be
        # part of the join as there is a TeamParticipation entry
        # showing that each person is a member of the "team" that
        # consists of themselves.
        store = Store.of(subscriber)
        return store.using(*origin).find(
            result_row,
            TeamParticipation.personID == subscriber.id,
            *extra_exprs).order_by(Desc(ArchiveSubscriber.date_created))

    def getBySubscriber(self, subscriber, archive=None, current_only=True):
        """See `IArchiveSubscriberSet`."""
        return self._getBySubscriber(subscriber, archive, current_only, False)

    def getBySubscriberWithActiveToken(self, subscriber, archive=None):
        """See `IArchiveSubscriberSet`."""
        return self._getBySubscriber(subscriber, archive, True, True)

    def getByArchive(self, archive, current_only=True):
        """See `IArchiveSubscriberSet`."""
        extra_exprs = self._getExprsForSubscriptionQueries(
            archive, current_only)

        store = Store.of(archive)
        result = store.using(ArchiveSubscriber,
             Join(Person, ArchiveSubscriber.subscriber_id == Person.id)).find(
            (ArchiveSubscriber, Person),
            *extra_exprs).order_by(Person.name)
        return DecoratedResultSet(result, itemgetter(0))

    def _getExprsForSubscriptionQueries(self, archive=None,
                                        current_only=True):
        """Return the Storm expressions required for the parameters.

        Just to keep the code DRY.
        """
        extra_exprs = []

        # Restrict the results to the specified archive if requested:
        if archive:
            extra_exprs.append(ArchiveSubscriber.archive == archive)

        # Restrict the results to only those subscriptions that are current
        # if requested:
        if current_only:
            extra_exprs.append(
                ArchiveSubscriber.status == ArchiveSubscriberStatus.CURRENT)

        return extra_exprs
