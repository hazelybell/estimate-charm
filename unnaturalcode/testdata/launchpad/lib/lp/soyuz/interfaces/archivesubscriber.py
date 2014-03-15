# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""ArchiveSubscriber interface."""

__metaclass__ = type

__all__ = [
    'ArchiveSubscriptionError',
    'IArchiveSubscriber',
    'IArchiveSubscriberSet',
    'IPersonalArchiveSubscription',
    ]

from lazr.restful.declarations import (
    export_as_webservice_entry,
    exported,
    )
from lazr.restful.fields import Reference
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Choice,
    Datetime,
    Int,
    Text,
    TextLine,
    )

from lp import _
from lp.app.interfaces.launchpad import IPrivacy
from lp.registry.interfaces.person import IPerson
from lp.services.fields import PersonChoice
from lp.soyuz.enums import ArchiveSubscriberStatus
from lp.soyuz.interfaces.archive import IArchive


class ArchiveSubscriptionError(Exception):
    """Raised for various errors when creating and activating subscriptions.
    """


class IArchiveSubscriberView(Interface):
    """An interface for launchpad.View ops on archive subscribers."""

    id = Int(title=_('ID'), required=True, readonly=True)

    archive_id = Int(title=_('Archive ID'), required=True, readonly=True)
    archive = exported(Reference(
        IArchive, title=_("Archive"), required=True, readonly=True,
        description=_("The archive for this subscription.")))

    registrant = exported(Reference(
        IPerson, title=_("Registrant"), required=True, readonly=True,
        description=_("The person who registered this subscription.")))

    date_created = exported(Datetime(
        title=_("Date Created"), required=True, readonly=True,
        description=_("The timestamp when the subscription was created.")))

    subscriber = exported(PersonChoice(
        title=_("Subscriber"), required=True, readonly=True,
        vocabulary='ValidPersonOrTeam',
        description=_("The person who is subscribed.")))
    subscriber_id = Attribute('database ID of the subscriber.')

    date_expires = exported(Datetime(
        title=_("Date of Expiration"), required=False,
        description=_("The timestamp when the subscription will expire.")))

    status = exported(Choice(
        title=_("Status"), required=True,
        vocabulary=ArchiveSubscriberStatus,
        description=_("The status of this subscription.")))

    description = exported(Text(
        title=_("Description"), required=False,
        description=_("Free text describing this subscription.")))

    date_cancelled = Datetime(
        title=_("Date of Cancellation"), required=False,
        description=_("The timestamp when the subscription was cancelled."))

    cancelled_by = Reference(
        IPerson, title=_("Cancelled By"), required=False,
        description=_("The person who cancelled the subscription."))

    displayname = TextLine(title=_("Subscription displayname"),
        required=False)

    def getNonActiveSubscribers():
        """Return the people included in this subscription.

        :return: a storm `ResultSet` of all the people and their preferred
            email address who are included in this subscription who do not
            yet have an active token for the corresponding archive.

            Persons with no preferred email addresses are not included.
        :rtype: `storm.store.ResultSet`
        """


class IArchiveSubscriberEdit(Interface):
    """An interface for launchpad.Edit ops on archive subscribers."""

    def cancel(cancelled_by):
        """Cancel a subscription.

        :param cancelled_by: An `IPerson` who is cancelling the subscription.

        Sets cancelled_by to the supplied person and date_cancelled to
        the current date/time.
        """


class IArchiveSubscriber(IArchiveSubscriberView, IArchiveSubscriberEdit):
    """An interface for archive subscribers."""
    export_as_webservice_entry()


class IArchiveSubscriberSet(Interface):
    """An interface for the set of all archive subscribers."""

    def getBySubscriber(subscriber, archive=None, current_only=True):
        """Return all the subscriptions for a person.

        :param subscriber: An `IPerson` for whom to return all
            `ArchiveSubscriber` records.
        :param archive: An optional `IArchive` which restricts
            the results to that particular archive.
        :param current_only: Whether the result should only include current
            subscriptions (which is the default).
        """

    def getBySubscriberWithActiveToken(subscriber, archive=None):
        """Return all the subscriptions for a person with the correspending
        token for each subscription.

        :param subscriber: An `IPerson` for whom to return all
            `ArchiveSubscriber` records.
        :param archive: An optional `IArchive` which restricts
            the results to that particular archive.
        :return: a storm `ResultSet` of
            (`IArchiveSubscriber`, `IArchiveAuthToken` or None) tuples.
        """

    def getByArchive(archive, current_only=True):
        """Return all the subscripions for an archive.

        :param archive: An `IArchive` for which to return all
            `ArchiveSubscriber` records.
        :param current_only: Whether the result should only include current
            subscriptions (which is the default).
        """


class IPersonalArchiveSubscription(Interface):
    """An abstract interface representing a subscription for an individual.

    An individual may be subscribed via a team, but should only ever be
    able to navigate and activate one token for their individual person.
    This non-db class allows a traversal for an individual's subscription
    to a p3a, irrespective of whether the ArchiveSubscriber records linking
    this individual to the archive are for teams or individuals.
    """
    subscriber = Reference(
        IPerson, title=_("Person"), required=True, readonly=True,
        description=_("The person for this individual subscription."))

    archive = Reference(
        IArchive, title=_("Archive"), required=True,
        description=_("The archive for this subscription."))

    displayname = TextLine(title=_("Subscription displayname"),
        required=False)

    title = TextLine(title=_("Subscription title"),
        required=False)


def pas_to_privacy(pas):
    """Converts a PersonalArchiveSubscription to privacy"""
    return IPrivacy(pas.archive)
