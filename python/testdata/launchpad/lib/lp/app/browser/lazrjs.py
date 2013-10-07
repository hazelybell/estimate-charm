# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Wrappers for lazr-js widgets."""

__metaclass__ = type
__all__ = [
    'BooleanChoiceWidget',
    'EnumChoiceWidget',
    'InlineEditPickerWidget',
    'InlinePersonEditPickerWidget',
    'InlineMultiCheckboxWidget',
    'standard_text_html_representation',
    'TextAreaEditorWidget',
    'TextLineEditorWidget',
    'vocabulary_to_choice_edit_items',
    ]

from lazr.enum import IEnumeratedType
from lazr.restful.declarations import LAZR_WEBSERVICE_EXPORTED
from lazr.restful.utils import (
    get_current_browser_request,
    safe_hasattr,
    )
import simplejson
from z3c.ptcompat import ViewPageTemplateFile
from zope.component import getUtility
from zope.schema.interfaces import (
    ICollection,
    IVocabulary,
    )
from zope.schema.vocabulary import getVocabularyRegistry
from zope.security.checker import (
    canAccess,
    canWrite,
    )

from lp.app.browser.stringformatter import FormattersAPI
from lp.app.browser.vocabulary import (
    get_person_picker_entry_metadata,
    vocabulary_filters,
    )
from lp.services.propertycache import cachedproperty
from lp.services.webapp.interfaces import ILaunchBag
from lp.services.webapp.publisher import canonical_url
from lp.services.webapp.vocabulary import IHugeVocabulary


class WidgetBase:
    """Useful methods for all widgets."""

    def __init__(self, context, exported_field, content_box_id,
                 edit_view, edit_url, edit_title):
        self.context = context
        self.exported_field = exported_field

        self.request = get_current_browser_request()
        self.attribute_name = exported_field.__name__
        self.optional_field = not exported_field.required

        if content_box_id is None:
            content_box_id = "edit-%s" % self.attribute_name
        self.content_box_id = content_box_id

        if edit_url is None:
            edit_url = canonical_url(self.context, view_name=edit_view)
        self.edit_url = edit_url
        if edit_title is None:
            edit_title = ''
        self.edit_title = edit_title

        # The mutator method name is used to determine whether or not the
        # current user has permission to alter the attribute if the attribute
        # is using a mutator function.
        self.mutator_method_name = None
        ws_stack = exported_field.queryTaggedValue(LAZR_WEBSERVICE_EXPORTED)
        if ws_stack is None:
            # The field may be a copy, or similarly named to one we care
            # about.
            self.api_attribute = self.attribute_name
        else:
            self.api_attribute = ws_stack['as']
            mutator_info = ws_stack.get('mutator_annotations')
            if mutator_info is not None:
                mutator_method, mutator_extra = mutator_info
                self.mutator_method_name = mutator_method.__name__
        self.json_attribute = simplejson.dumps(self.api_attribute)

    @property
    def resource_uri(self):
        """A local path to the context object.

        The javascript uses the normalize_uri method that adds the appropriate
        prefix to the uri.  Doing it this way avoids needing to adapt the
        current request into a webservice request in order to get an api url.
        """
        return canonical_url(self.context, force_local_path=True)

    @property
    def json_resource_uri(self):
        return simplejson.dumps(self.resource_uri)

    @property
    def can_write(self):
        """Can the current user write to the attribute."""
        if canWrite(self.context, self.attribute_name):
            return True
        elif self.mutator_method_name is not None:
            # The user may not have write access on the attribute itself, but
            # the REST API may have a mutator method configured, such as
            # transitionToAssignee.
            return canAccess(self.context, self.mutator_method_name)
        else:
            return False


class TextWidgetBase(WidgetBase):
    """Abstract base for the single and multiline text editor widgets."""

    def __init__(self, context, exported_field, title, content_box_id,
                 edit_view, edit_url, edit_title):
        super(TextWidgetBase, self).__init__(
            context, exported_field, content_box_id,
            edit_view, edit_url, edit_title)
        self.accept_empty = simplejson.dumps(self.optional_field)
        self.title = title
        self.widget_css_selector = simplejson.dumps('#' + self.content_box_id)

    @property
    def json_attribute_uri(self):
        return simplejson.dumps(self.resource_uri + '/' + self.api_attribute)


class DefinedTagMixin:
    """Mixin class to define open and closing tags."""

    @property
    def open_tag(self):
        if self.css_class:
            return '<%s id="%s" class="%s">' % (
                self.tag, self.content_box_id, self.css_class)
        else:
            return '<%s id="%s">' % (self.tag, self.content_box_id)

    @property
    def close_tag(self):
        return '</%s>' % self.tag


class TextLineEditorWidget(TextWidgetBase, DefinedTagMixin):
    """Wrapper for the lazr-js inlineedit/editor.js widget."""

    __call__ = ViewPageTemplateFile('../templates/text-line-editor.pt')

    def __init__(self, context, exported_field, title, tag, css_class=None,
                 content_box_id=None, edit_view="+edit", edit_url=None,
                 edit_title='', max_width=None, truncate_lines=0,
                 default_text=None, initial_value_override=None, width=None):
        """Create a widget wrapper.

        :param context: The object that is being edited.
        :param exported_field: The attribute being edited. This should be
            a field from an interface of the form ISomeInterface['fieldname']
        :param title: The string to use as the link title.
        :param tag: The HTML tag to use.
        :param css_class: The css class value to use.
        :param max_width: The maximum width of the rendered text before it is
            truncated with an '...'.
        :param truncate_lines: The maximum number of lines of text to display
            before any overflow is truncated with an '...'.
        :param content_box_id: The HTML id to use for this widget.
            Defaults to edit-<attribute name>.
        :param edit_view: The view name to use to generate the edit_url if
            one is not specified.
        :param edit_url: The URL to use for editing when the user isn't logged
            in and when JS is off.  Defaults to the edit_view on the context.
        :param edit_title: Used to set the title attribute of the anchor.
        :param default_text: Text to show in the unedited field, if the
            parameter value is missing or None.
        :param initial_value_override: Use this text for the initial edited
            field value instead of the attribute's current value.
        :param width: Initial widget width.
        """
        super(TextLineEditorWidget, self).__init__(
            context, exported_field, title, content_box_id,
            edit_view, edit_url, edit_title)
        self.tag = tag
        self.css_class = css_class
        self.max_width = max_width
        self.truncate_lines = truncate_lines
        self.default_text = default_text
        self.initial_value_override = simplejson.dumps(initial_value_override)
        self.width = simplejson.dumps(width)

    @property
    def value(self):
        text = getattr(self.context, self.attribute_name, self.default_text)
        if text is None:
            return self.default_text
        else:
            return FormattersAPI(text).obfuscate_email()

    @property
    def text_css_class(self):
        clazz = "yui3-editable_text-text"
        if self.truncate_lines and self.truncate_lines > 0:
            clazz += ' ellipsis'
            if self.truncate_lines == 1:
                clazz += ' single-line'
        return clazz

    @property
    def text_css_style(self):
        if self.max_width:
            return 'max-width: %s;' % self.max_width
        return ''


class TextAreaEditorWidget(TextWidgetBase):
    """Wrapper for the multine-line lazr-js inlineedit/editor.js widget."""

    __call__ = ViewPageTemplateFile('../templates/text-area-editor.pt')

    def __init__(self, context, exported_field, title, content_box_id=None,
                 edit_view="+edit", edit_url=None, edit_title='',
                 hide_empty=True, linkify_text=True):
        """Create the widget wrapper.

        :param context: The object that is being edited.
        :param exported_field: The attribute being edited. This should be
            a field from an interface of the form ISomeInterface['fieldname']
        :param title: The string to use as the link title.
        :param content_box_id: The HTML id to use for this widget.
            Defaults to edit-<attribute name>.
        :param edit_view: The view name to use to generate the edit_url if
            one is not specified.
        :param edit_url: The URL to use for editing when the user isn't logged
            in and when JS is off.  Defaults to the edit_view on the context.
        :param edit_title: Used to set the title attribute of the anchor.
        :param hide_empty: If the attribute has no value, or is empty, then
            hide the editor by adding the "hidden" CSS class.
        :param linkify_text: If True the HTML version of the text will have
            things that look like links made into anchors.
        """
        super(TextAreaEditorWidget, self).__init__(
            context, exported_field, title, content_box_id,
            edit_view, edit_url, edit_title)
        self.hide_empty = hide_empty
        self.linkify_text = linkify_text

    @property
    def tag_class(self):
        """The CSS class for the widget."""
        classes = ['lazr-multiline-edit']
        if self.hide_empty and not self.value:
            classes.append('hidden')
        return ' '.join(classes)

    @cachedproperty
    def value(self):
        text = getattr(self.context, self.attribute_name, None)
        return standard_text_html_representation(text, self.linkify_text)


class InlineEditPickerWidget(WidgetBase):
    """Wrapper for the lazr-js picker widget.

    This widget is not for editing form values like the
    VocabularyPickerWidget.
    """

    __call__ = ViewPageTemplateFile('../templates/inline-picker.pt')

    def __init__(self, context, exported_field, default_html,
                 content_box_id=None, header='Select an item',
                 step_title='Search',
                 null_display_value='None',
                 edit_view="+edit", edit_url=None, edit_title='',
                 help_link=None):
        """Create a widget wrapper.

        :param context: The object that is being edited.
        :param exported_field: The attribute being edited. This should be
            a field from an interface of the form ISomeInterface['fieldname']
        :param default_html: Default display of attribute.
        :param content_box_id: The HTML id to use for this widget.
            Automatically generated if this is not provided.
        :param header: The large text at the top of the picker.
        :param step_title: Smaller line of text below the header.
        :param null_display_value: This will be shown for a missing value
        :param edit_view: The view name to use to generate the edit_url if
            one is not specified.
        :param edit_url: The URL to use for editing when the user isn't logged
            in and when JS is off.  Defaults to the edit_view on the context.
        :param edit_title: Used to set the title attribute of the anchor.
        """
        super(InlineEditPickerWidget, self).__init__(
            context, exported_field, content_box_id,
            edit_view, edit_url, edit_title)
        self.default_html = default_html
        self.header = header
        self.step_title = step_title
        self.null_display_value = null_display_value
        self.help_link = help_link

        # JSON encoded attributes.
        self.json_content_box_id = simplejson.dumps(self.content_box_id)
        self.json_attribute = simplejson.dumps(self.api_attribute + '_link')
        self.json_vocabulary_name = simplejson.dumps(
            self.exported_field.vocabularyName)

    @property
    def picker_type(self):
        return 'default'

    @property
    def selected_value_metadata(self):
        return None

    @property
    def selected_value(self):
        """ String representation of field value associated with the picker.

        Default implementation is to return the 'name' attribute.
        """
        if self.context is None:
            return None
        val = getattr(self.context, self.exported_field.__name__)
        if val is not None and safe_hasattr(val, 'name'):
            return getattr(val, 'name')
        return None

    @property
    def config(self):
        return self.getConfig()

    def getConfig(self):
        return dict(
            picker_type=self.picker_type,
            header=self.header, step_title=self.step_title,
            selected_value=self.selected_value,
            selected_value_metadata=self.selected_value_metadata,
            null_display_value=self.null_display_value,
            show_search_box=self.show_search_box,
            vocabulary_filters=self.vocabulary_filters)

    @property
    def json_config(self):
        return simplejson.dumps(self.config)

    @cachedproperty
    def vocabulary(self):
        registry = getVocabularyRegistry()
        return registry.get(
            IVocabulary, self.exported_field.vocabularyName)

    @cachedproperty
    def vocabulary_filters(self):
        return vocabulary_filters(self.vocabulary)

    @property
    def show_search_box(self):
        return IHugeVocabulary.providedBy(self.vocabulary)


class InlinePersonEditPickerWidget(InlineEditPickerWidget):
    def __init__(self, context, exported_field, default_html,
                 content_box_id=None, header='Select an item',
                 step_title='Search', show_create_team=False,
                 assign_me_text='Pick me',
                 remove_person_text='Remove person',
                 remove_team_text='Remove team',
                 null_display_value='None',
                 edit_view="+edit", edit_url=None, edit_title='',
                 help_link=None):
        """Create a widget wrapper.

        :param context: The object that is being edited.
        :param exported_field: The attribute being edited. This should be
            a field from an interface of the form ISomeInterface['fieldname']
        :param default_html: Default display of attribute.
        :param content_box_id: The HTML id to use for this widget.
            Automatically generated if this is not provided.
        :param header: The large text at the top of the picker.
        :param step_title: Smaller line of text below the header.
        :param assign_me_text: Override default button text: "Pick me"
        :param remove_person_text: Override default link text: "Remove person"
        :param remove_team_text: Override default link text: "Remove team"
        :param null_display_value: This will be shown for a missing value
        :param edit_view: The view name to use to generate the edit_url if
            one is not specified.
        :param edit_url: The URL to use for editing when the user isn't logged
            in and when JS is off.  Defaults to the edit_view on the context.
        :param edit_title: Used to set the title attribute of the anchor.
        :param help_link: Used to set a link for help for the widget.
        """
        super(InlinePersonEditPickerWidget, self).__init__(
            context, exported_field, default_html, content_box_id, header,
            step_title, null_display_value,
            edit_view, edit_url, edit_title, help_link)

        self._show_create_team = show_create_team
        self.assign_me_text = assign_me_text
        self.remove_person_text = remove_person_text
        self.remove_team_text = remove_team_text

    @property
    def picker_type(self):
        return 'person'

    @property
    def selected_value_metadata(self):
        val = getattr(self.context, self.exported_field.__name__)
        return get_person_picker_entry_metadata(val)

    @property
    def show_assign_me_button(self):
        # show_assign_me_button is true if user is in the vocabulary.
        vocabulary = self.vocabulary
        user = getUtility(ILaunchBag).user
        return user and user in vocabulary

    @property
    def show_create_team(self):
        return self._show_create_team

    def getConfig(self):
        config = super(InlinePersonEditPickerWidget, self).getConfig()
        config.update(dict(
            show_remove_button=self.optional_field,
            show_assign_me_button=self.show_assign_me_button,
            show_create_team=self.show_create_team,
            assign_me_text=self.assign_me_text,
            remove_person_text=self.remove_person_text,
            remove_team_text=self.remove_team_text))
        return config


class InlineMultiCheckboxWidget(WidgetBase):
    """Wrapper for the lazr-js multicheckbox widget."""

    __call__ = ViewPageTemplateFile(
                        '../templates/inline-multicheckbox-widget.pt')

    def __init__(self, context, exported_field,
                 label, label_tag="span", attribute_type="default",
                 vocabulary=None, header=None,
                 empty_display_value="None", selected_items=list(),
                 items_tag="span", items_style='',
                 content_box_id=None, edit_view="+edit", edit_url=None,
                 edit_title=''):
        """Create a widget wrapper.

        :param context: The object that is being edited.
        :param exported_field: The attribute being edited. This should be
            a field from an interface of the form ISomeInterface['fieldname']
        :param label: The label text to display above the checkboxes
        :param label_tag: The tag in which to wrap the label text.
        :param attribute_type: The attribute type. Currently only "reference"
            is supported. Used to determine whether to linkify the selected
            checkbox item values. So ubuntu/hoary becomes
            http://launchpad.net/devel/api/ubuntu/hoary
        :param vocabulary: The name of the vocabulary which provides the
            items or a vocabulary instance.
        :param header: The text to display as the title of the popup form.
        :param empty_display_value: The text to display if no items are
            selected.
        :param selected_items: The currently selected items.
        :param items_tag: The tag in which to wrap the items checkboxes.
        :param items_style: The css style to use for each item checkbox.
        :param content_box_id: The HTML id to use for this widget.
            Automatically generated if this is not provided.
        :param edit_view: The view name to use to generate the edit_url if
            one is not specified.
        :param edit_url: The URL to use for editing when the user isn't logged
            in and when JS is off.  Defaults to the edit_view on the context.
        :param edit_title: Used to set the title attribute of the anchor.

        """
        super(InlineMultiCheckboxWidget, self).__init__(
            context, exported_field, content_box_id,
            edit_view, edit_url, edit_title)

        linkify_items = attribute_type == "reference"

        if header is None:
            header = self.exported_field.title + ":"
        self.header = header,
        self.empty_display_value = empty_display_value
        self.label = label
        self.label_open_tag = "<%s>" % label_tag
        self.label_close_tag = "</%s>" % label_tag
        self.items = selected_items
        self.items_open_tag = ("<%s id='%s'>" %
            (items_tag, self.content_box_id + "-items"))
        self.items_close_tag = "</%s>" % items_tag
        self.linkify_items = linkify_items

        if vocabulary is None:
            if ICollection.providedBy(exported_field):
                vocabulary = exported_field.value_type.vocabularyName
            else:
                vocabulary = exported_field.vocabularyName

        if isinstance(vocabulary, basestring):
            vocabulary = getVocabularyRegistry().get(context, vocabulary)

        # Construct checkbox data dict for each item in the vocabulary.
        items = []
        style = ';'.join(['font-weight: normal', items_style])
        for item in vocabulary:
            item_value = item.value if safe_hasattr(item, 'value') else item
            checked = item_value in selected_items
            if linkify_items:
                save_value = canonical_url(item_value, force_local_path=True)
            else:
                save_value = item_value.name
            new_item = {
                'name': item.title,
                'token': item.token,
                'style': style,
                'checked': checked,
                'value': save_value}
            items.append(new_item)
        self.has_choices = len(items)

        # JSON encoded attributes.
        self.json_content_box_id = simplejson.dumps(self.content_box_id)
        self.json_attribute = simplejson.dumps(self.api_attribute)
        self.json_attribute_type = simplejson.dumps(attribute_type)
        self.json_items = simplejson.dumps(items)
        self.json_description = simplejson.dumps(
            self.exported_field.description)

    @property
    def config(self):
        return dict(
            header=self.header,
            )

    @property
    def json_config(self):
        return simplejson.dumps(self.config)


def vocabulary_to_choice_edit_items(
    vocab, include_description=False, css_class_prefix=None,
    disabled_items=None, excluded_items=None,
    as_json=False, name_fn=None, value_fn=None, description_fn=None):
    """Convert an enumerable to JSON for a ChoiceEdit.

    :vocab: The enumeration to iterate over.
    :css_class_prefix: If present, append this to an item's value to create
        the css_class property for it.
    :disabled_items: A list of items that should be displayed, but disabled.
    :name_fn: A function receiving an item and returning its name.
    :value_fn: A function receiving an item and returning its value.
    """
    if disabled_items is None:
        disabled_items = []
    items = []
    for item in vocab:
        # Introspect to make sure we're dealing with the object itself.
        # SimpleTerm objects have the object itself at item.value.
        if safe_hasattr(item, 'value'):
            item = item.value
        if excluded_items and item in excluded_items:
            continue
        if name_fn is not None:
            name = name_fn(item)
        else:
            name = item.title
        if value_fn is not None:
            value = value_fn(item)
        else:
            value = item.title
        if description_fn is None:
            description_fn = lambda item: getattr(item, 'description', '')
        description = ''
        if include_description:
            description = description_fn(item)
        new_item = {
            'name': name,
            'value': value,
            'description': description,
            'description_css_class': 'choice-description',
            'style': '', 'help': '', 'disabled': False}
        for disabled_item in disabled_items:
            if disabled_item == item:
                new_item['disabled'] = True
                break
        if css_class_prefix is not None:
            new_item['css_class'] = css_class_prefix + item.name
        items.append(new_item)

    if as_json:
        return simplejson.dumps(items)
    else:
        return items


def standard_text_html_representation(value, linkify_text=True):
    """Render a string for html display.

    For this we obfuscate email and render as html.
    """
    if value is None:
        return ''
    nomail = FormattersAPI(value).obfuscate_email()
    return FormattersAPI(nomail).text_to_html(linkify_text=linkify_text)


class BooleanChoiceWidget(WidgetBase, DefinedTagMixin):
    """A ChoiceEdit for a boolean field."""

    __call__ = ViewPageTemplateFile('../templates/boolean-choice-widget.pt')

    def __init__(self, context, exported_field,
                 tag, false_text, true_text, css_class=None, prefix=None,
                 edit_view="+edit", edit_url=None, edit_title='',
                 content_box_id=None, header='Select an item'):
        """Create a widget wrapper.

        :param context: The object that is being edited.
        :param exported_field: The attribute being edited. This should be
            a field from an interface of the form ISomeInterface['fieldname']
        :param tag: The HTML tag to use.
        :param false_text: The string to show for a false value.
        :param true_text: The string to show for a true value.
        :param css_class: The css class value to use.
        :param prefix: Optional text to show before the value.
        :param edit_view: The view name to use to generate the edit_url if
            one is not specified.
        :param edit_url: The URL to use for editing when the user isn't logged
            in and when JS is off.  Defaults to the edit_view on the context.
        :param edit_title: Used to set the title attribute of the anchor.
        :param content_box_id: The HTML id to use for this widget.
            Automatically generated if this is not provided.
        :param header: The large text at the top of the choice popup.
        """
        super(BooleanChoiceWidget, self).__init__(
            context, exported_field, content_box_id,
            edit_view, edit_url, edit_title)
        self.header = header
        self.tag = tag
        self.css_class = css_class
        self.prefix = prefix
        self.true_text = true_text
        self.false_text = false_text
        self.current_value = getattr(self.context, self.attribute_name)

    @property
    def value(self):
        if self.current_value:
            return self.true_text
        else:
            return self.false_text

    @property
    def config(self):
        return dict(
            contentBox='#' + self.content_box_id,
            value=self.current_value,
            title=self.header,
            items=[
                dict(name=self.true_text, value=True, style='', help='',
                     disabled=False),
                dict(name=self.false_text, value=False, style='', help='',
                     disabled=False)])

    @property
    def json_config(self):
        return simplejson.dumps(self.config)


class EnumChoiceWidget(WidgetBase):
    """A popup choice widget."""

    __call__ = ViewPageTemplateFile('../templates/enum-choice-widget.pt')

    def __init__(self, context, exported_field, header,
                 content_box_id=None, enum=None,
                 edit_view="+edit", edit_url=None, edit_title='',
                 css_class_prefix='', include_description=False):
        """Create a widget wrapper.

        :param context: The object that is being edited.
        :param exported_field: The attribute being edited. This should be
            a field from an interface of the form ISomeInterface['fieldname']
        :param header: The large text at the top of the picker.
        :param content_box_id: The HTML id to use for this widget.
            Automatically generated if this is not provided.
        :param enum: The enumerated type used to generate the widget items.
        :param edit_view: The view name to use to generate the edit_url if
            one is not specified.
        :param edit_url: The URL to use for editing when the user isn't logged
            in and when JS is off.  Defaults to the edit_view on the context.
        :param edit_title: Used to set the title attribute of the anchor.
        :param css_class_prefix: Added to the start of the enum titles.
        """
        super(EnumChoiceWidget, self).__init__(
            context, exported_field, content_box_id,
            edit_view, edit_url, edit_title)
        self.header = header
        value = getattr(self.context, self.attribute_name)
        self.css_class = "value %s%s" % (css_class_prefix, value.name)
        self.value = value.title
        if enum is None:
            # Get the enum from the exported field.
            enum = exported_field.vocabulary
        if IEnumeratedType(enum, None) is None:
            raise ValueError('%r does not provide IEnumeratedType' % enum)
        self.items = vocabulary_to_choice_edit_items(
            enum, include_description=include_description,
            css_class_prefix=css_class_prefix)

    @property
    def config(self):
        return dict(
            contentBox='#' + self.content_box_id,
            value=self.value,
            title=self.header,
            items=self.items)

    @property
    def json_config(self):
        return simplejson.dumps(self.config)
