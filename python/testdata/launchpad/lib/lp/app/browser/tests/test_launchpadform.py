# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the lp.app.browser.launchpadform module."""

__metaclass__ = type

from os.path import (
    dirname,
    join,
    )

from lxml import html
import simplejson
from testtools.content import text_content
from z3c.ptcompat import ViewPageTemplateFile
from zope.formlib.form import action
from zope.interface import Interface
from zope.schema import (
    Choice,
    Text,
    TextLine,
    )
from zope.schema.vocabulary import SimpleVocabulary

from lp.app.browser.launchpadform import (
    has_structured_doc,
    LaunchpadFormView,
    )
from lp.services.config import config
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.testing import (
    test_tales,
    TestCase,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    FunctionalLayer,
    )


class TestInterface(Interface):
    """Test interface for the view below."""

    normal = Text(title=u'normal', description=u'plain text')

    structured = has_structured_doc(
        Text(title=u'structured',
             description=u'<strong>structured text</strong'))


class TestView(LaunchpadFormView):
    """A trivial view using the TestInterface."""

    schema = TestInterface


class TestHasStructuredDoc(TestCase):

    layer = FunctionalLayer

    def _widget_annotation(self, widget):
        return widget.context.queryTaggedValue('has_structured_doc')

    def test_has_structured_doc_sets_attribute(self):
        # Test that has_structured_doc sets the field annotation.
        request = LaunchpadTestRequest()
        view = TestView(None, request)
        view.initialize()
        normal_widget, structured_widget = view.widgets
        self.assertIs(None, self._widget_annotation(normal_widget))
        self.assertTrue(self._widget_annotation(structured_widget))


class TestQueryTalesForHasStructuredDoc(TestCase):

    layer = FunctionalLayer

    def test_query_tales(self):
        # Test that query:has-structured-doc gets sets the field annotation.
        request = LaunchpadTestRequest()
        view = TestView(None, request)
        view.initialize()
        normal_widget, structured_widget = view.widgets
        self.assertIs(None, test_tales(
                'widget/query:has-structured-doc', widget=normal_widget))
        self.assertTrue(test_tales(
                'widget/query:has-structured-doc', widget=structured_widget))


class TestHelpLinksInterface(Interface):
    """Test interface for the view below."""

    nickname = Text(title=u'nickname')

    displayname = Text(title=u'displayname')


class TestHelpLinksView(LaunchpadFormView):
    """A trivial view that contains help links."""

    schema = TestHelpLinksInterface

    page_title = u"TestHelpLinksView"
    template = ViewPageTemplateFile(
        config.root + '/lib/lp/app/templates/generic-edit.pt')

    help_links = {
        "nickname": u"http://widget.example.com/name",
        "displayname": u"http://widget.example.com/displayname",
        }


class TestHelpLinks(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_help_links_on_widget(self):
        # The values in a view's help_links dictionary gets copied into the
        # corresponding widgets' help_link attributes.
        request = LaunchpadTestRequest()
        view = TestHelpLinksView(None, request)
        view.initialize()
        nickname_widget, displayname_widget = view.widgets
        self.assertEqual(
            u"http://widget.example.com/name",
            nickname_widget.help_link)
        self.assertEqual(
            u"http://widget.example.com/displayname",
            displayname_widget.help_link)

    def test_help_links_render(self):
        # The values in a view's help_links dictionary are rendered in the
        # default generic-edit template.
        user = self.factory.makePerson()
        request = LaunchpadTestRequest(PATH_INFO="/")
        request.setPrincipal(user)
        view = TestHelpLinksView(user, request)
        view.initialize()
        root = html.fromstring(view.render())
        [nickname_help_link] = root.cssselect(
            "label[for$=nickname] ~ a[target=help]")
        self.assertEqual(
            u"http://widget.example.com/name",
            nickname_help_link.get("href"))
        [displayname_help_link] = root.cssselect(
            "label[for$=displayname] ~ a[target=help]")
        self.assertEqual(
            u"http://widget.example.com/displayname",
            displayname_help_link.get("href"))


class TestWidgetDivInterface(Interface):
    """Test interface for the view below."""

    single_line = TextLine(title=u'single_line')
    multi_line = Text(title=u'multi_line')
    checkbox = Choice(
        vocabulary=SimpleVocabulary.fromItems(
            (('yes', True), ('no', False))))


class TestWidgetDivView(LaunchpadFormView):
    """A trivial view using `TestWidgetDivInterface`."""

    schema = TestWidgetDivInterface
    template = ViewPageTemplateFile(
        join(dirname(__file__), "test-widget-div.pt"))


class TestWidgetDiv(TestCase):
    """Tests for the `widget_div` template macro."""

    layer = FunctionalLayer

    def test_all_widgets_present(self):
        request = LaunchpadTestRequest()
        view = TestWidgetDivView({}, request)
        content = view()
        self.addDetail("content", text_content(content))
        root = html.fromstring(content)
        # All the widgets appear in the page.
        self.assertEqual(
            ["field.single_line", "field.multi_line", "field.checkbox"],
            root.xpath("//@id"))

    def test_all_widgets_present_but_hidden(self):
        request = LaunchpadTestRequest()
        view = TestWidgetDivView({}, request)
        view.initialize()
        for widget in view.widgets:
            widget.visible = False
        content = view.render()
        self.addDetail("content", text_content(content))
        root = html.fromstring(content)
        # All the widgets appear in the page as hidden inputs.
        self.assertEqual(
            ["field.single_line", "hidden",
             "field.multi_line", "hidden",
             "field.checkbox", "hidden"],
            root.xpath("//input/@id | //input/@type"))


class TestFormView(TestWidgetDivView):
    """A trivial view with an action and a validator which sets errors."""
    @action('Test', name='test',
        failure=LaunchpadFormView.ajax_failure_handler)
    def test_action(self, action, data):
        single_line_value = data['single_line']
        if single_line_value == 'success':
            return
        self.addError("An action error")

    def validate(self, data):
        single_line_value = data['single_line']
        if single_line_value != 'error':
            return
        self.setFieldError('single_line', 'An error occurred')
        self.addError('A form error')


class TestAjaxValidator(TestCase):
    # For ajax requests to form views, when the validators record errors as
    # having occurred, the form returns json data which contains information
    # about the errors.

    layer = FunctionalLayer

    def test_ajax_failure_handler(self):
        # Validation errors are recorded properly.
        extra = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        request = LaunchpadTestRequest(
            method='POST',
            form={
                'field.actions.test': 'Test',
                'field.single_line': 'error'},
            **extra)
        view = TestFormView({}, request)
        view.initialize()
        self.assertEqual(
                {"error_summary": "There are 2 errors.",
                 "errors": {"field.single_line": "An error occurred"},
                 "form_wide_errors": ["A form error"]},
            simplejson.loads(view.form_result))

    def test_non_ajax_failure_handler(self):
        # The ajax error handler is not run if the request is not ajax.
        request = LaunchpadTestRequest(
            method='POST',
            form={
                'field.actions.test': 'Test',
                'field.single_line': 'error'})
        view = TestFormView({}, request)
        view.initialize()
        self.assertIsNone(view.form_result)

    def test_ajax_action_success(self):
        # When there are no errors, form_result is None.
        extra = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        request = LaunchpadTestRequest(
            method='POST',
            form={
                'field.actions.test': 'Test',
                'field.single_line': 'success'},
            **extra)
        view = TestFormView({}, request)
        view.initialize()
        self.assertIsNone(view.form_result)

    def test_ajax_action_failure(self):
        # When there are errors performing the action, these are recorded.
        extra = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        request = LaunchpadTestRequest(
            method='POST',
            form={
                'field.actions.test': 'Test',
                'field.single_line': 'failure'},
            **extra)
        view = TestFormView({}, request)
        view.initialize()
        self.assertEqual(
                {"error_summary": "There is 1 error.",
                 "errors": {},
                 "form_wide_errors": ["An action error"]},
            simplejson.loads(view.form_result))
