# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""BranchJob interfaces."""


__metaclass__ = type


__all__ = [
    'IBranchJob',
    'IBranchScanJob',
    'IBranchScanJobSource',
    'IBranchUpgradeJob',
    'IBranchUpgradeJobSource',
    'IReclaimBranchSpaceJob',
    'IReclaimBranchSpaceJobSource',
    'IRevisionMailJob',
    'IRevisionMailJobSource',
    'IRevisionsAddedJob',
    'IRevisionsAddedJobSource',
    'IRosettaUploadJob',
    'IRosettaUploadJobSource',
    ]


from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Bool,
    Bytes,
    Int,
    Object,
    Text,
    TextLine,
    )

from lp import _
from lp.code.interfaces.branch import IBranch
from lp.services.job.interfaces.job import (
    IJob,
    IJobSource,
    IRunnableJob,
    )


class IBranchJob(Interface):
    """A job related to a branch."""

    id = Int(title=_('Unique id of BranchScanJob.'))

    branch = Object(
        title=_('Branch to use for this job.'), required=False,
        schema=IBranch)

    job = Object(schema=IJob, required=True)

    metadata = Attribute('A dict of data about the job.')

    def destroySelf():
        """Destroy this object."""


class IBranchScanJob(IRunnableJob):
    """ A job to scan branches."""


class IBranchScanJobSource(IJobSource):

    def create(branch):
        """Scan a branch for new revisions.

        :param branch: The database branch to upgrade.
        """


class IBranchUpgradeJob(IRunnableJob):
    """A job to upgrade branches with out-of-date formats."""


class IBranchUpgradeJobSource(IJobSource):

    def create(branch, requester):
        """Upgrade a branch to a more current format.

        :param branch: The database branch to upgrade.
        :param requester: The person requesting the upgrade.
        """


class IRevisionMailJob(IRunnableJob):
    """A Job to send email a revision change in a branch."""

    revno = Int(title=u'The revno to send mail about.')

    from_address = Bytes(title=u'The address to send mail from.')

    body = Text(title=u'The main text of the email to send.')

    subject = Text(title=u'The subject of the email to send.')


class IRevisionMailJobSource(IJobSource):
    """A utility to create and retrieve RevisionMailJobs."""

    def create(db_branch, revno, email_from, message, subject):
        """Create and return a new object that implements IRevisionMailJob."""


class IRevisionsAddedJob(IRunnableJob):
    """A Job to send emails about revisions added to a branch."""


class IRevisionsAddedJobSource(IJobSource):
    """A utility to create and retrieve RevisionMailJobs."""

    def create(branch, last_scanned_id, last_revision_id, from_address):
        """Create and return a new object that implements IRevisionMailJob."""


class IRosettaUploadJob(IRunnableJob):
    """A job to upload translation files to Rosetta."""

    from_revision_id = TextLine(
        title=_('The revision id to compare against.'))

    force_translations_upload = Bool(
        title=_('Force an upload of translation files.'),
        description=_('Flag to override the settings in the product '
                      'series and upload all translation files.'))

    def run():
        """Extract translation files from the branch passed in by the factory
        (see IRosettaUploadJobSource) and put them into the translations
        import queue.
        """


class IRosettaUploadJobSource(IJobSource):

    def create(branch, from_revision_id, force_translations_upload):
        """Construct a new object that implements IRosettaUploadJob.

        :param branch: The database branch to exract files from.
        :param from_revision_id: The revision id to compare against.
        :param force_translations_upload: Flag to override the settings in the
            product series and upload all translation files.
        """

    def findUnfinishedJobs(branch, since=None):
        """Find any `IRosettaUploadJob`s for `branch` that haven't run yet.

        :param branch: Branch to find unfinished jobs for.
        :param since: Optional cutoff date: ignore jobs older than this.
        :return: Any jobs for `branch` (and newer than `since`, if
            given) whose status is neither "complete" nor "failed."
        """

    def providesTranslationFiles(branch):
        """Is anyone importing translation files from this branch?

        This is used to check if any product series is related to the branch
        in order to decide if a job needs to be created.

        :param branch: The `IBranch` that is being scanned.
        :return: Boolean.
        """


class IReclaimBranchSpaceJob(IRunnableJob):
    """A job to delete a branch from disk after its been deleted from the db.
    """

    branch_id = Int(
        title=_('The id of the now-deleted branch.'))


class IReclaimBranchSpaceJobSource(IJobSource):

    def create(branch_id):
        """Construct a new object that implements IReclaimBranchSpaceJob.

        :param branch_id: The id of the branch to remove from disk.
        """
