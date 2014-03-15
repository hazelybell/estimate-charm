# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'BuildPackageJob',
    ]


from storm.locals import (
    Int,
    Reference,
    Storm,
    )
from zope.component import getUtility
from zope.interface import implements

from lp.buildmaster.enums import BuildStatus
from lp.buildmaster.model.buildfarmjob import BuildFarmJobOld
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.interfaces.series import SeriesStatus
from lp.services.database.bulk import load_related
from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import sqlvalues
from lp.soyuz.enums import PackagePublishingStatus
from lp.soyuz.interfaces.binarypackagebuild import IBinaryPackageBuildSet
from lp.soyuz.interfaces.buildpackagejob import (
    COPY_ARCHIVE_SCORE_PENALTY,
    IBuildPackageJob,
    PRIVATE_ARCHIVE_SCORE_BONUS,
    SCORE_BY_COMPONENT,
    SCORE_BY_POCKET,
    SCORE_BY_URGENCY,
    )
from lp.soyuz.interfaces.packageset import IPackagesetSet
from lp.soyuz.model.packageset import Packageset


class BuildPackageJob(BuildFarmJobOld, Storm):
    """See `IBuildPackageJob`."""
    implements(IBuildPackageJob)

    __storm_table__ = 'buildpackagejob'
    id = Int(primary=True)

    job_id = Int(name='job', allow_none=False)
    job = Reference(job_id, 'Job.id')

    build_id = Int(name='build', allow_none=False)
    build = Reference(build_id, 'BinaryPackageBuild.id')

    def __init__(self, build, job):
        self.build, self.job = build, job
        super(BuildPackageJob, self).__init__()

    @staticmethod
    def preloadBuildFarmJobs(jobs):
        from lp.soyuz.model.binarypackagebuild import BinaryPackageBuild
        return list(IStore(BinaryPackageBuild).find(
            BinaryPackageBuild,
            [BuildPackageJob.job_id.is_in([job.id for job in jobs]),
             BuildPackageJob.build_id == BinaryPackageBuild.id]))

    def score(self):
        """See `IBuildPackageJob`."""
        score = 0

        # Private builds get uber score.
        if self.build.archive.private:
            score += PRIVATE_ARCHIVE_SCORE_BONUS

        if self.build.archive.is_copy:
            score -= COPY_ARCHIVE_SCORE_PENALTY

        score += self.build.archive.relative_build_score

        # Language packs don't get any of the usual package-specific
        # score bumps, as they unduly delay the building of packages in
        # the main component otherwise.
        if self.build.source_package_release.section.name == 'translations':
            return score

        # Calculates the urgency-related part of the score.
        score += SCORE_BY_URGENCY[self.build.source_package_release.urgency]

        # Calculates the pocket-related part of the score.
        score += SCORE_BY_POCKET[self.build.pocket]

        # Calculates the component-related part of the score.
        score += SCORE_BY_COMPONENT.get(
            self.build.current_component.name, 0)

        # Calculates the package-set-related part of the score.
        package_sets = getUtility(IPackagesetSet).setsIncludingSource(
            self.build.source_package_release.name,
            distroseries=self.build.distro_series)
        if not self.build.archive.is_ppa and not package_sets.is_empty():
            score += package_sets.max(Packageset.relative_build_score)

        return score

    @property
    def processor(self):
        """See `IBuildFarmJob`."""
        return self.build.processor

    @property
    def virtualized(self):
        """See `IBuildFarmJob`."""
        return self.build.is_virtualized

    @classmethod
    def preloadJobsData(cls, jobs):
        from lp.soyuz.model.binarypackagebuild import BinaryPackageBuild
        from lp.services.job.model.job import Job
        load_related(Job, jobs, ['job_id'])
        builds = load_related(BinaryPackageBuild, jobs, ['build_id'])
        getUtility(IBinaryPackageBuildSet).preloadBuildsData(list(builds))

    @staticmethod
    def addCandidateSelectionCriteria(processor, virtualized):
        """See `IBuildFarmJob`."""
        private_statuses = (
            PackagePublishingStatus.PUBLISHED,
            PackagePublishingStatus.SUPERSEDED,
            PackagePublishingStatus.DELETED,
            )
        return """
            SELECT TRUE FROM Archive, BinaryPackageBuild, BuildPackageJob,
                             DistroArchSeries
            WHERE
            BuildPackageJob.job = Job.id AND
            BuildPackageJob.build = BinaryPackageBuild.id AND
            BinaryPackageBuild.distro_arch_series =
                DistroArchSeries.id AND
            BinaryPackageBuild.archive = Archive.id AND
            ((Archive.private IS TRUE AND
              EXISTS (
                  SELECT SourcePackagePublishingHistory.id
                  FROM SourcePackagePublishingHistory
                  WHERE
                      SourcePackagePublishingHistory.distroseries =
                         DistroArchSeries.distroseries AND
                      SourcePackagePublishingHistory.sourcepackagerelease =
                         BinaryPackageBuild.source_package_release AND
                      SourcePackagePublishingHistory.archive = Archive.id AND
                      SourcePackagePublishingHistory.status IN %s))
              OR
              archive.private IS FALSE) AND
            BinaryPackageBuild.status = %s
        """ % sqlvalues(private_statuses, BuildStatus.NEEDSBUILD)

    @staticmethod
    def postprocessCandidate(job, logger):
        """See `IBuildFarmJob`."""
        # Mark build records targeted to old source versions as SUPERSEDED
        # and build records target to SECURITY pocket or against an OBSOLETE
        # distroseries without a flag as FAILEDTOBUILD.
        # Builds in those situation should not be built because they will
        # be wasting build-time.  In the former case, there is already a
        # newer source; the latter case needs an overhaul of the way
        # security builds are handled (by copying from a PPA) to avoid
        # creating duplicate builds.
        build = getUtility(IBinaryPackageBuildSet).getByQueueEntry(job)
        distroseries = build.distro_arch_series.distroseries
        if (
            build.pocket == PackagePublishingPocket.SECURITY or
            (distroseries.status == SeriesStatus.OBSOLETE and
                not build.archive.permit_obsolete_series_uploads)):
            # We never build anything in the security pocket, or for obsolete
            # series without the flag set.
            logger.debug(
                "Build %s FAILEDTOBUILD, queue item %s REMOVED"
                % (build.id, job.id))
            build.updateStatus(BuildStatus.FAILEDTOBUILD)
            job.destroySelf()
            return False

        publication = build.current_source_publication
        if publication is None:
            # The build should be superseded if it no longer has a
            # current publishing record.
            logger.debug(
                "Build %s SUPERSEDED, queue item %s REMOVED"
                % (build.id, job.id))
            build.updateStatus(BuildStatus.SUPERSEDED)
            job.destroySelf()
            return False

        return True
