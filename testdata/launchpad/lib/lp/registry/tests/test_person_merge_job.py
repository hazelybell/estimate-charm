# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests of `PersonMergeJob`."""

__metaclass__ = type

from testtools.content import Content
from testtools.content_type import UTF8_TEXT
import transaction
from zope.component import getUtility
from zope.interface.verify import verifyObject
from zope.security.proxy import removeSecurityProxy

from lp.registry.interfaces.persontransferjob import (
    IPersonMergeJob,
    IPersonMergeJobSource,
    )
from lp.services.database.interfaces import IStore
from lp.services.features.testing import FeatureFixture
from lp.services.identity.interfaces.emailaddress import EmailAddressStatus
from lp.services.job.interfaces.job import JobStatus
from lp.services.job.model.job import Job
from lp.services.job.tests import block_on_job
from lp.services.log.logger import BufferLogger
from lp.services.mail.sendmail import format_address_for_person
from lp.services.scripts import log
from lp.testing import (
    person_logged_in,
    run_script,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    CeleryJobLayer,
    DatabaseFunctionalLayer,
    )


def create_job(factory):
    """Create a PersonMergeJob for testing purposes.

    :param factory: A LaunchpadObjectFactory.
    """
    from_person = factory.makePerson(name='void')
    to_person = factory.makePerson(name='gestalt')
    requester = factory.makePerson(name='requester')
    return getUtility(IPersonMergeJobSource).create(
        from_person=from_person, to_person=to_person, requester=requester)


def transfer_email(job):
    """Reassign email address using the people specified in the job.

    IPersonSet.merge() does not (yet) promise to do this.
    """
    from_email = removeSecurityProxy(job.from_person.preferredemail)
    from_email.personID = job.to_person.id
    from_email.accountID = job.to_person.accountID
    from_email.status = EmailAddressStatus.NEW
    IStore(from_email).flush()


class TestPersonMergeJob(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestPersonMergeJob, self).setUp()
        self.job_source = getUtility(IPersonMergeJobSource)
        self.job = create_job(self.factory)
        self.from_person = self.job.from_person
        self.to_person = self.job.to_person
        self.requester = self.job.requester

    def test_interface(self):
        # PersonMergeJob implements IPersonMergeJob.
        verifyObject(IPersonMergeJob, self.job)

    def test_properties(self):
        # PersonMergeJobs have a few interesting properties.
        self.assertEqual(self.from_person, self.job.from_person)
        self.assertEqual(self.from_person, self.job.minor_person)
        self.assertEqual(self.to_person, self.job.to_person)
        self.assertEqual(self.to_person, self.job.major_person)
        self.assertEqual({'delete': False}, self.job.metadata)

    def test_getErrorRecipients(self):
        # The requester is the recipient.
        email_id = format_address_for_person(self.requester)
        self.assertEqual([email_id], self.job.getErrorRecipients())

    def test_enqueue(self):
        # Newly created jobs are enqueued.
        self.assertEqual([self.job], list(self.job_source.iterReady()))

    def test_create_job_already_exists(self):
        # create returns None if either of the persons are already
        # in a pending merge job.
        duplicate_job = self.job_source.create(
            from_person=self.from_person, to_person=self.to_person,
            requester=self.requester)
        inverted_job = self.job_source.create(
            from_person=self.to_person, to_person=self.from_person,
            requester=self.requester)
        self.assertEqual(None, duplicate_job)
        self.assertEqual(None, inverted_job)

    def transfer_email(self):
        # Reassign from_person's email address over to to_person because
        # IPersonSet.merge() does not (yet) promise to do that.
        transfer_email(self.job)

    def test_run(self):
        # When run it merges from_person into to_person.
        self.transfer_email()
        logger = BufferLogger()
        with log.use(logger):
            self.job.run()

        self.assertEqual(self.to_person, self.from_person.merged)
        self.assertEqual(
            ["DEBUG PersonMergeJob is about to merge ~void into ~gestalt",
             "DEBUG PersonMergeJob has merged ~void into ~gestalt"],
            logger.getLogBuffer().splitlines())
        self.assertEqual(self.to_person, self.from_person.merged)

    def test_smoke(self):
        # Smoke test, primarily for DB permissions need for users and teams.
        # Check the oopses in /var/tmp/lperr.test if the person.merged
        # assertion fails.
        self.transfer_email()
        to_team = self.factory.makeTeam(name='legion')
        from_team = self.factory.makeTeam(name='null')
        with person_logged_in(from_team.teamowner):
            from_team.teamowner.leave(from_team)
        self.job_source.create(
            from_person=from_team, to_person=to_team,
            reviewer=from_team.teamowner, requester=self.factory.makePerson())
        transaction.commit()

        out, err, exit_code = run_script(
            "LP_DEBUG_SQL=1 cronscripts/process-job-source.py -vv %s" % (
                IPersonMergeJobSource.getName()))

        self.addDetail("stdout", Content(UTF8_TEXT, lambda: out))
        self.addDetail("stderr", Content(UTF8_TEXT, lambda: err))

        self.assertEqual(0, exit_code)
        IStore(self.from_person).invalidate()
        self.assertEqual(self.to_person, self.from_person.merged)
        self.assertEqual(to_team, from_team.merged)

    def test_repr(self):
        # A useful representation is available for PersonMergeJob instances.
        self.assertEqual(
            "<PersonMergeJob to merge ~void into ~gestalt; status=Waiting>",
            repr(self.job))

    def test_getOperationDescription(self):
        self.assertEqual('merging ~void into ~gestalt',
                         self.job.getOperationDescription())

    def find(self, **kwargs):
        return list(self.job_source.find(**kwargs))

    def test_find(self):
        # find() looks for merge jobs.
        self.assertEqual([self.job], self.find())
        self.assertEqual(
            [self.job], self.find(from_person=self.from_person))
        self.assertEqual(
            [self.job], self.find(to_person=self.to_person))
        self.assertEqual(
            [self.job], self.find(
                from_person=self.from_person,
                to_person=self.to_person))
        self.assertEqual(
            [], self.find(from_person=self.to_person))

    def test_find_any_person(self):
        # find() any_person looks for merge jobs with either from_person
        # or to_person is true when both are specified.
        self.assertEqual(
            [self.job], self.find(
                from_person=self.to_person, to_person=self.to_person,
                any_person=True))
        self.assertEqual(
            [self.job], self.find(
                from_person=self.from_person, to_person=self.from_person,
                any_person=True))

    def test_find_only_pending_or_running(self):
        # find() only returns jobs that are pending.
        for status in JobStatus.items:
            removeSecurityProxy(self.job.job)._status = status
            if status in Job.PENDING_STATUSES:
                self.assertEqual([self.job], self.find())
            else:
                self.assertEqual([], self.find())

    def test_create_requester(self):
        requester = self.factory.makePerson()
        from_person = self.factory.makePerson()
        to_person = self.factory.makePerson()
        job = getUtility(IPersonMergeJobSource).create(
            from_person, to_person, requester)
        self.assertEqual(requester, job.requester)


class TestViaCelery(TestCaseWithFactory):
    """Test that PersonMergeJob runs under Celery."""

    layer = CeleryJobLayer

    def test_run(self):
        # When run it merges from_person into to_person.
        self.useFixture(FeatureFixture({
            'jobs.celery.enabled_classes': 'PersonMergeJob',
        }))
        job = create_job(self.factory)
        transfer_email(job)
        from_person = job.from_person
        with block_on_job(self):
            transaction.commit()
        self.assertEqual(job.to_person, from_person.merged)
