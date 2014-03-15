# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces for sharing jobs."""

__metaclass__ = type

__all__ = [
    'IRemoveArtifactSubscriptionsJob',
    'IRemoveArtifactSubscriptionsJobSource',
    'ISharingJob',
    'ISharingJobSource',
    ]

from zope.interface import Attribute
from zope.schema import (
    Int,
    Object,
    )

from lp import _
from lp.registry.interfaces.distribution import IDistribution
from lp.registry.interfaces.person import IPerson
from lp.registry.interfaces.product import IProduct
from lp.services.job.interfaces.job import (
    IJob,
    IJobSource,
    IRunnableJob,
    )


class ISharingJob(IRunnableJob):
    """A Job for sharing related tasks."""

    id = Int(
        title=_('DB ID'), required=True, readonly=True,
        description=_("The tracking number for this job."))

    job = Object(title=_('The common Job attributes'), schema=IJob,
        required=True)

    product = Object(
        title=_('The product the job is for'),
        schema=IProduct)

    distro = Object(
        title=_('The distribution the job is for'),
        schema=IDistribution)

    grantee = Object(
        title=_('The grantee the job is for'),
        schema=IPerson)

    metadata = Attribute('A dict of data about the job.')

    def destroySelf():
        """Destroy this object."""

    def getErrorRecipients(self):
        """See `BaseRunnableJob`."""

    def pillar():
        """Either product or distro, whichever is not None."""

    def requestor():
        """The person who initiated the job."""


class IRemoveArtifactSubscriptionsJob(ISharingJob):
    """Job to remove subscriptions to artifacts for which access is revoked.

    Invalid subscriptions for a specific bug are removed.
    """


class ISharingJobSource(IJobSource):
    """Base interface for acquiring ISharingJobs."""

    def create(pillar, grantee, metadata):
        """Create a new ISharingJob."""


class IRemoveArtifactSubscriptionsJobSource(ISharingJobSource):
    """An interface for acquiring IRemoveArtifactSubscriptionsJobs."""

    def create(requestor, artifacts=None, grantee=None, pillar=None,
               information_types=None):
        """Create a new job to remove subscriptions for the specified
        artifacts.

        Subscriptions for users who no longer have access to the artifacts
        are removed.
        """
