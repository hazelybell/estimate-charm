# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Translation Exporter tests."""

__metaclass__ = type

from cStringIO import StringIO
from operator import attrgetter
import unittest

from zope.interface.verify import verifyObject

from lp.testing.layers import LaunchpadZopelessLayer
from lp.translations.interfaces.translationexporter import (
    IExportedTranslationFile,
    ITranslationExporter,
    )
from lp.translations.interfaces.translationfileformat import (
    TranslationFileFormat,
    )
from lp.translations.utilities.translation_export import (
    ExportedTranslationFile,
    TranslationExporter,
    )


class TranslationExporterTestCase(unittest.TestCase):
    """Class test for translation importer component"""
    layer = LaunchpadZopelessLayer

    def setUp(self):
        self.translation_exporter = TranslationExporter()

    def testInterface(self):
        """Check whether the object follows the interface."""
        self.failUnless(
            verifyObject(ITranslationExporter, self.translation_exporter),
            "TranslationExporter doesn't follow the interface")
        self.failUnless(
            verifyObject(
                IExportedTranslationFile,
                ExportedTranslationFile(StringIO())),
            "ExportedTranslationFile doesn't follow the interface")

    def testGetTranslationFormatExporterByFileFormat(self):
        """Check whether we get the right exporter from the file format."""
        translation_exporter = self.translation_exporter
        po_format_exporter = (
            translation_exporter.getExporterProducingTargetFileFormat(
                TranslationFileFormat.PO))

        self.failIf(
            po_format_exporter is None,
            'Expected PO file format exporter was not found')

        mo_format_exporter = (
            translation_exporter.getExporterProducingTargetFileFormat(
                TranslationFileFormat.MO))

        self.failIf(
            mo_format_exporter is None,
            'Expected MO file format exporter was not found')

    def testGetTranslationFormatExportersForFileFormat(self):
        """Test the list of exporters handling a given file format."""
        translation_exporter = self.translation_exporter
        exporter_formats = []
        exporters_available = (
            translation_exporter.getExportersForSupportedFileFormat(
                TranslationFileFormat.PO))
        for exporter in exporters_available:
            exporter_formats.append(exporter.format)

        self.assertEqual(
            sorted(exporter_formats, key=attrgetter('name')),
            [TranslationFileFormat.MO,
             TranslationFileFormat.PO,
             ],
            'PO source file should be exported as '
            'PO and MO formats')

        exporter_formats = []
        exporters_available = (
            translation_exporter.getExportersForSupportedFileFormat(
                TranslationFileFormat.XPI))
        for exporter in exporters_available:
            exporter_formats.append(exporter.format)

        self.assertEqual(
            exporter_formats, [TranslationFileFormat.XPIPO],
            'XPI source file should be exported as PO format')
