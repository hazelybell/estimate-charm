# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'MozillaZipTraversal',
    ]

from cStringIO import StringIO
from os.path import (
    basename,
    splitext,
    )
from zipfile import (
    BadZipfile,
    ZipFile,
    )

from lp.translations.interfaces.translationimporter import (
    TranslationFormatInvalidInputError,
    )
from lp.translations.utilities.xpi_header import XpiHeader
from lp.translations.utilities.xpi_manifest import (
    make_jarpath,
    XpiManifest,
    )


class MozillaZipTraversal:
    """Traversal of an XPI file, or a jar file inside an XPI file.

    To traverse and process an XPI file, derive a class from this one
    and replace any hooks that you may need.

    If an XPI manifest is provided, traversal will be restricted to
    directories it lists as containing localizable resources.
    """

    def __init__(self, filename, archive, xpi_path=None, manifest=None):
        """Open zip (or XPI, or jar) file and scan its contents.

        :param filename: Name of this zip (XPI/jar) archive.
        :param archive: File-like object containing this zip archive.
        :param xpi_path: Full path of this file inside the XPI archive.
            Leave out for the XPI archive itself.
        :param manifest: `XpiManifest` representing the XPI archive's
            manifest file, if any.
        """
        self.filename = filename
        self.header = None
        self.last_translator = None
        self.manifest = manifest
        try:
            self.archive = ZipFile(archive, 'r')
        except BadZipfile as exception:
            raise TranslationFormatInvalidInputError(
                filename=filename, message=str(exception))

        if xpi_path is None:
            # This is the main XPI file.
            xpi_path = ''
            contained_files = set(self.archive.namelist())
            if manifest is None:
                # Look for a manifest.
                for filename in ['chrome.manifest', 'en-US.manifest']:
                    if filename in contained_files:
                        manifest_content = self.archive.read(filename)
                        self.manifest = XpiManifest(manifest_content)
                        break
            if 'install.rdf' in contained_files:
                rdf_content = self.archive.read('install.rdf')
                self.header = XpiHeader(rdf_content)

        # Strip trailing newline to avoid doubling it.
        xpi_path = xpi_path.rstrip('/')

        self._begin()

        # Process zipped files.  Sort by path to keep ordering deterministic.
        # Ordering matters in sequence numbering (which in turn shows up in
        # the UI), but also for consistency in duplicates resolution and for
        # automated testing.
        for entry in sorted(self.archive.namelist()):
            self._processEntry(entry, xpi_path)

        self._finish()

    def _processEntry(self, entry, xpi_path):
        """Read one zip archive entry, figure out what to do with it."""
        rootname, suffix = splitext(entry)
        if basename(rootname) == '':
            # If filename starts with a dot, that's not really a suffix.
            suffix = ''

        if suffix == '.jar':
            jarpath = make_jarpath(xpi_path, entry)
            if not self.manifest or self.manifest.containsLocales(jarpath):
                # If this is a jar file that may contain localizable
                # resources, don't process it in the normal way; recurse
                # by creating another parser instance.
                content = self.archive.read(entry)
                nested_instance = self.__class__(
                    filename=entry, archive=StringIO(content),
                    xpi_path=jarpath, manifest=self.manifest)

                self._processNestedJar(nested_instance)
                return

        # Construct XPI path; identical to "entry" if previous xpi_path
        # was empty.  XPI paths use slashes as separators, regardless of
        # what the native filesystem uses.
        xpi_path = '/'.join([xpi_path, entry]).lstrip('/')

        if self.manifest is None:
            # No manifest, so we don't have chrome paths.  Process
            # everything just to be sure.
            chrome_path = None
            locale_code = None
        else:
            chrome_path, locale_code = self.manifest.getChromePathAndLocale(
                xpi_path)
            if chrome_path is None:
                # Not in a directory containing localizable resources.
                return

        self._processTranslatableFile(
            entry, locale_code, xpi_path, chrome_path, suffix)

    def _begin(self):
        """Overridable hook: optional pre-traversal actions."""

    def _processTranslatableFile(self, entry, locale_code, xpi_path,
                                 chrome_path, filename_suffix):
        """Overridable hook: process a file entry.

        Called only for files that may be localizable.  If there is a
        manifest, that means the file must be in a location (or subtree)
        named by a "locale" entry.

        :param entry: Full name of file inside this zip archive,
            including path relative to the archive's root.
        :param locale_code: Code for locale this file belongs to, e.g.
            "en-US".
        :param xpi_path: Full path of this file inside the XPI archive,
            e.g. "jar:locale/en-US.jar!/data/messages.dtd".
        :param chrome_path: File's chrome path.  This is a kind of
            "normalized" path used in XPI to describe a virtual
            directory hierarchy.  The zip archive's actual layout (which
            the XPI paths describe) may be different.
        :param filename_suffix: File name suffix or "extension" of the
            translatable file.  This may be e.g. ".dtd" or ".xhtml," or
            the empty string if the filename does not contain a dot.
        """
        raise NotImplementedError(
            "XPI traversal class provides no _processTranslatableFile().")

    def _processNestedJar(self, zip_instance):
        """Overridable hook: handle a nested jar file.

        :param zip_instance: An instance of the same class as self, which
            has just parsed the nested jar file.
        """
        raise NotImplementedError(
            "XPI traversal class provides no _processNestedJar().")

    def _finish(self):
        """Overridable hook: post-traversal actions."""
        raise NotImplementedError(
            "XPI traversal class provides no _finish().")


