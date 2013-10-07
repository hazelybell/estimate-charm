# Copyright 2011-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test for the `generate-contents-files` script."""

__metaclass__ = type

from optparse import OptionValueError
import os

from testtools.matchers import StartsWith

from lp.archivepublisher.scripts.generate_contents_files import (
    differ_in_content,
    execute,
    GenerateContentsFiles,
    )
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.services.log.logger import DevNullLogger
from lp.services.osutils import write_file
from lp.services.scripts.base import LaunchpadScriptFailure
from lp.services.scripts.tests import run_script
from lp.services.utils import file_exists
from lp.testing import TestCaseWithFactory
from lp.testing.faketransaction import FakeTransaction
from lp.testing.layers import (
    LaunchpadZopelessLayer,
    ZopelessDatabaseLayer,
    )


def fake_overrides(script, distroseries):
    """Fake overrides files so `script` can run `apt-ftparchive`."""
    components = ['main', 'restricted', 'universe', 'multiverse']
    architectures = script.getArchs(distroseries.name)
    suffixes = components + ['extra.' + component for component in components]
    for suffix in suffixes:
        write_file(os.path.join(
            script.config.overrideroot,
            "override.%s.%s" % (distroseries.name, suffix)), "")

    for component in components:
        write_file(os.path.join(
            script.config.overrideroot,
            "%s_%s_source" % (distroseries.name, component)), "")
        for arch in architectures:
            write_file(os.path.join(
                script.config.overrideroot,
                "%s_%s_binary-%s" % (distroseries.name, component, arch)), "")


class TestHelpers(TestCaseWithFactory):
    """Tests for the module's helper functions."""

    layer = ZopelessDatabaseLayer

    def test_differ_in_content_returns_true_if_one_file_does_not_exist(self):
        # A nonexistent file differs from an existing one.
        self.useTempDir()
        write_file('one', self.factory.getUniqueString())
        self.assertTrue(differ_in_content('one', 'other'))

    def test_differ_in_content_returns_false_for_identical_files(self):
        # Identical files do not differ.
        self.useTempDir()
        text = self.factory.getUniqueString()
        write_file('one', text)
        write_file('other', text)
        self.assertFalse(differ_in_content('one', 'other'))

    def test_differ_in_content_returns_true_for_differing_files(self):
        # Files with different contents differ.
        self.useTempDir()
        write_file('one', self.factory.getUniqueString())
        write_file('other', self.factory.getUniqueString())
        self.assertTrue(differ_in_content('one', 'other'))

    def test_differ_in_content_returns_false_if_neither_file_exists(self):
        # Nonexistent files do not differ.
        self.useTempDir()
        self.assertFalse(differ_in_content('one', 'other'))

    def test_execute_raises_if_command_fails(self):
        # execute checks its command's return value.  If it's nonzero
        # (as with /bin/false), it raises a LaunchpadScriptFailure.
        logger = DevNullLogger()
        self.assertRaises(
            LaunchpadScriptFailure, execute, logger, "/bin/false")

    def test_execute_executes_command(self):
        # execute really does execute its command.  If we tell it to
        # "touch" a new file, that file really gets created.
        self.useTempDir()
        logger = DevNullLogger()
        filename = self.factory.getUniqueString()
        execute(logger, "touch", [filename])
        self.assertTrue(file_exists(filename))


class TestGenerateContentsFiles(TestCaseWithFactory):
    """Tests for the actual `GenerateContentsFiles` script."""

    layer = LaunchpadZopelessLayer

    def makeDistro(self):
        """Create a distribution for testing.

        The distribution will have a root directory set up, which will
        be cleaned up after the test.
        """
        return self.factory.makeDistribution(
            publish_root_dir=unicode(self.makeTemporaryDirectory()))

    def makeScript(self, distribution=None, run_setup=True):
        """Create a script for testing."""
        if distribution is None:
            distribution = self.makeDistro()
        script = GenerateContentsFiles(test_args=['-d', distribution.name])
        script.logger = DevNullLogger()
        script.txn = FakeTransaction()
        if run_setup:
            script.setUp()
        else:
            script.distribution = distribution
        return script

    def writeMarkerFile(self, file_path):
        """Create a marker file at location `file_path`.

        An arbitrary string is written to the file, and flushed to the
        filesystem.  Any surrounding directories are created as needed.

        :param file_path: Full path to a file: optional directory prefix
            followed by required file name.
        :return: The arbitrary string that is also in the file.
        """
        marker_contents = self.factory.getUniqueString()
        write_file(file_path, marker_contents)
        return marker_contents

    def test_name_is_consistent(self):
        # Script instances for the same distro get the same name.
        distro = self.factory.makeDistribution()
        self.assertEqual(
            GenerateContentsFiles(test_args=['-d', distro.name]).name,
            GenerateContentsFiles(test_args=['-d', distro.name]).name)

    def test_name_is_unique_for_each_distro(self):
        # Script instances for different distros get different names.
        self.assertNotEqual(
            GenerateContentsFiles(
                test_args=['-d', self.factory.makeDistribution().name]).name,
            GenerateContentsFiles(
                test_args=['-d', self.factory.makeDistribution().name]).name)

    def test_requires_distro(self):
        # The --distribution or -d argument is mandatory.
        script = GenerateContentsFiles(test_args=[])
        self.assertRaises(OptionValueError, script.processOptions)

    def test_requires_real_distro(self):
        # An incorrect distribution name is flagged as an invalid option
        # value.
        script = GenerateContentsFiles(
            test_args=['-d', self.factory.getUniqueString()])
        self.assertRaises(OptionValueError, script.processOptions)

    def test_looks_up_distro(self):
        # The script looks up and keeps the distribution named on the
        # command line.
        distro = self.makeDistro()
        script = self.makeScript(distro)
        self.assertEqual(distro, script.distribution)

    def test_getArchs(self):
        # getArchs returns a list of enabled architectures in the distroseries.
        distro = self.makeDistro()
        distroseries = self.factory.makeDistroSeries(distro)
        das = self.factory.makeDistroArchSeries(distroseries=distroseries)
        self.factory.makeDistroArchSeries(
            distroseries=distroseries, enabled=False)
        script = self.makeScript(das.distroseries.distribution)
        self.assertEqual(
            [das.architecturetag], script.getArchs(distroseries.name))

    def test_getSupportedSeries(self):
        # getSupportedSeries returns the supported distroseries in the
        # distribution.
        script = self.makeScript()
        distroseries = self.factory.makeDistroSeries(
            distribution=script.distribution)
        self.assertIn(distroseries, script.getSupportedSeries())

    def test_getSuites(self):
        # getSuites returns the full names (distroseries-pocket) of the
        # pockets that have packages to publish.
        distro = self.makeDistro()
        distroseries = self.factory.makeDistroSeries(distribution=distro)
        package = self.factory.makeSuiteSourcePackage(distroseries)
        script = self.makeScript(distro)
        os.makedirs(os.path.join(script.config.distsroot, package.suite))
        self.assertEqual([package.suite], list(script.getSuites()))

    def test_getSuites_includes_release_pocket(self):
        # getSuites also includes the release pocket, which is named
        # after the distroseries without a suffix.
        distro = self.makeDistro()
        distroseries = self.factory.makeDistroSeries(distribution=distro)
        package = self.factory.makeSuiteSourcePackage(
            distroseries, pocket=PackagePublishingPocket.RELEASE)
        script = self.makeScript(distro)
        os.makedirs(os.path.join(script.config.distsroot, package.suite))
        self.assertEqual([package.suite], list(script.getSuites()))

    def test_writeAptContentsConf_writes_header(self):
        # writeAptContentsConf writes apt-contents.conf.  At a minimum
        # this will include a header based on apt_conf_header.template,
        # with the right distribution name interpolated.
        distro = self.makeDistro()
        script = self.makeScript(distro)
        script.writeAptContentsConf([])
        apt_contents_conf = file(
            "%s/%s-misc/apt-contents.conf"
            % (script.content_archive, distro.name)).read()
        self.assertIn('\nDefault\n{', apt_contents_conf)
        self.assertIn(distro.name, apt_contents_conf)

    def test_writeAptContentsConf_writes_suite_sections(self):
        # writeAptContentsConf adds sections based on
        # apt_conf_dist.template for every suite, with certain
        # parameters interpolated.
        distro = self.makeDistro()
        distroseries = self.factory.makeDistroSeries(distro)
        das = self.factory.makeDistroArchSeries(distroseries=distroseries)
        script = self.makeScript(distro)
        content_archive = script.content_archive
        script.writeAptContentsConf([distroseries.name])
        apt_contents_conf = file(
            "%s/%s-misc/apt-contents.conf"
            % (script.content_archive, distro.name)).read()
        self.assertIn(
            'tree "dists/%s"\n' % distroseries.name, apt_contents_conf)
        overrides_path = os.path.join(
            content_archive, distro.name + "-overrides")
        self.assertIn('FileList "%s' % overrides_path, apt_contents_conf)
        self.assertIn(
            'Architectures "%s source";' % das.architecturetag,
            apt_contents_conf)

    def test_writeContentsTop(self):
        # writeContentsTop writes a Contents.top file based on a
        # standard template, with the distribution's title interpolated.
        distro = self.makeDistro()
        script = self.makeScript(distro)
        content_archive = script.content_archive
        script.writeContentsTop(distro.name, distro.title)

        contents_top = file(
            "%s/%s-misc/Contents.top" % (content_archive, distro.name)).read()

        self.assertIn("This file maps", contents_top)
        self.assertIn(distro.title, contents_top)

    def test_setUp_places_content_archive_in_distroroot(self):
        # The contents files are kept in subdirectories of distroroot.
        script = self.makeScript()
        self.assertThat(
            script.content_archive, StartsWith(script.config.distroroot))

    def test_main(self):
        # If run end-to-end, the script generates Contents.gz files.
        distro = self.makeDistro()
        distroseries = self.factory.makeDistroSeries(distribution=distro)
        processor = self.factory.makeProcessor()
        das = self.factory.makeDistroArchSeries(
            distroseries=distroseries, processor=processor)
        package = self.factory.makeSuiteSourcePackage(distroseries)
        self.factory.makeSourcePackagePublishingHistory(
            distroseries=distroseries, pocket=package.pocket)
        self.factory.makeBinaryPackageBuild(
            distroarchseries=das, pocket=package.pocket,
            processor=processor)
        suite = package.suite
        script = self.makeScript(distro)
        os.makedirs(os.path.join(script.config.distsroot, package.suite))
        self.assertNotEqual([], list(script.getSuites()))
        fake_overrides(script, distroseries)
        script.process()
        self.assertTrue(file_exists(os.path.join(
            script.config.distsroot, suite,
            "Contents-%s.gz" % das.architecturetag)))

    def test_run_script(self):
        # The script will run stand-alone.
        self.layer.force_dirty_database()
        retval, out, err = run_script(
            'cronscripts/generate-contents-files.py', ['-d', 'ubuntu', '-q'])
        self.assertEqual(0, retval)
