# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""A UIFactory useful for code imports."""

__metaclass__ = type
__all__ = ['LoggingUIFactory']


import sys
import time

from bzrlib.ui import NoninteractiveUIFactory
from bzrlib.ui.text import TextProgressView


class LoggingUIFactory(NoninteractiveUIFactory):
    """A UI Factory that produces reasonably sparse logging style output.

    The goal is to produce a line of output no more often than once a minute
    (by default).
    """

    # XXX: JelmerVernooij 2011-08-02 bug=820127: This seems generic enough to
    # live in bzrlib.ui

    def __init__(self, time_source=time.time, logger=None, interval=60.0):
        """Construct a `LoggingUIFactory`.

        :param time_source: A callable that returns time in seconds since the
            epoch.  Defaults to ``time.time`` and should be replaced with
            something deterministic in tests.
        :param logger: The logger object to write to
        :param interval: Don't produce output more often than once every this
            many seconds.  Defaults to 60 seconds.
        """
        NoninteractiveUIFactory.__init__(self)
        self.interval = interval
        self.logger = logger
        self._progress_view = LoggingTextProgressView(
            time_source, lambda m: logger.info("%s", m), interval)

    def show_user_warning(self, warning_id, **message_args):
        self.logger.warning(
            "%s", self.format_user_warning(warning_id, message_args))

    def show_warning(self, msg):
        if isinstance(msg, unicode):
            msg = msg.encode("utf-8")
        self.logger.warning("%s", msg)

    def get_username(self, prompt, **kwargs):
        return None

    def get_password(self, prompt, **kwargs):
        return None

    def show_message(self, msg):
        self.logger.info("%s", msg)

    def note(self, msg):
        self.logger.info("%s", msg)

    def show_error(self, msg):
        self.logger.error("%s", msg)

    def _progress_updated(self, task):
        """A task has been updated and wants to be displayed.
        """
        if not self._task_stack:
            self.logger.warning("%r updated but no tasks are active", task)
        self._progress_view.show_progress(task)

    def _progress_all_finished(self):
        self._progress_view.clear()

    def report_transport_activity(self, transport, byte_count, direction):
        """Called by transports as they do IO.

        This may update a progress bar, spinner, or similar display.
        By default it does nothing.
        """
        self._progress_view.show_transport_activity(transport,
            direction, byte_count)


class LoggingTextProgressView(TextProgressView):
    """Support class for `LoggingUIFactory`. """

    def __init__(self, time_source, writer, interval):
        """See `LoggingUIFactory.__init__` for descriptions of the parameters.
        """
        # If anything refers to _term_file, that's a bug for us.
        TextProgressView.__init__(self, term_file=None)
        self._writer = writer
        self.time_source = time_source
        if writer is None:
            self.write = sys.stdout.write
        else:
            self.write = writer
        # _transport_expire_time is how long to keep the transport activity in
        # the progress bar for when show_progress is called.  We opt for
        # always just showing the task info.
        self._transport_expire_time = 0
        # We repaint only after 'interval' seconds whether we're being told
        # about task progress or transport activity.
        self._update_repaint_frequency = interval
        self._transport_repaint_frequency = interval

    def _show_line(self, s):
        # This is a bit hackish: even though this method is just expected to
        # produce output, we reset the _bytes_since_update so that transport
        # activity is reported as "since last log message" and
        # _transport_update_time so that transport activity doesn't cause an
        # update until it occurs more than _transport_repaint_frequency
        # seconds after the last update of any kind.
        self._bytes_since_update = 0
        self._transport_update_time = self.time_source()
        self._writer(s)

    def _render_bar(self):
        # There's no point showing a progress bar in a flat log.
        return ''

    def _render_line(self):
        bar_string = self._render_bar()
        if self._last_task:
            task_part, counter_part = self._format_task(self._last_task)
        else:
            task_part = counter_part = ''
        if self._last_task and not self._last_task.show_transport_activity:
            trans = ''
        else:
            trans = self._last_transport_msg
        # the bar separates the transport activity from the message, so even
        # if there's no bar or spinner, we must show something if both those
        # fields are present
        if (task_part and trans) and not bar_string:
            bar_string = ' | '
        s = trans + bar_string + task_part + counter_part
        return s

    def _format_transport_msg(self, scheme, dir_char, rate):
        # We just report the amount of data transferred.
        return '%s bytes transferred' % self._bytes_since_update

    # What's below is copied and pasted from bzrlib.ui.text.TextProgressView
    # and changed to (a) get its notion of time from self.time_source (which
    # can be replaced by a deterministic time source in tests) rather than
    # time.time and (b) respect the _update_repaint_frequency,
    # _transport_expire_time and _transport_repaint_frequency instance
    # variables rather than having these as hard coded constants.  These
    # changes could and should be ported upstream and then we won't have to
    # carry our version of this code around any more.

    def show_progress(self, task):
        """Called by the task object when it has changed.

        :param task: The top task object; its parents are also included
            by following links.
        """
        must_update = task is not self._last_task
        self._last_task = task
        now = self.time_source()
        if ((not must_update) and
            (now < self._last_repaint + self._update_repaint_frequency)):
            return
        if now > self._transport_update_time + self._transport_expire_time:
            # no recent activity; expire it
            self._last_transport_msg = ''
        self._last_repaint = now
        self._repaint()

    def show_transport_activity(self, transport, direction, byte_count):
        """Called by transports via the ui_factory, as they do IO.

        This may update a progress bar, spinner, or similar display.
        By default it does nothing.
        """
        # XXX: Probably there should be a transport activity model, and that
        # too should be seen by the progress view, rather than being poked in
        # here.
        self._total_byte_count += byte_count
        self._bytes_since_update += byte_count
        now = self.time_source()
        if self._transport_update_time is None:
            self._transport_update_time = now
        elif now >= (self._transport_update_time
                     + self._transport_repaint_frequency):
            # guard against clock stepping backwards, and don't update too
            # often
            rate = self._bytes_since_update / (
                now - self._transport_update_time)
            scheme = getattr(transport, '_scheme', None) or repr(transport)
            if direction == 'read':
                dir_char = '>'
            elif direction == 'write':
                dir_char = '<'
            else:
                dir_char = '?'
            msg = self._format_transport_msg(scheme, dir_char, rate)
            self._transport_update_time = now
            self._last_repaint = now
            self._bytes_since_update = 0
            self._last_transport_msg = msg
            self._repaint()
