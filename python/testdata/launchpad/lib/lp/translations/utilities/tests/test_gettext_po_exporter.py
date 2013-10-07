# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from textwrap import dedent

from zope.interface.verify import verifyObject

from lp.services.helpers import test_diff
from lp.testing import TestCaseWithFactory
from lp.testing.layers import LaunchpadZopelessLayer
from lp.translations.interfaces.translationexporter import (
    ITranslationFormatExporter,
    )
from lp.translations.interfaces.translationfileformat import (
    TranslationFileFormat,
    )
from lp.translations.utilities.gettext_po_exporter import (
    comments_text_representation,
    GettextPOExporter,
    strip_last_newline,
    )
from lp.translations.utilities.gettext_po_parser import POParser
from lp.translations.utilities.translation_common_format import (
    TranslationMessageData,
    )
from lp.translations.utilities.translation_export import ExportFileStorage


class GettextPOExporterTestCase(TestCaseWithFactory):
    """Class test for gettext's .po file exports"""
    layer = LaunchpadZopelessLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.parser = POParser()
        self.translation_exporter = GettextPOExporter()

    def _compareImportAndExport(self, import_file, export_file):
        """Compare imported file and the export we got from it.

        :param import_file: buffer with the source file content.
        :param export_file: buffer with the output file content.
        """
        import_lines = [line for line in import_file.split('\n')]
        # Remove X-Launchpad-Export-Date line to prevent time bombs in tests.
        export_lines = [
            line for line in export_file.split('\n')
            if (not line.startswith('"X-Launchpad-Export-Date:') and
                not line.startswith('"X-Generator: Launchpad'))]

        line_pairs = zip(export_lines, import_lines)
        debug_diff = test_diff(import_lines, export_lines)
        for export_line, import_line in line_pairs:
            self.assertEqual(
                export_line, import_line,
                "Output doesn't match:\n\n %s" % debug_diff)

        self.assertEqual(
            len(export_lines), len(import_lines),
            "Output has excess lines:\n\n %s" % debug_diff)

    def testInterface(self):
        """Check whether the object follows the interface."""
        self.failUnless(
            verifyObject(ITranslationFormatExporter,
                         self.translation_exporter),
            "GettextPOExporter doesn't follow the interface")

    def testSupportedFormats(self):
        """Check that the exporter reports the correct formats."""
        self.failUnlessEqual(
            self.translation_exporter.format,
            TranslationFileFormat.PO,
            "Expected GettextPOExporter to provide PO format "
            "but got %r instead." % self.translation_exporter.format)
        self.failUnlessEqual(
            self.translation_exporter.supported_source_formats,
            [TranslationFileFormat.PO, TranslationFileFormat.KDEPO],
            "Expected GettextPOExporter to support PO and KDEPO source "
            "formats but got %r instead." % (
                self.translation_exporter.supported_source_formats))

    def testGeneralExport(self):
        """Check different kind of messages export."""

        pofile_cy = dedent('''
            msgid ""
            msgstr ""
            "Project-Id-Version: foo\\n"
            "Report-Msgid-Bugs-To: \\n"
            "POT-Creation-Date: 2007-07-09 03:39+0100\\n"
            "PO-Revision-Date: 2001-09-09 01:46+0000\\n"
            "Last-Translator: Kubla Kahn <kk@pleasure-dome.com>\\n"
            "Language-Team: LANGUAGE <LL@li.org>\\n"
            "MIME-Version: 1.0\\n"
            "Content-Type: text/plain; charset=UTF-8\\n"
            "Content-Transfer-Encoding: 8bit\\n"
            "Plural-Forms: nplurals=4; plural=n==1 ? 0 : n==2 ? 1 : (n != 8 || n != 11) ? "
            "2 : 3;\\n"

            msgid "foo"
            msgid_plural "foos"
            msgstr[0] "cy-F001"
            msgstr[1] "cy-F002"
            msgstr[2] ""
            msgstr[3] ""

            #, fuzzy
            #| msgid "zog"
            msgid "zig"
            msgstr "zag"

            #, c-format
            msgid "zip"
            msgstr "zap"

            # tove
            #. borogove
            #: rath
            msgid "zog"
            msgstr "zug"

            #~ msgid "zot"
            #~ msgstr "zat"
            ''')
        cy_translation_file = self.parser.parse(pofile_cy)
        cy_translation_file.is_template = False
        cy_translation_file.language_code = 'cy'
        cy_translation_file.path = 'po/cy.po'
        cy_translation_file.translation_domain = 'testing'
        storage = ExportFileStorage()
        self.translation_exporter.exportTranslationFile(
            cy_translation_file, storage)

        self._compareImportAndExport(
            pofile_cy.strip(), storage.export().read().strip())

    def testObsoleteExport(self):
        """Check how obsoleted messages are exported."""

        pofile_eo = dedent('''
            msgid ""
            msgstr ""
            "Project-Id-Version: Kumquats 1.0\\n"
            "Report-Msgid-Bugs-To: \\n"
            "POT-Creation-Date: 2007-07-09 03:39+0100\\n"
            "PO-Revision-Date: 2001-09-09 01:46+0000\\n"
            "Last-Translator: L.L. Zamenhoff <llz@uea.org>\\n"
            "Language-Team: Esperanto <eo@li.org>\\n"
            "MIME-Version: 1.0\\n"
            "Content-Type: text/plain; charset=UTF-8\\n"
            "Content-Transfer-Encoding: 8bit\\n"

            # Foo bar.
            #, c-format
            #: src/foo.c
            #| msgid "zog"
            msgid "zig"
            msgstr "zag"
            ''')

        pofile_eo_obsolete = dedent('''
            msgid ""
            msgstr ""
            "Project-Id-Version: Kumquats 1.0\\n"
            "Report-Msgid-Bugs-To: \\n"
            "POT-Creation-Date: 2007-07-09 03:39+0100\\n"
            "PO-Revision-Date: 2001-09-09 01:46+0000\\n"
            "Last-Translator: L.L. Zamenhoff <llz@uea.org>\\n"
            "Language-Team: Esperanto <eo@li.org>\\n"
            "MIME-Version: 1.0\\n"
            "Content-Type: text/plain; charset=UTF-8\\n"
            "Content-Transfer-Encoding: 8bit\\n"

            # Foo bar.
            #, c-format
            #~| msgid "zog"
            #~ msgid "zig"
            #~ msgstr "zag"
            ''')
        eo_translation_file = self.parser.parse(pofile_eo)
        eo_translation_file.is_template = False
        eo_translation_file.language_code = 'eo'
        eo_translation_file.path = 'po/eo.po'
        eo_translation_file.translation_domain = 'testing'
        eo_translation_file.messages[0].is_obsolete = True
        storage = ExportFileStorage()
        self.translation_exporter.exportTranslationFile(
            eo_translation_file, storage)

        self._compareImportAndExport(
            pofile_eo_obsolete.strip(), storage.export().read().strip())

    def testEncodingExport(self):
        """Test that PO headers specifying character sets are respected."""

        def compare(self, pofile):
            "Compare the original text with the exported one."""
            # This is the word 'Japanese' in Japanese, in Unicode.
            nihongo_unicode = u'\u65e5\u672c\u8a9e'
            translation_file = self.parser.parse(pofile)
            translation_file.is_template = False
            translation_file.language_code = 'ja'
            translation_file.path = 'po/ja.po'
            translation_file.translation_domain = 'testing'

            # We are sure that 'Japanese' is correctly stored as Unicode so
            # we are sure the exporter does its job instead of just export
            # what was imported.
            self.assertEqual(
                translation_file.messages[0].translations,
                [nihongo_unicode])

            storage = ExportFileStorage()
            self.translation_exporter.exportTranslationFile(
                translation_file, storage)

            self._compareImportAndExport(
                pofile.strip(), storage.export().read().strip())

        # File representing the same PO file three times. Each is identical
        # except for the charset declaration in the header.
        pofiles = [
            dedent('''
                msgid ""
                msgstr ""
                "Project-Id-Version: foo\\n"
                "Report-Msgid-Bugs-To: \\n"
                "POT-Creation-Date: 2007-07-09 03:39+0100\\n"
                "PO-Revision-Date: 2001-09-09 01:46+0000\\n"
                "Last-Translator: Kubla Kahn <kk@pleasure-dome.com>\\n"
                "Language-Team: LANGUAGE <LL@li.org>\\n"
                "MIME-Version: 1.0\\n"
                "Content-Type: text/plain; charset=UTF-8\\n"
                "Content-Transfer-Encoding: 8bit\\n"

                msgid "Japanese"
                msgstr "\xe6\x97\xa5\xe6\x9c\xac\xe8\xaa\x9e"
                '''),
            dedent('''
                msgid ""
                msgstr ""
                "Project-Id-Version: foo\\n"
                "Report-Msgid-Bugs-To: \\n"
                "POT-Creation-Date: 2007-07-09 03:39+0100\\n"
                "PO-Revision-Date: 2001-09-09 01:46+0000\\n"
                "Last-Translator: Kubla Kahn <kk@pleasure-dome.com>\\n"
                "Language-Team: LANGUAGE <LL@li.org>\\n"
                "MIME-Version: 1.0\\n"
                "Content-Type: text/plain; charset=Shift-JIS\\n"
                "Content-Transfer-Encoding: 8bit\\n"

                msgid "Japanese"
                msgstr "\x93\xfa\x96\x7b\x8c\xea"
                '''),
            dedent('''
                msgid ""
                msgstr ""
                "Project-Id-Version: foo\\n"
                "Report-Msgid-Bugs-To: \\n"
                "POT-Creation-Date: 2007-07-09 03:39+0100\\n"
                "PO-Revision-Date: 2001-09-09 01:46+0000\\n"
                "Last-Translator: Kubla Kahn <kk@pleasure-dome.com>\\n"
                "Language-Team: LANGUAGE <LL@li.org>\\n"
                "MIME-Version: 1.0\\n"
                "Content-Type: text/plain; charset=EUC-JP\\n"
                "Content-Transfer-Encoding: 8bit\\n"

                msgid "Japanese"
                msgstr "\xc6\xfc\xcb\xdc\xb8\xec"
                '''),
            ]
        for pofile in pofiles:
            compare(self, pofile)

    def _testBrokenEncoding(self, pofile_content):
        translation_file = self.parser.parse(
            pofile_content % {'charset': 'ISO-8859-15', 'special': '\xe1'})
        translation_file.is_template = False
        translation_file.language_code = 'es'
        translation_file.path = 'po/es.po'
        translation_file.translation_domain = 'testing'
        # Force the export as ASCII, it will not be possible because
        # translation is not available in that encoding and thus, we should
        # get an export in UTF-8.
        translation_file.header.charset = 'ASCII'
        storage = ExportFileStorage()
        self.translation_exporter.exportTranslationFile(
            translation_file, storage)

        self._compareImportAndExport(
            pofile_content.strip() % {
                'charset': 'UTF-8', 'special': '\xc3\xa1'},
            storage.export().read().strip())

    def testBrokenEncodingExport(self):
        """Test what happens when the content and the encoding don't agree.

        If a pofile fails to encode using the character set specified in the
        header, the header should be changed to specify to UTF-8 and the
        pofile exported accordingly.
        """

        pofile_content = dedent('''
            msgid ""
            msgstr ""
            "Project-Id-Version: foo\\n"
            "Report-Msgid-Bugs-To: \\n"
            "POT-Creation-Date: 2007-07-09 03:39+0100\\n"
            "PO-Revision-Date: 2001-09-09 01:46+0000\\n"
            "Last-Translator: Kubla Kahn <kk@pleasure-dome.com>\\n"
            "Language-Team: LANGUAGE <LL@li.org>\\n"
            "MIME-Version: 1.0\\n"
            "Content-Type: text/plain; charset=%(charset)s\\n"
            "Content-Transfer-Encoding: 8bit\\n"

            msgid "a"
            msgstr "%(special)s"
            ''')
        self._testBrokenEncoding(pofile_content)

    def testBrokenEncodingHeader(self):
        """A header field might require a different encoding, too.

        This usually happens if the Last-Translator name contains non-ascii
        characters.

        If a pofile fails to encode using the character set specified in the
        header, the header should be changed to specify to UTF-8 and the
        pofile exported accordingly.
        """

        pofile_content = dedent('''
            msgid ""
            msgstr ""
            "Project-Id-Version: foo\\n"
            "Report-Msgid-Bugs-To: \\n"
            "POT-Creation-Date: 2007-07-09 03:39+0100\\n"
            "PO-Revision-Date: 2001-09-09 01:46+0000\\n"
            "Last-Translator: Kubla K%(special)shn <kk@pleasure-dome.com>\\n"
            "Language-Team: LANGUAGE <LL@li.org>\\n"
            "MIME-Version: 1.0\\n"
            "Content-Type: text/plain; charset=%(charset)s\\n"
            "Content-Transfer-Encoding: 8bit\\n"

            msgid "a"
            msgstr "b"
            ''')
        self._testBrokenEncoding(pofile_content)

    def testIncompletePluralMessage(self):
        """Test export correctness for partial plural messages."""

        pofile = dedent('''
            msgid ""
            msgstr ""
            "Project-Id-Version: foo\\n"
            "Report-Msgid-Bugs-To: \\n"
            "POT-Creation-Date: 2007-07-09 03:39+0100\\n"
            "PO-Revision-Date: 2001-09-09 01:46+0000\\n"
            "Last-Translator: Kubla Kahn <kk@pleasure-dome.com>\\n"
            "Language-Team: LANGUAGE <LL@li.org>\\n"
            "MIME-Version: 1.0\\n"
            "Content-Type: text/plain; charset=UTF-8\\n"
            "Content-Transfer-Encoding: 8bit\\n"
            "Plural-Forms: nplurals=2; plural=(n != 1);\\n"

            msgid "1 dead horse"
            msgid_plural "%%d dead horses"
            msgstr[0] "ning\xc3\xban caballo muerto"
            %s''')
        translation_file = self.parser.parse(pofile % (''))
        translation_file.is_template = False
        translation_file.language_code = 'es'
        translation_file.path = 'po/es.po'
        translation_file.translation_domain = 'testing'
        storage = ExportFileStorage()
        self.translation_exporter.exportTranslationFile(
            translation_file, storage)

        self._compareImportAndExport(
            pofile.strip() % 'msgstr[1] ""', storage.export().read().strip())

    def testClashingSingularMsgIds(self):
        # We don't accept it in gettext imports directly, since it's not
        # valid gettext, but it's possible for our database to hold
        # messages that differ only in msgid_plural.  In gettext those
        # would be considered equal, so we can't export them.  Only the
        # first of the two messages is exported.
        template = self.factory.makePOTemplate()
        self.factory.makePOTMsgSet(
            template, singular='%d foo', plural='%d foos', sequence=1)
        self.factory.makePOTMsgSet(
            template, singular='%d foo', plural='%d foox', sequence=2)

        exported_file = template.export()

        # The "foos" (as opposed to "foox") tells us that the exporter
        # has picked the first message for export.
        expected_output = dedent("""
            msgid "%d foo"
            msgid_plural "%d foos"
            msgstr[0] ""
            msgstr[1] ""
            """).strip()

        body = exported_file.split('\n\n', 1)[1].strip()
        self.assertEqual(body, expected_output)

    def testObsoleteMessageYieldsToNonObsoleteClashingOne(self):
        # When an obsolete message and a non-obsolete message in the
        # same POFile have identical identifying information except
        # msgid_plural (which Launchpad considers part of the message's
        # identifying information but gettext does not), only the
        # non-obsolete one is exported.
        template = self.factory.makePOTemplate()
        obsolete_message = self.factory.makePOTMsgSet(
            template, singular='%d goo', plural='%d goos', sequence=0)
        current_message = self.factory.makePOTMsgSet(
            template, singular='%d goo', plural='%d gooim', sequence=1)

        pofile = self.factory.makePOFile(
            potemplate=template, language_code='nl')

        self.factory.makeCurrentTranslationMessage(
            pofile=pofile, potmsgset=obsolete_message,
            translations=['%d splut', '%d splutjes'])
        self.factory.makeCurrentTranslationMessage(
            pofile=pofile, potmsgset=current_message,
            translations=['%d gargl', '%d garglii'])

        exported_file = pofile.export()

        # The "gooim" (as opposed to "goos") tells us that the exporter
        # has picked the non-obsolete message for export.  The "gargl"
        # and "garglii" tell us we're not just getting the msgid from
        # the non-obsolete message, but the translations as well.
        expected_output = dedent("""
            msgid "%d goo"
            msgid_plural "%d gooim"
            msgstr[0] "%d gargl"
            msgstr[1] "%d garglii"
            """).strip()

        body = exported_file.split('\n\n', 1)[1].strip()
        self.assertEqual(expected_output, body)

    def test_strip_last_newline(self):
        # `strip_last_newline` strips only the last newline.
        self.assertEqual('text\n', strip_last_newline('text\n\n'))
        self.assertEqual('text\nx', strip_last_newline('text\nx'))
        self.assertEqual('text', strip_last_newline('text'))

        # It supports '\r' as well (Mac-style).
        self.assertEqual('text', strip_last_newline('text\r'))
        # And DOS-style '\r\n'.
        self.assertEqual('text', strip_last_newline('text\r\n'))

        # With weird combinations, it strips only the last
        # newline-indicating character.
        self.assertEqual('text\n', strip_last_newline('text\n\r'))

    def test_comments_text_representation_multiline(self):
        # Comments with newlines should be correctly exported.
        data = TranslationMessageData()
        data.comment = "Line One\nLine Two"
        self.assertEqual("#Line One\n#Line Two",
                         comments_text_representation(data))

        # It works the same when there's a final newline as well.
        data.comment = "Line One\nLine Two\n"
        self.assertEqual("#Line One\n#Line Two",
                         comments_text_representation(data))

        # And similar processing happens for source comments.
        data = TranslationMessageData()
        data.source_comment = "Line One\nLine Two"
        self.assertEqual("#. Line One\n#. Line Two",
                         comments_text_representation(data))

        # It works the same when there's a final newline as well.
        data.source_comment = "Line One\nLine Two\n"
        self.assertEqual("#. Line One\n#. Line Two",
                         comments_text_representation(data))

    def test_export_handles_empty_files(self):
        # Exporting an empty gettext file does not break the exporter.
        # The output does contain one message: the header.
        output = self.factory.makePOFile('nl').export()
        self.assertTrue(output.startswith('# Dutch translation for '))
        self.assertEqual(1, output.count('msgid'))
