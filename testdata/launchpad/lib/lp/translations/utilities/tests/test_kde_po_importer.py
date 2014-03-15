# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""KDE PO importer tests."""

__metaclass__ = type

import unittest

import transaction
from zope.component import getUtility
from zope.interface.verify import verifyObject

from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.product import IProductSet
from lp.testing.layers import LaunchpadZopelessLayer
from lp.translations.interfaces.translationfileformat import (
    TranslationFileFormat,
    )
from lp.translations.interfaces.translationimporter import (
    ITranslationFormatImporter,
    )
from lp.translations.interfaces.translationimportqueue import (
    ITranslationImportQueue,
    )
from lp.translations.utilities.gettext_po_importer import GettextPOImporter
from lp.translations.utilities.kde_po_importer import KdePOImporter
from lp.translations.utilities.tests.test_gettext_po_importer import (
    test_template,
    )


test_kde_template = r'''
msgid ""
msgstr ""
"PO-Revision-Date: 2005-05-03 20:41+0100\n"
"Last-Translator: FULL NAME <EMAIL@ADDRESS>\n"
"Content-Type: text/plain; charset=UTF-8\n"

msgid ""
"_n: %1 foo\n%1 foos"
msgstr ""

msgid "_: Context\nMessage"
msgstr ""
'''

test_kde_translation_file = r'''
msgid ""
msgstr ""
"PO-Revision-Date: 2005-05-03 20:41+0100\n"
"Last-Translator: Carlos Perello Marin <carlos@canonical.com>\n"
"Content-Type: text/plain; charset=UTF-8\n"

msgid "_n: %1 foo\n%1 foos"
msgstr ""
"1st plural form %1\n"
"2nd plural form %1\n"
"3rd plural form %1"

msgid "_: Context\nMessage"
msgstr "Contextual translation"
'''


class KdePOImporterTestCase(unittest.TestCase):
    """Class test for gettext's .po file imports"""
    layer = LaunchpadZopelessLayer

    def setUp(self):
        # Add a new entry for testing purposes. It's a template one.
        self.translation_import_queue = getUtility(ITranslationImportQueue)
        template_path = 'po/testing.pot'
        by_maintainer = True
        personset = getUtility(IPersonSet)
        importer = personset.getByName('carlos')
        productset = getUtility(IProductSet)
        firefox = productset.getByName('firefox')
        firefox_trunk = firefox.getSeries('trunk')
        template_entry = self.translation_import_queue.addOrUpdateEntry(
            template_path, test_kde_template, by_maintainer, importer,
            productseries=firefox_trunk)

        # Add another one, a translation file.
        pofile_path = 'po/sr.po'
        translation_entry = self.translation_import_queue.addOrUpdateEntry(
            pofile_path, test_kde_translation_file, by_maintainer, importer,
            productseries=firefox_trunk)

        # Add a non-KDE PO file which gets recognized as regular PO file
        # (we use different productseries so it doesn't conflict with
        # KDE PO file being imported into firefox_trunk)
        firefox_10 = firefox.getSeries('1.0')
        gettext_template_entry = (
            self.translation_import_queue.addOrUpdateEntry(
                template_path, test_template, by_maintainer, importer,
                productseries=firefox_10))

        transaction.commit()
        self.template_importer = KdePOImporter()
        self.template_file = self.template_importer.parse(template_entry)
        self.translation_importer = KdePOImporter()
        self.translation_file = self.translation_importer.parse(
            translation_entry)

        self.gettext_template_entry = gettext_template_entry

    def testInterface(self):
        """Check whether the object follows the interface."""
        self.failUnless(
            verifyObject(ITranslationFormatImporter, self.template_importer),
            "KdePOImporter doesn't conform to ITranslationFormatImporter"
                "interface.")

    def testFormat(self):
        """Check whether KdePOImporter can handle the KDEPO file format."""
        format = self.template_importer.getFormat(test_kde_template)
        self.failUnless(
            format == TranslationFileFormat.KDEPO,
            'KdePOImporter format expected KDEPO but got %s' % format.name)

    def testKDEPriorityIsHigherThanPOPriority(self):
        """Check if KdePOImporter has precedence over GettextPOImporter."""
        # For import queue to properly recognise KDEPO files which are
        # otherwise just regular PO files, KdePOImporter has to have higher
        # priority over GettextPOImporter
        gettext_importer = GettextPOImporter()

        self.failUnless(
            self.template_importer.priority > gettext_importer.priority,
            'KdePOImporter priority is not higher than priority of '
            'GettextPOImporter')

    def testGettextPOFileFormat(self):
        """Check that non-KDE PO files are recognized as regular PO files."""
        format = self.gettext_template_entry.format
        self.failUnless(format == TranslationFileFormat.PO,
                        ('KdePOImporter format expected PO '
                         'but got %s for non-KDE PO file.' % format.name))

    def testTemplatePlurals(self):
        """Check whether legacy KDE plural forms are correctly imported."""
        message = self.template_file.messages[0]
        singular = message.msgid_singular
        plural = message.msgid_plural
        self.failUnless(
            (singular == u'%1 foo' and plural == u'%1 foos'),
            "KdePOImporter didn't import KDE plural forms correctly.")

    def testTranslationPlurals(self):
        """Check if translated legacy KDE plural forms are correctly imported.
        """
        message = self.translation_file.messages[0]
        translations = message.translations
        self.failUnless(
            (translations[0] == u'1st plural form %1' and
             translations[1] == u'2nd plural form %1' and
             translations[2] == u'3rd plural form %1'),
            "KdePOImporter didn't import translated KDE plural forms "
            "correctly.")

    def testTemplateContext(self):
        """Check whether legacy KDE context is correctly imported."""
        message = self.template_file.messages[1]
        singular = message.msgid_singular
        context = message.context
        self.failUnless(
            (singular == u'Message' and context == u'Context'),
            "KdePOImporter didn't import KDE context correctly.")

    def testTranslationContext(self):
        """Check whether legacy KDE context is correctly imported."""
        message = self.translation_file.messages[1]
        singular = message.msgid_singular
        context = message.context
        translations = message.translations
        self.failUnless(
            (singular == u'Message' and context == u'Context' and
             translations[0] == u'Contextual translation'),
            "KdePOImporter didn't import translated KDE context correctly.")
