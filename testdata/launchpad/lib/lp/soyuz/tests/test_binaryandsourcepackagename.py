# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the binary and source package name vocabularies."""

__metaclass__ = type

from storm.store import Store

from lp.soyuz.model.binaryandsourcepackagename import (
    BinaryAndSourcePackageName,
    BinaryAndSourcePackageNameVocabulary,
    )
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


class TestBinaryAndSourcePackageNameVocabulary(TestCaseWithFactory):
    """Test that the ProductVocabulary behaves as expected."""
    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBinaryAndSourcePackageNameVocabulary, self).setUp()
        self.vocabulary = BinaryAndSourcePackageNameVocabulary()
        spn = self.factory.makeSourcePackageName(name='bedbugs')
        self.bspn = Store.of(spn).find(
            BinaryAndSourcePackageName, name=spn.name).one()

    def test_toTerm(self):
        # Binary and source package name terms are composed of name,
        # and the bspn.
        term = self.vocabulary.toTerm(self.bspn)
        self.assertEqual(self.bspn.name, term.title)
        self.assertEqual(self.bspn.name, term.token)
        self.assertEqual(self.bspn, term.value)

    def test_getTermByToken(self):
        # Tokens are case insentive because the name is lowercase.
        term = self.vocabulary.getTermByToken('BedBUGs')
        self.assertEqual(self.bspn, term.value)

    def test_getTermByToken_LookupError(self):
        # getTermByToken() raises a LookupError when no match is found.
        self.assertRaises(
            LookupError,
            self.vocabulary.getTermByToken, 'does-notexist')
