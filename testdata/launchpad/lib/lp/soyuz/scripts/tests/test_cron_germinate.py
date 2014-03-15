#!/usr/bin/python
# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""This is a test for the soyuz cron.germinate script."""

__metaclass__ = type

import copy
import gzip
import os
import subprocess

from lp.testing import TestCase


class TestCronGerminate(TestCase):

    DISTRO_NAMES = ["platform", "ubuntu", "kubuntu", "netbook"]
    DISTS = ["hardy", "lucid", "maverick"]
    DEVELOPMENT_DIST = "natty"
    COMPONENTS = ["main", "restricted", "universe", "multiverse"]
    ARCHES = ["i386", "amd64", "armel", "powerpc"]
    BASEPATH = os.path.abspath(os.path.dirname(__file__))
    source_root = os.path.normpath(
        os.path.join(BASEPATH, "..", "..", "..", "..", ".."))

    def setUp(self):
        super(TestCronGerminate, self).setUp()

        # Setup a temp archive directory and populate it with the right
        # sub-directories.
        self.tmpdir = self.makeTemporaryDirectory()
        self.archive_dir = self.setup_mock_archive_environment()
        self.ubuntu_misc_dir = os.path.join(self.archive_dir, "ubuntu-misc")
        self.ubuntu_germinate_dir = os.path.join(
            self.archive_dir, "ubuntu-germinate")
        # Create a mock archive environment for all the distros we support and
        # also include "updates" and "security".
        for dist in self.DISTS + [self.DEVELOPMENT_DIST]:
            self.populate_mock_archive_environment(
                self.archive_dir, self.COMPONENTS, self.ARCHES, dist)
            for component in ["security", "updates"]:
                self.populate_mock_archive_environment(
                    self.archive_dir, self.COMPONENTS, self.ARCHES,
                    "%s-%s" % (dist, component))
        # Generate test dummies for maintenance-time.py, if this is set to
        # "None" instead it will use the network to test against the real
        # data.
        self.germinate_output_dir = self.setup_mock_germinate_output()

    def create_directory_if_missing(self, directory):
        """Create the given directory if it does not exist."""
        if not os.path.exists(directory):
            os.makedirs(directory)

    def create_directory_list_if_missing(self, directory_list):
        """Create the given directories from the list if they don't exist."""
        for directory in directory_list:
            self.create_directory_if_missing(directory)

    def create_gzip_file(self, filepath, content=""):
        """Create a gziped file in the given path with the given content.

        If no content is given a empty file is created.
        """
        gz = gzip.GzipFile(filepath, "w")
        gz.write(content)
        gz.close()

    def create_file(self, filepath, content=""):
        """Create a file in the given path with the given content.

        If no content is given a empty file is created.
        """
        f = open(filepath, "w")
        f.write(content)
        f.close()

    def setup_mock_germinate_output(self):
        # empty structure files
        germinate_output_dir = os.path.join(
            self.tmpdir, "germinate-test-data", "germinate-output")
        dirs = []
        for distro_name in self.DISTRO_NAMES:
            for distro_series in self.DISTS:
                dirs.append(
                    os.path.join(
                        germinate_output_dir,
                        "%s.%s" % (distro_name, distro_series)))
        self.create_directory_list_if_missing(dirs)
        for dir in dirs:
            self.create_file(os.path.join(dir, "structure"))
        return germinate_output_dir

    def setup_mock_archive_environment(self):
        """
        Creates a mock archive environment and populate it with the
        subdirectories that germinate will expect.
        """
        archive_dir = os.path.join(
            self.tmpdir, "germinate-test-data", "ubuntu-archive")
        ubuntu_misc_dir = os.path.join(archive_dir, "ubuntu-misc")
        ubuntu_germinate_dir = os.path.join(archive_dir, "ubuntu-germinate")
        ubuntu_dists_dir = os.path.join(archive_dir, "ubuntu", "dists")
        self.create_directory_list_if_missing([
                archive_dir,
                ubuntu_misc_dir,
                ubuntu_germinate_dir,
                ubuntu_dists_dir])
        return archive_dir

    def populate_mock_archive_environment(self, archive_dir, components_list,
                                          arches_list, current_devel_distro):
        """
        Populates a mock archive environment with empty source packages and
        empty binary packages.
        """
        for component in components_list:
            # Create the environment for the source packages.
            targetdir = os.path.join(
                archive_dir,
                "ubuntu/dists/%s/%s/source" % (
                    current_devel_distro, component))
            self.create_directory_if_missing(targetdir)
            self.create_gzip_file(os.path.join(targetdir, "Sources.gz"))

            # Create the environment for the binary packages.
            for arch in arches_list:
                for subpath in ["", "debian-installer"]:
                    targetdir = os.path.join(
                        self.archive_dir,
                        "ubuntu/dists/%s/%s/%s/binary-%s" % (
                            current_devel_distro, component, subpath, arch))
                    self.create_directory_if_missing(targetdir)
                    self.create_gzip_file(os.path.join(
                            targetdir, "Packages.gz"))

    def create_fake_environment(self, basepath, archive_dir,
                                germinate_output_dir):
        """
        Create a fake process envirionment based on os.environ that sets
        TEST_ARCHIVEROOT, TEST_LAUNCHPADROOT and modifies PATH to point to the
        mock lp-bin directory.
        """
        fake_environ = copy.copy(os.environ)
        fake_environ["TEST_ARCHIVEROOT"] = os.path.abspath(
            os.path.join(archive_dir, "ubuntu"))
        fake_environ["TEST_LAUNCHPADROOT"] = os.path.abspath(
            os.path.join(basepath, "germinate-test-data/mock-lp-root"))
        # Set the PATH in the fake environment so that our mock lockfile is
        # used.
        fake_environ["PATH"] = "%s:%s" % (
            os.path.abspath(os.path.join(
                basepath, "germinate-test-data/mock-bin")),
            os.environ["PATH"])
        # test dummies for get-support-timeframe.py, they need to be
        # in URI format
        if germinate_output_dir:
            # redirect base url to the mock environment
            fake_environ["MAINTENANCE_CHECK_BASE_URL"] = "file://%s" % \
                germinate_output_dir
            # point to mock archive root
            archive_root_url = "file://%s" % os.path.abspath(
                os.path.join(archive_dir, "ubuntu"))
            fake_environ["MAINTENANCE_CHECK_ARCHIVE_ROOT"] = archive_root_url
            # maintenance-check.py expects a format string
            hints_file_url = (
                germinate_output_dir + "/platform.%s/SUPPORTED_HINTS")
            for distro in self.DISTS:
                open(hints_file_url % distro, "w")
            fake_environ["MAINTENANCE_CHECK_HINTS_DIR_URL"] = "file://%s" % \
                os.path.abspath(hints_file_url)
            # add hints override to test that feature
            f=open(hints_file_url % "lucid", "a")
            f.write("linux-image-2.6.32-25-server 5y\n")
            f.close()
        return fake_environ

    def test_maintenance_update(self):
        """
        Test the maintenance-check.py porition of the soyuz cron.germinate
        shell script by running it inside a fake environment and ensure that
        it did update the "Support" override information for apt-ftparchive
        without destroying/modifying the information that the "germinate"
        script added to it earlier.
        """
        # Write into more-extras.overrides to ensure it is alive after we
        # mucked around.
        canary = "abrowser Task mock\n"
        # Build fake environment based on the real one.
        fake_environ = self.create_fake_environment(
            self.BASEPATH, self.archive_dir, self.germinate_output_dir)
        # Create mock override data files that include the canary string
        # so that we can test later if it is still there.
        for dist in self.DISTS:
            self.create_file(
                os.path.join(self.ubuntu_misc_dir,
                             "more-extra.override.%s.main" % dist),
                canary)

        # Run cron.germinate in the fake environment.
        cron_germinate_path = os.path.join(
            self.source_root, "cronscripts", "publishing", "cron.germinate")
        subprocess.call(
            [cron_germinate_path], env=fake_environ, cwd=self.BASEPATH)

        # And check the output it generated for correctness.
        for dist in self.DISTS:
            supported_override_file = os.path.join(
                self.ubuntu_misc_dir,
                "more-extra.override.%s.main.supported" % dist)
            self.assertTrue(os.path.exists(supported_override_file),
                            "no override file created for '%s'" % dist)
            main_override_file = os.path.join(
                self.ubuntu_misc_dir,
                "more-extra.override.%s.main" % dist)
            self.assertIn(canary, open(main_override_file).read())

        # Check here if we got the data from maintenance-check.py that
        # we expected. This is a kernel name from lucid-updates and it
        # will be valid for 5 years.
        needle = "linux-image-2.6.32-25-server/i386 Supported 5y"
        lucid_supported_override_file = os.path.join(
            self.ubuntu_misc_dir, "more-extra.override.lucid.main")
        self.assertIn(needle, open(lucid_supported_override_file).read())
