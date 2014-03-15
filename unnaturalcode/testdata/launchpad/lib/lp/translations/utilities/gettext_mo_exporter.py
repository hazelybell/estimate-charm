# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Export module for gettext's .mo file format."""

__metaclass__ = type

__all__ = [
    'GettextMOExporter',
    'POCompiler',
    ]

import os
import subprocess

from zope.component import getUtility
from zope.interface import implements

from lp.translations.interfaces.translationexporter import (
    ITranslationExporter,
    ITranslationFormatExporter,
    UnknownTranslationExporterError,
    )
from lp.translations.interfaces.translationfileformat import (
    TranslationFileFormat,
    )
from lp.translations.utilities.translation_export import ExportFileStorage


class POCompiler:
    """Compile PO files to MO files."""

    MSGFMT = '/usr/bin/msgfmt'

    def compile(self, gettext_po_file):
        """Return a MO version of the given PO file."""

        msgfmt = subprocess.Popen(
            args=[POCompiler.MSGFMT, '-v', '-o', '-', '-'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        stdout, stderr = msgfmt.communicate(gettext_po_file)

        if msgfmt.returncode != 0:
            raise UnknownTranslationExporterError(
                'Error compiling PO file: %s\n%s' % (gettext_po_file, stderr))

        return stdout


class GettextMOExporter:
    """Support class to export Gettext .mo files."""
    implements(ITranslationFormatExporter)

    # We use x-gmo for consistency with .po editors such as GTranslator.
    mime_type = 'application/x-gmo'

    def __init__(self, context=None):
        # 'context' is ignored because it's only required by the way the
        # exporters are instantiated but it isn't used by this class.
        self.format = TranslationFileFormat.MO
        self.supported_source_formats = [TranslationFileFormat.PO]

    def exportTranslationMessageData(self, translation_message):
        """See `ITranslationFormatExporter`."""
        raise NotImplementedError(
            "This file format doesn't allow to export a single message.")

    def exportTranslationFile(self, translation_file, storage,
                              ignore_obsolete=False, force_utf8=False):
        """See `ITranslationFormatExporter`."""

        translation_exporter = getUtility(ITranslationExporter)
        gettext_po_exporter = (
            translation_exporter.getExporterProducingTargetFileFormat(
                TranslationFileFormat.PO))

        # To generate MO files we need first its PO version and then,
        # generate the MO one.
        temp_storage = ExportFileStorage()
        gettext_po_exporter.exportTranslationFile(
            translation_file, temp_storage, ignore_obsolete=ignore_obsolete,
            force_utf8=force_utf8)
        po_export = temp_storage.export()
        exported_file_content = po_export.read()

        if translation_file.is_template:
            # This exporter is not able to handle template files. We
            # include those as .pot files stored in a templates/
            # directory.
            file_path = 'templates/%s' % os.path.basename(po_export.path)
            content_type = gettext_po_exporter.mime_type
            file_extension = po_export.file_extension
        else:
            file_extension = 'mo'
            # Standard layout for MO files is
            # 'LANG_CODE/LC_MESSAGES/TRANSLATION_DOMAIN.mo'
            file_path = os.path.join(
                translation_file.language_code,
                'LC_MESSAGES',
                '%s.%s' % (
                    translation_file.translation_domain,
                    file_extension))
            mo_compiler = POCompiler()
            mo_content = mo_compiler.compile(exported_file_content)
            exported_file_content = mo_content
            content_type = self.mime_type

        storage.addFile(
            file_path, file_extension, exported_file_content, content_type)
