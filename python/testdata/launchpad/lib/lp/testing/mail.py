# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Useful helper functions used for testing."""

__metaclass__ = type

from email.Utils import formatdate
import os

from zope.component import getUtility

from lp.services.mail.mailbox import IMailBox
from lp.services.mail.sendmail import (
    get_msgid,
    MailController,
    )


def create_mail_for_directoryMailBox(from_addr, to_addrs, subject, body,
                                     headers=None):
    """Create a email in the DirectoryMailBox."""
    mc = MailController(from_addr, to_addrs, subject, body, headers)
    message = mc.makeMessage()
    if 'message-id' not in message:
        message['Message-Id'] = get_msgid()
    if 'date' not in message:
        message['Date'] = formatdate()
    # Since this is faking incoming email, set the X-Original-To.
    message['X-Original-To'] = to_addrs
    mailbox = getUtility(IMailBox)
    msg_file = open(
        os.path.join(mailbox.mail_dir, message['Message-Id']), 'w')
    msg_file.write(message.as_string())
    msg_file.close()
