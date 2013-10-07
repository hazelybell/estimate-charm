# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'BuildQueue',
    'BuildQueueSet',
    'specific_job_classes',
    ]

from collections import defaultdict
from datetime import (
    datetime,
    timedelta,
    )
from itertools import groupby
from operator import attrgetter

import pytz
from sqlobject import (
    BoolCol,
    ForeignKey,
    IntCol,
    IntervalCol,
    StringCol,
    )
from zope.component import getSiteManager
from zope.interface import implements

from lp.buildmaster.enums import BuildFarmJobType
from lp.buildmaster.interfaces.buildfarmjob import IBuildFarmJob
from lp.buildmaster.interfaces.buildqueue import (
    IBuildQueue,
    IBuildQueueSet,
    )
from lp.services.database.bulk import load_related
from lp.services.database.constants import DEFAULT
from lp.services.database.enumcol import EnumCol
from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import (
    SQLBase,
    sqlvalues,
    )
from lp.services.job.interfaces.job import JobStatus
from lp.services.job.model.job import Job
from lp.services.propertycache import (
    cachedproperty,
    get_property_cache,
    )


def normalize_virtualization(virtualized):
    """Jobs with NULL virtualization settings should be treated the
       same way as virtualized jobs."""
    return virtualized is None or virtualized


def specific_job_classes():
    """Job classes that may run on the build farm."""
    job_classes = dict()
    # Get all components that implement the `IBuildFarmJob` interface.
    components = getSiteManager()
    implementations = sorted(components.getUtilitiesFor(IBuildFarmJob))
    # The above yields a collection of 2-tuples where the first element
    # is the name of the `BuildFarmJobType` enum and the second element
    # is the implementing class respectively.
    for job_enum_name, job_class in implementations:
        job_enum = getattr(BuildFarmJobType, job_enum_name)
        job_classes[job_enum] = job_class

    return job_classes


def get_builder_data():
    """How many working builders are there, how are they configured?"""
    builder_data = """
        SELECT processor, virtualized, COUNT(id) FROM builder
        WHERE builderok = TRUE AND manual = FALSE
        GROUP BY processor, virtualized;
    """
    results = IStore(BuildQueue).execute(builder_data).get_all()
    builders_in_total = virtualized_total = 0

    builder_stats = defaultdict(int)
    for processor, virtualized, count in results:
        builders_in_total += count
        if virtualized:
            virtualized_total += count
        builder_stats[(processor, virtualized)] = count

    builder_stats[(None, True)] = virtualized_total
    # Jobs with a NULL virtualized flag should be treated the same as
    # jobs where virtualized=TRUE.
    builder_stats[(None, None)] = virtualized_total
    builder_stats[(None, False)] = builders_in_total - virtualized_total
    return builder_stats


class BuildQueue(SQLBase):
    implements(IBuildQueue)
    _table = "BuildQueue"
    _defaultOrder = "id"

    def __init__(self, job, job_type=DEFAULT,  estimated_duration=DEFAULT,
                 virtualized=DEFAULT, processor=DEFAULT, lastscore=None):
        super(BuildQueue, self).__init__(job_type=job_type, job=job,
            virtualized=virtualized, processor=processor,
            estimated_duration=estimated_duration, lastscore=lastscore)
        if lastscore is None and self.specific_job is not None:
            self.score()

    job = ForeignKey(dbName='job', foreignKey='Job', notNull=True)
    job_type = EnumCol(
        enum=BuildFarmJobType, notNull=True,
        default=BuildFarmJobType.PACKAGEBUILD, dbName='job_type')
    builder = ForeignKey(dbName='builder', foreignKey='Builder', default=None)
    logtail = StringCol(dbName='logtail', default=None)
    lastscore = IntCol(dbName='lastscore', default=0)
    manual = BoolCol(dbName='manual', default=False)
    estimated_duration = IntervalCol()
    processor = ForeignKey(dbName='processor', foreignKey='Processor')
    virtualized = BoolCol(dbName='virtualized')

    @cachedproperty
    def specific_job(self):
        """See `IBuildQueue`."""
        specific_class = specific_job_classes()[self.job_type]
        return specific_class.getByJob(self.job)

    def _clear_specific_job_cache(self):
        del get_property_cache(self).specific_job

    @staticmethod
    def preloadSpecificJobData(queues):
        key = attrgetter('job_type')
        for job_type, grouped_queues in groupby(queues, key=key):
            specific_class = specific_job_classes()[job_type]
            queue_subset = list(grouped_queues)
            job_subset = load_related(Job, queue_subset, ['jobID'])
            # We need to preload the build farm jobs early to avoid
            # the call to _set_build_farm_job to look up BuildFarmBuildJobs
            # one by one.
            specific_class.preloadBuildFarmJobs(job_subset)
            specific_jobs = list(specific_class.getByJobs(job_subset))
            if len(specific_jobs) == 0:
                continue
            specific_class.preloadJobsData(specific_jobs)
            specific_jobs_dict = dict(
                (specific_job.job, specific_job)
                    for specific_job in specific_jobs)
            for queue in queue_subset:
                cache = get_property_cache(queue)
                cache.specific_job = specific_jobs_dict[queue.job]

    @property
    def date_started(self):
        """See `IBuildQueue`."""
        return self.job.date_started

    @property
    def current_build_duration(self):
        """See `IBuildQueue`."""
        date_started = self.date_started
        if date_started is None:
            return None
        else:
            return self._now() - date_started

    def destroySelf(self):
        """Remove this record and associated job/specific_job."""
        job = self.job
        specific_job = self.specific_job
        builder = self.builder
        SQLBase.destroySelf(self)
        specific_job.cleanUp()
        job.destroySelf()
        if builder is not None:
            del get_property_cache(builder).currentjob
        self._clear_specific_job_cache()

    def manualScore(self, value):
        """See `IBuildQueue`."""
        self.lastscore = value
        self.manual = True

    def score(self):
        """See `IBuildQueue`."""
        if self.manual:
            return
        # Allow the `IBuildFarmJob` instance with the data/logic specific to
        # the job at hand to calculate the score as appropriate.
        self.lastscore = self.specific_job.score()

    def markAsBuilding(self, builder):
        """See `IBuildQueue`."""
        self.builder = builder
        if self.job.status != JobStatus.RUNNING:
            self.job.start()
        self.specific_job.jobStarted()
        if builder is not None:
            del get_property_cache(builder).currentjob

    def reset(self):
        """See `IBuildQueue`."""
        builder = self.builder
        self.builder = None
        if self.job.status != JobStatus.WAITING:
            self.job.queue()
        self.job.date_started = None
        self.job.date_finished = None
        self.logtail = None
        self.specific_job.jobReset()
        if builder is not None:
            del get_property_cache(builder).currentjob

    def cancel(self):
        """See `IBuildQueue`."""
        self.specific_job.jobCancel()
        self.destroySelf()

    def _getFreeBuildersCount(self, processor, virtualized):
        """How many builders capable of running jobs for the given processor
        and virtualization combination are idle/free at present?"""
        query = """
            SELECT COUNT(id) FROM builder
            WHERE
                builderok = TRUE AND manual = FALSE
                AND id NOT IN (
                    SELECT builder FROM BuildQueue WHERE builder IS NOT NULL)
                AND virtualized = %s
            """ % sqlvalues(normalize_virtualization(virtualized))
        if processor is not None:
            query += """
                AND processor = %s
            """ % sqlvalues(processor)
        result_set = IStore(BuildQueue).execute(query)
        free_builders = result_set.get_one()[0]
        return free_builders

    def _estimateTimeToNextBuilder(self):
        """Estimate time until next builder becomes available.

        For the purpose of estimating the dispatch time of the job of interest
        (JOI) we need to know how long it will take until the job at the head
        of JOI's queue is dispatched.

        There are two cases to consider here: the head job is

            - processor dependent: only builders with the matching
              processor/virtualization combination should be considered.
            - *not* processor dependent: all builders with the matching
              virtualization setting should be considered.

        :return: The estimated number of seconds untils a builder capable of
            running the head job becomes available.
        """
        head_job_platform = self._getHeadJobPlatform()

        # Return a zero delay if we still have free builders available for the
        # given platform/virtualization combination.
        free_builders = self._getFreeBuildersCount(*head_job_platform)
        if free_builders > 0:
            return 0

        head_job_processor, head_job_virtualized = head_job_platform

        now = self._now()
        delay_query = """
            SELECT MIN(
              CASE WHEN
                EXTRACT(EPOCH FROM
                  (BuildQueue.estimated_duration -
                   (((%s AT TIME ZONE 'UTC') - Job.date_started))))  >= 0
              THEN
                EXTRACT(EPOCH FROM
                  (BuildQueue.estimated_duration -
                   (((%s AT TIME ZONE 'UTC') - Job.date_started))))
              ELSE
                -- Assume that jobs that have overdrawn their estimated
                -- duration time budget will complete within 2 minutes.
                -- This is a wild guess but has worked well so far.
                --
                -- Please note that this is entirely innocuous i.e. if our
                -- guess is off nothing bad will happen but our estimate will
                -- not be as good as it could be.
                120
              END)
            FROM
                BuildQueue, Job, Builder
            WHERE
                BuildQueue.job = Job.id
                AND BuildQueue.builder = Builder.id
                AND Builder.manual = False
                AND Builder.builderok = True
                AND Job.status = %s
                AND Builder.virtualized = %s
            """ % sqlvalues(
                now, now, JobStatus.RUNNING,
                normalize_virtualization(head_job_virtualized))

        if head_job_processor is not None:
            # Only look at builders with specific processor types.
            delay_query += """
                AND Builder.processor = %s
                """ % sqlvalues(head_job_processor)

        result_set = IStore(BuildQueue).execute(delay_query)
        head_job_delay = result_set.get_one()[0]
        return (0 if head_job_delay is None else int(head_job_delay))

    def _getPendingJobsClauses(self):
        """WHERE clauses for pending job queries, used for dipatch time
        estimation."""
        virtualized = normalize_virtualization(self.virtualized)
        clauses = """
            BuildQueue.job = Job.id
            AND Job.status = %s
            AND (
                -- The score must be either above my score or the
                -- job must be older than me in cases where the
                -- score is equal.
                BuildQueue.lastscore > %s OR
                (BuildQueue.lastscore = %s AND Job.id < %s))
            -- The virtualized values either match or the job
            -- does not care about virtualization and the job
            -- of interest (JOI) is to be run on a virtual builder
            -- (we want to prevent the execution of untrusted code
            -- on native builders).
            AND COALESCE(buildqueue.virtualized, TRUE) = %s
            """ % sqlvalues(
                JobStatus.WAITING, self.lastscore, self.lastscore, self.job,
                virtualized)
        processor_clause = """
            AND (
                -- The processor values either match or the candidate
                -- job is processor-independent.
                buildqueue.processor = %s OR
                buildqueue.processor IS NULL)
            """ % sqlvalues(self.processor)
        # We don't care about processors if the estimation is for a
        # processor-independent job.
        if self.processor is not None:
            clauses += processor_clause
        return clauses

    def _getHeadJobPlatform(self):
        """Find the processor and virtualization setting for the head job.

        Among the jobs that compete with the job of interest (JOI) for
        builders and are queued ahead of it the head job is the one in pole
        position i.e. the one to be dispatched to a builder next.

        :return: A (processor, virtualized) tuple which is the head job's
        platform or None if the JOI is the head job.
        """
        my_platform = (
            getattr(self.processor, 'id', None),
            normalize_virtualization(self.virtualized))
        query = """
            SELECT
                processor,
                virtualized
            FROM
                BuildQueue, Job
            WHERE
            """
        query += self._getPendingJobsClauses()
        query += """
            ORDER BY lastscore DESC, job LIMIT 1
            """
        result = IStore(BuildQueue).execute(query).get_one()
        return (my_platform if result is None else result)

    def _estimateJobDelay(self, builder_stats):
        """Sum of estimated durations for *pending* jobs ahead in queue.

        For the purpose of estimating the dispatch time of the job of
        interest (JOI) we need to know the delay caused by all the pending
        jobs that are ahead of the JOI in the queue and that compete with it
        for builders.

        :param builder_stats: A dictionary with builder counts where the
            key is a (processor, virtualized) combination (aka "platform") and
            the value is the number of builders that can take on jobs
            requiring that combination.
        :return: An integer value holding the sum of delays (in seconds)
            caused by the jobs that are ahead of and competing with the JOI.
        """
        def jobs_compete_for_builders(a, b):
            """True if the two jobs compete for builders."""
            a_processor, a_virtualized = a
            b_processor, b_virtualized = b
            if a_processor is None or b_processor is None:
                # If either of the jobs is platform-independent then the two
                # jobs compete for the same builders if the virtualization
                # settings match.
                if a_virtualized == b_virtualized:
                    return True
            else:
                # Neither job is platform-independent, match processor and
                # virtualization settings.
                return a == b

        my_platform = (
            getattr(self.processor, 'id', None),
            normalize_virtualization(self.virtualized))
        query = """
            SELECT
                BuildQueue.processor,
                BuildQueue.virtualized,
                COUNT(BuildQueue.job),
                CAST(EXTRACT(
                    EPOCH FROM
                        SUM(BuildQueue.estimated_duration)) AS INTEGER)
            FROM
                BuildQueue, Job
            WHERE
            """
        query += self._getPendingJobsClauses()
        query += """
            GROUP BY BuildQueue.processor, BuildQueue.virtualized
            """

        delays_by_platform = IStore(BuildQueue).execute(query).get_all()

        # This will be used to capture per-platform delay totals.
        delays = defaultdict(int)
        # This will be used to capture per-platform job counts.
        job_counts = defaultdict(int)

        # Divide the estimated duration of the jobs as follows:
        #   - if a job is tied to a processor TP then divide the estimated
        #     duration of that job by the number of builders that target TP
        #     since only these can build the job.
        #   - if the job is processor-independent then divide its estimated
        #     duration by the total number of builders with the same
        #     virtualization setting because any one of them may run it.
        for processor, virtualized, job_count, delay in delays_by_platform:
            virtualized = normalize_virtualization(virtualized)
            platform = (processor, virtualized)
            builder_count = builder_stats.get(platform, 0)
            if builder_count == 0:
                # There is no builder that can run this job, ignore it
                # for the purpose of dispatch time estimation.
                continue

            if jobs_compete_for_builders(my_platform, platform):
                # The jobs that target the platform at hand compete with
                # the JOI for builders, add their delays.
                delays[platform] += delay
                job_counts[platform] += job_count

        sum_of_delays = 0
        # Now devide the delays based on a jobs/builders comparison.
        for platform, duration in delays.iteritems():
            jobs = job_counts[platform]
            builders = builder_stats[platform]
            # If there are less jobs than builders that can take them on,
            # the delays should be averaged/divided by the number of jobs.
            denominator = (jobs if jobs < builders else builders)
            if denominator > 1:
                duration = int(duration / float(denominator))

            sum_of_delays += duration

        return sum_of_delays

    def getEstimatedJobStartTime(self):
        """See `IBuildQueue`.

        The estimated dispatch time for the build farm job at hand is
        calculated from the following ingredients:
            * the start time for the head job (job at the
              head of the respective build queue)
            * the estimated build durations of all jobs that
              precede the job of interest (JOI) in the build queue
              (divided by the number of machines in the respective
              build pool)
        """
        # This method may only be invoked for pending jobs.
        if self.job.status != JobStatus.WAITING:
            raise AssertionError(
                "The start time is only estimated for pending jobs.")

        builder_stats = get_builder_data()
        platform = (getattr(self.processor, 'id', None), self.virtualized)
        if builder_stats[platform] == 0:
            # No builders that can run the job at hand
            #   -> no dispatch time estimation available.
            return None

        # Get the sum of the estimated run times for *pending* jobs that are
        # ahead of us in the queue.
        sum_of_delays = self._estimateJobDelay(builder_stats)

        # Get the minimum time duration until the next builder becomes
        # available.
        min_wait_time = self._estimateTimeToNextBuilder()

        # A job will not get dispatched in less than 5 seconds no matter what.
        start_time = max(5, min_wait_time + sum_of_delays)
        result = self._now() + timedelta(seconds=start_time)

        return result

    @staticmethod
    def _now():
        """Return current time (UTC).  Overridable for test purposes."""
        return datetime.now(pytz.UTC)


class BuildQueueSet(object):
    """Utility to deal with BuildQueue content class."""
    implements(IBuildQueueSet)

    def get(self, buildqueue_id):
        """See `IBuildQueueSet`."""
        return BuildQueue.get(buildqueue_id)

    def getByBuilder(self, builder):
        """See `IBuildQueueSet`."""
        return BuildQueue.selectOneBy(builder=builder)
