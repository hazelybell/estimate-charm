# Copyright 2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for `PersonDeactivateJob`."""

__metaclass__ = type

from zope.component import getUtility
from zope.interface.verify import verifyObject

from lp.registry.interfaces.persontransferjob import (
    IPersonDeactivateJob,
    IPersonDeactivateJobSource,
    )
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.dbuser import dbuser
from lp.testing.layers import LaunchpadZopelessLayer


class TestPersonDeactivateJob(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def makeJob(self):
        return getUtility(IPersonDeactivateJobSource).create(
            self.factory.makePerson())

    def test_interface(self):
        verifyObject(IPersonDeactivateJob, self.makeJob())

    def test_deactivate(self):
        job = self.makeJob()
        team = self.factory.makeTeam(members=[job.person])
        owned_team = self.factory.makeTeam(owner=job.person)
        bug = self.factory.makeBug(owner=job.person)
        with person_logged_in(job.person):
            bug.default_bugtask.transitionToAssignee(job.person)
        spec = self.factory.makeSpecification(assignee=job.person)
        product = self.factory.makeProduct(
            owner=job.person, bug_supervisor=job.person)
        distro = self.factory.makeDistribution(driver=job.person)
        expected_name = job.person.name + '-deactivatedaccount'
        with dbuser('person-merge-job'):
            job.run()
        self.assertIs(None, bug.default_bugtask.assignee)
        self.assertIs(None, spec.assignee)
        self.assertNotIn(job.person, list(team.activemembers))
        self.assertNotEqual(job.person, owned_team.teamowner)
        self.assertNotEqual(job.person, product.owner)
        self.assertIs(None, product.bug_supervisor)
        self.assertIs(None, distro.driver)
        self.assertEqual(expected_name, job.person.name)
