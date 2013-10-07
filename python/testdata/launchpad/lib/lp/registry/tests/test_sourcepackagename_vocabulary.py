# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the source package name vocabularies."""

__metaclass__ = type

from lp.registry.vocabularies import SourcePackageNameVocabulary
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


class TestSourcePackageNameVocabulary(TestCaseWithFactory):
    """Test that the ProductVocabulary behaves as expected."""
    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestSourcePackageNameVocabulary, self).setUp()
        self.vocabulary = SourcePackageNameVocabulary()
        self.spn = self.factory.makeSourcePackageName(name='bedbugs')

    def test_toTerm(self):
        # Source package name terms are composed of name, and the spn.
        term = self.vocabulary.toTerm(self.spn)
        self.assertEqual(self.spn.name, term.title)
        self.assertEqual(self.spn.name, term.token)
        self.assertEqual(self.spn, term.value)

    def test_getTermByToken(self):
        # Tokens are case insentive because the name is lowercase.
        term = self.vocabulary.getTermByToken('BedBUGs')
        self.assertEqual(self.spn, term.value)

    def test_getTermByToken_LookupError(self):
        # getTermByToken() raises a LookupError when no match is found.
        self.assertRaises(
            LookupError,
            self.vocabulary.getTermByToken, 'does-notexist')
