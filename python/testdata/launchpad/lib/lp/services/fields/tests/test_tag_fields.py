# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for tag related fields."""

from zope.schema.interfaces import ConstraintNotSatisfied

from lp.services.fields import (
    SearchTag,
    Tag,
    )
from lp.testing import TestCase
from lp.testing.layers import LaunchpadFunctionalLayer


class TestTag(TestCase):

    layer = LaunchpadFunctionalLayer
    field = Tag()

    def test_allow_valid_names(self):
        # Tag allows names all in lowercase, starting with any letter
        # of the English alphabet, followed by 1 or more letters,
        # numbers or minuses.
        self.assertIs(None, self.field.validate(u'fred'))
        self.assertIs(None, self.field.validate(u'one-two'))
        self.assertIs(None, self.field.validate(u'one-2'))
        self.assertIs(None, self.field.validate(u'one-2-3---5-'))

    def test_too_short(self):
        # Tag rejects tags that are less than 2 characters long.
        self.assertRaises(
            ConstraintNotSatisfied,
            self.field.validate, u'')
        self.assertRaises(
            ConstraintNotSatisfied,
            self.field.validate, u'x')

    def test_invalid_characters(self):
        # Tag rejects characters outside of the range [a-z0-9-].
        # Hyphens are also rejected at the start of a tag; see
        # test_negated_search_form.
        self.assertRaises(
            ConstraintNotSatisfied,
            self.field.validate, u'char^not^allowed')
        self.assertRaises(
            ConstraintNotSatisfied,
            self.field.validate, u'no whitespace')
        self.assertRaises(
            ConstraintNotSatisfied,
            self.field.validate, u'really\no-whitespace')

    def test_negated_search_form(self):
        # Tag rejects tags beginning with minuses. This form is
        # reserved to mean "not <tag>".
        self.assertRaises(
            ConstraintNotSatisfied,
            self.field.validate, u'-fred')

    def test_wildcard(self):
        # Tag rejects a solitary asterisk, or an asterisk preceded by
        # a minus. This is not surprising seeing as asterisks are
        # forbidden anyway, as are leading minuses. However, this form
        # is special because it is reserved to mean "any tag" or "not
        # any tag".
        self.assertRaises(
            ConstraintNotSatisfied,
            self.field.validate, u'*')
        self.assertRaises(
            ConstraintNotSatisfied,
            self.field.validate, u'-*')


class TestSearchTag(TestTag):

    field = SearchTag()

    def test_negated_search_form(self):
        # SearchTag allows tags beginning with minuses. This form is
        # reserved to mean "not <tag>".
        self.assertIs(None, self.field.validate(u'-fred'))

    def test_wildcard(self):
        # SearchTag allows a solitary asterisk, or an asterisk
        # preceded by a minus. This means "any tag" or "not any
        # tag".
        self.assertIs(None, self.field.validate(u'*'))
        self.assertIs(None, self.field.validate(u'-*'))

    def test_wildcard_elsewhere(self):
        # Asterisks are not allowed to appear anywhere else in a tag.
        self.assertRaises(
            ConstraintNotSatisfied,
            self.field.validate, u'sn*t-allowed')
