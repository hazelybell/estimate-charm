# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Fixture for the librarians."""

__metaclass__ = type
__all__ = [
    'fillLibrarianFile',
    'LibrarianServerFixture',
    ]

import os
import shutil
import tempfile
from textwrap import dedent
import warnings

from fixtures import (
    Fixture,
    FunctionFixture,
    )

from lp.services.config import config
from lp.services.daemons.tachandler import (
    TacException,
    TacTestSetup,
    )
from lp.services.librarianserver.storage import _relFileLocation
from lp.services.osutils import get_pid_from_file


class LibrarianServerFixture(TacTestSetup):
    """Librarian server fixture.

    :ivar service_config: A config fragment with the variables for this
           service.
    :ivar root: the root of the server storage area.
    :ivar upload_port: the port to upload on.
    :ivar download_port: the port to download from.
    :ivar restricted_upload_port: the port to upload restricted files on.
    :ivar restricted_download_port: the port to upload restricted files from.
    :ivar pid: pid of the external process.
    """

    def __init__(self, config_fixture):
        """Initialize the LibrarianServerFixture.

        :param config_fixture: The ConfigFixture in use by our tests.
                               In the layered environment, this is
                               BaseLayer.config_fixture.
        """
        Fixture.__init__(self)
        self._pid = None
        # Track whether the fixture has been setup or not.
        self._setup = False
        self.config_fixture = config_fixture

    def setUp(self):
        """Start both librarian instances."""
        if (self._persistent_servers() and self.pid):
            return
        else:
            # self.pid may have been evaluated - nuke it.
            self._pid = None
        # The try:except here can be removed if someone audits the callers to
        # make sure that they call cleanUp if setUp fails.
        try:
            TacTestSetup.setUp(self)
        except TacException:
            self.cleanUp()
            raise
        else:
            self._pid = self._read_pid()
        self._setup = True
        self.addCleanup(setattr, self, '_setup', False)

        # Update the config our tests are using to know about the
        # correct ports.
        self.config_fixture.add_section(self.service_config)
        config.reloadConfig()

    def cleanUp(self):
        """Shut downs both librarian instances."""
        if self._persistent_servers():
            return
        if not self._setup:
            warnings.warn("Attempt to tearDown inactive fixture.",
                DeprecationWarning, stacklevel=3)
            return
        TacTestSetup.cleanUp(self)

    def clear(self):
        """Clear all files from the Librarian"""
        # Make this smarter if our tests create huge numbers of files
        if os.path.isdir(os.path.join(self.root, '00')):
            shutil.rmtree(os.path.join(self.root, '00'))

    @property
    def pid(self):
        if self._pid:
            return self._pid
        if self._persistent_servers():
            self._pid = self._read_pid()
        return self._pid

    def _read_pid(self):
        return get_pid_from_file(self.pidfile)

    def _dynamic_config(self):
        """Is a dynamic config to be used?

        True if LP_TEST_INSTANCE is set in the environment.
        """
        return 'LP_TEST_INSTANCE' in os.environ

    def _persistent_servers(self):
        return os.environ.get('LP_PERSISTENT_TEST_SERVICES') is not None

    @property
    def root(self):
        """The root directory for the librarian file repository."""
        if self._dynamic_config():
            return self._root
        else:
            return config.librarian_server.root

    def setUpRoot(self):
        """Create the librarian root archive."""
        if self._dynamic_config():
            root_fixture = FunctionFixture(tempfile.mkdtemp, shutil.rmtree)
            self.useFixture(root_fixture)
            self._root = root_fixture.fn_result
            os.chmod(self.root, 0700)
            # Give the root to the new librarian.
            os.environ['LP_LIBRARIAN_ROOT'] = self._root
        else:
            # This should not happen in normal usage, but might if someone
            # interrupts the test suite.
            if os.path.exists(self.root):
                self.tearDownRoot()
            self.addCleanup(self.tearDownRoot)
            os.makedirs(self.root, 0700)

    def _waitForDaemonStartup(self):
        super(LibrarianServerFixture, self)._waitForDaemonStartup()
        # Expose the dynamically allocated ports, if we used them.
        if not self._dynamic_config():
            self.download_port = config.librarian.download_port
            self.upload_port = config.librarian.upload_port
            self.restricted_download_port = \
                config.librarian.restricted_download_port
            self.restricted_upload_port = \
                config.librarian.restricted_upload_port
            return
        chunks = self.getLogChunks()
        # A typical startup: upload, download, restricted up, restricted down.
        #2010-10-20 14:28:21+0530 [-] Log opened.
        #2010-10-20 14:28:21+0530 [-] twistd 10.1.0 (/usr/bin/python 2.6.5) starting up.
        #2010-10-20 14:28:21+0530 [-] reactor class: twisted.internet.selectreactor.SelectReactor.
        #2010-10-20 14:28:21+0530 [-] lp.services.librarianserver.libraryprotocol.FileUploadFactory starting on 59090
        #2010-10-20 14:28:21+0530 [-] Starting factory <lp.services.librarianserver.libraryprotocol.FileUploadFactory instance at 0x6f8ff38>
        #2010-10-20 14:28:21+0530 [-] twisted.web.server.Site starting on 58000
        #2010-10-20 14:28:21+0530 [-] Starting factory <twisted.web.server.Site instance at 0x6fb2638>
        #2010-10-20 14:28:21+0530 [-] lp.services.librarianserver.libraryprotocol.FileUploadFactory starting on 59095
        #2010-10-20 14:28:21+0530 [-] Starting factory <lp.services.librarianserver.libraryprotocol.FileUploadFactory instance at 0x6fb25f0>
        #2010-10-20 14:28:21+0530 [-] twisted.web.server.Site starting on 58005
        self.upload_port = int(chunks[3].split()[-1])
        self.download_port = int(chunks[5].split()[-1])
        self.restricted_upload_port = int(chunks[7].split()[-1])
        self.restricted_download_port = int(chunks[9].split()[-1])
        self.service_config = dedent("""\
            [librarian_server]
            root: %s
            [librarian]
            download_port: %s
            upload_port: %s
            download_url: http://%s:%s/
            restricted_download_port: %s
            restricted_upload_port: %s
            restricted_download_url: http://%s:%s/
            """) % (
                self.root,
                self.download_port,
                self.upload_port,
                config.librarian.download_host,
                self.download_port,
                self.restricted_download_port,
                self.restricted_upload_port,
                config.librarian.restricted_download_host,
                self.restricted_download_port,
                )

    def tearDownRoot(self):
        """Remove the librarian root archive."""
        if os.path.isdir(self.root):
            shutil.rmtree(self.root)

    @property
    def tacfile(self):
        return os.path.join(self.daemon_directory, 'librarian.tac')

    @property
    def pidfile(self):
        try:
            return os.path.join(self.root, 'librarian.pid')
        except AttributeError:
            # An attempt to read the pidfile before this fixture was setUp,
            # with dynamic configuration.
            return '/tmp/unused/'

    @property
    def logfile(self):
        # Store the log in the server root; if its wanted after a test, that
        # test can use addDetail to grab the log and include it in its
        # error.
        try:
            return os.path.join(self.root, 'librarian.log')
        except AttributeError:
            # An attempt to read the pidfile before this fixture was setUp,
            # with dynamic configuration.
            return '/tmp/unused/'

    def getLogChunks(self):
        """Get a list with the contents of the librarian log in it."""
        return open(self.logfile, 'rb').readlines()

    def reset(self):
        """Reset the librarian to a consistent initial state."""
        self.clear()
        self.truncateLog()


def fillLibrarianFile(fileid, content='Fake Content'):
    """Write contents in disk for a librarian sampledata."""
    filepath = os.path.join(
        config.librarian_server.root, _relFileLocation(fileid))

    if not os.path.exists(os.path.dirname(filepath)):
        os.makedirs(os.path.dirname(filepath))

    libfile = open(filepath, 'wb')
    libfile.write(content)
    libfile.close()
