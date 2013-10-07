# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from zope.schema.vocabulary import SimpleTerm

from lp.services.webapp.vocabulary import ForgivingSimpleVocabulary
from lp.testing import TestCase


class TestForgivingSimpleVocabulary(TestCase):
    """Tests for ForgivingSimpleVocabulary."""

    def setUp(self):
        super(TestForgivingSimpleVocabulary, self).setUp()
        self.term_1 = SimpleTerm('term-1', 'term-1', 'My first term')
        self.term_2 = SimpleTerm('term-2', 'term-2', 'My second term')
        self.vocabulary = ForgivingSimpleVocabulary(
            terms=[self.term_1, self.term_2], default_term=self.term_2)

    def test_normal_lookup(self):
        """Lookups for proper values succeed."""
        self.assertIs(self.vocabulary.getTerm('term-1'), self.term_1)

    def test_errant_lookup(self):
        """Lookups for invalid values return the default."""
        self.assertIs(self.vocabulary.getTerm('does-not-exist'), self.term_2)
