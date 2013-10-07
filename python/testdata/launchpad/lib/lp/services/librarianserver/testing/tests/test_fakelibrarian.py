# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the fake librarian."""

__metaclass__ = type

from StringIO import StringIO

import transaction
from transaction.interfaces import ISynchronizer
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.services.librarian.client import LibrarianClient
from lp.services.librarian.interfaces import ILibraryFileAliasSet
from lp.services.librarian.interfaces.client import ILibrarianClient
from lp.services.librarian.model import (
    LibraryFileAlias,
    LibraryFileAliasSet,
    )
from lp.services.librarianserver.testing.fake import FakeLibrarian
from lp.testing import (
    TestCaseWithFactory,
    verifyObject,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    )


class LibraryAccessScenarioMixin:
    """Simple Librarian uses that can be serviced by the FakeLibrarian.

    This tests the subset of the Librarian interface that is also
    implemented by the FakeLibrarian.  If your test needs anything more
    than this, then you want the real Librarian.
    """

    def _storeFile(self):
        """Store a file in the `FakeLibrarian`.

        :return: Tuple of filename, file contents, alias id.
        """
        name = self.factory.getUniqueString() + '.txt'
        text = self.factory.getUniqueString()
        alias = getUtility(ILibraryFileAliasSet).create(
            name, len(text), StringIO(text), 'text/plain')
        return name, text, alias

    def test_baseline(self):
        self.assertTrue(
            verifyObject(
                ILibrarianClient, getUtility(ILibrarianClient)))
        self.assertTrue(
            verifyObject(
                ILibraryFileAliasSet, getUtility(ILibraryFileAliasSet)))

    def test_insert_retrieve(self):
        name, text, alias = self._storeFile()
        self.assertIsInstance(alias.id, (int, long))

        transaction.commit()

        library_file = getUtility(ILibrarianClient).getFileByAlias(alias.id)
        self.assertEqual(text, library_file.read())

    def test_alias_set(self):
        name, text, alias = self._storeFile()
        retrieved_alias = getUtility(ILibraryFileAliasSet)[alias.id]
        self.assertEqual(alias, retrieved_alias)

    def test_read(self):
        name, text, alias = self._storeFile()
        transaction.commit()
        alias.open()
        self.assertEqual(text, alias.read())

    def test_uncommitted_file(self):
        name, text, alias = self._storeFile()
        retrieved_alias = getUtility(ILibraryFileAliasSet)[alias.id]
        self.assertRaises(LookupError, retrieved_alias.open)

    def test_incorrect_upload_size(self):
        name = self.factory.getUniqueString()
        text = self.factory.getUniqueString()
        wrong_length = len(text) + 1
        self.assertRaises(
            AssertionError,
            getUtility(ILibrarianClient).addFile,
            name, wrong_length, StringIO(text), 'text/plain')

    def test_create_returns_alias(self):
        alias = getUtility(ILibraryFileAliasSet).create(
            'foo.txt', 3, StringIO('foo'), 'text/plain')
        self.assertIsInstance(alias, LibraryFileAlias)

    def test_addFile_returns_alias_id(self):
        alias_id = getUtility(ILibrarianClient).addFile(
            'bar.txt', 3, StringIO('bar'), 'text/plain')
        self.assertIsInstance(alias_id, (int, long))
        self.assertIsInstance(
            getUtility(ILibraryFileAliasSet)[alias_id],
            LibraryFileAlias)

    def test_debugID_is_harmless(self):
        # addFile takes an argument debugID that doesn't do anything
        # observable.  We get a LibraryFileAlias regardless.
        alias = getUtility(ILibraryFileAliasSet).create(
            'txt.txt', 3, StringIO('txt'), 'text/plain', debugID='txt')
        self.assertNotEqual(None, alias)

    def test_getURLForAlias(self):
        name, text, alias = self._storeFile()
        librarian = getUtility(ILibrarianClient)
        self.assertIn(
            librarian.getURLForAlias(alias.id),
            (alias.http_url, alias.https_url))

    def test_getURLForAliasObject(self):
        name, text, alias = self._storeFile()
        librarian = getUtility(ILibrarianClient)
        self.assertEqual(
            librarian.getURLForAlias(alias.id),
            librarian.getURLForAliasObject(alias))

    def test_getURL(self):
        name, text, alias = self._storeFile()
        self.assertIn(alias.getURL(), (alias.http_url, alias.https_url))

    def test_deleted_alias_has_no_url(self):
        name, text, alias = self._storeFile()

        self.assertNotEqual(None, alias.getURL())
        removeSecurityProxy(alias).content = None
        self.assertIs(None, alias.getURL())


class TestFakeLibrarian(LibraryAccessScenarioMixin, TestCaseWithFactory):
    """Test the supported interface subset on the fake librarian."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestFakeLibrarian, self).setUp()
        self.fake_librarian = self.useFixture(FakeLibrarian())

    def test_fake(self):
        self.assertTrue(verifyObject(ISynchronizer, self.fake_librarian))
        self.assertIsInstance(self.fake_librarian, FakeLibrarian)

    def test_pretend_commit(self):
        name, text, alias = self._storeFile()

        self.fake_librarian.pretendCommit()

        retrieved_alias = getUtility(ILibraryFileAliasSet)[alias.id]
        retrieved_alias.open()
        self.assertEqual(text, retrieved_alias.read())


class TestRealLibrarian(LibraryAccessScenarioMixin, TestCaseWithFactory):
    """Test the supported interface subset on the real librarian."""

    layer = LaunchpadFunctionalLayer

    def test_real(self):
        self.assertIsInstance(getUtility(ILibrarianClient), LibrarianClient)
        self.assertIsInstance(
            getUtility(ILibraryFileAliasSet), LibraryFileAliasSet)
