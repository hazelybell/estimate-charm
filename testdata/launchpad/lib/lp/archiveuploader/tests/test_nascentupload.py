# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test NascentUpload functionality."""

__metaclass__ = type

from testtools import TestCase
from testtools.matchers import MatchesStructure

from lp.archiveuploader.changesfile import determine_file_class_and_name
from lp.archiveuploader.nascentupload import (
    EarlyReturnUploadError,
    NascentUpload,
    )
from lp.archiveuploader.tests import (
    datadir,
    getPolicy,
    )
from lp.archiveuploader.uploadpolicy import ArchiveUploadType
from lp.services.log.logger import DevNullLogger
from lp.testing.layers import (
    LaunchpadZopelessLayer,
    ZopelessDatabaseLayer,
    )


class FakeChangesFile:

    def __init__(self):
        self.files = []


class TestMatchDDEBs(TestCase):
    """Tests that NascentUpload correctly links DEBs to their DDEBs.

    Also verifies detection of DDEB-related error cases.
    """

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestMatchDDEBs, self).setUp()
        self.changes = FakeChangesFile()
        self.upload = NascentUpload(self.changes, None, DevNullLogger())

    def addFile(self, filename, comp_and_section='main/devel',
                priority='extra'):
        """Add a file of the right type to the upload."""
        package, cls = determine_file_class_and_name(filename)
        file = cls(
            filename, None, 100, comp_and_section, priority, package, '666',
            self.changes, None, self.upload.logger)
        self.changes.files.append(file)
        return file

    def assertMatchDDEBErrors(self, error_list):
        self.assertEquals(
            error_list, [str(e) for e in self.upload._matchDDEBs()])

    def testNoLinksWithNoBinaries(self):
        # No links will be made if there are no binaries whatsoever.
        self.addFile('something_1.0.diff.gz')
        self.assertMatchDDEBErrors([])

    def testNoLinksWithJustDEBs(self):
        # No links will be made if there are no DDEBs.
        self.addFile('blah_1.0_all.deb')
        self.addFile('libblah_1.0_i386.deb')
        self.assertMatchDDEBErrors([])
        for file in self.changes.files:
            self.assertIs(None, file.ddeb_file)

    def testLinksMatchingDDEBs(self):
        # DDEBs will be linked to their matching DEBs.
        self.addFile('blah_1.0_all.deb')
        self.addFile('libblah_1.0_i386.deb')
        self.addFile('libblah-dbgsym_1.0_i386.ddeb')
        self.addFile('libfooble_1.0_i386.udeb')
        self.addFile('libfooble-dbgsym_1.0_i386.ddeb')
        self.assertMatchDDEBErrors([])
        self.assertIs(None, self.changes.files[0].ddeb_file)
        self.assertIs(self.changes.files[2], self.changes.files[1].ddeb_file)
        self.assertIs(self.changes.files[1], self.changes.files[2].deb_file)
        self.assertIs(None, self.changes.files[2].ddeb_file)

    def testDuplicateDDEBsCauseErrors(self):
        # An error will be raised if a DEB has more than one matching
        # DDEB.
        self.addFile('libblah_1.0_i386.deb')
        self.addFile('libblah-dbgsym_1.0_i386.ddeb')
        self.addFile('libblah-dbgsym_1.0_i386.ddeb')
        self.assertMatchDDEBErrors(
            ['Duplicated debug packages: libblah-dbgsym 666 (i386)'])

    def testMismatchedDDEBsCauseErrors(self):
        # An error will be raised if a DDEB has no matching DEB.
        self.addFile('libblah_1.0_i386.deb')
        self.addFile('libblah-dbgsym_1.0_amd64.ddeb')
        self.assertMatchDDEBErrors(
            ['Orphaned debug packages: libblah-dbgsym 666 (amd64)'])


class TestOverrideDDEBs(TestMatchDDEBs):

    def test_DDEBsGetOverrideFromDEBs(self):
        # Test the basic case ensuring that DDEB files always match the
        # DEB's overrides.
        deb = self.addFile("foo_1.0_i386.deb", "main/devel", "extra")
        ddeb = self.addFile(
            "foo-dbgsym_1.0_i386.ddeb", "universe/web",  "low")
        self.assertMatchDDEBErrors([])
        self.upload._overrideDDEBSs()

        self.assertThat(
            ddeb,
            MatchesStructure.fromExample(
                deb, "component_name", "section_name", "priority_name"))


class TestNascentUpload(TestCase):

    layer = ZopelessDatabaseLayer

    def test_hash_mismatch_rejects(self):
        # A hash mismatch for any uploaded file will cause the upload to
        # be rejected.
        policy = getPolicy(
            name="sync", distro="ubuntu", distroseries="hoary")
        policy.accepted_type = ArchiveUploadType.BINARY_ONLY
        upload = NascentUpload.from_changesfile_path(
            datadir("suite/badhash_1.0-1/badhash_1.0-1_i386.changes"),
            policy, DevNullLogger())
        upload.process()
        self.assertTrue(upload.is_rejected)
        self.assertEqual(
            'File badhash_1.0-1_i386.deb mentioned in the changes has a SHA1 '
            'mismatch. 2ca33cf32a45852c62b465aaf9063fb7deb31725 != '
            '91556113ad38eb35d2fe03d27ae646e0ed487a3d',
            upload.rejection_message)
