# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import unittest

from lp.services.librarian.utils import guess_librarian_encoding


class LibrarianUtils(unittest.TestCase):
    """Librarian utilities functions."""

    def test_guess_librarian_encoding(self):
        """Diffs and buillogs are served differently from the other files.

        Package Diffs ('.diff.gz') and buildlogs ('.txt.gz') should be
        served using mimetype 'text/plain' and encoding 'gzip'.
        """
        encoding, mimetype = guess_librarian_encoding(
            'foo.html', 'text/html')
        self.assertEqual(encoding, None)
        self.assertEqual(mimetype, 'text/html')

        encoding, mimetype = guess_librarian_encoding(
            'foo.dsc', 'application/debian-control')
        self.assertEqual(encoding, None)
        self.assertEqual(mimetype, 'application/debian-control')

        encoding, mimetype = guess_librarian_encoding(
            'foo.tar.gz', 'application/octet-stream')
        self.assertEqual(encoding, None)
        self.assertEqual(mimetype, 'application/octet-stream')

        encoding, mimetype = guess_librarian_encoding(
            'foo.txt.gz', 'will_be_overridden')
        self.assertEqual(encoding, 'gzip')
        self.assertEqual(mimetype, 'text/plain')

        encoding, mimetype = guess_librarian_encoding(
            'foo.diff.gz', 'will_be_overridden')
        self.assertEqual(encoding, 'gzip')
        self.assertEqual(mimetype, 'text/plain')
