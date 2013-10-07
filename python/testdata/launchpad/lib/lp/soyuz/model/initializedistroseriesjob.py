# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    "InitializeDistroSeriesJob",
]

from zope.interface import (
    classProvides,
    implements,
    )

from lp.registry.model.distroseries import DistroSeries
from lp.services.config import config
from lp.services.database.interfaces import (
    IMasterStore,
    IStore,
    )
from lp.services.job.interfaces.job import JobStatus
from lp.services.job.model.job import Job
from lp.soyuz.interfaces.distributionjob import (
    DistributionJobType,
    IInitializeDistroSeriesJob,
    IInitializeDistroSeriesJobSource,
    InitializationCompleted,
    InitializationPending,
    )
from lp.soyuz.model.distributionjob import (
    DistributionJob,
    DistributionJobDerived,
    )
from lp.soyuz.model.packageset import Packageset
from lp.soyuz.scripts.initialize_distroseries import (
    InitializationError,
    InitializeDistroSeries,
    )


class InitializeDistroSeriesJob(DistributionJobDerived):

    implements(IInitializeDistroSeriesJob)

    class_job_type = DistributionJobType.INITIALIZE_SERIES
    classProvides(IInitializeDistroSeriesJobSource)

    user_error_types = (InitializationError,)

    config = config.IInitializeDistroSeriesJobSource

    @classmethod
    def create(cls, child, parents, arches=(), archindep_archtag=None,
               packagesets=(), rebuild=False, overlays=(),
               overlay_pockets=(), overlay_components=()):
        """Create a new `InitializeDistroSeriesJob`.

        :param child: The child `IDistroSeries` to initialize
        :param parents: An iterable of `IDistroSeries` of parents to
            initialize from.
        :param arches: An iterable of architecture tags which lists the
            architectures to enable in the child.
        :param packagesets: An iterable of `PackageSet` IDs from which to
            copy packages in parents.
        :param rebuild: A boolean to say whether the child should rebuild
            all the copied sources (if True), or to copy the parents'
            binaries (if False).
        :param overlays: An iterable of booleans corresponding exactly to
            each parent in the "parents" parameter.  Each boolean says
            whether this corresponding parent is an overlay for the child
            or not.  An overlay allows the child to use the parent's
            packages for build dependencies, and the overlay_pockets and
            overlay_components parameters dictate from where the
            dependencies may be used in the parent.
        :param overlay_pockets: An iterable of textual pocket names
            corresponding exactly to each parent.  The  name *must* be set
            if the corresponding overlays boolean is True.
        :param overlay_components: An iterable of textual component names
            corresponding exactly to each parent.  The  name *must* be set
            if the corresponding overlays boolean is True.
        """
        store = IMasterStore(DistributionJob)
        # Only one InitializeDistroSeriesJob can be present at a time.
        distribution_job = store.find(
            DistributionJob, DistributionJob.job_id == Job.id,
            DistributionJob.job_type == cls.class_job_type,
            DistributionJob.distroseries_id == child.id).one()
        if distribution_job is not None:
            if distribution_job.job.status == JobStatus.FAILED:
                # Delete the failed job to allow initialization of the series
                # to be rescheduled.
                store.remove(distribution_job)
                store.remove(distribution_job.job)
            elif distribution_job.job.status == JobStatus.COMPLETED:
                raise InitializationCompleted(cls(distribution_job))
            else:
                raise InitializationPending(cls(distribution_job))
        # Schedule the initialization.
        metadata = {
            'parents': parents,
            'arches': arches,
            'archindep_archtag': archindep_archtag,
            'packagesets': packagesets,
            'rebuild': rebuild,
            'overlays': overlays,
            'overlay_pockets': overlay_pockets,
            'overlay_components': overlay_components,
            }
        distribution_job = DistributionJob(
            child.distribution, child, cls.class_job_type, metadata)
        store.add(distribution_job)
        derived_job = cls(distribution_job)
        derived_job.celeryRunOnCommit()
        return derived_job

    @classmethod
    def get(cls, distroseries):
        """See `IInitializeDistroSeriesJob`."""
        distribution_job = IStore(DistributionJob).find(
            DistributionJob, DistributionJob.job_id == Job.id,
            DistributionJob.job_type == cls.class_job_type,
            DistributionJob.distroseries_id == distroseries.id).one()
        return None if distribution_job is None else cls(distribution_job)

    def __repr__(self):
        """Returns an informative representation of the job."""
        # This code assumes the job is referentially intact with good data,
        # or it will blow up.
        parts = "%s for" % self.__class__.__name__
        parts += " distribution: %s" % self.distribution.name
        parts += ", distroseries: %s" % self.distroseries.name
        parts += ", parent[overlay?/pockets/components]: "
        parents = []
        for i in range(len(self.overlays)):
            series = DistroSeries.get(self.parents[i])
            parents.append("%s[%s/%s/%s]" % (
                series.name,
                self.overlays[i],
                self.overlay_pockets[i],
                self.overlay_components[i]))
        parts += ",".join(parents)
        pkgsets = [
            IStore(Packageset).get(Packageset, int(pkgsetid)).name
            for pkgsetid in  self.packagesets]
        parts += ", architectures: %s" % (self.arches,)
        parts += ", archindep_archtag: %s" % self.archindep_archtag
        parts += ", packagesets: %s" % pkgsets
        parts += ", rebuild: %s" % self.rebuild
        return "<%s>" % parts

    @property
    def parents(self):
        return tuple(self.metadata['parents'])

    @property
    def overlays(self):
        if self.metadata['overlays'] is None:
            return ()
        else:
            return tuple(self.metadata['overlays'])

    @property
    def overlay_pockets(self):
        if self.metadata['overlay_pockets'] is None:
            return ()
        else:
            return tuple(self.metadata['overlay_pockets'])

    @property
    def overlay_components(self):
        if self.metadata['overlay_components'] is None:
            return ()
        else:
            return tuple(self.metadata['overlay_components'])

    @property
    def arches(self):
        if self.metadata['arches'] is None:
            return ()
        else:
            return tuple(self.metadata['arches'])

    @property
    def archindep_archtag(self):
        return self.metadata['archindep_archtag']

    @property
    def packagesets(self):
        if self.metadata['packagesets'] is None:
            return ()
        else:
            return tuple(self.metadata['packagesets'])

    @property
    def rebuild(self):
        return self.metadata['rebuild']

    @property
    def error_description(self):
        return self.metadata.get("error_description")

    def run(self):
        """See `IRunnableJob`."""
        ids = InitializeDistroSeries(
            self.distroseries, self.parents, self.arches,
            self.archindep_archtag, self.packagesets, self.rebuild,
            self.overlays, self.overlay_pockets, self.overlay_components)
        ids.check()
        ids.initialize()

    def notifyUserError(self, error):
        """Calls up and slso saves the error text in this job's metadata.

        See `BaseRunnableJob`.
        """
        # This method is called when error is an instance of
        # self.user_error_types.
        super(InitializeDistroSeriesJob, self).notifyUserError(error)
        self.metadata = dict(self.metadata, error_description=unicode(error))

    def getOopsVars(self):
        """See `IRunnableJob`."""
        vars = super(InitializeDistroSeriesJob, self).getOopsVars()
        vars.append(('parent_distroseries_ids', self.metadata.get("parents")))
        return vars
