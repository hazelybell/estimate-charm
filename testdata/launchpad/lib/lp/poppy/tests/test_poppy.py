# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Functional tests for poppy FTP daemon."""

__metaclass__ = type

import os
import shutil
import stat
import StringIO
import tempfile
import time
import unittest

from bzrlib.tests import (
    condition_id_re,
    exclude_tests_by_condition,
    multiply_tests,
    )
from bzrlib.transport import get_transport
from fixtures import (
    EnvironmentVariableFixture,
    Fixture,
    )
import transaction
from zope.component import getUtility

from lp.poppy.hooks import Hooks
from lp.registry.interfaces.ssh import ISSHKeySet
from lp.services.config import config
from lp.services.daemons.tachandler import TacTestSetup
from lp.testing import TestCaseWithFactory
from lp.testing.layers import (
    ZopelessAppServerLayer,
    ZopelessDatabaseLayer,
    )


class FTPServer(Fixture):
    """This is an abstraction of connecting to an FTP server."""

    def __init__(self, root_dir, factory):
        self.root_dir = root_dir
        self.port = 2121

    def setUp(self):
        super(FTPServer, self).setUp()
        self.poppytac = self.useFixture(PoppyTac(self.root_dir))

    def getAnonTransport(self):
        return get_transport(
            'ftp://anonymous:me@example.com@localhost:%s/' % (self.port,))

    def getTransport(self):
        return get_transport('ftp://ubuntu:@localhost:%s/' % (self.port,))

    def disconnect(self, transport):
        transport._get_connection().close()

    def waitForStartUp(self):
        """Wait for the FTP server to start up."""
        pass

    def waitForClose(self, number=1):
        """Wait for an FTP connection to close.

        Poppy is configured to echo 'Post-processing finished' to stdout
        when a connection closes, so we wait for that to appear in its
        output as a way to tell that the server has finished with the
        connection.
        """
        self.poppytac.waitForPostProcessing(number)


class SFTPServer(Fixture):
    """This is an abstraction of connecting to an SFTP server."""

    def __init__(self, root_dir, factory):
        self.root_dir = root_dir
        self._factory = factory
        self.port = int(config.poppy.port.partition(':')[2])

    def addSSHKey(self, person, public_key_path):
        f = open(public_key_path, 'r')
        try:
            public_key = f.read()
        finally:
            f.close()
        sshkeyset = getUtility(ISSHKeySet)
        key = sshkeyset.new(person, public_key)
        transaction.commit()
        return key

    def setUpUser(self, name):
        user = self._factory.makePerson(name=name)
        self.addSSHKey(
            user, os.path.join(os.path.dirname(__file__), 'poppy-sftp.pub'))
        # Set up a temporary home directory for Paramiko's sake
        self._home_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self._home_dir)
        os.mkdir(os.path.join(self._home_dir, '.ssh'))
        os.symlink(
            os.path.join(os.path.dirname(__file__), 'poppy-sftp'),
            os.path.join(self._home_dir, '.ssh', 'id_rsa'))
        self.useFixture(EnvironmentVariableFixture('HOME', self._home_dir))
        self.useFixture(EnvironmentVariableFixture('SSH_AUTH_SOCK', None))
        self.useFixture(EnvironmentVariableFixture('BZR_SSH', 'paramiko'))

    def setUp(self):
        super(SFTPServer, self).setUp()
        self.setUpUser('joe')
        self.poppytac = self.useFixture(PoppyTac(self.root_dir))

    def disconnect(self, transport):
        transport._get_connection().close()

    def waitForStartUp(self):
        pass

    def waitForClose(self, number=1):
        self.poppytac.waitForPostProcessing(number)

    def getTransport(self):
        return get_transport('sftp://joe@localhost:%s/' % (self.port,))


class PoppyTac(TacTestSetup):
    """A SFTP Poppy server fixture.

    This class has two distinct roots:
     - the POPPY_ROOT where the test looks for uploaded output.
     - the server root where ssh keys etc go.
    """

    def __init__(self, fs_root):
        self.fs_root = fs_root
        # The setUp check for stale pids races with self._root being assigned,
        # so store a plausible path temporarily. Once all fixtures use unique
        # environments this can go.
        self._root = '/var/does/not/exist'

    def setUp(self):
        os.environ['POPPY_ROOT'] = self.fs_root
        super(PoppyTac, self).setUp(umask='0')

    def setUpRoot(self):
        self._root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)

    @property
    def root(self):
        return self._root

    @property
    def tacfile(self):
        return os.path.abspath(
            os.path.join(config.root, 'daemons', 'poppy-sftp.tac'))

    @property
    def logfile(self):
        return os.path.join(self.root, 'poppy-sftp.log')

    @property
    def pidfile(self):
        return os.path.join(self.root, 'poppy-sftp.pid')

    def waitForPostProcessing(self, number=1):
        now = time.time()
        deadline = now + 20
        while now < deadline and not self._hasPostProcessed(number):
            time.sleep(0.1)
            now = time.time()

        if now >= deadline:
            raise Exception("Poppy post-processing did not complete")

    def _hasPostProcessed(self, number):
        if os.path.exists(self.logfile):
            with open(self.logfile, "r") as logfile:
                occurrences = logfile.read().count(Hooks.LOG_MAGIC)
                return occurrences >= number
        else:
            return False


class TestPoppy(TestCaseWithFactory):
    """Test if poppy.py daemon works properly."""

    def setUp(self):
        """Set up poppy in a temp dir."""
        super(TestPoppy, self).setUp()
        self.root_dir = self.makeTemporaryDirectory()
        self.server = self.server_factory(self.root_dir, self.factory)
        self.useFixture(self.server)

    def _uploadPath(self, path):
        """Return system path of specified path inside an upload.

        Only works for a single upload (poppy transaction).
        """
        contents = sorted(os.listdir(self.root_dir))
        upload_dir = contents[1]
        return os.path.join(self.root_dir, upload_dir, path)

    def test_change_directory_anonymous(self):
        # Check that FTP access with an anonymous user works.
        transport = self.server.getAnonTransport()
        self.test_change_directory(transport)

    def test_change_directory(self, transport=None):
        """Check automatic creation of directories 'cwd'ed in.

        Also ensure they are created with proper permission (g+rwxs)
        """
        self.server.waitForStartUp()

        if transport is None:
            transport = self.server.getTransport()
        transport.stat('foo/bar')  # .stat will implicity chdir for us

        self.server.disconnect(transport)
        self.server.waitForClose()

        wanted_path = self._uploadPath('foo/bar')
        self.assertTrue(os.path.exists(wanted_path))
        self.assertEqual(os.stat(wanted_path).st_mode, 042775)

    def test_mkdir(self):
        # Creating directories on the server makes actual directories where we
        # expect them, and creates them with g+rwxs
        self.server.waitForStartUp()

        transport = self.server.getTransport()
        transport.mkdir('foo/bar', mode=None)

        self.server.disconnect(transport)
        self.server.waitForClose()

        wanted_path = self._uploadPath('foo/bar')
        self.assertTrue(os.path.exists(wanted_path))
        self.assertEqual(os.stat(wanted_path).st_mode, 042775)

    def test_rmdir(self):
        """Check recursive RMD (aka rmdir)"""
        self.server.waitForStartUp()

        transport = self.server.getTransport()
        transport.mkdir('foo/bar')
        transport.rmdir('foo/bar')
        transport.rmdir('foo')

        self.server.disconnect(transport)
        self.server.waitForClose()

        wanted_path = self._uploadPath('foo')
        self.assertFalse(os.path.exists(wanted_path))

    def test_single_upload(self):
        """Check if the parent directories are created during file upload.

        The uploaded file permissions are also special (g+rwxs).
        """
        self.server.waitForStartUp()

        transport = self.server.getTransport()
        fake_file = StringIO.StringIO("fake contents")

        transport.put_file('foo/bar/baz', fake_file, mode=None)

        self.server.disconnect(transport)
        self.server.waitForClose()

        wanted_path = self._uploadPath('foo/bar/baz')
        fs_content = open(os.path.join(wanted_path)).read()
        self.assertEqual(fs_content, "fake contents")
        # Expected mode is -rw-rwSr--.
        self.assertEqual(
            os.stat(wanted_path).st_mode,
            stat.S_IROTH | stat.S_ISGID | stat.S_IRGRP | stat.S_IWGRP
            | stat.S_IWUSR | stat.S_IRUSR | stat.S_IFREG)

    def test_full_source_upload(self):
        """Check that the connection will deal with multiple files being
        uploaded.
        """
        self.server.waitForStartUp()

        transport = self.server.getTransport()

        files = ['test-source_0.1.dsc',
                 'test-source_0.1.orig.tar.gz',
                 'test-source_0.1.diff.gz',
                 'test-source_0.1_source.changes']

        for upload in files:
            fake_file = StringIO.StringIO(upload)
            file_to_upload = "~ppa-user/ppa/ubuntu/%s" % upload
            transport.put_file(file_to_upload, fake_file, mode=None)

        self.server.disconnect(transport)
        self.server.waitForClose()

        upload_path = self._uploadPath('')
        self.assertEqual(os.stat(upload_path).st_mode, 042770)
        dir_name = upload_path.split('/')[-2]
        if transport._user == 'joe':
            self.assertEqual(dir_name.startswith('upload-sftp-2'), True)
        elif transport._user == 'ubuntu':
            self.assertEqual(dir_name.startswith('upload-ftp-2'), True)
        for upload in files:
            wanted_path = self._uploadPath(
                "~ppa-user/ppa/ubuntu/%s" % upload)
            fs_content = open(os.path.join(wanted_path)).read()
            self.assertEqual(fs_content, upload)
            # Expected mode is -rw-rwSr--.
            self.assertEqual(
                os.stat(wanted_path).st_mode,
                stat.S_IROTH | stat.S_ISGID | stat.S_IRGRP | stat.S_IWGRP
                | stat.S_IWUSR | stat.S_IRUSR | stat.S_IFREG)

    def test_upload_isolation(self):
        """Check if poppy isolates the uploads properly.

        Upload should be done atomically, i.e., poppy should isolate the
        context according each connection/session.
        """
        # Perform a pair of sessions with distinct connections in time.
        self.server.waitForStartUp()

        conn_one = self.server.getTransport()
        fake_file = StringIO.StringIO("ONE")
        conn_one.put_file('test', fake_file, mode=None)
        self.server.disconnect(conn_one)
        self.server.waitForClose(1)

        conn_two = self.server.getTransport()
        fake_file = StringIO.StringIO("TWO")
        conn_two.put_file('test', fake_file, mode=None)
        self.server.disconnect(conn_two)
        self.server.waitForClose(2)

        # Perform a pair of sessions with simultaneous connections.
        conn_three = self.server.getTransport()
        conn_four = self.server.getTransport()

        fake_file = StringIO.StringIO("THREE")
        conn_three.put_file('test', fake_file, mode=None)

        fake_file = StringIO.StringIO("FOUR")
        conn_four.put_file('test', fake_file, mode=None)

        self.server.disconnect(conn_three)
        self.server.waitForClose(3)

        self.server.disconnect(conn_four)
        self.server.waitForClose(4)

        # Build a list of directories representing the 4 sessions.
        upload_dirs = [leaf for leaf in sorted(os.listdir(self.root_dir))
                       if not leaf.startswith(".") and
                       not leaf.endswith(".distro")]
        self.assertEqual(len(upload_dirs), 4)

        # Check the contents of files on each session.
        expected_contents = ['ONE', 'TWO', 'THREE', 'FOUR']
        for index in range(4):
            content = open(os.path.join(
                self.root_dir, upload_dirs[index], "test")).read()
            self.assertEqual(content, expected_contents[index])


def test_suite():
    tests = unittest.TestLoader().loadTestsFromName(__name__)
    scenarios = [
        ('ftp', {'server_factory': FTPServer,
                 # XXX: In an ideal world, this would be in the UnitTests
                 # layer. Let's get one step closer to that ideal world.
                 'layer': ZopelessDatabaseLayer}),
        ('sftp', {'server_factory': SFTPServer,
                  'layer': ZopelessAppServerLayer}),
        ]
    suite = unittest.TestSuite()
    multiply_tests(tests, scenarios, suite)
    # SFTP doesn't have the concept of the server changing directories, since
    # clients will only send absolute paths, so drop that test.
    return exclude_tests_by_condition(
        suite, condition_id_re(r'test_change_directory.*\(sftp\)$'))
