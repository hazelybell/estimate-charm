# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""BuildPackageJob interfaces."""

__metaclass__ = type

__all__ = [
    'IBuildPackageJob',
    'COPY_ARCHIVE_SCORE_PENALTY',
    'PRIVATE_ARCHIVE_SCORE_BONUS',
    'SCORE_BY_COMPONENT',
    'SCORE_BY_POCKET',
    'SCORE_BY_URGENCY',
    ]

from lazr.restful.fields import Reference
from zope.schema import Int

from lp import _
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.interfaces.sourcepackage import SourcePackageUrgency
from lp.services.job.interfaces.job import IJob
from lp.soyuz.interfaces.binarypackagebuild import IBinaryPackageBuild
from lp.soyuz.interfaces.buildfarmbuildjob import IBuildFarmBuildJob


SCORE_BY_POCKET = {
    PackagePublishingPocket.BACKPORTS: 0,
    PackagePublishingPocket.RELEASE: 1500,
    PackagePublishingPocket.PROPOSED: 3000,
    PackagePublishingPocket.UPDATES: 3000,
    PackagePublishingPocket.SECURITY: 4500,
}


SCORE_BY_COMPONENT = {
    'multiverse': 0,
    'universe': 250,
    'restricted': 750,
    'main': 1000,
    'partner': 1250,
}


SCORE_BY_URGENCY = {
    SourcePackageUrgency.LOW: 5,
    SourcePackageUrgency.MEDIUM: 10,
    SourcePackageUrgency.HIGH: 15,
    SourcePackageUrgency.EMERGENCY: 20,
}


PRIVATE_ARCHIVE_SCORE_BONUS = 10000


# Rebuilds have usually a lower priority than other builds.
# This will be subtracted from the final score, usually taking it
# below 0, ensuring they are built only when nothing else is waiting
# in the build farm.
COPY_ARCHIVE_SCORE_PENALTY = 2600


class IBuildPackageJob(IBuildFarmBuildJob):
    """A read-only interface for build package jobs."""

    id = Int(title=_('ID'), required=True, readonly=True)

    job = Reference(
        IJob, title=_("Job"), required=True, readonly=True,
        description=_("Data common to all job types."))

    build = Reference(
        IBinaryPackageBuild, title=_("Build"),
        required=True, readonly=True,
        description=_("Build record associated with this job."))
