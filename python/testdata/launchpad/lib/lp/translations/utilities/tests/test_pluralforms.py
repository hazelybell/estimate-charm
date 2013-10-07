# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import unittest

from lp.translations.utilities.pluralforms import (
    BadPluralExpression,
    make_friendly_plural_forms,
    )


class PluralFormsTest(unittest.TestCase):
    """Test utilities for handling plural forms."""

    def test_make_friendly_plural_forms(self):
        single_form = make_friendly_plural_forms('0', 1)
        self.assertEqual(single_form,
                         [{'examples': [0, 1, 2, 3, 4, 5], 'form': 0}])

        two_forms = make_friendly_plural_forms('n!=1', 2)
        self.assertEqual(two_forms,
                         [{'examples': [1], 'form': 0},
                          {'examples': [0, 2, 3, 4, 5, 6], 'form': 1}])

    def test_make_friendly_plural_form_failures(self):
        # 'To the degree of' is not accepted.
        self.assertRaises(BadPluralExpression,
                          make_friendly_plural_forms, 'n**2', 1)

        # Expressions longer than 500 characters are not accepted.
        long_but_valid = '+'.join(['0'] * 500)
        self.assertRaises(BadPluralExpression,
                          make_friendly_plural_forms, long_but_valid, 1)

        # Only "n" is allowed as a variable.
        self.assertRaises(BadPluralExpression,
                          make_friendly_plural_forms, '(a=1)', 1)

        # Dividing by zero doesn't work.
        self.assertRaises(BadPluralExpression,
                          make_friendly_plural_forms, '(n/0)', 1)

        # The modulo operator does not allow divide-by-zero either.
        self.assertRaises(BadPluralExpression,
                          make_friendly_plural_forms, '3%n', 1)

        # Must discover the expected number of forms.
        self.assertRaises(BadPluralExpression,
                          make_friendly_plural_forms, 'n!=1', 3)

        # Can't have more than the expected number of forms.
        self.assertRaises(BadPluralExpression,
                          make_friendly_plural_forms, 'n==0', 1)

        # Must find exactly the expected form numbers.
        self.assertRaises(BadPluralExpression,
                          make_friendly_plural_forms, 'n==0 ? 1 : 2', 2)

    def test_make_friendly_plural_form_zero_handling(self):
        zero_forms = make_friendly_plural_forms('n!=0', 2)
        self.assertEqual(zero_forms,
                         [{'examples': [0], 'form': 0},
                          {'examples': [1, 2, 3, 4, 5, 6], 'form': 1}])

        # Since 'n' can be zero as well, dividing by it won't work.
        self.assertRaises(BadPluralExpression,
                          make_friendly_plural_forms, '(1/n)', 1)
