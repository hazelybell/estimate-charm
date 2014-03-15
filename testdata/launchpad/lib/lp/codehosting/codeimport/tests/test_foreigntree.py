# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for foreign branch support."""

__metaclass__ = type

import os
import time

from bzrlib.tests import TestCaseWithTransport
import CVS
import subvertpy.client
import subvertpy.ra
import subvertpy.wc

from lp.codehosting.codeimport.foreigntree import (
    CVSWorkingTree,
    SubversionWorkingTree,
    )
from lp.codehosting.codeimport.tests.servers import (
    CVSServer,
    SubversionServer,
    )
from lp.testing.layers import BaseLayer


class TestSubversionWorkingTree(TestCaseWithTransport):

    layer = BaseLayer

    def assertIsUpToDate(self, original_url, new_path):
        """Assert that a Subversion working tree is up to date.

        :param original_url: The URL of the Subversion branch.
        :param new_path: The path of the checkout.
        """
        working_copy = subvertpy.wc.WorkingCopy(None, new_path)
        entry = working_copy.entry(new_path)

        remote = subvertpy.ra.RemoteAccess(original_url)
        self.assertEqual(original_url, entry.url)
        self.assertEqual(entry.revision, remote.get_latest_revnum())

    def setUp(self):
        super(TestSubversionWorkingTree, self).setUp()
        svn_server = SubversionServer('repository_path')
        svn_server.start_server()
        self.addCleanup(svn_server.stop_server)
        self.svn_branch_url = svn_server.makeBranch(
            'trunk', [('README', 'original')])

    def test_path(self):
        # The local path is passed to the constructor is available as
        # 'local_path'.
        tree = SubversionWorkingTree('url', 'path')
        self.assertEqual(tree.local_path, 'path')

    def test_url(self):
        # The URL of the repository is available as 'remote_url'.
        tree = SubversionWorkingTree('url', 'path')
        self.assertEqual(tree.remote_url, 'url')

    def test_checkout(self):
        # checkout() checks out an up-to-date working tree to the local path.
        tree = SubversionWorkingTree(self.svn_branch_url, 'tree')
        tree.checkout()
        self.assertIsUpToDate(self.svn_branch_url, tree.local_path)

    def test_update(self):
        # update() fetches any changes to the branch from the remote branch.
        # We test this by checking out the same branch twice, making
        # modifications in one, then updating the other. If the modifications
        # appear, then update() works.
        tree = SubversionWorkingTree(self.svn_branch_url, 'tree')
        tree.checkout()

        tree2 = SubversionWorkingTree(self.svn_branch_url, 'tree2')
        tree2.checkout()

        # Make a change.
        # XXX: JonathanLange 2008-02-19: "README" is a mystery guest.
        new_content = 'Comfort ye\n'
        self.build_tree_contents([('tree/README', new_content)])
        tree.commit()

        tree2.update()
        readme_path = os.path.join(tree2.local_path, 'README')
        self.assertFileEqual(new_content, readme_path)

    def test_update_ignores_externals(self):
        # update() ignores svn:externals.
        # We test this in a similar way to test_update, by getting two trees,
        # mutating one and checking its effect on the other tree -- though
        # here we are hoping for no effect.
        tree = SubversionWorkingTree(self.svn_branch_url, 'tree')
        tree.checkout()

        tree2 = SubversionWorkingTree(self.svn_branch_url, 'tree2')
        tree2.checkout()

        client = subvertpy.client.Client()
        client.propset(
            'svn:externals', 'external http://foo.invalid/svn/something',
            tree.local_path)
        tree.commit()

        tree2.update()


class TestCVSWorkingTree(TestCaseWithTransport):

    layer = BaseLayer

    def assertHasCheckout(self, cvs_working_tree):
        """Assert that `cvs_working_tree` has a checkout of its CVS module."""
        tree = CVS.tree(os.path.abspath(cvs_working_tree.local_path))
        repository = tree.repository()
        self.assertEqual(repository.root, cvs_working_tree.root)
        self.assertEqual(tree.module().name(), cvs_working_tree.module)

    def makeCVSWorkingTree(self, local_path):
        """Make a CVS working tree for testing."""
        return CVSWorkingTree(
            self.cvs_server.getRoot(), self.module_name, local_path)

    def setUp(self):
        super(TestCVSWorkingTree, self).setUp()
        self.cvs_server = CVSServer('repository_path')
        self.cvs_server.start_server()
        self.module_name = 'test_module'
        self.cvs_server.makeModule(
            self.module_name, [('README', 'Random content\n')])
        self.addCleanup(self.cvs_server.stop_server)

    def test_path(self):
        # The local path is passed to the constructor and available as
        # 'local_path'.
        tree = CVSWorkingTree('root', 'module', 'path')
        self.assertEqual(tree.local_path, os.path.abspath('path'))

    def test_module(self):
        # The module is passed to the constructor and available as 'module'.
        tree = CVSWorkingTree('root', 'module', 'path')
        self.assertEqual(tree.module, 'module')

    def test_root(self):
        # The root is passed to the constructor and available as 'root'.
        tree = CVSWorkingTree('root', 'module', 'path')
        self.assertEqual(tree.root, 'root')

    def test_checkout(self):
        # checkout() checks out an up-to-date working tree.
        tree = self.makeCVSWorkingTree('working_tree')
        tree.checkout()
        self.assertHasCheckout(tree)

    def test_commit(self):
        # commit() makes local changes available to other checkouts.
        tree = self.makeCVSWorkingTree('working_tree')
        tree.checkout()

        # If you write to a file in the same second as the previous commit,
        # CVS will not think that it has changed.
        time.sleep(1)

        # Make a change.
        new_content = 'Comfort ye\n'
        readme = open(os.path.join(tree.local_path, 'README'), 'w')
        readme.write(new_content)
        readme.close()
        self.assertFileEqual(new_content, 'working_tree/README')

        # Commit the change.
        tree.commit()

        tree2 = self.makeCVSWorkingTree('working_tree2')
        tree2.checkout()

        self.assertFileEqual(new_content, 'working_tree2/README')

    def test_update(self):
        # update() fetches any changes to the branch from the remote branch.
        # We test this by checking out the same branch twice, making
        # modifications in one, then updating the other. If the modifications
        # appear, then update() works.
        tree = self.makeCVSWorkingTree('working_tree')
        tree.checkout()

        tree2 = self.makeCVSWorkingTree('working_tree2')
        tree2.checkout()

        # If you write to a file in the same second as the previous commit,
        # CVS will not think that it has changed.
        time.sleep(1)

        # Make a change.
        new_content = 'Comfort ye\n'
        self.build_tree_contents([('working_tree/README', new_content)])

        # Commit the change.
        tree.commit()

        # Update.
        tree2.update()
        readme_path = os.path.join(tree2.local_path, 'README')
        self.assertFileEqual(new_content, readme_path)
