# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Specification interfaces."""

__metaclass__ = type

__all__ = [
    'GoalProposeError',
    'ISpecification',
    'ISpecificationDelta',
    'ISpecificationPublic',
    'ISpecificationSet',
    'ISpecificationView',
    ]

import httplib

from lazr.restful.declarations import (
    call_with,
    error_status,
    export_as_webservice_entry,
    export_operation_as,
    export_write_operation,
    exported,
    mutator_for,
    operation_for_version,
    operation_parameters,
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
    Int,
    List,
    Text,
    TextLine,
    )

from lp import _
from lp.app.enums import InformationType
from lp.app.interfaces.launchpad import IPrivacy
from lp.app.validators import LaunchpadValidationError
from lp.app.validators.url import valid_webref
from lp.blueprints.enums import (
    SpecificationDefinitionStatus,
    SpecificationGoalStatus,
    SpecificationImplementationStatus,
    SpecificationLifecycleStatus,
    SpecificationPriority,
    SpecificationWorkItemStatus,
    )
from lp.blueprints.interfaces.specificationsubscription import (
    ISpecificationSubscription,
    )
from lp.blueprints.interfaces.specificationtarget import (
    IHasSpecifications,
    ISpecificationTarget,
    )
from lp.blueprints.interfaces.specificationworkitem import (
    ISpecificationWorkItem,
    )
from lp.blueprints.interfaces.sprint import ISprint
from lp.bugs.interfaces.buglink import IBugLinkTarget
from lp.bugs.interfaces.bugtarget import IBugTarget
from lp.code.interfaces.branchlink import IHasLinkedBranches
from lp.registry.interfaces.milestone import IMilestone
from lp.registry.interfaces.person import IPerson
from lp.registry.interfaces.projectgroup import IProjectGroup
from lp.registry.interfaces.role import IHasOwner
from lp.services.fields import (
    ContentNameField,
    PublicPersonChoice,
    Summary,
    Title,
    WorkItemsText,
    )
from lp.services.webapp import canonical_url
from lp.services.webapp.escaping import structured


@error_status(httplib.BAD_REQUEST)
class GoalProposeError(Exception):
    """Invalid series goal for this specification."""


class SpecNameField(ContentNameField):

    errormessage = _("%s is already in use by another blueprint.")

    @property
    def _content_iface(self):
        return ISpecification

    def _getByName(self, name):
        """Finds a specification by name from the current context.

        Returns a specification if (and only if) the current context
        defines a unique specification namespace and then if a matching
        specification can be found within that namespace. Returns None
        otherwise.
        """
        if ISpecificationSet.providedBy(self.context):
            # The context is the set of all specifications. Since this
            # set corresponds to multiple specification namespaces, we
            # return None.
            return None
        elif IProjectGroup.providedBy(self.context):
            # The context is a project group. Since a project group
            # corresponds to multiple specification namespaces, we
            # return None.
            return None
        elif ISpecification.providedBy(self.context):
            # The context is a specification. Since a specification's
            # target defines a single specification namespace, we ask
            # the target to perform the lookup.
            return self.context.target.getSpecification(name)
        elif ISprint.providedBy(self.context):
            # The context is a sprint. Since a sprint corresponds
            # to multiple specification namespaces, we return None.
            return None
        else:
            # The context is a entity such as a product or distribution.
            # Since this type of context is associated with exactly one
            # specification namespace, we ask the context to perform the
            # lookup.
            return self.context.getSpecification(name)


class SpecURLField(TextLine):

    errormessage = _('%s is already registered by <a href=\"%s\">%s</a>.')

    def _validate(self, specurl):
        TextLine._validate(self, specurl)
        if (ISpecification.providedBy(self.context) and
            specurl == self.context.specurl):
            # The specurl wasn't changed
            return

        specification = getUtility(ISpecificationSet).getByURL(specurl)
        if specification is not None:
            specification_url = canonical_url(specification)
            raise LaunchpadValidationError(
                    structured(self.errormessage, specurl, specification_url,
                        specification.title))


class ISpecificationPublic(IPrivacy):
    """Specification's public attributes and methods."""

    id = Int(title=_("Database ID"), required=True, readonly=True)

    information_type = exported(
        Choice(
            title=_('Information Type'), vocabulary=InformationType,
            required=True, readonly=True, default=InformationType.PUBLIC,
            description=_(
                'The type of information contained in this specification.')))

    def userCanView(user):
        """Return True if `user` can see this ISpecification, false otherwise.
        """


class ISpecificationView(IHasOwner, IHasLinkedBranches):
    """Specification's attributes and methods that require
    the permission launchpad.LimitedView.
    """

    name = exported(
        SpecNameField(
            title=_('Name'), required=True, readonly=False,
            description=_(
                "May contain lower-case letters, numbers, and dashes. "
                "It will be used in the specification url. "
                "Examples: mozilla-type-ahead-find, postgres-smart-serial.")),
        as_of="devel")
    title = exported(
        Title(
            title=_('Title'), required=True, description=_(
                "Describe the feature as clearly as possible in up to 70 "
                "characters. This title is displayed in every feature "
                "list or report.")),
        as_of="devel")
    specurl = exported(
        SpecURLField(
            title=_('Specification URL'), required=False,
            description=_(
                "The URL of the specification. This is usually a wiki page."),
            constraint=valid_webref),
        exported_as="specification_url",
        as_of="devel",
        )
    summary = exported(
        Summary(
            title=_('Summary'), required=True, description=_(
                "A single-paragraph description of the feature. "
                "This will also be displayed in most feature listings.")),
        as_of="devel")

    definition_status = exported(
        Choice(
            title=_('Definition Status'), readonly=True,
            vocabulary=SpecificationDefinitionStatus,
            default=SpecificationDefinitionStatus.NEW,
            description=_(
                "The current status of the process to define the "
                "feature and get approval for the implementation plan.")),
        as_of="devel")

    assignee = exported(
        PublicPersonChoice(
            title=_('Assignee'), required=False,
            description=_(
                "The person responsible for implementing the feature."),
            vocabulary='ValidPersonOrTeam'),
        as_of="devel")
    assigneeID = Attribute('db assignee value')
    drafter = exported(
        PublicPersonChoice(
            title=_('Drafter'), required=False,
            description=_(
                    "The person responsible for drafting the specification."),
                vocabulary='ValidPersonOrTeam'),
        as_of="devel")
    drafterID = Attribute('db drafter value')
    approver = exported(
        PublicPersonChoice(
            title=_('Approver'), required=False,
            description=_(
                "The person responsible for approving the specification, "
                "and for reviewing the code when it's ready to be landed."),
            vocabulary='ValidPersonOrTeam'),
        as_of="devel")
    approverID = Attribute('db approver value')

    priority = exported(
        Choice(
            title=_('Priority'), vocabulary=SpecificationPriority,
            default=SpecificationPriority.UNDEFINED, required=True),
        as_of="devel")
    datecreated = exported(
        Datetime(
            title=_('Date Created'), required=True, readonly=True),
        as_of="devel",
        exported_as="date_created",
        )
    owner = exported(
        PublicPersonChoice(
            title=_('Owner'), required=True, readonly=True,
            vocabulary='ValidPersonOrTeam'),
        as_of="devel")

    product = Choice(title=_('Project'), required=False,
                     vocabulary='Product')
    distribution = Choice(title=_('Distribution'), required=False,
                          vocabulary='Distribution')

    # Exported as readonly for simplicity, but could be exported as read-write
    # using setTarget() as the mutator.
    target = exported(
        ReferenceChoice(
            title=_('For'), required=True, vocabulary='DistributionOrProduct',
            description=_(
                "The project for which this proposal is being made."),
            schema=ISpecificationTarget),
        as_of="devel",
        readonly=True,
        )

    productseries = Choice(
        title=_('Series Goal'), required=False,
        vocabulary='FilteredProductSeries',
        description=_(
             "Choose a series in which you would like to deliver this "
             "feature. Selecting '(nothing selected)' will clear the goal."))
    distroseries = Choice(
        title=_('Series Goal'), required=False,
        vocabulary='FilteredDistroSeries',
        description=_(
             "Choose a series in which you would like to deliver this "
             "feature. Selecting '(nothing selected)' will clear the goal."))

    # milestone
    milestone = exported(
        ReferenceChoice(
            title=_('Milestone'), required=False, vocabulary='Milestone',
            description=_(
                "The milestone in which we would like this feature to be "
                "delivered."),
            schema=IMilestone),
        as_of="devel")

    # nomination to a series for release management
    # XXX: It'd be nice to export goal as read-only, but it's tricky because
    # users will need to be aware of goalstatus as what's returned by .goal
    # may not be the accepted goal.
    goal = Attribute("The series for which this feature is a goal.")
    goalstatus = Choice(
        title=_('Goal Acceptance'), vocabulary=SpecificationGoalStatus,
        default=SpecificationGoalStatus.PROPOSED, description=_(
            "Whether or not the drivers have accepted this feature as "
            "a goal for the targeted series."))
    goal_proposer = Attribute("The person who nominated the spec for "
        "this series.")
    date_goal_proposed = Attribute("The date of the nomination.")
    goal_decider = Attribute("The person who approved or declined "
        "the spec a a goal.")
    date_goal_decided = Attribute("The date the spec was approved "
        "or declined as a goal.")

    work_items = List(
        description=_("All non-deleted work items for this spec, sorted by "
                      "their 'sequence'"),
        value_type=Reference(schema=ISpecificationWorkItem), readonly=True)
    whiteboard = exported(
        Text(title=_('Status Whiteboard'), required=False,
             description=_(
                "Any notes on the status of this spec you would like to "
                "make. Your changes will override the current text.")),
        as_of="devel")
    workitems_text = exported(
        WorkItemsText(
            title=_('Work Items'), required=False, readonly=True,
            description=_(
                "Work items for this specification input in a text format. "
                "Your changes will override the current work items.")),
        as_of="devel")
    direction_approved = exported(
        Bool(title=_('Basic direction approved?'),
             required=True, default=False,
             description=_(
                "Check this to indicate that the drafter and assignee "
                "have satisfied the approver that they are headed in "
                "the right basic direction with this specification.")),
        as_of="devel")
    man_days = Int(title=_("Estimated Developer Days"),
        required=False, default=None, description=_("An estimate of the "
        "number of developer days it will take to implement this feature. "
        "Please only provide an estimate if you are relatively confident "
        "in the number."))
    implementation_status = exported(
        Choice(
            title=_("Implementation Status"), required=True, readonly=True,
            default=SpecificationImplementationStatus.UNKNOWN,
            vocabulary=SpecificationImplementationStatus,
            description=_(
                "The state of progress being made on the actual "
                "implementation or delivery of this feature.")),
        as_of="devel")
    superseded_by = Choice(title=_("Superseded by"),
        required=False, default=None,
        vocabulary='Specification', description=_("The specification "
        "which supersedes this one. Note that selecting a specification "
        "here and pressing Continue will change the specification "
        "status to Superseded."))

    # lifecycle
    starter = exported(
        PublicPersonChoice(
            title=_('Starter'), required=False, readonly=True,
            description=_(
                'The person who first set the state of the '
                'spec to the values that we consider mark it as started.'),
            vocabulary='ValidPersonOrTeam'),
        as_of="devel")
    date_started = exported(
        Datetime(
            title=_('Date Started'), required=False, readonly=True,
            description=_('The date when this spec was marked started.')),
        as_of="devel")

    completer = exported(
        PublicPersonChoice(
            title=_('Starter'), required=False, readonly=True,
            description=_(
            'The person who finally set the state of the '
            'spec to the values that we consider mark it as complete.'),
            vocabulary='ValidPersonOrTeam'),
        as_of="devel")

    date_completed = exported(
        Datetime(
            title=_('Date Completed'), required=False, readonly=True,
            description=_(
                'The date when this spec was marked '
                'complete. Note that complete also includes "obsolete" and '
                'superseded. Essentially, it is the state where no more work '
                'will be done on the feature.')),
        as_of="devel")

    # joins
    subscriptions = Attribute('The set of subscriptions to this spec.')
    subscribers = Attribute('The set of subscribers to this spec.')
    sprints = Attribute('The sprints at which this spec is discussed.')
    sprint_links = Attribute('The entries that link this spec to sprints.')
    dependencies = exported(
        CollectionField(
            title=_('Specs on which this one depends.'),
            value_type=Reference(schema=Interface),  # ISpecification, really.
            readonly=True),
        as_of="devel")
    linked_branches = exported(
        CollectionField(
            title=_("Branches associated with this spec, usually "
            "branches on which this spec is being implemented."),
            value_type=Reference(schema=Interface),  # ISpecificationBranch
            readonly=True),
        as_of="devel")

    def getDependencies():
        """Specs on which this one depends."""

    def getBlockedSpecs():
        """Specs for which this spec is a dependency."""

    # emergent properties
    informational = Attribute('Is True if this spec is purely informational '
        'and requires no implementation.')
    is_complete = exported(
        Bool(title=_('Is started'),
             readonly=True, required=True,
             description=_(
                'Is True if this spec is already completely implemented. '
                'Note that it is True for informational specs, since '
                'they describe general functionality rather than specific '
                'code to be written. It is also true of obsolete and '
                'superseded specs, since there is no longer any need '
                'to schedule work for them.')),
        as_of="devel")

    is_incomplete = Attribute('Is True if this work still needs to '
        'be done. Is in fact always the opposite of is_complete.')
    is_blocked = Attribute('Is True if this spec depends on another spec '
        'which is still incomplete.')
    is_started = exported(
        Bool(title=_('Is started'),
             readonly=True, required=True,
             description=_(
                'Is True if the spec is in a state which '
                'we consider to be "started". This looks at the delivery '
                'attribute, and also considers informational specs to be '
                'started when they are approved.')),
        as_of="devel")

    lifecycle_status = exported(
        Choice(
            title=_('Lifecycle Status'),
            vocabulary=SpecificationLifecycleStatus,
            default=SpecificationLifecycleStatus.NOTSTARTED,
            readonly=True),
        as_of="devel")

    def all_deps():
        """All the dependencies, including dependencies of dependencies.

        If a user is provided, filters to only dependencies the user can see.
        """
    def all_blocked():
        """All specs blocked on this, and those blocked on the blocked ones.

        If a user is provided, filters to only blocked dependencies the user
        can see.
        """

    def validateMove(target):
        """Check that the specification can be moved to the target."""

    def getSprintSpecification(sprintname):
        """Get the record that links this spec to the named sprint."""

    def notificationRecipientAddresses():
        """Return the list of email addresses that receive notifications."""

    has_accepted_goal = exported(
        Bool(title=_('Series goal is accepted'),
             readonly=True, required=True,
             description=_(
                'Is true if this specification has been '
                'proposed as a goal for a specific series, '
                'and the drivers of that series have accepted the goal.')),
        as_of="devel")

    # lifecycle management
    def updateLifecycleStatus(user):
        """Mark the specification as started, and/or complete, if appropriate.

        This will verify that the state of the specification is in fact
        "complete" (there is a completeness test in
        Specification.is_complete) and then record the completer and the
        date_completed. If the spec is not completed, then it ensures that
        nothing is recorded about its completion.

        It returns a SpecificationLifecycleStatus dbschema showing the
        overall state of the specification IF the state has changed.
        """

    # event-related methods
    def getDelta(old_spec, user):
        """Return a dictionary of things that changed between this spec and
        the old_spec.

        This method is primarily used by event subscription code, to
        determine what has changed during an ObjectModifiedEvent.
        """

    # subscription-related methods
    def subscription(person):
        """Return the subscription for this person to this spec, or None."""

    @operation_parameters(
        person=Reference(IPerson, title=_('Person'), required=True),
        essential=copy_field(
            ISpecificationSubscription['essential'], required=False))
    @call_with(subscribed_by=REQUEST_USER)
    @export_write_operation()
    @operation_for_version('devel')
    def subscribe(person, subscribed_by=None, essential=False):
        """Subscribe this person to the feature specification."""

    @operation_parameters(
        person=Reference(IPerson, title=_('Person'), required=False))
    @call_with(unsubscribed_by=REQUEST_USER)
    @export_write_operation()
    @operation_for_version('devel')
    def unsubscribe(person, unsubscribed_by):
        """Remove the person's subscription to this spec."""

    def getSubscriptionByName(name):
        """Return a subscription based on the person's name, or None."""

    def isSubscribed(person):
        """Is person subscribed to this spec?

        Returns True if the user is explicitly subscribed to this spec
        (no matter what the type of subscription), otherwise False.

        If person is None, the return value is always False.
        """

    # sprints
    def linkSprint(sprint, user):
        """Put this spec on the agenda of the sprint."""

    def unlinkSprint(sprint):
        """Remove this spec from the agenda of the sprint."""

    # dependencies
    def createDependency(specification):
        """Create a dependency for this spec on the spec provided."""

    def removeDependency(specification):
        """Remove any dependency of this spec on the spec provided."""

    # branches
    def getBranchLink(branch):
        """Return the SpecificationBranch link for the branch, or None."""

    def getLinkedBugTasks(user):
        """Return the bug tasks that are relevant to this blueprint.

        When multiple tasks are on a bug, if one of the tasks is for the
        target, then only that task is returned. Otherwise the default
        bug task is returned.

        :param user: The user doing the search.
        """

    def getAllowedInformationTypes(who):
        """Get a list of acceptable `InformationType`s for this spec."""


class ISpecificationEditRestricted(Interface):
    """Specification's attributes and methods protected with launchpad.Edit.
    """

    @mutator_for(ISpecificationView['definition_status'])
    @call_with(user=REQUEST_USER)
    @operation_parameters(
        definition_status=copy_field(
            ISpecificationView['definition_status']))
    @export_write_operation()
    @operation_for_version("devel")
    def setDefinitionStatus(definition_status, user):
        """Mutator for definition_status that calls updateLifeCycle."""

    @mutator_for(ISpecificationView['implementation_status'])
    @call_with(user=REQUEST_USER)
    @operation_parameters(
        implementation_status=copy_field(
            ISpecificationView['implementation_status']))
    @export_write_operation()
    @operation_for_version("devel")
    def setImplementationStatus(implementation_status, user):
        """Mutator for implementation_status that calls updateLifeCycle."""

    def newWorkItem(title, sequence,
                    status=SpecificationWorkItemStatus.TODO, assignee=None,
                    milestone=None):
        """Create a new SpecificationWorkItem."""

    def updateWorkItems(new_work_items):
        """Update the existing work items to match the given ones.

        First, for every existing work item that is not present on the new
        list, mark it as deleted. Then, for every tuple in the given list,
        lookup an existing work item with the same title and update its
        status, assignee, milestone and sequence (position on the work-items
        list). If there's no existing work items with that title, we create a
        new one.

        :param new_work_items: A list of dictionaries containing the following
            keys: title, status, assignee and milestone.
        """

    def setTarget(target):
        """Set this specification's target.

        :param target: an IProduct or IDistribution.
        """

    def retarget(target):
        """Move the spec to the given target.

        The new target must be an IProduct or IDistribution.
        """

    def transitionToInformationType(information_type, who):
        """Change the information type of the Specification."""

    @call_with(proposer=REQUEST_USER)
    @operation_parameters(
        goal=Reference(
            schema=IBugTarget, title=_('Target'),
            required=False, default=None))
    @export_write_operation()
    @operation_for_version("devel")
    def proposeGoal(goal, proposer):
        """Propose this spec for a series or distroseries."""


class ISpecificationDriverRestricted(Interface):
    """Specification bits protected with launchpad.Driver."""

    @call_with(decider=REQUEST_USER)
    @export_operation_as('acceptGoal')
    @export_write_operation()
    @operation_for_version("devel")
    def acceptBy(decider):
        """Mark the spec as being accepted for its current series goal."""

    @call_with(decider=REQUEST_USER)
    @export_operation_as('declineGoal')
    @export_write_operation()
    @operation_for_version("devel")
    def declineBy(decider):
        """Mark the spec as being declined as a goal for the proposed
        series.
        """


class ISpecification(ISpecificationPublic, ISpecificationView,
                     ISpecificationEditRestricted,
                     ISpecificationDriverRestricted, IBugLinkTarget):
    """A Specification."""

    export_as_webservice_entry(as_of="beta")

    @mutator_for(ISpecificationView['workitems_text'])
    @operation_parameters(new_work_items=WorkItemsText())
    @export_write_operation()
    @operation_for_version('devel')
    def setWorkItems(new_work_items):
        """Set work items on this specification.

        :param new_work_items: Work items to set.
        """

    @operation_parameters(
        bug=Reference(schema=Interface))  # Really IBug
    @export_write_operation()
    @operation_for_version('devel')
    def linkBug(bug):
        """Link a bug to this specification.

        :param bug: IBug to link.
        """

    @operation_parameters(
        bug=Reference(schema=Interface))  # Really IBug
    @export_write_operation()
    @operation_for_version('devel')
    def unlinkBug(bug):
        """Unlink a bug to this specification.

        :param bug: IBug to unlink.
        """


class ISpecificationSet(IHasSpecifications):
    """A container for specifications."""

    displayname = Attribute('Displayname')

    title = Attribute('Title')

    coming_sprints = Attribute("The next 5 sprints in the system.")

    def specificationCount(user):
        """The total number of blueprints in Launchpad"""

    def getStatusCountsForProductSeries(product_series):
        """Return the status counts for blueprints in a series.

        Both the nominated and scheduled blueprints are included
        in the count.

        :param product_series: ProductSeries object.
        :return: A list of tuples containing (status_id, count).
        """

    def getByURL(url):
        """Return the specification with the given url."""

    def getByName(pillar, name):
        """Return the specification with the given name for the given pillar.
        """

    def new(name, title, specurl, summary, definition_status,
        owner, approver=None, product=None, distribution=None, assignee=None,
        drafter=None, whiteboard=None,
        priority=SpecificationPriority.UNDEFINED):
        """Create a new specification."""

    def getDependencyDict(specifications):
        """Return a dictionary mapping specifications to their dependencies.

        The results are ordered by descending priority, ascending dependency
        name, and id.

        :param specifications: a sequence of the `ISpecification` to look up.
        """

    def get(spec_id):
        """Return the ISpecification with the given spec_id."""


class ISpecificationDelta(Interface):
    """The quantitative changes made to a spec that was edited."""

    specification = Attribute("The ISpec, after it's been edited.")
    user = Attribute("The IPerson that did the editing.")

    # fields on the spec itself, we provide just the new changed value
    title = Attribute("The spec title or None.")
    summary = Attribute("The spec summary or None.")
    whiteboard = Attribute("The spec whiteboard or None.")
    workitems_text = Attribute("The spec work items as text or None.")
    specurl = Attribute("The URL to the spec home page (not in Launchpad).")
    productseries = Attribute("The product series.")
    distroseries = Attribute("The series to which this is targeted.")
    milestone = Attribute("The milestone to which the spec is targeted.")
    bugs_linked = Attribute("A list of new bugs linked to this spec.")
    bugs_unlinked = Attribute("A list of bugs unlinked from this spec.")

    # items where we provide 'old' and 'new' values if they changed
    name = Attribute("Old and new names, or None.")
    priority = Attribute("Old and new priorities, or None")
    definition_status = Attribute("Old and new statuses, or None")
    target = Attribute("Old and new target, or None")
    approver = Attribute("Old and new approver, or None")
    assignee = Attribute("Old and new assignee, or None")
    drafter = Attribute("Old and new drafter, or None")
