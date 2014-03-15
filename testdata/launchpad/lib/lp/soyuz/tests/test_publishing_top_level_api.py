# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test top-level publication API in Soyuz."""

from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.interfaces.series import SeriesStatus
from lp.soyuz.enums import (
    PackagePublishingStatus,
    PackageUploadStatus,
    )
from lp.soyuz.tests.test_publishing import TestNativePublishingBase


class TestICanPublishPackagesAPI(TestNativePublishingBase):

    def _createLinkedPublication(self, name, pocket):
        """Return a linked pair of source and binary publications."""
        pub_source = self.getPubSource(
            sourcename=name, filecontent="Hello", pocket=pocket)

        binaryname = '%s-bin' % name
        pub_bin = self.getPubBinaries(
            binaryname=binaryname, filecontent="World",
            pub_source=pub_source, pocket=pocket)[0]

        return (pub_source, pub_bin)

    def _createDefaulSourcePublications(self):
        """Create and return default source publications.

        See `TestNativePublishingBase.getPubSource` for more information.

        It creates the following publications in breezy-autotest context:

         * a PENDING publication for RELEASE pocket;
         * a PUBLISHED publication for RELEASE pocket;
         * a PENDING publication for UPDATES pocket;

        Returns the respective ISPPH objects as a tuple.
        """
        pub_pending_release = self.getPubSource(
            sourcename='first',
            status=PackagePublishingStatus.PENDING,
            pocket=PackagePublishingPocket.RELEASE)

        pub_published_release = self.getPubSource(
            sourcename='second',
            status=PackagePublishingStatus.PUBLISHED,
            pocket=PackagePublishingPocket.RELEASE)

        pub_pending_updates = self.getPubSource(
            sourcename='third',
            status=PackagePublishingStatus.PENDING,
            pocket=PackagePublishingPocket.UPDATES)

        return (pub_pending_release, pub_published_release,
                pub_pending_updates)

    def _createDefaulBinaryPublications(self):
        """Create and return default binary publications.

        See `TestNativePublishingBase.getPubBinaries` for more information.

        It creates the following publications in breezy-autotest context:

         * a PENDING publication for RELEASE pocket;
         * a PUBLISHED publication for RELEASE pocket;
         * a PENDING publication for UPDATES pocket;

        Returns the respective IBPPH objects as a tuple.
        """
        pub_pending_release = self.getPubBinaries(
            binaryname='first',
            status=PackagePublishingStatus.PENDING,
            pocket=PackagePublishingPocket.RELEASE)[0]

        pub_published_release = self.getPubBinaries(
            binaryname='second',
            status=PackagePublishingStatus.PUBLISHED,
            pocket=PackagePublishingPocket.RELEASE)[0]

        pub_pending_updates = self.getPubBinaries(
            binaryname='third',
            status=PackagePublishingStatus.PENDING,
            pocket=PackagePublishingPocket.UPDATES)[0]

        return (pub_pending_release, pub_published_release,
                pub_pending_updates)

    def _publish(self, pocket, is_careful=False):
        """Publish the test IDistroSeries.

        Note that it also issues IDistroArchSeries.publish() API, since it's
        invoked/chained inside IDistroSeries.publish().
        """
        self.breezy_autotest.publish(
            self.disk_pool, self.logger,
            archive=self.breezy_autotest.main_archive,
            pocket=pocket, is_careful=is_careful)
        self.layer.txn.commit()

    def checkPublicationsAreConsidered(self, pocket):
        """Check if publications are considered for a given pocket.

        Source and Binary publications to the given pocket get PUBLISHED in
        database and on disk.
        """
        pub_source, pub_bin = self._createLinkedPublication(
            name='foo', pocket=pocket)
        self._publish(pocket=pocket)

        # source and binary PUBLISHED in database.
        pub_source.sync()
        pub_bin.sync()
        self.assertEqual(pub_source.status, PackagePublishingStatus.PUBLISHED)
        self.assertEqual(pub_bin.status, PackagePublishingStatus.PUBLISHED)

        # source and binary PUBLISHED on disk.
        foo_dsc = "%s/main/f/foo/foo_666.dsc" % self.pool_dir
        self.assertEqual(open(foo_dsc).read().strip(), 'Hello')
        foo_deb = "%s/main/f/foo/foo-bin_666_all.deb" % self.pool_dir
        self.assertEqual(open(foo_deb).read().strip(), 'World')

    def checkPublicationsAreIgnored(self, pocket):
        """Check if publications are ignored for a given pocket.

        Source and Binary publications to the given pocket are still PENDING
        in database.
        """
        pub_source, pub_bin = self._createLinkedPublication(
            name='bar', pocket=pocket)
        self._publish(pocket=pocket)

        # The publications to pocket were ignored.
        self.assertEqual(pub_source.status, PackagePublishingStatus.PENDING)
        self.assertEqual(pub_bin.status, PackagePublishingStatus.PENDING)

    def checkSourceLookupForPocket(self, pocket, expected_result,
                                   is_careful=False):
        """Check the results of an IDistroSeries publishing lookup."""
        pub_records = self.breezy_autotest.getPendingPublications(
            archive=self.breezy_autotest.main_archive,
            pocket=pocket, is_careful=is_careful)

        self.assertEqual(pub_records.count(), len(expected_result))
        self.assertEqual(
            [item.id for item in expected_result],
            [pub.id for pub in pub_records])

    def checkBinaryLookupForPocket(self, pocket, expected_result,
                                   is_careful=False):
        """Check the results of an IDistroArchSeries publishing lookup."""
        pub_records = self.breezy_autotest_i386.getPendingPublications(
            archive=self.breezy_autotest.main_archive,
            pocket=pocket, is_careful=is_careful)

        self.assertEqual(pub_records.count(), len(expected_result))
        self.assertEqual(
            [item.id for item in expected_result],
            [pub.id for pub in pub_records])

    def testPublishUnstableDistroSeries(self):
        """Top level publication for IDistroSeries in 'unstable' states.

        Publications to RELEASE pocket are considered.
        Publication to UPDATES pocket (post-release pockets) are ignored
        """
        self.assertEqual(
            self.breezy_autotest.status, SeriesStatus.EXPERIMENTAL)
        self.assertEqual(self.breezy_autotest.isUnstable(), True)
        self.checkPublicationsAreConsidered(PackagePublishingPocket.RELEASE)
        self.checkPublicationsAreIgnored(PackagePublishingPocket.UPDATES)

    def testPublishStableDistroSeries(self):
        """Top level publication for IDistroSeries in 'stable' states.

        Publications to RELEASE pocket are ignored.
        Publications to UPDATES pocket are considered.
        """
        # Release ubuntu/breezy-autotest.
        self.breezy_autotest.status = SeriesStatus.CURRENT
        self.layer.commit()

        self.assertEqual(
            self.breezy_autotest.status, SeriesStatus.CURRENT)
        self.assertEqual(self.breezy_autotest.isUnstable(), False)
        self.checkPublicationsAreConsidered(PackagePublishingPocket.UPDATES)
        self.checkPublicationsAreIgnored(PackagePublishingPocket.RELEASE)

    def testPublishFrozenDistroSeries(self):
        """Top level publication for IDistroSeries in FROZEN state.

        Publications to both, RELEASE and UPDATES, pockets are considered.
        """
        # Release ubuntu/breezy-autotest.
        self.breezy_autotest.status = SeriesStatus.FROZEN
        self.layer.commit()

        self.assertEqual(
            self.breezy_autotest.status, SeriesStatus.FROZEN)
        self.assertEqual(
            self.breezy_autotest.isUnstable(), True)
        self.checkPublicationsAreConsidered(PackagePublishingPocket.UPDATES)
        self.checkPublicationsAreConsidered(PackagePublishingPocket.RELEASE)

    def testPublicationLookUpForUnstableDistroSeries(self):
        """Source publishing record lookup for a unstable DistroSeries.

        Check if the ICanPublishPackages.getPendingPublications() works
        properly for a DistroSeries when it is still in development,
        'unreleased'.
        """
        pub_pending_release, pub_published_release, pub_pending_updates = (
            self._createDefaulSourcePublications())

        # Usual publication procedure for a distroseries in development
        # state only 'pending' publishing records for pocket RELEASE
        # are published.
        self.checkSourceLookupForPocket(
            PackagePublishingPocket.RELEASE,
            expected_result=[pub_pending_release])

        # This step is unusual but checks if the pocket restriction also
        # work for other pockets than the RELEASE.
        self.checkSourceLookupForPocket(
            PackagePublishingPocket.UPDATES,
            expected_result=[pub_pending_updates])

        # Restricting to a pocket with no publication returns an
        # empty SQLResult.
        self.checkSourceLookupForPocket(
            PackagePublishingPocket.BACKPORTS, expected_result=[])

        # Using the 'careful' mode results in the consideration
        # of every 'pending' and 'published' records present in
        # the given pocket. The order is also important, NEWER first.
        self.checkSourceLookupForPocket(
            PackagePublishingPocket.RELEASE, is_careful=True,
            expected_result=[pub_published_release, pub_pending_release])

    def testPublicationLookUpForStableDistroSeries(self):
        """Source publishing record lookup for a stable/released DistroSeries.

        Check if the ICanPublishPackages.getPendingPublications() works
        properly for a DistroSeries when it is not in development anymore,
        i.e., 'released'.
        """
        pub_pending_release, pub_published_release, pub_pending_updates = (
            self._createDefaulSourcePublications())

        # Release 'breezy-autotest'.
        self.breezy_autotest.status = SeriesStatus.CURRENT
        self.layer.commit()

        # Since the distroseries is stable, nothing is returned because
        # RELEASE pocket is ignored, in both modes, careful or not.
        self.checkSourceLookupForPocket(
            PackagePublishingPocket.RELEASE, expected_result=[])

        # XXX cprov 2007-01-05: it means that "careful" mode is useless for
        # rebuilding released archives.
        # This is quite right, IMHO, since republication of a released
        # archive will, obviously contain new timestamps, which would freak
        # mirrors/clients out.
        # At the end, "careful" mode is such a gross hack.
        self.checkSourceLookupForPocket(
            PackagePublishingPocket.RELEASE, is_careful=True,
            expected_result=[])

        # Publications targeted to other pockets than RELEASE are
        # still reachable.
        self.checkSourceLookupForPocket(
            PackagePublishingPocket.UPDATES,
            expected_result=[pub_pending_updates])

    def testPublicationLookUpForFrozenDistroSeries(self):
        """Source publishing record lookup for a frozen DistroSeries.

        Check if the ICanPublishPackages.getPendingPubliations() works
        properly for a DistroSeries when it is in FROZEN state.
        """
        pub_pending_release, pub_published_release, pub_pending_updates = (
            self._createDefaulSourcePublications())
        # Freeze 'breezy-autotest'.
        self.breezy_autotest.status = SeriesStatus.FROZEN
        self.layer.commit()

        # Usual publication procedure for a distroseries in development
        # state only 'pending' publishing records for pocket RELEASE
        # are published.
        self.checkSourceLookupForPocket(
            PackagePublishingPocket.RELEASE,
            expected_result=[pub_pending_release])

        # This step is unusual but checks if the pocket restriction also
        # work for other pockets than the RELEASE.
        self.checkSourceLookupForPocket(
            PackagePublishingPocket.UPDATES,
            expected_result=[pub_pending_updates])

        # Restricting to a pocket with no publication returns an
        # empty SQLResult.
        self.checkSourceLookupForPocket(
            PackagePublishingPocket.BACKPORTS, expected_result=[])

        # Using the 'careful' mode results in the consideration
        # of every 'pending' and 'published' records present in
        # the given pocket.
        self.checkSourceLookupForPocket(
            PackagePublishingPocket.RELEASE, is_careful=True,
            expected_result=[pub_published_release, pub_pending_release])

    def testPublicationLookUpForUnstableDistroArchSeries(self):
        """Binary publishing record lookup for a unstable DistroArchSeries.

        Check if the ICanPublishPackages.getPendingPublications() works
        properly for a DistroArchSeries when it is still in DEVELOPMENT,
        i.e., 'unstable'.
        """
        pub_pending_release, pub_published_release, pub_pending_updates = (
            self._createDefaulBinaryPublications())
        self.layer.commit()

        # Usual publication procedure for a distroseries in development
        # state only 'pending' publishing records for pocket RELEASE
        # are published.
        self.checkBinaryLookupForPocket(
            PackagePublishingPocket.RELEASE,
            expected_result=[pub_pending_release])

        # This step is unusual but checks if the pocket restriction also
        # work for other pockets than the RELEASE.
        self.checkBinaryLookupForPocket(
            PackagePublishingPocket.UPDATES,
            expected_result=[pub_pending_updates])

        # Restricting to a pocket with no publication returns an
        # empty SQLResult.
        self.checkBinaryLookupForPocket(
            PackagePublishingPocket.BACKPORTS, expected_result=[])

        # Using the 'careful' mode results in the consideration
        # of every 'pending' and 'published' records present in
        # the given pocket.
        self.checkBinaryLookupForPocket(
            PackagePublishingPocket.RELEASE, is_careful=True,
            expected_result=[pub_published_release, pub_pending_release])

    def testPublicationLookUpForStableDistroArchSeries(self):
        """Binary publishing record lookup for released DistroArchSeries.

        Check if the ICanPublishPackages.getPendingPublications() works
        properly for a DistroArchSeries when it is not in development
        anymore, i.e., 'released'.

        Released DistroArchSeries can't be modified, so we expect empty
        results in the lookups, even if there are pending publishing
        records available.
        """
        pub_pending_release, pub_published_release, pub_pending_updates = (
            self._createDefaulBinaryPublications())

        # Release 'breezy-autotest'
        self.breezy_autotest.status = SeriesStatus.CURRENT
        self.layer.commit()

        # Since the distroseries is stable, nothing is returned because
        # RELEASE pocket is ignored, in both modes, careful or not.
        self.checkBinaryLookupForPocket(
            PackagePublishingPocket.RELEASE, expected_result=[])

        # XXX cprov 2007-01-05: it means that "careful" mode is useless for
        # rebuilding released archives.
        # This is quite right, IMHO, since republication of a released
        # archive will, obviously contain new timestamps, which would freak
        # mirrors/clients out.
        # At the end, "careful" mode is such a gross hack.
        self.checkBinaryLookupForPocket(
            PackagePublishingPocket.RELEASE, is_careful=True,
            expected_result=[])

        # Publications targeted to other pockets than RELEASE are
        # still reachable.
        self.checkBinaryLookupForPocket(
            PackagePublishingPocket.UPDATES,
            expected_result=[pub_pending_updates])

    def testPublicationLookUpForFrozenDistroArchSeries(self):
        """Binary publishing record lookup for a frozen DistroArchSeries.

        Check if the ICanPublishPackages.getPendingPublications() works
        properly for a DistroArchSeries when it is frozen state.
        """
        pub_pending_release, pub_published_release, pub_pending_updates = (
            self._createDefaulBinaryPublications())
        # Freeze 'breezy-autotest'
        self.breezy_autotest.status = SeriesStatus.FROZEN
        self.layer.commit()

        # Usual publication procedure for a distroseries in development
        # state only 'pending' publishing records for pocket RELEASE
        # are published.
        self.checkBinaryLookupForPocket(
            PackagePublishingPocket.RELEASE,
            expected_result=[pub_pending_release])

        # This step is unusual but checks if the pocket restriction also
        # work for other pockets than the RELEASE.
        self.checkBinaryLookupForPocket(
            PackagePublishingPocket.UPDATES,
            expected_result=[pub_pending_updates])

        # Restricting to a pocket with no publication returns an
        # empty SQLResult.
        self.checkBinaryLookupForPocket(
            PackagePublishingPocket.BACKPORTS, expected_result=[])

        # Using the 'careful' mode results in the consideration
        # of every 'pending' and 'published' records present in
        # the given pocket.
        self.checkBinaryLookupForPocket(
            PackagePublishingPocket.RELEASE, is_careful=True,
            expected_result=[pub_published_release, pub_pending_release])

    def test_publishing_disabled_distroarchseries(self):
        # Disabled DASes will not receive new publications at all.

        # Make an arch-all source and some builds for it.
        archive = self.factory.makeArchive(
            distribution=self.ubuntutest, virtualized=False)
        source = self.getPubSource(
            archive=archive, architecturehintlist='all')
        [build_i386] = source.createMissingBuilds()
        bin_i386 = self.uploadBinaryForBuild(build_i386, 'bin-i386')

        # Now make sure they have a packageupload (but no publishing
        # records).
        changes_file_name = '%s_%s_%s.changes' % (
            bin_i386.name, bin_i386.version, build_i386.arch_tag)
        pu_i386 = self.addPackageUpload(
            build_i386.archive, build_i386.distro_arch_series.distroseries,
            build_i386.pocket, changes_file_content='anything',
            changes_file_name=changes_file_name,
            upload_status=PackageUploadStatus.ACCEPTED)
        pu_i386.addBuild(build_i386)

        # Now we make hppa a disabled architecture, and then call the
        # publish method on the packageupload.  The arch-all binary
        # should be published only in the i386 arch, not the hppa one.
        hppa = pu_i386.distroseries.getDistroArchSeries('hppa')
        hppa.enabled = False
        for pu_build in pu_i386.builds:
            pu_build.publish()

        publications = archive.getAllPublishedBinaries(name="bin-i386")

        self.assertEqual(1, publications.count())
        self.assertEqual(
            'i386', publications[0].distroarchseries.architecturetag)
