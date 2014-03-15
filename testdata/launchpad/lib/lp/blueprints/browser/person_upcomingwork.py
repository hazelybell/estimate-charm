# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Person upcoming view showing workitems and bugs for a person."""

__meta__ = type
__all__ = [
    'PersonUpcomingWorkView',
    ]

from datetime import (
    datetime,
    timedelta,
    )
from operator import (
    attrgetter,
    itemgetter,
    )

from lp.app.browser.tales import format_link
from lp.blueprints.enums import SpecificationWorkItemStatus
from lp.services.propertycache import cachedproperty
from lp.services.webapp.publisher import LaunchpadView


class PersonUpcomingWorkView(LaunchpadView):
    """This view displays work items and bugtasks that are due within 60 days
    and are assigned to a person (or participants of of a team).
    """

    # We'll show bugs and work items targeted to milestones with a due date up
    # to DAYS from now.
    DAYS = 180

    def initialize(self):
        super(PersonUpcomingWorkView, self).initialize()
        self.workitem_counts = {}
        self.bugtask_counts = {}
        self.milestones_per_date = {}
        self.progress_per_date = {}
        for date, containers in self.work_item_containers:
            total_items = 0
            total_done = 0
            total_postponed = 0
            milestones = set()
            self.bugtask_counts[date] = 0
            self.workitem_counts[date] = 0
            for container in containers:
                total_items += len(container.items)
                total_done += len(container.done_items)
                total_postponed += len(container.postponed_items)
                if isinstance(container, AggregatedBugsContainer):
                    self.bugtask_counts[date] += len(container.items)
                else:
                    self.workitem_counts[date] += len(container.items)
                for item in container.items:
                    milestones.add(item.milestone)
            self.milestones_per_date[date] = sorted(
                milestones, key=attrgetter('displayname'))

            percent_done = 0
            if total_items > 0:
                done_or_postponed = total_done + total_postponed
                percent_done = 100.0 * done_or_postponed / total_items
            self.progress_per_date[date] = '{0:.0f}'.format(percent_done)

    @property
    def label(self):
        return self.page_title

    @property
    def page_title(self):
        return "Upcoming work for %s" % self.context.displayname

    @cachedproperty
    def work_item_containers(self):
        cutoff_date = datetime.today().date() + timedelta(days=self.DAYS)
        result = getWorkItemsDueBefore(self.context, cutoff_date, self.user)
        return sorted(result.items(), key=itemgetter(0))


class WorkItemContainer(object):
    """A container of work items, assigned to a person (or a team's
    participatns), whose milestone is due on a certain date.
    """

    def __init__(self):
        self._items = []

    @property
    def html_link(self):
        raise NotImplementedError("Must be implemented in subclasses")

    @property
    def priority_title(self):
        raise NotImplementedError("Must be implemented in subclasses")

    @property
    def target_link(self):
        raise NotImplementedError("Must be implemented in subclasses")

    @property
    def assignee_link(self):
        raise NotImplementedError("Must be implemented in subclasses")

    @property
    def items(self):
        raise NotImplementedError("Must be implemented in subclasses")

    @property
    def done_items(self):
        return [item for item in self._items if item.is_complete]

    @property
    def postponed_items(self):
        return [item for item in self._items
                if item.status == SpecificationWorkItemStatus.POSTPONED]

    @property
    def percent_done_or_postponed(self):
        """Returns % of work items to be worked on."""
        percent_done = 0
        if len(self._items) > 0:
            done_or_postponed = (len(self.done_items) +
                                 len(self.postponed_items))
            percent_done = 100.0 * done_or_postponed / len(self._items)
        return '{0:.0f}'.format(percent_done)

    @property
    def has_incomplete_work(self):
        """Return True if there are incomplete work items."""
        return (len(self.done_items) + len(self.postponed_items) <
                len(self._items))

    def append(self, item):
        self._items.append(item)


class SpecWorkItemContainer(WorkItemContainer):
    """A container of SpecificationWorkItems wrapped with GenericWorkItem."""

    def __init__(self, spec):
        super(SpecWorkItemContainer, self).__init__()
        self.spec = spec
        self.priority = spec.priority
        self.target = spec.target
        self.assignee = spec.assignee

    @property
    def html_link(self):
        return format_link(self.spec)

    @property
    def priority_title(self):
        return self.priority.title

    @property
    def target_link(self):
        return format_link(self.target)

    @property
    def assignee_link(self):
        if self.assignee is None:
            return 'Nobody'
        return format_link(self.assignee)

    @property
    def items(self):
        # Sort the work items by status only because they all have the same
        # priority.
        def sort_key(item):
            status_order = {
                SpecificationWorkItemStatus.POSTPONED: 5,
                SpecificationWorkItemStatus.DONE: 4,
                SpecificationWorkItemStatus.INPROGRESS: 3,
                SpecificationWorkItemStatus.TODO: 2,
                SpecificationWorkItemStatus.BLOCKED: 1,
                }
            return status_order[item.status]
        return sorted(self._items, key=sort_key)


class AggregatedBugsContainer(WorkItemContainer):
    """A container of BugTasks wrapped with GenericWorkItem."""

    @property
    def html_link(self):
        return 'Bugs targeted to a milestone on this date'

    @property
    def assignee_link(self):
        return 'N/A'

    @property
    def target_link(self):
        return 'N/A'

    @property
    def priority_title(self):
        return 'N/A'

    @property
    def items(self):
        def sort_key(item):
            return (item.status.value, item.priority.value)
        # Sort by (status, priority) in reverse order because the biggest the
        # status/priority the more interesting it is to us.
        return sorted(self._items, key=sort_key, reverse=True)


class GenericWorkItem:
    """A generic piece of work; either a BugTask or a SpecificationWorkItem.

    This class wraps a BugTask or a SpecificationWorkItem to provide a
    common API so that the template doesn't have to worry about what kind of
    work item it's dealing with.
    """

    def __init__(self, assignee, status, priority, target, title,
                 bugtask=None, work_item=None):
        self.assignee = assignee
        self.status = status
        self.priority = priority
        self.target = target
        self.title = title
        self._bugtask = bugtask
        self._work_item = work_item

    @classmethod
    def from_bugtask(cls, bugtask):
        return cls(
            bugtask.assignee, bugtask.status, bugtask.importance,
            bugtask.target, bugtask.bug.description, bugtask=bugtask)

    @classmethod
    def from_workitem(cls, work_item):
        assignee = work_item.assignee
        if assignee is None:
            assignee = work_item.specification.assignee
        return cls(
            assignee, work_item.status, work_item.specification.priority,
            work_item.specification.target, work_item.title,
            work_item=work_item)

    @property
    def milestone(self):
        milestone = self.actual_workitem.milestone
        if milestone is None:
            assert self._work_item is not None, (
                "BugTaks without a milestone must not be here.")
            milestone = self._work_item.specification.milestone
        return milestone

    @property
    def actual_workitem(self):
        """Return the actual work item that we are wrapping.

        This may be either an IBugTask or an ISpecificationWorkItem.
        """
        if self._work_item is not None:
            return self._work_item
        else:
            return self._bugtask

    @property
    def is_complete(self):
        return self.actual_workitem.is_complete


def getWorkItemsDueBefore(person, cutoff_date, user):
    """Return a dict mapping dates to lists of WorkItemContainers.

    This is a grouping, by milestone due date, of all work items
    (SpecificationWorkItems/BugTasks) assigned to this person (or any of its
    participants, in case it's a team).

    Only work items whose milestone have a due date between today and the
    given cut-off date are included in the results.
    """
    workitems = person.getAssignedSpecificationWorkItemsDueBefore(cutoff_date,
                                                                  user)
    # For every specification that has work items in the list above, create
    # one SpecWorkItemContainer holding the work items from that spec that are
    # targeted to the same milestone and assigned to this person (or its
    # participants, in case it's a team).
    containers_by_date = {}
    containers_by_spec = {}
    for workitem in workitems:
        spec = workitem.specification
        milestone = workitem.milestone
        if milestone is None:
            milestone = spec.milestone
        if milestone.dateexpected not in containers_by_date:
            containers_by_date[milestone.dateexpected] = []
        container = containers_by_spec.setdefault(milestone, {}).get(spec)
        if container is None:
            container = SpecWorkItemContainer(spec)
            containers_by_spec[milestone][spec] = container
            containers_by_date[milestone.dateexpected].append(container)
        container.append(GenericWorkItem.from_workitem(workitem))

    # Sort our containers by priority.
    for date in containers_by_date:
        containers_by_date[date].sort(
            key=attrgetter('priority'), reverse=True)

    bugtasks = person.getAssignedBugTasksDueBefore(cutoff_date, user)
    bug_containers_by_date = {}
    # For every milestone due date, create an AggregatedBugsContainer with all
    # the bugtasks targeted to a milestone on that date and assigned to
    # this person (or its participants, in case it's a team).
    for task in bugtasks:
        dateexpected = task.milestone.dateexpected
        container = bug_containers_by_date.get(dateexpected)
        if container is None:
            container = AggregatedBugsContainer()
            bug_containers_by_date[dateexpected] = container
            # Also append our new container to the dictionary we're going
            # to return.
            if dateexpected not in containers_by_date:
                containers_by_date[dateexpected] = []
            containers_by_date[dateexpected].append(container)
        container.append(GenericWorkItem.from_bugtask(task))

    return containers_by_date
