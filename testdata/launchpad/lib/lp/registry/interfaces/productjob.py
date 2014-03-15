# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces for the Jobs system to update products and send notifications."""

__metaclass__ = type
__all__ = [
    'IProductJob',
    'IProductJobSource',
    'IProductNotificationJob',
    'IProductNotificationJobSource',
    'ICommercialExpiredJob',
    'ICommercialExpiredJobSource',
    'ISevenDayCommercialExpirationJob',
    'ISevenDayCommercialExpirationJobSource',
    'IThirtyDayCommercialExpirationJob',
    'IThirtyDayCommercialExpirationJobSource',
    ]

from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Int,
    Object,
    )

from lp import _
from lp.registry.interfaces.product import IProduct
from lp.services.job.interfaces.job import (
    IJob,
    IJobSource,
    IRunnableJob,
    )


class IProductJob(IRunnableJob):
    """A Job related to an `IProduct`."""

    id = Int(
        title=_('DB ID'), required=True, readonly=True,
        description=_("The tracking number of this job."))

    job = Object(
        title=_('The common Job attributes'),
        schema=IJob,
        required=True)

    product = Object(
        title=_('The product the job is for'),
        schema=IProduct,
        required=True)

    metadata = Attribute('A dict of data for the job')


class IProductJobSource(IJobSource):
    """An interface for creating and finding `IProductJob`s."""

    def create(product, metadata):
        """Create a new `IProductJob`.

        :param product: An IProduct.
        :param metadata: a dict of configuration data for the job.
            The data must be JSON compatible keys and values.
        """

    def find(product=None, date_since=None, job_type=None):
        """Find `IProductJob`s that match the specified criteria.

        :param product: Match jobs for specific product.
        :param date_since: Match jobs since the specified date.
        :param job_type: Match jobs of a specific type. Type is expected
            to be a class name.
        :return: A `ResultSet` yielding `IProductJob`.
        """


class IProductNotificationJob(IProductJob):
    """A job that sends a notification about a product."""

    subject = Attribute('The subject line of the notification.')
    email_template_name = Attribute(
        'The name of the email template to create the message body from.')
    reviewer = Attribute('The user or agent sending the email.')
    recipients = Attribute('An `INotificationRecipientSet`.')
    message_data = Attribute(
        'A dict that is interpolated with the email template.')
    reply_to = Attribute('The optional address to set as the Reply-To.')

    def getBodyAndHeaders(email_template, address, reply_to=None):
        """Return a tuple of email message body and headers.

        The body is constructed from the email template and message_data.
        The headers are a dict that includes the X-Launchpad-Rationale.

        :param email_template: A string that will be interpolated
            with message_data.
        :param address: The email address of the user the message is to.
        :reply_to: An optional email address to set as the Reply-To header.
        :return a tuple (string, dict):
        """

    def sendEmailToMaintainer(template_name, subject, from_address):
        """Send an email to the product maintainer.

        :param email_template_name: The name of the email template to
            use as the email body.
        :param subject: The subject line of the notification.
        :param from_address: The email address sending the email.

        """


class IProductNotificationJobSource(IProductJobSource):
    """An interface for creating `IProductNotificationJob`s."""

    def create(product, email_template_name, subject,
               reviewer, reply_to_commercial=False):
        """Create a new `IProductNotificationJob`.

        :param product: An IProduct.
        :param email_template_name: The name of the email template without
            the extension.
        :param subject: The subject line of the notification.
        :param reviewer: The user or agent sending the email.
        :param reply_to_commercial: Set the reply_to property to the
            commercial email address.
        """


class ExpirationSource(Interface):

    def create(product, reviewer):
        """Create a new job.

        :param product: An IProduct.
        :param reviewer: The user or agent sending the email.
        """

    def getExpiringProducts():
        """Return the products that require a job to update them.

        The products returned can passed to create() to make the job.
        The products have a commercial subscription that expires within
        the job's effective date range. The products returned do not
        have a recent job; once the job is created, the product is
        excluded from the future calls to this method.
        """


class ISevenDayCommercialExpirationJob(IProductNotificationJob):
    """A job that sends an email about an expiring commercial subscription."""


class ISevenDayCommercialExpirationJobSource(IProductNotificationJobSource,
                                             ExpirationSource):
    """An interface for creating `ISevenDayCommercialExpirationJob`s."""


class IThirtyDayCommercialExpirationJob(IProductNotificationJob):
    """A job that sends an email about an expiring commercial subscription."""


class IThirtyDayCommercialExpirationJobSource(IProductNotificationJobSource,
                                              ExpirationSource):
    """An interface for creating `IThirtyDayCommercialExpirationJob`s."""


class ICommercialExpiredJob(IProductNotificationJob):
    """A job that sends an email about an expired commercial subscription.

    This job is responsible for deactivating the project if it has a
    proprietary licence or deactivating the commercial features if the
    licence is open.
    """


class ICommercialExpiredJobSource(IProductNotificationJobSource,
                                  ExpirationSource):
    """An interface for creating `IThirtyDayCommercialExpirationJob`s."""
