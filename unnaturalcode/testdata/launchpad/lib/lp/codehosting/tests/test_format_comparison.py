# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for comparing Bazaar formats."""

__metaclass__ = type

import unittest

from lp.codehosting.bzrutils import identical_formats

# Define a bunch of different fake format classes to pass to identical_formats

class BzrDirFormatA:
    pass

class BzrDirFormatB:
    pass

class BranchFormatA:
    pass

class BranchFormatB:
    pass

class RepoFormatA:
    pass

class RepoFormatB:
    pass


class StubObjectWithFormat:
    """A stub object with a _format attribute, like bzrdir and repositories."""
    def __init__(self, format):
        self._format = format


class StubBranch:
    """A stub branch object that just has formats."""
    def __init__(self, bzrdir_format, repo_format, branch_format):
        self.bzrdir = StubObjectWithFormat(bzrdir_format)
        self.repository = StubObjectWithFormat(repo_format)
        self._format = branch_format


class IdenticalFormatsTestCase(unittest.TestCase):
    """Test case for identical_formats function."""

    def testAllIdentical(self):
        # identical_formats should return True when both branches have the same
        # bzrdir, repository, and branch formats.
        self.failUnless(
            identical_formats(
                StubBranch(BzrDirFormatA(), RepoFormatA(), BranchFormatA()),
                StubBranch(BzrDirFormatA(), RepoFormatA(), BranchFormatA())))

    def testDifferentBzrDirFormats(self):
        # identical_formats should return False when both branches have the
        # different bzrdir formats.
        self.failIf(
            identical_formats(
                StubBranch(BzrDirFormatA(), RepoFormatA(), BranchFormatA()),
                StubBranch(BzrDirFormatB(), RepoFormatA(), BranchFormatA())))

    def testDifferentRepositoryFormats(self):
        # identical_formats should return False when both branches have the
        # different repository formats.
        self.failIf(
            identical_formats(
                StubBranch(BzrDirFormatA(), RepoFormatA(), BranchFormatA()),
                StubBranch(BzrDirFormatA(), RepoFormatB(), BranchFormatA())))

    def testDifferentBranchFormats(self):
        # identical_formats should return False when both branches have the
        # different branch formats.
        self.failIf(
            identical_formats(
                StubBranch(BzrDirFormatA(), RepoFormatA(), BranchFormatA()),
                StubBranch(BzrDirFormatA(), RepoFormatA(), BranchFormatB())))
