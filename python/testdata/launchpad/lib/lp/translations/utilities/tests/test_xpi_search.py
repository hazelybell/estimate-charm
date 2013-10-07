# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Functional tests for searching through XPI POTemplates"""
__metaclass__ = type

import unittest

from zope.component import getUtility

from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.product import IProductSet
from lp.testing.layers import LaunchpadZopelessLayer
from lp.translations.enums import RosettaImportStatus
from lp.translations.interfaces.potemplate import IPOTemplateSet
from lp.translations.utilities.tests.helpers import (
    import_pofile_or_potemplate,
    )
from lp.translations.utilities.tests.xpi_helpers import (
    get_en_US_xpi_file_to_import,
    )


class XpiSearchTestCase(unittest.TestCase):
    """XPI file import into Launchpad."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        # Get the importer.
        self.importer = getUtility(IPersonSet).getByName('mark')

        # Get the Firefox template.
        firefox_product = getUtility(IProductSet).getByName('firefox')
        firefox_productseries = firefox_product.getSeries('trunk')
        firefox_potemplate_subset = getUtility(IPOTemplateSet).getSubset(
            productseries=firefox_productseries)
        self.firefox_template = firefox_potemplate_subset.new(
            name='firefox',
            translation_domain='firefox',
            path='en-US.xpi',
            owner=self.importer)
        self.spanish_firefox = self.firefox_template.newPOFile('es')
        self.spanish_firefox.path = 'translations/es.xpi'

    def setUpTranslationImportQueueForTemplate(self, subdir):
        """Return an ITranslationImportQueueEntry for testing purposes.

        :param subdir: subdirectory in firefox-data to get XPI data from.
        """
        # Get the file to import.
        en_US_xpi = get_en_US_xpi_file_to_import(subdir)
        return import_pofile_or_potemplate(
            file_contents=en_US_xpi.read(),
            person=self.importer,
            potemplate=self.firefox_template)

    def test_templateSearching(self):
        """Searching through XPI template returns English 'translations'."""
        entry = self.setUpTranslationImportQueueForTemplate('en-US')

        # The status is now IMPORTED:
        self.assertEquals(entry.status, RosettaImportStatus.IMPORTED)

        potmsgsets = self.spanish_firefox.findPOTMsgSetsContaining(
            text='zilla')
        message_list = [message.singular_text for message in potmsgsets]

        self.assertEquals([u'SomeZilla', u'FooZilla!',
                           u'FooZilla Zilla Thingy'],
                          message_list)

    def test_templateSearchingForMsgIDs(self):
        """Searching returns no results for internal msg IDs."""
        entry = self.setUpTranslationImportQueueForTemplate('en-US')

        # The status is now IMPORTED:
        self.assertEquals(entry.status, RosettaImportStatus.IMPORTED)

        potmsgsets = list(self.spanish_firefox.findPOTMsgSetsContaining(
            text='foozilla.title'))

        self.assertEquals(potmsgsets, [])
