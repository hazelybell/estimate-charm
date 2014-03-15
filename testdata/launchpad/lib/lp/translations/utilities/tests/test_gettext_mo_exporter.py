# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for the MO exporter."""

__metaclass__ = type

from textwrap import dedent

from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.script import run_command
from lp.translations.utilities.gettext_mo_exporter import GettextMOExporter
from lp.translations.utilities.gettext_po_parser import POParser
from lp.translations.utilities.translation_common_format import (
    TranslationMessageData,
    )
from lp.translations.utilities.translation_export import ExportFileStorage


class TestGettextMOExporter(TestCaseWithFactory):
    """Tests GettextMOExporter."""

    layer = DatabaseFunctionalLayer

    def _makeTranslationFileData(self, is_template=False):
        """Produce a TranslationFileData with one message: "foo"."""
        file_data = POParser().parse(dedent("""
            msgid ""
            msgstr ""
            "MIME-Version: 1.0\\n"
            "Content-Type: text/plain; charset=UTF-8\\n"

            msgid "foo"
            msgstr "bar"
            """))
        file_data.is_template = is_template
        file_data.language_code = 'my'
        file_data.translation_domain = 'main'
        if is_template:
            file_data.path = file_data.translation_domain + '.pot'
        else:
            file_data.path = file_data.language_code + '.po'
        return file_data

    def test_export_message(self):
        # The MO exporter does not support export of individual
        # messages.
        exporter = GettextMOExporter()
        self.assertRaises(
            NotImplementedError,
            exporter.exportTranslationMessageData,
            TranslationMessageData())

    def test_export_MO_produces_MO(self):
        # Exporting a translation in MO format produces a proper MO
        # file.
        file_data = self._makeTranslationFileData(is_template=False)
        storage = ExportFileStorage()

        GettextMOExporter().exportTranslationFile(file_data, storage)

        output = storage.export()
        self.assertEqual('application/x-gmo', output.content_type)

        # The file can even be converted back to PO format.
        retval, text, stderr = run_command(
            '/usr/bin/msgunfmt', args=['-'], input=output.read())

        self.assertEqual(0, retval)
        self.assertIn('MIME-Version', text)
        self.assertIn('msgid', text)
        self.assertIn('"foo"', text)

    def test_export_template_stays_pot(self):
        # The MO exporter exports templates in their original POT
        # format.
        file_data = self._makeTranslationFileData(is_template=True)
        storage = ExportFileStorage()

        GettextMOExporter().exportTranslationFile(file_data, storage)

        output = storage.export()
        self.assertEqual('application/x-po', output.content_type)
        self.assertTrue(output.path.endswith('.pot'))
        text = output.read()
        self.assertIn('POT-Creation-Date:', text)
        self.assertIn('MIME-Version:', text)
        self.assertIn('msgid', text)
        self.assertIn('"foo"', text)
