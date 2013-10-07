# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the pillar vocabularies."""

__metaclass__ = type

from lp.registry.vocabularies import (
    DistributionOrProductOrProjectGroupVocabulary,
    DistributionOrProductVocabulary,
    PillarVocabularyBase,
    )
from lp.testing import (
    celebrity_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestPillarVocabularyBase(TestCaseWithFactory):
    """Test that the PillarVocabularyBase behaves as expected."""
    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestPillarVocabularyBase, self).setUp()
        self.vocabulary = PillarVocabularyBase()
        self.product = self.factory.makeProduct(name='orchid-snark')
        self.distribution = self.factory.makeDistribution(name='zebra-snark')
        self.project_group = self.factory.makeProject(name='apple-snark')

    def test_supported_filters(self):
        # The vocab supports the correct filters.
        self.assertEqual([
            PillarVocabularyBase.ALL_FILTER],
            self.vocabulary.supportedFilters()
        )

    def test_Product_toTerm(self):
        # Product terms are composed of title, name, and the object.
        term = self.vocabulary.toTerm(self.product)
        self.assertEqual(self.product.title, term.title)
        self.assertEqual(self.product.name, term.token)
        self.assertEqual(self.product, term.value)

    def test_ProjectGroup_toTerm(self):
        # ProductGroup terms are composed of title, name, and the object.
        term = self.vocabulary.toTerm(self.project_group)
        self.assertEqual(self.project_group.title, term.title)
        self.assertEqual(self.project_group.name, term.token)
        self.assertEqual(self.project_group, term.value)

    def test_getTermByToken(self):
        # Tokens are case insentive because the product name is lowercase.
        term = self.vocabulary.getTermByToken('ORCHID-SNARK')
        self.assertEqual(self.product, term.value)

    def test_getTermByToken_LookupError(self):
        # getTermByToken() raises a LookupError when no match is found.
        self.assertRaises(
            LookupError,
            self.vocabulary.getTermByToken, 'does-notexist')

    def test_ordering(self):
        # Results are ordered by rank, with exact matches first.
        terms = self.vocabulary.searchForTerms('snark')
        result = [term.value for term in terms]
        self.assertEqual(
            [self.project_group, self.product, self.distribution], result)


class VocabFilterMixin:

    def _test_distribution_filter(self):
        # Only distributions should be included in the search results.
        terms = self.vocabulary.searchForTerms('snark', vocab_filter='DISTRO')
        result = [term.value for term in terms]
        self.assertEqual([self.distribution], result)

    def _test_project_filter(self):
        # Only projects should be included in the search results.
        terms = self.vocabulary.searchForTerms(
            'snark', vocab_filter='PROJECT')
        result = [term.value for term in terms]
        self.assertEqual([self.product], result)

    def _test_projectgroup_filter(self):
        # Only project groups should be included in the search results.
        terms = self.vocabulary.searchForTerms(
            'snark', vocab_filter='PROJECTGROUP')
        result = [term.value for term in terms]
        self.assertEqual([self.project_group], result)


class TestDistributionOrProductVocabulary(TestCaseWithFactory,
                                          VocabFilterMixin):
    """Test that the ProductVocabulary behaves as expected."""
    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestDistributionOrProductVocabulary, self).setUp()
        self.vocabulary = DistributionOrProductVocabulary()
        self.product = self.factory.makeProduct(name='orchid-snark')
        self.distribution = self.factory.makeDistribution(name='zebra-snark')

    def test_supported_filters(self):
        # The vocab supports the correct filters.
        self.assertEqual([
            DistributionOrProductVocabulary.ALL_FILTER,
            DistributionOrProductVocabulary.PROJECT_FILTER,
            DistributionOrProductVocabulary.DISTRO_FILTER,
            ],
            self.vocabulary.supportedFilters()
        )

    def test_project_filter(self):
        self._test_project_filter()

    def test_distribution_filter(self):
        self._test_distribution_filter()

    def test_inactive_products_are_excluded(self):
        # Inactive product are not in the vocabulary.
        with celebrity_logged_in('registry_experts'):
            self.product.active = False
        terms = self.vocabulary.searchForTerms('snark')
        result = [term.value for term in terms]
        self.assertEqual([self.distribution], result)
        self.assertFalse(self.product in self.vocabulary)

    def test_project_groups_are_excluded(self):
        # Project groups are not in the vocabulary.
        project_group = self.factory.makeProject(name='apple-snark')
        terms = self.vocabulary.searchForTerms('snark')
        result = [term.value for term in terms]
        self.assertEqual([self.product, self.distribution], result)
        self.assertFalse(project_group in self.vocabulary)


class TestDistributionOrProductOrProjectGroupVocabulary(TestCaseWithFactory,
                                                        VocabFilterMixin):
    """Test for DistributionOrProductOrProjectGroupVocabulary."""
    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestDistributionOrProductOrProjectGroupVocabulary, self).setUp()
        self.vocabulary = DistributionOrProductOrProjectGroupVocabulary()
        self.product = self.factory.makeProduct(name='orchid-snark')
        self.distribution = self.factory.makeDistribution(name='zebra-snark')
        self.project_group = self.factory.makeProject(name='apple-snark')

    def test_supported_filters(self):
        # The vocab supports the correct filters.
        self.assertEqual([
            DistributionOrProductOrProjectGroupVocabulary.ALL_FILTER,
            DistributionOrProductOrProjectGroupVocabulary.PROJECT_FILTER,
            DistributionOrProductOrProjectGroupVocabulary.PROJECTGROUP_FILTER,
            DistributionOrProductOrProjectGroupVocabulary.DISTRO_FILTER,
            ],
            self.vocabulary.supportedFilters()
        )

    def test_project_filter(self):
        self._test_project_filter()

    def test_projectgroup_filter(self):
        self._test_projectgroup_filter()

    def test_distribution_filter(self):
        self._test_distribution_filter()

    def test_contains_all_pillars_active(self):
        # All active products, project groups and distributions are included.
        self.assertTrue(self.product in self.vocabulary)
        self.assertTrue(self.distribution in self.vocabulary)
        self.assertTrue(self.project_group in self.vocabulary)

    def test_inactive_products_are_excluded(self):
        # Inactive product are not in the vocabulary.
        with celebrity_logged_in('registry_experts'):
            self.product.active = False
        terms = self.vocabulary.searchForTerms('snark')
        result = [term.value for term in terms]
        self.assertEqual([self.project_group, self.distribution], result)
        self.assertFalse(self.product in self.vocabulary)

    def test_inactive_product_groups_are_excluded(self):
        # Inactive project groups are not in the vocabulary.
        with celebrity_logged_in('registry_experts'):
            self.project_group.active = False
        terms = self.vocabulary.searchForTerms('snark')
        result = [term.value for term in terms]
        self.assertEqual([self.product, self.distribution], result)
        self.assertFalse(self.project_group in self.vocabulary)
