# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'add_bug_change_notifications',
    'get_bug_delta',
    'notify_bug_attachment_added',
    'notify_bug_attachment_removed',
    'notify_bug_comment_added',
    'notify_bug_modified',
    'notify_bug_subscription_added',
    'send_bug_details_to_new_bug_subscribers',
    ]


import datetime

from lp.bugs.adapters.bugchange import (
    BugDuplicateChange,
    BugTaskAssigneeChange,
    get_bug_changes,
    )
from lp.bugs.adapters.bugdelta import BugDelta
from lp.bugs.enums import BugNotificationLevel
from lp.bugs.mail.bugnotificationbuilder import BugNotificationBuilder
from lp.bugs.mail.bugnotificationrecipients import BugNotificationRecipients
from lp.bugs.mail.newbug import generate_bug_add_email
from lp.bugs.model.bug import get_also_notified_subscribers
from lp.registry.interfaces.person import IPerson
from lp.services.config import config
from lp.services.database.sqlbase import block_implicit_flushes
from lp.services.mail.helpers import get_contact_email_addresses
from lp.services.mail.sendmail import (
    format_address,
    sendmail,
    )
from lp.services.webapp.publisher import canonical_url


@block_implicit_flushes
def notify_bug_modified(bug, event):
    """Handle bug change events."""
    bug_delta = get_bug_delta(
        old_bug=event.object_before_modification,
        new_bug=event.object, user=IPerson(event.user))

    if bug_delta is not None:
        add_bug_change_notifications(bug_delta)


@block_implicit_flushes
def notify_bug_comment_added(bugmessage, event):
    """Notify CC'd list that a message was added to this bug.

    bugmessage must be an IBugMessage. event must be an
    IObjectCreatedEvent. If bugmessage.bug is a duplicate the
    comment will also be sent to the dup target's subscribers.
    """
    bug = bugmessage.bug
    bug.addCommentNotification(bugmessage.message)


@block_implicit_flushes
def notify_bug_attachment_added(bugattachment, event):
    """Notify CC'd list that a new attachment has been added.

    bugattachment must be an IBugAttachment. event must be an
    IObjectCreatedEvent.
    """
    bug = bugattachment.bug
    bug_delta = BugDelta(
        bug=bug,
        bugurl=canonical_url(bug),
        user=IPerson(event.user),
        attachment={'new': bugattachment, 'old': None})

    add_bug_change_notifications(bug_delta)


@block_implicit_flushes
def notify_bug_attachment_removed(bugattachment, event):
    """Notify that an attachment has been removed."""
    bug = bugattachment.bug
    bug_delta = BugDelta(
        bug=bug,
        bugurl=canonical_url(bug),
        user=IPerson(event.user),
        attachment={'old': bugattachment, 'new': None})

    add_bug_change_notifications(bug_delta)


@block_implicit_flushes
def notify_bug_subscription_added(bug_subscription, event):
    """Notify that a new bug subscription was added."""
    # When a user is subscribed to a bug by someone other
    # than themselves, we send them a notification email.
    if bug_subscription.person != bug_subscription.subscribed_by:
        send_bug_details_to_new_bug_subscribers(
            bug_subscription.bug, [], [bug_subscription.person],
            subscribed_by=bug_subscription.subscribed_by)


def get_bug_delta(old_bug, new_bug, user):
    """Compute the delta from old_bug to new_bug.

    old_bug and new_bug are IBug's. user is an IPerson. Returns an
    IBugDelta if there are changes, or None if there were no changes.
    """
    changes = {}
    fields = ["title", "description", "name", "information_type",
        "duplicateof", "tags"]
    for field_name in fields:
        # fields for which we show old => new when their values change
        old_val = getattr(old_bug, field_name)
        new_val = getattr(new_bug, field_name)
        if old_val != new_val:
            changes[field_name] = {}
            changes[field_name]["old"] = old_val
            changes[field_name]["new"] = new_val

    if changes:
        changes["bug"] = new_bug
        changes["bug_before_modification"] = old_bug
        changes["bugurl"] = canonical_url(new_bug)
        changes["user"] = user
        return BugDelta(**changes)
    else:
        return None


def add_bug_change_notifications(bug_delta, old_bugtask=None,
                                 new_subscribers=None):
    """Generate bug notifications and add them to the bug."""
    changes = get_bug_changes(bug_delta)
    recipients = bug_delta.bug.getBugNotificationRecipients(
        level=BugNotificationLevel.METADATA)
    if old_bugtask is not None:
        old_bugtask_recipients = BugNotificationRecipients()
        get_also_notified_subscribers(
            old_bugtask, recipients=old_bugtask_recipients,
            level=BugNotificationLevel.METADATA)
        recipients.update(old_bugtask_recipients)
    for change in changes:
        bug = bug_delta.bug
        if isinstance(change, BugDuplicateChange):
            no_dupe_master_recipients = bug.getBugNotificationRecipients(
                level=change.change_level)
            bug_delta.bug.addChange(
                change, recipients=no_dupe_master_recipients)
        elif (isinstance(change, BugTaskAssigneeChange) and
              new_subscribers is not None):
            for person in new_subscribers:
                # If this change involves multiple changes, other structural
                # subscribers will leak into new_subscribers, and they may
                # not be in the recipients list, due to having a LIFECYCLE
                # structural subscription.
                if person not in recipients:
                    continue
                # We are only interested in dropping the assignee out, since
                # we send assignment notifications separately.
                reason, rationale = recipients.getReason(person)
                if 'Assignee' in rationale:
                    recipients.remove(person)
            bug_delta.bug.addChange(change, recipients=recipients)
        else:
            if change.change_level == BugNotificationLevel.LIFECYCLE:
                change_recipients = bug.getBugNotificationRecipients(
                    level=change.change_level)
                recipients.update(change_recipients)
            bug_delta.bug.addChange(change, recipients=recipients)


def send_bug_details_to_new_bug_subscribers(
    bug, previous_subscribers, current_subscribers, subscribed_by=None,
    event_creator=None):
    """Send an email containing full bug details to new bug subscribers.

    This function is designed to handle situations where bugtasks get
    reassigned to new products or sourcepackages, and the new bug subscribers
    need to be notified of the bug.

    A boolean is returned indicating whether any emails were sent.
    """
    prev_subs_set = set(previous_subscribers)
    cur_subs_set = set(current_subscribers)
    new_subs = cur_subs_set.difference(prev_subs_set)

    if (event_creator is not None
            and not event_creator.selfgenerated_bugnotifications):
        new_subs.discard(event_creator)

    to_addrs = set()
    for new_sub in new_subs:
        to_addrs.update(get_contact_email_addresses(new_sub))

    if not to_addrs:
        return False

    from_addr = format_address(
        'Launchpad Bug Tracker',
        "%s@%s" % (bug.id, config.launchpad.bugs_domain))
    # Now's a good a time as any for this email; don't use the original
    # reported date for the bug as it will just confuse mailer and
    # recipient.
    email_date = datetime.datetime.now()

    # The new subscriber email is effectively the initial message regarding
    # a new bug. The bug's initial message is used in the References
    # header to establish the message's context in the email client.
    references = [bug.initial_message.rfc822msgid]
    recipients = bug.getBugNotificationRecipients()

    bug_notification_builder = BugNotificationBuilder(bug, event_creator)
    for to_addr in sorted(to_addrs):
        reason, rationale = recipients.getReason(to_addr)
        subject, contents = generate_bug_add_email(
            bug, new_recipients=True, subscribed_by=subscribed_by,
            reason=reason, event_creator=event_creator)
        msg = bug_notification_builder.build(
            from_addr, to_addr, contents, subject, email_date,
            rationale=rationale, references=references)
        sendmail(msg)

    return True
