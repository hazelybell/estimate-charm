# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from lp.services.config import DatabaseConfig
from lp.testing import TestCase
from lp.testing.layers import DatabaseLayer


class TestDatabaseConfig(TestCase):

    layer = DatabaseLayer

    def test_override(self):
        # dbuser and isolation_level can be overridden at runtime.
        dbc = DatabaseConfig()
        self.assertEqual('launchpad_main', dbc.dbuser)
        self.assertEqual('repeatable_read', dbc.isolation_level)

        # dbuser and isolation_level overrides both work.
        dbc.override(dbuser='not_launchpad', isolation_level='autocommit')
        self.assertEqual('not_launchpad', dbc.dbuser)
        self.assertEqual('autocommit', dbc.isolation_level)

        # Overriding dbuser again preserves the isolation_level override.
        dbc.override(dbuser='also_not_launchpad')
        self.assertEqual('also_not_launchpad', dbc.dbuser)
        self.assertEqual('autocommit', dbc.isolation_level)

        # Overriding with None removes the override.
        dbc.override(dbuser=None, isolation_level=None)
        self.assertEqual('launchpad_main', dbc.dbuser)
        self.assertEqual('repeatable_read', dbc.isolation_level)

    def test_reset(self):
        # reset() removes any overrides.
        dbc = DatabaseConfig()
        self.assertEqual('launchpad_main', dbc.dbuser)
        dbc.override(dbuser='not_launchpad')
        self.assertEqual('not_launchpad', dbc.dbuser)
        dbc.reset()
        self.assertEqual('launchpad_main', dbc.dbuser)
