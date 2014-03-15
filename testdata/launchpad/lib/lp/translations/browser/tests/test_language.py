# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the language views."""

__metaclass__ = type


from lp.testing import (
    login_celebrity,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.views import create_initialized_view


class LanguageAdminViewTestCase(TestCaseWithFactory):
    """Test language view."""

    layer = DatabaseFunctionalLayer

    def test_validatePluralData_invariant_error(self):
        # Both the number of plural forms and the plural form expression
        # fields must be provided together, or not at all.
        language = self.factory.makeLanguage(
            language_code='qq', name='Queque',
            pluralforms=None, plural_expression=None)
        form = {
            'field.code': 'qq',
            'field.englishname': 'Queque',
            'field.nativename': '',
            'field.pluralforms': '2',
            'field.pluralexpression': '',
            'field.visible': True,
            'field.direction': 'LTR',
            'field.actions.admin': 'Admin Language',
            }
        login_celebrity('admin')
        view = create_initialized_view(
             language, '+admin', rootsite='translations', form=form)
        self.assertEqual(1, len(view.errors), view.errors)
        self.assertEqual(
            'The number of plural forms and the plural form expression '
            'must be set together, or not at all.',
            view.errors[0])
