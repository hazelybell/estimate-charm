# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Replacement for some standard library traceback module functions.

These honor traceback supplements as defined in zope.exceptions.
"""

__metaclass__ = type
__all__ = [
    'extract_stack',
    'extract_tb',
    'format_list',
    'print_list',
    'print_stack',
    ]

import linecache
import sys
import traceback


DEBUG_EXCEPTION_FORMATTER = False
EXPLOSIVE_ERRORS = (SystemExit, MemoryError, KeyboardInterrupt)


def _try_except(callable, *args, **kwargs):
    try:
        return callable(*args, **kwargs)
    except EXPLOSIVE_ERRORS:
        raise
    except:
        if DEBUG_EXCEPTION_FORMATTER:
            traceback.print_exc()
    # return None


def _get_frame(f):
    "if the frame is None, make one."
    if f is None:
        try:
            raise ZeroDivisionError
        except ZeroDivisionError:
            f = sys.exc_info()[2].tb_frame.f_back.f_back
    return f


def _fmt(string):
    "Return the string as deemed suitable for the extra information."
    return '   - %s' % string


def print_list(extracted_list, file=None):
    """Print the list of tuples as returned by extract_tb() or
    extract_stack() as a formatted stack trace to the given file."""
    if file is None:
        file = sys.stderr
    for line in format_list(extracted_list):
        file.write(line)


def format_list(extracted_list):
    """Format a list of traceback entry tuples for printing.

    Given a list of tuples as returned by extract_tb() or
    extract_stack(), return a list of strings ready for printing.
    Each string in the resulting list corresponds to the item with the
    same index in the argument list.  Each string ends in a newline;
    the strings may contain internal newlines as well, for those items
    whose source text line or supplement or info are not None.
    """
    list = []
    for filename, lineno, name, line, modname, supp, info in extracted_list:
        item = []
        item.append(
               '  File "%s", line %d, in %s' % (filename, lineno, name))
        if line:
            item.append('    %s' % line.strip())
        # The "supp" and "info" bits are adapted from zope.exceptions.
        try:
            if supp:
                if supp['source_url']:
                    item.append(_fmt(supp['source_url']))
                if supp['line']:
                    if supp['column']:
                        item.append(
                            _fmt('Line %(line)s, Column %(column)s' % supp))
                    else:
                        item.append(_fmt('Line %(line)s' % supp))
                elif supp['column']:
                    item.append(_fmt('Column %(column)s' % supp))
                if supp['expression']:
                    item.append(_fmt('Expression: %(expression)s' % supp))
                if supp['warnings']:
                    for warning in supp['warnings']:
                        item.append(_fmt('Warning: %s' % warning))
                if supp['extra']:
                    item.append(supp['extra'])  # We do not include a prefix.
            if info:
                item.append(_fmt(info))
        except EXPLOSIVE_ERRORS:
            raise
        except:
            # The values above may not stringify properly, or who knows what
            # else.  Be defensive.
            if DEBUG_EXCEPTION_FORMATTER:
                traceback.print_exc()
            # else just swallow the exception.
        item.append('')  # This gives us a trailing newline.
        list.append('\n'.join(item))
    return list


def print_stack(f=None, limit=None, file=None):
    """Print a stack trace from its invocation point.

    The optional 'f' argument can be used to specify an alternate
    stack frame at which to start. The optional 'limit' and 'file'
    arguments have the same meaning as for print_exception().
    """
    print_list(extract_stack(_get_frame(f), limit), file)


def _get_limit(limit):
    "Return the limit or the globally-set limit, if any."
    if limit is None:
        # stdlib uses hasattr here.
        if hasattr(sys, 'tracebacklimit'):
            limit = sys.tracebacklimit
    return limit


def _get_frame_data(f, lineno):
    "Given a frame and a lineno, return data for each item of extract_*."
    # Adapted from zope.exceptions.
    try_except = _try_except  # This is a micro-optimization.
    modname = f.f_globals.get('__name__')
    # Output a traceback supplement, if any.
    supplement_dict = info = None
    if '__traceback_supplement__' in f.f_locals:
        # Use the supplement defined in the function.
        tbs = f.f_locals['__traceback_supplement__']
    elif '__traceback_supplement__' in f.f_globals:
        # Use the supplement defined in the module.
        tbs = f.f_globals['__traceback_supplement__']
    else:
        tbs = None
    if tbs is not None:
        factory = tbs[0]
        args = tbs[1:]
        supplement = try_except(factory, *args)
        if supplement is not None:
            # It might be nice if supplements could be dicts, for simplicity.
            # Historically, though, they are objects.
            # We will turn the supplement into a dict of strings, so that we
            # have "getInfo" pre-processed and so that we are not holding on
            # to anything from the frame.
            extra = None
            getInfo = getattr(supplement, 'getInfo', None)
            if getInfo is not None:
                extra = try_except(getInfo)
                extra = try_except(str, extra) if extra is not None else None
            warnings = []
            # The outer try-except is for the iteration.
            try:
                for warning in getattr(supplement, 'warnings', ()):
                    if warning is not None:
                        warning = try_except(str, warning)
                    if warning is not None:
                        warnings.append(warning)
            except EXPLOSIVE_ERRORS:
                raise
            except:
                if DEBUG_EXCEPTION_FORMATTER:
                    traceback.print_exc()
            supplement_dict = dict(warnings=warnings, extra=extra)
            for key in ('source_url', 'line', 'column', 'expression'):
                value = getattr(supplement, key, None)
                if value is not None:
                    value = try_except(str, value)
                supplement_dict[key] = value
    info = f.f_locals.get('__traceback_info__', None)
    info = try_except(str, info) if info is not None else None
    # End part adapted from zope.exceptions.
    co = f.f_code
    filename = co.co_filename
    name = co.co_name
    linecache.checkcache(filename)
    line = linecache.getline(filename, lineno, f.f_globals)
    if line:
        line = line.strip()
    else:
        line = None
    return (filename, lineno, name, line, modname, supplement_dict, info)


def extract_stack(f=None, limit=None):
    """Extract the raw traceback from the current stack frame.

    The return value has the same format as for extract_tb().  The optional
    'f' and 'limit' arguments have the same meaning as for print_stack().
    Each item in the list is a septuple (filename, line number, function name,
    text, module name, optional supplement dict, optional info string), and
    the entries are in order from oldest to newest stack frame.
    """
    f = _get_frame(f)
    limit = _get_limit(limit)
    list = []
    n = 0
    get_frame_data = _get_frame_data  # This is a micro-optimization.
    while f is not None and (limit is None or n < limit):
        list.append(get_frame_data(f, f.f_lineno))
        f = f.f_back
        n = n + 1
    list.reverse()
    return list


def extract_tb(tb, limit=None):
    """Return list of up to limit pre-processed entries from traceback.

    This is useful for alternate formatting of stack traces.  If 'limit' is
    omitted or None, all entries are extracted.  A pre-processed stack trace
    entry is a sextuple (filename, line number, function name, text, module
    name, optional supplement dict, optional info string) representing the
    information that is printed for a stack trace.  The text is a string with
    leading and trailing whitespace stripped; if the source is not available
    it is None. The supplement dict has keys 'source_url', 'line', 'column',
    'expression', 'warnings' (an iterable), and 'extra', any of which may be
    None.
    """
    # zope.exceptions handles tracebacks.  This function is implemented just
    # to show how this module's patterns might be extended to tracebacks.
    limit = _get_limit(limit)
    list = []
    n = 0
    get_frame_data = _get_frame_data  # This is a micro-optimization.
    while tb is not None and (limit is None or n < limit):
        list.append(get_frame_data(tb.tb_frame, tb.tb_lineno))
        tb = tb.tb_next
        n = n + 1
    return list
