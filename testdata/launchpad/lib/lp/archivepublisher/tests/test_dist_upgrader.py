# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test dist-upgrader custom uploads.

See also lp.soyuz.tests.test_distroseriesqueue_dist_upgrader for high-level
tests of dist-upgrader upload and queue manipulation.
"""

import os

from lp.archivepublisher.customupload import (
    CustomUploadAlreadyExists,
    CustomUploadBadUmask,
    )
from lp.archivepublisher.dist_upgrader import (
    DistUpgraderBadVersion,
    DistUpgraderUpload,
    process_dist_upgrader,
    )
from lp.services.tarfile_helpers import LaunchpadWriteTarFile
from lp.testing import TestCase


class FakeConfig:
    """A fake publisher configuration."""
    def __init__(self, archiveroot):
        self.archiveroot = archiveroot


class TestDistUpgrader(TestCase):

    def setUp(self):
        super(TestDistUpgrader, self).setUp()
        self.temp_dir = self.makeTemporaryDirectory()
        self.pubconf = FakeConfig(self.temp_dir)
        self.suite = "distroseries"
        # CustomUpload.installFiles requires a umask of 022.
        old_umask = os.umask(022)
        self.addCleanup(os.umask, old_umask)

    def openArchive(self, version):
        self.path = os.path.join(
            self.temp_dir, "dist-upgrader_%s_all.tar.gz" % version)
        self.buffer = open(self.path, "wb")
        self.archive = LaunchpadWriteTarFile(self.buffer)

    def process(self):
        self.archive.close()
        self.buffer.close()
        process_dist_upgrader(self.pubconf, self.path, self.suite)

    def getUpgraderPath(self):
        return os.path.join(
            self.temp_dir, "dists", self.suite, "main", "dist-upgrader-all")

    def test_basic(self):
        # Processing a simple correct tar file works.
        self.openArchive("20060302.0120")
        self.archive.add_file("20060302.0120/hello", "world")
        self.process()

    def test_already_exists(self):
        # If the target directory already exists, processing fails.
        self.openArchive("20060302.0120")
        self.archive.add_file("20060302.0120/hello", "world")
        os.makedirs(os.path.join(self.getUpgraderPath(), "20060302.0120"))
        self.assertRaises(CustomUploadAlreadyExists, self.process)

    def test_bad_umask(self):
        # The umask must be 022 to avoid incorrect permissions.
        self.openArchive("20060302.0120")
        self.archive.add_file("20060302.0120/file", "foo")
        os.umask(002)  # cleanup already handled by setUp
        self.assertRaises(CustomUploadBadUmask, self.process)

    def test_current_symlink(self):
        # A "current" symlink is created to the last version.
        self.openArchive("20060302.0120")
        self.archive.add_file("20060302.0120/hello", "world")
        self.process()
        upgrader_path = self.getUpgraderPath()
        self.assertContentEqual(
            ["20060302.0120", "current"], os.listdir(upgrader_path))
        self.assertEqual(
            "20060302.0120",
            os.readlink(os.path.join(upgrader_path, "current")))
        self.assertContentEqual(
            ["hello"],
            os.listdir(os.path.join(upgrader_path, "20060302.0120")))

    def test_bad_version(self):
        # Bad versions in the tarball are refused.
        self.openArchive("20070219.1234")
        self.archive.add_file("foobar/foobar/dapper.tar.gz", "")
        self.assertRaises(DistUpgraderBadVersion, self.process)

    def test_getSeriesKey_extracts_architecture(self):
        # getSeriesKey extracts the architecture from an upload's filename.
        self.openArchive("20060302.0120")
        self.assertEqual("all", DistUpgraderUpload.getSeriesKey(self.path))

    def test_getSeriesKey_returns_None_on_mismatch(self):
        # getSeriesKey returns None if the filename does not match the
        # expected pattern.
        self.assertIsNone(DistUpgraderUpload.getSeriesKey("argh_1.0.jpg"))

    def test_getSeriesKey_refuses_names_with_wrong_number_of_fields(self):
        # getSeriesKey requires exactly three fields.
        self.assertIsNone(DistUpgraderUpload.getSeriesKey(
            "package_1.0.tar.gz"))
        self.assertIsNone(DistUpgraderUpload.getSeriesKey(
            "one_two_three_four_5.tar.gz"))
