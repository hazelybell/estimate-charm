# Copyright 2011-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'PersonSubscriptions',
    ]

from storm.expr import SQL
from storm.store import Store
from zope.component import getUtility
from zope.interface import implements
from zope.proxy import sameProxiedObjects

from lp.bugs.interfaces.personsubscriptioninfo import (
    IAbstractSubscriptionInfoCollection,
    IPersonSubscriptions,
    IRealSubscriptionInfo,
    IRealSubscriptionInfoCollection,
    IVirtualSubscriptionInfo,
    IVirtualSubscriptionInfoCollection,
    )
from lp.bugs.model.bug import (
    Bug,
    BugMute,
    generate_subscription_with,
    )
from lp.bugs.model.bugsubscription import BugSubscription
from lp.registry.interfaces.person import IPersonSet
from lp.registry.model.distribution import Distribution
from lp.registry.model.person import Person
from lp.registry.model.product import Product
from lp.services.database.bulk import load_related


class RealSubscriptionInfo:
    """See `IRealSubscriptionInfo`"""

    implements(IRealSubscriptionInfo)

    def __init__(self, principal, bug, subscription):
        self.principal = principal
        self.bug = bug
        self.subscription = subscription
        self.principal_is_reporter = False
        self.bug_supervisor_tasks = []


class VirtualSubscriptionInfo:
    """See `IVirtualSubscriptionInfo`"""

    implements(IVirtualSubscriptionInfo)

    def __init__(self, principal, bug, pillar):
        self.principal = principal
        self.bug = bug
        self.pillar = pillar
        self.tasks = []


class AbstractSubscriptionInfoCollection:
    """See `IAbstractSubscriptionInfoCollection`"""

    implements(IAbstractSubscriptionInfoCollection)

    def __init__(self, person, administrated_team_ids):
        self.person = person
        self.administrated_team_ids = administrated_team_ids
        self.personal = []
        self.as_team_member = []
        self.as_team_admin = []
        self.count = 0

    def add(self, principal, bug, *args):
        if sameProxiedObjects(principal, self.person):
            collection = self.personal
        else:
            assert principal.is_team, (principal, self.person)
            if principal.id in self.administrated_team_ids:
                collection = self.as_team_admin
            else:
                collection = self.as_team_member
        self._add_item_to_collection(
            collection, principal, bug, *args)

    def _add_item_to_collection(self, *args):
        raise NotImplementedError('Programmer error: use a subclass')


class VirtualSubscriptionInfoCollection(AbstractSubscriptionInfoCollection):
    """See `IVirtualSubscriptionInfoCollection`"""

    implements(IVirtualSubscriptionInfoCollection)

    def __init__(self, person, administrated_team_ids):
        super(VirtualSubscriptionInfoCollection, self).__init__(
            person, administrated_team_ids)
        self._principal_pillar_to_info = {}

    def _add_item_to_collection(self, collection, principal, bug, pillar,
                                task):
        key = (principal, pillar)
        info = self._principal_pillar_to_info.get(key)
        if info is None:
            info = VirtualSubscriptionInfo(principal, bug, pillar)
            collection.append(info)
            self.count += 1
        info.tasks.append(task)


class RealSubscriptionInfoCollection(
    AbstractSubscriptionInfoCollection):
    """Core functionality for Duplicate and Direct"""

    implements(IRealSubscriptionInfoCollection)

    def __init__(self, person, administrated_team_ids):
        super(RealSubscriptionInfoCollection, self).__init__(
            person, administrated_team_ids)
        self._principal_bug_to_infos = {}

    def _add_item_to_collection(self, collection, principal, bug,
                                subscription):
        info = RealSubscriptionInfo(principal, bug, subscription)
        key = (principal, bug)
        infos = self._principal_bug_to_infos.get(key)
        if infos is None:
            infos = self._principal_bug_to_infos[key] = []
        infos.append(info)
        collection.append(info)
        self.count += 1

    def annotateReporter(self, bug, principal):
        key = (principal, bug)
        infos = self._principal_bug_to_infos.get(key)
        if infos is not None:
            for info in infos:
                info.principal_is_reporter = True

    def annotateBugTaskResponsibilities(self, bugtask, pillar, bug_supervisor):
        if bug_supervisor is not None:
            key = (bug_supervisor, bugtask.bug)
            infos = self._principal_bug_to_infos.get(key)
            if infos is not None:
                value = {'task': bugtask, 'pillar': pillar}
                for info in infos:
                    info.bug_supervisor_tasks.append(value)


class PersonSubscriptions(object):
    """See `IPersonSubscriptions`."""

    implements(IPersonSubscriptions)

    def __init__(self, person, bug):
        self.loadSubscriptionsFor(person, bug)

    def reload(self):
        """See `IPersonSubscriptions`."""
        self.loadSubscriptionsFor(self.person, self.bug)

    def _getDirectAndDuplicateSubscriptions(self, person, bug):
        # Fetch all information for direct and duplicate
        # subscriptions (including indirect through team
        # membership) in a single query.
        with_statement = generate_subscription_with(bug, person)
        info = Store.of(person).with_(with_statement).find(
            (BugSubscription, Bug, Person),
            BugSubscription.id.is_in(
                SQL('SELECT bugsubscriptions.id FROM bugsubscriptions')),
            Person.id == BugSubscription.person_id,
            Bug.id == BugSubscription.bug_id)

        direct = RealSubscriptionInfoCollection(
            self.person, self.administrated_team_ids)
        duplicates = RealSubscriptionInfoCollection(
            self.person, self.administrated_team_ids)
        bugs = set()
        for subscription, subscribed_bug, subscriber in info:
            bugs.add(subscribed_bug)
            if subscribed_bug.id != bug.id:
                # This is a subscription through a duplicate.
                collection = duplicates
            else:
                # This is a direct subscription.
                collection = direct
            collection.add(
                subscriber, subscribed_bug, subscription)
        # Preload bug owners, then all pillars.
        list(getUtility(IPersonSet).getPrecachedPersonsFromIDs(
            [bug.ownerID for bug in bugs]))
        all_tasks = [task for task in bug.bugtasks for bug in bugs] 
        load_related(Product, all_tasks, ['productID'])
        load_related(Distribution, all_tasks, ['distributionID'])
        for bug in bugs:
            # indicate the reporter and bug_supervisor
            duplicates.annotateReporter(bug, bug.owner)
            direct.annotateReporter(bug, bug.owner)
        for task in all_tasks:
            # Get bug_supervisor.
            duplicates.annotateBugTaskResponsibilities(
                task, task.pillar, task.pillar.bug_supervisor)
            direct.annotateBugTaskResponsibilities(
                task, task.pillar, task.pillar.bug_supervisor)
        return (direct, duplicates)

    def _isMuted(self, person, bug):
        return not Store.of(person).find(
            BugMute, bug=bug, person=person).is_empty()

    def loadSubscriptionsFor(self, person, bug):
        self.person = person
        self.administrated_team_ids = [
            team.id for team in person.getAdministratedTeams()]
        self.bug = bug

        # First get direct and duplicate real subscriptions.
        direct, from_duplicate = (
            self._getDirectAndDuplicateSubscriptions(person, bug))

        # Then get the 'muted' flag.
        self.muted = self._isMuted(person, bug)

        # Then get owner and assignee virtual subscriptions.
        as_owner = VirtualSubscriptionInfoCollection(
            self.person, self.administrated_team_ids)
        as_assignee = VirtualSubscriptionInfoCollection(
            self.person, self.administrated_team_ids)
        for bugtask in bug.bugtasks:
            owner = bugtask.pillar.owner
            if person.inTeam(owner) and bugtask.pillar.bug_supervisor is None:
                as_owner.add(owner, bug, bugtask.pillar, bugtask)
            assignee = bugtask.assignee
            if person.inTeam(assignee):
                as_assignee.add(assignee, bug, bugtask.pillar, bugtask)
        self.count = 0
        for name, collection in (
            ('direct', direct), ('from_duplicate', from_duplicate),
            ('as_owner', as_owner), ('as_assignee', as_assignee)):
            self.count += collection.count
            setattr(self, name, collection)

    def getDataForClient(self):
        reference_map = {}
        dest = {}

        def get_id(obj):
            "Get an id for the object so it can be shared."
            # We could leverage .id for most objects, but not pillars.
            identifier = reference_map.get(obj)
            if identifier is None:
                identifier = 'subscription-cache-reference-%d' % (
                    len(reference_map),)
                reference_map[obj] = identifier
                dest[identifier] = obj
            return identifier

        def virtual_sub_data(info):
            return {
                'principal': get_id(info.principal),
                'bug': get_id(info.bug),
                'pillar': get_id(info.pillar),
                # We won't add bugtasks yet unless we need them.
                }

        def real_sub_data(info):
            return {
                'principal': get_id(info.principal),
                'bug': get_id(info.bug),
                'subscription': get_id(info.subscription),
                'principal_is_reporter': info.principal_is_reporter,
                # We won't add bugtasks yet unless we need them.
                'bug_supervisor_pillars': sorted(set(
                    get_id(d['pillar']) for d
                    in info.bug_supervisor_tasks)),
                }
        direct = {}
        from_duplicate = {}
        as_owner = {}  # This is an owner of a pillar with no bug supervisor.
        as_assignee = {}
        subscription_data = {
            'direct': direct,
            'from_duplicate': from_duplicate,
            'as_owner': as_owner,
            'as_assignee': as_assignee,
            'count': self.count,
            'muted': self.muted,
            'bug_id': self.bug.id,
            }
        for category, collection in ((as_owner, self.as_owner),
                                 (as_assignee, self.as_assignee)):
            for name, inner in (
                ('personal', collection.personal),
                ('as_team_admin', collection.as_team_admin),
                ('as_team_member', collection.as_team_member)):
                category[name] = [virtual_sub_data(info) for info in inner]
            category['count'] = collection.count
        for category, collection in ((direct, self.direct),
                                     (from_duplicate, self.from_duplicate)):
            for name, inner in (
                ('personal', collection.personal),
                ('as_team_admin', collection.as_team_admin),
                ('as_team_member', collection.as_team_member)):
                category[name] = [real_sub_data(info) for info in inner]
            category['count'] = collection.count
        return subscription_data, dest
