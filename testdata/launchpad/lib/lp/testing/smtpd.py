# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""SMTP test helper."""


__metaclass__ = type
__all__ = [
    'SMTPController',
    ]


import fcntl
import logging
import Queue as queue

from lazr.smtptest.controller import QueueController
from lazr.smtptest.server import QueueServer


log = logging.getLogger('lazr.smtptest')


class SMTPServer(QueueServer):
    """SMTP server which knows about Launchpad test specifics."""

    def handle_message(self, message):
        """See `QueueServer.handle_message()`."""
        message_id = message.get('message-id', 'n/a')
        log.debug('msgid: %s, to: %s, beenthere: %s, from: %s, rcpt: %s',
                  message_id, message['to'],
                  message['x-beenthere'],
                  message['x-mailfrom'], message['x-rcptto'])
        self.queue.put(message)

    def reset(self):
        # Base class is old-style.
        QueueServer.reset(self)
        # Consume everything out of the queue.
        while True:
            try:
                self.queue.get_nowait()
            except queue.Empty:
                break


class SMTPController(QueueController):
    """A controller for the `SMTPServer`."""

    def _make_server(self, host, port):
        """See `QueueController`."""
        self.server = SMTPServer(host, port, self.queue)
        # Set FD_CLOEXEC on the port's file descriptor, so that forked
        # processes like uuidd won't steal the port.
        flags = fcntl.fcntl(self.server._fileno, fcntl.F_GETFD)
        flags |= fcntl.FD_CLOEXEC
        fcntl.fcntl(self.server._fileno, fcntl.F_SETFD, flags)
