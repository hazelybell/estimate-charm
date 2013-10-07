# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from datetime import datetime
import gzip
import os

from contrib import apachelog
from lazr.uri import (
    InvalidURIError,
    URI,
    )
import pytz
from zope.component import getUtility

from lp.services.apachelogparser.model.parsedapachelog import ParsedApacheLog
from lp.services.config import config
from lp.services.database.interfaces import IStore
from lp.services.geoip.interfaces import IGeoIP


parser = apachelog.parser(apachelog.formats['extended'])


def get_files_to_parse(file_paths):
    """Return an iterator of file and position where reading should start.

    The lines read from that position onwards will be the ones that have not
    been parsed yet.

    :param file_paths: The paths to the files.
    """
    store = IStore(ParsedApacheLog)
    for file_path in file_paths:
        fd, file_size = get_fd_and_file_size(file_path)
        first_line = unicode(fd.readline())
        parsed_file = store.find(ParsedApacheLog, first_line=first_line).one()
        position = 0
        if parsed_file is not None:
            # This file has been parsed already; we'll now check if there's
            # anything in it that hasn't been parsed yet.
            if parsed_file.bytes_read >= file_size:
                # There's nothing new in it for us to parse, so just skip it.
                fd.close()
                continue
            else:
                # This one has stuff we haven't parsed yet, so we'll just
                # parse what's new.
                position = parsed_file.bytes_read

        yield fd, position


def get_fd_and_file_size(file_path):
    """Return a file descriptor and the file size for the given file path.

    The file descriptor will have the default mode ('r') and will be seeked to
    the beginning.

    The file size returned is that of the uncompressed file, in case the given
    file_path points to a gzipped file.
    """
    if file_path.endswith('.gz'):
        # The last 4 bytes of the file contains the uncompressed file's
        # size, modulo 2**32.  This code is somewhat stolen from the gzip
        # module in Python 2.6.
        fd = gzip.open(file_path)
        fd.fileobj.seek(-4, os.SEEK_END)
        isize = gzip.read32(fd.fileobj)   # may exceed 2GB
        file_size = isize & 0xffffffffL
        fd.fileobj.seek(0)
    else:
        fd = open(file_path)
        file_size = os.path.getsize(file_path)
    return fd, file_size


def parse_file(fd, start_position, logger, get_download_key, parsed_lines=0):
    """Parse the given file starting on the given position.

    parsed_lines accepts the number of lines that have been parsed during
    previous calls to this function so they can be taken into account against
    max_parsed_lines.  The total number of parsed lines is then returned so it
    can be passed back to future calls to this function.

    Return a dictionary mapping file_ids (from the librarian) to days to
    countries to number of downloads.
    """
    # Seek file to given position, read all lines.
    fd.seek(start_position)
    next_line = fd.readline()

    parsed_bytes = start_position

    geoip = getUtility(IGeoIP)
    downloads = {}

    # Check for an optional max_parsed_lines config option.
    max_parsed_lines = getattr(
        config.launchpad, 'logparser_max_parsed_lines', None)

    while next_line:
        if max_parsed_lines is not None and parsed_lines >= max_parsed_lines:
            break

        line = next_line

        # Always skip the last line as it may be truncated since we're
        # rsyncing live logs, unless there is only one line for us to
        # parse, in which case This probably means we're dealing with a
        # logfile that has been rotated already, so it should be safe to
        # parse its last line.
        try:
            next_line = fd.next()
        except StopIteration:
            if parsed_lines > 0:
                break

        try:
            parsed_lines += 1
            parsed_bytes += len(line)
            host, date, status, request = get_host_date_status_and_request(
                line)

            if status != '200':
                continue

            method, path = get_method_and_path(request)

            if method != 'GET':
                continue

            download_key = get_download_key(path)

            if download_key is None:
                # Not a file or request that we care about.
                continue

            # Get the dict containing this file's downloads.
            if download_key not in downloads:
                downloads[download_key] = {}
            file_downloads = downloads[download_key]

            # Get the dict containing these day's downloads for this file.
            day = get_day(date)
            if day not in file_downloads:
                file_downloads[day] = {}
            daily_downloads = file_downloads[day]

            country_code = None
            geoip_record = geoip.getRecordByAddress(host)
            if geoip_record is not None:
                country_code = geoip_record['country_code']
            if country_code not in daily_downloads:
                daily_downloads[country_code] = 0
            daily_downloads[country_code] += 1
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as e:
            # Update parsed_bytes to the end of the last line we parsed
            # successfully, log this as an error and break the loop so that
            # we return.
            parsed_bytes -= len(line)
            logger.error('Error (%s) while parsing "%s"' % (e, line))
            break


    if parsed_lines > 0:
        logger.info('Parsed %d lines resulting in %d download stats.' % (
            parsed_lines, len(downloads)))

    return downloads, parsed_bytes, parsed_lines


def create_or_update_parsedlog_entry(first_line, parsed_bytes):
    """Create or update the ParsedApacheLog with the given first_line."""
    first_line = unicode(first_line)
    parsed_file = IStore(ParsedApacheLog).find(
        ParsedApacheLog, first_line=first_line).one()
    if parsed_file is None:
        ParsedApacheLog(first_line, parsed_bytes)
    else:
        parsed_file.bytes_read = parsed_bytes
        parsed_file.date_last_parsed = datetime.now(pytz.UTC)


def get_day(date):
    """Extract the day from the given date and return it as a datetime."""
    date, offset = apachelog.parse_date(date)
    # After the call above, date will be in the 'YYYYMMDD' format, but we need
    # to break it into pieces that can be fed to datetime().
    year, month, day = date[0:4], date[4:6], date[6:8]
    return datetime(int(year), int(month), int(day))


def get_host_date_status_and_request(line):
    """Extract the host, date, status and request from the given line."""
    # The keys in the 'data' dictionary below are the Apache log format codes.
    data = parser.parse(line)
    return data['%h'], data['%t'], data['%>s'], data['%r']


def get_method_and_path(request):
    """Extract the method of the request and path of the requested file."""
    method, ignore, rest = request.partition(' ')
    # In the below, the common case is that `first` is the path and `last` is
    # the protocol.
    first, ignore, last = rest.rpartition(' ')
    if first == '':
        # HTTP 1.0 requests might omit the HTTP version so we cope with them.
        path = last
    elif not last.startswith('HTTP'):
        # We cope with HTTP 1.0 protocol without HTTP version *and* a
        # space in the path (see bug 676489 for example).
        path = rest
    else:
        # This is the common case.
        path = first
    if path.startswith('http://') or path.startswith('https://'):
        try:
            uri = URI(path)
            path = uri.path
        except InvalidURIError:
            # The URL is not valid, so we can't extract a path. Let it
            # pass through, where it will probably be skipped when no
            # download key can be determined.
            pass
    return method, path
