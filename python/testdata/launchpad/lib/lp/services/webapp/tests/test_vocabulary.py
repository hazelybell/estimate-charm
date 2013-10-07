# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type


from zope.interface import implements

from lp.services.webapp.vocabulary import (
    FilteredVocabularyBase,
    IHugeVocabulary,
    VocabularyFilter,
    )
from lp.testing import TestCaseWithFactory
from lp.testing.layers import ZopelessLayer


class TestVocabulary(FilteredVocabularyBase):
    implements(IHugeVocabulary)

    def search(self, query=None, vocab_filter=None):
        assert(isinstance(vocab_filter, VocabularyFilter))
        assert(vocab_filter.name == "ALL")
        assert(vocab_filter.title == "All")

    def searchForTerms(self, query=None, vocab_filter=None):
        assert(isinstance(vocab_filter, VocabularyFilter))
        assert(vocab_filter.name == "ALL")
        assert(vocab_filter.title == "All")

    def supportedFilters(self):
        return [FilteredVocabularyBase.ALL_FILTER]


class FilteredVocabularyBaseTestCase(TestCaseWithFactory):

    layer = ZopelessLayer

    def test_searchForTerms_filter_parameter_as_string(self):
        # If the vocab filter parameter is passed in as a string (name), it is
        # correctly transformed to a VocabularyFilter instance.
        vocab = TestVocabulary()
        vocab.searchForTerms(vocab_filter="ALL")

    def test_searchForTerms_filter_parameter_as_filter(self):
        # If the vocab filter parameter is passed in as a filter instance, it
        # is used as is.
        vocab = TestVocabulary()
        vocab.searchForTerms(vocab_filter=FilteredVocabularyBase.ALL_FILTER)

    def test_searchForTerms_invalid_filter_parameter(self):
        # If the vocab filter parameter is passed in as a string (name), and
        # the string is not a valid filter name, an exception is raised.
        vocab = TestVocabulary()
        self.assertRaises(
            ValueError, vocab.searchForTerms, vocab_filter="invalid")

    def test_search_filter_parameter_as_string(self):
        # If the vocab filter parameter is passed in as a string (name), it is
        # correctly transformed to a VocabularyFilter instance.
        vocab = TestVocabulary()
        vocab.search(vocab_filter="ALL")

    def test_search_filter_parameter_as_filter(self):
        # If the vocab filter parameter is passed in as a filter instance, it
        # is used as is.
        vocab = TestVocabulary()
        vocab.search(vocab_filter=FilteredVocabularyBase.ALL_FILTER)

    def test_search_invalid_filter_parameter(self):
        # If the vocab filter parameter is passed in as a string (name), and
        # the string is not a valid filter name, an exception is raised.
        vocab = TestVocabulary()
        self.assertRaises(
            ValueError, vocab.search, vocab_filter="invalid")
