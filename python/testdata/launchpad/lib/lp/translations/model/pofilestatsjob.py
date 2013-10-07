# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Job for merging translations."""


__metaclass__ = type


__all__ = [
    'POFileStatsJob',
    ]

import logging

from storm.locals import (
    And,
    Int,
    Reference,
    )
from zope.component import getUtility
from zope.interface import (
    classProvides,
    implements,
    )

from lp.services.config import config
from lp.services.database.interfaces import IStore
from lp.services.database.stormbase import StormBase
from lp.services.job.interfaces.job import IRunnableJob
from lp.services.job.model.job import Job
from lp.services.job.runner import BaseRunnableJob
from lp.translations.interfaces.pofilestatsjob import IPOFileStatsJobSource
from lp.translations.interfaces.potemplate import IPOTemplateSet
from lp.translations.model.pofile import POFile


class POFileStatsJob(StormBase, BaseRunnableJob):
    """The details for a POFile status update job."""

    __storm_table__ = 'POFileStatsJob'

    config = config.IPOFileStatsJobSource

    # Instances of this class are runnable jobs.
    implements(IRunnableJob)

    # Oddly, BaseRunnableJob inherits from BaseRunnableJobSource so this class
    # is both the factory for jobs (the "implements", above) and the source
    # for runnable jobs (not the constructor of the job source, the class
    # provides the IJobSource interface itself).
    classProvides(IPOFileStatsJobSource)

    # The Job table contains core job details.
    job_id = Int('job', primary=True)
    job = Reference(job_id, Job.id)

    # This is the POFile which needs its statistics updated.
    pofile_id = Int('pofile')
    pofile = Reference(pofile_id, POFile.id)

    def __init__(self, pofile):
        self.job = Job()
        self.pofile = pofile
        super(POFileStatsJob, self).__init__()

    def getOperationDescription(self):
        """See `IRunnableJob`."""
        return 'updating POFile statistics'

    def run(self):
        """See `IRunnableJob`."""
        logger = logging.getLogger()
        logger.info('Updating statistics for %s' % self.pofile.title)
        self.pofile.updateStatistics()

        # Next we have to find any POFiles that share translations with the
        # above POFile so we can update their statistics too.  To do that we
        # first have to find the set of shared templates.
        subset = getUtility(IPOTemplateSet).getSharingSubset(
            product=self.pofile.potemplate.product,
            distribution=self.pofile.potemplate.distribution,
            sourcepackagename=self.pofile.potemplate.sourcepackagename)
        shared_templates = subset.getSharingPOTemplates(
            self.pofile.potemplate.name)
        # Now we have to find any POFiles that translate the shared templates
        # into the same language as the POFile this job is about.
        for template in shared_templates:
            pofile = template.getPOFileByLang(self.pofile.language.code)
            if pofile is None:
                continue
            pofile.updateStatistics()

    @staticmethod
    def iterReady():
        """See `IJobSource`."""
        return IStore(POFileStatsJob).find((POFileStatsJob),
            And(POFileStatsJob.job == Job.id,
                Job.id.is_in(Job.ready_jobs)))

    def makeDerived(self):
        """Support UniversalJobSource.

        (Most Job ORM classes are generic, because their database table is
        used for several related job types.  Therefore, they have derived
        classes to implement the specific Job.

        POFileStatsJob implements the specific job, so its makeDerived returns
        itself.)
        """
        return self

    def getDBClass(self):
        return self.__class__


def schedule(pofile):
    """Schedule a job to update a POFile's stats."""
    job = POFileStatsJob(pofile)
    job.celeryRunOnCommit()
    return job
