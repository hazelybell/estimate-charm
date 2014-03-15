# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'BranchTargetWidget',
    ]

from z3c.ptcompat import ViewPageTemplateFile
from zope.formlib.interfaces import (
    ConversionError,
    IInputWidget,
    InputErrors,
    MissingInputError,
    WidgetInputError,
    )
from zope.formlib.utility import setUpWidget
from zope.formlib.widget import (
    BrowserWidget,
    InputWidget,
    renderElement,
    )
from zope.interface import implements
from zope.schema import Choice

from lp.app.errors import UnexpectedFormData
from lp.app.validators import LaunchpadValidationError
from lp.code.interfaces.branchtarget import IBranchTarget
from lp.registry.interfaces.person import IPerson
from lp.registry.interfaces.product import IProduct
from lp.services.webapp.interfaces import (
    IAlwaysSubmittedWidget,
    IMultiLineWidgetLayout,
    )


class BranchTargetWidget(BrowserWidget, InputWidget):
    """Widget for selecting a personal (+junk) or product branch target."""

    implements(IAlwaysSubmittedWidget, IMultiLineWidgetLayout, IInputWidget)

    template = ViewPageTemplateFile('templates/branch-target.pt')
    default_option = "product"
    _widgets_set_up = False

    def setUpSubWidgets(self):
        if self._widgets_set_up:
            return
        fields = [
            Choice(
                __name__='product', title=u'Project',
                required=True, vocabulary='Product'),
            ]
        for field in fields:
            setUpWidget(
                self, field.__name__, field, IInputWidget, prefix=self.name)
        self._widgets_set_up = True

    def setUpOptions(self):
        """Set up options to be rendered."""
        self.options = {}
        for option in ['personal', 'product']:
            attributes = dict(
                type='radio', name=self.name, value=option,
                id='%s.option.%s' % (self.name, option))
            if self.request.form_ng.getOne(
                     self.name, self.default_option) == option:
                attributes['checked'] = 'checked'
            self.options[option] = renderElement('input', **attributes)
        self.product_widget.onKeyPress = (
            "selectWidget('%s.option.product', event)" % self.name)

    def hasInput(self):
        return self.name in self.request.form

    def hasValidInput(self):
        """See zope.formlib.interfaces.IInputWidget."""
        try:
            self.getInputValue()
            return True
        except (InputErrors, UnexpectedFormData):
            return False

    def getInputValue(self):
        """See zope.formlib.interfaces.IInputWidget."""
        self.setUpSubWidgets()
        form_value = self.request.form_ng.getOne(self.name)
        if form_value == 'product':
            try:
                return self.product_widget.getInputValue()
            except MissingInputError:
                raise WidgetInputError(
                    self.name, self.label,
                    LaunchpadValidationError('Please enter a project name'))
            except ConversionError:
                entered_name = self.request.form_ng.getOne(
                    "%s.product" % self.name)
                raise WidgetInputError(
                    self.name, self.label,
                    LaunchpadValidationError(
                        "There is no project named '%s' registered in"
                        " Launchpad" % entered_name))
        elif form_value == 'personal':
            return '+junk'
        else:
            raise UnexpectedFormData("No valid option was selected.")

    def setRenderedValue(self, value):
        """See IWidget."""
        self.setUpSubWidgets()
        if IBranchTarget.providedBy(value):
            if IProduct.providedBy(value.context):
                self.default_option = 'product'
                self.product_widget.setRenderedValue(value.context)
                return
            elif IPerson.providedBy(value.context):
                self.default_option = 'personal'
                return
        else:
            raise AssertionError('Not a valid value: %r' % value)

    def error(self):
        """See zope.formlib.interfaces.IBrowserWidget."""
        try:
            if self.hasInput():
                self.getInputValue()
        except InputErrors as error:
            self._error = error
        return super(BranchTargetWidget, self).error()

    def __call__(self):
        """See zope.formlib.interfaces.IBrowserWidget."""
        self.setUpSubWidgets()
        self.setUpOptions()
        return self.template()
