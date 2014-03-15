# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the branch vocabularies."""

__metaclass__ = type


from zope.component import getUtility

from lp.code.interfaces.branchlookup import IBranchLookup
from lp.code.vocabularies.branch import (
    BranchRestrictedOnProductVocabulary,
    BranchVocabulary,
    )
from lp.registry.enums import TeamMembershipPolicy
from lp.registry.interfaces.product import IProductSet
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


class TestBranchVocabulary(TestCaseWithFactory):
    """Test that the BranchVocabulary behaves as expected."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBranchVocabulary, self).setUp()
        self._createBranches()
        self.vocab = BranchVocabulary(context=None)

    def _createBranches(self):
        widget = self.factory.makeProduct(name='widget')
        sprocket = self.factory.makeProduct(name='sprocket')
        scotty = self.factory.makePerson(name='scotty')
        self.factory.makeProductBranch(
            owner=scotty, product=widget, name='fizzbuzz')
        self.factory.makeProductBranch(
            owner=scotty, product=widget, name='mountain')
        self.factory.makeProductBranch(
            owner=scotty, product=sprocket, name='fizzbuzz')

    def test_fizzbuzzBranches(self):
        """Return branches that match the string 'fizzbuzz'."""
        results = self.vocab.searchForTerms('fizzbuzz')
        expected = [
            u'~scotty/sprocket/fizzbuzz', u'~scotty/widget/fizzbuzz']
        branch_names = sorted([branch.token for branch in results])
        self.assertEqual(expected, branch_names)

    def test_singleQueryResult(self):
        # If there is a single search result that matches, use that
        # as the result.
        term = self.vocab.getTermByToken('mountain')
        self.assertEqual('~scotty/widget/mountain', term.value.unique_name)

    def test_multipleQueryResult(self):
        # If there are more than one search result, a LookupError is still
        # raised.
        self.assertRaises(LookupError, self.vocab.getTermByToken, 'fizzbuzz')


class TestRestrictedBranchVocabularyOnProduct(TestCaseWithFactory):
    """Test the BranchRestrictedOnProductVocabulary behaves as expected.

    When a BranchRestrictedOnProductVocabulary is used with a product the
    product of the branches in the vocabulary match the product given as the
    context.
    """

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestRestrictedBranchVocabularyOnProduct, self).setUp()
        self._createBranches()
        self.vocab = BranchRestrictedOnProductVocabulary(
            context=self._getVocabRestriction())

    def _getVocabRestriction(self):
        """Restrict using the widget product."""
        return getUtility(IProductSet).getByName('widget')

    def _createBranches(self):
        test_product = self.factory.makeProduct(name='widget')
        other_product = self.factory.makeProduct(name='sprocket')
        person = self.factory.makePerson(name='scotty')
        self.factory.makeProductBranch(
            owner=person, product=test_product, name='main')
        self.factory.makeProductBranch(
            owner=person, product=test_product, name='mountain')
        self.factory.makeProductBranch(
            owner=person, product=other_product, name='main')
        person = self.factory.makePerson(name='spotty')
        self.factory.makeProductBranch(
            owner=person, product=test_product, name='hill')
        self.product = test_product

    def test_mainBranches(self):
        """Look for widget's main branch.

        The result set should not show ~scotty/sprocket/main.
        """
        results = self.vocab.searchForTerms('main')
        expected = [u'~scotty/widget/main']
        branch_names = sorted([branch.token for branch in results])
        self.assertEqual(expected, branch_names)

    def test_singleQueryResult(self):
        # If there is a single search result that matches, use that
        # as the result.
        term = self.vocab.getTermByToken('mountain')
        self.assertEqual('~scotty/widget/mountain', term.value.unique_name)

    def test_multipleQueryResult(self):
        # If there are more than one search result, a LookupError is still
        # raised.
        self.assertRaises(LookupError, self.vocab.getTermByToken, 'scotty')

    def test_does_not_contain_inclusive_teams(self):
        open_team = self.factory.makeTeam(name='open-team',
            membership_policy=TeamMembershipPolicy.OPEN)
        delegated_team = self.factory.makeTeam(name='delegated-team',
            membership_policy=TeamMembershipPolicy.DELEGATED)
        for team in [open_team, delegated_team]:
            self.factory.makeProductBranch(
                owner=team, product=self.product, name='mountain')
        results = self.vocab.searchForTerms('mountain')
        branch_names = sorted([branch.token for branch in results])
        self.assertEqual(['~scotty/widget/mountain'], branch_names)


class TestRestrictedBranchVocabularyOnBranch(
    TestRestrictedBranchVocabularyOnProduct):
    """Test the BranchRestrictedOnProductVocabulary behaves as expected.

    When a BranchRestrictedOnProductVocabulary is used with a branch the
    product of the branches in the vocabulary match the product of the branch
    that is the context.
    """

    def _getVocabRestriction(self):
        """Restrict using a branch on widget."""
        return getUtility(IBranchLookup).getByUniqueName('~spotty/widget/hill')
