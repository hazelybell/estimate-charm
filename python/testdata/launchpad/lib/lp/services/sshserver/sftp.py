# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Generic SFTP server functionality."""

__metaclass__ = type
__all__ = [
    'FileIsADirectory',
    'FileTransferServer',
    ]

from bzrlib import errors as bzr_errors
from twisted.conch.ssh import filetransfer
from zope.event import notify

from lp.services.sshserver import events


class FileIsADirectory(bzr_errors.PathError):
    """Raised when writeChunk is called on a directory.

    This exists mainly to be translated into the appropriate SFTP error.
    """

    _fmt = 'File is a directory: %(path)r%(extra)s'


class FileTransferServer(filetransfer.FileTransferServer):
    """SFTP protocol implementation that logs key events."""

    def __init__(self, data=None, avatar=None):
        filetransfer.FileTransferServer.__init__(self, data, avatar)
        notify(events.SFTPStarted(avatar))
        self.avatar = avatar

    def connectionLost(self, reason):
        # This method gets called twice: once from `SSHChannel.closeReceived`
        # when the client closes the channel and once from `SSHSession.closed`
        # when the server closes the session. We change the avatar attribute
        # to avoid logging the `SFTPClosed` event twice.
        filetransfer.FileTransferServer.connectionLost(self, reason)
        if self.avatar is not None:
            avatar = self.avatar
            self.avatar = None
            notify(events.SFTPClosed(avatar))
