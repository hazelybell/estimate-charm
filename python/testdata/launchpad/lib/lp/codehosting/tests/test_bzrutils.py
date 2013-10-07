# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for bzrutils."""

__metaclass__ = type

import gc
import sys

from bzrlib import (
    errors,
    trace,
    )
from bzrlib.branch import Branch
from bzrlib.bzrdir import format_registry
from bzrlib.errors import AppendRevisionsOnlyViolation
from bzrlib.remote import RemoteBranch
from bzrlib.tests import (
    multiply_tests,
    test_server,
    TestCaseWithTransport,
    TestLoader,
    TestNotApplicable,
    )
from bzrlib.tests.per_branch import (
    branch_scenarios,
    TestCaseWithControlDir,
    )

from lp.codehosting.bzrutils import (
    add_exception_logging_hook,
    DenyingServer,
    get_branch_stacked_on_url,
    get_vfs_format_classes,
    install_oops_handler,
    is_branch_stackable,
    remove_exception_logging_hook,
    )
from lp.codehosting.tests.helpers import TestResultWrapper
from lp.testing import TestCase


class TestGetBranchStackedOnURL(TestCaseWithControlDir):
    """Tests for get_branch_stacked_on_url()."""

    def __str__(self):
        """Return the test id so that Zope test output shows the format."""
        return self.id()

    def tearDown(self):
        # This makes sure the connections held by the branches opened in the
        # test are dropped, so the daemon threads serving those branches can
        # exit.
        gc.collect()
        TestCaseWithControlDir.tearDown(self)

    def run(self, result=None):
        """Run the test, with the result wrapped so that it knows about skips.
        """
        if result is None:
            result = self.defaultTestResult()
        super(TestGetBranchStackedOnURL, self).run(TestResultWrapper(result))

    def testGetBranchStackedOnUrl(self):
        # get_branch_stacked_on_url returns the URL of the stacked-on branch.
        self.make_branch('stacked-on')
        stacked_branch = self.make_branch('stacked')
        try:
            stacked_branch.set_stacked_on_url('../stacked-on')
        except errors.UnstackableBranchFormat:
            raise TestNotApplicable('This format does not support stacking.')
        # Deleting the stacked-on branch ensures that Bazaar will raise an
        # error if it tries to open the stacked-on branch.
        self.get_transport('.').delete_tree('stacked-on')
        self.assertEqual(
            '../stacked-on',
            get_branch_stacked_on_url(stacked_branch.bzrdir))

    def testGetBranchStackedOnUrlUnstackable(self):
        # get_branch_stacked_on_url raises UnstackableBranchFormat if it's
        # called on the bzrdir of a branch that cannot be stacked.
        branch = self.make_branch('source')
        try:
            branch.get_stacked_on_url()
        except errors.NotStacked:
            raise TestNotApplicable('This format supports stacked branches.')
        except errors.UnstackableBranchFormat:
            pass
        self.assertRaises(
            errors.UnstackableBranchFormat,
            get_branch_stacked_on_url, branch.bzrdir)

    def testGetBranchStackedOnUrlNotStacked(self):
        # get_branch_stacked_on_url raises NotStacked if it's called on the
        # bzrdir of a non-stacked branch.
        branch = self.make_branch('source')
        try:
            branch.get_stacked_on_url()
        except errors.NotStacked:
            pass
        except errors.UnstackableBranchFormat:
            raise TestNotApplicable(
                'This format does not support stacked branches')
        self.assertRaises(
            errors.NotStacked, get_branch_stacked_on_url, branch.bzrdir)

    def testGetBranchStackedOnUrlNoBranch(self):
        # get_branch_stacked_on_url raises a NotBranchError if it's called on
        # a bzrdir that's not got a branch.
        a_bzrdir = self.make_bzrdir('source')
        if a_bzrdir.has_branch():
            raise TestNotApplicable(
                'This format does not support branchless bzrdirs.')
        self.assertRaises(
            errors.NotBranchError, get_branch_stacked_on_url, a_bzrdir)


class TestIsBranchStackable(TestCaseWithTransport):
    """Tests for is_branch_stackable."""

    def test_packs_unstackable(self):
        # The original packs are unstackable.
        branch = self.make_branch(
            'branch', format=format_registry.get("pack-0.92")())
        self.assertFalse(is_branch_stackable(branch))

    def test_1_9_stackable(self):
        # The original packs are unstackable.
        branch = self.make_branch(
            'branch', format=format_registry.get("1.9")())
        self.assertTrue(is_branch_stackable(branch))


class TestDenyingServer(TestCaseWithTransport):
    """Tests for `DenyingServer`."""

    def test_denyingServer(self):
        # DenyingServer prevents creations of transports for the given URL
        # schemes between setUp() and tearDown().
        branch = self.make_branch('branch')
        self.assertTrue(
            branch.base.startswith('file://'),
            "make_branch() didn't make branch with file:// URL")
        file_denier = DenyingServer(['file://'])
        file_denier.start_server()
        self.assertRaises(AssertionError, Branch.open, branch.base)
        file_denier.stop_server()
        # This is just "assertNotRaises":
        Branch.open(branch.base)


class TestExceptionLoggingHooks(TestCase):

    def logException(self, exception):
        """Log exception with Bazaar's exception logger."""
        try:
            raise exception
        except exception.__class__:
            trace.log_exception_quietly()

    def test_calls_hook_when_added(self):
        # add_exception_logging_hook adds a hook function that's called
        # whenever Bazaar logs an exception.
        exceptions = []

        def hook():
            exceptions.append(sys.exc_info()[:2])

        add_exception_logging_hook(hook)
        self.addCleanup(remove_exception_logging_hook, hook)
        exception = RuntimeError('foo')
        self.logException(exception)
        self.assertEqual([(RuntimeError, exception)], exceptions)

    def test_doesnt_call_hook_for_non_important_exception(self):
        # Some exceptions are exempt from OOPSes.
        exceptions = []

        self.assertEqual(0, len(self.oopses))
        hook = install_oops_handler(1000)
        self.addCleanup(remove_exception_logging_hook, hook)
        exception = AppendRevisionsOnlyViolation("foo")
        self.logException(exception)
        self.assertEqual(0, len(self.oopses))

    def test_doesnt_call_hook_when_removed(self):
        # remove_exception_logging_hook removes the hook function, ensuring
        # it's not called when Bazaar logs an exception.
        exceptions = []

        def hook():
            exceptions.append(sys.exc_info()[:2])

        add_exception_logging_hook(hook)
        remove_exception_logging_hook(hook)
        self.logException(RuntimeError('foo'))
        self.assertEqual([], exceptions)


class TestGetVfsFormatClasses(TestCaseWithTransport):
    """Tests for `lp.codehosting.bzrutils.get_vfs_format_classes`.
    """

    def setUp(self):
        super(TestGetVfsFormatClasses, self).setUp()
        self.disable_directory_isolation()
        # This makes sure the connections held by the branches opened in the
        # test are dropped, so the daemon threads serving those branches can
        # exit.
        self.addCleanup(gc.collect)

    def test_get_vfs_format_classes(self):
        # get_vfs_format_classes for a returns the underlying format classes
        # of the branch, repo and bzrdir, even if the branch is a
        # RemoteBranch.
        vfs_branch = self.make_branch('.')
        smart_server = test_server.SmartTCPServer_for_testing()
        smart_server.start_server(self.get_vfs_only_server())
        self.addCleanup(smart_server.stop_server)
        remote_branch = Branch.open(smart_server.get_url())
        # Check that our set up worked: remote_branch is Remote and
        # source_branch is not.
        self.assertIsInstance(remote_branch, RemoteBranch)
        self.failIf(isinstance(vfs_branch, RemoteBranch))
        # Now, get_vfs_format_classes on both branches returns the same format
        # information.
        self.assertEqual(
            get_vfs_format_classes(vfs_branch),
            get_vfs_format_classes(remote_branch))


def load_tests(basic_tests, module, loader):
    """Parametrize the tests of get_branch_stacked_on_url by branch format."""
    result = loader.suiteClass()

    get_branch_stacked_on_url_tests = loader.loadTestsFromTestCase(
        TestGetBranchStackedOnURL)
    scenarios = [scenario for scenario in branch_scenarios()
                 if scenario[0] not in (
                     'BranchReferenceFormat', 'GitBranchFormat',
                     'SvnBranchFormat')]
    multiply_tests(get_branch_stacked_on_url_tests, scenarios, result)

    result.addTests(loader.loadTestsFromTestCase(TestIsBranchStackable))
    result.addTests(loader.loadTestsFromTestCase(TestDenyingServer))
    result.addTests(loader.loadTestsFromTestCase(TestExceptionLoggingHooks))
    result.addTests(loader.loadTestsFromTestCase(TestGetVfsFormatClasses))
    return result


def test_suite():
    loader = TestLoader()
    return loader.loadTestsFromName(__name__)
