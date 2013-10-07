# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'HasSpecificationsMixin',
    'recursive_blocked_query',
    'Specification',
    'SPECIFICATION_POLICY_ALLOWED_TYPES',
    'SPECIFICATION_POLICY_DEFAULT_TYPES',
    'SpecificationSet',
    ]

from lazr.lifecycle.event import (
    ObjectCreatedEvent,
    ObjectModifiedEvent,
    )
from lazr.lifecycle.objectdelta import ObjectDelta
from sqlobject import (
    BoolCol,
    ForeignKey,
    IntCol,
    SQLMultipleJoin,
    SQLRelatedJoin,
    StringCol,
    )
from storm.expr import Join
from storm.locals import (
    Desc,
    SQL,
    )
from storm.store import Store
from zope.component import getUtility
from zope.event import notify
from zope.interface import implements

from lp.app.enums import (
    InformationType,
    PRIVATE_INFORMATION_TYPES,
    PUBLIC_INFORMATION_TYPES,
    )
from lp.app.errors import UserCannotUnsubscribePerson
from lp.app.interfaces.informationtype import IInformationType
from lp.app.interfaces.services import IService
from lp.app.model.launchpad import InformationTypeMixin
from lp.blueprints.adapters import SpecificationDelta
from lp.blueprints.enums import (
    NewSpecificationDefinitionStatus,
    SpecificationDefinitionStatus,
    SpecificationFilter,
    SpecificationGoalStatus,
    SpecificationImplementationStatus,
    SpecificationLifecycleStatus,
    SpecificationPriority,
    SpecificationSort,
    SpecificationWorkItemStatus,
    )
from lp.blueprints.errors import TargetAlreadyHasSpecification
from lp.blueprints.interfaces.specification import (
    GoalProposeError,
    ISpecification,
    ISpecificationSet,
    )
from lp.blueprints.model.specificationbranch import SpecificationBranch
from lp.blueprints.model.specificationbug import SpecificationBug
from lp.blueprints.model.specificationdependency import (
    SpecificationDependency,
    )
from lp.blueprints.model.specificationsubscription import (
    SpecificationSubscription,
    )
from lp.blueprints.model.specificationworkitem import SpecificationWorkItem
from lp.bugs.interfaces.buglink import IBugLinkTarget
from lp.bugs.interfaces.bugtask import IBugTaskSet
from lp.bugs.interfaces.bugtaskfilter import filter_bugtasks_by_context
from lp.bugs.interfaces.bugtasksearch import BugTaskSearchParams
from lp.bugs.model.buglinktarget import BugLinkTargetMixin
from lp.registry.enums import SpecificationSharingPolicy
from lp.registry.errors import CannotChangeInformationType
from lp.registry.interfaces.accesspolicy import (
    IAccessArtifactGrantSource,
    IAccessArtifactSource,
    )
from lp.registry.interfaces.distribution import IDistribution
from lp.registry.interfaces.distroseries import IDistroSeries
from lp.registry.interfaces.person import validate_public_person
from lp.registry.interfaces.product import IProduct
from lp.registry.interfaces.productseries import IProductSeries
from lp.services.database.constants import (
    DEFAULT,
    UTC_NOW,
    )
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.enumcol import EnumCol
from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import (
    convert_storm_clause_to_string,
    cursor,
    SQLBase,
    sqlvalues,
    )
from lp.services.mail.helpers import get_contact_email_addresses
from lp.services.propertycache import (
    cachedproperty,
    get_property_cache,
    )
from lp.services.webapp.interfaces import ILaunchBag


def recursive_blocked_query(user):
    from lp.blueprints.model.specificationsearch import (
        get_specification_privacy_filter)
    return """
        RECURSIVE blocked(id) AS (
            SELECT ?
        UNION
            SELECT sd.specification
            FROM blocked b, specificationdependency sd
            JOIN specification ON sd.specification = specification.id
            WHERE sd.dependency = b.id AND (%s))""" % (
                convert_storm_clause_to_string(
                    *get_specification_privacy_filter(user)))


def recursive_dependent_query(user):
    from lp.blueprints.model.specificationsearch import (
        get_specification_privacy_filter)
    return """
        RECURSIVE dependencies(id) AS (
            SELECT ?
        UNION
            SELECT sd.dependency
            FROM dependencies d, specificationdependency sd
            JOIN specification ON sd.dependency = specification.id
            WHERE sd.specification = d.id AND (%s))""" % (
                convert_storm_clause_to_string(
                    *get_specification_privacy_filter(user)))


SPECIFICATION_POLICY_ALLOWED_TYPES = {
    SpecificationSharingPolicy.PUBLIC: [InformationType.PUBLIC],
    SpecificationSharingPolicy.PUBLIC_OR_PROPRIETARY:
        [InformationType.PUBLIC, InformationType.PROPRIETARY],
    SpecificationSharingPolicy.PROPRIETARY_OR_PUBLIC:
        [InformationType.PUBLIC, InformationType.PROPRIETARY],
    SpecificationSharingPolicy.PROPRIETARY: [InformationType.PROPRIETARY],
    SpecificationSharingPolicy.EMBARGOED_OR_PROPRIETARY:
        [InformationType.PROPRIETARY, InformationType.EMBARGOED],
    SpecificationSharingPolicy.FORBIDDEN: [],
    }

SPECIFICATION_POLICY_DEFAULT_TYPES = {
    SpecificationSharingPolicy.PUBLIC: InformationType.PUBLIC,
    SpecificationSharingPolicy.PUBLIC_OR_PROPRIETARY: (
        InformationType.PUBLIC),
    SpecificationSharingPolicy.PROPRIETARY_OR_PUBLIC: (
        InformationType.PROPRIETARY),
    SpecificationSharingPolicy.PROPRIETARY: InformationType.PROPRIETARY,
    SpecificationSharingPolicy.EMBARGOED_OR_PROPRIETARY: (
        InformationType.EMBARGOED),
    }


class Specification(SQLBase, BugLinkTargetMixin, InformationTypeMixin):
    """See ISpecification."""

    implements(ISpecification, IBugLinkTarget, IInformationType)

    _defaultOrder = ['-priority', 'definition_status', 'name', 'id']

    # db field names
    name = StringCol(unique=True, notNull=True)
    title = StringCol(notNull=True)
    summary = StringCol(notNull=True)
    definition_status = EnumCol(
        schema=SpecificationDefinitionStatus, notNull=True,
        default=SpecificationDefinitionStatus.NEW)
    priority = EnumCol(schema=SpecificationPriority, notNull=True,
        default=SpecificationPriority.UNDEFINED)
    _assignee = ForeignKey(dbName='assignee', notNull=False,
        foreignKey='Person',
        storm_validator=validate_public_person, default=None)
    _drafter = ForeignKey(dbName='drafter', notNull=False,
        foreignKey='Person',
        storm_validator=validate_public_person, default=None)
    _approver = ForeignKey(dbName='approver', notNull=False,
        foreignKey='Person',
        storm_validator=validate_public_person, default=None)
    owner = ForeignKey(
        dbName='owner', foreignKey='Person',
        storm_validator=validate_public_person, notNull=True)
    datecreated = UtcDateTimeCol(notNull=True, default=DEFAULT)
    product = ForeignKey(dbName='product', foreignKey='Product',
        notNull=False, default=None)
    productseries = ForeignKey(dbName='productseries',
        foreignKey='ProductSeries', notNull=False, default=None)
    distribution = ForeignKey(dbName='distribution',
        foreignKey='Distribution', notNull=False, default=None)
    distroseries = ForeignKey(dbName='distroseries',
        foreignKey='DistroSeries', notNull=False, default=None)
    goalstatus = EnumCol(schema=SpecificationGoalStatus, notNull=True,
        default=SpecificationGoalStatus.PROPOSED)
    goal_proposer = ForeignKey(dbName='goal_proposer', notNull=False,
        foreignKey='Person',
        storm_validator=validate_public_person, default=None)
    date_goal_proposed = UtcDateTimeCol(notNull=False, default=None)
    goal_decider = ForeignKey(dbName='goal_decider', notNull=False,
        foreignKey='Person',
        storm_validator=validate_public_person, default=None)
    date_goal_decided = UtcDateTimeCol(notNull=False, default=None)
    milestone = ForeignKey(dbName='milestone',
        foreignKey='Milestone', notNull=False, default=None)
    specurl = StringCol(notNull=False, default=None)
    whiteboard = StringCol(notNull=False, default=None)
    direction_approved = BoolCol(notNull=True, default=False)
    man_days = IntCol(notNull=False, default=None)
    implementation_status = EnumCol(
        schema=SpecificationImplementationStatus, notNull=True,
        default=SpecificationImplementationStatus.UNKNOWN)
    superseded_by = ForeignKey(dbName='superseded_by',
        foreignKey='Specification', notNull=False, default=None)
    completer = ForeignKey(dbName='completer', notNull=False,
        foreignKey='Person',
        storm_validator=validate_public_person, default=None)
    date_completed = UtcDateTimeCol(notNull=False, default=None)
    starter = ForeignKey(dbName='starter', notNull=False,
        foreignKey='Person',
        storm_validator=validate_public_person, default=None)
    date_started = UtcDateTimeCol(notNull=False, default=None)

    # useful joins
    _subscriptions = SQLMultipleJoin('SpecificationSubscription',
        joinColumn='specification', orderBy='id')
    subscribers = SQLRelatedJoin('Person',
        joinColumn='specification', otherColumn='person',
        intermediateTable='SpecificationSubscription',
        orderBy=['displayname', 'name'])
    sprint_links = SQLMultipleJoin('SprintSpecification', orderBy='id',
        joinColumn='specification')
    sprints = SQLRelatedJoin('Sprint', orderBy='name',
        joinColumn='specification', otherColumn='sprint',
        intermediateTable='SprintSpecification')
    bug_links = SQLMultipleJoin(
        'SpecificationBug', joinColumn='specification', orderBy='id')
    bugs = SQLRelatedJoin('Bug',
        joinColumn='specification', otherColumn='bug',
        intermediateTable='SpecificationBug', orderBy='id')
    spec_dependency_links = SQLMultipleJoin('SpecificationDependency',
        joinColumn='specification', orderBy='id')

    dependencies = SQLRelatedJoin('Specification', joinColumn='specification',
        otherColumn='dependency', orderBy='title',
        intermediateTable='SpecificationDependency')
    information_type = EnumCol(
        enum=InformationType, notNull=True, default=InformationType.PUBLIC)

    @cachedproperty
    def linked_branches(self):
        return list(Store.of(self).find(
            SpecificationBranch,
            SpecificationBranch.specificationID == self.id).order_by(
                SpecificationBranch.id))

    def _fetch_children_or_parents(self, join_cond, cond, user):
        from lp.blueprints.model.specificationsearch import (
            get_specification_privacy_filter)
        return list(Store.of(self).using(
            Specification,
            Join(SpecificationDependency, join_cond == self.id)).find(
            Specification,
            cond == Specification.id, *get_specification_privacy_filter(user)
            ).order_by(Specification.title))

    def getDependencies(self, user=None):
        return self._fetch_children_or_parents(
            SpecificationDependency.specificationID,
            SpecificationDependency.dependencyID, user)

    def getBlockedSpecs(self, user=None):
        return self._fetch_children_or_parents(
            SpecificationDependency.dependencyID,
            SpecificationDependency.specificationID, user)

    def set_assignee(self, person):
        self.subscribeIfAccessGrantNeeded(person)
        self._assignee = person

    def get_assignee(self):
        return self._assignee

    assignee = property(get_assignee, set_assignee)

    def set_drafter(self, person):
        self.subscribeIfAccessGrantNeeded(person)
        self._drafter = person

    def get_drafter(self):
        return self._drafter

    drafter = property(get_drafter, set_drafter)

    def set_approver(self, person):
        self.subscribeIfAccessGrantNeeded(person)
        self._approver = person

    def get_approver(self):
        return self._approver

    approver = property(get_approver, set_approver)

    def subscribeIfAccessGrantNeeded(self, person):
        """Subscribe person if this specification is not public and if
        the person does not already have grants to access the specification.
        """
        if person is None or self.userCanView(person):
            return
        current_user = getUtility(ILaunchBag).user
        self.subscribe(person, subscribed_by=current_user)

    @cachedproperty
    def subscriptions(self):
        """Sort the subscriptions"""
        from lp.registry.model.person import person_sort_key
        return sorted(
            self._subscriptions, key=lambda sub: person_sort_key(sub.person))

    @property
    def workitems_text(self):
        """See ISpecification."""
        workitems_lines = []

        def get_header_text(milestone):
            if milestone is None:
                return "Work items:"
            else:
                return "Work items for %s:" % milestone.name

        if len(self.work_items) == 0:
            return ''
        milestone = self.work_items[0].milestone
        # Start by appending a header for the milestone of the first work
        # item. After this we're going to write a new header whenever we see a
        # work item with a different milestone.
        workitems_lines.append(get_header_text(milestone))
        for work_item in self.work_items:
            if work_item.milestone != milestone:
                workitems_lines.append("")
                milestone = work_item.milestone
                workitems_lines.append(get_header_text(milestone))
            assignee = work_item.assignee
            if assignee is not None:
                assignee_part = "[%s] " % assignee.name
            else:
                assignee_part = ""
            # work_items are ordered by sequence
            workitems_lines.append(
                "%s%s: %s" % (
                    assignee_part, work_item.title, work_item.status.name))
        return "\n".join(workitems_lines)

    @property
    def target(self):
        """See ISpecification."""
        if self.product:
            return self.product
        return self.distribution

    def newWorkItem(self, title, sequence,
                    status=SpecificationWorkItemStatus.TODO, assignee=None,
                    milestone=None):
        """See ISpecification."""
        if milestone is not None:
            assert milestone.target == self.target, (
                "%s does not belong to this spec's target (%s)" %
                    (milestone.displayname, self.target.name))
        return SpecificationWorkItem(
            title=title, status=status, specification=self, assignee=assignee,
            milestone=milestone, sequence=sequence)

    @cachedproperty
    def work_items(self):
        """See ISpecification."""
        return list(self._work_items)

    @property
    def _work_items(self):
        return Store.of(self).find(
            SpecificationWorkItem, specification=self,
            deleted=False).order_by("sequence")

    def setWorkItems(self, new_work_items):
        field = ISpecification['workitems_text'].bind(self)
        self.updateWorkItems(field.parseAndValidate(new_work_items))

    def _deleteWorkItemsNotMatching(self, titles):
        """Delete all work items whose title does not match the given ones.

        Also set the sequence of those deleted work items to -1.
        """
        title_counts = self._list_to_dict_of_frequency(titles)

        for work_item in self._work_items:
            if (work_item.title not in title_counts or
                title_counts[work_item.title] == 0):
                work_item.deleted = True

            elif title_counts[work_item.title] > 0:
                title_counts[work_item.title] -= 1

    def _list_to_dict_of_frequency(self, list):
        dictionary = {}
        for item in list:
            if not item in dictionary:
                dictionary[item] = 1
            else:
                dictionary[item] += 1
        return dictionary

    def updateWorkItems(self, new_work_items):
        """See ISpecification."""
        # First mark work items with titles that are no longer present as
        # deleted.
        self._deleteWorkItemsNotMatching(
            [wi['title'] for wi in new_work_items])
        work_items = self._work_items
        # At this point the list of new_work_items is necessarily the same
        # size (or longer) than the list of existing ones, so we can just
        # iterate over it updating the existing items and creating any new
        # ones.
        to_insert = []
        existing_titles = [wi.title for wi in work_items]
        existing_title_count = self._list_to_dict_of_frequency(existing_titles)

        for i, new_wi in enumerate(new_work_items):
            if (new_wi['title'] not in existing_titles or
                existing_title_count[new_wi['title']] == 0):
                to_insert.append((i, new_wi))
            else:
                existing_title_count[new_wi['title']] -= 1
                # Get an existing work item with the same title and update
                # it to match what we have now.
                existing_wi_index = existing_titles.index(new_wi['title'])
                existing_wi = work_items[existing_wi_index]
                # Mark a work item as dirty - don't use it again this update.
                existing_titles[existing_wi_index] = None
                # Update the sequence to match its current position on the
                # list entered by the user.
                existing_wi.sequence = i
                existing_wi.status = new_wi['status']
                existing_wi.assignee = new_wi['assignee']
                milestone = new_wi['milestone']
                if milestone is not None:
                    assert milestone.target == self.target, (
                        "%s does not belong to this spec's target (%s)" %
                            (milestone.displayname, self.target.name))
                existing_wi.milestone = milestone

        for sequence, item in to_insert:
            self.newWorkItem(item['title'], sequence, item['status'],
                             item['assignee'], item['milestone'])
        del get_property_cache(self).work_items

    def setTarget(self, target):
        """See ISpecification."""
        if IProduct.providedBy(target):
            self.product = target
            self.distribution = None
        elif IDistribution.providedBy(target):
            self.product = None
            self.distribution = target
        else:
            raise AssertionError("Unknown target: %s" % target)

    def retarget(self, target):
        """See ISpecification."""
        if self.target == target:
            return

        self.validateMove(target)

        # We must lose any goal we have set and approved/declined because we
        # are moving to a different target that will have different
        # policies and drivers.
        self.productseries = None
        self.distroseries = None
        self.goalstatus = SpecificationGoalStatus.PROPOSED
        self.goal_proposer = None
        self.date_goal_proposed = None
        self.milestone = None

        self.setTarget(target)
        self.priority = SpecificationPriority.UNDEFINED
        self.direction_approved = False

    def validateMove(self, target):
        """See ISpecification."""
        if target.getSpecification(self.name) is not None:
            raise TargetAlreadyHasSpecification(target, self.name)

    @property
    def goal(self):
        """See ISpecification."""
        if self.productseries:
            return self.productseries
        return self.distroseries

    def proposeGoal(self, goal, proposer):
        """See ISpecification."""
        if goal is None:
            # we are clearing goals
            self.productseries = None
            self.distroseries = None
        elif (IProductSeries.providedBy(goal) and
              goal.product == self.target):
            # set the product series as a goal
            self.productseries = goal
            self.goal_proposer = proposer
            self.date_goal_proposed = UTC_NOW
            # and make sure there is no leftover distroseries goal
            self.distroseries = None
        elif (IDistroSeries.providedBy(goal) and
              goal.distribution == self.target):
            # set the distroseries goal
            self.distroseries = goal
            self.goal_proposer = proposer
            self.date_goal_proposed = UTC_NOW
            # and make sure there is no leftover distroseries goal
            self.productseries = None
        else:
            raise GoalProposeError('Inappropriate goal.')
        # record who made the proposal, and when
        self.goal_proposer = proposer
        self.date_goal_proposed = UTC_NOW
        # and of course set the goal status to PROPOSED
        self.goalstatus = SpecificationGoalStatus.PROPOSED
        # the goal should now also not have a decider
        self.goal_decider = None
        self.date_goal_decided = None
        if goal is not None and goal.personHasDriverRights(proposer):
            self.acceptBy(proposer)

    def acceptBy(self, decider):
        """See ISpecification."""
        self.goalstatus = SpecificationGoalStatus.ACCEPTED
        self.goal_decider = decider
        self.date_goal_decided = UTC_NOW

    def declineBy(self, decider):
        """See ISpecification."""
        self.goalstatus = SpecificationGoalStatus.DECLINED
        self.goal_decider = decider
        self.date_goal_decided = UTC_NOW

    def getSprintSpecification(self, sprintname):
        """See ISpecification."""
        for sprintspecification in self.sprint_links:
            if sprintspecification.sprint.name == sprintname:
                return sprintspecification
        return None

    def notificationRecipientAddresses(self):
        """See ISpecification."""
        related_people = [
            self.owner, self.assignee, self.approver, self.drafter]
        related_people = [
            person for person in related_people if person is not None]
        subscribers = [
            subscription.person for subscription in self.subscriptions]
        notify_people = set(related_people + subscribers)
        without_access = set(
            getUtility(IService, 'sharing').getPeopleWithoutAccess(
                self, notify_people))
        notify_people -= without_access
        addresses = set()
        for person in notify_people:
            addresses.update(get_contact_email_addresses(person))
        return sorted(addresses)

    # emergent properties
    @property
    def is_incomplete(self):
        """See ISpecification."""
        return not self.is_complete

    @property
    def is_complete(self):
        """See `ISpecification`."""
        # Implemented blueprints are by definition complete.
        if (self.implementation_status ==
            SpecificationImplementationStatus.IMPLEMENTED):
            return True
        # Obsolete and superseded blueprints are considered complete.
        if self.definition_status in (
            SpecificationDefinitionStatus.OBSOLETE,
            SpecificationDefinitionStatus.SUPERSEDED):
            return True
        # Approved information blueprints are also considered complete.
        if ((self.implementation_status ==
             SpecificationImplementationStatus.INFORMATIONAL) and
            (self.definition_status ==
             SpecificationDefinitionStatus.APPROVED)):
            return True
        else:
            return False

    @property
    def is_started(self):
        """See ISpecification. This is a code implementation of the
        SQL in spec_started_clause
        """
        return (self.implementation_status not in [
                    SpecificationImplementationStatus.UNKNOWN,
                    SpecificationImplementationStatus.NOTSTARTED,
                    SpecificationImplementationStatus.DEFERRED,
                    SpecificationImplementationStatus.INFORMATIONAL,
                    ]
                or ((self.implementation_status ==
                     SpecificationImplementationStatus.INFORMATIONAL) and
                    (self.definition_status ==
                     SpecificationDefinitionStatus.APPROVED)))

    @property
    def lifecycle_status(self):
        """Combine the is_complete and is_started emergent properties."""
        if self.is_complete:
            return SpecificationLifecycleStatus.COMPLETE
        elif self.is_started:
            return SpecificationLifecycleStatus.STARTED
        else:
            return SpecificationLifecycleStatus.NOTSTARTED

    def setDefinitionStatus(self, definition_status, user):
        self.definition_status = definition_status
        self.updateLifecycleStatus(user)

    def setImplementationStatus(self, implementation_status, user):
        self.implementation_status = implementation_status
        self.updateLifecycleStatus(user)

    def updateLifecycleStatus(self, user):
        """See ISpecification."""
        newstatus = None
        if self.is_started:
            if self.starterID is None:
                newstatus = SpecificationLifecycleStatus.STARTED
                self.date_started = UTC_NOW
                self.starter = user
        else:
            if self.starterID is not None:
                newstatus = SpecificationLifecycleStatus.NOTSTARTED
                self.date_started = None
                self.starter = None
        if self.is_complete:
            if self.completerID is None:
                newstatus = SpecificationLifecycleStatus.COMPLETE
                self.date_completed = UTC_NOW
                self.completer = user
        else:
            if self.completerID is not None:
                self.date_completed = None
                self.completer = None
                if self.is_started:
                    newstatus = SpecificationLifecycleStatus.STARTED
                else:
                    newstatus = SpecificationLifecycleStatus.NOTSTARTED

        return newstatus

    @property
    def is_blocked(self):
        """See ISpecification."""
        for spec in self.dependencies:
            if spec.is_incomplete:
                return True
        return False

    @property
    def has_accepted_goal(self):
        """See ISpecification."""
        if (self.goal is not None and
            self.goalstatus == SpecificationGoalStatus.ACCEPTED):
            return True
        return False

    def getDelta(self, old_spec, user):
        """See ISpecification."""
        delta = ObjectDelta(old_spec, self)
        delta.recordNewValues(("title", "summary",
                               "specurl", "productseries",
                               "distroseries", "milestone"))
        delta.recordNewAndOld(("name", "priority", "definition_status",
                               "target", "approver", "assignee", "drafter",
                               "whiteboard", "workitems_text"))
        delta.recordListAddedAndRemoved("bugs", "bugs_linked", "bugs_unlinked")

        if delta.changes:
            changes = delta.changes
            changes["specification"] = self
            changes["user"] = user

            return SpecificationDelta(**changes)
        else:
            return None

    @property
    def informational(self):
        """For backwards compatibility:
        implemented as a value in implementation_status.
        """
        return (self.implementation_status ==
                SpecificationImplementationStatus.INFORMATIONAL)

    # subscriptions
    def subscription(self, person):
        """See ISpecification."""
        return SpecificationSubscription.selectOneBy(
                specification=self, person=person)

    def getSubscriptionByName(self, name):
        """See ISpecification."""
        for sub in self.subscriptions:
            if sub.person.name == name:
                return sub
        return None

    def subscribe(self, person, subscribed_by=None, essential=False):
        """See ISpecification."""
        if subscribed_by is None:
            subscribed_by = person
        # Create or modify a user's subscription to this blueprint.
        # First see if a relevant subscription exists, and if so, return it
        sub = self.subscription(person)
        if sub is not None:
            if sub.essential != essential:
                # If a subscription already exists, but the value for
                # 'essential' changes, there's no need to create a new
                # subscription, but we modify the existing subscription
                # and notify the user about the change.
                sub.essential = essential
                # The second argument should really be a copy of sub with
                # only the essential attribute changed, but we know
                # that we can get away with not examining the attribute
                # at all - it's a boolean!
                notify(ObjectModifiedEvent(
                        sub, sub, ['essential'], user=subscribed_by))
            return sub
        # since no previous subscription existed, create and return a new one
        sub = SpecificationSubscription(specification=self,
            person=person, essential=essential)
        property_cache = get_property_cache(self)
        if 'subscription' in property_cache:
            from lp.registry.model.person import person_sort_key
            property_cache.subscriptions.append(sub)
            property_cache.subscriptions.sort(
                key=lambda sub: person_sort_key(sub.person))
        if self.information_type in PRIVATE_INFORMATION_TYPES:
            # Grant the subscriber access if they can't see the
            # specification.
            service = getUtility(IService, 'sharing')
            ignored, ignored, shared_specs = service.getVisibleArtifacts(
                person, specifications=[self], ignore_permissions=True)
            if not shared_specs:
                service.ensureAccessGrants(
                    [person], subscribed_by, specifications=[self])
        notify(ObjectCreatedEvent(sub, user=subscribed_by))
        return sub

    def unsubscribe(self, person, unsubscribed_by, ignore_permissions=False):
        """See ISpecification."""
        # see if a relevant subscription exists, and if so, delete it
        if person is None:
            person = unsubscribed_by
        for sub in self.subscriptions:
            if sub.person.id == person.id:
                if (not sub.canBeUnsubscribedByUser(unsubscribed_by) and
                    not ignore_permissions):
                    raise UserCannotUnsubscribePerson(
                        '%s does not have permission to unsubscribe %s.' % (
                            unsubscribed_by.displayname,
                            person.displayname))
                get_property_cache(self).subscriptions.remove(sub)
                SpecificationSubscription.delete(sub.id)
                artifacts_to_delete = getUtility(
                    IAccessArtifactSource).find([self])
                getUtility(IAccessArtifactGrantSource).revokeByArtifact(
                    artifacts_to_delete, [person])
                return

    def isSubscribed(self, person):
        """See lp.blueprints.interfaces.specification.ISpecification."""
        if person is None:
            return False

        return bool(self.subscription(person))

    # Template methods for BugLinkTargetMixin
    buglinkClass = SpecificationBug

    def createBugLink(self, bug):
        """See BugLinkTargetMixin."""
        return SpecificationBug(specification=self, bug=bug)

    # sprint linking
    def linkSprint(self, sprint, user):
        """See ISpecification."""
        from lp.blueprints.model.sprintspecification import (
            SprintSpecification)
        for sprint_link in self.sprint_links:
            # sprints have unique names
            if sprint_link.sprint.name == sprint.name:
                return sprint_link
        sprint_link = SprintSpecification(specification=self,
            sprint=sprint, registrant=user)
        if sprint.isDriver(user):
            sprint_link.acceptBy(user)
        return sprint_link

    def unlinkSprint(self, sprint):
        """See ISpecification."""
        from lp.blueprints.model.sprintspecification import (
            SprintSpecification)
        for sprint_link in self.sprint_links:
            # sprints have unique names
            if sprint_link.sprint.name == sprint.name:
                SprintSpecification.delete(sprint_link.id)
                return sprint_link

    # dependencies
    def createDependency(self, specification):
        """See ISpecification."""
        for deplink in self.spec_dependency_links:
            if deplink.dependency.id == specification.id:
                return deplink
        return SpecificationDependency(specification=self,
            dependency=specification)

    def removeDependency(self, specification):
        """See ISpecification."""
        # see if a relevant dependency link exists, and if so, delete it
        for deplink in self.spec_dependency_links:
            if deplink.dependency.id == specification.id:
                SpecificationDependency.delete(deplink.id)
                return deplink

    def all_deps(self, user=None):
        return list(Store.of(self).with_(
            SQL(recursive_dependent_query(user), params=(self.id,))).find(
            Specification,
            Specification.id != self.id,
            Specification.id.is_in(SQL('select id from dependencies')),
            ).order_by(Specification.name, Specification.id))

    def all_blocked(self, user=None):
        """See `ISpecification`."""
        return list(Store.of(self).with_(
            SQL(recursive_blocked_query(user), params=(self.id,))).find(
            Specification,
            Specification.id != self.id,
            Specification.id.is_in(SQL('select id from blocked')),
            ).order_by(Specification.name, Specification.id))

    # branches
    def getBranchLink(self, branch):
        return SpecificationBranch.selectOneBy(
            specificationID=self.id, branchID=branch.id)

    def linkBranch(self, branch, registrant):
        branch_link = self.getBranchLink(branch)
        if branch_link is not None:
            return branch_link
        branch_link = SpecificationBranch(
            specification=self, branch=branch, registrant=registrant)
        Store.of(self).flush()
        del get_property_cache(self).linked_branches
        notify(ObjectCreatedEvent(branch_link))
        return branch_link

    def unlinkBranch(self, branch, user):
        spec_branch = self.getBranchLink(branch)
        spec_branch.destroySelf()
        Store.of(self).flush()
        del get_property_cache(self).linked_branches

    def getLinkedBugTasks(self, user):
        """See `ISpecification`."""
        params = BugTaskSearchParams(user=user, linked_blueprints=self.id)
        tasks = getUtility(IBugTaskSet).search(params)
        if self.distroseries is not None:
            context = self.distroseries
        elif self.distribution is not None:
            context = self.distribution
        elif self.productseries is not None:
            context = self.productseries
        else:
            context = self.product
        return filter_bugtasks_by_context(context, tasks)

    def __repr__(self):
        return '<Specification %s %r for %r>' % (
            self.id, self.name, self.target.name)

    def getAllowedInformationTypes(self, who):
        """See `ISpecification`."""
        return self.target.getAllowedSpecificationInformationTypes()

    def transitionToInformationType(self, information_type, who):
        """See ISpecification."""
        # avoid circular imports.
        from lp.registry.model.accesspolicy import (
            reconcile_access_for_artifact,
            )
        if self.information_type == information_type:
            return False
        if information_type not in self.getAllowedInformationTypes(who):
            raise CannotChangeInformationType("Forbidden by project policy.")
        self.information_type = information_type
        reconcile_access_for_artifact(self, information_type, [self.target])
        if information_type in PRIVATE_INFORMATION_TYPES and self.subscribers:
            # Grant the subscribers access if they do not have a
            # policy grant.
            service = getUtility(IService, 'sharing')
            blind_subscribers = service.getPeopleWithoutAccess(
                self, self.subscribers)
            if len(blind_subscribers):
                service.ensureAccessGrants(
                    blind_subscribers, who, specifications=[self],
                    ignore_permissions=True)
        return True

    @cachedproperty
    def _known_viewers(self):
        """A set of known persons able to view the specifcation."""
        return set()

    def userCanView(self, user):
        """See `ISpecification`."""
        # Avoid circular imports.
        from lp.blueprints.model.specificationsearch import (
            get_specification_privacy_filter)
        if self.information_type in PUBLIC_INFORMATION_TYPES:
            return True
        if user is None:
            return False
        if user.id in self._known_viewers:
            return True

        if not Store.of(self).find(
            Specification, Specification.id == self.id,
            *get_specification_privacy_filter(user)).is_empty():
            self._known_viewers.add(user.id)
            return True
        return False


class HasSpecificationsMixin:
    """A mixin class that implements many of the common shortcut properties
    for other classes that have specifications.
    """

    def specifications(self, user, sort=None, quantity=None, filter=None,
                       need_people=True, need_branches=True,
                       need_workitems=False):
        """See IHasSpecifications."""
        # This should be implemented by the actual context class.
        raise NotImplementedError

    def _specification_sort(self, sort):
        """Return the storm sort order for 'specifications'.

        :param sort: As per HasSpecificationsMixin.specifications.
        """
        # sort by priority descending, by default
        if sort is None or sort == SpecificationSort.PRIORITY:
            return (
                Desc(Specification.priority), Specification.definition_status,
                Specification.name)
        elif sort == SpecificationSort.DATE:
            return (Desc(Specification.datecreated), Specification.id)

    @property
    def visible_specifications(self):
        """See IHasSpecifications."""
        user = getUtility(ILaunchBag).user
        return self.specifications(user, filter=[SpecificationFilter.ALL])

    def valid_specifications(self, **kwargs):
        """See IHasSpecifications."""
        user = getUtility(ILaunchBag).user
        return self.specifications(
            user, filter=[SpecificationFilter.VALID], **kwargs)

    @property
    def api_valid_specifications(self):
        return self.valid_specifications(
            need_people=True, need_branches=True, need_workitems=True)

    def specificationCount(self, user):
        """See IHasSpecifications."""
        return self.specifications(
            user, filter=[SpecificationFilter.ALL]).count()


class SpecificationSet(HasSpecificationsMixin):
    """The set of feature specifications."""

    implements(ISpecificationSet)

    def __init__(self):
        """See ISpecificationSet."""
        self.title = 'Specifications registered in Launchpad'
        self.displayname = 'All Specifications'

    def getStatusCountsForProductSeries(self, product_series):
        """See `ISpecificationSet`."""
        cur = cursor()
        condition = """
            (Specification.productseries = %s
                 OR Milestone.productseries = %s)
            """ % sqlvalues(product_series, product_series)
        query = """
            SELECT Specification.implementation_status, count(*)
            FROM Specification
                LEFT JOIN Milestone ON Specification.milestone = Milestone.id
            WHERE
                %s
            GROUP BY Specification.implementation_status
            """ % condition
        cur.execute(query)
        return cur.fetchall()

    def specifications(self, user, sort=None, quantity=None, filter=None,
                       need_people=True, need_branches=True,
                       need_workitems=False):
        from lp.blueprints.model.specificationsearch import (
            search_specifications)
        return search_specifications(
            self, [], user, sort, quantity, filter, need_people=need_people,
            need_branches=need_branches, need_workitems=need_workitems)

    def getByURL(self, url):
        """See ISpecificationSet."""
        return Specification.selectOneBy(specurl=url)

    def getByName(self, pillar, name):
        """See ISpecificationSet."""
        clauses = [Specification.name == name]
        if IDistribution.providedBy(pillar):
            clauses.append(Specification.distributionID == pillar.id)
        elif IProduct.providedBy(pillar):
            clauses.append(Specification.productID == pillar.id)
        return IStore(Specification).find(Specification, *clauses).one()

    @property
    def coming_sprints(self):
        """See ISpecificationSet."""
        from lp.blueprints.model.sprint import Sprint
        return Sprint.select("time_ends > 'NOW'", orderBy='time_starts',
            limit=5)

    def new(self, name, title, specurl, summary, definition_status,
        owner, approver=None, product=None, distribution=None, assignee=None,
        drafter=None, whiteboard=None, workitems_text=None,
        priority=SpecificationPriority.UNDEFINED, information_type=None):
        """See ISpecificationSet."""
        # Adapt the NewSpecificationDefinitionStatus item to a
        # SpecificationDefinitionStatus item.
        if information_type is None:
            information_type = InformationType.PUBLIC
        status_name = definition_status.name
        status_names = NewSpecificationDefinitionStatus.items.mapping.keys()
        if status_name not in status_names:
            raise AssertionError(
                "definition_status must an item found in "
                "NewSpecificationDefinitionStatus.")
        definition_status = SpecificationDefinitionStatus.items[status_name]
        spec = Specification(name=name, title=title, specurl=specurl,
            summary=summary, priority=priority,
            definition_status=definition_status, owner=owner,
            _approver=approver, product=product, distribution=distribution,
            _assignee=assignee, _drafter=drafter, whiteboard=whiteboard)
        spec.transitionToInformationType(information_type, None)
        return spec

    def getDependencyDict(self, specifications):
        """See `ISpecificationSet`."""
        specification_ids = [spec.id for spec in specifications]

        if len(specification_ids) == 0:
            return {}

        results = Store.of(specifications[0]).execute("""
            SELECT SpecificationDependency.specification,
                   SpecificationDependency.dependency
            FROM SpecificationDependency, Specification
            WHERE SpecificationDependency.specification IN %s
            AND SpecificationDependency.dependency = Specification.id
            ORDER BY Specification.priority DESC, Specification.name,
                     Specification.id
        """ % sqlvalues(specification_ids)).get_all()

        dependencies = {}
        for spec_id, dep_id in results:
            if spec_id not in dependencies:
                dependencies[spec_id] = []
            dependency = Specification.get(dep_id)
            dependencies[spec_id].append(dependency)

        return dependencies

    def get(self, spec_id):
        """See lp.blueprints.interfaces.specification.ISpecificationSet."""
        return Specification.get(spec_id)
