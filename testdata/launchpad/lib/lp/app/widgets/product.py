# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Widgets related to IProduct."""

__metaclass__ = type
__all__ = [
    'GhostCheckBoxWidget',
    'GhostWidget',
    'LicenseWidget',
    'ProductBugTrackerWidget',
    'ProductNameWidget',
    ]

import math

from lazr.restful.interface import copy_field
from z3c.ptcompat import ViewPageTemplateFile
from zope.component import getUtility
from zope.formlib.boolwidgets import CheckBoxWidget
from zope.formlib.interfaces import IInputWidget
from zope.formlib.textwidgets import TextWidget
from zope.formlib.utility import setUpWidget
from zope.formlib.widget import (
    CustomWidgetFactory,
    renderElement,
    )
from zope.schema import (
    Choice,
    Text,
    )

from lp.app.validators import LaunchpadValidationError
from lp.app.validators.email import email_validator
from lp.app.widgets.itemswidgets import (
    CheckBoxMatrixWidget,
    LaunchpadRadioWidget,
    )
from lp.app.widgets.popup import BugTrackerPickerWidget
from lp.app.widgets.textwidgets import (
    DescriptionWidget,
    StrippedTextWidget,
    URIComponentWidget,
    )
from lp.bugs.interfaces.bugtracker import (
    BugTrackerType,
    IBugTracker,
    IBugTrackerSet,
    )
from lp.registry.interfaces.product import IProduct
from lp.services.fields import StrippedTextLine
from lp.services.webapp import canonical_url
from lp.services.webapp.escaping import structured
from lp.services.webapp.interfaces import ILaunchBag
from lp.services.webapp.vhosts import allvhosts


class ProductBugTrackerWidget(LaunchpadRadioWidget):
    """Widget for selecting a product bug tracker."""

    _joinButtonToMessageTemplate = u'%s&nbsp;%s'
    template = ViewPageTemplateFile('templates/product-bug-tracker.pt')

    def __init__(self, field, vocabulary, request):
        LaunchpadRadioWidget.__init__(self, field, vocabulary, request)

        # Bug tracker widget.
        self.bugtracker = Choice(
            vocabulary="WebBugTracker",
            __name__='bugtracker')
        self.bugtracker_widget = CustomWidgetFactory(BugTrackerPickerWidget)
        setUpWidget(
            self, 'bugtracker', self.bugtracker, IInputWidget,
            prefix=self.name, value=field.context.bugtracker,
            context=field.context)
        self.bugtracker_widget.onKeyPress = (
            "selectWidget('%s.2', event);" % self.name)

        # Upstream email address field and widget.
        ## This is to make email address bug trackers appear
        ## separately from the main bug tracker list.
        self.upstream_email_address = StrippedTextLine(
            required=False, constraint=email_validator,
            __name__='upstream_email_address')
        self.upstream_email_address_widget = (
            CustomWidgetFactory(StrippedTextWidget))
        setUpWidget(
            self, 'upstream_email_address', self.upstream_email_address,
            IInputWidget, prefix=self.name, value='',
            context=self.upstream_email_address.context)
        ## Select the corresponding radio option automatically if
        ## the user starts typing.
        if self.upstream_email_address_widget.extra is None:
            self.upstream_email_address_widget.extra = ''
        self.upstream_email_address_widget.extra += (
            ''' onkeypress="selectWidget('%s.3', event);"\n''' % self.name)

    def _renderItem(self, index, text, value, name, cssClass, checked=False):
        # This form has a custom need to render their labels separately,
        # because of a Firefox problem: see comment in renderItems.
        kw = {}
        if checked:
            kw['checked'] = 'checked'
        id = '%s.%s' % (name, index)
        elem = renderElement(u'input',
                             value=value,
                             name=name,
                             id=id,
                             cssClass=cssClass,
                             type='radio',
                             **kw)
        return '%s&nbsp;%s' % (elem, text)

    def _toFieldValue(self, form_value):
        if form_value == "malone":
            return self.context.malone_marker
        elif form_value == "external":
            return self.bugtracker_widget.getInputValue()
        elif form_value == "external-email":
            email_address = self.upstream_email_address_widget.getInputValue()
            if email_address is None or len(email_address) == 0:
                self.upstream_email_address_widget._error = (
                    LaunchpadValidationError(
                        'Please enter an email address.'))
                raise self.upstream_email_address_widget._error
            bugtracker = getUtility(IBugTrackerSet).ensureBugTracker(
                'mailto:%s' % email_address, getUtility(ILaunchBag).user,
                BugTrackerType.EMAILADDRESS)
            return bugtracker
        elif form_value == "project":
            return None

    def getInputValue(self):
        return self._toFieldValue(self._getFormInput())

    def setRenderedValue(self, value):
        self._data = value
        if value is not self.context.malone_marker:
            self.bugtracker_widget.setRenderedValue(value)

    def _renderLabel(self, text, index):
        """Render a label for the option with the specified index."""
        option_id = '%s.%s' % (self.name, index)
        return u'<label for="%s" style="font-weight: normal">%s</label>' % (
            option_id, text)

    def error(self):
        """Concatenate errors from this widget and sub-widgets."""
        errors = [super(ProductBugTrackerWidget, self).error(),
                  self.upstream_email_address_widget.error()]
        return '; '.join(err for err in errors if len(err) > 0)

    def renderItems(self, value):
        """Custom-render the radio-buttons and dependent widgets.

        Some of the radio options have dependent widgets: the bug
        tracker drop-down box, and the email address text field. To
        render these in the correct place we must override the default
        rendering of `LaunchpadRadioWidget`.

        We must also make sure that these dependent widgets are
        populated with the correct information, specifically the bug
        tracker selected, or the email address where bugs must be
        reported.
        """
        field = self.context
        product = field.context
        if value == self._missing:
            value = field.missing_value

        # Bugs tracked in Launchpad Bugs.
        malone_item_arguments = dict(
            index=0, text=self._renderLabel("In Launchpad", 0),
            value="malone", name=self.name, cssClass=self.cssClass)

        # Project or somewhere else.
        project = product.project
        if project is None or project.bugtracker is None:
            project_bugtracker_caption = "Somewhere else"
        else:
            project_bugtracker_caption = structured(
                'In the %s bug tracker (<a href="%s">%s</a>)</label>',
                project.displayname, canonical_url(project.bugtracker),
                project.bugtracker.title).escapedtext
        project_bugtracker_arguments = dict(
            index=1, text=self._renderLabel(project_bugtracker_caption, 1),
            value="project", name=self.name, cssClass=self.cssClass)

        # External bug tracker.
        ## The bugtracker widget can't be within the <label> tag,
        ## since Firefox doesn't cope with it well.
        external_bugtracker_text = "%s %s" % (
            self._renderLabel("In a registered bug tracker:", 2),
            self.bugtracker_widget())
        external_bugtracker_arguments = dict(
            index=2, text=external_bugtracker_text,
            value="external", name=self.name, cssClass=self.cssClass)

        # Upstream email address (special-case bug tracker).
        if (IBugTracker.providedBy(value) and
            value.bugtrackertype == BugTrackerType.EMAILADDRESS):
            self.upstream_email_address_widget.setRenderedValue(
                value.baseurl.lstrip('mailto:'))
        external_bugtracker_email_text = "%s %s" % (
            self._renderLabel("By emailing an upstream bug contact:\n", 3),
            self.upstream_email_address_widget())
        external_bugtracker_email_arguments = dict(
            index=3, text=external_bugtracker_email_text,
            value="external-email", name=self.name, cssClass=self.cssClass)

        # All the choices arguments in order.
        all_arguments = {
            'launchpad': malone_item_arguments,
            'external_bugtracker': external_bugtracker_arguments,
            'external_email': external_bugtracker_email_arguments,
            'unknown': project_bugtracker_arguments,
            }

        # Figure out the selected choice.
        if value == field.malone_marker:
            selected = malone_item_arguments
        elif value != self.context.missing_value:
            # value will be 'external-email' if there was an error on
            # upstream_email_address_widget.
            if (value == 'external-email' or (
                    IBugTracker.providedBy(value) and
                    value.bugtrackertype == BugTrackerType.EMAILADDRESS)):
                selected = external_bugtracker_email_arguments
            else:
                selected = external_bugtracker_arguments
        else:
            selected = project_bugtracker_arguments

        # Render.
        for name, arguments in all_arguments.items():
            if arguments is selected:
                render = self.renderSelectedItem
            else:
                render = self.renderItem
            yield (name, render(**arguments))

    def renderValue(self, value):
        # Render the items with subordinate fields and support markup.
        self.bug_trackers = dict(self.renderItems(value))
        self.product = self.context.context
        # The view must also use GhostWidget for the 'remote_product' field.
        self.remote_product = copy_field(IProduct['remote_product'])
        self.remote_product_widget = CustomWidgetFactory(TextWidget)
        setUpWidget(
            self, 'remote_product', self.remote_product, IInputWidget,
            prefix='field', value=self.product.remote_product,
            context=self.product)
        # The view must also use GhostWidget for the 'enable_bug_expiration'
        # field.
        self.enable_bug_expiration = copy_field(
            IProduct['enable_bug_expiration'])
        self.enable_bug_expiration_widget = CustomWidgetFactory(
            CheckBoxWidget)
        setUpWidget(
            self, 'enable_bug_expiration', self.enable_bug_expiration,
            IInputWidget, prefix='field',
            value=self.product.enable_bug_expiration, context=self.product)
        return self.template()


class LicenseWidget(CheckBoxMatrixWidget):
    """A CheckBox widget with a custom template.

    The allow_pending_license is provided so that $product/+edit
    can display radio buttons to show that the licence field is
    optional for pre-existing products that have never had a licence set.
    """
    template = ViewPageTemplateFile('templates/license.pt')
    allow_pending_license = False

    CATEGORIES = {
        'AFFERO': 'recommended',
        'APACHE': 'recommended',
        'BSD': 'recommended',
        'GNU_GPL_V2': 'recommended',
        'GNU_GPL_V3': 'recommended',
        'GNU_LGPL_V2_1': 'recommended',
        'GNU_LGPL_V3': 'recommended',
        'MIT': 'recommended',
        'CC_0': 'recommended',
        'ACADEMIC': 'more',
        'ARTISTIC': 'more',
        'ARTISTIC_2_0': 'more',
        'COMMON_PUBLIC': 'more',
        'ECLIPSE': 'more',
        'EDUCATIONAL_COMMUNITY': 'more',
        'GNU_FDL_NO_OPTIONS': 'more',
        'MPL': 'more',
        'OFL': 'more',
        'OPEN_SOFTWARE': 'more',
        'PHP': 'more',
        'PUBLIC_DOMAIN': 'more',
        'PYTHON': 'more',
        'ZPL': 'more',
        'CC_BY': 'more',
        'CC_BY_SA': 'more',
        'PERL': 'deprecated',
        'OTHER_PROPRIETARY': 'special',
        'OTHER_OPEN_SOURCE': 'special',
        'DONT_KNOW': 'special',
        }

    items_by_category = None

    def __init__(self, field, vocabulary, request):
        super(LicenseWidget, self).__init__(field, vocabulary, request)
        # We want to put the license_info widget inside the licences widget's
        # HTML, for better alignment and JavaScript dynamism.  This is
        # accomplished by ghosting the form's license_info widget (see
        # lp/registry/browser/product.py and the GhostWidget implementation
        # below) and creating a custom widget here.  It's a pretty simple text
        # widget so create that now.  The fun part is that it's all within the
        # same form, so posts work correctly.
        self.license_info = Text(__name__='license_info')
        self.license_info_widget = CustomWidgetFactory(DescriptionWidget)
        # The initial value of the license_info widget will be taken from the
        # field's context when available.  This will be the IProduct when
        # we're editing an existing project, but when we're creating a new
        # one, it'll be an IProductSet, which does not have license_info.
        initial_value = getattr(field.context, 'license_info', None)
        setUpWidget(
            self, 'license_info', self.license_info, IInputWidget,
            prefix='field', value=initial_value,
            context=field.context)
        self.source_package_release = None
        # These will get filled in by _categorize().  They are the number of
        # selected licences in the category.  The actual count doesn't matter,
        # since if it's greater than 0 it will start opened.  Note that we
        # always want the recommended licences to be opened, so we initialize
        # its value to 1.
        self.recommended_count = 1
        self.more_count = 0
        self.deprecated_count = 0
        self.special_count = 0

    def textForValue(self, term):
        """See `ItemsWidgetBase`."""
        # This will return just the DBItem's text.  We want to wrap that text
        # in the URL to the licence, which is stored in the DBItem's
        # description.
        value = super(LicenseWidget, self).textForValue(term)
        if term.value.url is None:
            return value
        else:
            return structured(
                '%s&nbsp;<a href="%s" class="sprite external-link action-icon"'
                '>view licence</a>'
                % (value, term.value.url))

    def renderItem(self, index, text, value, name, cssClass):
        """See `ItemsEditWidgetBase`."""
        rendered = super(LicenseWidget, self).renderItem(
            index, text, value, name, cssClass)
        self._categorize(value, rendered)
        return rendered

    def renderSelectedItem(self, index, text, value, name, cssClass):
        """See `ItemsEditWidgetBase`."""
        rendered = super(LicenseWidget, self).renderSelectedItem(
            index, text, value, name, cssClass)
        category = self._categorize(value, rendered)
        # Increment the category counter.  This is used by the template to
        # determine whether a category should start opened or not.
        attribute_name = category + '_count'
        setattr(self, attribute_name, getattr(self, attribute_name) + 1)
        return rendered

    def _categorize(self, value, rendered):
        # Place the value in the proper category.
        if self.items_by_category is None:
            self.items_by_category = {}
        # When allow_pending_license is set, we'll see a radio button labeled
        # "I haven't specified the licence yet".  In that case, do not show
        # the "I don't know" option.
        if self.allow_pending_license and value == 'DONT_KNOW':
            return
        category = self.CATEGORIES.get(value)
        assert category is not None, 'Uncategorized value: %s' % value
        self.items_by_category.setdefault(category, []).append(rendered)
        return category

    def __call__(self):
        # Trigger textForValue() which does the categorization of the
        # individual checkbox items.  We don't actually care about the return
        # value though since we'll be building up our checkbox tables
        # manually.
        super(LicenseWidget, self).__call__()
        self.recommended = self._renderTable('recommended', 3)
        self.more = self._renderTable('more', 3)
        self.deprecated = self._renderTable('deprecated')
        self.special = self._renderTable('special')
        return self.template()

    def _renderTable(self, category, column_count=1):
        # The tables are wrapped in divs, since IE8 does not respond
        # to setting the table's height to zero.
        attribute_name = category + '_count'
        attr_count = getattr(self, attribute_name)
        klass = 'expanded' if attr_count > 0 else ''
        html = [
            '<div id="%s" class="hide-on-load %s"><table>' % (category, klass)]
        rendered_items = self.items_by_category[category]
        row_count = int(math.ceil(len(rendered_items) / float(column_count)))
        for i in range(0, row_count):
            html.append('<tr>')
            for j in range(0, column_count):
                index = i + (j * row_count)
                if index >= len(rendered_items):
                    break
                html.append('<td>%s</td>' % rendered_items[index])
            html.append('</tr>')
        html.append('</table></div>')
        return '\n'.join(html)


class ProductNameWidget(URIComponentWidget):
    """A text input widget that looks like a url path component entry.

    URL: http://launchpad.net/[____________]
    """

    @property
    def base_url(self):
        return allvhosts.configs['mainsite'].rooturl


class GhostMixin:
    """A simple widget that has no HTML."""
    visible = False
    # This suppresses the stuff above the widget.
    display_label = False
    # This suppresses the stuff underneath the widget.
    hint = ''

    # This suppresses all of the widget's HTML.
    def __call__(self):
        """See `SimpleInputWidget`."""
        return ''

    hidden = __call__


class GhostWidget(GhostMixin, TextWidget):
    """Suppress the rendering of Text input fields."""


class GhostCheckBoxWidget(GhostMixin, CheckBoxWidget):
    """Suppress the rendering of Bool input fields."""
