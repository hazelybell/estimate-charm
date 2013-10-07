# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Jobs classes to update products and send notifications."""

__metaclass__ = type
__all__ = [
    'ProductJob',
    'ProductJobManager',
    'CommercialExpiredJob',
    'SevenDayCommercialExpirationJob',
    'ThirtyDayCommercialExpirationJob',
    ]

from datetime import (
    datetime,
    timedelta,
    )

from lazr.delegates import delegates
from pytz import utc
import simplejson
from storm.expr import (
    And,
    Not,
    Select,
    )
from storm.locals import (
    Int,
    Reference,
    Unicode,
    )
from zope.component import getUtility
from zope.interface import (
    classProvides,
    implements,
    )
from zope.security.proxy import removeSecurityProxy

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.registry.enums import (
    BranchSharingPolicy,
    BugSharingPolicy,
    ProductJobType,
    )
from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.product import (
    IProduct,
    License,
    )
from lp.registry.interfaces.productjob import (
    ICommercialExpiredJob,
    ICommercialExpiredJobSource,
    IProductJob,
    IProductJobSource,
    IProductNotificationJob,
    IProductNotificationJobSource,
    ISevenDayCommercialExpirationJob,
    ISevenDayCommercialExpirationJobSource,
    IThirtyDayCommercialExpirationJob,
    IThirtyDayCommercialExpirationJobSource,
    )
from lp.registry.model.commercialsubscription import CommercialSubscription
from lp.registry.model.product import Product
from lp.services.config import config
from lp.services.database.decoratedresultset import DecoratedResultSet
from lp.services.database.enumcol import EnumCol
from lp.services.database.interfaces import (
    IMasterStore,
    IStore,
    )
from lp.services.database.stormbase import StormBase
from lp.services.job.model.job import Job
from lp.services.job.runner import BaseRunnableJob
from lp.services.mail.helpers import get_email_template
from lp.services.mail.mailwrapper import MailWrapper
from lp.services.mail.notificationrecipientset import NotificationRecipientSet
from lp.services.mail.sendmail import (
    format_address,
    format_address_for_person,
    simple_sendmail,
    )
from lp.services.propertycache import cachedproperty
from lp.services.scripts import log
from lp.services.webapp.publisher import canonical_url


class ProductJobManager:
    """Creates jobs for product that need updating or notification."""

    def __init__(self, logger):
        self.logger = logger

    def createAllDailyJobs(self):
        """Create jobs for all products that have timed updates.

        :return: The count of jobs that were created.
        """
        reviewer = getUtility(ILaunchpadCelebrities).janitor
        total = 0
        total += self.createDailyJobs(CommercialExpiredJob, reviewer)
        total += self.createDailyJobs(
            SevenDayCommercialExpirationJob, reviewer)
        total += self.createDailyJobs(
            ThirtyDayCommercialExpirationJob, reviewer)
        return total

    def createDailyJobs(self, job_class, reviewer):
        """Create jobs for products that have timed updates.

        :param job_class: A JobSource class that provides `ExpirationSource`.
        :param reviewer: The user that is creating the job.
        :return: The count of jobs that were created.
        """
        total = 0
        for product in job_class.getExpiringProducts():
            self.logger.debug(
                'Creating a %s for %s' %
                (job_class.__class__.__name__, product.name))
            job_class.create(product, reviewer)
            total += 1
        return total


class ProductJob(StormBase):
    """Base class for product jobs."""

    implements(IProductJob)

    __storm_table__ = 'ProductJob'

    id = Int(primary=True)

    job_id = Int(name='job')
    job = Reference(job_id, Job.id)

    product_id = Int(name='product')
    product = Reference(product_id, Product.id)

    job_type = EnumCol(enum=ProductJobType, notNull=True)

    _json_data = Unicode('json_data')

    @property
    def metadata(self):
        return simplejson.loads(self._json_data)

    def __init__(self, product, job_type, metadata):
        """Constructor.

        :param product: The product the job is for.
        :param job_type: The type job the product needs run.
        :param metadata: A dict of JSON-compatible data to pass to the job.
        """
        super(ProductJob, self).__init__()
        self.job = Job()
        self.product = product
        self.job_type = job_type
        json_data = simplejson.dumps(metadata)
        self._json_data = json_data.decode('utf-8')


class ProductJobDerived(BaseRunnableJob):
    """Intermediate class for deriving from ProductJob.

    Storm classes can't simply be subclassed or you can end up with
    multiple objects referencing the same row in the db. This class uses
    lazr.delegates, which is a little bit simpler than storm's
    inheritance solution to the problem. Subclasses need to override
    the run() method.
    """

    delegates(IProductJob)
    classProvides(IProductJobSource)

    def __init__(self, job):
        self.context = job

    def __repr__(self):
        return (
            "<{self.__class__.__name__} for {self.product.name} "
            "status={self.job.status}>").format(self=self)

    @classmethod
    def create(cls, product, metadata):
        """See `IProductJob`."""
        if not IProduct.providedBy(product):
            raise TypeError("Product must be an IProduct: %s" % repr(product))
        job = ProductJob(
            product=product, job_type=cls.class_job_type, metadata=metadata)
        return cls(job)

    @classmethod
    def find(cls, product, date_since=None, job_type=None):
        """See `IPersonMergeJobSource`."""
        conditions = [
            ProductJob.job_id == Job.id,
            ProductJob.product == product.id,
            ]
        if date_since is not None:
            conditions.append(
                Job.date_created >= date_since)
        if job_type is not None:
            conditions.append(
                ProductJob.job_type == job_type)
        return DecoratedResultSet(
            IStore(ProductJob).find(
                ProductJob, *conditions), cls)

    @classmethod
    def iterReady(cls):
        """Iterate through all ready ProductJobs."""
        store = IMasterStore(ProductJob)
        jobs = store.find(
            ProductJob,
            And(ProductJob.job_type == cls.class_job_type,
                ProductJob.job_id.is_in(Job.ready_jobs)))
        return (cls(job) for job in jobs)

    @property
    def log_name(self):
        return self.__class__.__name__

    def getOopsVars(self):
        """See `IRunnableJob`."""
        vars = BaseRunnableJob.getOopsVars(self)
        vars.extend([
            ('product', self.context.product.name),
            ])
        return vars


class ProductNotificationJob(ProductJobDerived):
    """A Job that send an email to the product maintainer."""

    implements(IProductNotificationJob)
    classProvides(IProductNotificationJobSource)
    class_job_type = ProductJobType.REVIEWER_NOTIFICATION

    @classmethod
    def create(cls, product, email_template_name,
               subject, reviewer, reply_to_commercial=False):
        """See `IProductNotificationJob`."""
        metadata = {
            'email_template_name': email_template_name,
            'subject': subject,
            'reviewer_id': reviewer.id,
            'reply_to_commercial': reply_to_commercial,
            }
        return super(ProductNotificationJob, cls).create(product, metadata)

    @property
    def subject(self):
        """See `IProductNotificationJob`."""
        return self.metadata['subject']

    @property
    def email_template_name(self):
        """See `IProductNotificationJob`."""
        return self.metadata['email_template_name']

    @cachedproperty
    def reviewer(self):
        """See `IProductNotificationJob`."""
        return getUtility(IPersonSet).get(self.metadata['reviewer_id'])

    @property
    def reply_to_commercial(self):
        """See `IProductNotificationJob`."""
        return self.metadata['reply_to_commercial']

    @cachedproperty
    def reply_to(self):
        """See `IProductNotificationJob`."""
        if self.reply_to_commercial:
            return 'Commercial <commercial@launchpad.net>'
        return None

    @cachedproperty
    def recipients(self):
        """See `IProductNotificationJob`."""
        maintainer = self.product.owner
        if maintainer.is_team:
            team_name = maintainer.displayname
            role = "an admin of %s which is the maintainer" % team_name
            users = maintainer.adminmembers
        else:
            role = "the maintainer"
            users = maintainer
        reason = (
            "You received this notification because you are %s of %s.\n%s" %
            (role, self.product.displayname, self.message_data['product_url']))
        header = 'Maintainer'
        notification_set = NotificationRecipientSet()
        notification_set.add(users, reason, header)
        return notification_set

    @cachedproperty
    def message_data(self):
        """See `IProductNotificationJob`."""
        return {
            'product_name': self.product.name,
            'product_displayname': self.product.displayname,
            'product_url': canonical_url(self.product),
            'reviewer_name': self.reviewer.name,
            'reviewer_displayname': self.reviewer.displayname,
            }

    def getErrorRecipients(self):
        """See `BaseRunnableJob`."""
        return [format_address_for_person(self.reviewer)]

    def getBodyAndHeaders(self, email_template, address, reply_to=None):
        """See `IProductNotificationJob`."""
        reason, rationale = self.recipients.getReason(address)
        maintainer = self.recipients._emailToPerson[address]
        message_data = dict(self.message_data)
        message_data['user_name'] = maintainer.name
        message_data['user_displayname'] = maintainer.displayname
        raw_body = email_template % message_data
        raw_body += '\n\n-- \n%s' % reason
        body = MailWrapper().format(raw_body, force_wrap=True)
        headers = {
            'X-Launchpad-Project':
                '%(product_displayname)s (%(product_name)s)' % message_data,
            'X-Launchpad-Message-Rationale': rationale,
            }
        if reply_to is not None:
            headers['Reply-To'] = reply_to
        return body, headers

    def sendEmailToMaintainer(self, template_name, subject, from_address):
        """See `IProductNotificationJob`."""
        email_template = get_email_template(
            "%s.txt" % template_name, app='registry')
        for address in self.recipients.getEmails():
            body, headers = self.getBodyAndHeaders(
                email_template, address, self.reply_to)
            simple_sendmail(from_address, address, subject, body, headers)
        log.debug("%s has sent email to the maintainer of %s.",
            self.log_name, self.product.name)

    def run(self):
        """See `BaseRunnableJob`.

         Subclasses that are updating products may make changes to the product
         before or after calling this class' run() method.
        """
        from_address = format_address(
            'Launchpad', config.canonical.noreply_from_address)
        self.sendEmailToMaintainer(
            self.email_template_name, self.subject, from_address)


class CommericialExpirationMixin:

    _email_template_name = 'product-commercial-subscription-expiration'
    _subject_template = (
        'The commercial subscription for %s in Launchpad is expiring')

    @classmethod
    def create(cls, product, reviewer):
        """See `ExpirationSourceMixin`."""
        subject = cls._subject_template % product.name
        return super(CommericialExpirationMixin, cls).create(
            product, cls._email_template_name, subject, reviewer,
            reply_to_commercial=True)

    @classmethod
    def getExpiringProducts(cls):
        """See `ExpirationSourceMixin`."""
        earliest_date, latest_date, past_date = cls._get_expiration_dates()
        recent_jobs = And(
            ProductJob.job_type == cls.class_job_type,
            ProductJob.job_id == Job.id,
            Job.date_created > past_date,
            )
        conditions = [
            Product.active == True,
            CommercialSubscription.productID == Product.id,
            CommercialSubscription.date_expires >= earliest_date,
            CommercialSubscription.date_expires < latest_date,
            Not(Product.id.is_in(Select(
                ProductJob.product_id,
                tables=[ProductJob, Job], where=recent_jobs))),
            ]
        return IStore(Product).find(Product, *conditions)

    @cachedproperty
    def message_data(self):
        """See `IProductNotificationJob`."""
        data = super(CommericialExpirationMixin, self).message_data
        commercial_subscription = self.product.commercial_subscription
        iso_date = commercial_subscription.date_expires.date().isoformat()
        extra_data = {
            'commercial_use_expiration': iso_date,
            }
        data.update(extra_data)
        return data


class SevenDayCommercialExpirationJob(CommericialExpirationMixin,
                                      ProductNotificationJob):
    """A job that sends an email about an expiring commercial subscription."""

    implements(ISevenDayCommercialExpirationJob)
    classProvides(ISevenDayCommercialExpirationJobSource)
    class_job_type = ProductJobType.COMMERCIAL_EXPIRATION_7_DAYS

    @staticmethod
    def _get_expiration_dates():
        now = datetime.now(utc)
        in_seven_days = now + timedelta(days=7)
        seven_days_ago = now - timedelta(days=7)
        return now, in_seven_days, seven_days_ago


class ThirtyDayCommercialExpirationJob(CommericialExpirationMixin,
                                       ProductNotificationJob):
    """A job that sends an email about an expiring commercial subscription."""

    implements(IThirtyDayCommercialExpirationJob)
    classProvides(IThirtyDayCommercialExpirationJobSource)
    class_job_type = ProductJobType.COMMERCIAL_EXPIRATION_30_DAYS

    @staticmethod
    def _get_expiration_dates():
        now = datetime.now(utc)
        # Avoid overlay with the seven day notification.
        in_twenty_three_days = now + timedelta(days=7)
        in_thirty_days = now + timedelta(days=30)
        thirty_days_ago = now - timedelta(days=30)
        return in_twenty_three_days, in_thirty_days, thirty_days_ago


class CommercialExpiredJob(CommericialExpirationMixin, ProductNotificationJob):
    """A job that sends an email about an expired commercial subscription."""

    implements(ICommercialExpiredJob)
    classProvides(ICommercialExpiredJobSource)
    class_job_type = ProductJobType.COMMERCIAL_EXPIRED

    _email_template_name = ''  # email_template_name does not need this.
    _subject_template = (
        'The commercial subscription for %s in Launchpad expired')

    @staticmethod
    def _get_expiration_dates():
        now = datetime.now(utc)
        ten_years_ago = now - timedelta(days=3650)
        thirty_days_ago = now - timedelta(days=30)
        return ten_years_ago, now, thirty_days_ago

    @property
    def _is_proprietary(self):
        """Does the product have a proprietary licence?"""
        return License.OTHER_PROPRIETARY in self.product.licenses

    @property
    def email_template_name(self):
        """See `IProductNotificationJob`.

        The email template is determined by the product's licences.
        """
        if self._is_proprietary:
            return 'product-commercial-subscription-expired-proprietary'
        else:
            return 'product-commercial-subscription-expired-open-source'

    def _deactivateCommercialFeatures(self):
        """Deactivate the project or just the commercial features it uses."""
        if self._is_proprietary:
            self.product.active = False
        else:
            naked_product = removeSecurityProxy(self.product)
            naked_product.setBranchSharingPolicy(BranchSharingPolicy.FORBIDDEN)
            naked_product.setBugSharingPolicy(BugSharingPolicy.FORBIDDEN)
            for series in self.product.series:
                if series.branch is not None and series.branch.private:
                    removeSecurityProxy(series).branch = None
            self.product.commercial_subscription.delete()

    def run(self):
        """See `ProductNotificationJob`."""
        if self.product.has_current_commercial_subscription:
            # The commercial subscription was renewed after this job was
            # created. Nothing needs to be done.
            return
        super(CommercialExpiredJob, self).run()
        self._deactivateCommercialFeatures()
