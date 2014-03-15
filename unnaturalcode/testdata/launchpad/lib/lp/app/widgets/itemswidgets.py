# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Widgets dealing with a choice of options."""

__metaclass__ = type

__all__ = [
    'CheckBoxMatrixWidget',
    'LabeledMultiCheckBoxWidget',
    'LaunchpadBooleanRadioWidget',
    'LaunchpadDropdownWidget',
    'LaunchpadRadioWidget',
    'LaunchpadRadioWidgetWithDescription',
    'PlainMultiCheckBoxWidget',
    ]

import math

from lazr.enum import IEnumeratedType
from zope.formlib.itemswidgets import (
    DropdownWidget,
    RadioWidget,
    )
from zope.formlib.widget import renderElement
from zope.formlib.widgets import MultiCheckBoxWidget
from zope.schema.interfaces import IChoice
from zope.schema.vocabulary import SimpleVocabulary

from lp.services.webapp.escaping import html_escape


class LaunchpadDropdownWidget(DropdownWidget):
    """A Choice widget that doesn't encloses itself in <div> tags."""

    def _div(self, cssClass, contents, **kw):
        return contents


class PlainMultiCheckBoxWidget(MultiCheckBoxWidget):
    """MultiCheckBoxWidget that copes with CustomWidgetFacotry."""

    _joinButtonToMessageTemplate = u'%s&nbsp;%s '

    def __init__(self, field, vocabulary, request):
        # XXX flacoste 2006-07-23 Workaround Zope3 bug #545:
        # CustomWidgetFactory passes wrong arguments to a MultiCheckBoxWidget
        if IChoice.providedBy(vocabulary):
            vocabulary = vocabulary.vocabulary
        MultiCheckBoxWidget.__init__(self, field, vocabulary, request)

    def _renderItem(self, index, text, value, name, cssClass, checked=False):
        """Render a checkbox and text without without label."""
        kw = {}
        if checked:
            kw['checked'] = 'checked'
        value = html_escape(value)
        text = html_escape(text)
        id = '%s.%s' % (name, index)
        element = renderElement(
            u'input', value=value, name=name, id=id,
            cssClass=cssClass, type='checkbox', **kw)
        return self._joinButtonToMessageTemplate % (element, text)


class LabeledMultiCheckBoxWidget(PlainMultiCheckBoxWidget):
    """MultiCheckBoxWidget which wraps option labels with proper
    <label> elements.
    """

    _joinButtonToMessageTemplate = (
        u'<label for="%s" style="font-weight: normal">%s&nbsp;%s</label> ')

    def _renderItem(self, index, text, value, name, cssClass, checked=False):
        """Render a checkbox and text in a label with a style attribute."""
        kw = {}
        if checked:
            kw['checked'] = 'checked'
        value = html_escape(value)
        text = html_escape(text)
        id = '%s.%s' % (name, index)
        elem = renderElement(u'input',
                             value=value,
                             name=name,
                             id=id,
                             cssClass=cssClass,
                             type='checkbox',
                             **kw)
        option_id = '%s.%s' % (self.name, index)
        return self._joinButtonToMessageTemplate % (option_id, elem, text)


# XXX Brad Bollenbach 2006-08-10 bugs=56062: This is a hack to
# workaround Zope's RadioWidget not properly selecting the default value.
class LaunchpadRadioWidget(RadioWidget):
    """A widget to work around a bug in RadioWidget."""

    def _renderItem(self, index, text, value, name, cssClass, checked=False):
        # This is an almost-complete copy of the method in Zope.  We need it
        # to inject the style in the label, and we omit the "for" in the label
        # because it is redundant (and not used in legacy tests).
        kw = {}
        if checked:
            kw['checked'] = 'checked'
        value = html_escape(value)
        text = html_escape(text)
        id = '%s.%s' % (name, index)
        elem = renderElement(u'input',
                             value=value,
                             name=name,
                             id=id,
                             cssClass=cssClass,
                             type='radio',
                             **kw)
        if '<label' in text:
            return '%s&nbsp;%s' % (elem, text)
        else:
            return renderElement(u'label',
                                 contents='%s&nbsp;%s' % (elem, text),
                                 **{'style': 'font-weight: normal'})

    def _div(self, cssClass, contents, **kw):
        return contents


class LaunchpadRadioWidgetWithDescription(LaunchpadRadioWidget):
    """Display the enumerated type description after the label.

    If the value of the vocabulary terms have a description this
    is shown as text on a line under the label.
    """

    _labelWithDescriptionTemplate = (
        u'''<tr>
              <td rowspan="2">%s</td>
              <td><label for="%s">%s</label></td>
            </tr>
            <tr>
              <td class="formHelp">%s</td>
            </tr>
         ''')
    _labelWithoutDescriptionTemplate = (
        u'''<tr>
              <td>%s</td>
              <td><label for="%s">%s</label></td>
            </tr>
         ''')

    def __init__(self, field, vocabulary, request):
        """Initialize the widget."""
        assert IEnumeratedType.providedBy(vocabulary), (
            'The vocabulary must implement IEnumeratedType')
        super(LaunchpadRadioWidgetWithDescription, self).__init__(
            field, vocabulary, request)
        self.extra_hint = None
        self.extra_hint_class = None

    def _renderRow(self, text, form_value, id, elem):
        """Render the table row for the widget depending on description."""
        if form_value != self._missing:
            vocab_term = self.vocabulary.getTermByToken(form_value)
            description = vocab_term.value.description
        else:
            description = None

        if description is None:
            return self._labelWithoutDescriptionTemplate % (elem, id, text)
        else:
            return self._labelWithDescriptionTemplate % (
                elem, id, text, html_escape(description))

    def renderItem(self, index, text, value, name, cssClass):
        """Render an item of the list."""
        text = html_escape(text)
        id = '%s.%s' % (name, index)
        elem = renderElement(u'input',
                             value=value,
                             name=name,
                             id=id,
                             cssClass=cssClass,
                             type='radio')
        return self._renderRow(text, value, id, elem)

    def renderSelectedItem(self, index, text, value, name, cssClass):
        """Render a selected item of the list."""
        text = html_escape(text)
        id = '%s.%s' % (name, index)
        elem = renderElement(u'input',
                             value=value,
                             name=name,
                             id=id,
                             cssClass=cssClass,
                             checked="checked",
                             type='radio')
        return self._renderRow(text, value, id, elem)

    def renderExtraHint(self):
        extra_hint_html = ''
        extra_hint_class = ''
        if self.extra_hint_class:
            extra_hint_class = ' class="%s"' % self.extra_hint_class
        if self.extra_hint:
            extra_hint_html = ('<div%s>%s</div>'
                % (extra_hint_class, html_escape(self.extra_hint)))
        return extra_hint_html

    def renderValue(self, value):
        # Render the items in a table to align the descriptions.
        rendered_items = self.renderItems(value)
        extra_hint = self.renderExtraHint()
        return (
            '%(extra_hint)s\n'
            '<table class="radio-button-widget">%(items)s</table>'
            % {'extra_hint': extra_hint,
               'items': ''.join(rendered_items)})


class LaunchpadBooleanRadioWidget(LaunchpadRadioWidget):
    """Render a Bool field as radio widget.

    The `LaunchpadRadioWidget` does the rendering. Only the True-False values
    are rendered; a missing value item is not rendered. The default labels
    are rendered as 'yes' and 'no', but can be changed by setting the widget's
    true_label and false_label attributes.
    """

    TRUE = 'yes'
    FALSE = 'no'

    def __init__(self, field, request):
        """Initialize the widget."""
        vocabulary = SimpleVocabulary.fromItems(
            ((self.TRUE, True), (self.FALSE, False)))
        super(LaunchpadBooleanRadioWidget, self).__init__(
            field, vocabulary, request)
        # Suppress the missing value behaviour; this is a boolean field.
        self.required = True
        self._displayItemForMissingValue = False
        # Set the default labels for true and false values.
        self.true_label = 'yes'
        self.false_label = 'no'

    def _renderItem(self, index, text, value, name, cssClass, checked=False):
        """Render the item with the preferred true and false labels."""
        if value == self.TRUE:
            text = self.true_label
        else:
            # value == self.FALSE.
            text = self.false_label
        return super(LaunchpadBooleanRadioWidget, self)._renderItem(
            index, text, value, name, cssClass, checked=checked)


class CheckBoxMatrixWidget(LabeledMultiCheckBoxWidget):
    """A CheckBox widget which organizes the inputs in a grid.

    The column_count attribute can be set in the view to change
    the number of columns in the matrix.
    """

    column_count = 1

    def renderValue(self, value):
        """Render the checkboxes inside a <table>."""
        rendered_items = self.renderItems(value)
        html = ['<table>']
        if self.orientation == 'horizontal':
            for i in range(0, len(rendered_items), self.column_count):
                html.append('<tr>')
                for j in range(0, self.column_count):
                    index = i + j
                    if index >= len(rendered_items):
                        break
                    html.append('<td>%s</td>' % rendered_items[index])
                html.append('</tr>')
        else:
            row_count = int(math.ceil(
                len(rendered_items) / float(self.column_count)))
            for i in range(0, row_count):
                html.append('<tr>')
                for j in range(0, self.column_count):
                    index = i + (j * row_count)
                    if index >= len(rendered_items):
                        break
                    html.append('<td>%s</td>' % rendered_items[index])
                html.append('</tr>')

        html.append('</table>')
        return '\n'.join(html)
