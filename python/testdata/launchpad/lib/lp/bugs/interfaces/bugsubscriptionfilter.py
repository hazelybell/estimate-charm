# Copyright 2010-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Bug subscription filter interfaces."""

__metaclass__ = type
__all__ = [
    "IBugSubscriptionFilter",
    "IBugSubscriptionFilterMute",
    ]

from lazr.restful.declarations import (
    call_with,
    export_as_webservice_entry,
    export_destructor_operation,
    export_read_operation,
    export_write_operation,
    exported,
    operation_for_version,
    REQUEST_USER,
    )
from lazr.restful.fields import Reference
from zope.interface import Interface
from zope.schema import (
    Bool,
    Choice,
    Datetime,
    FrozenSet,
    Int,
    Text,
    )

from lp import _
from lp.app.enums import InformationType
from lp.bugs.enums import BugNotificationLevel
from lp.bugs.interfaces.bugtask import (
    BugTaskImportance,
    BugTaskStatus,
    )
from lp.bugs.interfaces.structuralsubscription import IStructuralSubscription
from lp.services.fields import (
    PersonChoice,
    SearchTag,
    )


class IBugSubscriptionFilterAttributes(Interface):
    """Attributes of `IBugSubscriptionFilter`."""

    id = Int(required=True, readonly=True)

    structural_subscription = exported(
        Reference(
            IStructuralSubscription,
            title=_("Structural subscription"),
            required=True, readonly=True))

    find_all_tags = exported(
        Bool(
            title=_("Find all tags"),
            description=_(
                "If enabled, all tags must match, "
                "else at least one tag must match."),
            required=True, default=False))
    include_any_tags = Bool(
        title=_("Include any tags"),
        required=True, default=False)
    exclude_any_tags = Bool(
        title=_("Exclude all tags"),
        required=True, default=False)
    bug_notification_level = exported(
        Choice(
            title=_("Bug notification level"), required=True,
            vocabulary=BugNotificationLevel,
            default=BugNotificationLevel.COMMENTS,
            description=_("The volume and type of bug notifications "
                          "this subscription will generate.")))

    description = exported(
        Text(
            title=_("A short description of this filter"),
            required=False))

    statuses = exported(
        FrozenSet(
            title=_("The statuses interested in (empty for all)"),
            required=True, default=frozenset(),
            value_type=Choice(
                title=_('Status'), vocabulary=BugTaskStatus)))

    importances = exported(
        FrozenSet(
            title=_("The importances interested in (empty for all)"),
            required=True, default=frozenset(),
            value_type=Choice(
                title=_('Importance'), vocabulary=BugTaskImportance)))

    tags = exported(
        FrozenSet(
            title=_("The tags interested in"),
            required=True, default=frozenset(),
            value_type=SearchTag()))

    information_types = exported(
        FrozenSet(
            title=_("The information types interested in (empty for all)"),
            required=True, default=frozenset(),
            value_type=Choice(
                title=_('Information type'), vocabulary=InformationType)))


class IBugSubscriptionFilterMethodsPublic(Interface):
    """Methods on `IBugSubscriptionFilter` that can be called by anyone."""

    @call_with(person=REQUEST_USER)
    @export_read_operation()
    @operation_for_version('devel')
    def isMuteAllowed(person):
        """Return True if this filter can be muted for `person`."""

    @call_with(person=REQUEST_USER)
    @export_read_operation()
    @operation_for_version('devel')
    def muted(person):
        """Return date muted if this filter was muted for `person`, or None.
        """

    @call_with(person=REQUEST_USER)
    @export_write_operation()
    @operation_for_version('devel')
    def mute(person):
        """Add a mute for `person` to this filter."""

    @call_with(person=REQUEST_USER)
    @export_write_operation()
    @operation_for_version('devel')
    def unmute(person):
        """Remove any mute for `person` to this filter."""


class IBugSubscriptionFilterMethodsProtected(Interface):
    """Methods of `IBugSubscriptionFilter` that require launchpad.Edit."""

    @export_destructor_operation()
    def delete():
        """Delete this bug subscription filter.

        If it is the last filter in the structural subscription, delete the
        structural subscription."""


class IBugSubscriptionFilter(
    IBugSubscriptionFilterAttributes, IBugSubscriptionFilterMethodsProtected,
    IBugSubscriptionFilterMethodsPublic):
    """A bug subscription filter."""
    export_as_webservice_entry()


class IBugSubscriptionFilterMute(Interface):
    """A mute on an IBugSubscriptionFilter."""

    person = PersonChoice(
        title=_('Person'), required=True, vocabulary='ValidPersonOrTeam',
        readonly=True, description=_("The person subscribed."))
    filter = Reference(
        IBugSubscriptionFilter, title=_("Subscription filter"),
        required=True, readonly=True,
        description=_("The subscription filter to be muted."))
    date_created = Datetime(
        title=_("The date on which the mute was created."), required=False,
        readonly=True)
