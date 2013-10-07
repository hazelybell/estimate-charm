# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Specific models for uploaded files"""

__metaclass__ = type

__all__ = [
    'BaseBinaryUploadFile',
    'CustomUploadFile',
    'DdebBinaryUploadFile',
    'DebBinaryUploadFile',
    'NascentUploadFile',
    'PackageUploadFile',
    'SourceUploadFile',
    'UdebBinaryUploadFile',
    'splitComponentAndSection',
    ]

import hashlib
import os
import subprocess
import sys
import time

import apt_inst
import apt_pkg
from debian.deb822 import Deb822Dict
from zope.component import getUtility

from lp.app.errors import NotFoundError
from lp.archivepublisher.ddtp_tarball import DdtpTarballUpload
from lp.archivepublisher.debian_installer import DebianInstallerUpload
from lp.archivepublisher.dist_upgrader import DistUpgraderUpload
from lp.archivepublisher.uefi import UefiUpload
from lp.archiveuploader.utils import (
    determine_source_file_type,
    prefix_multi_line_string,
    re_extract_src_version,
    re_isadeb,
    re_issource,
    re_no_epoch,
    re_no_revision,
    re_taint_free,
    re_valid_pkg_name,
    re_valid_version,
    UploadError,
    )
from lp.buildmaster.enums import BuildStatus
from lp.services.encoding import guess as guess_encoding
from lp.services.librarian.interfaces import ILibraryFileAliasSet
from lp.services.librarian.utils import filechunks
from lp.soyuz.enums import (
    BinaryPackageFormat,
    PackagePublishingPriority,
    PackageUploadCustomFormat,
    )
from lp.soyuz.interfaces.binarypackagename import IBinaryPackageNameSet
from lp.soyuz.interfaces.component import IComponentSet
from lp.soyuz.interfaces.section import ISectionSet
from lp.soyuz.model.files import SourceFileMixin


apt_pkg.init_system()


class TarFileDateChecker:
    """Verify all files in a tar in a deb are within a given date range.

    This was taken from jennifer in the DAK suite.
    """

    def __init__(self, future_cutoff, past_cutoff):
        """Setup timestamp limits """
        self.reset()
        self.future_cutoff = future_cutoff
        self.past_cutoff = past_cutoff

    def reset(self):
        """Reset local values."""
        self.future_files = {}
        self.ancient_files = {}

    def callback(self, member, data):
        """Callback designed to cope with apt_inst.TarFile.go.

        It check and store timestamp details of the extracted DEB.
        """
        self.check_cutoff(member.name, member.mtime)

    def check_cutoff(self, name, mtime):
        """Check the timestamp details of the supplied file.

        Store the name of the file with its mtime timestamp if it's
        outside the required date range.
        """
        if mtime > self.future_cutoff:
            self.future_files[name] = mtime
        if mtime < self.past_cutoff:
            self.ancient_files[name] = mtime


def splitComponentAndSection(component_and_section):
    """Split the component out of the section."""
    if "/" not in component_and_section:
        return "main", component_and_section
    return component_and_section.split("/", 1)


class NascentUploadFile:
    """A nascent uploaded file is a file on disk that is part of an upload.

    The filename, along with information about it, is kept here.
    """
    new = False

    # Files need their content type for creating in the librarian.
    # This maps endings of filenames onto content types we may encounter
    # in the processing of an upload.
    filename_ending_content_type_map = {
        ".dsc": "text/x-debian-source-package",
        ".deb": "application/x-debian-package",
        ".udeb": "application/x-micro-debian-package",
        ".diff.gz": "application/gzipped-patch",
        ".tar.gz": "application/gzipped-tar",
        }

    def __init__(self, filepath, checksums, size, component_and_section,
                 priority_name, policy, logger):
        self.filepath = filepath
        self.checksums = checksums
        self.priority_name = priority_name
        self.policy = policy
        self.logger = logger

        self.size = int(size)
        self.component_name, self.section_name = (
            splitComponentAndSection(component_and_section))

        self.librarian = getUtility(ILibraryFileAliasSet)

    #
    # Helpers used quen inserting into queue
    #
    @property
    def content_type(self):
        """The content type for this file.

        Return a value ready for adding to the librarian.
        """
        for content_type_map in self.filename_ending_content_type_map.items():
            ending, content_type = content_type_map
            if self.filename.endswith(ending):
                return content_type
        return "application/octet-stream"

    #
    # Useful properties.
    #
    @property
    def filename(self):
        """Return the NascentUpload filename."""
        return os.path.basename(self.filepath)

    @property
    def dirname(self):
        """Return the NascentUpload filename."""
        return os.path.dirname(self.filepath)

    @property
    def exists_on_disk(self):
        """Whether or not the file is present on disk."""
        return os.path.exists(self.filepath)

    #
    # DB storage helpers
    #
    def storeInDatabase(self):
        """Implement this to store this representation in the database."""
        raise NotImplementedError

    #
    # Verification
    #
    def verify(self):
        """Implemented locally.

        It does specific checks acording the subclass type and returns
        an iterator over all the encountered errors and warnings.
        """
        raise NotImplementedError

    def checkNameIsTaintFree(self):
        """Verify if the filename contains forbidden characters."""
        if not re_taint_free.match(self.filename):
            raise UploadError(
                "Invalid character(s) in filename: '%s'." % self.filename)

    def checkSizeAndCheckSum(self):
        """Check the size and checksums of the nascent file.

        Raise UploadError if the size or checksums do not match or if the
        file is not found on the disk.
        """
        if not self.exists_on_disk:
            raise UploadError(
                "File %s mentioned in the changes file was not found."
                % self.filename)

        # Read in the file and compute its md5 and sha1 checksums and remember
        # the size of the file as read-in.
        digesters = dict((n, hashlib.new(n)) for n in self.checksums.keys())
        ckfile = open(self.filepath, "r")
        size = 0
        for chunk in filechunks(ckfile):
            for digester in digesters.itervalues():
                digester.update(chunk)
            size += len(chunk)
        ckfile.close()

        # Check the size and checksum match what we were told in __init__
        for n in sorted(self.checksums.keys()):
            if digesters[n].hexdigest() != self.checksums[n]:
                raise UploadError(
                    "File %s mentioned in the changes has a %s mismatch. "
                    "%s != %s" % (
                        self.filename, n, digesters[n].hexdigest(),
                        self.checksums[n]))
        if size != self.size:
            raise UploadError(
                "File %s mentioned in the changes has a size mismatch. "
                "%s != %s" % (self.filename, size, self.size))


class CustomUploadFile(NascentUploadFile):
    """NascentUpload file for Custom uploads.

    Custom uploads are anything else than source or binaries that are meant
    to be published in the archive.

    They are usually Tarballs which are processed according its type and
    results in new archive files.
    """

    # This is a marker as per the comment in lib/lp/soyuz/enums.py:
    ##CUSTOMFORMAT##
    # Essentially if you change anything to do with custom formats, grep for
    # the marker in the codebase and make sure the same changes are made
    # everywhere which needs them.
    custom_sections = {
        'raw-installer': PackageUploadCustomFormat.DEBIAN_INSTALLER,
        'raw-translations': PackageUploadCustomFormat.ROSETTA_TRANSLATIONS,
        'raw-dist-upgrader': PackageUploadCustomFormat.DIST_UPGRADER,
        'raw-ddtp-tarball': PackageUploadCustomFormat.DDTP_TARBALL,
        'raw-translations-static':
            PackageUploadCustomFormat.STATIC_TRANSLATIONS,
        'raw-meta-data':
            PackageUploadCustomFormat.META_DATA,
        'raw-uefi': PackageUploadCustomFormat.UEFI,
        }

    custom_handlers = {
        PackageUploadCustomFormat.DEBIAN_INSTALLER: DebianInstallerUpload,
        PackageUploadCustomFormat.DIST_UPGRADER: DistUpgraderUpload,
        PackageUploadCustomFormat.DDTP_TARBALL: DdtpTarballUpload,
        PackageUploadCustomFormat.UEFI: UefiUpload,
        }

    @property
    def custom_type(self):
        """The custom upload type for this file. (None if not custom)."""
        return self.custom_sections[self.section_name]

    def verify(self):
        """Verify CustomUploadFile.

        Simply check is the given section is allowed for custom uploads.
        It returns an iterator over all the encountered errors and warnings.
        """
        if self.section_name not in self.custom_sections:
            yield UploadError(
                "Unsupported custom section name %r" % self.section_name)
        else:
            handler = self.custom_handlers.get(
                self.custom_sections[self.section_name])
            if handler is not None:
                try:
                    handler.parsePath(self.filename)
                except ValueError:
                    yield UploadError(
                        "Invalid filename %r for section name %r" % (
                            self.filename, self.section_name))

    def storeInDatabase(self):
        """Create and return the corresponding LibraryFileAlias reference."""
        libraryfile = self.librarian.create(
            self.filename, self.size,
            open(self.filepath, "rb"),
            self.content_type,
            restricted=self.policy.archive.private)
        return libraryfile

    def autoApprove(self):
        """Return whether this custom upload can be automatically approved."""
        # UEFI uploads are signed, and must therefore be approved by a human.
        if self.custom_type == PackageUploadCustomFormat.UEFI:
            return False
        return True


class PackageUploadFile(NascentUploadFile):
    """Base class to model sources and binary files contained in a upload. """

    def __init__(self, filepath, md5, size, component_and_section,
                 priority_name, package, version, changes, policy, logger):
        """Check presence of the component and section from an uploaded_file.

        They need to satisfy at least the NEW queue constraints that includes
        SourcePackageRelease creation, so component and section need to exist.
        Even if they might be overridden in the future.
        """
        super(PackageUploadFile, self).__init__(
            filepath, md5, size, component_and_section, priority_name,
            policy, logger)
        self.package = package
        self.version = version
        self.changes = changes

        valid_components = [component.name for component in
                            getUtility(IComponentSet)]
        valid_sections = [section.name for section in getUtility(ISectionSet)]

        if self.section_name not in valid_sections:
            raise UploadError(
                "%s: Unknown section %r" % (
                self.filename, self.section_name))

        if self.component_name not in valid_components:
            raise UploadError(
                "%s: Unknown component %r" % (
                self.filename, self.component_name))

    @property
    def component(self):
        """Return an IComponent for self.component.name."""
        return getUtility(IComponentSet)[self.component_name]

    @property
    def section(self):
        """Return an ISection for self.section_name."""
        return getUtility(ISectionSet)[self.section_name]

    def checkBuild(self, build):
        """Check the status of the build this file is part of.

        :param build: an `IPackageBuild` instance
        """
        raise NotImplementedError(self.checkBuild)

    def extractUserDefinedFields(self, control):
        """Extract the user defined fields out of a control file list.
        """
        return [
            (field, contents)
            for (field, contents) in
            control if field not in self.known_fields]


class SourceUploadFile(SourceFileMixin, PackageUploadFile):
    """Files mentioned in changesfile as source (orig, diff, tar).

    This class only check consistency on information contained in
    changesfile (CheckSum, Size, component, section, filename).
    Further checks on file contents and package consistency are done
    in DSCFile.
    """

    @property
    def filetype(self):
        return determine_source_file_type(self.filename)

    def verify(self):
        """Verify the uploaded source file.

        It returns an iterator over all the encountered errors and warnings.
        """
        self.logger.debug("Verifying source file %s" % self.filename)

        if 'source' not in self.changes.architectures:
            yield UploadError("%s: changes file doesn't list 'source' in "
                "Architecture field." % (self.filename))

        version_chopped = re_no_epoch.sub('', self.version)
        if self.is_orig:
            version_chopped = re_no_revision.sub('', version_chopped)

        source_match = re_issource.match(self.filename)
        filename_version = source_match.group(2)
        if filename_version != version_chopped:
            yield UploadError("%s: should be %s according to changes file."
                % (filename_version, version_chopped))

    def checkBuild(self, build):
        """See PackageUploadFile."""
        # The master verifies the status to confirm successful upload.
        build.updateStatus(BuildStatus.FULLYBUILT)

        # Sanity check; raise an error if the build we've been
        # told to link to makes no sense.
        if (build.pocket != self.policy.pocket or
            build.distroseries != self.policy.distroseries or
            build.archive != self.policy.archive):
            raise UploadError(
                "Attempt to upload source specifying "
                "recipe build %s, where it doesn't fit." % build.id)


class BaseBinaryUploadFile(PackageUploadFile):
    """Base methods for binary upload modeling."""

    format = None
    ddeb_file = None

    # Capitalised because we extract these directly from the control file.
    mandatory_fields = set(["Package", "Architecture", "Version"])

    known_fields = mandatory_fields.union(set([
        "Depends",
        "Conflicts",
        "Breaks",
        "Recommends",
        "Suggests",
        "Replaces",
        "Provides",
        "Pre-Depends",
        "Enhances",
        "Essential",
        "Description",
        "Installed-Size",
        "Priority",
        "Section",
        "Maintainer",
        "Source",
        "Homepage",
        ]))

    # Map priorities to their dbschema valuesa
    # We treat a priority of '-' as EXTRA since some packages in some distros
    # are broken and we can't fix the world.
    priority_map = {
        "required": PackagePublishingPriority.REQUIRED,
        "important": PackagePublishingPriority.IMPORTANT,
        "standard": PackagePublishingPriority.STANDARD,
        "optional": PackagePublishingPriority.OPTIONAL,
        "extra": PackagePublishingPriority.EXTRA,
        "-": PackagePublishingPriority.EXTRA,
        }

    # These are divined when parsing the package file in verify(), and
    # then used to locate or create the relevant sources and build.
    control = None
    control_version = None
    sourcepackagerelease = None
    source_name = None
    source_version = None

    def __init__(self, filepath, md5, size, component_and_section,
                 priority_name, package, version, changes, policy, logger):

        PackageUploadFile.__init__(
            self, filepath, md5, size, component_and_section,
            priority_name, package, version, changes, policy, logger)

        if self.priority_name not in self.priority_map:
            default_priority = 'extra'
            self.logger.warn(
                 "Unable to grok priority %r, overriding it with %s"
                 % (self.priority_name, default_priority))
            self.priority_name = default_priority

        # Yeah, this is weird. Where else can I discover this without
        # unpacking the deb file, though?
        binary_match = re_isadeb.match(self.filename)
        self.architecture = binary_match.group(3)

    #
    # Useful properties.
    #
    @property
    def is_archindep(self):
        """Check if the binary is targeted to architecture 'all'.

        We call binaries in this condition 'architecture-independent', i.e.
        They can be build in any architecture and the result will fit all
        architectures available.
        """
        return self.architecture.lower() == 'all'

    @property
    def archtag(self):
        """Return the binary target architecture.

        If the binary is architecture independent, return the architecture
        of the machine that has built it (it is encoded in the changesfile
        name).
        """
        archtag = self.architecture
        if archtag == 'all':
            return self.changes.filename_archtag
        return archtag

    @property
    def priority(self):
        """Checks whether the priority indicated is valid"""
        return self.priority_map[self.priority_name]

    #
    # Binary file checks
    #
    @property
    def local_checks(self):
        """Should be implemented locally."""
        raise NotImplementedError

    def verify(self):
        """Verify the contents of the .deb or .udeb as best we can.

        It returns an iterator over all the encountered errors and warnings.
        """
        self.logger.debug("Verifying binary %s" % self.filename)

        # Run mandatory and local checks and collect errors.
        mandatory_checks = [
            self.extractAndParseControl,
            ]
        checks = mandatory_checks + self.local_checks
        for check in checks:
            for error in check():
                yield error

    def extractAndParseControl(self):
        """Extract and parse control information."""
        try:
            deb_file = apt_inst.DebFile(self.filepath)
            control_file = deb_file.control.extractdata("control")
            control_lines = apt_pkg.TagSection(control_file)
        except (SystemExit, KeyboardInterrupt):
            raise
        except:
            yield UploadError(
                "%s: extracting control file raised %s, giving up."
                 % (self.filename, sys.exc_type))
            return

        for mandatory_field in self.mandatory_fields:
            if control_lines.find(mandatory_field) is None:
                yield UploadError(
                    "%s: control file lacks mandatory field %r"
                     % (self.filename, mandatory_field))
        control = {}
        for key in control_lines.keys():
            control[key] = control_lines.find(key)
        self.parseControl(control)

    def parseControl(self, control):
        # XXX kiko 2007-02-15: We never use the Maintainer information in
        # the control file for anything. Should we? --
        self.control = control

        control_source = self.control.get("Source", None)
        if control_source is not None:
            if "(" in control_source:
                src_match = re_extract_src_version.match(control_source)
                self.source_name = src_match.group(1)
                self.source_version = src_match.group(2)
            else:
                self.source_name = control_source
                self.source_version = self.control.get("Version")
        else:
            self.source_name = self.control.get("Package")
            self.source_version = self.control.get("Version")

        # Store control_version for external use (archive version consistency
        # checks in nascentupload.py)
        self.control_version = self.control.get("Version")

    def verifyPackage(self):
        """Check if the binary is in changesfile and its name is valid."""
        control_package = self.control.get("Package", '')

        # Since DDEBs are generated after the original DEBs are processed
        # and considered by `dpkg-genchanges` they are only half-incorporated
        # the binary upload changes file. DDEBs are only listed in the
        # Files/Checksums-Sha1/ChecksumsSha256 sections and missing from
        # Binary/Description.
        if not self.filename.endswith('.ddeb'):
            if control_package not in self.changes.binaries:
                yield UploadError(
                    "%s: control file lists name as %r, which isn't in "
                    "changes file." % (self.filename, control_package))

        if not re_valid_pkg_name.match(control_package):
            yield UploadError("%s: invalid package name %r." % (
                self.filename, control_package))

        # Ensure the filename matches the contents of the .deb
        # First check the file package name matches the deb contents.
        binary_match = re_isadeb.match(self.filename)
        file_package = binary_match.group(1)
        if control_package != file_package:
            yield UploadError(
                "%s: package part of filename %r does not match "
                "package name in the control fields %r"
                % (self.filename, file_package, control_package))

    def verifyVersion(self):
        """Check if control version is valid matches the filename version.

        Binary version  doesn't need to match the changesfile version,
        because the changesfile version refers to the SOURCE version.
        """
        if not re_valid_version.match(self.control_version):
            yield UploadError("%s: invalid version number %r."
                              % (self.filename, self.control_version))

        binary_match = re_isadeb.match(self.filename)
        filename_version = binary_match.group(2)
        control_version_chopped = re_no_epoch.sub('', self.control_version)
        if filename_version != control_version_chopped:
            yield UploadError("%s: should be %s according to control file."
                              % (filename_version, control_version_chopped))

    def verifyArchitecture(self):
        """Check if the control architecture matches the changesfile.

        Also check if it is a valid architecture in LP context.
        """
        control_arch = self.control.get("Architecture", '')
        valid_archs = [a.architecturetag
                       for a in self.policy.distroseries.architectures]

        if control_arch not in valid_archs and control_arch != "all":
            yield UploadError(
                "%s: Unknown architecture: %r" % (
                self.filename, control_arch))

        if control_arch not in self.changes.architectures:
            yield UploadError(
                "%s: control file lists arch as %r which isn't "
                "in the changes file." % (self.filename, control_arch))

        if control_arch != self.architecture:
            yield UploadError(
                "%s: control file lists arch as %r which doesn't "
                "agree with version %r in the filename."
                % (self.filename, control_arch, self.architecture))

    def verifyDepends(self):
        """Check if control depends field is present and not empty."""
        control_depends = self.control.get('Depends', "--unset-marker--")
        if not control_depends:
            yield UploadError(
                "%s: Depends field present and empty." % self.filename)

    def verifySection(self):
        """Check the section & priority match those in changesfile."""
        control_section_and_component = self.control.get('Section', '')
        control_component, control_section = splitComponentAndSection(
            control_section_and_component)
        if ((control_component, control_section) !=
            (self.component_name, self.section_name)):
            yield UploadError(
                "%s control file lists section as %s/%s but changes file "
                "has %s/%s." % (self.filename, control_component,
                                control_section, self.component_name,
                                self.section_name))

    def verifyPriority(self):
        """Check if priority matches changesfile."""
        control_priority = self.control.get('Priority', '')
        if control_priority and self.priority_name != control_priority:
            yield UploadError(
                "%s control file lists priority as %s but changes file has "
                "%s." % (self.filename, control_priority, self.priority_name))

    def verifyFormat(self):
        """Check if the DEB format is sane.

        Debian packages are in fact 'ar' files. Thus we run '/usr/bin/ar'
        to look at the contents of the deb files to confirm they make sense.
        """
        ar_process = subprocess.Popen(
            ["/usr/bin/ar", "t", self.filepath],
            stdout=subprocess.PIPE)
        output = ar_process.stdout.read()
        result = ar_process.wait()
        if result != 0:
            yield UploadError(
                "%s: 'ar t' invocation failed." % self.filename)
            yield UploadError(
                prefix_multi_line_string(output, " [ar output:] "))

        chunks = output.strip().split("\n")
        if len(chunks) != 3:
            yield UploadError(
                "%s: found %d chunks, expecting 3. %r" % (
                self.filename, len(chunks), chunks))

        debian_binary, control_tar, data_tar = chunks
        if debian_binary != "debian-binary":
            yield UploadError(
                "%s: first chunk is %s, expected debian-binary." % (
                self.filename, debian_binary))
        if control_tar != "control.tar.gz":
            yield UploadError(
                "%s: second chunk is %s, expected control.tar.gz." % (
                self.filename, control_tar))
        if data_tar not in ("data.tar.gz", "data.tar.bz2", "data.tar.lzma",
                            "data.tar.xz"):
            yield UploadError(
                "%s: third chunk is %s, expected data.tar.gz, "
                "data.tar.bz2, data.tar.lzma or data.tar.xz." %
                (self.filename, data_tar))

    def verifyDebTimestamp(self):
        """Check specific DEB format timestamp checks."""
        self.logger.debug("Verifying timestamps in %s" % (self.filename))

        future_cutoff = time.time() + self.policy.future_time_grace
        earliest_year = time.strptime(str(self.policy.earliest_year), "%Y")
        past_cutoff = time.mktime(earliest_year)

        tar_checker = TarFileDateChecker(future_cutoff, past_cutoff)
        tar_checker.reset()
        try:
            deb_file = apt_inst.DebFile(self.filepath)
        except SystemError as error:
            # We get an error from the constructor if the .deb does not
            # contain all the expected top-level members (debian-binary,
            # control.tar.gz, and data.tar.*).
            yield UploadError(error)
        try:
            deb_file.control.go(tar_checker.callback)
            deb_file.data.go(tar_checker.callback)
            future_files = tar_checker.future_files.keys()
            if future_files:
                first_file = future_files[0]
                timestamp = time.ctime(tar_checker.future_files[first_file])
                yield UploadError(
                    "%s: has %s file(s) with a time stamp too "
                    "far into the future (e.g. %s [%s])."
                     % (self.filename, len(future_files), first_file,
                        timestamp))

            ancient_files = tar_checker.ancient_files.keys()
            if ancient_files:
                first_file = ancient_files[0]
                timestamp = time.ctime(tar_checker.ancient_files[first_file])
                yield UploadError(
                    "%s: has %s file(s) with a time stamp too "
                    "far in the past (e.g. %s [%s])."
                     % (self.filename, len(ancient_files), first_file,
                        timestamp))
        except (SystemExit, KeyboardInterrupt):
            raise
        except Exception as error:
            # There is a very large number of places where we
            # might get an exception while checking the timestamps.
            # Many of them come from apt_inst/apt_pkg and they are
            # terrible in giving sane exceptions. We thusly capture
            # them all and make them into rejection messages instead
            yield UploadError("%s: deb contents timestamp check failed: %s"
                 % (self.filename, error))

    #
    #   Database relationship methods
    #
    def findCurrentSourcePublication(self):
        """Return the respective ISourcePackagePublishingHistory for this
        binary upload.

        It inspects publication in the targeted DistroSeries.

        It raises UploadError if the spph was not found.
        """
        assert self.source_name is not None
        assert self.source_version is not None
        distroseries = self.policy.distroseries
        spphs = distroseries.getPublishedSources(
            self.source_name, version=self.source_version,
            include_pending=True, archive=self.policy.archive)
        # Workaround storm bug in EmptyResultSet.
        spphs = list(spphs[:1])
        try:
            return spphs[0]
        except IndexError:
            raise UploadError(
                "Unable to find source publication %s/%s in %s" % (
                self.source_name, self.source_version, distroseries.name))

    def findSourcePackageRelease(self):
        """Return the respective ISourcePackageRelease for this binary upload.

        It inspect publication in the targeted DistroSeries.

        It raises UploadError if the source was not found.

        Verifications on the designed source are delayed because for
        mixed_uploads (source + binary) we do not have the source stored
        in DB yet (see verifySourcepackagerelease).
        """
        spph = self.findCurrentSourcePublication()
        return spph.sourcepackagerelease

    def verifySourcePackageRelease(self, sourcepackagerelease):
        """Check if the given ISourcePackageRelease matches the context."""
        assert 'source' in self.changes.architectures, (
            "It should be a mixed upload, but no source part was found.")

        if self.source_version != sourcepackagerelease.version:
            raise UploadError(
                "source version %r for %s does not match version %r "
                "from control file" % (sourcepackagerelease.version,
                self.source_version, self.filename))

        if self.source_name != sourcepackagerelease.name:
            raise UploadError(
                "source name %r for %s does not match name %r in "
                "control file" % (sourcepackagerelease.name, self.filename,
                                  self.source_name))

    def findBuild(self, sourcepackagerelease):
        """Find and return a build for the given archtag, cached on policy.

        To find the right build, we try these steps, in order, until we have
        one:
        - Check first if a build id was provided. If it was, load that build.
        - Try to locate an existing suitable build, and use that. We also,
        in this case, change this build to be FULLYBUILT.
        - Create a new build in FULLYBUILT status.

        """
        dar = self.policy.distroseries[self.archtag]

        # Check if there's a suitable existing build.
        build = sourcepackagerelease.getBuildByArch(
            dar, self.policy.archive)
        if build is not None:
            build.updateStatus(BuildStatus.FULLYBUILT)
            self.logger.debug("Updating build for %s: %s" % (
                dar.architecturetag, build.id))
        else:
            # No luck. Make one.
            # Usually happen for security binary uploads.
            build = sourcepackagerelease.createBuild(
                dar, self.policy.pocket, self.policy.archive,
                status=BuildStatus.FULLYBUILT)
            self.logger.debug("Build %s created" % build.id)
        return build

    def checkBuild(self, build):
        """See PackageUploadFile."""
        try:
            dar = self.policy.distroseries[self.archtag]
        except NotFoundError:
            raise UploadError(
                "Upload to unknown architecture %s for distroseries %s" %
                (self.archtag, self.policy.distroseries))

        build.updateStatus(BuildStatus.FULLYBUILT)

        # Sanity check; raise an error if the build we've been
        # told to link to makes no sense.
        if (build.pocket != self.policy.pocket or
            build.distro_arch_series != dar or
            build.archive != self.policy.archive):
            raise UploadError(
                "Attempt to upload binaries specifying "
                "build %s, where they don't fit." % build.id)

    def storeInDatabase(self, build):
        """Insert this binary release and build into the database."""
        # Reencode everything we are supplying, because old packages
        # contain latin-1 text and that sucks.
        encoded = Deb822Dict()
        for key, value in self.control.items():
            encoded[key] = guess_encoding(value)

        desclines = encoded['Description'].split("\n")
        summary = desclines[0]
        description = "\n".join(desclines[1:])

        # XXX: dsilvers 2005-10-14 bug 3160: erm, need to work shlibdeps out.
        shlibdeps = ""

        is_essential = encoded.get('Essential', '').lower() == 'yes'
        architecturespecific = not self.is_archindep
        installedsize = int(self.control.get('Installed-Size', '0'))
        binary_name = getUtility(
            IBinaryPackageNameSet).getOrCreateByName(self.package)

        if self.ddeb_file:
            debug_package = build.getBinaryPackageFileByName(
                self.ddeb_file.filename).binarypackagerelease
        else:
            debug_package = None

        user_defined_fields = self.extractUserDefinedFields(
            [(field, encoded[field]) for field in self.control.iterkeys()])

        binary = build.createBinaryPackageRelease(
            binarypackagename=binary_name,
            version=self.control_version,
            summary=summary,
            description=description,
            binpackageformat=self.format,
            component=self.component,
            section=self.section,
            priority=self.priority,
            shlibdeps=shlibdeps,
            depends=encoded.get('Depends', ''),
            recommends=encoded.get('Recommends', ''),
            suggests=encoded.get('Suggests', ''),
            conflicts=encoded.get('Conflicts', ''),
            replaces=encoded.get('Replaces', ''),
            provides=encoded.get('Provides', ''),
            pre_depends=encoded.get('Pre-Depends', ''),
            enhances=encoded.get('Enhances', ''),
            breaks=encoded.get('Breaks', ''),
            homepage=encoded.get('Homepage'),
            essential=is_essential,
            installedsize=installedsize,
            architecturespecific=architecturespecific,
            user_defined_fields=user_defined_fields,
            debug_package=debug_package)

        library_file = self.librarian.create(self.filename,
             self.size, open(self.filepath, "rb"), self.content_type,
             restricted=self.policy.archive.private)
        binary.addFile(library_file)
        return binary


class UdebBinaryUploadFile(BaseBinaryUploadFile):
    """Represents an uploaded binary package file in udeb format."""
    format = BinaryPackageFormat.UDEB

    @property
    def local_checks(self):
        """Checks to be executed on UDEBs."""
        return [
            self.verifyPackage,
            self.verifyVersion,
            self.verifyArchitecture,
            self.verifyDepends,
            self.verifySection,
            self.verifyPriority,
            self.verifyFormat,
            ]


class DebBinaryUploadFile(BaseBinaryUploadFile):
    """Represents an uploaded binary package file in deb format."""
    format = BinaryPackageFormat.DEB

    @property
    def local_checks(self):
        """Checks to be executed on DEBs."""
        return [
            self.verifyPackage,
            self.verifyVersion,
            self.verifyArchitecture,
            self.verifyDepends,
            self.verifySection,
            self.verifyPriority,
            self.verifyFormat,
            self.verifyDebTimestamp,
            ]


class DdebBinaryUploadFile(DebBinaryUploadFile):
    """Represents an uploaded binary package file in ddeb format."""
    format = BinaryPackageFormat.DDEB
    deb_file = None
