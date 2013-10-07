# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'DirectoryMailBox',
    'IMailBox',
    'MailBoxError',
    'POP3MailBox',
    'TestMailBox',
    ]

import os
import poplib
import socket
import threading

from zope.interface import (
    implements,
    Interface,
    )

from lp.services.mail import stub


class MailBoxError(Exception):
    """Indicates that some went wrong while interacting with the mail box."""


class IMailBox(Interface):
    def open():
        """Opens the mail box.

        Raises MailBoxError if the mail box can't be opened.

        This method has to be called before any operations on the mail
        box is performed.
        """

    def items():
        """Returns all the ids and mails in the mail box.

        Returns an iterable of (id, mail) tuples.

        Raises MailBoxError if there's some error while returning the mails.
        """

    def delete(id):
        """Deletes the mail with the given id.

        Raises MailBoxError if the mail couldn't be deleted.
        """

    def close():
        """Closes the mailbox."""


class TestMailBox:
    """Mail box used for testing.

    It operates on stub.test_emails.
    """
    implements(IMailBox)

    def __init__(self):
        self._lock = threading.Lock()

    def open(self):
        """See IMailBox."""
        if not self._lock.acquire(False):
            raise MailBoxError("The mail box is already open.")

    def items(self):
        """See IMailBox."""
        id = 0
        # Loop over a copy of test_emails to avoid infinite loops.
        for item in list(stub.test_emails):
            if item is not None:
                from_addr, to_addr, raw_mail = item
                yield id, raw_mail
            id += 1

    def delete(self, id):
        """See IMailBox."""
        if id not in [valid_id for valid_id, mail in self.items()]:
            raise MailBoxError("No such id: %s" % id)

        # Mark it as deleted. We can't really delete it yet, since the
        # ids need to be preserved.
        stub.test_emails[id] = None

    def close(self):
        """See IMailBox."""
        # Clean up test_emails
        stub.test_emails = [item for item in stub.test_emails
                            if item is not None]
        self._lock.release()


class POP3MailBox:
    """Mail box which talks to a POP3 server."""
    implements(IMailBox)

    def __init__(self, host, user, password, ssl=False):
        self._host = host
        self._user = user
        self._password = password
        self._ssl = ssl

    def open(self):
        """See IMailBox."""
        try:
            if self._ssl:
                popbox = poplib.POP3_SSL(self._host)
            else:
                popbox = poplib.POP3(self._host)
        except socket.error as e:
            raise MailBoxError(str(e))
        try:
            popbox.user(self._user)
            popbox.pass_(self._password)
        except poplib.error_proto as e:
            popbox.quit()
            raise MailBoxError(str(e))
        self._popbox = popbox

    def items(self):
        """See IMailBox."""
        popbox = self._popbox
        try:
            count, size = popbox.stat()
        except poplib.error_proto as e:
            # This means we lost the connection.
            raise MailBoxError(str(e))

        for msg_id in range(1, count + 1):
            response, msg_lines, size = popbox.retr(msg_id)
            yield (msg_id, '\n'.join(msg_lines))

    def delete(self, id):
        """See IMailBox."""
        try:
            self._popbox.dele(id)
        except poplib.error_proto as e:
            raise MailBoxError(str(e))

    def close(self):
        """See IMailBox."""
        self._popbox.quit()


class DirectoryMailBox:
    """Mail box which reads files from a directory."""
    implements(IMailBox)

    def __init__(self, directory):
        self.mail_dir = os.path.abspath(directory)

    def open(self):
        """See IMailBox."""
        # No-op.

    def items(self):
        """See IMailBox."""
        for name in os.listdir(self.mail_dir):
            filename = os.path.join(self.mail_dir, name)
            if os.path.isfile(filename):
                yield (filename, open(filename).read())

    def delete(self, id):
        """See IMailBox."""
        if not os.path.isfile(id):
            raise MailBoxError("No such id: %s" % id)
        if not os.path.abspath(id).startswith(self.mail_dir):
            raise MailBoxError("No such id: %s" % id)
        os.remove(id)

    def close(self):
        """See IMailBox."""
        # No-op.
