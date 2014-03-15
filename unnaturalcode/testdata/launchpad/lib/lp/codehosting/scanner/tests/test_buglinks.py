# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for creating BugBranch items based on Bazaar revisions."""

__metaclass__ = type

from bzrlib.revision import Revision
from zope.component import getUtility
from zope.event import notify

from lp.app.errors import NotFoundError
from lp.bugs.interfaces.bug import IBugSet
from lp.bugs.interfaces.bugbranch import IBugBranchSet
from lp.code.interfaces.revision import IRevisionSet
from lp.codehosting.scanner import events
from lp.codehosting.scanner.buglinks import BugBranchLinker
from lp.codehosting.scanner.tests.test_bzrsync import BzrSyncTestCase
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.services.osutils import override_environ
from lp.testing import (
    TestCase,
    TestCaseWithFactory,
    )
from lp.testing.dbuser import (
    lp_dbuser,
    switch_dbuser,
    )
from lp.testing.layers import LaunchpadZopelessLayer


class RevisionPropertyParsing(TestCase):
    """Tests for parsing the bugs revision property.

    The bugs revision property holds information about Launchpad bugs which
    are affected by a revision. A given revision may affect multiple bugs in
    different ways. A revision may indicate work has begin on a bug, or that
    it constitutes a fix for a bug.

    The bugs property is formatted as a newline-separated list of entries.
    Each entry is of the form '<bug_id> <status>', where '<bug_id>' is the URL
    for a page that describes the bug, and status is one of 'fixed' or
    'inprogress'.

    In general, the parser skips over any lines with errors.

    Blank lines and extraneous whitespace are ignored. URLs for non-Launchpad
    bugs are ignored. The '<status>' field is case-insensitive.

    If the same bug is mentioned more than once, the final mention is
    considered authoritative.
    """

    def extractBugInfo(self, bug_property):
        revision = Revision(
            self.factory.getUniqueString(),
            properties=dict(bugs=bug_property))
        bug_linker = BugBranchLinker(None)
        return bug_linker.extractBugInfo(revision)

    def test_single(self):
        # Parsing a single line should give a dict with a single entry,
        # mapping the bug_id to the status.
        bugs = self.extractBugInfo("https://launchpad.net/bugs/9999 fixed")
        self.assertEquals(bugs, {9999: 'fixed'})

    def test_multiple(self):
        # Information about more than one bug can be specified. Make sure that
        # all the information is processed.
        bugs = self.extractBugInfo(
            "https://launchpad.net/bugs/9999 fixed\n"
            "https://launchpad.net/bugs/8888 fixed")
        self.assertEquals(bugs, {9999: 'fixed',
                                 8888: 'fixed'})

    def test_empty(self):
        # If the property is empty, then return an empty dict.
        bugs = self.extractBugInfo('')
        self.assertEquals(bugs, {})

    def test_bad_bug(self):
        # If the given bug is not a valid integer, then skip it, generate an
        # OOPS and continue processing.
        bugs = self.extractBugInfo('https://launchpad.net/~jml fixed')
        self.assertEquals(bugs, {})

    def test_non_launchpad_bug(self):
        # References to bugs on sites other than launchpad are ignored.
        bugs = self.extractBugInfo('http://bugs.debian.org/1234 fixed')
        self.assertEquals(bugs, {})

    def test_duplicated_line(self):
        # If a particular line is duplicated, silently ignore the duplicates.
        bugs = self.extractBugInfo(
            'https://launchpad.net/bugs/9999 fixed\n'
            'https://launchpad.net/bugs/9999 fixed')
        self.assertEquals(bugs, {9999: 'fixed'})

    def test_strict_url_checking(self):
        # Ignore URLs that look like a Launchpad bug URL but aren't.
        bugs = self.extractBugInfo('https://launchpad.net/people/1234 fixed')
        self.assertEquals(bugs, {})
        bugs = self.extractBugInfo(
            'https://launchpad.net/bugs/foo/1234 fixed')
        self.assertEquals(bugs, {})


class TestBugLinking(BzrSyncTestCase):
    """Tests for creating BugBranch items on scanning branches.

    We create a BugBranch item if we find a good 'bugs' property in a new
    mainline revision of a branch.
    """

    def setUp(self):
        BzrSyncTestCase.setUp(self)

    def makeFixtures(self):
        super(TestBugLinking, self).makeFixtures()
        self.bug1 = self.factory.makeBug()
        sp = self.factory.makeSourcePackage(publish=True)
        self.bug1.addTask(self.bug1.owner, sp)
        dsp = self.factory.makeDistributionSourcePackage()
        self.bug1.addTask(self.bug1.owner, dsp)
        distro = self.factory.makeDistribution()
        self.bug1.addTask(self.bug1.owner, distro)
        self.bug2 = self.factory.makeBug()
        self.new_db_branch = self.factory.makeAnyBranch()
        self.layer.txn.commit()

    def getBugURL(self, bug):
        """Get the canonical URL for 'bug'.

        We don't use canonical_url because we don't want to have to make
        Bazaar know about launchpad.dev.
        """
        return 'https://launchpad.net/bugs/%s' % bug.id

    def assertBugBranchLinked(self, bug, branch):
        """Assert that the BugBranch for `bug` and `branch` exists.

        Raises an assertion error if there's no such bug.
        """
        bug_branch = getUtility(IBugBranchSet).getBugBranch(bug, branch)
        if bug_branch is None:
            self.fail('No BugBranch found for %r, %r' % (bug, branch))

    def test_newMainlineRevisionAddsBugBranch(self):
        """New mainline revisions with bugs properties create BugBranches."""
        self.commitRevision(
            rev_id='rev1',
            revprops={'bugs': '%s fixed' % self.getBugURL(self.bug1)})
        self.syncBazaarBranchToDatabase(self.bzr_branch, self.db_branch)
        self.assertBugBranchLinked(self.bug1, self.db_branch)

    def test_scanningTwiceDoesntMatter(self):
        """Scanning a branch twice is the same as scanning it once."""
        self.commitRevision(
            rev_id='rev1',
            revprops={'bugs': '%s fixed' % self.getBugURL(self.bug1)})
        self.syncBazaarBranchToDatabase(self.bzr_branch, self.db_branch)
        self.syncBazaarBranchToDatabase(self.bzr_branch, self.db_branch)
        self.assertBugBranchLinked(self.bug1, self.db_branch)

    def makePackageBranch(self):
        with lp_dbuser():
            branch = self.factory.makePackageBranch()
            branch.sourcepackage.setBranch(
                PackagePublishingPocket.RELEASE, branch, branch.owner)
        return branch

    def test_linking_bug_to_official_package_branch(self):
        # We can link a bug to an official package branch. Test added to catch
        # bug 391303.
        self.commitRevision(
            rev_id='rev1',
            revprops={'bugs': '%s fixed' % self.getBugURL(self.bug1)})
        branch = self.makePackageBranch()
        self.syncBazaarBranchToDatabase(self.bzr_branch, branch)
        self.assertBugBranchLinked(self.bug1, branch)

    def test_knownMainlineRevisionsDoesntMakeLink(self):
        """Don't add BugBranches for known mainline revision."""
        self.commitRevision(
            rev_id='rev1',
            revprops={'bugs': '%s fixed' % self.getBugURL(self.bug1)})
        self.syncBazaarBranchToDatabase(self.bzr_branch, self.db_branch)
        # Create a new DB branch to sync with.
        self.syncBazaarBranchToDatabase(self.bzr_branch, self.new_db_branch)
        self.assertEqual(
            getUtility(IBugBranchSet).getBugBranch(
                self.bug1, self.new_db_branch),
            None,
            "Should not create a BugBranch.")

    def test_nonMainlineRevisionsDontMakeBugBranches(self):
        """Don't add BugBranches based on non-mainline revisions."""
        # Make the base revision.
        author = self.factory.getUniqueString()
        # XXX: AaronBentley 2010-08-06 bug=614404: a bzr username is
        # required to generate the revision-id.
        with override_environ(BZR_EMAIL='me@example.com'):
            self.bzr_tree.commit(
                u'common parent', committer=author, rev_id='r1',
                allow_pointless=True)

            # Branch from the base revision.
            new_tree = self.make_branch_and_tree('bzr_branch_merged')
            new_tree.pull(self.bzr_branch)

            # Commit to both branches
            self.bzr_tree.commit(
                u'commit one', committer=author, rev_id='r2',
                allow_pointless=True)
            new_tree.commit(
                u'commit two', committer=author, rev_id='r1.1.1',
                allow_pointless=True,
                revprops={'bugs': '%s fixed' % self.getBugURL(self.bug1)})

            # Merge and commit.
            self.bzr_tree.merge_from_branch(new_tree.branch)
            self.bzr_tree.commit(
                u'merge', committer=author, rev_id='r3',
                allow_pointless=True)

        self.syncBazaarBranchToDatabase(self.bzr_branch, self.db_branch)
        self.assertEqual(
            getUtility(IBugBranchSet).getBugBranch(self.bug1, self.db_branch),
            None,
            "Should not create a BugBranch.")

    def test_ignoreNonExistentBug(self):
        """If the bug doesn't actually exist, we just ignore it."""
        self.assertRaises(NotFoundError, getUtility(IBugSet).get, 99999)
        self.assertEqual([], list(self.db_branch.linked_bugs))
        self.commitRevision(
            rev_id='rev1',
            revprops={'bugs': 'https://launchpad.net/bugs/99999 fixed'})
        self.syncBazaarBranchToDatabase(self.bzr_branch, self.db_branch)
        self.assertEqual([], list(self.db_branch.linked_bugs))

    def test_multipleBugsInProperty(self):
        """Create BugBranch links for *all* bugs in the property."""
        self.commitRevision(
            rev_id='rev1',
            revprops={'bugs': '%s fixed\n%s fixed' % (
                    self.getBugURL(self.bug1), self.getBugURL(self.bug2))})
        self.syncBazaarBranchToDatabase(self.bzr_branch, self.db_branch)

        self.assertBugBranchLinked(self.bug1, self.db_branch)
        self.assertBugBranchLinked(self.bug2, self.db_branch)


class TestSubscription(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def test_got_new_revision_subscribed(self):
        """got_new_revision is subscribed to NewRevision."""
        self.useBzrBranches(direct_database=True)
        db_branch, tree = self.create_branch_and_tree()
        bug = self.factory.makeBug()
        switch_dbuser("branchscanner")
        # XXX: AaronBentley 2010-08-06 bug=614404: a bzr username is
        # required to generate the revision-id.
        with override_environ(BZR_EMAIL='me@example.com'):
            revision_id = tree.commit('fix revision',
                revprops={
                    'bugs': 'https://launchpad.net/bugs/%d fixed' % bug.id})
        bzr_revision = tree.branch.repository.get_revision(revision_id)
        revision_set = getUtility(IRevisionSet)
        revision_set.newFromBazaarRevisions([bzr_revision])
        notify(events.NewMainlineRevisions(
            db_branch, tree.branch, [bzr_revision]))
        bug_branch = getUtility(IBugBranchSet).getBugBranch(bug, db_branch)
        self.assertIsNot(None, bug_branch)
