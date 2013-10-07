#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Simple tool to upload arbitrary files into Librarian."""

import _pythonpath

import logging
import os

from zope.component import getUtility

from lp.services.helpers import filenameToContentType
from lp.services.librarian.interfaces import ILibraryFileAliasSet
from lp.services.scripts.base import (
    LaunchpadScript,
    LaunchpadScriptFailure,
    )


class LibrarianUploader(LaunchpadScript):
    description = "Upload a file to librarian."
    usage = "usage: %prog <f|--file> <filename>"
    loglevel = logging.INFO

    def add_my_options(self):
        self.parser.set_defaults(format='simple')
        self.parser.add_option(
        "-f", "--file", dest="filepath", metavar="FILE",
        help="filename to upload")

    def main(self):
        """Upload file, commit the transaction and prints the file URL."""
        if self.options.filepath is None:
            raise LaunchpadScriptFailure('File not provided.')

        library_file = self.upload_file(self.options.filepath)

        self.txn.commit()
        self.logger.info(library_file.http_url)

    def upload_file(self, filepath):
        """Upload given file to Librarian.

        :param filepath: path to the file on disk that should be uploaded to
            Librarian.
        :raise: `LaunchpadScriptFailure` if the given filepath could not be
            opened.
        :return: the `LibraryFileAlias` record corresponding to the uploaded
            file.
        """
        try:
            file = open(filepath)
        except IOError:
            raise LaunchpadScriptFailure('Could not open: %s' % filepath)

        flen = os.stat(filepath).st_size
        filename = os.path.basename(filepath)
        ftype = filenameToContentType(filename)
        library_file = getUtility(ILibraryFileAliasSet).create(
            filename, flen, file, contentType=ftype)
        return library_file


if __name__ == '__main__':
    script = LibrarianUploader('librarian-uploader')
    script.run()
