# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__all__ = [
    'BranchJob',
    'BranchScanJob',
    'BranchJobDerived',
    'BranchJobType',
    'BranchUpgradeJob',
    'RevisionsAddedJob',
    'RevisionMailJob',
    'RosettaUploadJob',
]

import contextlib
import operator
import os
import shutil
from StringIO import StringIO
import tempfile

from bzrlib.branch import Branch as BzrBranch
from bzrlib.diff import show_diff_trees
from bzrlib.errors import (
    NoSuchFile,
    NotBranchError,
    )
from bzrlib.log import (
    log_formatter,
    show_log,
    )
from bzrlib.revision import NULL_REVISION
from bzrlib.revisionspec import RevisionInfo
from bzrlib.transport import get_transport
from bzrlib.upgrade import upgrade
from lazr.delegates import delegates
from lazr.enum import (
    DBEnumeratedType,
    DBItem,
    )
import simplejson
from sqlobject import (
    ForeignKey,
    SQLObjectNotFound,
    StringCol,
    )
from storm.exceptions import LostObjectError
from storm.expr import (
    And,
    SQL,
    )
from storm.locals import Store
import transaction
from zope.component import getUtility
from zope.interface import (
    classProvides,
    implements,
    )

from lp.code.bzr import (
    branch_revision_history,
    get_branch_formats,
    )
from lp.code.enums import (
    BranchMergeProposalStatus,
    BranchSubscriptionDiffSize,
    BranchSubscriptionNotificationLevel,
    )
from lp.code.interfaces.branchjob import (
    IBranchJob,
    IBranchScanJob,
    IBranchScanJobSource,
    IBranchUpgradeJob,
    IBranchUpgradeJobSource,
    IReclaimBranchSpaceJob,
    IReclaimBranchSpaceJobSource,
    IRevisionMailJob,
    IRevisionMailJobSource,
    IRevisionsAddedJob,
    IRosettaUploadJob,
    IRosettaUploadJobSource,
    )
from lp.code.mail.branch import BranchMailer
from lp.code.model.branch import Branch
from lp.code.model.branchmergeproposal import BranchMergeProposal
from lp.code.model.revision import RevisionSet
from lp.codehosting.bzrutils import (
    read_locked,
    server,
    )
from lp.codehosting.scanner.bzrsync import BzrSync
from lp.codehosting.vfs import (
    get_ro_server,
    get_rw_server,
    )
from lp.codehosting.vfs.branchfs import get_real_branch_path
from lp.registry.interfaces.productseries import IProductSeriesSet
from lp.scripts.helpers import TransactionFreeOperation
from lp.services.config import config
from lp.services.database.enumcol import EnumCol
from lp.services.database.interfaces import (
    IMasterStore,
    IStore,
    )
from lp.services.database.locking import (
    AdvisoryLockHeld,
    LockType,
    try_advisory_lock,
    )
from lp.services.database.sqlbase import SQLBase
from lp.services.job.interfaces.job import JobStatus
from lp.services.job.model.job import (
    EnumeratedSubclass,
    Job,
    )
from lp.services.job.runner import (
    BaseRunnableJob,
    BaseRunnableJobSource,
    )
from lp.services.mail.sendmail import format_address_for_person
from lp.services.webapp import (
    canonical_url,
    errorlog,
    )
from lp.translations.interfaces.translationimportqueue import (
    ITranslationImportQueue,
    )
from lp.translations.interfaces.translations import (
    TranslationsBranchImportMode,
    )
from lp.translations.model.approver import TranslationBranchApprover
from lp.translations.utilities.translation_import import TranslationImporter

# Use at most the first 100 characters of the commit message for the subject
# the mail describing the revision.
SUBJECT_COMMIT_MESSAGE_LENGTH = 100


class BranchJobType(DBEnumeratedType):
    """Values that ICodeImportJob.state can take."""

    STATIC_DIFF = DBItem(0, """
        Static Diff

        This job runs against a branch to produce a diff that cannot change.
        """)

    REVISION_MAIL = DBItem(1, """
        Revision Mail

        This job runs against a branch to send emails about revisions.
        """)

    REVISIONS_ADDED_MAIL = DBItem(2, """
        Revisions Added Mail

        This job runs against a branch to send emails about added revisions.
        """)

    ROSETTA_UPLOAD = DBItem(3, """
        Rosetta Upload

        This job runs against a branch to upload translation files to rosetta.
        """)

    UPGRADE_BRANCH = DBItem(4, """
        Upgrade Branch

        This job upgrades the branch in the hosted area.
        """)

    RECLAIM_BRANCH_SPACE = DBItem(5, """
        Reclaim Branch Space

        This job removes a branch that have been deleted from the database
        from disk.
        """)

    TRANSLATION_TEMPLATES_BUILD = DBItem(6, """
        Generate translation templates

        This job generates translations templates from a source branch.
        """)

    SCAN_BRANCH = DBItem(7, """
        Scan Branch

        This job scans a branch for new revisions.
        """)


class BranchJob(SQLBase):
    """Base class for jobs related to branches."""

    implements(IBranchJob)

    _table = 'BranchJob'

    job = ForeignKey(foreignKey='Job', notNull=True)

    branch = ForeignKey(foreignKey='Branch')

    job_type = EnumCol(enum=BranchJobType, notNull=True)

    _json_data = StringCol(dbName='json_data')

    @property
    def metadata(self):
        return simplejson.loads(self._json_data)

    def __init__(self, branch, job_type, metadata, **job_args):
        """Constructor.

        Extra keyword parameters are used to construct the underlying Job
        object.

        :param branch: The database branch this job relates to.
        :param job_type: The BranchJobType of this job.
        :param metadata: The type-specific variables, as a JSON-compatible
            dict.
        """
        json_data = simplejson.dumps(metadata)
        SQLBase.__init__(
            self, job=Job(**job_args), branch=branch, job_type=job_type,
            _json_data=json_data)

    def destroySelf(self):
        """See `IBranchJob`."""
        SQLBase.destroySelf(self)
        self.job.destroySelf()

    def makeDerived(self):
        return BranchJobDerived.makeSubclass(self)


class BranchJobDerived(BaseRunnableJob):

    __metaclass__ = EnumeratedSubclass

    delegates(IBranchJob)

    def __init__(self, branch_job):
        self.context = branch_job

    def __repr__(self):
        branch = self.branch
        return '<%(job_type)s branch job (%(id)s) for %(branch)s>' % {
            'job_type': self.context.job_type.name,
            'id': self.context.id,
            'branch': branch.unique_name,
            }

    # XXX: henninge 2009-02-20 bug=331919: These two standard operators
    # should be implemented by delegates().
    def __eq__(self, other):
        # removeSecurityProxy, since 'other' might well be a delegated object
        # and the context attribute is not exposed by design.
        from zope.security.proxy import removeSecurityProxy
        return (self.__class__ == other.__class__ and
                self.context == removeSecurityProxy(other).context)

    def __ne__(self, other):
        return not (self == other)

    @classmethod
    def iterReady(cls):
        """See `IRevisionMailJobSource`."""
        jobs = IMasterStore(Branch).find(
            (BranchJob),
            And(BranchJob.job_type == cls.class_job_type,
                BranchJob.job == Job.id,
                Job.id.is_in(Job.ready_jobs)))
        return (cls(job) for job in jobs)

    @classmethod
    def get(cls, key):
        """Return the instance of this class whose key is supplied.

        :raises: SQLObjectNotFound
        """
        instance = IStore(BranchJob).get(BranchJob, key)
        if instance is None or instance.job_type != cls.class_job_type:
            raise SQLObjectNotFound(
                'No occurrence of %s has key %s' % (cls.__name__, key))
        return cls(instance)

    def getOopsVars(self):
        """See `IRunnableJob`."""
        vars = BaseRunnableJob.getOopsVars(self)
        vars.extend([
            ('branch_job_id', self.context.id),
            ('branch_job_type', self.context.job_type.title)])
        if self.context.branch is not None:
            vars.append(('branch_name', self.context.branch.unique_name))
        return vars

    def getErrorRecipients(self):
        if self.requester is None:
            return []
        return [format_address_for_person(self.requester)]


class BranchScanJob(BranchJobDerived):
    """A Job that scans a branch for new revisions."""

    implements(IBranchScanJob)

    classProvides(IBranchScanJobSource)
    class_job_type = BranchJobType.SCAN_BRANCH
    memory_limit = 2 * (1024 ** 3)

    max_retries = 5

    retry_error_types = (AdvisoryLockHeld,)

    task_queue = 'bzrsyncd_job'

    config = config.IBranchScanJobSource

    @classmethod
    def create(cls, branch):
        """See `IBranchScanJobSource`."""
        branch_job = BranchJob(
            branch, cls.class_job_type, {'branch_name': branch.unique_name})
        return cls(branch_job)

    def __init__(self, branch_job):
        super(BranchScanJob, self).__init__(branch_job)
        self._cached_branch_name = self.metadata['branch_name']

    def run(self):
        """See `IBranchScanJob`."""
        from lp.services.scripts import log
        with server(get_ro_server(), no_replace=True):
            try:
                with try_advisory_lock(
                    LockType.BRANCH_SCAN, self.branch.id,
                    Store.of(self.branch)):
                    bzrsync = BzrSync(self.branch, log)
                    bzrsync.syncBranchAndClose()
            except LostObjectError:
                log.warning('Skipping branch %s because it has been deleted.'
                    % self._cached_branch_name)


class BranchUpgradeJob(BranchJobDerived):
    """A Job that upgrades branches to the current stable format."""

    implements(IBranchUpgradeJob)

    classProvides(IBranchUpgradeJobSource)
    class_job_type = BranchJobType.UPGRADE_BRANCH

    user_error_types = (NotBranchError,)

    task_queue = 'branch_write_job'

    config = config.IBranchUpgradeJobSource

    def getOperationDescription(self):
        return 'upgrading a branch'

    @classmethod
    def create(cls, branch, requester):
        """See `IBranchUpgradeJobSource`."""
        branch.checkUpgrade()
        branch_job = BranchJob(
            branch, cls.class_job_type, {}, requester=requester)
        return cls(branch_job)

    def run(self, _check_transaction=False):
        """See `IBranchUpgradeJob`."""
        # Set up the new branch structure
        with server(get_rw_server(), no_replace=True):
            upgrade_branch_path = tempfile.mkdtemp()
            try:
                upgrade_transport = get_transport(upgrade_branch_path)
                upgrade_transport.mkdir('.bzr')
                source_branch_transport = get_transport(
                    self.branch.getInternalBzrUrl())
                source_branch_transport.clone('.bzr').copy_tree_to_transport(
                    upgrade_transport.clone('.bzr'))
                transaction.commit()
                upgrade_branch = BzrBranch.open_from_transport(
                    upgrade_transport)

                # No transactions are open so the DB connection won't be
                # killed.
                with TransactionFreeOperation():
                    # Perform the upgrade.
                    upgrade(upgrade_branch.base)

                # Re-open the branch, since its format has changed.
                upgrade_branch = BzrBranch.open_from_transport(
                    upgrade_transport)
                source_branch = BzrBranch.open_from_transport(
                    source_branch_transport)

                source_branch.lock_write()
                upgrade_branch.pull(source_branch)
                upgrade_branch.fetch(source_branch)
                source_branch.unlock()

                # Move the branch in the old format to backup.bzr
                try:
                    source_branch_transport.delete_tree('backup.bzr')
                except NoSuchFile:
                    pass
                source_branch_transport.rename('.bzr', 'backup.bzr')
                source_branch_transport.mkdir('.bzr')
                upgrade_transport.clone('.bzr').copy_tree_to_transport(
                    source_branch_transport.clone('.bzr'))

                # Re-open the source branch again.
                source_branch = BzrBranch.open_from_transport(
                    source_branch_transport)

                formats = get_branch_formats(source_branch)

                self.branch.branchChanged(
                    self.branch.stacked_on,
                    self.branch.last_scanned_id,
                    *formats)
            finally:
                shutil.rmtree(upgrade_branch_path)


class RevisionMailJob(BranchJobDerived):
    """A Job that sends a mail for a scan of a Branch."""

    implements(IRevisionMailJob)

    classProvides(IRevisionMailJobSource)

    class_job_type = BranchJobType.REVISION_MAIL

    config = config.IRevisionMailJobSource

    @classmethod
    def create(cls, branch, revno, from_address, body, subject):
        """See `IRevisionMailJobSource`."""
        metadata = {
            'revno': revno,
            'from_address': from_address,
            'body': body,
            'subject': subject,
        }
        branch_job = BranchJob(branch, cls.class_job_type, metadata)
        return cls(branch_job)

    @property
    def revno(self):
        return self.metadata['revno']

    @property
    def from_address(self):
        return str(self.metadata['from_address'])

    @property
    def body(self):
        return self.metadata['body']

    @property
    def subject(self):
        return self.metadata['subject']

    def getMailer(self):
        """Return a BranchMailer for this job."""
        return BranchMailer.forRevision(
            self.branch, self.revno, self.from_address, self.body,
            None, self.subject)

    def run(self):
        """See `IRevisionMailJob`."""
        self.getMailer().sendAll()


class RevisionsAddedJob(BranchJobDerived):
    """A job for sending emails about added revisions."""
    implements(IRevisionsAddedJob)

    class_job_type = BranchJobType.REVISIONS_ADDED_MAIL

    config = config.IRevisionsAddedJobSource

    @classmethod
    def create(cls, branch, last_scanned_id, last_revision_id,
               from_address):
        metadata = {'last_scanned_id': last_scanned_id,
                    'last_revision_id': last_revision_id,
                    'from_address': from_address}
        branch_job = BranchJob(branch, cls.class_job_type, metadata)
        return RevisionsAddedJob(branch_job)

    def __init__(self, context):
        super(RevisionsAddedJob, self).__init__(context)
        self._bzr_branch = None
        self._tree_cache = {}

    @property
    def bzr_branch(self):
        if self._bzr_branch is None:
            self._bzr_branch = self.branch.getBzrBranch()
        return self._bzr_branch

    @property
    def last_scanned_id(self):
        return self.metadata['last_scanned_id']

    @property
    def last_revision_id(self):
        return self.metadata['last_revision_id']

    @property
    def from_address(self):
        return self.metadata['from_address']

    def iterAddedMainline(self):
        """Iterate through revisions added to the mainline."""
        repository = self.bzr_branch.repository
        added_revisions = repository.get_graph().find_unique_ancestors(
            self.last_revision_id, [self.last_scanned_id])
        # Avoid hitting the database since bzrlib makes it easy to check.
        # There are possibly more efficient ways to get the mainline
        # revisions, but this is simple and it works.
        history = branch_revision_history(self.bzr_branch)
        for num, revid in enumerate(history):
            if revid in added_revisions:
                yield repository.get_revision(revid), num + 1

    def generateDiffs(self):
        """Determine whether to generate diffs."""
        for subscription in self.branch.subscriptions:
            if (subscription.max_diff_lines !=
                BranchSubscriptionDiffSize.NODIFF):
                return True
        else:
            return False

    def run(self):
        """Send all the emails about all the added revisions."""
        diff_levels = (BranchSubscriptionNotificationLevel.DIFFSONLY,
                       BranchSubscriptionNotificationLevel.FULL)
        subscriptions = self.branch.getSubscriptionsByLevel(diff_levels)
        if not subscriptions:
            return
        with server(get_ro_server(), no_replace=True):
            with read_locked(self.bzr_branch):
                for revision, revno in self.iterAddedMainline():
                    assert revno is not None
                    mailer = self.getMailerForRevision(
                        revision, revno, self.generateDiffs())
                    mailer.sendAll()

    def getDiffForRevisions(self, from_revision_id, to_revision_id):
        """Generate the diff between from_revision_id and to_revision_id."""
        # Try to reuse a tree from the last time through.
        repository = self.bzr_branch.repository
        from_tree = self._tree_cache.get(from_revision_id)
        if from_tree is None:
            from_tree = repository.revision_tree(from_revision_id)
        to_tree = self._tree_cache.get(to_revision_id)
        if to_tree is None:
            to_tree = repository.revision_tree(to_revision_id)
        # Replace the tree cache with these two trees.
        self._tree_cache = {
            from_revision_id: from_tree, to_revision_id: to_tree}
        # Now generate the diff.
        diff_content = StringIO()
        show_diff_trees(
            from_tree, to_tree, diff_content, old_label='', new_label='')
        return diff_content.getvalue()

    def getMailerForRevision(self, revision, revno, generate_diff):
        """Return a BranchMailer for a revision.

        :param revision: A bzr revision.
        :param revno: The revno of the revision in this branch.
        :param generate_diffs: If true, generate a diff for the revision.
        """
        message = self.getRevisionMessage(revision.revision_id, revno)
        # Use the first (non blank) line of the commit message
        # as part of the subject, limiting it to 100 characters
        # if it is longer.
        message_lines = [
            line.strip() for line in revision.message.split('\n')
            if len(line.strip()) > 0]
        if len(message_lines) == 0:
            first_line = 'no commit message given'
        else:
            first_line = message_lines[0]
            if len(first_line) > SUBJECT_COMMIT_MESSAGE_LENGTH:
                offset = SUBJECT_COMMIT_MESSAGE_LENGTH - 3
                first_line = first_line[:offset] + '...'
        subject = '[Branch %s] Rev %s: %s' % (
            self.branch.unique_name, revno, first_line)
        if generate_diff:
            if len(revision.parent_ids) > 0:
                parent_id = revision.parent_ids[0]
            else:
                parent_id = NULL_REVISION

            diff_text = self.getDiffForRevisions(
                parent_id, revision.revision_id)
        else:
            diff_text = None
        return BranchMailer.forRevision(
            self.branch, revno, self.from_address, message, diff_text,
            subject)

    def getMergedRevisionIDs(self, revision_id, graph):
        """Determine which revisions were merged by this revision.

        :param revision_id: ID of the revision to examine.
        :param graph: a bzrlib.graph.Graph.
        :return: a set of revision IDs.
        """
        parents = graph.get_parent_map([revision_id])[revision_id]
        merged_revision_ids = set()
        for merge_parent in parents[1:]:
            merged = graph.find_difference(parents[0], merge_parent)[1]
            merged_revision_ids.update(merged)
        return merged_revision_ids

    def getAuthors(self, revision_ids, graph):
        """Determine authors of the revisions merged by this revision.

        Ghost revisions are skipped.
        :param revision_ids: The revision to examine.
        :return: a set of author commit-ids
        """
        present_ids = graph.get_parent_map(revision_ids).keys()
        present_revisions = self.bzr_branch.repository.get_revisions(
            present_ids)
        authors = set()
        for revision in present_revisions:
            authors.update(revision.get_apparent_authors())
        return authors

    def findRelatedBMP(self, revision_ids):
        """Find merge proposals related to the revision-ids and branch.

        Only proposals whose source branch last-scanned-id is in the set of
        revision-ids and whose target_branch is the BranchJob branch are
        returned.

        Only return the most recent proposal for any given source branch.

        :param revision_ids: A list of revision-ids to look for.
        :param include_superseded: If true, include merge proposals that are
            superseded in the results.
        """
        store = Store.of(self.branch)
        result = store.find(
            (BranchMergeProposal, Branch),
            BranchMergeProposal.target_branch == self.branch.id,
            BranchMergeProposal.source_branch == Branch.id,
            Branch.last_scanned_id.is_in(revision_ids),
            (BranchMergeProposal.queue_status !=
             BranchMergeProposalStatus.SUPERSEDED))

        proposals = {}
        for proposal, source in result:
            # Only show the must recent proposal for any given source.
            date_created = proposal.date_created
            source_id = source.id

            if (source_id not in proposals or
                date_created > proposals[source_id][1]):
                proposals[source_id] = (proposal, date_created)

        return sorted(
            [proposal for proposal, date_created in proposals.itervalues()],
            key=operator.attrgetter('date_created'), reverse=True)

    def getRevisionMessage(self, revision_id, revno):
        """Return the log message for a revision.

        :param revision_id: The revision-id of the revision.
        :param revno: The revno of the revision in the branch.
        :return: The log message entered for this revision.
        """
        self.bzr_branch.lock_read()
        try:
            graph = self.bzr_branch.repository.get_graph()
            merged_revisions = self.getMergedRevisionIDs(revision_id, graph)
            authors = self.getAuthors(merged_revisions, graph)
            revision_set = RevisionSet()
            rev_authors = revision_set.acquireRevisionAuthors(authors)
            outf = StringIO()
            pretty_authors = []
            for rev_author in rev_authors.values():
                if rev_author.person is None:
                    displayname = rev_author.name
                else:
                    displayname = rev_author.person.unique_displayname
                pretty_authors.append('  %s' % displayname)

            if len(pretty_authors) > 0:
                outf.write('Merge authors:\n')
                pretty_authors.sort(key=lambda x: x.lower())
                outf.write('\n'.join(pretty_authors[:5]))
                if len(pretty_authors) > 5:
                    outf.write('...\n')
                outf.write('\n')
            bmps = self.findRelatedBMP(merged_revisions)
            if len(bmps) > 0:
                outf.write('Related merge proposals:\n')
            for bmp in bmps:
                outf.write('  %s\n' % canonical_url(bmp))
                proposer = bmp.registrant
                outf.write('  proposed by: %s\n' %
                           proposer.unique_displayname)
                for review in bmp.votes:
                    # If comment is None, this is a request for a review, not
                    # a completed review.
                    if review.comment is None:
                        continue
                    outf.write('  review: %s - %s\n' %
                        (review.comment.vote.title,
                         review.reviewer.unique_displayname))
            info = RevisionInfo(self.bzr_branch, revno, revision_id)
            lf = log_formatter('long', to_file=outf)
            show_log(self.bzr_branch,
                     lf,
                     start_revision=info,
                     end_revision=info,
                     verbose=True)
        finally:
            self.bzr_branch.unlock()
        return outf.getvalue()


class RosettaUploadJob(BranchJobDerived):
    """A Job that uploads translation files to Rosetta."""

    implements(IRosettaUploadJob)

    classProvides(IRosettaUploadJobSource)

    class_job_type = BranchJobType.ROSETTA_UPLOAD

    task_queue = 'bzrsyncd_job'

    config = config.IRosettaUploadJobSource

    def __init__(self, branch_job):
        super(RosettaUploadJob, self).__init__(branch_job)

        self.template_file_names = []
        self.template_files_changed = []
        self.translation_file_names = []
        self.translation_files_changed = []

    @staticmethod
    def getMetadata(from_revision_id, force_translations_upload):
        return {
            'from_revision_id': from_revision_id,
            'force_translations_upload': force_translations_upload,
        }

    @property
    def from_revision_id(self):
        return self.metadata['from_revision_id']

    @property
    def force_translations_upload(self):
        return self.metadata['force_translations_upload']

    @classmethod
    def providesTranslationFiles(cls, branch):
        """See `IRosettaUploadJobSource`."""
        productseries = getUtility(
            IProductSeriesSet).findByTranslationsImportBranch(branch)
        return not productseries.is_empty()

    @classmethod
    def create(cls, branch, from_revision_id,
               force_translations_upload=False):
        """See `IRosettaUploadJobSource`."""
        if branch is None:
            return None

        if from_revision_id is None:
            from_revision_id = NULL_REVISION

        if force_translations_upload or cls.providesTranslationFiles(branch):
            metadata = cls.getMetadata(from_revision_id,
                                       force_translations_upload)
            branch_job = BranchJob(
                branch, BranchJobType.ROSETTA_UPLOAD, metadata)
            job = cls(branch_job)
            job.celeryRunOnCommit()
            return job
        else:
            return None

    def _iter_all_lists(self):
        """Iterate through all the file lists.

        File names and files are stored in different lists according to their
        type (template or translation). But some operations need to be
        performed on both lists. This generator yields a pair of lists, one
        containing all file names for the given type, the other containing
        all file names *and* content of the changed files.
        """
        yield (self.template_file_names, self.template_files_changed)
        yield (self.translation_file_names, self.translation_files_changed)

    def _iter_lists_and_uploaders(self, productseries):
        """Iterate through all files for a productseries.

        File names and files are stored in different lists according to their
        type (template or translation). Which of these are needed depends on
        the configuration of the product series these uploads are for. This
        generator checks the configuration of the series and produces the
        a lists of lists and a person object. The first list contains all
        file names or the given type, the second contains all file names
        *and* content of the changed files. The person is who is to be
        credited as the importer of these files and will vary depending on
        the file type.
        """
        if (productseries.translations_autoimport_mode in (
            TranslationsBranchImportMode.IMPORT_TEMPLATES,
            TranslationsBranchImportMode.IMPORT_TRANSLATIONS) or
            self.force_translations_upload):
            #
            yield (self.template_file_names,
                   self.template_files_changed,
                   self._uploader_person_pot(productseries))

        if (productseries.translations_autoimport_mode ==
            TranslationsBranchImportMode.IMPORT_TRANSLATIONS or
            self.force_translations_upload):
            #
            yield (self.translation_file_names,
                   self.translation_files_changed,
                   self._uploader_person_po(productseries))

    @property
    def file_names(self):
        """A contatenation of all lists of filenames."""
        return self.template_file_names + self.translation_file_names

    def _init_translation_file_lists(self):
        """Initialize the member variables that hold the information about
        the relevant files.

        The information is collected from the branch tree and stored in the
        following member variables:
        * file_names is a dictionary of two lists ('pot', 'po') of file names
          that are POT or PO files respectively. This includes all files,
          changed or unchanged.
        * changed_files is a dictionary of two lists ('pot', 'po') of tuples
          of (file_name, file_content) of all changed files that are POT or
          PO files respectively.
        """

        bzrbranch = self.branch.getBzrBranch()
        from_tree = bzrbranch.repository.revision_tree(
            self.from_revision_id)
        to_tree = bzrbranch.repository.revision_tree(
            self.branch.last_scanned_id)

        importer = TranslationImporter()

        to_tree.lock_read()
        try:
            for dir, files in to_tree.walkdirs():
                for afile in files:
                    file_path, file_name, file_type = afile[:3]
                    if file_type != 'file':
                        continue
                    if importer.isHidden(file_path):
                        continue
                    if importer.isTemplateName(file_name):
                        append_to = self.template_file_names
                    elif importer.isTranslationName(file_name):
                        append_to = self.translation_file_names
                    else:
                        continue
                    append_to.append(file_path)
            from_tree.lock_read()
            try:
                for file_names, changed_files in self._iter_all_lists():
                    for changed_file in to_tree.iter_changes(
                            from_tree, specific_files=file_names):
                        (from_kind, to_kind) = changed_file[6]
                        if to_kind != 'file':
                            continue
                        file_id, (from_path, to_path) = changed_file[:2]
                        changed_files.append((
                            to_path, to_tree.get_file_text(file_id)))
            finally:
                from_tree.unlock()
        finally:
            to_tree.unlock()

    def _uploader_person_pot(self, series):
        """Determine which person is the uploader for a pot file."""
        # Default uploader is the driver or owner of the series.
        uploader = series.driver
        if uploader is None:
            uploader = series.owner
        return uploader

    def _uploader_person_po(self, series):
        """Determine which person is the uploader for a po file."""
        # For po files, try to determine the author of the latest push.
        uploader = None
        revision = self.branch.getTipRevision()
        if revision is not None and revision.revision_author is not None:
            uploader = revision.revision_author.person
        if uploader is None:
            uploader = self._uploader_person_pot(series)
        return uploader

    def run(self):
        """See `IRosettaUploadJob`."""
        with server(get_ro_server(), no_replace=True):
            # This is not called upon job creation because the branch would
            # neither have been mirrored nor scanned then.
            self._init_translation_file_lists()
            # Get the product series that are connected to this branch and
            # that want to upload translations.
            productseriesset = getUtility(IProductSeriesSet)
            productseries = productseriesset.findByTranslationsImportBranch(
                self.branch, self.force_translations_upload)
            translation_import_queue = getUtility(ITranslationImportQueue)
            for series in productseries:
                approver = TranslationBranchApprover(self.file_names,
                                                     productseries=series)
                for iter_info in self._iter_lists_and_uploaders(series):
                    file_names, changed_files, uploader = iter_info
                    for upload_file_name, upload_file_content in changed_files:
                        if len(upload_file_content) == 0:
                            continue  # Skip empty files
                        entry = translation_import_queue.addOrUpdateEntry(
                            upload_file_name, upload_file_content,
                            True, uploader, productseries=series)
                        approver.approve(entry)

    @staticmethod
    def iterReady():
        """See `IRosettaUploadJobSource`."""
        jobs = IMasterStore(BranchJob).using(BranchJob, Job, Branch).find(
            (BranchJob),
            And(BranchJob.job_type == BranchJobType.ROSETTA_UPLOAD,
                BranchJob.job == Job.id,
                BranchJob.branch == Branch.id,
                Branch.last_mirrored_id == Branch.last_scanned_id,
                Job.id.is_in(Job.ready_jobs))).order_by(BranchJob.id)
        return (RosettaUploadJob(job) for job in jobs)

    @staticmethod
    def findUnfinishedJobs(branch, since=None):
        """See `IRosettaUploadJobSource`."""
        store = IMasterStore(BranchJob)
        match = And(
            Job.id == BranchJob.jobID,
            BranchJob.branch == branch,
            BranchJob.job_type == BranchJobType.ROSETTA_UPLOAD,
            Job._status != JobStatus.COMPLETED,
            Job._status != JobStatus.FAILED)
        if since is not None:
            match = And(match, Job.date_created > since)
        jobs = store.using(BranchJob, Job).find((BranchJob), match)
        return jobs


class ReclaimBranchSpaceJob(BranchJobDerived, BaseRunnableJobSource):
    """Reclaim the disk space used by a branch that's deleted from the DB."""

    implements(IReclaimBranchSpaceJob)

    classProvides(IReclaimBranchSpaceJobSource)

    class_job_type = BranchJobType.RECLAIM_BRANCH_SPACE

    task_queue = 'branch_write_job'

    config = config.IReclaimBranchSpaceJobSource

    def __repr__(self):
        return '<RECLAIM_BRANCH_SPACE branch job (%(id)s) for %(branch)s>' % {
            'id': self.context.id,
            'branch': self.branch_id,
            }

    @classmethod
    def create(cls, branch_id):
        """See `IBranchDiffJobSource`."""
        metadata = {'branch_id': branch_id}
        # The branch_job has a branch of None, as there is no branch left in
        # the database to refer to.
        start = SQL("CURRENT_TIMESTAMP AT TIME ZONE 'UTC' + '7 days'")
        branch_job = BranchJob(
            None, cls.class_job_type, metadata, scheduled_start=start)
        return cls(branch_job)

    @property
    def branch_id(self):
        return self.metadata['branch_id']

    def run(self):
        branch_path = get_real_branch_path(self.branch_id)
        if os.path.exists(branch_path):
            shutil.rmtree(branch_path)
