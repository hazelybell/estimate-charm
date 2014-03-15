# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit test for sprints."""

__metaclass__ = type


import datetime

from pytz import utc
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.blueprints.enums import (
    NewSpecificationDefinitionStatus,
    SpecificationDefinitionStatus,
    SpecificationFilter,
    SpecificationPriority,
    SpecificationSort,
    )
from lp.registry.interfaces.accesspolicy import IAccessPolicySource
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


def list_result(sprint, filter=None, user=None):
    result = sprint.specifications(user, SpecificationSort.DATE, filter=filter)
    return list(result)


class TestSpecifications(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestSpecifications, self).setUp()
        self.date_decided = datetime.datetime.now(utc)

    def makeSpec(self, sprint=None, date_decided=0, date_created=0,
                 proposed=False, declined=False, title=None,
                 status=NewSpecificationDefinitionStatus.NEW,
                 name=None, priority=None, information_type=None):
        if sprint is None:
            sprint = self.factory.makeSprint()
        blueprint = self.factory.makeSpecification(
            title=title, status=status, name=name, priority=priority,
            information_type=information_type)
        link = blueprint.linkSprint(sprint, blueprint.owner)
        naked_link = removeSecurityProxy(link)
        if declined:
            link.declineBy(sprint.owner)
        elif not proposed:
            link.acceptBy(sprint.owner)
        if not proposed:
            date_decided = self.date_decided + datetime.timedelta(date_decided)
            naked_link.date_decided = date_decided
        date_created = self.date_decided + datetime.timedelta(date_created)
        naked_link.date_created = date_created
        return blueprint

    def test_specifications_quantity(self):
        # Ensure the quantity controls the maximum number of entries.
        sprint = self.factory.makeSprint()
        for count in range(10):
            self.makeSpec(sprint)
        self.assertEqual(10, sprint.specifications(None).count())
        result = sprint.specifications(None, quantity=None).count()
        self.assertEqual(10, result)
        self.assertEqual(8, sprint.specifications(None, quantity=8).count())
        self.assertEqual(10, sprint.specifications(None, quantity=11).count())

    def test_specifications_date_sort_accepted_decided(self):
        # If only accepted proposals are requested, date-sorting uses
        # date_decided.  Otherwise, it uses date_created.
        sprint = self.factory.makeSprint()
        blueprint1 = self.makeSpec(sprint, date_decided=0, date_created=0)
        blueprint2 = self.makeSpec(sprint, date_decided=-1, date_created=1)
        blueprint3 = self.makeSpec(sprint, date_decided=1, date_created=2)
        result = list_result(sprint)
        self.assertEqual([blueprint3, blueprint1, blueprint2], result)
        # SpecificationFilter.ALL forces sorting by date_created, since not
        # all entries will have date_decided.
        result = list_result(sprint, [SpecificationFilter.ALL])
        self.assertEqual([blueprint3, blueprint2, blueprint1], result)

    def test_accepted_date_sort_creation(self):
        # If date_decided does not vary, sort on date_created.
        sprint = self.factory.makeSprint()
        blueprint1 = self.makeSpec(sprint, date_created=0)
        blueprint2 = self.makeSpec(sprint, date_created=-1)
        blueprint3 = self.makeSpec(sprint, date_created=1)
        result = list_result(sprint)
        self.assertEqual([blueprint3, blueprint1, blueprint2], result)
        result = list_result(sprint, [SpecificationFilter.ALL])
        self.assertEqual([blueprint3, blueprint1, blueprint2], result)

    def test_proposed_date_sort_creation(self):
        # date-sorting by PROPOSED uses date_created.
        sprint = self.factory.makeSprint()
        blueprint1 = self.makeSpec(sprint, date_created=0, proposed=True)
        blueprint2 = self.makeSpec(sprint, date_created=-1, proposed=True)
        blueprint3 = self.makeSpec(sprint, date_created=1, proposed=True)
        result = list_result(sprint, [SpecificationFilter.PROPOSED])
        self.assertEqual([blueprint3, blueprint1, blueprint2], result)

    def test_accepted_date_sort_id(self):
        # date-sorting when no date varies uses object id.
        sprint = self.factory.makeSprint()
        blueprint1 = self.makeSpec(sprint)
        blueprint2 = self.makeSpec(sprint)
        blueprint3 = self.makeSpec(sprint)
        result = list_result(sprint)
        self.assertEqual([blueprint1, blueprint2, blueprint3], result)
        # date-sorting ALL when no date varies uses object id.
        result = list_result(sprint, [SpecificationFilter.ALL])
        self.assertEqual([blueprint1, blueprint2, blueprint3], result)

    def test_proposed_date_sort_id(self):
        # date-sorting PROPOSED when no date varies uses object id.
        sprint = self.factory.makeSprint()
        blueprint1 = self.makeSpec(sprint, proposed=True)
        blueprint2 = self.makeSpec(sprint, proposed=True)
        blueprint3 = self.makeSpec(sprint, proposed=True)
        result = list_result(sprint, [SpecificationFilter.PROPOSED])
        self.assertEqual([blueprint1, blueprint2, blueprint3], result)

    def test_priority_sort(self):
        # Sorting by priority works and is the default.
        # When priority is supplied, status is ignored.
        blueprint1 = self.makeSpec(priority=SpecificationPriority.UNDEFINED,
                                   status=SpecificationDefinitionStatus.NEW)
        sprint = blueprint1.sprints[0]
        blueprint2 = self.makeSpec(
            sprint, priority=SpecificationPriority.NOTFORUS,
            status=SpecificationDefinitionStatus.APPROVED)
        blueprint3 = self.makeSpec(
            sprint, priority=SpecificationPriority.LOW,
            status=SpecificationDefinitionStatus.OBSOLETE)
        result = sprint.specifications(None)
        self.assertEqual([blueprint3, blueprint1, blueprint2], list(result))
        result = sprint.specifications(None, sort=SpecificationSort.PRIORITY)
        self.assertEqual([blueprint3, blueprint1, blueprint2], list(result))

    def test_priority_sort_fallback_status(self):
        # Sorting by priority falls back to defintion_status.
        # When status is supplied, name is ignored.
        blueprint1 = self.makeSpec(
            status=SpecificationDefinitionStatus.OBSOLETE, name='a')
        sprint = blueprint1.sprints[0]
        blueprint2 = self.makeSpec(
            sprint, status=SpecificationDefinitionStatus.APPROVED, name='c')
        blueprint3 = self.makeSpec(
            sprint, status=SpecificationDefinitionStatus.NEW, name='b')
        result = sprint.specifications(None)
        self.assertEqual([blueprint2, blueprint3, blueprint1], list(result))
        result = sprint.specifications(None, sort=SpecificationSort.PRIORITY)
        self.assertEqual([blueprint2, blueprint3, blueprint1], list(result))

    def test_priority_sort_fallback_name(self):
        # Sorting by priority falls back to name
        blueprint1 = self.makeSpec(name='b')
        sprint = blueprint1.sprints[0]
        blueprint2 = self.makeSpec(sprint, name='c')
        blueprint3 = self.makeSpec(sprint, name='a')
        result = sprint.specifications(None)
        self.assertEqual([blueprint3, blueprint1, blueprint2], list(result))
        result = sprint.specifications(None, sort=SpecificationSort.PRIORITY)
        self.assertEqual([blueprint3, blueprint1, blueprint2], list(result))

    def test_text_search(self):
        # Text searches work.
        blueprint1 = self.makeSpec(title='abc')
        sprint = blueprint1.sprints[0]
        blueprint2 = self.makeSpec(sprint, title='def')
        result = list_result(sprint, [u'abc'])
        self.assertEqual([blueprint1], result)
        result = list_result(sprint, [u'def'])
        self.assertEqual([blueprint2], result)

    def test_declined(self):
        # Specifying SpecificationFilter.DECLINED shows only declined specs.
        blueprint1 = self.makeSpec()
        sprint = blueprint1.sprints[0]
        blueprint2 = self.makeSpec(sprint, declined=True)
        result = list_result(sprint, [SpecificationFilter.DECLINED])
        self.assertEqual([blueprint2], result)

    def test_proprietary_not_listed(self):
        # Proprietary blueprints are not listed for random users
        blueprint1 = self.makeSpec(
            information_type=InformationType.PROPRIETARY)
        self.assertEqual([], list_result(blueprint1.sprints[0]))

    def test_proprietary_listed_for_artifact_grant(self):
        # Proprietary blueprints are listed for users with an artifact grant.
        blueprint1 = self.makeSpec(
            information_type=InformationType.PROPRIETARY)
        grant = self.factory.makeAccessArtifactGrant(
            concrete_artifact=blueprint1)
        self.assertEqual(
            [blueprint1],
            list_result(blueprint1.sprints[0], user=grant.grantee))

    def test_proprietary_listed_for_policy_grant(self):
        # Proprietary blueprints are listed for users with a policy grant.
        blueprint1 = self.makeSpec(
            information_type=InformationType.PROPRIETARY)
        policy_source = getUtility(IAccessPolicySource)
        (policy,) = policy_source.find(
            [(blueprint1.product, InformationType.PROPRIETARY)])
        grant = self.factory.makeAccessPolicyGrant(policy)
        self.assertEqual(
            [blueprint1],
            list_result(blueprint1.sprints[0], user=grant.grantee))


class TestSprintAttendancesSort(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_attendances(self):
        #Test the sorting of attendances to be by displayname rather than name
        sprint = self.factory.makeSprint()
        bob = self.factory.makePerson(name='zbob', displayname='Bob')
        ced = self.factory.makePerson(name='xed', displayname='ced')
        dave = self.factory.makePerson(name='wdave', displayname='Dave')
        sprint.attend(
            bob, sprint.time_starts, sprint.time_ends, True)
        sprint.attend(
            ced, sprint.time_starts, sprint.time_ends, True)
        sprint.attend(
            dave, sprint.time_starts, sprint.time_ends, True)
        attendances = [bob.displayname, ced.displayname, dave.displayname]
        people = [attendee.attendee.displayname for attendee in
                  sprint.attendances]
        self.assertEqual(attendances, people)
