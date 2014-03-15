# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from cStringIO import StringIO
import hashlib
import httplib
import textwrap
import unittest
from urllib2 import (
    HTTPError,
    URLError,
    )

import transaction

from lp.services.config import config
from lp.services.database.interfaces import ISlaveStore
from lp.services.database.policy import SlaveDatabasePolicy
from lp.services.database.sqlbase import block_implicit_flushes
from lp.services.librarian import client as client_module
from lp.services.librarian.client import (
    LibrarianClient,
    LibrarianServerError,
    RestrictedLibrarianClient,
    )
from lp.services.librarian.interfaces.client import UploadFailed
from lp.services.librarian.model import LibraryFileAlias
from lp.testing.layers import (
    DatabaseLayer,
    FunctionalLayer,
    LaunchpadFunctionalLayer,
    )
from lp.testing.views import create_webservice_error_view


class InstrumentedLibrarianClient(LibrarianClient):

    def __init__(self, *args, **kwargs):
        super(InstrumentedLibrarianClient, self).__init__(*args, **kwargs)
        self.check_error_calls = 0

    sentDatabaseName = False

    def _sendHeader(self, name, value):
        if name == 'Database-Name':
            self.sentDatabaseName = True
        return LibrarianClient._sendHeader(self, name, value)

    called_getURLForDownload = False

    def _getURLForDownload(self, aliasID):
        self.called_getURLForDownload = True
        return LibrarianClient._getURLForDownload(self, aliasID)

    def _checkError(self):
        self.check_error_calls += 1
        super(InstrumentedLibrarianClient, self)._checkError()


def make_mock_file(error, max_raise):
    """Return a surrogate for client._File.

    The surrogate function raises error when called for the first
    max_raise times.
    """

    file_status = {
        'error': error,
        'max_raise': max_raise,
        'num_calls': 0,
        }

    def mock_file(url_file, url):
        if file_status['num_calls'] < file_status['max_raise']:
            file_status['num_calls'] += 1
            raise file_status['error']
        return 'This is a fake file object'

    return mock_file


class LibrarianClientTestCase(unittest.TestCase):
    layer = LaunchpadFunctionalLayer

    def test_addFileSendsDatabaseName(self):
        # addFile should send the Database-Name header.
        client = InstrumentedLibrarianClient()
        client.addFile(
            'sample.txt', 6, StringIO('sample'), 'text/plain')
        self.failUnless(client.sentDatabaseName,
            "Database-Name header not sent by addFile")

    def test_remoteAddFileDoesntSendDatabaseName(self):
        # remoteAddFile should send the Database-Name header as well.
        client = InstrumentedLibrarianClient()
        # Because the remoteAddFile call commits to the database in a
        # different process, we need to explicitly tell the DatabaseLayer to
        # fully tear down and set up the database.
        DatabaseLayer.force_dirty_database()
        client.remoteAddFile('sample.txt', 6, StringIO('sample'),
                                   'text/plain')
        self.failUnless(client.sentDatabaseName,
            "Database-Name header not sent by remoteAddFile")

    def test_clientWrongDatabase(self):
        # If the client is using the wrong database, the server should refuse
        # the upload, causing LibrarianClient to raise UploadFailed.
        client = LibrarianClient()
        # Force the client to mis-report its database
        client._getDatabaseName = lambda cur: 'wrong_database'
        try:
            client.addFile('sample.txt', 6, StringIO('sample'), 'text/plain')
        except UploadFailed as e:
            msg = e.args[0]
            self.failUnless(
                msg.startswith('Server said: 400 Wrong database'),
                'Unexpected UploadFailed error: ' + msg)
        else:
            self.fail("UploadFailed not raised")

    def test_addFile_uses_master(self):
        # addFile is a write operation, so it should always use the
        # master store, even if the slave is the default. Close the
        # slave store and try to add a file, verifying that the master
        # is used.
        client = LibrarianClient()
        ISlaveStore(LibraryFileAlias).close()
        with SlaveDatabasePolicy():
            alias_id = client.addFile(
                'sample.txt', 6, StringIO('sample'), 'text/plain')
        transaction.commit()
        f = client.getFileByAlias(alias_id)
        self.assertEqual(f.read(), 'sample')

    def test_addFile_no_response_check_at_end_headers_for_empty_file(self):
        # When addFile() sends the request header, it checks if the
        # server responded with an error response after sending each
        # header line. It does _not_ do this check when it sends the
        # empty line following the headers.
        client = InstrumentedLibrarianClient()
        client.addFile(
            'sample.txt', 0, StringIO(''), 'text/plain',
            allow_zero_length=True)
        # addFile() calls _sendHeader() three times and _sendLine()
        # twice, but it does not check if the server responded
        # in the second call.
        self.assertEqual(4, client.check_error_calls)

    def test_addFile_response_check_at_end_headers_for_non_empty_file(self):
        # When addFile() sends the request header, it checks if the
        # server responded with an error response after sending each
        # header line. It does _not_ do this check when it sends the
        # empty line following the headers.
        client = InstrumentedLibrarianClient()
        client.addFile('sample.txt', 4, StringIO('1234'), 'text/plain')
        # addFile() calls _sendHeader() three times and _sendLine()
        # twice.
        self.assertEqual(5, client.check_error_calls)

    def test_addFile_hashes(self):
        # addFile() sets the MD5, SHA-1 and SHA-256 hashes on the
        # LibraryFileContent record.
        data = 'i am some data'
        md5 = hashlib.md5(data).hexdigest()
        sha1 = hashlib.sha1(data).hexdigest()
        sha256 = hashlib.sha256(data).hexdigest()

        client = LibrarianClient()
        lfa = LibraryFileAlias.get(
            client.addFile('file', len(data), StringIO(data), 'text/plain'))

        self.assertEqual(md5, lfa.content.md5)
        self.assertEqual(sha1, lfa.content.sha1)
        self.assertEqual(sha256, lfa.content.sha256)

    def test__getURLForDownload(self):
        # This protected method is used by getFileByAlias. It is supposed to
        # use the internal host and port rather than the external, proxied
        # host and port. This is to provide relief for our own issues with the
        # problems reported in bug 317482.
        #
        # (Set up:)
        client = LibrarianClient()
        alias_id = client.addFile(
            'sample.txt', 6, StringIO('sample'), 'text/plain')
        config.push(
            'test config',
            textwrap.dedent('''\
                [librarian]
                download_host: example.org
                download_port: 1234
                '''))
        try:
            # (Test:)
            # The LibrarianClient should use the download_host and
            # download_port.
            expected_host = 'http://example.org:1234/'
            download_url = client._getURLForDownload(alias_id)
            self.failUnless(download_url.startswith(expected_host),
                            'expected %s to start with %s' % (download_url,
                                                              expected_host))
            # If the alias has been deleted, _getURLForDownload returns None.
            lfa = LibraryFileAlias.get(alias_id)
            lfa.content = None
            call = block_implicit_flushes(  # Prevent a ProgrammingError
                LibrarianClient._getURLForDownload)
            self.assertEqual(call(client, alias_id), None)
        finally:
            # (Tear down:)
            config.pop('test config')

    def test_restricted_getURLForDownload(self):
        # The RestrictedLibrarianClient should use the
        # restricted_download_host and restricted_download_port, but is
        # otherwise identical to the behavior of the LibrarianClient discussed
        # and demonstrated above.
        #
        # (Set up:)
        client = RestrictedLibrarianClient()
        alias_id = client.addFile(
            'sample.txt', 6, StringIO('sample'), 'text/plain')
        config.push(
            'test config',
            textwrap.dedent('''\
                [librarian]
                restricted_download_host: example.com
                restricted_download_port: 5678
                '''))
        try:
            # (Test:)
            # The LibrarianClient should use the download_host and
            # download_port.
            expected_host = 'http://example.com:5678/'
            download_url = client._getURLForDownload(alias_id)
            self.failUnless(download_url.startswith(expected_host),
                            'expected %s to start with %s' % (download_url,
                                                              expected_host))
            # If the alias has been deleted, _getURLForDownload returns None.
            lfa = LibraryFileAlias.get(alias_id)
            lfa.content = None
            call = block_implicit_flushes(  # Prevent a ProgrammingError
                RestrictedLibrarianClient._getURLForDownload)
            self.assertEqual(call(client, alias_id), None)
        finally:
            # (Tear down:)
            config.pop('test config')

    def test_getFileByAlias(self):
        # This method should use _getURLForDownload to download the file.
        # We use the InstrumentedLibrarianClient to show that it is consulted.
        #
        # (Set up:)
        client = InstrumentedLibrarianClient()
        alias_id = client.addFile(
            'sample.txt', 6, StringIO('sample'), 'text/plain')
        transaction.commit()  # Make sure the file is in the "remote" database.
        self.failIf(client.called_getURLForDownload)
        # (Test:)
        f = client.getFileByAlias(alias_id)
        self.assertEqual(f.read(), 'sample')
        self.failUnless(client.called_getURLForDownload)

    def test_getFileByAliasLookupError(self):
        # The Librarian server can return a 404 HTTPError;
        # LibrarienClient.getFileByAlias() returns a LookupError in
        # this case.
        _File = client_module._File
        client_module._File = make_mock_file(
            HTTPError('http://fake.url/', 404, 'Forced error', None, None), 1)

        client = InstrumentedLibrarianClient()
        alias_id = client.addFile(
            'sample.txt', 6, StringIO('sample'), 'text/plain')
        transaction.commit()
        self.assertRaises(LookupError, client.getFileByAlias, alias_id)

        client_module._File = _File

    def test_getFileByAliasLibrarianLongServerError(self):
        # The Librarian server can return a 500 HTTPError.
        # LibrarienClient.getFileByAlias() returns a LibrarianServerError
        # if the server returns this error for a longer time than given
        # by the parameter timeout.
        _File = client_module._File

        client_module._File = make_mock_file(
            HTTPError('http://fake.url/', 500, 'Forced error', None, None), 2)
        client = InstrumentedLibrarianClient()
        alias_id = client.addFile(
            'sample.txt', 6, StringIO('sample'), 'text/plain')
        transaction.commit()
        self.assertRaises(
            LibrarianServerError, client.getFileByAlias, alias_id, 1)

        client_module._File = make_mock_file(
            URLError('Connection refused'), 2)
        client = InstrumentedLibrarianClient()
        alias_id = client.addFile(
            'sample.txt', 6, StringIO('sample'), 'text/plain')
        transaction.commit()
        self.assertRaises(
            LibrarianServerError, client.getFileByAlias, alias_id, 1)

        client_module._File = _File

    def test_getFileByAliasLibrarianShortServerError(self):
        # The Librarian server can return a 500 HTTPError;
        # LibrarienClient.getFileByAlias() returns a LibrarianServerError
        # in this case.
        _File = client_module._File

        client_module._File = make_mock_file(
            HTTPError('http://fake.url/', 500, 'Forced error', None, None), 1)
        client = InstrumentedLibrarianClient()
        alias_id = client.addFile(
            'sample.txt', 6, StringIO('sample'), 'text/plain')
        transaction.commit()
        self.assertEqual(
            client.getFileByAlias(alias_id), 'This is a fake file object', 3)

        client_module._File = make_mock_file(
            URLError('Connection refused'), 1)
        client = InstrumentedLibrarianClient()
        alias_id = client.addFile(
            'sample.txt', 6, StringIO('sample'), 'text/plain')
        transaction.commit()
        self.assertEqual(
            client.getFileByAlias(alias_id), 'This is a fake file object', 3)

        client_module._File = _File


class TestWebServiceErrors(unittest.TestCase):
    """ Test that errors are correctly mapped to HTTP status codes."""

    layer = FunctionalLayer

    def test_LibrarianServerError_timeout(self):
        error_view = create_webservice_error_view(LibrarianServerError())
        self.assertEqual(httplib.REQUEST_TIMEOUT, error_view.status)
