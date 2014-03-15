# Copyright 2011-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test for the `generate-extra-overrides` script."""

__metaclass__ = type

from functools import partial
import logging
from optparse import OptionValueError
import os
import tempfile

from germinate import (
    archive,
    germinator,
    seeds,
    )
import transaction

from lp.archivepublisher.publishing import (
    get_packages_path,
    get_sources_path,
    )
from lp.archivepublisher.scripts.generate_extra_overrides import (
    AtomicFile,
    GenerateExtraOverrides,
    )
from lp.archivepublisher.utils import RepositoryIndexFile
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.interfaces.series import SeriesStatus
from lp.services.log.logger import DevNullLogger
from lp.services.osutils import (
    ensure_directory_exists,
    open_for_writing,
    write_file,
    )
from lp.services.scripts.base import LaunchpadScriptFailure
from lp.services.scripts.tests import run_script
from lp.services.utils import file_exists
from lp.soyuz.enums import PackagePublishingStatus
from lp.testing import TestCaseWithFactory
from lp.testing.fakemethod import FakeMethod
from lp.testing.faketransaction import FakeTransaction
from lp.testing.layers import (
    LaunchpadZopelessLayer,
    ZopelessDatabaseLayer,
    )


def file_contents(path):
    """Return the contents of the file at path."""
    with open(path) as handle:
        return handle.read()


class TestAtomicFile(TestCaseWithFactory):
    """Tests for the AtomicFile helper class."""

    layer = ZopelessDatabaseLayer

    def test_atomic_file_creates_file(self):
        # AtomicFile creates the named file with the requested contents.
        self.useTempDir()
        filename = self.factory.getUniqueString()
        text = self.factory.getUniqueString()
        with AtomicFile(filename) as test:
            test.write(text)
        self.assertEqual(text, file_contents(filename))

    def test_atomic_file_removes_dot_new(self):
        # AtomicFile does not leave .new files lying around.
        self.useTempDir()
        filename = self.factory.getUniqueString()
        with AtomicFile(filename):
            pass
        self.assertFalse(file_exists("%s.new" % filename))


class TestGenerateExtraOverrides(TestCaseWithFactory):
    """Tests for the actual `GenerateExtraOverrides` script."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestGenerateExtraOverrides, self).setUp()
        self.seeddir = self.makeTemporaryDirectory()
        # XXX cjwatson 2011-12-06 bug=694140: Make sure germinate doesn't
        # lose its loggers between tests, due to Launchpad's messing with
        # global log state.
        archive._logger = logging.getLogger("germinate.archive")
        germinator._logger = logging.getLogger("germinate.germinator")
        seeds._logger = logging.getLogger("germinate.seeds")

    def assertFilesEqual(self, expected_path, observed_path):
        self.assertEqual(
            file_contents(expected_path), file_contents(observed_path))

    def makeDistro(self):
        """Create a distribution for testing.

        The distribution will have a root directory set up, which will
        be cleaned up after the test.  It will have an attached archive.
        """
        return self.factory.makeDistribution(
            publish_root_dir=unicode(self.makeTemporaryDirectory()))

    def makeScript(self, distribution, run_setup=True, extra_args=None):
        """Create a script for testing."""
        test_args = []
        if distribution is not None:
            test_args.extend(["-d", distribution.name])
        if extra_args is not None:
            test_args.extend(extra_args)
        script = GenerateExtraOverrides(test_args=test_args)
        script.logger = DevNullLogger()
        script.txn = FakeTransaction()
        if distribution is not None and run_setup:
            script.setUp()
        else:
            script.distribution = distribution
        return script

    def setUpDistroAndScript(self, series_statuses=["DEVELOPMENT"], **kwargs):
        """Helper wrapping distro and script setup."""
        self.distro = self.makeDistro()
        self.distroseries = [
            self.factory.makeDistroSeries(
                distribution=self.distro, status=SeriesStatus.items[status])
            for status in series_statuses]
        self.script = self.makeScript(self.distro, **kwargs)

    def setUpComponent(self, component=None):
        """Create a component and attach it to all distroseries."""
        if component is None:
            component = self.factory.makeComponent()
        for distroseries in self.distroseries:
            self.factory.makeComponentSelection(
                distroseries=distroseries, component=component)
        return component

    def makePackage(self, component, dases, **kwargs):
        """Create a published source and binary package for testing."""
        package = self.factory.makeDistributionSourcePackage(
            distribution=dases[0].distroseries.distribution)
        spph = self.factory.makeSourcePackagePublishingHistory(
            distroseries=dases[0].distroseries,
            pocket=PackagePublishingPocket.RELEASE,
            status=PackagePublishingStatus.PUBLISHED,
            sourcepackagename=package.name, component=component)
        for das in dases:
            build = self.factory.makeBinaryPackageBuild(
                source_package_release=spph.sourcepackagerelease,
                distroarchseries=das, processor=das.processor)
            bpr = self.factory.makeBinaryPackageRelease(
                binarypackagename=package.name, build=build,
                component=component, architecturespecific=True,
                **kwargs)
            lfa = self.factory.makeLibraryFileAlias(
                filename="%s.deb" % package.name)
            transaction.commit()
            bpr.addFile(lfa)
            self.factory.makeBinaryPackagePublishingHistory(
                binarypackagerelease=bpr, distroarchseries=das,
                pocket=PackagePublishingPocket.RELEASE,
                status=PackagePublishingStatus.PUBLISHED)
        return package

    def makeIndexFiles(self, script, distroseries):
        """Create a limited subset of index files for testing."""
        ensure_directory_exists(script.config.temproot)

        for component in distroseries.components:
            source_index = RepositoryIndexFile(
                get_sources_path(script.config, distroseries.name, component),
                script.config.temproot)
            for spp in distroseries.getSourcePackagePublishing(
                    PackagePublishingPocket.RELEASE, component,
                    distroseries.main_archive):
                stanza = spp.getIndexStanza().encode("utf-8") + "\n\n"
                source_index.write(stanza)
            source_index.close()

            for arch in distroseries.architectures:
                package_index = RepositoryIndexFile(
                    get_packages_path(
                        script.config, distroseries.name, component, arch),
                    script.config.temproot)
                for bpp in distroseries.getBinaryPackagePublishing(
                        arch.architecturetag, PackagePublishingPocket.RELEASE,
                        component, distroseries.main_archive):
                    stanza = bpp.getIndexStanza().encode("utf-8") + "\n\n"
                    package_index.write(stanza)
                package_index.close()

    def composeSeedPath(self, flavour, series_name, seed_name):
        return os.path.join(
            self.seeddir, "%s.%s" % (flavour, series_name), seed_name)

    def makeSeedStructure(self, flavour, series_name, seed_names,
                          seed_inherit={}):
        """Create a simple seed structure file."""
        structure_path = self.composeSeedPath(
            flavour, series_name, "STRUCTURE")
        with open_for_writing(structure_path, "w") as structure:
            for seed_name in seed_names:
                inherit = seed_inherit.get(seed_name, [])
                line = "%s: %s" % (seed_name, " ".join(inherit))
                print >>structure, line.strip()

    def makeSeed(self, flavour, series_name, seed_name, entries,
                 headers=None):
        """Create a simple seed file."""
        seed_path = self.composeSeedPath(flavour, series_name, seed_name)
        with open_for_writing(seed_path, "w") as seed:
            if headers is not None:
                for header in headers:
                    print >>seed, header
                print >>seed
            for entry in entries:
                print >>seed, " * %s" % entry

    def getTaskNameFromSeed(self, script, flavour, series_name, seed,
                            primary_flavour):
        """Use script to parse a seed and return its task name."""
        seed_path = self.composeSeedPath(flavour, series_name, seed)
        with open(seed_path) as seed_text:
            task_headers = script.parseTaskHeaders(seed_text)
        return script.getTaskName(
            task_headers, flavour, seed, primary_flavour)

    def getTaskSeedsFromSeed(self, script, flavour, series_name, seed):
        """Use script to parse a seed and return its task seed list."""
        seed_path = self.composeSeedPath(flavour, series_name, seed)
        with open(seed_path) as seed_text:
            task_headers = script.parseTaskHeaders(seed_text)
        return script.getTaskSeeds(task_headers, seed)

    def test_name_is_consistent(self):
        # Script instances for the same distro get the same name.
        distro = self.factory.makeDistribution()
        self.assertEqual(
            GenerateExtraOverrides(test_args=["-d", distro.name]).name,
            GenerateExtraOverrides(test_args=["-d", distro.name]).name)

    def test_name_is_unique_for_each_distro(self):
        # Script instances for different distros get different names.
        self.assertNotEqual(
            GenerateExtraOverrides(
                test_args=["-d", self.factory.makeDistribution().name]).name,
            GenerateExtraOverrides(
                test_args=["-d", self.factory.makeDistribution().name]).name)

    def test_requires_distro(self):
        # The --distribution or -d argument is mandatory.
        script = self.makeScript(None)
        self.assertRaises(OptionValueError, script.processOptions)

    def test_requires_real_distro(self):
        # An incorrect distribution name is flagged as an invalid option
        # value.
        script = self.makeScript(
            None, extra_args=["-d", self.factory.getUniqueString()])
        self.assertRaises(OptionValueError, script.processOptions)

    def test_looks_up_distro(self):
        # The script looks up and keeps the distribution named on the
        # command line.
        self.setUpDistroAndScript()
        self.assertEqual(self.distro, self.script.distribution)

    def test_prefers_development_distro_series(self):
        # The script prefers a DEVELOPMENT series for the named
        # distribution over CURRENT and SUPPORTED series.
        self.setUpDistroAndScript(["SUPPORTED", "CURRENT", "DEVELOPMENT"])
        self.assertEqual([self.distroseries[2]], self.script.series)

    def test_permits_frozen_distro_series(self):
        # If there is no DEVELOPMENT series, a FROZEN one will do.
        self.setUpDistroAndScript(["SUPPORTED", "CURRENT", "FROZEN"])
        self.assertEqual([self.distroseries[2]], self.script.series)

    def test_requires_development_frozen_distro_series(self):
        # If there is no DEVELOPMENT or FROZEN series, the script fails.
        self.setUpDistroAndScript(["SUPPORTED", "CURRENT"], run_setup=False)
        self.assertRaises(LaunchpadScriptFailure, self.script.processOptions)

    def test_multiple_development_frozen_distro_series(self):
        # If there are multiple DEVELOPMENT or FROZEN series, they are all
        # used.
        self.setUpDistroAndScript(
            ["DEVELOPMENT", "DEVELOPMENT", "FROZEN", "FROZEN"])
        self.assertContentEqual(self.distroseries, self.script.series)

    def test_components_exclude_partner(self):
        # If a 'partner' component exists, it is excluded.
        self.setUpDistroAndScript()
        self.setUpComponent(component="main")
        self.setUpComponent(component="partner")
        self.assertEqual(1, len(self.script.series))
        self.assertEqual(
            ["main"], self.script.getComponents(self.script.series[0]))

    def test_compose_output_path_in_germinateroot(self):
        # Output files are written to the correct locations under
        # germinateroot.
        self.setUpDistroAndScript()
        flavour = self.factory.getUniqueString()
        arch = self.factory.getUniqueString()
        base = self.factory.getUniqueString()
        output = self.script.composeOutputPath(
            flavour, self.distroseries[0].name, arch, base)
        self.assertEqual(
            "%s/%s_%s_%s_%s" % (
                self.script.config.germinateroot, base, flavour,
                self.distroseries[0].name, arch),
            output)

    def test_make_seed_structures_missing_seeds(self):
        # makeSeedStructures ignores missing seeds.
        self.setUpDistroAndScript()
        series_name = self.distroseries[0].name
        flavour = self.factory.getUniqueString()

        structures = self.script.makeSeedStructures(
            series_name, [flavour], seed_bases=["file://%s" % self.seeddir])
        self.assertEqual({}, structures)

    def test_make_seed_structures_empty_seed_structure(self):
        # makeSeedStructures ignores an empty seed structure.
        self.setUpDistroAndScript()
        series_name = self.distroseries[0].name
        flavour = self.factory.getUniqueString()
        self.makeSeedStructure(flavour, series_name, [])

        structures = self.script.makeSeedStructures(
            series_name, [flavour], seed_bases=["file://%s" % self.seeddir])
        self.assertEqual({}, structures)

    def test_make_seed_structures_valid_seeds(self):
        # makeSeedStructures reads valid seeds successfully.
        self.setUpDistroAndScript()
        series_name = self.distroseries[0].name
        flavour = self.factory.getUniqueString()
        seed = self.factory.getUniqueString()
        self.makeSeedStructure(flavour, series_name, [seed])
        self.makeSeed(flavour, series_name, seed, [])

        structures = self.script.makeSeedStructures(
            series_name, [flavour], seed_bases=["file://%s" % self.seeddir])
        self.assertIn(flavour, structures)

    def fetchGerminatedOverrides(self, script, distroseries, arch, flavours):
        """Helper to call script.germinateArch and return overrides."""
        structures = script.makeSeedStructures(
            distroseries.name, flavours,
            seed_bases=["file://%s" % self.seeddir])

        override_fd, override_path = tempfile.mkstemp()
        with os.fdopen(override_fd, "w") as override_file:
            script.germinateArch(
                override_file, distroseries.name,
                script.getComponents(distroseries), arch, flavours,
                structures)
        return file_contents(override_path).splitlines()

    def test_germinate_output(self):
        # A single call to germinateArch produces output for all flavours on
        # one architecture.
        self.setUpDistroAndScript()
        series_name = self.distroseries[0].name
        component = self.setUpComponent()
        das = self.factory.makeDistroArchSeries(
            distroseries=self.distroseries[0])
        arch = das.architecturetag
        one = self.makePackage(component, [das])
        two = self.makePackage(component, [das])
        self.makeIndexFiles(self.script, self.distroseries[0])

        flavour_one = self.factory.getUniqueString()
        flavour_two = self.factory.getUniqueString()
        seed = self.factory.getUniqueString()
        self.makeSeedStructure(flavour_one, series_name, [seed])
        self.makeSeed(flavour_one, series_name, seed, [one.name])
        self.makeSeedStructure(flavour_two, series_name, [seed])
        self.makeSeed(flavour_two, series_name, seed, [two.name])

        overrides = self.fetchGerminatedOverrides(
            self.script, self.distroseries[0], arch,
            [flavour_one, flavour_two])
        self.assertEqual([], overrides)

        seed_dir_one = os.path.join(
            self.seeddir, "%s.%s" % (flavour_one, series_name))
        self.assertFilesEqual(
            os.path.join(seed_dir_one, "STRUCTURE"),
            self.script.composeOutputPath(
                flavour_one, series_name, arch, "structure"))
        self.assertTrue(file_exists(self.script.composeOutputPath(
            flavour_one, series_name, arch, "all")))
        self.assertTrue(file_exists(self.script.composeOutputPath(
            flavour_one, series_name, arch, "all.sources")))
        self.assertTrue(file_exists(self.script.composeOutputPath(
            flavour_one, series_name, arch, seed)))

        seed_dir_two = os.path.join(
            self.seeddir, "%s.%s" % (flavour_two, series_name))
        self.assertFilesEqual(
            os.path.join(seed_dir_two, "STRUCTURE"),
            self.script.composeOutputPath(
                flavour_two, series_name, arch, "structure"))
        self.assertTrue(file_exists(self.script.composeOutputPath(
            flavour_two, series_name, arch, "all")))
        self.assertTrue(file_exists(self.script.composeOutputPath(
            flavour_two, series_name, arch, "all.sources")))
        self.assertTrue(file_exists(self.script.composeOutputPath(
            flavour_two, series_name, arch, seed)))

    def test_germinate_output_task(self):
        # germinateArch produces Task extra overrides.
        self.setUpDistroAndScript()
        series_name = self.distroseries[0].name
        component = self.setUpComponent()
        das = self.factory.makeDistroArchSeries(
            distroseries=self.distroseries[0])
        arch = das.architecturetag
        one = self.makePackage(component, [das])
        two = self.makePackage(component, [das], depends=one.name)
        three = self.makePackage(component, [das])
        self.makePackage(component, [das])
        self.makeIndexFiles(self.script, self.distroseries[0])

        flavour = self.factory.getUniqueString()
        seed_one = self.factory.getUniqueString()
        seed_two = self.factory.getUniqueString()
        self.makeSeedStructure(flavour, series_name, [seed_one, seed_two])
        self.makeSeed(
            flavour, series_name, seed_one, [two.name],
            headers=["Task-Description: one"])
        self.makeSeed(
            flavour, series_name, seed_two, [three.name],
            headers=["Task-Description: two"])

        overrides = self.fetchGerminatedOverrides(
            self.script, self.distroseries[0], arch, [flavour])
        expected_overrides = [
            "%s/%s  Task  %s" % (one.name, arch, seed_one),
            "%s/%s  Task  %s" % (two.name, arch, seed_one),
            "%s/%s  Task  %s" % (three.name, arch, seed_two),
            ]
        self.assertContentEqual(expected_overrides, overrides)

    def test_task_name(self):
        # The Task-Name field is honoured.
        series_name = self.factory.getUniqueString()
        package = self.factory.getUniqueString()
        script = self.makeScript(None)

        flavour = self.factory.getUniqueString()
        seed = self.factory.getUniqueString()
        task = self.factory.getUniqueString()
        self.makeSeed(
            flavour, series_name, seed, [package],
            headers=["Task-Name: %s" % task])

        observed_task = self.getTaskNameFromSeed(
            script, flavour, series_name, seed, True)
        self.assertEqual(task, observed_task)

    def test_task_per_derivative(self):
        # The Task-Per-Derivative field is honoured.
        series_name = self.factory.getUniqueString()
        package = self.factory.getUniqueString()
        script = self.makeScript(None)

        flavour_one = self.factory.getUniqueString()
        flavour_two = self.factory.getUniqueString()
        seed_one = self.factory.getUniqueString()
        seed_two = self.factory.getUniqueString()
        self.makeSeed(
            flavour_one, series_name, seed_one, [package],
            headers=["Task-Description: one"])
        self.makeSeed(
            flavour_one, series_name, seed_two, [package],
            headers=["Task-Per-Derivative: 1"])
        self.makeSeed(
            flavour_two, series_name, seed_one, [package],
            headers=["Task-Description: one"])
        self.makeSeed(
            flavour_two, series_name, seed_two, [package],
            headers=["Task-Per-Derivative: 1"])

        observed_task_one_one = self.getTaskNameFromSeed(
            script, flavour_one, series_name, seed_one, True)
        observed_task_one_two = self.getTaskNameFromSeed(
            script, flavour_one, series_name, seed_two, True)
        observed_task_two_one = self.getTaskNameFromSeed(
            script, flavour_two, series_name, seed_one, False)
        observed_task_two_two = self.getTaskNameFromSeed(
            script, flavour_two, series_name, seed_two, False)

        # seed_one is not per-derivative, so it is honoured only for
        # flavour_one and has a global name.
        self.assertEqual(seed_one, observed_task_one_one)
        self.assertIsNone(observed_task_two_one)

        # seed_two is per-derivative, so it is honoured for both flavours
        # and has the flavour name prefixed.
        self.assertEqual(
            "%s-%s" % (flavour_one, seed_two), observed_task_one_two)
        self.assertEqual(
            "%s-%s" % (flavour_two, seed_two), observed_task_two_two)

    def test_task_seeds(self):
        # The Task-Seeds field is honoured.
        series_name = self.factory.getUniqueString()
        one = self.getUniqueString()
        two = self.getUniqueString()
        script = self.makeScript(None)

        flavour = self.factory.getUniqueString()
        seed_one = self.factory.getUniqueString()
        seed_two = self.factory.getUniqueString()
        self.makeSeed(flavour, series_name, seed_one, [one])
        self.makeSeed(
            flavour, series_name, seed_two, [two],
            headers=["Task-Seeds: %s" % seed_one])

        task_seeds = self.getTaskSeedsFromSeed(
            script, flavour, series_name, seed_two)
        self.assertContentEqual([seed_one, seed_two], task_seeds)

    def test_germinate_output_build_essential(self):
        # germinateArch produces Build-Essential extra overrides.
        self.setUpDistroAndScript()
        series_name = self.distroseries[0].name
        component = self.setUpComponent()
        das = self.factory.makeDistroArchSeries(
            distroseries=self.distroseries[0])
        arch = das.architecturetag
        package = self.makePackage(component, [das])
        self.makeIndexFiles(self.script, self.distroseries[0])

        flavour = self.factory.getUniqueString()
        seed = "build-essential"
        self.makeSeedStructure(flavour, series_name, [seed])
        self.makeSeed(flavour, series_name, seed, [package.name])

        overrides = self.fetchGerminatedOverrides(
            self.script, self.distroseries[0], arch, [flavour])
        self.assertContentEqual(
            ["%s/%s  Build-Essential  yes" % (package.name, arch)], overrides)

    def test_removes_only_stale_files(self):
        # removeStaleOutputs removes only stale germinate output files.
        self.setUpDistroAndScript()
        series_name = self.distroseries[0].name
        seed_old_file = "old_flavour_%s_i386" % series_name
        seed_new_file = "new_flavour_%s_i386" % series_name
        other_file = "other-file"
        output = partial(os.path.join, self.script.config.germinateroot)
        for base in (seed_old_file, seed_new_file, other_file):
            write_file(output(base), "")
        self.script.removeStaleOutputs(series_name, set([seed_new_file]))
        self.assertFalse(os.path.exists(output(seed_old_file)))
        self.assertTrue(os.path.exists(output(seed_new_file)))
        self.assertTrue(os.path.exists(output(other_file)))

    def test_process_missing_seeds(self):
        # The script ignores series with no seed structures.
        flavour = self.factory.getUniqueString()
        self.setUpDistroAndScript(
            ["DEVELOPMENT", "DEVELOPMENT"], extra_args=[flavour])
        self.setUpComponent()
        self.factory.makeDistroArchSeries(distroseries=self.distroseries[0])
        self.factory.makeDistroArchSeries(distroseries=self.distroseries[1])
        self.makeIndexFiles(self.script, self.distroseries[1])
        seed = self.factory.getUniqueString()
        self.makeSeedStructure(flavour, self.distroseries[1].name, [seed])
        self.makeSeed(flavour, self.distroseries[1].name, seed, [])

        self.script.process(seed_bases=["file://%s" % self.seeddir])
        self.assertFalse(os.path.exists(os.path.join(
            self.script.config.miscroot,
            "more-extra.override.%s.main" % self.distroseries[0].name)))
        self.assertTrue(os.path.exists(os.path.join(
            self.script.config.miscroot,
            "more-extra.override.%s.main" % self.distroseries[1].name)))

    def test_process_removes_only_stale_files(self):
        # The script removes only stale germinate output files.
        flavour = self.factory.getUniqueString()
        self.setUpDistroAndScript(extra_args=[flavour])
        series_name = self.distroseries[0].name
        self.setUpComponent()
        das = self.factory.makeDistroArchSeries(
            distroseries=self.distroseries[0])
        arch = das.architecturetag
        self.makeIndexFiles(self.script, self.distroseries[0])

        seed_old = self.factory.getUniqueString()
        seed_new = self.factory.getUniqueString()
        self.makeSeedStructure(flavour, series_name, [seed_old])
        self.makeSeed(flavour, series_name, seed_old, [])
        self.script.process(seed_bases=["file://%s" % self.seeddir])
        output = partial(
            self.script.composeOutputPath, flavour, series_name, arch)
        self.assertTrue(os.path.exists(output(seed_old)))
        self.makeSeedStructure(flavour, series_name, [seed_new])
        self.makeSeed(flavour, series_name, seed_new, [])
        self.script.process(seed_bases=["file://%s" % self.seeddir])
        self.assertTrue(os.path.exists(os.path.join(self.script.log_file)))
        self.assertTrue(os.path.exists(output("structure")))
        self.assertTrue(os.path.exists(output("all")))
        self.assertTrue(os.path.exists(output("all.sources")))
        self.assertTrue(os.path.exists(output(seed_new)))
        self.assertFalse(os.path.exists(output(seed_old)))

    def test_process_skips_disabled_distroarchseries(self):
        # The script does not generate overrides for disabled DistroArchSeries.
        flavour = self.factory.getUniqueString()
        self.setUpDistroAndScript(extra_args=[flavour])
        das = self.factory.makeDistroArchSeries(
            distroseries=self.distroseries[0])
        self.factory.makeDistroArchSeries(
            distroseries=self.distroseries[0], enabled=False)
        self.script.generateExtraOverrides = FakeMethod()
        self.script.process()
        self.assertEqual(1, self.script.generateExtraOverrides.call_count)
        self.assertEqual(
            [das.architecturetag],
            self.script.generateExtraOverrides.calls[0][0][2])

    def test_main(self):
        # If run end-to-end, the script generates override files containing
        # output for all architectures, and sends germinate's log output to
        # a file.
        flavour = self.factory.getUniqueString()
        self.setUpDistroAndScript(extra_args=[flavour])
        series_name = self.distroseries[0].name
        component = self.setUpComponent()
        das_one = self.factory.makeDistroArchSeries(
            distroseries=self.distroseries[0])
        das_two = self.factory.makeDistroArchSeries(
            distroseries=self.distroseries[0])
        package = self.makePackage(component, [das_one, das_two])
        self.makeIndexFiles(self.script, self.distroseries[0])

        seed = self.factory.getUniqueString()
        self.makeSeedStructure(flavour, series_name, [seed])
        self.makeSeed(
            flavour, series_name, seed, [package.name],
            headers=["Task-Description: task"])

        self.script.process(seed_bases=["file://%s" % self.seeddir])
        override_path = os.path.join(
            self.script.config.miscroot,
            "more-extra.override.%s.main" % series_name)
        expected_overrides = [
            "%s/%s  Task  %s" % (package.name, das_one.architecturetag, seed),
            "%s/%s  Task  %s" % (package.name, das_two.architecturetag, seed),
            ]
        self.assertContentEqual(
            expected_overrides, file_contents(override_path).splitlines())

        log_file = os.path.join(
            self.script.config.germinateroot, "germinate.output")
        self.assertIn("Downloading file://", file_contents(log_file))

    def test_run_script(self):
        # The script will run stand-alone.
        distro = self.makeDistro()
        self.factory.makeDistroSeries(distro)
        transaction.commit()
        retval, out, err = run_script(
            "cronscripts/generate-extra-overrides.py",
            ["-d", distro.name, "-q"])
        self.assertEqual(0, retval)
