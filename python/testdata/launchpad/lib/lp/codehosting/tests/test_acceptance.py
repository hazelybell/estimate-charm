# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Acceptance tests for the codehosting server."""

__metaclass__ = type

import atexit
import os
import re
import signal
import subprocess
import sys
import time
import unittest
import urllib2
import xmlrpclib

import bzrlib.branch
from bzrlib.tests import (
    multiply_tests,
    TestCaseWithTransport,
    )
from bzrlib.urlutils import local_path_from_url
from bzrlib.workingtree import WorkingTree
from zope.component import getUtility

from lp.code.bzr import (
    BranchFormat,
    ControlFormat,
    RepositoryFormat,
    )
from lp.code.enums import BranchType
from lp.code.interfaces.branch import IBranchSet
from lp.code.interfaces.branchnamespace import get_branch_namespace
from lp.code.tests.helpers import (
    get_non_existant_source_package_branch_unique_name,
    )
from lp.codehosting import (
    get_bzr_path,
    get_BZR_PLUGIN_PATH_for_subprocess,
    )
from lp.codehosting.bzrutils import DenyingServer
from lp.codehosting.tests.helpers import (
    adapt_suite,
    LoomTestMixin,
    )
from lp.codehosting.tests.servers import (
    CodeHostingTac,
    set_up_test_user,
    SSHCodeHostingServer,
    )
from lp.codehosting.vfs import branch_id_to_path
from lp.registry.model.person import Person
from lp.registry.model.product import Product
from lp.services.config import config
from lp.services.testing.profiled import profiled
from lp.testing import TestCaseWithFactory
from lp.testing.layers import ZopelessAppServerLayer


class ForkingServerForTests(object):
    """Map starting/stopping a LPForkingService to setUp() and tearDown()."""

    def __init__(self):
        self.process = None
        self.socket_path = None

    def setUp(self):
        bzr_path = get_bzr_path()
        BZR_PLUGIN_PATH = get_BZR_PLUGIN_PATH_for_subprocess()
        env = os.environ.copy()
        env['BZR_PLUGIN_PATH'] = BZR_PLUGIN_PATH
        # TODO: We probably want to use a random disk path for
        #       forking_daemon_socket, but we need to update config so that
        #       the CodeHosting service can find it.
        #       The main problem is that CodeHostingTac seems to start a tac
        #       server directly from the disk configs, and doesn't use the
        #       in-memory config. So we can't just override the memory
        #       settings, we have to somehow pass it a new config-on-disk to
        #       use.
        self.socket_path = config.codehosting.forking_daemon_socket
        command = [sys.executable, bzr_path, 'launchpad-forking-service',
                   '--path', self.socket_path, '-Derror']
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        self.process = process
        stderr = []
        # The first line should be "Preloading" indicating it is ready
        stderr.append(process.stderr.readline())
        # The next line is the "Listening on socket" line
        stderr.append(process.stderr.readline())
        # Now it should be ready.  If there were any errors, let's check, and
        # report them.
        if (process.poll() is not None or
            not stderr[1].strip().startswith('Listening on socket')):
            if process.poll() is None:
                time.sleep(1)  # Give the traceback a chance to render.
                os.kill(process.pid, signal.SIGTERM)
                process.wait()
                self.process = None
            # Looks like there was a problem. We cannot use the "addDetail"
            # method because this class is not a TestCase and does not have
            # access to one.  It runs as part of a layer. A "print" is the
            # best we can do.  That should still be visible on buildbot, which
            # is where we have seen spurious failures so far.
            print
            print "stdout:"
            print process.stdout.read()
            print "-" * 70
            print "stderr:"
            print ''.join(stderr)
            print process.stderr.read()
            print "-" * 70
            raise RuntimeError(
                'Bzr server did not start correctly.  See stdout and stderr '
                'reported above. Command was "%s".  PYTHONPATH was "%s".  '
                'BZR_PLUGIN_PATH was "%s".' %
                (' '.join(command),
                 env.get('PYTHONPATH'),
                 env.get('BZR_PLUGIN_PATH')))

    def tearDown(self):
        # SIGTERM is the graceful exit request, potentially we could wait a
        # bit and send something stronger?
        if self.process is not None and self.process.poll() is None:
            os.kill(self.process.pid, signal.SIGTERM)
            self.process.wait()
            self.process = None
        # We want to make sure the socket path has been cleaned up, so that
        # future runs can work correctly
        if os.path.exists(self.socket_path):
            # Should there be a warning/error here?
            os.remove(self.socket_path)


class SSHServerLayer(ZopelessAppServerLayer):

    _tac_handler = None
    _forker_service = None

    @classmethod
    def getTacHandler(cls):
        if cls._tac_handler is None:
            cls._tac_handler = CodeHostingTac(
                config.codehosting.mirrored_branches_root)
        return cls._tac_handler

    @classmethod
    def getForker(cls):
        if cls._forker_service is None:
            cls._forker_service = ForkingServerForTests()
        return cls._forker_service

    @classmethod
    @profiled
    def setUp(cls):
        tac_handler = SSHServerLayer.getTacHandler()
        tac_handler.setUp()
        SSHServerLayer._reset()
        atexit.register(tac_handler.tearDown)
        forker = SSHServerLayer.getForker()
        forker.setUp()

    @classmethod
    @profiled
    def tearDown(cls):
        SSHServerLayer._reset()
        SSHServerLayer.getTacHandler().tearDown()
        SSHServerLayer.getForker().tearDown()

    @classmethod
    @profiled
    def _reset(cls):
        """Reset the storage."""
        SSHServerLayer.getTacHandler().clear()

    @classmethod
    @profiled
    def testSetUp(cls):
        SSHServerLayer._reset()
        set_up_test_user('testuser', 'testteam')

    @classmethod
    @profiled
    def testTearDown(cls):
        SSHServerLayer._reset()


class SSHTestCase(TestCaseWithTransport, LoomTestMixin, TestCaseWithFactory):
    """TestCase class that runs an SSH server as well as the app server."""

    layer = SSHServerLayer
    scheme = None

    def setUp(self):
        super(SSHTestCase, self).setUp()
        self.disable_directory_isolation()
        tac_handler = SSHServerLayer.getTacHandler()
        self.server = SSHCodeHostingServer(self.scheme, tac_handler)
        self.server.start_server()
        self.addCleanup(self.server.stop_server)

        # Prevent creation of in-process sftp:// and bzr+ssh:// transports --
        # such connections tend to leak threads and occasionally create
        # uncollectable garbage.
        ssh_denier = DenyingServer(['bzr+ssh://', 'sftp://'])
        ssh_denier.start_server()
        self.addCleanup(ssh_denier.stop_server)

        # Create a local branch with one revision
        tree = self.make_branch_and_tree('local')
        self.local_branch = tree.branch
        self.local_branch_path = local_path_from_url(self.local_branch.base)
        self.build_tree(['local/foo'])
        tree.add('foo')
        self.revid = tree.commit('Added foo')

    def __str__(self):
        return self.id()

    def getTransport(self, relpath=None):
        return self.server.getTransport(relpath)

    def assertBranchesMatch(self, local_url, remote_url):
        """Assert that two branches have the same last revision."""
        local_revision = self.getLastRevision(local_url)
        remote_revision = self.getLastRevision(remote_url)
        self.assertEqual(local_revision, remote_revision)

    def runInChdir(self, directory, func, *args, **kwargs):
        old_dir = os.getcwdu()
        os.chdir(directory)
        try:
            return func(*args, **kwargs)
        finally:
            os.chdir(old_dir)

    def _run_bzr(self, args, retcode=0):
        """Call run_bzr_subprocess with some common options.

        We always want to force the subprocess to do its ssh communication
        with paramiko (because OpenSSH doesn't respect the $HOME environment
        variable) and we want to load the plugins that are in rocketfuel
        (mainly so we can test the loom support).
        """
        return self.run_bzr_subprocess(
            args, env_changes={
                'BZR_SSH': 'paramiko',
                'BZR_PLUGIN_PATH': get_BZR_PLUGIN_PATH_for_subprocess()
            },
            allow_plugins=True, retcode=retcode)

    def _run_bzr_error(self, args):
        """Run bzr expecting an error, returning the error message.
        """
        output, error = self._run_bzr(args, retcode=3)
        for line in error.splitlines():
            if line.startswith("bzr: ERROR"):
                return line
        raise AssertionError(
            "Didn't find error line in output:\n\n%s\n" % error)

    def branch(self, remote_url, local_directory):
        """Branch from the given URL to a local directory."""
        self._run_bzr(['branch', remote_url, local_directory])

    def get_bzr_path(self):
        """See `bzrlib.tests.TestCase.get_bzr_path`.

        We override this to return the 'bzr' executable from sourcecode.
        """
        return get_bzr_path()

    def push(self, local_directory, remote_url, extra_args=None):
        """Push the local branch to the given URL."""
        args = ['push', '-d', local_directory, remote_url]
        if extra_args is not None:
            args.extend(extra_args)
        self._run_bzr(args)

    def assertCantPush(self, local_directory, remote_url, error_messages=()):
        """Check that we cannot push from 'local_directory' to 'remote_url'.

        In addition, if a list of messages is supplied as the error_messages
        argument, check that the bzr client printed one of these messages
        which shouldn't include the 'bzr: ERROR:' part of the message.

        :return: The last line of the stderr from the subprocess, which will
            be the 'bzr: ERROR: <repr of Exception>' line.
        """
        error_line = self._run_bzr_error(
            ['push', '-d', local_directory, remote_url])
        # This will be the will be the 'bzr: ERROR: <repr of Exception>' line.
        if not error_messages:
            return error_line
        for msg in error_messages:
            if error_line.startswith('bzr: ERROR: ' + msg):
                return error_line
        self.fail(
            "Error message %r didn't match any of those supplied."
            % error_line)

    def getLastRevision(self, remote_url):
        """Get the last revision ID at the given URL."""
        output, error = self._run_bzr(
            ['revision-info', '-d', remote_url])
        return output.split()[1]

    def getTransportURL(self, relpath=None, username=None):
        """Return the base URL for the tests."""
        if relpath is None:
            relpath = ''
        return self.server.get_url(username) + relpath

    def getDatabaseBranch(self, personName, productName, branchName):
        """Look up and return the specified branch from the database."""
        owner = Person.byName(personName)
        if productName is None:
            product = None
        else:
            product = Product.selectOneBy(name=productName)
        namespace = get_branch_namespace(owner, product)
        return namespace.getByName(branchName)

    def createBazaarBranch(self, user, product, branch, creator=None,
                           branch_root=None):
        """Create a new branch in the database and push our test branch there.

        Used to create branches that the test user is not able to create, and
        might not even be able to view.
        """
        authserver = xmlrpclib.ServerProxy(
            config.codehosting.authentication_endpoint)
        codehosting_api = xmlrpclib.ServerProxy(
            config.codehosting.codehosting_endpoint)
        if creator is None:
            creator_id = authserver.getUserAndSSHKeys(user)['id']
        else:
            creator_id = authserver.getUserAndSSHKeys(creator)['id']
        if branch_root is None:
            branch_root = self.server._mirror_root
        branch_id = codehosting_api.createBranch(
            creator_id, '/~%s/%s/%s' % (user, product, branch))
        branch_url = 'file://' + os.path.abspath(
            os.path.join(branch_root, branch_id_to_path(branch_id)))
        self.push(self.local_branch_path, branch_url, ['--create-prefix'])
        return branch_url


class SmokeTest(SSHTestCase):
    """Smoke test for repository support."""

    def setUp(self):
        self.scheme = 'bzr+ssh'
        super(SmokeTest, self).setUp()
        self.first_tree = 'first'
        self.second_tree = 'second'

    def make_branch_specifying_repo_format(self, relpath, repo_format):
        bd = self.make_bzrdir(relpath, format=self.bzrdir_format)
        repo_format.initialize(bd)
        return bd.create_branch()

    def make_branch_and_tree(self, relpath):
        b = self.make_branch_specifying_repo_format(
            relpath, self.repository_format)
        return b.bzrdir.create_workingtree()

    def test_smoke(self):
        # Make a new branch
        tree = self.make_branch_and_tree(self.first_tree)

        # Push up a new branch.
        remote_url = self.getTransportURL('~testuser/+junk/new-branch')
        self.push(self.first_tree, remote_url)
        self.assertBranchesMatch(self.first_tree, remote_url)

        # Commit to it.
        tree.commit('new revision', allow_pointless=True)

        # Push it up again.
        self.push(self.first_tree, remote_url)
        self.assertBranchesMatch(self.first_tree, remote_url)

        # Pull it back down.
        self.branch(remote_url, self.second_tree)
        self.assertBranchesMatch(self.first_tree, self.second_tree)


class AcceptanceTests(SSHTestCase):
    """Acceptance tests for the Launchpad codehosting service.

    Originally converted from the English at
    https://launchpad.canonical.com/SupermirrorTaskList
    """

    def assertNotBranch(self, url):
        """Assert that there's no branch at 'url'."""
        error_line = self._run_bzr_error(
            ['cat-revision', '-r', 'branch:' + url])
        self.assertTrue(
            error_line.startswith('bzr: ERROR: Not a branch:'),
            'Expected "Not a branch", found %r' % error_line)

    def makeDatabaseBranch(self, owner_name, product_name, branch_name,
                           branch_type=BranchType.HOSTED):
        """Create a new branch in the database."""
        owner = Person.selectOneBy(name=owner_name)
        if product_name == '+junk':
            product = None
        else:
            product = Product.selectOneBy(name=product_name)
        if branch_type == BranchType.MIRRORED:
            url = 'http://example.com'
        else:
            url = None

        namespace = get_branch_namespace(owner, product)
        return namespace.createBranch(
            branch_type=branch_type, name=branch_name, registrant=owner,
            url=url)

    def test_push_to_new_branch(self):
        remote_url = self.getTransportURL('~testuser/+junk/test-branch')
        self.push(self.local_branch_path, remote_url)
        self.assertBranchesMatch(self.local_branch_path, remote_url)
        ZopelessAppServerLayer.txn.begin()
        db_branch = getUtility(IBranchSet).getByUniqueName(
            '~testuser/+junk/test-branch')
        self.assertEqual(
            RepositoryFormat.BZR_CHK_2A, db_branch.repository_format)
        self.assertEqual(
            BranchFormat.BZR_BRANCH_7, db_branch.branch_format)
        self.assertEqual(
            ControlFormat.BZR_METADIR_1, db_branch.control_format)
        ZopelessAppServerLayer.txn.commit()

    def test_push_to_existing_branch(self):
        """Pushing to an existing branch must work."""
        # Initial push.
        remote_url = self.getTransportURL('~testuser/+junk/test-branch')
        self.push(self.local_branch_path, remote_url)
        remote_revision = self.getLastRevision(remote_url)
        self.assertEqual(self.revid, remote_revision)
        # Add a single revision to the local branch.
        tree = WorkingTree.open(self.local_branch.base)
        tree.commit('Empty commit', rev_id='rev2')
        # Push the new revision.
        self.push(self.local_branch_path, remote_url)
        self.assertBranchesMatch(self.local_branch_path, remote_url)

    def test_branch_renaming(self):
        """
        Branches should be able to be renamed in the Launchpad webapp, and
        those renames should be immediately reflected in subsequent SFTP
        connections.

        Changing the owner or product, or changing the name of the owner,
        product or branch can change the URL of the branch, so we change
        everything in this test.
        """
        # Push the local branch to the server
        remote_url = self.getTransportURL('~testuser/+junk/test-branch')
        self.push(self.local_branch_path, remote_url)

        # Rename owner, product and branch in the database
        ZopelessAppServerLayer.txn.begin()
        branch = self.getDatabaseBranch('testuser', None, 'test-branch')
        branch.owner.name = 'renamed-user'
        branch.setTarget(user=branch.owner, project=Product.byName('firefox'))
        branch.name = 'renamed-branch'
        ZopelessAppServerLayer.txn.commit()

        # Check that it's not at the old location.
        self.assertNotBranch(
            self.getTransportURL(
                '~testuser/+junk/test-branch', username='renamed-user'))

        # Check that it *is* at the new location.
        self.assertBranchesMatch(
            self.local_branch_path,
            self.getTransportURL(
                '~renamed-user/firefox/renamed-branch',
                username='renamed-user'))

    def test_push_team_branch(self):
        remote_url = self.getTransportURL('~testteam/firefox/a-new-branch')
        self.push(self.local_branch_path, remote_url)
        self.assertBranchesMatch(self.local_branch_path, remote_url)

    def test_push_new_branch_creates_branch_in_database(self):
        # pushing creates a branch in the database with the correct name and
        # last_mirrored_id.
        remote_url = self.getTransportURL(
            '~testuser/+junk/totally-new-branch')
        self.push(self.local_branch_path, remote_url)

        ZopelessAppServerLayer.txn.begin()
        branch = self.getDatabaseBranch(
            'testuser', None, 'totally-new-branch')

        self.assertEqual(
            ['~testuser/+junk/totally-new-branch', self.revid],
            [branch.unique_name, branch.last_mirrored_id])
        ZopelessAppServerLayer.txn.abort()

    def test_record_default_stacking(self):
        # If the location being pushed to has a default stacked-on branch,
        # then branches pushed to that location end up stacked on it by
        # default.
        product = self.factory.makeProduct()
        ZopelessAppServerLayer.txn.commit()

        ZopelessAppServerLayer.txn.begin()

        self.make_branch_and_tree('stacked-on')
        trunk_unique_name = '~testuser/%s/trunk' % product.name
        self.push('stacked-on', self.getTransportURL(trunk_unique_name))
        db_trunk = getUtility(IBranchSet).getByUniqueName(trunk_unique_name)

        self.factory.enableDefaultStackingForProduct(
            db_trunk.product, db_trunk)

        ZopelessAppServerLayer.txn.commit()

        stacked_unique_name = '~testuser/%s/stacked' % product.name
        self.push(
            self.local_branch_path, self.getTransportURL(stacked_unique_name))
        db_stacked = getUtility(IBranchSet).getByUniqueName(
            stacked_unique_name)

        self.assertEqual(db_trunk, db_stacked.stacked_on)

    def test_explicit_stacking(self):
        # If a branch is pushed to launchpad --stacked-on the absolute URL of
        # another Launchpad branch, this is recorded as the stacked_on
        # attribute of the database branch, and stacked on location of the new
        # branch is normalized to be a relative path.
        product = self.factory.makeProduct()
        ZopelessAppServerLayer.txn.commit()

        self.make_branch_and_tree('stacked-on')
        trunk_unique_name = '~testuser/%s/trunk' % product.name
        trunk_url = self.getTransportURL(trunk_unique_name)
        self.push('stacked-on', self.getTransportURL(trunk_unique_name))

        stacked_unique_name = '~testuser/%s/stacked' % product.name
        stacked_url = self.getTransportURL(stacked_unique_name)
        self.push(
            self.local_branch_path, stacked_url,
            extra_args=['--stacked-on', trunk_url])

        branch_set = getUtility(IBranchSet)
        db_trunk = branch_set.getByUniqueName(trunk_unique_name)
        db_stacked = branch_set.getByUniqueName(stacked_unique_name)

        self.assertEqual(db_trunk, db_stacked.stacked_on)

        output, error = self._run_bzr(['info', stacked_url])
        actually_stacked_on = re.search('stacked on: (.*)$', output).group(1)
        self.assertEqual('/' + trunk_unique_name, actually_stacked_on)

    def test_cant_access_private_branch(self):
        # Trying to get information about a private branch should fail as if
        # the branch doesn't exist.

        # 'salgado' is a member of landscape-developers.
        salgado = Person.selectOneBy(name='salgado')
        landscape_dev = Person.selectOneBy(
            name='landscape-developers')
        self.assertTrue(
            salgado.inTeam(landscape_dev),
            "salgado should be a member of landscape-developers, but isn't.")

        # Make a private branch.
        branch_url = self.createBazaarBranch(
            'landscape-developers', 'landscape', 'some-branch',
            creator='salgado')
        # Sanity checking that the branch is actually there. We don't care
        # about the result, only that the call succeeds.
        self.getLastRevision(branch_url)

        # Check that testuser can't access the branch.
        remote_url = self.getTransportURL(
            '~landscape-developers/landscape/some-branch')
        self.assertNotBranch(remote_url)

    def test_push_to_new_full_branch_alias(self):
        # We can also push branches to URLs like /+branch/~foo/bar/baz.
        unique_name = '~testuser/firefox/new-branch'
        remote_url = self.getTransportURL('+branch/%s' % unique_name)
        self.push(self.local_branch_path, remote_url)
        self.assertBranchesMatch(self.local_branch_path, remote_url)
        self.assertBranchesMatch(
            self.local_branch_path, self.getTransportURL(unique_name))

    def test_push_to_new_short_branch_alias(self):
        # We can also push branches to URLs like /+branch/firefox
        # Hack 'firefox' so we have permission to do this.
        ZopelessAppServerLayer.txn.begin()
        firefox = Product.selectOneBy(name='firefox')
        testuser = Person.selectOneBy(name='testuser')
        firefox.development_focus.owner = testuser
        ZopelessAppServerLayer.txn.commit()
        remote_url = self.getTransportURL('+branch/firefox')
        self.push(self.local_branch_path, remote_url)
        self.assertBranchesMatch(self.local_branch_path, remote_url)

    def test_can_push_to_existing_hosted_branch(self):
        # If a hosted branch exists in the database, but not on the
        # filesystem, and is writable by the user, then the user is able to
        # push to it.
        ZopelessAppServerLayer.txn.begin()
        branch = self.makeDatabaseBranch('testuser', 'firefox', 'some-branch')
        remote_url = self.getTransportURL(branch.unique_name)
        ZopelessAppServerLayer.txn.commit()
        self.push(
            self.local_branch_path, remote_url,
            extra_args=['--use-existing-dir'])
        self.assertBranchesMatch(self.local_branch_path, remote_url)

    def test_cant_push_to_existing_mirrored_branch(self):
        # Users cannot push to mirrored branches.
        ZopelessAppServerLayer.txn.begin()
        branch = self.makeDatabaseBranch(
            'testuser', 'firefox', 'some-branch', BranchType.MIRRORED)
        remote_url = self.getTransportURL(branch.unique_name)
        ZopelessAppServerLayer.txn.commit()
        self.assertCantPush(
            self.local_branch_path, remote_url,
            ['Permission denied:', 'Transport operation not possible:'])

    def test_cant_push_to_existing_unowned_hosted_branch(self):
        # Users can only push to hosted branches that they own.
        ZopelessAppServerLayer.txn.begin()
        branch = self.makeDatabaseBranch('mark', 'firefox', 'some-branch')
        remote_url = self.getTransportURL(branch.unique_name)
        ZopelessAppServerLayer.txn.commit()
        self.assertCantPush(
            self.local_branch_path, remote_url,
            ['Permission denied:', 'Transport operation not possible:'])

    def test_push_new_branch_of_non_existant_source_package_name(self):
        ZopelessAppServerLayer.txn.begin()
        unique_name = get_non_existant_source_package_branch_unique_name(
            'testuser', self.factory)
        ZopelessAppServerLayer.txn.commit()
        remote_url = self.getTransportURL(unique_name)
        self.push(self.local_branch_path, remote_url)
        self.assertBranchesMatch(self.local_branch_path, remote_url)

    def test_can_push_loom_branch(self):
        # We can push and pull a loom branch.
        self.makeLoomBranchAndTree('loom')
        remote_url = self.getTransportURL('~testuser/+junk/loom')
        self.push('loom', remote_url)
        self.assertBranchesMatch('loom', remote_url)


class SmartserverTests(SSHTestCase):
    """Acceptance tests for the codehosting smartserver."""

    def makeMirroredBranch(self, person_name, product_name, branch_name):
        ro_branch_url = self.createBazaarBranch(
            person_name, product_name, branch_name)

        # Mark as mirrored.
        ZopelessAppServerLayer.txn.begin()
        branch = self.getDatabaseBranch(
            person_name, product_name, branch_name)
        branch.branch_type = BranchType.MIRRORED
        branch.url = "http://example.com/smartservertest/branch"
        ZopelessAppServerLayer.txn.commit()
        return ro_branch_url

    def test_can_read_readonly_branch(self):
        # We can get information from a read-only branch.
        ro_branch_url = self.createBazaarBranch(
            'mark', '+junk', 'ro-branch')
        revision = bzrlib.branch.Branch.open(ro_branch_url).last_revision()
        remote_revision = self.getLastRevision(
            self.getTransportURL('~mark/+junk/ro-branch'))
        self.assertEqual(revision, remote_revision)

    def test_cant_write_to_readonly_branch(self):
        # We can't write to a read-only branch.
        self.createBazaarBranch('mark', '+junk', 'ro-branch')

        # Create a new revision on the local branch.
        tree = WorkingTree.open(self.local_branch.base)
        tree.commit('Empty commit', rev_id='rev2')

        # Push the local branch to the remote url
        remote_url = self.getTransportURL('~mark/+junk/ro-branch')
        self.assertCantPush(self.local_branch_path, remote_url)

    def test_can_read_mirrored_branch(self):
        # Users should be able to read mirrored branches that they own.
        # Added to catch bug 126245.
        ro_branch_url = self.makeMirroredBranch(
            'testuser', 'firefox', 'mirror')
        revision = bzrlib.branch.Branch.open(ro_branch_url).last_revision()
        remote_revision = self.getLastRevision(
            self.getTransportURL('~testuser/firefox/mirror'))
        self.assertEqual(revision, remote_revision)

    def test_can_read_unowned_mirrored_branch(self):
        # Users should be able to read mirrored branches even if they don't
        # own those branches.
        ro_branch_url = self.makeMirroredBranch('mark', 'firefox', 'mirror')
        revision = bzrlib.branch.Branch.open(ro_branch_url).last_revision()
        remote_revision = self.getLastRevision(
            self.getTransportURL('~mark/firefox/mirror'))
        self.assertEqual(revision, remote_revision)

    def test_authserver_error_propagation(self):
        # Errors raised by createBranch in the XML-RPC server should be
        # displayed sensibly by the client.  We test this by pushing to a
        # product that does not exist (the other error message possibilities
        # are covered by unit tests).
        remote_url = self.getTransportURL('~mark/no-such-product/branch')
        message = "Project 'no-such-product' does not exist."
        last_line = self.assertCantPush(self.local_branch_path, remote_url)
        self.assertTrue(
            message in last_line, '%r not in %r' % (message, last_line))

    def test_web_status_available(self):
        # There is an HTTP service that reports whether the SSH server is
        # available for new connections.
        # Munge the config value in strport format into a URL.
        self.assertEqual('tcp:', config.codehosting.web_status_port[:4])
        port = int(config.codehosting.web_status_port[4:])
        web_status_url = 'http://localhost:%d/' % port
        urllib2.urlopen(web_status_url)


def make_server_tests(base_suite, servers):
    from lp.codehosting.tests.helpers import (
        CodeHostingTestProviderAdapter)
    adapter = CodeHostingTestProviderAdapter(servers)
    return adapt_suite(adapter, base_suite)


def make_smoke_tests(base_suite):
    from bzrlib.tests.per_repository import (
        all_repository_format_scenarios,
        )
    excluded_scenarios = [
        # RepositoryFormat4 is not initializable (bzrlib raises TestSkipped
        # when you try).
        'RepositoryFormat4',
        # Fetching weave formats from the smart server is known to be broken.
        # See bug 173807 and bzrlib.tests.test_repository.
        'RepositoryFormat5',
        'RepositoryFormat6',
        'RepositoryFormat7',
        'GitRepositoryFormat',
        'SvnRepositoryFormat',
        ]
    scenarios = all_repository_format_scenarios()
    scenarios = [
        scenario for scenario in scenarios
        if scenario[0] not in excluded_scenarios
        and not scenario[0].startswith('RemoteRepositoryFormat')]
    new_suite = unittest.TestSuite()
    multiply_tests(base_suite, scenarios, new_suite)
    return new_suite


def test_suite():
    base_suite = unittest.makeSuite(AcceptanceTests)
    suite = unittest.TestSuite()

    suite.addTest(make_server_tests(base_suite, ['sftp', 'bzr+ssh']))
    suite.addTest(make_server_tests(
            unittest.makeSuite(SmartserverTests), ['bzr+ssh']))
    suite.addTest(make_smoke_tests(unittest.makeSuite(SmokeTest)))
    return suite
