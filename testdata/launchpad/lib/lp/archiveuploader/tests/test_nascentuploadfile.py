# Copyright 2010-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test NascentUploadFile functionality."""

__metaclass__ = type

import hashlib
import os
import subprocess

from debian.deb822 import (
    Changes,
    Dsc,
    )

from lp.archiveuploader.changesfile import ChangesFile
from lp.archiveuploader.dscfile import DSCFile
from lp.archiveuploader.nascentuploadfile import (
    CustomUploadFile,
    DebBinaryUploadFile,
    NascentUploadFile,
    UploadError,
    )
from lp.archiveuploader.tests import AbsolutelyAnythingGoesUploadPolicy
from lp.buildmaster.enums import BuildStatus
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.services.log.logger import BufferLogger
from lp.services.osutils import write_file
from lp.soyuz.enums import (
    PackagePublishingStatus,
    PackageUploadCustomFormat,
    )
from lp.testing import TestCaseWithFactory
from lp.testing.layers import (
    LaunchpadZopelessLayer,
    ZopelessDatabaseLayer,
    )


class NascentUploadFileTestCase(TestCaseWithFactory):
    """Base class for all tests of classes deriving from NascentUploadFile."""

    def setUp(self):
        super(NascentUploadFileTestCase, self).setUp()
        self.logger = BufferLogger()
        self.policy = AbsolutelyAnythingGoesUploadPolicy()
        self.distro = self.factory.makeDistribution()
        self.policy.pocket = PackagePublishingPocket.RELEASE
        self.policy.archive = self.factory.makeArchive(
            distribution=self.distro)

    def writeUploadFile(self, filename, contents):
        """Write a temporary file but with a specific filename.

        :param filename: Filename to use
        :param contents: Contents of the file
        :return: Tuple with path, md5 and size
        """
        path = os.path.join(self.makeTemporaryDirectory(), filename)
        with open(path, 'w') as f:
            f.write(contents)
        return (
            path, hashlib.md5(contents).hexdigest(),
            hashlib.sha1(contents).hexdigest(), len(contents))


class TestNascentUploadFile(NascentUploadFileTestCase):

    layer = ZopelessDatabaseLayer

    def test_checkSizeAndCheckSum_validates_size(self):
        (path, md5, sha1, size) = self.writeUploadFile('foo', 'bar')
        nuf = NascentUploadFile(
            path, dict(MD5=md5), size - 1, 'main/devel', None, None, None)
        self.assertRaisesWithContent(
            UploadError,
            'File foo mentioned in the changes has a size mismatch. 3 != 2',
            nuf.checkSizeAndCheckSum)

    def test_checkSizeAndCheckSum_validates_md5(self):
        (path, md5, sha1, size) = self.writeUploadFile('foo', 'bar')
        nuf = NascentUploadFile(
            path, dict(MD5='deadbeef'), size, 'main/devel', None, None, None)
        self.assertRaisesWithContent(
            UploadError,
            'File foo mentioned in the changes has a MD5 mismatch. '
            '37b51d194a7513e45b56f6524f2d51f2 != deadbeef',
            nuf.checkSizeAndCheckSum)

    def test_checkSizeAndCheckSum_validates_sha1(self):
        (path, md5, sha1, size) = self.writeUploadFile('foo', 'bar')
        nuf = NascentUploadFile(
            path, dict(MD5=md5, SHA1='foobar'), size, 'main/devel', None,
            None, None)
        self.assertRaisesWithContent(
            UploadError,
            'File foo mentioned in the changes has a SHA1 mismatch. '
            '62cdb7020ff920e5aa642c3d4066950dd1f01f4d != foobar',
            nuf.checkSizeAndCheckSum)


class CustomUploadFileTests(NascentUploadFileTestCase):
    """Tests for CustomUploadFile."""

    layer = LaunchpadZopelessLayer

    def createCustomUploadFile(self, filename, contents,
                               component_and_section, priority_name):
        """Simple wrapper to create a CustomUploadFile."""
        (path, md5, sha1, size) = self.writeUploadFile(filename, contents)
        uploadfile = CustomUploadFile(
            path, dict(MD5=md5), size, component_and_section, priority_name,
            self.policy, self.logger)
        return uploadfile

    def test_custom_type(self):
        # The mime type gets set according to PackageUploadCustomFormat.
        uploadfile = self.createCustomUploadFile(
            "bla.txt", "data", "main/raw-installer", "extra")
        self.assertEquals(
            PackageUploadCustomFormat.DEBIAN_INSTALLER,
            uploadfile.custom_type)

    def test_storeInDatabase(self):
        # storeInDatabase creates a library file.
        uploadfile = self.createCustomUploadFile(
            "bla.txt", "data", "main/raw-installer", "extra")
        self.assertEquals("application/octet-stream", uploadfile.content_type)
        libraryfile = uploadfile.storeInDatabase()
        self.assertEquals("bla.txt", libraryfile.filename)
        self.assertEquals("application/octet-stream", libraryfile.mimetype)

    def test_debian_installer_verify(self):
        # debian-installer uploads are required to have sensible filenames.
        uploadfile = self.createCustomUploadFile(
            "debian-installer-images_20120627_i386.tar.gz", "data",
            "main/raw-installer", "extra")
        self.assertEqual([], list(uploadfile.verify()))
        uploadfile = self.createCustomUploadFile(
            "bla.txt", "data", "main/raw-installer", "extra")
        errors = list(uploadfile.verify())
        self.assertEqual(1, len(errors))
        self.assertIsInstance(errors[0], UploadError)

    def test_no_handler_no_verify(self):
        # Uploads without special handlers have no filename checks.
        uploadfile = self.createCustomUploadFile(
            "bla.txt", "data", "main/raw-meta-data", "extra")
        self.assertEqual([], list(uploadfile.verify()))

    def test_debian_installer_auto_approved(self):
        # debian-installer uploads are auto-approved.
        uploadfile = self.createCustomUploadFile(
            "bla.txt", "data", "main/raw-installer", "extra")
        self.assertTrue(uploadfile.autoApprove())

    def test_uefi_not_auto_approved(self):
        # UEFI uploads are auto-approved.
        uploadfile = self.createCustomUploadFile(
            "bla.txt", "data", "main/raw-uefi", "extra")
        self.assertFalse(uploadfile.autoApprove())


class PackageUploadFileTestCase(NascentUploadFileTestCase):
    """Base class for all tests of classes deriving from PackageUploadFile."""

    def setUp(self):
        super(PackageUploadFileTestCase, self).setUp()
        self.policy.distroseries = self.factory.makeDistroSeries(
            distribution=self.distro)

    def getBaseChanges(self):
        contents = Changes()
        contents["Source"] = "mypkg"
        contents["Binary"] = "binary"
        contents["Architecture"] = "i386"
        contents["Version"] = "0.1"
        contents["Distribution"] = "nifty"
        contents["Description"] = "\n Foo"
        contents["Maintainer"] = "Somebody"
        contents["Changes"] = "Something changed"
        contents["Date"] = "Fri, 25 Jun 2010 11:20:22 -0600"
        contents["Urgency"] = "low"
        contents["Changed-By"] = "Seombody Else <somebody@example.com>"
        contents["Files"] = [{
            "md5sum": "d2bd347b3fed184fe28e112695be491c",
            "size": "1791",
            "section": "python",
            "priority": "optional",
            "name": "dulwich_0.4.1-1.dsc"}]
        return contents

    def createChangesFile(self, filename, changes):
        tempdir = self.makeTemporaryDirectory()
        path = os.path.join(tempdir, filename)
        with open(path, "w") as changes_fd:
            changes.dump(changes_fd)
        return ChangesFile(path, self.policy, self.logger)


class DSCFileTests(PackageUploadFileTestCase):
    """Tests for DSCFile."""

    layer = LaunchpadZopelessLayer

    def getBaseDsc(self):
        dsc = Dsc()
        dsc["Architecture"] = "all"
        dsc["Version"] = "0.42"
        dsc["Source"] = "dulwich"
        dsc["Binary"] = "python-dulwich"
        dsc["Standards-Version"] = "0.2.2"
        dsc["Maintainer"] = "Jelmer Vernooij <jelmer@ubuntu.com>"
        dsc["Files"] = [{
            "md5sum": "5e8ba79b4074e2f305ddeaf2543afe83",
            "size": "182280",
            "name": "dulwich_0.42.tar.gz"}]
        return dsc

    def createDSCFile(self, filename, dsc, component_and_section,
                      priority_name, package, version, changes):
        (path, md5, sha1, size) = self.writeUploadFile(filename, dsc.dump())
        if changes:
            self.assertEquals([], list(changes.processAddresses()))
        return DSCFile(
            path, dict(MD5=md5), size, component_and_section, priority_name,
            package, version, changes, self.policy, self.logger)

    def test_filetype(self):
        # The filetype attribute is set based on the file extension.
        dsc = self.getBaseDsc()
        uploadfile = self.createDSCFile(
            "foo.dsc", dsc, "main/net", "extra", "dulwich", "0.42", None)
        self.assertEquals(
            "text/x-debian-source-package", uploadfile.content_type)

    def test_storeInDatabase(self):
        # storeInDatabase creates a SourcePackageRelease.
        dsc = self.getBaseDsc()
        dsc["Build-Depends"] = "dpkg, bzr"
        changes = self.getBaseChanges()
        uploadfile = self.createDSCFile(
            "foo.dsc", dsc, "main/net", "extra", "dulwich", "0.42",
            self.createChangesFile("foo.changes", changes))
        uploadfile.changelog = "DUMMY"
        uploadfile.files = []
        release = uploadfile.storeInDatabase(None)
        self.assertEquals("0.42", release.version)
        self.assertEquals("dpkg, bzr", release.builddepends)

    def test_storeInDatabase_case_sensitivity(self):
        # storeInDatabase supports field names with different cases,
        # confirming to Debian policy.
        dsc = self.getBaseDsc()
        dsc["buIld-depends"] = "dpkg, bzr"
        changes = self.getBaseChanges()
        uploadfile = self.createDSCFile(
            "foo.dsc", dsc, "main/net", "extra", "dulwich", "0.42",
            self.createChangesFile("foo.changes", changes))
        uploadfile.files = []
        uploadfile.changelog = "DUMMY"
        release = uploadfile.storeInDatabase(None)
        self.assertEquals("dpkg, bzr", release.builddepends)

    def test_user_defined_fields(self):
        # storeInDatabase updates user_defined_fields.
        dsc = self.getBaseDsc()
        dsc["Python-Version"] = "2.5"
        changes = self.getBaseChanges()
        uploadfile = self.createDSCFile(
            "foo.dsc", dsc, "main/net", "extra", "dulwich", "0.42",
            self.createChangesFile("foo.changes", changes))
        uploadfile.changelog = "DUMMY"
        uploadfile.files = []
        release = uploadfile.storeInDatabase(None)
        # DSCFile lowercases the field names
        self.assertEquals(
            [["Python-Version", u"2.5"]], release.user_defined_fields)

    def test_homepage(self):
        # storeInDatabase updates homepage.
        dsc = self.getBaseDsc()
        dsc["Homepage"] = "http://samba.org/~jelmer/bzr"
        changes = self.getBaseChanges()
        uploadfile = self.createDSCFile(
            "foo.dsc", dsc, "main/net", "extra", "dulwich", "0.42",
            self.createChangesFile("foo.changes", changes))
        uploadfile.changelog = "DUMMY"
        uploadfile.files = []
        release = uploadfile.storeInDatabase(None)
        self.assertEquals(u"http://samba.org/~jelmer/bzr", release.homepage)

    def test_checkBuild(self):
        # checkBuild() verifies consistency with a build.
        build = self.factory.makeSourcePackageRecipeBuild(
            pocket=self.policy.pocket, distroseries=self.policy.distroseries,
            archive=self.policy.archive)
        dsc = self.getBaseDsc()
        uploadfile = self.createDSCFile(
            "foo.dsc", dsc, "main/net", "extra", "dulwich", "0.42",
            self.createChangesFile("foo.changes", self.getBaseChanges()))
        uploadfile.checkBuild(build)
        # checkBuild() sets the build status to FULLYBUILT and
        # removes the upload log.
        self.assertEquals(BuildStatus.FULLYBUILT, build.status)
        self.assertIs(None, build.upload_log)

    def test_checkBuild_inconsistent(self):
        # checkBuild() raises UploadError if inconsistencies between build
        # and upload file are found.
        build = self.factory.makeSourcePackageRecipeBuild(
            pocket=self.policy.pocket,
            distroseries=self.factory.makeDistroSeries(),
            archive=self.policy.archive)
        dsc = self.getBaseDsc()
        uploadfile = self.createDSCFile(
            "foo.dsc", dsc, "main/net", "extra", "dulwich", "0.42",
            self.createChangesFile("foo.changes", self.getBaseChanges()))
        self.assertRaises(UploadError, uploadfile.checkBuild, build)


class DebBinaryUploadFileTests(PackageUploadFileTestCase):
    """Tests for DebBinaryUploadFile."""

    layer = LaunchpadZopelessLayer

    def getBaseControl(self):
        return {
            "Package": "python-dulwich",
            "Source": "dulwich",
            "Version": "0.42",
            "Architecture": "i386",
            "Maintainer": "Jelmer Vernooij <jelmer@debian.org>",
            "Installed-Size": "524",
            "Depends": "python (<< 2.7), python (>= 2.5)",
            "Provides": "python2.5-dulwich, python2.6-dulwich",
            "Section": "python",
            "Priority": "optional",
            "Homepage": "http://samba.org/~jelmer/dulwich",
            "Description": "Pure-python Git library\n"
                "Dulwich is a Python implementation of the file formats and "
                "protocols",
            }

    def createDeb(self, filename, data_format):
        """Return the contents of a dummy .deb file."""
        tempdir = self.makeTemporaryDirectory()
        members = [
            "debian-binary",
            "control.tar.gz",
            "data.tar.%s" % data_format,
            ]
        for member in members:
            write_file(os.path.join(tempdir, member), "")
        retcode = subprocess.call(
            ["ar", "rc", filename] + members, cwd=tempdir)
        self.assertEqual(0, retcode)
        with open(os.path.join(tempdir, filename)) as f:
            return f.read()

    def createDebBinaryUploadFile(self, filename, component_and_section,
                                  priority_name, package, version, changes,
                                  data_format=None):
        """Create a DebBinaryUploadFile."""
        if data_format:
            data = self.createDeb(filename, data_format)
        else:
            data = "DUMMY DATA"
        (path, md5, sha1, size) = self.writeUploadFile(filename, data)
        return DebBinaryUploadFile(
            path, dict(MD5=md5), size, component_and_section, priority_name,
            package, version, changes, self.policy, self.logger)

    def test_unknown_priority(self):
        # Unknown priorities automatically get changed to 'extra'.
        uploadfile = self.createDebBinaryUploadFile(
            "foo_0.42_i386.deb", "main/net", "unknown", "mypkg", "0.42", None)
        self.assertEquals("extra", uploadfile.priority_name)

    def test_parseControl(self):
        # parseControl sets various fields on DebBinaryUploadFile.
        uploadfile = self.createDebBinaryUploadFile(
            "foo_0.42_i386.deb", "main/python", "unknown", "mypkg", "0.42",
            None)
        control = self.getBaseControl()
        uploadfile.parseControl(control)
        self.assertEquals("python", uploadfile.section_name)
        self.assertEquals("dulwich", uploadfile.source_name)
        self.assertEquals("0.42", uploadfile.source_version)
        self.assertEquals("0.42", uploadfile.control_version)

    def test_verifyFormat_xz(self):
        # verifyFormat accepts xz-compressed .debs.
        uploadfile = self.createDebBinaryUploadFile(
            "foo_0.42_i386.deb", "main/python", "unknown", "mypkg", "0.42",
            None, data_format="xz")
        control = self.getBaseControl()
        uploadfile.parseControl(control)
        self.assertEqual([], list(uploadfile.verifyFormat()))

    def test_storeInDatabase(self):
        # storeInDatabase creates a BinaryPackageRelease.
        uploadfile = self.createDebBinaryUploadFile(
            "foo_0.42_i386.deb", "main/python", "unknown", "mypkg", "0.42",
            None)
        control = self.getBaseControl()
        uploadfile.parseControl(control)
        build = self.factory.makeBinaryPackageBuild()
        bpr = uploadfile.storeInDatabase(build)
        self.assertEquals(u'python (<< 2.7), python (>= 2.5)', bpr.depends)
        self.assertEquals(
            u"Dulwich is a Python implementation of the file formats "
            u"and protocols", bpr.description)
        self.assertEquals(False, bpr.essential)
        self.assertEquals(524, bpr.installedsize)
        self.assertEquals(True, bpr.architecturespecific)
        self.assertEquals(u"", bpr.recommends)
        self.assertEquals("0.42", bpr.version)

    def test_user_defined_fields(self):
        # storeInDatabase stores user defined fields.
        uploadfile = self.createDebBinaryUploadFile(
            "foo_0.42_i386.deb", "main/python", "unknown", "mypkg", "0.42",
            None)
        control = self.getBaseControl()
        control["Python-Version"] = "2.5"
        uploadfile.parseControl(control)
        build = self.factory.makeBinaryPackageBuild()
        bpr = uploadfile.storeInDatabase(build)
        self.assertEquals(
            [[u"Python-Version", u"2.5"]], bpr.user_defined_fields)

    def test_user_defined_fields_newlines(self):
        # storeInDatabase stores user defined fields and keeps newlines.
        uploadfile = self.createDebBinaryUploadFile(
            "foo_0.42_i386.deb", "main/python", "unknown", "mypkg", "0.42",
            None)
        control = self.getBaseControl()
        control["RandomData"] = "Foo\nbar\nbla\n"
        uploadfile.parseControl(control)
        build = self.factory.makeBinaryPackageBuild()
        bpr = uploadfile.storeInDatabase(build)
        self.assertEquals(
            [
                [u"RandomData", u"Foo\nbar\nbla\n"],
            ], bpr.user_defined_fields)

    def test_homepage(self):
        # storeInDatabase stores homepage field.
        uploadfile = self.createDebBinaryUploadFile(
            "foo_0.42_i386.deb", "main/python", "unknown", "mypkg", "0.42",
            None)
        control = self.getBaseControl()
        control["Python-Version"] = "2.5"
        uploadfile.parseControl(control)
        build = self.factory.makeBinaryPackageBuild()
        bpr = uploadfile.storeInDatabase(build)
        self.assertEquals(
            u"http://samba.org/~jelmer/dulwich", bpr.homepage)

    def test_checkBuild(self):
        # checkBuild() verifies consistency with a build.
        das = self.factory.makeDistroArchSeries(
            distroseries=self.policy.distroseries, architecturetag="i386")
        build = self.factory.makeBinaryPackageBuild(
            distroarchseries=das,
            archive=self.policy.archive)
        uploadfile = self.createDebBinaryUploadFile(
            "foo_0.42_i386.deb", "main/python", "unknown", "mypkg", "0.42",
            None)
        uploadfile.checkBuild(build)
        # checkBuild() sets the build status to FULLYBUILT and
        # removes the upload log.
        self.assertEquals(BuildStatus.FULLYBUILT, build.status)
        self.assertIs(None, build.upload_log)

    def test_checkBuild_inconsistent(self):
        # checkBuild() raises UploadError if inconsistencies between build
        # and upload file are found.
        das = self.factory.makeDistroArchSeries(
            distroseries=self.policy.distroseries, architecturetag="amd64")
        build = self.factory.makeBinaryPackageBuild(
            distroarchseries=das,
            archive=self.policy.archive)
        uploadfile = self.createDebBinaryUploadFile(
            "foo_0.42_i386.deb", "main/python", "unknown", "mypkg", "0.42",
            None)
        self.assertRaises(UploadError, uploadfile.checkBuild, build)

    def test_findSourcePackageRelease(self):
        # findSourcePackageRelease finds the matching SourcePackageRelease.
        das = self.factory.makeDistroArchSeries(
            distroseries=self.policy.distroseries, architecturetag="i386")
        self.factory.makeBinaryPackageBuild(
            distroarchseries=das,
            archive=self.policy.archive)
        uploadfile = self.createDebBinaryUploadFile(
            "foo_0.42_i386.deb", "main/python", "unknown", "mypkg", "0.42",
            None)
        spph = self.factory.makeSourcePackagePublishingHistory(
            sourcepackagename=self.factory.makeSourcePackageName("foo"),
            distroseries=self.policy.distroseries,
            version="0.42", archive=self.policy.archive)
        control = self.getBaseControl()
        control["Source"] = "foo"
        uploadfile.parseControl(control)
        self.assertEquals(
            spph.sourcepackagerelease, uploadfile.findSourcePackageRelease())

    def test_findSourcePackageRelease_no_spph(self):
        # findSourcePackageRelease raises UploadError if there is no
        # SourcePackageRelease.
        das = self.factory.makeDistroArchSeries(
            distroseries=self.policy.distroseries, architecturetag="i386")
        self.factory.makeBinaryPackageBuild(
            distroarchseries=das,
            archive=self.policy.archive)
        uploadfile = self.createDebBinaryUploadFile(
            "foo_0.42_i386.deb", "main/python", "unknown", "mypkg", "0.42",
            None)
        control = self.getBaseControl()
        control["Source"] = "foo"
        uploadfile.parseControl(control)
        self.assertRaises(UploadError, uploadfile.findSourcePackageRelease)

    def test_findSourcePackageRelease_multiple_sprs(self):
        # findSourcePackageRelease finds the last uploaded
        # SourcePackageRelease and can deal with multiple pending source
        # package releases.
        das = self.factory.makeDistroArchSeries(
            distroseries=self.policy.distroseries, architecturetag="i386")
        self.factory.makeBinaryPackageBuild(
            distroarchseries=das,
            archive=self.policy.archive)
        uploadfile = self.createDebBinaryUploadFile(
            "foo_0.42_i386.deb", "main/python", "unknown", "mypkg", "0.42",
            None)
        spn = self.factory.makeSourcePackageName("foo")
        self.factory.makeSourcePackagePublishingHistory(
            sourcepackagename=spn,
            distroseries=self.policy.distroseries,
            version="0.42", archive=self.policy.archive,
            status=PackagePublishingStatus.PUBLISHED)
        spph2 = self.factory.makeSourcePackagePublishingHistory(
            sourcepackagename=spn,
            distroseries=self.policy.distroseries,
            version="0.42", archive=self.policy.archive,
            status=PackagePublishingStatus.PENDING)
        control = self.getBaseControl()
        control["Source"] = "foo"
        uploadfile.parseControl(control)
        self.assertEquals(
            spph2.sourcepackagerelease, uploadfile.findSourcePackageRelease())
