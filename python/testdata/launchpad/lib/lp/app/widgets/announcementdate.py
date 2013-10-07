# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from datetime import datetime

import pytz
from zope.formlib import form
from zope.formlib.interfaces import (
    ConversionError,
    ISimpleInputWidget,
    WidgetInputError,
    )
from zope.formlib.widget import (
    CustomWidgetFactory,
    SimpleInputWidget,
    )
from zope.interface import implements
from zope.schema import (
    Choice,
    Datetime,
    )
from zope.schema.vocabulary import (
    SimpleTerm,
    SimpleVocabulary,
    )

from lp import _
from lp.app.validators import LaunchpadValidationError
from lp.app.widgets.date import DateTimeWidget
from lp.app.widgets.itemswidgets import LaunchpadRadioWidget
from lp.registry.interfaces.announcement import IAnnouncement
from lp.services.webapp.interfaces import IAlwaysSubmittedWidget


class IAnnouncementDateWidget(ISimpleInputWidget):
    """A widget for selecting the date of a news item."""


class AnnouncementDateWidget(SimpleInputWidget):
    """See IAnnouncementDateWidget."""

    implements(IAlwaysSubmittedWidget)

    def __init__(self, context, request):
        SimpleInputWidget.__init__(self, context, request)
        fields = form.Fields(
            Choice(__name__='action', source=self._getActionsVocabulary(),
                   title=_('Action')),
            Datetime(__name__='announcement_date', title=_('Date'),
                     required=False, default=None))
        fields['action'].custom_widget = CustomWidgetFactory(
            LaunchpadRadioWidget)
        fields['announcement_date'].custom_widget = CustomWidgetFactory(
            DateTimeWidget)
        if IAnnouncement.providedBy(self.context.context):
            # we are editing an existing announcement
            data = {}
            date_announced = self.context.context.date_announced
            data['announcement_date'] = date_announced
            if date_announced is None:
                data['action'] = 'sometime'
            else:
                data['action'] = 'specific'
        else:
            data = {'action': 'immediately'}
        widgets = form.setUpWidgets(
            fields, self.name, context, request, ignore_request=False,
            data=data)
        self.action_widget = widgets['action']
        self.announcement_date_widget = widgets['announcement_date']

    def __call__(self):
        html = '<div>Publish this announcement:</div>\n'
        html += "<p>%s</p><p>%s</p>" % (
            self.action_widget(), self.announcement_date_widget())
        return html

    def hasInput(self):
        return self.action_widget.hasInput()

    def _getActionsVocabulary(self):
        action_names = [
            ('immediately', 'Immediately'),
            ('sometime', 'At some time in the future when I come back to '
                         'authorize it'),
            ('specific', 'At this specific date and time:')]
        terms = [
            SimpleTerm(name, name, label) for name, label in action_names]
        return SimpleVocabulary(terms)

    def getInputValue(self):
        self._error = None
        action = self.action_widget.getInputValue()
        try:
            announcement_date = self.announcement_date_widget.getInputValue()
        except ConversionError:
            self._error = WidgetInputError(
                self.name, self.label,
                LaunchpadValidationError(
                    _('Please provide a valid date and time.')))
            raise self._error
        if action == 'immediately' and announcement_date is not None:
            self._error = WidgetInputError(
                self.name, self.label,
                LaunchpadValidationError(
                    _('Please do not provide a date if you want to publish '
                      'immediately.')))
            raise self._error
        if action == 'specific' and announcement_date is None:
            self._error = WidgetInputError(
                self.name, self.label,
                LaunchpadValidationError(
                    _('Please provide a publication date.')))
            raise self._error
        if action == 'immediately':
            return datetime.now(pytz.utc)
        elif action == "sometime":
            return None
        elif action == "specific":
            return announcement_date
        else:
            raise AssertionError, 'Unknown action in AnnouncementDateWidget'


