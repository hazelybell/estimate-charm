# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Enumerations used in the lp/code modules."""

__metaclass__ = type
__all__ = [
    'BranchLifecycleStatus',
    'BranchLifecycleStatusFilter',
    'BranchMergeProposalStatus',
    'BranchSubscriptionDiffSize',
    'BranchSubscriptionNotificationLevel',
    'BranchType',
    'CodeImportEventDataType',
    'CodeImportEventType',
    'CodeImportJobState',
    'CodeImportMachineOfflineReason',
    'CodeImportMachineState',
    'CodeImportResultStatus',
    'CodeImportReviewStatus',
    'CodeReviewNotificationLevel',
    'CodeReviewVote',
    'NON_CVS_RCS_TYPES',
    'RevisionControlSystems',
    'UICreatableBranchType',
    ]

from lazr.enum import (
    DBEnumeratedType,
    DBItem,
    EnumeratedType,
    Item,
    use_template,
    )


class BranchLifecycleStatus(DBEnumeratedType):
    """Branch Lifecycle Status

    This indicates the status of the branch, as part of an overall
    "lifecycle". The idea is to indicate to other people how mature this
    branch is, or whether or not the code in the branch has been deprecated.
    Essentially, this tells us what the author of the branch thinks of the
    code in the branch.
    """

    EXPERIMENTAL = DBItem(10, """
        Experimental

        Still under active development, and not suitable for merging into
        release branches.
        """)

    DEVELOPMENT = DBItem(30, """
        Development

        Shaping up nicely, but incomplete or untested, and not yet ready for
        merging or production use.
        """)

    MATURE = DBItem(50, """
        Mature

        Completely addresses the issues it is supposed to, tested, and stable
        enough for merging into other branches.
        """)

    MERGED = DBItem(70, """
        Merged

        Successfully merged into its target branch(es). No further development
        is anticipated.
        """)

    ABANDONED = DBItem(80, "Abandoned")


class BranchType(DBEnumeratedType):
    """Branch Type

    The type of a branch determins the branch interaction with a number
    of other subsystems.
    """

    HOSTED = DBItem(1, """
        Hosted

        Launchpad is the primary location of this branch.
        """)

    MIRRORED = DBItem(2, """
        Mirrored

        Primarily hosted elsewhere and is periodically mirrored
        from the external location into Launchpad.
        """)

    IMPORTED = DBItem(3, """
        Imported

        Branches that have been imported from an externally hosted
        branch in bzr or another VCS and are made available through Launchpad.
        """)

    REMOTE = DBItem(4, """
        Remote

        Registered in Launchpad with an external location,
        but is not to be mirrored, nor available through Launchpad.
        """)


class UICreatableBranchType(EnumeratedType):
    """The types of branches that can be created through the web UI."""
    use_template(BranchType, exclude='IMPORTED')


class BranchLifecycleStatusFilter(EnumeratedType):
    """Branch Lifecycle Status Filter

    Used to populate the branch lifecycle status filter widget.
    UI only.
    """
    use_template(BranchLifecycleStatus)

    sort_order = (
        'CURRENT', 'ALL', 'EXPERIMENTAL', 'DEVELOPMENT', 'MATURE',
        'MERGED', 'ABANDONED')

    CURRENT = Item("""
        Any active status

        Show the currently active branches.
        """)

    ALL = Item("""
        Any status

        Show all the branches.
        """)


class BranchMergeProposalStatus(DBEnumeratedType):
    """Branch Merge Proposal Status

    The current state of a proposal to merge.
    """

    WORK_IN_PROGRESS = DBItem(1, """
        Work in progress

        The source branch is actively being worked on.
        """)

    NEEDS_REVIEW = DBItem(2, """
        Needs review

        A review of the changes has been requested.
        """)

    CODE_APPROVED = DBItem(3, """
        Approved

        The changes have been approved for merging.
        """)

    REJECTED = DBItem(4, """
        Rejected

        The changes have been rejected and will not be merged in their
        current state.
        """)

    MERGED = DBItem(5, """
        Merged

        The changes from the source branch were merged into the target
        branch.
        """)

    MERGE_FAILED = DBItem(6, """
        Code failed to merge

        The changes from the source branch failed to merge into the
        target branch for some reason.
        """)

    QUEUED = DBItem(7, """
        Queued

        The changes from the source branch are queued to be merged into the
        target branch.
        """)

    SUPERSEDED = DBItem(10, """
        Superseded

        This proposal has been superseded by anther proposal to merge.
        """)


class BranchSubscriptionDiffSize(DBEnumeratedType):
    """Branch Subscription Diff Size

    When getting branch revision notifications, the person can set a size
    limit of the diff to send out. If the generated diff is greater than
    the specified number of lines, then it is omitted from the email.
    This enumerated type defines the number of lines as a choice
    so we can sensibly limit the user to a number of size choices.
    """

    NODIFF = DBItem(0, """
        Don't send diffs

        Don't send generated diffs with the revision notifications.
        """)

    HALFKLINES = DBItem(500, """
        500 lines

        Limit the generated diff to 500 lines.
        """)

    ONEKLINES = DBItem(1000, """
        1000 lines

        Limit the generated diff to 1000 lines.
        """)

    FIVEKLINES = DBItem(5000, """
        5000 lines

        Limit the generated diff to 5000 lines.
        """)

    WHOLEDIFF = DBItem(-1, """
        Send entire diff

        Don't limit the size of the diff.
        """)


class BranchSubscriptionNotificationLevel(DBEnumeratedType):
    """Branch Subscription Notification Level

    The notification level is used to control the amount and content
    of the email notifications send with respect to modifications
    to branches whether it be to branch attributes in the UI, or
    to the contents of the branch found by the branch scanner.
    """

    NOEMAIL = DBItem(0, """
        No email

        Do not send any email about changes to this branch.
        """)

    ATTRIBUTEONLY = DBItem(1, """
        Branch attribute notifications only

        Only send notifications for branch attribute changes such
        as name, description and whiteboard.
        """)

    DIFFSONLY = DBItem(2, """
        Branch revision notifications only

        Only send notifications about new revisions added to this
        branch.
        """)

    FULL = DBItem(3, """
        Branch attribute and revision notifications

        Send notifications for both branch attribute updates
        and new revisions added to the branch.
        """)


class CodeReviewNotificationLevel(DBEnumeratedType):
    """Code Review Notification Level

    The notification level is used to control the amount and content
    of the email notifications send with respect to code reviews related
    to this branch.
    """

    NOEMAIL = DBItem(0, """
        No email

        Do not send any email about code review for this branch.
        """)

    STATUS = DBItem(1, """
        Status changes only

        Send email when votes are cast or status is changed.
        """)

    FULL = DBItem(2, """
        Email about all changes

        Send email about any code review activity for this branch.
        """)


class RevisionControlSystems(DBEnumeratedType):
    """Revision Control Systems

    Bazaar brings code from a variety of upstream revision control
    systems into bzr. This schema documents the known and supported
    revision control systems.
    """

    CVS = DBItem(1, """
        Concurrent Versions System

        Imports from CVS via CSCVS.
        """)

    SVN = DBItem(2, """
        Subversion via CSCVS

        Imports from SVN using CSCVS.
        """)

    BZR_SVN = DBItem(3, """
        Subversion via bzr-svn

        Imports from SVN using bzr-svn.
        """)

    GIT = DBItem(4, """
        Git

        Imports from Git using bzr-git.
        """)

    HG = DBItem(5, """
        Mercurial

        Imports from Mercurial using bzr-hg. (no longer supported)
        """)

    BZR = DBItem(6, """
        Bazaar

        Mirror of a Bazaar branch.
        """)


class CodeImportReviewStatus(DBEnumeratedType):
    """CodeImport review status.

    Before a code import is performed, it is reviewed. Only reviewed imports
    are processed.
    """

    NEW = DBItem(1, """Pending Review

        This code import request has recently been filed and has not
        been reviewed yet.
        """)

    INVALID = DBItem(10, """Invalid

        This code import will not be processed.
        """)

    REVIEWED = DBItem(20, """Reviewed

        This code import has been approved and will be processed.
        """)

    SUSPENDED = DBItem(30, """Suspended

        This code import has been approved, but it has been suspended
        and is not processed.""")

    FAILING = DBItem(40, """Failed

        The code import is failing for some reason and is no longer being
        attempted.""")


class CodeImportEventType(DBEnumeratedType):
    """CodeImportEvent type.

    Event types identify all the events that are significant to the code
    import system. Either user-driven events, or events recording the
    operation of unattended systems.
    """

    # Event types are named so that "a FOO event" sounds natural. For example,
    # MODIFY because "a MODIFIED event" sounds confusing and "a MODIFICATION
    # event" is awkward.

    # Code import life cycle.

    CREATE = DBItem(110, """
        Import Created

        A CodeImport object was created.
        """)

    MODIFY = DBItem(120, """
        Import Modified

        A code import was modified. Either the CodeImport object, or an
        associated object, was modified.
        """)

    DELETE = DBItem(130, """
        Import Deleted

        A CodeImport object was deleted.
        """)

    # Code import job events.

    START = DBItem(210, """
        Job Started

        An import job was started.
        """)

    FINISH = DBItem(220, """
        Job Finished

        An import job finished, either successfully or by a failure.
        """)

    PUBLISH = DBItem(230, """
        Import First Published

        A code import has completed for the first time and was published.
        """)

    RECLAIM = DBItem(240, """
        Job Reclaimed Automatically

        A code import job has not finished, but has probably crashed and is
        allowed to run again.
        """)

    # Code import job control events.

    REQUEST = DBItem(310, """
        Update Requested

        A user requested that an import job be run immediately.
        """)

    KILL = DBItem(320, """
        Termination Requested

        A user requested that a running import job be aborted.
        """)

    # Code import machine events.

    ONLINE = DBItem(410, """
        Machine Online

        A code-import-controller daemon has started, and is now accepting
        jobs.
        """)

    OFFLINE = DBItem(420, """
        Machine Offline

        A code-import-controller daemon has finished, or crashed is and no
        longer running.
        """)

    QUIESCE = DBItem(430, """
        Quiescing Requested

        A code-import-controller daemon has been requested to shut down. It
        will no longer accept jobs, and will terminate once the last running
        job finishes.
        """)


class CodeImportEventDataType(DBEnumeratedType):
    """CodeImportEventData type.

    CodeImportEvent objects record unstructured additional data. Each data
    item associated to an event has a type from this enumeration.
    """

    # Generic data

    MESSAGE = DBItem(10, """Message

    User-provided message.
    """)

    # CodeImport attributes

    CODE_IMPORT = DBItem(110, """
        Code Import

        Database id of the CodeImport, useful to collate events associated to
        deleted CodeImport objects.
        """)

    OWNER = DBItem(120, """
        Code Import Owner

        Value of CodeImport.owner. Useful to record ownership changes.
        """)

    OLD_OWNER = DBItem(121, """
        Previous Owner

        Previous value of CodeImport.owner, when recording an ownership
        change.
        """)

    REVIEW_STATUS = DBItem(130, """
        Review Status

        Value of CodeImport.review_status. Useful to understand the review
        life cycle of a code import.
        """)

    OLD_REVIEW_STATUS = DBItem(131, """
        Previous Review Status

        Previous value of CodeImport.review_status, when recording a status
        change.
        """)

    ASSIGNEE = DBItem(140, """
        Code Import Assignee

        Value of CodeImport.assignee. Useful to understand the review life
        cycle of a code import.
        """)

    OLD_ASSIGNEE = DBItem(141, """
        Previous Assignee

        Previous value of CodeImport.assignee, when recording an assignee
        change.
        """)

    # CodeImport attributes related to the import source

    UPDATE_INTERVAL = DBItem(210, """
        Update Interval

        User-specified interval between updates of the code import.
        """)

    OLD_UPDATE_INTERVAL = DBItem(211, """
        Previous Update Interval

        Previous user-specified update interval, when recording an interval
        change.
        """)

    CVS_ROOT = DBItem(220, """
        CVSROOT

        Location and access method of the CVS repository.
        """)

    CVS_MODULE = DBItem(221, """
        CVS module

        Path to import within the CVSROOT.
        """)

    OLD_CVS_ROOT = DBItem(222, """
        Previous CVSROOT

        Previous CVSROOT, when recording an import source change.
        """)

    OLD_CVS_MODULE = DBItem(223, """
        Previous CVS module

        Previous CVS module, when recording an import source change.
        """)

    SVN_BRANCH_URL = DBItem(230, """
        Subversion URL

        Location of the Subversion branch to import.
        """)

    OLD_SVN_BRANCH_URL = DBItem(231, """
        Previous Subversion URL

        Previous Subversion URL, when recording an import source change.
        """)

    GIT_REPO_URL = DBItem(237, """
        Git repo URL

        Location of the Git repo to import.
        """)

    OLD_GIT_REPO_URL = DBItem(238, """
        Previous Git repo URL

        Previous Git repo URL, when recording on import source change.
        """)

    URL = DBItem(240, """
        Foreign VCS branch URL

        Location of the foreign VCS branch to import.
        """)

    OLD_URL = DBItem(241, """
        Previous foreign VCS branch URL

        Previous foreign VCS branch location, when recording an import source
        change.
        """)

    # Data related to machine events

    OFFLINE_REASON = DBItem(410, """Offline Reason

    Reason why a code import machine went offline.
    """)

    # Data related to reclaim events

    RECLAIMED_JOB_ID = DBItem(510, """Reclaimed Job Id

    The database id of the reclaimed code import job.
    """)


class CodeImportJobState(DBEnumeratedType):
    """Values that ICodeImportJob.state can take."""

    PENDING = DBItem(10, """
        Pending

        The job has a time when it is due to run, and will wait until
        that time or an explicit update request is made.
        """)

    SCHEDULED = DBItem(20, """
        Scheduled

        The job is due to be run.
        """)

    RUNNING = DBItem(30, """
        Running

        The job is running.
        """)


class CodeImportMachineState(DBEnumeratedType):
    """CodeImportMachine State

    The operational state of the code-import-controller daemon on a given
    machine.
    """

    OFFLINE = DBItem(10, """
        Offline

        The code-import-controller daemon is not running on this machine.
        """)

    ONLINE = DBItem(20, """
        Online

        The code-import-controller daemon is running on this machine and
        accepting new jobs.
        """)

    QUIESCING = DBItem(30, """
        Quiescing

        The code-import-controller daemon is running on this machine, but has
        been requested to shut down and will not accept any new job.
        """)


class CodeImportMachineOfflineReason(DBEnumeratedType):
    """Reason why a CodeImportMachine is offline.

    A machine goes offline when a code-import-controller daemon process shuts
    down, or appears to have crashed. Recording the reason a machine went
    offline provides useful diagnostic information.
    """

    # Daemon termination

    STOPPED = DBItem(110, """
        Stopped

        The code-import-controller daemon was shut-down, interrupting running
        jobs.
        """)

    QUIESCED = DBItem(120, """
        Quiesced

        The code-import-controller daemon has shut down after completing
        any running jobs.
        """)

    # Crash recovery

    WATCHDOG = DBItem(210, """
        Watchdog

        The watchdog has detected that the machine's heartbeat has not been
        updated recently.
        """)


class CodeImportResultStatus(DBEnumeratedType):
    """Values for ICodeImportResult.status.

    How did a code import job complete? Was it successful, did it fail
    when trying to checkout or update the source tree, in the
    conversion step, or in one of the internal house-keeping steps?
    """

    SUCCESS = DBItem(100, """
        Success

        Import job completed successfully.
        """)

    SUCCESS_NOCHANGE = DBItem(110, """
        Success with no changes

        Import job completed successfully, but there were no new revisions to
        import.
        """)

    SUCCESS_PARTIAL = DBItem(120, """
        Partial Success

        Import job successfully imported some but not all of the foreign
        revisions.
        """)

    FAILURE = DBItem(200, """
        Failure

        Import job failed.
        """)

    INTERNAL_FAILURE = DBItem(210, """
        Internal Failure

        An internal error occurred. This is a problem with Launchpad.
        """)

    FAILURE_INVALID = DBItem(220, """
        Foreign branch invalid

        The import failed because the foreign branch did not exist or
        was not accessible.
        """)

    FAILURE_UNSUPPORTED_FEATURE = DBItem(230, """
        Unsupported feature

        The import failed because of missing feature support in
        Bazaar or the Bazaar foreign branch support.
        """)

    FAILURE_FORBIDDEN = DBItem(240, """
        Forbidden URL

        The import failed because the URL of the branch that is imported
        or the URL of one of the branches that it references is blacklisted.
        """)

    FAILURE_REMOTE_BROKEN = DBItem(250, """
        Broken remote branch

        The remote branch exists but is corrupted in some way
        """)

    RECLAIMED = DBItem(310, """
        Job reclaimed

        The job apparently crashed and was automatically marked as
        complete to allow further jobs to run for this code import.
        """)

    KILLED = DBItem(320, """
        Job killed

        A user action caused this job to be killed before it
        completed. It could have been an explicit request to kill the
        job, or the deletion of a CodeImport which had a running job.
        """)

    successes = [SUCCESS, SUCCESS_NOCHANGE, SUCCESS_PARTIAL]


class CodeReviewVote(DBEnumeratedType):
    """Code Review Votes

    Responses from the reviews to the code author.
    """
    sort_order = ('APPROVE',
                  'NEEDS_FIXING',
                  'NEEDS_INFO',
                  'ABSTAIN',
                  'DISAPPROVE',
                  'RESUBMIT',
                  )

    DISAPPROVE = DBItem(1, """
        Disapprove

        Reviewer does not want the proposed merge to happen.
        """)

    ABSTAIN = DBItem(2, """
        Abstain

        Reviewer cannot or does not want to decide whether the proposed merge
        should happen.
        """)

    APPROVE = DBItem(3, """
        Approve

        Reviewer wants the proposed merge to happen.
        """)

    RESUBMIT = DBItem(4, """
        Resubmit

        Reviewer thinks that the idea might be sound but the implementation
        needs significant rework.
        """)

    NEEDS_FIXING = DBItem(5, """
        Needs Fixing

        Reviewer thinks that some fixing is needed before they can approve it.
        """)

    NEEDS_INFO = DBItem(6, """
        Needs Information

        The reviewer needs more information before making a decision.
        """)

NON_CVS_RCS_TYPES = (
    RevisionControlSystems.SVN, RevisionControlSystems.BZR_SVN,
    RevisionControlSystems.GIT, RevisionControlSystems.BZR)
