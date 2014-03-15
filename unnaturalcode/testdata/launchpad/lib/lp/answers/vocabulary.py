# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Named vocabularies defined by the Answers application."""

__metaclass__ = type
__all__ = [
    'FAQVocabulary',
    'UsesAnswersDistributionVocabulary',
    'UsesAnswersProductVocabulary',
    ]

from sqlobject import OR
from storm.expr import And
from zope.interface import implements
from zope.schema.vocabulary import SimpleTerm

from lp.answers.interfaces.faq import IFAQ
from lp.answers.interfaces.faqtarget import IFAQTarget
from lp.app.enums import ServiceUsage
from lp.registry.interfaces.distribution import IDistribution
from lp.registry.model.product import Product
from lp.registry.vocabularies import (
    DistributionVocabulary,
    ProductVocabulary,
    )
from lp.services.webapp.vocabulary import (
    CountableIterator,
    FilteredVocabularyBase,
    IHugeVocabulary,
    )


class FAQVocabulary(FilteredVocabularyBase):
    """Vocabulary containing all the FAQs in an `IFAQTarget`."""
    implements(IHugeVocabulary)

    displayname = 'Select a FAQ'
    step_title = 'Search'

    def __init__(self, context):
        """Create a new vocabulary for the context.

        :param context: It should adaptable to `IFAQTarget`.
        """
        self.context = IFAQTarget(context)

    def __len__(self):
        """See `IIterableVocabulary`."""
        return self.context.searchFAQs().count()

    def __iter__(self):
        """See `IIterableVocabulary`."""
        for faq in self.context.searchFAQs():
            yield self.toTerm(faq)

    def __contains__(self, value):
        """See `IVocabulary`."""
        if not IFAQ.providedBy(value):
            return False
        return self.context.getFAQ(value.id) is not None

    def getTerm(self, value):
        """See `IVocabulary`."""
        if value not in self:
            raise LookupError(value)
        return self.toTerm(value)

    def getTermByToken(self, token):
        """See `IVocabularyTokenized`."""
        try:
            int(token)
        except ValueError:
            raise LookupError(token)
        faq = self.context.getFAQ(token)
        if faq is None:
            raise LookupError(token)
        return self.toTerm(faq)

    def toTerm(self, faq):
        """Return the term for a FAQ."""
        return SimpleTerm(faq, faq.id, faq.title)

    def searchForTerms(self, query=None, vocab_filter=None):
        """See `IHugeVocabulary`."""
        results = self.context.findSimilarFAQs(query)
        return CountableIterator(results.count(), results, self.toTerm)


class UsesAnswersProductVocabulary(ProductVocabulary):
    """Products that use Launchpad to track questions."""

    def search(self, query, vocab_filter=None):
        if vocab_filter is None:
            vocab_filter = []
        vocab_filter.append(
            And(Product.official_answers == True))
        return super(UsesAnswersProductVocabulary, self).search(
            query, vocab_filter)

class UsesAnswersDistributionVocabulary(DistributionVocabulary):
    """Distributions that use Launchpad to track questions.

    If the context is a distribution, it is always included in the
    vocabulary. Historic data is not invalidated if a distro stops
    using Launchpad to track questions. This vocabulary offers the correct
    choices of distributions at this moment.
    """

    def __init__(self, context=None):
        super(UsesAnswersDistributionVocabulary, self).__init__(
            context=context)
        self.distribution = IDistribution(self.context, None)

    @property
    def _filter(self):
        if self.distribution is None:
            distro_id = 0
        else:
            distro_id = self.distribution.id
        return OR(
            self._table.q.official_answers == True,
            self._table.id == distro_id)
