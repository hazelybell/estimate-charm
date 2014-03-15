# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Components for exporting translation files."""

__metaclass__ = type

__all__ = [
    'ExportedTranslationFile',
    'ExportFileStorage',
    'TranslationExporter',
    ]

from StringIO import StringIO
import tempfile

from zope.component import subscribers
from zope.interface import implements

from lp.services.tarfile_helpers import LaunchpadWriteTarFile
from lp.translations.interfaces.translationexporter import (
    IExportedTranslationFile,
    ITranslationExporter,
    ITranslationFormatExporter,
    )
from lp.translations.interfaces.translationfileformat import (
    TranslationFileFormat,
    )


class ExportedTranslationFile:
    """See `IExportedTranslationFile`."""
    implements(IExportedTranslationFile)

    def __init__(self, content_file):
        self._content_file = content_file
        self.content_type = None
        self.path = None
        self.file_extension = None

        # Go to the end of the file.
        self._content_file.seek(0, 2)
        self.size = self._content_file.tell()
        # Go back to the start of the file.
        self._content_file.seek(0)

    def read(self, *args, **kwargs):
        """See `IExportedTranslationFile`."""
        if 'size' in kwargs:
            return self._content_file.read(kwargs['size'])
        else:
            return self._content_file.read()

    def close(self):
        """See `IExportedTranslationFile`."""
        self._content_file.close()


class TranslationExporter:
    """See `ITranslationExporter`."""
    implements(ITranslationExporter)

    def getExportersForSupportedFileFormat(self, file_format):
        """See `ITranslationExporter`."""
        exporters_available = []
        for exporter in subscribers([self], ITranslationFormatExporter):
            if file_format in exporter.supported_source_formats:
                exporters_available.append(exporter)

        return exporters_available

    def getExporterProducingTargetFileFormat(self, file_format):
        """See `ITranslationExporter`."""
        for exporter in subscribers([self], ITranslationFormatExporter):
            if (exporter.format == file_format or
                (file_format == TranslationFileFormat.XPI and
                 exporter.format == TranslationFileFormat.XPIPO)):
                # XPIPO is a special case for XPI exports.
                return exporter

        return None

    def exportTranslationFiles(self, translation_files, target_format=None,
                               ignore_obsolete=False, force_utf8=False):
        """See `ITranslationExporter`."""
        storage = ExportFileStorage()
        for translation_file in translation_files:
            if target_format is None:
                output_format = translation_file.format
            else:
                output_format = target_format
            format_exporter = self.getExporterProducingTargetFileFormat(
                output_format)
            file_content = format_exporter.exportTranslationFile(
                translation_file, storage, ignore_obsolete=ignore_obsolete,
                force_utf8=force_utf8)

        return storage.export()


class StorageStrategy:
    """Implementation strategy for `ExportFileStorage`.

    Storage for single files is implemented by `SingleFileStorageStrategy`;
    multiple files go into a `TarballFileStorageStrategy`.
    """

    def addFile(self, path, extension, content, mime_type):
        """Add a file to be stored."""
        raise NotImplementedError()

    def isEmpty(self):
        """Is this storage object still devoid of files?"""
        raise NotImplementedError()

    def isFull(self):
        """Does this storage object have its fill of files?"""
        raise NotImplementedError()

    def export(self):
        raise NotImplementedError()


class SingleFileStorageStrategy(StorageStrategy):
    """Store a single file for export.

    Provides a way to store a single PO or POT file, but through the same API
    that `TarballFileStorageStrategy` offers to store any number of files into
    a single tarball.  Both classes have an `addFile` operation, though a
    `SingleFileStorageStrategy` instance will only let you add a single file.

    (The type of the stored file matters in this strategy because the storage
    strategy declares the MIME type of the file it produces).
    """

    path = None
    extension = None

    def addFile(self, path, extension, content, mime_type):
        """See `StorageStrategy`."""
        assert path is not None, "Storing file without path."
        assert self.path is None, "Multiple files added; expected just one."
        self.path = path
        self.extension = extension
        self.content = content
        self.mime_type = mime_type

    def isEmpty(self):
        """See `StorageStrategy`."""
        return self.path is None

    def isFull(self):
        """See `StorageStrategy`.

        A `SingleFileStorageStrategy` can only store one file.
        """
        return not self.isEmpty()

    def export(self):
        """See `StorageStrategy`."""
        assert self.path is not None, "Exporting empty file."
        output = ExportedTranslationFile(StringIO(self.content))
        output.path = self.path
        # We use x-po for consistency with other .po editors like GTranslator.
        output.content_type = self.mime_type
        output.file_extension = self.extension
        return output


class TarballFileStorageStrategy(StorageStrategy):
    """Store any number of files for export as a tarball.

    Similar to `SingleFileStorageStrategy`, but lets you store any number of
    files using the same API.  Each file is written into the resulting tarball
    as soon as it is added.  There is no need to keep the full contents of the
    tarball in memory at any single time.
    """
    mime_type = 'application/x-gtar'

    empty = False

    def __init__(self, single_file_storage=None):
        """Initialze empty storage strategy, or subsume single-file one."""
        self.buffer = tempfile.TemporaryFile()
        self.tar_writer = LaunchpadWriteTarFile(self.buffer)
        if single_file_storage is not None:
            self.addFile(
                single_file_storage.path, single_file_storage.extension,
                single_file_storage.content, single_file_storage.mime_type)

    def addFile(self, path, extension, content, mime_type):
        """See `StorageStrategy`."""
        # Tarballs don't store MIME types, so ignore that.
        self.empty = False
        self.tar_writer.add_file(path, content)

    def isEmpty(self):
        """See `StorageStrategy`."""
        return self.empty

    def isFull(self):
        """See `StorageStrategy`.

        A `TarballFileStorageStrategy` can store any number of files, so no.
        """
        return False

    def export(self):
        """See `StorageStrategy`."""
        self.tar_writer.close()
        self.buffer.seek(0)
        output = ExportedTranslationFile(self.buffer)

        # Don't set path; let the caller decide.

        # For tar.gz files, the standard content type is application/x-gtar.
        # You can see more info on
        #   http://en.wikipedia.org/wiki/List_of_archive_formats
        output.content_type = self.mime_type
        output.file_extension = 'tar.gz'
        return output


class ExportFileStorage:
    """Store files to export, either as tarball or plain single file."""

    def __init__(self):
        # Start out with a single file.  We can replace that strategy later if
        # we get more than one file.
        self._store = SingleFileStorageStrategy()

    def addFile(self, path, extension, content, mime_type):
        """Add file to be stored.

        :param path: location and name of this file, relative to root of tar
            archive.
        :param extension: filename suffix (ignored here).
        :param content: contents of file.
        """
        if self._store.isFull():
            # We're still using a single-file storage strategy, but we just
            # received our second file.  Switch to tarball strategy.
            self._store = TarballFileStorageStrategy(self._store)
        self._store.addFile(path, extension, content, mime_type)

    def export(self):
        """Export as `ExportedTranslationFile`."""
        assert not self._store.isEmpty(), "Got empty list of files to export."
        return self._store.export()
