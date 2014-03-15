# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the information type vocabulary."""

__metaclass__ = type

from testtools.matchers import MatchesStructure

from lp.app.enums import InformationType
from lp.app.vocabularies import InformationTypeVocabulary
from lp.testing import TestCase


class TestInformationTypeVocabulary(TestCase):

    def test_vocabulary_items_custom(self):
        # The vocab is given a custom set of types to include.
        vocab = InformationTypeVocabulary(
            [InformationType.PUBLICSECURITY, InformationType.USERDATA])
        self.assertIn(InformationType.USERDATA, vocab)
        self.assertIn(InformationType.PUBLICSECURITY, vocab)
        self.assertNotIn(InformationType.PUBLIC, vocab)

    def test_getTermByToken(self):
        vocab = InformationTypeVocabulary([InformationType.PUBLIC])
        self.assertThat(
            vocab.getTermByToken('PUBLIC'),
            MatchesStructure.byEquality(
                value=InformationType.PUBLIC,
                token='PUBLIC',
                title='Public',
                description=InformationType.PUBLIC.description))
