# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the stacktrace module."""

__metaclass__ = type

import StringIO
import sys

from lp.services import stacktrace
from lp.testing import TestCase
from lp.testing.layers import BaseLayer

# This constant must always be equal to the line number on which it lives for
# the tests to pass.
MY_LINE_NUMBER = 17

MY_FILE_NAME = __file__[:__file__.rindex('.py')] + '.py'


class Supplement:
    def __init__(self, kwargs):
        for key, value in kwargs.items():
            assert key in ('getInfo', 'source_url', 'line', 'column',
                           'expression', 'warnings'), 'Bad attribute name.'
            setattr(self, key, value)


def get_frame(supplement=None, info=None):
    if supplement is not None:
        __traceback_supplement__ = (Supplement, supplement)
        __traceback_supplement__  # Quiet down the linter.
    if info is not None:
        __traceback_info__ = info
        __traceback_info__  # Quiet down the linter.
    return sys._getframe()


class BadString:

    def __str__(self):
        raise ValueError()


class TestStacktrace(TestCase):

    layer = BaseLayer

    def test_get_frame_helper(self):
        # non-None argument passed is returned unchanged.
        self.assertEqual(self, stacktrace._get_frame(self))
        # Otherwise get the frame two-up.

        def run_get_frame():
            """run _get_frame from inside another function."""
            return stacktrace._get_frame(None)
        self.assertEqual(sys._getframe(), run_get_frame())

    def test_get_limit_helper(self):
        # non-None argument is returned unchanged.
        self.assertEqual(self, stacktrace._get_limit(self))
        # Otherwise return sys.tracebacklimit if it exists, or None if not.
        original_limit = getattr(sys, 'tracebacklimit', self)
        try:
            if original_limit is not self:
                del sys.tracebacklimit
            self.assertEqual(None, stacktrace._get_limit(None))
            sys.tracebacklimit = 1000
            self.assertEqual(1000, stacktrace._get_limit(None))
        finally:
            if (original_limit is self and
                getattr(sys, 'tracebacklimit', self) is not self):
                # Clean it off.
                del sys.tracebacklimit
            else:
                sys.tracebacklimit = original_limit

    def test_get_frame_data_standard(self):
        filename, lineno, name, line, modname, supplement, info = (
            stacktrace._get_frame_data(get_frame(), MY_LINE_NUMBER))
        self.assertEqual(MY_FILE_NAME, filename)
        self.assertEqual(MY_LINE_NUMBER, lineno)
        self.assertEqual('get_frame', name)
        self.assertStartsWith(line, 'MY_LINE_NUMBER = ')
        self.assertEqual(__name__, modname)
        self.assertIs(None, supplement)
        self.assertIs(None, info)

    def test_get_frame_data_info(self):
        filename, lineno, name, line, modname, supplement, info = (
            stacktrace._get_frame_data(
                get_frame(info='foo bar'), MY_LINE_NUMBER))
        self.assertEqual('foo bar', info)

    def test_get_frame_data_supplement_empty(self):
        filename, lineno, name, line, modname, supplement, info = (
            stacktrace._get_frame_data(
                get_frame(supplement={}), MY_LINE_NUMBER))
        self.assertEqual(
            dict(source_url=None, line=None, column=None, expression=None,
                 warnings=[], extra=None),
            supplement)

    def test_get_frame_data_supplement_and_info(self):
        filename, lineno, name, line, modname, supplement, info = (
            stacktrace._get_frame_data(
                get_frame(supplement={}, info='foo bar'),
                MY_LINE_NUMBER))
        self.assertEqual(
            dict(source_url=None, line=None, column=None, expression=None,
                 warnings=[], extra=None),
            supplement)
        self.assertEqual('foo bar', info)

    def test_get_frame_data_supplement_all(self):
        filename, lineno, name, line, modname, supplement, info = (
            stacktrace._get_frame_data(
                get_frame(
                    supplement=dict(
                        source_url='/foo/bar.pt',
                        line=42,
                        column=84,
                        expression='tal:define="foo view/foo"',
                        warnings=('watch out', 'pass auf'),
                        getInfo=lambda: 'read all about it'
                    )),
                MY_LINE_NUMBER))
        self.assertEqual(
            dict(source_url='/foo/bar.pt', line='42', column='84',
                 expression='tal:define="foo view/foo"',
                 warnings=['watch out', 'pass auf'],
                 extra='read all about it'),
            supplement)

    def test_get_frame_data_supplement_bad_getInfo(self):
        def boo_hiss():
            raise ValueError()
        filename, lineno, name, line, modname, supplement, info = (
            stacktrace._get_frame_data(
                get_frame(supplement=dict(getInfo=boo_hiss)),
                MY_LINE_NUMBER))
        self.assertEqual(
            dict(source_url=None, line=None, column=None, expression=None,
                 warnings=[], extra=None),
            supplement)

    def test_get_frame_data_supplement_bad_getInfo_with_traceback(self):
        def boo_hiss():
            raise ValueError()
        original_stderr = sys.__stderr__
        stderr = sys.stderr = StringIO.StringIO()
        self.assertFalse(stacktrace.DEBUG_EXCEPTION_FORMATTER)
        stacktrace.DEBUG_EXCEPTION_FORMATTER = True
        try:
            filename, lineno, name, line, modname, supplement, info = (
                stacktrace._get_frame_data(
                    get_frame(supplement=dict(getInfo=boo_hiss)),
                    MY_LINE_NUMBER))
        finally:
            sys.stderr = original_stderr
            stacktrace.DEBUG_EXCEPTION_FORMATTER = False
        self.assertEqual(
            dict(source_url=None, line=None, column=None, expression=None,
                 warnings=[], extra=None),
            supplement)
        self.assertIn('boo_hiss', stderr.getvalue())

    def test_get_frame_data_broken_str(self):
        bad = BadString()
        filename, lineno, name, line, modname, supplement, info = (
            stacktrace._get_frame_data(
                get_frame(
                    supplement=dict(
                        source_url=bad,
                        line=bad,
                        column=bad,
                        expression=bad,
                        warnings=('watch out', bad),
                        getInfo=lambda: bad
                    ),
                    info=bad),
                MY_LINE_NUMBER))
        self.assertEqual(
            dict(source_url=None, line=None, column=None,
                 expression=None, warnings=['watch out'], extra=None),
            supplement)
        self.assertIs(None, info)

    def test_get_frame_data_broken_warnings(self):
        filename, lineno, name, line, modname, supplement, info = (
            stacktrace._get_frame_data(
                get_frame(
                    supplement=dict(
                        warnings=object()
                    )),
                MY_LINE_NUMBER))
        self.assertEqual([], supplement['warnings'])

    def test_extract_stack(self):
        extracted = stacktrace.extract_stack(get_frame())
        self.assertTrue(len(extracted) > 1)
        filename, lineno, name, line, modname, supplement, info = (
            extracted[-1])
        self.assertEqual(MY_FILE_NAME, filename)
        self.assertIsInstance(lineno, int)
        self.assertEqual('get_frame', name)
        self.assertEqual('return sys._getframe()', line)
        self.assertEqual(__name__, modname)
        self.assertIs(None, supplement)
        self.assertIs(None, info)

    def test_extract_tb(self):
        try:
            raise ValueError()
        except ValueError:
            type_, value, tb = sys.exc_info()
        extracted = stacktrace.extract_tb(tb)
        self.assertEqual(1, len(extracted))
        filename, lineno, name, line, modname, supplement, info = (
            extracted[0])
        self.assertEqual(MY_FILE_NAME, filename)
        self.assertIsInstance(lineno, int)
        self.assertEqual('test_extract_tb', name)
        self.assertEqual('raise ValueError()', line)
        self.assertEqual(__name__, modname)
        self.assertIs(None, supplement)
        self.assertIs(None, info)

    def test_format_list_simple(self):
        extracted = stacktrace.extract_stack(get_frame())
        formatted = stacktrace.format_list(extracted)
        self.assertIsInstance(formatted, list)
        for line in formatted:
            self.assertEndsWith(line, '\n')
        line = formatted[-1].split('\n')
        self.assertStartsWith(
            line[0], '  File "' + MY_FILE_NAME + '", line ')
        self.assertEndsWith(line[0], ', in get_frame')
        self.assertEqual('    return sys._getframe()', line[1])

    def test_format_list_full(self):
        extracted = stacktrace.extract_stack(
            get_frame(
                supplement=dict(
                    source_url='/foo/bar.pt',
                    line=42,
                    column=84,
                    expression='tal:define="foo view/foo"',
                    warnings=('watch out', 'pass auf'),
                    getInfo=lambda: 'read all about it'),
                info='I am the Walrus'
                )
            )
        formatted = stacktrace.format_list(extracted)
        self.assertIsInstance(formatted, list)
        for line in formatted:
            self.assertEndsWith(line, '\n')
        line = formatted[-1].split('\n')
        self.assertStartsWith(
            line[0], '  File "' + MY_FILE_NAME + '", line ')
        self.assertEndsWith(line[0], ', in get_frame')
        self.assertEqual('    return sys._getframe()', line[1])
        self.assertEqual('   - /foo/bar.pt', line[2])
        self.assertEqual('   - Line 42, Column 84', line[3])
        self.assertEqual(
            '   - Expression: tal:define="foo view/foo"', line[4])
        self.assertEqual(
            '   - Warning: watch out', line[5])
        self.assertEqual(
            '   - Warning: pass auf', line[6])
        self.assertEqual(
            'read all about it', line[7])
        self.assertEqual('   - I am the Walrus', line[8])

    def test_format_list_extra_errors(self):
        extracted = stacktrace.extract_stack(get_frame(supplement=dict()))
        extracted[-1][-2]['warnings'] = object()  # This should never happen.
        original_stderr = sys.__stderr__
        stderr = sys.stderr = StringIO.StringIO()
        self.assertFalse(stacktrace.DEBUG_EXCEPTION_FORMATTER)
        stacktrace.DEBUG_EXCEPTION_FORMATTER = True
        try:
            formatted = stacktrace.format_list(extracted)
        finally:
            sys.stderr = original_stderr
            stacktrace.DEBUG_EXCEPTION_FORMATTER = False
        self.assertStartsWith(stderr.getvalue(), 'Traceback (most recent')
        self.assertEndsWith(formatted[-1], '    return sys._getframe()\n')

    def test_print_list_default(self):
        extracted = stacktrace.extract_stack(get_frame())
        original_stderr = sys.__stderr__
        stderr = sys.stderr = StringIO.StringIO()
        try:
            stacktrace.print_list(extracted)
        finally:
            sys.stderr = original_stderr
        self.assertEndsWith(stderr.getvalue(), 'return sys._getframe()\n')

    def test_print_list_file(self):
        extracted = stacktrace.extract_stack(get_frame())
        f = StringIO.StringIO()
        stacktrace.print_list(extracted, file=f)
        self.assertEndsWith(f.getvalue(), 'return sys._getframe()\n')

    def test_print_stack_default(self):
        original_stderr = sys.__stderr__
        stderr = sys.stderr = StringIO.StringIO()
        try:
            stacktrace.print_stack()
        finally:
            sys.stderr = original_stderr
        self.assertEndsWith(stderr.getvalue(), 'stacktrace.print_stack()\n')

    def test_print_stack_options(self):
        f = StringIO.StringIO()
        frame = get_frame()
        stacktrace.print_stack(f=frame, limit=100, file=f)
        self.assertEndsWith(f.getvalue(), 'return sys._getframe()\n')
        self.assertTrue(len(f.getvalue().split('\n')) > 4)
        f = StringIO.StringIO()
        stacktrace.print_stack(f=frame, limit=2, file=f)
        self.assertEqual(4, len(f.getvalue().strip().split('\n')))
        self.assertEndsWith(f.getvalue(), 'return sys._getframe()\n')
