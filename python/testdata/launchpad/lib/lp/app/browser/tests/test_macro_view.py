# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for traversal from the root branch object."""

__metaclass__ = type

from zope.publisher.interfaces import NotFound

from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.publication import test_traverse


class TestMacroNontraversability(TestCaseWithFactory):
    """Macros should not be URL accessable (see bug 162868)."""

    layer = DatabaseFunctionalLayer

    # Names of some macros that are tested to ensure that they're not
    # accessable via URL.  This is not an exhaustive list.
    macro_names = (
        'feed-entry-atom',
        '+base-layout-macros',
        '+main-template-macros',
        'launchpad_form',
        'launchpad_widget_macros',
        '+forbidden-page-macros',
        '+search-form',
        '+primary-search-form"',
        'form-picker-macros',
        '+filebug-macros',
        '+bugtarget-macros-search',
        'bugcomment-macros',
        'bug-attachment-macros',
        '+portlet-malone-bugmail-filtering-faq',
        '+bugtask-macros-tableview',
        'bugtask-macros-cve',
        '+bmp-macros',
        'branch-form-macros',
        '+bmq-macros',
        '+announcement-macros',
        '+person-macros',
        '+milestone-macros',
        '+distributionmirror-macros',
        '+timeline-macros',
        '+macros',
        '+translations-macros',
        '+object-reassignment',
        '+team-bugs-macro',
    )

    @staticmethod
    def is_not_found(path):
        def traverse_and_call():
            view = test_traverse(path)[1]
            view()
        try:
            traverse_and_call()
        except NotFound:
            return True
        else:
            return False

    def test_macro_names_not_traversable(self):
        for name in self.macro_names:
            self.assertTrue(self.is_not_found('http://launchpad.dev/' + name),
                'macro name %r should not be URL accessable' % name)
