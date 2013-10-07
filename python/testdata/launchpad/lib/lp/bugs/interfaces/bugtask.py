# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Bug task interfaces."""

__metaclass__ = type

__all__ = [
    'BUG_SUPERVISOR_BUGTASK_STATUSES',
    'BugTaskImportance',
    'BugTaskStatus',
    'BugTaskStatusSearch',
    'BugTaskStatusSearchDisplay',
    'CannotDeleteBugtask',
    'DB_INCOMPLETE_BUGTASK_STATUSES',
    'DB_UNRESOLVED_BUGTASK_STATUSES',
    'get_bugtask_status',
    'IAddBugTaskForm',
    'IAddBugTaskWithProductCreationForm',
    'IBugTask',
    'IBugTaskDelete',
    'IBugTaskDelta',
    'IBugTaskSet',
    'ICreateQuestionFromBugTaskForm',
    'IllegalTarget',
    'IRemoveQuestionFromBugTaskForm',
    'normalize_bugtask_status',
    'RESOLVED_BUGTASK_STATUSES',
    'UNRESOLVED_BUGTASK_STATUSES',
    'UserCannotEditBugTaskAssignee',
    'UserCannotEditBugTaskImportance',
    'UserCannotEditBugTaskMilestone',
    'UserCannotEditBugTaskStatus',
    'valid_remote_bug_url',
    ]

import httplib

from lazr.enum import (
    DBEnumeratedType,
    DBItem,
    use_template,
    )
from lazr.restful.declarations import (
    call_with,
    error_status,
    export_as_webservice_entry,
    export_destructor_operation,
    export_read_operation,
    export_write_operation,
    exported,
    mutator_for,
    operation_for_version,
    operation_parameters,
    operation_returns_collection_of,
    rename_parameters_as,
    REQUEST_USER,
    )
from lazr.restful.fields import (
    CollectionField,
    Reference,
    ReferenceChoice,
    )
from lazr.restful.interface import copy_field
from zope.component import getUtility
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Bool,
    Choice,
    Datetime,
    Field,
    Int,
    Text,
    TextLine,
    )
from zope.security.interfaces import Unauthorized

from lp import _
from lp.app.interfaces.launchpad import IHasDateCreated
from lp.app.validators import LaunchpadValidationError
from lp.app.validators.name import name_validator
from lp.bugs.interfaces.bugwatch import (
    IBugWatch,
    IBugWatchSet,
    NoBugTrackerFound,
    UnrecognizedBugTrackerURL,
    )
from lp.bugs.interfaces.hasbug import IHasBug
from lp.services.fields import (
    BugField,
    PersonChoice,
    ProductNameField,
    StrippedTextLine,
    Summary,
    )


class BugTaskImportance(DBEnumeratedType):
    """Bug Task Importance.

    Importance is used by developers and their managers to indicate how
    important fixing a bug is. Importance is typically a combination of the
    harm caused by the bug, and how often it is encountered.
    """

    UNKNOWN = DBItem(999, """
        Unknown

        The importance of this bug is not known.
        """)

    UNDECIDED = DBItem(5, """
        Undecided

        Not decided yet. Maybe needs more discussion.
        """)

    CRITICAL = DBItem(50, """
        Critical

        Fix now or as soon as possible.
        """)

    HIGH = DBItem(40, """
        High

        Schedule to be fixed soon.
        """)

    MEDIUM = DBItem(30, """
        Medium

        Fix when convenient, or schedule to fix later.
        """)

    LOW = DBItem(20, """
        Low

        Fix when convenient.
        """)

    WISHLIST = DBItem(10, """
        Wishlist

        Not a bug. It's an enhancement/new feature.
        """)


class BugTaskStatus(DBEnumeratedType):
    """Bug Task Status

    The various possible states for a bugfix in a specific place.
    """

    NEW = DBItem(10, """
        New

        Not looked at yet.
        """)

    # INCOMPLETE is never actually stored now: INCOMPLETE_WITH_RESPONSE and
    # INCOMPLETE_WITHOUT_RESPONSE are mapped to INCOMPLETE on read, and on
    # write INCOMPLETE is mapped to INCOMPLETE_WITHOUT_RESPONSE. This permits
    # An index on the INCOMPLETE_WITH*_RESPONSE queries that the webapp
    # generates.
    INCOMPLETE = DBItem(15, """
        Incomplete

        Cannot be verified, the reporter needs to give more info.
        """)

    OPINION = DBItem(16, """
        Opinion

        Doesn't fit with the project, but can be discussed.
        """)

    INVALID = DBItem(17, """
        Invalid

        Not a bug. May be a support request or spam.
        """)

    WONTFIX = DBItem(18, """
        Won't Fix

        Doesn't fit with the project plans, sorry.
        """)

    EXPIRED = DBItem(19, """
        Expired

        This bug is expired. There was no activity for a long time.
        """)

    CONFIRMED = DBItem(20, """
        Confirmed

        Verified by someone other than the reporter.
        """)

    TRIAGED = DBItem(21, """
        Triaged

        Verified by the bug supervisor.
        """)

    INPROGRESS = DBItem(22, """
        In Progress

        The assigned person is working on it.
        """)

    FIXCOMMITTED = DBItem(25, """
        Fix Committed

        Fixed, but not available until next release.
        """)

    FIXRELEASED = DBItem(30, """
        Fix Released

        The fix was released.
        """)

    UNKNOWN = DBItem(999, """
        Unknown

        The status of this bug is not known.
        """)


class BugTaskStatusSearch(DBEnumeratedType):
    """Bug Task Status

    The various possible states for a bugfix in searches.
    """
    use_template(BugTaskStatus, exclude=('UNKNOWN'))

    INCOMPLETE_WITH_RESPONSE = DBItem(13, """
        Incomplete (with response)

        This bug has new information since it was last marked
        as requiring a response.
        """)

    INCOMPLETE_WITHOUT_RESPONSE = DBItem(14, """
        Incomplete (without response)

        This bug requires more information, but no additional
        details were supplied yet..
        """)


def get_bugtask_status(status_id):
    """Get a member of `BugTaskStatus` or `BugTaskStatusSearch` by value.

    `BugTaskStatus` and `BugTaskStatusSearch` intersect, but neither is a
    subset of the other, so this searches first in `BugTaskStatus` then in
    `BugTaskStatusSearch` for a member with the given ID.
    """
    try:
        return BugTaskStatus.items[status_id]
    except KeyError:
        return BugTaskStatusSearch.items[status_id]


def normalize_bugtask_status(status):
    """Normalize `status`.

    It might be a member of any of three related enums: `BugTaskStatus`,
    `BugTaskStatusSearch`, or `BugTaskStatusSearchDisplay`. This tries to
    normalize by value back to the first of those three enums in which the
    status appears.
    """
    try:
        return BugTaskStatus.items[status.value]
    except KeyError:
        return BugTaskStatusSearch.items[status.value]


class BugTaskStatusSearchDisplay(DBEnumeratedType):
    """Bug Task Status

    The various possible states for a bugfix in advanced
    bug search forms.
    """
    use_template(BugTaskStatusSearch, exclude=('INCOMPLETE'))


UNRESOLVED_BUGTASK_STATUSES = (
    BugTaskStatus.NEW,
    BugTaskStatus.INCOMPLETE,
    BugTaskStatus.CONFIRMED,
    BugTaskStatus.TRIAGED,
    BugTaskStatus.INPROGRESS,
    BugTaskStatus.FIXCOMMITTED)

# Actual values stored in the DB:
DB_INCOMPLETE_BUGTASK_STATUSES = (
    BugTaskStatusSearch.INCOMPLETE_WITH_RESPONSE,
    BugTaskStatusSearch.INCOMPLETE_WITHOUT_RESPONSE,
    )

DB_UNRESOLVED_BUGTASK_STATUSES = (
    UNRESOLVED_BUGTASK_STATUSES +
    DB_INCOMPLETE_BUGTASK_STATUSES
    )

RESOLVED_BUGTASK_STATUSES = (
    BugTaskStatus.FIXRELEASED,
    BugTaskStatus.OPINION,
    BugTaskStatus.INVALID,
    BugTaskStatus.WONTFIX,
    BugTaskStatus.EXPIRED)

BUG_SUPERVISOR_BUGTASK_STATUSES = (
    BugTaskStatus.WONTFIX,
    BugTaskStatus.EXPIRED,
    BugTaskStatus.TRIAGED)


@error_status(httplib.BAD_REQUEST)
class CannotDeleteBugtask(Exception):
    """The bugtask cannot be deleted.

    Raised when a user tries to delete a bugtask but the deletion cannot
    proceed because of a model constraint or other business rule violation.
    """


@error_status(httplib.UNAUTHORIZED)
class UserCannotEditBugTaskStatus(Unauthorized):
    """User not permitted to change status.

    Raised when a user tries to transition to a new status who doesn't
    have the necessary permissions.
    """


@error_status(httplib.UNAUTHORIZED)
class UserCannotEditBugTaskImportance(Unauthorized):
    """User not permitted to change importance.

    Raised when a user tries to transition to a new importance who
    doesn't have the necessary permissions.
    """


@error_status(httplib.UNAUTHORIZED)
class UserCannotEditBugTaskMilestone(Unauthorized):
    """User not permitted to change milestone.

    Raised when a user tries to transition to a milestone who doesn't have
    the necessary permissions.
    """


@error_status(httplib.UNAUTHORIZED)
class UserCannotEditBugTaskAssignee(Unauthorized):
    """User not permitted to change bugtask assignees.

    Raised when a user with insufficient prilieges tries to set
    the assignee of a bug task.
    """


@error_status(httplib.BAD_REQUEST)
class IllegalTarget(Exception):
    """Exception raised when trying to set an illegal bug task target."""


class IBugTaskDelete(Interface):
    """An interface for operations allowed with the Delete permission."""
    @export_destructor_operation()
    @call_with(who=REQUEST_USER)
    @operation_for_version('devel')
    def delete(who):
        """Delete this bugtask.

        :param who: the user who is removing the bugtask.
        :raises: CannotDeleteBugtask if the bugtask cannot be deleted due to a
            business rule or other model constraint.
        :raises: Unauthorized if the user does not have permission
            to delete the bugtask.
        """


class IBugTask(IHasDateCreated, IHasBug, IBugTaskDelete):
    """A bug needing fixing in a particular product or package."""
    export_as_webservice_entry()

    id = Int(title=_("Bug Task #"))
    bug = exported(
        BugField(title=_("Bug"), readonly=True))
    product = Choice(
        title=_('Project'), required=False, vocabulary='Product')
    productID = Attribute('The product ID')
    productseries = Choice(
        title=_('Series'), required=False, vocabulary='ProductSeries')
    productseriesID = Attribute('The product series ID')
    sourcepackagename = Choice(
        title=_("Package"), required=False,
        vocabulary='SourcePackageName')
    sourcepackagenameID = Attribute('The sourcepackagename ID')
    distribution = Choice(
        title=_("Distribution"), required=False, vocabulary='Distribution')
    distributionID = Attribute('The distribution ID')
    distroseries = Choice(
        title=_("Series"), required=False,
        vocabulary='DistroSeries')
    distroseriesID = Attribute('The distroseries ID')
    milestone = exported(ReferenceChoice(
        title=_('Milestone'),
        required=False,
        readonly=True,
        vocabulary='BugTaskMilestone',
        schema=Interface))  # IMilestone
    milestoneID = Attribute('The id of the milestone.')

    # The status and importance's vocabularies do not
    # contain an UNKNOWN item in bugtasks that aren't linked to a remote
    # bugwatch; this would be better described in a separate interface,
    # but adding a marker interface during initialization is expensive,
    # and adding it post-initialization is not trivial.
    # Note that status is a property because the model only exposes INCOMPLETE
    # but the DB stores INCOMPLETE_WITH_RESPONSE and
    # INCOMPLETE_WITHOUT_RESPONSE for query efficiency.
    status = exported(
        Choice(title=_('Status'), vocabulary=BugTaskStatus,
               default=BugTaskStatus.NEW, readonly=True))
    _status = Attribute('The actual status DB column used in queries.')
    importance = exported(
        Choice(title=_('Importance'), vocabulary=BugTaskImportance,
               default=BugTaskImportance.UNDECIDED, readonly=True))
    assignee = exported(
        PersonChoice(
            title=_('Assigned to'), required=False,
            vocabulary='ValidAssignee',
            readonly=True))
    assigneeID = Int(title=_('The assignee ID (for eager loading)'))
    bugtargetdisplayname = exported(
        Text(title=_("The short, descriptive name of the target"),
             readonly=True),
        exported_as='bug_target_display_name')
    bugtargetname = exported(
        Text(title=_("The target as presented in mail notifications"),
             readonly=True),
        exported_as='bug_target_name')
    bugwatch = exported(
        ReferenceChoice(
            title=_("Remote Bug Details"), required=False,
            schema=IBugWatch,
            vocabulary='BugWatch', description=_(
                "Select the bug watch that "
                "represents this task in the relevant bug tracker. If none "
                "of the bug watches represents this particular bug task, "
                "leave it as (None). Linking the remote bug watch with the "
                "task in this way means that a change in the remote bug "
                "status will change the status of this bug task in "
                "Launchpad.")),
        exported_as='bug_watch')
    date_assigned = exported(
        Datetime(title=_("Date Assigned"),
                 description=_("The date on which this task was assigned "
                               "to someone."),
                 readonly=True,
                 required=False))
    datecreated = exported(
        Datetime(title=_("Date Created"),
                 description=_("The date on which this task was created."),
                 readonly=True),
        exported_as='date_created')
    date_confirmed = exported(
        Datetime(title=_("Date Confirmed"),
                 description=_("The date on which this task was marked "
                               "Confirmed."),
                 readonly=True,
                 required=False))
    date_incomplete = exported(
        Datetime(title=_("Date Incomplete"),
                 description=_("The date on which this task was marked "
                               "Incomplete."),
                 readonly=True,
                 required=False))
    date_inprogress = exported(
        Datetime(title=_("Date In Progress"),
                 description=_("The date on which this task was marked "
                               "In Progress."),
                 readonly=True,
                 required=False),
        exported_as='date_in_progress')
    date_closed = exported(
        Datetime(title=_("Date Closed"),
                 description=_("The date on which this task was marked "
                               "either Won't Fix, Invalid or Fix Released."),
                 readonly=True,
                 required=False))
    date_left_new = exported(
        Datetime(title=_("Date left new"),
                 description=_("The date on which this task was marked "
                               "with a status higher than New."),
                 readonly=True,
                 required=False))
    date_triaged = exported(
        Datetime(title=_("Date Triaged"),
                 description=_("The date on which this task was marked "
                               "Triaged."),
                 readonly=True,
                 required=False))
    date_fix_committed = exported(
        Datetime(title=_("Date Fix Committed"),
                 description=_("The date on which this task was marked "
                               "Fix Committed."),
                 readonly=True,
                 required=False))
    date_fix_released = exported(
        Datetime(title=_("Date Fix Released"),
                 description=_("The date on which this task was marked "
                               "Fix Released."),
                 readonly=True,
                 required=False))
    date_left_closed = exported(
        Datetime(title=_("Date left closed"),
                 description=_("The date on which this task was "
                               "last reopened."),
                 readonly=True,
                 required=False))
    age = Datetime(title=_("Age"),
                   description=_("The age of this task, expressed as the "
                                 "length of time between the creation date "
                                 "and now."))
    task_age = Int(title=_("Age of the bug task"),
            description=_("The age of this task in seconds, a delta between "
                         "now and the date the bug task was created."))
    owner = exported(
        Reference(title=_("The owner"), schema=Interface, readonly=True))
    target = exported(Reference(
        title=_('Target'), required=True, schema=Interface,  # IBugTarget
        readonly=True,
        description=_("The software in which this bug should be fixed.")))
    title = exported(
        Text(title=_("The title of the bug related to this bugtask"),
             readonly=True))
    related_tasks = exported(
        CollectionField(
            description=_(
                "IBugTasks related to this one, namely other "
                "IBugTasks on the same IBug."),
            value_type=Reference(schema=Interface),  # Will be specified later
            readonly=True))
    pillar = Choice(
        title=_('Pillar'),
        description=_("The LP pillar (product or distribution) "
                      "associated with this task."),
        vocabulary='DistributionOrProduct', readonly=True)
    other_affected_pillars = Attribute(
        "The other pillars (products or distributions) affected by this bug. "
        "This returns a list of pillars OTHER THAN the pillar associated "
        "with this particular bug.")
    # This property does various database queries. It is a property so a
    # "snapshot" of its value will be taken when a bugtask is modified, which
    # allows us to compare it to the current value and see if there are any
    # new subscribers that should get an email containing full bug details
    # (rather than just the standard change mail.) It is a property on
    # IBugTask because we currently only ever need this value for events
    # handled on IBugTask.
    bug_subscribers = Field(
        title=_("A list of IPersons subscribed to the bug, whether directly "
                "or indirectly."), readonly=True)

    conjoined_master = Attribute(
        "The series-specific bugtask in a conjoined relationship")
    conjoined_slave = Attribute(
        "The generic bugtask in a conjoined relationship")

    is_complete = exported(
        Bool(description=_(
                "True or False depending on whether or not there is more "
                "work required on this bug task."),
             readonly=True))

    @operation_returns_collection_of(Interface)  # Actually IBug.
    @call_with(user=REQUEST_USER, limit=10)
    @export_read_operation()
    def findSimilarBugs(user, limit=10):
        """Return the list of possible duplicates for this BugTask."""

    @call_with(user=REQUEST_USER)
    @operation_parameters(person=copy_field(assignee))
    @export_read_operation()
    @operation_for_version("devel")
    def getContributorInfo(user, person):
        """Is the person a contributor to bugs in this task's pillar?

        :param user: The user doing the search. Private bugs that this
            user doesn't have access to won't be included in the search.
        :param person: The person to check to see if they are a contributor.

        Return a dict with the following values:
        is_contributor: True if the user has any bugs assigned to him in the
        context of this bug task's pillar, either directly or by team
        participation.
        person_name: the displayname of the person
        pillar_name: the displayname of the bug task's pillar

        This API call is provided for use by the client Javascript where the
        calling context does not have access to the person or pillar names.
        """

    def getConjoinedMaster(bugtasks, bugtasks_by_package=None):
        """Return the conjoined master in the given bugtasks, if any.

        :param bugtasks: The bugtasks to be considered when looking for
            the conjoined master.
        :param bugtasks_by_package: A cache, mapping a
            `ISourcePackageName` to a list of bug tasks targeted to such
            a package name. Both distribution and distro series tasks
            should be included in this list.

        This method exists mainly to allow calculating the conjoined
        master from a cached list of bug tasks, reducing the number of
        db queries needed.
        """

    def subscribe(person, subscribed_by):
        """Subscribe this person to the underlying bug.

        This method was documented as being required here so that
        MentorshipOffers could happen on IBugTask. If that was the sole reason
        this method should be deletable. When we move to context-less bug
        presentation (where the bug is at /bugs/n?task=ubuntu) then we can
        eliminate this if it is no longer useful.
        """

    def isSubscribed(person):
        """Return True if the person is an explicit subscriber to the
        underlying bug for this bugtask.

        This method was documented as being required here so that
        MentorshipOffers could happen on IBugTask. If that was the sole
        reason then this method should be deletable.  When we move to
        context-less bug presentation (where the bug is at
        /bugs/n?task=ubuntu) then we can eliminate this if it is no
        longer useful.
        """

    @mutator_for(milestone)
    @rename_parameters_as(new_milestone='milestone')
    @operation_parameters(new_milestone=copy_field(milestone))
    @call_with(user=REQUEST_USER)
    @export_write_operation()
    def transitionToMilestone(new_milestone, user):
        """Set the BugTask milestone.

        Set the bugtask milestone, making sure that the user is
        authorised to do so.
        """

    @mutator_for(importance)
    @rename_parameters_as(new_importance='importance')
    @operation_parameters(new_importance=copy_field(importance))
    @call_with(user=REQUEST_USER)
    @export_write_operation()
    def transitionToImportance(new_importance, user):
        """Set the BugTask importance.

        Set the bugtask importance, making sure that the user is
        authorised to do so.
        """

    def canTransitionToStatus(new_status, user):
        """Return True if the user is allowed to change the status to
        `new_status`.

        :new_status: new status from `BugTaskStatus`
        :user: the user requesting the change

        Some status transitions, e.g. Triaged, require that the user
        be a bug supervisor or the owner of the project.
        """

    @mutator_for(status)
    @rename_parameters_as(new_status='status')
    @operation_parameters(
        new_status=copy_field(status))
    @call_with(user=REQUEST_USER)
    @export_write_operation()
    def transitionToStatus(new_status, user):
        """Perform a workflow transition to the new_status.

        :new_status: new status from `BugTaskStatus`
        :user: the user requesting the change

        For certain statuses, e.g. Confirmed, other actions will
        happen, like recording the date when the task enters this
        status.

        Some status transitions require extra conditions to be met.
        See `canTransitionToStatus` for more details.
        """

    def userCanSetAnyAssignee(user):
        """Check if the current user can set anybody sa a bugtask assignee.

        Owners, drivers, bug supervisors and Launchpad admins can always
        assign to someone else.  Other users can assign to someone else if a
        bug supervisor is not defined.
        """

    def userCanUnassign(user):
        """Check if the current user can set assignee to None."""

    @mutator_for(assignee)
    @operation_parameters(assignee=copy_field(assignee))
    @export_write_operation()
    def transitionToAssignee(assignee, validate=True):
        """Perform a workflow transition to the given assignee.

        When the bugtask assignee is changed from None to an IPerson
        object, the date_assigned is set on the task. If the assignee
        value is set to None, date_assigned is also set to None.
        """

    def validateTransitionToTarget(target):
        """Check whether a transition to this target is legal.

        :raises IllegalTarget: if the new target is not allowed.
        """

    @mutator_for(target)
    @call_with(user=REQUEST_USER)
    @operation_parameters(
        target=copy_field(target))
    @export_write_operation()
    def transitionToTarget(target, user):
        """Convert the bug task to a different bug target."""

    def updateTargetNameCache():
        """Update the targetnamecache field in the database.

        This method is meant to be called when an IBugTask is created or
        modified and will also be called from the update_stats.py cron script
        to ensure that the targetnamecache is properly updated when, for
        example, an IDistribution is renamed.
        """

    def asEmailHeaderValue():
        """Return a value suitable for an email header value for this bugtask.

        The return value is a single line of arbitrary length, so header
        folding should be done by the callsite, as needed.

        For an upstream task, this value might look like:

          product=firefox; status=New; importance=Critical; assignee=None;

        See doc/bugmail-headers.txt for a complete explanation and more
        examples.
        """

    def getDelta(old_task):
        """Compute the delta from old_task to this task.

        Returns an IBugTaskDelta or None if there were no changes between
        old_task and this task.
        """

    def getPackageComponent():
        """Return the task's package's component or None.

        Returns the component associated to the current published
        package in that distribution's current series. If the task is
        not a package task, returns None.
        """

    def userHasDriverPrivileges(user):
        """Does the user have driver privileges on the current bugtask?

        :return: A boolean.
        """

    def userHasBugSupervisorPrivileges(user):
        """Is the user privileged and allowed to change details on a bug?

        :return: A boolean.
        """


# Set schemas that were impossible to specify during the definition of
# IBugTask itself.
IBugTask['related_tasks'].value_type.schema = IBugTask

# We are forced to define this now to avoid circular import problems.
IBugWatch['bugtasks'].value_type.schema = IBugTask


class IBugTaskDelta(Interface):
    """The change made to a bug task (e.g. in an edit screen).

    If product is not None, the sourcepackagename must be None.

    Likewise, if sourcepackagename is not None, product must be None.
    """
    bugtask = Attribute("The modified IBugTask.")
    target = Attribute(
        """The change made to the IBugTarget for this task.

        The value is a dict like {'old' : IBugTarget, 'new' : IBugTarget},
        or None, if no change was made to the target.
        """)
    status = Attribute(
        """The change made to the status for this task.

        The value is a dict like
        {'old' : BugTaskStatus.FOO, 'new' : BugTaskStatus.BAR}, or None,
        if no change was made to the status.
        """)
    importance = Attribute(
        """The change made to the importance of this task.

        The value is a dict like
        {'old' : BugTaskImportance.FOO, 'new' : BugTaskImportance.BAR},
        or None, if no change was made to the importance.
        """)
    assignee = Attribute(
        """The change made to the assignee of this task.

        The value is a dict like {'old' : IPerson, 'new' : IPerson}, or None,
        if no change was made to the assignee.
        """)
    bugwatch = Attribute("The bugwatch which governs this task.")
    milestone = Attribute("The milestone for which this task is scheduled.")


class IBugTaskSet(Interface):
    """A utility to retrieving BugTasks."""
    title = Attribute('Title')
    orderby_expression = Attribute(
        "The SQL expression for a sort key")

    def get(task_id):
        """Retrieve a BugTask with the given id.

        Raise a NotFoundError if there is no IBugTask
        matching the given id. Raise a zope.security.interfaces.Unauthorized
        if the user doesn't have the permission to view this bug.
        """

    def getBugTaskTags(bugtasks):
        """Return a set of bugtasks bug tags

        Return a dict mapping from bugtask to tag.
        """

    def getBugTaskPeople(bugtasks):
        """Return a set of people related to bugtasks.

        Return a dict mapping from Person.id to Person.
        """

    def getBugTaskBadgeProperties(bugtasks):
        """Return whether the bugtasks should have badges.

        Return a mapping from a bug task, to a dict of badge properties.
        """

    def getMultiple(task_ids):
        """Retrieve a dictionary of bug tasks for the given sequence of IDs.

        :param task_ids: a sequence of bug task IDs.

        :return: a dictionary mapping task IDs to tasks. The
            dictionary contains an entry for every bug task ID in
            the given sequence that also matches a bug task in the
            database. The dictionary does not contain entries for
            bug task IDs not present in the database.

        :return: an empty dictionary if the given sequence of IDs
            is empty, or if none of the specified IDs matches a bug
            task in the database.
        """

    def findSimilar(user, summary, product=None, distribution=None,
                    sourcepackagename=None):
        """Find bugs similar to the given summary.

        The search is limited to the given product or distribution
        (together with an optional source package).

        Only BugTasks that the user has access to will be returned.
        """

    def search(params, *args, **kwargs):
        """Search IBugTasks with the given search parameters.

        Note: only use this method of BugTaskSet if you want to query
        tasks across multiple IBugTargets; otherwise, use the
        IBugTarget's searchTasks() method.

        :param search_params: a BugTaskSearchParams object
        :param args: any number of BugTaskSearchParams objects

        If more than one BugTaskSearchParams is given, return the union of
        IBugTasks which match any of them, with the results ordered by the
        orderby specified in the first BugTaskSearchParams object.
        """

    def searchBugIds(params):
        """Search bug ids.

        This is a variation on IBugTaskSet.search that returns only bug ids.

        :param params: the BugTaskSearchParams to search on.
        """

    def countBugs(user, contexts, group_on):
        """Count open bugs that match params, grouping by group_on.

        This serves results from the bugsummary fact table: it is fast but not
        completely precise. See the bug summary documentation for more detail.

        :param user: The user to query on behalf of.
        :param contexts: A list of contexts to search. Contexts must support
            the IBugSummaryDimension interface.
        :param group_on: The column(s) group on - .e.g (
            BugSummary.distroseries_id, BugSummary.milestone_id) will cause
            grouping by distro series and then milestone.
        :return: A dict {group_instance: count, ...}
        """

    def getStatusCountsForProductSeries(user, product_series):
        """Returns status counts for a product series' bugs.

        Both the nominated and scheduled blueprints are included
        in the count.

        :param product_series: ProductSeries object.
        :return: A list of tuples containing (status_id, count).
        """

    def createManyTasks(bug, owner, targets, status=None, importance=None,
                   assignee=None, milestone=None):
        """Create a series of bug tasks and return them."""

    def createTask(bug, owner, target, status=None, importance=None,
                   assignee=None, milestone=None):
        """Create a bug task on a bug and return it.

        If the bug is public, bug supervisors will be automatically
        subscribed.

        If the bug has any accepted series nominations for a supplied
        distribution, series tasks will be created for them.
        """

    def findExpirableBugTasks(min_days_old, user, bug=None, target=None,
                              limit=None):
        """Return a list of bugtasks that are at least min_days_old.

        :param min_days_old: An int representing the minimum days of
            inactivity for a bugtask to be considered expirable. Setting
            this parameter to 0 will return all bugtask that can expire.
        :param user: The `IPerson` doing the search. Only bugs the user
            has permission to view are returned.
        :param bug: An `IBug`. If a bug is provided, only bugtasks that belong
            to the bug may be returned. If bug is None, all bugs are searched.
        :param target: An `IBugTarget`. If a target is provided, only
            bugtasks that belong to the target may be returned. If target
            is None, all bugtargets are searched.
        :param limit: An int for limiting the number of bugtasks returned.
        :return: A ResultSet of bugtasks that are considered expirable.

        A bugtask is expirable if its status is Incomplete, and the bug
        report has been never been confirmed, and it has been inactive for
        min_days_old. Only bugtasks that belong to Products or Distributions
        that use launchpad to track bugs can be returned. The implementation
        must define the criteria for determining that the bug report is
        inactive and have never been confirmed.
        """

    def getBugCountsForPackages(user, packages):
        """Return open bug counts for the list of packages.

        :param user: The user doing the search. Private bugs that this
            user doesn't have access to won't be included in the count.
        :param packages: A list of `IDistributionSourcePackage`
            instances.

        :return: A list of dictionaries, where each dict contains:
            'package': The package the bugs are open on.
            'open': The number of open bugs.
            'open_critical': The number of open critical bugs.
            'open_unassigned': The number of open unassigned bugs.
            'open_inprogress': The number of open bugs that are In Progress.
        """

    def getOpenBugTasksPerProduct(user, products):
        """Return open bugtask count for multiple products."""

    def getPrecachedNonConjoinedBugTasks(user, milestone):
        """List of non-conjoined bugtasks targeted to the milestone.

        The assignee and the assignee's validity are precached.
        """

    def getBugTaskTargetMilestones(bugtasks):
        """Get all the milestones for the selected bugtasks' targets."""

    open_bugtask_search = Attribute("A search returning open bugTasks.")


def valid_remote_bug_url(value):
    """Verify that the URL is to a bug to a known bug tracker."""
    try:
        getUtility(IBugWatchSet).extractBugTrackerAndBug(value)
    except NoBugTrackerFound:
        pass
    except UnrecognizedBugTrackerURL:
        raise LaunchpadValidationError(
            "Launchpad does not recognize the bug tracker at this URL.")
    return True


class ILinkPackaging(Interface):
    """Form for linking a source package to a project."""
    add_packaging = Bool(
        title=_('Link the package to the upstream project?'),
        description=_('Always suggest this project when adding an '
                      'upstream bug for this package.'),
        required=True, default=False)


class IAddBugTaskForm(ILinkPackaging):
    """Form for adding an upstream bugtask."""
    # It is tempting to replace the first three attributes here with their
    # counterparts from IUpstreamBugTask and IDistroBugTask.
    # BUT: This will cause OOPSes with adapters, hence IAddBugTask reinvents
    # the wheel somewhat. There is a test to ensure that this remains so.
    product = Choice(title=_('Project'), required=True, vocabulary='Product')
    distribution = Choice(
        title=_("Distribution"), required=True, vocabulary='Distribution')
    sourcepackagename = Choice(
        title=_("Source Package Name"), required=False,
        description=_("The source package in which the bug occurs. "
                      "Leave blank if you are not sure."),
        vocabulary='SourcePackageName')
    bug_url = StrippedTextLine(
        title=_('URL'), required=False, constraint=valid_remote_bug_url,
        description=_("The URL of this bug in the remote bug tracker."))


class IAddBugTaskWithProductCreationForm(ILinkPackaging):

    bug_url = StrippedTextLine(
        title=_('Bug URL'), required=True, constraint=valid_remote_bug_url,
        description=_("The URL of this bug in the remote bug tracker."))
    displayname = TextLine(title=_('Project name'))
    name = ProductNameField(
        title=_('Project ID'), constraint=name_validator, required=True,
        description=_(
            "A short name starting with a lowercase letter or number, "
            "followed by letters, dots, hyphens or plusses. e.g. firefox, "
            "linux, gnome-terminal."))
    summary = Summary(title=_('Project summary'), required=True)


class ICreateQuestionFromBugTaskForm(Interface):
    """Form for creating and question from a bug."""
    comment = Text(
        title=_('Comment'),
        description=_('An explanation of why the bug report is a question.'),
        required=False)


class IRemoveQuestionFromBugTaskForm(Interface):
    """Form for removing a question created from a bug."""
    comment = Text(
        title=_('Comment'),
        description=_('An explanation of why the bug report is valid.'),
        required=False)
