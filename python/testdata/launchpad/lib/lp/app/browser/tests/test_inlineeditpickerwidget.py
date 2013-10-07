# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the InlineEditPickerWidget."""

__metaclass__ = type

from zope.interface import (
    implements,
    Interface,
    )
from zope.schema import Choice

from lp.app.browser.lazrjs import (
    InlineEditPickerWidget,
    InlinePersonEditPickerWidget,
    )
from lp.testing import (
    login_person,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestInlineEditPickerWidget(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def getWidget(self, **kwargs):
        class ITest(Interface):
            test_field = Choice(**kwargs)
        return InlineEditPickerWidget(
            None, ITest['test_field'], None, edit_url='fake')

    def test_huge_vocabulary_is_searchable(self):
        # Make sure that when given a field for a huge vocabulary, the picker
        # is set to show the search box.
        widget = self.getWidget(vocabulary='ValidPersonOrTeam')
        self.assertTrue(widget.config['show_search_box'])

    def test_vocabulary_filters(self):
        # Make sure that when given a vocabulary which supports vocab filters,
        # the vocab filters are include in the widget config.
        widget = self.getWidget(vocabulary='ValidPersonOrTeam')
        self.assertEquals([
            {'name': 'ALL',
             'title': 'All',
             'description': 'Display all search results'},
            {'name': 'PERSON',
             'title': 'Person',
             'description':
                 'Display search results for people only'},
            {'name': 'TEAM',
             'title': 'Team',
             'description':
                 'Display search results for teams only'}
            ],
            widget.config['vocabulary_filters'])

    def test_normal_vocabulary_is_not_searchable(self):
        # Make sure that when given a field for a normal vocabulary, the
        # picker is set to show the search box.
        widget = self.getWidget(vocabulary='UserTeamsParticipation')
        self.assertFalse(widget.config['show_search_box'])


class TestInlinePersonEditPickerWidget(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def getWidget(self, widget_value, show_create_team=False, **kwargs):
        class ITest(Interface):
            test_field = Choice(**kwargs)

        class Test:
            implements(ITest)

            def __init__(self):
                self.test_field = widget_value

        context = Test()
        return InlinePersonEditPickerWidget(
            context, ITest['test_field'], None, edit_url='fake',
            show_create_team=show_create_team)

    def test_person_selected_value_meta(self):
        # The widget has the correct meta value for a person value.
        widget_value = self.factory.makePerson()
        widget = self.getWidget(widget_value, vocabulary='ValidPersonOrTeam')
        self.assertEquals('person', widget.config['selected_value_metadata'])

    def test_team_selected_value_meta(self):
        # The widget has the correct meta value for a team value.
        widget_value = self.factory.makeTeam()
        widget = self.getWidget(widget_value, vocabulary='ValidPersonOrTeam')
        self.assertEquals('team', widget.config['selected_value_metadata'])

    def test_required_fields_dont_have_a_remove_link(self):
        widget = self.getWidget(
            None, vocabulary='ValidPersonOrTeam', required=True)
        self.assertFalse(widget.config['show_remove_button'])

    def test_optional_fields_do_have_a_remove_link(self):
        widget = self.getWidget(
            None, vocabulary='ValidPersonOrTeam', required=False)
        self.assertTrue(widget.config['show_remove_button'])

    def test_assign_me_exists_if_user_in_vocabulary(self):
        widget = self.getWidget(
            None, vocabulary='ValidPersonOrTeam', required=True)
        login_person(self.factory.makePerson())
        self.assertTrue(widget.config['show_assign_me_button'])

    def test_assign_me_not_shown_if_user_not_in_vocabulary(self):
        widget = self.getWidget(
            None, vocabulary='TargetPPAs', required=True)
        login_person(self.factory.makePerson())
        self.assertFalse(widget.config['show_assign_me_button'])

    def test_show_create_team_link(self):
        widget = self.getWidget(
            None, vocabulary='ValidPersonOrTeam', required=True,
            show_create_team=True)
        login_person(self.factory.makePerson())
        self.assertTrue(widget.config['show_create_team'])
