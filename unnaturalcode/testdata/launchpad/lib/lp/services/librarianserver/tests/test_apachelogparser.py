# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from datetime import datetime
import os
from StringIO import StringIO
import subprocess

from zope.component import getUtility

from lp.services.apachelogparser.base import (
    get_method_and_path,
    parse_file,
    )
from lp.services.librarian.interfaces import ILibraryFileAliasSet
from lp.services.librarianserver.apachelogparser import get_library_file_id
from lp.services.log.logger import BufferLogger
from lp.testing import (
    ANONYMOUS,
    login,
    TestCase,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    ZopelessLayer,
    )


here = os.path.dirname(__file__)


class TestRequestParsing(TestCase):
    """Test parsing the request part of an apache log line."""

    def assertMethodAndFileIDAreCorrect(self, request):
        method, path = get_method_and_path(request)
        file_id = get_library_file_id(path)
        self.assertEqual(method, 'GET')
        self.assertEqual(file_id, '8196569')

    def test_return_value(self):
        request = 'GET /8196569/mediumubuntulogo.png HTTP/1.1'
        self.assertMethodAndFileIDAreCorrect(request)

    def test_return_value_for_http_path(self):
        request = ('GET http://launchpadlibrarian.net/8196569/'
                   'mediumubuntulogo.png HTTP/1.1')
        self.assertMethodAndFileIDAreCorrect(request)

    def test_extra_slashes_are_ignored(self):
        request = 'GET http://launchpadlibrarian.net//8196569//foo HTTP/1.1'
        self.assertMethodAndFileIDAreCorrect(request)

        request = 'GET //8196569//foo HTTP/1.1'
        self.assertMethodAndFileIDAreCorrect(request)

    def test_multiple_consecutive_white_spaces(self):
        # Some request strings might have multiple consecutive white spaces,
        # but they're parsed just like if they didn't have the extra spaces.
        request = 'GET /8196569/mediumubuntulogo.png  HTTP/1.1'
        self.assertMethodAndFileIDAreCorrect(request)

    def test_return_value_for_https_path(self):
        request = ('GET https://launchpadlibrarian.net/8196569/'
                   'mediumubuntulogo.png HTTP/1.1')
        self.assertMethodAndFileIDAreCorrect(request)

    def test_return_value_for_request_missing_http_version(self):
        # HTTP 1.0 requests might omit the HTTP version so we must cope with
        # them.
        request = 'GET https://launchpadlibrarian.net/8196569/foo.png'
        self.assertMethodAndFileIDAreCorrect(request)

    def test_requests_for_paths_that_are_not_of_an_lfa_return_none(self):
        request = 'GET https://launchpadlibrarian.net/ HTTP/1.1'
        self.assertEqual(
            get_library_file_id(get_method_and_path(request)[1]), None)

        request = 'GET /robots.txt HTTP/1.1'
        self.assertEqual(
            get_library_file_id(get_method_and_path(request)[1]), None)

        request = 'GET /@@person HTTP/1.1'
        self.assertEqual(
            get_library_file_id(get_method_and_path(request)[1]), None)


class TestLibrarianLogFileParsing(TestCase):
    """Test the parsing of librarian log files."""

    layer = ZopelessLayer

    def setUp(self):
        TestCase.setUp(self)
        self.logger = BufferLogger()

    def test_request_to_lfa_is_parsed(self):
        fd = StringIO(
            '69.233.136.42 - - [13/Jun/2008:14:55:22 +0100] "GET '
            '/15018215/ul_logo_64x64.png HTTP/1.1" 200 2261 '
            '"https://launchpad.net/~ubuntulite/+archive" "Mozilla"')
        downloads, parsed_bytes, ignored = parse_file(
            fd, start_position=0, logger=self.logger,
            get_download_key=get_library_file_id)
        self.assertEqual(
            self.logger.getLogBuffer().strip(),
            'INFO Parsed 1 lines resulting in 1 download stats.')

        self.assertEqual(downloads,
            {'15018215': {datetime(2008, 6, 13): {'US': 1}}})

        self.assertEqual(parsed_bytes, fd.tell())

    def test_request_to_non_lfa_is_ignored(self):
        # A request to a path which doesn't map to a LibraryFileAlias (e.g.
        # '/') is ignored.
        fd = StringIO(
            '69.233.136.42 - - [13/Jun/2008:14:55:22 +0100] "GET / HTTP/1.1" '
            '200 2261 "https://launchpad.net/~ubuntulite/+archive" "Mozilla"')
        downloads, parsed_bytes, ignored = parse_file(
            fd, start_position=0, logger=self.logger,
            get_download_key=get_library_file_id)
        self.assertEqual(
            self.logger.getLogBuffer().strip(),
            'INFO Parsed 1 lines resulting in 0 download stats.')
        self.assertEqual(downloads, {})
        self.assertEqual(parsed_bytes, fd.tell())


class TestScriptRunning(TestCase):
    """Run parse-librarian-apache-access-logs.py and test its outcome."""

    layer = DatabaseFunctionalLayer

    def test_script_run(self):
        # Before we run the script, the LibraryFileAliases with id 1, 2 and 3
        # will have download counts set to 0.  After the script's run, each of
        # them will have their download counts set to 1, matching the sample
        # log files we use for this test:
        # scripts/tests/apache-log-files-for-sampledata.
        login(ANONYMOUS)
        libraryfile_set = getUtility(ILibraryFileAliasSet)
        self.assertEqual(libraryfile_set[1].hits, 0)
        self.assertEqual(libraryfile_set[2].hits, 0)
        self.assertEqual(libraryfile_set[3].hits, 0)

        process = subprocess.Popen(
            'cronscripts/parse-librarian-apache-access-logs.py', shell=True,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        (out, err) = process.communicate()
        self.assertEqual(
            process.returncode, 0, "stdout:%s, stderr:%s" % (out, err))

        # Must commit because the changes were done in another transaction.
        import transaction
        transaction.commit()
        self.assertEqual(libraryfile_set[1].hits, 1)
        self.assertEqual(libraryfile_set[2].hits, 1)
        self.assertEqual(libraryfile_set[3].hits, 1)
