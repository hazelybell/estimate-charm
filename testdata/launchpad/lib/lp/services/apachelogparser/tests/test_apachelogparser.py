# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from datetime import datetime
import gzip
from operator import itemgetter
import os
from StringIO import StringIO
import tempfile

from lp.services.apachelogparser.base import (
    create_or_update_parsedlog_entry,
    get_day,
    get_fd_and_file_size,
    get_files_to_parse,
    get_host_date_status_and_request,
    get_method_and_path,
    parse_file,
    )
from lp.services.apachelogparser.model.parsedapachelog import ParsedApacheLog
from lp.services.config import config
from lp.services.database.interfaces import IStore
from lp.services.librarianserver.apachelogparser import DBUSER
from lp.services.log.logger import BufferLogger
from lp.testing import TestCase
from lp.testing.dbuser import switch_dbuser
from lp.testing.layers import (
    LaunchpadZopelessLayer,
    ZopelessLayer,
    )


here = os.path.dirname(__file__)


class TestLineParsing(TestCase):
    """Test parsing of lines of an apache log file."""

    def test_return_value(self):
        fd = open(
            os.path.join(here, 'apache-log-files', 'librarian-oneline.log'))
        host, date, status, request = get_host_date_status_and_request(
            fd.readline())
        self.assertEqual(host, '201.158.154.121')
        self.assertEqual(date, '[13/Jun/2008:18:38:57 +0100]')
        self.assertEqual(status, '200')
        self.assertEqual(
            request, 'GET /15166065/gnome-do-0.5.0.1.tar.gz HTTP/1.1')

    def test_parsing_line_with_quotes_inside_user_agent_and_referrer(self):
        # Some lines have quotes as part of the referrer and/or user agent,
        # and they are parsed just fine too.
        line = (r'84.113.215.193 - - [25/Jan/2009:15:48:07 +0000] "GET '
                r'/10133748/cramfsswap_1.4.1.tar.gz HTTP/1.0" 200 12341 '
                r'"http://foo.bar/?baz=\"bang\"" '
                r'"\"Nokia2630/2.0 (05.20) Profile/MIDP-2.1 '
                r'Configuration/CLDC-1.1\""')
        host, date, status, request = get_host_date_status_and_request(line)
        self.assertEqual(host, '84.113.215.193')
        self.assertEqual(date, '[25/Jan/2009:15:48:07 +0000]')
        self.assertEqual(status, '200')
        self.assertEqual(
            request, 'GET /10133748/cramfsswap_1.4.1.tar.gz HTTP/1.0')

    def test_parsing_line_with_spaces_in_username(self):
        # Some lines have spaces in the username, left unquoted by
        # Apache. They can still be parsed OK, since no other fields
        # have similar issues.
        line = (r'1.1.1.1 - Some User [25/Jan/2009:15:48:07 +0000] "GET '
                r'/10133748/cramfsswap_1.4.1.tar.gz HTTP/1.0" 200 12341 '
                r'"http://foo.bar/?baz=\"bang\"" '
                r'"\"Nokia2630/2.0 (05.20) Profile/MIDP-2.1 '
                r'Configuration/CLDC-1.1\""')
        host, date, status, request = get_host_date_status_and_request(line)
        self.assertEqual(host, '1.1.1.1')
        self.assertEqual(date, '[25/Jan/2009:15:48:07 +0000]')
        self.assertEqual(status, '200')
        self.assertEqual(
            request, 'GET /10133748/cramfsswap_1.4.1.tar.gz HTTP/1.0')

    def test_day_extraction(self):
        date = '[13/Jun/2008:18:38:57 +0100]'
        self.assertEqual(get_day(date), datetime(2008, 6, 13))

    def test_parsing_path_with_missing_protocol(self):
        request = (r'GET /56222647/deluge-gtk_1.3.0-0ubuntu1_all.deb?'
                   r'N\x1f\x9b')
        method, path = get_method_and_path(request)
        self.assertEqual(method, 'GET')
        self.assertEqual(
            path,
            r'/56222647/deluge-gtk_1.3.0-0ubuntu1_all.deb?N\x1f\x9b')

    def test_parsing_path_with_space(self):
        # See bug 676489.
        request = (r'GET /56222647/deluge-gtk_1.3.0-0ubuntu1_all.deb?'
                   r'N\x1f\x9b Z%7B... HTTP/1.0')
        method, path = get_method_and_path(request)
        self.assertEqual(method, 'GET')
        self.assertEqual(
            path,
            r'/56222647/deluge-gtk_1.3.0-0ubuntu1_all.deb?N\x1f\x9b Z%7B...')

    def test_parsing_path_with_space_and_missing_protocol(self):
        # This is a variation of bug 676489.
        request = (r'GET /56222647/deluge-gtk_1.3.0-0ubuntu1_all.deb?'
                   r'N\x1f\x9b Z%7B...')
        method, path = get_method_and_path(request)
        self.assertEqual(method, 'GET')
        self.assertEqual(
            path,
            r'/56222647/deluge-gtk_1.3.0-0ubuntu1_all.deb?N\x1f\x9b Z%7B...')

    def test_parsing_invalid_url(self):
        # An invalid URL should just be treated as a path, not cause an
        # exception.
        request = r'GET http://blah/1234/fewfwfw GET http://blah HTTP/1.0'
        method, path = get_method_and_path(request)
        self.assertEqual(method, 'GET')
        self.assertEqual(
            path,
            r'http://blah/1234/fewfwfw GET http://blah')


class Test_get_fd_and_file_size(TestCase):

    def _ensureFileSizeIsCorrect(self, file_path):
        """Ensure the file size returned is correct.

        Also ensure that the file descriptors returned where seek()ed to the
        very beginning.
        """
        fd, file_size = get_fd_and_file_size(file_path)
        self.assertEqual(fd.tell(), 0)
        self.assertEqual(len(fd.read()), file_size)

    def test_regular_file(self):
        file_path = os.path.join(
            here, 'apache-log-files', 'librarian-oneline.log')
        self._ensureFileSizeIsCorrect(file_path)

    def test_gzip_file(self):
        file_path = os.path.join(
            here, 'apache-log-files',
            'launchpadlibrarian.net.access-log.1.gz')
        self._ensureFileSizeIsCorrect(file_path)


def get_path_download_key(path):
    return path


class TestLogFileParsing(TestCase):
    """Test the parsing of log files."""

    layer = ZopelessLayer
    sample_line = (
        '69.233.136.42 - - [13/Jun/2008:14:55:22 +0100] "%(method)s '
        '/15018215/ul_logo_64x64.png HTTP/1.1" %(status)s 2261 '
        '"https://launchpad.net/~ubuntulite/+archive" "Mozilla/5.0 (X11; '
        'U; Linux i686; en-US; rv:1.9b5) Gecko/2008041514 Firefox/3.0b5"')

    def setUp(self):
        TestCase.setUp(self)
        self.logger = BufferLogger()

    def _getLastLineStart(self, fd):
        """Return the position (in bytes) where the last line of the given
        file starts.
        """
        fd.seek(0)
        lines = fd.readlines()
        return fd.tell() - len(lines[-1])

    def test_parsing(self):
        # The parse_file() function returns a tuple containing a dict (mapping
        # days and library file IDs to number of downloads), the total number
        # of bytes that have been parsed from this file, and the running total
        # of lines parsed (for testing against the maximum).  In our sample
        # log, the file with ID 8196569 has been downloaded twice (once from
        # Argentina and once from Japan) and the files with ID 12060796 and
        # 9096290 have been downloaded once.  The file with ID 15018215 has
        # also been downloaded once (last line of the sample log), but
        # parse_file() always skips the last line as it may be truncated, so
        # it doesn't show up in the dict returned.
        fd = open(os.path.join(
            here, 'apache-log-files', 'launchpadlibrarian.net.access-log'))
        downloads, parsed_bytes, parsed_lines = parse_file(
            fd, start_position=0, logger=self.logger,
            get_download_key=get_path_download_key)
        self.assertEqual(
            self.logger.getLogBuffer().strip(),
            'INFO Parsed 5 lines resulting in 3 download stats.')
        date = datetime(2008, 6, 13)
        self.assertContentEqual(
            downloads.items(),
            [('/12060796/me-tv-icon-64x64.png', {date: {'AU': 1}}),
             ('/8196569/mediumubuntulogo.png', {date: {'AR': 1, 'JP': 1}}),
             ('/9096290/me-tv-icon-14x14.png', {date: {'AU': 1}})])

        # The last line is skipped, so we'll record that the file has been
        # parsed until the beginning of the last line.
        self.assertNotEqual(parsed_bytes, fd.tell())
        self.assertEqual(parsed_bytes, self._getLastLineStart(fd))

    def test_parsing_last_line(self):
        # When there's only the last line of a given file for us to parse, we
        # assume the file has been rotated and it's safe to parse its last
        # line without worrying about whether or not it's been truncated.
        fd = open(os.path.join(
            here, 'apache-log-files', 'launchpadlibrarian.net.access-log'))
        downloads, parsed_bytes, parsed_lines = parse_file(
            fd, start_position=self._getLastLineStart(fd), logger=self.logger,
            get_download_key=get_path_download_key)
        self.assertEqual(
            self.logger.getLogBuffer().strip(),
            'INFO Parsed 1 lines resulting in 1 download stats.')
        self.assertEqual(parsed_bytes, fd.tell())

        self.assertContentEqual(
            downloads.items(),
            [('/15018215/ul_logo_64x64.png',
              {datetime(2008, 6, 13): {'US': 1}})])

    def test_unexpected_error_while_parsing(self):
        # When there's an unexpected error, we log it and return as if we had
        # parsed up to the line before the one where the failure occurred.
        # Here we force an unexpected error on the first line.
        fd = StringIO('Not a log')
        downloads, parsed_bytes, parsed_lines = parse_file(
            fd, start_position=0, logger=self.logger,
            get_download_key=get_path_download_key)
        self.assertIn('Error', self.logger.getLogBuffer())
        self.assertEqual(downloads, {})
        self.assertEqual(parsed_bytes, 0)

    def _assertResponseWithGivenStatusIsIgnored(self, status):
        """Assert that responses with the given status are ignored."""
        fd = StringIO(
            self.sample_line % dict(status=status, method='GET'))
        downloads, parsed_bytes, parsed_lines = parse_file(
            fd, start_position=0, logger=self.logger,
            get_download_key=get_path_download_key)
        self.assertEqual(
            self.logger.getLogBuffer().strip(),
            'INFO Parsed 1 lines resulting in 0 download stats.')
        self.assertEqual(downloads, {})
        self.assertEqual(parsed_bytes, fd.tell())

    def test_responses_with_404_status_are_ignored(self):
        self._assertResponseWithGivenStatusIsIgnored('404')

    def test_responses_with_206_status_are_ignored(self):
        self._assertResponseWithGivenStatusIsIgnored('206')

    def test_responses_with_304_status_are_ignored(self):
        self._assertResponseWithGivenStatusIsIgnored('304')

    def test_responses_with_503_status_are_ignored(self):
        self._assertResponseWithGivenStatusIsIgnored('503')

    def _assertRequestWithGivenMethodIsIgnored(self, method):
        """Assert that requests with the given method are ignored."""
        fd = StringIO(
            self.sample_line % dict(status='200', method=method))
        downloads, parsed_bytes, parsed_lines = parse_file(
            fd, start_position=0, logger=self.logger,
            get_download_key=get_path_download_key)
        self.assertEqual(
            self.logger.getLogBuffer().strip(),
            'INFO Parsed 1 lines resulting in 0 download stats.')
        self.assertEqual(downloads, {})
        self.assertEqual(parsed_bytes, fd.tell())

    def test_HEAD_request_is_ignored(self):
        self._assertRequestWithGivenMethodIsIgnored('HEAD')

    def test_POST_request_is_ignored(self):
        self._assertRequestWithGivenMethodIsIgnored('POST')

    def test_normal_request_is_not_ignored(self):
        fd = StringIO(
            self.sample_line % dict(status=200, method='GET'))
        downloads, parsed_bytes, parsed_lines = parse_file(
            fd, start_position=0, logger=self.logger,
            get_download_key=get_path_download_key)
        self.assertEqual(
            self.logger.getLogBuffer().strip(),
            'INFO Parsed 1 lines resulting in 1 download stats.')

        self.assertEqual(downloads,
            {'/15018215/ul_logo_64x64.png':
                {datetime(2008, 6, 13): {'US': 1}}})

        self.assertEqual(parsed_bytes, fd.tell())

    def test_max_parsed_lines(self):
        # The max_parsed_lines config option limits the number of parsed
        # lines.
        config.push(
            'log_parser config',
            '[launchpad]\nlogparser_max_parsed_lines: 2')
        self.addCleanup(config.pop, 'log_parser config')
        fd = open(os.path.join(
            here, 'apache-log-files', 'launchpadlibrarian.net.access-log'))
        self.addCleanup(fd.close)

        downloads, parsed_bytes, parsed_lines = parse_file(
            fd, start_position=0, logger=self.logger,
            get_download_key=get_path_download_key)

        # We have initially parsed only the first two lines of data,
        # corresponding to one download (the first line is a 404 and
        # so ignored).
        self.assertEqual(parsed_lines, 2)
        date = datetime(2008, 6, 13)
        self.assertContentEqual(
            downloads.items(),
            [('/9096290/me-tv-icon-14x14.png', {date: {'AU': 1}})])
        fd.seek(0)
        lines = fd.readlines()
        line_lengths = [len(line) for line in lines]
        self.assertEqual(parsed_bytes, sum(line_lengths[:2]))

        # And the subsequent parse will be for the 3rd and 4th lines,
        # corresponding to two downloads of the same file.
        downloads, parsed_bytes, parsed_lines = parse_file(
            fd, start_position=parsed_bytes, logger=self.logger,
            get_download_key=get_path_download_key)
        self.assertContentEqual(
            downloads.items(),
            [('/12060796/me-tv-icon-64x64.png', {date: {'AU': 1}}),
             ('/8196569/mediumubuntulogo.png', {date: {'AR': 1}})])
        self.assertEqual(parsed_bytes, sum(line_lengths[:4]))

    def test_max_parsed_lines_exceeded(self):
        # Show that if a non-zero parsed_lines is passed in, the number of
        # lines parsed will be less than it would otherwise have been.

        # The max_parsed_lines config option limits the number of parsed
        # lines.
        config.push(
            'log_parser config',
            '[launchpad]\nlogparser_max_parsed_lines: 2')
        self.addCleanup(config.pop, 'log_parser config')
        fd = open(os.path.join(
            here, 'apache-log-files', 'launchpadlibrarian.net.access-log'))
        self.addCleanup(fd.close)

        # We want to start parsing on line 2 so we will have a value in
        # "downloads" to make a positive assertion about.  (The first line is
        # a 404 so wouldn't generate any output.)
        start_position = len(fd.readline())

        # If we have already parsed some lines, then the number of lines
        # parsed will be passed in (parsed_lines argument) and parse_file will
        # take that number into account when determining if the maximum number
        # of lines to parse has been reached.
        parsed_lines = 1
        downloads, parsed_bytes, parsed_lines = parse_file(
            fd, start_position=start_position, logger=self.logger,
            get_download_key=get_path_download_key, parsed_lines=parsed_lines)

        # The total number of lines parsed during the run (1 line) plus the
        # number of lines parsed previously (1 line, as passed in via
        # parsed_lines) is returned.
        self.assertEqual(parsed_lines, 2)
        # Since we told parse_file that we had already parsed 1 line and the
        # limit is 2 lines, it only parsed a single line.
        date = datetime(2008, 6, 13)
        self.assertContentEqual(
            downloads.items(),
            [('/9096290/me-tv-icon-14x14.png', {date: {'AU': 1}})])


class TestParsedFilesDetection(TestCase):
    """Test the detection of already parsed logs."""

    layer = LaunchpadZopelessLayer
    # The directory in which the sample log files live.
    root = os.path.join(here, 'apache-log-files')
    file_path = os.path.join(root, 'launchpadlibrarian.net.access-log')

    def setUp(self):
        super(TestParsedFilesDetection, self).setUp()
        switch_dbuser(DBUSER)

    def test_not_parsed_file(self):
        # A file that has never been parsed will have to be parsed from the
        # start.
        files_to_parse = get_files_to_parse([self.file_path])
        fd, position = list(files_to_parse)[0]
        self.assertEqual(position, 0)

    def test_completely_parsed_file(self):
        # A file that has been completely parsed will be skipped.
        fd = open(self.file_path)
        first_line = fd.readline()
        fd.seek(0)
        ParsedApacheLog(first_line, len(fd.read()))

        files_to_parse = get_files_to_parse([self.file_path])
        self.failUnlessEqual(list(files_to_parse), [])

    def test_parsed_file_with_new_content(self):
        # A file that has been parsed already but in which new content was
        # added will be parsed again, starting from where parsing stopped last
        # time.
        first_line = open(self.file_path).readline()
        ParsedApacheLog(first_line, len(first_line))

        files_to_parse = list(get_files_to_parse([self.file_path]))
        self.assertEqual(len(files_to_parse), 1)
        fd, position = files_to_parse[0]
        # Since we parsed the first line above, we'll be told to start where
        # the first line ends.
        self.assertEqual(position, len(first_line))

    def test_different_files_with_same_name(self):
        # Thanks to log rotation, two runs of our script may see files with
        # the same name but completely different content.  If we see a file
        # with a name matching that of an already parsed file but with content
        # differing from the last file with that name parsed, we know we need
        # to parse the file from the start.
        ParsedApacheLog('First line', bytes_read=1000)

        # This file has the same name of the previous one (which has been
        # parsed already), but its first line is different, so we'll have to
        # parse it from the start.
        fd, new_path = tempfile.mkstemp()
        content2 = 'Different First Line\nSecond Line'
        fd = open(new_path, 'w')
        fd.write(content2)
        fd.close()
        files_to_parse = get_files_to_parse([new_path])
        positions = map(itemgetter(1), files_to_parse)
        self.failUnlessEqual(positions, [0])

    def test_fresh_gzipped_file(self):
        # get_files_to_parse() handles gzipped files just like uncompressed
        # ones.  The first time we see one, we'll parse from the beginning.
        gz_name = 'launchpadlibrarian.net.access-log.1.gz'
        gz_path = os.path.join(self.root, gz_name)
        first_line = gzip.open(gz_path).readline()
        files_to_parse = get_files_to_parse([gz_path])
        positions = map(itemgetter(1), files_to_parse)
        self.assertEqual(positions, [0])

    def test_resumed_gzipped_file(self):
        # In subsequent runs of the script we will resume from where we
        # stopped last time. (Here we pretend we parsed only the first line)
        gz_name = 'launchpadlibrarian.net.access-log.1.gz'
        gz_path = os.path.join(self.root, gz_name)
        first_line = gzip.open(gz_path).readline()
        ParsedApacheLog(first_line, len(first_line))
        files_to_parse = get_files_to_parse([gz_path])
        positions = map(itemgetter(1), files_to_parse)
        self.failUnlessEqual(positions, [len(first_line)])


class Test_create_or_update_parsedlog_entry(TestCase):
    """Test the create_or_update_parsedlog_entry function."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(Test_create_or_update_parsedlog_entry, self).setUp()
        switch_dbuser(DBUSER)

    def test_creation_of_new_entries(self):
        # When given a first_line that doesn't exist in the ParsedApacheLog
        # table, create_or_update_parsedlog_entry() will create a new entry
        # with the given number of bytes read.
        first_line = u'First line'
        create_or_update_parsedlog_entry(
            first_line, parsed_bytes=len(first_line))

        entry = IStore(ParsedApacheLog).find(
            ParsedApacheLog, first_line=first_line).one()
        self.assertIsNot(None, entry)
        self.assertEqual(entry.bytes_read, len(first_line))

    def test_update_of_existing_entries(self):
        # When given a first_line that already exists in the ParsedApacheLog
        # table, create_or_update_parsedlog_entry() will update that entry
        # with the given number of bytes read.
        first_line = u'First line'
        create_or_update_parsedlog_entry(first_line, parsed_bytes=2)
        store = IStore(ParsedApacheLog)
        entry = store.find(ParsedApacheLog, first_line=first_line).one()

        # Here we see that the new entry was created.
        self.assertIsNot(None, entry)
        self.assertEqual(entry.bytes_read, 2)

        create_or_update_parsedlog_entry(
            first_line, parsed_bytes=len(first_line))

        # And here we see that same entry was updated by the second call to
        # create_or_update_parsedlog_entry().
        entry2 = store.find(ParsedApacheLog, first_line=first_line).one()
        self.assertIs(entry, entry2)
        self.assertIsNot(None, entry2)
        self.assertEqual(entry2.bytes_read, len(first_line))
