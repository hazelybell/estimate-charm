# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'PackageUploadQueue',
    'PackageUpload',
    'PackageUploadBuild',
    'PackageUploadSource',
    'PackageUploadCustom',
    'PackageUploadSet',
    ]

from itertools import chain
import os
import shutil
import StringIO
import tempfile

from sqlobject import (
    ForeignKey,
    SQLMultipleJoin,
    SQLObjectNotFound,
    StringCol,
    )
from storm.locals import (
    And,
    Desc,
    Int,
    Join,
    List,
    Reference,
    SQL,
    Unicode,
    )
from storm.store import (
    EmptyResultSet,
    Store,
    )
from zope.component import getUtility
from zope.interface import implements

from lp.app.errors import NotFoundError
# XXX 2009-05-10 julian
# This should not import from archivepublisher, but to avoid
# that it needs a bit of redesigning here around the publication stuff.
from lp.archivepublisher.config import getPubConfig
from lp.archivepublisher.customupload import CustomUploadError
from lp.archivepublisher.debversion import Version
from lp.archiveuploader.tagfiles import parse_tagfile_content
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.model.sourcepackagename import SourcePackageName
from lp.services.auditor.client import AuditorClient
from lp.services.database.bulk import (
    load_referencing,
    load_related,
    )
from lp.services.database.constants import UTC_NOW
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.decoratedresultset import DecoratedResultSet
from lp.services.database.enumcol import EnumCol
from lp.services.database.interfaces import (
    IMasterStore,
    IStore,
    )
from lp.services.database.sqlbase import (
    SQLBase,
    sqlvalues,
    )
from lp.services.database.stormexpr import (
    Array,
    ArrayContains,
    )
from lp.services.features import getFeatureFlag
from lp.services.librarian.browser import ProxiedLibraryFileAlias
from lp.services.librarian.model import (
    LibraryFileAlias,
    LibraryFileContent,
    )
from lp.services.librarian.utils import copy_and_close
from lp.services.mail.signedmessage import strip_pgp_signature
from lp.services.propertycache import (
    cachedproperty,
    get_property_cache,
    )
from lp.soyuz.adapters.notification import notify
from lp.soyuz.enums import (
    PackageUploadCustomFormat,
    PackageUploadStatus,
    )
from lp.soyuz.interfaces.archive import (
    ComponentNotFound,
    MAIN_ARCHIVE_PURPOSES,
    PriorityNotFound,
    SectionNotFound,
    )
from lp.soyuz.interfaces.archivepermission import IArchivePermissionSet
from lp.soyuz.interfaces.component import IComponentSet
from lp.soyuz.interfaces.packagecopyjob import IPackageCopyJobSource
from lp.soyuz.interfaces.packagediff import IPackageDiffSet
from lp.soyuz.interfaces.packagetranslationsuploadjob import (
    IPackageTranslationsUploadJobSource,
    )
from lp.soyuz.interfaces.publishing import (
    IPublishingSet,
    name_priority_map,
    )
from lp.soyuz.interfaces.queue import (
    IPackageUpload,
    IPackageUploadBuild,
    IPackageUploadCustom,
    IPackageUploadQueue,
    IPackageUploadSet,
    IPackageUploadSource,
    NonBuildableSourceUploadError,
    QueueAdminUnauthorizedError,
    QueueBuildAcceptError,
    QueueInconsistentStateError,
    QueueSourceAcceptError,
    QueueStateWriteProtectedError,
    )
from lp.soyuz.interfaces.section import ISectionSet
from lp.soyuz.model.binarypackagename import BinaryPackageName
from lp.soyuz.model.binarypackagerelease import BinaryPackageRelease
from lp.soyuz.model.component import Component
from lp.soyuz.model.distroarchseries import DistroArchSeries
from lp.soyuz.model.section import Section

# There are imports below in PackageUploadCustom for various bits
# of the archivepublisher which cause circular import errors if they
# are placed here.


def debug(logger, msg):
    """Shorthand debug notation for publish() methods."""
    if logger is not None:
        logger.debug(msg)


class PassthroughStatusValue:
    """A wrapper to allow setting PackageUpload.status."""

    def __init__(self, value):
        self.value = value


def validate_status(self, attr, value):
    # Is the status wrapped in the special passthrough class?
    if isinstance(value, PassthroughStatusValue):
        return value.value

    if self._SO_creating:
        return value
    else:
        raise QueueStateWriteProtectedError(
            'Directly write on queue status is forbidden use the '
            'provided methods to set it.')


class PackageUploadQueue:

    implements(IPackageUploadQueue)

    def __init__(self, distroseries, status):
        self.distroseries = distroseries
        self.status = status


class PackageUpload(SQLBase):
    """A Queue item for the archive uploader."""

    implements(IPackageUpload)

    _defaultOrder = ['id']

    status = EnumCol(
        dbName='status', unique=False, notNull=True,
        default=PackageUploadStatus.NEW, schema=PackageUploadStatus,
        storm_validator=validate_status)

    date_created = UtcDateTimeCol(notNull=False, default=UTC_NOW)

    distroseries = ForeignKey(dbName="distroseries", foreignKey='DistroSeries')

    pocket = EnumCol(
        dbName='pocket', unique=False, notNull=True,
        schema=PackagePublishingPocket)

    changes_file_id = Int(name='changesfile')
    changesfile = Reference(changes_file_id, 'LibraryFileAlias.id')

    archive = ForeignKey(dbName="archive", foreignKey="Archive", notNull=True)

    signing_key = ForeignKey(
        foreignKey='GPGKey', dbName='signing_key', notNull=False)

    package_copy_job_id = Int(name='package_copy_job', allow_none=True)
    package_copy_job = Reference(package_copy_job_id, 'PackageCopyJob.id')

    searchable_names = StringCol(name='searchable_names', default='')
    searchable_versions = List(type=Unicode(), default_factory=list)

    # XXX julian 2007-05-06:
    # Sources should not be SQLMultipleJoin, there is only ever one
    # of each at most.

    # Join this table to the PackageUploadBuild and the
    # PackageUploadSource objects which are related.
    _sources = SQLMultipleJoin('PackageUploadSource',
                               joinColumn='packageupload')
    # Does not include source builds.
    _builds = SQLMultipleJoin('PackageUploadBuild',
                              joinColumn='packageupload')

    def __init__(self, *args, **kwargs):
        super(PackageUpload, self).__init__(*args, **kwargs)
        # searchable_{name,version}s are set for the other cases when
        # add{Source,Build,Custom} are called.
        if self.package_copy_job:
            self.addSearchableNames([self.package_copy_job.package_name])
            self.addSearchableVersions([self.package_copy_job.package_version])

    @cachedproperty
    def sources(self):
        return list(self._sources)

    def sourceFileUrls(self):
        """See `IPackageUpload`."""
        if self.contains_source:
            return [
                ProxiedLibraryFileAlias(file.libraryfile, self).http_url
                for file in self.sourcepackagerelease.files]
        else:
            return []

    @cachedproperty
    def builds(self):
        return list(self._builds)

    def binaryFileUrls(self):
        """See `IPackageUpload`."""
        return [
            ProxiedLibraryFileAlias(file.libraryfile, build.build).http_url
            for build in self.builds
            for bpr in build.build.binarypackages
            for file in bpr.files]

    @property
    def changes_file_url(self):
        if self.changesfile is not None:
            return ProxiedLibraryFileAlias(self.changesfile, self).http_url
        else:
            return None

    def getSourceBuild(self):
        #avoid circular import
        from lp.code.model.sourcepackagerecipebuild import (
            SourcePackageRecipeBuild)
        from lp.soyuz.model.sourcepackagerelease import SourcePackageRelease
        return Store.of(self).find(
            SourcePackageRecipeBuild,
            SourcePackageRecipeBuild.id ==
                SourcePackageRelease.source_package_recipe_build_id,
            SourcePackageRelease.id ==
            PackageUploadSource.sourcepackagereleaseID,
            PackageUploadSource.packageupload == self.id).one()

    # Also the custom files associated with the build.
    _customfiles = SQLMultipleJoin('PackageUploadCustom',
                                   joinColumn='packageupload')

    @cachedproperty
    def customfiles(self):
        return list(self._customfiles)

    @property
    def custom_file_urls(self):
        """See `IPackageUpload`."""
        return tuple(
            ProxiedLibraryFileAlias(file.libraryfilealias, self).http_url
            for file in self.customfiles)

    def customFileUrls(self):
        """See `IPackageUpload`."""
        return self.custom_file_urls

    def getBinaryProperties(self):
        """See `IPackageUpload`."""
        properties = list(chain.from_iterable(
            build.binaries for build in self.builds))
        for file in self.customfiles:
            properties.append({
                "name": file.libraryfilealias.filename,
                "customformat": file.customformat.title,
                })
        return properties

    @property
    def copy_source_archive(self):
        """See `IPackageUpload`."""
        if self.package_copy_job_id is not None:
            return self.package_copy_job.source_archive
        else:
            return None

    def getFileByName(self, filename):
        """See `IPackageUpload`."""
        if (self.changesfile is not None and
            self.changesfile.filename == filename):
            return self.changesfile

        if self.sourcepackagerelease is not None:
            try:
                return self.sourcepackagerelease.getFileByName(filename)
            except NotFoundError:
                pass

        custom = Store.of(self).find(
            PackageUploadCustom,
            PackageUploadCustom.packageupload == self.id,
            LibraryFileAlias.id ==
                PackageUploadCustom.libraryfilealiasID,
            LibraryFileAlias.filename == filename).one()
        if custom is not None:
            return custom.libraryfilealias

        raise NotFoundError(filename)

    def setUnapproved(self):
        """See `IPackageUpload`."""
        if self.status != PackageUploadStatus.NEW:
            raise QueueInconsistentStateError(
                'Can not set modified queue items to UNAPPROVED.')
        self.status = PassthroughStatusValue(PackageUploadStatus.UNAPPROVED)

    def setAccepted(self):
        """See `IPackageUpload`."""
        # Explode if something wrong like warty/RELEASE pass through
        # NascentUpload/UploadPolicies checks for 'ubuntu' main distro.
        assert self.archive.canModifySuite(self.distroseries, self.pocket), (
            "Not permitted acceptance in the %s pocket in a "
            "series in the '%s' state." % (
            self.pocket.name, self.distroseries.status.name))

        if self.status not in (
                PackageUploadStatus.NEW, PackageUploadStatus.UNAPPROVED,
                PackageUploadStatus.REJECTED):
            raise QueueInconsistentStateError(
                'Unable to accept queue item due to status.')

        for source in self.sources:
            source.verifyBeforeAccept()
            # if something goes wrong we will raise an exception
            # (QueueSourceAcceptError) before setting any value.
            # Mask the error with state-machine default exception
            try:
                source.checkComponentAndSection()
            except QueueSourceAcceptError as info:
                raise QueueInconsistentStateError(info)

        self._checkForBinariesinDestinationArchive(
            [queue_build.build for queue_build in self.builds])
        for queue_build in self.builds:
            try:
                queue_build.checkComponentAndSection()
            except QueueBuildAcceptError as info:
                raise QueueInconsistentStateError(info)

        # if the previous checks applied and pass we do set the value
        self.status = PassthroughStatusValue(PackageUploadStatus.ACCEPTED)

    def _checkForBinariesinDestinationArchive(self, builds):
        """
        Check for existing binaries (in destination archive) for all binary
        uploads to be accepted.

        Before accepting binary uploads we check whether any of the binaries
        already exists in the destination archive and raise an exception
        (QueueInconsistentStateError) if this is the case.

        The only way to find pre-existing binaries is to match on binary
        package file names.
        """
        if len(builds) == 0:
            return

        # Collects the binary file names for all builds.
        inner_query = """
            SELECT DISTINCT lfa.filename
            FROM
                binarypackagefile bpf, binarypackagerelease bpr,
                libraryfilealias lfa
            WHERE
                bpr.build IN %s
                AND bpf.binarypackagerelease = bpr.id
                AND bpf.libraryfile = lfa.id
        """ % sqlvalues([build.id for build in builds])

        # Check whether any of the binary file names have already been
        # published in the destination archive.
        query = """
            SELECT DISTINCT lfa.filename
            FROM
                binarypackagefile bpf, binarypackagepublishinghistory bpph,
                distroarchseries das, distroseries ds, libraryfilealias lfa
            WHERE
                bpph.archive = %s
                AND bpph.distroarchseries = das.id
                AND bpph.dateremoved IS NULL
                AND das.distroseries = ds.id
                AND ds.distribution = %s
                AND bpph.binarypackagerelease = bpf.binarypackagerelease
                AND bpf.libraryfile = lfa.id
                AND lfa.filename IN (%%s)
        """ % sqlvalues(self.archive, self.distroseries.distribution)
        # Inject the inner query.
        query %= inner_query

        store = Store.of(self)
        result_set = store.execute(query)
        known_filenames = [row[0] for row in result_set.get_all()]

        # Do any of the files to be uploaded already exist in the destination
        # archive?
        if len(known_filenames) > 0:
            filename_list = "\n\t%s".join(
                [filename for filename in known_filenames])
            raise QueueInconsistentStateError(
                'The following files are already published in %s:\n%s' % (
                    self.archive.displayname, filename_list))

    def setDone(self):
        """See `IPackageUpload`."""
        if self.status == PackageUploadStatus.DONE:
            raise QueueInconsistentStateError('Queue item already done')
        self.status = PassthroughStatusValue(PackageUploadStatus.DONE)

    def setRejected(self):
        """See `IPackageUpload`."""
        if self.status not in (
                PackageUploadStatus.NEW, PackageUploadStatus.UNAPPROVED,
                PackageUploadStatus.ACCEPTED):
            raise QueueInconsistentStateError(
                'Unable to reject queue item due to status.')
        self.status = PassthroughStatusValue(PackageUploadStatus.REJECTED)

    def _closeBugs(self, changesfile_path, logger=None):
        """Close bugs for a just-accepted source.

        :param changesfile_path: path to the context changesfile.
        :param logger: optional context Logger object (used on DEBUG level);

        It does not close bugs for PPA sources.
        """
        from lp.soyuz.scripts.processaccepted import close_bugs_for_queue_item

        if self.isPPA():
            debug(logger, "Not closing bugs for PPA source.")
            return

        debug(logger, "Closing bugs.")
        changesfile_object = open(changesfile_path, 'r')
        close_bugs_for_queue_item(
            self, changesfile_object=changesfile_object)
        changesfile_object.close()

    def _validateBuildsForSource(self, sourcepackagerelease, builds):
        """Check if the sourcepackagerelease generates at least one build.

        :raise NonBuildableSourceUploadError: when the uploaded source
            doesn't result in any builds in its targeted distroseries.
        """
        if len(builds) == 0 and self.isPPA():
            raise NonBuildableSourceUploadError(
                "Cannot build any of the architectures requested: %s" %
                sourcepackagerelease.architecturehintlist)

    def _giveKarma(self):
        """Assign karma as appropriate for an accepted upload."""
        # Give some karma to the uploader for source uploads only.
        if not bool(self.sources):
            return

        changed_by = self.sources[0].sourcepackagerelease.creator
        if self.signing_key is not None:
            uploader = self.signing_key.owner
        else:
            uploader = None

        if self.archive.is_ppa:
            main_karma_action = 'ppauploadaccepted'
        else:
            main_karma_action = 'distributionuploadaccepted'

        distribution = self.distroseries.distribution
        sourcepackagename = self.sources[
            0].sourcepackagerelease.sourcepackagename

        # The package creator always gets his karma.
        changed_by.assignKarma(
            main_karma_action, distribution=distribution,
            sourcepackagename=sourcepackagename)

        if self.archive.is_ppa:
            return

        # If a sponsor was involved, give him some too.
        if uploader is not None and changed_by != uploader:
            uploader.assignKarma(
                'sponsoruploadaccepted', distribution=distribution,
                sourcepackagename=sourcepackagename)

    def acceptFromUploader(self, changesfile_path, logger=None):
        """See `IPackageUpload`."""
        debug(logger, "Setting it to ACCEPTED")
        self.setAccepted()

        # If it is a pure-source upload we can further process it
        # in order to have a pending publishing record in place.
        # This change is based on discussions for bug #77853 and aims
        # to fix a deficiency on published file lookup system.
        if not self._isSingleSourceUpload():
            return

        debug(logger, "Creating PENDING publishing record.")
        [pub_source] = self.realiseUpload()
        builds = pub_source.createMissingBuilds(logger=logger)
        self._validateBuildsForSource(pub_source.sourcepackagerelease, builds)
        self._closeBugs(changesfile_path, logger)
        self._giveKarma()

    def _acceptSyncFromQueue(self):
        """Accept a sync upload from the queue."""
        # Circular imports :(
        from lp.soyuz.model.packagecopyjob import PlainPackageCopyJob

        assert self.package_copy_job is not None, (
            "This method is for copy-job uploads only.")

        if self.status == PackageUploadStatus.REJECTED:
            raise QueueInconsistentStateError(
                "Can't resurrect rejected syncs")

        # Release the job hounds, Smithers.
        self.setAccepted()
        job = PlainPackageCopyJob.get(self.package_copy_job_id)
        job.resume()
        job.celeryRunOnCommit()
        # The copy job will send emails as appropriate.  We don't
        # need to worry about closing bugs from syncs, although we
        # should probably give karma but that needs more work to
        # fix here.

    def _acceptNonSyncFromQueue(self, logger=None, dry_run=False):
        """Accept a "regular" upload from the queue.

        This is the normal case, for uploads that are not delayed and are not
        attached to package copy jobs.
        """
        from lp.soyuz.scripts.processaccepted import close_bugs_for_queue_item

        assert self.package_copy_job is None, (
            "This method is not for copy-job uploads.")
        assert self.changesfile is not None, (
            "Obsolete delayed copies can no longer be accepted. Repeat the "
            "copy operation instead.")

        self.setAccepted()

        changes_file_object = StringIO.StringIO(self.changesfile.read())
        # We explicitly allow unsigned uploads here since the .changes file
        # is pulled from the librarian which are stripped of their
        # signature just before being stored.
        self.notify(
            logger=logger, dry_run=dry_run,
            changes_file_object=changes_file_object)
        self.syncUpdate()

        # If this is a single source upload we can create the
        # publishing records now so that the user doesn't have to
        # wait for a publisher cycle (which calls process-accepted
        # to do this).
        if self._isSingleSourceUpload():
            [pub_source] = self.realiseUpload()
            builds = pub_source.createMissingBuilds()
            self._validateBuildsForSource(
                pub_source.sourcepackagerelease, builds)

        # When accepting packages, we must also check the changes file
        # for bugs to close automatically.
        close_bugs_for_queue_item(self)

        # Give some karma!
        self._giveKarma()

    def acceptFromQueue(self, logger=None, dry_run=False, user=None):
        """See `IPackageUpload`."""
        if self.package_copy_job is None:
            self._acceptNonSyncFromQueue(logger, dry_run)
        else:
            self._acceptSyncFromQueue()
        if bool(getFeatureFlag('auditor.enabled')):
            client = AuditorClient()
            client.send(self, 'packageupload-accepted', user)

    def rejectFromQueue(self, user, logger=None, dry_run=False, comment=None):
        """See `IPackageUpload`."""
        self.setRejected()
        if self.package_copy_job is not None:
            # Circular imports :(
            from lp.soyuz.model.packagecopyjob import PlainPackageCopyJob
            job = PlainPackageCopyJob.get(self.package_copy_job_id)
            # Do the state transition dance.
            job.queue()
            job.start()
            job.fail()
            # This possibly should be sending a rejection email but I
            # don't think we need them for sync rejections.
            return

        if self.changesfile is None:
            changes_file_object = None
        else:
            changes_file_object = StringIO.StringIO(self.changesfile.read())
        if comment:
            summary_text = "Rejected by %s: %s" % (user.displayname, comment)
        else:
            summary_text = "Rejected by %s." % user.displayname
        # We allow unsigned uploads since they come from the librarian,
        # which are now stored unsigned.
        self.notify(
            logger=logger, dry_run=dry_run,
            changes_file_object=changes_file_object, summary_text=summary_text)
        self.syncUpdate()
        if bool(getFeatureFlag('auditor.enabled')):
            client = AuditorClient()
            client.send(self, 'packageupload-rejected', user)

    def _isSingleSourceUpload(self):
        """Return True if this upload contains only a single source."""
        return ((len(self.sources) == 1) and
                (not bool(self.builds)) and
                (not bool(self.customfiles)))

    # XXX cprov 2006-03-14: Following properties should be redesigned to
    # reduce the duplicated code.
    @cachedproperty
    def contains_source(self):
        """See `IPackageUpload`."""
        return bool(self.sources)

    @cachedproperty
    def contains_build(self):
        """See `IPackageUpload`."""
        return bool(self.builds)

    @cachedproperty
    def contains_copy(self):
        """See `IPackageUpload`."""
        return self.package_copy_job_id is not None

    @cachedproperty
    def from_build(self):
        return bool(self.builds) or self.getSourceBuild()

    @cachedproperty
    def _customFormats(self):
        """Return the custom upload formats contained in this upload."""
        return [custom.customformat for custom in self.customfiles]

    @cachedproperty
    def contains_installer(self):
        """See `IPackageUpload`."""
        return (PackageUploadCustomFormat.DEBIAN_INSTALLER
                in self._customFormats)

    @cachedproperty
    def contains_translation(self):
        """See `IPackageUpload`."""
        return (PackageUploadCustomFormat.ROSETTA_TRANSLATIONS
                in self._customFormats)

    @cachedproperty
    def contains_upgrader(self):
        """See `IPackageUpload`."""
        return PackageUploadCustomFormat.DIST_UPGRADER in self._customFormats

    @cachedproperty
    def contains_ddtp(self):
        """See `IPackageUpload`."""
        return PackageUploadCustomFormat.DDTP_TARBALL in self._customFormats

    @cachedproperty
    def contains_uefi(self):
        """See `IPackageUpload`."""
        return PackageUploadCustomFormat.UEFI in self._customFormats

    @property
    def package_name(self):
        """See `IPackageUpload`."""
        if self.package_copy_job_id is not None:
            return self.package_copy_job.package_name
        elif self.sourcepackagerelease is not None:
            return self.sourcepackagerelease.sourcepackagename.name
        else:
            return None

    @property
    def package_version(self):
        """See `IPackageUpload`."""
        if self.package_copy_job_id is not None:
            return self.package_copy_job.package_version
        elif self.sourcepackagerelease is not None:
            return self.sourcepackagerelease.version
        else:
            return None

    @property
    def component_name(self):
        """See `IPackageUpload`."""
        if self.package_copy_job_id is not None:
            return self.package_copy_job.component_name
        elif self.contains_source:
            return self.sourcepackagerelease.component.name
        else:
            return None

    @property
    def section_name(self):
        """See `IPackageUpload`."""
        if self.package_copy_job_id is not None:
            return self.package_copy_job.section_name
        elif self.contains_source:
            return self.sourcepackagerelease.section.name
        else:
            return None

    @cachedproperty
    def displayname(self):
        """See `IPackageUpload`."""
        names = []
        if self.contains_source or self.package_copy_job_id is not None:
            names.append(self.package_name)
        for queue_build in self.builds:
            names.append(queue_build.build.source_package_release.name)
        for queue_custom in self.customfiles:
            names.append(queue_custom.libraryfilealias.filename)
        # Make sure the list items have a whitespace separator so
        # that they can be wrapped in table cells in the UI.
        return ", ".join(names)

    @cachedproperty
    def displayarchs(self):
        """See `IPackageUpload`"""
        archs = []
        if self.package_copy_job_id is not None:
            archs.append('sync')
        if self.contains_source:
            archs.append('source')
        for queue_build in self.builds:
            archs.append(queue_build.build.distro_arch_series.architecturetag)
        for queue_custom in self.customfiles:
            archs.append(queue_custom.customformat.title)
        return ", ".join(archs)

    @cachedproperty
    def displayversion(self):
        """See `IPackageUpload`"""
        package_version = self.package_version
        if package_version is not None:
            return package_version
        elif self.customfiles:
            return '-'
        else:
            return None

    @cachedproperty
    def sourcepackagerelease(self):
        """See `IPackageUpload`."""
        if self.contains_source:
            return self.sources[0].sourcepackagerelease
        elif self.contains_build:
            return self.builds[0].build.source_package_release
        else:
            return None

    def realiseUpload(self, logger=None):
        """See `IPackageUpload`."""
        if self.package_copy_job is not None:
            # PCJs are "realised" in the job runner,
            # which creates publishing records using the packagecopier.
            # Because the process-accepted script calls realiseUpload for
            # any outstanding uploads in the ACCEPTED state we need to skip
            # them here.  The runner is also responsible for calling
            # setDone().
            return
        assert self.status == PackageUploadStatus.ACCEPTED, (
            "Can not publish a non-ACCEPTED queue record (%s)" % self.id)
        # Explode if something wrong like warty/RELEASE pass through
        # NascentUpload/UploadPolicies checks
        assert self.archive.canModifySuite(self.distroseries, self.pocket), (
            "Not permitted to publish to the %s pocket in a "
            "series in the '%s' state." % (
            self.pocket.name, self.distroseries.status.name))

        publishing_records = []
        # In realising an upload we first load all the sources into
        # the publishing tables, then the binaries, then we attempt
        # to publish the custom objects.
        for queue_source in self.sources:
            queue_source.verifyBeforePublish()
            publishing_records.append(queue_source.publish(logger))
        for queue_build in self.builds:
            publishing_records.extend(queue_build.publish(logger))
        for customfile in self.customfiles:
            try:
                customfile.publish(logger)
            except CustomUploadError as e:
                if logger is not None:
                    logger.error("Queue item ignored: %s" % e)
                    return []

        self.setDone()

        return publishing_records

    def _appendSearchables(self, existing, new):
        return sorted(filter(None, set(existing) | set(new)))

    def addSearchableNames(self, names):
        self.searchable_names = ' '.join(
            self._appendSearchables(self.searchable_names.split(' '), names))

    def addSearchableVersions(self, versions):
        self.searchable_versions = self._appendSearchables(
            self.searchable_versions, versions)

    def addSource(self, spr):
        """See `IPackageUpload`."""
        self.addSearchableNames([spr.name])
        self.addSearchableVersions([spr.version])
        pus = PackageUploadSource(
            packageupload=self, sourcepackagerelease=spr.id)
        Store.of(self).flush()
        del get_property_cache(self).sources
        return pus

    def addBuild(self, build):
        """See `IPackageUpload`."""
        names = [build.source_package_release.name]
        versions = []
        for bpr in build.binarypackages:
            names.append(bpr.name)
            versions.append(bpr.version)
        self.addSearchableNames(names)
        self.addSearchableVersions(versions)
        pub = PackageUploadBuild(packageupload=self, build=build.id)
        Store.of(self).flush()
        del get_property_cache(self).builds
        return pub

    def addCustom(self, library_file, custom_type):
        """See `IPackageUpload`."""
        self.addSearchableNames([library_file.filename])
        puc = PackageUploadCustom(
            packageupload=self, libraryfilealias=library_file.id,
            customformat=custom_type)
        Store.of(self).flush()
        del get_property_cache(self).customfiles
        return puc

    def isPPA(self):
        """See `IPackageUpload`."""
        return self.archive.is_ppa

    def _getChangesDict(self, changes_file_object=None):
        """Return a dictionary with changes file tags in it."""
        if changes_file_object is None:
            if self.changesfile is None:
                return {}, ''
            changes_file_object = self.changesfile
        changes_content = changes_file_object.read()

        # Rewind the file so that the next read starts at offset zero. Please
        # note that a LibraryFileAlias does not support seek operations.
        if hasattr(changes_file_object, "seek"):
            changes_file_object.seek(0)

        changes = parse_tagfile_content(changes_content)

        # Leaving the PGP signature on a package uploaded
        # leaves the possibility of someone hijacking the notification
        # and uploading to any archive as the signer.
        return changes, strip_pgp_signature(changes_content).splitlines(True)

    def findSourcePublication(self):
        """Find the `SourcePackagePublishingHistory` for this build."""
        first_build = self.builds[:1]
        if first_build:
            [first_build] = first_build
            return first_build.build._getLatestPublication()
        else:
            return None

    def findPersonToNotify(self):
        """Find the right person to notify about this upload."""
        spph = self.findSourcePublication()
        spr = self.sourcepackagerelease
        if spph and spr.upload_archive != self.archive:
            # This is a build triggered by the syncing of a source
            # package.  Notify the person who requested the sync.
            return spph.creator
        elif self.signing_key:
            return self.signing_key.owner
            # It may be a recipe upload.
        elif spr and spr.source_package_recipe_build:
            return spr.source_package_recipe_build.requester
        else:
            return None

    def notify(self, summary_text=None, changes_file_object=None,
               logger=None, dry_run=False):
        """See `IPackageUpload`."""
        status_action = {
            PackageUploadStatus.NEW: 'new',
            PackageUploadStatus.UNAPPROVED: 'unapproved',
            PackageUploadStatus.REJECTED: 'rejected',
            PackageUploadStatus.ACCEPTED: 'accepted',
            PackageUploadStatus.DONE: 'accepted',
            }
        changes, changes_lines = self._getChangesDict(changes_file_object)
        if changes_file_object is not None:
            changesfile_content = changes_file_object.read()
        else:
            changesfile_content = 'No changes file content available.'
        blamee = self.findPersonToNotify()
        notify(
            blamee, self.sourcepackagerelease, self.builds, self.customfiles,
            self.archive, self.distroseries, self.pocket, summary_text,
            changes, changesfile_content, changes_file_object,
            status_action[self.status], dry_run=dry_run, logger=logger)

    @property
    def components(self):
        """See `IPackageUpload`."""
        existing_components = set()
        if self.contains_source:
            existing_components.add(self.sourcepackagerelease.component)
        else:
            # For builds we need to iterate through all its binaries
            # and collect each component.
            for build in self.builds:
                for binary in build.build.binarypackages:
                    existing_components.add(binary.component)
        return existing_components

    @cachedproperty
    def concrete_package_copy_job(self):
        """See `IPackageUpload`."""
        return getUtility(IPackageCopyJobSource).wrap(self.package_copy_job)

    def _nameToComponent(self, component):
        """Helper to convert a possible string component to IComponent."""
        try:
            if isinstance(component, basestring):
                component = getUtility(IComponentSet)[component]
            return component
        except NotFoundError:
            raise ComponentNotFound(component)

    def _nameToSection(self, section):
        """Helper to convert a possible string section to ISection."""
        try:
            if isinstance(section, basestring):
                section = getUtility(ISectionSet)[section]
            return section
        except NotFoundError:
            raise SectionNotFound(section)

    def _nameToPriority(self, priority):
        """Helper to convert a possible string priority to its enum."""
        try:
            if isinstance(priority, basestring):
                priority = name_priority_map[priority]
            return priority
        except KeyError:
            raise PriorityNotFound(priority)

    def _overrideSyncSource(self, new_component, new_section,
                            allowed_components):
        """Override source on the upload's `PackageCopyJob`, if any."""
        from lp.soyuz.adapters.overrides import SourceOverride

        if self.package_copy_job is None:
            return False

        copy_job = self.concrete_package_copy_job
        allowed_component_names = [
            component.name for component in allowed_components]
        if copy_job.component_name not in allowed_component_names:
            raise QueueAdminUnauthorizedError(
                "No rights to override from %s" % copy_job.component_name)
        copy_job.addSourceOverride(SourceOverride(
            copy_job.package_name, new_component, new_section))

        return True

    def _overrideNonSyncSource(self, new_component, new_section,
                               allowed_components):
        """Override sources on a source upload."""
        made_changes = False

        for source in self.sources:
            old_component = source.sourcepackagerelease.component
            if old_component not in allowed_components:
                # The old component is not in the list of allowed components
                # to override.
                raise QueueAdminUnauthorizedError(
                    "No rights to override from %s" % old_component.name)
            source.sourcepackagerelease.override(
                component=new_component, section=new_section)
            made_changes = True

        # We override our own archive too, as it is used to create
        # the SPPH during publish().
        if new_component is not None:
            distribution = self.distroseries.distribution
            self.archive = distribution.getArchiveByComponent(
                new_component.name)

        return made_changes

    def overrideSource(self, new_component=None, new_section=None,
                       allowed_components=None, user=None):
        """See `IPackageUpload`."""
        if new_component is None and new_section is None:
            # Nothing needs overriding, bail out.
            return False

        new_component = self._nameToComponent(new_component)
        new_section = self._nameToSection(new_section)

        if allowed_components is None and user is not None:
            # Get a list of components for which the user has rights to
            # override to or from.
            permission_set = getUtility(IArchivePermissionSet)
            permissions = permission_set.componentsForQueueAdmin(
                self.distroseries.main_archive, user)
            allowed_components = set(
                permission.component for permission in permissions)
        assert allowed_components is not None, (
            "Must provide allowed_components for non-webservice calls.")

        if new_component not in list(allowed_components) + [None]:
            raise QueueAdminUnauthorizedError(
                "No rights to override to %s" % new_component.name)

        return (
            self._overrideSyncSource(
                new_component, new_section, allowed_components) or
            self._overrideNonSyncSource(
                new_component, new_section, allowed_components))

    def _filterBinaryChanges(self, changes):
        """Process a binary changes mapping into a more convenient form."""
        changes_by_name = {}
        changes_for_all = None

        for change in changes:
            filtered_change = {}
            if change.get("component") is not None:
                filtered_change["component"] = self._nameToComponent(
                    change.get("component"))
            if change.get("section") is not None:
                filtered_change["section"] = self._nameToSection(
                    change.get("section"))
            if change.get("priority") is not None:
                filtered_change["priority"] = self._nameToPriority(
                    change.get("priority"))

            if "name" in change:
                changes_by_name[change["name"]] = filtered_change
            else:
                # Changes with no "name" item provide a default for all
                # binaries.
                changes_for_all = filtered_change

        return changes_by_name, changes_for_all

    def overrideBinaries(self, changes, allowed_components=None, user=None):
        """See `IPackageUpload`."""
        if not self.contains_build:
            return False

        if not changes:
            # Nothing needs overriding, bail out.
            return False

        if allowed_components is None and user is not None:
            # Get a list of components for which the user has rights to
            # override to or from.
            permission_set = getUtility(IArchivePermissionSet)
            permissions = permission_set.componentsForQueueAdmin(
                self.distroseries.main_archive, user)
            allowed_components = set(
                permission.component for permission in permissions)
        assert allowed_components is not None, (
            "Must provide allowed_components for non-webservice calls.")

        changes_by_name, changes_for_all = self._filterBinaryChanges(changes)

        new_components = set()
        for change in changes_by_name.values():
            if "component" in change:
                new_components.add(change["component"])
        if changes_for_all is not None and "component" in changes_for_all:
            new_components.add(changes_for_all["component"])
        new_components.discard(None)
        disallowed_components = sorted(
            component.name
            for component in new_components.difference(allowed_components))
        if disallowed_components:
            raise QueueAdminUnauthorizedError(
                "No rights to override to %s" %
                ", ".join(disallowed_components))

        made_changes = False
        for build in self.builds:
            # See if the new component requires a new archive on the build.
            for component in new_components:
                distroarchseries = build.build.distro_arch_series
                distribution = distroarchseries.distroseries.distribution
                new_archive = distribution.getArchiveByComponent(
                    component.name)
                if new_archive != build.build.archive:
                    raise QueueInconsistentStateError(
                        "Overriding component to '%s' failed because it "
                        "would require a new archive." % component.name)

            for binarypackage in build.build.binarypackages:
                change = changes_by_name.get(
                    binarypackage.name, changes_for_all)
                if change:
                    if binarypackage.component not in allowed_components:
                        # The old component is not in the list of allowed
                        # components to override.
                        raise QueueAdminUnauthorizedError(
                            "No rights to override from %s" %
                            binarypackage.component.name)
                    binarypackage.override(**change)
                    made_changes = True

        return made_changes


class PackageUploadBuild(SQLBase):
    """A Queue item's related builds."""
    implements(IPackageUploadBuild)

    _defaultOrder = ['id']

    packageupload = ForeignKey(
        dbName='packageupload',
        foreignKey='PackageUpload')

    build = ForeignKey(dbName='build', foreignKey='BinaryPackageBuild')

    @property
    def binaries(self):
        """See `IPackageUploadBuild`."""
        for binary in self.build.binarypackages:
            yield binary.properties

    def checkComponentAndSection(self):
        """See `IPackageUploadBuild`."""
        distroseries = self.packageupload.distroseries
        is_ppa = self.packageupload.archive.is_ppa

        for binary in self.build.binarypackages:
            if (not is_ppa and
                binary.component not in distroseries.upload_components):
                # Only complain about non-PPA uploads.
                raise QueueBuildAcceptError(
                    'Component "%s" is not allowed in %s'
                    % (binary.component.name, distroseries.name))
            # At this point (uploads are already processed) sections are
            # guaranteed to exist in the DB. We don't care if sections are
            # not official.
            pass

    def publish(self, logger=None):
        """See `IPackageUploadBuild`."""
        # Determine the build's architecturetag
        build_archtag = self.build.distro_arch_series.architecturetag
        distroseries = self.packageupload.distroseries
        debug(logger, "Publishing build to %s/%s/%s" % (
            distroseries.distribution.name, distroseries.name,
            build_archtag))

        # Publish all of the build's binaries.
        bins = {}
        for binary in self.build.binarypackages:
            debug(
                logger, "... %s/%s (Arch %s)" % (
                binary.binarypackagename.name,
                binary.version,
                'Specific' if binary.architecturespecific else 'Independent',
                ))
            bins[binary] = (
                binary.component, binary.section, binary.priority, None)
        return getUtility(IPublishingSet).publishBinaries(
            self.packageupload.archive, distroseries,
            self.packageupload.pocket, bins)


class PackageUploadSource(SQLBase):
    """A Queue item's related sourcepackagereleases."""

    implements(IPackageUploadSource)

    _defaultOrder = ['id']

    packageupload = ForeignKey(
        dbName='packageupload',
        foreignKey='PackageUpload')

    sourcepackagerelease = ForeignKey(
        dbName='sourcepackagerelease',
        foreignKey='SourcePackageRelease')

    def getSourceAncestryForDiffs(self):
        """See `IPackageUploadSource`."""
        primary_archive = self.packageupload.distroseries.main_archive
        release_pocket = PackagePublishingPocket.RELEASE
        current_distroseries = self.packageupload.distroseries
        ancestry_locations = [
            (self.packageupload.archive, current_distroseries,
             self.packageupload.pocket),
            (primary_archive, current_distroseries, release_pocket),
            (primary_archive, None, release_pocket),
            ]

        for archive, distroseries, pocket in ancestry_locations:
            ancestries = archive.getPublishedSources(
                name=self.sourcepackagerelease.name,
                distroseries=distroseries, pocket=pocket,
                exact_match=True)
            try:
                return ancestries[0]
            except IndexError:
                pass

        return None

    def verifyBeforeAccept(self):
        """See `IPackageUploadSource`."""
        # Check for duplicate source version across all distroseries.
        conflict = getUtility(IPackageUploadSet).findSourceUpload(
            self.sourcepackagerelease.name,
            self.sourcepackagerelease.version,
            self.packageupload.archive,
            self.packageupload.distroseries.distribution)

        if conflict is not None:
            raise QueueInconsistentStateError(
                "The source %s is already accepted in %s/%s and you "
                "cannot upload the same version within the same "
                "distribution. You have to modify the source version "
                "and re-upload." % (
                    self.sourcepackagerelease.title,
                    conflict.distroseries.distribution.name,
                    conflict.distroseries.name))

    def verifyBeforePublish(self):
        """See `IPackageUploadSource`."""
        # Check for duplicate filenames currently present in the archive.
        for source_file in self.sourcepackagerelease.files:
            try:
                published_file = self.packageupload.archive.getFileByName(
                    source_file.libraryfile.filename)
            except NotFoundError:
                # NEW files are *OK*.
                continue

            filename = source_file.libraryfile.filename
            proposed_sha1 = source_file.libraryfile.content.sha1
            published_sha1 = published_file.content.sha1

            # Multiple orig(s) with the same content are fine.
            if source_file.is_orig:
                if proposed_sha1 == published_sha1:
                    continue
                raise QueueInconsistentStateError(
                    '%s is already published in archive for %s with a '
                    'different SHA1 hash (%s != %s)' % (
                    filename, self.packageupload.distroseries.name,
                    proposed_sha1, published_sha1))

            # Any dsc(s), targz(s) and diff(s) already present
            # are a very big problem.
            raise QueueInconsistentStateError(
                '%s is already published in archive for %s' % (
                filename, self.packageupload.distroseries.name))

    def checkComponentAndSection(self):
        """See `IPackageUploadSource`."""
        distroseries = self.packageupload.distroseries
        component = self.sourcepackagerelease.component

        if (not self.packageupload.archive.is_ppa and
            component not in distroseries.upload_components):
            # Only complain about non-PPA uploads.
            raise QueueSourceAcceptError(
                'Component "%s" is not allowed in %s' % (component.name,
                                                         distroseries.name))

        # At this point (uploads are already processed) sections are
        # guaranteed to exist in the DB. We don't care if sections are
        # not official.
        pass

    def publish(self, logger=None):
        """See `IPackageUploadSource`."""
        # Publish myself in the distroseries pointed at by my queue item.
        debug(logger, "Publishing source %s/%s to %s/%s in the %s archive" % (
            self.sourcepackagerelease.name,
            self.sourcepackagerelease.version,
            self.packageupload.distroseries.distribution.name,
            self.packageupload.distroseries.name,
            self.packageupload.archive.name))

        return getUtility(IPublishingSet).newSourcePublication(
            archive=self.packageupload.archive,
            sourcepackagerelease=self.sourcepackagerelease,
            distroseries=self.packageupload.distroseries,
            component=self.sourcepackagerelease.component,
            section=self.sourcepackagerelease.section,
            pocket=self.packageupload.pocket,
            packageupload=self.packageupload)


class PackageUploadCustom(SQLBase):
    """A Queue item's related custom format uploads."""
    implements(IPackageUploadCustom)

    _defaultOrder = ['id']

    packageupload = ForeignKey(
        dbName='packageupload', foreignKey='PackageUpload')

    customformat = EnumCol(
        dbName='customformat', unique=False, notNull=True,
        schema=PackageUploadCustomFormat)

    libraryfilealias = ForeignKey(
        dbName='libraryfilealias', foreignKey="LibraryFileAlias", notNull=True)

    def publish(self, logger=None):
        """See `IPackageUploadCustom`."""
        # This is a marker as per the comment in lib/lp/soyuz/enums.py:
        ##CUSTOMFORMAT##
        # Essentially, if you alter anything to do with what custom formats
        # are, what their tags are, or anything along those lines, you should
        # grep for the marker in the source tree and fix it up in every place
        # so marked.
        debug(logger, "Publishing custom %s to %s/%s" % (
            self.packageupload.displayname,
            self.packageupload.distroseries.distribution.name,
            self.packageupload.distroseries.name))

        self.publisher_dispatch[self.customformat](self, logger)

    def temp_filename(self):
        """See `IPackageUploadCustom`."""
        temp_dir = tempfile.mkdtemp()
        temp_file_name = os.path.join(
            temp_dir, self.libraryfilealias.filename)
        temp_file = file(temp_file_name, "wb")
        self.libraryfilealias.open()
        copy_and_close(self.libraryfilealias, temp_file)
        return temp_file_name

    def _publishCustom(self, action_method, logger=None):
        """Publish custom formats.

        Publish Either an installer, an upgrader or a ddtp upload using the
        supplied action method.
        """
        temp_filename = self.temp_filename()
        suite = self.packageupload.distroseries.getSuite(
            self.packageupload.pocket)
        try:
            # See the XXX near the import for getPubConfig.
            archive_config = getPubConfig(self.packageupload.archive)
            action_method(archive_config, temp_filename, suite, logger=logger)
        finally:
            shutil.rmtree(os.path.dirname(temp_filename))

    def publishDebianInstaller(self, logger=None):
        """See `IPackageUploadCustom`."""
        # XXX cprov 2005-03-03: We need to use the Zope Component Lookup
        # to instantiate the object in question and avoid circular imports
        from lp.archivepublisher.debian_installer import (
            process_debian_installer)

        self._publishCustom(process_debian_installer, logger=logger)

    def publishDistUpgrader(self, logger=None):
        """See `IPackageUploadCustom`."""
        # XXX cprov 2005-03-03: We need to use the Zope Component Lookup
        # to instantiate the object in question and avoid circular imports
        from lp.archivepublisher.dist_upgrader import process_dist_upgrader

        self._publishCustom(process_dist_upgrader, logger=logger)

    def publishDdtpTarball(self, logger=None):
        """See `IPackageUploadCustom`."""
        # XXX cprov 2005-03-03: We need to use the Zope Component Lookup
        # to instantiate the object in question and avoid circular imports
        from lp.archivepublisher.ddtp_tarball import process_ddtp_tarball

        self._publishCustom(process_ddtp_tarball, logger=logger)

    def publishRosettaTranslations(self, logger=None):
        """See `IPackageUploadCustom`."""
        sourcepackagerelease = self.packageupload.sourcepackagerelease

        # Ignore translations not with main distribution purposes.
        if self.packageupload.archive.purpose not in MAIN_ARCHIVE_PURPOSES:
            debug(logger,
                  "Skipping translations since its purpose is not "
                  "in MAIN_ARCHIVE_PURPOSES.")
            return

        # If the distroseries is 11.10 (oneiric) or later, the valid names
        # check is not required.  (See bug 788685.)
        distroseries = sourcepackagerelease.upload_distroseries
        do_names_check = Version(distroseries.version) < Version('11.10')

        valid_pockets = (
            PackagePublishingPocket.RELEASE, PackagePublishingPocket.SECURITY,
            PackagePublishingPocket.UPDATES, PackagePublishingPocket.PROPOSED)
        valid_components = ('main', 'restricted')
        if (self.packageupload.pocket not in valid_pockets or
            (do_names_check and
            sourcepackagerelease.component.name not in valid_components)):
            # XXX: CarlosPerelloMarin 2006-02-16 bug=31665:
            # This should be implemented using a more general rule to accept
            # different policies depending on the distribution.
            # Ubuntu's MOTU told us that they are not able to handle
            # translations like we do in main. We are going to import only
            # packages in main.
            return

        blamee = self.packageupload.findPersonToNotify()
        getUtility(IPackageTranslationsUploadJobSource).create(
            sourcepackagerelease, self.libraryfilealias, blamee)

    def publishStaticTranslations(self, logger=None):
        """See `IPackageUploadCustom`."""
        # Static translations are not published.  Currently, they're
        # only exposed via webservice methods so that third parties can
        # retrieve them from the librarian.
        debug(logger, "Skipping publishing of static translations.")
        return

    def publishMetaData(self, logger=None):
        """See `IPackageUploadCustom`."""
        # In the future this could use the existing custom upload file
        # processing which deals with versioning, etc., but that's too
        # complicated for our needs right now.  Also, the existing code
        # assumes that everything is a tarball and tries to unpack it.

        archive = self.packageupload.archive
        # See the XXX near the import for getPubConfig.
        archive_config = getPubConfig(archive)
        dest_file = os.path.join(
            archive_config.metaroot, self.libraryfilealias.filename)
        if not os.path.isdir(archive_config.metaroot):
            os.makedirs(archive_config.metaroot, 0755)

        # At this point we now have a directory of the format:
        # <person_name>/meta/<ppa_name>
        # We're ready to copy the file out of the librarian into it.

        file_obj = file(dest_file, "wb")
        self.libraryfilealias.open()
        copy_and_close(self.libraryfilealias, file_obj)

    def publishUefi(self, logger=None):
        """See `IPackageUploadCustom`."""
        # XXX cprov 2005-03-03: We need to use the Zope Component Lookup
        # to instantiate the object in question and avoid circular imports
        from lp.archivepublisher.uefi import process_uefi

        self._publishCustom(process_uefi, logger=logger)

    publisher_dispatch = {
        PackageUploadCustomFormat.DEBIAN_INSTALLER: publishDebianInstaller,
        PackageUploadCustomFormat.ROSETTA_TRANSLATIONS:
            publishRosettaTranslations,
        PackageUploadCustomFormat.DIST_UPGRADER: publishDistUpgrader,
        PackageUploadCustomFormat.DDTP_TARBALL: publishDdtpTarball,
        PackageUploadCustomFormat.STATIC_TRANSLATIONS:
            publishStaticTranslations,
        PackageUploadCustomFormat.META_DATA: publishMetaData,
        PackageUploadCustomFormat.UEFI: publishUefi,
        }

    # publisher_dispatch must have an entry for each value of
    # PackageUploadCustomFormat.
    assert len(publisher_dispatch) == len(PackageUploadCustomFormat)


class PackageUploadSet:
    """See `IPackageUploadSet`"""
    implements(IPackageUploadSet)

    def __iter__(self):
        """See `IPackageUploadSet`."""
        return iter(PackageUpload.select())

    def __getitem__(self, queue_id):
        """See `IPackageUploadSet`."""
        try:
            return PackageUpload.get(queue_id)
        except SQLObjectNotFound:
            raise NotFoundError(queue_id)

    def get(self, queue_id):
        """See `IPackageUploadSet`."""
        try:
            return PackageUpload.get(queue_id)
        except SQLObjectNotFound:
            raise NotFoundError(queue_id)

    def findSourceUpload(self, name, version, archive, distribution):
        """See `IPackageUploadSet`."""
        # Avoiding circular imports.
        from lp.registry.model.distroseries import DistroSeries
        from lp.soyuz.model.sourcepackagerelease import SourcePackageRelease

        store = IMasterStore(PackageUpload)
        origin = (
            PackageUpload,
            Join(DistroSeries,
                 DistroSeries.id == PackageUpload.distroseriesID),
            Join(PackageUploadSource,
                 PackageUploadSource.packageuploadID == PackageUpload.id),
            Join(SourcePackageRelease,
                 SourcePackageRelease.id ==
                     PackageUploadSource.sourcepackagereleaseID),
            Join(SourcePackageName,
                 SourcePackageName.id ==
                     SourcePackageRelease.sourcepackagenameID),
            )

        approved_status = (
            PackageUploadStatus.ACCEPTED,
            PackageUploadStatus.DONE,
            )
        conflicts = store.using(*origin).find(
            PackageUpload,
            PackageUpload.status.is_in(approved_status),
            PackageUpload.archive == archive,
            DistroSeries.distribution == distribution,
            SourcePackageRelease.version == version,
            SourcePackageName.name == name)

        return conflicts.one()

    def getBuildsForSources(self, distroseries, status=None, pockets=None,
                            names=None):
        """See `IPackageUploadSet`."""
        # Avoiding circular imports.
        from lp.soyuz.model.binarypackagebuild import BinaryPackageBuild

        archives = distroseries.distribution.getArchiveIDList()
        clauses = [
            PackageUpload.distroseries == distroseries,
            PackageUpload.archiveID.is_in(archives),
            PackageUploadBuild.packageuploadID == PackageUpload.id,
            ]

        if status is not None:
            clauses.append(PackageUpload.status.is_in(status))
        if pockets is not None:
            clauses.append(PackageUpload.pocket.is_in(pockets))
        if names is not None:
            clauses.extend([
                BinaryPackageBuild.id == PackageUploadBuild.buildID,
                BinaryPackageBuild.source_package_name ==
                    SourcePackageName.id,
                SourcePackageName.name.is_in(names),
                ])

        store = IStore(PackageUpload)
        return store.find(PackageUpload, *clauses)

    def count(self, status=None, distroseries=None, pocket=None):
        """See `IPackageUploadSet`."""
        clauses = []
        if status:
            clauses.append("status=%s" % sqlvalues(status))

        if distroseries:
            clauses.append("distroseries=%s" % sqlvalues(distroseries))

        if pocket:
            clauses.append("pocket=%s" % sqlvalues(pocket))

        query = " AND ".join(clauses)
        return PackageUpload.select(query).count()

    def getAll(self, distroseries, created_since_date=None, status=None,
               archive=None, pocket=None, custom_type=None, name=None,
               version=None, exact_match=False):
        """See `IPackageUploadSet`."""
        store = Store.of(distroseries)

        def dbitem_tuple(item_or_list):
            if not isinstance(item_or_list, list):
                return (item_or_list,)
            else:
                return tuple(item_or_list)

        joins = [PackageUpload]
        conditions = []

        if created_since_date is not None:
            conditions.append(PackageUpload.date_created > created_since_date)

        if status is not None:
            status = dbitem_tuple(status)
            conditions.append(PackageUpload.status.is_in(status))

        archives = distroseries.distribution.getArchiveIDList(archive)
        conditions.append(PackageUpload.archiveID.is_in(archives))

        if pocket is not None:
            pocket = dbitem_tuple(pocket)
            conditions.append(PackageUpload.pocket.is_in(pocket))

        if custom_type is not None:
            custom_type = dbitem_tuple(custom_type)
            joins.append(Join(PackageUploadCustom, And(
                PackageUpload.id == PackageUploadCustom.packageuploadID,
                PackageUploadCustom.customformat.is_in(custom_type))))

        if name:
            # Escape special characters, namely backslashes and single quotes.
            name = name.replace('\\', '\\\\')
            name = name.replace("'", "\\'")
            name = "'%s'" % name
            if not exact_match:
                name += ':*'
            conditions.append(
                SQL("searchable_names::tsvector @@ ?", params=(name,)))

        if version:
            conditions.append(
                ArrayContains(PackageUpload.searchable_versions,
                    Array(version)))

        query = store.using(*joins).find(
            PackageUpload, PackageUpload.distroseries == distroseries,
            *conditions).order_by(Desc(PackageUpload.id)).config(distinct=True)

        def preload_hook(rows):
            puses = load_referencing(
                PackageUploadSource, rows, ["packageuploadID"])
            pubs = load_referencing(
                PackageUploadBuild, rows, ["packageuploadID"])
            pucs = load_referencing(
                PackageUploadCustom, rows, ["packageuploadID"])

            prefill_packageupload_caches(rows, puses, pubs, pucs)

        return DecoratedResultSet(query, pre_iter_hook=preload_hook)

    def getBuildByBuildIDs(self, build_ids):
        """See `IPackageUploadSet`."""
        if build_ids is None or len(build_ids) == 0:
            return []
        return PackageUploadBuild.select(
            "PackageUploadBuild.build IN %s" % sqlvalues(build_ids))

    def getByPackageCopyJobIDs(self, pcj_ids):
        """See `IPackageUploadSet`."""
        if pcj_ids is None or len(pcj_ids) == 0:
            return EmptyResultSet()

        return IStore(PackageUpload).find(
            PackageUpload,
            PackageUpload.package_copy_job_id.is_in(pcj_ids))


def prefill_packageupload_caches(uploads, puses, pubs, pucs):
    # Circular imports.
    from lp.soyuz.model.archive import Archive
    from lp.soyuz.model.binarypackagebuild import BinaryPackageBuild
    from lp.soyuz.model.publishing import SourcePackagePublishingHistory
    from lp.soyuz.model.sourcepackagerelease import SourcePackageRelease

    for pu in uploads:
        cache = get_property_cache(pu)
        cache.sources = []
        cache.builds = []
        cache.customfiles = []

    for pus in puses:
        get_property_cache(pus.packageupload).sources.append(pus)
    for pub in pubs:
        get_property_cache(pub.packageupload).builds.append(pub)
    for puc in pucs:
        get_property_cache(puc.packageupload).customfiles.append(puc)

    source_sprs = load_related(
        SourcePackageRelease, puses, ['sourcepackagereleaseID'])
    bpbs = load_related(BinaryPackageBuild, pubs, ['buildID'])
    load_related(DistroArchSeries, bpbs, ['distro_arch_series_id'])
    binary_sprs = load_related(
        SourcePackageRelease, bpbs, ['source_package_release_id'])
    bprs = load_referencing(BinaryPackageRelease, bpbs, ['buildID'])
    load_related(BinaryPackageName, bprs, ['binarypackagenameID'])
    sprs = source_sprs + binary_sprs

    load_related(SourcePackageName, sprs, ['sourcepackagenameID'])
    load_related(Section, sprs + bprs, ['sectionID'])
    load_related(Component, sprs, ['componentID'])
    load_related(LibraryFileAlias, uploads, ['changes_file_id'])
    publications = load_referencing(
        SourcePackagePublishingHistory, sprs, ['sourcepackagereleaseID'])
    load_related(Archive, publications, ['archiveID'])
    diffs = getUtility(IPackageDiffSet).getDiffsToReleases(
        sprs, preload_for_display=True)

    puc_lfas = load_related(LibraryFileAlias, pucs, ['libraryfilealiasID'])
    load_related(LibraryFileContent, puc_lfas, ['contentID'])

    for spr_cache in sprs:
        get_property_cache(spr_cache).published_archives = []
        get_property_cache(spr_cache).package_diffs = []
    for publication in publications:
        spr_cache = get_property_cache(publication.sourcepackagerelease)
        spr_cache.published_archives.append(publication.archive)
    for diff in diffs:
        get_property_cache(diff.to_source).package_diffs.append(diff)
