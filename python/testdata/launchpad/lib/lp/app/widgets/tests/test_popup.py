# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

import simplejson
from zope.interface import Interface
from zope.interface.interface import InterfaceClass
from zope.schema import Choice
from zope.schema.vocabulary import getVocabularyRegistry

from lp.app.widgets.popup import (
    PersonPickerWidget,
    VocabularyPickerWidget,
    )
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


class TestMetaClass(InterfaceClass):
# We want to force creation of a field with an invalid HTML id.
    def __init__(self, name, bases=(), attrs=None, __doc__=None,
                 __module__=None):
        attrs = {
            "test_invalid_chars+":
            Choice(vocabulary='ValidTeamOwner'),
            "test_valid.item":
            Choice(vocabulary='ValidTeamOwner'),
            "test_filtered.item":
            Choice(vocabulary='DistributionOrProduct')}
        super(TestMetaClass, self).__init__(
            name, bases=bases, attrs=attrs, __doc__=__doc__,
            __module__=__module__)


class ITest(Interface):
# The schema class for the widget we will test.
    __metaclass__ = TestMetaClass


class TestVocabularyPickerWidget(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestVocabularyPickerWidget, self).setUp()
        self.context = self.factory.makeTeam()
        self.vocabulary_registry = getVocabularyRegistry()
        self.vocabulary = self.vocabulary_registry.get(
            self.context, 'ValidTeamOwner')
        self.request = LaunchpadTestRequest()

    def test_widget_template_properties(self):
        # Check the picker widget is correctly set up for a field which has a
        # name containing only valid HTML ID characters.

        field = ITest['test_valid.item']
        bound_field = field.bind(self.context)
        picker_widget = VocabularyPickerWidget(
            bound_field, self.vocabulary, self.request)

        widget_config = simplejson.loads(picker_widget.json_config)
        self.assertEqual(
            'ValidTeamOwner', picker_widget.vocabulary_name)
        self.assertEqual([
            {'name': 'ALL',
             'title': 'All',
             'description': 'Display all search results'},
            {'name': 'PERSON',
             'title': 'Person',
             'description': 'Display search results for people only'},
            {'name': 'TEAM',
             'title': 'Team',
             'description': 'Display search results for teams only'}
            ], picker_widget.vocabulary_filters)
        self.assertEqual(self.vocabulary.displayname, widget_config['header'])
        self.assertEqual(self.vocabulary.step_title,
            widget_config['step_title'])
        self.assertEqual(
            'show-widget-field-test_valid-item', picker_widget.show_widget_id)
        self.assertEqual(
            'field.test_valid.item', picker_widget.input_id)
        self.assertIsNone(picker_widget.extra_no_results_message)
        markup = picker_widget()
        self.assertIn("Y.lp.app.picker.addPicker", markup)
        self.assertIn('ValidTeamOwner', markup)

    def test_widget_filtered_vocabulary(self):
        # Check if a vocabulary supports filters, these are included in the
        # widget configuration.
        field = ITest['test_filtered.item']
        bound_field = field.bind(self.context)
        vocabulary = self.vocabulary_registry.get(
            self.context, 'DistributionOrProduct')
        picker_widget = VocabularyPickerWidget(
            bound_field, vocabulary, self.request)

        widget_config = simplejson.loads(picker_widget.json_config)
        self.assertEqual([
            {'name': 'ALL',
             'title': 'All',
             'description': 'Display all search results'},
            {'name': 'PROJECT',
             'title': 'Project',
             'description':
                 'Display search results associated with projects'},
            {'name': 'DISTRO',
             'title': 'Distribution',
             'description':
                 'Display search results associated with distributions'}
        ], widget_config['vocabulary_filters'])

    def test_widget_fieldname_with_invalid_html_chars(self):
        # Check the picker widget is correctly set up for a field which has a
        # name containing some invalid HTML ID characters.

        field = ITest['test_invalid_chars+']
        bound_field = field.bind(self.context)
        picker_widget = VocabularyPickerWidget(
            bound_field, self.vocabulary, self.request)

        # The widget name is encoded to get the widget's ID. It must only
        # contain valid HTML characters.
        self.assertEqual(
            'show-widget-field-test_invalid_chars-'
            'ZmllbGQudGVzdF9pbnZhbGlkX2NoYXJzKw',
            picker_widget.show_widget_id)
        self.assertEqual(
            'field.test_invalid_chars-ZmllbGQudGVzdF9pbnZhbGlkX2NoYXJzKw',
            picker_widget.input_id)

    def test_widget_suggestions(self):
        # The suggestions menu is shown when the input is invalid and there
        # are matches to suggest to the user.
        field = ITest['test_valid.item']
        bound_field = field.bind(self.context)
        request = LaunchpadTestRequest(form={'field.test_valid.item': 'foo'})
        picker_widget = VocabularyPickerWidget(
            bound_field, self.vocabulary, request)
        matches = list(picker_widget.matches)
        self.assertEqual(1, len(matches))
        self.assertEqual('Foo Bar', matches[0].title)
        markup = picker_widget()
        self.assertIn('id="field.test_valid.item-suggestions"', markup)
        self.assertIn(
            "Y.DOM.byId('field.test_valid.item-suggestions')", markup)
        self.assertTextMatchesExpressionIgnoreWhitespace(
            'Y.lp.app.picker.connect_select_menu\( '
            'select_menu, text_input\);',
            markup)

    def test_widget_extra_buttons(self):
        # The picker widgets define defaults for the display of extra buttons.
        field = ITest['test_valid.item']
        bound_field = field.bind(self.context)

        # A vocabulary widget does not show the extra buttons by default.
        picker_widget = VocabularyPickerWidget(
            bound_field, self.vocabulary, self.request)
        self.assertFalse(picker_widget.config['show_assign_me_button'])
        self.assertFalse(picker_widget.config['show_remove_button'])

        # A person picker widget does the assign button by default.
        person_picker_widget = PersonPickerWidget(
            bound_field, self.vocabulary, self.request)
        self.assertTrue(person_picker_widget.config['show_assign_me_button'])
        # But not the remove button.
        self.assertFalse(person_picker_widget.config['show_remove_button'])

    def test_create_team_link(self):
        # The person picker widget shows a create team link.
        field = ITest['test_valid.item']
        bound_field = field.bind(self.context)

        picker_widget = PersonPickerWidget(
            bound_field, self.vocabulary, self.request)
        picker_widget.show_create_team_link = True
        self.assertTrue(picker_widget.config['show_create_team'])

    def test_widget_personvalue_meta(self):
        # The person picker has the correct meta value for a person value.
        person = self.factory.makePerson()
        bound_field = ITest['test_valid.item'].bind(person)
        person_picker_widget = PersonPickerWidget(
            bound_field, self.vocabulary, self.request)
        person_picker_widget.setRenderedValue(person)
        self.assertEqual('person',
            person_picker_widget.config['selected_value_metadata'])

    def test_widget_teamvalue_meta(self):
        # The person picker has the correct meta value for a team value.
        team = self.factory.makeTeam()
        bound_field = ITest['test_valid.item'].bind(team)
        person_picker_widget = PersonPickerWidget(
            bound_field, self.vocabulary, self.request)
        person_picker_widget.setRenderedValue(team)
        self.assertEqual('team',
            person_picker_widget.config['selected_value_metadata'])
