# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for XPI manifests."""

__metaclass__ = type

import unittest

from lp.translations.interfaces.translationimporter import (
    TranslationFormatSyntaxError,
    )
from lp.translations.utilities.xpi_manifest import XpiManifest


class XpiManifestTestCase(unittest.TestCase):
    """Test `XpiManifest`."""

    def test_TrivialParse(self):
        # Parse and use minimal manifest.
        manifest = XpiManifest("locale chromepath en-US directory/")
        self.assertEqual(len(manifest._locales), 1)
        chrome_path, locale = manifest.getChromePathAndLocale(
            'directory/file.dtd')
        self.failIf(chrome_path is None, "Failed to match simple path")
        self.assertEqual(
            chrome_path, "chromepath/file.dtd", "Bad chrome path")

    def test_NonMatch(self):
        # Failure to match path.
        manifest = XpiManifest("locale chromepath en-US directory/")
        chrome_path, locale = manifest.getChromePathAndLocale(
            'nonexistent/file')
        self.failIf(chrome_path is not None, "Unexpected path match.")
        self.failIf(locale is not None, "Got locale without a match.")

    def test_NoUsefulLines(self):
        # Parse manifest without useful data.  Lines that don't match what
        # we're looking for are ignored.
        manifest = XpiManifest("""
            There are no usable
            locale lines
            in this file.
            """.lstrip())
        self.assertEqual(len(manifest._locales), 0)
        chrome_path, locale = manifest.getChromePathAndLocale('lines')
        self.failIf(chrome_path is not None, "Empty manifest matched a path.")
        chrome_path, locale = manifest.getChromePathAndLocale('')
        self.failIf(chrome_path is not None, "Matched empty path.")

    def _checkSortOrder(self, manifest):
        """Verify that manifest is sorted by increasing path length."""
        last_entry = None
        for entry in manifest._locales:
            if last_entry is not None:
                self.failIf(len(entry.path) < len(last_entry.path),
                    "Manifest entries not sorted by increasing path length.")
            last_entry = entry

    def test_MultipleLines(self):
        # Parse manifest file with multiple entries.
        manifest = XpiManifest("""
            locale foo en-US foodir/
            locale bar en-US bardir/
            locale ixx en-US ixxdir/
            locale gna en-US gnadir/
            """.lstrip())
        self.assertEqual(len(manifest._locales), 4)
        self._checkSortOrder(manifest)
        for dir in ['gna', 'bar', 'ixx', 'foo']:
            path = "%sdir/file.html" % dir
            chrome_path, locale = manifest.getChromePathAndLocale(path)
            self.assertEqual(chrome_path, "%s/file.html" % dir,
                "Bad chrome path in multi-line parse.")
            self.assertEqual(
                locale, 'en-US', "Bad locale in multi-line parse.")

    def test_MultipleLocales(self):
        # Different locales.
        dirs = {
            'foo': 'en-US',
            'bar': 'es',
            'ixx': 'zh_CN',
            'zup': 'zh_TW',
            'gna': 'pt',
            'gnu': 'pt_BR'
            }
        manifest_text = '\n'.join([
            "locale %s %s %sdir/\n" % (dir, locale, dir)
            for dir, locale in dirs.iteritems()
            ])
        manifest = XpiManifest(manifest_text)
        self._checkSortOrder(manifest)
        for dir, dirlocale in dirs.iteritems():
            path = "%sdir/file.html" % dir
            chrome_path, locale = manifest.getChromePathAndLocale(path)
            self.assertEqual(chrome_path, "%s/file.html" % dir,
                "Bad chrome path in multi-line parse.")
            self.assertEqual(locale, dirlocale, "Locales got mixed up.")

    def test_IgnoredLines(self):
        # Ignored lines: anything that doesn't start with "locale" or doesn't
        # have the right number of arguments.  The one correct line is picked
        # out though.
        manifest = XpiManifest("""
            nonlocale obsolete fr foodir/
            anotherline

            #locale obsolete fr foodir/
            locale okay fr foodir/
            locale overlong fr foordir/ etc. etc. etc.
            locale incomplete fr
            """.lstrip())
        self.assertEqual(len(manifest._locales), 1)
        chrome_path, locale = manifest.getChromePathAndLocale('foodir/x')
        self.failIf(chrome_path is None, "Garbage lines messed up match.")
        self.assertEqual(chrome_path, "okay/x", "Matched wrong line.")
        self.assertEqual(locale, "fr", "Inexplicably mismatched locale.")

    def test_DuplicateLines(self):
        # The manifest ignores redundant lines with the same path.
        manifest = XpiManifest("""
            locale dup fy boppe
            locale dup fy boppe
            """.lstrip())
        self.assertEqual(len(manifest._locales), 1)

    def _checkLookup(self, manifest, path, chrome_path, locale):
        """Helper: look up `path` in `manifest`, expect given output."""
        found_chrome_path, found_locale = manifest.getChromePathAndLocale(
            path)
        self.failIf(found_chrome_path is None, "No match found for " + path)
        self.assertEqual(found_chrome_path, chrome_path)
        self.assertEqual(found_locale, locale)

    def test_NormalizedLookup(self):
        # Both sides of a path lookup are normalized, so that a matching
        # prefix is recognized in a path even if the two have some meaningless
        # differences in their spelling.
        manifest = XpiManifest("locale x nn //a/dir")
        self._checkLookup(manifest, "a//dir///etc", 'x/etc', 'nn')

    def _checkNormalize(self, bad_path, good_path):
        """Test that `bad_path` normalizes to `good_path`."""
        self.assertEqual(XpiManifest._normalizePath(bad_path), good_path)

    def test_Normalize(self):
        # These paths are all wrong or difficult for one reason or another.
        # Check that the normalization of paths renders those little
        # imperfections irrelevant to path lookup.
        self._checkNormalize('x/', 'x/')
        self._checkNormalize('x', 'x')
        self._checkNormalize('/x', 'x')
        self._checkNormalize('//x', 'x')
        self._checkNormalize('/x/', 'x/')
        self._checkNormalize('x//', 'x/')
        self._checkNormalize('x///', 'x/')
        self._checkNormalize('x/y/', 'x/y/')
        self._checkNormalize('x/y', 'x/y')
        self._checkNormalize('x//y/', 'x/y/')

    def test_PathBoundaries(self):
        # Paths can only match on path boundaries, where the slashes are
        # supposed to be.
        manifest = XpiManifest("""
            locale short el /ploink/squit
            locale long he /ploink/squittle
            """.lstrip())
        self._checkSortOrder(manifest)
        self._checkLookup(manifest, 'ploink/squit/x', 'short/x', 'el')
        self._checkLookup(manifest, '/ploink/squittle/x', 'long/x', 'he')

    def test_Overlap(self):
        # Path matching looks for longest prefix.  Make sure this works right,
        # even when nested directories are in "overlapping" manifest entries.
        manifest = XpiManifest("""
            locale foo1 ca a/
            locale foo2 ca a/b/
            locale foo3 ca a/b/c/x1
            locale foo4 ca a/b/c/x2
            """.lstrip())
        self._checkSortOrder(manifest)
        self._checkLookup(manifest, 'a/bb', 'foo1/bb', 'ca')
        self._checkLookup(manifest, 'a/bb/c', 'foo1/bb/c', 'ca')
        self._checkLookup(manifest, 'a/b/y', 'foo2/y', 'ca')
        self._checkLookup(manifest, 'a/b/c/', 'foo2/c/', 'ca')
        self._checkLookup(manifest, 'a/b/c/x12', 'foo2/c/x12', 'ca')
        self._checkLookup(manifest, 'a/b/c/x1/y', 'foo3/y', 'ca')
        self._checkLookup(manifest, 'a/b/c/x2/y', 'foo4/y', 'ca')

    def test_JarLookup(self):
        # Simple, successful lookup of a correct path inside a jar file.
        manifest = XpiManifest("""
            locale foo en_GB jar:foo.jar!/dir/
            locale bar id jar:bar.jar!/
            """.lstrip())
        self._checkSortOrder(manifest)
        self._checkLookup(
            manifest, 'jar:foo.jar!/dir/file', 'foo/file', 'en_GB')
        self._checkLookup(
            manifest, 'jar:bar.jar!/dir/file', 'bar/dir/file', 'id')

    def test_JarNormalization(self):
        # Various badly-formed or corner-case paths.  All get normalized.
        self._checkNormalize('jar:jarless/path', 'jarless/path')
        self._checkNormalize(
            'jar:foo.jar!/contained/file', 'jar:foo.jar!/contained/file')
        self._checkNormalize(
            'foo.jar!contained/file', 'jar:foo.jar!/contained/file')
        self._checkNormalize(
            'jar:foo.jar!//contained/file', 'jar:foo.jar!/contained/file')
        self._checkNormalize('splat.jar!', 'jar:splat.jar!/')
        self._checkNormalize('dir/x.jar!dir', 'jar:dir/x.jar!/dir')

    def test_NestedJarNormalization(self):
        # Test that paths with jars inside jars are normalized correctly.
        self._checkNormalize(
            'jar:dir/x.jar!/y.jar!/dir', 'jar:dir/x.jar!/y.jar!/dir')
        self._checkNormalize(
            'dir/x.jar!y.jar!dir', 'jar:dir/x.jar!/y.jar!/dir')
        self._checkNormalize(
            'dir/x.jar!/dir/y.jar!', 'jar:dir/x.jar!/dir/y.jar!/')

    def test_JarMixup(self):
        # Two jar files can have files for the same locale.  Two locales can
        # have files in the same jar file.  Two translations in different
        # places can have the same chrome path.
        manifest = XpiManifest("""
            locale serbian sr jar:translations.jar!/sr/
            locale croatian hr jar:translations.jar!/hr/
            locale docs sr jar:docs.jar!/sr/
            locale docs hr jar:docs.jar!/hr/
            """.lstrip())
        self._checkSortOrder(manifest)
        self._checkLookup(
            manifest, 'jar:translations.jar!/sr/x', 'serbian/x', 'sr')
        self._checkLookup(
            manifest, 'jar:translations.jar!/hr/x', 'croatian/x', 'hr')
        self._checkLookup(manifest, 'jar:docs.jar!/sr/x', 'docs/x', 'sr')
        self._checkLookup(manifest, 'jar:docs.jar!/hr/x', 'docs/x', 'hr')

    def test_NestedJars(self):
        # Jar files can be contained in jar files.
        manifest = XpiManifest("""
            locale x it jar:dir/x.jar!/subdir/y.jar!/
            locale y it jar:dir/x.jar!/subdir/y.jar!/deep/
            locale z it jar:dir/x.jar!/subdir/z.jar!/
            """.lstrip())
        self._checkSortOrder(manifest)
        self._checkLookup(
            manifest, 'jar:dir/x.jar!/subdir/y.jar!/foo', 'x/foo', 'it')
        self._checkLookup(
            manifest, 'jar:dir/x.jar!/subdir/y.jar!/deep/foo', 'y/foo', 'it')
        self._checkLookup(
            manifest, 'dir/x.jar!/subdir/z.jar!/foo', 'z/foo', 'it')

    def test_ContainsLocales(self):
        # Jar files need to be descended into if any locale line mentions a
        # path inside them.
        manifest = XpiManifest("locale in my jar:x/foo.jar!/y")
        self.failIf(not manifest.containsLocales("jar:x/foo.jar!/"))
        self.failIf(manifest.containsLocales("jar:zzz/foo.jar!/"))

    def test_NormalizeContainsLocales(self):
        # "containsLocales" lookup is normalized, just like chrome path
        # lookup, so it's not fazed by syntactical misspellings.
        manifest = XpiManifest("locale main kh jar:/x/foo.jar!bar.jar!")
        self.failIf(not manifest.containsLocales("x/foo.jar!//bar.jar!/"))

    def test_ReverseMapping(self):
        # Test "reverse mapping" from chrome path to XPI path.
        manifest = XpiManifest(
            "locale browser en-US jar:locales/en-US.jar!/chrome/")
        path = manifest.findMatchingXpiPath('browser/gui/print.dtd', 'en-US')
        self.assertEqual(path, "jar:locales/en-US.jar!/chrome/gui/print.dtd")

    def test_NoReverseMapping(self):
        # Failed reverse lookup.
        manifest = XpiManifest(
            "locale browser en-US jar:locales/en-US.jar!/chrome/")
        path = manifest.findMatchingXpiPath('manual/gui/print.dtd', 'en-US')
        self.assertEqual(path, None)

    def test_ReverseMappingWrongLocale(self):
        # Reverse mapping fails if given the wrong locale.
        manifest = XpiManifest(
            "locale browser en-US jar:locales/en-US.jar!/chrome/")
        path = manifest.findMatchingXpiPath('browser/gui/print.dtd', 'pt')
        self.assertEqual(path, None)

    def test_ReverseMappingLongestMatch(self):
        # Reverse mapping always finds the longest match.
        manifest = XpiManifest("""
            locale browser en-US jar:locales/
            locale browser en-US jar:locales/en-US.jar!/chrome/
            locale browser en-US jar:locales/en-US.jar!/
            """.lstrip())
        path = manifest.findMatchingXpiPath('browser/gui/print.dtd', 'en-US')
        self.assertEqual(path, "jar:locales/en-US.jar!/chrome/gui/print.dtd")

    def test_blank_line(self):
        # Manifests must not begin with newline.
        self.assertRaises(
            TranslationFormatSyntaxError,
            XpiManifest, """
            locale browser en-US jar:locales
            """)
