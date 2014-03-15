# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Base class for sending out emails."""

__metaclass__ = type

__all__ = ['BaseMailer', 'RecipientReason']

import logging
from smtplib import SMTPException

from lp.services.mail.helpers import get_email_template
from lp.services.mail.notificationrecipientset import NotificationRecipientSet
from lp.services.mail.sendmail import (
    append_footer,
    format_address,
    MailController,
    )
from lp.services.utils import text_delta


class BaseMailer:
    """Base class for notification mailers.

    Subclasses must provide getReason (or reimplement _getTemplateParameters
    or generateEmail).

    It is expected that subclasses may override _getHeaders,
    _getTemplateParams, and perhaps _getBody.
    """

    app = None

    def __init__(self, subject, template_name, recipients, from_address,
                 delta=None, message_id=None, notification_type=None,
                 mail_controller_class=None):
        """Constructor.

        :param subject: A Python dict-replacement template for the subject
            line of the email.
        :param template: Name of the template to use for the message body.
        :param recipients: A dict of recipient to Subscription.
        :param from_address: The from_address to use on emails.
        :param delta: A Delta object with members "delta_values", "interface"
            and "new_values", such as BranchMergeProposalDelta.
        :param message_id: The Message-Id to use for generated emails.  If
            not supplied, random message-ids will be used.
        :param mail_controller_class: The class of the mail controller to
            use to send the mails.  Defaults to `MailController`.
        """
        self._subject_template = subject
        self._template_name = template_name
        self._recipients = NotificationRecipientSet()
        for recipient, reason in recipients.iteritems():
            self._recipients.add(recipient, reason, reason.mail_header)
        self.from_address = from_address
        self.delta = delta
        self.message_id = message_id
        self.notification_type = notification_type
        self.logger = logging.getLogger('lp.services.mail.basemailer')
        if mail_controller_class is None:
            mail_controller_class = MailController
        self._mail_controller_class = mail_controller_class

    def _getToAddresses(self, recipient, email):
        return [format_address(recipient.displayname, email)]

    def generateEmail(self, email, recipient, force_no_attachments=False):
        """Generate the email for this recipient.

        :param email: Email address of the recipient to send to.
        :param recipient: The Person to send to.
        :return: (headers, subject, body) of the email.
        """
        to_addresses = self._getToAddresses(recipient, email)
        headers = self._getHeaders(email)
        subject = self._getSubject(email, recipient)
        body = self._getBody(email, recipient)
        ctrl = self._mail_controller_class(
            self.from_address, to_addresses, subject, body, headers,
            envelope_to=[email])
        if force_no_attachments:
            ctrl.addAttachment(
                'Excessively large attachments removed.',
                content_type='text/plain', inline=True)
        else:
            self._addAttachments(ctrl, email)
        return ctrl

    def _getSubject(self, email, recipient):
        """The subject template expanded with the template params."""
        return (self._subject_template %
                    self._getTemplateParams(email, recipient))

    def _getReplyToAddress(self):
        """Return the address to use for the reply-to header."""
        return None

    def _getHeaders(self, email):
        """Return the mail headers to use."""
        reason, rationale = self._recipients.getReason(email)
        headers = {'X-Launchpad-Message-Rationale': reason.mail_header}
        if self.notification_type is not None:
            headers['X-Launchpad-Notification-Type'] = self.notification_type
        reply_to = self._getReplyToAddress()
        if reply_to is not None:
            headers['Reply-To'] = reply_to
        if self.message_id is not None:
            headers['Message-Id'] = self.message_id
        return headers

    def _addAttachments(self, ctrl, email):
        """Add any appropriate attachments to a MailController.

        Default implementation does nothing.
        :param ctrl: The MailController to add attachments to.
        :param email: The email address of the recipient.
        """
        pass

    def _getTemplateParams(self, email, recipient):
        """Return a dict of values to use in the body and subject."""
        reason, rationale = self._recipients.getReason(email)
        params = {'reason': reason.getReason()}
        if self.delta is not None:
            params['delta'] = self.textDelta()
        return params

    def textDelta(self):
        """Return a textual version of the class delta."""
        return text_delta(self.delta, self.delta.delta_values,
            self.delta.new_values, self.delta.interface)

    def _getBody(self, email, recipient):
        """Return the complete body to use for this email."""
        template = get_email_template(self._template_name, app=self.app)
        params = self._getTemplateParams(email, recipient)
        body = template % params
        footer = self._getFooter(params)
        if footer is not None:
            body = append_footer(body, footer)
        return body

    def _getFooter(self, params):
        """Provide a footer to attach to the body, or None."""
        return None

    def sendAll(self):
        """Send notifications to all recipients."""
        # We never want SMTP errors to propagate from this function.
        for email, recipient in self._recipients.getRecipientPersons():
            try:
                ctrl = self.generateEmail(email, recipient)
                ctrl.send()
            except SMTPException as e:
                # If the initial sending failed, try again without
                # attachments.
                try:
                    ctrl = self.generateEmail(
                        email, recipient, force_no_attachments=True)
                    ctrl.send()
                except SMTPException as e:
                    # Don't want an entire stack trace, just some details.
                    self.logger.warning(
                        'send failed for %s, %s' % (email, e))


class RecipientReason:
    """Reason for sending mail to a recipient."""

    def __init__(self, subscriber, recipient, mail_header, reason_template):
        self.subscriber = subscriber
        self.recipient = recipient
        self.mail_header = mail_header
        self.reason_template = reason_template

    @staticmethod
    def makeRationale(rationale_base, person):
        if person.is_team:
            return '%s @%s' % (rationale_base, person.name)
        else:
            return rationale_base

    def _getTemplateValues(self):
        template_values = {
            'entity_is': 'You are',
            'lc_entity_is': 'you are',
            }
        if self.recipient != self.subscriber:
            assert self.recipient.hasParticipationEntryFor(self.subscriber), (
                '%s does not participate in team %s.' %
                (self.recipient.displayname, self.subscriber.displayname))
        if self.recipient != self.subscriber or self.subscriber.is_team:
            template_values['entity_is'] = (
                'Your team %s is' % self.subscriber.displayname)
            template_values['lc_entity_is'] = (
                'your team %s is' % self.subscriber.displayname)
        return template_values

    def getReason(self):
        """Return a string explaining why the recipient is a recipient."""
        return (self.reason_template % self._getTemplateValues())

    @classmethod
    def forBuildRequester(cls, requester):
        header = cls.makeRationale('Requester', requester)
        reason = '%(entity_is)s the requester of the build.'
        return cls(requester, requester, header, reason)
