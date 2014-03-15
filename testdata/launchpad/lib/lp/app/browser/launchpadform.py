# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Launchpad Form View Classes
"""

__metaclass__ = type

__all__ = [
    'action',
    'custom_widget',
    'has_structured_doc',
    'LaunchpadEditFormView',
    'LaunchpadFormView',
    'render_radio_widget_part',
    'ReturnToReferrerMixin',
    'safe_action',
    ]

from lazr.lifecycle.event import ObjectModifiedEvent
from lazr.lifecycle.snapshot import Snapshot
import simplejson
import transaction
from zope.event import notify
from zope.formlib import form
# imported so it may be exported
from zope.formlib.form import action
from zope.formlib.interfaces import IInputWidget
from zope.formlib.widget import CustomWidgetFactory
from zope.formlib.widgets import (
    CheckBoxWidget,
    DropdownWidget,
    RadioWidget,
    TextAreaWidget,
    )
from zope.interface import (
    classImplements,
    implements,
    providedBy,
    )
from zope.interface.advice import addClassAdvisor
from zope.traversing.interfaces import (
    ITraversable,
    TraversalError,
    )

from lp.services.webapp.escaping import html_escape
from lp.services.webapp.interfaces import (
    IAlwaysSubmittedWidget,
    ICheckBoxWidgetLayout,
    IMultiLineWidgetLayout,
    INotificationResponse,
    UnsafeFormGetSubmissionError,
    )
from lp.services.webapp.publisher import (
    canonical_url,
    LaunchpadView,
    )


classImplements(CheckBoxWidget, ICheckBoxWidgetLayout)
classImplements(DropdownWidget, IAlwaysSubmittedWidget)
classImplements(RadioWidget, IAlwaysSubmittedWidget)
classImplements(TextAreaWidget, IMultiLineWidgetLayout)


# marker to represent "focus the first widget in the form"
_first_widget_marker = object()


class LaunchpadFormView(LaunchpadView):

    # The prefix used for all form inputs.
    prefix = 'field'

    # The form schema
    schema = None
    # Subset of fields to use
    field_names = None
    # Dictionary mapping field names to custom widgets
    custom_widgets = ()

    # The next URL to redirect to on successful form submission
    next_url = None
    # The cancel URL is rendered as a Cancel link in the form
    # macro if set in a derived class.
    cancel_url = None

    # The name of the widget that will receive initial focus in the form.
    # By default, the first widget will receive focus.  Set this to None
    # to disable setting of initial focus.
    initial_focus_widget = _first_widget_marker

    label = ''

    actions = ()

    action_taken = None

    render_context = False

    form_result = None
    # The for_input is passed through to create the fields.  If this value
    # is set to true in derived classes, then fields that are marked
    # read only will have editable widgets created for them.
    for_input = None

    def __init__(self, context, request):
        LaunchpadView.__init__(self, context, request)
        self.errors = []
        self.form_wide_errors = []
        self.widget_errors = {}

    def initialize(self):
        self.setUpFields()
        self.setUpWidgets()

        data = {}
        errors, form_action = form.handleSubmit(
            self.actions, data, self._validate)

        # no action selected, so return
        if form_action is None:
            return

        # Check to see if an attempt was made to submit a non-safe
        # action with a GET query.
        is_safe = getattr(form_action, 'is_safe', False)
        if not is_safe and self.request.method != 'POST':
            raise UnsafeFormGetSubmissionError(form_action.__name__)

        if errors:
            self.form_result = form_action.failure(data, errors)
            self._abort()
        else:
            self.form_result = form_action.success(data)
            if self.next_url:
                self.request.response.redirect(self.next_url)
        if self.request.is_ajax:
            self._processNotifications(self.request)
        if self.errors:
            self.form_result = form_action.failure(data, self.errors)
            self._abort()
        self.action_taken = form_action

    def _processNotifications(self, request):
        """Add any notification messages to the response headers."""
        if not INotificationResponse.providedBy(request.response):
            return
        notifications = ([(notification.level, notification.message)
             for notification in request.response.notifications])
        if notifications:
            request.response.setHeader(
                'X-Lazr-Notifications', simplejson.dumps(notifications))

    def render(self):
        """Return the body of the response.

        By default, this method will execute the template attribute to
        render the content. But if an action handler was executed and
        it returned a value other than None, that value will be used as
        the rendered content.

        See LaunchpadView.render() for other information.
        """
        if self.form_result is not None:
            return self.form_result
        else:
            return self.template()

    def _abort(self):
        """Abort the form edit.

        This will be called in the case of a validation error.
        """
        # XXX jamesh 2006-08-02:
        # This should really be dooming the transaction rather than
        # aborting.  What we really want is to prevent more work being
        # done and then committed.
        transaction.abort()

    def extendFields(self):
        """Allow subclasses to extend the form fields."""
        pass

    def setUpFields(self):
        assert self.schema is not None, (
            "Schema must be set for LaunchpadFormView")
        self.form_fields = form.Fields(self.schema, for_input=self.for_input,
                                       render_context=self.render_context)
        self.extendFields()
        if self.field_names is not None:
            self.form_fields = self.form_fields.select(*self.field_names)

    def setUpWidgets(self, context=None):
        """Set up the widgets using the view's form fields and the context.

        If no context is given, the view's context is used."""
        for field in self.form_fields:
            if (field.custom_widget is None and
                field.__name__ in self.custom_widgets):
                # The check for custom_widget is None means that we honor the
                # value if previously set. This is important for some existing
                # forms.
                field.custom_widget = self.custom_widgets[field.__name__]
        if context is None:
            context = self.context
        self.widgets = form.setUpWidgets(
            self.form_fields, self.prefix, context, self.request,
            data=self.initial_values, adapters=self.adapters,
            ignore_request=False)
        for field_name, help_link in self.help_links.iteritems():
            self.widgets[field_name].help_link = help_link

    @property
    def help_links(self):
        """Dictionary mapping field names to help links."""
        return {}

    @property
    def adapters(self):
        """Provide custom adapters for use when setting up the widgets."""
        return {}

    @property
    def action_url(self):
        """Set the default action URL for the form."""

        # XXX: bac 2007-04-13:
        # Rather than use a property it is tempting to just cache the value of
        # request.getURL.  This caching cannot be done in __init__ as the full
        # URL has not been traversed at instantiation time.  It could be
        # done in 'initialize' if the functionality for initialization and
        # form processing are split.
        return self.request.getURL()

    @property
    def has_available_actions(self):
        """Does the view have any available actions that will render?

        If False is returned, the view or template probably needs to explain
        why no actions can be performed and offer a cancel link.
        """
        for form_action in self.actions:
            if form_action.available():
                return True
        return False

    @property
    def initial_values(self):
        """Override this in your subclass if you want any widgets to have
        initial values.
        """
        return {}

    def addError(self, message):
        """Add a form wide error.

        The 'message' parameter is CGI-escaped in accordance with the
        `INotificationResponse.addNotification()` API.  Please see it
        for details re: internationalized and markup text.
        """
        cleanmsg = html_escape(message)
        self.form_wide_errors.append(cleanmsg)
        self.errors.append(cleanmsg)

    def getFieldError(self, field_name):
        """Get the error associated with a particular field.

        If an error message is available in widget_errors, it is
        returned.  As a fallback, the corresponding widget's error()
        method is called.
        """
        if field_name in self.widget_errors:
            return self.widget_errors[field_name]
        else:
            return self.widgets[field_name].error()

    def setFieldError(self, field_name, message):
        """Set the error associated with a particular field.

        If the validator for the field also flagged an error, the
        message passed to this method will be used in preference.

        The 'message' parameter is CGI-escaped in accordance with the
        `INotificationResponse.addNotification()` API.  Please see it
        for details re: internationalized and markup text.
        """
        cleanmsg = html_escape(message)
        self.widget_errors[field_name] = cleanmsg
        self.errors.append(cleanmsg)

    @staticmethod
    def validate_none(form, action, data):
        """Do not do any validation.

        This is to be used in subclasses that have actions in which no
        validation is wanted (e.g. a cancel action).
        """
        return []

    def validate_widgets(self, data, names=None):
        """Validate the named form widgets.

        :param names: Names of widgets to validate. If None, all widgets
            will be validated.
        """
        if names is None:
            # Validate all widgets.
            widgets = self.widgets
        else:
            widgets = []
            for input, widget in self.widgets.__iter_input_and_widget__():
                if widget.context.__name__ in names:
                    widgets.append((input, widget))
            widgets = form.Widgets(widgets, len(self.prefix) + 1)
        for error in form.getWidgetsData(widgets, self.prefix, data):
            self.errors.append(error)
        for error in form.checkInvariants(self.form_fields, data):
            self.addError(error)
        return self.errors

    def _validate(self, action, data):
        """Check all widgets and perform any custom validation."""
        # Check the widgets.
        self.validate_widgets(data)

        # Perform custom validation.
        self.validate(data)
        return self.errors

    @property
    def error_count(self):
        # this should use ngettext if we ever translate Launchpad's UI
        count = len(self.form_wide_errors)
        for field in self.form_fields:
            if field.__name__ in self.widget_errors:
                count += 1
            else:
                widget = self.widgets.get(field.__name__)
                if widget and widget.error():
                    count += 1

        if count == 0:
            return ''
        elif count == 1:
            return 'There is 1 error.'
        else:
            return 'There are %d errors.' % count

    def ajax_failure_handler(self, action, data, errors):
        """Called by the form if validate() finds any errors.

        For ajax requests the standard Launchpad form template is not available
        to render any errors. We simply convert the errors to json and return
        that data to the caller so the errors can be rendered.
        """

        if not self.request.is_ajax:
            return
        self.request.response.setStatus(400, "Validation")
        self.request.response.setHeader('Content-type', 'application/json')
        errors = {}
        for widget in self.widgets:
            widget_error = self.getFieldError(widget.context.getName())
            if widget_error:
                errors[widget.name] = widget_error
        return_data = dict(
            form_wide_errors=self.form_wide_errors,
            errors=errors,
            error_summary=self.error_count)
        return simplejson.dumps(return_data)

    def validate(self, data):
        """Validate the form.

        For each error encountered, the addError() method should be
        called to log the problem.
        """
        pass

    def validate_cancel(self, action, data):
        """Noop validation in case we cancel.

        You can use this in your Form views by simply setting
        validator='validate_cancel' in the @action line of your cancel
        button."""
        return []

    def focusedElementScript(self):
        """Helper function to construct the script element content."""
        # Work out which widget needs to be focused.  First we check
        # for the first widget with an error set:
        first_widget = None
        for widget in self.widgets:
            if first_widget is None:
                first_widget = widget
            if self.getFieldError(widget.context.__name__):
                break
        else:
            # otherwise we use the widget named by self.initial_focus_widget
            if self.initial_focus_widget is _first_widget_marker:
                widget = first_widget
            elif self.initial_focus_widget is not None:
                widget = self.widgets[self.initial_focus_widget]
            else:
                widget = None

        if widget is None:
            return ''
        else:
            return ("<!--\n"
                    "setFocusByName('%s');\n"
                    "// -->" % widget.name)

    def isSingleLineLayout(self, field_name):
        widget = self.widgets[field_name]
        return not (IMultiLineWidgetLayout.providedBy(widget) or
                    ICheckBoxWidgetLayout.providedBy(widget))

    def isMultiLineLayout(self, field_name):
        widget = self.widgets[field_name]
        return IMultiLineWidgetLayout.providedBy(widget)

    def isCheckBoxLayout(self, field_name):
        widget = self.widgets[field_name]
        return (ICheckBoxWidgetLayout.providedBy(widget) and
                not IMultiLineWidgetLayout.providedBy(widget))

    def showOptionalMarker(self, field_name):
        """Should the (Optional) marker be shown?"""
        widget = self.widgets[field_name]
        # Do not show the (Optional) marker for display (i.e. read-only)
        # widgets.
        if not IInputWidget.providedBy(widget):
            return False

        # Do not show for readonly fields.
        context = getattr(widget, 'context', None)
        if getattr(context, 'readonly', None):
            return False

        # Do not show the marker for required widgets or always submitted
        # widgets.  Everything else gets the marker.
        return not (widget.required or
                    IAlwaysSubmittedWidget.providedBy(widget))


class LaunchpadEditFormView(LaunchpadFormView):

    render_context = True

    def updateContextFromData(self, data, context=None, notify_modified=True):
        """Update the context object based on form data.

        If no context is given, the view's context is used.

        If any changes were made, ObjectModifiedEvent will be
        emitted.

        This method should be called by an action method of the form.

        Returns True if there were any changes to apply.
        """
        if context is None:
            context = self.context
        if notify_modified:
            context_before_modification = Snapshot(
                context, providing=providedBy(context))

        was_changed = form.applyChanges(context, self.form_fields,
                                        data, self.adapters)
        if was_changed and notify_modified:
            field_names = [form_field.__name__
                           for form_field in self.form_fields]
            notify(ObjectModifiedEvent(
                context, context_before_modification, field_names))
        return was_changed


class custom_widget:
    """A class advisor for overriding the default widget for a field."""

    def __init__(self, field_name, widget, *args, **kwargs):
        self.field_name = field_name
        if widget is None:
            self.widget = None
        else:
            self.widget = CustomWidgetFactory(widget, *args, **kwargs)
        addClassAdvisor(self.advise)

    def advise(self, cls):
        if cls.custom_widgets is None:
            cls.custom_widgets = {}
        else:
            cls.custom_widgets = dict(cls.custom_widgets)
        cls.custom_widgets[self.field_name] = self.widget
        return cls


def safe_action(action):
    """A decorator used to mark a particular action as 'safe'.

    In the context of LaunchpadFormView, only actions marked as safe
    can be submitted using a GET request.
    """
    action.is_safe = True
    return action


class ReturnToReferrerMixin:
    """Return to the previous page after submitting the form.

    The _return_url is stored in a hidden field in the launchpad-form.pt
    between the request to view the form and submitting the form.

    _return_attribute_name and _return_attribute_values are also stored
    as hidden fields and they are used to check the validity of _return_url.

    If _return_url depends on _return_attribute_name, the result of a form
    submission can invalidate it.
    If this is the case, _return_attribute_name should be overwritten to
    return the attribute name to which _return_url depends.
    """

    @property
    def _return_attribute_name(self):
        return None

    @property
    def _return_attribute_value(self):
        if self._return_attribute_name is not None:
            return getattr(self.context, self._return_attribute_name)
        else:
            return None

    @property
    def _return_url(self):
        """See `LaunchpadFormView`."""
        # The referer header we want is only available before the view's
        # form submits to itself. This field is a hidden input in the form.
        referrer = self.request.form.get('_return_url')
        returnNotChanged = True
        if referrer is None:
            # "referer" is misspelled in the HTTP specification.
            referrer = self.request.getHeader('referer')
        else:
            attribute_name = self.request.form.get('_return_attribute_name')
            attribute_value = self.request.form.get('_return_attribute_value')
            if (attribute_name is not None
                and attribute_value is not None
                and getattr(self.context, attribute_name) != attribute_value):
                returnNotChanged = False

        if (referrer is not None
            and returnNotChanged
            and referrer.startswith(self.request.getApplicationURL())
            and referrer != self.request.getHeader('location')):
            return referrer
        else:
            return canonical_url(self.context)

    next_url = _return_url
    cancel_url = _return_url


def has_structured_doc(field):
    """Set an annotation to mark that the field's doc should be structured."""
    field.setTaggedValue('has_structured_doc', True)
    return field


class WidgetHasStructuredDoc:
    """Check if widget has structured doc.

    Example usage::
        tal:condition="widget/query:has-structured-doc"
    """

    implements(ITraversable)

    def __init__(self, widget):
        self.widget = widget

    def traverse(self, name, furtherPath):
        if name != 'has-structured-doc':
            raise TraversalError("Unknown query %r" % name)
        if len(furtherPath) > 0:
            raise TraversalError(
                "There should be no further path segments after "
                "query:has-structured-doc")
        return self.widget.context.queryTaggedValue('has_structured_doc')


def render_radio_widget_part(widget, term_value, current_value, label=None):
    """Render a particular term for a radio button widget.

    This may well work for other widgets, but has only been tested with radio
    button widgets.
    """
    term = widget.vocabulary.getTerm(term_value)
    if term.value == current_value:
        render = widget.renderSelectedItem
    else:
        render = widget.renderItem
    if label is None:
        label = term.title
    value = term.token
    return render(
        index=term.value, text=label, value=value, name=widget.name,
        cssClass='')
