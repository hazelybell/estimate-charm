# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Translation File Importer tests."""

__metaclass__ = type

from textwrap import dedent

import transaction
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.registry.interfaces.person import IPersonSet
from lp.services.librarianserver.testing.fake import FakeLibrarian
from lp.testing import TestCaseWithFactory
from lp.testing.layers import (
    LaunchpadZopelessLayer,
    ZopelessDatabaseLayer,
    )
from lp.translations.enums import TranslationPermission
from lp.translations.interfaces.potemplate import IPOTemplateSet
from lp.translations.interfaces.side import TranslationSide
from lp.translations.interfaces.translationfileformat import (
    TranslationFileFormat,
    )
from lp.translations.interfaces.translationimporter import (
    OutdatedTranslationError,
    )
from lp.translations.interfaces.translationimportqueue import (
    ITranslationImportQueue,
    )
from lp.translations.utilities.gettext_po_importer import GettextPOImporter
from lp.translations.utilities.translation_common_format import (
    TranslationMessageData,
    )
from lp.translations.utilities.translation_import import (
    FileImporter,
    importers,
    POFileImporter,
    POTFileImporter,
    )


TEST_LANGUAGE = "eo"
TEST_MSGID = "Thank You"
TEST_MSGSTR = "Dankon"
TEST_MSGSTR2 = "Dankon al vi"
TEST_EXPORT_DATE = '"X-Launchpad-Export-Date: 2008-11-05 13:31+0000\\n"\n'
TEST_EXPORT_DATE_EARLIER = (
                   '"X-Launchpad-Export-Date: 2008-11-05 13:20+0000\\n"\n')
NUMBER_OF_TEST_MESSAGES = 1
TEST_TEMPLATE = r'''
msgid ""
msgstr ""
"PO-Revision-Date: 2005-05-03 20:41+0100\n"
"Last-Translator: FULL NAME <EMAIL@ADDRESS>\n"
"Content-Type: text/plain; charset=UTF-8\n"
%s
msgid "%s"
msgstr ""
'''
TEST_TEMPLATE_EXPORTED = TEST_TEMPLATE % (TEST_EXPORT_DATE, TEST_MSGID)
TEST_TEMPLATE_UPSTREAM = TEST_TEMPLATE % ("", TEST_MSGID)

TEST_TRANSLATION_FILE = r'''
msgid ""
msgstr ""
"PO-Revision-Date: 2008-11-05 13:22+0000\n"
"Last-Translator: Someone New <someone.new@canonical.com>\n"
"Content-Type: text/plain; charset=UTF-8\n"
%s
msgid "%s"
msgstr "%s"
'''
TEST_TRANSLATION_EXPORTED = TEST_TRANSLATION_FILE % (
    TEST_EXPORT_DATE, TEST_MSGID, TEST_MSGSTR)
TEST_TRANSLATION_UPSTREAM = TEST_TRANSLATION_FILE % (
    "", TEST_MSGID, TEST_MSGSTR)
# This is needed for test_FileImporter_importFile_conflict and differs from
# the others in export timestamp and msgstr content.
TEST_TRANSLATION_EXPORTED_EARLIER = TEST_TRANSLATION_FILE % (
    TEST_EXPORT_DATE_EARLIER, TEST_MSGID, TEST_MSGSTR2)

# The following two are needed for test_FileImporter_importFile_error.
# The translation file has an error in the format specifiers.
TEST_MSGID_ERROR = "format specifier follows %d"
TEST_TEMPLATE_FOR_ERROR = r'''
msgid ""
msgstr ""
"PO-Revision-Date: 2005-05-03 20:41+0100\n"
"Last-Translator: FULL NAME <EMAIL@ADDRESS>\n"
"Content-Type: text/plain; charset=UTF-8\n"

#, c-format
msgid "%s"
msgstr ""
''' % TEST_MSGID_ERROR


TEST_TRANSLATION_FILE_WITH_ERROR = r'''
msgid ""
msgstr ""
"PO-Revision-Date: 2008-09-17 20:41+0100\n"
"Last-Translator: Foo Bar <foo.bar@canonical.com>\n"
"Content-Type: text/plain; charset=UTF-8\n"
"X-Launchpad-Export-Date: 2008-11-05 13:31+0000\n"

#, c-format
msgid "%s"
msgstr "format specifier changes %%s"
''' % TEST_MSGID_ERROR


class FileImporterTestCase(TestCaseWithFactory):
    """Class test for translation importer component"""
    layer = ZopelessDatabaseLayer

    def _createFileImporters(self, pot_content, po_content, by_maintainer):
        """Create queue entries from POT and PO content strings.
        Create importers from the entries."""
        pot_importer = self._createPOTFileImporter(
            pot_content, by_maintainer)
        po_importer = self._createPOFileImporter(
            pot_importer, po_content, by_maintainer)
        return (pot_importer, po_importer)

    def _createPOTFileImporter(self, pot_content, by_maintainer):
        """Create queue entries from POT content string.
        Create an importer from the entry."""
        potemplate = self.factory.makePOTemplate()
        template_entry = self.translation_import_queue.addOrUpdateEntry(
            potemplate.path, pot_content,
            by_maintainer, self.importer_person,
            productseries=potemplate.productseries,
            potemplate=potemplate)
        self.fake_librarian.pretendCommit()
        return POTFileImporter(template_entry, GettextPOImporter(), None)

    def _createPOFileImporter(self,
            pot_importer, po_content, by_maintainer, existing_pofile=None,
            person=None):
        """Create a PO entry from content, relating to a template_entry.
        Create an importer for the entry."""
        potemplate = pot_importer.translation_import_queue_entry.potemplate
        if existing_pofile == None:
            pofile = self.factory.makePOFile(
                TEST_LANGUAGE, potemplate=potemplate)
        else:
            pofile = existing_pofile
        person = person or self.importer_person
        translation_entry = self.translation_import_queue.addOrUpdateEntry(
            pofile.path, po_content, by_maintainer, person,
            productseries=potemplate.productseries, pofile=pofile)
        self.fake_librarian.pretendCommit()
        return POFileImporter(translation_entry, GettextPOImporter(), None)

    def _createImporterForExportedEntries(self):
        """Set up entries that where exported from LP, i.e. that contain the
        'X-Launchpad-Export-Date:' header."""
        return self._createFileImporters(
            TEST_TEMPLATE_EXPORTED, TEST_TRANSLATION_EXPORTED, False)

    def _createImporterForUpstreamEntries(self):
        """Set up entries that where not exported from LP, i.e. that do not
        contain the 'X-Launchpad-Export-Date:' header."""
        return self._createFileImporters(
            TEST_TEMPLATE_UPSTREAM, TEST_TRANSLATION_UPSTREAM, True)

    def _createFileImporter(self):
        """Create just an (incomplete) FileImporter for basic tests.
        The importer is based on a template.
        These tests don't care about Imported or Upstream."""
        potemplate = self.factory.makePOTemplate()
        template_entry = self.translation_import_queue.addOrUpdateEntry(
            potemplate.path, TEST_TEMPLATE_EXPORTED,
            False, self.importer_person,
            productseries=potemplate.productseries,
            potemplate=potemplate)
        self.fake_librarian.pretendCommit()
        return FileImporter(template_entry, GettextPOImporter(), None)

    def setUp(self):
        super(FileImporterTestCase, self).setUp()
        self.fake_librarian = self.useFixture(FakeLibrarian())
        self.translation_import_queue = getUtility(ITranslationImportQueue)
        self.importer_person = self.factory.makePerson()

    def test_FileImporter_importMessage_NotImplemented(self):
        importer = self._createFileImporter()
        self.failUnlessRaises(NotImplementedError,
            importer.importMessage, None)

    def test_FileImporter_format_exporter(self):
        # Test if format_exporter behaves like a singleton
        importer = self._createFileImporter()
        self.failUnless(importer._cached_format_exporter is None,
            "FileImporter._cached_format_exporter was not None, "
            "although it had not been used yet.")

        format_exporter1 = importer.format_exporter
        self.failUnless(format_exporter1 is not None,
            "FileImporter.format_exporter was not instantiated on demand.")

        format_exporter2 = importer.format_exporter
        self.failUnless(format_exporter1 is format_exporter2,
            "FileImporter.format_exporter was instantiated multiple time, "
            "but should have been cached.")

    def test_FileImporter_getOrCreatePOTMsgSet(self):
        pot_importer = self._createPOTFileImporter(
            TEST_TEMPLATE_EXPORTED, False)
        # There is another test (init) to make sure this works.
        message = pot_importer.translation_file.messages[0]
        # Try to get the potmsgset by hand to verify it is not already in
        # the DB
        potmsgset1 = (
            pot_importer.potemplate.getPOTMsgSetByMsgIDText(
                message.msgid_singular, plural_text=message.msgid_plural,
                context=message.context))
        self.failUnless(potmsgset1 is None,
            "IPOTMsgSet object already existed in DB, unable to test "
            "FileImporter.getOrCreatePOTMsgSet")

        potmsgset1 = pot_importer.getOrCreatePOTMsgSet(message)
        self.failUnless(potmsgset1 is not None,
            "FileImporter.getOrCreatePOTMessageSet did not create a new "
            "IPOTMsgSet object in the database.")

        potmsgset2 = pot_importer.getOrCreatePOTMsgSet(message)
        self.failUnlessEqual(potmsgset1.id, potmsgset2.id,
            "FileImporter.getOrCreatePOTMessageSet did not get an existing "
            "IPOTMsgSet object from the database.")

    def _test_storeTranslationsInDatabase_empty(self, by_maintainer=True):
        """Check whether we store empty messages appropriately."""
        # Construct a POFile importer.
        pot_importer = self._createPOTFileImporter(
            TEST_TEMPLATE_EXPORTED, by_maintainer=True)
        importer = self._createPOFileImporter(
            pot_importer, TEST_TRANSLATION_EXPORTED,
            by_maintainer=by_maintainer, person=self.importer_person)

        # Empty message to import.
        message = TranslationMessageData()
        message.addTranslation(0, u'')

        potmsgset = self.factory.makePOTMsgSet(
            potemplate=importer.potemplate, sequence=50)
        translation = importer.storeTranslationsInDatabase(
            message, potmsgset)
        # No TranslationMessage is created.
        self.assertIs(None, translation)

    def test_storeTranslationsInDatabase_empty_imported(self):
        """Storing empty messages for maintainer uploads appropriately."""
        self._test_storeTranslationsInDatabase_empty(by_maintainer=True)

    def test_storeTranslationsInDatabase_empty_user(self):
        """Store empty messages for user uploads appropriately."""
        self._test_storeTranslationsInDatabase_empty(by_maintainer=False)

    def test_FileImporter_storeTranslationsInDatabase_privileges(self):
        """Test `storeTranslationsInDatabase` privileges."""

        # On an upstream import, unprivileged person can still store
        # translations if they were able to add an entry to the queue.
        unprivileged_person = self.factory.makePerson()

        # Steps:
        #  * Get a POT importer and import a POT file.
        #  * Get a POTMsgSet in the imported template.
        #  * Create an upstream PO file importer with unprivileged
        #    person as the importer.
        #  * Make sure this person lacks editing permissions.
        #  * Try storing translations and watch it succeed.
        #
        pot_importer = self._createPOTFileImporter(
            TEST_TEMPLATE_EXPORTED, True)
        pot_importer.importFile()
        product = pot_importer.potemplate.productseries.product
        product.translationpermission = TranslationPermission.CLOSED
        product.translationgroup = self.factory.makeTranslationGroup(
            self.importer_person)
        self.fake_librarian.pretendCommit()

        # Get one POTMsgSet to do storeTranslationsInDatabase on.
        message = pot_importer.translation_file.messages[0]
        potmsgset = (
            pot_importer.potemplate.getPOTMsgSetByMsgIDText(
                message.msgid_singular, plural_text=message.msgid_plural,
                context=message.context))

        po_importer = self._createPOFileImporter(
            pot_importer, TEST_TRANSLATION_EXPORTED, by_maintainer=True,
            person=unprivileged_person)

        entry = removeSecurityProxy(
            po_importer.translation_import_queue_entry)
        entry.importer = po_importer.translation_import_queue_entry.importer
        is_editor = po_importer.pofile.canEditTranslations(
            unprivileged_person)
        self.assertFalse(is_editor,
            "Unprivileged person is a translations editor.")

        translation_message = po_importer.translation_file.messages[0]
        db_message = po_importer.storeTranslationsInDatabase(
            translation_message, potmsgset)
        self.assertNotEqual(db_message, None)

    def test_FileImporter_init(self):
        (pot_importer, po_importer) = self._createImporterForExportedEntries()
        # The number of test messages is constant (see above).
        self.failUnlessEqual(
            len(pot_importer.translation_file.messages),
            NUMBER_OF_TEST_MESSAGES,
            "FileImporter.__init__ did not parse the template file "
            "correctly.")
        # Test if POTFileImporter gets initialized correctly.
        self.failUnless(pot_importer.potemplate is not None,
            "POTFileImporter had no reference to an IPOTemplate.")
        self.failUnless(pot_importer.pofile is None or
            pot_importer.pofile.language == "en",
            "POTFileImporter referenced an IPOFile which was not English.")
        # Test if POFileImporter gets initialized correctly.
        self.failUnless(po_importer.potemplate is not None,
            "POTFileImporter had no reference to an IPOTemplate.")
        self.failUnless(po_importer.pofile is not None,
            "POFileImporter had no reference to an IPOFile.")

    def test_FileImporter_getPersonByEmail(self):
        (pot_importer, po_importer) = self._createImporterForExportedEntries()
        # Check whether we create new persons with the correct explanation.
        # When importing a POFile, it may be necessary to create new Person
        # entries, to represent the last translators of that POFile.
        test_email = 'danilo@canonical.com'
        personset = getUtility(IPersonSet)

        # The account we are going to use is not yet in Launchpad.
        self.failUnless(
            personset.getByEmail(test_email) is None,
            'There is already an account for %s' % test_email)

        person = po_importer._getPersonByEmail(test_email)

        self.failUnlessEqual(
            person.creation_rationale.name, 'POFILEIMPORT',
            '%s was not created due to a POFile import' % test_email)
        self.failUnlessEqual(
            person.creation_comment,
            'when importing the %s translation of %s' % (
                po_importer.pofile.language.displayname,
                po_importer.potemplate.displayname),
            'Did not create the correct comment for %s' % test_email)

    def test_getPersonByEmail_bad_address(self):
        # _getPersonByEmail returns None for malformed addresses.
        (pot_importer, po_importer) = self._createImporterForExportedEntries()
        test_email = 'john over at swansea'

        person = po_importer._getPersonByEmail(test_email)

        self.assertEqual(None, person)

    def test_FileImporter_importFile_ok(self):
        # Test correct import operation for both
        # exported and upstream files.
        used_importers = (
            self._createImporterForExportedEntries(),
            self._createImporterForUpstreamEntries(),
            )
        for (pot_importer, po_importer) in used_importers:
            # Run the import and see if PotMsgSet and TranslationMessage
            # entries are correctly created in the DB.
            errors, warnings = pot_importer.importFile()
            self.failUnlessEqual(len(errors), 0,
                "POTFileImporter.importFile returned errors where there "
                "should be none.")
            potmsgset = pot_importer.potemplate.getPOTMsgSetByMsgIDText(
                                                                TEST_MSGID)
            self.failUnless(potmsgset is not None,
                "POTFileImporter.importFile did not create an IPOTMsgSet "
                "object in the database.")

            errors, warnings = po_importer.importFile()
            self.failUnlessEqual(len(errors), 0,
                "POFileImporter.importFile returned errors where there "
                "should be none.")
            potmsgset = po_importer.pofile.potemplate.getPOTMsgSetByMsgIDText(
                                                        unicode(TEST_MSGID))
            message = potmsgset.getCurrentTranslation(
                po_importer.potemplate, po_importer.pofile.language,
                po_importer.potemplate.translation_side)
            self.failUnless(message is not None,
                "POFileImporter.importFile did not create an "
                "ITranslationMessage object in the database.")

    def test_FileImporter_importFile_conflict(self):
        (pot_importer, po_importer) = (
            self._createImporterForExportedEntries())
        # Use importFile to store a template and a translation.
        # Then try to store a different translation for the same msgid
        # with an earlier export timestamp to provoke an update conflict.

        # First import template.
        errors, warnings = pot_importer.importFile()
        self.failUnlessEqual(len(errors), 0,
            "POTFileImporter.importFile returned errors where there should "
            "be none.")
        # Now import translation.
        errors, warnings = po_importer.importFile()
        self.failUnlessEqual(len(errors), 0,
            "POFileImporter.importFile returned errors where there should "
            "be none.")
        self.fake_librarian.pretendCommit()

        # Create new POFileImporter with an earlier timestamp and
        # a different translation (msgstr).
        po_importer2 = self._createPOFileImporter(
            pot_importer, TEST_TRANSLATION_EXPORTED_EARLIER, False,
            po_importer.pofile)
        # Try to import this, too.
        errors, warnings = po_importer2.importFile()
        self.failUnlessEqual(len(errors), 1,
            "No error detected when importing a pofile with an earlier "
            "export timestamp (update conflict).")
        self.failUnless(
            errors[0]['error-message'].find(
                u"updated by someone else after you") != -1,
            "importFile() failed to detect a message update conflict.")

    def test_FileImporter_importFile_error(self):
        # Test that a validation error is handled correctly during import.
        # This is done by trying to store a translation (msgstr) with format
        # spefifiers that do not match those in the msgid, as they should.
        (pot_importer, po_importer) = self._createFileImporters(
            TEST_TEMPLATE_FOR_ERROR,
            TEST_TRANSLATION_FILE_WITH_ERROR, False)
        errors, warnings = pot_importer.importFile()
        self.failUnlessEqual(len(errors), 0,
            "POTFileImporter.importFile returned errors where there should "
            "be none.")
        errors, warnings = po_importer.importFile()
        self.failUnlessEqual(len(errors), 1,
            "No error detected when importing a pofile with mismatched "
            "format specifiers.")
        self.failUnless(errors[0]['error-message'].find(
                u"format specifications in 'msgid' and 'msgstr' "
                u"for argument 1 are not the same") != -1,
            "importFile() failed to detect mismatched format specifiers "
            "when importing a pofile.")
        # Although the message has an error, it should still be stored
        # in the database, though only as a suggestion.
        potmsgset = po_importer.pofile.potemplate.getPOTMsgSetByMsgIDText(
            unicode(TEST_MSGID_ERROR))
        message = potmsgset.getLocalTranslationMessages(
            po_importer.potemplate, po_importer.pofile.language)[0]
        self.failUnless(message is not None,
            "POFileImporter.importFile did not create an "
            "ITranslationMessage object with format errors in the database.")

    def test_ValidationErrorPlusConflict(self):
        # Sometimes a conflict is detected when we resubmit a message as
        # a suggestion because it failed validation.  We don't much care
        # what happens to it, so long as the import doesn't bomb out and
        # the message doesn't become a current translation.
        (pot_importer, po_importer) = self._createFileImporters(
                TEST_TEMPLATE_FOR_ERROR,
                TEST_TRANSLATION_FILE_WITH_ERROR, False)
        pot_importer.importFile()
        po_importer.importFile()
        self.fake_librarian.pretendCommit()

        po_importer2 = self._createPOFileImporter(
            pot_importer, TEST_TRANSLATION_EXPORTED_EARLIER, False,
            po_importer.pofile)
        po_importer2.importFile()

        potmsgset = po_importer.pofile.potemplate.getPOTMsgSetByMsgIDText(
            unicode(TEST_MSGID_ERROR))
        messages = potmsgset.getLocalTranslationMessages(
            po_importer.pofile.potemplate, po_importer.pofile.language)

        for message in messages:
            if message.potmsgset.msgid_singular.msgid == TEST_MSGID_ERROR:
                # This is the accursed message.  Whatever happens, it
                # must not be set as the current translation.
                self.assertFalse(message.is_current_ubuntu)
            else:
                # This is the other message that the doomed message
                # conflicted with.
                self.assertEqual(
                    message.potmsgset.msgid_singular.msgid, TEST_MSGID)
                self.assertEqual(message.translations, [TEST_MSGSTR2])

    def test_InvalidTranslatorEmail(self):
        # A Last-Translator with invalid email address does not upset
        # the importer.  It just picks the uploader as the last
        # translator.
        pot_content = TEST_TEMPLATE_UPSTREAM
        po_content = """
            msgid ""
            msgstr ""
            "PO-Revision-Date: 2005-05-03 20:41+0100\\n"
            "Last-Translator: Hector Atlas <??@??.??>\\n"
            "Content-Type: text/plain; charset=UTF-8\\n"
            "X-Launchpad-Export-Date: 2008-11-05 13:31+0000\\n"

            msgid "%s"
            msgstr "Dankuwel"
            """ % TEST_MSGID
        (pot_importer, po_importer) = self._createFileImporters(
            pot_content, po_content, False)
        pot_importer.importFile()

        po_importer.importFile()
        self.assertEqual(
            po_importer.last_translator,
            po_importer.translation_import_queue_entry.importer)


class CreateFileImporterTestCase(TestCaseWithFactory):
    """Class test for translation importer creation."""
    layer = ZopelessDatabaseLayer

    def setUp(self):
        super(CreateFileImporterTestCase, self).setUp()
        self.fake_librarian = self.useFixture(FakeLibrarian())
        self.translation_import_queue = getUtility(ITranslationImportQueue)
        self.importer_person = self.factory.makePerson()

    def _make_queue_entry(self, by_maintainer):
        pofile = self.factory.makePOFile('eo')
        # Create a header with a newer date than what is found in
        # TEST_TRANSLATION_FILE.
        pofile.header = ("PO-Revision-Date: 2009-01-05 13:22+0000\n"
                         "Content-Type: text/plain; charset=UTF-8\n")
        po_content = TEST_TRANSLATION_FILE % ("", "foo", "bar")
        queue_entry = self.translation_import_queue.addOrUpdateEntry(
            pofile.path, po_content, by_maintainer, self.importer_person,
            productseries=pofile.potemplate.productseries, pofile=pofile)
        self.fake_librarian.pretendCommit()
        return queue_entry

    def test_raises_OutdatedTranslationError_on_user_uploads(self):
        queue_entry = self._make_queue_entry(False)
        self.assertRaises(
            OutdatedTranslationError,
            POFileImporter, queue_entry, GettextPOImporter(), None)

    def test_not_raises_OutdatedTranslationError_on_upstream_uploads(self):
        queue_entry = self._make_queue_entry(True)
        try:
            POFileImporter(queue_entry, GettextPOImporter(), None)
        except OutdatedTranslationError:
            self.fail("OutdatedTranslationError raised.")

    def test_old_upstream_upload_not_changes_header(self):
        queue_entry = self._make_queue_entry(True)
        pofile = queue_entry.pofile
        old_raw_header = pofile.header
        POFileImporter(queue_entry, GettextPOImporter(), None)
        self.assertEqual(old_raw_header, pofile.header)


class FileImporterSharingTest(TestCaseWithFactory):
    """Class test for the sharing operation of the FileImporter base class."""
    layer = LaunchpadZopelessLayer

    POFILE = dedent("""\
        msgid ""
        msgstr ""
        "PO-Revision-Date: 2005-05-03 20:41+0100\\n"
        "Last-Translator: FULL NAME <EMAIL@ADDRESS>\\n"
        "Content-Type: text/plain; charset=UTF-8\\n"
        "X-Launchpad-Export-Date: 2009-05-14 08:54+0000\\n"

        msgid "Thank You"
        msgstr "Translation"
        """)

    def setUp(self):
        super(FileImporterSharingTest, self).setUp()
        # Create the upstream series and template with a translator.
        self.language = self.factory.makeLanguage()
        self.translator = self.factory.makeTranslator(self.language.code)
        self.upstream_productseries = self.factory.makeProductSeries()
        self.upstream_productseries.product.translationgroup = (
            self.translator.translationgroup)
        self.upstream_productseries.product.translationpermission = (
                TranslationPermission.RESTRICTED)
        self.upstream_template = self.factory.makePOTemplate(
                productseries=self.upstream_productseries)

    def _makeImportEntry(self, side, by_maintainer=False, uploader=None,
                         no_upstream=False):
        if side == TranslationSide.UPSTREAM:
            potemplate = self.upstream_template
        else:
            # Create a template in a source package.
            potemplate = self.factory.makePOTemplate(
                name=self.upstream_template.name, side=side)
            distroseries = potemplate.distroseries
            sourcepackagename = potemplate.sourcepackagename
            distroseries.distribution.translation_focus = distroseries
            if not no_upstream:
                # Link the source package to the upstream series to
                # enable sharing.
                self.factory.makeSourcePackagePublishingHistory(
                    sourcepackagename=sourcepackagename,
                    distroseries=distroseries)
                sourcepackage = distroseries.getSourcePackage(
                    sourcepackagename)
                sourcepackage.setPackaging(
                    self.upstream_productseries, self.factory.makePerson())
        pofile = self.factory.makePOFile(
            self.language.code, potemplate=potemplate, create_sharing=True)
        entry = self.factory.makeTranslationImportQueueEntry(
            potemplate=potemplate, by_maintainer=by_maintainer,
            uploader=uploader, content=self.POFILE)
        entry.potemplate = potemplate
        entry.pofile = pofile
        # The uploaded file is only created in the librarian by a commit.
        transaction.commit()
        return entry

    def test_translator_permissions(self):
        # Sanity check that the translator has the right permissions but
        # others don't.
        pofile = self.factory.makePOFile(
            self.language.code, potemplate=self.upstream_template)
        self.assertFalse(
            pofile.canEditTranslations(self.factory.makePerson()))
        self.assertTrue(
            pofile.canEditTranslations(self.translator.translator))

    def test_makeImportEntry_templates_are_sharing(self):
        # Sharing between upstream and Ubuntu was set up correctly.
        entry = self._makeImportEntry(TranslationSide.UBUNTU)
        subset = getUtility(IPOTemplateSet).getSharingSubset(
                distribution=entry.distroseries.distribution,
                sourcepackagename=entry.sourcepackagename)
        self.assertContentEqual(
            [entry.potemplate, self.upstream_template],
            list(subset.getSharingPOTemplates(entry.potemplate.name)))

    def test_share_with_other_side_upstream(self):
        # An upstream queue entry will be shared with ubuntu.
        entry = self._makeImportEntry(TranslationSide.UPSTREAM)
        importer = POFileImporter(
            entry, importers[TranslationFileFormat.PO], None)
        self.assertTrue(
            importer.share_with_other_side,
            "Upstream import should share with Ubuntu.")

    def test_share_with_other_side_ubuntu(self):
        # An ubuntu queue entry will not be shared with upstream.
        entry = self._makeImportEntry(TranslationSide.UBUNTU)
        importer = POFileImporter(
            entry, importers[TranslationFileFormat.PO], None)
        self.assertFalse(
            importer.share_with_other_side,
            "Ubuntu import should not share with upstream.")

    def test_share_with_other_side_ubuntu_no_upstream(self):
        # An ubuntu queue entry cannot share with a non-existent upstream.
        entry = self._makeImportEntry(
            TranslationSide.UBUNTU, no_upstream=True)
        importer = POFileImporter(
            entry, importers[TranslationFileFormat.PO], None)
        self.assertFalse(
            importer.share_with_other_side,
            "Ubuntu import should not share with upstream.")

    def test_share_with_other_side_ubuntu_uploader_upstream_translator(self):
        # If the uploader in ubuntu has rights on upstream as well, the
        # translations are shared.
        entry = self._makeImportEntry(
            TranslationSide.UBUNTU, uploader=self.translator.translator)
        importer = POFileImporter(
            entry, importers[TranslationFileFormat.PO], None)
        self.assertTrue(
            importer.share_with_other_side,
            "Ubuntu import should share with upstream.")

    def test_is_upstream_import_on_sourcepackage_none(self):
        # To do an upstream import on a sourcepackage, three conditions must
        # be met.
        # - It has to be on a sourcepackage.
        # - The by_maintainer flag must be set on the queue entry.
        # - There must be no matching template in the upstream project or
        #   even no upstream project at all.
        # This case meets none of them.
        entry = self._makeImportEntry(
            TranslationSide.UPSTREAM, uploader=self.translator.translator)
        importer = POFileImporter(
            entry, importers[TranslationFileFormat.PO], None)
        self.assertFalse(importer.is_upstream_import_on_sourcepackage)

    def test_is_upstream_import_on_sourcepackage_by_maintainer(self):
        # This entry is by_maintainer.
        entry = self._makeImportEntry(
            TranslationSide.UPSTREAM, by_maintainer=True,
            uploader=self.translator.translator)
        importer = POFileImporter(
            entry, importers[TranslationFileFormat.PO], None)
        self.assertFalse(importer.is_upstream_import_on_sourcepackage)

    def test_is_upstream_import_on_sourcepackage_upstream_template(self):
        # This entry is for a sourcepackage with an upstream potemplate.
        entry = self._makeImportEntry(
            TranslationSide.UBUNTU, uploader=self.translator.translator)
        importer = POFileImporter(
            entry, importers[TranslationFileFormat.PO], None)
        self.assertFalse(importer.is_upstream_import_on_sourcepackage)

    def test_is_upstream_import_on_sourcepackage_upstream_any_template(self):
        # Actually any upstream potemplate will disallow upstream imports.

        # Use _makeImportEntry to create upstream template and packaging
        # link.
        unused_entry = self._makeImportEntry(
            TranslationSide.UBUNTU, uploader=self.translator.translator)

        sourcepackagename = unused_entry.sourcepackagename
        distroseries = unused_entry.distroseries
        other_potemplate = self.factory.makePOTemplate(
            distroseries=distroseries, sourcepackagename=sourcepackagename)

        entry = self.factory.makeTranslationImportQueueEntry(
            potemplate=other_potemplate, by_maintainer=True,
            uploader=self.translator.translator, content=self.POFILE)
        entry.potemplate = other_potemplate
        entry.pofile = self.factory.makePOFile(potemplate=other_potemplate)
        transaction.commit()

        importer = POFileImporter(
            entry, importers[TranslationFileFormat.PO], None)

        self.assertFalse(importer.is_upstream_import_on_sourcepackage)

    def test_is_upstream_import_on_sourcepackage_ok(self):
        # This entry qualifies.
        entry = self._makeImportEntry(
            TranslationSide.UBUNTU, by_maintainer=True, no_upstream=True,
            uploader=self.translator.translator)
        importer = POFileImporter(
            entry, importers[TranslationFileFormat.PO], None)
        self.assertTrue(importer.is_upstream_import_on_sourcepackage)
