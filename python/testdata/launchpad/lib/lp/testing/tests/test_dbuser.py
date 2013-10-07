# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test for dbuser helper."""

__metaclass__ = type

from lp.registry.model.person import Person
from lp.services.config import config
from lp.services.database.interfaces import IStore
# or TestCaseWithFactory
from lp.testing import TestCase
from lp.testing.dbuser import (
    dbuser,
    lp_dbuser,
    switch_dbuser,
    )
from lp.testing.layers import LaunchpadZopelessLayer


class TestDbUser(TestCase):

    layer = LaunchpadZopelessLayer

    def get_current_dbuser(self):
        store = IStore(Person)
        query = store.execute('SELECT current_user;')
        result = query.get_one()[0]
        query.close()
        return result

    def test_dbuser(self):
        switch_dbuser(config.uploader.dbuser)
        self.assertEqual(config.uploader.dbuser, self.get_current_dbuser())
        with dbuser(config.archivepublisher.dbuser):
            self.assertEqual(config.archivepublisher.dbuser,
                             self.get_current_dbuser())
        self.assertEqual(config.uploader.dbuser, self.get_current_dbuser())

    def test_lp_dpuser(self):
        switch_dbuser(config.uploader.dbuser)
        self.assertEqual(config.uploader.dbuser, self.get_current_dbuser())
        with lp_dbuser():
            self.assertEqual('launchpad', self.get_current_dbuser())
        self.assertEqual(config.uploader.dbuser, self.get_current_dbuser())
