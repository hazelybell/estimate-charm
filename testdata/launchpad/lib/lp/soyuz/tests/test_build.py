# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from datetime import (
    datetime,
    timedelta,
    )
from exceptions import AssertionError

import pytz
import transaction
from zope.component import getUtility

from lp.buildmaster.enums import BuildStatus
from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.interfaces.series import SeriesStatus
from lp.soyuz.enums import (
    ArchivePurpose,
    BinaryPackageFormat,
    PackagePublishingPriority,
    PackageUploadStatus,
    )
from lp.soyuz.interfaces.binarypackagebuild import CannotBeRescored
from lp.soyuz.interfaces.component import IComponentSet
from lp.soyuz.interfaces.publishing import PackagePublishingStatus
from lp.soyuz.tests.test_publishing import SoyuzTestPublisher
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import LaunchpadFunctionalLayer
from lp.testing.sampledata import ADMIN_EMAIL


class TestBuild(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestBuild, self).setUp()
        self.admin = getUtility(IPersonSet).getByEmail(ADMIN_EMAIL)
        self.processor = self.factory.makeProcessor()
        self.distroseries = self.factory.makeDistroSeries()
        self.das = self.factory.makeDistroArchSeries(
            distroseries=self.distroseries, processor=self.processor,
            supports_virtualized=True)
        with person_logged_in(self.admin):
            self.publisher = SoyuzTestPublisher()
            self.publisher.prepareBreezyAutotest()
            self.distroseries.nominatedarchindep = self.das
            self.publisher.addFakeChroots(distroseries=self.distroseries)
            self.builder = self.factory.makeBuilder(processor=self.processor)
        self.now = datetime.now(pytz.UTC)

    def test_title(self):
        # A build has a title which describes the context source version and
        # in which series and architecture it is targeted for.
        spph = self.publisher.getPubSource(
            sourcename=self.factory.getUniqueString(),
            version="%s.1" % self.factory.getUniqueInteger(),
            distroseries=self.distroseries)
        [build] = spph.createMissingBuilds()
        expected_title = '%s build of %s %s in %s %s RELEASE' % (
            self.das.architecturetag, spph.source_package_name,
            spph.source_package_version, self.distroseries.distribution.name,
            self.distroseries.name)
        self.assertEquals(expected_title, build.title)

    def test_linking(self):
        # A build directly links to the archive, distribution, distroseries,
        # distroarchseries, pocket in its context and also the source version
        # that generated it.
        spph = self.publisher.getPubSource(
            sourcename=self.factory.getUniqueString(),
            version="%s.1" % self.factory.getUniqueInteger(),
            distroseries=self.distroseries)
        [build] = spph.createMissingBuilds()
        self.assertEquals(self.distroseries.main_archive, build.archive)
        self.assertEquals(self.distroseries.distribution, build.distribution)
        self.assertEquals(self.distroseries, build.distro_series)
        self.assertEquals(self.das, build.distro_arch_series)
        self.assertEquals(PackagePublishingPocket.RELEASE, build.pocket)
        self.assertEquals(self.das.architecturetag, build.arch_tag)
        self.assertTrue(build.is_virtualized)
        self.assertEquals(
            '%s - %s' % (spph.source_package_name,
                spph.source_package_version),
            build.source_package_release.title)

    def test_processed_builds(self):
        # Builds which were already processed also offer additional
        # information about its process such as the time it was started and
        # finished and its 'log' and 'upload_changesfile' as librarian files.
        spn = self.factory.getUniqueString()
        version = "%s.1" % self.factory.getUniqueInteger()
        spph = self.publisher.getPubSource(
            sourcename=spn, version=version,
            distroseries=self.distroseries,
            status=PackagePublishingStatus.PUBLISHED)
        with person_logged_in(self.admin):
            binary = self.publisher.getPubBinaries(binaryname=spn,
                distroseries=self.distroseries, pub_source=spph,
                version=version, builder=self.builder)
        build = binary[0].binarypackagerelease.build
        self.assertTrue(build.was_built)
        self.assertEquals(
            PackageUploadStatus.DONE, build.package_upload.status)
        self.assertEquals(
            datetime(2008, 01, 01, 0, 0, 0, tzinfo=pytz.UTC),
            build.date_started)
        self.assertEquals(
            datetime(2008, 01, 01, 0, 5, 0, tzinfo=pytz.UTC),
            build.date_finished)
        self.assertEquals(timedelta(minutes=5), build.duration)
        expected_buildlog = 'buildlog_%s-%s-%s.%s_%s_FULLYBUILT.txt.gz' % (
            self.distroseries.distribution.name, self.distroseries.name,
            self.das.architecturetag, spn, version)
        self.assertEquals(expected_buildlog, build.log.filename)
        url_start = (
            'http://launchpad.dev/%s/+source/%s/%s/+build/%s/+files' % (
                self.distroseries.distribution.name, spn, version, build.id))
        expected_buildlog_url = '%s/%s' % (url_start, expected_buildlog)
        self.assertEquals(expected_buildlog_url, build.log_url)
        expected_changesfile = '%s_%s_%s.changes' % (
            spn, version, self.das.architecturetag)
        self.assertEquals(
            expected_changesfile, build.upload_changesfile.filename)
        expected_changesfile_url = '%s/%s' % (url_start, expected_changesfile)
        self.assertEquals(expected_changesfile_url, build.changesfile_url)
        # Since this build was sucessful, it can not be retried
        self.assertFalse(build.can_be_retried)

    def test_current_component(self):
        # The currently published component is provided via the
        # 'current_component' property.  It looks over the publishing records
        # and finds the current publication of the source in question.
        spph = self.publisher.getPubSource(
            sourcename=self.factory.getUniqueString(),
            version="%s.1" % self.factory.getUniqueInteger(),
            distroseries=self.distroseries)
        [build] = spph.createMissingBuilds()
        self.assertEquals('main', build.current_component.name)
        # It may not be the same as
        self.assertEquals('main', build.source_package_release.component.name)
        # If the package has no uploads, its package_upload is None
        self.assertEquals(None, build.package_upload)

    def test_current_component_when_unpublished(self):
        # Production has some buggy builds without source publications.
        # current_component returns None in that case.
        spph = self.publisher.getPubSource()
        other_das = self.factory.makeDistroArchSeries()
        build = spph.sourcepackagerelease.createBuild(
            other_das, PackagePublishingPocket.RELEASE, spph.archive)
        self.assertIs(None, build.current_component)

    def test_retry_for_released_series(self):
        # Builds can not be retried for released distroseries
        distroseries = self.factory.makeDistroSeries()
        das = self.factory.makeDistroArchSeries(
            distroseries=distroseries, processor=self.processor,
            supports_virtualized=True)
        with person_logged_in(self.admin):
            distroseries.nominatedarchindep = das
            distroseries.status = SeriesStatus.OBSOLETE
            self.publisher.addFakeChroots(distroseries=distroseries)
        spph = self.publisher.getPubSource(
            sourcename=self.factory.getUniqueString(),
            version="%s.1" % self.factory.getUniqueInteger(),
            distroseries=distroseries)
        [build] = spph.createMissingBuilds()
        self.assertFalse(build.can_be_retried)

    def test_partner_retry_for_released_series(self):
        # Builds for PARTNER can be retried -- even if the distroseries is
        # released.
        distroseries = self.factory.makeDistroSeries()
        das = self.factory.makeDistroArchSeries(
            distroseries=distroseries, processor=self.processor,
            supports_virtualized=True)
        archive = self.factory.makeArchive(
            purpose=ArchivePurpose.PARTNER,
            distribution=distroseries.distribution)
        with person_logged_in(self.admin):
            distroseries.nominatedarchindep = das
            distroseries.status = SeriesStatus.OBSOLETE
            self.publisher.addFakeChroots(distroseries=distroseries)
        spph = self.publisher.getPubSource(
            sourcename=self.factory.getUniqueString(),
            version="%s.1" % self.factory.getUniqueInteger(),
            distroseries=distroseries, archive=archive)
        [build] = spph.createMissingBuilds()
        build.updateStatus(BuildStatus.FAILEDTOBUILD)
        self.assertTrue(build.can_be_retried)

    def test_retry(self):
        # A build can be retried
        spph = self.publisher.getPubSource(
            sourcename=self.factory.getUniqueString(),
            version="%s.1" % self.factory.getUniqueInteger(),
            distroseries=self.distroseries)
        [build] = spph.createMissingBuilds()
        build.updateStatus(BuildStatus.FAILEDTOBUILD)
        self.assertTrue(build.can_be_retried)

    def test_retry_cancelled(self):
        # A cancelled build can be retried
        spph = self.publisher.getPubSource(
            sourcename=self.factory.getUniqueString(),
            version="%s.1" % self.factory.getUniqueInteger(),
            distroseries=self.distroseries)
        [build] = spph.createMissingBuilds()
        build.updateStatus(BuildStatus.CANCELLED)
        self.assertTrue(build.can_be_retried)

    def test_uploadlog(self):
        # The upload log can be attached to a build
        spph = self.publisher.getPubSource(
            sourcename=self.factory.getUniqueString(),
            version="%s.1" % self.factory.getUniqueInteger(),
            distroseries=self.distroseries)
        [build] = spph.createMissingBuilds()
        self.assertEquals(None, build.upload_log)
        self.assertEquals(None, build.upload_log_url)
        build.storeUploadLog('sample upload log')
        expected_filename = 'upload_%s_log.txt' % build.id
        self.assertEquals(expected_filename, build.upload_log.filename)
        url_start = (
            'http://launchpad.dev/%s/+source/%s/%s/+build/%s/+files' % (
                self.distroseries.distribution.name, spph.source_package_name,
                spph.source_package_version, build.id))
        expected_url = '%s/%s' % (url_start, expected_filename)
        self.assertEquals(expected_url, build.upload_log_url)

    def test_retry_resets_state(self):
        # Retrying a build resets most of the state attributes, but does
        # not modify the first dispatch time.
        build = self.factory.makeBinaryPackageBuild()
        build.updateStatus(BuildStatus.BUILDING, date_started=self.now)
        build.updateStatus(BuildStatus.FAILEDTOBUILD)
        build.gotFailure()
        with person_logged_in(self.admin):
            build.retry()
        self.assertEquals(BuildStatus.NEEDSBUILD, build.status)
        self.assertEquals(self.now, build.date_first_dispatched)
        self.assertEquals(None, build.log)
        self.assertEquals(None, build.upload_log)
        self.assertEquals(0, build.failure_count)

    def test_create_bpr(self):
        # Test that we can create a BPR from a given build.
        spn = self.factory.getUniqueString()
        version = "%s.1" % self.factory.getUniqueInteger()
        bpn = self.factory.makeBinaryPackageName(name=spn)
        spph = self.publisher.getPubSource(
            sourcename=spn, version=version, distroseries=self.distroseries)
        [build] = spph.createMissingBuilds()
        binary = build.createBinaryPackageRelease(
            binarypackagename=bpn, version=version, summary='',
            description='', binpackageformat=BinaryPackageFormat.DEB,
            component=spph.sourcepackagerelease.component.id,
            section=spph.sourcepackagerelease.section.id,
            priority=PackagePublishingPriority.STANDARD, installedsize=0,
            architecturespecific=False)
        self.assertEquals(1, build.binarypackages.count())
        self.assertEquals([binary], list(build.binarypackages))

    def test_multiple_create_bpr(self):
        # We can create multiple BPRs from a build
        spn = self.factory.getUniqueString()
        version = "%s.1" % self.factory.getUniqueInteger()
        spph = self.publisher.getPubSource(
            sourcename=spn, version=version, distroseries=self.distroseries)
        [build] = spph.createMissingBuilds()
        expected_names = []
        for i in range(15):
            bpn_name = '%s-%s' % (spn, i)
            bpn = self.factory.makeBinaryPackageName(bpn_name)
            expected_names.append(bpn_name)
            build.createBinaryPackageRelease(
                binarypackagename=bpn, version=str(i), summary='',
                description='', binpackageformat=BinaryPackageFormat.DEB,
                component=spph.sourcepackagerelease.component.id,
                section=spph.sourcepackagerelease.section.id,
                priority=PackagePublishingPriority.STANDARD, installedsize=0,
                architecturespecific=False)
        self.assertEquals(15, build.binarypackages.count())
        bin_names = [b.name for b in build.binarypackages]
        # Verify .binarypackages returns sorted by name
        expected_names.sort()
        self.assertEquals(expected_names, bin_names)

    def test_cannot_rescore_non_needsbuilds_builds(self):
        # If a build record isn't in NEEDSBUILD, it can not be rescored.
        # We will also need to log into an admin to do the rescore.
        with person_logged_in(self.admin):
            [bpph] = self.publisher.getPubBinaries(
                binaryname=self.factory.getUniqueString(),
                version="%s.1" % self.factory.getUniqueInteger(),
                distroseries=self.distroseries)
            build = bpph.binarypackagerelease.build
            self.assertRaises(CannotBeRescored, build.rescore, 20)

    def test_rescore_builds(self):
        # If the user has build-admin privileges, they can rescore builds
        spph = self.publisher.getPubSource(
            sourcename=self.factory.getUniqueString(),
            version="%s.1" % self.factory.getUniqueInteger(),
            distroseries=self.distroseries)
        [build] = spph.createMissingBuilds()
        self.assertEquals(BuildStatus.NEEDSBUILD, build.status)
        self.assertEquals(2505, build.buildqueue_record.lastscore)
        with person_logged_in(self.admin):
            build.rescore(5000)
            transaction.commit()
        self.assertEquals(5000, build.buildqueue_record.lastscore)

    def test_source_publication_override(self):
        # Components can be overridden in builds.
        spph = self.publisher.getPubSource(
            sourcename=self.factory.getUniqueString(),
            version="%s.1" % self.factory.getUniqueInteger(),
            distroseries=self.distroseries)
        [build] = spph.createMissingBuilds()
        self.assertEquals(spph, build.current_source_publication)
        universe = getUtility(IComponentSet)['universe']
        overridden_spph = spph.changeOverride(new_component=universe)
        # We can now see current source publication points to the overridden
        # publication.
        self.assertNotEquals(spph, build.current_source_publication)
        self.assertEquals(overridden_spph, build.current_source_publication)

    def test_estimated_duration(self):
        # Builds will have an estimated duration that is set to a
        # previous build of the same sources duration.
        spn = self.factory.getUniqueString()
        spph = self.publisher.getPubSource(
            sourcename=spn, status=PackagePublishingStatus.PUBLISHED)
        [build] = spph.createMissingBuilds()
        # Duration is based on package size if there is no previous build.
        self.assertEquals(
            timedelta(0, 60), build.buildqueue_record.estimated_duration)
        # Set the build as done, and its duration.
        build.updateStatus(
            BuildStatus.BUILDING,
            date_started=self.now - timedelta(minutes=72))
        build.updateStatus(BuildStatus.FULLYBUILT, date_finished=self.now)
        build.buildqueue_record.destroySelf()
        new_spph = self.publisher.getPubSource(
            sourcename=spn, status=PackagePublishingStatus.PUBLISHED)
        [new_build] = new_spph.createMissingBuilds()
        # The duration for this build is now 72 minutes.
        self.assertEquals(
            timedelta(0, 72 * 60),
            new_build.buildqueue_record.estimated_duration)

    def test_store_uploadlog_refuses_to_overwrite(self):
        # Storing an upload log for a build will fail if the build already
        # has an upload log.
        spph = self.publisher.getPubSource(
            sourcename=self.factory.getUniqueString(),
            version="%s.1" % self.factory.getUniqueInteger(),
            distroseries=self.distroseries)
        [build] = spph.createMissingBuilds()
        build.updateStatus(BuildStatus.FAILEDTOUPLOAD)
        build.storeUploadLog('foo')
        self.assertRaises(AssertionError, build.storeUploadLog, 'bar')
