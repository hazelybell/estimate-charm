# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Twisted SFTP implementation of the Poppy upload server."""

__metaclass__ = type
__all__ = [
    'SFTPFile',
    'SFTPServer',
    ]

import errno
import logging
import os
import tempfile

from twisted.conch.interfaces import (
    ISFTPFile,
    ISFTPServer,
    )
from zope.component import (
    adapter,
    provideHandler,
    )
from zope.interface import implements

from lp.poppy.filesystem import UploadFileSystem
from lp.poppy.hooks import Hooks
from lp.services.sshserver.events import SFTPClosed
from lp.services.sshserver.sftp import FileIsADirectory


class SFTPServer:
    """An implementation of `ISFTPServer` that backs onto a Poppy filesystem.
    """

    implements(ISFTPServer)

    def __init__(self, avatar, fsroot):
        provideHandler(self.connectionClosed)
        self._avatar = avatar
        self._fs_root = fsroot
        self.uploadfilesystem = UploadFileSystem(tempfile.mkdtemp())
        self._current_upload = self.uploadfilesystem.rootpath
        os.chmod(self._current_upload, 0770)
        self._log = logging.getLogger("poppy-sftp")
        self.hook = Hooks(
            self._fs_root, self._log, "ubuntu", perms='g+rws', prefix='-sftp')
        self.hook.new_client_hook(self._current_upload, 0, 0)
        self.hook.auth_verify_hook(self._current_upload, None, None)

    def gotVersion(self, other_version, ext_data):
        return {}

    def openFile(self, filename, flags, attrs):
        self._create_missing_directories(filename)
        absfile = self._translate_path(filename)
        return SFTPFile(absfile)

    def removeFile(self, filename):
        pass

    def renameFile(self, old_path, new_path):
        abs_old = self._translate_path(old_path)
        abs_new = self._translate_path(new_path)
        os.rename(abs_old, abs_new)

    def makeDirectory(self, path, attrs):
        # XXX: We ignore attrs here
        self.uploadfilesystem.mkdir(path)

    def removeDirectory(self, path):
        self.uploadfilesystem.rmdir(path)

    def openDirectory(self, path):
        pass

    def getAttrs(self, path, follow_links):
        pass

    def setAttrs(self, path, attrs):
        pass

    def readLink(self, path):
        pass

    def makeLink(self, link_path, target_path):
        pass

    def realPath(self, path):
        return path

    def extendedRequest(self, extended_name, extended_data):
        pass

    def _create_missing_directories(self, filename):
        new_dir, new_file = os.path.split(
            self.uploadfilesystem._sanitize(filename))
        if new_dir != '':
            if not os.path.exists(
                os.path.join(self._current_upload, new_dir)):
                self.uploadfilesystem.mkdir(new_dir)

    def _translate_path(self, filename):
        return self.uploadfilesystem._full(
            self.uploadfilesystem._sanitize(filename))

    @adapter(SFTPClosed)
    def connectionClosed(self, event):
        if event.avatar is not self._avatar:
            return
        self.hook.client_done_hook(self._current_upload, 0, 0)


class SFTPFile:

    implements(ISFTPFile)

    def __init__(self, filename):
        self.filename = filename

    def close(self):
        pass

    def readChunk(self, offset, length):
        pass

    def writeChunk(self, offset, data):
        try:
            chunk_file = os.open(
                self.filename, os.O_CREAT | os.O_WRONLY, 0644)
        except OSError as e:
            if e.errno != errno.EISDIR:
                raise
            raise FileIsADirectory(self.filename)
        os.lseek(chunk_file, offset, 0)
        os.write(chunk_file, data)
        os.close(chunk_file)

    def getAttrs(self):
        pass

    def setAttrs(self, attr):
        pass
