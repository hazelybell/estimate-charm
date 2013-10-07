# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

""" ChangesFile class

Classes representing Changes and DSC files, which encapsulate collections of
files uploaded.
"""

__metaclass__ = type

__all__ = [
    'CannotDetermineFileTypeError',
    'ChangesFile',
    'determine_file_class_and_name',
    ]

import os

from lp.archiveuploader.dscfile import (
    DSCFile,
    SignableTagFile,
    )
from lp.archiveuploader.nascentuploadfile import (
    BaseBinaryUploadFile,
    CustomUploadFile,
    DdebBinaryUploadFile,
    DebBinaryUploadFile,
    SourceUploadFile,
    splitComponentAndSection,
    UdebBinaryUploadFile,
    )
from lp.archiveuploader.utils import (
    determine_binary_file_type,
    determine_source_file_type,
    parse_and_merge_file_lists,
    re_changes_file_name,
    re_isadeb,
    re_issource,
    UploadError,
    UploadWarning,
    )
from lp.registry.interfaces.sourcepackage import (
    SourcePackageFileType,
    SourcePackageUrgency,
    )
from lp.soyuz.enums import BinaryPackageFileType


class CannotDetermineFileTypeError(Exception):
    """The type of the given file could not be determined."""


class ChangesFile(SignableTagFile):
    """Changesfile model."""

    mandatory_fields = set([
        "Source", "Binary", "Architecture", "Version", "Distribution",
        "Maintainer", "Files", "Changes", "Date",
        # Changed-By is not technically mandatory according to
        # Debian policy but Soyuz relies on it being set in
        # various places.
        "Changed-By"])

    # Map urgencies to their dbschema values.
    # Debian policy only permits low, medium, high, emergency.
    # Britney also uses critical which it maps to emergency.
    urgency_map = {
        "low": SourcePackageUrgency.LOW,
        "medium": SourcePackageUrgency.MEDIUM,
        "high": SourcePackageUrgency.HIGH,
        "critical": SourcePackageUrgency.EMERGENCY,
        "emergency": SourcePackageUrgency.EMERGENCY,
        }

    dsc = None
    maintainer = None
    changed_by = None
    filename_archtag = None
    files = None

    def __init__(self, filepath, policy, logger):
        """Process the given changesfile.

        Does:
            * Verification of required fields
            * Verification of the required Format
            * Parses maintainer and changed-by
            * Checks name of changes file
            * Checks signature of changes file

        If any of these checks fail, UploadError is raised, and it's
        considered a fatal error (no subsequent processing of the upload
        will be done).

        Logger and Policy are instances built in uploadprocessor.py passed
        via NascentUpload class.
        """
        self.filepath = filepath
        self.policy = policy
        self.logger = logger

        self.parse(verify_signature=not policy.unsigned_changes_ok)

        for field in self.mandatory_fields:
            if field not in self._dict:
                raise UploadError(
                    "Unable to find mandatory field '%s' in the changes "
                    "file." % field)

        try:
            format = float(self._dict["Format"])
        except KeyError:
            # If format is missing, pretend it's 1.5
            format = 1.5

        if format < 1.5 or format > 2.0:
            raise UploadError(
                "Format out of acceptable range for changes file. Range "
                "1.5 - 2.0, format %g" % format)

    def checkFileName(self):
        """Make sure the changes file name is well-formed.

        Please note: for well-formed changes file names the `filename_archtag`
        property will be set appropriately.
        """
        match_changes = re_changes_file_name.match(self.filename)
        if match_changes is None:
            yield UploadError(
                '%s -> inappropriate changesfile name, '
                'should follow "<pkg>_<version>_<arch>.changes" format'
                % self.filename)
        else:
            self.filename_archtag = match_changes.group(3)

    def processAddresses(self):
        """Parse addresses and build person objects.

        Process 'maintainer' and 'changed_by' addresses separately and return
        an iterator over all exceptions generated while processing them.
        """
        if self.signer:
            # We only set the maintainer attribute up if we received a
            # signed upload.  This is desireable because it avoids us
            # doing ensurePerson() for buildds and sync owners.
            try:
                self.maintainer = self.parseAddress(self._dict['Maintainer'])
            except UploadError as error:
                yield error

        try:
            self.changed_by = self.parseAddress(self._dict['Changed-By'])
        except UploadError as error:
            yield error

    def isCustom(self, component_and_section):
        """Check if given 'component_and_section' matches a custom upload.

        We recognize an upload as custom if it is targeted at a section like
        'raw-<something>'.
        Further checks will be performed in CustomUploadFile class.
        """
        component_name, section_name = splitComponentAndSection(
            component_and_section)
        if section_name.startswith('raw-'):
            return True
        return False

    def processFiles(self):
        """Build objects for each file mentioned in this changesfile.

        This method is an error generator, i.e, it returns an iterator over
        all exceptions that are generated while processing all mentioned
        files.
        """
        try:
            raw_files = parse_and_merge_file_lists(self._dict, changes=True)
        except UploadError as e:
            yield e
            return

        files = []
        for attr in raw_files:
            filename, hashes, size, component_and_section, priority_name = attr
            filepath = os.path.join(self.dirname, filename)
            try:
                if self.isCustom(component_and_section):
                    # This needs to be the first check, because
                    # otherwise the tarballs in custom uploads match
                    # with source_match.
                    file_instance = CustomUploadFile(
                        filepath, hashes, size, component_and_section,
                        priority_name, self.policy, self.logger)
                else:
                    try:
                        package, cls = determine_file_class_and_name(filename)
                    except CannotDetermineFileTypeError:
                        yield UploadError(
                            "Unable to identify file %s (%s) in changes."
                            % (filename, component_and_section))
                        continue

                    file_instance = cls(
                        filepath, hashes, size, component_and_section,
                        priority_name, package, self.version, self,
                        self.policy, self.logger)

                    if cls == DSCFile:
                        self.dsc = file_instance
            except UploadError as error:
                yield error
            else:
                files.append(file_instance)

        self.files = files

    def verify(self):
        """Run all the verification checks on the changes data.

        This method is an error generator, i.e, it returns an iterator over
        all exceptions that are generated while verifying the changesfile
        consistency.
        """
        self.logger.debug("Verifying the changes file.")

        if len(self.files) == 0:
            yield UploadError("No files found in the changes")

        if 'Urgency' not in self._dict:
            # Urgency is recommended but not mandatory. Default to 'low'
            self._dict['Urgency'] = "low"

        raw_urgency = self._dict['Urgency'].lower()
        if raw_urgency not in self.urgency_map:
            yield UploadWarning(
                "Unable to grok urgency %s, overriding with 'low'"
                % (raw_urgency))
            self._dict['Urgency'] = "low"

        if not self.policy.unsigned_changes_ok:
            assert self.signer is not None, (
                "Policy does not allow unsigned changesfile")

    #
    # useful properties
    #
    @property
    def filename(self):
        """Return the changesfile name."""
        return os.path.basename(self.filepath)

    @property
    def dirname(self):
        """Return the current upload path name."""
        return os.path.dirname(self.filepath)

    def _getFilesByType(self, upload_filetype):
        """Look up for specific type of processed uploaded files.

        It ensure the files mentioned in the changes are already processed.
        """
        assert self.files is not None, "Files must but processed first."
        return [upload_file for upload_file in self.files
                if isinstance(upload_file, upload_filetype)]

    @property
    def binary_package_files(self):
        """Get a list of BaseBinaryUploadFile initialized in this context."""
        return self._getFilesByType(BaseBinaryUploadFile)

    @property
    def source_package_files(self):
        """Return a list of SourceUploadFile initialized in this context."""
        return self._getFilesByType(SourceUploadFile)

    @property
    def custom_files(self):
        """Return a list of CustomUploadFile initialized in this context."""
        return self._getFilesByType(CustomUploadFile)

    @property
    def suite_name(self):
        """Returns the targeted suite name.

        For example, 'hoary' or 'hoary-security'.
        """
        return self._dict['Distribution']

    @property
    def architectures(self):
        """Return set of strings specifying architectures listed in file.

        For instance ['source', 'all'] or ['source', 'i386', 'amd64']
        or ['source'].
        """
        return set(self._dict['Architecture'].split())

    @property
    def binaries(self):
        """Return set of binary package names listed."""
        return set(self._dict['Binary'].strip().split())

    @property
    def converted_urgency(self):
        """Return the appropriate SourcePackageUrgency item."""
        return self.urgency_map[self._dict['Urgency'].lower()]

    @property
    def version(self):
        """Return changesfile claimed version."""
        return self._dict['Version']

    @classmethod
    def formatChangesComment(cls, comment):
        """A class utility method for formatting changes for display."""

        # Return the display version of the comment using the
        # debian policy rules. First replacing the blank line
        # indicator '\n .' and then stripping one space from each
        # successive line.
        comment = comment.replace('\n .', '\n')
        comment = comment.replace('\n ', '\n')
        return comment

    @property
    def changes_comment(self):
        """Return changesfile 'change' comment."""
        comment = self._dict['Changes']

        return self.formatChangesComment(comment)

    @property
    def date(self):
        """Return changesfile date."""
        return self._dict['Date']

    @property
    def source(self):
        """Return changesfile claimed source name."""
        return self._dict['Source']

    @property
    def architecture_line(self):
        """Return changesfile archicteture line."""
        return self._dict['Architecture']

    @property
    def simulated_changelog(self):
        """Build and return a changelog entry for this changesfile.

        it includes the change comments followed by the author identification.
        {{{
        <CHANGES_COMMENT>
         -- <CHANGED-BY>  <DATE>
        }}}
        """
        changes_author = (
            '\n -- %s   %s' %
            (self.changed_by['rfc822'], self.date))
        return self.changes_comment + changes_author


def determine_file_class_and_name(filename):
    """Determine the name and PackageUploadFile subclass for the filename."""
    source_match = re_issource.match(filename)
    binary_match = re_isadeb.match(filename)
    if source_match:
        package = source_match.group(1)
        if (determine_source_file_type(filename) ==
            SourcePackageFileType.DSC):
            cls = DSCFile
        else:
            cls = SourceUploadFile
    elif binary_match:
        package = binary_match.group(1)
        cls = {
            BinaryPackageFileType.DEB: DebBinaryUploadFile,
            BinaryPackageFileType.DDEB: DdebBinaryUploadFile,
            BinaryPackageFileType.UDEB: UdebBinaryUploadFile,
            }[determine_binary_file_type(filename)]
    else:
        raise CannotDetermineFileTypeError(
            "Could not determine the type of %r" % filename)

    return package, cls
