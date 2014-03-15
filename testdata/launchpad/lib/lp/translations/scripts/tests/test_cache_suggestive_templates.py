# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test script that refreshes the suggestive-POTemplates cache."""

__metaclass__ = type

from zope.component import getUtility

from lp.app.enums import ServiceUsage
from lp.services.database.interfaces import IStore
from lp.testing import TestCaseWithFactory
from lp.testing.layers import ZopelessDatabaseLayer
from lp.translations.interfaces.potemplate import IPOTemplateSet
from lp.translations.model.pofile import POFile


class TestSuggestivePOTemplatesCache(TestCaseWithFactory):
    layer = ZopelessDatabaseLayer

    def setUp(self):
        super(TestSuggestivePOTemplatesCache, self).setUp()
        self.utility = getUtility(IPOTemplateSet)

    def _refreshCache(self):
        """Refresh the cache, but do not commit."""
        self.utility.wipeSuggestivePOTemplatesCache()
        self.utility.populateSuggestivePOTemplatesCache()

    def _readCache(self):
        """Read cache contents, in deterministic order."""
        result = IStore(POFile).execute(
            "SELECT * FROM SuggestivePOTemplate ORDER BY potemplate")
        return [id for id, in result.get_all()]

    def test_contents_stay_consistent(self):
        # Refreshing the cache will reproduce the same cache if there
        # have been no intervening template changes.
        self._refreshCache()
        contents = self._readCache()
        self._refreshCache()
        self.assertEqual(contents, self._readCache())

    def test_wipeSuggestivePOTemplatesCache(self):
        # The wipe method clears the cache.
        self._refreshCache()
        self.assertNotEqual([], self._readCache())

        self.utility.wipeSuggestivePOTemplatesCache()

        self.assertEqual([], self._readCache())

    def test_removeFromSuggestivePOTemplatesCache(self):
        # It is possible to remove a template from the cache.
        pot = self.factory.makePOTemplate()
        self._refreshCache()
        cache_with_template = self._readCache()

        was_in_cache = self.utility.removeFromSuggestivePOTemplatesCache(pot)
        cache_without_template = self._readCache()

        self.assertTrue(was_in_cache)
        self.assertNotEqual(cache_with_template, cache_without_template)
        self.assertContentEqual(
            cache_with_template, cache_without_template + [pot.id])

    def test_removeFromSuggestivePOTemplatesCache_not_in_cache(self):
        # Removing a not-cached template from the cache does nothing.
        self._refreshCache()
        cache_before = self._readCache()

        pot = self.factory.makePOTemplate()

        was_in_cache = self.utility.removeFromSuggestivePOTemplatesCache(pot)

        self.assertFalse(was_in_cache)
        self.assertEqual(cache_before, self._readCache())

    def test_populateSuggestivePOTemplatesCache(self):
        # The populate method fills an empty cache.
        self.utility.wipeSuggestivePOTemplatesCache()
        self.utility.populateSuggestivePOTemplatesCache()
        self.assertNotEqual([], self._readCache())

    def test_new_template_appears(self):
        # A new template appears in the cache on the next refresh.
        self._refreshCache()
        cache_before = self._readCache()

        pot = self.factory.makePOTemplate()
        self._refreshCache()

        self.assertContentEqual(cache_before + [pot.id], self._readCache())

    def test_product_translations_usage_affects_caching(self):
        # Templates from projects are included in the cache only where
        # the project uses Launchpad Translations.
        productseries = self.factory.makeProductSeries()
        productseries.product.translations_usage = ServiceUsage.LAUNCHPAD
        pot = self.factory.makePOTemplate(productseries=productseries)
        self._refreshCache()

        cache_with_template = self._readCache()

        productseries.product.translations_usage = ServiceUsage.UNKNOWN
        self._refreshCache()

        cache_without_template = self._readCache()
        self.assertNotEqual(cache_with_template, cache_without_template)
        self.assertContentEqual(
            cache_with_template, cache_without_template + [pot.id])

    def test_distro_translations_usage_affects_caching(self):
        # Templates from distributions are included in the cache only
        # where the distribution uses Launchpad Translations.
        package = self.factory.makeSourcePackage()
        package.distroseries.distribution.translations_usage = (
            ServiceUsage.LAUNCHPAD)
        pot = self.factory.makePOTemplate(
            distroseries=package.distroseries,
            sourcepackagename=package.sourcepackagename)
        self._refreshCache()

        cache_with_template = self._readCache()

        package.distroseries.distribution.translations_usage = (
            ServiceUsage.UNKNOWN)
        self._refreshCache()

        cache_without_template = self._readCache()
        self.assertNotEqual(cache_with_template, cache_without_template)
        self.assertContentEqual(
            cache_with_template, cache_without_template + [pot.id])

    def test_disabled_template_does_not_appear(self):
        # A template that is not current is excluded from the cache.
        self._refreshCache()
        cache_before = self._readCache()

        pot = self.factory.makePOTemplate()
        pot.setActive(False)
        self._refreshCache()

        self.assertEqual(cache_before, self._readCache())

    def test_disabled_template_is_removed(self):
        # A disabled template is removed from the cache immediately.
        pot = self.factory.makePOTemplate()
        self._refreshCache()
        cache_with_template = self._readCache()

        pot.setActive(False)
        cache_without_template = self._readCache()

        self.assertNotEqual(cache_with_template, cache_without_template)
        self.assertContentEqual(
            cache_with_template, cache_without_template + [pot.id])
