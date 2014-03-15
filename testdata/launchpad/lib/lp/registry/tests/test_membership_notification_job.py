# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests of `MembershipNotificationJob`."""

__metaclass__ = type

from testtools.content import Content
from testtools.content_type import UTF8_TEXT
import transaction
from zope.component import getUtility

from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.persontransferjob import (
    IMembershipNotificationJobSource,
    )
from lp.registry.interfaces.teammembership import (
    ITeamMembershipSet,
    TeamMembershipStatus,
    )
from lp.registry.model.persontransferjob import MembershipNotificationJob
from lp.services.features.testing import FeatureFixture
from lp.services.job.interfaces.job import JobStatus
from lp.services.job.tests import (
    block_on_job,
    pop_remote_notifications,
    )
from lp.testing import (
    login_person,
    person_logged_in,
    run_script,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    CeleryJobLayer,
    DatabaseFunctionalLayer,
    )
from lp.testing.sampledata import ADMIN_EMAIL


class MembershipNotificationJobTest(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(MembershipNotificationJobTest, self).setUp()
        self.person = self.factory.makePerson(name='murdock')
        self.team = self.factory.makeTeam(name='a-team')
        self.job_source = getUtility(IMembershipNotificationJobSource)

    def test_setstatus_admin(self):
        login_person(self.team.teamowner)
        self.team.addMember(self.person, self.team.teamowner)
        membership_set = getUtility(ITeamMembershipSet)
        tm = membership_set.getByPersonAndTeam(self.person, self.team)
        tm.setStatus(TeamMembershipStatus.ADMIN, self.team.teamowner)
        jobs = list(self.job_source.iterReady())
        job_info = [
            (job.__class__, job.member, job.team, job.status)
            for job in jobs]
        self.assertEqual(
            [(MembershipNotificationJob,
              self.person,
              self.team,
              JobStatus.WAITING),
            ],
            job_info)

    def test_setstatus_silent(self):
        person_set = getUtility(IPersonSet)
        admin = person_set.getByEmail(ADMIN_EMAIL)
        login_person(admin)
        self.team.addMember(self.person, self.team.teamowner)
        membership_set = getUtility(ITeamMembershipSet)
        tm = membership_set.getByPersonAndTeam(self.person, self.team)
        tm.setStatus(
            TeamMembershipStatus.ADMIN, admin, silent=True)
        self.assertEqual([], list(self.job_source.iterReady()))

    def test_repr(self):
        # A useful representation is available for MembershipNotificationJob
        # instances.
        with person_logged_in(self.team.teamowner):
            self.team.addMember(self.person, self.team.teamowner)
            membership = getUtility(ITeamMembershipSet).getByPersonAndTeam(
                self.person, self.team)
            membership.setStatus(
                TeamMembershipStatus.ADMIN, self.team.teamowner)
        [job] = self.job_source.iterReady()
        self.assertEqual(
            ("<MembershipNotificationJob about "
             "~murdock in ~a-team; status=Waiting>"),
            repr(job))

    def test_smoke_admining_team(self):
        # Smoke test, primarily for DB permissions needed by queries to work
        # with admining users and teams
        # Check the oopses in /var/tmp/lperr.test if the assertions fail.
        with person_logged_in(self.team.teamowner):
            # This implicitly creates a job, but it is not the job under test.
            admining_team = self.factory.makeTeam()
            self.team.addMember(
                admining_team, self.team.teamowner, force_team_add=True)
            membership = getUtility(ITeamMembershipSet).getByPersonAndTeam(
                admining_team, self.team)
            membership.setStatus(
                TeamMembershipStatus.ADMIN, self.team.teamowner)
        job = self.job_source.create(
            self.person, self.team, self.team.teamowner,
            TeamMembershipStatus.APPROVED, TeamMembershipStatus.ADMIN)
        job_repr = repr(job)
        transaction.commit()
        out, err, exit_code = run_script(
            "LP_DEBUG_SQL=1 cronscripts/process-job-source.py -vv %s" % (
                IMembershipNotificationJobSource.getName()))
        self.addDetail("stdout", Content(UTF8_TEXT, lambda: [out]))
        self.addDetail("stderr", Content(UTF8_TEXT, lambda: [err]))
        self.assertEqual(0, exit_code)
        self.assertTrue(job_repr in err, err)
        self.assertTrue("MembershipNotificationJob sent email" in err, err)


class TestViaCelery(TestCaseWithFactory):

    layer = CeleryJobLayer

    def test_smoke_admining_team(self):
        # Smoke test, primarily for DB permissions needed by queries to work
        # with admining users and teams
        # Check the oopses in /var/tmp/lperr.test if the assertions fail.
        self.useFixture(FeatureFixture({
                'jobs.celery.enabled_classes': 'MembershipNotificationJob'
        }))
        team = self.factory.makeTeam(name='a-team')
        with person_logged_in(team.teamowner):
            # This implicitly creates a job, but it is not the job under test.
            admining_team = self.factory.makeTeam()
            team.addMember(
                admining_team, team.teamowner, force_team_add=True)
            membership = getUtility(ITeamMembershipSet).getByPersonAndTeam(
                admining_team, team)
            membership.setStatus(
                TeamMembershipStatus.ADMIN, team.teamowner)
        person = self.factory.makePerson(name='murdock')
        with block_on_job(self):
            transaction.commit()
        pop_remote_notifications()
        job = getUtility(IMembershipNotificationJobSource).create(
            person, team, team.teamowner,
            TeamMembershipStatus.APPROVED, TeamMembershipStatus.ADMIN)
        with block_on_job(self):
            transaction.commit()
        self.assertEqual(JobStatus.COMPLETED, job.status)
        (notification,) = pop_remote_notifications()
        self.assertIn('murdock made admin by', notification['Subject'])
