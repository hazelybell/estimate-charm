# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
"""Event handlers that send email notifications."""

__metaclass__ = type

from lp.blueprints.interfaces.specification import ISpecification
from lp.registry.interfaces.person import IPerson
from lp.services.database.sqlbase import block_implicit_flushes
from lp.services.mail.helpers import (
    get_contact_email_addresses,
    get_email_template,
    )
from lp.services.mail.mailwrapper import MailWrapper
from lp.services.mail.notification import get_unified_diff
from lp.services.mail.sendmail import simple_sendmail_from_person
from lp.services.webapp.publisher import canonical_url


def specification_notification_subject(spec):
    """Format the email subject line for a specification."""
    return '[Blueprint %s] %s' % (spec.name, spec.title)


def notify_specification_modified(spec, event):
    """Notify the related people that a specification has been modifed."""
    user = IPerson(event.user)
    spec_delta = spec.getDelta(event.object_before_modification, user)
    if spec_delta is None:
        # XXX: Bjorn Tillenius 2006-03-08:
        #      Ideally, if an IObjectModifiedEvent event is generated,
        #      spec_delta shouldn't be None. I'm not confident that we
        #      have enough test yet to assert this, though.
        return

    subject = specification_notification_subject(spec)
    indent = ' ' * 4
    info_lines = []
    if spec_delta.name:
        info_lines.append('%sName: %s => %s' % (
            indent, spec_delta.name['old'], spec_delta.name['new']))
    for dbitem_name in ('definition_status', 'priority'):
        title = ISpecification[dbitem_name].title
        assert ISpecification[dbitem_name].required, (
            "The mail notification assumes %s can't be None" % dbitem_name)
        dbitem_delta = getattr(spec_delta, dbitem_name)
        if dbitem_delta is not None:
            old_item = dbitem_delta['old']
            new_item = dbitem_delta['new']
            info_lines.append("%s%s: %s => %s" % (
                indent, title, old_item.title, new_item.title))

    for person_attrname in ('approver', 'assignee', 'drafter'):
        title = ISpecification[person_attrname].title
        person_delta = getattr(spec_delta, person_attrname)
        if person_delta is not None:
            old_person = person_delta['old']
            if old_person is None:
                old_value = "(none)"
            else:
                old_value = old_person.displayname
            new_person = person_delta['new']
            if new_person is None:
                new_value = "(none)"
            else:
                new_value = new_person.displayname
            info_lines.append(
                "%s%s: %s => %s" % (indent, title, old_value, new_value))

    mail_wrapper = MailWrapper(width=72)
    if spec_delta.whiteboard is not None:
        if info_lines:
            info_lines.append('')
        whiteboard_delta = spec_delta.whiteboard
        if whiteboard_delta['old'] is None:
            info_lines.append('Whiteboard set to:')
            info_lines.append(mail_wrapper.format(whiteboard_delta['new']))
        else:
            whiteboard_diff = get_unified_diff(
                whiteboard_delta['old'], whiteboard_delta['new'], 72)
            info_lines.append('Whiteboard changed:')
            info_lines.append(whiteboard_diff)
    if spec_delta.workitems_text is not None:
        if info_lines:
            info_lines.append('')
        workitems_delta = spec_delta.workitems_text
        if workitems_delta['old'] is '':
            info_lines.append('Work items set to:')
            info_lines.append(mail_wrapper.format(workitems_delta['new']))
        else:
            workitems_diff = get_unified_diff(
                workitems_delta['old'], workitems_delta['new'], 72)
            info_lines.append('Work items changed:')
            info_lines.append(workitems_diff)
    if not info_lines:
        # The specification was modified, but we don't yet support
        # sending notification for the change.
        return
    body = get_email_template('specification-modified.txt', 'blueprints') % {
        'editor': user.displayname,
        'info_fields': '\n'.join(info_lines),
        'spec_title': spec.title,
        'spec_url': canonical_url(spec)}

    for address in spec.notificationRecipientAddresses():
        simple_sendmail_from_person(user, address, subject, body)


@block_implicit_flushes
def notify_specification_subscription_created(specsub, event):
    """Notify a user that they have been subscribed to a blueprint."""
    user = IPerson(event.user)
    spec = specsub.specification
    person = specsub.person
    subject = specification_notification_subject(spec)
    mailwrapper = MailWrapper(width=72)
    body = mailwrapper.format(
        'You are now subscribed to the blueprint '
        '%(blueprint_name)s - %(blueprint_title)s.\n\n'
        '-- \n%(blueprint_url)s' %
        {'blueprint_name': spec.name,
         'blueprint_title': spec.title,
         'blueprint_url': canonical_url(spec)})
    for address in get_contact_email_addresses(person):
        simple_sendmail_from_person(user, address, subject, body)


@block_implicit_flushes
def notify_specification_subscription_modified(specsub, event):
    """Notify a subscriber to a blueprint that their
    subscription has changed.
    """
    user = IPerson(event.user)
    spec = specsub.specification
    person = specsub.person
    # Only send a notification if the
    # subscription changed by someone else.
    if person == user:
        return
    subject = specification_notification_subject(spec)
    if specsub.essential:
        specsub_type = 'Participation essential'
    else:
        specsub_type = 'Participation non-essential'
    mailwrapper = MailWrapper(width=72)
    body = mailwrapper.format(
        'Your subscription to the blueprint '
        '%(blueprint_name)s - %(blueprint_title)s '
        'has changed to [%(specsub_type)s].\n\n'
        '--\n  %(blueprint_url)s' %
        {'blueprint_name': spec.name,
         'blueprint_title': spec.title,
         'specsub_type': specsub_type,
         'blueprint_url': canonical_url(spec)})
    for address in get_contact_email_addresses(person):
        simple_sendmail_from_person(user, address, subject, body)
