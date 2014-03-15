# Copyright 2010-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Enumerations used in the lp/blueprints modules."""

__metaclass__ = type
__all__ = [
    'NewSpecificationDefinitionStatus',
    'SpecificationDefinitionStatus',
    'SpecificationFilter',
    'SpecificationGoalStatus',
    'SpecificationImplementationStatus',
    'SpecificationLifecycleStatus',
    'SpecificationPriority',
    'SpecificationSort',
    'SprintSpecificationStatus',
    'SpecificationWorkItemStatus',
    ]


from lazr.enum import (
    DBEnumeratedType,
    DBItem,
    EnumeratedType,
    Item,
    use_template,
    )


class SpecificationImplementationStatus(DBEnumeratedType):
    """The Specification Delivery Status

    This tracks the implementation or delivery of the feature being
    specified. The status values indicate the progress that is being made
    in the actual coding or configuration that is needed to realise the
    feature.

    Note that some of the states associated with this schema correlate
    to a "not started" definition. See spec_started_clause for further
    information, and make sure that it is updated (together with the relevant
    database checks) if additional states are added that are also "not
    started".
    """
    # The `UNKNOWN` state is considered "not started"
    UNKNOWN = DBItem(0, """
        Unknown

        We have no information on the implementation of this feature.
        """)

    # The `NOTSTARTED` state is considered "not started"
    NOTSTARTED = DBItem(5, """
        Not started

        No work has yet been done on the implementation of this feature.
        """)

    # The `DEFERRED` state is considered "not started"
    DEFERRED = DBItem(10, """
        Deferred

        There is no chance that this feature will actually be delivered in
        the targeted release. The specification has effectively been
        deferred to a later date of implementation.
        """)

    NEEDSINFRASTRUCTURE = DBItem(40, """
        Needs Infrastructure

        Work cannot proceed, because the feature depends on
        infrastructure (servers, databases, connectivity, system
        administration work) that has not been supplied.
        """)

    BLOCKED = DBItem(50, """
        Blocked

        Work cannot proceed on this specification because it depends on
        a separate feature that has not yet been implemented.
        (The specification for that feature should be listed as a blocker of
        this one.)
        """)

    STARTED = DBItem(60, """
        Started

        Work has begun, but has not yet been published
        except as informal branches or patches. No indication is given as to
        whether or not this work will be completed for the targeted release.
        """)

    SLOW = DBItem(65, """
        Slow progress

        Work has been slow on this item, and it has a high risk of not being
        delivered on time. Help is wanted with the implementation.
        """)

    GOOD = DBItem(70, """
        Good progress

        The feature is considered on track for delivery in the targeted
        release.
        """)

    BETA = DBItem(75, """
        Beta Available

        A beta version, implementing substantially all of the feature,
        has been published for widespread testing in personal package
        archives or a personal release. The code is not yet in the
        main archive or mainline branch. Testing and feedback are solicited.
        """)

    NEEDSREVIEW = DBItem(80, """
        Needs Code Review

        The developer is satisfied that the feature has been well
        implemented. It is now ready for review and final sign-off,
        after which it will be marked implemented or deployed.
        """)

    AWAITINGDEPLOYMENT = DBItem(85, """
        Deployment

        The implementation has been done, and can be deployed in the
        production environment, but this has not yet been done by the system
        administrators. (This status is typically used for Web services where
        code is not released but instead is pushed into production.
        """)

    IMPLEMENTED = DBItem(90, """
        Implemented

        This functionality has been delivered for the targeted release, the
        code has been uploaded to the main archives or committed to the
        targeted product series, and no further work is necessary.
        """)

    INFORMATIONAL = DBItem(95, """
        Informational

        This specification is informational, and does not require
        any implementation.
        """)


class SpecificationLifecycleStatus(DBEnumeratedType):
    """The current "lifecycle" status of a specification.

    Specs go from NOTSTARTED, to STARTED, to COMPLETE.
    """

    NOTSTARTED = DBItem(10, """
        Not started

        No work has yet been done on this feature.
        """)

    STARTED = DBItem(20, """
        Started

        This feature is under active development.
        """)

    COMPLETE = DBItem(30, """
        Complete

        This feature has been marked "complete" because no further work is
        expected. Either the feature is done, or it has been abandoned.
        """)


class SpecificationPriority(DBEnumeratedType):
    """The Priority with a Specification must be implemented.

    This enum is used to prioritize work.
    """

    NOTFORUS = DBItem(0, """
        Not

        This feature has been proposed but the project leaders have decided
        that it is not appropriate for inclusion in the mainline codebase.
        See the status whiteboard or the
        specification itself for the rationale for this decision. Of course,
        you are welcome to implement it in any event and publish that work
        for consideration by the community and end users, but it is unlikely
        to be accepted by the mainline developers.
        """)

    UNDEFINED = DBItem(5, """
        Undefined

        This feature has recently been proposed and has not yet been
        evaluated and prioritized by the project leaders.
        """)

    LOW = DBItem(10, """
        Low

        We would like to have it in the
        code, but it's not on any critical path and is likely to get bumped
        in favour of higher-priority work. The idea behind the specification
        is sound and the project leaders would incorporate this
        functionality if the work was done. In general, "low" priority
        specifications will not get core resources assigned to them.
        """)

    MEDIUM = DBItem(50, """
        Medium

        The project developers will definitely get to this feature,
        but perhaps not in the next major release or two.
        """)

    HIGH = DBItem(70, """
        High

        Strongly desired by the project leaders.
        The feature will definitely get review time, and contributions would
        be most effective if directed at a feature with this priority.
        """)

    ESSENTIAL = DBItem(90, """
        Essential

        The specification is essential for the next release, and should be
        the focus of current development. Use this state only for the most
        important of all features.
        """)


class SpecificationFilter(DBEnumeratedType):
    """The kinds of specifications that a listing should include.

    This is used by browser classes that are generating a list of
    specifications for a person, or product, or project, to indicate what
    kinds of specs they want returned. The different filters can be OR'ed so
    that multiple pieces of information can be used for the filter.
    """
    ALL = DBItem(0, """
        All

        This indicates that the list should simply include ALL
        specifications for the underlying object (person, product etc).
        """)

    COMPLETE = DBItem(5, """
        Complete

        This indicates that the list should include only the complete
        specifications for this object.
        """)

    INCOMPLETE = DBItem(10, """
        Incomplete

        This indicates that the list should include the incomplete items
        only. The rules for determining if a specification is incomplete are
        complex, depending on whether or not the spec is informational.
        """)

    INFORMATIONAL = DBItem(20, """
        Informational

        This indicates that the list should include only the informational
        specifications.
        """)

    PROPOSED = DBItem(30, """
        Proposed

        This indicates that the list should include specifications that have
        been proposed as goals for the underlying objects, but not yet
        accepted or declined.
        """)

    DECLINED = DBItem(40, """
        Declined

        This indicates that the list should include specifications that were
        declined as goals for the underlying productseries or distroseries.
        """)

    ACCEPTED = DBItem(50, """
        Accepted

        This indicates that the list should include specifications that were
        accepted as goals for the underlying productseries or distroseries.
        """)

    VALID = DBItem(55, """
        Valid

        This indicates that the list should include specifications that are
        not obsolete or superseded.
        """)

    CREATOR = DBItem(60, """
        Creator

        This indicates that the list should include specifications that the
        person registered in Launchpad.
        """)

    ASSIGNEE = DBItem(70, """
        Assignee

        This indicates that the list should include specifications that the
        person has been assigned to implement.
        """)

    APPROVER = DBItem(80, """
        Approver

        This indicates that the list should include specifications that the
        person is supposed to review and approve.
        """)

    DRAFTER = DBItem(90, """
        Drafter

        This indicates that the list should include specifications that the
        person is supposed to draft. The drafter is usually only needed
        during spec sprints when there's a bottleneck on guys who are
        assignees for many specs.
        """)

    SUBSCRIBER = DBItem(100, """
        Subscriber

        This indicates that the list should include all the specifications
        to which the person has subscribed.
        """)

    STARTED = DBItem(110, """
        Started

        This indicates that the list should include specifications that are
        marked as started.
        """)


class SpecificationSort(EnumeratedType):
    """The scheme to sort the results of a specifications query.

    This is usually used in interfaces which ask for a filtered list of
    specifications, so that you can tell which specifications you would
    expect to see first.
    """
    DATE = Item("""
        Date

        This indicates a preferred sort order of date of creation, newest
        first.
        """)

    PRIORITY = Item("""
        Priority

        This indicates a preferred sort order of priority (highest first)
        followed by status. This is the default sort order when retrieving
        specifications from the system.
        """)


class SpecificationDefinitionStatus(DBEnumeratedType):
    """The current status of a Specification.

    This enum tells us whether or not a specification is approved, or still
    being drafted, or implemented, or obsolete in some way. The ordinality
    of the values is important, it's the order (lowest to highest) in which
    we probably want them displayed by default.
    """

    APPROVED = DBItem(10, """
        Approved

        The project team believe that the specification is ready to be
        implemented, without substantial issues being encountered.
        """)

    PENDINGAPPROVAL = DBItem(15, """
        Pending Approval

        Reviewed and considered ready for final approval.
        The reviewer believes the specification is clearly written,
        and adequately addresses all important issues that will
        be raised during implementation.
        """)

    PENDINGREVIEW = DBItem(20, """
        Review

        Has been put in a reviewer's queue. The reviewer will
        assess it for clarity and comprehensiveness, and decide
        whether further work is needed before the spec can be considered for
        actual approval.
        """)

    DRAFT = DBItem(30, """
        Drafting

        The specification is actively being drafted, with a drafter in place
        and frequent revision occurring.
        Do not park specs in the "drafting" state indefinitely.
        """)

    DISCUSSION = DBItem(35, """
        Discussion

        Still needs active discussion, at a sprint for example.
        """)

    NEW = DBItem(40, """
        New

        No thought has yet been given to implementation strategy,
        dependencies, or presentation/UI issues.
        """)

    SUPERSEDED = DBItem(60, """
        Superseded

        Still interesting, but superseded by a newer spec or set of specs that
        clarify or describe a newer way to implement the desired feature.
        Please use the newer specs and not this one.
        """)

    OBSOLETE = DBItem(70, """
        Obsolete

        The specification has been obsoleted, probably because it was decided
        against. People should not put any effort into implementing it.
        """)


class NewSpecificationDefinitionStatus(DBEnumeratedType):
    """The Initial status of a Specification.

    The initial status to define the feature and get approval for the
    implementation plan.
    """
    use_template(SpecificationDefinitionStatus, include=(
        'NEW',
        'DISCUSSION',
        'DRAFT',
        'PENDINGREVIEW',
        'PENDINGAPPROVAL',
        'APPROVED',
        ))


class SpecificationGoalStatus(DBEnumeratedType):
    """The target status for this specification.

    This enum allows us to show whether or not the specification has been
    approved or declined as a target for the given productseries or
    distroseries.
    """

    ACCEPTED = DBItem(10, """
        Accepted

        The drivers have confirmed that this specification is targeted to
        the stated distribution release or product series.
        """)

    DECLINED = DBItem(20, """
        Declined

        The drivers have decided not to accept this specification as a goal
        for the stated distribution release or product series.
        """)

    PROPOSED = DBItem(30, """
        Proposed

        This spec has been submitted as a potential goal for the stated
        product series or distribution release, but the drivers have not yet
        accepted or declined that goal.
        """)


class SprintSpecificationStatus(DBEnumeratedType):
    """The current approval status of the spec on this sprint's agenda.

    This enum allows us to know whether or not the meeting admin team has
    agreed to discuss an item.
    """

    ACCEPTED = DBItem(10, """
        Accepted

        The meeting organisers have confirmed this topic for the meeting
        agenda.
        """)

    DECLINED = DBItem(20, """
        Declined

        This spec has been declined from the meeting agenda
        because of a lack of available resources, or uncertainty over
        the specific requirements or outcome desired.
        """)

    PROPOSED = DBItem(30, """
        Proposed

        This spec has been submitted for consideration by the meeting
        organisers. It has not yet been accepted or declined for the
        agenda.
        """)


class SpecificationWorkItemStatus(DBEnumeratedType):
    TODO = DBItem(0, """
        Todo

        A work item that's not done yet.
        """)
    DONE = DBItem(1, """
        Done

        A work item that's done.
        """)
    POSTPONED = DBItem(2, """
        Postponed

        A work item that has been postponed.
        """)
    INPROGRESS = DBItem(3, """
        In progress

        A work item that is inprogress.
        """)
    BLOCKED = DBItem(4, """
        Blocked

        A work item that is blocked.
        """)
