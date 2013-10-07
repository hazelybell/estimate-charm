# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test ChangesFile functionality."""

__metaclass__ = type

import os

from debian.deb822 import Changes
from testtools.matchers import MatchesStructure
from zope.component import getUtility

from lp.archiveuploader.changesfile import (
    CannotDetermineFileTypeError,
    ChangesFile,
    determine_file_class_and_name,
    )
from lp.archiveuploader.dscfile import DSCFile
from lp.archiveuploader.nascentuploadfile import (
    DdebBinaryUploadFile,
    DebBinaryUploadFile,
    SourceUploadFile,
    UdebBinaryUploadFile,
    UploadError,
    )
from lp.archiveuploader.tests import (
    AbsolutelyAnythingGoesUploadPolicy,
    datadir,
    )
from lp.archiveuploader.uploadpolicy import InsecureUploadPolicy
from lp.archiveuploader.utils import merge_file_lists
from lp.registry.interfaces.person import IPersonSet
from lp.services.log.logger import BufferLogger
from lp.testing import TestCase
from lp.testing.gpgkeys import import_public_test_keys
from lp.testing.keyserver import KeyServerTac
from lp.testing.layers import (
    LaunchpadZopelessLayer,
    ZopelessDatabaseLayer,
    )


class TestDetermineFileClassAndName(TestCase):

    def testSourceFile(self):
        # A non-DSC source file is a SourceUploadFile.
        self.assertEquals(
            ('foo', SourceUploadFile),
            determine_file_class_and_name('foo_1.0.diff.gz'))

    def testDSCFile(self):
        # A DSC is a DSCFile, since they're special.
        self.assertEquals(
            ('foo', DSCFile),
            determine_file_class_and_name('foo_1.0.dsc'))

    def testDEBFile(self):
        # A binary file is the appropriate PackageUploadFile subclass.
        self.assertEquals(
            ('foo', DebBinaryUploadFile),
            determine_file_class_and_name('foo_1.0_all.deb'))
        self.assertEquals(
            ('foo', DdebBinaryUploadFile),
            determine_file_class_and_name('foo_1.0_all.ddeb'))
        self.assertEquals(
            ('foo', UdebBinaryUploadFile),
            determine_file_class_and_name('foo_1.0_all.udeb'))

    def testUnmatchingFile(self):
        # Files with unknown extensions or none at all are not
        # identified.
        self.assertRaises(
            CannotDetermineFileTypeError,
            determine_file_class_and_name,
            'foo_1.0.notdsc')
        self.assertRaises(
            CannotDetermineFileTypeError,
            determine_file_class_and_name,
            'foo')


class TestMergeFileLists(TestCase):

    def test_all_hashes(self):
        # merge_file_lists returns a list of
        # (filename, {algo: hash}, size, component_and_section, priority).
        files = [
            ('a', '1', 'd', 'e', 'foo.deb'), ('b', '2', 's', 'o', 'bar.dsc')]
        checksums_sha1 = [('aa', '1', 'foo.deb'), ('bb', '2', 'bar.dsc')]
        checksums_sha256 = [('aaa', '1', 'foo.deb'), ('bbb', '2', 'bar.dsc')]
        self.assertEqual(
            [("foo.deb",
              {'MD5': 'a', 'SHA1': 'aa', 'SHA256': 'aaa'}, '1', 'd', 'e'),
             ("bar.dsc",
              {'MD5': 'b', 'SHA1': 'bb', 'SHA256': 'bbb'}, '2', 's', 'o')],
             merge_file_lists(files, checksums_sha1, checksums_sha256))

    def test_all_hashes_for_dsc(self):
        # merge_file_lists in DSC mode returns a list of
        # (filename, {algo: hash}, size).
        files = [
            ('a', '1', 'foo.deb'), ('b', '2', 'bar.dsc')]
        checksums_sha1 = [('aa', '1', 'foo.deb'), ('bb', '2', 'bar.dsc')]
        checksums_sha256 = [('aaa', '1', 'foo.deb'), ('bbb', '2', 'bar.dsc')]
        self.assertEqual(
            [("foo.deb", {'MD5': 'a', 'SHA1': 'aa', 'SHA256': 'aaa'}, '1'),
             ("bar.dsc", {'MD5': 'b', 'SHA1': 'bb', 'SHA256': 'bbb'}, '2')],
             merge_file_lists(
                 files, checksums_sha1, checksums_sha256, changes=False))

    def test_just_md5(self):
        # merge_file_lists copes with the omission of SHA1 or SHA256
        # hashes.
        files = [
            ('a', '1', 'd', 'e', 'foo.deb'), ('b', '2', 's', 'o', 'bar.dsc')]
        self.assertEqual(
            [("foo.deb", {'MD5': 'a'}, '1', 'd', 'e'),
             ("bar.dsc", {'MD5': 'b'}, '2', 's', 'o')],
             merge_file_lists(files, None, None))

    def test_duplicate_filename_is_rejected(self):
        # merge_file_lists rejects fields with duplicated filenames.
        files = [
            ('a', '1', 'd', 'e', 'foo.deb'), ('b', '2', 's', 'o', 'foo.deb')]
        self.assertRaisesWithContent(
            UploadError, "Duplicate filenames in Files field.",
            merge_file_lists, files, None, None)

    def test_differing_file_lists_are_rejected(self):
        # merge_file_lists rejects Checksums-* fields which are present
        # but have a different set of filenames.
        files = [
            ('a', '1', 'd', 'e', 'foo.deb'), ('b', '2', 's', 'o', 'bar.dsc')]
        sha1s = [('aa', '1', 'foo.deb')]
        sha256s = [('aaa', '1', 'foo.deb')]
        self.assertRaisesWithContent(
            UploadError, "Mismatch between Checksums-Sha1 and Files fields.",
            merge_file_lists, files, sha1s, None)
        self.assertRaisesWithContent(
            UploadError, "Mismatch between Checksums-Sha256 and Files fields.",
            merge_file_lists, files, None, sha256s)

    def test_differing_file_sizes_are_rejected(self):
        # merge_file_lists rejects Checksums-* fields which are present
        # but have a different set of filenames.
        files = [('a', '1', 'd', 'e', 'foo.deb')]
        sha1s = [('aa', '1', 'foo.deb')]
        sha1s_bad_size = [('aa', '2', 'foo.deb')]
        self.assertEqual(1, len(merge_file_lists(files, sha1s, None)))
        self.assertRaisesWithContent(
            UploadError, "Mismatch between Checksums-Sha1 and Files fields.",
            merge_file_lists, files, sha1s_bad_size, None)


class ChangesFileTests(TestCase):
    """Tests for ChangesFile."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(ChangesFileTests, self).setUp()
        self.logger = BufferLogger()
        self.policy = AbsolutelyAnythingGoesUploadPolicy()

    def createChangesFile(self, filename, changes):
        tempdir = self.makeTemporaryDirectory()
        path = os.path.join(tempdir, filename)
        changes_fd = open(path, "w")
        try:
            changes.dump(changes_fd)
        finally:
            changes_fd.close()
        return ChangesFile(path, self.policy, self.logger)

    def getBaseChanges(self):
        contents = Changes()
        contents["Source"] = "mypkg"
        contents["Binary"] = "binary"
        contents["Date"] = "Fri, 25 Jun 2010 11:20:22 -0600"
        contents["Architecture"] = "i386"
        contents["Version"] = "0.1"
        contents["Distribution"] = "nifty"
        contents["Maintainer"] = "Somebody"
        contents["Changes"] = "Something changed"
        contents["Description"] = "\n An awesome package."
        contents["Changed-By"] = "Somebody <somebody@ubuntu.com>"
        contents["Files"] = [{
            "md5sum": "d2bd347b3fed184fe28e112695be491c",
            "size": "1791",
            "section": "python",
            "priority": "optional",
            "name": "dulwich_0.4.1-1_i386.deb"}]
        return contents

    def test_newline_in_Binary_field(self):
        # Test that newlines in Binary: fields are accepted
        contents = self.getBaseChanges()
        contents["Binary"] = "binary1\n binary2 \n binary3"
        changes = self.createChangesFile("mypkg_0.1_i386.changes", contents)
        self.assertEqual(
            set(["binary1", "binary2", "binary3"]), changes.binaries)

    def test_checkFileName(self):
        # checkFileName() yields an UploadError if the filename is invalid.
        contents = self.getBaseChanges()
        changes = self.createChangesFile("mypkg_0.1_i386.changes", contents)
        self.assertEquals([], list(changes.checkFileName()))
        changes = self.createChangesFile("mypkg_0.1.changes", contents)
        errors = list(changes.checkFileName())
        self.assertIsInstance(errors[0], UploadError)
        self.assertEquals(1, len(errors))

    def test_filename(self):
        # Filename gets set to the basename of the changes file on disk.
        changes = self.createChangesFile(
            "mypkg_0.1_i386.changes", self.getBaseChanges())
        self.assertEquals("mypkg_0.1_i386.changes", changes.filename)

    def test_suite_name(self):
        # The suite name gets extracted from the changes file.
        changes = self.createChangesFile(
            "mypkg_0.1_i386.changes", self.getBaseChanges())
        self.assertEquals("nifty", changes.suite_name)

    def test_version(self):
        # The version gets extracted from the changes file.
        changes = self.createChangesFile(
            "mypkg_0.1_i386.changes", self.getBaseChanges())
        self.assertEquals("0.1", changes.version)

    def test_architectures(self):
        # The architectures get extracted from the changes file
        # and parsed correctly.
        changes = self.createChangesFile(
            "mypkg_0.1_i386.changes", self.getBaseChanges())
        self.assertEquals("i386", changes.architecture_line)
        self.assertEquals(set(["i386"]), changes.architectures)

    def test_source(self):
        # The source package name gets extracted from the changes file.
        changes = self.createChangesFile(
            "mypkg_0.1_i386.changes", self.getBaseChanges())
        self.assertEquals("mypkg", changes.source)

    def test_processAddresses(self):
        # processAddresses parses the changes file and sets the
        # changed_by field.
        contents = self.getBaseChanges()
        changes = self.createChangesFile(
            "mypkg_0.1_i386.changes", contents)
        self.assertEquals(None, changes.changed_by)
        errors = list(changes.processAddresses())
        self.assertEquals(0, len(errors), "Errors: %r" % errors)
        self.assertEquals(
            "Somebody <somebody@ubuntu.com>", changes.changed_by['rfc822'])

    def test_simulated_changelog(self):
        # The simulated_changelog property returns a changelog entry based on
        # the control fields.
        contents = self.getBaseChanges()
        changes = self.createChangesFile(
            "mypkg_0.1_i386.changes", contents)
        self.assertEquals([], list(changes.processAddresses()))
        self.assertEquals(
            "Something changed\n"
            " -- Somebody <somebody@ubuntu.com>   "
            "Fri, 25 Jun 2010 11:20:22 -0600",
            changes.simulated_changelog)

    def test_requires_changed_by(self):
        # A changes file is rejected if it does not have a Changed-By field.
        contents = self.getBaseChanges()
        del contents["Changed-By"]
        self.assertRaises(
            UploadError,
            self.createChangesFile, "mypkg_0.1_i386.changes", contents)

    def test_processFiles(self):
        # processFiles sets self.files to a list of NascentUploadFiles.
        contents = self.getBaseChanges()
        changes = self.createChangesFile("mypkg_0.1_i386.changes", contents)
        self.assertEqual([], list(changes.processFiles()))
        [file] = changes.files
        self.assertEqual(DebBinaryUploadFile, type(file))
        self.assertThat(
            file,
            MatchesStructure.byEquality(
                filepath=changes.dirname + "/dulwich_0.4.1-1_i386.deb",
                checksums=dict(MD5="d2bd347b3fed184fe28e112695be491c"),
                size=1791, priority_name="optional",
                component_name="main", section_name="python"))

    def test_processFiles_additional_checksums(self):
        # processFiles parses the Checksums-Sha1 and Checksums-Sha256
        # fields if present.
        contents = self.getBaseChanges()
        md5 = "d2bd347b3fed184fe28e112695be491c"
        sha1 = "378b3498ead213d35a82033a6e9196014a5ef25c"
        sha256 = (
            "39bb3bad01bf931b34f3983536c0f331e4b4e3e38fb78abfc75e5b09"
            "efd6507f")
        contents["Checksums-Sha1"] = [{
            "sha1": sha1, "size": "1791",
            "name": "dulwich_0.4.1-1_i386.deb"}]
        contents["Checksums-Sha256"] = [{
            "sha256": sha256, "size": "1791",
            "name": "dulwich_0.4.1-1_i386.deb"}]
        changes = self.createChangesFile("mypkg_0.1_i386.changes", contents)
        self.assertEqual([], list(changes.processFiles()))
        [file] = changes.files
        self.assertEqual(DebBinaryUploadFile, type(file))
        self.assertThat(
            file,
            MatchesStructure.byEquality(
                filepath=changes.dirname + "/dulwich_0.4.1-1_i386.deb",
                checksums=dict(MD5=md5, SHA1=sha1, SHA256=sha256),
                size=1791, priority_name="optional",
                component_name="main", section_name="python"))

    def test_processFiles_additional_checksums_must_match(self):
        # processFiles ensures that Files, Checksums-Sha1 and
        # Checksums-Sha256 all list the same files.
        contents = self.getBaseChanges()
        contents["Checksums-Sha1"] = [{
            "sha1": "aaa", "size": "1791", "name": "doesnotexist.deb"}]
        changes = self.createChangesFile("mypkg_0.1_i386.changes", contents)
        [error] = list(changes.processFiles())
        self.assertEqual(
            "Mismatch between Checksums-Sha1 and Files fields.", error[0])

    def test_processFiles_rejects_duplicate_filenames(self):
        # processFiles ensures that Files lists each file only once.
        contents = self.getBaseChanges()
        contents['Files'].append(contents['Files'][0])
        changes = self.createChangesFile("mypkg_0.1_i386.changes", contents)
        [error] = list(changes.processFiles())
        self.assertEqual("Duplicate filenames in Files field.", error[0])


class TestSignatureVerification(TestCase):

    layer = ZopelessDatabaseLayer

    def setUp(self):
        super(TestSignatureVerification, self).setUp()
        self.useFixture(KeyServerTac())
        import_public_test_keys()

    def test_valid_signature_accepted(self):
        # A correctly signed changes file is excepted, and all its
        # content is parsed.
        path = datadir('signatures/signed.changes')
        parsed = ChangesFile(path, InsecureUploadPolicy(), BufferLogger())
        self.assertEqual(
            getUtility(IPersonSet).getByEmail('foo.bar@canonical.com'),
            parsed.signer)
        expected = "\AFormat: 1.7\n.*foo_1.0-1.diff.gz\Z"
        self.assertTextMatchesExpressionIgnoreWhitespace(
            expected,
            parsed.parsed_content)

    def test_no_signature_rejected(self):
        # An unsigned changes file is rejected.
        path = datadir('signatures/unsigned.changes')
        self.assertRaises(
            UploadError,
            ChangesFile, path, InsecureUploadPolicy(), BufferLogger())

    def test_prefix_ignored(self):
        # A signed changes file with an unsigned prefix has only the
        # signed part parsed.
        path = datadir('signatures/prefixed.changes')
        parsed = ChangesFile(path, InsecureUploadPolicy(), BufferLogger())
        self.assertEqual(
            getUtility(IPersonSet).getByEmail('foo.bar@canonical.com'),
            parsed.signer)
        expected = "\AFormat: 1.7\n.*foo_1.0-1.diff.gz\Z"
        self.assertTextMatchesExpressionIgnoreWhitespace(
            expected,
            parsed.parsed_content)
        self.assertEqual("breezy", parsed.suite_name)
        self.assertNotIn("evil", parsed.changes_comment)
