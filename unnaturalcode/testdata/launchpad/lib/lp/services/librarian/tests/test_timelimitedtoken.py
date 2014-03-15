# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for TimeLimitedToken."""

__metaclass__ = type

import testtools

from lp.services.database.sqlbase import session_store
from lp.services.librarian.model import TimeLimitedToken
from lp.testing.layers import LaunchpadFunctionalLayer


class TestLibraryFileAlias(testtools.TestCase):

    layer = LaunchpadFunctionalLayer

    def test_allocate(self):
        store = session_store()
        store.find(TimeLimitedToken).remove()
        token1 = TimeLimitedToken.allocate('foo://')
        token2 = TimeLimitedToken.allocate('foo://')
        # We must get unique tokens
        self.assertNotEqual(token1, token2)
        # They must be bytestrings (as a surrogate for valid url fragment')
        self.assertIsInstance(token1, str)
        self.assertIsInstance(token2, str)
