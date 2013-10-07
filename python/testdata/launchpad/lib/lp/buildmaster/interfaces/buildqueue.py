# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Build interfaces."""

__metaclass__ = type

__all__ = [
    'IBuildQueue',
    'IBuildQueueSet',
    ]

from lazr.restful.fields import Reference
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Bool,
    Choice,
    Datetime,
    Int,
    Text,
    Timedelta,
    )

from lp import _
from lp.buildmaster.enums import BuildFarmJobType
from lp.buildmaster.interfaces.builder import IBuilder
from lp.buildmaster.interfaces.buildfarmjob import IBuildFarmJob
from lp.services.job.interfaces.job import IJob
from lp.soyuz.interfaces.processor import IProcessor


class IBuildQueue(Interface):
    """A Launchpad Auto Build queue entry.

    This table contains work-in-progress in Buildd environment, as well as
    incoming jobs.

    It relates a pending Builds with an heuristic index (last_score) which
    is used to order build jobs in a proper way.

    When building (job dispatched) it also includes the responsible Builder
    (builder), the time it has started (buildstarted) and up to 2 Kbytes
    of the current processing log (logtail).
    """

    id = Attribute("Job identifier")
    builder = Reference(
        IBuilder, title=_("Builder"), required=True, readonly=True,
        description=_("The IBuilder instance processing this job"))
    logtail = Text(
        description=_("The current tail of the log of the job"))
    lastscore = Int(description=_("This job's score."))
    manual = Bool(
        description=_("Whether or not the job was manually scored."))
    processor = Reference(
        IProcessor, title=_("Processor"), required=False, readonly=True,
        description=_("The processor required by this build farm job."))
    virtualized = Bool(
        required=False,
        description=_(
            "The virtualization setting required by this build farm job."))

    job = Reference(
        IJob, title=_("Job"), required=True, readonly=True,
        description=_("Data common to all job types."))

    job_type = Choice(
        title=_('Job type'), required=True, vocabulary=BuildFarmJobType,
        description=_("The type of this job."))

    estimated_duration = Timedelta(
        title=_("Estimated Job Duration"), required=True,
        description=_("Estimated job duration interval."))

    current_build_duration = Timedelta(
        title=_("Current build duration"), required=False,
        description=_("Time spent building so far."))

    def manualScore(value):
        """Manually set a score value to a queue item and lock it."""

    def score():
        """The job score calculated for the job type in question."""

    def destroySelf():
        """Delete this entry from the database."""

    def markAsBuilding(builder):
        """Set this queue item to a 'building' state."""

    def reset():
        """Reset this job, so it can be re-dispatched."""

    def cancel():
        """Cancel this job, it will not be re-dispatched."""

    specific_job = Reference(
        IBuildFarmJob, title=_("Job"),
        description=_("Data and operations common to all build farm jobs."))

    date_started = Datetime(
        title=_('Start time'),
        description=_('Time when the job started.'))

    def getEstimatedJobStartTime():
        """Get the estimated start time for a pending build farm job.

        :return: a timestamp upon success or None on failure. None
            indicates that an estimated start time is not available.
        :raise: AssertionError when the build job is not in the
            `JobStatus.WAITING` state.
        """


class IBuildQueueSet(Interface):
    """Launchpad Auto Build queue set handler and auxiliary methods."""

    def get(buildqueue_id):
        """Return the `IBuildQueue` with the given id."""

    def getByBuilder(builder):
        """Return an IBuildQueue instance for a builder.

        Retrieve the only one possible entry being processed for a given
        builder. If not found, return None.
        """
