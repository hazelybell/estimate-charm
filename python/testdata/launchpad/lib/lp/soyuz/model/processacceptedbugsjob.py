# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    "close_bug_ids_for_sourcepackagerelease",
    "ProcessAcceptedBugsJob",
    ]

import logging

from storm.locals import (
    And,
    Int,
    JSON,
    Reference,
    )
from zope.component import getUtility
from zope.interface import (
    classProvides,
    implements,
    )

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.bugs.interfaces.bug import IBugSet
from lp.bugs.interfaces.bugtask import BugTaskStatus
from lp.registry.model.distroseries import DistroSeries
from lp.services.config import config
from lp.services.database.interfaces import (
    IMasterStore,
    IStore,
    )
from lp.services.database.stormbase import StormBase
from lp.services.job.model.job import Job
from lp.services.job.runner import BaseRunnableJob
from lp.soyuz.interfaces.processacceptedbugsjob import (
    IProcessAcceptedBugsJob,
    IProcessAcceptedBugsJobSource,
    )
from lp.soyuz.model.sourcepackagerelease import SourcePackageRelease


def close_bug_ids_for_sourcepackagerelease(distroseries, spr, bug_ids):
    bugs = list(getUtility(IBugSet).getByNumbers(bug_ids))
    janitor = getUtility(ILaunchpadCelebrities).janitor
    target = distroseries.getSourcePackage(spr.sourcepackagename)
    assert spr.changelog_entry is not None, (
        "New source uploads should have a changelog.")
    content = (
        "This bug was fixed in the package %s"
        "\n\n---------------\n%s" % (spr.title, spr.changelog_entry))

    for bug in bugs:
        edited_task = bug.setStatus(
            target=target, status=BugTaskStatus.FIXRELEASED, user=janitor)
        if edited_task is not None:
            bug.newMessage(
                owner=janitor,
                subject=bug.followup_subject(),
                content=content)


class ProcessAcceptedBugsJob(StormBase, BaseRunnableJob):
    """Base class for jobs to close bugs for accepted package uploads."""

    __storm_table__ = "ProcessAcceptedBugsJob"

    config = config.IProcessAcceptedBugsJobSource

    implements(IProcessAcceptedBugsJob)

    # Oddly, BaseRunnableJob inherits from BaseRunnableJobSource so this class
    # is both the factory for jobs (the "implements", above) and the source
    # for runnable jobs (not the constructor of the job source, the class
    # provides the IJobSource interface itself).
    classProvides(IProcessAcceptedBugsJobSource)

    # The Job table contains core job details.
    job_id = Int("job", primary=True)
    job = Reference(job_id, Job.id)

    distroseries_id = Int(name="distroseries")
    distroseries = Reference(distroseries_id, DistroSeries.id)

    sourcepackagerelease_id = Int(name="sourcepackagerelease")
    sourcepackagerelease = Reference(
        sourcepackagerelease_id, SourcePackageRelease.id)

    metadata = JSON('json_data')

    def __init__(self, distroseries, sourcepackagerelease, bug_ids):
        self.job = Job()
        self.distroseries = distroseries
        self.sourcepackagerelease = sourcepackagerelease
        self.metadata = {"bug_ids": list(bug_ids)}
        super(ProcessAcceptedBugsJob, self).__init__()

    @property
    def bug_ids(self):
        return self.metadata["bug_ids"]

    @classmethod
    def create(cls, distroseries, sourcepackagerelease, bug_ids):
        """See `IProcessAcceptedBugsJobSource`."""
        assert distroseries is not None, "No distroseries specified."
        assert sourcepackagerelease is not None, (
            "No sourcepackagerelease specified.")
        assert sourcepackagerelease.changelog_entry is not None, (
            "New source uploads should have a changelog.")
        assert bug_ids, "No bug IDs specified."
        job = ProcessAcceptedBugsJob(
            distroseries, sourcepackagerelease, bug_ids)
        IMasterStore(ProcessAcceptedBugsJob).add(job)
        job.celeryRunOnCommit()
        return job

    def getOperationDescription(self):
        """See `IRunnableJob`."""
        return "closing bugs for accepted package upload"

    def run(self):
        """See `IRunnableJob`."""
        logger = logging.getLogger()
        spr = self.sourcepackagerelease
        logger.info(
            "Closing bugs for %s/%s (%s)" %
            (spr.name, spr.version, self.distroseries))
        close_bug_ids_for_sourcepackagerelease(
            self.distroseries, spr, self.metadata["bug_ids"])

    def __repr__(self):
        """Returns an informative representation of the job."""
        parts = ["%s to close bugs [" % self.__class__.__name__]
        parts.append(", ".join(str(bug_id) for bug_id in self.bug_ids))
        spr = self.sourcepackagerelease
        parts.append(
            "] for %s/%s (%s)" % (spr.name, spr.version, self.distroseries))
        return "<%s>" % "".join(parts)

    @staticmethod
    def iterReady():
        """See `IJobSource`."""
        return IStore(ProcessAcceptedBugsJob).find((ProcessAcceptedBugsJob),
            And(ProcessAcceptedBugsJob.job == Job.id,
                Job.id.is_in(Job.ready_jobs)))

    def makeDerived(self):
        """Support UniversalJobSource.

        (Most Job ORM classes are generic, because their database table is
        used for several related job types.  Therefore, they have derived
        classes to implement the specific Job.

        ProcessAcceptedBugsJob implements the specific job, so its
        makeDerived returns itself.)
        """
        return self

    def getDBClass(self):
        return self.__class__
