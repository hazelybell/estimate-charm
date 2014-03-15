# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
"""Event handlers that send email notifications."""

__metaclass__ = type
__all__ = [
    'send_process_error_notification',
    'get_unified_diff',
    ]


from difflib import unified_diff
from email import message_from_string
from email.MIMEMessage import MIMEMessage
from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText
import re

from lp.bugs.mail.bugnotificationbuilder import get_bugmail_error_address
from lp.services.config import config
from lp.services.mail.helpers import get_email_template
from lp.services.mail.mailwrapper import MailWrapper
from lp.services.mail.sendmail import sendmail


CC = "CC"
MAX_RETURN_MESSAGE_SIZE = config.processmail.max_error_message_return_size


def send_process_error_notification(to_address, subject, error_msg,
                                    original_msg, failing_command=None,
                                    max_return_size=MAX_RETURN_MESSAGE_SIZE):
    """Send a mail about an error occurring while using the email interface.

    Tells the user that an error was encountered while processing his
    request and attaches the original email which caused the error to
    happen.  The original message will be truncated to
    max_return_size bytes.

        :to_address: The address to send the notification to.
        :subject: The subject of the notification.
        :error_msg: The error message that explains the error.
        :original_msg: The original message sent by the user.
        :failing_command: The command that caused the error to happen.
        :max_return_size: The maximum size returned for the original message.
    """
    if isinstance(failing_command, list):
        failing_commands = failing_command
    elif failing_command is None:
        failing_commands = []
    else:
        failing_commands = [failing_command]
    failed_commands_information = ''
    if len(failing_commands) > 0:
        failed_commands_information = 'Failing command:'
        for failing_command in failing_commands:
            failed_commands_information += '\n    %s' % str(failing_command)

    body = get_email_template(
        'email-processing-error.txt', app='services/mail') % {
            'failed_command_information': failed_commands_information,
            'error_msg': error_msg}
    mailwrapper = MailWrapper(width=72)
    body = mailwrapper.format(body)
    error_part = MIMEText(body.encode('utf-8'), 'plain', 'utf-8')

    msg = MIMEMultipart()
    msg['To'] = to_address
    msg['From'] = get_bugmail_error_address()
    msg['Subject'] = subject
    msg.attach(error_part)
    original_msg_str = str(original_msg)
    if len(original_msg_str) > max_return_size:
        truncated_msg_str = original_msg_str[:max_return_size]
        original_msg = message_from_string(truncated_msg_str)
    msg.attach(MIMEMessage(original_msg))
    sendmail(msg)


def get_unified_diff(old_text, new_text, text_width):
    r"""Return a unified diff of the two texts.

    Before the diff is produced, the texts are wrapped to the given text
    width.

        >>> print get_unified_diff(
        ...     'Some text\nAnother line\n',get_un
        ...     'Some more text\nAnother line\n',
        ...     text_width=72)
        - Some text
        + Some more text
          Another line

    """
    mailwrapper = MailWrapper(width=72)
    old_text_wrapped = mailwrapper.format(old_text or '')
    new_text_wrapped = mailwrapper.format(new_text or '')

    lines_of_context = len(old_text_wrapped.splitlines())
    text_diff = unified_diff(
        old_text_wrapped.splitlines(),
        new_text_wrapped.splitlines(),
        n=lines_of_context)
    # Remove the diff header, which consists of the first three
    # lines.
    text_diff = list(text_diff)[3:]
    # Let's simplify the diff output by removing the helper lines,
    # which begin with '?'.
    text_diff = [
        diff_line for diff_line in text_diff
        if not diff_line.startswith('?')]
    # Add a whitespace between the +/- and the text line.
    text_diff = [
        re.sub('^([\+\- ])(.*)', r'\1 \2', line)
        for line in text_diff]
    text_diff = '\n'.join(text_diff)
    return text_diff
