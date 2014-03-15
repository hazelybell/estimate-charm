# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the InlineMultiCheckboxWidget."""

__metaclass__ = type

from lazr.enum import (
    EnumeratedType,
    Item,
    )
import simplejson
from zope.interface import Interface
from zope.schema import List
from zope.schema._field import Choice
from zope.schema.vocabulary import getVocabularyRegistry

from lp.app.browser.lazrjs import InlineMultiCheckboxWidget
from lp.services.webapp.publisher import canonical_url
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


class Alphabet(EnumeratedType):
    """A vocabulary for testing."""
    A = Item("A", "Letter A")
    B = Item("B", "Letter B")


class TestInlineMultiCheckboxWidget(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def _getWidget(self, **kwargs):

        class ITest(Interface):
            test_field = List(
                Choice(vocabulary='BuildableDistroSeries'))
        return InlineMultiCheckboxWidget(
            None, ITest['test_field'], "Label", edit_url='fake', **kwargs)

    def _makeExpectedItems(self, vocab, selected=list(), value_fn=None):
        if value_fn is None:
            value_fn = lambda item: item.value.name
        expected_items = []
        style = 'font-weight: normal;'
        for item in vocab:
            new_item = {
                'name': item.title,
                'token': item.token,
                'style': style,
                'checked': (item.value in selected),
                'value': value_fn(item)}
            expected_items.append(new_item)
        return expected_items

    def test_items_for_field_vocabulary(self):
        widget = self._getWidget(attribute_type="reference")
        vocab = getVocabularyRegistry().get(None, 'BuildableDistroSeries')
        value_fn = lambda item: canonical_url(
            item.value, force_local_path=True)
        expected_items = self._makeExpectedItems(vocab, value_fn=value_fn)
        self.assertEqual(simplejson.dumps(expected_items), widget.json_items)

    def test_items_for_custom_vocabulary(self):
        widget = self._getWidget(vocabulary=Alphabet)
        expected_items = self._makeExpectedItems(Alphabet)
        self.assertEqual(simplejson.dumps(expected_items), widget.json_items)

    def test_items_for_custom_vocabulary_name(self):
        widget = self._getWidget(vocabulary="CountryName")
        vocab = getVocabularyRegistry().get(None, "CountryName")
        expected_items = self._makeExpectedItems(vocab)
        self.assertEqual(simplejson.dumps(expected_items), widget.json_items)

    def test_selected_items_checked(self):
        widget = self._getWidget(
            vocabulary=Alphabet, selected_items=[Alphabet.A])
        expected_items = self._makeExpectedItems(
            Alphabet, selected=[Alphabet.A])
        self.assertEqual(simplejson.dumps(expected_items), widget.json_items)
