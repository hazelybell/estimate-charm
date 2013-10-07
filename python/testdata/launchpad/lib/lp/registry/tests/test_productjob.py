# Copyright 2010-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for ProductJobs."""

__metaclass__ = type

from datetime import (
    datetime,
    timedelta,
    )

import pytz
from testtools.content import Content
from testtools.content_type import UTF8_TEXT
import transaction
from zope.component import getUtility
from zope.interface import (
    classProvides,
    implements,
    )
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.registry.enums import (
    BranchSharingPolicy,
    BugSharingPolicy,
    ProductJobType,
    )
from lp.registry.interfaces.person import TeamMembershipPolicy
from lp.registry.interfaces.product import License
from lp.registry.interfaces.productjob import (
    ICommercialExpiredJob,
    ICommercialExpiredJobSource,
    IProductJob,
    IProductJobSource,
    IProductNotificationJobSource,
    ISevenDayCommercialExpirationJob,
    ISevenDayCommercialExpirationJobSource,
    IThirtyDayCommercialExpirationJob,
    IThirtyDayCommercialExpirationJobSource,
    )
from lp.registry.interfaces.teammembership import TeamMembershipStatus
from lp.registry.model.productjob import (
    CommercialExpiredJob,
    ProductJob,
    ProductJobDerived,
    ProductJobManager,
    ProductNotificationJob,
    SevenDayCommercialExpirationJob,
    ThirtyDayCommercialExpirationJob,
    )
from lp.services.database.interfaces import IStore
from lp.services.job.interfaces.job import JobStatus
from lp.services.log.logger import BufferLogger
from lp.services.propertycache import clear_property_cache
from lp.services.webapp.publisher import canonical_url
from lp.testing import (
    person_logged_in,
    run_script,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadZopelessLayer,
    ZopelessAppServerLayer,
    )
from lp.testing.mail_helpers import pop_notifications


class CommercialHelpers:

    @staticmethod
    def expire_commercial_subscription(product):
        expired_date = (
            product.commercial_subscription.date_expires - timedelta(days=365))
        removeSecurityProxy(
            product.commercial_subscription).date_expires = expired_date

    def make_expiring_product(self, date_expires, job_class=None):
        product = self.factory.makeProduct(
            licenses=[License.OTHER_PROPRIETARY])
        removeSecurityProxy(
            product.commercial_subscription).date_expires = date_expires
        if job_class:
            reviewer = getUtility(ILaunchpadCelebrities).janitor
            job_class.create(product, reviewer)
        return product

    def make_test_products(self):
        products = {}
        now = datetime.now(pytz.utc)
        products['approved'] = self.factory.makeProduct(licenses=[License.MIT])
        products['expired'] = self.make_expiring_product(now - timedelta(1))
        products['expired_with_job'] = self.make_expiring_product(
            now - timedelta(1), job_class=CommercialExpiredJob)
        products['seven'] = self.make_expiring_product(now + timedelta(6))
        products['seven_with_job'] = self.make_expiring_product(
            now + timedelta(6), job_class=SevenDayCommercialExpirationJob)
        products['thirty'] = self.make_expiring_product(now + timedelta(29))
        products['thirty_with_job'] = self.make_expiring_product(
            now + timedelta(29), job_class=ThirtyDayCommercialExpirationJob)
        products['sixty'] = self.make_expiring_product(now + timedelta(60))
        return products


class ProductJobManagerTestCase(TestCaseWithFactory, CommercialHelpers):
    """Test case for the ProductJobManager class."""
    layer = DatabaseFunctionalLayer

    @staticmethod
    def make_manager():
        logger = BufferLogger()
        return ProductJobManager(logger)

    def test_init(self):
        # The logger was set.
        manager = self.make_manager()
        self.assertIsInstance(manager.logger, BufferLogger)

    def test_createAllDailyJobs(self):
        # 3 kinds of commercial expiration jobs are created.
        self.make_test_products()
        manager = self.make_manager()
        self.assertEqual(3, manager.createAllDailyJobs())
        log = manager.logger.getLogBuffer()
        self.assertIn(CommercialExpiredJob.__class__.__name__, log)
        self.assertIn(SevenDayCommercialExpirationJob.__class__.__name__, log)
        self.assertIn(ThirtyDayCommercialExpirationJob.__class__.__name__, log)

    def test_createDailyJobs(self):
        # Commercial expiration jobs are created.
        test_products = self.make_test_products()
        manager = self.make_manager()
        reviewer = self.factory.makePerson()
        total = manager.createDailyJobs(CommercialExpiredJob, reviewer)
        self.assertEqual(1, total)
        self.assertIn(
            'DEBUG Creating a %s for %s' %
            (CommercialExpiredJob.__class__.__name__,
             test_products['expired'].name),
            manager.logger.getLogBuffer())


class DailyProductJobsTestCase(TestCaseWithFactory, CommercialHelpers):
    """Test case for the ProductJobManager class."""
    layer = ZopelessAppServerLayer

    def test_run(self):
        # The script called ProductJobManager.createAllDailyJobs().
        # This test uses the same setup as
        # ProductJobManagerTestCase.test_createAllDailyJobs
        self.make_test_products()
        transaction.commit()
        stdout, stderr, retcode = run_script(
            'cronscripts/daily_product_jobs.py')
        self.addDetail("stdout", Content(UTF8_TEXT, lambda: stdout))
        self.addDetail("stderr", Content(UTF8_TEXT, lambda: stderr))
        self.assertEqual(0, retcode)
        self.assertIn('Requested 3 total product jobs.', stderr)


class ProductJobTestCase(TestCaseWithFactory):
    """Test case for basic ProductJob class."""

    layer = LaunchpadZopelessLayer

    def test_init(self):
        product = self.factory.makeProduct()
        metadata = ('some', 'arbitrary', 'metadata')
        product_job = ProductJob(
            product, ProductJobType.REVIEWER_NOTIFICATION, metadata)
        self.assertEqual(product, product_job.product)
        self.assertEqual(
            ProductJobType.REVIEWER_NOTIFICATION, product_job.job_type)
        expected_json_data = '["some", "arbitrary", "metadata"]'
        self.assertEqual(expected_json_data, product_job._json_data)

    def test_metadata(self):
        # The python structure stored as json is returned as python.
        product = self.factory.makeProduct()
        metadata = {
            'a_list': ('some', 'arbitrary', 'metadata'),
            'a_number': 1,
            'a_string': 'string',
            }
        product_job = ProductJob(
            product, ProductJobType.REVIEWER_NOTIFICATION, metadata)
        metadata['a_list'] = list(metadata['a_list'])
        self.assertEqual(metadata, product_job.metadata)


class IProductThingJob(IProductJob):
    """An interface for testing derived job classes."""


class IProductThingJobSource(IProductJobSource):
    """An interface for testing derived job source classes."""


class FakeProductJob(ProductJobDerived):
    """A class that reuses other interfaces and types for testing."""
    class_job_type = ProductJobType.REVIEWER_NOTIFICATION
    implements(IProductThingJob)
    classProvides(IProductThingJobSource)


class OtherFakeProductJob(ProductJobDerived):
    """A class that reuses other interfaces and types for testing."""
    class_job_type = ProductJobType.COMMERCIAL_EXPIRED
    implements(IProductThingJob)
    classProvides(IProductThingJobSource)


class ProductJobDerivedTestCase(TestCaseWithFactory):
    """Test case for the ProductJobDerived class."""

    layer = DatabaseFunctionalLayer

    def test_repr(self):
        product = self.factory.makeProduct('fnord')
        metadata = {'foo': 'bar'}
        job = FakeProductJob.create(product, metadata)
        self.assertEqual(
            '<FakeProductJob for fnord status=Waiting>', repr(job))

    def test_create_success(self):
        # Create an instance of ProductJobDerived that delegates to
        # ProductJob.
        product = self.factory.makeProduct()
        metadata = {'foo': 'bar'}
        self.assertIs(True, IProductJobSource.providedBy(ProductJobDerived))
        job = FakeProductJob.create(product, metadata)
        self.assertIsInstance(job, ProductJobDerived)
        self.assertIs(True, IProductJob.providedBy(job))
        self.assertIs(True, IProductJob.providedBy(job.context))

    def test_create_raises_error(self):
        # ProductJobDerived.create() raises an error because it
        # needs to be subclassed to work properly.
        product = self.factory.makeProduct()
        metadata = {'foo': 'bar'}
        self.assertRaises(
            AttributeError, ProductJobDerived.create, product, metadata)

    def test_iterReady(self):
        # iterReady finds job in the READY status that are of the same type.
        product = self.factory.makeProduct()
        metadata = {'foo': 'bar'}
        job_1 = FakeProductJob.create(product, metadata)
        job_2 = FakeProductJob.create(product, metadata)
        job_2.start()
        OtherFakeProductJob.create(product, metadata)
        jobs = list(FakeProductJob.iterReady())
        self.assertEqual(1, len(jobs))
        self.assertEqual(job_1, jobs[0])

    def test_find_product(self):
        # Find all the jobs for a product regardless of date or job type.
        product = self.factory.makeProduct()
        metadata = {'foo': 'bar'}
        job_1 = FakeProductJob.create(product, metadata)
        job_2 = OtherFakeProductJob.create(product, metadata)
        FakeProductJob.create(self.factory.makeProduct(), metadata)
        jobs = list(ProductJobDerived.find(product=product))
        self.assertEqual(2, len(jobs))
        self.assertContentEqual([job_1.id, job_2.id], [job.id for job in jobs])

    def test_find_job_type(self):
        # Find all the jobs for a product and job_type regardless of date.
        product = self.factory.makeProduct()
        metadata = {'foo': 'bar'}
        job_1 = FakeProductJob.create(product, metadata)
        job_2 = FakeProductJob.create(product, metadata)
        OtherFakeProductJob.create(product, metadata)
        jobs = list(ProductJobDerived.find(
            product, job_type=ProductJobType.REVIEWER_NOTIFICATION))
        self.assertEqual(2, len(jobs))
        self.assertContentEqual([job_1.id, job_2.id], [job.id for job in jobs])

    def test_find_date_since(self):
        # Find all the jobs for a product since a date regardless of job_type.
        now = datetime.now(pytz.utc)
        seven_days_ago = now - timedelta(7)
        thirty_days_ago = now - timedelta(30)
        product = self.factory.makeProduct()
        metadata = {'foo': 'bar'}
        job_1 = FakeProductJob.create(product, metadata)
        removeSecurityProxy(job_1.job).date_created = thirty_days_ago
        job_2 = FakeProductJob.create(product, metadata)
        removeSecurityProxy(job_2.job).date_created = seven_days_ago
        job_3 = OtherFakeProductJob.create(product, metadata)
        removeSecurityProxy(job_3.job).date_created = now
        jobs = list(ProductJobDerived.find(product, date_since=seven_days_ago))
        self.assertEqual(2, len(jobs))
        self.assertContentEqual([job_2.id, job_3.id], [job.id for job in jobs])

    def test_log_name(self):
        # The log_name is the name of the implementing class.
        product = self.factory.makeProduct('fnord')
        metadata = {'foo': 'bar'}
        job = FakeProductJob.create(product, metadata)
        self.assertEqual('FakeProductJob', job.log_name)

    def test_getOopsVars(self):
        # The project name is added to the oops vars.
        product = self.factory.makeProduct('fnord')
        metadata = {'foo': 'bar'}
        job = FakeProductJob.create(product, metadata)
        oops_vars = job.getOopsVars()
        self.assertIs(True, len(oops_vars) > 1)
        self.assertIn(('product', product.name), oops_vars)


class ProductNotificationJobTestCase(TestCaseWithFactory):
    """Test case for the ProductNotificationJob class."""

    layer = DatabaseFunctionalLayer

    def make_notification_data(self):
        product = self.factory.makeProduct()
        reviewer = self.factory.makePerson('reviewer@eg.com', name='reviewer')
        subject = "test subject"
        email_template_name = 'product-license-dont-know'
        return product, email_template_name, subject, reviewer

    def make_maintainer_team(self, product):
        team = self.factory.makeTeam(
            owner=product.owner,
            membership_policy=TeamMembershipPolicy.MODERATED)
        team_admin = self.factory.makePerson()
        with person_logged_in(team.teamowner):
            team.addMember(
                team_admin, team.teamowner, status=TeamMembershipStatus.ADMIN)
            product.owner = team
        return team, team_admin

    def test_create(self):
        # Create an instance of ProductNotificationJob that stores
        # the notification information.
        data = self.make_notification_data()
        product, email_template_name, subject, reviewer = data
        self.assertIs(
            True,
            IProductNotificationJobSource.providedBy(ProductNotificationJob))
        self.assertEqual(
            ProductJobType.REVIEWER_NOTIFICATION,
            ProductNotificationJob.class_job_type)
        job = ProductNotificationJob.create(
            product, email_template_name, subject, reviewer,
            reply_to_commercial=False)
        self.assertIsInstance(job, ProductNotificationJob)
        self.assertEqual(product, job.product)
        self.assertEqual(email_template_name, job.email_template_name)
        self.assertEqual(subject, job.subject)
        self.assertEqual(reviewer, job.reviewer)
        self.assertEqual(False, job.reply_to_commercial)

    def test_getErrorRecipients(self):
        # The reviewer is the error recipient.
        data = self.make_notification_data()
        job = ProductNotificationJob.create(*data)
        self.assertEqual(
            ['Reviewer <reviewer@eg.com>'], job.getErrorRecipients())

    def test_reply_to_commercial(self):
        # Commercial emails have the commercial@launchpad.net reply-to
        # by setting the reply_to_commercial arg to True.
        data = list(self.make_notification_data())
        data.append(True)
        job = ProductNotificationJob.create(*data)
        self.assertEqual('Commercial <commercial@launchpad.net>', job.reply_to)

    def test_reply_to_non_commercial(self):
        # Non-commercial emails do not have a reply-to.
        data = list(self.make_notification_data())
        data.append(False)
        job = ProductNotificationJob.create(*data)
        self.assertIs(None, job.reply_to)

    def test_recipients_user(self):
        # The product maintainer is the recipient.
        data = self.make_notification_data()
        job = ProductNotificationJob.create(*data)
        product, email_template_name, subject, reviewer = data
        recipients = job.recipients
        self.assertEqual([product.owner], recipients.getRecipients())
        reason, header = recipients.getReason(product.owner)
        self.assertEqual('Maintainer', header)
        self.assertIn(canonical_url(product), reason)
        self.assertIn(
            'you are the maintainer of %s' % product.displayname, reason)

    def test_recipients_team(self):
        # The product maintainer team admins are the recipient.
        data = self.make_notification_data()
        job = ProductNotificationJob.create(*data)
        product, email_template_name, subject, reviewer = data
        team, team_admin = self.make_maintainer_team(product)
        recipients = job.recipients
        self.assertContentEqual(
            [team.teamowner, team_admin], recipients.getRecipients())
        reason, header = recipients.getReason(team.teamowner)
        self.assertEqual('Maintainer', header)
        self.assertIn(canonical_url(product), reason)
        self.assertIn(
            'you are an admin of %s which is the maintainer of %s' %
            (team.displayname, product.displayname),
            reason)

    def test_message_data(self):
        # The message_data is a dict of interpolatable strings.
        data = self.make_notification_data()
        job = ProductNotificationJob.create(*data)
        product, email_template_name, subject, reviewer = data
        self.assertEqual(product.name, job.message_data['product_name'])
        self.assertEqual(
            product.displayname, job.message_data['product_displayname'])
        self.assertEqual(
            canonical_url(product), job.message_data['product_url'])
        self.assertEqual(reviewer.name, job.message_data['reviewer_name'])
        self.assertEqual(
            reviewer.displayname, job.message_data['reviewer_displayname'])

    def test_getBodyAndHeaders_with_reply_to(self):
        # The body and headers contain reasons and rationales.
        data = self.make_notification_data()
        job = ProductNotificationJob.create(*data)
        product, email_template_name, subject, reviewer = data
        [address] = job.recipients.getEmails()
        email_template = (
            'hello %(user_name)s %(product_name)s %(reviewer_name)s')
        reply_to = 'me@eg.dom'
        body, headers = job.getBodyAndHeaders(
            email_template, address, reply_to)
        self.assertIn(reviewer.name, body)
        self.assertIn(product.name, body)
        self.assertIn(product.owner.name, body)
        self.assertIn('\n\n--\nYou received', body)
        expected_headers = [
            ('X-Launchpad-Project', '%s (%s)' %
              (product.displayname, product.name)),
            ('X-Launchpad-Message-Rationale', 'Maintainer'),
            ('Reply-To', reply_to),
            ]
        self.assertContentEqual(expected_headers, headers.items())

    def test_getBodyAndHeaders_without_reply_to(self):
        # The reply-to is an optional argument.
        data = self.make_notification_data()
        job = ProductNotificationJob.create(*data)
        product, email_template_name, subject, reviewer = data
        [address] = job.recipients.getEmails()
        email_template = 'hello'
        body, headers = job.getBodyAndHeaders(email_template, address)
        expected_headers = [
            ('X-Launchpad-Project', '%s (%s)' %
              (product.displayname, product.name)),
            ('X-Launchpad-Message-Rationale', 'Maintainer'),
            ]
        self.assertContentEqual(expected_headers, headers.items())

    def test_sendEmailToMaintainer(self):
        # sendEmailToMaintainer() sends an email to the maintainers.
        data = self.make_notification_data()
        job = ProductNotificationJob.create(*data)
        product, email_template_name, subject, reviewer = data
        team, team_admin = self.make_maintainer_team(product)
        addresses = job.recipients.getEmails()
        pop_notifications()
        job.sendEmailToMaintainer(email_template_name, 'frog', 'me@eg.dom')
        notifications = pop_notifications()
        self.assertEqual(2, len(notifications))
        self.assertEqual(addresses[0], notifications[0]['To'])
        self.assertEqual(addresses[1], notifications[1]['To'])
        self.assertEqual('me@eg.dom', notifications[1]['From'])
        self.assertEqual('frog', notifications[1]['Subject'])

    def test_run(self):
        # sendEmailToMaintainer() sends an email to the maintainers.
        data = self.make_notification_data()
        job = ProductNotificationJob.create(*data)
        product, email_template_name, subject, reviewer = data
        [address] = job.recipients.getEmails()
        pop_notifications()
        job.run()
        notifications = pop_notifications()
        self.assertEqual(1, len(notifications))
        self.assertEqual(address, notifications[0]['To'])
        self.assertEqual(subject, notifications[0]['Subject'])
        self.assertIn(
            'Launchpad <noreply@launchpad.net>', notifications[0]['From'])


class CommericialExpirationMixin(CommercialHelpers):

    layer = DatabaseFunctionalLayer

    EXPIRE_SUBSCRIPTION = False
    EXPECTED_PRODUCT = None

    def make_notification_data(self, licenses=[License.MIT]):
        product = self.factory.makeProduct(licenses=licenses)
        if License.OTHER_PROPRIETARY not in product.licenses:
            # The proprietary project was automatically given a CS.
            self.factory.makeCommercialSubscription(product)
        reviewer = getUtility(ILaunchpadCelebrities).janitor
        return product, reviewer

    def test_getExpiringProducts(self):
        # Get the products with an expiring commercial subscription in
        # the job type's date range that do not already have a recent job.
        test_products = self.make_test_products()
        products = list(self.JOB_CLASS.getExpiringProducts())
        self.assertEqual(1, len(products))
        self.assertEqual(test_products[self.EXPECTED_PRODUCT], products[0])

    def test_create(self):
        # Create an instance of an commercial expiration job that stores
        # the notification information.
        product = self.factory.makeProduct()
        reviewer = getUtility(ILaunchpadCelebrities).janitor
        self.assertIs(
            True,
            self.JOB_SOURCE_INTERFACE.providedBy(self.JOB_CLASS))
        self.assertEqual(
            self.JOB_CLASS_TYPE, self.JOB_CLASS.class_job_type)
        job = self.JOB_CLASS.create(product, reviewer)
        self.assertIsInstance(job, self.JOB_CLASS)
        self.assertIs(
            True, self.JOB_INTERFACE.providedBy(job))
        self.assertEqual(product, job.product)
        self.assertEqual(job._subject_template % product.name, job.subject)
        self.assertEqual(reviewer, job.reviewer)
        self.assertEqual(True, job.reply_to_commercial)

    def test_email_template_name(self):
        # The class defines the email_template_name.
        product, reviewer = self.make_notification_data()
        job = self.JOB_CLASS.create(product, reviewer)
        self.assertEqual(job.email_template_name, job._email_template_name)

    def test_message_data(self):
        # The commercial expiration data is added.
        product, reviewer = self.make_notification_data()
        job = self.JOB_CLASS.create(product, reviewer)
        commercial_subscription = product.commercial_subscription
        iso_date = commercial_subscription.date_expires.date().isoformat()
        self.assertEqual(
            iso_date, job.message_data['commercial_use_expiration'])

    def test_run(self):
        # Smoke test that run() can make the email from the template and data.
        product, reviewer = self.make_notification_data(
            licenses=[License.OTHER_PROPRIETARY])
        commercial_subscription = product.commercial_subscription
        if self.EXPIRE_SUBSCRIPTION:
            self.expire_commercial_subscription(product)
        iso_date = commercial_subscription.date_expires.date().isoformat()
        job = self.JOB_CLASS.create(product, reviewer)
        pop_notifications()
        job.run()
        notifications = pop_notifications()
        self.assertEqual(1, len(notifications))
        self.assertIn(iso_date, notifications[0].get_payload())

    def test_run_cronscript(self):
        # Everything is configured: ZCML, schema-lazr.conf, and security.cfg.
        product, reviewer = self.make_notification_data()
        private_branch = self.factory.makeBranch(
            owner=product.owner, product=product,
            information_type=InformationType.USERDATA)
        with person_logged_in(product.owner):
            product.development_focus.branch = private_branch
        self.expire_commercial_subscription(product)
        job = self.JOB_CLASS.create(product, reviewer)
        # Create a proprietary project owned by a team which will have
        # different DB relations.
        team = self.factory.makeTeam(
            membership_policy=TeamMembershipPolicy.RESTRICTED)
        proprietary_product = self.factory.makeProduct(
            owner=team, licenses=[License.OTHER_PROPRIETARY])
        self.expire_commercial_subscription(proprietary_product)
        proprietary_job = self.JOB_CLASS.create(proprietary_product, reviewer)
        transaction.commit()

        out, err, exit_code = run_script(
            "LP_DEBUG_SQL=1 cronscripts/process-job-source.py -vv %s" %
             self.JOB_SOURCE_INTERFACE.getName())
        self.addDetail("stdout", Content(UTF8_TEXT, lambda: out))
        self.addDetail("stderr", Content(UTF8_TEXT, lambda: err))
        self.assertEqual(0, exit_code)
        self.assertTrue(
            'Traceback (most recent call last)' not in err)
        message = (
            '%s has sent email to the maintainer of %s.' % (
                self.JOB_CLASS.__name__, product.name))
        self.assertTrue(
            message in err,
            'Cound not find "%s" in err log:\n%s.' % (message, err))
        message = (
            '%s has sent email to the maintainer of %s.' % (
                self.JOB_CLASS.__name__, proprietary_product.name))
        self.assertTrue(
            message in err,
            'Cound not find "%s" in err log:\n%s.' % (message, err))
        IStore(job.job).invalidate()
        self.assertEqual(JobStatus.COMPLETED, job.job.status)
        self.assertEqual(JobStatus.COMPLETED, proprietary_job.job.status)


class SevenDayCommercialExpirationJobTestCase(CommericialExpirationMixin,
                                              TestCaseWithFactory):
    """Test case for the SevenDayCommercialExpirationJob class."""

    EXPECTED_PRODUCT = 'seven'
    JOB_INTERFACE = ISevenDayCommercialExpirationJob
    JOB_SOURCE_INTERFACE = ISevenDayCommercialExpirationJobSource
    JOB_CLASS = SevenDayCommercialExpirationJob
    JOB_CLASS_TYPE = ProductJobType.COMMERCIAL_EXPIRATION_7_DAYS

    def test_get_expiration_dates(self):
        dates = SevenDayCommercialExpirationJob._get_expiration_dates()
        earliest_date, latest_date, past_date = dates
        self.assertEqual(timedelta(days=7), latest_date - earliest_date)
        self.assertEqual(timedelta(days=14), latest_date - past_date)


class ThirtyDayCommercialExpirationJobTestCase(CommericialExpirationMixin,
                                               TestCaseWithFactory):
    """Test case for the SevenDayCommercialExpirationJob class."""

    EXPECTED_PRODUCT = 'thirty'
    JOB_INTERFACE = IThirtyDayCommercialExpirationJob
    JOB_SOURCE_INTERFACE = IThirtyDayCommercialExpirationJobSource
    JOB_CLASS = ThirtyDayCommercialExpirationJob
    JOB_CLASS_TYPE = ProductJobType.COMMERCIAL_EXPIRATION_30_DAYS

    def test_get_expiration_dates(self):
        dates = ThirtyDayCommercialExpirationJob._get_expiration_dates()
        earliest_date, latest_date, past_date = dates
        self.assertEqual(timedelta(days=23), latest_date - earliest_date)
        self.assertEqual(timedelta(days=60), latest_date - past_date)


class CommercialExpiredJobTestCase(CommericialExpirationMixin,
                                   TestCaseWithFactory):
    """Test case for the CommercialExpiredJob class."""

    EXPIRE_SUBSCRIPTION = True
    EXPECTED_PRODUCT = 'expired'
    JOB_INTERFACE = ICommercialExpiredJob
    JOB_SOURCE_INTERFACE = ICommercialExpiredJobSource
    JOB_CLASS = CommercialExpiredJob
    JOB_CLASS_TYPE = ProductJobType.COMMERCIAL_EXPIRED

    def test_get_expiration_dates(self):
        dates = CommercialExpiredJob._get_expiration_dates()
        earliest_date, latest_date, past_date = dates
        self.assertEqual(timedelta(days=3650), latest_date - earliest_date)
        self.assertEqual(timedelta(days=30), latest_date - past_date)

    def test_is_proprietary_open_source(self):
        product, reviewer = self.make_notification_data(licenses=[License.MIT])
        job = CommercialExpiredJob.create(product, reviewer)
        self.assertIs(False, job._is_proprietary)

    def test_is_proprietary_proprietary(self):
        product, reviewer = self.make_notification_data(
            licenses=[License.OTHER_PROPRIETARY])
        job = CommercialExpiredJob.create(product, reviewer)
        self.assertIs(True, job._is_proprietary)

    def test_email_template_name(self):
        # Redefine the inherited test to verify the open source licence case.
        # The state of the product's licence defines the email_template_name.
        product, reviewer = self.make_notification_data(licenses=[License.MIT])
        job = CommercialExpiredJob.create(product, reviewer)
        self.assertEqual(
            'product-commercial-subscription-expired-open-source',
            job.email_template_name)

    def test_email_template_name_proprietary(self):
        # The state of the product's licence defines the email_template_name.
        product, reviewer = self.make_notification_data(
            licenses=[License.OTHER_PROPRIETARY])
        job = CommercialExpiredJob.create(product, reviewer)
        self.assertEqual(
            'product-commercial-subscription-expired-proprietary',
            job.email_template_name)

    def test_deactivateCommercialFeatures_proprietary(self):
        # When the project is proprietary, the product is deactivated.
        product, reviewer = self.make_notification_data(
            licenses=[License.OTHER_PROPRIETARY])
        self.expire_commercial_subscription(product)
        job = CommercialExpiredJob.create(product, reviewer)
        job._deactivateCommercialFeatures()
        clear_property_cache(product)
        self.assertIs(False, product.active)
        self.assertIsNot(None, product.commercial_subscription)

    def test_deactivateCommercialFeatures_open_source(self):
        # When the project is open source, the product's commercial features
        # are deactivated and the commercial subscription is deleted.
        product, reviewer = self.make_notification_data(licenses=[License.MIT])
        public_branch = self.factory.makeBranch(
            owner=product.owner, product=product)
        private_branch = self.factory.makeBranch(
            owner=product.owner, product=product,
            information_type=InformationType.USERDATA)
        with person_logged_in(product.owner):
            public_series = product.development_focus
            public_series.branch = public_branch
            private_series = product.newSeries(
                product.owner, 'special', 'testing', branch=private_branch)
            # Verify that branchless series do not raise an error.
            product.newSeries(product.owner, 'unused', 'no branch')
        self.expire_commercial_subscription(product)
        job = CommercialExpiredJob.create(product, reviewer)
        job._deactivateCommercialFeatures()
        clear_property_cache(product)
        self.assertTrue(product.active)
        self.assertEqual(
            BranchSharingPolicy.FORBIDDEN, product.branch_sharing_policy)
        self.assertEqual(
            BugSharingPolicy.FORBIDDEN, product.bug_sharing_policy)
        self.assertEqual(public_branch, public_series.branch)
        self.assertIs(None, private_series.branch)
        self.assertIs(None, product.commercial_subscription)

    def test_run_deactivation_performed(self):
        # An email is sent and the deactivation steps are performed.
        product, reviewer = self.make_notification_data(
            licenses=[License.OTHER_PROPRIETARY])
        self.expire_commercial_subscription(product)
        job = CommercialExpiredJob.create(product, reviewer)
        job.run()
        self.assertIs(False, product.active)

    def test_run_deactivation_aborted(self):
        # The deactivation steps and email are aborted if the commercial
        # subscription was renewed after the job was created.
        product, reviewer = self.make_notification_data(
            licenses=[License.OTHER_PROPRIETARY])
        job = CommercialExpiredJob.create(product, reviewer)
        pop_notifications()
        job.run()
        notifications = pop_notifications()
        self.assertEqual(0, len(notifications))
        self.assertIs(True, product.active)
