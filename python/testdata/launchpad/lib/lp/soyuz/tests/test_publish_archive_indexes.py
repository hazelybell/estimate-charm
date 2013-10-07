# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test native archive index generation for Soyuz."""

import os
import tempfile
import unittest

import apt_pkg

from lp.soyuz.model.publishing import IndexStanzaFields
from lp.soyuz.tests.test_publishing import TestNativePublishingBase


def get_field(stanza_fields, name):
    return dict(stanza_fields.fields).get(name)


class TestNativeArchiveIndexes(TestNativePublishingBase):

    deb_md5 = '008409e7feb1c24a6ccab9f6a62d24c5'
    deb_sha1 = '30b7b4e583fa380772c5a40e428434628faef8cf'
    deb_sha256 = (
        '006ca0f356f54b1916c24c282e6fd19961f4356441401f4b0966f2a00bb3e945')
    dsc_md5 = '5913c3ad52c14a62e6ae7eef51f9ef42'
    dsc_sha1 = 'e35e29b2ea94bbaa831882e11d1f456690f04e69'
    dsc_sha256 = (
        'ac512102db9724bee18f26945efeeb82fdab89819e64e120fbfda755ca50c2c6')

    def setUp(self):
        """Setup global attributes."""
        TestNativePublishingBase.setUp(self)
        apt_pkg.init_system()

    def testSourceStanza(self):
        """Check just-created source publication Index stanza.

        The so-called 'stanza' method return a chunk of text which
        corresponds to the APT index reference.

        It contains specific package attributes, like: name of the source,
        maintainer identification, DSC format and standards version, etc

        Also contains the paths and checksums for the files included in
        the package in question.
        """
        pub_source = self.getPubSource(
            builddepends='fooish', builddependsindep='pyfoo',
            build_conflicts='bar', build_conflicts_indep='pybar')

        self.assertEqual(
            [u'Package: foo',
             u'Binary: foo-bin',
             u'Version: 666',
             u'Section: base',
             u'Maintainer: Foo Bar <foo@bar.com>',
             u'Build-Depends: fooish',
             u'Build-Depends-Indep: pyfoo',
             u'Build-Conflicts: bar',
             u'Build-Conflicts-Indep: pybar',
             u'Architecture: all',
             u'Standards-Version: 3.6.2',
             u'Format: 1.0',
             u'Directory: pool/main/f/foo',
             u'Files:',
             u' %s 28 foo_666.dsc' % self.dsc_md5,
             u'Checksums-Sha1:',
             u' %s 28 foo_666.dsc' % self.dsc_sha1,
             u'Checksums-Sha256:',
             u' %s 28 foo_666.dsc' % self.dsc_sha256,
             ],
            pub_source.getIndexStanza().splitlines())

    def testSourceStanzaCustomFields(self):
        """Check just-created source publication Index stanza
        with custom fields (Python-Version).

        A field is excluded if its key case-insensitively matches one that's
        already there. This mostly affects sources that were uploaded before
        Homepage, Checksums-Sha1 or Checksums-Sha256 were excluded.
        """
        pub_source = self.getPubSource(
            builddepends='fooish', builddependsindep='pyfoo',
            build_conflicts='bar', build_conflicts_indep='pybar',
            user_defined_fields=[
                ("Python-Version", "< 1.5"),
                ("CHECKSUMS-SHA1", "BLAH")])

        self.assertEqual(
            [u'Package: foo',
             u'Binary: foo-bin',
             u'Version: 666',
             u'Section: base',
             u'Maintainer: Foo Bar <foo@bar.com>',
             u'Build-Depends: fooish',
             u'Build-Depends-Indep: pyfoo',
             u'Build-Conflicts: bar',
             u'Build-Conflicts-Indep: pybar',
             u'Architecture: all',
             u'Standards-Version: 3.6.2',
             u'Format: 1.0',
             u'Directory: pool/main/f/foo',
             u'Files:',
             u' %s 28 foo_666.dsc' % self.dsc_md5,
             u'Checksums-Sha1:',
             u' %s 28 foo_666.dsc' % self.dsc_sha1,
             u'Checksums-Sha256:',
             u' %s 28 foo_666.dsc' % self.dsc_sha256,
             u'Python-Version: < 1.5'],
            pub_source.getIndexStanza().splitlines())

    def testBinaryStanza(self):
        """Check just-created binary publication Index stanza.

        See also testSourceStanza, it must present something similar for
        binary packages.
        """
        pub_binaries = self.getPubBinaries(
            depends='biscuit', recommends='foo-dev', suggests='pyfoo',
            conflicts='old-foo', replaces='old-foo', provides='foo-master',
            pre_depends='master-foo', enhances='foo-super', breaks='old-foo',
            phased_update_percentage=50)
        pub_binary = pub_binaries[0]
        self.assertEqual(
            [u'Package: foo-bin',
             u'Source: foo',
             u'Priority: standard',
             u'Section: base',
             u'Installed-Size: 100',
             u'Maintainer: Foo Bar <foo@bar.com>',
             u'Architecture: all',
             u'Version: 666',
             u'Recommends: foo-dev',
             u'Replaces: old-foo',
             u'Suggests: pyfoo',
             u'Provides: foo-master',
             u'Depends: biscuit',
             u'Conflicts: old-foo',
             u'Pre-Depends: master-foo',
             u'Enhances: foo-super',
             u'Breaks: old-foo',
             u'Filename: pool/main/f/foo/foo-bin_666_all.deb',
             u'Size: 18',
             u'MD5sum: ' + self.deb_md5,
             u'SHA1: ' + self.deb_sha1,
             u'SHA256: ' + self.deb_sha256,
             u'Phased-Update-Percentage: 50',
             u'Description: Foo app is great',
             u' Well ...',
             u' it does nothing, though'],
            pub_binary.getIndexStanza().splitlines())

    def testBinaryStanzaWithCustomFields(self):
        """Check just-created binary publication Index stanza with
        custom fields (Python-Version).

        """
        pub_binaries = self.getPubBinaries(
            depends='biscuit', recommends='foo-dev', suggests='pyfoo',
            conflicts='old-foo', replaces='old-foo', provides='foo-master',
            pre_depends='master-foo', enhances='foo-super', breaks='old-foo',
            user_defined_fields=[("Python-Version", ">= 2.4")])
        pub_binary = pub_binaries[0]
        self.assertEqual(
            [u'Package: foo-bin',
             u'Source: foo',
             u'Priority: standard',
             u'Section: base',
             u'Installed-Size: 100',
             u'Maintainer: Foo Bar <foo@bar.com>',
             u'Architecture: all',
             u'Version: 666',
             u'Recommends: foo-dev',
             u'Replaces: old-foo',
             u'Suggests: pyfoo',
             u'Provides: foo-master',
             u'Depends: biscuit',
             u'Conflicts: old-foo',
             u'Pre-Depends: master-foo',
             u'Enhances: foo-super',
             u'Breaks: old-foo',
             u'Filename: pool/main/f/foo/foo-bin_666_all.deb',
             u'Size: 18',
             u'MD5sum: ' + self.deb_md5,
             u'SHA1: ' + self.deb_sha1,
             u'SHA256: ' + self.deb_sha256,
             u'Description: Foo app is great',
             u' Well ...',
             u' it does nothing, though',
             u'Python-Version: >= 2.4'],
            pub_binary.getIndexStanza().splitlines())

    def testBinaryStanzaDescription(self):
        """ Check the description field.

        The description field should formated as:

        Description: <single line synopsis>
         <extended description over several lines>

        The extended description should allow the following formatting
        actions supported by the dpkg-friend tools:

         * lines to be wraped should start with a space.
         * lines to be preserved empty should start with single space followed
           by a single full stop (DOT).
         * lines to be presented in Verbatim should start with two or
           more spaces.

        We just want to check if the original description uploaded and stored
        in the system is preserved when we build the archive index.
        """
        description = (
            "Normal\nNormal"
            "\n.\n.\n."
            "\n %s" % ('x' * 100))
        pub_binary = self.getPubBinaries(
            description=description)[0]

        self.assertEqual(
            [u'Package: foo-bin',
             u'Source: foo',
             u'Priority: standard',
             u'Section: base',
             u'Installed-Size: 100',
             u'Maintainer: Foo Bar <foo@bar.com>',
             u'Architecture: all',
             u'Version: 666',
             u'Filename: pool/main/f/foo/foo-bin_666_all.deb',
             u'Size: 18',
             u'MD5sum: ' + self.deb_md5,
             u'SHA1: ' + self.deb_sha1,
             u'SHA256: ' + self.deb_sha256,
             u'Description: Foo app is great',
             u' Normal',
             u' Normal',
             u' .',
             u' .',
             u' .',
             u' %s' % ('x' * 100),
             ],
            pub_binary.getIndexStanza().splitlines())

    def testBinaryStanzaWithNonAscii(self):
        """Check how will be a stanza with non-ascii content

        Only 'Maintainer' (IPerson.displayname) and 'Description'
        (IBinaryPackageRelease.{summary, description}) can possibly
        contain non-ascii stuff.
        The encoding should be preserved and able to be encoded in
        'utf-8' for disk writing.
        """
        description = u'Using non-ascii as: \xe7\xe3\xe9\xf3'
        pub_binary = self.getPubBinaries(
            description=description)[0]

        self.assertEqual(
            [u'Package: foo-bin',
             u'Source: foo',
             u'Priority: standard',
             u'Section: base',
             u'Installed-Size: 100',
             u'Maintainer: Foo Bar <foo@bar.com>',
             u'Architecture: all',
             u'Version: 666',
             u'Filename: pool/main/f/foo/foo-bin_666_all.deb',
             u'Size: 18',
             u'MD5sum: ' + self.deb_md5,
             u'SHA1: ' + self.deb_sha1,
             u'SHA256: ' + self.deb_sha256,
             u'Description: Foo app is great',
             u' Using non-ascii as: \xe7\xe3\xe9\xf3',
             ],
            pub_binary.getIndexStanza().splitlines())

    def testBinaryOmitsIdenticalSourceName(self):
        # Binaries omit the Source field if it identical to Package.
        pub_source = self.getPubSource(sourcename='foo')
        pub_binary = self.getPubBinaries(
            binaryname='foo', pub_source=pub_source)[0]
        self.assertIs(
            None,
            get_field(pub_binary.buildIndexStanzaFields(), 'Source'))

    def testBinaryIncludesDifferingSourceName(self):
        # Binaries include a Source field if their name differs.
        pub_source = self.getPubSource(sourcename='foo')
        pub_binary = self.getPubBinaries(
            binaryname='foo-bin', pub_source=pub_source)[0]
        self.assertEqual(
            u'foo',
            get_field(pub_binary.buildIndexStanzaFields(), 'Source'))

    def testBinaryIncludesDifferingSourceVersion(self):
        # Binaries also include a Source field if their versions differ.
        pub_source = self.getPubSource(sourcename='foo', version='666')
        pub_binary = self.getPubBinaries(
            binaryname='foo', version='999', pub_source=pub_source)[0]
        self.assertEqual(
            u'foo (666)',
            get_field(pub_binary.buildIndexStanzaFields(), 'Source'))


class TestNativeArchiveIndexesReparsing(TestNativePublishingBase):
    """Tests for ensuring the native archive indexes that we publish
    can be parsed correctly by apt_pkg.TagFile.
    """

    def setUp(self):
        """Setup global attributes."""
        TestNativePublishingBase.setUp(self)
        apt_pkg.init_system()

    def write_stanza_and_reparse(self, stanza):
        """Helper method to return the apt_pkg parser for the stanza."""
        index_filename = tempfile.mktemp()
        index_file = open(index_filename, 'w')
        index_file.write(stanza.encode('utf-8'))
        index_file.close()

        parser = apt_pkg.TagFile(open(index_filename))

        # We're only interested in one stanza, so we'll parse it and remove
        # the tmp file again.
        section = next(parser)
        os.remove(index_filename)

        return section

    def test_getIndexStanza_binary_stanza(self):
        """Check a binary stanza with APT parser."""
        pub_binary = self.getPubBinaries()[0]

        section = self.write_stanza_and_reparse(pub_binary.getIndexStanza())

        self.assertEqual(section.get('Package'), 'foo-bin')
        self.assertEqual(
            section.get('Description').splitlines(),
            ['Foo app is great', ' Well ...', ' it does nothing, though'])

    def test_getIndexStanza_source_stanza(self):
        """Check a source stanza with APT parser."""
        pub_source = self.getPubSource()

        section = self.write_stanza_and_reparse(pub_source.getIndexStanza())

        self.assertEqual(section.get('Package'), 'foo')
        self.assertEqual(section.get('Maintainer'), 'Foo Bar <foo@bar.com>')

    def test_getIndexStanza_with_corrupt_dsc_binaries(self):
        """Ensure corrupt binary fields are written correctly to indexes.

        This is a regression test for bug 436182.

        During upload, our custom parser at:
          lp.archiveuploader.tagfiles.parse_tagfile_lines
        strips leading spaces from subsequent lines of fields with values
        spanning multiple lines, such as the binary field, and in addition
        leaves a trailing '\n' (which results in a blank line after the
        Binary field).

        The second issue causes apt_pkg.TagFile() to error during
        germination when it attempts to parse the generated Sources index.
        But the first issue will also cause apt_pkg.TagFile to skip each
        newline of a multiline field that is not preceded with a space.

        This test ensures that binary fields saved as such will continue
        to be written correctly to index files.

        This test can be removed if the parser is fixed and the corrupt
        data has been cleaned.
        """
        pub_source = self.getPubSource()

        # An example of a corrupt dsc_binaries field. We need to ensure
        # that the corruption is not carried over into the index stanza.
        pub_source.sourcepackagerelease.dsc_binaries = (
            'foo_bin,\nbar_bin,\nzed_bin')

        section = self.write_stanza_and_reparse(pub_source.getIndexStanza())

        self.assertEqual('foo', section['Package'])

        # Without the fix, this raises a key-error due to apt-pkg not
        # being able to parse the file.
        self.assertEqual(
            '666', section['Version'],
            'The Version field should be parsed correctly.')

        # Without the fix, the second binary would not be parsed at all.
        self.assertEqual('foo_bin,\n bar_bin,\n zed_bin', section['Binary'])

    def test_getIndexStanza_with_correct_dsc_binaries(self):
        """Ensure correct binary fields are written correctly to indexes.

        During upload, our custom parser at:
          lp.archiveuploader.tagfiles.parse_tagfile_lines
        strips leading spaces from subsequent lines of fields with values
        spanning multiple lines, such as the binary field, and in addition
        leaves a trailing '\n' (which results in a blank line after the
        Binary field).

        This test ensures that when our parser is updated to store the
        binary field in the same way that apt_pkg.TagFile would, that it
        will continue to be written correctly to index files.
        """
        pub_source = self.getPubSource()

        # An example of a corrupt dsc_binaries field. We need to ensure
        # that the corruption is not carried over into the index stanza.
        pub_source.sourcepackagerelease.dsc_binaries = (
            'foo_bin,\n bar_bin,\n zed_bin')

        section = self.write_stanza_and_reparse(pub_source.getIndexStanza())

        self.assertEqual('foo', section['Package'])

        # Without the fix, this raises a key-error due to apt-pkg not
        # being able to parse the file.
        self.assertEqual(
            '666', section['Version'],
            'The Version field should be parsed correctly.')

        # Without the fix, the second binary would not be parsed at all.
        self.assertEqual('foo_bin,\n bar_bin,\n zed_bin', section['Binary'])


class TestIndexStanzaFieldsHelper(unittest.TestCase):
    """Check how this auxiliary class works...

    This class provides simple FIFO API for aggregating fields
    (name & values) in a ordered way.

    Provides an method to format the option in a ready-to-use string.
    """

    def test_simple(self):
        fields = IndexStanzaFields()
        fields.append('breakfast', 'coffee')
        fields.append('lunch', 'beef')
        fields.append('dinner', 'fish')

        self.assertEqual(3, len(fields.fields))
        self.assertTrue(('dinner', 'fish') in fields.fields)
        self.assertEqual(
            ['breakfast: coffee', 'lunch: beef', 'dinner: fish',
             ], fields.makeOutput().splitlines())

    def test_preserves_order(self):
        fields = IndexStanzaFields()
        fields.append('one', 'um')
        fields.append('three', 'tres')
        fields.append('two', 'dois')

        self.assertEqual(
            ['one: um', 'three: tres', 'two: dois',
             ], fields.makeOutput().splitlines())

    def test_files(self):
        # Special treatment for field named 'Files'
        # do not add a space between <name>:<value>
        # <value> will always start with a new line.
        fields = IndexStanzaFields()
        fields.append('one', 'um')
        fields.append('Files', '<no_sep>')

        self.assertEqual(
            ['one: um', 'Files:<no_sep>'], fields.makeOutput().splitlines())

    def test_extend(self):
        fields = IndexStanzaFields()
        fields.append('one', 'um')
        fields.extend([('three', 'tres'), ['four', 'five']])

        self.assertEqual(
            ['one: um', 'three: tres', 'four: five',
             ], fields.makeOutput().splitlines())
