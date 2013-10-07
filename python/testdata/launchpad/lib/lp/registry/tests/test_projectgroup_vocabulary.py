# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the ProjectGroup vocabulary."""

__metaclass__ = type

from lp.registry.vocabularies import ProjectGroupVocabulary
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


class TestProjectGroupVocabulary(TestCaseWithFactory):
    """Test that the ProjectGroupVocabulary behaves as expected."""
    layer = DatabaseFunctionalLayer

    def test_search_with_or_expression(self):
        # Searches for either of two or more names are possible.
        blah_group = self.factory.makeProject(
            name='blah', displayname='Blah', summary='Blah blather')
        baz_group = self.factory.makeProject(
            name='baz', displayname='Baz')
        vocabulary = ProjectGroupVocabulary()
        result = vocabulary.search('blah OR baz')
        self.assertEqual(
            [blah_group, baz_group], list(result))
