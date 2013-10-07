# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Loggers."""

__metaclass__ = type
__all__ = [
    'BufferLogger',
    'DevNullLogger',
    'FakeLogger',
    'LaunchpadLogger',
    'NullHandler',
    'PrefixFilter',
    ]

import logging
from StringIO import StringIO
import sys
import traceback

from testtools.content import (
    Content,
    UTF8_TEXT,
    )

from lp.services.log import loglevels


LEVEL_PREFIXES = dict(
    (debug_level, "DEBUG%d" % (1 + debug_level - loglevels.DEBUG))
    for debug_level in xrange(loglevels.DEBUG9, loglevels.DEBUG))

LEVEL_PREFIXES.update({
    loglevels.DEBUG: 'DEBUG',
    loglevels.INFO: 'INFO',
    loglevels.WARNING: 'WARNING',
    loglevels.ERROR: 'ERROR',
    loglevels.CRITICAL: 'CRITICAL',
})


class LaunchpadLogger(logging.Logger):
    """Logger that support our custom levels."""

    def debug1(self, msg, *args, **kwargs):
        if self.isEnabledFor(loglevels.DEBUG1):
            self._log(loglevels.DEBUG1, msg, args, **kwargs)

    def debug2(self, msg, *args, **kwargs):
        if self.isEnabledFor(loglevels.DEBUG2):
            self._log(loglevels.DEBUG2, msg, args, **kwargs)

    def debug3(self, msg, *args, **kwargs):
        if self.isEnabledFor(loglevels.DEBUG3):
            self._log(loglevels.DEBUG3, msg, args, **kwargs)

    def debug4(self, msg, *args, **kwargs):
        if self.isEnabledFor(loglevels.DEBUG4):
            self._log(loglevels.DEBUG4, msg, args, **kwargs)

    def debug5(self, msg, *args, **kwargs):
        if self.isEnabledFor(loglevels.DEBUG5):
            self._log(loglevels.DEBUG5, msg, args, **kwargs)

    def debug6(self, msg, *args, **kwargs):
        if self.isEnabledFor(loglevels.DEBUG6):
            self._log(loglevels.DEBUG6, msg, args, **kwargs)

    def debug7(self, msg, *args, **kwargs):
        if self.isEnabledFor(loglevels.DEBUG7):
            self._log(loglevels.DEBUG7, msg, args, **kwargs)

    def debug8(self, msg, *args, **kwargs):
        if self.isEnabledFor(loglevels.DEBUG8):
            self._log(loglevels.DEBUG8, msg, args, **kwargs)

    def debug9(self, msg, *args, **kwargs):
        if self.isEnabledFor(loglevels.DEBUG9):
            self._log(loglevels.DEBUG9, msg, args, **kwargs)


class PrefixFilter:
    """A logging Filter that inserts a prefix into messages.

    If no static prefix is provided, the Logger's name is used.
    """

    def __init__(self, prefix=None):
        self.prefix = prefix

    def filter(self, record):
        prefix = self.prefix or record.name
        record.msg = '[%s] %s' % (prefix, record.msg)
        return True


class NullHandler(logging.Handler):
    """A do-nothing Handler used to silence 'No handlers for logger' warnings.
    """

    def emit(self, record):
        pass


class FakeLogger:
    """Emulates a proper logger, just printing everything out the given file.
    """
    # XXX: GavinPanella 2011-11-04 bug=886053: This is a test fixture not a
    # service.

    loglevel = loglevels.DEBUG

    def __init__(self, output_file=None):
        """The default output_file is sys.stdout."""
        self.output_file = output_file

    def setLevel(self, loglevel):
        self.loglevel = loglevel

    def getEffectiveLevel(self):
        return self.loglevel

    def _format_message(self, msg, *args):
        if not isinstance(msg, basestring):
            msg = str(msg)
        # To avoid type errors when the msg has % values and args is empty,
        # don't expand the string with empty args.
        if len(args) > 0:
            msg %= args
        return msg

    def message(self, level, msg, *stuff, **kw):
        if level < self.loglevel:
            return

        # We handle the default output file here because sys.stdout
        # might have been reassigned. Between now and when this object
        # was instantiated.
        if self.output_file is None:
            output_file = sys.stdout
        else:
            output_file = self.output_file
        prefix = LEVEL_PREFIXES.get(level, "%d>" % level)
        print >> output_file, prefix, self._format_message(msg, *stuff)

        if 'exc_info' in kw:
            traceback.print_exc(file=output_file)

    def log(self, level, *stuff, **kw):
        self.message(level, *stuff, **kw)

    def warning(self, *stuff, **kw):
        self.message(loglevels.WARNING, *stuff, **kw)

    warn = warning

    def error(self, *stuff, **kw):
        self.message(loglevels.ERROR, *stuff, **kw)

    exception = error

    def critical(self, *stuff, **kw):
        self.message(loglevels.CRITICAL, *stuff, **kw)

    fatal = critical

    def info(self, *stuff, **kw):
        self.message(loglevels.INFO, *stuff, **kw)

    def debug(self, *stuff, **kw):
        self.message(loglevels.DEBUG, *stuff, **kw)

    def debug2(self, *stuff, **kw):
        self.message(loglevels.DEBUG2, *stuff, **kw)

    def debug3(self, *stuff, **kw):
        self.message(loglevels.DEBUG3, *stuff, **kw)

    def debug4(self, *stuff, **kw):
        self.message(loglevels.DEBUG4, *stuff, **kw)

    def debug5(self, *stuff, **kw):
        self.message(loglevels.DEBUG5, *stuff, **kw)

    def debug6(self, *stuff, **kw):
        self.message(loglevels.DEBUG6, *stuff, **kw)

    def debug7(self, *stuff, **kw):
        self.message(loglevels.DEBUG7, *stuff, **kw)

    def debug8(self, *stuff, **kw):
        self.message(loglevels.DEBUG8, *stuff, **kw)

    def debug9(self, *stuff, **kw):
        self.message(loglevels.DEBUG9, *stuff, **kw)


class DevNullLogger(FakeLogger):
    """A logger that drops all messages."""
    # XXX: GavinPanella 2011-11-04 bug=886053: This is a test fixture not a
    # service.

    def message(self, *args, **kwargs):
        """Do absolutely nothing."""


class BufferLogger(FakeLogger):
    """A logger that logs to a StringIO object."""
    # XXX: GavinPanella 2011-11-04 bug=886053: This is a test fixture not a
    # service.

    def __init__(self):
        super(BufferLogger, self).__init__(StringIO())

    def getLogBuffer(self):
        """Return the existing log messages."""
        return self.output_file.getvalue()

    def clearLogBuffer(self):
        """Clear out the existing log messages."""
        self.output_file = StringIO()

    def getLogBufferAndClear(self):
        """Return the existing log messages and clear the buffer."""
        messages = self.getLogBuffer()
        self.clearLogBuffer()
        return messages

    @property
    def content(self):
        """Return a `testtools.content.Content` for this object's buffer.

        Use with `testtools.TestCase.addDetail`, `fixtures.Fixture.addDetail`,
        and anything else that understands details.
        """
        get_bytes = lambda: [self.getLogBuffer().encode("utf-8")]
        return Content(UTF8_TEXT, get_bytes)
