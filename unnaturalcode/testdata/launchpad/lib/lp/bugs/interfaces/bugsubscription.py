# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Bug subscription interfaces."""

__metaclass__ = type

__all__ = [
    'IBugSubscription',
    ]

from lazr.lifecycle.snapshot import doNotSnapshot
from lazr.restful.declarations import (
    call_with,
    export_as_webservice_entry,
    export_read_operation,
    exported,
    operation_for_version,
    REQUEST_USER,
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
    )

from lp import _
from lp.bugs.enums import BugNotificationLevel
from lp.services.fields import PersonChoice
from lp.services.webservice.apihelpers import patch_reference_property


class IBugSubscription(Interface):
    """The relationship between a person and a bug."""

    export_as_webservice_entry(publish_web_link=False, as_of="beta")

    id = Int(title=_('ID'), readonly=True, required=True)
    person = exported(PersonChoice(
        title=_('Person'), required=True, vocabulary='ValidPersonOrTeam',
        readonly=True, description=_("The person's Launchpad ID or "
        "e-mail address.")), as_of="beta")
    bug = exported(Reference(
        Interface, title=_("Bug"), required=True, readonly=True),
        as_of="beta")
    # We mark this as doNotSnapshot() because it's a magically-generated
    # Storm attribute and it causes Snapshot to break.
    bugID = doNotSnapshot(Int(title=u"The bug id.", readonly=True))
    bug_notification_level = exported(
        Choice(
            title=_("Bug notification level"), required=True,
            vocabulary=BugNotificationLevel,
            default=BugNotificationLevel.COMMENTS,
            description=_(
                "The volume and type of bug notifications "
                "this subscription will generate."),
            ),
        as_of="devel")
    date_created = exported(
        Datetime(title=_('Date subscribed'), required=True, readonly=True),
        as_of="beta")
    subscribed_by = exported(
        PersonChoice(
            title=_('Subscribed by'), required=True,
            vocabulary='ValidPersonOrTeam', readonly=True,
            description=_("The person who created this subscription.")),
        as_of="beta")

    display_subscribed_by = Attribute(
        "`subscribed_by` formatted for display.")

    display_duplicate_subscribed_by = Attribute(
        "duplicate bug `subscribed_by` formatted for display.")

    @call_with(user=REQUEST_USER)
    @export_read_operation()
    @operation_for_version("beta")
    def canBeUnsubscribedByUser(user):
        """Can the user unsubscribe the subscriber from the bug?"""


# In order to avoid circular dependencies, we only import
# IBug (which itself imports IBugSubscription) here, and assign it as
# the value type for the `bug` reference.
from lp.bugs.interfaces.bug import IBug
patch_reference_property(IBugSubscription, 'bug', IBug)
