#! /usr/bin/python
#
# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test `reupload_translations` and `ReuploadPackageTranslations`."""

__metaclass__ = type

import re
from StringIO import StringIO
import tarfile

import transaction
from zope.security.proxy import removeSecurityProxy

from lp.registry.model.sourcepackage import SourcePackage
from lp.services.librarian.model import LibraryFileAliasSet
from lp.services.scripts.tests import run_script
from lp.soyuz.model.sourcepackagerelease import (
    _filter_ubuntu_translation_file,
    )
from lp.testing import TestCaseWithFactory
from lp.testing.layers import LaunchpadZopelessLayer
from lp.translations.model.translationimportqueue import (
    TranslationImportQueue,
    )
from lp.translations.scripts.reupload_translations import (
    ReuploadPackageTranslations,
    )


class UploadInjector:
    """Mockup for `SourcePackage.getLatestTranslationsUploads`.

    If patched into a `SourcePackage` object, makes its
    getLatestTranslationsUploads method return the given library file
    alias.
    """

    def __init__(self, script, tar_alias):
        self.tar_alias = tar_alias
        self.script = script
        self.original_findPackage = script._findPackage

    def __call__(self, name):
        package = self.original_findPackage(name)
        removeSecurityProxy(package).getLatestTranslationsUploads = (
            self._fakeTranslationsUpload)
        return package

    def _fakeTranslationsUpload(self):
        return [self.tar_alias]


def upload_tarball(translation_files):
    """Create a tarball and upload it to the Librarian.

    :param translation_files: A dict mapping filenames to file contents.
    :return: A `LibraryFileAlias`.
    """
    buf = StringIO()
    tarball = tarfile.open('', 'w:gz', buf)
    for name, contents in translation_files.iteritems():
        pseudofile = StringIO(contents)
        tarinfo = tarfile.TarInfo()
        tarinfo.name = name
        tarinfo.size = len(contents)
        tarinfo.type = tarfile.REGTYPE
        tarball.addfile(tarinfo, pseudofile)

    tarball.close()
    buf.flush()
    tarsize = buf.tell()
    buf.seek(0)

    return LibraryFileAliasSet().create(
        'uploads.tar.gz', tarsize, buf, 'application/x-gtar')


def summarize_translations_queue(sourcepackage):
    """Describe queue entries for `sourcepackage` as a name/contents dict."""
    entries = TranslationImportQueue().getAllEntries(sourcepackage)
    return dict((entry.path, entry.content.read()) for entry in entries)


def filter_paths(files_dict):
    """Apply `_filter_ubuntu_translation_file` to each file in `files_dict.`

    :param files_dict: A dict mapping translation file names to their
        contents.
    :return: A similar dict, but with `_filter_ubuntu_translation_file`
        applied to each file's path, and non-Ubuntu files left out.
    """
    filtered_dict = {}
    for original_path, content in files_dict.iteritems():
        new_path = _filter_ubuntu_translation_file(original_path)
        if new_path:
            filtered_dict[new_path] = content

    return filtered_dict


class TestReuploadPackageTranslations(TestCaseWithFactory):
    """Test `ReuploadPackageTranslations`."""
    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestReuploadPackageTranslations, self).setUp()
        sourcepackagename = self.factory.makeSourcePackageName()
        distroseries = self.factory.makeDistroSeries()
        self.sourcepackage = SourcePackage(sourcepackagename, distroseries)
        self.script = ReuploadPackageTranslations('reupload', test_args=[
            '-d', distroseries.distribution.name,
            '-s', distroseries.name,
            '-p', sourcepackagename.name,
            '-qqq'])

    def _uploadAndProcess(self, files_dict):
        """Fake an upload and cause _processPackage to be run on it.

        :param files_dict: A dict mapping file paths to file contents.
        :return: A dict describing the resulting import queue for the
            package.
        """
        tar_alias = upload_tarball(files_dict)

        # Force Librarian update
        transaction.commit()

        self.script._findPackage = UploadInjector(self.script, tar_alias)
        self.script.main()
        self.assertEqual([], self.script.uploadless_packages)

        # Force Librarian update
        transaction.commit()

        return summarize_translations_queue(self.sourcepackage)

    def test_findPackage(self):
        # _findPackage finds a SourcePackage by name.
        self.script._setDistroDetails()
        found_package = self.script._findPackage(
            self.sourcepackage.sourcepackagename.name)
        self.assertEqual(self.sourcepackage, found_package)

    def test_processPackage_nothing(self):
        # A package need not have a translations upload.  The script
        # notices this but does nothing about it.
        self.script.main()
        self.assertEqual(
            [self.sourcepackage], self.script.uploadless_packages)

    def test_processPackage(self):
        # _processPackage will fetch the package's latest translations
        # upload from the Librarian and re-import it.
        translation_files = {
            'source/po/messages.pot': '# pot',
            'source/po/nl.po': '# nl',
        }
        queue_summary = self._uploadAndProcess(translation_files)
        self.assertEqual(filter_paths(translation_files), queue_summary)

    def test_processPackage_filters_paths(self):
        # Uploads are filtered just like other Ubuntu tarballs.
        translation_files = {
            'source/foo.pot': '# foo',
            'elsewhere/bar.pot': '# bar',
        }
        queue_summary = self._uploadAndProcess(translation_files)
        self.assertEqual({'foo.pot': '# foo'}, queue_summary)


class TestReuploadScript(TestCaseWithFactory):
    """Test reupload-translations script."""
    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestReuploadScript, self).setUp()
        self.distroseries = self.factory.makeDistroSeries()
        self.sourcepackagename1 = self.factory.makeSourcePackageName()
        self.sourcepackagename2 = self.factory.makeSourcePackageName()
        transaction.commit()

    def test_reupload_translations(self):
        """Test a run of the script."""
        retcode, stdout, stderr = run_script(
            'scripts/rosetta/reupload-translations.py', [
                '-d', self.distroseries.distribution.name,
                '-s', self.distroseries.name,
                '-p', self.sourcepackagename1.name,
                '-p', self.sourcepackagename2.name,
                '-v',
                '--dry-run',
            ])

        self.assertEqual(0, retcode)
        self.assertEqual('', stdout)

        expected_output = (
            "INFO\s*Dry run.  Not really uploading anything.\n"
            "INFO\s*Processing [^\s]+ in .*\n"
            "WARNING\s*Found no translations upload for .*\n"
            "INFO\s*Processing [^\s]+ in .*\n"
            "WARNING\s*Found no translations upload for .*\n"
            "INFO\s*Done.\n")
        self.assertTrue(
            re.match(expected_output, stderr),
            'expected %s, got %s' % (expected_output, stderr))
