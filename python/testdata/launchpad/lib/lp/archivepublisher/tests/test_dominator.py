# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for domination.py."""

__metaclass__ = type

import datetime
from operator import attrgetter

import apt_pkg
from testtools.matchers import LessThan
from zope.security.proxy import removeSecurityProxy

from lp.archivepublisher.domination import (
    ArchSpecificPublicationsCache,
    contains_arch_indep,
    Dominator,
    find_live_binary_versions_pass_1,
    find_live_binary_versions_pass_2,
    find_live_source_versions,
    GeneralizedPublication,
    STAY_OF_EXECUTION,
    )
from lp.archivepublisher.publishing import Publisher
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.interfaces.series import SeriesStatus
from lp.services.database.sqlbase import flush_database_updates
from lp.services.log.logger import DevNullLogger
from lp.soyuz.enums import PackagePublishingStatus
from lp.soyuz.interfaces.publishing import ISourcePackagePublishingHistory
from lp.soyuz.tests.test_publishing import TestNativePublishingBase
from lp.testing import (
    StormStatementRecorder,
    TestCaseWithFactory,
    )
from lp.testing.fakemethod import FakeMethod
from lp.testing.layers import ZopelessDatabaseLayer
from lp.testing.matchers import HasQueryCount


class TestDominator(TestNativePublishingBase):
    """Test Dominator class."""

    def createSourceAndBinaries(self, version, with_debug=False,
                                archive=None):
        """Create a source and binaries with the given version."""
        source = self.getPubSource(
            version=version, archive=archive,
            status=PackagePublishingStatus.PUBLISHED)
        binaries = self.getPubBinaries(
            pub_source=source, with_debug=with_debug,
            status=PackagePublishingStatus.PUBLISHED)
        return (source, binaries)

    def createSimpleDominationContext(self):
        """Create simple domination context.

        Creates source and binary publications for:

         * Dominated: foo_1.0 & foo-bin_1.0_i386
         * Dominant: foo_1.1 & foo-bin_1.1_i386

        Return the corresponding publication records as a 4-tuple:

         (dominant_source, dominant_binary, dominated_source,
          dominated_binary)

        Note that as an optimization the binaries list is already unpacked.
        """
        foo_10_source, foo_10_binaries = self.createSourceAndBinaries('1.0')
        foo_11_source, foo_11_binaries = self.createSourceAndBinaries('1.1')
        return (foo_11_source, foo_11_binaries[0],
                foo_10_source, foo_10_binaries[0])

    def dominateAndCheck(self, dominant, dominated, supersededby):
        generalization = GeneralizedPublication(
            is_source=ISourcePackagePublishingHistory.providedBy(dominant))
        dominator = Dominator(self.logger, self.ubuntutest.main_archive)

        pubs = [dominant, dominated]
        live_versions = [generalization.getPackageVersion(dominant)]
        dominator.dominatePackage(pubs, live_versions, generalization)
        flush_database_updates()

        # The dominant version remains correctly published.
        self.checkPublication(dominant, PackagePublishingStatus.PUBLISHED)
        self.assertTrue(dominant.supersededby is None)
        self.assertTrue(dominant.datesuperseded is None)

        # The dominated version is correctly dominated.
        self.checkPublication(dominated, PackagePublishingStatus.SUPERSEDED)
        self.assertEqual(dominated.supersededby, supersededby)
        self.checkPastDate(dominated.datesuperseded)

    def testManualSourceDomination(self):
        """Test source domination procedure."""
        [dominant_source, dominant_binary, dominated_source,
         dominated_binary] = self.createSimpleDominationContext()

        self.dominateAndCheck(
            dominant_source, dominated_source,
            dominant_source.sourcepackagerelease)

    def testManualBinaryDomination(self):
        """Test binary domination procedure."""
        [dominant_source, dominant, dominated_source,
         dominated] = self.createSimpleDominationContext()

        self.dominateAndCheck(
            dominant, dominated, dominant.binarypackagerelease.build)

    def testJudgeAndDominate(self):
        """Verify that judgeAndDominate correctly dominates everything."""
        foo_10_source, foo_10_binaries = self.createSourceAndBinaries('1.0')
        foo_11_source, foo_11_binaries = self.createSourceAndBinaries('1.1')
        foo_12_source, foo_12_binaries = self.createSourceAndBinaries('1.2')

        dominator = Dominator(self.logger, foo_10_source.archive)
        dominator.judgeAndDominate(
            foo_10_source.distroseries, foo_10_source.pocket)

        self.checkPublications(
            [foo_12_source] + foo_12_binaries,
            PackagePublishingStatus.PUBLISHED)
        self.checkPublications(
            [foo_11_source] + foo_11_binaries,
            PackagePublishingStatus.SUPERSEDED)
        self.checkPublications(
            [foo_10_source] + foo_10_binaries,
            PackagePublishingStatus.SUPERSEDED)

    def testJudgeAndDominateWithDDEBs(self):
        """Verify that judgeAndDominate ignores DDEBs correctly.

        DDEBs are superseded by their corresponding DEB publications, so they
        are forbidden from superseding publications (an attempt would result
        in an AssertionError), and shouldn't be directly considered for
        superseding either.
        """
        ppa = self.factory.makeArchive()
        foo_10_source, foo_10_binaries = self.createSourceAndBinaries(
            '1.0', with_debug=True, archive=ppa)
        foo_11_source, foo_11_binaries = self.createSourceAndBinaries(
            '1.1', with_debug=True, archive=ppa)
        foo_12_source, foo_12_binaries = self.createSourceAndBinaries(
            '1.2', with_debug=True, archive=ppa)

        dominator = Dominator(self.logger, ppa)
        dominator.judgeAndDominate(
            foo_10_source.distroseries, foo_10_source.pocket)

        self.checkPublications(
            [foo_12_source] + foo_12_binaries,
            PackagePublishingStatus.PUBLISHED)
        self.checkPublications(
            [foo_11_source] + foo_11_binaries,
            PackagePublishingStatus.SUPERSEDED)
        self.checkPublications(
            [foo_10_source] + foo_10_binaries,
            PackagePublishingStatus.SUPERSEDED)

    def test_dominateBinaries_rejects_empty_publication_list(self):
        """Domination asserts for non-empty input list."""
        package = self.factory.makeBinaryPackageName()
        dominator = Dominator(self.logger, self.ubuntutest.main_archive)
        dominator._sortPackages = FakeMethod({package.name: []})
        # This isn't a really good exception. It should probably be
        # something more indicative of bad input.
        self.assertRaises(
            AssertionError,
            dominator.dominateBinaries,
            self.factory.makeDistroArchSeries().distroseries,
            self.factory.getAnyPocket())

    def test_dominateSources_rejects_empty_publication_list(self):
        """Domination asserts for non-empty input list."""
        package = self.factory.makeSourcePackageName()
        dominator = Dominator(self.logger, self.ubuntutest.main_archive)
        dominator._sortPackages = FakeMethod({package.name: []})
        # This isn't a really good exception. It should probably be
        # something more indicative of bad input.
        self.assertRaises(
            AssertionError,
            dominator.dominateSources,
            self.factory.makeDistroSeries(), self.factory.getAnyPocket())

    def test_archall_domination(self):
        # Arch-all binaries should not be dominated when a new source
        # version builds an updated arch-all binary, because slower builds
        # of other architectures will leave the previous version
        # uninstallable if they depend on the arch-all binary.
        # See https://bugs.launchpad.net/launchpad/+bug/34086

        # Set up a source, "foo" which builds "foo-bin" and foo-common
        # (which is arch-all).
        foo_10_src = self.getPubSource(
            sourcename="foo", version="1.0", architecturehintlist="i386",
            status=PackagePublishingStatus.PUBLISHED)
        [foo_10_i386_bin] = self.getPubBinaries(
            binaryname="foo-bin", status=PackagePublishingStatus.PUBLISHED,
            architecturespecific=True, version="1.0", pub_source=foo_10_src)
        [build] = foo_10_src.getBuilds()
        bpr = self.factory.makeBinaryPackageRelease(
            binarypackagename="foo-common", version="1.0", build=build,
            architecturespecific=False)
        foo_10_all_bins = self.publishBinaryInArchive(
            bpr, self.ubuntutest.main_archive, pocket=foo_10_src.pocket,
            status=PackagePublishingStatus.PUBLISHED)

        # Now, make version 1.1 of foo and add a foo-common but not foo-bin
        # (imagine that it's not finished building yet).
        foo_11_src = self.getPubSource(
            sourcename="foo", version="1.1", architecturehintlist="all",
            status=PackagePublishingStatus.PUBLISHED)
        # Generate binary publications for architecture "all" (actually,
        # one such publication per architecture).
        self.getPubBinaries(
            binaryname="foo-common", status=PackagePublishingStatus.PUBLISHED,
            architecturespecific=False, version="1.1", pub_source=foo_11_src)

        dominator = Dominator(self.logger, self.ubuntutest.main_archive)
        dominator.judgeAndDominate(
            foo_10_src.distroseries, foo_10_src.pocket)

        # The source will be superseded.
        self.checkPublication(foo_10_src, PackagePublishingStatus.SUPERSEDED)
        # The arch-specific has no dominant, so it's still published
        self.checkPublication(
            foo_10_i386_bin, PackagePublishingStatus.PUBLISHED)
        # The arch-indep has a dominant but must not be superseded yet
        # since the arch-specific is still published.
        self.checkPublications(
            foo_10_all_bins, PackagePublishingStatus.PUBLISHED)

        # Now creating a newer foo-bin should see those last two
        # publications superseded.
        [build2] = foo_11_src.getBuilds()
        foo_11_bin = self.factory.makeBinaryPackageRelease(
            binarypackagename="foo-bin", version="1.1", build=build2,
            architecturespecific=True)
        self.publishBinaryInArchive(
            foo_11_bin, self.ubuntutest.main_archive,
            pocket=foo_10_src.pocket,
            status=PackagePublishingStatus.PUBLISHED)
        dominator.judgeAndDominate(
            foo_10_src.distroseries, foo_10_src.pocket)
        self.checkPublication(
            foo_10_i386_bin, PackagePublishingStatus.SUPERSEDED)
        self.checkPublications(
            foo_10_all_bins, PackagePublishingStatus.SUPERSEDED)

    def test_any_superseded_by_all(self):
        # Set up a source, foo, which builds an architecture-dependent
        # binary, foo-bin.
        foo_10_src = self.getPubSource(
            sourcename="foo", version="1.0", architecturehintlist="i386",
            status=PackagePublishingStatus.PUBLISHED)
        [foo_10_i386_bin] = self.getPubBinaries(
            binaryname="foo-bin", status=PackagePublishingStatus.PUBLISHED,
            architecturespecific=True, version="1.0", pub_source=foo_10_src)

        # Now, make version 1.1 of foo, where foo-bin is now
        # architecture-independent.
        foo_11_src = self.getPubSource(
            sourcename="foo", version="1.1", architecturehintlist="all",
            status=PackagePublishingStatus.PUBLISHED)
        [foo_10_all_bin, foo_10_all_bin_2] = self.getPubBinaries(
            binaryname="foo-bin", status=PackagePublishingStatus.PUBLISHED,
            architecturespecific=False, version="1.1", pub_source=foo_11_src)

        dominator = Dominator(self.logger, self.ubuntutest.main_archive)
        dominator.judgeAndDominate(
            foo_10_src.distroseries, foo_10_src.pocket)

        # The source will be superseded.
        self.checkPublication(foo_10_src, PackagePublishingStatus.SUPERSEDED)
        # The arch-specific is superseded by the new arch-indep.
        self.checkPublication(
            foo_10_i386_bin, PackagePublishingStatus.SUPERSEDED)

    def test_schitzoid_package(self):
        # Test domination of a source that produces an arch-indep and an
        # arch-all, that then switches both on the next version to the
        # other arch type.
        foo_10_src = self.getPubSource(
            sourcename="foo", version="1.0", architecturehintlist="i386",
            status=PackagePublishingStatus.PUBLISHED)
        [foo_10_i386_bin] = self.getPubBinaries(
            binaryname="foo-bin", status=PackagePublishingStatus.PUBLISHED,
            architecturespecific=True, version="1.0", pub_source=foo_10_src)
        [build] = foo_10_src.getBuilds()
        bpr = self.factory.makeBinaryPackageRelease(
            binarypackagename="foo-common", version="1.0", build=build,
            architecturespecific=False)
        foo_10_all_bins = self.publishBinaryInArchive(
            bpr, self.ubuntutest.main_archive, pocket=foo_10_src.pocket,
            status=PackagePublishingStatus.PUBLISHED)

        foo_11_src = self.getPubSource(
            sourcename="foo", version="1.1", architecturehintlist="i386",
            status=PackagePublishingStatus.PUBLISHED)
        [foo_11_i386_bin] = self.getPubBinaries(
            binaryname="foo-common", status=PackagePublishingStatus.PUBLISHED,
            architecturespecific=True, version="1.1", pub_source=foo_11_src)
        [build] = foo_11_src.getBuilds()
        bpr = self.factory.makeBinaryPackageRelease(
            binarypackagename="foo-bin", version="1.1", build=build,
            architecturespecific=False)
        # Generate binary publications for architecture "all" (actually,
        # one such publication per architecture).
        self.publishBinaryInArchive(
            bpr, self.ubuntutest.main_archive, pocket=foo_11_src.pocket,
            status=PackagePublishingStatus.PUBLISHED)

        dominator = Dominator(self.logger, self.ubuntutest.main_archive)
        dominator.judgeAndDominate(foo_10_src.distroseries, foo_10_src.pocket)

        self.checkPublications(foo_10_all_bins + [foo_10_i386_bin],
                               PackagePublishingStatus.SUPERSEDED)


class TestDomination(TestNativePublishingBase):
    """Test overall domination procedure."""

    def testCarefulDomination(self):
        """Test the careful domination procedure.

        Check if it works on a development series.
        A SUPERSEDED, DELETED or OBSOLETE published source should
        have its scheduleddeletiondate set.
        """
        publisher = Publisher(
            self.logger, self.config, self.disk_pool,
            self.ubuntutest.main_archive)

        superseded_source = self.getPubSource(
            status=PackagePublishingStatus.SUPERSEDED)
        self.assertTrue(superseded_source.scheduleddeletiondate is None)
        deleted_source = self.getPubSource(
            status=PackagePublishingStatus.DELETED)
        self.assertTrue(deleted_source.scheduleddeletiondate is None)
        obsoleted_source = self.getPubSource(
            status=PackagePublishingStatus.OBSOLETE)
        self.assertTrue(obsoleted_source.scheduleddeletiondate is None)

        publisher.B_dominate(True)

        # The publishing records will be scheduled for removal.
        # DELETED and OBSOLETED publications are set to be deleted
        # immediately, whereas SUPERSEDED ones get a stay of execution
        # according to the configuration.
        self.checkPublication(
            deleted_source, PackagePublishingStatus.DELETED)
        self.checkPastDate(deleted_source.scheduleddeletiondate)

        self.checkPublication(
            obsoleted_source, PackagePublishingStatus.OBSOLETE)
        self.checkPastDate(deleted_source.scheduleddeletiondate)

        self.checkPublication(
            superseded_source, PackagePublishingStatus.SUPERSEDED)
        self.checkPastDate(
            superseded_source.scheduleddeletiondate,
            lag=datetime.timedelta(days=STAY_OF_EXECUTION))


class TestDominationOfObsoletedSeries(TestDomination):
    """Replay domination tests upon a OBSOLETED distroseries."""

    def setUp(self):
        TestDomination.setUp(self)
        self.ubuntutest['breezy-autotest'].status = (
            SeriesStatus.OBSOLETE)


def remove_security_proxies(proxied_objects):
    """Return list of `proxied_objects`, without their proxies.

    The dominator runs only in scripts, where security proxies don't get
    in the way.  To test realistically for this environment, strip the
    proxies wherever necessary and do as you will.
    """
    return [removeSecurityProxy(obj) for obj in proxied_objects]


def make_spphs_for_versions(factory, versions):
    """Create publication records for each of `versions`.

    All these publications will be in the same source package, archive,
    distroseries, and pocket.  They will all be in Published status.

    The records are created in the same order in which they are specified.
    Make the order irregular to prove that version ordering is not a
    coincidence of object creation order etc.

    Versions may also be identical; each publication record will still have
    its own package release.
    """
    spn = factory.makeSourcePackageName()
    distroseries = factory.makeDistroSeries()
    pocket = factory.getAnyPocket()
    archive = distroseries.main_archive
    sprs = [
        factory.makeSourcePackageRelease(
            sourcepackagename=spn, version=version)
        for version in versions]
    return [
        factory.makeSourcePackagePublishingHistory(
            distroseries=distroseries, pocket=pocket,
            sourcepackagerelease=spr, archive=archive,
            status=PackagePublishingStatus.PUBLISHED)
        for spr in sprs]


def make_bpphs_for_versions(factory, versions):
    """Create publication records for each of `versions`.

    All these publications will be in the same binary package, source
    package, archive, distroarchseries, and pocket.  They will all be in
    Published status.
    """
    bpn = factory.makeBinaryPackageName()
    spn = factory.makeSourcePackageName()
    das = factory.makeDistroArchSeries()
    archive = das.distroseries.main_archive
    pocket = factory.getAnyPocket()
    bprs = [
        factory.makeBinaryPackageRelease(
            binarypackagename=bpn, version=version)
        for version in versions]
    return remove_security_proxies([
        factory.makeBinaryPackagePublishingHistory(
            binarypackagerelease=bpr, binarypackagename=bpn,
            distroarchseries=das, pocket=pocket, archive=archive,
            sourcepackagename=spn, status=PackagePublishingStatus.PUBLISHED)
        for bpr in bprs])


def list_source_versions(spphs):
    """Extract the versions from `spphs` as a list, in the same order."""
    return [spph.sourcepackagerelease.version for spph in spphs]


def alter_creation_dates(spphs, ages):
    """Set `datecreated` on each of `spphs` according to `ages`.

    :param spphs: Iterable of `SourcePackagePublishingHistory`.  Their
        respective creation dates will be offset by the respective ages found
        in `ages` (with the two being matched up in the same order).
    :param ages: Iterable of ages.  Must provide the same number of items as
        `spphs`.  Ages are `timedelta` objects that will be subtracted from
        the creation dates on the respective records in `spph`.
    """
    for spph, age in zip(spphs, ages):
        spph.datecreated -= age


class TestGeneralizedPublication(TestCaseWithFactory):
    """Test publication generalization helpers."""

    layer = ZopelessDatabaseLayer

    def test_getPackageVersion_gets_source_version(self):
        spph = self.factory.makeSourcePackagePublishingHistory()
        self.assertEqual(
            spph.sourcepackagerelease.version,
            GeneralizedPublication(is_source=True).getPackageVersion(spph))

    def test_getPackageVersion_gets_binary_version(self):
        bpph = self.factory.makeBinaryPackagePublishingHistory()
        self.assertEqual(
            bpph.binarypackagerelease.version,
            GeneralizedPublication(is_source=False).getPackageVersion(bpph))

    def test_compare_sorts_versions(self):
        versions = [
            '1.1v2',
            '1.1v1',
            '1.1v3',
            ]
        spphs = make_spphs_for_versions(self.factory, versions)
        sorted_spphs = sorted(spphs, cmp=GeneralizedPublication().compare)
        self.assertEqual(
            sorted(versions), list_source_versions(sorted_spphs))

    def test_compare_orders_versions_by_debian_rules(self):
        versions = [
            '1.1.0',
            '1.10',
            '1.1',
            '1.1ubuntu0',
            ]
        spphs = make_spphs_for_versions(self.factory, versions)

        debian_sorted_versions = sorted(versions, cmp=apt_pkg.version_compare)

        # Assumption: in this case, Debian version ordering is not the
        # same as alphabetical version ordering.
        self.assertNotEqual(sorted(versions), debian_sorted_versions)

        # The compare method produces the Debian ordering.
        sorted_spphs = sorted(spphs, cmp=GeneralizedPublication().compare)
        self.assertEqual(
            sorted(versions, cmp=apt_pkg.version_compare),
            list_source_versions(sorted_spphs))

    def test_compare_breaks_tie_with_creation_date(self):
        # When two publications are tied for comparison because they are
        # for the same package release, they are ordered by creation
        # date.
        distroseries = self.factory.makeDistroSeries()
        pocket = self.factory.getAnyPocket()
        spr = self.factory.makeSourcePackageRelease()
        ages = [
            datetime.timedelta(2),
            datetime.timedelta(1),
            datetime.timedelta(3),
            ]
        spphs = [
            self.factory.makeSourcePackagePublishingHistory(
                sourcepackagerelease=spr, distroseries=distroseries,
                pocket=pocket)
            for counter in xrange(len(ages))]
        alter_creation_dates(spphs, ages)

        self.assertEqual(
            [spphs[2], spphs[0], spphs[1]],
            sorted(spphs, cmp=GeneralizedPublication().compare))

    def test_compare_breaks_tie_for_releases_with_same_version(self):
        # When two publications are tied for comparison because they
        # belong to releases with the same version string, they are
        # ordered by creation date.
        version = "1.%d" % self.factory.getUniqueInteger()
        ages = [
            datetime.timedelta(2),
            datetime.timedelta(1),
            datetime.timedelta(3),
            ]
        distroseries = self.factory.makeDistroSeries()
        pocket = self.factory.getAnyPocket()
        spphs = [
            self.factory.makeSourcePackagePublishingHistory(
                distroseries=distroseries, pocket=pocket,
                sourcepackagerelease=self.factory.makeSourcePackageRelease(
                    version=version))
            for counter in xrange(len(ages))]
        alter_creation_dates(spphs, ages)

        self.assertEqual(
            [spphs[2], spphs[0], spphs[1]],
            sorted(spphs, cmp=GeneralizedPublication().compare))


def jumble(ordered_list):
    """Jumble the elements of `ordered_list` into a weird order.

    Ordering is very important in domination.  We jumble some of our lists to
    insure against "lucky coincidences" that might give our tests the right
    answers for the wrong reasons.
    """
    even = [
        item for offset, item in enumerate(ordered_list) if offset % 2 == 0]
    odd = [
        item for offset, item in enumerate(ordered_list) if offset % 2 != 0]
    return list(reversed(odd)) + even


class TestDominatorMethods(TestCaseWithFactory):

    layer = ZopelessDatabaseLayer

    def makeDominator(self, publications):
        """Create a `Dominator` suitable for `publications`."""
        if len(publications) == 0:
            archive = self.factory.makeArchive()
        else:
            archive = publications[0].archive
        return Dominator(DevNullLogger(), archive)

    def test_dominatePackage_survives_empty_publications_list(self):
        # Nothing explodes when dominatePackage is called with an empty
        # packages list.
        self.makeDominator([]).dominatePackage(
            [], [], GeneralizedPublication(True))
        # The test is that we get here without error.
        pass

    def test_dominatePackage_leaves_live_version_untouched(self):
        # dominatePackage does not supersede live versions.
        [pub] = make_spphs_for_versions(self.factory, ['3.1'])
        self.makeDominator([pub]).dominatePackage(
            [pub], ['3.1'], GeneralizedPublication(True))
        self.assertEqual(PackagePublishingStatus.PUBLISHED, pub.status)

    def test_dominatePackage_deletes_dead_version_without_successor(self):
        # dominatePackage marks non-live package versions without
        # superseding versions as deleted.
        [pub] = make_spphs_for_versions(self.factory, ['1.1'])
        self.makeDominator([pub]).dominatePackage(
            [pub], [], GeneralizedPublication(True))
        self.assertEqual(PackagePublishingStatus.DELETED, pub.status)

    def test_dominatePackage_supersedes_older_pub_with_newer_live_pub(self):
        # When marking a package as superseded, dominatePackage
        # designates a newer live version as the superseding version.
        generalization = GeneralizedPublication(True)
        pubs = make_spphs_for_versions(self.factory, ['1.0', '1.1'])
        self.makeDominator(pubs).dominatePackage(
            generalization.sortPublications(pubs), ['1.1'], generalization)
        self.assertEqual(PackagePublishingStatus.SUPERSEDED, pubs[0].status)
        self.assertEqual(pubs[1].sourcepackagerelease, pubs[0].supersededby)
        self.assertEqual(PackagePublishingStatus.PUBLISHED, pubs[1].status)

    def test_dominatePackage_only_supersedes_with_live_pub(self):
        # When marking a package as superseded, dominatePackage will
        # only pick a live version as the superseding one.
        generalization = GeneralizedPublication(True)
        pubs = make_spphs_for_versions(
            self.factory, ['1.0', '2.0', '3.0', '4.0'])
        self.makeDominator(pubs).dominatePackage(
            generalization.sortPublications(pubs), ['3.0'], generalization)
        self.assertEqual([
                pubs[2].sourcepackagerelease,
                pubs[2].sourcepackagerelease,
                None,
                None,
                ],
            [pub.supersededby for pub in pubs])

    def test_dominatePackage_supersedes_with_oldest_newer_live_pub(self):
        # When marking a package as superseded, dominatePackage picks
        # the oldest of the newer, live versions as the superseding one.
        generalization = GeneralizedPublication(True)
        pubs = make_spphs_for_versions(self.factory, ['2.7', '2.8', '2.9'])
        self.makeDominator(pubs).dominatePackage(
            generalization.sortPublications(pubs), ['2.8', '2.9'],
            generalization)
        self.assertEqual(pubs[1].sourcepackagerelease, pubs[0].supersededby)

    def test_dominatePackage_only_supersedes_with_newer_live_pub(self):
        # When marking a package as superseded, dominatePackage only
        # considers a newer version as the superseding one.
        generalization = GeneralizedPublication(True)
        pubs = make_spphs_for_versions(self.factory, ['0.1', '0.2'])
        self.makeDominator(pubs).dominatePackage(
            generalization.sortPublications(pubs), ['0.1'], generalization)
        self.assertEqual(None, pubs[1].supersededby)
        self.assertEqual(PackagePublishingStatus.DELETED, pubs[1].status)

    def test_dominatePackage_supersedes_replaced_pub_for_live_version(self):
        # Even if a publication record is for a live version, a newer
        # one for the same version supersedes it.
        generalization = GeneralizedPublication(True)
        spr = self.factory.makeSourcePackageRelease()
        series = self.factory.makeDistroSeries()
        pocket = PackagePublishingPocket.RELEASE
        pubs = [
            self.factory.makeSourcePackagePublishingHistory(
                archive=series.main_archive, distroseries=series,
                pocket=pocket, status=PackagePublishingStatus.PUBLISHED,
                sourcepackagerelease=spr)
            for counter in xrange(3)]
        alter_creation_dates(pubs, [
            datetime.timedelta(3),
            datetime.timedelta(2),
            datetime.timedelta(1),
            ])

        self.makeDominator(pubs).dominatePackage(
            generalization.sortPublications(pubs), [spr.version],
            generalization)
        self.assertEqual([
            PackagePublishingStatus.SUPERSEDED,
            PackagePublishingStatus.SUPERSEDED,
            PackagePublishingStatus.PUBLISHED,
            ],
            [pub.status for pub in pubs])
        self.assertEqual(
            [spr, spr, None], [pub.supersededby for pub in pubs])

    def test_dominatePackage_is_efficient(self):
        # dominatePackage avoids issuing too many queries.
        generalization = GeneralizedPublication(True)
        versions = ["1.%s" % revision for revision in xrange(5)]
        pubs = make_spphs_for_versions(self.factory, versions)
        with StormStatementRecorder() as recorder:
            self.makeDominator(pubs).dominatePackage(
                generalization.sortPublications(pubs), versions[2:-1],
                generalization)
        self.assertThat(recorder, HasQueryCount(LessThan(5)))

    def test_dominatePackage_advanced_scenario(self):
        # Put dominatePackage through its paces with complex combined
        # data.
        # This test should be redundant in theory (which in theory
        # equates practice but in practice does not).  If this fails,
        # don't just patch up the code or this test.  Create unit tests
        # that specifically cover the difference, then change the code
        # and/or adapt this test to return to harmony.
        generalization = GeneralizedPublication(True)
        series = self.factory.makeDistroSeries()
        package = self.factory.makeSourcePackageName()
        pocket = PackagePublishingPocket.RELEASE

        versions = ["1.%d" % number for number in xrange(4)]

        # We have one package releases for each version.
        relevant_releases = dict(
            (version, self.factory.makeSourcePackageRelease(
                sourcepackagename=package, version=version))
            for version in jumble(versions))

        # Each of those releases is subsequently published in
        # different components.
        components = jumble(
            [self.factory.makeComponent() for version in versions])

        # Map versions to lists of publications for that version, from
        # oldest to newest.  Each re-publishing into a different
        # component is meant to supersede publication into the previous
        # component.
        pubs_by_version = dict(
            (version, [
                self.factory.makeSourcePackagePublishingHistory(
                    archive=series.main_archive, distroseries=series,
                    pocket=pocket, status=PackagePublishingStatus.PUBLISHED,
                    sourcepackagerelease=relevant_releases[version],
                    component=component)
                for component in components])
            for version in jumble(versions))

        ages = jumble(
            [datetime.timedelta(age) for age in xrange(len(versions))])

        # Actually the "oldest to newest" order on the publications only
        # applies to their creation dates.  Their creation orders are
        # irrelevant.
        for pubs_list in pubs_by_version.itervalues():
            alter_creation_dates(pubs_list, ages)
            pubs_list.sort(key=attrgetter('datecreated'))

        live_versions = ["1.1", "1.2"]
        last_version_alive = sorted(live_versions)[-1]

        all_pubs = sum(pubs_by_version.itervalues(), [])
        Dominator(DevNullLogger(), series.main_archive).dominatePackage(
            generalization.sortPublications(all_pubs), live_versions,
            generalization)

        for version in reversed(versions):
            pubs = pubs_by_version[version]

            if version in live_versions:
                # Beware: loop-carried variable.  Used locally as well,
                # but tells later iterations what the highest-versioned
                # release so far was.  This is used in tracking
                # supersededby links.
                superseding_release = pubs[-1].sourcepackagerelease

            if version in live_versions:
                # The live versions' latest publications are Published,
                # their older ones Superseded.
                expected_status = (
                    [PackagePublishingStatus.SUPERSEDED] * (len(pubs) - 1) +
                    [PackagePublishingStatus.PUBLISHED])
                expected_supersededby = (
                    [superseding_release] * (len(pubs) - 1) + [None])
            elif version < last_version_alive:
                # The superseded versions older than the last live
                # version have all been superseded.
                expected_status = (
                    [PackagePublishingStatus.SUPERSEDED] * len(pubs))
                expected_supersededby = [superseding_release] * len(pubs)
            else:
                # Versions that are newer than any live release have
                # been deleted.
                expected_status = (
                    [PackagePublishingStatus.DELETED] * len(pubs))
                expected_supersededby = [None] * len(pubs)

            self.assertEqual(expected_status, [pub.status for pub in pubs])
            self.assertEqual(
                expected_supersededby, [pub.supersededby for pub in pubs])

    def test_dominateSourceVersions_dominates_publications(self):
        # dominateSourceVersions finds the publications for a package
        # and calls dominatePackage on them.
        pubs = make_spphs_for_versions(self.factory, ['0.1', '0.2', '0.3'])
        package_name = pubs[0].sourcepackagerelease.sourcepackagename.name

        self.makeDominator(pubs).dominateSourceVersions(
            pubs[0].distroseries, pubs[0].pocket, package_name, ['0.2'])
        self.assertEqual([
                PackagePublishingStatus.SUPERSEDED,
                PackagePublishingStatus.PUBLISHED,
                PackagePublishingStatus.DELETED,
                ],
            [pub.status for pub in pubs])
        self.assertEqual(
            [pubs[1].sourcepackagerelease, None, None],
            [pub.supersededby for pub in pubs])

    def test_dominateSourceVersions_ignores_other_pockets(self):
        # dominateSourceVersions ignores publications in other pockets
        # than the one specified.
        pubs = make_spphs_for_versions(self.factory, ['2.3', '2.4'])
        package_name = pubs[0].sourcepackagerelease.sourcepackagename.name
        removeSecurityProxy(pubs[0]).pocket = PackagePublishingPocket.UPDATES
        removeSecurityProxy(pubs[1]).pocket = PackagePublishingPocket.PROPOSED
        self.makeDominator(pubs).dominateSourceVersions(
            pubs[0].distroseries, pubs[0].pocket, package_name, ['2.3'])
        self.assertEqual(PackagePublishingStatus.PUBLISHED, pubs[1].status)

    def test_dominateSourceVersions_ignores_other_packages(self):
        pubs = make_spphs_for_versions(self.factory, ['1.0', '1.1'])
        other_package_name = self.factory.makeSourcePackageName().name
        self.makeDominator(pubs).dominateSourceVersions(
            pubs[0].distroseries, pubs[0].pocket, other_package_name, ['1.1'])
        self.assertEqual(PackagePublishingStatus.PUBLISHED, pubs[0].status)

    def test_findPublishedSourcePackageNames_finds_package(self):
        spph = self.factory.makeSourcePackagePublishingHistory(
            status=PackagePublishingStatus.PUBLISHED)
        dominator = self.makeDominator([spph])
        self.assertContentEqual(
            [(spph.sourcepackagerelease.sourcepackagename.name, 1)],
            dominator.findPublishedSourcePackageNames(
                spph.distroseries, spph.pocket))

    def test_findPublishedSourcePackageNames_ignores_other_states(self):
        series = self.factory.makeDistroSeries()
        pocket = PackagePublishingPocket.RELEASE
        spphs = dict(
            (status, self.factory.makeSourcePackagePublishingHistory(
                distroseries=series, archive=series.main_archive,
                pocket=pocket, status=status))
            for status in PackagePublishingStatus.items)
        published_spph = spphs[PackagePublishingStatus.PUBLISHED]
        dominator = self.makeDominator(spphs.values())
        self.assertContentEqual(
            [(published_spph.sourcepackagerelease.sourcepackagename.name, 1)],
            dominator.findPublishedSourcePackageNames(series, pocket))

    def test_findPublishedSourcePackageNames_ignores_other_archives(self):
        spph = self.factory.makeSourcePackagePublishingHistory(
            status=PackagePublishingStatus.PUBLISHED)
        dominator = self.makeDominator([spph])
        dominator.archive = self.factory.makeArchive()
        self.assertContentEqual(
            [],
            dominator.findPublishedSourcePackageNames(
                spph.distroseries, spph.pocket))

    def test_findPublishedSourcePackageNames_ignores_other_series(self):
        spph = self.factory.makeSourcePackagePublishingHistory(
            status=PackagePublishingStatus.PUBLISHED)
        distro = spph.distroseries.distribution
        other_series = self.factory.makeDistroSeries(distribution=distro)
        dominator = self.makeDominator([spph])
        self.assertContentEqual(
            [],
            dominator.findPublishedSourcePackageNames(
                other_series, spph.pocket))

    def test_findPublishedSourcePackageNames_ignores_other_pockets(self):
        spph = self.factory.makeSourcePackagePublishingHistory(
            status=PackagePublishingStatus.PUBLISHED,
            pocket=PackagePublishingPocket.RELEASE)
        dominator = self.makeDominator([spph])
        self.assertContentEqual(
            [],
            dominator.findPublishedSourcePackageNames(
                spph.distroseries, PackagePublishingPocket.SECURITY))

    def test_findPublishedSourcePackageNames_counts_published_SPPHs(self):
        series = self.factory.makeDistroSeries()
        pocket = PackagePublishingPocket.RELEASE
        spr = self.factory.makeSourcePackageRelease()
        spphs = [
            self.factory.makeSourcePackagePublishingHistory(
                distroseries=series, sourcepackagerelease=spr, pocket=pocket,
                status=PackagePublishingStatus.PUBLISHED)
            for counter in xrange(2)]
        dominator = self.makeDominator(spphs)
        self.assertContentEqual(
            [(spr.sourcepackagename.name, len(spphs))],
            dominator.findPublishedSourcePackageNames(series, pocket))

    def test_findPublishedSourcePackageNames_counts_no_other_state(self):
        series = self.factory.makeDistroSeries()
        pocket = PackagePublishingPocket.RELEASE
        spr = self.factory.makeSourcePackageRelease()
        spphs = [
            self.factory.makeSourcePackagePublishingHistory(
                distroseries=series, sourcepackagerelease=spr, pocket=pocket,
                status=status)
            for status in PackagePublishingStatus.items]
        dominator = self.makeDominator(spphs)
        self.assertContentEqual(
            [(spr.sourcepackagename.name, 1)],
            dominator.findPublishedSourcePackageNames(series, pocket))

    def test_findPublishedSPPHs_finds_published_SPPH(self):
        spph = self.factory.makeSourcePackagePublishingHistory(
            status=PackagePublishingStatus.PUBLISHED)
        package_name = spph.sourcepackagerelease.sourcepackagename.name
        dominator = self.makeDominator([spph])
        self.assertContentEqual(
            [spph],
            dominator.findPublishedSPPHs(
                spph.distroseries, spph.pocket, package_name))

    def test_findPublishedSPPHs_ignores_other_states(self):
        series = self.factory.makeDistroSeries()
        package = self.factory.makeSourcePackageName()
        pocket = PackagePublishingPocket.RELEASE
        spphs = dict(
            (status, self.factory.makeSourcePackagePublishingHistory(
                distroseries=series, archive=series.main_archive,
                pocket=pocket, status=status,
                sourcepackagerelease=self.factory.makeSourcePackageRelease(
                    sourcepackagename=package)))
            for status in PackagePublishingStatus.items)
        dominator = self.makeDominator(spphs.values())
        self.assertContentEqual(
            [spphs[PackagePublishingStatus.PUBLISHED]],
            dominator.findPublishedSPPHs(series, pocket, package.name))

    def test_findPublishedSPPHs_ignores_other_archives(self):
        spph = self.factory.makeSourcePackagePublishingHistory(
            status=PackagePublishingStatus.PUBLISHED)
        package = spph.sourcepackagerelease.sourcepackagename
        dominator = self.makeDominator([spph])
        dominator.archive = self.factory.makeArchive()
        self.assertContentEqual(
            [],
            dominator.findPublishedSPPHs(
                spph.distroseries, spph.pocket, package.name))

    def test_findPublishedSPPHs_ignores_other_series(self):
        spph = self.factory.makeSourcePackagePublishingHistory(
            status=PackagePublishingStatus.PUBLISHED)
        distro = spph.distroseries.distribution
        package = spph.sourcepackagerelease.sourcepackagename
        other_series = self.factory.makeDistroSeries(distribution=distro)
        dominator = self.makeDominator([spph])
        self.assertContentEqual(
            [],
            dominator.findPublishedSPPHs(
                other_series, spph.pocket, package.name))

    def test_findPublishedSPPHs_ignores_other_pockets(self):
        spph = self.factory.makeSourcePackagePublishingHistory(
            status=PackagePublishingStatus.PUBLISHED,
            pocket=PackagePublishingPocket.RELEASE)
        package = spph.sourcepackagerelease.sourcepackagename
        dominator = self.makeDominator([spph])
        self.assertContentEqual(
            [],
            dominator.findPublishedSPPHs(
                spph.distroseries, PackagePublishingPocket.SECURITY,
                package.name))

    def test_findPublishedSPPHs_ignores_other_packages(self):
        spph = self.factory.makeSourcePackagePublishingHistory(
            status=PackagePublishingStatus.PUBLISHED)
        other_package = self.factory.makeSourcePackageName()
        dominator = self.makeDominator([spph])
        self.assertContentEqual(
            [],
            dominator.findPublishedSPPHs(
                spph.distroseries, spph.pocket, other_package.name))

    def test_findBinariesForDomination_finds_published_publications(self):
        bpphs = make_bpphs_for_versions(self.factory, ['1.0', '1.1'])
        dominator = self.makeDominator(bpphs)
        self.assertContentEqual(
            bpphs, dominator.findBinariesForDomination(
                bpphs[0].distroarchseries, bpphs[0].pocket))

    def test_findBinariesForDomination_skips_single_pub_packages(self):
        # The domination algorithm that uses findBinariesForDomination
        # always keeps the latest version live.  Thus, a single
        # publication isn't worth dominating.  findBinariesForDomination
        # won't return it.
        bpphs = make_bpphs_for_versions(self.factory, ['1.0'])
        dominator = self.makeDominator(bpphs)
        self.assertContentEqual(
            [], dominator.findBinariesForDomination(
                bpphs[0].distroarchseries, bpphs[0].pocket))

    def test_findBinariesForDomination_ignores_other_distroseries(self):
        bpphs = make_bpphs_for_versions(self.factory, ['1.0', '1.1'])
        dominator = self.makeDominator(bpphs)
        das = bpphs[0].distroarchseries
        other_series = self.factory.makeDistroSeries(
            distribution=das.distroseries.distribution)
        other_das = self.factory.makeDistroArchSeries(
            distroseries=other_series, architecturetag=das.architecturetag,
            processor=das.processor)
        self.assertContentEqual(
            [], dominator.findBinariesForDomination(
                other_das, bpphs[0].pocket))

    def test_findBinariesForDomination_ignores_other_architectures(self):
        bpphs = make_bpphs_for_versions(self.factory, ['1.0', '1.1'])
        dominator = self.makeDominator(bpphs)
        other_das = self.factory.makeDistroArchSeries(
            distroseries=bpphs[0].distroseries)
        self.assertContentEqual(
            [], dominator.findBinariesForDomination(
                other_das, bpphs[0].pocket))

    def test_findBinariesForDomination_ignores_other_archive(self):
        bpphs = make_bpphs_for_versions(self.factory, ['1.0', '1.1'])
        dominator = self.makeDominator(bpphs)
        dominator.archive = self.factory.makeArchive()
        self.assertContentEqual(
            [], dominator.findBinariesForDomination(
                bpphs[0].distroarchseries, bpphs[0].pocket))

    def test_findBinariesForDomination_ignores_other_pocket(self):
        bpphs = make_bpphs_for_versions(self.factory, ['1.0', '1.1'])
        dominator = self.makeDominator(bpphs)
        for bpph in bpphs:
            removeSecurityProxy(bpph).pocket = PackagePublishingPocket.UPDATES
        self.assertContentEqual(
            [], dominator.findBinariesForDomination(
                bpphs[0].distroarchseries, PackagePublishingPocket.SECURITY))

    def test_findBinariesForDomination_ignores_other_status(self):
        # If we have one BPPH for each possible status, plus one
        # Published one to stop findBinariesForDomination from skipping
        # the package, findBinariesForDomination returns only the
        # Published ones.
        versions = [
            '1.%d' % self.factory.getUniqueInteger()
            for status in PackagePublishingStatus.items] + ['0.9']
        bpphs = make_bpphs_for_versions(self.factory, versions)
        dominator = self.makeDominator(bpphs)

        for bpph, status in zip(bpphs, PackagePublishingStatus.items):
            bpph.status = status

        # These are the Published publications.  The other ones will all
        # be ignored.
        published_bpphs = [
            bpph
            for bpph in bpphs
                if bpph.status == PackagePublishingStatus.PUBLISHED]

        self.assertContentEqual(
            published_bpphs,
            dominator.findBinariesForDomination(
                bpphs[0].distroarchseries, bpphs[0].pocket))

    def test_findSourcesForDomination_finds_published_publications(self):
        spphs = make_spphs_for_versions(self.factory, ['2.0', '2.1'])
        dominator = self.makeDominator(spphs)
        self.assertContentEqual(
            spphs, dominator.findSourcesForDomination(
                spphs[0].distroseries, spphs[0].pocket))

    def test_findSourcesForDomination_skips_single_pub_packages(self):
        # The domination algorithm that uses findSourcesForDomination
        # always keeps the latest version live.  Thus, a single
        # publication isn't worth dominating.  findSourcesForDomination
        # won't return it.
        spphs = make_spphs_for_versions(self.factory, ['2.0'])
        dominator = self.makeDominator(spphs)
        self.assertContentEqual(
            [], dominator.findSourcesForDomination(
                spphs[0].distroseries, spphs[0].pocket))

    def test_findSourcesForDomination_ignores_other_distroseries(self):
        spphs = make_spphs_for_versions(self.factory, ['2.0', '2.1'])
        dominator = self.makeDominator(spphs)
        other_series = self.factory.makeDistroSeries(
            distribution=spphs[0].distroseries.distribution)
        self.assertContentEqual(
            [], dominator.findSourcesForDomination(
                other_series, spphs[0].pocket))

    def test_findSourcesForDomination_ignores_other_pocket(self):
        spphs = make_spphs_for_versions(self.factory, ['2.0', '2.1'])
        dominator = self.makeDominator(spphs)
        for spph in spphs:
            removeSecurityProxy(spph).pocket = PackagePublishingPocket.UPDATES
        self.assertContentEqual(
            [], dominator.findSourcesForDomination(
                spphs[0].distroseries, PackagePublishingPocket.SECURITY))

    def test_findSourcesForDomination_ignores_other_status(self):
        versions = [
            '1.%d' % self.factory.getUniqueInteger()
            for status in PackagePublishingStatus.items] + ['0.9']
        spphs = make_spphs_for_versions(self.factory, versions)
        dominator = self.makeDominator(spphs)

        for spph, status in zip(spphs, PackagePublishingStatus.items):
            spph.status = status

        # These are the Published publications.  The other ones will all
        # be ignored.
        published_spphs = [
            spph
            for spph in spphs
                if spph.status == PackagePublishingStatus.PUBLISHED]

        self.assertContentEqual(
            published_spphs,
            dominator.findSourcesForDomination(
                spphs[0].distroseries, spphs[0].pocket))


def make_publications_arch_specific(pubs, arch_specific=True):
    """Set the `architecturespecific` attribute for given SPPHs.

    :param pubs: An iterable of `BinaryPackagePublishingHistory`.
    :param arch_specific: Whether the binary package releases published
        by `pubs` are to be architecture-specific.  If not, they will be
        treated as being for the "all" architecture.
    """
    for pub in pubs:
        bpr = removeSecurityProxy(pub).binarypackagerelease
        bpr.architecturespecific = arch_specific


class TestLivenessFunctions(TestCaseWithFactory):
    """Tests for the functions that say which versions are live."""

    layer = ZopelessDatabaseLayer

    def test_find_live_source_versions_blesses_latest(self):
        # find_live_source_versions, assuming that you passed it
        # publications sorted from most current to least current
        # version, simply returns the most current version.
        spphs = make_spphs_for_versions(self.factory, ['1.2', '1.1', '1.0'])
        self.assertEqual(['1.2'], find_live_source_versions(spphs))

    def test_find_live_binary_versions_pass_1_blesses_latest(self):
        # find_live_binary_versions_pass_1 always includes the latest
        # version among the input publications in its result.
        bpphs = make_bpphs_for_versions(self.factory, ['1.2', '1.1', '1.0'])
        make_publications_arch_specific(bpphs)
        self.assertEqual(['1.2'], find_live_binary_versions_pass_1(bpphs))

    def test_find_live_binary_versions_pass_1_blesses_arch_all(self):
        # find_live_binary_versions_pass_1 includes any
        # architecture-independent publications among the input in its
        # result.
        versions = list(reversed(['1.%d' % version for version in range(3)]))
        bpphs = make_bpphs_for_versions(self.factory, versions)

        # All of these publications are architecture-specific, except
        # the last one.  This would happen if the binary package had
        # just changed from being architecture-specific to being
        # architecture-independent.
        make_publications_arch_specific(bpphs, True)
        make_publications_arch_specific(bpphs[-1:], False)
        self.assertEqual(
            versions[:1] + versions[-1:],
            find_live_binary_versions_pass_1(bpphs))

    def test_find_live_binary_versions_pass_2_blesses_latest(self):
        # find_live_binary_versions_pass_2 always includes the latest
        # version among the input publications in its result.
        bpphs = make_bpphs_for_versions(self.factory, ['1.2', '1.1', '1.0'])
        make_publications_arch_specific(bpphs, False)
        cache = ArchSpecificPublicationsCache()
        self.assertEqual(
            ['1.2'], find_live_binary_versions_pass_2(bpphs, cache))

    def test_find_live_binary_versions_pass_2_blesses_arch_specific(self):
        # find_live_binary_versions_pass_2 includes any
        # architecture-specific publications among the input in its
        # result.
        versions = list(reversed(['1.%d' % version for version in range(3)]))
        bpphs = make_bpphs_for_versions(self.factory, versions)
        make_publications_arch_specific(bpphs)
        cache = ArchSpecificPublicationsCache()
        self.assertEqual(
            versions, find_live_binary_versions_pass_2(bpphs, cache))

    def test_find_live_binary_versions_pass_2_reprieves_arch_all(self):
        # An arch-all BPPH for a BPR built by an SPR that also still has
        # active arch-dependent BPPHs gets a reprieve: it can't be
        # superseded until those arch-dependent BPPHs have been
        # superseded.
        bpphs = make_bpphs_for_versions(self.factory, ['1.2', '1.1', '1.0'])
        make_publications_arch_specific(bpphs, False)
        dependent = self.factory.makeBinaryPackagePublishingHistory(
            binarypackagerelease=bpphs[1].binarypackagerelease)
        make_publications_arch_specific([dependent], True)
        cache = ArchSpecificPublicationsCache()
        self.assertEqual(
            ['1.2', '1.1'], find_live_binary_versions_pass_2(bpphs, cache))


class TestDominationHelpers(TestCaseWithFactory):
    """Test lightweight helpers for the `Dominator`."""

    layer = ZopelessDatabaseLayer

    def test_contains_arch_indep_says_True_for_arch_indep(self):
        bpphs = [self.factory.makeBinaryPackagePublishingHistory()]
        make_publications_arch_specific(bpphs, False)
        self.assertTrue(contains_arch_indep(bpphs))

    def test_contains_arch_indep_says_False_for_arch_specific(self):
        bpphs = [self.factory.makeBinaryPackagePublishingHistory()]
        make_publications_arch_specific(bpphs, True)
        self.assertFalse(contains_arch_indep(bpphs))

    def test_contains_arch_indep_says_True_for_combination(self):
        bpphs = make_bpphs_for_versions(self.factory, ['1.1', '1.0'])
        make_publications_arch_specific(bpphs[:1], True)
        make_publications_arch_specific(bpphs[1:], False)
        self.assertTrue(contains_arch_indep(bpphs))

    def test_contains_arch_indep_says_False_for_empty_list(self):
        self.assertFalse(contains_arch_indep([]))


class TestArchSpecificPublicationsCache(TestCaseWithFactory):
    """Tests for `ArchSpecificPublicationsCache`."""

    layer = ZopelessDatabaseLayer

    def makeCache(self):
        """Shorthand: create a ArchSpecificPublicationsCache."""
        return ArchSpecificPublicationsCache()

    def makeSPR(self):
        """Create a `BinaryPackageRelease`."""
        # Return an un-proxied SPR.  This is script code, so it won't be
        # running into them in real life.
        return removeSecurityProxy(self.factory.makeSourcePackageRelease())

    def makeBPPH(self, spr=None, arch_specific=True, archive=None,
                 distroseries=None):
        """Create a `BinaryPackagePublishingHistory`."""
        if spr is None:
            spr = self.makeSPR()
        das = self.factory.makeDistroArchSeries(distroseries=distroseries)
        bpb = self.factory.makeBinaryPackageBuild(
            source_package_release=spr, distroarchseries=das)
        bpr = self.factory.makeBinaryPackageRelease(
            build=bpb, architecturespecific=arch_specific)
        return removeSecurityProxy(
            self.factory.makeBinaryPackagePublishingHistory(
                binarypackagerelease=bpr, archive=archive,
                distroarchseries=das, pocket=PackagePublishingPocket.UPDATES,
                status=PackagePublishingStatus.PUBLISHED))

    def test_getKey_is_consistent_and_distinguishing(self):
        # getKey consistently returns the same key for the same BPPH,
        # but different keys for non-matching BPPHs.
        bpphs = [
            self.factory.makeBinaryPackagePublishingHistory()
            for counter in range(2)]
        cache = self.makeCache()
        self.assertContentEqual(
            [cache.getKey(bpph) for bpph in bpphs],
            set(cache.getKey(bpph) for bpph in bpphs * 2))

    def test_hasArchSpecificPublications_is_consistent_and_correct(self):
        # hasArchSpecificPublications consistently, repeatably returns
        # the same result for the same key.  Naturally, different keys
        # can still produce different results.
        spr = self.makeSPR()
        dependent = self.makeBPPH(spr, arch_specific=True)
        bpph1 = self.makeBPPH(
            spr, arch_specific=False, archive=dependent.archive,
            distroseries=dependent.distroseries)
        bpph2 = self.makeBPPH(arch_specific=False)
        cache = self.makeCache()
        self.assertEqual(
            [True, True, False, False],
            [
                cache.hasArchSpecificPublications(bpph1),
                cache.hasArchSpecificPublications(bpph1),
                cache.hasArchSpecificPublications(bpph2),
                cache.hasArchSpecificPublications(bpph2),
            ])

    def test_hasArchSpecificPublications_caches_results(self):
        # Results are cached, so once the presence of archive-specific
        # publications has been looked up in the database, the query is
        # not performed again for the same inputs.
        spr = self.makeSPR()
        self.makeBPPH(spr, arch_specific=True)
        bpph = self.makeBPPH(spr, arch_specific=False)
        cache = self.makeCache()
        cache.hasArchSpecificPublications(bpph)
        spr.getActiveArchSpecificPublications = FakeMethod()
        cache.hasArchSpecificPublications(bpph)
        self.assertEqual(0, spr.getActiveArchSpecificPublications.call_count)
