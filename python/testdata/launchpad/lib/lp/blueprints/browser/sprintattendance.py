# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Views for SprintAttendance."""

__metaclass__ = type
__all__ = [
    'SprintAttendanceAttendView',
    'SprintAttendanceRegisterView',
    ]

from datetime import timedelta

import pytz

from lp import _
from lp.app.browser.launchpadform import (
    action,
    custom_widget,
    LaunchpadFormView,
    )
from lp.app.widgets.date import DateTimeWidget
from lp.app.widgets.itemswidgets import LaunchpadBooleanRadioWidget
from lp.blueprints.interfaces.sprintattendance import ISprintAttendance
from lp.services.webapp import canonical_url


class BaseSprintAttendanceAddView(LaunchpadFormView):

    schema = ISprintAttendance
    field_names = ['time_starts', 'time_ends', 'is_physical']
    custom_widget('time_starts', DateTimeWidget)
    custom_widget('time_ends', DateTimeWidget)
    custom_widget(
        'is_physical', LaunchpadBooleanRadioWidget, orientation='vertical',
        true_label="Physically", false_label="Remotely", hint=None)

    def setUpWidgets(self):
        LaunchpadFormView.setUpWidgets(self)
        tz = pytz.timezone(self.context.time_zone)
        self.starts_widget = self.widgets['time_starts']
        self.ends_widget = self.widgets['time_ends']
        self.starts_widget.required_time_zone = tz
        self.ends_widget.required_time_zone = tz
        # We don't need to display seconds
        timeformat = '%Y-%m-%d %H:%M'
        self.starts_widget.timeformat = timeformat
        self.ends_widget.timeformat = timeformat
        # Constrain the widget to dates from the day before to the day
        # after the sprint. We will accept a time just before or just after
        # and map those to the beginning and end times, respectively, in
        # self.getDates().
        from_date = self.context.time_starts.astimezone(tz)
        to_date = self.context.time_ends.astimezone(tz)
        self.starts_widget.from_date = from_date - timedelta(days=1)
        self.starts_widget.to_date = to_date
        self.ends_widget.from_date = from_date
        self.ends_widget.to_date = to_date + timedelta(days=1)

    def validate(self, data):
        """Verify that the entered times are valid.

        We check that:
         * they depart after they arrive
         * they don't arrive after the end of the sprint
         * they don't depart before the start of the sprint
        """
        time_starts = data.get('time_starts')
        time_ends = data.get('time_ends')

        if time_starts and time_starts > self.context.time_ends:
            self.setFieldError(
                'time_starts',
                _('Choose an arrival time before the end of the meeting.'))
        if time_ends:
            if time_starts and time_ends < time_starts:
                self.setFieldError(
                    'time_ends',
                    _('The end time must be after the start time.'))
            elif time_ends < self.context.time_starts:
                self.setFieldError(
                    'time_ends', _('Choose a departure time after the '
                                   'start of the meeting.'))
            elif (time_ends.hour == 0 and time_ends.minute == 0 and
                  time_ends.second == 0):
                # We assume the user entered just a date, which gives them
                # midnight in the morning of that day, when they probably want
                # the end of the day.
                data['time_ends'] = min(
                    self.context.time_ends,
                    time_ends + timedelta(days=1, seconds=-1))

    def getDates(self, data):
        time_starts = data['time_starts']
        time_ends = data['time_ends']
        if (time_ends.hour == 0 and time_ends.minute == 0 and
            time_ends.second == 0):
            # We assume the user entered just a date, which gives them
            # midnight in the morning of that day, when they probably want
            # the end of the day.
            time_ends = time_ends + timedelta(days=1, seconds=-1)
        if time_starts < self.context.time_starts:
            # Can't arrive before the conference starts, we assume that you
            # meant to say you will get there at the beginning
            time_starts = self.context.time_starts
        if time_ends > self.context.time_ends:
            # Can't stay after the conference ends, we assume that you meant
            # to say you will leave at the end.
            time_ends = self.context.time_ends
        return time_starts, time_ends

    @property
    def next_url(self):
        return canonical_url(self.context)

    cancel_url = next_url

    _local_timeformat = '%H:%M on %A, %Y-%m-%d'

    @property
    def local_start(self):
        """The sprint start time, in the local time zone, as text."""
        tz = pytz.timezone(self.context.time_zone)
        return self.context.time_starts.astimezone(tz).strftime(
                    self._local_timeformat)

    @property
    def local_end(self):
        """The sprint end time, in the local time zone, as text."""
        tz = pytz.timezone(self.context.time_zone)
        return self.context.time_ends.astimezone(tz).strftime(
                    self._local_timeformat)


class SprintAttendanceAttendView(BaseSprintAttendanceAddView):
    """A view used to register your attendance at a sprint."""

    label = "Register your attendance"

    @property
    def initial_values(self):
        """Show committed attendance, or default to the sprint times."""
        for attendance in self.context.attendances:
            if attendance.attendee == self.user:
                return dict(time_starts=attendance.time_starts,
                            time_ends=attendance.time_ends,
                            is_physical=attendance.is_physical)
        # If this person is not yet registered, then default to showing the
        # full sprint dates.
        return {'time_starts': self.context.time_starts,
                'time_ends': self.context.time_ends}

    @action(_('Register'), name='register')
    def register_action(self, action, data):
        time_starts, time_ends = self.getDates(data)
        is_physical = data['is_physical']
        self.context.attend(self.user, time_starts, time_ends, is_physical)


class SprintAttendanceRegisterView(BaseSprintAttendanceAddView):
    """A view used to register someone else's attendance at a sprint."""

    label = 'Register someone else'
    field_names = ['attendee'] + list(BaseSprintAttendanceAddView.field_names)

    @property
    def initial_values(self):
        """Default to displaying the full span of the sprint."""
        return {'time_starts': self.context.time_starts,
                'time_ends': self.context.time_ends}

    @action(_('Register'), name='register')
    def register_action(self, action, data):
        time_starts, time_ends = self.getDates(data)
        is_physical = data['is_physical']
        self.context.attend(
            data['attendee'], time_starts, time_ends, is_physical)
