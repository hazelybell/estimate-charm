#!/usr/bin/python -S
#
# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Librarian garbage collector.

This script is run on the Librarian server to merge duplicate files,
remove expired files from the file system and clean up unreachable
rows in the database.
"""

__metaclass__ = type

import _pythonpath

import logging

from lp.services.config import config
from lp.services.database.interfaces import IStore
from lp.services.librarian.model import LibraryFileAlias
from lp.services.librarianserver import librariangc
from lp.services.scripts.base import LaunchpadCronScript


class LibrarianGC(LaunchpadCronScript):
    def add_my_options(self):
        self.parser.add_option(
                '', "--skip-duplicates", action="store_true", default=False,
                dest="skip_duplicates",
                help="Skip duplicate LibraryFileContent merging"
                )
        self.parser.add_option(
                '', "--skip-aliases", action="store_true", default=False,
                dest="skip_aliases",
                help="Skip unreferenced LibraryFileAlias removal"
                )
        self.parser.add_option(
                '', "--skip-content", action="store_true", default=False,
                dest="skip_content",
                help="Skip unreferenced LibraryFileContent removal"
                )
        self.parser.add_option(
                '', "--skip-blobs", action="store_true", default=False,
                dest="skip_blobs",
                help="Skip removing expired TemporaryBlobStorage rows"
                )
        self.parser.add_option(
                '', "--skip-files", action="store_true", default=False,
                dest="skip_files",
                help="Skip removing files on disk with no database references"
                     " or flagged for deletion."
                )
        self.parser.add_option(
                '', "--skip-expiry", action="store_true", default=False,
                dest="skip_expiry",
                help="Skip expiring aliases with an expiry date in the past."
                )

    def main(self):
        librariangc.log = self.logger

        if self.options.loglevel <= logging.DEBUG:
            librariangc.debug = True

        # XXX wgrant 2011-09-18 bug=853066: Using Storm's raw connection
        # here is wrong. We should either create our own or use
        # Store.execute or cursor() and the transaction module.
        conn = IStore(LibraryFileAlias)._connection._raw_connection

        # Refuse to run if we have significant clock skew between the
        # librarian and the database.
        librariangc.confirm_no_clock_skew(conn)

        # Note that each of these next steps will issue commit commands
        # as appropriate to make this script transaction friendly
        if not self.options.skip_expiry:
            librariangc.expire_aliases(conn)
        if not self.options.skip_content:
            # First sweep.
            librariangc.delete_unreferenced_content(conn)
        if not self.options.skip_blobs:
            librariangc.delete_expired_blobs(conn)
        if not self.options.skip_duplicates:
            librariangc.merge_duplicates(conn)
        if not self.options.skip_aliases:
            librariangc.delete_unreferenced_aliases(conn)
        if not self.options.skip_content:
            # Second sweep.
            librariangc.delete_unreferenced_content(conn)
        if not self.options.skip_files:
            librariangc.delete_unwanted_files(conn)


if __name__ == '__main__':
    script = LibrarianGC('librarian-gc',
                         dbuser=config.librarian_gc.dbuser)
    script.lock_and_run(isolation='autocommit')
