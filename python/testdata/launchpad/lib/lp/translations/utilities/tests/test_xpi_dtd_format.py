# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

import unittest

from lp.translations.interfaces.translationimporter import (
    TranslationFormatInvalidInputError,
    )
from lp.translations.utilities.mozilla_dtd_parser import DtdFile


class DtdFormatTestCase(unittest.TestCase):
    """Test class for dtd file format."""

    def test_DtdSyntaxError(self):
        # Syntax errors in a DTD file are reported as translation format
        # errors.
        content = '<!ENTITY foo "gah"></ENTITY>'
        self.assertRaises(
            TranslationFormatInvalidInputError, DtdFile, 'test.dtd', None,
            content)

    def test_UTF8DtdFileTest(self):
        """This test makes sure that we handle UTF-8 encoding files."""

        content = (
            '<!ENTITY utf8.message "\xc2\xbfQuieres? \xc2\xa1S\xc3\xad!">')

        dtd_file = DtdFile('test.dtd', None, content)

        # There is a single message.
        self.assertEquals(len(dtd_file.messages), 1)
        message = dtd_file.messages[0]

        self.assertEquals(
            [u'\xbfQuieres? \xa1S\xed!'], message.translations)

    def test_Latin1DtdFileTest(self):
        """This test makes sure that we detect bad encodings."""

        content = '<!ENTITY latin1.message "\xbfQuieres? \xa1S\xed!">\n'

        self.assertRaises(TranslationFormatInvalidInputError, DtdFile, None,
            'test.dtd', content)
