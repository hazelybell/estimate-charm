# Copyright 2010-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    "PackageCopyJob",
    "PlainPackageCopyJob",
    ]

import logging

from lazr.delegates import delegates
from lazr.jobrunner.jobrunner import SuspendJobException
from psycopg2.extensions import TransactionRollbackError
from storm.locals import (
    Int,
    JSON,
    Not,
    Reference,
    Unicode,
    )
import transaction
from zope.component import getUtility
from zope.interface import (
    classProvides,
    implements,
    )
from zope.security.proxy import removeSecurityProxy

from lp.app.errors import NotFoundError
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.registry.enums import DistroSeriesDifferenceStatus
from lp.registry.interfaces.distroseriesdifference import (
    IDistroSeriesDifferenceSource,
    )
from lp.registry.interfaces.distroseriesdifferencecomment import (
    IDistroSeriesDifferenceCommentSource,
    )
from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.interfaces.sourcepackagename import ISourcePackageNameSet
from lp.registry.model.distroseries import DistroSeries
from lp.services.config import config
from lp.services.database import bulk
from lp.services.database.decoratedresultset import DecoratedResultSet
from lp.services.database.enumcol import EnumCol
from lp.services.database.interfaces import (
    IMasterStore,
    IStore,
    )
from lp.services.database.stormbase import StormBase
from lp.services.job.interfaces.job import JobStatus
from lp.services.job.model.job import (
    EnumeratedSubclass,
    Job,
    )
from lp.services.job.runner import BaseRunnableJob
from lp.services.mail.sendmail import format_address_for_person
from lp.soyuz.adapters.overrides import (
    FromExistingOverridePolicy,
    SourceOverride,
    UnknownOverridePolicy,
    )
from lp.soyuz.enums import (
    ArchivePurpose,
    PackageCopyPolicy,
    )
from lp.soyuz.interfaces.archive import CannotCopy
from lp.soyuz.interfaces.component import IComponentSet
from lp.soyuz.interfaces.copypolicy import ICopyPolicy
from lp.soyuz.interfaces.packagecopyjob import (
    IPackageCopyJob,
    IPackageCopyJobSource,
    IPlainPackageCopyJob,
    IPlainPackageCopyJobSource,
    PackageCopyJobType,
    )
from lp.soyuz.interfaces.packagediff import PackageDiffAlreadyRequested
from lp.soyuz.interfaces.publishing import ISourcePackagePublishingHistory
from lp.soyuz.interfaces.queue import IPackageUploadSet
from lp.soyuz.interfaces.section import ISectionSet
from lp.soyuz.model.archive import Archive
from lp.soyuz.scripts.packagecopier import do_copy


class PackageCopyJob(StormBase):
    """Base class for package copying jobs."""

    implements(IPackageCopyJob)
    classProvides(IPackageCopyJobSource)

    __storm_table__ = 'PackageCopyJob'

    id = Int(primary=True)

    job_id = Int(name='job')
    job = Reference(job_id, Job.id)

    source_archive_id = Int(name='source_archive')
    source_archive = Reference(source_archive_id, Archive.id)

    target_archive_id = Int(name='target_archive')
    target_archive = Reference(target_archive_id, Archive.id)

    target_distroseries_id = Int(name='target_distroseries')
    target_distroseries = Reference(target_distroseries_id, DistroSeries.id)

    package_name = Unicode('package_name')
    copy_policy = EnumCol(enum=PackageCopyPolicy)

    job_type = EnumCol(enum=PackageCopyJobType, notNull=True)

    metadata = JSON('json_data')

    # Derived concrete classes.  The entire class gets one dict for
    # this; it's not meant to be on an instance.
    concrete_classes = {}

    @classmethod
    def registerConcreteClass(cls, new_class):
        """Register a concrete `IPackageCopyJob`-implementing class."""
        assert new_class.class_job_type not in cls.concrete_classes, (
            "Class %s is already registered." % new_class)
        cls.concrete_classes[new_class.class_job_type] = new_class

    @classmethod
    def wrap(cls, package_copy_job):
        """See `IPackageCopyJobSource`."""
        if package_copy_job is None:
            return None
        # Read job_type so You Don't Have To.  If any other code reads
        # job_type, that's probably a sign that the interfaces need more
        # work.
        job_type = removeSecurityProxy(package_copy_job).job_type
        concrete_class = cls.concrete_classes[job_type]
        return concrete_class(package_copy_job)

    @classmethod
    def getByID(cls, pcj_id):
        """See `IPackageCopyJobSource`."""
        return cls.wrap(IStore(PackageCopyJob).get(PackageCopyJob, pcj_id))

    def __init__(self, source_archive, target_archive, target_distroseries,
                 job_type, metadata, requester, package_name=None,
                 copy_policy=None):
        super(PackageCopyJob, self).__init__()
        self.job = Job()
        self.job.requester = requester
        self.job_type = job_type
        self.source_archive = source_archive
        self.target_archive = target_archive
        self.target_distroseries = target_distroseries
        self.package_name = unicode(package_name)
        self.copy_policy = copy_policy
        self.metadata = metadata

    @property
    def package_version(self):
        return self.metadata["package_version"]

    def extendMetadata(self, metadata_dict):
        """Add metadata_dict to the existing metadata."""
        existing = self.metadata
        existing.update(metadata_dict)
        self.metadata = existing

    @property
    def component_name(self):
        """See `IPackageCopyJob`."""
        return self.metadata.get("component_override")

    @property
    def section_name(self):
        """See `IPackageCopyJob`."""
        return self.metadata.get("section_override")

    def makeDerived(self):
        return PackageCopyJobDerived.makeSubclass(self)


class PackageCopyJobDerived(BaseRunnableJob):
    """Abstract class for deriving from PackageCopyJob."""

    __metaclass__ = EnumeratedSubclass

    delegates(IPackageCopyJob)

    def __init__(self, job):
        self.context = job
        self.logger = logging.getLogger()

    @classmethod
    def get(cls, job_id):
        """Get a job by id.

        :return: the PackageCopyJob with the specified id, as the current
            PackageCopyJobDerived subclass.
        :raises: NotFoundError if there is no job with the specified id, or
            its job_type does not match the desired subclass.
        """
        job = IStore(PackageCopyJob).get(PackageCopyJob, job_id)
        if job.job_type != cls.class_job_type:
            raise NotFoundError(
                'No object found with id %d and type %s' % (job_id,
                cls.class_job_type.title))
        return cls(job)

    @classmethod
    def iterReady(cls):
        """Iterate through all ready PackageCopyJobs.

        Even though it's slower, we repeat the query each time in order that
        very long queues of mass syncs can be pre-empted by other jobs.
        """
        seen = set()
        while True:
            jobs = IStore(PackageCopyJob).find(
                PackageCopyJob,
                PackageCopyJob.job_type == cls.class_job_type,
                PackageCopyJob.job == Job.id,
                Job.id.is_in(Job.ready_jobs),
                Not(Job.id.is_in(seen)))
            jobs.order_by(PackageCopyJob.copy_policy)
            job = jobs.first()
            if job is None:
                break
            seen.add(job.job_id)
            yield cls(job)

    def getOopsVars(self):
        """See `IRunnableJob`."""
        vars = super(PackageCopyJobDerived, self).getOopsVars()
        vars.extend([
            ('source_archive_id', self.context.source_archive_id),
            ('target_archive_id', self.context.target_archive_id),
            ('target_distroseries_id', self.context.target_distroseries_id),
            ('package_copy_job_id', self.context.id),
            ('package_copy_job_type', self.context.job_type.title),
            ])
        return vars

    def getOperationDescription(self):
        """See `IPlainPackageCopyJob`."""
        return "copying a package"

    def getErrorRecipients(self):
        """See `IPlainPackageCopyJob`."""
        return [format_address_for_person(self.requester)]

    @property
    def copy_policy(self):
        """See `PlainPackageCopyJob`."""
        return self.context.copy_policy


class PlainPackageCopyJob(PackageCopyJobDerived):
    """Job that copies a package from one archive to another."""
    # This job type serves in different places: it supports copying
    # packages between archives, but also the syncing of packages from
    # parents into a derived distroseries.  We may split these into
    # separate types at some point, but for now we (allenap, bigjools,
    # jtv) chose to keep it as one.

    implements(IPlainPackageCopyJob)

    class_job_type = PackageCopyJobType.PLAIN
    classProvides(IPlainPackageCopyJobSource)
    config = config.IPlainPackageCopyJobSource
    user_error_types = (CannotCopy,)
    # Raised when closing bugs ends up hitting another process and
    # deadlocking.
    retry_error_types = (TransactionRollbackError,)
    max_retries = 5

    @classmethod
    def _makeMetadata(cls, target_pocket, package_version,
                      include_binaries, sponsored=None, unembargo=False,
                      auto_approve=False, source_distroseries=None,
                      source_pocket=None, phased_update_percentage=None):
        """Produce a metadata dict for this job."""
        return {
            'target_pocket': target_pocket.value,
            'package_version': package_version,
            'include_binaries': bool(include_binaries),
            'sponsored': sponsored.name if sponsored else None,
            'unembargo': unembargo,
            'auto_approve': auto_approve,
            'source_distroseries':
                source_distroseries.name if source_distroseries else None,
            'source_pocket': source_pocket.value if source_pocket else None,
            'phased_update_percentage': phased_update_percentage,
        }

    @classmethod
    def create(cls, package_name, source_archive,
               target_archive, target_distroseries, target_pocket,
               include_binaries=False, package_version=None,
               copy_policy=PackageCopyPolicy.INSECURE, requester=None,
               sponsored=None, unembargo=False, auto_approve=False,
               source_distroseries=None, source_pocket=None,
               phased_update_percentage=None):
        """See `IPlainPackageCopyJobSource`."""
        assert package_version is not None, "No package version specified."
        assert requester is not None, "No requester specified."
        metadata = cls._makeMetadata(
            target_pocket, package_version, include_binaries, sponsored,
            unembargo, auto_approve, source_distroseries, source_pocket,
            phased_update_percentage)
        job = PackageCopyJob(
            job_type=cls.class_job_type,
            source_archive=source_archive,
            target_archive=target_archive,
            target_distroseries=target_distroseries,
            package_name=package_name,
            copy_policy=copy_policy,
            metadata=metadata,
            requester=requester)
        IMasterStore(PackageCopyJob).add(job)
        derived = cls(job)
        derived.celeryRunOnCommit()
        return derived

    @classmethod
    def _composeJobInsertionTuple(cls, copy_policy, include_binaries, job_id,
                                  copy_task, sponsored, unembargo,
                                  auto_approve):
        """Create an SQL fragment for inserting a job into the database.

        :return: A string representing an SQL tuple containing initializers
            for a `PackageCopyJob` in the database (minus `id`, which is
            assigned automatically).  Contents are escaped for use in SQL.
        """
        (
            package_name,
            package_version,
            source_archive,
            target_archive,
            target_distroseries,
            target_pocket,
        ) = copy_task
        metadata = cls._makeMetadata(
            target_pocket, package_version, include_binaries, sponsored,
            unembargo, auto_approve)
        data = (
            cls.class_job_type, target_distroseries, copy_policy,
            source_archive, target_archive, package_name, job_id,
            metadata)
        return data

    @classmethod
    def createMultiple(cls, copy_tasks, requester,
                       copy_policy=PackageCopyPolicy.INSECURE,
                       include_binaries=False, sponsored=None,
                       unembargo=False, auto_approve=False):
        """See `IPlainPackageCopyJobSource`."""
        store = IMasterStore(Job)
        job_ids = Job.createMultiple(store, len(copy_tasks), requester)
        job_contents = [
            cls._composeJobInsertionTuple(
                copy_policy, include_binaries, job_id, task, sponsored,
                unembargo, auto_approve)
            for job_id, task in zip(job_ids, copy_tasks)]
        return bulk.create(
                (PackageCopyJob.job_type, PackageCopyJob.target_distroseries,
                 PackageCopyJob.copy_policy, PackageCopyJob.source_archive,
                 PackageCopyJob.target_archive, PackageCopyJob.package_name,
                 PackageCopyJob.job_id, PackageCopyJob.metadata),
                job_contents, get_primary_keys=True)

    @classmethod
    def getActiveJobs(cls, target_archive):
        """See `IPlainPackageCopyJobSource`."""
        jobs = IStore(PackageCopyJob).find(
            PackageCopyJob,
            PackageCopyJob.job_type == cls.class_job_type,
            PackageCopyJob.target_archive == target_archive,
            Job.id == PackageCopyJob.job_id,
            Job._status == JobStatus.WAITING)
        jobs = jobs.order_by(PackageCopyJob.id)
        return DecoratedResultSet(jobs, cls)

    @classmethod
    def getPendingJobsForTargetSeries(cls, target_series):
        """Get upcoming jobs for `target_series`, ordered by age."""
        raw_jobs = IStore(PackageCopyJob).find(
            PackageCopyJob,
            Job.id == PackageCopyJob.job_id,
            PackageCopyJob.job_type == cls.class_job_type,
            PackageCopyJob.target_distroseries == target_series,
            Job._status.is_in(Job.PENDING_STATUSES))
        raw_jobs = raw_jobs.order_by(PackageCopyJob.id)
        return DecoratedResultSet(raw_jobs, cls)

    @classmethod
    def getPendingJobsPerPackage(cls, target_series):
        """See `IPlainPackageCopyJobSource`."""
        result = {}
        # Go through jobs in-order, picking the first matching job for
        # any (package, version) tuple.  Because of how
        # getPendingJobsForTargetSeries orders its results, the first
        # will be the oldest and thus presumably the first to finish.
        for job in cls.getPendingJobsForTargetSeries(target_series):
            result.setdefault(job.package_name, job)
        return result

    @classmethod
    def getIncompleteJobsForArchive(cls, archive):
        """See `IPlainPackageCopyJobSource`."""
        jobs = IStore(PackageCopyJob).find(
            PackageCopyJob,
            PackageCopyJob.target_archive == archive,
            PackageCopyJob.job_type == cls.class_job_type,
            Job.id == PackageCopyJob.job_id,
            Job._status.is_in(
                [JobStatus.WAITING, JobStatus.RUNNING, JobStatus.FAILED])
            )
        return DecoratedResultSet(jobs, cls)

    @property
    def target_pocket(self):
        return PackagePublishingPocket.items[self.metadata['target_pocket']]

    @property
    def include_binaries(self):
        return self.metadata['include_binaries']

    @property
    def error_message(self):
        """See `IPackageCopyJob`."""
        return self.metadata.get("error_message")

    @property
    def sponsored(self):
        name = self.metadata['sponsored']
        if name is None:
            return None
        return getUtility(IPersonSet).getByName(name)

    @property
    def unembargo(self):
        return self.metadata.get('unembargo', False)

    @property
    def auto_approve(self):
        return self.metadata.get('auto_approve', False)

    @property
    def source_distroseries(self):
        name = self.metadata.get('source_distroseries')
        if name is None:
            return None
        return self.source_archive.distribution[name]

    @property
    def source_pocket(self):
        name = self.metadata.get('source_pocket')
        if name is None:
            return None
        return PackagePublishingPocket.items[name]

    @property
    def phased_update_percentage(self):
        return self.metadata.get('phased_update_percentage')

    def _createPackageUpload(self, unapproved=False):
        pu = self.target_distroseries.createQueueEntry(
            pocket=self.target_pocket, archive=self.target_archive,
            package_copy_job=self.context)
        if unapproved:
            pu.setUnapproved()

    def addSourceOverride(self, override):
        """Add an `ISourceOverride` to the metadata."""
        metadata_changes = {}
        if override.component is not None:
            metadata_changes['component_override'] = override.component.name
        if override.section is not None:
            metadata_changes['section_override'] = override.section.name
        self.context.extendMetadata(metadata_changes)

    def setErrorMessage(self, message):
        """See `IPackageCopyJob`."""
        self.metadata["error_message"] = message

    def getSourceOverride(self):
        """Fetch an `ISourceOverride` from the metadata."""
        name = self.package_name
        component_name = self.component_name
        section_name = self.section_name
        source_package_name = getUtility(ISourcePackageNameSet)[name]
        try:
            component = getUtility(IComponentSet)[component_name]
        except NotFoundError:
            component = None
        try:
            section = getUtility(ISectionSet)[section_name]
        except NotFoundError:
            section = None

        return SourceOverride(source_package_name, component, section)

    def findSourcePublication(self):
        """Find the appropriate origin `ISourcePackagePublishingHistory`."""
        name = self.package_name
        version = self.package_version
        source_package = self.source_archive.getPublishedSources(
            name=name, version=version, exact_match=True,
            distroseries=self.source_distroseries,
            pocket=self.source_pocket).first()
        if source_package is None:
            raise CannotCopy("Package %r %r not found." % (name, version))
        return source_package

    def _checkPolicies(self, source_name, source_component=None,
                       auto_approve=False):
        # This helper will only return if it's safe to carry on with the
        # copy, otherwise it raises SuspendJobException to tell the job
        # runner to suspend the job.
        override_policy = FromExistingOverridePolicy()
        ancestry = override_policy.calculateSourceOverrides(
            self.target_archive, self.target_distroseries,
            self.target_pocket, [source_name])

        copy_policy = self.getPolicyImplementation()

        if len(ancestry) == 0:
            # We need to get the default overrides and put them in the
            # metadata.
            defaults = UnknownOverridePolicy().calculateSourceOverrides(
                self.target_archive, self.target_distroseries,
                self.target_pocket, [source_name], source_component)
            self.addSourceOverride(defaults[0])
            if auto_approve:
                auto_approve = self.target_archive.canAdministerQueue(
                    self.requester, self.getSourceOverride().component,
                    self.target_pocket, self.target_distroseries)

            approve_new = auto_approve or copy_policy.autoApproveNew(
                self.target_archive, self.target_distroseries,
                self.target_pocket)

            if not approve_new:
                # There's no existing package with the same name and the
                # policy says unapproved, so we poke it in the NEW queue.
                self._createPackageUpload()
                raise SuspendJobException
        else:
            # Put the existing override in the metadata.
            self.addSourceOverride(ancestry[0])
            if auto_approve:
                auto_approve = self.target_archive.canAdministerQueue(
                    self.requester, self.getSourceOverride().component,
                    self.target_pocket, self.target_distroseries)

        # The package is not new (it has ancestry) so check the copy
        # policy for existing packages.
        approve_existing = auto_approve or copy_policy.autoApprove(
            self.target_archive, self.target_distroseries, self.target_pocket)
        if not approve_existing:
            self._createPackageUpload(unapproved=True)
            raise SuspendJobException

    def _rejectPackageUpload(self):
        # Helper to find and reject any associated PackageUpload.
        pu = getUtility(IPackageUploadSet).getByPackageCopyJobIDs(
            [self.context.id]).any()
        if pu is not None:
            pu.setRejected()

    def notifyOops(self, oops):
        """See `IRunnableJob`."""
        if not self.error_message:
            transaction.abort()
            self.reportFailure(
                "Launchpad encountered an internal error while copying this"
                " package.  It was logged with id %s.  Sorry for the"
                " inconvenience." % oops["id"])
            transaction.commit()
        super(PlainPackageCopyJob, self).notifyOops(oops)

    def run(self):
        """See `IRunnableJob`."""
        try:
            self.attemptCopy()
        except CannotCopy as e:
            # Remember the target archive purpose, as otherwise aborting the
            # transaction will forget it.
            target_archive_purpose = self.target_archive.purpose
            self.logger.info("Job:\n%s\nraised CannotCopy:\n%s" % (self, e))
            self.abort()  # Abort the txn.
            self.reportFailure(unicode(e))

            # If there is an associated PackageUpload we need to reject it,
            # else it will sit in ACCEPTED forever.
            self._rejectPackageUpload()

            if target_archive_purpose == ArchivePurpose.PPA:
                # If copying to a PPA, commit the failure and re-raise the
                # exception.  We turn a copy failure into a job failure in
                # order that it can show up in the UI.
                transaction.commit()
                raise
            else:
                # Otherwise, rely on the job runner to do the final commit,
                # and do not consider a failure of a copy to be a failure of
                # the job.  We will normally have a DistroSeriesDifference
                # in this case.
                pass
        except SuspendJobException:
            raise
        except:
            # Abort work done so far, but make sure that we commit the
            # rejection to the PackageUpload.
            transaction.abort()
            self._rejectPackageUpload()
            transaction.commit()
            raise

    def attemptCopy(self):
        """Attempt to perform the copy.

        :raise CannotCopy: If the copy fails for a reason that the user
            can deal with.
        """
        reason = self.target_archive.checkUploadToPocket(
            self.target_distroseries, self.target_pocket,
            person=self.requester)
        if reason:
            # Wrap any forbidden-pocket error in CannotCopy.
            raise CannotCopy(unicode(reason))

        source_package = self.findSourcePublication()

        # If there's a PackageUpload associated with this job then this
        # job has just been released by an archive admin from the queue.
        # We don't need to check any policies, but the admin may have
        # set overrides which we will get from the job's metadata.
        pu = getUtility(IPackageUploadSet).getByPackageCopyJobIDs(
            [self.context.id]).any()
        if pu is None:
            source_name = getUtility(ISourcePackageNameSet)[self.package_name]
            self._checkPolicies(
                source_name, source_package.sourcepackagerelease.component,
                self.auto_approve)

        # The package is free to go right in, so just copy it now.
        ancestry = self.target_archive.getPublishedSources(
            name=self.package_name, distroseries=self.target_distroseries,
            pocket=self.target_pocket, exact_match=True)
        override = self.getSourceOverride()
        copy_policy = self.getPolicyImplementation()
        send_email = copy_policy.send_email(self.target_archive)
        copied_publications = do_copy(
            sources=[source_package], archive=self.target_archive,
            series=self.target_distroseries, pocket=self.target_pocket,
            include_binaries=self.include_binaries, check_permissions=True,
            person=self.requester, overrides=[override],
            send_email=send_email, announce_from_person=self.requester,
            sponsored=self.sponsored, packageupload=pu,
            unembargo=self.unembargo,
            phased_update_percentage=self.phased_update_percentage)

        # Add a PackageDiff for this new upload if it has ancestry.
        if copied_publications and not ancestry.is_empty():
            from_spr = None
            for publication in copied_publications:
                if ISourcePackagePublishingHistory.providedBy(publication):
                    from_spr = publication.sourcepackagerelease
                    break
            if from_spr:
                for ancestor in ancestry:
                    to_spr = ancestor.sourcepackagerelease
                    if from_spr != to_spr:
                        try:
                            to_spr.requestDiffTo(self.requester, from_spr)
                        except PackageDiffAlreadyRequested:
                            pass
                        break

        if pu is not None:
            # A PackageUpload will only exist if the copy job had to be
            # held in the queue because of policy/ancestry checks.  If one
            # does exist we need to make sure it gets moved to DONE.
            pu.setDone()

        if copied_publications:
            self.logger.debug(
                "Packages copied to %s:" % self.target_archive.displayname)
            for copy in copied_publications:
                self.logger.debug(copy.displayname)

    def abort(self):
        """Abort work."""
        transaction.abort()

    def findMatchingDSDs(self):
        """Find any `DistroSeriesDifference`s that this job might resolve."""
        dsd_source = getUtility(IDistroSeriesDifferenceSource)
        target_series = self.target_distroseries
        candidates = dsd_source.getForDistroSeries(
            distro_series=target_series, name_filter=self.package_name,
            status=DistroSeriesDifferenceStatus.NEEDS_ATTENTION)

        # The job doesn't know what distroseries a given package is
        # coming from, and the version number in the DSD may have
        # changed.  We can however filter out DSDs that are from
        # different distributions, based on the job's target archive.
        source_distro_id = self.source_archive.distributionID
        return [
            dsd
            for dsd in candidates
                if dsd.parent_series.distributionID == source_distro_id]

    def reportFailure(self, message):
        """Attempt to report failure to the user."""
        if self.target_archive.purpose != ArchivePurpose.PPA:
            dsds = self.findMatchingDSDs()
            comment_source = getUtility(IDistroSeriesDifferenceCommentSource)

            # Register the error comment in the name of the Janitor.  Not a
            # great choice, but we have no user identity to represent
            # Launchpad; it's far too costly to create one; and
            # impersonating the requester can be misleading and would also
            # involve extra bookkeeping.
            reporting_persona = getUtility(ILaunchpadCelebrities).janitor

            for dsd in dsds:
                comment_source.new(dsd, reporting_persona, message)
        else:
            self.setErrorMessage(message)

    def __repr__(self):
        """Returns an informative representation of the job."""
        parts = ["%s to copy" % self.__class__.__name__]
        if self.package_name is None:
            parts.append(" no package (!)")
        else:
            parts.append(" package %s" % self.package_name)
        parts.append(
            " from %s/%s" % (
                self.source_archive.distribution.name,
                self.source_archive.name))
        if self.source_pocket is not None:
            parts.append(", %s pocket," % self.source_pocket.name)
        if self.source_distroseries is not None:
            parts.append(" in %s" % self.source_distroseries)
        parts.append(
            " to %s/%s" % (
                self.target_archive.distribution.name,
                self.target_archive.name))
        parts.append(", %s pocket," % self.target_pocket.name)
        if self.target_distroseries is not None:
            parts.append(" in %s" % self.target_distroseries)
        if self.include_binaries:
            parts.append(", including binaries")
        return "<%s>" % "".join(parts)

    def getPolicyImplementation(self):
        """Return the `ICopyPolicy` applicable to this job."""
        return ICopyPolicy(self.copy_policy)


PackageCopyJob.registerConcreteClass(PlainPackageCopyJob)
