# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Launchpad specific tests of Storm behavior."""

__metaclass__ = type

import storm

from lp.testing import TestCase


class TestStorm(TestCase):
    def test_has_cextensions(self):
        """Ensure Storm C extensions are being used."""
        self.assert_(
            storm.has_cextensions,
            'Storm not running with C extensions')
