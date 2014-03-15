# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    "IProcessAcceptedBugsJob",
    "IProcessAcceptedBugsJobSource",
    ]

from lazr.restful.fields import Reference
from zope.interface import Attribute

from lp import _
from lp.registry.interfaces.distroseries import IDistroSeries
from lp.services.job.interfaces.job import (
    IJob,
    IJobSource,
    IRunnableJob,
    )
from lp.soyuz.interfaces.sourcepackagerelease import ISourcePackageRelease


class IProcessAcceptedBugsJob(IRunnableJob):
    """An `IJob` to close bugs for accepted package uploads."""

    job = Reference(
        schema=IJob, title=_("The common Job attributes"),
        required=True, readonly=True)

    distroseries = Reference(
        schema=IDistroSeries, title=_("Context distroseries"),
        required=True, readonly=True)

    sourcepackagerelease = Reference(
        schema=ISourcePackageRelease, title=_("Context sourcepackagerelease"),
        required=True, readonly=True)

    metadata = Attribute(_("A dict of data about the job."))

    bug_ids = Attribute(_("A list of bug IDs."))

    def getOperationDescription():
        """Return a description of the bug-closing operation."""


class IProcessAcceptedBugsJobSource(IJobSource):
    """A source for jobs to close bugs for accepted package uploads."""

    def create(distroseries, sourcepackagerelease, bug_ids):
        """Create a new `IProcessAcceptedBugsJob`.

        :param distroseries: A `IDistroSeries` for which to close bugs.
        :param sourcepackagerelease: An `ISourcePackageRelease` for which to
            close bugs.
        :param bug_ids: An iterable of bug IDs to close.
        """
