# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for SharingJobs."""

__metaclass__ = type

from testtools.content import Content
from testtools.content_type import UTF8_TEXT
import transaction
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.code.enums import (
    BranchSubscriptionNotificationLevel,
    CodeReviewNotificationLevel,
    )
from lp.registry.enums import SpecificationSharingPolicy
from lp.registry.interfaces.accesspolicy import (
    IAccessArtifactGrantSource,
    IAccessPolicySource,
    )
from lp.registry.interfaces.person import TeamMembershipPolicy
from lp.registry.interfaces.sharingjob import (
    IRemoveArtifactSubscriptionsJobSource,
    ISharingJob,
    ISharingJobSource,
    )
from lp.registry.model.accesspolicy import reconcile_access_for_artifact
from lp.registry.model.sharingjob import (
    RemoveArtifactSubscriptionsJob,
    SharingJob,
    SharingJobDerived,
    SharingJobType,
    )
from lp.services.database.interfaces import IStore
from lp.services.features.testing import FeatureFixture
from lp.services.job.interfaces.job import JobStatus
from lp.services.job.tests import block_on_job
from lp.services.mail.sendmail import format_address_for_person
from lp.testing import (
    login_person,
    person_logged_in,
    run_script,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    CeleryJobLayer,
    DatabaseFunctionalLayer,
    LaunchpadZopelessLayer,
    )


class SharingJobTestCase(TestCaseWithFactory):
    """Test case for basic SharingJob class."""

    layer = LaunchpadZopelessLayer

    def test_init(self):
        pillar = self.factory.makeProduct()
        grantee = self.factory.makePerson()
        metadata = ('some', 'arbitrary', 'metadata')
        sharing_job = SharingJob(
            SharingJobType.REMOVE_GRANTEE_SUBSCRIPTIONS,
            pillar, grantee, metadata)
        self.assertEqual(
            SharingJobType.REMOVE_GRANTEE_SUBSCRIPTIONS, sharing_job.job_type)
        self.assertEqual(pillar, sharing_job.product)
        self.assertEqual(grantee, sharing_job.grantee)
        expected_json_data = '["some", "arbitrary", "metadata"]'
        self.assertEqual(expected_json_data, sharing_job._json_data)

    def test_metadata(self):
        # The python structure stored as json is returned as python.
        metadata = {
            'a_list': ('some', 'arbitrary', 'metadata'),
            'a_number': 1,
            'a_string': 'string',
            }
        pillar = self.factory.makeProduct()
        grantee = self.factory.makePerson()
        sharing_job = SharingJob(
            SharingJobType.REMOVE_GRANTEE_SUBSCRIPTIONS,
            pillar, grantee, metadata)
        metadata['a_list'] = list(metadata['a_list'])
        self.assertEqual(metadata, sharing_job.metadata)


class SharingJobDerivedTestCase(TestCaseWithFactory):
    """Test case for the SharingJobDerived class."""

    layer = DatabaseFunctionalLayer

    def _makeJob(self):
        self.bug = self.factory.makeBug()
        self.requestor = self.factory.makePerson()
        job = getUtility(IRemoveArtifactSubscriptionsJobSource).create(
            self.requestor, artifacts=[self.bug])
        return job

    def test_repr_bugs(self):
        job = self._makeJob()
        self.assertEqual(
            '<REMOVE_ARTIFACT_SUBSCRIPTIONS job reconciling subscriptions '
            'for bug_ids=[%d], requestor=%s>'
            % (self.bug.id, self.requestor.name),
            repr(job))

    def test_repr_branches(self):
        requestor = self.factory.makePerson()
        branch = self.factory.makeBranch()
        job = getUtility(IRemoveArtifactSubscriptionsJobSource).create(
            requestor, artifacts=[branch])
        self.assertEqual(
            '<REMOVE_ARTIFACT_SUBSCRIPTIONS job reconciling subscriptions '
            'for branch_ids=[%d], requestor=%s>'
            % (branch.id, requestor.name), repr(job))

    def test_repr_specifications(self):
        requestor = self.factory.makePerson()
        specification = self.factory.makeSpecification()
        job = getUtility(IRemoveArtifactSubscriptionsJobSource).create(
            requestor, artifacts=[specification])
        self.assertEqual(
            '<REMOVE_ARTIFACT_SUBSCRIPTIONS job reconciling subscriptions '
            'for requestor=%s, specification_ids=[%d]>'
            % (requestor.name, specification.id), repr(job))

    def test_create_success(self):
        # Create an instance of SharingJobDerived that delegates to SharingJob.
        self.assertIs(True, ISharingJobSource.providedBy(SharingJobDerived))
        job = self._makeJob()
        self.assertIsInstance(job, SharingJobDerived)
        self.assertIs(True, ISharingJob.providedBy(job))
        self.assertIs(True, ISharingJob.providedBy(job.context))

    def test_create_raises_error(self):
        # SharingJobDerived.create() raises an error because it
        # needs to be subclassed to work properly.
        pillar = self.factory.makeProduct()
        grantee = self.factory.makePerson()
        self.assertRaises(
            AttributeError, SharingJobDerived.create, pillar, grantee, {})

    def test_iterReady(self):
        # iterReady finds job in the READY status that are of the same type.
        job_1 = self._makeJob()
        job_2 = self._makeJob()
        job_2.start()
        jobs = list(RemoveArtifactSubscriptionsJob.iterReady())
        self.assertEqual(1, len(jobs))
        self.assertEqual(job_1, jobs[0])

    def test_log_name(self):
        # The log_name is the name of the implementing class.
        job = self._makeJob()
        self.assertEqual('RemoveArtifactSubscriptionsJob', job.log_name)

    def test_getOopsVars(self):
        # The pillar and grantee name are added to the oops vars.
        bug = self.factory.makeBug()
        requestor = self.factory.makePerson()
        job = getUtility(IRemoveArtifactSubscriptionsJobSource).create(
            requestor, artifacts=[bug])
        oops_vars = job.getOopsVars()
        self.assertIs(True, len(oops_vars) >= 3)
        self.assertIn(
            ('sharing_job_type',
            'Remove subscriptions for users who can no longer access '
            'artifacts.'), oops_vars)


class TestRunViaCron(TestCaseWithFactory):
    """Sharing jobs run via cron."""

    layer = DatabaseFunctionalLayer

    def _assert_run_cronscript(self, create_job):
        # The cronscript is configured: schema-lazr.conf and security.cfg.
        # The job runs correctly and the requested bug subscriptions are
        # removed.
        distro = self.factory.makeDistribution()
        grantee = self.factory.makePerson()
        owner = self.factory.makePerson()
        bug = self.factory.makeBug(
            owner=owner, target=distro,
            information_type=InformationType.USERDATA)
        with person_logged_in(owner):
            bug.subscribe(grantee, owner)
        job, job_type = create_job(distro, bug, grantee, owner)
        # Subscribing grantee has created an artifact grant so we need to
        # revoke that to test the job.
        artifact = self.factory.makeAccessArtifact(concrete=bug)
        getUtility(IAccessArtifactGrantSource).revokeByArtifact(
            [artifact], [grantee])
        transaction.commit()

        out, err, exit_code = run_script(
            "LP_DEBUG_SQL=1 cronscripts/process-job-source.py -vv %s" % (
                job_type))
        self.addDetail("stdout", Content(UTF8_TEXT, lambda: out))
        self.addDetail("stderr", Content(UTF8_TEXT, lambda: err))
        self.assertEqual(0, exit_code)
        self.assertTrue(
            'Traceback (most recent call last)' not in err)
        IStore(job.job).invalidate()
        self.assertEqual(JobStatus.COMPLETED, job.job.status)
        self.assertNotIn(
            grantee, removeSecurityProxy(bug).getDirectSubscribers())

    def test_run_remove_bug_subscriptions_cronscript(self):
        # The cronscript is configured: schema-lazr.conf and security.cfg.
        # The job runs correctly and the requested bug subscriptions are
        # removed.

        def create_job(distro, bug, grantee, owner):
            job = getUtility(IRemoveArtifactSubscriptionsJobSource).create(
                owner, [bug])
            with person_logged_in(owner):
                bug.transitionToInformationType(
                            InformationType.PRIVATESECURITY, owner)
            return job, IRemoveArtifactSubscriptionsJobSource.getName()

        self._assert_run_cronscript(create_job)


class RemoveArtifactSubscriptionsJobTestCase(TestCaseWithFactory):
    """Test case for the RemoveArtifactSubscriptionsJob class."""

    layer = CeleryJobLayer

    def setUp(self):
        self.useFixture(FeatureFixture({
            'jobs.celery.enabled_classes': 'RemoveArtifactSubscriptionsJob',
        }))
        super(RemoveArtifactSubscriptionsJobTestCase, self).setUp()

    def test_create(self):
        # Create an instance of RemoveArtifactSubscriptionsJob.
        self.assertIs(
            True,
            IRemoveArtifactSubscriptionsJobSource.providedBy(
                RemoveArtifactSubscriptionsJob))
        self.assertEqual(
            SharingJobType.REMOVE_ARTIFACT_SUBSCRIPTIONS,
            RemoveArtifactSubscriptionsJob.class_job_type)
        requestor = self.factory.makePerson()
        bug = self.factory.makeBug()
        job = getUtility(IRemoveArtifactSubscriptionsJobSource).create(
            requestor, [bug])
        naked_job = removeSecurityProxy(job)
        self.assertIsInstance(job, RemoveArtifactSubscriptionsJob)
        self.assertEqual(requestor.id, naked_job.requestor_id)
        self.assertContentEqual([bug.id], naked_job.bug_ids)

    def test_create__bad_artifact_class(self):
        # A ValueError is raised if an object of an unsupported type
        # is passed as an artifact to
        # IRemoveArtifactSubscriptionsJob.create().
        requestor = self.factory.makePerson()
        wrong_object = self.factory.makePerson()
        self.assertRaises(
            ValueError,
            getUtility(IRemoveArtifactSubscriptionsJobSource).create,
            requestor, [wrong_object])

    def test_getErrorRecipients(self):
        # The pillar owner and job requestor are the error recipients.
        requestor = self.factory.makePerson()
        product = self.factory.makeProduct()
        bug = self.factory.makeBug(target=product)
        job = getUtility(IRemoveArtifactSubscriptionsJobSource).create(
            requestor, [bug], pillar=product)
        expected_emails = [
            format_address_for_person(person)
            for person in (product.owner, requestor)]
        self.assertContentEqual(
            expected_emails, job.getErrorRecipients())

    def _assert_artifact_change_unsubscribes(self, change_callback,
                                             configure_test):
        # Subscribers are unsubscribed if the artifact becomes invisible
        # due to a change in information_type.
        product = self.factory.makeProduct(
            specification_sharing_policy=(
                SpecificationSharingPolicy.EMBARGOED_OR_PROPRIETARY))
        owner = self.factory.makePerson()
        [policy] = getUtility(IAccessPolicySource).find(
            [(product, InformationType.USERDATA)])
        # The policy grantees will lose access.
        policy_indirect_grantee = self.factory.makePerson()
        policy_team_grantee = self.factory.makeTeam(
            membership_policy=TeamMembershipPolicy.RESTRICTED,
            members=[policy_indirect_grantee])

        self.factory.makeAccessPolicyGrant(policy, policy_team_grantee, owner)
        login_person(owner)
        bug = self.factory.makeBug(
            owner=owner, target=product,
            information_type=InformationType.USERDATA)
        branch = self.factory.makeBranch(
            owner=owner, product=product,
            information_type=InformationType.USERDATA)
        specification = self.factory.makeSpecification(
            owner=owner, product=product,
            information_type=InformationType.PROPRIETARY)

        # The artifact grantees will not lose access when the job is run.
        artifact_indirect_grantee = self.factory.makePerson()
        artifact_team_grantee = self.factory.makeTeam(
            membership_policy=TeamMembershipPolicy.RESTRICTED,
            members=[artifact_indirect_grantee])

        bug.subscribe(artifact_indirect_grantee, owner)
        branch.subscribe(artifact_indirect_grantee,
            BranchSubscriptionNotificationLevel.NOEMAIL, None,
            CodeReviewNotificationLevel.NOEMAIL, owner)
        # Subscribing somebody to a specification does not automatically
        # create an artifact grant.
        spec_artifact = self.factory.makeAccessArtifact(specification)
        self.factory.makeAccessArtifactGrant(
            spec_artifact, artifact_indirect_grantee)
        specification.subscribe(artifact_indirect_grantee, owner)

        # pick one of the concrete artifacts (bug, branch or spec)
        # and subscribe the teams and persons.
        concrete_artifact, get_pillars, get_subscribers = configure_test(
            bug, branch, specification, policy_team_grantee,
            policy_indirect_grantee, artifact_team_grantee, owner)

        # Subscribing policy_team_grantee has created an artifact grant so we
        # need to revoke that to test the job.
        artifact = self.factory.makeAccessArtifact(concrete=concrete_artifact)
        getUtility(IAccessArtifactGrantSource).revokeByArtifact(
            [artifact], [policy_team_grantee])

        # policy grantees are subscribed because the job has not been run yet.
        subscribers = get_subscribers(concrete_artifact)
        self.assertIn(policy_team_grantee, subscribers)
        self.assertIn(policy_indirect_grantee, subscribers)

        # Change artifact attributes so that it can become inaccessible for
        # some users.
        change_callback(concrete_artifact)
        reconcile_access_for_artifact(
            concrete_artifact, concrete_artifact.information_type,
            get_pillars(concrete_artifact))

        getUtility(IRemoveArtifactSubscriptionsJobSource).create(
            owner, [concrete_artifact])
        with block_on_job(self):
            transaction.commit()

        # Check the result. Policy grantees will be unsubscribed.
        subscribers = get_subscribers(concrete_artifact)
        self.assertNotIn(policy_team_grantee, subscribers)
        self.assertNotIn(policy_indirect_grantee, subscribers)
        self.assertIn(artifact_team_grantee, subscribers)
        self.assertIn(artifact_indirect_grantee, bug.getDirectSubscribers())
        self.assertIn(artifact_indirect_grantee, branch.subscribers)
        self.assertIn(artifact_indirect_grantee, specification.subscribers)

    def _assert_bug_change_unsubscribes(self, change_callback):

        def get_pillars(concrete_artifact):
            return concrete_artifact.affected_pillars

        def get_subscribers(concrete_artifact):
            return removeSecurityProxy(
                concrete_artifact).getDirectSubscribers()

        def configure_test(bug, branch, specification, policy_team_grantee,
                           policy_indirect_grantee, artifact_team_grantee,
                           owner):
            concrete_artifact = bug
            bug.subscribe(policy_team_grantee, owner)
            bug.subscribe(policy_indirect_grantee, owner)
            bug.subscribe(artifact_team_grantee, owner)
            return concrete_artifact, get_pillars, get_subscribers

        self._assert_artifact_change_unsubscribes(
            change_callback, configure_test)

    def _assert_branch_change_unsubscribes(self, change_callback):

        def get_pillars(concrete_artifact):
            return [concrete_artifact.product]

        def get_subscribers(concrete_artifact):
            return concrete_artifact.subscribers

        def configure_test(bug, branch, specification, policy_team_grantee,
                           policy_indirect_grantee, artifact_team_grantee,
                           owner):
            concrete_artifact = branch
            branch.subscribe(
                policy_team_grantee,
                BranchSubscriptionNotificationLevel.NOEMAIL,
                None, CodeReviewNotificationLevel.NOEMAIL, owner)
            branch.subscribe(
                policy_indirect_grantee,
                BranchSubscriptionNotificationLevel.NOEMAIL, None,
                CodeReviewNotificationLevel.NOEMAIL, owner)
            branch.subscribe(
                artifact_team_grantee,
                BranchSubscriptionNotificationLevel.NOEMAIL, None,
                CodeReviewNotificationLevel.NOEMAIL, owner)
            return concrete_artifact, get_pillars, get_subscribers

        self._assert_artifact_change_unsubscribes(
            change_callback, configure_test)

    def _assert_specification_change_unsubscribes(self, change_callback):

        def get_pillars(concrete_artifact):
            return [concrete_artifact.product]

        def get_subscribers(concrete_artifact):
            return concrete_artifact.subscribers

        def configure_test(bug, branch, specification, policy_team_grantee,
                           policy_indirect_grantee, artifact_team_grantee,
                           owner):
            concrete_artifact = specification
            specification.subscribe(policy_team_grantee, owner)
            specification.subscribe(policy_indirect_grantee, owner)
            spec_artifact = self.factory.makeAccessArtifact(specification)
            self.factory.makeAccessArtifactGrant(
                spec_artifact, artifact_team_grantee)
            specification.subscribe(artifact_team_grantee, owner)
            return concrete_artifact, get_pillars, get_subscribers

        self._assert_artifact_change_unsubscribes(
            change_callback, configure_test)

    def test_change_information_type_branch(self):
        def change_information_type(branch):
            removeSecurityProxy(branch).information_type = (
                InformationType.PRIVATESECURITY)

        self._assert_branch_change_unsubscribes(change_information_type)

    def test_change_information_type_specification(self):
        def change_information_type(specification):
            removeSecurityProxy(specification).information_type = (
                InformationType.EMBARGOED)

        self._assert_specification_change_unsubscribes(change_information_type)

    def test_change_information_type(self):
        # Changing the information type of a bug unsubscribes users who can no
        # longer see the bug.
        def change_information_type(bug):
            # Set the info_type attribute directly since
            # transitionToInformationType queues a job.
            removeSecurityProxy(bug).information_type = (
                InformationType.PRIVATESECURITY)

        self._assert_bug_change_unsubscribes(change_information_type)

    def test_change_target(self):
        # Changing the target of a bug unsubscribes users who can no
        # longer see the bug.
        def change_target(bug):
            # Set the new target directly since transitionToTarget queues a job
            another_product = self.factory.makeProduct()
            removeSecurityProxy(bug).default_bugtask.product = another_product

        self._assert_bug_change_unsubscribes(change_target)

    def _make_subscribed_bug(self, grantee, target,
                             information_type=InformationType.USERDATA):
        owner = self.factory.makePerson()
        bug = self.factory.makeBug(
            owner=owner, target=target, information_type=information_type)
        with person_logged_in(owner):
            bug.subscribe(grantee, owner)
        # Subscribing grantee to bug creates an access grant so we need to
        # revoke that for our test.
        artifact = self.factory.makeAccessArtifact(concrete=bug)
        getUtility(IAccessArtifactGrantSource).revokeByArtifact(
            [artifact], [grantee])

        return bug, owner

    def test_unsubscribe_pillar_artifacts_specific_info_types(self):
        # Only remove subscriptions for bugs of the specified info type.

        person_grantee = self.factory.makePerson(name='grantee')

        owner = self.factory.makePerson(name='pillarowner')
        pillar = self.factory.makeProduct(owner=owner)

        # Make bugs the person_grantee is subscribed to.
        bug1, ignored = self._make_subscribed_bug(
            person_grantee, pillar,
            information_type=InformationType.USERDATA)

        bug2, ignored = self._make_subscribed_bug(
            person_grantee, pillar,
            information_type=InformationType.PRIVATESECURITY)

        # Now run the job, removing access to userdata artifacts.
        getUtility(IRemoveArtifactSubscriptionsJobSource).create(
            pillar.owner, pillar=pillar,
            information_types=[InformationType.USERDATA])
        with block_on_job(self):
            transaction.commit()

        self.assertNotIn(
            person_grantee, removeSecurityProxy(bug1).getDirectSubscribers())
        self.assertIn(
            person_grantee, removeSecurityProxy(bug2).getDirectSubscribers())

    def test_admins_retain_subscriptions(self):
        # Admins subscriptions are retained even if they don't have explicit
        # access.
        product = self.factory.makeProduct()
        owner = self.factory.makePerson()
        admin = getUtility(ILaunchpadCelebrities).admin.teamowner

        login_person(owner)
        bug = self.factory.makeBug(
            owner=owner, target=product,
            information_type=InformationType.USERDATA)

        bug.subscribe(admin, owner)
        getUtility(IRemoveArtifactSubscriptionsJobSource).create(
            owner, [bug], pillar=product)
        with block_on_job(self):
            transaction.commit()

        # Check the result. admin should still be subscribed.
        subscribers = removeSecurityProxy(bug).getDirectSubscribers()
        self.assertIn(admin, subscribers)
