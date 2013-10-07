#! /usr/bin/python -S
#
# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Perform simple librarian operations to verify the current configuration.
"""

from cStringIO import StringIO
import datetime
import sys
import urllib

import pytz
import transaction
from zope.component import getUtility

from lp.services.librarian.interfaces import ILibraryFileAliasSet


FILE_SIZE = 1024
FILE_DATA = 'x' * FILE_SIZE
FILE_LIFETIME = datetime.timedelta(hours=1)


def store_file(client):
    expiry_date = datetime.datetime.now(pytz.UTC) + FILE_LIFETIME
    file_id = client.addFile(
        'smoke-test-file', FILE_SIZE, StringIO(FILE_DATA), 'text/plain',
        expires=expiry_date)
    # To be able to retrieve the file, we must commit the current transaction.
    transaction.commit()
    alias = getUtility(ILibraryFileAliasSet)[file_id]
    return (file_id, alias.http_url)


def read_file(url):
    try:
        data = urllib.urlopen(url).read()
    except (MemoryError, KeyboardInterrupt, SystemExit):
        # Re-raise catastrophic errors.
        raise
    except:
        # An error is represented by returning None, which won't match when
        # comapred against FILE_DATA.
        return None

    return data


def upload_and_check(client, output):
    id, url = store_file(client)
    output.write('retrieving file from http_url (%s)\n' % (url,))
    if read_file(url) != FILE_DATA:
        return False
    output.write('retrieving file from client\n')
    if client.getFileByAlias(id).read() != FILE_DATA:
        return False
    return True


def do_smoketest(restricted_client, regular_client, output=None):
    if output is None:
        output = sys.stdout
    output.write('adding a private file to the librarian...\n')
    if not upload_and_check(restricted_client, output):
        output.write('ERROR: data fetched does not match data written\n')
        return 1

    output.write('adding a public file to the librarian...\n')
    if not upload_and_check(regular_client, output):
        output.write('ERROR: data fetched does not match data written\n')
        return 1

    return 0
