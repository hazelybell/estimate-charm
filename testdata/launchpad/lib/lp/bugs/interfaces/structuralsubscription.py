# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""StructuralSubscription interfaces."""

__metaclass__ = type

__all__ = [
    'IStructuralSubscription',
    'IStructuralSubscriptionForm',
    'IStructuralSubscriptionTarget',
    'IStructuralSubscriptionTargetHelper',
    ]

from lazr.restful.declarations import (
    call_with,
    export_as_webservice_entry,
    export_destructor_operation,
    export_factory_operation,
    export_read_operation,
    export_write_operation,
    exported,
    operation_for_version,
    operation_parameters,
    operation_returns_collection_of,
    operation_returns_entry,
    REQUEST_USER,
    )
from lazr.restful.fields import (
    CollectionField,
    Reference,
    )
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Bool,
    Datetime,
    Int,
    )

from lp import _
from lp.registry.interfaces.person import IPerson
from lp.services.fields import (
    PersonChoice,
    PublicPersonChoice,
    )


class IStructuralSubscriptionPublic(Interface):
    """The public parts of a subscription to a Launchpad structure."""

    id = Int(title=_('ID'), readonly=True, required=True)
    product = Int(title=_('Product'), required=False, readonly=True)
    productseries = Int(
        title=_('Product series'), required=False, readonly=True)
    project = Int(title=_('Project group'), required=False, readonly=True)
    milestone = Int(title=_('Milestone'), required=False, readonly=True)
    distribution = Int(title=_('Distribution'), required=False, readonly=True)
    distroseries = Int(
        title=_('Distribution series'), required=False, readonly=True)
    sourcepackagename = Int(
        title=_('Source package name'), required=False, readonly=True)
    subscriber = exported(PersonChoice(
        title=_('Subscriber'), required=True, vocabulary='ValidPersonOrTeam',
        readonly=True, description=_("The person subscribed.")))
    subscribed_by = exported(PublicPersonChoice(
        title=_('Subscribed by'), required=True,
        vocabulary='ValidPersonOrTeam', readonly=True,
        description=_("The person creating the subscription.")))
    date_created = exported(Datetime(
        title=_("The date on which this subscription was created."),
        required=False, readonly=True))
    date_last_updated = exported(Datetime(
        title=_("The date on which this subscription was last updated."),
        required=False, readonly=True))

    target = exported(Reference(
        schema=Interface, # IStructuralSubscriptionTarget
        required=True, readonly=True,
        title=_("The structure to which this subscription belongs.")))

    bug_filters = exported(CollectionField(
        title=_('List of bug filters that narrow this subscription.'),
        readonly=True, required=False,
        value_type=Reference(schema=Interface))) # IBugSubscriptionFilter


class IStructuralSubscriptionRestricted(Interface):
    """The restricted parts of a subscription to a Launchpad structure."""

    @export_factory_operation(Interface, [])
    def newBugFilter():
        """Returns a new `BugSubscriptionFilter` for this subscription."""

    @export_destructor_operation()
    def delete():
        """Delete this structural subscription filter."""


class IStructuralSubscription(
    IStructuralSubscriptionPublic, IStructuralSubscriptionRestricted):
    """A subscription to a Launchpad structure."""

    export_as_webservice_entry(publish_web_link=False)


class IStructuralSubscriptionTargetRead(Interface):
    """A Launchpad Structure allowing users to subscribe to it.

    Read-only parts.
    """

    @operation_returns_collection_of(IStructuralSubscription)
    @export_read_operation()
    @operation_for_version('beta')
    def getSubscriptions():
        """Return all the subscriptions with the specified levels.

        :return: A sequence of `IStructuralSubscription`.
        """

    parent_subscription_target = Attribute(
        "The target's parent, or None if one doesn't exist.")

    bug_subscriptions = Attribute(
        "All subscriptions to bugs at the METADATA level or higher.")

    def userCanAlterSubscription(subscriber, subscribed_by):
        """Check if a user can change a subscription for a person."""

    def userCanAlterBugSubscription(subscriber, subscribed_by):
        """Check if a user can change a bug subscription for a person."""

    @operation_parameters(person=Reference(schema=IPerson))
    @operation_returns_entry(IStructuralSubscription)
    @export_read_operation()
    @operation_for_version('beta')
    def getSubscription(person):
        """Return the subscription for `person`, if it exists."""

    target_type_display = Attribute("The type of the target, for display.")

    @call_with(user=REQUEST_USER)
    @export_read_operation()
    @operation_for_version('beta')
    def userHasBugSubscriptions(user):
        """Is `user` subscribed, directly or via a team, to bug mail?"""


class IStructuralSubscriptionTargetWrite(Interface):
    """A Launchpad Structure allowing users to subscribe to it.

    Modify-only parts.
    """

    def addSubscription(subscriber, subscribed_by):
        """Add a subscription for this structure.

        This method is used to create a new `IStructuralSubscription`
        for the target.

        :subscriber: The IPerson who will be subscribed. If omitted,
            subscribed_by will be used.
        :subscribed_by: The IPerson creating the subscription.
        :return: The new subscription.
        """

    @operation_parameters(
        subscriber=Reference(
            schema=IPerson,
            title=_(
                'Person to subscribe. If omitted, the requesting user will be'
                ' subscribed.'),
            required=False))
    @call_with(subscribed_by=REQUEST_USER)
    @export_factory_operation(IStructuralSubscription, [])
    @operation_for_version('beta')
    def addBugSubscription(subscriber, subscribed_by):
        """Add a bug subscription for this structure.

        This method is used to create a new `IStructuralSubscription` for the
        target.  This initially has a single filter which will allow all
        notifications will be sent.

        :subscriber: The IPerson who will be subscribed. If omitted,
            subscribed_by will be used.
        :subscribed_by: The IPerson creating the subscription.
        :return: The new bug subscription.
        """

    @operation_parameters(
        subscriber=Reference(
            schema=IPerson,
            title=_(
                'Person to subscribe. If omitted, the requesting user will be'
                ' subscribed.'),
            required=False))
    @call_with(subscribed_by=REQUEST_USER)
    @export_factory_operation(Interface, []) # Really IBugSubscriptionFilter
    @operation_for_version('beta')
    def addBugSubscriptionFilter(subscriber, subscribed_by):
        """Add a bug subscription filter for this structure.

        This method is used to create a new `IBugSubscriptionFilter` for the
        target.  It will initially allow all notifications to be sent.

        :subscriber: The IPerson who will be subscribed. If omitted,
            subscribed_by will be used.
        :subscribed_by: The IPerson creating the subscription.
        :return: The new bug subscription filter.
        """

    @operation_parameters(
        subscriber=Reference(
            schema=IPerson,
            title=_(
                'Person to unsubscribe. If omitted, the requesting user will '
                'be unsubscribed.'),
            required=False))
    @call_with(unsubscribed_by=REQUEST_USER)
    @export_write_operation()
    @operation_for_version('beta')
    def removeBugSubscription(subscriber, unsubscribed_by):
        """Remove a subscription to bugs from this structure.

        This will delete all associated filters.

        :subscriber: The IPerson who will be unsubscribed. If omitted,
            unsubscribed_by will be used.
        :unsubscribed_by: The IPerson removing the subscription.
        """


class IStructuralSubscriptionTarget(IStructuralSubscriptionTargetRead,
                                    IStructuralSubscriptionTargetWrite):
    """A Launchpad Structure allowing users to subscribe to it."""
    export_as_webservice_entry()


class IStructuralSubscriptionTargetHelper(Interface):
    """Provides information on subscribable objects."""

    target = Attribute("The target.")

    target_parent = Attribute(
        "The target's parent, or None if one doesn't exist.")

    target_type_display = Attribute(
        "The type of the target, for display.")

    target_arguments = Attribute(
        "A dict of arguments that can be used as arguments to the "
        "structural subscription constructor.")

    pillar = Attribute(
        "The pillar most closely corresponding to the context.")

    join = Attribute(
        "A Storm join to get the `IStructuralSubscription`s relating "
        "to the context.")


class IStructuralSubscriptionForm(Interface):
    """Schema for the structural subscription form."""
    subscribe_me = Bool(
        title=u"I want to receive these notifications by e-mail.",
        required=False)
