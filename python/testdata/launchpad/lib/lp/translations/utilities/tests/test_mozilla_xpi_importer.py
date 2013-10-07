# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Mozilla XPI importer tests."""

__metaclass__ = type

import unittest

from zope.interface.verify import verifyObject

from lp.testing.layers import LaunchpadZopelessLayer
from lp.translations.interfaces.translationfileformat import (
    TranslationFileFormat,
    )
from lp.translations.interfaces.translationimporter import (
    ITranslationFormatImporter,
    )
from lp.translations.utilities.mozilla_xpi_importer import MozillaXpiImporter


class MozillaXpiImporterTestCase(unittest.TestCase):
    """Class test for mozilla's .xpi file imports"""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        self.importer = MozillaXpiImporter()

    def testInterface(self):
        """Check whether the object follows the interface."""
        self.failUnless(
            verifyObject(ITranslationFormatImporter, self.importer))

    def testFormat(self):
        """Check that MozillaXpiImporter handles the XPI file format."""
        format = self.importer.getFormat(u'')
        self.failUnless(
            format == TranslationFileFormat.XPI,
            'MozillaXpiImporter format expected XPI but got %s' % format.name)

    def testHasAlternativeMsgID(self):
        """Check that MozillaXpiImporter has an alternative msgid."""
        self.failUnless(
            self.importer.uses_source_string_msgids,
            "MozillaXpiImporter format says it's not using alternative msgid"
            " when it really does!")
