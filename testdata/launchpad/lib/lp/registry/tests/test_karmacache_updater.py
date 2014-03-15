# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type


import subprocess
import unittest

import transaction
from zope.component import getUtility

from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.product import IProductSet
from lp.registry.model.karma import KarmaCache
from lp.services.database.sqlbase import flush_database_caches
from lp.testing import (
    ANONYMOUS,
    login,
    logout,
    )
from lp.testing.layers import LaunchpadFunctionalLayer


class TestKarmaCacheUpdater(unittest.TestCase):
    layer = LaunchpadFunctionalLayer

    def setUp(self):
        login(ANONYMOUS)
        self.personset = getUtility(IPersonSet)

    def tearDown(self):
        logout()
        # As the test performs DB changes in a subprocess, make sure
        # the database is marked dirty.
        self.layer.force_dirty_database()

    def _getCacheEntriesByPerson(self, person):
        return KarmaCache.selectBy(person=person)

    def _runScript(self):
        process = subprocess.Popen(
            'cronscripts/foaf-update-karma-cache.py', shell=True,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        (out, err) = process.communicate()
        self.failUnless(process.returncode == 0, (out, err))

    # This is a quite long test, but it's better this way because the
    # karmacache updater script takes quite a while to run and changes/deletes
    # all KarmaCache entries. IOW, if we split this test it'll take a LOT
    # longer to run and we'll have to restore the database after each time
    # it's run.
    def test_karmacache_entries(self):
        # Sample Person has some KarmaCache entries, but it's a long time
        # since we last updated this cache, and now the karma he earned a long
        # ago is not worth anything, so the karmacache-updater script will
        # delete the cache entries for Sample Person.
        sample_person = self.personset.getByName('name12')
        cache_entries = self._getCacheEntriesByPerson(sample_person)
        self.failUnless(not cache_entries.is_empty())
        for cache in cache_entries:
            self.failIf(cache.karmavalue <= 0)

        # As we can see, Foo Bar already has some karmacache entries. We'll
        # now add some fresh Karma entries for him and later we'll check that
        # the cache-updater script simply updated the existing cache entries
        # instead of creating new ones.
        foobar = self.personset.getByName('name16')
        cache_entries = self._getCacheEntriesByPerson(foobar)
        foobar_original_entries_count = cache_entries.count()
        self.failUnless(foobar_original_entries_count > 0)
        for cache in cache_entries:
            self.failIf(cache.karmavalue <= 0)
        firefox = getUtility(IProductSet)['firefox']
        foobar.assignKarma('bugcreated', firefox)

        # In the case of No Priv, he has no KarmaCache entries, so if we add
        # some fresh Karma entries to him, our cache-updater script will have
        # to create new KarmaCache entries for him.
        nopriv = self.personset.getByName('no-priv')
        self.failUnless(self._getCacheEntriesByPerson(nopriv).count() == 0)
        nopriv.assignKarma('bugcreated', firefox)

        transaction.commit()

        self._runScript()

        # Need to flush our caches since things were updated behind our back.
        flush_database_caches()

        # Check that Sample Person has no KarmaCache entries at all
        sample_person = self.personset.getByName('name12')
        self.failUnless(
            self._getCacheEntriesByPerson(sample_person).count() == 0)

        # Check that Foo Bar had his KarmaCache entries updated.
        entries_count = self._getCacheEntriesByPerson(foobar).count()
        # The cache entries that would have their karmavalue updated to 0 are
        # instead deleted from the DB; that's why the new count can be smaller
        # than the original one.
        self.failUnless(entries_count <= foobar_original_entries_count)

        # And finally, ensure that No Priv got some new KarmaCache entries.
        self.failUnless(not self._getCacheEntriesByPerson(nopriv).is_empty())
