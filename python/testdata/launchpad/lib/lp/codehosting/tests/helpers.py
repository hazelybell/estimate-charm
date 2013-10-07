# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Common helpers for codehosting tests."""

__metaclass__ = type
__all__ = [
    'AvatarTestCase',
    'adapt_suite',
    'CodeHostingTestProviderAdapter',
    'create_branch_with_one_revision',
    'deferToThread',
    'force_stacked_on_url',
    'LoomTestMixin',
    'make_bazaar_branch_and_tree',
    'TestResultWrapper',
    ]

import os
import threading
import unittest

from bzrlib.bzrdir import BzrDir
from bzrlib.errors import FileExists
from bzrlib.plugins.loom import branch as loom_branch
from bzrlib.tests import (
    TestNotApplicable,
    TestSkipped,
    )
from testtools.deferredruntest import AsynchronousDeferredRunTest
from twisted.internet import (
    defer,
    threads,
    )
from twisted.python.util import mergeFunctionMetadata

from lp.code.enums import BranchType
from lp.codehosting.vfs import branch_id_to_path
from lp.services.config import config
from lp.testing import TestCase


class AvatarTestCase(TestCase):
    """Base class for tests that need a LaunchpadAvatar with some basic sample
    data.
    """

    run_tests_with = AsynchronousDeferredRunTest

    def setUp(self):
        super(AvatarTestCase, self).setUp()
        # A basic user dict, 'alice' is a member of no teams (aside from the
        # user themself).
        self.aliceUserDict = {
            'id': 1,
            'name': 'alice',
            'teams': [{'id': 1, 'name': 'alice'}],
            'initialBranches': [(1, [])]
        }

        # An slightly more complex user dict for a user, 'bob', who is also a
        # member of a team.
        self.bobUserDict = {
            'id': 2,
            'name': 'bob',
            'teams': [{'id': 2, 'name': 'bob'},
                      {'id': 3, 'name': 'test-team'}],
            'initialBranches': [(2, []), (3, [])]
        }


class LoomTestMixin:
    """Mixin to provide Bazaar test classes with limited loom support."""

    def loomify(self, branch):
        tree = branch.create_checkout('checkout')
        tree.lock_write()
        try:
            tree.branch.nick = 'bottom-thread'
            loom_branch.loomify(tree.branch)
        finally:
            tree.unlock()
        loom_tree = tree.bzrdir.open_workingtree()
        loom_tree.lock_write()
        loom_tree.branch.new_thread('bottom-thread')
        loom_tree.commit('this is a commit', rev_id='commit-1')
        loom_tree.unlock()
        loom_tree.branch.record_loom('sample loom')
        self.get_transport().delete_tree('checkout')
        return loom_tree

    def makeLoomBranchAndTree(self, tree_directory):
        """Make a looms-enabled branch and working tree."""
        tree = self.make_branch_and_tree(tree_directory)
        tree.lock_write()
        try:
            tree.branch.nick = 'bottom-thread'
            loom_branch.loomify(tree.branch)
        finally:
            tree.unlock()
        loom_tree = tree.bzrdir.open_workingtree()
        loom_tree.lock_write()
        loom_tree.branch.new_thread('bottom-thread')
        loom_tree.commit('this is a commit', rev_id='commit-1')
        loom_tree.unlock()
        loom_tree.branch.record_loom('sample loom')
        return loom_tree


def deferToThread(f):
    """Run the given callable in a separate thread and return a Deferred which
    fires when the function completes.
    """
    def decorated(*args, **kwargs):
        d = defer.Deferred()

        def runInThread():
            return threads._putResultInDeferred(d, f, args, kwargs)

        t = threading.Thread(target=runInThread)
        t.start()
        return d
    return mergeFunctionMetadata(f, decorated)


def clone_test(test, new_id):
    """Return a clone of the given test."""
    from copy import deepcopy
    new_test = deepcopy(test)

    def make_new_test_id():
        return lambda: new_id

    new_test.id = make_new_test_id()
    return new_test


class CodeHostingTestProviderAdapter:
    """Test adapter to run a single test against many codehosting servers."""

    def __init__(self, schemes):
        self._schemes = schemes

    def adaptForServer(self, test, scheme):
        new_test = clone_test(test, '%s(%s)' % (test.id(), scheme))
        new_test.scheme = scheme
        return new_test

    def adapt(self, test):
        result = unittest.TestSuite()
        for scheme in self._schemes:
            new_test = self.adaptForServer(test, scheme)
            result.addTest(new_test)
        return result


def make_bazaar_branch_and_tree(db_branch):
    """Make a dummy Bazaar branch and working tree from a database Branch."""
    assert db_branch.branch_type == BranchType.HOSTED, (
        "Can only create branches for HOSTED branches: %r"
        % db_branch)
    branch_dir = os.path.join(
        config.codehosting.mirrored_branches_root,
        branch_id_to_path(db_branch.id))
    return create_branch_with_one_revision(branch_dir)


def adapt_suite(adapter, base_suite):
    from bzrlib.tests import iter_suite_tests
    suite = unittest.TestSuite()
    for test in iter_suite_tests(base_suite):
        suite.addTests(adapter.adapt(test))
    return suite


def create_branch_with_one_revision(branch_dir, format=None):
    """Create a dummy Bazaar branch at the given directory."""
    if not os.path.exists(branch_dir):
        os.makedirs(branch_dir)
    try:
        tree = BzrDir.create_standalone_workingtree(branch_dir, format)
    except FileExists:
        return
    f = open(os.path.join(branch_dir, 'hello'), 'w')
    f.write('foo')
    f.close()
    tree.commit('message')
    return tree


def force_stacked_on_url(branch, url):
    """Set the stacked_on url of a branch without standard error-checking.

    Bazaar 1.17 and up make it harder to create branches with invalid
    stacking.  It's still worth testing that we don't blow up in the face of
    them, so this function lets us create them anyway.
    """
    branch.get_config().set_user_option('stacked_on_location', url)


class TestResultWrapper:
    """A wrapper for `TestResult` that knows about bzrlib's `TestSkipped`."""

    def __init__(self, result):
        self.result = result

    def addError(self, test_case, exc_info):
        if isinstance(exc_info[1], (TestSkipped, TestNotApplicable)):
            # If Bazaar says the test was skipped, or that it wasn't
            # applicable to this environment, then treat that like a success.
            # After all, it's not exactly an error, is it?
            self.result.addSuccess(test_case)
        else:
            self.result.addError(test_case, exc_info)

    def addFailure(self, test_case, exc_info):
        self.result.addFailure(test_case, exc_info)

    def addSuccess(self, test_case):
        self.result.addSuccess(test_case)

    def startTest(self, test_case):
        self.result.startTest(test_case)

    def stopTest(self, test_case):
        self.result.stopTest(test_case)
