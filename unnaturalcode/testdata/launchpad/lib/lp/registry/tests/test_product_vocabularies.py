# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the product vocabularies."""

__metaclass__ = type

from zope.component import getUtility

from lp.app.enums import InformationType
from lp.app.interfaces.services import IService
from lp.registry.enums import SharingPermission
from lp.registry.vocabularies import ProductVocabulary
from lp.testing import (
    ANONYMOUS,
    celebrity_logged_in,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestProductVocabulary(TestCaseWithFactory):
    """Test that the ProductVocabulary behaves as expected."""
    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestProductVocabulary, self).setUp()
        self.vocabulary = ProductVocabulary()
        self.product = self.factory.makeProduct(
            name='bedbugs', displayname='BedBugs')

    def test_toTerm(self):
        # Product terms are composed of title, name, and the object.
        term = self.vocabulary.toTerm(self.product)
        self.assertEqual(self.product.title, term.title)
        self.assertEqual(self.product.name, term.token)
        self.assertEqual(self.product, term.value)

    def test_getTermByToken(self):
        # Tokens are case insentive because the product name is lowercase.
        term = self.vocabulary.getTermByToken('BedBUGs')
        self.assertEqual(self.product, term.value)

    def test_getTermByToken_LookupError(self):
        # getTermByToken() raises a LookupError when no match is found.
        self.assertRaises(
            LookupError,
            self.vocabulary.getTermByToken, 'does-notexist')

    def test_search_in_any_case(self):
        # Search is case insensitive and uses stem rules.
        result = self.vocabulary.search('BEDBUG')
        self.assertEqual([self.product], list(result))

    def test_order_by_displayname(self):
        # Results are ordered by displayname.
        z_product = self.factory.makeProduct(
            name='mule', displayname='Bed zebra')
        a_product = self.factory.makeProduct(
            name='orange', displayname='Bed apple')
        result = self.vocabulary.search('bed')
        self.assertEqual(
            [a_product, z_product, self.product], list(result))

    def test_order_by_relevance(self):
        # When the flag is enabled, the most relevant result is first.
        bar_product = self.factory.makeProduct(
            name='foo-bar', displayname='Foo bar', summary='quux')
        quux_product = self.factory.makeProduct(
            name='foo-quux', displayname='Foo quux')
        result = self.vocabulary.search('quux')
        self.assertEqual(
            [quux_product, bar_product], list(result))

    def test_search_with_or_expression(self):
        # Searches for either of two or more names are possible.
        blah_product = self.factory.makeProduct(
            name='blah', displayname='Blah', summary='Blah blather')
        baz_product = self.factory.makeProduct(
            name='baz', displayname='Baz')
        result = self.vocabulary.search('blah OR baz')
        self.assertEqual(
            [blah_product, baz_product], list(result))

    def test_exact_match_is_first(self):
        # When the flag is enabled, an exact name match always wins.
        the_quux_product = self.factory.makeProduct(
            name='the-quux', displayname='The quux')
        quux_product = self.factory.makeProduct(
            name='quux', displayname='The quux')
        result = self.vocabulary.search('quux')
        self.assertEqual(
            [quux_product, the_quux_product], list(result))

    def test_inactive_products_are_excluded(self):
        # Inactive products are not in the vocabulary.
        with celebrity_logged_in('registry_experts'):
            self.product.active = False
        result = self.vocabulary.search('bedbugs')
        self.assertEqual([], list(result))

    def test_private_products(self):
        # Embargoed and proprietary products are only returned if
        # the current user can see them.
        public_product = self.factory.makeProduct('quux-public')
        embargoed_owner = self.factory.makePerson()
        embargoed_product = self.factory.makeProduct(
            name='quux-embargoed', owner=embargoed_owner,
            information_type=InformationType.EMBARGOED)
        proprietary_owner = self.factory.makePerson()
        proprietary_product = self.factory.makeProduct(
            name='quux-proprietary', owner=proprietary_owner,
            information_type=InformationType.PROPRIETARY)

        # Anonymous users see only the public product.
        with person_logged_in(ANONYMOUS):
            result = self.vocabulary.search('quux')
            self.assertEqual([public_product], list(result))

        # Ordinary logged in users see only the public product.
        user = self.factory.makePerson()
        with person_logged_in(user):
            result = self.vocabulary.search('quux')
            self.assertEqual([public_product], list(result))

        # People with grants on a private product can see this product.
        with person_logged_in(embargoed_owner):
            getUtility(IService, 'sharing').sharePillarInformation(
                embargoed_product, user, embargoed_owner,
                {InformationType.EMBARGOED: SharingPermission.ALL})
        with person_logged_in(user):
            result = self.vocabulary.search('quux')
            self.assertEqual([embargoed_product, public_product], list(result))

        # Admins can see all products.
        with celebrity_logged_in('admin'):
            result = self.vocabulary.search('quux')
            self.assertEqual(
                [embargoed_product, proprietary_product, public_product],
                list(result))
