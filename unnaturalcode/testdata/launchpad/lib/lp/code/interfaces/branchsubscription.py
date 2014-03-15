# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Bug subscription interfaces."""

__metaclass__ = type

__all__ = [
    'IBranchSubscription',
    ]

from lazr.restful.declarations import (
    call_with,
    export_as_webservice_entry,
    export_read_operation,
    exported,
    REQUEST_USER,
    )
from lazr.restful.fields import Reference
from zope.interface import Interface
from zope.schema import (
    Choice,
    Int,
    )

from lp import _
from lp.code.enums import (
    BranchSubscriptionDiffSize,
    BranchSubscriptionNotificationLevel,
    CodeReviewNotificationLevel,
    )
from lp.code.interfaces.branch import IBranch
from lp.services.fields import PersonChoice


class IBranchSubscription(Interface):
    """The relationship between a person and a branch."""
    export_as_webservice_entry()

    id = Int(title=_('ID'), readonly=True, required=True)
    personID = Int(title=_('Person ID'), required=True, readonly=True)
    person = exported(
        PersonChoice(
            title=_('Person'), required=True, vocabulary='ValidPersonOrTeam',
            readonly=True, description=_('Enter the launchpad id, or email '
            'address of the person you wish to subscribe to this branch. '
            'If you are unsure, use the "Choose..." option to find the '
            'person in Launchpad. You can only subscribe someone who is '
            'a registered user of the system.')))
    branch = exported(
        Reference(
            title=_('Branch ID'), required=True, readonly=True,
            schema=IBranch))
    notification_level = exported(
        Choice(
            title=_('Notification Level'), required=True,
            vocabulary=BranchSubscriptionNotificationLevel,
            default=BranchSubscriptionNotificationLevel.ATTRIBUTEONLY,
            description=_(
                'Attribute notifications are sent when branch details are '
                'changed such as lifecycle status and name.  Revision '
                'notifications are generated when new branch revisions are '
                'found due to the branch being updated through either pushes '
                'to the hosted branches or the mirrored branches being '
                'updated.')))
    max_diff_lines = exported(
        Choice(
            title=_('Generated Diff Size Limit'), required=True,
            vocabulary=BranchSubscriptionDiffSize,
            default=BranchSubscriptionDiffSize.ONEKLINES,
            description=_(
                'Diffs greater than the specified number of lines will not '
                'be sent to the subscriber.  The subscriber will still '
                'receive an email with the new revision details even if the '
                'diff is larger than the specified number of lines.')))
    review_level = exported(
        Choice(
            title=_('Code review Level'), required=True,
            vocabulary=CodeReviewNotificationLevel,
            default=CodeReviewNotificationLevel.FULL,
            description=_(
                'Control the kind of review activity that triggers '
                'notifications.'
                )))

    subscribed_by = exported(PersonChoice(
        title=_('Subscribed by'), required=True,
        vocabulary='ValidPersonOrTeam', readonly=True,
        description=_("The person who created this subscription.")))

    @call_with(user=REQUEST_USER)
    @export_read_operation()
    def canBeUnsubscribedByUser(user):
        """Can the user unsubscribe the subscriber from the branch?"""
