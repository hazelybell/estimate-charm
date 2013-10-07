# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""End-to-end tests for the branch puller."""

__metaclass__ = type
__all__ = []


import os
from subprocess import (
    PIPE,
    Popen,
    )

from bzrlib import errors
from bzrlib.branch import Branch
from bzrlib.bzrdir import BzrDir
from bzrlib.upgrade import upgrade
from bzrlib.urlutils import (
    join as urljoin,
    local_path_from_url,
    )
from bzrlib.workingtree import WorkingTree
from fixtures import TempDir
import transaction
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.code.enums import BranchType
from lp.code.interfaces.branchtarget import IBranchTarget
from lp.codehosting.puller.tests import PullerBranchTestCase
from lp.codehosting.tests.helpers import LoomTestMixin
from lp.codehosting.vfs import get_lp_server
from lp.services.config import config
from lp.services.scripts.interfaces.scriptactivity import IScriptActivitySet
from lp.testing.layers import ZopelessAppServerLayer


class TestBranchPuller(PullerBranchTestCase, LoomTestMixin):
    """Integration tests for the branch puller.

    These tests actually run the supermirror-pull.py script. Instead of
    checking specific behaviour, these tests help ensure that all of the
    components in the branch puller system work together sanely.
    """

    layer = ZopelessAppServerLayer

    def setUp(self):
        PullerBranchTestCase.setUp(self)
        self._puller_script = os.path.join(
            config.root, 'cronscripts', 'supermirror-pull.py')
        self.makeCleanDirectory(config.codehosting.mirrored_branches_root)
        self.makeCleanDirectory(
            local_path_from_url(config.launchpad.bzr_imports_root_url))

    def assertMirrored(self, db_branch, source_branch):
        """Assert that 'db_branch' was mirrored succesfully.

        This method checks that the fields on db_branch show that the branch
        has been mirrored successfully, and checks that the Bazaar source and
        destination branches (from the puller's point of view) are consistent
        with this and each other.

        :param db_branch: The `IBranch` representing the branch that was
            mirrored.
        :param source_branch: The source branch.  If not passed, look for the
            branch in the hosted area.
        :param accessing_user: Open the mirrored branch as this user.  If not
            supplied create a fresh user for this -- but this won't work for a
            private branch.
        """
        accessing_user = self.factory.makePerson()
        transaction.commit()
        self.assertEqual(None, db_branch.mirror_status_message)
        self.assertEqual(
            db_branch.last_mirror_attempt, db_branch.last_mirrored)
        self.assertEqual(0, db_branch.mirror_failures)
        mirrored_branch = self.openBranchAsUser(db_branch, accessing_user)
        self.assertEqual(
            source_branch.last_revision(), db_branch.last_mirrored_id)
        self.assertEqual(
            source_branch.last_revision(), mirrored_branch.last_revision())
        self.assertEqual(
            source_branch._format.__class__,
            mirrored_branch._format.__class__)
        self.assertEqual(
            source_branch.repository._format.__class__,
            mirrored_branch.repository._format.__class__)
        return mirrored_branch

    def assertRanSuccessfully(self, command, retcode, stdout, stderr):
        """Assert that the command ran successfully.

        'Successfully' means that it's return code was 0 and it printed
        nothing to stdout or stderr.
        """
        message = '\n'.join(
            ['Command: %r' % (command,),
             'Return code: %s' % retcode,
             'Output:',
             stdout,
             '',
             'Error:',
             stderr])
        self.assertEqual(0, retcode, message)
        self.assertEqualDiff('', stdout)
        self.assertEqualDiff('', stderr)

    def runSubprocess(self, command):
        """Run the given command in a subprocess.

        :param command: A command and arguments given as a list.
        :return: retcode, stdout, stderr
        """
        process = Popen(command, stdout=PIPE, stderr=PIPE)
        output, error = process.communicate()
        return process.returncode, output, error

    def runPuller(self, *args):
        """Run the puller script for the given branch type.

        :param branch_type: One of 'upload', 'mirror' or 'import'
        :return: Tuple of command, retcode, output, error. 'command' is the
            executed command as a list, retcode is the process's return code,
            output and error are strings contain the output of the process to
            stdout and stderr respectively.
        """
        tempdir = self.useFixture(TempDir()).path
        logfile = os.path.join(tempdir, "supermirror_test.log")
        command = [
            '%s/bin/py' % config.root, self._puller_script, '--log-file',
            logfile, '-q'] + list(args)
        retcode, output, error = self.runSubprocess(command)
        return command, retcode, output, error

    def getLPServerForUser(self, user):
        """Construct a LaunchpadServer that serves branches as seen by `user`.

        Given 'db_branch', a database branch object 'db_branch', and
        'lp_server', the server returned by this method,
        'Branch.open(lp_server.get_url() + db_branch.unique_name)' will open
        the branch as 'user' sees it as a client of the code hosting service,
        i.e. it will be opened from the hosting area if the branch type HOSTED
        and the user has launchpad.Edit on the branch and opened from the
        mirrored area otherwise.
        """
        # We use the configured directories because these tests run the puller
        # in a subprocess which would have no way of knowing which directories
        # to look in if we used freshly created temporary directories.
        lp_server = get_lp_server(user.id)
        lp_server.start_server()
        self.addCleanup(lp_server.stop_server)
        return lp_server

    def openBranchAsUser(self, db_branch, user):
        """Open the branch as 'user' would see it as a client of codehosting.
        """
        lp_server = self.getLPServerForUser(user)
        return Branch.open(lp_server.get_url() + db_branch.unique_name)

    def setUpMirroredBranch(self, db_branch, format=None):
        """Make a tree in the cwd and serve it over HTTP, returning the URL.
        """
        tree = self.make_branch_and_tree('.', format=format)
        tree.commit('rev1')
        db_branch.url = self.serveOverHTTP()
        db_branch.requestMirror()
        return tree

    def test_mirror_mirrored_branch(self):
        # Run the puller with a mirrored branch ready to be pulled.
        db_branch = self.factory.makeAnyBranch(
            branch_type=BranchType.MIRRORED)
        tree = self.setUpMirroredBranch(db_branch)
        transaction.commit()
        command, retcode, output, error = self.runPuller()
        self.assertRanSuccessfully(command, retcode, output, error)
        self.assertMirrored(db_branch, source_branch=tree.branch)

    def test_mirror_mirrored_loom_branch(self):
        # Run the puller with a mirrored loom branch ready to be pulled.
        db_branch = self.factory.makeAnyBranch(
            branch_type=BranchType.MIRRORED)
        tree = self.setUpMirroredBranch(db_branch)
        self.loomify(tree.branch)
        transaction.commit()
        command, retcode, output, error = self.runPuller()
        self.assertRanSuccessfully(command, retcode, output, error)
        self.assertMirrored(db_branch, source_branch=tree.branch)

    def test_format_change(self):
        # When the format of a mirrored branch changes, the puller remirrors
        # the branch into the new format.
        db_branch = self.factory.makeAnyBranch(
            branch_type=BranchType.MIRRORED)
        tree = self.setUpMirroredBranch(db_branch, format='pack-0.92')
        transaction.commit()
        command, retcode, output, error = self.runPuller()
        self.assertRanSuccessfully(command, retcode, output, error)
        self.assertMirrored(db_branch, source_branch=tree.branch)
        transaction.begin()
        db_branch.requestMirror()
        upgrade(tree.basedir)
        tree = WorkingTree.open(tree.basedir)
        transaction.commit()
        command, retcode, output, error = self.runPuller()
        self.assertRanSuccessfully(command, retcode, output, error)
        self.assertMirrored(db_branch, source_branch=tree.branch)

    def _makeDefaultStackedOnBranch(self, private=False):
        """Make a default stacked-on branch.

        This creates a database product branch, makes it the default
        stacked-on branch for its product and creates a Bazaar branch for it.

        :param private: Whether the created branch should be private or not
            (defaults to not).
        :return: `IBranch`.
        """
        # Make the branch in the database.
        product = self.factory.makeProduct()
        if private:
            information_type = InformationType.USERDATA
        else:
            information_type = InformationType.PUBLIC
        default_branch = self.factory.makeProductBranch(
            product=product, information_type=information_type)
        transaction.commit()
        # Create the underlying bzr branch.
        lp_server = self.getLPServerForUser(default_branch.owner)
        BzrDir.create_branch_convenience(
            lp_server.get_url() + default_branch.unique_name)
        transaction.commit()
        # Make it the default stacked-on branch for the product.
        series = removeSecurityProxy(product.development_focus)
        series.branch = default_branch
        self.assertEqual(
            default_branch, IBranchTarget(product).default_stacked_on_branch)
        return default_branch

    def test_stack_mirrored_branch(self):
        # Pulling a mirrored branch stacks that branch on the default stacked
        # branch of the product if such a thing exists.
        default_branch = self._makeDefaultStackedOnBranch()
        db_branch = self.factory.makeProductBranch(
            branch_type=BranchType.MIRRORED, product=default_branch.product)
        tree = self.setUpMirroredBranch(db_branch)
        transaction.commit()
        command, retcode, output, error = self.runPuller()
        self.assertRanSuccessfully(command, retcode, output, error)
        mirrored_branch = self.assertMirrored(
            db_branch, source_branch=tree.branch)
        self.assertEqual(
            '/' + default_branch.unique_name,
            mirrored_branch.get_stacked_on_url())

    def test_stack_mirrored_branch_onto_private(self):
        # If the default stacked-on branch is private then mirrored branches
        # aren't stacked when they are mirrored.
        default_branch = self._makeDefaultStackedOnBranch(private=True)
        db_branch = self.factory.makeProductBranch(
            branch_type=BranchType.MIRRORED, product=default_branch.product)

        tree = self.setUpMirroredBranch(db_branch)
        transaction.commit()
        command, retcode, output, error = self.runPuller()
        self.assertRanSuccessfully(command, retcode, output, error)
        mirrored_branch = self.assertMirrored(
            db_branch, source_branch=tree.branch)
        self.assertRaises(
            errors.NotStacked, mirrored_branch.get_stacked_on_url)

    def test_mirror_imported_branch(self):
        # Run the puller on a populated imported branch pull queue.
        # Create the branch in the database.
        db_branch = self.factory.makeAnyBranch(
            branch_type=BranchType.IMPORTED)
        db_branch.requestMirror()
        transaction.commit()

        # Create the Bazaar branch in the expected location.
        branch_url = urljoin(
            config.launchpad.bzr_imports_root_url, '%08x' % db_branch.id)
        branch = BzrDir.create_branch_convenience(branch_url)
        tree = branch.bzrdir.open_workingtree()
        tree.commit('rev1')

        transaction.commit()

        # Run the puller.
        command, retcode, output, error = self.runPuller()
        self.assertRanSuccessfully(command, retcode, output, error)

        self.assertMirrored(db_branch, source_branch=branch)

    def test_mirror_empty(self):
        # Run the puller on an empty pull queue.
        command, retcode, output, error = self.runPuller()
        self.assertRanSuccessfully(command, retcode, output, error)

    def test_type_filtering(self):
        # When run with --branch-type arguments, the puller only mirrors those
        # branches of the specified types.
        imported_branch = self.factory.makeAnyBranch(
            branch_type=BranchType.IMPORTED)
        imported_branch.requestMirror()
        mirrored_branch = self.factory.makeAnyBranch(
            branch_type=BranchType.MIRRORED)
        mirrored_branch.requestMirror()
        tree = self.setUpMirroredBranch(mirrored_branch)

        transaction.commit()

        command, retcode, output, error = self.runPuller(
            '--branch-type', 'MIRRORED')
        self.assertRanSuccessfully(command, retcode, output, error)
        self.assertMirrored(mirrored_branch, source_branch=tree.branch)
        self.assertIsNot(
            None, imported_branch.next_mirror_time)

    def test_records_script_activity(self):
        # A record gets created in the ScriptActivity table.
        script_activity_set = getUtility(IScriptActivitySet)
        self.assertIs(
            script_activity_set.getLastActivity("branch-puller"),
            None)
        self.runPuller()
        transaction.abort()
        self.assertIsNot(
            script_activity_set.getLastActivity("branch-puller"),
            None)

    # Possible tests to add:
    # - branch already exists in new location
    # - branch doesn't exist in fs?
    # - different branch exists in new location
    # - running puller while another puller is running
    # - expected output on non-quiet runs
