# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'PersonSpecsMenu',
    'PersonSpecWorkloadTableView',
    'PersonSpecWorkloadView',
    ]

from lp.registry.interfaces.person import IPerson
from lp.services.propertycache import cachedproperty
from lp.services.webapp import (
    Link,
    NavigationMenu,
    )
from lp.services.webapp.batching import BatchNavigator
from lp.services.webapp.publisher import LaunchpadView


class PersonSpecsMenu(NavigationMenu):

    usedfor = IPerson
    facet = 'specifications'
    links = ['assignee', 'drafter', 'approver',
             'subscriber', 'registrant', 'workload']

    def registrant(self):
        text = 'Registrant'
        summary = 'List specs registered by %s' % self.context.displayname
        return Link('+specs?role=registrant', text, summary, icon='blueprint')

    def approver(self):
        text = 'Approver'
        summary = 'List specs with %s is supposed to approve' % (
            self.context.displayname)
        return Link('+specs?role=approver', text, summary, icon='blueprint')

    def assignee(self):
        text = 'Assignee'
        summary = 'List specs for which %s is the assignee' % (
            self.context.displayname)
        return Link('+specs?role=assignee', text, summary, icon='blueprint')

    def drafter(self):
        text = 'Drafter'
        summary = 'List specs drafted by %s' % self.context.displayname
        return Link('+specs?role=drafter', text, summary, icon='blueprint')

    def subscriber(self):
        text = 'Subscriber'
        return Link('+specs?role=subscriber', text, icon='blueprint')

    def workload(self):
        text = 'Workload'
        summary = 'Show all specification work assigned'
        return Link('+specworkload', text, summary, icon='info')


class PersonSpecWorkloadView(LaunchpadView):
    """View to render the specification workload for a person or team.

    It shows the set of specifications with which this person has a role.  If
    the person is a team, then all members of the team are presented using
    batching with their individual specifications.
    """

    label = 'Blueprint workload'

    @cachedproperty
    def members(self):
        """Return a batch navigator for all members.

        This batch does not test for whether the person has specifications or
        not.
        """
        members = self.context.allmembers
        batch_nav = BatchNavigator(members, self.request, size=20)
        return batch_nav

    def specifications(self):
        return self.context.specifications(self.user)


class PersonSpecWorkloadTableView(LaunchpadView):
    """View to render the specification workload table for a person.

    It shows the set of specifications with which this person has a role
    in a single table.
    """

    page_title = 'Blueprint workload'

    class PersonSpec:
        """One record from the workload list."""

        def __init__(self, spec, person):
            self.spec = spec
            self.assignee = spec.assignee == person
            self.drafter = spec.drafter == person
            self.approver = spec.approver == person

    @cachedproperty
    def workload(self):
        """This code is copied in large part from browser/sprint.py. It may
        be worthwhile refactoring this to use a common code base.

        Return a structure that lists the specs for which this person is the
        approver, the assignee or the drafter.
        """
        return [PersonSpecWorkloadTableView.PersonSpec(spec, self.context)
                for spec in self.context.specifications(self.user)]
