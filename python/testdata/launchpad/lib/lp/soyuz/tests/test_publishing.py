# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test native publication workflow for Soyuz. """

import datetime
import operator
import os
import shutil
from StringIO import StringIO
import tempfile

import pytz
from storm.store import Store
from testtools.matchers import Equals
import transaction
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.errors import NotFoundError
from lp.archivepublisher.config import getPubConfig
from lp.archivepublisher.diskpool import DiskPool
from lp.buildmaster.enums import BuildStatus
from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.interfaces.series import SeriesStatus
from lp.registry.interfaces.sourcepackage import SourcePackageUrgency
from lp.registry.interfaces.sourcepackagename import ISourcePackageNameSet
from lp.services.config import config
from lp.services.database.constants import UTC_NOW
from lp.services.librarian.interfaces import ILibraryFileAliasSet
from lp.services.log.logger import DevNullLogger
from lp.soyuz.enums import (
    BinaryPackageFormat,
    PackageUploadStatus,
    )
from lp.soyuz.interfaces.archivearch import IArchiveArchSet
from lp.soyuz.interfaces.binarypackagename import IBinaryPackageNameSet
from lp.soyuz.interfaces.component import IComponentSet
from lp.soyuz.interfaces.processor import IProcessorSet
from lp.soyuz.interfaces.publishing import (
    DeletionError,
    IPublishingSet,
    OverrideError,
    PackagePublishingPriority,
    PackagePublishingStatus,
    )
from lp.soyuz.interfaces.queue import QueueInconsistentStateError
from lp.soyuz.interfaces.section import ISectionSet
from lp.soyuz.model.distroseriesdifferencejob import find_waiting_jobs
from lp.soyuz.model.distroseriespackagecache import DistroSeriesPackageCache
from lp.soyuz.model.publishing import (
    BinaryPackagePublishingHistory,
    SourcePackagePublishingHistory,
    )
from lp.testing import (
    StormStatementRecorder,
    TestCaseWithFactory,
    )
from lp.testing.dbuser import (
    dbuser,
    switch_dbuser,
    )
from lp.testing.factory import LaunchpadObjectFactory
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadZopelessLayer,
    ZopelessDatabaseLayer,
    )
from lp.testing.matchers import HasQueryCount


class SoyuzTestPublisher:
    """Helper class able to publish coherent source and binaries in Soyuz."""

    def __init__(self):
        self.factory = LaunchpadObjectFactory()
        self.default_package_name = 'foo'

    def setUpDefaultDistroSeries(self, distroseries=None):
        """Set up a distroseries that will be used by default.

        This distro series is used to publish packages in, if you don't
        specify any when using the publishing methods.

        It also sets up a person that can act as the default uploader,
        and makes sure that the default package name exists in the
        database.

        :param distroseries: The `IDistroSeries` to use as default. If
            it's None, one will be created.
        :return: The `IDistroSeries` that got set as default.
        """
        if distroseries is None:
            distroseries = self.factory.makeDistroSeries()
        self.distroseries = distroseries
        # Set up a person that has a GPG key.
        self.person = getUtility(IPersonSet).getByName('name16')
        # Make sure the name exists in the database, to make it easier
        # to get packages from distributions and distro series.
        name_set = getUtility(ISourcePackageNameSet)
        name_set.getOrCreateByName(self.default_package_name)
        return self.distroseries

    def prepareBreezyAutotest(self):
        """Prepare ubuntutest/breezy-autotest for publications.

        It's also called during the normal test-case setUp.
        """
        self.ubuntutest = getUtility(IDistributionSet)['ubuntutest']
        self.breezy_autotest = self.ubuntutest['breezy-autotest']
        self.setUpDefaultDistroSeries(self.breezy_autotest)
        # Only create the DistroArchSeries needed if they do not exist yet.
        # This makes it easier to experiment at the python command line
        # (using "make harness").
        try:
            self.breezy_autotest_i386 = self.breezy_autotest['i386']
        except NotFoundError:
            self.breezy_autotest_i386 = self.breezy_autotest.newArch(
                'i386', getUtility(IProcessorSet).getByName('386'), False,
                self.person, supports_virtualized=True)
        try:
            self.breezy_autotest_hppa = self.breezy_autotest['hppa']
        except NotFoundError:
            self.breezy_autotest_hppa = self.breezy_autotest.newArch(
                'hppa', getUtility(IProcessorSet).getByName('hppa'), False,
                self.person)
        self.breezy_autotest.nominatedarchindep = self.breezy_autotest_i386
        fake_chroot = self.addMockFile('fake_chroot.tar.gz')
        self.breezy_autotest_i386.addOrUpdateChroot(fake_chroot)
        self.breezy_autotest_hppa.addOrUpdateChroot(fake_chroot)

    def addFakeChroots(self, distroseries=None, db_only=False):
        """Add fake chroots for all the architectures in distroseries."""
        if distroseries is None:
            distroseries = self.distroseries
        if db_only:
            fake_chroot = self.factory.makeLibraryFileAlias(
                filename='fake_chroot.tar.gz', db_only=True)
        else:
            fake_chroot = self.addMockFile('fake_chroot.tar.gz')
        for arch in distroseries.architectures:
            arch.addOrUpdateChroot(fake_chroot)

    def regetBreezyAutotest(self):
        self.ubuntutest = getUtility(IDistributionSet)['ubuntutest']
        self.breezy_autotest = self.ubuntutest['breezy-autotest']
        self.person = getUtility(IPersonSet).getByName('name16')
        self.breezy_autotest_i386 = self.breezy_autotest['i386']
        self.breezy_autotest_hppa = self.breezy_autotest['hppa']

    def addMockFile(self, filename, filecontent='nothing', restricted=False):
        """Add a mock file in Librarian.

        Returns a ILibraryFileAlias corresponding to the file uploaded.
        """
        library_file = getUtility(ILibraryFileAliasSet).create(
            filename, len(filecontent), StringIO(filecontent),
            'application/text', restricted=restricted)
        return library_file

    def addPackageUpload(self, archive, distroseries,
                         pocket=PackagePublishingPocket.RELEASE,
                         changes_file_name="foo_666_source.changes",
                         changes_file_content="fake changes file content",
                         upload_status=PackageUploadStatus.DONE):
        signing_key = self.person.gpg_keys[0]
        package_upload = distroseries.createQueueEntry(
            pocket, archive, changes_file_name, changes_file_content,
            signing_key=signing_key)

        status_to_method = {
            PackageUploadStatus.DONE: 'setDone',
            PackageUploadStatus.ACCEPTED: 'setAccepted',
            }
        naked_package_upload = removeSecurityProxy(package_upload)
        method = getattr(
            naked_package_upload, status_to_method[upload_status])
        method()

        return package_upload

    def getPubSource(self, sourcename=None, version=None, component='main',
                     filename=None, section='base',
                     filecontent='I do not care about sources.',
                     changes_file_content="Fake: fake changes file content",
                     status=PackagePublishingStatus.PENDING,
                     pocket=PackagePublishingPocket.RELEASE,
                     urgency=SourcePackageUrgency.LOW,
                     scheduleddeletiondate=None, dateremoved=None,
                     distroseries=None, archive=None, builddepends=None,
                     builddependsindep=None, architecturehintlist='all',
                     dsc_standards_version='3.6.2', dsc_format='1.0',
                     dsc_binaries='foo-bin', build_conflicts=None,
                     build_conflicts_indep=None,
                     dsc_maintainer_rfc822='Foo Bar <foo@bar.com>',
                     maintainer=None, creator=None, date_uploaded=UTC_NOW,
                     spr_only=False, user_defined_fields=None):
        """Return a mock source publishing record.

        if spr_only is specified, the source is not published and the
        sourcepackagerelease object is returned instead.
        """
        if sourcename is None:
            sourcename = self.default_package_name
        if version is None:
            version = '666'
        spn = getUtility(ISourcePackageNameSet).getOrCreateByName(sourcename)

        component = getUtility(IComponentSet)[component]
        section = getUtility(ISectionSet)[section]

        if distroseries is None:
            distroseries = self.distroseries
        if archive is None:
            archive = distroseries.main_archive
        if maintainer is None:
            maintainer = self.person
        if creator is None:
            creator = self.person

        spr = distroseries.createUploadedSourcePackageRelease(
            sourcepackagename=spn,
            maintainer=maintainer,
            creator=creator,
            component=component,
            section=section,
            urgency=urgency,
            version=version,
            builddepends=builddepends,
            builddependsindep=builddependsindep,
            build_conflicts=build_conflicts,
            build_conflicts_indep=build_conflicts_indep,
            architecturehintlist=architecturehintlist,
            changelog=None,
            changelog_entry=None,
            dsc=None,
            copyright='placeholder ...',
            dscsigningkey=self.person.gpg_keys[0],
            dsc_maintainer_rfc822=dsc_maintainer_rfc822,
            dsc_standards_version=dsc_standards_version,
            dsc_format=dsc_format,
            dsc_binaries=dsc_binaries,
            archive=archive, dateuploaded=date_uploaded,
            user_defined_fields=user_defined_fields)

        changes_file_name = "%s_%s_source.changes" % (sourcename, version)
        if spr_only:
            upload_status = PackageUploadStatus.ACCEPTED
        else:
            upload_status = PackageUploadStatus.DONE
        package_upload = self.addPackageUpload(
            archive, distroseries, pocket,
            changes_file_name=changes_file_name,
            changes_file_content=changes_file_content,
            upload_status=upload_status)
        naked_package_upload = removeSecurityProxy(
            package_upload)
        naked_package_upload.addSource(spr)

        if filename is None:
            filename = "%s_%s.dsc" % (sourcename, version)
        alias = self.addMockFile(
            filename, filecontent, restricted=archive.private)
        spr.addFile(alias)

        if spr_only:
            return spr

        if status == PackagePublishingStatus.PUBLISHED:
            datepublished = UTC_NOW
        else:
            datepublished = None

        spph = SourcePackagePublishingHistory(
            distroseries=distroseries,
            sourcepackagerelease=spr,
            sourcepackagename=spr.sourcepackagename,
            component=spr.component,
            section=spr.section,
            status=status,
            datecreated=date_uploaded,
            dateremoved=dateremoved,
            datepublished=datepublished,
            scheduleddeletiondate=scheduleddeletiondate,
            pocket=pocket,
            archive=archive,
            creator=creator)

        return spph

    def getPubBinaries(self, binaryname='foo-bin', summary='Foo app is great',
                       description='Well ...\nit does nothing, though',
                       shlibdep=None, depends=None, recommends=None,
                       suggests=None, conflicts=None, replaces=None,
                       provides=None, pre_depends=None, enhances=None,
                       breaks=None, filecontent='bbbiiinnnaaarrryyy',
                       changes_file_content="Fake: fake changes file",
                       status=PackagePublishingStatus.PENDING,
                       pocket=PackagePublishingPocket.RELEASE,
                       format=BinaryPackageFormat.DEB,
                       scheduleddeletiondate=None, dateremoved=None,
                       distroseries=None,
                       archive=None,
                       pub_source=None,
                       version=None,
                       architecturespecific=False,
                       builder=None,
                       component='main',
                       phased_update_percentage=None,
                       with_debug=False, user_defined_fields=None):
        """Return a list of binary publishing records."""
        if distroseries is None:
            distroseries = self.distroseries

        if archive is None:
            archive = distroseries.main_archive

        if pub_source is None:
            sourcename = "%s" % binaryname.split('-')[0]
            if architecturespecific:
                architecturehintlist = 'any'
            else:
                architecturehintlist = 'all'

            pub_source = self.getPubSource(
                sourcename=sourcename, status=status, pocket=pocket,
                archive=archive, distroseries=distroseries,
                version=version, architecturehintlist=architecturehintlist,
                component=component)
        else:
            archive = pub_source.archive

        builds = pub_source.createMissingBuilds()
        published_binaries = []
        for build in builds:
            build.updateStatus(BuildStatus.FULLYBUILT, builder=builder)
            pub_binaries = []
            if with_debug:
                binarypackagerelease_ddeb = self.uploadBinaryForBuild(
                    build, binaryname + '-dbgsym', filecontent, summary,
                    description, shlibdep, depends, recommends, suggests,
                    conflicts, replaces, provides, pre_depends, enhances,
                    breaks, BinaryPackageFormat.DDEB, version=version)
                pub_binaries += self.publishBinaryInArchive(
                    binarypackagerelease_ddeb, archive, status,
                    pocket, scheduleddeletiondate, dateremoved,
                    phased_update_percentage)
            else:
                binarypackagerelease_ddeb = None

            binarypackagerelease = self.uploadBinaryForBuild(
                build, binaryname, filecontent, summary, description,
                shlibdep, depends, recommends, suggests, conflicts, replaces,
                provides, pre_depends, enhances, breaks, format,
                binarypackagerelease_ddeb, version=version,
                user_defined_fields=user_defined_fields)
            pub_binaries += self.publishBinaryInArchive(
                binarypackagerelease, archive, status, pocket,
                scheduleddeletiondate, dateremoved, phased_update_percentage)
            published_binaries.extend(pub_binaries)
            package_upload = self.addPackageUpload(
                archive, distroseries, pocket,
                changes_file_content=changes_file_content,
                changes_file_name='%s_%s_%s.changes' %
                    (binaryname, binarypackagerelease.version,
                     build.arch_tag))
            package_upload.addBuild(build)

        return sorted(
            published_binaries, key=operator.attrgetter('id'), reverse=True)

    def uploadBinaryForBuild(
        self, build, binaryname, filecontent="anything",
        summary="summary", description="description", shlibdep=None,
        depends=None, recommends=None, suggests=None, conflicts=None,
        replaces=None, provides=None, pre_depends=None, enhances=None,
        breaks=None, format=BinaryPackageFormat.DEB, debug_package=None,
        user_defined_fields=None, homepage=None, version=None):
        """Return the corresponding `BinaryPackageRelease`."""
        sourcepackagerelease = build.source_package_release
        distroarchseries = build.distro_arch_series
        architecturespecific = (
            not sourcepackagerelease.architecturehintlist == 'all')

        binarypackagename = getUtility(
            IBinaryPackageNameSet).getOrCreateByName(binaryname)

        if version is None:
            version = sourcepackagerelease.version

        binarypackagerelease = build.createBinaryPackageRelease(
            version=version,
            component=sourcepackagerelease.component,
            section=sourcepackagerelease.section,
            binarypackagename=binarypackagename,
            summary=summary,
            description=description,
            shlibdeps=shlibdep,
            depends=depends,
            recommends=recommends,
            suggests=suggests,
            conflicts=conflicts,
            replaces=replaces,
            provides=provides,
            pre_depends=pre_depends,
            enhances=enhances,
            breaks=breaks,
            essential=False,
            installedsize=100,
            architecturespecific=architecturespecific,
            binpackageformat=format,
            priority=PackagePublishingPriority.STANDARD,
            debug_package=debug_package,
            user_defined_fields=user_defined_fields, homepage=homepage)

        # Create the corresponding binary file.
        if architecturespecific:
            filearchtag = distroarchseries.architecturetag
        else:
            filearchtag = 'all'
        filename = '%s_%s_%s.%s' % (binaryname, sourcepackagerelease.version,
                                    filearchtag, format.name.lower())
        alias = self.addMockFile(
            filename, filecontent=filecontent,
            restricted=build.archive.private)
        binarypackagerelease.addFile(alias)

        # Adjust the build record in way it looks complete.
        date_finished = datetime.datetime(2008, 1, 1, 0, 5, 0, tzinfo=pytz.UTC)
        date_started = date_finished - datetime.timedelta(minutes=5)
        build.updateStatus(BuildStatus.BUILDING, date_started=date_started)
        build.updateStatus(BuildStatus.FULLYBUILT, date_finished=date_finished)
        buildlog_filename = 'buildlog_%s-%s-%s.%s_%s_%s.txt.gz' % (
            build.distribution.name,
            build.distro_series.name,
            build.distro_arch_series.architecturetag,
            build.source_package_release.name,
            build.source_package_release.version,
            build.status.name)
        if not build.log:
            build.setLog(
                self.addMockFile(
                    buildlog_filename, filecontent='Built!',
                    restricted=build.archive.private))

        return binarypackagerelease

    def publishBinaryInArchive(
        self, binarypackagerelease, archive,
        status=PackagePublishingStatus.PENDING,
        pocket=PackagePublishingPocket.RELEASE,
        scheduleddeletiondate=None, dateremoved=None,
        phased_update_percentage=None):
        """Return the corresponding BinaryPackagePublishingHistory."""
        distroarchseries = binarypackagerelease.build.distro_arch_series

        # Publish the binary.
        if binarypackagerelease.architecturespecific:
            archs = [distroarchseries]
        else:
            archs = distroarchseries.distroseries.architectures

        pub_binaries = []
        for arch in archs:
            pub = BinaryPackagePublishingHistory(
                distroarchseries=arch,
                binarypackagerelease=binarypackagerelease,
                binarypackagename=binarypackagerelease.binarypackagename,
                component=binarypackagerelease.component,
                section=binarypackagerelease.section,
                priority=binarypackagerelease.priority,
                status=status,
                scheduleddeletiondate=scheduleddeletiondate,
                dateremoved=dateremoved,
                datecreated=UTC_NOW,
                pocket=pocket,
                archive=archive,
                phased_update_percentage=phased_update_percentage)
            if status == PackagePublishingStatus.PUBLISHED:
                pub.datepublished = UTC_NOW
            pub_binaries.append(pub)

        return pub_binaries

    def _findChangesFile(self, top, name_fragment):
        """File with given name fragment in directory tree starting at top."""
        for root, dirs, files in os.walk(top, topdown=False):
            for name in files:
                if (name.endswith('.changes') and
                    name.find(name_fragment) > -1):
                    return os.path.join(root, name)
        return None

    def createSource(
        self, archive, sourcename, version, distroseries=None,
        new_version=None):
        """Create source with meaningful '.changes' file."""
        top = 'lib/lp/archiveuploader/tests/data/suite'
        name_fragment = '%s_%s' % (sourcename, version)
        changesfile_path = self._findChangesFile(top, name_fragment)

        source = None

        if changesfile_path is not None:
            if new_version is None:
                new_version = version
            changesfile_content = ''
            with open(changesfile_path, 'r') as handle:
                changesfile_content = handle.read()

            source = self.getPubSource(
                sourcename=sourcename, archive=archive, version=new_version,
                changes_file_content=changesfile_content,
                distroseries=distroseries)

        return source

    def makeSourcePackageSummaryData(self, source_pub=None):
        """Make test data for SourcePackage.summary.

        The distroseries that is returned from this method needs to be
        passed into updateDistroseriesPackageCache() so that
        SourcePackage.summary can be populated.
        """
        if source_pub is None:
            distribution = self.factory.makeDistribution(
                name='youbuntu', displayname='Youbuntu')
            distroseries = self.factory.makeDistroSeries(
                name='busy', distribution=distribution)
            source_package_name = self.factory.makeSourcePackageName(
                name='bonkers')
            self.factory.makeSourcePackage(
                sourcepackagename=source_package_name,
                distroseries=distroseries)
            component = self.factory.makeComponent('multiverse')
            source_pub = self.factory.makeSourcePackagePublishingHistory(
                sourcepackagename=source_package_name,
                distroseries=distroseries,
                component=component)

        das = self.factory.makeDistroArchSeries(
            distroseries=source_pub.distroseries)

        for name in ('flubber-bin', 'flubber-lib'):
            binary_package_name = self.factory.makeBinaryPackageName(name)
            build = self.factory.makeBinaryPackageBuild(
                source_package_release=source_pub.sourcepackagerelease,
                archive=self.factory.makeArchive(),
                distroarchseries=das)
            bpr = self.factory.makeBinaryPackageRelease(
                binarypackagename=binary_package_name,
                summary='summary for %s' % name,
                build=build, component=source_pub.component)
            self.factory.makeBinaryPackagePublishingHistory(
                binarypackagerelease=bpr, distroarchseries=das)
        return dict(
            distroseries=source_pub.distroseries,
            source_package=source_pub.meta_sourcepackage)

    def updateDistroSeriesPackageCache(self, distroseries):
        with dbuser(config.statistician.dbuser):
            DistroSeriesPackageCache.updateAll(
                distroseries,
                archive=distroseries.distribution.main_archive,
                ztm=transaction,
                log=DevNullLogger())


class TestNativePublishingBase(TestCaseWithFactory, SoyuzTestPublisher):
    layer = LaunchpadZopelessLayer
    dbuser = config.archivepublisher.dbuser

    def __init__(self, methodName='runTest'):
        super(TestNativePublishingBase, self).__init__(methodName=methodName)
        SoyuzTestPublisher.__init__(self)

    def setUp(self):
        """Setup a pool dir, the librarian, and instantiate the DiskPool."""
        super(TestNativePublishingBase, self).setUp()
        switch_dbuser(config.archivepublisher.dbuser)
        self.prepareBreezyAutotest()
        self.config = getPubConfig(self.ubuntutest.main_archive)
        self.config.setupArchiveDirs()
        self.pool_dir = self.config.poolroot
        self.temp_dir = self.config.temproot
        self.logger = DevNullLogger()
        self.disk_pool = DiskPool(self.pool_dir, self.temp_dir, self.logger)

    def tearDown(self):
        """Tear down blows the pool dir away."""
        super(TestNativePublishingBase, self).tearDown()
        shutil.rmtree(self.config.distroroot)

    def getPubSource(self, *args, **kwargs):
        """Overrides `SoyuzTestPublisher.getPubSource`.

        Commits the transaction before returning, this way the rest of
        the test will immediately notice the just-created records.
        """
        source = SoyuzTestPublisher.getPubSource(self, *args, **kwargs)
        self.layer.commit()
        return source

    def getPubBinaries(self, *args, **kwargs):
        """Overrides `SoyuzTestPublisher.getPubBinaries`.

        Commits the transaction before returning, this way the rest of
        the test will immediately notice the just-created records.
        """
        binaries = SoyuzTestPublisher.getPubBinaries(self, *args, **kwargs)
        self.layer.commit()
        return binaries

    def checkPublication(self, pub, status):
        """Assert the publication has the given status."""
        self.assertEqual(
            pub.status, status, "%s is not %s (%s)" % (
            pub.displayname, status.name, pub.status.name))

    def checkPublications(self, pubs, status):
        """Assert the given publications have the given status.

        See `checkPublication`.
        """
        for pub in pubs:
            self.checkPublication(pub, status)

    def checkPastDate(self, date, lag=None):
        """Assert given date is older than 'now'.

        Optionally the user can pass a 'lag' which will be added to 'now'
        before comparing.
        """
        UTC = pytz.timezone("UTC")
        limit = datetime.datetime.now(UTC)
        if lag is not None:
            limit = limit + lag
        self.assertTrue(date < limit, "%s >= %s" % (date, limit))

    def checkSuperseded(self, pubs, supersededby=None):
        self.checkPublications(pubs, PackagePublishingStatus.SUPERSEDED)
        for pub in pubs:
            self.checkPastDate(pub.datesuperseded)
            if supersededby is not None:
                if isinstance(pub, BinaryPackagePublishingHistory):
                    dominant = supersededby.binarypackagerelease.build
                else:
                    dominant = supersededby.sourcepackagerelease
                self.assertEqual(dominant, pub.supersededby)
            else:
                self.assertIsNone(pub.supersededby)


class TestNativePublishing(TestNativePublishingBase):

    def test_publish_source(self):
        # Source publications result in a PUBLISHED publishing record and
        # the corresponding files are dumped in the disk pool/.
        pub_source = self.getPubSource(filecontent='Hello world')
        pub_source.publish(self.disk_pool, self.logger)
        self.assertEqual(PackagePublishingStatus.PUBLISHED, pub_source.status)
        pool_path = "%s/main/f/foo/foo_666.dsc" % self.pool_dir
        self.assertEqual(open(pool_path).read().strip(), 'Hello world')

    def test_publish_binaries(self):
        # Binary publications result in a PUBLISHED publishing record and
        # the corresponding files are dumped in the disk pool/.
        pub_binary = self.getPubBinaries(filecontent='Hello world')[0]
        pub_binary.publish(self.disk_pool, self.logger)
        self.assertEqual(PackagePublishingStatus.PUBLISHED, pub_binary.status)
        pool_path = "%s/main/f/foo/foo-bin_666_all.deb" % self.pool_dir
        self.assertEqual(open(pool_path).read().strip(), 'Hello world')

    def test_publish_ddeb_when_disabled_is_noop(self):
        # Publishing a DDEB publication when
        # Archive.publish_debug_symbols is false just sets PUBLISHED,
        # without a file in the pool.
        pubs = self.getPubBinaries(
            binaryname='dbg', filecontent='Hello world', with_debug=True)

        def publish_everything():
            existence_map = {}
            for pub in pubs:
                pub.publish(self.disk_pool, self.logger)
                self.assertEqual(PackagePublishingStatus.PUBLISHED, pub.status)
                filename = pub.files[0].libraryfilealias.filename
                path = "%s/main/d/dbg/%s" % (self.pool_dir, filename)
                existence_map[filename] = os.path.exists(path)
            return existence_map

        self.assertEqual(
            {u'dbg_666_all.deb': True, u'dbg-dbgsym_666_all.ddeb': False},
            publish_everything())

        pubs[0].archive.publish_debug_symbols = True

        self.assertEqual(
            {u'dbg_666_all.deb': True, u'dbg-dbgsym_666_all.ddeb': True},
            publish_everything())

    def testPublishingOverwriteFileInPool(self):
        """Test if publishOne refuses to overwrite a file in pool.

        Check if it also keeps the original file content.
        It's done by publishing 'foo' by-hand and ensuring it
        has a special content, then publish 'foo' again, via publisher,
        and finally check one of the 'foo' files content.
        """
        foo_path = os.path.join(self.pool_dir, 'main', 'f', 'foo')
        os.makedirs(foo_path)
        foo_dsc_path = os.path.join(foo_path, 'foo_666.dsc')
        with open(foo_dsc_path, 'w') as foo_dsc:
            foo_dsc.write('Hello world')

        pub_source = self.getPubSource(filecontent="Something")
        pub_source.publish(self.disk_pool, self.logger)

        # And an oops should be filed for the error.
        self.assertEqual("PoolFileOverwriteError", self.oopses[0]['type'])

        self.layer.commit()
        self.assertEqual(pub_source.status, PackagePublishingStatus.PENDING)
        self.assertEqual(open(foo_dsc_path).read().strip(), 'Hello world')

    def testPublishingDifferentContents(self):
        """Test if publishOne refuses to overwrite its own publication."""
        pub_source = self.getPubSource(filecontent='foo is happy')
        pub_source.publish(self.disk_pool, self.logger)
        self.layer.commit()

        foo_name = "%s/main/f/foo/foo_666.dsc" % self.pool_dir
        pub_source.sync()
        self.assertEqual(pub_source.status, PackagePublishingStatus.PUBLISHED)
        self.assertEqual(open(foo_name).read().strip(), 'foo is happy')

        # try to publish 'foo' again with a different content, it
        # raises internally and keeps the files with the original
        # content.
        pub_source2 = self.getPubSource(filecontent='foo is depressing')
        pub_source2.publish(self.disk_pool, self.logger)
        self.layer.commit()

        pub_source2.sync()
        self.assertEqual(pub_source2.status, PackagePublishingStatus.PENDING)
        self.assertEqual(open(foo_name).read().strip(), 'foo is happy')

    def testPublishingAlreadyInPool(self):
        """Test if publishOne works if file is already in Pool.

        It should identify that the file has the same content and
        mark it as PUBLISHED.
        """
        pub_source = self.getPubSource(
            sourcename='bar', filecontent='bar is good')
        pub_source.publish(self.disk_pool, self.logger)
        self.layer.commit()
        bar_name = "%s/main/b/bar/bar_666.dsc" % self.pool_dir
        self.assertEqual(open(bar_name).read().strip(), 'bar is good')
        pub_source.sync()
        self.assertEqual(pub_source.status, PackagePublishingStatus.PUBLISHED)

        pub_source2 = self.getPubSource(
            sourcename='bar', filecontent='bar is good')
        pub_source2.publish(self.disk_pool, self.logger)
        self.layer.commit()
        pub_source2.sync()
        self.assertEqual(pub_source2.status, PackagePublishingStatus.PUBLISHED)

    def testPublishingSymlink(self):
        """Test if publishOne moving publication between components.

        After check if the pool file contents as the same, it should
        create a symlink in the new pointing to the original file.
        """
        content = 'am I a file or a symbolic link ?'
        # publish sim.dsc in main and re-publish in universe
        pub_source = self.getPubSource(sourcename='sim', filecontent=content)
        pub_source2 = self.getPubSource(
            sourcename='sim', component='universe', filecontent=content)
        pub_source.publish(self.disk_pool, self.logger)
        pub_source2.publish(self.disk_pool, self.logger)
        self.layer.commit()

        pub_source.sync()
        pub_source2.sync()
        self.assertEqual(pub_source.status, PackagePublishingStatus.PUBLISHED)
        self.assertEqual(pub_source2.status, PackagePublishingStatus.PUBLISHED)

        # check the resulted symbolic link
        sim_universe = "%s/universe/s/sim/sim_666.dsc" % self.pool_dir
        self.assertEqual(
            os.readlink(sim_universe), '../../../main/s/sim/sim_666.dsc')

        # if the contexts don't match it raises, so the publication
        # remains pending.
        pub_source3 = self.getPubSource(
            sourcename='sim', component='restricted',
            filecontent='It is all my fault')
        pub_source3.publish(self.disk_pool, self.logger)
        self.layer.commit()

        pub_source3.sync()
        self.assertEqual(pub_source3.status, PackagePublishingStatus.PENDING)

    def testPublishInAnotherArchive(self):
        """Publication in another archive

        Basically test if publishing records target to other archive
        than Distribution.main_archive work as expected
        """
        cprov = getUtility(IPersonSet).getByName('cprov')
        test_pool_dir = tempfile.mkdtemp()
        test_temp_dir = tempfile.mkdtemp()
        test_disk_pool = DiskPool(test_pool_dir, test_temp_dir, self.logger)

        pub_source = self.getPubSource(
            sourcename="foo", filecontent='Am I a PPA Record ?',
            archive=cprov.archive)
        pub_source.publish(test_disk_pool, self.logger)
        self.layer.commit()

        pub_source.sync()
        self.assertEqual(pub_source.status, PackagePublishingStatus.PUBLISHED)
        self.assertEqual(pub_source.sourcepackagerelease.upload_archive,
                         cprov.archive)
        foo_name = "%s/main/f/foo/foo_666.dsc" % test_pool_dir
        self.assertEqual(open(foo_name).read().strip(), 'Am I a PPA Record ?')

        # Remove locally created dir.
        shutil.rmtree(test_pool_dir)
        shutil.rmtree(test_temp_dir)


class BuildRecordCreationTests(TestNativePublishingBase):
    """Test the creation of build records."""

    def setUp(self):
        super(BuildRecordCreationTests, self).setUp()
        self.distro = self.factory.makeDistribution()
        self.distroseries = self.factory.makeDistroSeries(
            distribution=self.distro, name="crazy")
        self.archive = self.factory.makeArchive()
        self.avr = self.factory.makeProcessor(name="avr2001", restricted=True)
        self.avr_distroarch = self.factory.makeDistroArchSeries(
            architecturetag='avr', processor=self.avr,
            distroseries=self.distroseries, supports_virtualized=True)
        self.sparc = self.factory.makeProcessor(
            name="sparc64", restricted=False)
        self.sparc_distroarch = self.factory.makeDistroArchSeries(
            architecturetag='sparc', processor=self.sparc,
            distroseries=self.distroseries, supports_virtualized=True)
        self.distroseries.nominatedarchindep = self.sparc_distroarch
        self.addFakeChroots(self.distroseries)

    def getPubSource(self, architecturehintlist):
        """Return a mock source package publishing record for the archive
        and architecture used in this testcase.

        :param architecturehintlist: Architecture hint list
            (e.g. "i386 amd64")
        """
        return super(BuildRecordCreationTests, self).getPubSource(
            archive=self.archive, distroseries=self.distroseries,
            architecturehintlist=architecturehintlist)

    def test__getAllowedArchitectures_restricted(self):
        """Test _getAllowedArchitectures doesn't return unrestricted
        archs.

        For a normal archive, only unrestricted architectures should
        be used.
        """
        available_archs = [self.sparc_distroarch, self.avr_distroarch]
        pubrec = self.getPubSource(architecturehintlist='any')
        self.assertEqual(
            [self.sparc_distroarch],
            pubrec._getAllowedArchitectures(available_archs))

    def test__getAllowedArchitectures_restricted_override(self):
        """Test _getAllowedArchitectures honors overrides of restricted archs.

        Restricted architectures should only be allowed if there is
        an explicit ArchiveArch association with the archive.
        """
        available_archs = [self.sparc_distroarch, self.avr_distroarch]
        getUtility(IArchiveArchSet).new(self.archive, self.avr)
        pubrec = self.getPubSource(architecturehintlist='any')
        self.assertEqual(
            [self.sparc_distroarch, self.avr_distroarch],
            pubrec._getAllowedArchitectures(available_archs))

    def test_createMissingBuilds_restricts_any(self):
        """createMissingBuilds() should limit builds targeted at 'any'
        architecture to those allowed for the archive.
        """
        pubrec = self.getPubSource(architecturehintlist='any')
        builds = pubrec.createMissingBuilds()
        self.assertEqual(1, len(builds))
        self.assertEqual(self.sparc_distroarch, builds[0].distro_arch_series)

    def test_createMissingBuilds_restricts_explicitlist(self):
        """createMissingBuilds() limits builds targeted at a variety of
        architectures architecture to those allowed for the archive.
        """
        pubrec = self.getPubSource(architecturehintlist='sparc i386 avr')
        builds = pubrec.createMissingBuilds()
        self.assertEqual(1, len(builds))
        self.assertEqual(self.sparc_distroarch, builds[0].distro_arch_series)

    def test_createMissingBuilds_restricts_all(self):
        """createMissingBuilds() should limit builds targeted at 'all'
        architectures to the nominated independent architecture,
        if that is allowed for the archive.
        """
        pubrec = self.getPubSource(architecturehintlist='all')
        builds = pubrec.createMissingBuilds()
        self.assertEqual(1, len(builds))
        self.assertEqual(self.sparc_distroarch, builds[0].distro_arch_series)

    def test_createMissingBuilds_restrict_override(self):
        """createMissingBuilds() should limit builds targeted at 'any'
        architecture to architectures that are unrestricted or
        explicitly associated with the archive.
        """
        getUtility(IArchiveArchSet).new(self.archive, self.avr)
        pubrec = self.getPubSource(architecturehintlist='any')
        builds = pubrec.createMissingBuilds()
        self.assertEqual(2, len(builds))
        self.assertEqual(self.avr_distroarch, builds[0].distro_arch_series)
        self.assertEqual(self.sparc_distroarch, builds[1].distro_arch_series)


class PublishingSetTests(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(PublishingSetTests, self).setUp()
        self.distroseries = self.factory.makeDistroSeries()
        self.archive = self.factory.makeArchive(
            distribution=self.distroseries.distribution)
        self.publishing = self.factory.makeSourcePackagePublishingHistory(
            distroseries=self.distroseries, archive=self.archive)
        self.publishing_set = getUtility(IPublishingSet)

    def test_getByIdAndArchive_finds_record(self):
        record = self.publishing_set.getByIdAndArchive(
            self.publishing.id, self.archive)
        self.assertEqual(self.publishing, record)

    def test_getByIdAndArchive_finds_record_explicit_source(self):
        record = self.publishing_set.getByIdAndArchive(
            self.publishing.id, self.archive, source=True)
        self.assertEqual(self.publishing, record)

    def test_getByIdAndArchive_wrong_archive(self):
        wrong_archive = self.factory.makeArchive()
        record = self.publishing_set.getByIdAndArchive(
            self.publishing.id, wrong_archive)
        self.assertEqual(None, record)

    def makeBinaryPublishing(self):
        distroarchseries = self.factory.makeDistroArchSeries(
            distroseries=self.distroseries)
        binary_publishing = self.factory.makeBinaryPackagePublishingHistory(
            archive=self.archive, distroarchseries=distroarchseries)
        return binary_publishing

    def test_getByIdAndArchive_wrong_type(self):
        self.makeBinaryPublishing()
        record = self.publishing_set.getByIdAndArchive(
            self.publishing.id, self.archive, source=False)
        self.assertEqual(None, record)

    def test_getByIdAndArchive_finds_binary(self):
        binary_publishing = self.makeBinaryPublishing()
        record = self.publishing_set.getByIdAndArchive(
            binary_publishing.id, self.archive, source=False)
        self.assertEqual(binary_publishing, record)

    def test_getByIdAndArchive_binary_wrong_archive(self):
        binary_publishing = self.makeBinaryPublishing()
        wrong_archive = self.factory.makeArchive()
        record = self.publishing_set.getByIdAndArchive(
            binary_publishing.id, wrong_archive, source=False)
        self.assertEqual(None, record)


class TestPublishingSetLite(TestCaseWithFactory):

    layer = ZopelessDatabaseLayer

    def setUp(self):
        super(TestPublishingSetLite, self).setUp()
        self.person = self.factory.makePerson()

    def test_requestDeletion_marks_SPPHs_deleted(self):
        spph = self.factory.makeSourcePackagePublishingHistory()
        getUtility(IPublishingSet).requestDeletion([spph], self.person)
        self.assertEqual(PackagePublishingStatus.DELETED, spph.status)

    def test_requestDeletion_leaves_other_SPPHs_alone(self):
        spph = self.factory.makeSourcePackagePublishingHistory()
        other_spph = self.factory.makeSourcePackagePublishingHistory()
        getUtility(IPublishingSet).requestDeletion([other_spph], self.person)
        self.assertEqual(PackagePublishingStatus.PENDING, spph.status)

    def test_requestDeletion_marks_BPPHs_deleted(self):
        bpph = self.factory.makeBinaryPackagePublishingHistory()
        getUtility(IPublishingSet).requestDeletion([bpph], self.person)
        self.assertEqual(PackagePublishingStatus.DELETED, bpph.status)

    def test_requestDeletion_marks_attached_BPPHs_deleted(self):
        bpph = self.factory.makeBinaryPackagePublishingHistory()
        spph = self.factory.makeSPPHForBPPH(bpph)
        getUtility(IPublishingSet).requestDeletion([spph], self.person)
        self.assertEqual(PackagePublishingStatus.DELETED, spph.status)

    def test_requestDeletion_leaves_other_BPPHs_alone(self):
        bpph = self.factory.makeBinaryPackagePublishingHistory()
        unrelated_spph = self.factory.makeSourcePackagePublishingHistory()
        getUtility(IPublishingSet).requestDeletion(
            [unrelated_spph], self.person)
        self.assertEqual(PackagePublishingStatus.PENDING, bpph.status)

    def test_requestDeletion_accepts_empty_sources_list(self):
        getUtility(IPublishingSet).requestDeletion([], self.person)
        # The test is that this does not fail.
        Store.of(self.person).flush()

    def test_requestDeletion_creates_DistroSeriesDifferenceJobs(self):
        dsp = self.factory.makeDistroSeriesParent()
        spph = self.factory.makeSourcePackagePublishingHistory(
            dsp.derived_series, pocket=PackagePublishingPocket.RELEASE)
        spn = spph.sourcepackagerelease.sourcepackagename
        getUtility(IPublishingSet).requestDeletion([spph], self.person)
        self.assertEqual(
            1, len(find_waiting_jobs(
                dsp.derived_series, spn, dsp.parent_series)))

    def test_requestDeletion_disallows_unmodifiable_suites(self):
        bpph = self.factory.makeBinaryPackagePublishingHistory(
            pocket=PackagePublishingPocket.RELEASE)
        spph = self.factory.makeSourcePackagePublishingHistory(
            distroseries=bpph.distroseries,
            pocket=PackagePublishingPocket.RELEASE)
        spph.distroseries.status = SeriesStatus.CURRENT
        message = "Cannot delete publications from suite '%s'" % (
            spph.distroseries.getSuite(spph.pocket))
        for pub in spph, bpph:
            self.assertRaisesWithContent(
                DeletionError, message, pub.requestDeletion, self.person)
            self.assertRaisesWithContent(
                DeletionError, message, pub.api_requestDeletion, self.person)

    def test_requestDeletion_marks_debug_as_deleted(self):
        matching_bpph, debug_matching_bpph = (
            self.factory.makeBinaryPackagePublishingHistory(
                pocket=PackagePublishingPocket.RELEASE, with_debug=True))
        non_match_bpph = self.factory.makeBinaryPackagePublishingHistory(
            pocket=PackagePublishingPocket.RELEASE)
        non_match_bpr = removeSecurityProxy(
            non_match_bpph.binarypackagerelease)
        debug_non_match_bpph = self.factory.makeBinaryPackagePublishingHistory(
            pocket=PackagePublishingPocket.RELEASE,
            binpackageformat=BinaryPackageFormat.DDEB)
        debug_non_match_bpr = debug_non_match_bpph.binarypackagerelease
        non_match_bpr.debug_package = debug_non_match_bpr
        getUtility(IPublishingSet).requestDeletion(
            [matching_bpph, non_match_bpph], self.person)
        for pub in (matching_bpph, debug_matching_bpph, non_match_bpph):
            self.assertEqual(pub.status, PackagePublishingStatus.DELETED)
        self.assertEqual(
            debug_non_match_bpph.status, PackagePublishingStatus.PENDING)

    def test_changeOverride_also_overrides_debug_package(self):
        bpph, debug_bpph = self.factory.makeBinaryPackagePublishingHistory(
            pocket=PackagePublishingPocket.RELEASE, with_debug=True)
        new_section = self.factory.makeSection()
        new_bpph = bpph.changeOverride(new_section=new_section)
        publishing_set = getUtility(IPublishingSet)
        [new_debug_bpph] = publishing_set.findCorrespondingDDEBPublications(
            [new_bpph])
        self.assertEqual(new_debug_bpph.section, new_section)

    def test_requestDeletion_forbids_debug_package(self):
        bpph, debug_bpph = self.factory.makeBinaryPackagePublishingHistory(
            pocket=PackagePublishingPocket.RELEASE, with_debug=True)
        self.assertRaisesWithContent(
            DeletionError, "Cannot delete ddeb publications directly; delete "
            "the corresponding deb instead.",
            debug_bpph.requestDeletion, self.factory.makePerson())

    def test_changeOverride_forbids_debug_package(self):
        bpph, debug_bpph = self.factory.makeBinaryPackagePublishingHistory(
            pocket=PackagePublishingPocket.RELEASE, with_debug=True)
        self.assertRaisesWithContent(
            OverrideError, "Cannot override ddeb publications directly; "
            "override the corresponding deb instead.",
            debug_bpph.changeOverride, new_phased_update_percentage=20)


class TestSourceDomination(TestNativePublishingBase):
    """Test SourcePackagePublishingHistory.supersede() operates correctly."""

    def testSupersede(self):
        """Check that supersede() without arguments works."""
        source = self.getPubSource()
        source.supersede()
        self.checkSuperseded([source])

    def testSupersedeWithDominant(self):
        """Check that supersede() with a dominant publication works."""
        source = self.getPubSource()
        super_source = self.getPubSource()
        source.supersede(super_source)
        self.checkSuperseded([source], super_source)

    def testSupersedingSupersededSourceFails(self):
        """Check that supersede() fails with a superseded source.

        Sources should not be superseded twice. If a second attempt is made,
        the Dominator's lookups are buggy.
        """
        source = self.getPubSource()
        super_source = self.getPubSource()
        source.supersede(super_source)
        self.checkSuperseded([source], super_source)

        # Manually set a date in the past, so we can confirm that
        # the second supersede() fails properly.
        source.datesuperseded = datetime.datetime(
            2006, 12, 25, tzinfo=pytz.timezone("UTC"))
        super_date = source.datesuperseded

        self.assertRaises(AssertionError, source.supersede, super_source)
        self.checkSuperseded([source], super_source)
        self.assertEqual(super_date, source.datesuperseded)


class TestBinaryDomination(TestNativePublishingBase):
    """Test BinaryPackagePublishingHistory.supersede() operates correctly."""

    def testSupersede(self):
        """Check that supersede() without arguments works."""
        bins = self.getPubBinaries(architecturespecific=True)
        bins[0].supersede()
        self.checkSuperseded([bins[0]])
        self.checkPublication(bins[1], PackagePublishingStatus.PENDING)

    def testSupersedeWithDominant(self):
        """Check that supersede() with a dominant publication works."""
        bins = self.getPubBinaries(architecturespecific=True)
        super_bins = self.getPubBinaries(architecturespecific=True)
        bins[0].supersede(super_bins[0])
        self.checkSuperseded([bins[0]], super_bins[0])
        self.checkPublication(bins[1], PackagePublishingStatus.PENDING)

    def testSupersedesArchIndepBinariesAtomically(self):
        """Check that supersede() supersedes arch-indep binaries atomically.

        Architecture-independent binaries should be removed from all
        architectures when they are superseded on at least one (bug #48760).
        """
        bins = self.getPubBinaries(architecturespecific=False)
        super_bins = self.getPubBinaries(architecturespecific=False)
        bins[0].supersede(super_bins[0])
        self.checkSuperseded(bins, super_bins[0])

    def testAtomicDominationRespectsOverrides(self):
        """Check that atomic domination only covers identical overrides.

        This is important, as otherwise newly-overridden arch-indep binaries
        will supersede themselves, and vanish entirely (bug #178102).  We
        check both DEBs and DDEBs.
        """
        universe = getUtility(IComponentSet)['universe']
        games = getUtility(ISectionSet)['games']
        for name, override in (
            ("component", {"new_component": universe}),
            ("section", {"new_section": games}),
            ("priority", {"new_priority": PackagePublishingPriority.EXTRA}),
            ("phase", {"new_phased_update_percentage": 50})):
            bins = self.getPubBinaries(
                binaryname=name, architecturespecific=False)

            super_bins = []
            for bin in bins:
                super_bins.append(bin.changeOverride(**override))

            bins[0].supersede(super_bins[0])
            self.checkSuperseded(bins, super_bins[0])
            self.checkPublications(super_bins, PackagePublishingStatus.PENDING)

    def testSupersedingSupersededArchSpecificBinaryFails(self):
        """Check that supersede() fails with a superseded arch-dep binary.

        Architecture-specific binaries should not normally be superseded
        twice. If a second attempt is made, the Dominator's lookups are buggy.
        """
        bin = self.getPubBinaries(architecturespecific=True)[0]
        super_bin = self.getPubBinaries(architecturespecific=True)[0]
        bin.supersede(super_bin)

        # Manually set a date in the past, so we can confirm that
        # the second supersede() fails properly.
        bin.datesuperseded = datetime.datetime(
            2006, 12, 25, tzinfo=pytz.timezone("UTC"))
        super_date = bin.datesuperseded

        self.assertRaises(AssertionError, bin.supersede, super_bin)
        self.checkSuperseded([bin], super_bin)
        self.assertEqual(super_date, bin.datesuperseded)

    def testSkipsSupersededArchIndependentBinary(self):
        """Check that supersede() skips a superseded arch-indep binary.

        Since all publications of an architecture-independent binary are
        superseded atomically, they may be superseded again later. In that
        case, we skip the domination, leaving the old date unchanged.
        """
        bin = self.getPubBinaries(architecturespecific=False)[0]
        super_bin = self.getPubBinaries(architecturespecific=False)[0]
        bin.supersede(super_bin)
        self.checkSuperseded([bin], super_bin)

        # Manually set a date in the past, so we can confirm that
        # the second supersede() skips properly.
        bin.datesuperseded = datetime.datetime(
            2006, 12, 25, tzinfo=pytz.timezone("UTC"))
        super_date = bin.datesuperseded

        bin.supersede(super_bin)
        self.checkSuperseded([bin], super_bin)
        self.assertEqual(super_date, bin.datesuperseded)

    def testSupersedesCorrespondingDDEB(self):
        """Check that supersede() takes with it any corresponding DDEB.

        DDEB publications should be superseded when their corresponding DEB
        is.
        """
        # Each of these will return (i386 deb, i386 ddeb, hppa deb,
        # hppa ddeb).
        bins = self.getPubBinaries(architecturespecific=True, with_debug=True)
        super_bins = self.getPubBinaries(
            architecturespecific=True, with_debug=True)

        bins[0].supersede(super_bins[0])
        self.checkSuperseded(bins[:2], super_bins[0])
        self.checkPublications(bins[2:], PackagePublishingStatus.PENDING)
        self.checkPublications(super_bins, PackagePublishingStatus.PENDING)

        bins[2].supersede(super_bins[2])
        self.checkSuperseded(bins[:2], super_bins[0])
        self.checkSuperseded(bins[2:], super_bins[2])
        self.checkPublications(super_bins, PackagePublishingStatus.PENDING)

    def testDDEBsCannotSupersede(self):
        """Check that DDEBs cannot supersede other publications.

        Since DDEBs are superseded when their DEBs are, there's no need to
        for them supersede anything themselves. Any such attempt is an error.
        """
        # This will return (i386 deb, i386 ddeb, hppa deb, hppa ddeb).
        bins = self.getPubBinaries(architecturespecific=True, with_debug=True)
        self.assertRaises(AssertionError, bins[0].supersede, bins[1])


class TestBinaryGetOtherPublications(TestNativePublishingBase):
    """Test BinaryPackagePublishingHistory._getOtherPublications() works."""

    def checkOtherPublications(self, this, others):
        self.assertContentEqual(
            removeSecurityProxy(this)._getOtherPublications(), others)

    def testFindsOtherArchIndepPublications(self):
        """Arch-indep publications with the same overrides should be found."""
        bins = self.getPubBinaries(architecturespecific=False)
        self.checkOtherPublications(bins[0], bins)

    def testDoesntFindArchSpecificPublications(self):
        """Arch-dep publications shouldn't be found."""
        bins = self.getPubBinaries(architecturespecific=True)
        self.checkOtherPublications(bins[0], [bins[0]])

    def testDoesntFindPublicationsInOtherArchives(self):
        """Publications in other archives shouldn't be found."""
        bins = self.getPubBinaries(architecturespecific=False)
        foreign_bins = bins[0].copyTo(
            bins[0].distroarchseries.distroseries, bins[0].pocket,
            self.factory.makeArchive())
        self.checkOtherPublications(bins[0], bins)
        self.checkOtherPublications(foreign_bins[0], foreign_bins)

    def testDoesntFindPublicationsWithDifferentOverrides(self):
        """Publications with different overrides shouldn't be found."""
        bins = self.getPubBinaries(architecturespecific=False)
        universe = getUtility(IComponentSet)['universe']
        foreign_bin = bins[0].changeOverride(new_component=universe)
        self.checkOtherPublications(bins[0], bins)
        self.checkOtherPublications(foreign_bin, [foreign_bin])

    def testDoesntFindSupersededPublications(self):
        """Superseded publications shouldn't be found."""
        bins = self.getPubBinaries(architecturespecific=False)
        self.checkOtherPublications(bins[0], bins)
        # This will supersede both atomically.
        bins[0].supersede()
        self.checkOtherPublications(bins[0], [])

    def testDoesntFindPublicationsInOtherSeries(self):
        """Publications in other series shouldn't be found."""
        bins = self.getPubBinaries(architecturespecific=False)
        series = self.factory.makeDistroSeries()
        self.factory.makeDistroArchSeries(
            distroseries=series, architecturetag='i386')
        foreign_bins = bins[0].copyTo(
            series, bins[0].pocket, bins[0].archive)
        self.checkOtherPublications(bins[0], bins)
        self.checkOtherPublications(foreign_bins[0], foreign_bins)


class TestGetOtherPublicationsForSameSource(TestNativePublishingBase):
    """Test parts of the BinaryPackagePublishingHistory model.

    See also lib/lp/soyuz/doc/publishing.txt
    """

    layer = LaunchpadZopelessLayer

    def _makeMixedSingleBuildPackage(self, version="1.0"):
        # Set up a source with a build that generated four binaries,
        # two of them an arch-all.
        foo_src_pub = self.getPubSource(
            sourcename="foo", version=version, architecturehintlist="i386",
            status=PackagePublishingStatus.PUBLISHED)
        [foo_bin_pub] = self.getPubBinaries(
            binaryname="foo-bin", status=PackagePublishingStatus.PUBLISHED,
            architecturespecific=True, version=version,
            pub_source=foo_src_pub)
        # Now need to grab the build for the source so we can add
        # more binaries to it.
        [build] = foo_src_pub.getBuilds()
        foo_one_common = self.factory.makeBinaryPackageRelease(
            binarypackagename="foo-one-common", version=version, build=build,
            architecturespecific=False)
        foo_one_common_pubs = self.publishBinaryInArchive(
            foo_one_common, self.ubuntutest.main_archive,
            pocket=foo_src_pub.pocket,
            status=PackagePublishingStatus.PUBLISHED)
        foo_two_common = self.factory.makeBinaryPackageRelease(
            binarypackagename="foo-two-common", version=version, build=build,
            architecturespecific=False)
        foo_two_common_pubs = self.publishBinaryInArchive(
            foo_two_common, self.ubuntutest.main_archive,
            pocket=foo_src_pub.pocket,
            status=PackagePublishingStatus.PUBLISHED)
        foo_three = self.factory.makeBinaryPackageRelease(
            binarypackagename="foo-three", version=version, build=build,
            architecturespecific=True)
        [foo_three_pub] = self.publishBinaryInArchive(
            foo_three, self.ubuntutest.main_archive,
            pocket=foo_src_pub.pocket,
            status=PackagePublishingStatus.PUBLISHED)
        # So now we have source foo, which has arch specific binaries
        # foo-bin and foo-three, and arch:all binaries foo-one-common and
        # foo-two-common. The latter two will have multiple publications,
        # one for each DAS in the series.
        return (
            foo_src_pub, foo_bin_pub, foo_one_common_pubs,
            foo_two_common_pubs, foo_three_pub)


class TestGetBuiltBinaries(TestNativePublishingBase):
    """Test SourcePackagePublishingHistory.getBuiltBinaries() works."""

    def test_flat_query_count(self):
        spph = self.getPubSource(architecturehintlist='any')
        store = Store.of(spph)
        store.flush()
        store.invalidate()

        # An initial invocation issues one query for the each of the
        # SPPH, BPPHs and BPRs.
        with StormStatementRecorder() as recorder:
            bins = spph.getBuiltBinaries()
        self.assertEqual(0, len(bins))
        self.assertThat(recorder, HasQueryCount(Equals(3)))

        self.getPubBinaries(pub_source=spph)
        store.flush()
        store.invalidate()

        # A subsequent invocation with files preloaded queries the SPPH,
        # BPPHs, BPRs, BPFs and LFAs. Checking the filenames of each
        # BPF has no query penalty.
        with StormStatementRecorder() as recorder:
            bins = spph.getBuiltBinaries(want_files=True)
            self.assertEqual(2, len(bins))
            for bpph in bins:
                files = bpph.binarypackagerelease.files
                self.assertEqual(1, len(files))
                for bpf in files:
                    bpf.libraryfile.filename
        self.assertThat(recorder, HasQueryCount(Equals(5)))


class TestPublishBinaries(TestCaseWithFactory):
    """Test PublishingSet.publishBinaries() works."""

    layer = LaunchpadZopelessLayer

    def makeArgs(self, bprs, distroseries, archive=None):
        """Create a dict of arguments for publishBinaries."""
        if archive is None:
            archive = distroseries.main_archive
        return {
            'archive': archive,
            'distroseries': distroseries,
            'pocket': PackagePublishingPocket.BACKPORTS,
            'binaries': dict(
                (bpr, (self.factory.makeComponent(),
                 self.factory.makeSection(),
                 PackagePublishingPriority.REQUIRED, 50)) for bpr in bprs),
            }

    def test_architecture_dependent(self):
        # Architecture-dependent binaries get created as PENDING in the
        # corresponding architecture of the destination series and pocket,
        # with the given overrides.
        arch_tag = self.factory.getUniqueString('arch-')
        orig_das = self.factory.makeDistroArchSeries(
            architecturetag=arch_tag)
        target_das = self.factory.makeDistroArchSeries(
            architecturetag=arch_tag)
        build = self.factory.makeBinaryPackageBuild(distroarchseries=orig_das)
        bpr = self.factory.makeBinaryPackageRelease(
            build=build, architecturespecific=True)
        args = self.makeArgs([bpr], target_das.distroseries)
        [bpph] = getUtility(IPublishingSet).publishBinaries(**args)
        overrides = args['binaries'][bpr]
        self.assertEqual(bpr, bpph.binarypackagerelease)
        self.assertEqual(
            (args['archive'], target_das, args['pocket']),
            (bpph.archive, bpph.distroarchseries, bpph.pocket))
        self.assertEqual(
            overrides,
            (bpph.component, bpph.section, bpph.priority,
             bpph.phased_update_percentage))
        self.assertEqual(PackagePublishingStatus.PENDING, bpph.status)

    def test_architecture_independent(self):
        # Architecture-independent binaries get published to all enabled
        # DASes in the series.
        bpr = self.factory.makeBinaryPackageRelease(architecturespecific=False)
        # Create 3 architectures. The binary will not be published in
        # the disabled one.
        target_das_a = self.factory.makeDistroArchSeries()
        target_das_b = self.factory.makeDistroArchSeries(
            distroseries=target_das_a.distroseries)
        # We don't reference target_das_c so it doesn't get a name.
        self.factory.makeDistroArchSeries(
            distroseries=target_das_a.distroseries, enabled=False)
        args = self.makeArgs([bpr], target_das_a.distroseries)
        bpphs = getUtility(IPublishingSet).publishBinaries(**args)
        self.assertEqual(2, len(bpphs))
        self.assertContentEqual(
            (target_das_a, target_das_b),
            [bpph.distroarchseries for bpph in bpphs])

    def test_architecture_disabled(self):
        # An empty list is return if the DistroArchSeries was disabled.
        arch_tag = self.factory.getUniqueString('arch-')
        orig_das = self.factory.makeDistroArchSeries(
            architecturetag=arch_tag)
        target_das = self.factory.makeDistroArchSeries(
            architecturetag=arch_tag)
        build = self.factory.makeBinaryPackageBuild(distroarchseries=orig_das)
        bpr = self.factory.makeBinaryPackageRelease(
            build=build, architecturespecific=True)
        target_das.enabled = False
        args = self.makeArgs([bpr], target_das.distroseries)
        results = getUtility(IPublishingSet).publishBinaries(**args)
        self.assertEqual([], results)

    def test_does_not_duplicate(self):
        # An attempt to copy something for a second time is ignored.
        bpr = self.factory.makeBinaryPackageRelease()
        target_das = self.factory.makeDistroArchSeries()
        args = self.makeArgs([bpr], target_das.distroseries)
        [new_bpph] = getUtility(IPublishingSet).publishBinaries(**args)
        self.assertContentEqual(
            [], getUtility(IPublishingSet).publishBinaries(**args))

        # But changing the target (eg. to RELEASE instead of BACKPORTS)
        # causes a new publication to be created.
        args['pocket'] = PackagePublishingPocket.RELEASE
        [another_bpph] = getUtility(IPublishingSet).publishBinaries(**args)

    def test_primary_ddebs_need_ddebs_enabled(self):
        debug = self.factory.makeBinaryPackageRelease(
            binpackageformat=BinaryPackageFormat.DDEB)
        args = self.makeArgs(
            [debug], debug.build.distro_arch_series.distroseries)

        # ddebs are rejected with build_debug_symbols unset
        self.assertRaises(
            QueueInconsistentStateError,
            getUtility(IPublishingSet).publishBinaries, **args)

        # But accepted with build_debug_symbols set
        archive = debug.build.distro_arch_series.distroseries.main_archive
        archive.build_debug_symbols = True
        getUtility(IPublishingSet).publishBinaries(**args)


class TestChangeOverride(TestNativePublishingBase):
    """Test that changing overrides works."""

    def setUpOverride(self, status=SeriesStatus.DEVELOPMENT,
                      pocket=PackagePublishingPocket.RELEASE, binary=False,
                      ddeb=False, **kwargs):
        self.distroseries.status = status
        if ddeb:
            pub = self.getPubBinaries(pocket=pocket, with_debug=True)[2]
            self.assertEqual(
                BinaryPackageFormat.DDEB,
                pub.binarypackagerelease.binpackageformat)
        elif binary:
            pub = self.getPubBinaries(pocket=pocket)[0]
        else:
            pub = self.getPubSource(pocket=pocket)
        return pub.changeOverride(**kwargs)

    def assertCanOverride(self, status=SeriesStatus.DEVELOPMENT,
                          pocket=PackagePublishingPocket.RELEASE, **kwargs):
        new_pub = self.setUpOverride(status=status, pocket=pocket, **kwargs)
        self.assertEqual(new_pub.status, PackagePublishingStatus.PENDING)
        self.assertEqual(new_pub.pocket, pocket)
        if "new_component" in kwargs:
            self.assertEqual(kwargs["new_component"], new_pub.component.name)
        if "new_section" in kwargs:
            self.assertEqual(kwargs["new_section"], new_pub.section.name)
        if "new_priority" in kwargs:
            self.assertEqual(
                kwargs["new_priority"], new_pub.priority.name.lower())
        if "new_phased_update_percentage" in kwargs:
            self.assertEqual(
                kwargs["new_phased_update_percentage"],
                new_pub.phased_update_percentage)
        return new_pub

    def assertCannotOverride(self, **kwargs):
        self.assertRaises(OverrideError, self.setUpOverride, **kwargs)

    def test_changes_source(self):
        # SPPH.changeOverride changes the properties of source publications.
        self.assertCanOverride(new_component="universe", new_section="misc")

    def test_changes_binary(self):
        # BPPH.changeOverride changes the properties of binary publications.
        self.assertCanOverride(
            binary=True, new_component="universe", new_section="misc",
            new_priority="extra", new_phased_update_percentage=90)

    def test_set_and_clear_phased_update_percentage(self):
        # new_phased_update_percentage=<integer> sets a phased update
        # percentage; new_phased_update_percentage=100 clears it.
        pub = self.assertCanOverride(
            binary=True, new_phased_update_percentage=50)
        new_pub = pub.changeOverride(new_phased_update_percentage=100)
        self.assertIsNone(new_pub.phased_update_percentage)

    def test_no_change(self):
        # changeOverride does not create a new publication if the existing
        # publication is already in the desired state.
        self.assertIsNone(
            self.setUpOverride(new_component="main", new_section="base"))
        self.assertIsNone(
            self.setUpOverride(
                binary=True, new_component="main", new_section="base",
                new_priority="standard"))

    def test_forbids_stable_RELEASE(self):
        # changeOverride is not allowed in the RELEASE pocket of a stable
        # distroseries.
        self.assertCannotOverride(
            status=SeriesStatus.CURRENT, new_component="universe")
        self.assertCannotOverride(
            status=SeriesStatus.CURRENT, binary=True, new_component="universe")

    def test_allows_development_RELEASE(self):
        # changeOverride is allowed in the RELEASE pocket of a development
        # distroseries.
        self.assertCanOverride(new_component="universe")
        self.assertCanOverride(binary=True, new_component="universe")

    def test_allows_stable_PROPOSED(self):
        # changeOverride is allowed in the PROPOSED pocket of a stable
        # distroseries.
        self.assertCanOverride(
            status=SeriesStatus.CURRENT,
            pocket=PackagePublishingPocket.PROPOSED, new_component="universe")
        self.assertCanOverride(
            status=SeriesStatus.CURRENT,
            pocket=PackagePublishingPocket.PROPOSED, binary=True,
            new_component="universe")

    def test_forbids_changing_archive(self):
        # changeOverride refuses to make changes that would require changing
        # archive.
        self.assertCannotOverride(new_component="partner")
        self.assertCannotOverride(binary=True, new_component="partner")
