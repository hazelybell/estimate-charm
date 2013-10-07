# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for mime module."""

__metaclass__ = type

import mimetypes

from lp.services.mime import customizeMimetypes
from lp.testing import TestCase

# In our run-time environment this call is made via the initialization section
# of buildout.cfg but that initialization is not done for tests so it must be
# done manually here.
customizeMimetypes()


class TestBzip(TestCase):
    """Tests for iter_split."""

    def test_bzip2(self):
        # Test for '.tar.bzip2' support.
        filename = "foo.tar.bzip2"
        (application, encoding) = mimetypes.guess_type(filename)
        self.assertEqual('application/x-tar', application)
        self.assertEqual('bzip2', encoding)

    def test_tbz2(self):
        # Test for '.tb2' support.
        filename = "foo.tbz2"
        (application, encoding) = mimetypes.guess_type(filename)
        self.assertEqual('application/x-tar', application)
        self.assertEqual('bzip2', encoding)

    def test_bz2(self):
        # Test for '.tar.bz2' support.
        filename = "foo.tar.bz2"
        (application, encoding) = mimetypes.guess_type(filename)
        self.assertEqual('application/x-tar', application)
        self.assertEqual('bzip2', encoding)
