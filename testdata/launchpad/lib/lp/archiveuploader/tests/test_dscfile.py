# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test dscfile.py"""

__metaclass__ = type

from collections import namedtuple
import os

from lp.archiveuploader.dscfile import (
    cleanup_unpacked_dir,
    DSCFile,
    find_changelog,
    find_copyright,
    format_to_file_checker_map,
    SignableTagFile,
    unpack_source,
    )
from lp.archiveuploader.nascentuploadfile import UploadError
from lp.archiveuploader.tests import (
    datadir,
    getPolicy,
    )
from lp.archiveuploader.uploadpolicy import BuildDaemonUploadPolicy
from lp.registry.interfaces.sourcepackage import SourcePackageFileType
from lp.registry.model.person import Person
from lp.services.log.logger import (
    BufferLogger,
    DevNullLogger,
    )
from lp.soyuz.enums import SourcePackageFormat
from lp.testing import (
    TestCase,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    LaunchpadZopelessLayer,
    ZopelessDatabaseLayer,
    )


ORIG_TARBALL = SourcePackageFileType.ORIG_TARBALL
DEBIAN_TARBALL = SourcePackageFileType.DEBIAN_TARBALL
NATIVE_TARBALL = SourcePackageFileType.NATIVE_TARBALL
DIFF = SourcePackageFileType.DIFF


class TestDscFile(TestCase):

    def setUp(self):
        super(TestDscFile, self).setUp()
        self.tmpdir = self.makeTemporaryDirectory()
        self.dir_path = os.path.join(self.tmpdir, "foo", "debian")
        os.makedirs(self.dir_path)
        self.copyright_path = os.path.join(self.dir_path, "copyright")
        self.changelog_path = os.path.join(self.dir_path, "changelog")

    def testBadDebianCopyright(self):
        """Test that a symlink as debian/copyright will fail.

        This is a security check, to make sure its not possible to use a
        dangling symlink in an attempt to try and access files on the system
        processing the source packages."""
        os.symlink("/etc/passwd", self.copyright_path)
        error = self.assertRaises(
            UploadError, find_copyright, self.tmpdir, DevNullLogger())
        self.assertEqual(
            error.args[0], "Symbolic link for debian/copyright not allowed")

    def testGoodDebianCopyright(self):
        """Test that a proper copyright file will be accepted"""
        copyright = "copyright for dummies"
        file = open(self.copyright_path, "w")
        file.write(copyright)
        file.close()

        self.assertEquals(
            copyright, find_copyright(self.tmpdir, DevNullLogger()))

    def testBadDebianChangelog(self):
        """Test that a symlink as debian/changelog will fail.

        This is a security check, to make sure its not possible to use a
        dangling symlink in an attempt to try and access files on the system
        processing the source packages."""
        os.symlink("/etc/passwd", self.changelog_path)
        error = self.assertRaises(
            UploadError, find_changelog, self.tmpdir, DevNullLogger())
        self.assertEqual(
            error.args[0], "Symbolic link for debian/changelog not allowed")

    def testGoodDebianChangelog(self):
        """Test that a proper changelog file will be accepted"""
        changelog = "changelog for dummies"
        file = open(self.changelog_path, "w")
        file.write(changelog)
        file.close()

        self.assertEquals(
            changelog, find_changelog(self.tmpdir, DevNullLogger()))

    def testOversizedFile(self):
        """Test that a file larger than 10MiB will fail.

        This check exists to prevent a possible denial of service attack
        against launchpad by overloaded the database or librarian with massive
        changelog and copyright files. 10MiB was set as a sane lower limit
        which is incredibly unlikely to be hit by normal files in the
        archive"""
        dev_zero = open("/dev/zero", "r")
        ten_MiB = 10 * (2 ** 20)
        empty_file = dev_zero.read(ten_MiB + 1)
        dev_zero.close()

        file = open(self.changelog_path, "w")
        file.write(empty_file)
        file.close()

        error = self.assertRaises(
            UploadError, find_changelog, self.tmpdir, DevNullLogger())
        self.assertEqual(
            error.args[0], "debian/changelog file too large, 10MiB max")


class FakeChangesFile:
    architectures = ['source']


class TestDSCFileWithDatabase(TestCaseWithFactory):

    layer = ZopelessDatabaseLayer

    def test_checkFiles_verifies_additional_hashes(self):
        """Test that checkFiles detects SHA1 and SHA256 mismatches."""
        policy = getPolicy(
            name="sync", distro="ubuntu", distroseries="hoary")
        path = datadir(os.path.join(
            'suite', 'badhash_1.0-1_broken_dsc', 'badhash_1.0-1.dsc'))
        dsc = DSCFile(
            path, {}, 426, 'main/editors', 'priority',
            'badhash', '1.0-1', FakeChangesFile(), policy, DevNullLogger())
        errors = [e[0] for e in dsc.verify()]
        self.assertEqual(
            ['File badhash_1.0-1.tar.gz mentioned in the changes has a SHA256'
             ' mismatch. a29ec2370df83193c3fb2cc9e1287dbfe9feba04108ccfa490bb'
             'e20ea66f3d08 != aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
             'aaaaaaaaaaaaaaaaa',
             'Files specified in DSC are broken or missing, skipping package '
             'unpack verification.'],
            errors)


class TestSignableTagFile(TestCaseWithFactory):
    """Test `SignableTagFile`, a helper mixin."""

    layer = ZopelessDatabaseLayer

    def makeSignableTagFile(self):
        """Create a minimal `SignableTagFile` object."""
        FakePolicy = namedtuple(
            'FakePolicy',
            ['pocket', 'distroseries', 'create_people'])
        tagfile = SignableTagFile()
        tagfile.logger = DevNullLogger()
        tagfile.policy = FakePolicy(None, None, create_people=True)
        tagfile._dict = {
            'Source': 'arbitrary-source-package-name',
            'Version': '1.0',
            }
        return tagfile

    def test_parseAddress_finds_addressee(self):
        tagfile = self.makeSignableTagFile()
        email = self.factory.getUniqueEmailAddress()
        person = self.factory.makePerson(email=email)
        self.assertEqual(person, tagfile.parseAddress(email)['person'])

    def test_parseAddress_creates_addressee_for_unknown_address(self):
        unknown_email = self.factory.getUniqueEmailAddress()
        results = self.makeSignableTagFile().parseAddress(unknown_email)
        self.assertEqual(unknown_email, results['email'])
        self.assertIsInstance(results['person'], Person)

    def test_parseAddress_raises_UploadError_if_address_is_malformed(self):
        self.assertRaises(
            UploadError,
            self.makeSignableTagFile().parseAddress, "invalid@bad-address")


class TestDscFileLibrarian(TestCaseWithFactory):
    """Tests for DscFile that may use the Librarian."""

    layer = LaunchpadZopelessLayer

    def getDscFile(self, name):
        dsc_path = datadir(os.path.join('suite', name, name + '.dsc'))

        class Changes:
            architectures = ['source']
        logger = BufferLogger()
        policy = BuildDaemonUploadPolicy()
        policy.distroseries = self.factory.makeDistroSeries()
        policy.archive = self.factory.makeArchive()
        policy.distro = policy.distroseries.distribution
        return DSCFile(dsc_path, {}, 0, 'main/editors',
            'priority', 'package', 'version', Changes, policy, logger)

    def test_ReadOnlyCWD(self):
        """Processing a file should work when cwd is read-only."""
        tempdir = self.useTempDir()
        os.chmod(tempdir, 0555)
        try:
            dsc_file = self.getDscFile('bar_1.0-1')
            list(dsc_file.verify())
        finally:
            os.chmod(tempdir, 0755)


class BaseTestSourceFileVerification(TestCase):

    def assertErrorsForFiles(self, expected, files, components={},
                             bzip2_count=0, xz_count=0):
        """Check problems with the given set of files for the given format.

        :param expected: a list of expected errors, as strings.
        :param format: the `SourcePackageFormat` to check against.
        :param files: a dict mapping `SourcePackageFileType`s to counts.
        :param components: a dict mapping orig component tarball components
            to counts.
        :param bzip2_count: number of files using bzip2 compression.
        :param xz_count: number of files using xz compression.
        """
        full_files = {
            NATIVE_TARBALL: 0,
            ORIG_TARBALL: 0,
            DIFF: 0,
            DEBIAN_TARBALL: 0,
            }
        full_files.update(files)
        self.assertEquals(
            expected,
            [str(e) for e in format_to_file_checker_map[self.format](
                'foo_1.dsc', full_files, components, bzip2_count, xz_count)])

    def assertFilesOK(self, files, components={}, bzip2_count=0, xz_count=0):
        """Check that the given set of files is OK for the given format.

        :param format: the `SourcePackageFormat` to check against.
        :param files: a dict mapping `SourcePackageFileType`s to counts.
        :param components: a dict mapping orig component tarball components
            to counts.
        :param bzip2_count: number of files using bzip2 compression.
        :param xz_count: number of files using xz compression.
        """
        self.assertErrorsForFiles(
            [], files, components, bzip2_count, xz_count)


class Test10SourceFormatVerification(BaseTestSourceFileVerification):

    format = SourcePackageFormat.FORMAT_1_0

    wrong_files_error = ('foo_1.dsc: must have exactly one tar.gz, or an '
                         'orig.tar.gz and diff.gz')
    bzip2_error = 'foo_1.dsc: is format 1.0 but uses bzip2 compression.'
    xz_error = 'foo_1.dsc: is format 1.0 but uses xz compression.'

    def testFormat10Debian(self):
        # A 1.0 source can contain an original tarball and a Debian diff
        self.assertFilesOK({ORIG_TARBALL: 1, DIFF: 1})

    def testFormat10Native(self):
        # A 1.0 source can contain a native tarball.
        self.assertFilesOK({NATIVE_TARBALL: 1})

    def testFormat10CannotHaveWrongFiles(self):
        # A 1.0 source cannot have a combination of native and
        # non-native files, and cannot have just one of the non-native
        # files.
        for combination in (
            {DIFF: 1}, {ORIG_TARBALL: 1}, {ORIG_TARBALL: 1, DIFF: 1,
            NATIVE_TARBALL: 1}):
            self.assertErrorsForFiles([self.wrong_files_error], combination)

        # A 1.0 source with component tarballs is invalid.
        self.assertErrorsForFiles(
            [self.wrong_files_error], {ORIG_TARBALL: 1, DIFF: 1}, {'foo': 1})

    def testFormat10CannotUseBzip2(self):
        # 1.0 sources cannot use bzip2 compression.
        self.assertErrorsForFiles(
            [self.bzip2_error], {NATIVE_TARBALL: 1}, {}, 1, 0)

    def testFormat10CannotUseXz(self):
        # 1.0 sources cannot use xz compression.
        self.assertErrorsForFiles(
            [self.xz_error], {NATIVE_TARBALL: 1}, {}, 0, 1)


class Test30QuiltSourceFormatVerification(BaseTestSourceFileVerification):

    format = SourcePackageFormat.FORMAT_3_0_QUILT

    wrong_files_error = ('foo_1.dsc: must have only an orig.tar.*, a '
                         'debian.tar.* and optionally orig-*.tar.*')
    comp_conflict_error = 'foo_1.dsc: has more than one orig-bar.tar.*.'

    def testFormat30Quilt(self):
        # A 3.0 (quilt) source must contain an orig tarball and a debian
        # tarball. It may also contain at most one component tarball for
        # each component, and can use gzip, bzip2, or xz compression.
        for components in ({}, {'foo': 1}, {'foo': 1, 'bar': 1}):
            for bzip2_count in (0, 1):
                for xz_count in (0, 1):
                    self.assertFilesOK(
                        {ORIG_TARBALL: 1, DEBIAN_TARBALL: 1}, components,
                        bzip2_count, xz_count)

    def testFormat30QuiltCannotHaveConflictingComponentTarballs(self):
        # Multiple conflicting tarballs for a single component are
        # invalid.
        self.assertErrorsForFiles(
            [self.comp_conflict_error],
            {ORIG_TARBALL: 1, DEBIAN_TARBALL: 1}, {'foo': 1, 'bar': 2})

    def testFormat30QuiltCannotHaveWrongFiles(self):
        # 3.0 (quilt) sources may not have a diff or native tarball.
        for filetype in (DIFF, NATIVE_TARBALL):
            self.assertErrorsForFiles(
                [self.wrong_files_error],
                {ORIG_TARBALL: 1, DEBIAN_TARBALL: 1, filetype: 1})


class Test30QuiltSourceFormatVerification(BaseTestSourceFileVerification):

    format = SourcePackageFormat.FORMAT_3_0_NATIVE

    wrong_files_error = 'foo_1.dsc: must have only a tar.*.'

    def testFormat30Native(self):
        # 3.0 (native) sources must contain just a native tarball. They
        # may use gzip, bzip2, or xz compression.
        for bzip2_count in (0, 1):
            self.assertFilesOK({NATIVE_TARBALL: 1}, {},
            bzip2_count, 0)
        self.assertFilesOK({NATIVE_TARBALL: 1}, {}, 0, 1)

    def testFormat30NativeCannotHaveWrongFiles(self):
        # 3.0 (quilt) sources may not have a diff, Debian tarball, orig
        # tarball, or any component tarballs.
        for filetype in (DIFF, DEBIAN_TARBALL, ORIG_TARBALL):
            self.assertErrorsForFiles(
                [self.wrong_files_error], {NATIVE_TARBALL: 1, filetype: 1})
        # A 3.0 (native) source with component tarballs is invalid.
        self.assertErrorsForFiles(
            [self.wrong_files_error], {NATIVE_TARBALL: 1}, {'foo': 1})


class UnpackedDirTests(TestCase):
    """Tests for unpack_source and cleanup_unpacked_dir."""

    def test_unpack_source(self):
        # unpack_source unpacks in a temporary directory and returns the
        # path.
        unpacked_dir = unpack_source(
            datadir(os.path.join('suite', 'bar_1.0-1', 'bar_1.0-1.dsc')))
        try:
            self.assertEquals(["bar-1.0"], os.listdir(unpacked_dir))
            self.assertContentEqual(
                ["THIS_IS_BAR", "debian"],
                os.listdir(os.path.join(unpacked_dir, "bar-1.0")))
        finally:
            cleanup_unpacked_dir(unpacked_dir)

    def test_cleanup(self):
        # cleanup_dir removes the temporary directory and all files under it.
        temp_dir = self.makeTemporaryDirectory()
        unpacked_dir = os.path.join(temp_dir, "unpacked")
        os.mkdir(unpacked_dir)
        os.mkdir(os.path.join(unpacked_dir, "bar_1.0"))
        cleanup_unpacked_dir(unpacked_dir)
        self.assertFalse(os.path.exists(unpacked_dir))

    def test_cleanup_invalid_mode(self):
        # cleanup_dir can remove a directory even if the mode does
        # not allow it.
        temp_dir = self.makeTemporaryDirectory()
        unpacked_dir = os.path.join(temp_dir, "unpacked")
        os.mkdir(unpacked_dir)
        bar_path = os.path.join(unpacked_dir, "bar_1.0")
        os.mkdir(bar_path)
        os.chmod(bar_path, 0600)
        os.chmod(unpacked_dir, 0600)
        cleanup_unpacked_dir(unpacked_dir)
        self.assertFalse(os.path.exists(unpacked_dir))
