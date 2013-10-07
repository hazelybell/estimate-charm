# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the safe branch open code."""


__metaclass__ = type

from bzrlib.branch import (
    Branch,
    BranchReferenceFormat,
    BzrBranchFormat7,
    )
from bzrlib.bzrdir import (
    BzrDir,
    BzrDirMetaFormat1,
    BzrProber,
    )
from bzrlib.controldir import ControlDirFormat
from bzrlib.errors import NotBranchError
from bzrlib.repofmt.knitpack_repo import RepositoryFormatKnitPack1
from bzrlib.tests import TestCaseWithTransport
from bzrlib.transport import chroot
from lazr.uri import URI

from lp.codehosting.safe_open import (
    BadUrl,
    BlacklistPolicy,
    BranchLoopError,
    BranchReferenceForbidden,
    safe_open,
    SafeBranchOpener,
    WhitelistPolicy,
    )
from lp.codehosting.tests.helpers import force_stacked_on_url
from lp.testing import TestCase


class TestSafeBranchOpenerCheckAndFollowBranchReference(TestCase):
    """Unit tests for `SafeBranchOpener.checkAndFollowBranchReference`."""

    def setUp(self):
        super(TestSafeBranchOpenerCheckAndFollowBranchReference, self).setUp()
        SafeBranchOpener.install_hook()

    class StubbedSafeBranchOpener(SafeBranchOpener):
        """SafeBranchOpener that provides canned answers.

        We implement the methods we need to to be able to control all the
        inputs to the `BranchMirrorer.checkSource` method, which is what is
        being tested in this class.
        """

        def __init__(self, references, policy):
            parent_cls = TestSafeBranchOpenerCheckAndFollowBranchReference
            super(parent_cls.StubbedSafeBranchOpener, self).__init__(policy)
            self._reference_values = {}
            for i in range(len(references) - 1):
                self._reference_values[references[i]] = references[i + 1]
            self.follow_reference_calls = []

        def followReference(self, url):
            self.follow_reference_calls.append(url)
            return self._reference_values[url]

    def makeBranchOpener(self, should_follow_references, references,
                         unsafe_urls=None):
        policy = BlacklistPolicy(should_follow_references, unsafe_urls)
        opener = self.StubbedSafeBranchOpener(references, policy)
        return opener

    def testCheckInitialURL(self):
        # checkSource rejects all URLs that are not allowed.
        opener = self.makeBranchOpener(None, [], set(['a']))
        self.assertRaises(
            BadUrl, opener.checkAndFollowBranchReference, 'a')

    def testNotReference(self):
        # When branch references are forbidden, checkAndFollowBranchReference
        # does not raise on non-references.
        opener = self.makeBranchOpener(False, ['a', None])
        self.assertEquals(
            'a', opener.checkAndFollowBranchReference('a'))
        self.assertEquals(['a'], opener.follow_reference_calls)

    def testBranchReferenceForbidden(self):
        # checkAndFollowBranchReference raises BranchReferenceForbidden if
        # branch references are forbidden and the source URL points to a
        # branch reference.
        opener = self.makeBranchOpener(False, ['a', 'b'])
        self.assertRaises(
            BranchReferenceForbidden,
            opener.checkAndFollowBranchReference, 'a')
        self.assertEquals(['a'], opener.follow_reference_calls)

    def testAllowedReference(self):
        # checkAndFollowBranchReference does not raise if following references
        # is allowed and the source URL points to a branch reference to a
        # permitted location.
        opener = self.makeBranchOpener(True, ['a', 'b', None])
        self.assertEquals(
            'b', opener.checkAndFollowBranchReference('a'))
        self.assertEquals(['a', 'b'], opener.follow_reference_calls)

    def testCheckReferencedURLs(self):
        # checkAndFollowBranchReference checks if the URL a reference points
        # to is safe.
        opener = self.makeBranchOpener(
            True, ['a', 'b', None], unsafe_urls=set('b'))
        self.assertRaises(
            BadUrl, opener.checkAndFollowBranchReference, 'a')
        self.assertEquals(['a'], opener.follow_reference_calls)

    def testSelfReferencingBranch(self):
        # checkAndFollowBranchReference raises BranchReferenceLoopError if
        # following references is allowed and the source url points to a
        # self-referencing branch reference.
        opener = self.makeBranchOpener(True, ['a', 'a'])
        self.assertRaises(
            BranchLoopError, opener.checkAndFollowBranchReference, 'a')
        self.assertEquals(['a'], opener.follow_reference_calls)

    def testBranchReferenceLoop(self):
        # checkAndFollowBranchReference raises BranchReferenceLoopError if
        # following references is allowed and the source url points to a loop
        # of branch references.
        references = ['a', 'b', 'a']
        opener = self.makeBranchOpener(True, references)
        self.assertRaises(
            BranchLoopError, opener.checkAndFollowBranchReference, 'a')
        self.assertEquals(['a', 'b'], opener.follow_reference_calls)


class TrackingProber(BzrProber):
    """Subclass of BzrProber which tracks URLs it has been asked to open."""

    seen_urls = []

    @classmethod
    def probe_transport(klass, transport):
        klass.seen_urls.append(transport.base)
        return BzrProber.probe_transport(transport)


class TestSafeBranchOpenerStacking(TestCaseWithTransport):

    def setUp(self):
        super(TestSafeBranchOpenerStacking, self).setUp()
        SafeBranchOpener.install_hook()

    def makeBranchOpener(self, allowed_urls, probers=None):
        policy = WhitelistPolicy(True, allowed_urls, True)
        return SafeBranchOpener(policy, probers)

    def makeBranch(self, path, branch_format, repository_format):
        """Make a Bazaar branch at 'path' with the given formats."""
        bzrdir_format = BzrDirMetaFormat1()
        bzrdir_format.set_branch_format(branch_format)
        bzrdir = self.make_bzrdir(path, format=bzrdir_format)
        repository_format.initialize(bzrdir)
        return bzrdir.create_branch()

    def testProbers(self):
        # Only the specified probers should be used
        b = self.make_branch('branch')
        opener = self.makeBranchOpener([b.base], probers=[])
        self.assertRaises(NotBranchError, opener.open, b.base)
        opener = self.makeBranchOpener([b.base], probers=[BzrProber])
        self.assertEquals(b.base, opener.open(b.base).base)

    def testDefaultProbers(self):
        # If no probers are specified to the constructor
        # of SafeBranchOpener, then a safe set will be used,
        # rather than all probers registered in bzr.
        self.addCleanup(ControlDirFormat.unregister_prober, TrackingProber)
        ControlDirFormat.register_prober(TrackingProber)
        # Open a location without any branches, so that all probers are
        # tried.
        # First, check that the TrackingProber tracks correctly.
        TrackingProber.seen_urls = []
        opener = self.makeBranchOpener(["."], probers=[TrackingProber])
        self.assertRaises(NotBranchError, opener.open, ".")
        self.assertEquals(1, len(TrackingProber.seen_urls))
        TrackingProber.seen_urls = []
        # And make sure it's registered in such a way that BzrDir.open would
        # use it.
        self.assertRaises(NotBranchError, BzrDir.open, ".")
        self.assertEquals(1, len(TrackingProber.seen_urls))
        TrackingProber.seen_urls = []
        # Make sure that SafeBranchOpener doesn't use it if no
        # probers were specified
        opener = self.makeBranchOpener(["."])
        self.assertRaises(NotBranchError, opener.open, ".")
        self.assertEquals(0, len(TrackingProber.seen_urls))

    def testAllowedURL(self):
        # checkSource does not raise an exception for branches stacked on
        # branches with allowed URLs.
        stacked_on_branch = self.make_branch('base-branch')
        stacked_branch = self.make_branch('stacked-branch')
        stacked_branch.set_stacked_on_url(stacked_on_branch.base)
        opener = self.makeBranchOpener(
            [stacked_branch.base, stacked_on_branch.base])
        # This doesn't raise an exception.
        opener.open(stacked_branch.base)

    def testUnstackableRepository(self):
        # checkSource treats branches with UnstackableRepositoryFormats as
        # being not stacked.
        branch = self.makeBranch(
            'unstacked', BzrBranchFormat7(), RepositoryFormatKnitPack1())
        opener = self.makeBranchOpener([branch.base])
        # This doesn't raise an exception.
        opener.open(branch.base)

    def testAllowedRelativeURL(self):
        # checkSource passes on absolute urls to checkOneURL, even if the
        # value of stacked_on_location in the config is set to a relative URL.
        stacked_on_branch = self.make_branch('base-branch')
        stacked_branch = self.make_branch('stacked-branch')
        stacked_branch.set_stacked_on_url('../base-branch')
        opener = self.makeBranchOpener(
            [stacked_branch.base, stacked_on_branch.base])
        # Note that stacked_on_branch.base is not '../base-branch', it's an
        # absolute URL.
        self.assertNotEqual('../base-branch', stacked_on_branch.base)
        # This doesn't raise an exception.
        opener.open(stacked_branch.base)

    def testAllowedRelativeNested(self):
        # Relative URLs are resolved relative to the stacked branch.
        self.get_transport().mkdir('subdir')
        a = self.make_branch('subdir/a')
        b = self.make_branch('b')
        b.set_stacked_on_url('../subdir/a')
        c = self.make_branch('subdir/c')
        c.set_stacked_on_url('../../b')
        opener = self.makeBranchOpener([c.base, b.base, a.base])
        # This doesn't raise an exception.
        opener.open(c.base)

    def testForbiddenURL(self):
        # checkSource raises a BadUrl exception if a branch is stacked on a
        # branch with a forbidden URL.
        stacked_on_branch = self.make_branch('base-branch')
        stacked_branch = self.make_branch('stacked-branch')
        stacked_branch.set_stacked_on_url(stacked_on_branch.base)
        opener = self.makeBranchOpener([stacked_branch.base])
        self.assertRaises(BadUrl, opener.open, stacked_branch.base)

    def testForbiddenURLNested(self):
        # checkSource raises a BadUrl exception if a branch is stacked on a
        # branch that is in turn stacked on a branch with a forbidden URL.
        a = self.make_branch('a')
        b = self.make_branch('b')
        b.set_stacked_on_url(a.base)
        c = self.make_branch('c')
        c.set_stacked_on_url(b.base)
        opener = self.makeBranchOpener([c.base, b.base])
        self.assertRaises(BadUrl, opener.open, c.base)

    def testSelfStackedBranch(self):
        # checkSource raises StackingLoopError if a branch is stacked on
        # itself. This avoids infinite recursion errors.
        a = self.make_branch('a')
        force_stacked_on_url(a, a.base)
        opener = self.makeBranchOpener([a.base])
        self.assertRaises(BranchLoopError, opener.open, a.base)

    def testLoopStackedBranch(self):
        # checkSource raises StackingLoopError if a branch is stacked in such
        # a way so that it is ultimately stacked on itself. e.g. a stacked on
        # b stacked on a.
        a = self.make_branch('a')
        b = self.make_branch('b')
        a.set_stacked_on_url(b.base)
        b.set_stacked_on_url(a.base)
        opener = self.makeBranchOpener([a.base, b.base])
        self.assertRaises(BranchLoopError, opener.open, a.base)
        self.assertRaises(BranchLoopError, opener.open, b.base)

    def testCustomOpener(self):
        # A custom function for opening a control dir can be specified.
        a = self.make_branch('a')
        b = self.make_branch('b')
        b.set_stacked_on_url(a.base)

        TrackingProber.seen_urls = []
        opener = self.makeBranchOpener(
            [a.base, b.base], probers=[TrackingProber])
        opener.open(b.base)
        self.assertEquals(
            set(TrackingProber.seen_urls), set([b.base, a.base]))

    def testCustomOpenerWithBranchReference(self):
        # A custom function for opening a control dir can be specified.
        a = self.make_branch('a')
        b_dir = self.make_bzrdir('b')
        b = BranchReferenceFormat().initialize(b_dir, target_branch=a)
        TrackingProber.seen_urls = []
        opener = self.makeBranchOpener(
            [a.base, b.base], probers=[TrackingProber])
        opener.open(b.base)
        self.assertEquals(
            set(TrackingProber.seen_urls), set([b.base, a.base]))

    def test_ignore_fallbacks(self):
        """"Cross-format stacking doesn't error with ignore_fallbacks."""
        stacked, stacked_on = make_cross_format_stacked(self)
        opener = self.makeBranchOpener([stacked.base, stacked_on.base])
        opener.open(stacked.base, ignore_fallbacks=True)


def make_cross_format_stacked(test_case):
    test_case.get_transport().mkdir('inside')
    stacked = test_case.make_branch('inside/stacked', format='1.6')
    stacked_on = test_case.make_branch('inside/stacked-on', format='2a')
    force_stacked_on_url(stacked, stacked_on.base)
    return stacked, stacked_on


class TestSafeOpen(TestCaseWithTransport):
    """Tests for `safe_open`."""

    def setUp(self):
        super(TestSafeOpen, self).setUp()
        SafeBranchOpener.install_hook()

    def test_hook_does_not_interfere(self):
        # The transform_fallback_location hook does not interfere with regular
        # stacked branch access outside of safe_open.
        self.make_branch('stacked')
        self.make_branch('stacked-on')
        Branch.open('stacked').set_stacked_on_url('../stacked-on')
        Branch.open('stacked')

    def get_chrooted_scheme(self, relpath):
        """Create a server that is chrooted to `relpath`.

        :return: ``(scheme, get_url)`` where ``scheme`` is the scheme of the
            chroot server and ``get_url`` returns URLs on said server.
        """
        transport = self.get_transport(relpath)
        chroot_server = chroot.ChrootServer(transport)
        chroot_server.start_server()
        self.addCleanup(chroot_server.stop_server)

        def get_url(relpath):
            return chroot_server.get_url() + relpath

        return URI(chroot_server.get_url()).scheme, get_url

    def test_stacked_within_scheme(self):
        # A branch that is stacked on a URL of the same scheme is safe to
        # open.
        self.get_transport().mkdir('inside')
        self.make_branch('inside/stacked')
        self.make_branch('inside/stacked-on')
        scheme, get_chrooted_url = self.get_chrooted_scheme('inside')
        Branch.open(get_chrooted_url('stacked')).set_stacked_on_url(
            get_chrooted_url('stacked-on'))
        safe_open(scheme, get_chrooted_url('stacked'))

    def test_stacked_outside_scheme(self):
        # A branch that is stacked on a URL that is not of the same scheme is
        # not safe to open.
        self.get_transport().mkdir('inside')
        self.get_transport().mkdir('outside')
        self.make_branch('inside/stacked')
        self.make_branch('outside/stacked-on')
        scheme, get_chrooted_url = self.get_chrooted_scheme('inside')
        Branch.open(get_chrooted_url('stacked')).set_stacked_on_url(
            self.get_url('outside/stacked-on'))
        self.assertRaises(
            BadUrl, safe_open, scheme, get_chrooted_url('stacked'))

    def test_ignore_fallbacks(self):
        """"Cross-format stacking doesn't error with ignore_fallbacks."""
        scheme, get_chrooted_url = self.get_chrooted_scheme('inside')
        stacked, stacked_on = make_cross_format_stacked(self)
        force_stacked_on_url(stacked, get_chrooted_url('stacked-on'))
        safe_open(scheme, get_chrooted_url('stacked'), ignore_fallbacks=True)
