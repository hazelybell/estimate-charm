# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""`MozillaZipTraversal` tests."""

__metaclass__ = type

import unittest

from lp.testing.layers import LaunchpadZopelessLayer
from lp.translations.interfaces.translationimporter import (
    TranslationFormatInvalidInputError,
    )
from lp.translations.utilities.mozilla_zip import MozillaZipTraversal
from lp.translations.utilities.tests.xpi_helpers import (
    get_en_US_xpi_file_to_import,
    )


class TraversalRecorder(MozillaZipTraversal):
    """XPI "parser": records traversal of an XPI or jar file.

    Does nothing but keep track of the structure of nested zip files it
    traverses, and the various parameters for each translatable file.

    Produces a nice list of tuples (representing parameters for a
    translatable file) and lists (representing nested jar files).  Each
    zip file's traversal, including nested ones, is concluded with a
    string containing a full stop (".").
    """
    traversal = None

    def _begin(self):
        self.traversal = []

    def _processTranslatableFile(self, entry, locale_code, xpi_path,
                                 chrome_path, filename_suffix):
        record = (entry, locale_code, xpi_path, chrome_path, filename_suffix)
        self.traversal.append(record)

    def _processNestedJar(self, nested_recorder):
        self.traversal.append(nested_recorder.traversal)

    def _finish(self):
        self.traversal.append('.')


class MozillaZipTraversalTestCase(unittest.TestCase):
    """Test Mozilla XPI/jar traversal."""

    layer = LaunchpadZopelessLayer

    def test_InvalidXpiFile(self):
        # If the "XPI" file isn't really a zip file, that's a
        # TranslationFormatInvalidInputError.
        self.assertRaises(
            TranslationFormatInvalidInputError,
            TraversalRecorder,
            'foo.xpi', __file__)

    def test_XpiTraversal(self):
        """Test a typical traversal of XPI file, with nested jar file."""
        xpi_archive = get_en_US_xpi_file_to_import('en-US')
        record = TraversalRecorder('', xpi_archive)
        self.assertEqual(record.traversal, [
                [
                    ('copyover1.foo', 'en-US',
                        'jar:chrome/en-US.jar!/copyover1.foo',
                        'main/copyover1.foo', '.foo'
                    ),
                    ('subdir/copyover2.foo', 'en-US',
                        'jar:chrome/en-US.jar!/subdir/copyover2.foo',
                        'main/subdir/copyover2.foo', '.foo'
                    ),
                    ('subdir/test2.dtd', 'en-US',
                        'jar:chrome/en-US.jar!/subdir/test2.dtd',
                        'main/subdir/test2.dtd', '.dtd'
                    ),
                    ('subdir/test2.properties', 'en-US',
                        'jar:chrome/en-US.jar!/subdir/test2.properties',
                        'main/subdir/test2.properties', '.properties'
                    ),
                    ('test1.dtd', 'en-US',
                        'jar:chrome/en-US.jar!/test1.dtd',
                        'main/test1.dtd', '.dtd'
                    ),
                    ('test1.properties', 'en-US',
                        'jar:chrome/en-US.jar!/test1.properties',
                        'main/test1.properties', '.properties'
                    ),
                    '.'
                ],
                '.'
            ])

    def test_XpiTraversalWithoutManifest(self):
        """Test traversal of an XPI file without manifest."""
        xpi_archive = get_en_US_xpi_file_to_import('no-manifest')
        record = TraversalRecorder('', xpi_archive)
        # Without manifest, there is no knowledge of locale or chrome
        # paths, so those are None.
        self.assertEqual(record.traversal, [
                [
                    ('file.txt', None,
                        'jar:chrome/en-US.jar!/file.txt', None, '.txt'
                    ),
                    '.'
                ],
                ('no-jar.txt', None,
                    'no-jar.txt', None, '.txt'
                ),
                '.'
            ])
