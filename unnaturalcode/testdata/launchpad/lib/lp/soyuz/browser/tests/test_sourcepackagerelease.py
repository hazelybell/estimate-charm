# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for TestSourcePackageReleaseFiles."""

__metaclass__ = type
__all__ = [
    'TestSourcePackageReleaseFiles',
    'TestSourcePackageReleaseView',
    ]

from zope.security.proxy import removeSecurityProxy

from lp.testing import TestCaseWithFactory
from lp.testing.factory import remove_security_proxy_and_shout_at_engineer
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    )
from lp.testing.views import create_initialized_view


class TestSourcePackageReleaseFiles(TestCaseWithFactory):
    """Source package release files are rendered correctly."""

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestSourcePackageReleaseFiles, self).setUp()
        self.source_package_release = self.factory.makeSourcePackageRelease()

    def test_spr_files_none(self):
        # The snippet renders appropriately when there are no files.
        view = create_initialized_view(self.source_package_release, "+files")
        html = view.__call__()
        self.failUnless('No files available for download.' in html)

    def test_spr_files_one(self):
        # The snippet links to the file when present.
        library_file = self.factory.makeLibraryFileAlias(
            filename='test_file.dsc', content='0123456789')
        self.source_package_release.addFile(library_file)
        view = create_initialized_view(self.source_package_release, "+files")
        html = view.__call__()
        self.failUnless('test_file.dsc' in html)

    def test_spr_files_deleted(self):
        # The snippet handles deleted files too.
        library_file = self.factory.makeLibraryFileAlias(
            filename='test_file.dsc', content='0123456789')
        self.source_package_release.addFile(library_file)
        removeSecurityProxy(library_file).content = None
        view = create_initialized_view(self.source_package_release, "+files")
        html = view.__call__()
        self.failUnless('test_file.dsc (deleted)' in html)


class TestSourcePackageReleaseView(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestSourcePackageReleaseView, self).setUp()
        self.source_package_release = self.factory.makeSourcePackageRelease()

    def test_highlighted_copyright_is_None(self):
        expected = ''
        remove_security_proxy_and_shout_at_engineer(
            self.source_package_release).copyright = None
        view = create_initialized_view(
            self.source_package_release, '+copyright')
        self.assertEqual(expected, view.highlighted_copyright)

    def test_highlighted_copyright_no_matches(self):
        expected = 'nothing to see and/or do.'
        remove_security_proxy_and_shout_at_engineer(
            self.source_package_release).copyright = expected
        view = create_initialized_view(
            self.source_package_release, '+copyright')
        self.assertEqual(expected, view.highlighted_copyright)

    def test_highlighted_copyright_match_url(self):
        remove_security_proxy_and_shout_at_engineer(
            self.source_package_release).copyright = (
            'Downloaded from https://upstream.dom/fnord/no/ and')
        expected = (
            'Downloaded from '
            '<span class="highlight">https://upstream.dom/fnord/no/</span> '
            'and')
        view = create_initialized_view(
            self.source_package_release, '+copyright')
        self.assertEqual(expected, view.highlighted_copyright)

    def test_highlighted_copyright_match_path(self):
        remove_security_proxy_and_shout_at_engineer(
            self.source_package_release).copyright = (
            'See /usr/share/common-licenses/GPL')
        expected = (
            'See '
            '<span class="highlight">/usr/share/common-licenses/GPL</span>')
        view = create_initialized_view(
            self.source_package_release, '+copyright')
        self.assertEqual(expected, view.highlighted_copyright)

    def test_highlighted_copyright_match_multiple(self):
        remove_security_proxy_and_shout_at_engineer(
            self.source_package_release).copyright = (
            'See /usr/share/common-licenses/GPL or https://osi.org/mit')
        expected = (
            'See '
            '<span class="highlight">/usr/share/common-licenses/GPL</span> '
             'or <span class="highlight">https://osi.org/mit</span>')
        view = create_initialized_view(
            self.source_package_release, '+copyright')
        self.assertEqual(expected, view.highlighted_copyright)
