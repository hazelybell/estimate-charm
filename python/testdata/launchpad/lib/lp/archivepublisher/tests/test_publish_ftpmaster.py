# Copyright 2011-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test publish-ftpmaster cron script."""

__metaclass__ = type

import logging
import os
from textwrap import dedent

from apt_pkg import TagFile
from testtools.matchers import (
    MatchesStructure,
    StartsWith,
    )
from zope.component import getUtility

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.archivepublisher.config import getPubConfig
from lp.archivepublisher.interfaces.publisherconfig import IPublisherConfigSet
from lp.archivepublisher.scripts.publish_ftpmaster import (
    compose_env_string,
    compose_shell_boolean,
    find_run_parts_dir,
    get_working_dists,
    PublishFTPMaster,
    shell_quote,
    )
from lp.registry.interfaces.pocket import (
    PackagePublishingPocket,
    pocketsuffix,
    )
from lp.registry.interfaces.series import SeriesStatus
from lp.services.config import config
from lp.services.database.interfaces import IMasterStore
from lp.services.log.logger import (
    BufferLogger,
    DevNullLogger,
    )
from lp.services.scripts.base import LaunchpadScriptFailure
from lp.services.utils import file_exists
from lp.soyuz.enums import (
    ArchivePurpose,
    PackagePublishingStatus,
    PackageUploadCustomFormat,
    )
from lp.soyuz.tests.test_publishing import SoyuzTestPublisher
from lp.testing import (
    run_script,
    TestCase,
    TestCaseWithFactory,
    )
from lp.testing.fakemethod import FakeMethod
from lp.testing.layers import (
    LaunchpadZopelessLayer,
    ZopelessDatabaseLayer,
    )


def path_exists(*path_components):
    """Does the given file or directory exist?"""
    return file_exists(os.path.join(*path_components))


def name_pph_suite(pph):
    """Return name of `pph`'s suite."""
    return pph.distroseries.name + pocketsuffix[pph.pocket]


def get_pub_config(distro):
    """Find the publishing config for `distro`."""
    return getUtility(IPublisherConfigSet).getByDistribution(distro)


def get_archive_root(pub_config):
    """Return the archive root for the given publishing config."""
    return os.path.join(pub_config.root_dir, pub_config.distribution.name)


def get_dists_root(pub_config):
    """Return the dists root directory for the given publishing config."""
    return os.path.join(get_archive_root(pub_config), "dists")


def get_distscopy_root(pub_config):
    """Return the "distscopy" root for the given publishing config."""
    return get_archive_root(pub_config) + "-distscopy"


def write_marker_file(path, contents):
    """Write a marker file for checking directory movements.

    :param path: A list of path components.
    :param contents: Text to write into the file.
    """
    marker = file(os.path.join(*path), "w")
    marker.write(contents)
    marker.flush()
    marker.close()


def read_marker_file(path):
    """Read the contents of a marker file.

    :param return: Contents of the marker file.
    """
    return file(os.path.join(*path)).read()


def get_a_suite(distroseries):
    """Return some suite name for `distroseries`."""
    # Don't pick Release; it's too easy.
    return distroseries.getSuite(PackagePublishingPocket.SECURITY)


def get_marker_files(script, distroseries):
    """Return filesystem paths for all indexes markers for `distroseries`."""
    suites = [
        distroseries.getSuite(pocket) for pocket in pocketsuffix.iterkeys()]
    distro = distroseries.distribution
    return [script.locateIndexesMarker(distro, suite) for suite in suites]


class HelpersMixin:
    """Helpers for the PublishFTPMaster tests."""

    def enableRunParts(self, parts_directory=None):
        """Set up for run-parts execution.

        :param parts_directory: Base location for the run-parts directories.
            If omitted, a temporary directory will be used.
        """
        if parts_directory is None:
            parts_directory = self.makeTemporaryDirectory()
            os.makedirs(os.path.join(
                parts_directory, "ubuntu", "publish-distro.d"))
            os.makedirs(os.path.join(parts_directory, "ubuntu", "finalize.d"))
        self.parts_directory = parts_directory

        config.push("run-parts", dedent("""\
            [archivepublisher]
            run_parts_location: %s
            """ % parts_directory))

        self.addCleanup(config.pop, "run-parts")

    def makeDistroWithPublishDirectory(self):
        """Create a `Distribution` for testing.

        The distribution will have a publishing directory set up, which
        will be cleaned up after the test.
        """
        return self.factory.makeDistribution(
            publish_root_dir=unicode(self.makeTemporaryDirectory()))

    def makeScript(self, distro=None, extra_args=[]):
        """Produce instance of the `PublishFTPMaster` script."""
        if distro is None:
            distro = self.makeDistroWithPublishDirectory()
        script = PublishFTPMaster(test_args=["-d", distro.name] + extra_args)
        script.txn = self.layer.txn
        script.logger = DevNullLogger()
        return script

    def setUpForScriptRun(self, distro):
        """Mock up config to run the script on `distro`."""
        pub_config = getUtility(IPublisherConfigSet).getByDistribution(distro)
        pub_config.root_dir = unicode(
            self.makeTemporaryDirectory())


class TestPublishFTPMasterHelpers(TestCase):

    def test_compose_env_string_iterates_env_dict(self):
        env = {
            "A": "1",
            "B": "2",
        }
        env_string = compose_env_string(env)
        self.assertIn(env_string, ["A=1 B=2", "B=2 A=1"])

    def test_compose_env_string_combines_env_dicts(self):
        env1 = {"A": "1"}
        env2 = {"B": "2"}
        env_string = compose_env_string(env1, env2)
        self.assertIn(env_string, ["A=1 B=2", "B=2 A=1"])

    def test_compose_env_string_overrides_repeated_keys(self):
        self.assertEqual("A=2", compose_env_string({"A": "1"}, {"A": "2"}))

    def test_shell_quote_quotes_string(self):
        self.assertEqual('"x"', shell_quote("x"))

    def test_shell_quote_escapes_string(self):
        self.assertEqual('"\\\\"', shell_quote("\\"))

    def test_shell_quote_does_not_escape_its_own_escapes(self):
        self.assertEqual('"\\$"', shell_quote("$"))

    def test_shell_quote_escapes_entire_string(self):
        self.assertEqual('"\\$\\$\\$"', shell_quote("$$$"))

    def test_compose_shell_boolean_shows_True_as_yes(self):
        self.assertEqual("yes", compose_shell_boolean(True))

    def test_compose_shell_boolean_shows_False_as_no(self):
        self.assertEqual("no", compose_shell_boolean(False))


class TestFindRunPartsDir(TestCaseWithFactory, HelpersMixin):
    layer = ZopelessDatabaseLayer

    def test_find_run_parts_dir_finds_runparts_directory(self):
        self.enableRunParts()
        ubuntu = getUtility(ILaunchpadCelebrities).ubuntu
        self.assertEqual(
            os.path.join(
                config.root, self.parts_directory, "ubuntu", "finalize.d"),
            find_run_parts_dir(ubuntu, "finalize.d"))

    def test_find_run_parts_dir_ignores_blank_config(self):
        self.enableRunParts("")
        ubuntu = getUtility(ILaunchpadCelebrities).ubuntu
        self.assertIs(None, find_run_parts_dir(ubuntu, "finalize.d"))

    def test_find_run_parts_dir_ignores_none_config(self):
        self.enableRunParts("none")
        ubuntu = getUtility(ILaunchpadCelebrities).ubuntu
        self.assertIs(None, find_run_parts_dir(ubuntu, "finalize.d"))

    def test_find_run_parts_dir_ignores_nonexistent_directory(self):
        self.enableRunParts()
        distro = self.factory.makeDistribution()
        self.assertIs(None, find_run_parts_dir(distro, "finalize.d"))


class TestPublishFTPMasterScript(TestCaseWithFactory, HelpersMixin):
    layer = LaunchpadZopelessLayer

    # Location of shell script.
    SCRIPT_PATH = "cronscripts/publish-ftpmaster.py"

    def prepareUbuntu(self):
        """Obtain a reference to Ubuntu, set up for testing.

        A temporary publishing directory will be set up, and it will be
        cleaned up after the test.
        """
        ubuntu = getUtility(ILaunchpadCelebrities).ubuntu
        self.setUpForScriptRun(ubuntu)
        return ubuntu

    def readReleaseFile(self, filename):
        """Read a Release file, return as a keyword/value dict."""
        sections = list(TagFile(file(filename)))
        self.assertEqual(1, len(sections))
        return dict(sections[0])

    def installRunPartsScript(self, distro, parts_dir, script_code):
        """Set up a run-parts script, and configure it to run.

        :param distro: The `Distribution` you're testing on.  Must have
            a temporary directory as its publishing root directory.
        :param parts_dir: The run-parts subdirectory to execute:
            publish-distro.d or finalize.d.
        :param script_code: The code to go into the script.
        """
        distro_config = get_pub_config(distro)
        parts_base = os.path.join(distro_config.root_dir, "distro-parts")
        self.enableRunParts(parts_base)
        script_dir = os.path.join(parts_base, distro.name, parts_dir)
        os.makedirs(script_dir)
        script_path = os.path.join(script_dir, self.factory.getUniqueString())
        script_file = file(script_path, "w")
        script_file.write(script_code)
        script_file.close()
        os.chmod(script_path, 0755)

    def test_script_runs_successfully(self):
        self.prepareUbuntu()
        self.layer.txn.commit()
        stdout, stderr, retval = run_script(
            self.SCRIPT_PATH + " -d ubuntu")
        self.assertEqual(0, retval, "Script failure:\n" + stderr)

    def test_getConfigs_maps_distro_and_purpose_to_matching_config(self):
        distro = self.makeDistroWithPublishDirectory()
        script = self.makeScript(distro)
        script.setUp()
        reference_config = getPubConfig(distro.main_archive)
        config = script.getConfigs()[distro][ArchivePurpose.PRIMARY]
        self.assertThat(
            config, MatchesStructure.fromExample(
                reference_config, 'temproot', 'distroroot', 'archiveroot'))

    def test_getConfigs_maps_distros(self):
        distro = self.makeDistroWithPublishDirectory()
        script = self.makeScript(distro)
        script.setUp()
        self.assertEqual([distro], script.getConfigs().keys())

    def test_getConfigs_skips_configless_distros(self):
        distro = self.factory.makeDistribution(no_pubconf=True)
        script = self.makeScript(distro)
        script.setUp()
        self.assertEqual({}, script.getConfigs()[distro])

    def test_script_is_happy_with_no_publications(self):
        distro = self.makeDistroWithPublishDirectory()
        self.makeScript(distro).main()

    def test_script_is_happy_with_no_pubconfigs(self):
        distro = self.factory.makeDistribution(no_pubconf=True)
        self.makeScript(distro).main()

    def test_produces_listings(self):
        distro = self.makeDistroWithPublishDirectory()
        self.makeScript(distro).main()
        self.assertTrue(
            path_exists(get_archive_root(get_pub_config(distro)), 'ls-lR.gz'))

    def test_can_run_twice(self):
        test_publisher = SoyuzTestPublisher()
        distroseries = test_publisher.setUpDefaultDistroSeries()
        distro = distroseries.distribution
        self.factory.makeComponentSelection(
            distroseries=distroseries, component="main")
        self.factory.makeArchive(
            distribution=distro, purpose=ArchivePurpose.PARTNER)
        test_publisher.getPubSource()

        self.setUpForScriptRun(distro)
        self.makeScript(distro).main()
        self.makeScript(distro).main()

    def test_publishes_package(self):
        test_publisher = SoyuzTestPublisher()
        distroseries = test_publisher.setUpDefaultDistroSeries()
        distro = distroseries.distribution
        pub_config = get_pub_config(distro)
        self.factory.makeComponentSelection(
            distroseries=distroseries, component="main")
        self.factory.makeArchive(
            distribution=distro, purpose=ArchivePurpose.PARTNER)
        test_publisher.getPubSource()

        self.setUpForScriptRun(distro)
        self.makeScript(distro).main()

        archive_root = get_archive_root(pub_config)
        dists_root = get_dists_root(pub_config)

        dsc = os.path.join(
            archive_root, 'pool', 'main', 'f', 'foo', 'foo_666.dsc')
        self.assertEqual("I do not care about sources.", file(dsc).read())
        overrides = os.path.join(
            archive_root + '-overrides', distroseries.name + '_main_source')
        self.assertEqual(dsc, file(overrides).read().rstrip())
        self.assertTrue(path_exists(
            dists_root, distroseries.name, 'main', 'source', 'Sources.gz'))
        self.assertTrue(path_exists(
            dists_root, distroseries.name, 'main', 'source', 'Sources.bz2'))

        distcopyseries = os.path.join(dists_root, distroseries.name)
        release = self.readReleaseFile(
            os.path.join(distcopyseries, "Release"))
        self.assertEqual(distro.displayname, release['Origin'])
        self.assertEqual(distro.displayname, release['Label'])
        self.assertEqual(distroseries.name, release['Suite'])
        self.assertEqual(distroseries.name, release['Codename'])
        self.assertEqual("main", release['Components'])
        self.assertEqual("", release["Architectures"])
        self.assertIn("Date", release)
        self.assertIn("Description", release)
        self.assertNotEqual("", release["MD5Sum"])
        self.assertNotEqual("", release["SHA1"])
        self.assertNotEqual("", release["SHA256"])

        main_release = self.readReleaseFile(
            os.path.join(distcopyseries, 'main', 'source', "Release"))
        self.assertEqual(distroseries.name, main_release["Archive"])
        self.assertEqual("main", main_release["Component"])
        self.assertEqual(distro.displayname, main_release["Origin"])
        self.assertEqual(distro.displayname, main_release["Label"])
        self.assertEqual("source", main_release["Architecture"])

    def test_getDirtySuites_returns_suite_with_pending_publication(self):
        spph = self.factory.makeSourcePackagePublishingHistory()
        distro = spph.distroseries.distribution
        script = self.makeScript(spph.distroseries.distribution)
        script.setUp()
        self.assertContentEqual(
            [name_pph_suite(spph)], script.getDirtySuites(distro))

    def test_getDirtySuites_returns_suites_with_pending_publications(self):
        distro = self.makeDistroWithPublishDirectory()
        spphs = [
            self.factory.makeSourcePackagePublishingHistory(
                distroseries=self.factory.makeDistroSeries(
                    distribution=distro))
            for counter in xrange(2)]

        script = self.makeScript(distro)
        script.setUp()
        self.assertContentEqual(
            [name_pph_suite(spph) for spph in spphs],
            script.getDirtySuites(distro))

    def test_getDirtySuites_ignores_suites_without_pending_publications(self):
        spph = self.factory.makeSourcePackagePublishingHistory(
            status=PackagePublishingStatus.PUBLISHED)
        distro = spph.distroseries.distribution
        script = self.makeScript(spph.distroseries.distribution)
        script.setUp()
        self.assertContentEqual([], script.getDirtySuites(distro))

    def test_getDirtySuites_returns_suites_with_pending_binaries(self):
        bpph = self.factory.makeBinaryPackagePublishingHistory()
        distro = bpph.distroseries.distribution
        script = self.makeScript(bpph.distroseries.distribution)
        script.setUp()
        self.assertContentEqual(
            [name_pph_suite(bpph)], script.getDirtySuites(distro))

    def test_getDirtySecuritySuites_returns_security_suites(self):
        distro = self.makeDistroWithPublishDirectory()
        spphs = [
            self.factory.makeSourcePackagePublishingHistory(
                distroseries=self.factory.makeDistroSeries(
                    distribution=distro),
                pocket=PackagePublishingPocket.SECURITY)
            for counter in xrange(2)]

        script = self.makeScript(distro)
        script.setUp()
        self.assertContentEqual(
            [name_pph_suite(spph) for spph in spphs],
            script.getDirtySecuritySuites(distro))

    def test_getDirtySecuritySuites_ignores_non_security_suites(self):
        distroseries = self.factory.makeDistroSeries()
        pockets = [
            PackagePublishingPocket.RELEASE,
            PackagePublishingPocket.UPDATES,
            PackagePublishingPocket.PROPOSED,
            PackagePublishingPocket.BACKPORTS,
            ]
        for pocket in pockets:
            self.factory.makeSourcePackagePublishingHistory(
                distroseries=distroseries, pocket=pocket)
        script = self.makeScript(distroseries.distribution)
        script.setUp()
        self.assertEqual(
            [], script.getDirtySecuritySuites(distroseries.distribution))

    def test_rsync_copies_files(self):
        distro = self.makeDistroWithPublishDirectory()
        script = self.makeScript(distro)
        script.setUp()
        dists_root = get_dists_root(get_pub_config(distro))
        dists_backup = os.path.join(
            get_distscopy_root(get_pub_config(distro)), "dists")
        os.makedirs(dists_backup)
        os.makedirs(dists_root)
        write_marker_file([dists_root, "new-file"], "New file")
        script.rsyncBackupDists(distro)
        self.assertEqual(
            "New file", read_marker_file([dists_backup, "new-file"]))

    def test_rsync_cleans_up_obsolete_files(self):
        distro = self.makeDistroWithPublishDirectory()
        script = self.makeScript(distro)
        script.setUp()
        dists_backup = os.path.join(
            get_distscopy_root(get_pub_config(distro)), "dists")
        os.makedirs(dists_backup)
        old_file = [dists_backup, "old-file"]
        write_marker_file(old_file, "old-file")
        os.makedirs(get_dists_root(get_pub_config(distro)))
        script.rsyncBackupDists(distro)
        self.assertFalse(path_exists(*old_file))

    def test_setUpDirs_creates_directory_structure(self):
        distro = self.makeDistroWithPublishDirectory()
        pub_config = get_pub_config(distro)
        archive_root = get_archive_root(pub_config)
        dists_root = get_dists_root(pub_config)
        script = self.makeScript(distro)
        script.setUp()

        self.assertFalse(file_exists(archive_root))

        script.setUpDirs()

        self.assertTrue(file_exists(archive_root))
        self.assertTrue(file_exists(dists_root))
        self.assertTrue(file_exists(get_distscopy_root(pub_config)))

    def test_setUpDirs_does_not_mind_if_dist_directories_already_exist(self):
        distro = self.makeDistroWithPublishDirectory()
        script = self.makeScript(distro)
        script.setUp()
        script.setUpDirs()
        script.setUpDirs()
        self.assertTrue(file_exists(get_archive_root(get_pub_config(distro))))

    def test_publishDistroArchive_runs_parts(self):
        distro = self.makeDistroWithPublishDirectory()
        script = self.makeScript(distro)
        script.setUp()
        script.setUpDirs()
        script.runParts = FakeMethod()
        script.publishDistroArchive(distro, distro.main_archive)
        self.assertEqual(1, script.runParts.call_count)
        args, kwargs = script.runParts.calls[0]
        run_distro, parts_dir, env = args
        self.assertEqual(distro, run_distro)
        self.assertEqual("publish-distro.d", parts_dir)

    def test_runPublishDistroParts_passes_parameters(self):
        distro = self.makeDistroWithPublishDirectory()
        script = self.makeScript(distro)
        script.setUp()
        script.setUpDirs()
        script.runParts = FakeMethod()
        script.runPublishDistroParts(distro, distro.main_archive)
        args, kwargs = script.runParts.calls[0]
        run_distro, parts_dir, env = args
        required_parameters = set([
            "ARCHIVEROOT", "DISTSROOT", "OVERRIDEROOT"])
        missing_parameters = required_parameters.difference(set(env.keys()))
        self.assertEqual(set(), missing_parameters)

    def test_generateListings_writes_ls_lR_gz(self):
        distro = self.makeDistroWithPublishDirectory()
        script = self.makeScript(distro)
        script.setUp()
        script.setUpDirs()
        script.generateListings(distro)
        pass

    def test_clearEmptyDirs_cleans_up_empty_directories(self):
        distro = self.makeDistroWithPublishDirectory()
        script = self.makeScript(distro)
        script.setUp()
        script.setUpDirs()
        empty_dir = os.path.join(
            get_dists_root(get_pub_config(distro)), 'empty-dir')
        os.makedirs(empty_dir)
        script.clearEmptyDirs(distro)
        self.assertFalse(file_exists(empty_dir))

    def test_clearEmptyDirs_does_not_clean_up_nonempty_directories(self):
        distro = self.makeDistroWithPublishDirectory()
        script = self.makeScript(distro)
        script.setUp()
        script.setUpDirs()
        nonempty_dir = os.path.join(
            get_dists_root(get_pub_config(distro)), 'nonempty-dir')
        os.makedirs(nonempty_dir)
        write_marker_file([nonempty_dir, "placeholder"], "Data here!")
        script.clearEmptyDirs(distro)
        self.assertTrue(file_exists(nonempty_dir))

    def test_processOptions_finds_distribution(self):
        distro = self.makeDistroWithPublishDirectory()
        script = self.makeScript(distro)
        script.processOptions()
        self.assertEqual(distro.name, script.options.distribution)
        self.assertEqual([distro], script.distributions)

    def test_processOptions_for_all_derived_finds_derived_distros(self):
        dsp = self.factory.makeDistroSeriesParent()
        script = PublishFTPMaster(test_args=['--all-derived'])
        script.processOptions()
        self.assertIn(dsp.derived_series.distribution, script.distributions)

    def test_processOptions_for_all_derived_ignores_nonderived_distros(self):
        distro = self.factory.makeDistribution()
        script = PublishFTPMaster(test_args=['--all-derived'])
        script.processOptions()
        self.assertNotIn(distro, script.distributions)

    def test_processOptions_complains_about_unknown_distribution(self):
        script = self.makeScript()
        script.options.distribution = self.factory.getUniqueString()
        self.assertRaises(LaunchpadScriptFailure, script.processOptions)

    def test_runParts_runs_parts(self):
        self.enableRunParts()
        script = self.makeScript(self.prepareUbuntu())
        script.setUp()
        distro = script.distributions[0]
        script.executeShell = FakeMethod()
        script.runParts(distro, "finalize.d", {})
        self.assertEqual(1, script.executeShell.call_count)
        args, kwargs = script.executeShell.calls[-1]
        command_line, = args
        self.assertIn("run-parts", command_line)
        self.assertIn(
            os.path.join(self.parts_directory, "ubuntu/finalize.d"),
            command_line)

    def test_runParts_passes_parameters(self):
        self.enableRunParts()
        script = self.makeScript(self.prepareUbuntu())
        script.setUp()
        distro = script.distributions[0]
        script.executeShell = FakeMethod()
        key = self.factory.getUniqueString()
        value = self.factory.getUniqueString()
        script.runParts(distro, "finalize.d", {key: value})
        args, kwargs = script.executeShell.calls[-1]
        command_line, = args
        self.assertIn("%s=%s" % (key, value), command_line)

    def test_executeShell_executes_shell_command(self):
        distro = self.makeDistroWithPublishDirectory()
        script = self.makeScript(distro)
        marker = os.path.join(
            get_pub_config(distro).root_dir, "marker")
        script.executeShell("touch %s" % marker)
        self.assertTrue(file_exists(marker))

    def test_executeShell_reports_failure_if_requested(self):
        distro = self.makeDistroWithPublishDirectory()
        script = self.makeScript(distro)

        class ArbitraryFailure(Exception):
            """Some exception that's not likely to come from elsewhere."""

        self.assertRaises(
            ArbitraryFailure,
            script.executeShell, "/bin/false", failure=ArbitraryFailure())

    def test_executeShell_does_not_report_failure_if_not_requested(self):
        distro = self.makeDistroWithPublishDirectory()
        script = self.makeScript(distro)
        # The test is that this does not fail:
        script.executeShell("/bin/false")

    def test_runFinalizeParts_passes_parameters(self):
        script = self.makeScript(self.prepareUbuntu())
        script.setUp()
        distro = script.distributions[0]
        script.runParts = FakeMethod()
        script.runFinalizeParts(distro)
        args, kwargs = script.runParts.calls[0]
        run_distro, parts_dir, env = args
        required_parameters = set(["ARCHIVEROOTS", "SECURITY_UPLOAD_ONLY"])
        missing_parameters = required_parameters.difference(set(env.keys()))
        self.assertEqual(set(), missing_parameters)

    def test_publishSecurityUploads_skips_pub_if_no_security_updates(self):
        script = self.makeScript()
        script.setUp()
        distro = script.distributions[0]
        script.setUpDirs()
        script.installDists = FakeMethod()
        script.publishSecurityUploads(distro)
        self.assertEqual(0, script.installDists.call_count)

    def test_publishDistroUploads_publishes_all_distro_archives(self):
        distro = self.makeDistroWithPublishDirectory()
        distroseries = self.factory.makeDistroSeries(distribution=distro)
        partner_archive = self.factory.makeArchive(
            distribution=distro, purpose=ArchivePurpose.PARTNER)
        for archive in distro.all_distro_archives:
            self.factory.makeSourcePackagePublishingHistory(
                distroseries=distroseries,
                archive=archive)
        script = self.makeScript(distro)
        script.setUp()
        script.setUpDirs()
        script.publishDistroArchive = FakeMethod()
        script.publishDistroUploads(distro)
        published_archives = [
            args[1] for args, kwargs in script.publishDistroArchive.calls]

        self.assertContentEqual(
            distro.all_distro_archives, published_archives)
        self.assertIn(distro.main_archive, published_archives)
        self.assertIn(partner_archive, published_archives)

    def test_recoverWorkingDists_is_quiet_normally(self):
        script = self.makeScript()
        script.setUp()
        script.logger = BufferLogger()
        script.logger.setLevel(logging.INFO)
        script.recoverWorkingDists()
        self.assertEqual('', script.logger.getLogBuffer())

    def test_recoverWorkingDists_recovers_working_directory(self):
        distro = self.makeDistroWithPublishDirectory()
        script = self.makeScript(distro)
        script.setUp()
        script.logger = BufferLogger()
        script.logger.setLevel(logging.INFO)
        script.setUpDirs()
        archive_config = getPubConfig(distro.main_archive)
        backup_dists = os.path.join(
            archive_config.archiveroot + "-distscopy", "dists")
        working_dists = get_working_dists(archive_config)
        os.rename(backup_dists, working_dists)
        write_marker_file([working_dists, "marker"], "Recovered")
        script.recoverWorkingDists()
        self.assertEqual(
            "Recovered", read_marker_file([backup_dists, "marker"]))
        self.assertNotEqual('', script.logger.getLogBuffer())

    def test_publishes_first_security_updates_then_all_updates(self):
        script = self.makeScript()
        script.publish = FakeMethod()
        script.main()
        self.assertEqual(2, script.publish.call_count)
        args, kwargs = script.publish.calls[0]
        self.assertEqual({'security_only': True}, kwargs)
        args, kwargs = script.publish.calls[1]
        self.assertEqual(False, kwargs.get('security_only', False))

    def test_security_run_publishes_only_security_updates(self):
        script = self.makeScript(extra_args=['--security-only'])
        script.publish = FakeMethod()
        script.main()
        self.assertEqual(1, script.publish.call_count)
        args, kwargs = script.publish.calls[0]
        self.assertEqual({'security_only': True}, kwargs)

    def test_publishDistroUploads_processes_all_archives(self):
        distro = self.makeDistroWithPublishDirectory()
        partner_archive = self.factory.makeArchive(
            distribution=distro, purpose=ArchivePurpose.PARTNER)
        script = self.makeScript(distro)
        script.publishDistroArchive = FakeMethod()
        script.setUp()
        script.publishDistroUploads(distro)
        published_archives = [
            args[1] for args, kwargs in script.publishDistroArchive.calls]
        self.assertContentEqual(
            [distro.main_archive, partner_archive], published_archives)

    def test_runFinalizeParts_quotes_archiveroots(self):
        # Passing ARCHIVEROOTS to the finalize.d scripts is a bit
        # difficult because the variable holds multiple values in a
        # single, double-quoted string.  Escaping and quoting a sequence
        # of escaped and quoted items won't work.
        # This test establishes how a script can sanely deal with the
        # list.  It'll probably go wrong if the configured archive root
        # contains spaces and such, but should work with Unix-sensible
        # paths.
        distro = self.makeDistroWithPublishDirectory()
        self.factory.makeArchive(
            distribution=distro, purpose=ArchivePurpose.PARTNER)
        script = self.makeScript(distro)
        script.setUp()
        script.setUpDirs()

        # Create a run-parts script that creates marker files in each of
        # the archive roots, and writes an expected string to them.
        # Doesn't write to a marker file that already exists, because it
        # might be a sign that the path it received is ridiculously
        # wrong.  Don't want to go overwriting random files now do we?
        self.installRunPartsScript(distro, "finalize.d", dedent("""\
            #!/bin/sh -e
            MARKER_NAME="marker file"
            for DIRECTORY in $ARCHIVEROOTS
            do
                MARKER="$DIRECTORY/$MARKER_NAME"
                if [ -e "$MARKER" ]
                then
                    echo "Marker file $MARKER already exists." >&2
                    exit 1
                fi
                echo "This is an archive root." >"$MARKER"
            done
            """))

        script.runFinalizeParts(distro)

        for archive in [distro.main_archive, distro.getArchive("partner")]:
            archive_root = getPubConfig(archive).archiveroot
            self.assertEqual(
                "This is an archive root.",
                read_marker_file([archive_root, "marker file"]).rstrip(),
                "Did not find expected marker for %s."
                % archive.purpose.title)

    def test_publish_reraises_exception(self):
        # If an Exception comes up while publishing, it bubbles up out
        # of the publish method even though the method must intercept
        # it for its own purposes.
        class MoonPhaseError(Exception):
            """Simulated failure."""

        message = self.factory.getUniqueString()
        script = self.makeScript()
        script.publishDistroUploads = FakeMethod(
            failure=MoonPhaseError(message))
        script.setUp()
        self.assertRaisesWithContent(
            MoonPhaseError, message,
            script.publish, script.distributions[0])

    def test_publish_obeys_keyboard_interrupt(self):
        # Similar to an Exception, a keyboard interrupt does not get
        # swallowed.
        message = self.factory.getUniqueString()
        script = self.makeScript()
        script.publishDistroUploads = FakeMethod(
            failure=KeyboardInterrupt(message))
        script.setUp()
        self.assertRaisesWithContent(
            KeyboardInterrupt, message,
            script.publish, script.distributions[0])

    def test_publish_recovers_working_dists_on_exception(self):
        # If an Exception comes up while publishing, the publish method
        # recovers its working directory.
        class MoonPhaseError(Exception):
            """Simulated failure."""

        failure = MoonPhaseError(self.factory.getUniqueString())

        script = self.makeScript()
        script.publishDistroUploads = FakeMethod(failure=failure)
        script.recoverArchiveWorkingDir = FakeMethod()
        script.setUp()

        try:
            script.publish(script.distributions[0])
        except MoonPhaseError:
            pass

        self.assertEqual(1, script.recoverArchiveWorkingDir.call_count)

    def test_publish_recovers_working_dists_on_ctrl_C(self):
        # If the user hits ctrl-C while publishing, the publish method
        # recovers its working directory.
        failure = KeyboardInterrupt("Ctrl-C!")

        script = self.makeScript()
        script.publishDistroUploads = FakeMethod(failure=failure)
        script.recoverArchiveWorkingDir = FakeMethod()
        script.setUp()

        try:
            script.publish(script.distributions[0])
        except KeyboardInterrupt:
            pass

        self.assertEqual(1, script.recoverArchiveWorkingDir.call_count)


class TestCreateDistroSeriesIndexes(TestCaseWithFactory, HelpersMixin):
    """Test initial creation of archive indexes for a `DistroSeries`."""
    layer = LaunchpadZopelessLayer

    def createIndexesMarkerDir(self, script, distroseries):
        """Create the directory for `distroseries`'s indexes marker."""
        marker = script.locateIndexesMarker(
            distroseries.distribution, get_a_suite(distroseries))
        os.makedirs(os.path.dirname(marker))

    def makeDistroSeriesNeedingIndexes(self, distribution=None):
        """Create `DistroSeries` that needs indexes created."""
        return self.factory.makeDistroSeries(
            status=SeriesStatus.FROZEN, distribution=distribution)

    def test_listSuitesNeedingIndexes_is_nonempty_for_new_frozen_series(self):
        # If a distroseries is Frozen and has not had its indexes
        # created yet, listSuitesNeedingIndexes returns a nonempty list
        # for it.
        series = self.makeDistroSeriesNeedingIndexes()
        script = self.makeScript(series.distribution)
        script.setUp()
        self.assertNotEqual([], list(script.listSuitesNeedingIndexes(series)))

    def test_listSuitesNeedingIndexes_initially_includes_entire_series(self):
        # If a series has not had any of its indexes created yet,
        # listSuitesNeedingIndexes returns all of its suites.
        series = self.makeDistroSeriesNeedingIndexes()
        script = self.makeScript(series.distribution)
        script.setUp()
        self.assertContentEqual(
            [series.getSuite(pocket) for pocket in pocketsuffix.iterkeys()],
            script.listSuitesNeedingIndexes(series))

    def test_listSuitesNeedingIndexes_is_empty_for_nonfrozen_series(self):
        # listSuitesNeedingIndexes only returns suites for Frozen
        # distroseries.
        series = self.factory.makeDistroSeries()
        script = self.makeScript(series.distribution)
        self.assertEqual([], script.listSuitesNeedingIndexes(series))

    def test_listSuitesNeedingIndexes_is_empty_for_configless_distro(self):
        # listSuitesNeedingIndexes returns no suites for distributions
        # that have no publisher config, such as Debian.  We don't want
        # to publish such distributions.
        series = self.makeDistroSeriesNeedingIndexes()
        pub_config = get_pub_config(series.distribution)
        IMasterStore(pub_config).remove(pub_config)
        script = self.makeScript(series.distribution)
        self.assertEqual([], script.listSuitesNeedingIndexes(series))

    def test_markIndexCreationComplete_repels_listSuitesNeedingIndexes(self):
        # The effect of markIndexCreationComplete is to remove the suite
        # in question from the results of listSuitesNeedingIndexes for
        # that distroseries.
        distro = self.makeDistroWithPublishDirectory()
        series = self.makeDistroSeriesNeedingIndexes(distribution=distro)
        script = self.makeScript(distro)
        script.setUp()
        self.createIndexesMarkerDir(script, series)

        needful_suites = script.listSuitesNeedingIndexes(series)
        suite = get_a_suite(series)
        script.markIndexCreationComplete(distro, suite)
        needful_suites.remove(suite)
        self.assertContentEqual(
            needful_suites, script.listSuitesNeedingIndexes(series))

    def test_listSuitesNeedingIndexes_ignores_other_series(self):
        # listSuitesNeedingIndexes only returns suites for series that
        # need indexes created.  It ignores other distroseries.
        series = self.makeDistroSeriesNeedingIndexes()
        self.factory.makeDistroSeries(distribution=series.distribution)
        script = self.makeScript(series.distribution)
        script.setUp()
        suites = list(script.listSuitesNeedingIndexes(series))
        self.assertNotEqual([], suites)
        for suite in suites:
            self.assertThat(suite, StartsWith(series.name))

    def test_createIndexes_marks_index_creation_complete(self):
        # createIndexes calls markIndexCreationComplete for the suite.
        distro = self.makeDistroWithPublishDirectory()
        series = self.factory.makeDistroSeries(distribution=distro)
        script = self.makeScript(distro)
        script.markIndexCreationComplete = FakeMethod()
        script.runPublishDistro = FakeMethod()
        suite = get_a_suite(series)
        script.createIndexes(distro, [suite])
        self.assertEqual(
            [((distro, suite), {})], script.markIndexCreationComplete.calls)

    def test_failed_index_creation_is_not_marked_complete(self):
        # If index creation fails, it is not marked as having been
        # completed.  The next run will retry.
        class Boom(Exception):
            """Simulated failure."""

        series = self.factory.makeDistroSeries()
        script = self.makeScript(series.distribution)
        script.markIndexCreationComplete = FakeMethod()
        script.runPublishDistro = FakeMethod(failure=Boom("Sorry!"))
        try:
            script.createIndexes(series.distribution, [get_a_suite(series)])
        except:
            pass
        self.assertEqual([], script.markIndexCreationComplete.calls)

    def test_locateIndexesMarker_places_file_in_archive_root(self):
        # The marker file for index creation is in the distribution's
        # archive root.
        series = self.factory.makeDistroSeries()
        script = self.makeScript(series.distribution)
        script.setUp()
        archive_root = getPubConfig(series.main_archive).archiveroot
        self.assertThat(
            script.locateIndexesMarker(
                series.distribution, get_a_suite(series)),
            StartsWith(os.path.normpath(archive_root)))

    def test_locateIndexesMarker_uses_separate_files_per_suite(self):
        # Each suite in a distroseries gets its own marker file for
        # index creation.
        distro = self.makeDistroWithPublishDirectory()
        series = self.factory.makeDistroSeries(distribution=distro)
        script = self.makeScript(distro)
        script.setUp()
        markers = get_marker_files(script, series)
        self.assertEqual(sorted(markers), sorted(list(set(markers))))

    def test_locateIndexesMarker_separates_distroseries(self):
        # Each distroseries gets its own marker files for index
        # creation.
        distro = self.makeDistroWithPublishDirectory()
        series1 = self.factory.makeDistroSeries(distribution=distro)
        series2 = self.factory.makeDistroSeries(distribution=distro)
        script = self.makeScript(distro)
        script.setUp()
        markers1 = set(get_marker_files(script, series1))
        markers2 = set(get_marker_files(script, series2))
        self.assertEqual(set(), markers1.intersection(markers2))

    def test_locateIndexMarker_uses_hidden_file(self):
        # The index-creation marker file is a "dot file," so it's not
        # visible in normal directory listings.
        series = self.factory.makeDistroSeries()
        script = self.makeScript(series.distribution)
        script.setUp()
        suite = get_a_suite(series)
        self.assertThat(
            os.path.basename(script.locateIndexesMarker(
                series.distribution, suite)),
            StartsWith("."))

    def test_script_calls_createIndexes_for_new_series(self):
        # If the script's main() finds a distroseries that needs its
        # indexes created, it calls createIndexes on that distroseries,
        # passing it all of the series' suite names.
        distro = self.makeDistroWithPublishDirectory()
        series = self.makeDistroSeriesNeedingIndexes(distribution=distro)
        script = self.makeScript(distro)
        script.createIndexes = FakeMethod()
        script.main()
        [((given_distro, given_suites), kwargs)] = script.createIndexes.calls
        self.assertEqual(distro, given_distro)
        self.assertContentEqual(
            [series.getSuite(pocket) for pocket in pocketsuffix.iterkeys()],
            given_suites)

    def test_createIndexes_ignores_other_series(self):
        # createIndexes does not accidentally also touch other
        # distroseries than the one it's meant to.
        distro = self.makeDistroWithPublishDirectory()
        series = self.factory.makeDistroSeries(distribution=distro)
        self.factory.makeDistroSeries(distribution=distro)
        script = self.makeScript(distro)
        script.setUp()
        script.runPublishDistro = FakeMethod()
        self.createIndexesMarkerDir(script, series)
        suite = get_a_suite(series)

        script.createIndexes(distro, [suite])

        args, kwargs = script.runPublishDistro.calls[0]
        self.assertEqual([suite], kwargs['suites'])
        self.assertThat(kwargs['suites'][0], StartsWith(series.name))

    def test_prepareFreshSeries_copies_custom_uploads(self):
        distro = self.makeDistroWithPublishDirectory()
        old_series = self.factory.makeDistroSeries(
            distribution=distro, status=SeriesStatus.CURRENT)
        new_series = self.factory.makeDistroSeries(
            distribution=distro, previous_series=old_series,
            status=SeriesStatus.FROZEN)
        self.factory.makeDistroArchSeries(
            distroseries=new_series, architecturetag='i386')
        custom_upload = self.factory.makeCustomPackageUpload(
            distroseries=old_series,
            custom_type=PackageUploadCustomFormat.DEBIAN_INSTALLER,
            filename='debian-installer-images_1.0-20110805_i386.tar.gz')
        script = self.makeScript(distro)
        script.createIndexes = FakeMethod()
        script.setUp()
        have_fresh_series = script.prepareFreshSeries(distro)
        self.assertTrue(have_fresh_series)
        [copied_upload] = new_series.getPackageUploads(
            name=u'debian-installer-images', exact_match=False)
        [copied_custom] = copied_upload.customfiles
        self.assertEqual(
            custom_upload.customfiles[0].libraryfilealias.filename,
            copied_custom.libraryfilealias.filename)

    def test_script_creates_indexes(self):
        # End-to-end test: the script creates indexes for distroseries
        # that need them.
        test_publisher = SoyuzTestPublisher()
        series = test_publisher.setUpDefaultDistroSeries()
        series.status = SeriesStatus.FROZEN
        self.factory.makeComponentSelection(
            distroseries=series, component="main")
        self.layer.txn.commit()
        self.setUpForScriptRun(series.distribution)
        script = self.makeScript(series.distribution)
        script.main()
        self.assertEqual([], script.listSuitesNeedingIndexes(series))
        sources = os.path.join(
            getPubConfig(series.main_archive).distsroot,
            series.name, "main", "source", "Sources")
        self.assertTrue(file_exists(sources))
