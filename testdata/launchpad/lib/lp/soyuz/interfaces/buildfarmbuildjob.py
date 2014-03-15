# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interface to support UI for most build-farm jobs."""

__metaclass__ = type
__all__ = [
    'IBuildFarmBuildJob'
    ]

from lazr.restful.fields import Reference

from lp import _
from lp.buildmaster.interfaces.buildfarmjob import IBuildFarmJobOld
from lp.soyuz.interfaces.binarypackagebuild import IBinaryPackageBuild


class IBuildFarmBuildJob(IBuildFarmJobOld):
    """An `IBuildFarmJob` with an `IBuild` reference."""
    build = Reference(
        IBinaryPackageBuild, title=_("Build"), required=True, readonly=True,
        description=_("Build record associated with this job."))
