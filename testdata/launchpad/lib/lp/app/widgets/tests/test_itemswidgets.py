# Copyright 2011-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

import doctest

from lazr.enum import (
    EnumeratedType,
    Item,
    )
from lazr.enum._enum import (
    DBEnumeratedType,
    DBItem,
    )
from testtools.matchers import DocTestMatches
from zope.schema import Choice
from zope.schema.vocabulary import (
    SimpleTerm,
    SimpleVocabulary,
    )

from lp.app.browser.lazrjs import (
    EnumChoiceWidget,
    vocabulary_to_choice_edit_items,
    )
from lp.app.widgets.itemswidgets import (
    LabeledMultiCheckBoxWidget,
    LaunchpadRadioWidget,
    LaunchpadRadioWidgetWithDescription,
    PlainMultiCheckBoxWidget,
    )
from lp.code.interfaces.branch import IBranch
from lp.services.webapp.escaping import structured
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.testing import (
    ANONYMOUS,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class ItemWidgetTestCase(TestCaseWithFactory):
    """A test case that sets up an items widget for testing."""

    layer = DatabaseFunctionalLayer

    WIDGET_CLASS = None
    SAFE_TERM = SimpleTerm('object-1', 'token-1', 'Safe title')
    UNSAFE_TERM = SimpleTerm('object-2', 'token-2', '<unsafe> &nbsp; title')

    def setUp(self):
        super(ItemWidgetTestCase, self).setUp()
        self.request = LaunchpadTestRequest()
        self.vocabulary = SimpleVocabulary([self.SAFE_TERM, self.UNSAFE_TERM])
        field = Choice(__name__='test_field', vocabulary=self.vocabulary)
        self.field = field.bind(object())
        self.widget = self.WIDGET_CLASS(
            self.field, self.vocabulary, self.request)

    def assertRenderItem(self, expected, term, checked=False):
        markup = self.widget._renderItem(
            index=1, text=term.title, value=term.token,
            name=self.field.__name__, cssClass=None, checked=checked)
        expected_matcher = DocTestMatches(
            expected, (doctest.NORMALIZE_WHITESPACE |
                       doctest.REPORT_NDIFF | doctest.ELLIPSIS))
        self.assertThat(markup, expected_matcher)


class TestPlainMultiCheckBoxWidget(ItemWidgetTestCase):
    """Test the PlainMultiCheckBoxWidget class."""

    WIDGET_CLASS = PlainMultiCheckBoxWidget

    def test__renderItem_checked(self):
        # Render item in checked state.
        expected = (
            '<input ... checked="checked" ... />&nbsp;Safe title')
        self.assertRenderItem(expected, self.SAFE_TERM, checked=True)

    def test__renderItem_unchecked(self):
        # Render item in unchecked state.
        expected = (
            '<input class="checkboxType" id="test_field.1" name="test_field" '
            'type="checkbox" value="token-1" />&nbsp;Safe title ')
        self.assertRenderItem(expected, self.SAFE_TERM, checked=False)

    def test__renderItem_unsafe_content(self):
        # Render item escapes unsafe markup.
        expected = '<input ... />&nbsp;&lt;unsafe&gt; &amp;nbsp; title '
        self.assertRenderItem(expected, self.UNSAFE_TERM, checked=False)


class TestLabeledMultiCheckBoxWidget(ItemWidgetTestCase):
    """Test the LabeledMultiCheckBoxWidget class."""

    WIDGET_CLASS = LabeledMultiCheckBoxWidget

    def test__renderItem_checked(self):
        # Render item in checked state.
        expected = (
            '<label ...><input ... checked="checked" ... />&nbsp;'
            'Safe title</label>')
        self.assertRenderItem(expected, self.SAFE_TERM, checked=True)

    def test__renderItem_unchecked(self):
        # Render item in unchecked state.
        expected = (
            '<label for="field.test_field.1" style="font-weight: normal">'
            '<input class="checkboxType" id="test_field.1" name="test_field" '
            'type="checkbox" value="token-1" />&nbsp;Safe title</label> ')
        self.assertRenderItem(expected, self.SAFE_TERM, checked=False)

    def test__renderItem_unsafe_content(self):
        # Render item escapes unsafe markup.
        expected = '<label .../>&nbsp;&lt;unsafe&gt; &amp;nbsp; title</label>'
        self.assertRenderItem(expected, self.UNSAFE_TERM, checked=False)


class TestLaunchpadRadioWidget(ItemWidgetTestCase):
    """Test the LaunchpadRadioWidget class."""

    WIDGET_CLASS = LaunchpadRadioWidget

    def test__renderItem_checked(self):
        # Render item in checked state.
        expected = (
            '<label ...><input ... checked="checked" ... />&nbsp;'
            'Safe title</label>')
        self.assertRenderItem(expected, self.SAFE_TERM, checked=True)

    def test__renderItem_unchecked(self):
        # Render item in unchecked state.
        expected = (
            '<label style="font-weight: normal">'
            '<input class="radioType" id="test_field.1" name="test_field" '
            'type="radio" value="token-1" />&nbsp;Safe title</label>')
        self.assertRenderItem(expected, self.SAFE_TERM, checked=False)

    def test__renderItem_unsafe_content(self):
        # Render item escapes unsafe markup.
        expected = (
            '<label ...><input ... />'
            '&nbsp;&lt;unsafe&gt; &amp;nbsp; title</label>')
        self.assertRenderItem(expected, self.UNSAFE_TERM, checked=False)

    def test__renderItem_without_label(self):
        # Render item omits a wrapping label if the text contains a label.
        html_term = SimpleTerm(
            'object-3', 'token-3', structured('<label>title</label>'))
        expected = ('<input ... />&nbsp;<label>title</label>')
        self.assertRenderItem(expected, html_term, checked=False)


class TestLaunchpadRadioWidgetWithDescription(TestCaseWithFactory):
    """Test the LaunchpadRadioWidgetWithDescription class."""

    layer = DatabaseFunctionalLayer

    class TestEnum(EnumeratedType):
        SAFE_TERM = Item('item-1', description='Safe title')
        UNSAFE_TERM = Item('item-<2>', description='<unsafe> &nbsp; title')

    def setUp(self):
        super(TestLaunchpadRadioWidgetWithDescription, self).setUp()
        self.request = LaunchpadTestRequest()
        field = Choice(__name__='test_field', vocabulary=self.TestEnum)
        self.field = field.bind(object())
        self.widget = LaunchpadRadioWidgetWithDescription(
            self.field, self.TestEnum, self.request)

    def assertRenderItem(self, expected, method, enum_item):
        markup = method(
            index=1, text=enum_item.title, value=enum_item.name,
            name=self.field.__name__, cssClass=None)
        expected_matcher = DocTestMatches(
            expected, (doctest.NORMALIZE_WHITESPACE |
                       doctest.REPORT_NDIFF | doctest.ELLIPSIS))
        self.assertThat(markup, expected_matcher)

    def test_renderSelectedItem(self):
        # Render checked="checked" item in checked state.
        expected = (
            '<tr> <td rowspan="2">'
            '<input class="radioType" checked="checked" id="test_field.1" '
            'name="test_field" type="radio" value="SAFE_TERM" /></td> '
            '<td><label for="test_field.1">item-1</label></td> </tr> '
            '<tr> <td class="formHelp">Safe title</td> </tr>')
        self.assertRenderItem(
            expected, self.widget.renderSelectedItem, self.TestEnum.SAFE_TERM)

    def test_renderItem(self):
        # Render item in unchecked state.
        expected = (
            '<tr> <td rowspan="2">'
            '<input class="radioType" id="test_field.1" '
            'name="test_field" type="radio" value="SAFE_TERM" /></td> '
            '<td><label for="test_field.1">item-1</label></td> </tr> '
            '<tr> <td class="formHelp">Safe title</td> </tr>')
        self.assertRenderItem(
            expected, self.widget.renderItem, self.TestEnum.SAFE_TERM)

    def test_renderSelectedItem_unsafe_content(self):
        # Render selected item escapes unsafe markup.
        expected = (
            '<...>item-&lt;2&gt;<...>&lt;unsafe&gt; &amp;nbsp; title<...>')
        self.assertRenderItem(
            expected,
            self.widget.renderSelectedItem, self.TestEnum.UNSAFE_TERM)

    def test_renderItem_unsafe_content(self):
        # Render item escapes unsafe markup.
        expected = (
            '<...>item-&lt;2&gt;<...>&lt;unsafe&gt; &amp;nbsp; title<...>')
        self.assertRenderItem(
            expected, self.widget.renderItem, self.TestEnum.UNSAFE_TERM)

    def test_renderExtraHint(self):
        # If an extra hint is specified, it is rendered.
        self.widget.extra_hint = "Hello World"
        self.widget.extra_hint_class = 'hint_class'
        expected = (
            '<div class="hint_class">Hello World</div>')
        hint_html = self.widget.renderExtraHint()
        self.assertEqual(expected, hint_html)


class TestEnumChoiceWidget(TestCaseWithFactory):
    """Tests for EnumChoiceWidget and vocabulary_to_choice_edit_items."""

    layer = DatabaseFunctionalLayer

    class ChoiceEnum(DBEnumeratedType):

        ITEM_A = DBItem(1, """
            Item A

            This is item A.
            """)

        ITEM_B = DBItem(2, """
            Item B

            This is item B.
            """)

    def _makeItemDict(self, item, overrides=None):
        if not overrides:
            overrides = dict()
        result = {
            'value': item.title,
            'name': item.title,
            'description': item.description,
            'description_css_class': 'choice-description',
            'style': '', 'help': '', 'disabled': False}
        result.update(overrides)
        return result

    def test_vocabulary_to_choice_edit_items(self):
        # The items list is as expected without the feature flag.
        items = vocabulary_to_choice_edit_items(self.ChoiceEnum)
        overrides = {'description': ''}
        expected = [self._makeItemDict(e.value, overrides)
                    for e in self.ChoiceEnum]
        self.assertEqual(expected, items)

    def test_vocabulary_to_choice_edit_items_no_description(self):
        # There are no descriptions unless wanted.
        overrides = {'description': ''}
        items = vocabulary_to_choice_edit_items(self.ChoiceEnum)
        expected = [self._makeItemDict(e.value, overrides)
                    for e in self.ChoiceEnum]
        self.assertEqual(expected, items)

    def test_vocabulary_to_choice_edit_items_with_description(self):
        # The items list is as expected.
        items = vocabulary_to_choice_edit_items(
            self.ChoiceEnum, include_description=True)
        expected = [self._makeItemDict(e.value) for e in self.ChoiceEnum]
        self.assertEqual(expected, items)

    def test_vocabulary_to_choice_edit_items_excluded_items(self):
        # Excluded items are not included.
        items = vocabulary_to_choice_edit_items(
            self.ChoiceEnum, include_description=True,
            excluded_items=[self.ChoiceEnum.ITEM_B])
        expected = [self._makeItemDict(self.ChoiceEnum.ITEM_A)]
        self.assertEqual(expected, items)

    def test_widget_with_anonymous_user(self):
        # When the user is anonymous, the widget outputs static text.
        branch = self.factory.makeAnyBranch()
        widget = EnumChoiceWidget(
            branch, IBranch['lifecycle_status'],
            header='Change status to', css_class_prefix='branchstatus')
        with person_logged_in(ANONYMOUS):
            markup = widget()
        expected = """
        <span id="edit-lifecycle_status">
            <span class="value branchstatusDEVELOPMENT">Development</span>
        </span>
        """
        expected_matcher = DocTestMatches(
            expected, (doctest.NORMALIZE_WHITESPACE |
                       doctest.REPORT_NDIFF | doctest.ELLIPSIS))
        self.assertThat(markup, expected_matcher)

    def test_widget_with_user(self):
        # When the user has edit permission, the widget allows changes via JS.
        branch = self.factory.makeAnyBranch()
        widget = EnumChoiceWidget(
            branch, IBranch['lifecycle_status'],
            header='Change status to', css_class_prefix='branchstatus')
        with person_logged_in(branch.owner):
            markup = widget()
        expected = """
        <span id="edit-lifecycle_status">
            <span class="value branchstatusDEVELOPMENT">Development</span>
            <span>
            <a class="editicon sprite edit action-icon"
                href="http://.../+edit"
                title="">Edit</a>
            </span>
        </span>
        <script>
        LPJS.use('lp.app.choice', function(Y) {
        ...
        </script>
        """
        expected_matcher = DocTestMatches(
            expected, (doctest.NORMALIZE_WHITESPACE |
                       doctest.REPORT_NDIFF | doctest.ELLIPSIS))
        self.assertThat(markup, expected_matcher)
