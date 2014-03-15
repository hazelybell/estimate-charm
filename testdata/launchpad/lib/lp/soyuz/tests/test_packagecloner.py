# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.buildmaster.enums import BuildStatus
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.soyuz.adapters.packagelocation import PackageLocation
from lp.soyuz.enums import (
    ArchivePurpose,
    PackagePublishingStatus,
    )
from lp.soyuz.interfaces.archivearch import IArchiveArchSet
from lp.soyuz.interfaces.binarypackagebuild import IBinaryPackageBuildSet
from lp.soyuz.interfaces.component import IComponentSet
from lp.soyuz.interfaces.packagecloner import IPackageCloner
from lp.soyuz.interfaces.processor import IProcessorSet
from lp.soyuz.interfaces.publishing import (
    active_publishing_status,
    IPublishingSet,
    )
from lp.testing import TestCaseWithFactory
from lp.testing.layers import LaunchpadZopelessLayer


class PackageInfo:

    def __init__(self, name, version,
                 status=PackagePublishingStatus.PUBLISHED, component="main"):
        self.name = name
        self.version = version
        self.status = status
        self.component = component


class PackageClonerTests(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def checkCopiedSources(self, archive, distroseries, expected):
        """Check the sources published in an archive against an expected set.

        Given an archive and a target distroseries the sources published in
        that distroseries are checked against a set of PackageInfo to
        ensure that the correct package names and versions are published.
        """
        expected_set = set([(info.name, info.version) for info in expected])
        sources = archive.getPublishedSources(
            distroseries=distroseries,
            status=active_publishing_status)
        actual_set = set()
        for source in sources:
            source = removeSecurityProxy(source)
            actual_set.add(
                (source.source_package_name, source.source_package_version))
        self.assertEqual(expected_set, actual_set)

    def createSourceDistribution(self, package_infos):
        """Create a distribution to be the source of a copy archive."""
        distroseries = self.createSourceDistroSeries()
        self.createSourcePublications(package_infos, distroseries)
        return distroseries

    def createSourceDistroSeries(self):
        """Create a DistroSeries suitable for copying.

        Creates a distroseries with a DistroArchSeries and nominatedarchindep,
        which makes it suitable for copying because it will create some
        builds.
        """
        distro_name = "foobuntu"
        distro = self.factory.makeDistribution(name=distro_name)
        distroseries_name = "maudlin"
        distroseries = self.factory.makeDistroSeries(
            distribution=distro, name=distroseries_name)
        das = self.factory.makeDistroArchSeries(
            distroseries=distroseries, architecturetag="i386",
            processor=getUtility(IProcessorSet).getByName('386'),
            supports_virtualized=True)
        distroseries.nominatedarchindep = das
        return distroseries

    def getTargetArchive(self, distribution):
        """Get a target archive for copying in to."""
        return self.factory.makeArchive(
            name="test-copy-archive", purpose=ArchivePurpose.COPY,
            distribution=distribution)

    def createSourcePublication(self, info, distroseries):
        """Create a SourcePackagePublishingHistory based on a PackageInfo."""
        archive = distroseries.distribution.main_archive
        sources = archive.getPublishedSources(
            distroseries=distroseries,
            status=active_publishing_status,
            name=info.name, exact_match=True)
        for src in sources:
            src.supersede()
        self.factory.makeSourcePackagePublishingHistory(
            sourcepackagename=self.factory.getOrMakeSourcePackageName(
                name=info.name),
            distroseries=distroseries, component=self.factory.makeComponent(
                info.component),
            version=info.version, architecturehintlist='any',
            archive=archive, status=info.status,
            pocket=PackagePublishingPocket.RELEASE)

    def createSourcePublications(self, package_infos, distroseries):
        """Create a source publication for each item in package_infos."""
        for package_info in package_infos:
            self.createSourcePublication(package_info, distroseries)

    def makeCopyArchive(self, package_infos, component="main",
                        source_pocket=None, target_pocket=None,
                        processors=None):
        """Make a copy archive based on a new distribution."""
        distroseries = self.createSourceDistribution(package_infos)
        copy_archive = self.getTargetArchive(distroseries.distribution)
        to_component = getUtility(IComponentSet).ensure(component)
        self.copyArchive(
            copy_archive, distroseries, from_pocket=source_pocket,
            to_pocket=target_pocket, to_component=to_component,
            processors=processors)
        return (copy_archive, distroseries)

    def checkBuilds(self, archive, package_infos):
        """Check the build records pending in an archive.

        Given a set of PackageInfo objects check that each has a build
        created for it.
        """
        expected_builds = list(
            [(info.name, info.version) for info in package_infos])
        builds = list(
            getUtility(IBinaryPackageBuildSet).getBuildsForArchive(
            archive, status=BuildStatus.NEEDSBUILD))
        actual_builds = list()
        for build in builds:
            naked_build = removeSecurityProxy(build)
            spr = naked_build.source_package_release
            actual_builds.append((spr.name, spr.version))
        self.assertEqual(sorted(expected_builds), sorted(actual_builds))

    def copyArchive(self, to_archive, to_distroseries, from_archive=None,
                    from_distroseries=None, from_pocket=None, to_pocket=None,
                    to_component=None, packagesets=None, processors=None):
        """Use a PackageCloner to copy an archive."""
        if from_distroseries is None:
            from_distroseries = to_distroseries
        if from_archive is None:
            from_archive = from_distroseries.distribution.main_archive
        if from_pocket is None:
            from_pocket = PackagePublishingPocket.RELEASE
        if to_pocket is None:
            to_pocket = PackagePublishingPocket.RELEASE
        if packagesets is None:
            packagesets = []
        origin = PackageLocation(
            from_archive, from_distroseries.distribution, from_distroseries,
            from_pocket)
        destination = PackageLocation(
            to_archive, to_distroseries.distribution, to_distroseries,
            to_pocket)
        origin.packagesets = packagesets
        if to_component is not None:
            destination.component = to_component
        cloner = getUtility(IPackageCloner)
        cloner.clonePackages(
            origin, destination, distroarchseries_list=None,
            processors=processors)
        return cloner

    def testCopiesPublished(self):
        """Test that PUBLISHED sources are copied."""
        package_info = PackageInfo(
            "bzr", "2.1", status=PackagePublishingStatus.PUBLISHED)
        copy_archive, distroseries = self.makeCopyArchive([package_info])
        self.checkCopiedSources(
            copy_archive, distroseries, [package_info])

    def testCopiesPending(self):
        """Test that PENDING sources are copied."""
        package_info = PackageInfo(
            "bzr", "2.1", status=PackagePublishingStatus.PENDING)
        copy_archive, distroseries = self.makeCopyArchive([package_info])
        self.checkCopiedSources(
            copy_archive, distroseries, [package_info])

    def testDoesntCopySuperseded(self):
        """Test that SUPERSEDED sources are not copied."""
        package_info = PackageInfo(
            "bzr", "2.1", status=PackagePublishingStatus.SUPERSEDED)
        copy_archive, distroseries = self.makeCopyArchive([package_info])
        self.checkCopiedSources(
            copy_archive, distroseries, [])

    def testDoesntCopyDeleted(self):
        """Test that DELETED sources are not copied."""
        package_info = PackageInfo(
            "bzr", "2.1", status=PackagePublishingStatus.DELETED)
        copy_archive, distroseries = self.makeCopyArchive([package_info])
        self.checkCopiedSources(
            copy_archive, distroseries, [])

    def testDoesntCopyObsolete(self):
        """Test that OBSOLETE sources are not copied."""
        package_info = PackageInfo(
            "bzr", "2.1", status=PackagePublishingStatus.OBSOLETE)
        copy_archive, distroseries = self.makeCopyArchive([package_info])
        self.checkCopiedSources(
            copy_archive, distroseries, [])

    def testCopiesAllComponents(self):
        """Test that packages from all components are copied.

        When copying you specify a component, but that component doesn't
        limit the packages copied. We create a source in main and one in
        universe, and then copy with --component main, and expect to see
        both sources in the copy.
        """
        package_infos = [
            PackageInfo(
                "bzr", "2.1", status=PackagePublishingStatus.PUBLISHED,
                component="universe"),
            PackageInfo(
                "apt", "2.2", status=PackagePublishingStatus.PUBLISHED,
                component="main")]
        copy_archive, distroseries = self.makeCopyArchive(package_infos,
            component="main")
        self.checkCopiedSources(copy_archive, distroseries, package_infos)

    def testSubsetsBasedOnPackageset(self):
        """Test that --package-set limits the sources copied."""
        package_infos = [
            PackageInfo(
                "bzr", "2.1", status=PackagePublishingStatus.PUBLISHED),
            PackageInfo(
                "apt", "2.2", status=PackagePublishingStatus.PUBLISHED),
            ]
        distroseries = self.createSourceDistribution(package_infos)
        spn = self.factory.getOrMakeSourcePackageName(name="apt")
        packageset = self.factory.makePackageset(
            distroseries=distroseries, packages=(spn,))
        copy_archive = self.getTargetArchive(distroseries.distribution)
        self.copyArchive(copy_archive, distroseries, packagesets=[packageset])
        self.checkCopiedSources(
            copy_archive, distroseries, [package_infos[1]])

    def testUnionsPackagesets(self):
        """Test that package sets are unioned when copying archives."""
        package_infos = [
            PackageInfo(
                "bzr", "2.1", status=PackagePublishingStatus.PUBLISHED),
            PackageInfo(
                "apt", "2.2", status=PackagePublishingStatus.PUBLISHED),
            PackageInfo(
                "gcc", "4.5", status=PackagePublishingStatus.PUBLISHED),
            ]
        distroseries = self.createSourceDistribution(package_infos)
        apt_spn = self.factory.getOrMakeSourcePackageName(name="apt")
        gcc_spn = self.factory.getOrMakeSourcePackageName(name="gcc")
        apt_packageset = self.factory.makePackageset(
            distroseries=distroseries, packages=(apt_spn,))
        gcc_packageset = self.factory.makePackageset(
            distroseries=distroseries, packages=(gcc_spn,))
        copy_archive = self.getTargetArchive(distroseries.distribution)
        self.copyArchive(
            copy_archive, distroseries,
            packagesets=[apt_packageset, gcc_packageset])
        self.checkCopiedSources(
            copy_archive, distroseries, package_infos[1:])

    def testRecursivelyCopiesPackagesets(self):
        """Test that package set copies include subsets."""
        package_infos = [
            PackageInfo(
                "bzr", "2.1", status=PackagePublishingStatus.PUBLISHED),
            PackageInfo(
                "apt", "2.2", status=PackagePublishingStatus.PUBLISHED),
            PackageInfo(
                "gcc", "4.5", status=PackagePublishingStatus.PUBLISHED),
            ]
        distroseries = self.createSourceDistribution(package_infos)
        apt_spn = self.factory.getOrMakeSourcePackageName(name="apt")
        gcc_spn = self.factory.getOrMakeSourcePackageName(name="gcc")
        apt_packageset = self.factory.makePackageset(
            distroseries=distroseries, packages=(apt_spn,))
        gcc_packageset = self.factory.makePackageset(
            distroseries=distroseries, packages=(gcc_spn,))
        apt_packageset.add((gcc_packageset,))
        copy_archive = self.getTargetArchive(distroseries.distribution)
        self.copyArchive(
            copy_archive, distroseries, packagesets=[apt_packageset])
        self.checkCopiedSources(
            copy_archive, distroseries, package_infos[1:])

    def testCloneFromPPA(self):
        """Test we can create a copy archive with a PPA as the source."""
        distroseries = self.createSourceDistroSeries()
        ppa = self.factory.makeArchive(
            purpose=ArchivePurpose.PPA,
            distribution=distroseries.distribution)
        package_info = PackageInfo(
                "bzr", "2.1", status=PackagePublishingStatus.PUBLISHED,
                component="universe")
        self.factory.makeSourcePackagePublishingHistory(
            sourcepackagename=self.factory.getOrMakeSourcePackageName(
                name=package_info.name),
            distroseries=distroseries, component=self.factory.makeComponent(
                package_info.component),
            version=package_info.version, archive=ppa,
            status=package_info.status, architecturehintlist='any',
            pocket=PackagePublishingPocket.RELEASE)
        copy_archive = self.getTargetArchive(distroseries.distribution)
        self.copyArchive(copy_archive, distroseries, from_archive=ppa)
        self.checkCopiedSources(
            copy_archive, distroseries, [package_info])

    def testCreatesNoBuildsWithNoProcessors(self):
        """Test that no builds are created if we specify no processors."""
        package_info = PackageInfo(
            "bzr", "2.1", status=PackagePublishingStatus.PUBLISHED)
        copy_archive, distroseries = self.makeCopyArchive([package_info])
        self.checkBuilds(copy_archive, [])

    def testCreatesBuilds(self):
        """Test that a copy archive creates builds for the copied packages."""
        package_info = PackageInfo(
            "bzr", "2.1", status=PackagePublishingStatus.PUBLISHED)
        # This is the processor for the DAS that the source has, so we expect
        # to get builds.
        processors = [getUtility(IProcessorSet).getByName('386')]
        copy_archive, distroseries = self.makeCopyArchive(
            [package_info], processors=processors)
        self.checkBuilds(copy_archive, [package_info])

    def testNoBuildsIfProcessorNotInSource(self):
        """Test that no builds are created for a processor without a DAS."""
        package_info = PackageInfo(
            "bzr", "2.1", status=PackagePublishingStatus.PUBLISHED)
        # This is a processor without a DAS in the source, so we expect no
        # builds.
        processors = [self.factory.makeProcessor(name="armel")]
        copy_archive, distroseries = self.makeCopyArchive(
            [package_info], processors=processors)
        self.checkBuilds(copy_archive, [])

    def testBuildsOnlyForProcessorsInSource(self):
        """Test that builds are only created for processors in source."""
        package_info = PackageInfo(
            "bzr", "2.1", status=PackagePublishingStatus.PUBLISHED)
        # One of these processors has a DAS in the source, so we expect one
        # set of builds.
        processors = [
            self.factory.makeProcessor(name="armel"),
            getUtility(IProcessorSet).getByName('386')]
        copy_archive, distroseries = self.makeCopyArchive(
            [package_info], processors=processors)
        self.checkBuilds(copy_archive, [package_info])

    def testCreatesSubsetOfBuilds(self):
        """Test that builds are only created for requested processors."""
        package_info = PackageInfo(
            "bzr", "2.1", status=PackagePublishingStatus.PUBLISHED)
        distroseries = self.createSourceDistribution([package_info])
        # Create a DAS for a second processor. 
        self.factory.makeDistroArchSeries(
            distroseries=distroseries, architecturetag="amd64",
            processor=getUtility(IProcessorSet).getByName('amd64'),
            supports_virtualized=True)
        # The request builds for only one of the processors, so we
        # expect just one build for each source.
        processors = [getUtility(IProcessorSet).getByName('386')]
        copy_archive = self.getTargetArchive(distroseries.distribution)
        self.copyArchive(
            copy_archive, distroseries, processors=processors)
        self.checkBuilds(copy_archive, [package_info])

    def testCreatesMultipleBuilds(self):
        """Test that multiple processors result in mutiple builds."""
        package_info = PackageInfo(
            "bzr", "2.1", status=PackagePublishingStatus.PUBLISHED)
        distroseries = self.createSourceDistribution([package_info])
        # Create a DAS for a second processor.
        amd64 = getUtility(IProcessorSet).getByName('amd64')
        self.factory.makeDistroArchSeries(
            distroseries=distroseries, architecturetag="amd64",
            processor=amd64, supports_virtualized=True)
        # The request builds for both processors, so we expect two builds
        # per source.
        processors = [getUtility(IProcessorSet).getByName('386'), amd64]
        copy_archive = self.getTargetArchive(distroseries.distribution)
        self.copyArchive(
            copy_archive, distroseries, processors=processors)
        self.checkBuilds(copy_archive, [package_info, package_info])

    def diffArchives(self, target_archive, target_distroseries,
                     source_archive=None, source_distroseries=None):
        """Run a packageSetDiff of two archives."""
        if source_distroseries is None:
            source_distroseries = target_distroseries
        if source_archive is None:
            source_archive = source_distroseries.distribution.main_archive
        source_location = PackageLocation(
            source_archive, source_distroseries.distribution,
            source_distroseries, PackagePublishingPocket.RELEASE)
        target_location = PackageLocation(
            target_archive, target_distroseries.distribution,
            target_distroseries, PackagePublishingPocket.RELEASE)
        cloner = getUtility(IPackageCloner)
        return cloner.packageSetDiff(source_location, target_location)

    def checkPackageDiff(self, expected_changed, expected_new, actual,
                         archive):
        """Check that the diff of two archives is as expected."""
        actual_changed_keys, actual_new_keys = actual
        expected_changed_tuples = [(e.name, e.version)
                                   for e in expected_changed]
        expected_new_tuples = [(e.name, e.version) for e in expected_new]

        def get_tuples(source_keys):
            tuples = []
            for source_key in source_keys:
                source = getUtility(IPublishingSet).getByIdAndArchive(
                    source_key, archive, source=True)
                self.assertNotEqual(source, None, "Got a non-existant "
                        "source publishing record: %d" % source_key)
                naked_source = removeSecurityProxy(source)
                tuples.append(
                    (naked_source.source_package_name,
                     naked_source.source_package_version))
            return tuples
        actual_changed_tuples = get_tuples(actual_changed_keys)
        actual_new_tuples = get_tuples(actual_new_keys)
        self.assertContentEqual(expected_changed_tuples, actual_changed_tuples)
        self.assertContentEqual(expected_new_tuples, actual_new_tuples)

    def testPackageSetDiffWithNothingNew(self):
        """Test packageSetDiff."""
        package_info = PackageInfo(
            "bzr", "2.1", status=PackagePublishingStatus.PUBLISHED)
        copy_archive, distroseries = self.makeCopyArchive([package_info])
        diff = self.diffArchives(copy_archive, distroseries)
        self.checkPackageDiff(
            [], [], diff, distroseries.distribution.main_archive)

    def testPackageSetDiffWithNewPackages(self):
        package_info = PackageInfo(
            "bzr", "2.1", status=PackagePublishingStatus.PUBLISHED)
        copy_archive, distroseries = self.makeCopyArchive([package_info])
        package_infos = [
            PackageInfo(
            "apt", "1.2", status=PackagePublishingStatus.PUBLISHED),
            PackageInfo(
            "gcc", "4.5", status=PackagePublishingStatus.PENDING),
        ]
        self.createSourcePublications(package_infos, distroseries)
        diff = self.diffArchives(copy_archive, distroseries)
        self.checkPackageDiff(
            [], package_infos, diff, distroseries.distribution.main_archive)

    def testPackageSetDiffWithChangedPackages(self):
        package_infos = [
            PackageInfo(
            "bzr", "2.1", status=PackagePublishingStatus.PUBLISHED),
            PackageInfo(
            "apt", "1.2", status=PackagePublishingStatus.PUBLISHED),
        ]
        copy_archive, distroseries = self.makeCopyArchive(package_infos)
        package_infos = [
            PackageInfo(
            "bzr", "2.2", status=PackagePublishingStatus.PUBLISHED),
            PackageInfo(
            "apt", "1.3", status=PackagePublishingStatus.PENDING),
        ]
        self.createSourcePublications(package_infos, distroseries)
        diff = self.diffArchives(copy_archive, distroseries)
        self.checkPackageDiff(
            package_infos, [], diff, distroseries.distribution.main_archive)

    def testPackageSetDiffWithBoth(self):
        package_infos = [
            PackageInfo(
            "bzr", "2.1", status=PackagePublishingStatus.PUBLISHED),
            PackageInfo(
            "apt", "1.2", status=PackagePublishingStatus.PUBLISHED),
        ]
        copy_archive, distroseries = self.makeCopyArchive(package_infos)
        package_infos = [
            PackageInfo(
            "bzr", "2.2", status=PackagePublishingStatus.PUBLISHED),
            PackageInfo(
            "gcc", "1.3", status=PackagePublishingStatus.PENDING),
        ]
        self.createSourcePublications(package_infos, distroseries)
        diff = self.diffArchives(copy_archive, distroseries)
        self.checkPackageDiff(
            [package_infos[0]], [package_infos[1]], diff,
            distroseries.distribution.main_archive)

    def mergeCopy(self, target_archive, target_distroseries,
                  source_archive=None, source_distroseries=None):
        if source_distroseries is None:
            source_distroseries = target_distroseries
        if source_archive is None:
            source_archive = source_distroseries.distribution.main_archive
        source_location = PackageLocation(
            source_archive, source_distroseries.distribution,
            source_distroseries, PackagePublishingPocket.RELEASE)
        target_location = PackageLocation(
            target_archive, target_distroseries.distribution,
            target_distroseries, PackagePublishingPocket.RELEASE)
        cloner = getUtility(IPackageCloner)
        return cloner.mergeCopy(source_location, target_location)

    def test_mergeCopy_initializes_sourcepackagename(self):
        copy_archive, distroseries = self.makeCopyArchive([])
        package_info = PackageInfo(
            "bzr", "2.1", status=PackagePublishingStatus.PUBLISHED)
        self.createSourcePublications([package_info], distroseries)
        self.mergeCopy(copy_archive, distroseries)
        [spph] = copy_archive.getPublishedSources()
        self.assertEqual(
            spph.sourcepackagerelease.sourcepackagename,
            spph.sourcepackagename)

    def testMergeCopyNoChanges(self):
        package_info = PackageInfo(
            "bzr", "2.1", status=PackagePublishingStatus.PUBLISHED)
        copy_archive, distroseries = self.makeCopyArchive([package_info])
        self.mergeCopy(copy_archive, distroseries)
        self.checkCopiedSources(
            copy_archive, distroseries, [package_info])

    def testMergeCopyWithNewPackages(self):
        package_info = PackageInfo(
            "bzr", "2.1", status=PackagePublishingStatus.PUBLISHED)
        copy_archive, distroseries = self.makeCopyArchive([package_info])
        package_infos = [
            PackageInfo(
            "apt", "1.2", status=PackagePublishingStatus.PUBLISHED),
            PackageInfo(
            "gcc", "4.5", status=PackagePublishingStatus.PENDING),
        ]
        self.createSourcePublications(package_infos, distroseries)
        self.mergeCopy(copy_archive, distroseries)
        self.checkCopiedSources(
            copy_archive, distroseries, [package_info] + package_infos)

    def testMergeCopyWithChangedPackages(self):
        package_infos = [
            PackageInfo(
            "bzr", "2.1", status=PackagePublishingStatus.PUBLISHED),
            PackageInfo(
            "apt", "1.2", status=PackagePublishingStatus.PUBLISHED),
        ]
        copy_archive, distroseries = self.makeCopyArchive(package_infos)
        package_infos = [
            PackageInfo(
            "bzr", "2.2", status=PackagePublishingStatus.PUBLISHED),
            PackageInfo(
            "apt", "1.3", status=PackagePublishingStatus.PENDING),
        ]
        self.createSourcePublications(package_infos, distroseries)
        self.mergeCopy(copy_archive, distroseries)
        # Critically there is only one record for each info, as the
        # others have been obsoleted.
        self.checkCopiedSources(
            copy_archive, distroseries, package_infos)

    def testMergeCopyWithBoth(self):
        package_infos = [
            PackageInfo(
            "bzr", "2.1", status=PackagePublishingStatus.PUBLISHED),
            PackageInfo(
            "apt", "1.2", status=PackagePublishingStatus.PUBLISHED),
        ]
        copy_archive, distroseries = self.makeCopyArchive(package_infos)
        package_infos2 = [
            PackageInfo(
            "bzr", "2.2", status=PackagePublishingStatus.PUBLISHED),
            PackageInfo(
            "gcc", "1.3", status=PackagePublishingStatus.PENDING),
        ]
        self.createSourcePublications(package_infos2, distroseries)
        self.mergeCopy(copy_archive, distroseries)
        # Again bzr is obsoleted, gcc is added and apt remains.
        self.checkCopiedSources(
            copy_archive, distroseries, [package_infos[1]] + package_infos2)

    def setArchiveArchitectures(self, archive, processors):
        """Associate the archive with the processors."""
        aa_set = getUtility(IArchiveArchSet)
        for processor in processors:
            aa_set.new(archive, processor)

    def testMergeCopyCreatesBuilds(self):
        package_infos = [
            PackageInfo(
            "bzr", "2.1", status=PackagePublishingStatus.PUBLISHED),
            PackageInfo(
            "apt", "1.2", status=PackagePublishingStatus.PUBLISHED),
        ]
        processors = [getUtility(IProcessorSet).getByName('386')]
        copy_archive, distroseries = self.makeCopyArchive(
            package_infos, processors=processors)
        self.setArchiveArchitectures(copy_archive, processors)
        package_infos2 = [
            PackageInfo(
            "bzr", "2.2", status=PackagePublishingStatus.PUBLISHED),
            PackageInfo(
            "gcc", "1.3", status=PackagePublishingStatus.PENDING),
        ]
        self.createSourcePublications(package_infos2, distroseries)
        self.mergeCopy(copy_archive, distroseries)
        # We get all builds, as superseding bzr doesn't cancel the
        # build
        self.checkBuilds(copy_archive, package_infos + package_infos2)

    def testMergeCopyCreatesNoBuildsWhenNoArchitectures(self):
        package_infos = [
            PackageInfo(
            "bzr", "2.1", status=PackagePublishingStatus.PUBLISHED),
        ]
        # We specify no processors at creation time.
        copy_archive, distroseries = self.makeCopyArchive(
            package_infos, processors=[])
        package_infos2 = [
            PackageInfo(
            "bzr", "2.2", status=PackagePublishingStatus.PUBLISHED),
        ]
        self.createSourcePublications(package_infos2, distroseries)
        self.mergeCopy(copy_archive, distroseries)
        # And so we get no builds at merge time.
        self.checkBuilds(copy_archive, [])

    def testMergeCopyCreatesBuildsForMultipleArchitectures(self):
        package_infos = [
            PackageInfo(
            "bzr", "2.1", status=PackagePublishingStatus.PUBLISHED),
            PackageInfo(
            "apt", "1.2", status=PackagePublishingStatus.PUBLISHED),
        ]
        distroseries = self.createSourceDistribution(package_infos)
        # Create a DAS for a second processor.
        amd64 = getUtility(IProcessorSet).getByName('amd64')
        self.factory.makeDistroArchSeries(
            distroseries=distroseries, architecturetag="amd64",
            processor=amd64, supports_virtualized=True)
        # The request builds for both processors, so we expect two builds
        # per source.
        processors = [getUtility(IProcessorSet).getByName('386'), amd64]
        copy_archive = self.getTargetArchive(distroseries.distribution)
        self.setArchiveArchitectures(copy_archive, processors)
        self.copyArchive(
            copy_archive, distroseries, processors=processors)
        package_infos2 = [
            PackageInfo(
            "bzr", "2.2", status=PackagePublishingStatus.PUBLISHED),
            PackageInfo(
            "gcc", "1.3", status=PackagePublishingStatus.PENDING),
        ]
        self.createSourcePublications(package_infos2, distroseries)
        self.mergeCopy(copy_archive, distroseries)
        # We get all builds twice, one for each architecture.
        self.checkBuilds(
            copy_archive,
            package_infos + package_infos + package_infos2 + package_infos2)
