# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test Soyuz vocabularies."""

__metaclass__ = type

from testtools.matchers import MatchesStructure
from zope.schema.vocabulary import SimpleTerm

from lp.soyuz.vocabularies import PPAVocabulary
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


class TestPPAVocabulary(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_toTerm_empty_description(self):
        archive = self.factory.makeArchive(description='')
        vocab = PPAVocabulary()
        term = vocab.toTerm(archive)
        self.assertThat(term, MatchesStructure.byEquality(
            value=archive,
            token='%s/%s' % (archive.owner.name, archive.name),
            title='No description available'))
