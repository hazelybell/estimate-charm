# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Functions related to sending bug notifications."""

__metaclass__ = type

__all__ = [
    "construct_email_notifications",
    "get_email_notifications",
    "process_deferred_notifications",
    ]

from itertools import groupby
from operator import itemgetter

from storm.store import Store
import transaction
from zope.component import getUtility

from lp.bugs.enums import BugNotificationLevel
from lp.bugs.interfaces.bugnotification import IBugNotificationSet
from lp.bugs.mail.bugnotificationbuilder import (
    BugNotificationBuilder,
    get_bugmail_from_address,
    )
from lp.bugs.mail.newbug import generate_bug_add_email
from lp.registry.model.person import get_recipients
from lp.services.mail.helpers import get_email_template
from lp.services.mail.mailwrapper import MailWrapper
from lp.services.scripts.logger import log
from lp.services.webapp import canonical_url


def get_activity_key(notification):
    """Given a notification, return a key for the activity if it exists.

    The key will be used to determine whether changes for the activity are
    undone within the same batch of notifications (which are supposed to
    be all for the same bug when they get to this function).  Therefore,
    the activity's attribute is a good start for the key.

    If the activity was on a bugtask, we will also want to distinguish
    by bugtask, because, for instance, changing a status from INPROGRESS
    to FIXCOMMITED on one bug task is not undone if the status changes
    from FIXCOMMITTED to INPROGRESS on another bugtask.

    Similarly, if the activity is about adding or removing something
    that we can have multiple of, like a branch or an attachment, the
    key should include information on that value, because adding one
    attachment is not undone by removing another one.
    """
    activity = notification.activity
    if activity is not None:
        key = activity.attribute
        if activity.target is not None:
            key = ':'.join((activity.target, key))
        if key in ('attachments', 'watches', 'cves', 'linked_branches'):
            # We are intentionally leaving bug task bugwatches out of this
            # list, so we use the key rather than the activity.attribute.
            if activity.oldvalue is not None:
                key = ':'.join((key, activity.oldvalue))
            elif activity.newvalue is not None:
                key = ':'.join((key, activity.newvalue))
        return key


def construct_email_notifications(bug_notifications):
    """Construct an email from a list of related bug notifications.

    The person and bug has to be the same for all notifications, and
    there can be only one comment.
    """
    first_notification = bug_notifications[0]
    bug = first_notification.bug
    actor = first_notification.message.owner
    subject = first_notification.message.subject

    comment = None
    references = []
    text_notifications = []
    old_values = {}
    new_values = {}

    for notification in bug_notifications:
        assert notification.bug == bug, bug.id
        assert notification.message.owner == actor, actor.id
        if notification.is_comment:
            assert comment is None, (
                "Only one of the notifications is allowed to be a comment.")
            comment = notification.message
        else:
            key = get_activity_key(notification)
            if key is not None:
                if key not in old_values:
                    old_values[key] = notification.activity.oldvalue
                new_values[key] = notification.activity.newvalue

    recipients = {}
    filtered_notifications = []
    omitted_notifications = []
    for notification in bug_notifications:
        key = get_activity_key(notification)
        if (notification.is_comment or
            key is None or
            key == 'removed_subscriber' or
            old_values[key] != new_values[key]):
            # We will report this notification.
            filtered_notifications.append(notification)
            for subscription_source in notification.recipients:
                for recipient in get_recipients(
                    subscription_source.person):
                    # The subscription_source.person may be a person or a
                    # team.  The get_recipients function gives us everyone
                    # who should actually get an email for that person.
                    # If subscription_source.person is a person or a team
                    # with a preferred email address, then the people to
                    # be emailed will only be subscription_source.person.
                    # However, if it is a team without a preferred email
                    # address, then this list will be the people and teams
                    # that comprise the team, transitively, stopping the walk
                    # at each person and at each team with a preferred email
                    # address.
                    sources_for_person = recipients.get(recipient)
                    if sources_for_person is None:
                        sources_for_person = []
                        recipients[recipient] = sources_for_person
                    sources_for_person.append(subscription_source)
        else:
            omitted_notifications.append(notification)

    # If the actor does not want self-generated bug notifications, remove the
    # actor now.
    if not actor.selfgenerated_bugnotifications:
        recipients.pop(actor, None)

    if bug.duplicateof is not None:
        text_notifications.append(
            '*** This bug is a duplicate of bug %d ***\n    %s' %
                (bug.duplicateof.id, canonical_url(bug.duplicateof)))

    if comment is not None:
        if comment == bug.initial_message:
            subject, text = generate_bug_add_email(bug)
        else:
            text = comment.text_contents
        text_notifications.append(text)

        msgid = comment.rfc822msgid
        email_date = comment.datecreated

        reference = comment.parent
        while reference is not None:
            references.insert(0, reference.rfc822msgid)
            reference = reference.parent
    else:
        msgid = first_notification.message.rfc822msgid
        email_date = first_notification.message.datecreated

    for notification in filtered_notifications:
        if notification.message == comment:
            # Comments were just handled in the previous if block.
            continue
        text = notification.message.text_contents.rstrip()
        text_notifications.append(text)

    if bug.initial_message.rfc822msgid not in references:
        # Ensure that references contain the initial message ID
        references.insert(0, bug.initial_message.rfc822msgid)

    # At this point we've got the data we need to construct the
    # messages. Now go ahead and actually do that.
    messages = []
    mail_wrapper = MailWrapper(width=72)
    content = '\n\n'.join(text_notifications)
    from_address = get_bugmail_from_address(actor, bug)
    bug_notification_builder = BugNotificationBuilder(bug, actor)
    recipients = getUtility(IBugNotificationSet).getRecipientFilterData(
        bug, recipients, filtered_notifications)
    sorted_recipients = sorted(
        recipients.items(), key=lambda t: t[0].preferredemail.email)

    for email_person, data in sorted_recipients:
        address = str(email_person.preferredemail.email)
        # Choosing the first source is a bit arbitrary, but it
        # is simple for the user to understand.  We may want to reconsider
        # this in the future.
        reason = data['sources'][0].reason_body
        rationale = data['sources'][0].reason_header

        if data['filter descriptions']:
            # There are some filter descriptions as well. Add them to
            # the email body.
            filters_text = u"\nMatching subscriptions: %s" % ", ".join(
                data['filter descriptions'])
        else:
            filters_text = u""

        # In the rare case of a bug with no bugtasks, we can't generate the
        # subscription management URL so just leave off the subscription
        # management message entirely.
        if len(bug.bugtasks):
            bug_url = canonical_url(bug.bugtasks[0])
            notification_url = bug_url + '/+subscriptions'
            subscriptions_message = (
                "To manage notifications about this bug go to:\n%s"
                % notification_url)
        else:
            subscriptions_message = ''

        data_wrapper = MailWrapper(width=72, indent='  ')
        body_data = {
            'content': mail_wrapper.format(content),
            'bug_title': data_wrapper.format(bug.title),
            'bug_url': canonical_url(bug),
            'notification_rationale': mail_wrapper.format(reason),
            'subscription_filters': filters_text,
            'subscriptions_message': subscriptions_message,
            }

        # If the person we're sending to receives verbose notifications
        # we include the description and status of the bug in the email
        # footer.
        if email_person.verbose_bugnotifications:
            email_template = 'bug-notification-verbose.txt'
            body_data['bug_description'] = data_wrapper.format(
                bug.description)

            status_base = "Status in %s:\n  %s"
            status_strings = []
            for bug_task in bug.bugtasks:
                status_strings.append(status_base % (bug_task.target.title,
                    bug_task.status.title))

            body_data['bug_statuses'] = "\n".join(status_strings)
        else:
            email_template = 'bug-notification.txt'

        body_template = get_email_template(email_template, 'bugs')
        body = (body_template % body_data).strip()
        msg = bug_notification_builder.build(
            from_address, address, body, subject, email_date,
            rationale, references, msgid, filters=data['filter descriptions'])
        messages.append(msg)

    return filtered_notifications, omitted_notifications, messages


def notification_comment_batches(notifications):
    """Search `notification` for continuous spans with only one comment.

    Generates `comment_group, notification` tuples.

    The notifications are searched in order for continuous spans containing
    only one comment. Each continous span is given a unique number. Each
    notification is yielded along with its span number.
    """
    comment_count = 0
    for notification in notifications:
        if notification.is_comment:
            comment_count += 1
        # Everything before the 2nd comment is in the first comment group.
        yield comment_count or 1, notification


def get_bug_and_owner(notification):
    """Retrieve `notification`'s `bug` and `message.owner` attributes."""
    return notification.bug, notification.message.owner


def notification_batches(notifications):
    """Batch notifications for `get_email_notifications`."""
    notifications_grouped = groupby(notifications, get_bug_and_owner)
    for (bug, person), notification_group in notifications_grouped:
        batches = notification_comment_batches(notification_group)
        for comment_group, batch in groupby(batches, itemgetter(0)):
            yield [notification for (comment_group, notification) in batch]


def get_email_notifications(bug_notifications):
    """Return the email notifications pending to be sent.

    The intention of this code is to ensure that as many notifications
    as possible are batched into a single email. The criteria is that
    the notifications:
        - Must share the same owner.
        - Must be related to the same bug.
        - Must contain at most one comment.
    """
    for batch in notification_batches(bug_notifications):
        # We don't want bugs preventing all bug notifications from
        # being sent, so catch and log all exceptions.
        try:
            yield construct_email_notifications(batch)
        except (KeyboardInterrupt, SystemExit, GeneratorExit):
            raise
        except:
            log.exception("Error while building email notifications.")
            transaction.abort()
            transaction.begin()


def process_deferred_notifications(bug_notifications):
    """Transform deferred notifications into real ones.

    Deferred notifications must have their recipients list calculated and then
    re-inserted as real notifications.
    """
    bug_notification_set = getUtility(IBugNotificationSet)
    for notification in bug_notifications:
        # Construct the real notification with recipients.
        bug = notification.bug
        recipients = bug.getBugNotificationRecipients(
            level=BugNotificationLevel.LIFECYCLE)
        message = notification.message
        is_comment = notification.is_comment
        activity = notification.activity
        # Remove the deferred notification.
        # Is activity affected?
        store = Store.of(notification)
        notification.destroySelf()
        store.flush()
        bug_notification_set.addNotification(
            bug=bug,
            is_comment=is_comment,
            message=message,
            recipients=recipients,
            activity=activity)
