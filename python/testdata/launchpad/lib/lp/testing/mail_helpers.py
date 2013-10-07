# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Helper functions dealing with emails in tests.
"""
__metaclass__ = type

import email
import operator

import transaction
from zope.component import getUtility

from lp.registry.interfaces.persontransferjob import (
    IMembershipNotificationJobSource,
    )
from lp.services.job.runner import JobRunner
from lp.services.log.logger import DevNullLogger
from lp.services.mail import stub


def pop_notifications(sort_key=None, commit=True):
    """Return generated emails as email messages.

    A helper function which optionally commits the transaction, so
    that the notifications are queued in stub.test_emails and pops these
    notifications from the queue.

    :param sort_key: define sorting function.  sort_key specifies a
    function of one argument that is used to extract a comparison key from
    each list element.  (See the sorted() Python built-in.)
    :param commit: whether to commit before reading email (defaults to True).
    """
    if commit:
        transaction.commit()
    if sort_key is None:
        sort_key = operator.itemgetter('To')

    notifications = []
    for fromaddr, toaddrs, raw_message in stub.test_emails:
        notification = email.message_from_string(raw_message)
        notification['X-Envelope-To'] = ', '.join(toaddrs)
        notification['X-Envelope-From'] = fromaddr
        notifications.append(notification)
    stub.test_emails = []

    return sorted(notifications, key=sort_key)


def sort_addresses(header):
    """Sort an address-list in an e-mail header field body."""
    addresses = set(address.strip() for address in header.split(','))
    return ", ".join(sorted(addresses))


def print_emails(include_reply_to=False, group_similar=False,
                 include_rationale=False, notifications=None):
    """Pop all messages from stub.test_emails and print them with
     their recipients.

    Since the same message may be sent more than once (for different
    recipients), setting 'group_similar' will print each distinct
    message only once and group all recipients of that message
    together in the 'To:' field.  It will also strip the first line of
    the email body.  (The line with "Hello Foo," which is likely
    distinct for each recipient.)

    :param include_reply_to: Include the reply-to header if True.
    :param group_similar: Group messages sent to multiple recipients if True.
    :param include_rationale: Include the X-Launchpad-Message-Rationale
        header.
    :param notifications: Use the provided list of notifications instead of
        the stack.
    """
    distinct_bodies = {}
    if notifications is None:
        notifications = pop_notifications()
    for message in notifications:
        recipients = set(
            recipient.strip()
            for recipient in message['To'].split(','))
        body = message.get_payload()
        if group_similar:
            # Strip the first line as it's different for each recipient.
            body = body[body.find('\n') + 1:]
        if body in distinct_bodies and group_similar:
            message, existing_recipients = distinct_bodies[body]
            distinct_bodies[body] = (
                message, existing_recipients.union(recipients))
        else:
            distinct_bodies[body] = (message, recipients)
    for body in sorted(distinct_bodies):
        message, recipients = distinct_bodies[body]
        print 'From:', message['From']
        print 'To:', ", ".join(sorted(recipients))
        if include_reply_to:
            print 'Reply-To:', message['Reply-To']
        rationale_header = 'X-Launchpad-Message-Rationale'
        if include_rationale and rationale_header in message:
            print (
                '%s: %s' % (rationale_header, message[rationale_header]))
        print 'Subject:', message['Subject']
        print body
        print "-" * 40


def print_distinct_emails(include_reply_to=False, include_rationale=True):
    """A convenient shortcut for `print_emails`(group_similar=True)."""
    return print_emails(group_similar=True,
                        include_reply_to=include_reply_to,
                        include_rationale=include_rationale)


def run_mail_jobs():
    """Process job queues that send out emails.

    If a new job type is added that sends emails, this function can be
    extended to run those jobs, so that testing emails doesn't require a
    bunch of different function calls to process different queues.
    """
    # Commit the transaction to make sure that the JobRunner can find
    # the queued jobs.
    transaction.commit()
    job_source = getUtility(IMembershipNotificationJobSource)
    logger = DevNullLogger()
    runner = JobRunner.fromReady(job_source, logger)
    runner.runAll()
