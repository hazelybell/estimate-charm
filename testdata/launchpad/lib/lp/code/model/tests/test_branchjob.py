# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for BranchJobs."""

__metaclass__ = type

import datetime
import os
import shutil

from bzrlib import errors as bzr_errors
from bzrlib.branch import (
    Branch,
    BzrBranchFormat7,
    )
from bzrlib.bzrdir import (
    BzrDir,
    BzrDirMetaFormat1,
    )
from bzrlib.repofmt.knitpack_repo import RepositoryFormatKnitPack6
from bzrlib.revision import NULL_REVISION
from bzrlib.transport import get_transport
import pytz
from sqlobject import SQLObjectNotFound
from storm.locals import Store
import transaction
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.code.bzr import (
    branch_revision_history,
    BranchFormat,
    RepositoryFormat,
    )
from lp.code.enums import (
    BranchMergeProposalStatus,
    BranchSubscriptionDiffSize,
    BranchSubscriptionNotificationLevel,
    CodeReviewNotificationLevel,
    )
from lp.code.errors import AlreadyLatestFormat
from lp.code.interfaces.branchjob import (
    IBranchJob,
    IBranchScanJob,
    IBranchUpgradeJob,
    IReclaimBranchSpaceJob,
    IReclaimBranchSpaceJobSource,
    IRevisionMailJob,
    IRosettaUploadJob,
    )
from lp.code.model.branchjob import (
    BranchJob,
    BranchJobDerived,
    BranchJobType,
    BranchScanJob,
    BranchUpgradeJob,
    ReclaimBranchSpaceJob,
    RevisionMailJob,
    RevisionsAddedJob,
    RosettaUploadJob,
    )
from lp.code.model.branchrevision import BranchRevision
from lp.code.model.directbranchcommit import DirectBranchCommit
from lp.code.model.revision import RevisionSet
from lp.code.model.tests.test_branch import create_knit
from lp.codehosting.vfs import branch_id_to_path
from lp.scripts.helpers import TransactionFreeOperation
from lp.services.config import config
from lp.services.database.constants import UTC_NOW
from lp.services.database.interfaces import IMasterStore
from lp.services.features.testing import FeatureFixture
from lp.services.identity.interfaces.emailaddress import EmailAddressStatus
from lp.services.job.interfaces.job import JobStatus
from lp.services.job.model.job import Job
from lp.services.job.runner import JobRunner
from lp.services.job.tests import block_on_job
from lp.services.osutils import override_environ
from lp.services.webapp import canonical_url
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.dbuser import (
    dbuser,
    switch_dbuser,
    )
from lp.testing.layers import (
    CeleryBzrsyncdJobLayer,
    DatabaseFunctionalLayer,
    LaunchpadZopelessLayer,
    )
from lp.testing.librarianhelpers import get_newest_librarian_file
from lp.testing.mail_helpers import pop_notifications
from lp.translations.enums import RosettaImportStatus
from lp.translations.interfaces.translationimportqueue import (
    ITranslationImportQueue,
    )
from lp.translations.interfaces.translations import (
    TranslationsBranchImportMode,
    )


class TestBranchJob(TestCaseWithFactory):
    """Tests for BranchJob."""

    layer = DatabaseFunctionalLayer

    def test_providesInterface(self):
        """Ensure that BranchJob implements IBranchJob."""
        branch = self.factory.makeAnyBranch()
        self.assertProvides(
            BranchJob(branch, BranchJobType.STATIC_DIFF, {}),
            IBranchJob)

    def test_destroySelf_destroys_job(self):
        """Ensure that BranchJob.destroySelf destroys the Job as well."""
        branch = self.factory.makeAnyBranch()
        branch_job = BranchJob(branch, BranchJobType.STATIC_DIFF, {})
        job_id = branch_job.job.id
        branch_job.destroySelf()
        self.assertRaises(SQLObjectNotFound, BranchJob.get, job_id)


class TestBranchJobDerived(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def test_getOopsMailController(self):
        """By default, no mail is sent about failed BranchJobs."""
        branch = self.factory.makeAnyBranch()
        job = BranchJob(branch, BranchJobType.STATIC_DIFF, {})
        derived = BranchJobDerived(job)
        self.assertIs(None, derived.getOopsMailController('x'))


class TestBranchScanJob(TestCaseWithFactory):
    """Tests for `BranchScanJob`."""

    layer = LaunchpadZopelessLayer

    def test_providesInterface(self):
        """Ensure that BranchScanJob implements IBranchScanJob."""
        branch = self.factory.makeAnyBranch()
        job = BranchScanJob.create(branch)
        self.assertProvides(job, IBranchScanJob)

    def test_run(self):
        """Ensure the job scans the branch."""
        self.useBzrBranches(direct_database=True)

        db_branch, bzr_tree = self.create_branch_and_tree()
        # XXX: AaronBentley 2010-08-06 bug=614404: a bzr username is
        # required to generate the revision-id.
        with override_environ(BZR_EMAIL='me@example.com'):
            bzr_tree.commit('First commit', rev_id='rev1')
            bzr_tree.commit('Second commit', rev_id='rev2')
            bzr_tree.commit('Third commit', rev_id='rev3')
            LaunchpadZopelessLayer.commit()

            job = BranchScanJob.create(db_branch)
            with dbuser("branchscanner"):
                job.run()

            self.assertEqual(db_branch.revision_count, 3)

            bzr_tree.commit('Fourth commit', rev_id='rev4')
            bzr_tree.commit('Fifth commit', rev_id='rev5')

        job = BranchScanJob.create(db_branch)
        with dbuser("branchscanner"):
            job.run()

        self.assertEqual(db_branch.revision_count, 5)

    def test_branch_deleted(self):
        """Ensure a job for a deleted branch completes with logged message."""
        self.useBzrBranches(direct_database=True)

        db_branch, bzr_tree = self.create_branch_and_tree()
        # XXX: AaronBentley 2010-08-06 bug=614404: a bzr username is
        # required to generate the revision-id.
        with override_environ(BZR_EMAIL='me@example.com'):
            bzr_tree.commit('First commit', rev_id='rev1')
            LaunchpadZopelessLayer.commit()

        expected_message = (
            'Skipping branch %s because it has been deleted.'
            % db_branch.unique_name)
        job = BranchScanJob.create(db_branch)
        db_branch.destroySelf()
        with self.expectedLog(expected_message):
            with dbuser("branchscanner"):
                job.run()

    def test_run_with_private_linked_bug(self):
        """Ensure the job scans a branch with a private bug in the revprops."""
        self.useBzrBranches(direct_database=True)
        db_branch, bzr_tree = self.create_branch_and_tree()
        product = self.factory.makeProduct()
        private_bug = self.factory.makeBug(
            target=product, information_type=InformationType.USERDATA)
        bug_line = 'https://launchpad.net/bugs/%s fixed' % private_bug.id
        with override_environ(BZR_EMAIL='me@example.com'):
            bzr_tree.commit(
                'First commit', rev_id='rev1', revprops={'bugs': bug_line})
        job = BranchScanJob.create(db_branch)
        with dbuser("branchscanner"):
            job.run()
        self.assertEqual(db_branch.revision_count, 1)
        self.assertTrue(private_bug.hasBranch(db_branch))


class TestBranchUpgradeJob(TestCaseWithFactory):
    """Tests for `BranchUpgradeJob`."""

    layer = LaunchpadZopelessLayer

    def make_format(self, branch_format=None, repo_format=None):
        # Return a Bzr MetaDir format with the provided branch and repository
        # formats.
        if branch_format is None:
            branch_format = BzrBranchFormat7
        if repo_format is None:
            repo_format = RepositoryFormatKnitPack6
        format = BzrDirMetaFormat1()
        format.set_branch_format(branch_format())
        format._set_repository_format(repo_format())
        return format

    def test_providesInterface(self):
        """Ensure that BranchUpgradeJob implements IBranchUpgradeJob."""
        branch = self.factory.makeAnyBranch(
            branch_format=BranchFormat.BZR_BRANCH_5,
            repository_format=RepositoryFormat.BZR_REPOSITORY_4)
        job = BranchUpgradeJob.create(branch, self.factory.makePerson())
        self.assertProvides(job, IBranchUpgradeJob)

    def test_upgrades_branch(self):
        """Ensure that a branch with an outdated format is upgraded."""
        self.useBzrBranches(direct_database=True)
        db_branch, tree = create_knit(self)
        self.assertEqual(
            tree.branch.repository._format.get_format_string(),
            'Bazaar-NG Knit Repository Format 1')

        job = BranchUpgradeJob.create(db_branch, self.factory.makePerson())

        dbuser = config.launchpad.dbuser
        self.becomeDbUser('upgrade-branches')
        with TransactionFreeOperation.require():
            job.run()
        new_branch = Branch.open(tree.branch.base)
        self.assertEqual(
            new_branch.repository._format.get_format_string(),
            'Bazaar repository format 2a (needs bzr 1.16 or later)\n')

        self.becomeDbUser(dbuser)
        self.assertFalse(db_branch.needs_upgrading)

    def test_needs_no_upgrading(self):
        # Branch upgrade job creation should raise an AlreadyLatestFormat if
        # the branch does not need to be upgraded.
        branch = self.factory.makeAnyBranch(
            branch_format=BranchFormat.BZR_BRANCH_7,
            repository_format=RepositoryFormat.BZR_CHK_2A)
        self.assertRaises(
            AlreadyLatestFormat, BranchUpgradeJob.create, branch,
            self.factory.makePerson())

    def test_existing_bzr_backup(self):
        # If the target branch already has a backup.bzr dir, the upgrade copy
        # should remove it.
        self.useBzrBranches(direct_database=True)
        db_branch, tree = create_knit(self)

        # Add a fake backup.bzr dir
        source_branch_transport = get_transport(db_branch.getInternalBzrUrl())
        source_branch_transport.mkdir('backup.bzr')
        source_branch_transport.clone('.bzr').copy_tree_to_transport(
            source_branch_transport.clone('backup.bzr'))

        job = BranchUpgradeJob.create(db_branch, self.factory.makePerson())
        self.becomeDbUser('upgrade-branches')
        job.run()

        new_branch = Branch.open(tree.branch.base)
        self.assertEqual(
            new_branch.repository._format.get_format_string(),
            'Bazaar repository format 2a (needs bzr 1.16 or later)\n')

    def test_db_user_can_request_scan(self):
        # The database user that does the upgrade needs to be able to request
        # a scan of the branch.
        branch = self.factory.makeAnyBranch()
        self.becomeDbUser('upgrade-branches')
        # Scan jobs are created by the branchChanged method.
        branch.branchChanged('', 'new-id', None, None, None)
        Store.of(branch).flush()

    def test_not_branch_error(self):
        self.useBzrBranches(direct_database=True)
        db_branch, tree = self.create_branch_and_tree()
        branch2 = BzrDir.create_branch_convenience('.')
        tree.branch.set_stacked_on_url(branch2.base)
        branch2.bzrdir.destroy_branch()
        # Create BranchUpgradeJob manually, because we're trying to upgrade a
        # branch that doesn't need upgrading.
        requester = self.factory.makePerson()
        branch_job = BranchJob(
            db_branch, BranchJobType.UPGRADE_BRANCH, {}, requester=requester)
        job = BranchUpgradeJob(branch_job)
        self.becomeDbUser('upgrade-branches')
        runner = JobRunner([job])
        runner.runJobHandleError(job)
        self.assertEqual([], self.oopses)
        (mail,) = pop_notifications()
        self.assertEqual(
            'Launchpad error while upgrading a branch', mail['subject'])
        self.assertIn('Not a branch', mail.get_payload(decode=True))


class TestRevisionMailJob(TestCaseWithFactory):
    """Tests for RevisionMailJob."""

    layer = LaunchpadZopelessLayer

    def test_providesInterface(self):
        """Ensure that RevisionMailJob implements IRevisionMailJob."""
        branch = self.factory.makeAnyBranch()
        job = RevisionMailJob.create(
            branch, 0, 'from@example.com', 'hello', 'subject')
        self.assertProvides(job, IRevisionMailJob)

    def test_repr(self):
        """Ensure that the revision mail job as a reasonable repr."""
        branch = self.factory.makeAnyBranch()
        job = RevisionMailJob.create(
            branch, 0, 'from@example.com', 'hello', 'subject')
        self.assertEqual(
            '<REVISION_MAIL branch job (%s) for %s>'
            % (job.context.id, branch.unique_name),
            repr(job))

    def test_run_sends_mail(self):
        """Ensure RevisionMailJob.run sends mail with correct values."""
        branch = self.factory.makeAnyBranch()
        branch.subscribe(
            branch.registrant,
            BranchSubscriptionNotificationLevel.FULL,
            BranchSubscriptionDiffSize.WHOLEDIFF,
            CodeReviewNotificationLevel.FULL,
            branch.registrant)
        job = RevisionMailJob.create(
            branch, 0, 'from@example.com', 'hello', 'subject')
        job.run()
        (mail, ) = pop_notifications()
        self.assertEqual('0', mail['X-Launchpad-Branch-Revision-Number'])
        self.assertEqual('from@example.com', mail['from'])
        self.assertEqual('subject', mail['subject'])
        self.assertEqual(
            'hello\n'
            '\n--\n'
            '%(identity)s\n'
            '%(url)s\n'
            '\nYou are subscribed to branch %(identity)s.\n'
            'To unsubscribe from this branch go to'
            ' %(url)s/+edit-subscription\n' % {
                'url': canonical_url(branch),
                'identity': branch.bzr_identity,
                },
            mail.get_payload(decode=True))

    def test_revno_string(self):
        """Ensure that revnos can be strings."""
        branch = self.factory.makeAnyBranch()
        job = RevisionMailJob.create(
            branch, 'removed', 'from@example.com', 'hello', 'subject')
        self.assertEqual('removed', job.revno)

    def test_iterReady_includes_ready_jobs(self):
        """Ready jobs should be listed."""
        branch = self.factory.makeAnyBranch()
        job = RevisionMailJob.create(
            branch, 0, 'from@example.org', 'body', 'subject')
        job.job.sync()
        job.context.sync()
        self.assertEqual([job], list(RevisionMailJob.iterReady()))

    def test_iterReady_excludes_unready_jobs(self):
        """Unready jobs should not be listed."""
        branch = self.factory.makeAnyBranch()
        job = RevisionMailJob.create(
            branch, 0, 'from@example.org', 'body', 'subject')
        job.job.start()
        job.job.complete()
        self.assertEqual([], list(RevisionMailJob.iterReady()))


class TestRevisionsAddedJob(TestCaseWithFactory):
    """Tests for RevisionsAddedJob."""

    layer = LaunchpadZopelessLayer

    def test_create(self):
        """RevisionsAddedJob.create uses the correct values."""
        branch = self.factory.makeBranch()
        job = RevisionsAddedJob.create(branch, 'rev1', 'rev2', '')
        self.assertEqual('rev1', job.last_scanned_id)
        self.assertEqual('rev2', job.last_revision_id)
        self.assertEqual(branch, job.branch)
        self.assertEqual(
            BranchJobType.REVISIONS_ADDED_MAIL, job.context.job_type)

    def test_iterReady(self):
        """IterReady iterates through ready jobs."""
        branch = self.factory.makeBranch()
        job = RevisionsAddedJob.create(branch, 'rev1', 'rev2', '')
        self.assertEqual([job], list(RevisionsAddedJob.iterReady()))

    def updateDBRevisions(self, branch, bzr_branch, revision_ids):
        """Update the database for the revisions.

        :param branch: The database branch associated with the revisions.
        :param bzr_branch: The Bazaar branch associated with the revisions.
        :param revision_ids: The ids of the revisions to update.  If not
            supplied, the branch revision history is used.
        """
        for bzr_revision in bzr_branch.repository.get_revisions(revision_ids):
            existing = branch.getBranchRevision(
                revision_id=bzr_revision.revision_id)
            if existing is None:
                RevisionSet().newFromBazaarRevisions([bzr_revision])
            revision = RevisionSet().getByRevisionId(
                bzr_revision.revision_id)
            try:
                revno = bzr_branch.revision_id_to_revno(revision.revision_id)
            except bzr_errors.NoSuchRevision:
                revno = None
            if existing is not None:
                branchrevision = IMasterStore(branch).find(
                    BranchRevision,
                    BranchRevision.branch_id == branch.id,
                    BranchRevision.revision_id == revision.id)
                branchrevision.remove()
            branch.createBranchRevision(revno, revision)

    def create3CommitsBranch(self):
        """Create a branch with three commits."""
        branch, tree = self.create_branch_and_tree()
        tree.lock_write()
        try:
            # XXX: AaronBentley 2010-08-06 bug=614404: a bzr username is
            # required to generate the revision-id.
            with override_environ(BZR_EMAIL='me@example.com'):
                tree.commit('rev1', rev_id='rev1')
                tree.commit('rev2', rev_id='rev2')
                tree.commit('rev3', rev_id='rev3')
            switch_dbuser('branchscanner')
            self.updateDBRevisions(
                branch, tree.branch, ['rev1', 'rev2', 'rev3'])
        finally:
            tree.unlock()
        return branch, tree

    def test_iterAddedMainline(self):
        """iterAddedMainline iterates through mainline revisions."""
        self.useBzrBranches(direct_database=True)
        branch, tree = self.create3CommitsBranch()
        job = RevisionsAddedJob.create(branch, 'rev1', 'rev2', '')
        job.bzr_branch.lock_read()
        self.addCleanup(job.bzr_branch.unlock)
        [(revision, revno)] = list(job.iterAddedMainline())
        self.assertEqual(2, revno)

    def test_iterAddedNonMainline(self):
        """iterAddedMainline drops non-mainline revisions."""
        self.useBzrBranches(direct_database=True)
        branch, tree = self.create3CommitsBranch()
        tree.pull(tree.branch, overwrite=True, stop_revision='rev2')
        tree.add_parent_tree_id('rev3')
        # XXX: AaronBentley 2010-08-06 bug=614404: a bzr username is
        # required to generate the revision-id.
        with override_environ(BZR_EMAIL='me@example.com'):
            tree.commit('rev3a', rev_id='rev3a')
        self.updateDBRevisions(branch, tree.branch, ['rev3', 'rev3a'])
        job = RevisionsAddedJob.create(branch, 'rev1', 'rev3', '')
        job.bzr_branch.lock_read()
        self.addCleanup(job.bzr_branch.unlock)
        out = [x.revision_id for x, y in job.iterAddedMainline()]
        self.assertEqual(['rev2'], out)

    def test_iterAddedMainline_order(self):
        """iterAddedMainline iterates in commit order."""
        self.useBzrBranches(direct_database=True)
        branch, tree = self.create3CommitsBranch()
        job = RevisionsAddedJob.create(branch, 'rev1', 'rev3', '')
        job.bzr_branch.lock_read()
        self.addCleanup(job.bzr_branch.unlock)
        # Since we've gone from rev1 to rev3, we've added rev2 and rev3.
        [(rev2, revno2), (rev3, revno3)] = list(job.iterAddedMainline())
        self.assertEqual('rev2', rev2.revision_id)
        self.assertEqual(2, revno2)
        self.assertEqual('rev3', rev3.revision_id)
        self.assertEqual(3, revno3)

    def makeBranchWithCommit(self):
        """Create a branch with a commit."""
        jrandom = self.factory.makePerson(name='jrandom')
        product = self.factory.makeProduct(name='foo')
        branch = self.factory.makeProductBranch(
            name='bar', product=product, owner=jrandom)
        branch.subscribe(
            branch.registrant,
            BranchSubscriptionNotificationLevel.FULL,
            BranchSubscriptionDiffSize.WHOLEDIFF,
            CodeReviewNotificationLevel.FULL,
            branch.registrant)
        branch, tree = self.create_branch_and_tree(db_branch=branch)
        tree.branch.nick = 'nicholas'
        tree.lock_write()
        self.addCleanup(tree.unlock)
        # XXX: AaronBentley 2010-08-06 bug=614404: a bzr username is
        # required to generate the revision-id.
        with override_environ(BZR_EMAIL='me@example.com'):
            tree.commit(
                'rev1', rev_id='rev1', timestamp=1000, timezone=0,
                committer='J. Random Hacker <jrandom@example.org>')
        return branch, tree

    def makeRevisionsAddedWithMergeCommit(self, authors=None,
                                          include_ghost=False):
        """Create a RevisionsAdded job with a revision that is a merge.

        :param authors: If specified, the list of authors of the commit
            that merges the others.
        :param include_ghost:If true, add revision 2c as a ghost revision.
        """
        self.useBzrBranches(direct_database=True)
        branch, tree = self.create_branch_and_tree()
        tree.branch.nick = 'nicholas'
        # XXX: AaronBentley 2010-08-06 bug=614404: a bzr username is
        # required to generate the revision-id.
        with override_environ(BZR_EMAIL='me@example.com'):
            tree.commit('rev1')
            tree2 = tree.bzrdir.sprout('tree2').open_workingtree()
            tree2.commit('rev2a', rev_id='rev2a-id', committer='foo@')
            tree2.commit('rev3', rev_id='rev3-id',
                         authors=['bar@', 'baz@blaine.com'])
            tree.merge_from_branch(tree2.branch)
            tree3 = tree.bzrdir.sprout('tree3').open_workingtree()
            tree3.commit('rev2b', rev_id='rev2b-id', committer='qux@')
            tree.merge_from_branch(tree3.branch, force=True)
            if include_ghost:
                tree.add_parent_tree_id('rev2c-id')
            tree.commit('rev2d', rev_id='rev2d-id', timestamp=1000,
                timezone=0, authors=authors,
                committer='J. Random Hacker <jrandom@example.org>')
        return RevisionsAddedJob.create(branch, 'rev2d-id', 'rev2d-id', '')

    def test_getMergedRevisionIDs(self):
        """Ensure the correct revision ids are returned for a merge."""
        job = self.makeRevisionsAddedWithMergeCommit(include_ghost=True)
        job.bzr_branch.lock_write()
        graph = job.bzr_branch.repository.get_graph()
        self.addCleanup(job.bzr_branch.unlock)
        self.assertEqual(set(['rev2a-id', 'rev3-id', 'rev2b-id', 'rev2c-id']),
                         job.getMergedRevisionIDs('rev2d-id', graph))

    def test_findRelatedBMP(self):
        """The related branch merge proposals can be identified."""
        self.useBzrBranches(direct_database=True)
        target_branch, tree = self.create_branch_and_tree('tree')
        desired_proposal = self.factory.makeBranchMergeProposal(
            target_branch=target_branch)
        desired_proposal.source_branch.last_scanned_id = 'rev2a-id'
        wrong_revision_proposal = self.factory.makeBranchMergeProposal(
            target_branch=target_branch)
        wrong_revision_proposal.source_branch.last_scanned_id = 'rev3-id'
        wrong_target_proposal = self.factory.makeBranchMergeProposal()
        wrong_target_proposal.source_branch.last_scanned_id = 'rev2a-id'
        job = RevisionsAddedJob.create(target_branch, 'rev2b-id', 'rev2b-id',
                                       '')
        self.assertEqual(
            [desired_proposal], job.findRelatedBMP(['rev2a-id']))

    def test_findRelatedBMP_one_per_source(self):
        """findRelatedBMP only returns the most recent proposal for any
        particular source branch.
        """
        self.useBzrBranches(direct_database=True)
        target_branch, tree = self.create_branch_and_tree('tree')
        the_past = datetime.datetime(2009, 1, 1, tzinfo=pytz.UTC)
        old_proposal = self.factory.makeBranchMergeProposal(
            target_branch=target_branch, date_created=the_past,
            set_state=BranchMergeProposalStatus.MERGED)
        source_branch = old_proposal.source_branch
        source_branch.last_scanned_id = 'rev2a-id'
        desired_proposal = source_branch.addLandingTarget(
            source_branch.owner, target_branch)
        job = RevisionsAddedJob.create(
            target_branch, 'rev2b-id', 'rev2b-id', '')
        self.assertEqual(
            [desired_proposal], job.findRelatedBMP(['rev2a-id']))

    def test_getAuthors(self):
        """Ensure getAuthors returns the authors for the revisions."""
        job = self.makeRevisionsAddedWithMergeCommit()
        job.bzr_branch.lock_write()
        self.addCleanup(job.bzr_branch.unlock)
        graph = job.bzr_branch.repository.get_graph()
        revision_ids = ['rev2a-id', 'rev3-id', 'rev2b-id']
        self.assertEqual(set(['foo@', 'bar@', 'baz@blaine.com', 'qux@']),
                         job.getAuthors(revision_ids, graph))

    def test_getAuthors_with_ghost(self):
        """getAuthors ignores ghosts when returning the authors."""
        job = self.makeRevisionsAddedWithMergeCommit(include_ghost=True)
        job.bzr_branch.lock_write()
        graph = job.bzr_branch.repository.get_graph()
        self.addCleanup(job.bzr_branch.unlock)
        revision_ids = ['rev2a-id', 'rev3-id', 'rev2b-id', 'rev2c-id']
        self.assertEqual(set(['foo@', 'bar@', 'baz@blaine.com', 'qux@']),
                         job.getAuthors(revision_ids, graph))

    def test_getRevisionMessage(self):
        """getRevisionMessage provides a correctly-formatted message."""
        self.useBzrBranches(direct_database=True)
        branch, tree = self.makeBranchWithCommit()
        job = RevisionsAddedJob.create(branch, 'rev1', 'rev1', '')
        message = job.getRevisionMessage('rev1', 1)
        self.assertEqual(
        '------------------------------------------------------------\n'
        'revno: 1\n'
        'committer: J. Random Hacker <jrandom@example.org>\n'
        'branch nick: nicholas\n'
        'timestamp: Thu 1970-01-01 00:16:40 +0000\n'
        'message:\n'
        '  rev1\n', message)

    def test_getRevisionMessage_with_merge_authors(self):
        """Merge authors are included after the main bzr log."""
        self.factory.makePerson(name='baz',
            displayname='Basil Blaine',
            email='baz@blaine.com',
            email_address_status=EmailAddressStatus.VALIDATED)
        job = self.makeRevisionsAddedWithMergeCommit()
        message = job.getRevisionMessage('rev2d-id', 1)
        self.assertEqual(
        u'Merge authors:\n'
        '  bar@\n'
        '  Basil Blaine (baz)\n'
        '  foo@\n'
        '  qux@\n'
        '------------------------------------------------------------\n'
        'revno: 2 [merge]\n'
        'committer: J. Random Hacker <jrandom@example.org>\n'
        'branch nick: nicholas\n'
        'timestamp: Thu 1970-01-01 00:16:40 +0000\n'
        'message:\n'
        '  rev2d\n', message)

    def test_getRevisionMessage_with_merge_authors_and_authors(self):
        """Merge authors are separate from normal authors."""
        job = self.makeRevisionsAddedWithMergeCommit(authors=['quxx'])
        message = job.getRevisionMessage('rev2d-id', 1)
        self.assertEqual(
        'Merge authors:\n'
        '  bar@\n'
        '  baz@blaine.com\n'
        '  foo@\n'
        '  qux@\n'
        '------------------------------------------------------------\n'
        'revno: 2 [merge]\n'
        'author: quxx\n'
        'committer: J. Random Hacker <jrandom@example.org>\n'
        'branch nick: nicholas\n'
        'timestamp: Thu 1970-01-01 00:16:40 +0000\n'
        'message:\n'
        '  rev2d\n', message)

    def makeJobAndBMP(self):
        job = self.makeRevisionsAddedWithMergeCommit()
        hacker = self.factory.makePerson(displayname='J. Random Hacker',
                                         name='jrandom')
        bmp = self.factory.makeBranchMergeProposal(target_branch=job.branch,
                                                   registrant=hacker)
        bmp.source_branch.last_scanned_id = 'rev3-id'
        return job, bmp

    def test_getRevisionMessage_with_related_BMP(self):
        """Information about related proposals is displayed."""
        job, bmp = self.makeJobAndBMP()
        with dbuser('send-branch-mail'):
            message = job.getRevisionMessage('rev2d-id', 1)
        self.assertEqual(
        'Merge authors:\n'
        '  bar@\n'
        '  baz@blaine.com\n'
        '  foo@\n'
        '  qux@\n'
        'Related merge proposals:\n'
        '  %s\n'
        '  proposed by: J. Random Hacker (jrandom)\n'
        '------------------------------------------------------------\n'
        'revno: 2 [merge]\n'
        'committer: J. Random Hacker <jrandom@example.org>\n'
        'branch nick: nicholas\n'
        'timestamp: Thu 1970-01-01 00:16:40 +0000\n'
        'message:\n'
        '  rev2d\n' % canonical_url(bmp), message)

    def test_getRevisionMessage_with_related_superseded_BMP(self):
        """Superseded proposals are skipped."""
        job, bmp = self.makeJobAndBMP()
        bmp2 = bmp.resubmit(bmp.registrant)
        with dbuser('send-branch-mail'):
            message = job.getRevisionMessage('rev2d-id', 1)
        self.assertEqual(
        'Merge authors:\n'
        '  bar@\n'
        '  baz@blaine.com\n'
        '  foo@\n'
        '  qux@\n'
        'Related merge proposals:\n'
        '  %s\n'
        '  proposed by: J. Random Hacker (jrandom)\n'
        '------------------------------------------------------------\n'
        'revno: 2 [merge]\n'
        'committer: J. Random Hacker <jrandom@example.org>\n'
        'branch nick: nicholas\n'
        'timestamp: Thu 1970-01-01 00:16:40 +0000\n'
        'message:\n'
        '  rev2d\n' % canonical_url(bmp2), message)

    def test_getRevisionMessage_with_BMP_with_requested_review(self):
        """Information about incomplete reviews is omitted.

        If there is a related branch merge proposal, and it has
        requested reviews which have not been completed, they are ignored.
        """
        job, bmp = self.makeJobAndBMP()
        reviewer = self.factory.makePerson()
        bmp.nominateReviewer(reviewer, bmp.registrant)
        with dbuser('send-branch-mail'):
            message = job.getRevisionMessage('rev2d-id', 1)
        self.assertEqual(
        'Merge authors:\n'
        '  bar@\n'
        '  baz@blaine.com\n'
        '  foo@\n'
        '  qux@\n'
        'Related merge proposals:\n'
        '  %s\n'
        '  proposed by: J. Random Hacker (jrandom)\n'
        '------------------------------------------------------------\n'
        'revno: 2 [merge]\n'
        'committer: J. Random Hacker <jrandom@example.org>\n'
        'branch nick: nicholas\n'
        'timestamp: Thu 1970-01-01 00:16:40 +0000\n'
        'message:\n'
        '  rev2d\n' % canonical_url(bmp), message)

    def test_getRevisionMessage_with_related_rejected_BMP(self):
        """The reviewer is shown for non-approved proposals."""
        job = self.makeRevisionsAddedWithMergeCommit()
        hacker = self.factory.makePerson(displayname='J. Random Hacker',
                                         name='jrandom')
        reviewer = self.factory.makePerson(displayname='J. Random Reviewer',
                                           name='jrandom2')
        job.branch.reviewer = reviewer
        bmp = self.factory.makeBranchMergeProposal(target_branch=job.branch,
                                                   registrant=hacker)
        bmp.rejectBranch(reviewer, 'rev3-id')
        bmp.source_branch.last_scanned_id = 'rev3-id'
        message = job.getRevisionMessage('rev2d-id', 1)
        self.assertEqual(
        'Merge authors:\n'
        '  bar@\n'
        '  baz@blaine.com\n'
        '  foo@\n'
        '  qux@\n'
        'Related merge proposals:\n'
        '  %s\n'
        '  proposed by: J. Random Hacker (jrandom)\n'
        '------------------------------------------------------------\n'
        'revno: 2 [merge]\n'
        'committer: J. Random Hacker <jrandom@example.org>\n'
        'branch nick: nicholas\n'
        'timestamp: Thu 1970-01-01 00:16:40 +0000\n'
        'message:\n'
        '  rev2d\n' % canonical_url(bmp), message)

    def test_email_format(self):
        """Contents of the email are as expected."""
        self.useBzrBranches(direct_database=True)
        db_branch, tree = self.create_branch_and_tree()
        first_revision = 'rev-1'
        tree.bzrdir.root_transport.put_bytes('hello.txt', 'Hello World\n')
        tree.add('hello.txt')
        # XXX: AaronBentley 2010-08-06 bug=614404: a bzr username is
        # required to generate the revision-id.
        with override_environ(BZR_EMAIL='me@example.com'):
            tree.commit(
                rev_id=first_revision, message="Log message",
                committer="Joe Bloggs <joe@example.com>",
                timestamp=1000000000.0, timezone=0)
            tree.bzrdir.root_transport.put_bytes(
                'hello.txt', 'Hello World\n\nFoo Bar\n')
            second_revision = 'rev-2'
            tree.commit(
                rev_id=second_revision, message="Extended contents",
                committer="Joe Bloggs <joe@example.com>",
                timestamp=1000100000.0, timezone=0)
        switch_dbuser('branchscanner')
        self.updateDBRevisions(db_branch, tree.branch,
            branch_revision_history(tree.branch))
        expected = (
            u"-" * 60 + '\n'
            "revno: 1" '\n'
            "committer: Joe Bloggs <joe@example.com>" '\n'
            "branch nick: %s" '\n'
            "timestamp: Sun 2001-09-09 01:46:40 +0000" '\n'
            "message:" '\n'
            "  Log message" '\n'
            "added:" '\n'
            "  hello.txt" '\n' % tree.branch.nick)
        job = RevisionsAddedJob.create(db_branch, '', '', '')
        self.assertEqual(
            job.getRevisionMessage(first_revision, 1), expected)

        expected_message = (
            u"-" * 60 + '\n'
            "revno: 2" '\n'
            "committer: Joe Bloggs <joe@example.com>" '\n'
            "branch nick: %s" '\n'
            "timestamp: Mon 2001-09-10 05:33:20 +0000" '\n'
            "message:" '\n'
            "  Extended contents" '\n'
            "modified:" '\n'
            "  hello.txt" '\n' % tree.branch.nick)
        tree.branch.lock_read()
        tree.branch.unlock()
        message = job.getRevisionMessage(second_revision, 2)
        self.assertEqual(message, expected_message)

    def test_message_encoding(self):
        """Test handling of non-ASCII commit messages."""
        self.useBzrBranches(direct_database=True)
        db_branch, tree = self.create_branch_and_tree()
        rev_id = 'rev-1'
        # XXX: AaronBentley 2010-08-06 bug=614404: a bzr username is
        # required to generate the revision-id.
        with override_environ(BZR_EMAIL='me@example.com'):
            tree.commit(
                rev_id=rev_id, message=u"Non ASCII: \xe9",
                committer=u"Non ASCII: \xed", timestamp=1000000000.0,
                timezone=0)
        switch_dbuser('branchscanner')
        self.updateDBRevisions(db_branch, tree.branch,
            branch_revision_history(tree.branch))
        job = RevisionsAddedJob.create(db_branch, '', '', '')
        message = job.getRevisionMessage(rev_id, 1)
        # The revision message must be a unicode object.
        expected = (
            u'-' * 60 + '\n'
            u"revno: 1" '\n'
            u"committer: Non ASCII: \xed" '\n'
            u"branch nick: %s" '\n'
            u"timestamp: Sun 2001-09-09 01:46:40 +0000" '\n'
            u"message:" '\n'
            u"  Non ASCII: \xe9" '\n' % tree.branch.nick)
        self.assertEqual(message, expected)

    def test_getMailerForRevision(self):
        """The mailer for the revision is as expected."""
        self.useBzrBranches(direct_database=True)
        branch, tree = self.makeBranchWithCommit()
        revision = tree.branch.repository.get_revision('rev1')
        job = RevisionsAddedJob.create(branch, 'rev1', 'rev1', '')
        mailer = job.getMailerForRevision(revision, 1, True)
        subject = mailer.generateEmail(
            branch.registrant.preferredemail.email, branch.registrant).subject
        self.assertEqual(
            '[Branch ~jrandom/foo/bar] Rev 1: rev1', subject)

    def test_only_nodiff_subscribers_means_no_diff_generated(self):
        """No diff is generated when no subscribers need it."""
        switch_dbuser('launchpad')
        self.useBzrBranches(direct_database=True)
        branch, tree = self.create_branch_and_tree()
        subscriptions = branch.getSubscriptionsByLevel(
            [BranchSubscriptionNotificationLevel.FULL])
        for s in subscriptions:
            s.max_diff_lines = BranchSubscriptionDiffSize.NODIFF
        job = RevisionsAddedJob.create(branch, '', '', '')
        self.assertFalse(job.generateDiffs())


class TestRosettaUploadJob(TestCaseWithFactory):
    """Tests for RosettaUploadJob."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestRosettaUploadJob, self).setUp()
        self.series = None

    def _makeBranchWithTreeAndFile(self, file_name, file_content=None):
        return self._makeBranchWithTreeAndFiles(((file_name, file_content), ))

    def _makeBranchWithTreeAndFiles(self, files):
        """Create a branch with a tree that contains the given files.

        :param files: A list of pairs of file names and file content. file
            content is a byte string and may be None or missing completely,
            in which case an arbitrary unique string is used.
        :returns: The revision of the first commit.
        """
        self.useBzrBranches(direct_database=True)
        self.branch, self.tree = self.create_branch_and_tree()
        return self._commitFilesToTree(files, 'First commit')

    def _makeRosettaUploadJob(self):
        """Create a `RosettaUploadJob`."""
        # RosettaUploadJob's parent BranchJob is joined to Job through
        # BranchJob.job, but in tests those two ids can also be the same.
        # This may hide broken joins, so make sure that the ids are not
        # identical.
        # There are at least as many Jobs as BranchJobs, so we can whack
        # the two out of any accidental sync by advancing the Job.id
        # sequence.
        dummy = Job()
        dummy.sync()
        dummy.destroySelf()

        # Now create the RosettaUploadJob.
        job = RosettaUploadJob.create(self.branch, NULL_REVISION)
        job.job.sync()
        job.context.sync()
        return job

    def _commitFilesToTree(self, files, commit_message=None):
        """Add files to the tree.

        :param files: A list of pairs of file names and file content. file
            content is a byte string and may be None or missing completely,
            in which case an arbitrary unique string is used.
        :returns: The revision of this commit.
        """
        for file_pair in files:
            file_name = file_pair[0]
            try:
                file_content = file_pair[1]
                if file_content is None:
                    raise IndexError  # Same as if missing.
            except IndexError:
                file_content = self.factory.getUniqueString()
            dname = os.path.dirname(file_name)
            self.tree.bzrdir.root_transport.clone(dname).create_prefix()
            self.tree.bzrdir.root_transport.put_bytes(file_name, file_content)
        if len(files) > 0:
            self.tree.smart_add(
                [self.tree.abspath(file_pair[0]) for file_pair in files])
        if commit_message is None:
            commit_message = self.factory.getUniqueString('commit')
        # XXX: AaronBentley 2010-08-06 bug=614404: a bzr username is
        # required to generate the revision-id.
        with override_environ(BZR_EMAIL='me@example.com'):
            revision_id = self.tree.commit(commit_message)
        self.branch.last_scanned_id = revision_id
        self.branch.last_mirrored_id = revision_id
        return revision_id

    def _makeProductSeries(self, mode):
        if self.series is None:
            self.series = self.factory.makeProductSeries()
            self.series.branch = self.branch
            self.series.translations_autoimport_mode = mode

    def _runJobWithFile(self, import_mode, file_name, file_content=None):
        return self._runJobWithFiles(
            import_mode, ((file_name, file_content), ))

    def _runJobWithFiles(self, import_mode, files,
                         do_upload_translations=False):
        self._makeBranchWithTreeAndFiles(files)
        return self._runJob(import_mode, NULL_REVISION,
                            do_upload_translations)

    def _runJob(self, import_mode, revision_id,
                do_upload_translations=False):
        self._makeProductSeries(import_mode)
        job = RosettaUploadJob.create(self.branch, revision_id,
                                      do_upload_translations)
        if job is not None:
            job.run()
        queue = getUtility(ITranslationImportQueue)
        # Using getAllEntries also asserts that the right product series
        # was used in the upload.
        return list(queue.getAllEntries(target=self.series))

    def test_providesInterface(self):
        # RosettaUploadJob implements IRosettaUploadJob.
        self.branch = self.factory.makeAnyBranch()
        self._makeProductSeries(
            TranslationsBranchImportMode.IMPORT_TEMPLATES)
        job = self._makeRosettaUploadJob()
        self.assertProvides(job, IRosettaUploadJob)

    def test_upload_pot(self):
        # A POT can be uploaded to a product series that is
        # configured to do so, other files are not uploaded.
        pot_name = "foo.pot"
        entries = self._runJobWithFiles(
            TranslationsBranchImportMode.IMPORT_TEMPLATES,
            ((pot_name,), ('eo.po',), ('README',)))
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(pot_name, entry.path)

    def test_upload_pot_subdir(self):
        # A POT can be uploaded from a subdirectory.
        pot_path = "subdir/foo.pot"
        entries = self._runJobWithFile(
            TranslationsBranchImportMode.IMPORT_TEMPLATES, pot_path)
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(pot_path, entry.path)

    def test_init_translation_file_lists_skip_dirs(self):
        # The method _init_translation_file_lists extracts all translation
        # files from the branch but does not add changed directories to the
        # template_files_changed and translation_files_changed lists .
        pot_path = u"subdir/foo.pot"
        pot_content = self.factory.getUniqueString()
        po_path = u"subdir/foo.po"
        po_content = self.factory.getUniqueString()
        self._makeBranchWithTreeAndFiles(((pot_path, pot_content),
                                          (po_path, po_content)))
        self._makeProductSeries(TranslationsBranchImportMode.NO_IMPORT)
        job = RosettaUploadJob.create(self.branch, NULL_REVISION, True)
        job._init_translation_file_lists()

        self.assertEqual([(pot_path, pot_content)],
                         job.template_files_changed)
        self.assertEqual([(po_path, po_content)],
                         job.translation_files_changed)

    def test_upload_xpi_template(self):
        # XPI templates are indentified by a special name. They are imported
        # like POT files.
        pot_name = "en-US.xpi"
        entries = self._runJobWithFiles(
            TranslationsBranchImportMode.IMPORT_TEMPLATES,
            ((pot_name,), ('eo.xpi',), ('README',)))
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(pot_name, entry.path)

    def test_upload_empty_pot(self):
        # An empty POT cannot be uploaded, if if the product series is
        # configured for template import.
        entries = self._runJobWithFile(
            TranslationsBranchImportMode.IMPORT_TEMPLATES, 'empty.pot', '')
        self.assertEqual(entries, [])

    def test_upload_hidden_pot(self):
        # A POT cannot be uploaded if its name starts with a dot.
        entries = self._runJobWithFile(
            TranslationsBranchImportMode.IMPORT_TEMPLATES, '.hidden.pot')
        self.assertEqual(entries, [])

    def test_upload_pot_hidden_in_subdirectory(self):
        # In fact, if any parent directory is hidden, the file will not be
        # imported.
        entries = self._runJobWithFile(
            TranslationsBranchImportMode.IMPORT_TEMPLATES,
            'bar/.hidden/bla/foo.pot')
        self.assertEqual(entries, [])

    def test_upload_pot_uploader(self):
        # The uploader of a POT is the series owner.
        entries = self._runJobWithFile(
            TranslationsBranchImportMode.IMPORT_TEMPLATES, 'foo.pot')
        entry = entries[0]
        self.assertEqual(self.series.owner, entry.importer)

    def test_upload_pot_content(self):
        # The content of the uploaded file is stored in the librarian.
        # The uploader of a POT is the series owner.
        POT_CONTENT = "pot content\n"
        self._runJobWithFile(
            TranslationsBranchImportMode.IMPORT_TEMPLATES,
            'foo.pot', POT_CONTENT)
        # Commit so that the file is stored in the librarian.
        transaction.commit()
        self.assertEqual(POT_CONTENT, get_newest_librarian_file().read())

    def test_upload_changed_files(self):
        # Only changed files are queued for import.
        pot_name = "foo.pot"
        revision_id = self._makeBranchWithTreeAndFiles(
            ((pot_name,), ('eo.po',), ('README',)))
        self._commitFilesToTree(((pot_name, ), ))
        entries = self._runJob(
            TranslationsBranchImportMode.IMPORT_TEMPLATES, revision_id)
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(pot_name, entry.path)

    def test_upload_to_no_import_series(self):
        # Nothing can be uploaded to a product series that is
        # not configured to do so.
        entries = self._runJobWithFiles(
            TranslationsBranchImportMode.NO_IMPORT,
            (('foo.pot',), ('eo.po',), ('README',)))
        self.assertEqual([], entries)

    def test_upload_translations(self):
        # A PO file can be uploaded if the series is configured for it.
        po_path = "eo.po"
        entries = self._runJobWithFile(
            TranslationsBranchImportMode.IMPORT_TRANSLATIONS, po_path)
        self.assertEqual(1, len(entries))
        entry = entries[0]
        self.assertEqual(po_path, entry.path)

    def test_upload_template_and_translations(self):
        # The same configuration will upload template and translation files
        # in one go. Other files are still ignored.
        entries = self._runJobWithFiles(
            TranslationsBranchImportMode.IMPORT_TRANSLATIONS,
            (('foo.pot',), ('eo.po',), ('fr.po',), ('README',)))
        self.assertEqual(3, len(entries))

    def test_upload_extra_translations_no_import(self):
        # Even if the series is configured not to upload any files, the
        # job can be told to upload template and translation files.
        entries = self._runJobWithFiles(
            TranslationsBranchImportMode.NO_IMPORT,
            (('foo.pot',), ('eo.po',), ('fr.po',), ('README',)), True)
        self.assertEqual(3, len(entries))

    def test_upload_extra_translations_import_templates(self):
        # Even if the series is configured to only upload template files, the
        # job can be told to upload translation files, too.
        entries = self._runJobWithFiles(
            TranslationsBranchImportMode.IMPORT_TEMPLATES,
            (('foo.pot',), ('eo.po',), ('fr.po',), ('README',)), True)
        self.assertEqual(3, len(entries))

    def test_upload_approved(self):
        # A single new entry should be created approved.
        entries = self._runJobWithFile(
            TranslationsBranchImportMode.IMPORT_TEMPLATES, 'foo.pot')
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(RosettaImportStatus.APPROVED, entry.status)

    def test_upload_simplest_case_approved(self):
        # A single new entry should be created approved and linked to the
        # only POTemplate object in the database, if there is only one such
        # object for this product series.
        self._makeBranchWithTreeAndFile('foo.pot')
        self._makeProductSeries(TranslationsBranchImportMode.IMPORT_TEMPLATES)
        potemplate = self.factory.makePOTemplate(self.series)
        entries = self._runJob(None, NULL_REVISION)
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(potemplate, entry.potemplate)
        self.assertEqual(RosettaImportStatus.APPROVED, entry.status)

    def test_upload_multiple_approved(self):
        # A single new entry should be created approved and linked to the
        # only POTemplate object in the database, if there is only one such
        # object for this product series.
        self._makeBranchWithTreeAndFiles(
            [('foo.pot', None), ('bar.pot', None)])
        self._makeProductSeries(TranslationsBranchImportMode.IMPORT_TEMPLATES)
        self.factory.makePOTemplate(self.series, path='foo.pot')
        self.factory.makePOTemplate(self.series, path='bar.pot')
        entries = self._runJob(None, NULL_REVISION)
        self.assertEqual(len(entries), 2)
        self.assertEqual(RosettaImportStatus.APPROVED, entries[0].status)
        self.assertEqual(RosettaImportStatus.APPROVED, entries[1].status)

    def test_iterReady_job_type(self):
        # iterReady only returns RosettaUploadJobs.
        self._makeBranchWithTreeAndFiles([])
        self._makeProductSeries(
            TranslationsBranchImportMode.IMPORT_TEMPLATES)
        # Add a job that is not a RosettaUploadJob.
        branch = self.factory.makeBranch(
            branch_format=BranchFormat.BZR_BRANCH_6)
        BranchUpgradeJob.create(branch, branch.owner)
        ready_jobs = list(RosettaUploadJob.iterReady())
        self.assertEqual([], ready_jobs)

    def test_iterReady_not_ready(self):
        # iterReady only returns RosettaUploadJobs in ready state.
        self._makeBranchWithTreeAndFiles([])
        self._makeProductSeries(
            TranslationsBranchImportMode.IMPORT_TEMPLATES)
        # Add a job and complete it -> not in ready state.
        job = self._makeRosettaUploadJob()
        job.job.start()
        job.job.complete()
        ready_jobs = list(RosettaUploadJob.iterReady())
        self.assertEqual([], ready_jobs)

    def test_iterReady_revision_ids_differ(self):
        # iterReady does not return jobs for branches where last_scanned_id
        # and last_mirror_id are different.
        self._makeBranchWithTreeAndFiles([])
        self.branch.last_scanned_id = NULL_REVISION  # Was not scanned yet.
        self._makeProductSeries(
            TranslationsBranchImportMode.IMPORT_TEMPLATES)
        # Put the job in ready state.
        self._makeRosettaUploadJob()
        ready_jobs = list(RosettaUploadJob.iterReady())
        self.assertEqual([], ready_jobs)

    def test_iterReady(self):
        # iterReady only returns RosettaUploadJob in ready state.
        self._makeBranchWithTreeAndFiles([])
        self._makeProductSeries(
            TranslationsBranchImportMode.IMPORT_TEMPLATES)
        # Put the job in ready state.
        job = self._makeRosettaUploadJob()
        ready_jobs = list(RosettaUploadJob.iterReady())
        self.assertEqual([job], ready_jobs)

    def test_findUnfinishedJobs(self):
        # findUnfinishedJobs returns jobs that haven't finished yet.
        self._makeBranchWithTreeAndFiles([])
        self._makeProductSeries(
            TranslationsBranchImportMode.IMPORT_TEMPLATES)
        job = self._makeRosettaUploadJob()
        unfinished_jobs = list(RosettaUploadJob.findUnfinishedJobs(
            self.branch))
        self.assertEqual([job.context], unfinished_jobs)

    def test_findUnfinishedJobs_does_not_find_finished_jobs(self):
        # findUnfinishedJobs ignores completed jobs.
        self._makeBranchWithTreeAndFiles([])
        self._makeProductSeries(
            TranslationsBranchImportMode.IMPORT_TEMPLATES)
        job = self._makeRosettaUploadJob()
        job.job.start()
        job.job.complete()
        unfinished_jobs = list(RosettaUploadJob.findUnfinishedJobs(
            self.branch))
        self.assertEqual([], unfinished_jobs)

    def test_findUnfinishedJobs_does_not_find_failed_jobs(self):
        # findUnfinishedJobs ignores failed jobs.
        self._makeBranchWithTreeAndFiles([])
        self._makeProductSeries(
            TranslationsBranchImportMode.IMPORT_TEMPLATES)
        job = self._makeRosettaUploadJob()
        job.job.start()
        job.job.complete()
        job.job._status = JobStatus.FAILED
        unfinished_jobs = list(RosettaUploadJob.findUnfinishedJobs(
            self.branch))
        self.assertEqual([], unfinished_jobs)


class TestViaCelery(TestCaseWithFactory):

    layer = CeleryBzrsyncdJobLayer

    def test_RosettaUploadJob(self):
        """Ensure RosettaUploadJob can run under Celery."""
        self.useBzrBranches(direct_database=True)
        self.useFixture(FeatureFixture({
            'jobs.celery.enabled_classes': 'BranchScanJob RosettaUploadJob'
        }))
        db_branch = self.factory.makeAnyBranch()
        self.createBzrBranch(db_branch)
        commit = DirectBranchCommit(db_branch, no_race_check=True)
        commit.writeFile('foo.pot', 'gibberish')
        with person_logged_in(db_branch.owner):
            # wait for branch scan
            with block_on_job(self):
                commit.commit('message')
                transaction.commit()
        series = self.factory.makeProductSeries(branch=db_branch)
        with block_on_job(self):
            RosettaUploadJob.create(
                commit.db_branch, NULL_REVISION,
                force_translations_upload=True)
            transaction.commit()
        queue = getUtility(ITranslationImportQueue)
        entries = list(queue.getAllEntries(target=series))
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual('foo.pot', entry.path)


class TestReclaimBranchSpaceJob(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def cleanBranchArea(self):
        """Ensure that the branch area is present and empty."""
        mirrored = config.codehosting.mirrored_branches_root
        shutil.rmtree(mirrored, ignore_errors=True)
        os.makedirs(mirrored)
        self.addCleanup(shutil.rmtree, mirrored)

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.cleanBranchArea()

    def test_providesInterface(self):
        # ReclaimBranchSpaceJob implements IReclaimBranchSpaceJob.
        job = getUtility(IReclaimBranchSpaceJobSource).create(
            self.factory.getUniqueInteger())
        self.assertProvides(job, IReclaimBranchSpaceJob)

    def test_scheduled_in_future(self):
        # A freshly created ReclaimBranchSpaceJob is scheduled to run in a
        # week's time.
        job = getUtility(IReclaimBranchSpaceJobSource).create(
            self.factory.getUniqueInteger())
        self.assertEqual(
            datetime.timedelta(days=7),
            job.job.scheduled_start - job.job.date_created)

    def test_stores_id(self):
        # An instance of ReclaimBranchSpaceJob stores the ID of the branch
        # that has been deleted.
        branch_id = self.factory.getUniqueInteger()
        job = getUtility(IReclaimBranchSpaceJobSource).create(branch_id)
        self.assertEqual(branch_id, job.branch_id)

    def makeJobReady(self, job):
        """Force `job` to be scheduled to run now.

        New `ReclaimBranchSpaceJob`s are scheduled to run a week after
        creation, so to be able to test running the job we have to force them
        to be scheduled now.
        """
        removeSecurityProxy(job).job.scheduled_start = UTC_NOW

    def runReadyJobs(self):
        """Run all ready `ReclaimBranchSpaceJob`s with the appropriate dbuser.
        """
        switch_dbuser('reclaim-branch-space')
        job_count = 0
        for job in ReclaimBranchSpaceJob.iterReady():
            job.run()
            job_count += 1
        self.assertTrue(job_count > 0, "No jobs ran!")

    def test_run_no_branch_on_disk(self):
        # Running a job to reclaim space for a branch that was never pushed to
        # does nothing quietly.
        branch_id = self.factory.getUniqueInteger()
        job = getUtility(IReclaimBranchSpaceJobSource).create(branch_id)
        self.makeJobReady(job)
        # Just "assertNotRaises"
        self.runReadyJobs()

    def test_run_with_branch_on_disk(self):
        # Running a job to reclaim space for a branch that was pushed to
        # but never mirrored removes the branch from the hosted area.
        branch_id = self.factory.getUniqueInteger()
        job = getUtility(IReclaimBranchSpaceJobSource).create(branch_id)
        self.makeJobReady(job)
        branch_path = os.path.join(
            config.codehosting.mirrored_branches_root,
            branch_id_to_path(branch_id), '.bzr')
        os.makedirs(branch_path)
        self.runReadyJobs()
        self.assertFalse(os.path.exists(branch_path))
