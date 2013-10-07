# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Widgets related to IProjectGroup."""

__metaclass__ = type

from textwrap import dedent

from zope.formlib.interfaces import (
    ConversionError,
    IInputWidget,
    InputErrors,
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
from lp.services.webapp.interfaces import IAlwaysSubmittedWidget


class ProjectScopeWidget(BrowserWidget, InputWidget):
    """Widget for selecting a scope. Either 'All projects' or only one."""

    implements(IAlwaysSubmittedWidget, IInputWidget)

    default_option = "all"
    _error = None

    def __init__(self, field, vocabulary, request):
        super(ProjectScopeWidget, self).__init__(field, request)

        # We copy the title, description and vocabulary from the main
        # field since it determines the valid target types.
        # XXX flacoste 2007-02-21 bug=86861: We must
        # use field.vocabularyName instead of the vocabulary parameter
        # otherwise VocabularyPickerWidget will fail.
        target_field = Choice(
            __name__='target', title=field.title,
            description=field.description, vocabulary=field.vocabularyName,
            required=True)
        setUpWidget(
            self, target_field.__name__, target_field, IInputWidget,
            prefix=self.name)
        self.setUpOptions()

    def setUpOptions(self):
        """Set up options to be rendered."""
        self.options = {}
        for option in ['all', 'project']:
            attributes = dict(
                type='radio', name=self.name, value=option,
                id='%s.option.%s' % (self.name, option))
            if self.request.form_ng.getOne(
                     self.name, self.default_option) == option:
                attributes['checked'] = 'checked'
            if option == 'project':
                attributes['onclick'] = (
                    "document.getElementById('field.scope.target').focus();")
            self.options[option] = renderElement('input', **attributes)
        self.target_widget.onKeyPress = (
            "selectWidget('%s.option.project', event)" % self.name)

    def hasInput(self):
        """See zope.formlib.interfaces.IInputWidget."""
        return self.name in self.request.form

    def hasValidInput(self):
        """See zope.formlib.interfaces.IInputWidget."""
        try:
            self.getInputValue()
            return self.hasInput()
        except (InputErrors, UnexpectedFormData, LaunchpadValidationError):
            return False

    def getInputValue(self):
        """See zope.formlib.interfaces.IInputWidget."""
        scope = self.request.form_ng.getOne(self.name)
        if scope == 'all':
            return None
        elif scope == 'project':
            if not self.request.form_ng.getOne(self.target_widget.name):
                self._error = WidgetInputError(
                    self.name, self.label,
                    LaunchpadValidationError('Please enter a project name'))
                raise self._error
            try:
                return self.target_widget.getInputValue()
            except ConversionError:
                entered_name = self.request.form_ng.getOne(
                     "%s.target" % self.name)
                self._error = WidgetInputError(
                    self.name, self.label,
                    LaunchpadValidationError(
                        "There is no project named '%s' registered in"
                        " Launchpad" % entered_name))
                raise self._error
        elif self.required:
            raise UnexpectedFormData("No valid option was selected.")
        else:
            return None

    def getScope(self):
        """Return the selected scope or None if it isn't selected."""
        return self.request.form_ng.getOne(self.name)

    def setRenderedValue(self, value):
        """See IWidget."""
        if value is None:
            self.default_option = 'all'
            self.target_widget.setRenderedValue(None)
        else:
            self.default_option = 'project'
            self.target_widget.setRenderedValue(value)
        self.setUpOptions()

    def __call__(self):
        """See zope.formlib.interfaces.IBrowserWidget."""
        return "\n".join([
            self.renderScopeOptions(),
            self.target_widget()])

    def renderScopeOptions(self):
        """Render the HTML for the scope radio widgets."""
        return dedent('''\
        <label>
          %(all)s All projects
        </label>
        <label>
          %(project)s One project:
        </label>
        ''' % self.options)

    def error(self):
        """See zope.formlib.interfaces.IBrowserWidget"""
        if self._error:
            return self._error.doc()
        else:
            return u""
