# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Handlers for warnings, to be installed when testing."""

__metaclass__ = type

import atexit
import inspect
import StringIO
import sys
import warnings


class WarningReport:

    def __init__(self, message, info):
        self.message = message
        self.info = info

    def __str__(self):
        info = str(self.info)
        if info:
            return info
        else:
            return self.message

class ImportantInfo:

    def __init__(self, expressiontext, viewclassname, templatefilename,
        requesturl, viewclassfilename, viewclasslineno, viewclassfunc,
        doctestname, doctestline):
        self.expressiontext = expressiontext
        self.viewclassname = viewclassname
        self.viewclassfilename = viewclassfilename
        self.viewclasslineno = viewclasslineno
        self.templatefilename = templatefilename
        self.requesturl = requesturl
        self.viewclassfunc = viewclassfunc
        self.doctestname = doctestname
        self.doctestline = doctestline

    def __str__(self):
        L = []
        if self.expressiontext:
            L.append('The expression: %s in %s' % (
                self.expressiontext, self.templatefilename))
        if self.viewclassname:
            L.append('The method %s.%s' % (
                self.viewclassname, self.viewclassfunc))
            #L.append('at line %s of file %s' % (
            #    self.viewclasslineno, self.viewclassfilename)
        if self.doctestname:
            L.append("The doctest %s, at the line:" % self.doctestname)
            L.append("    >>> %s" % self.doctestline)
        if self.requesturl:
            L.append('request url: %s' % self.requesturl)
        return '\n'.join(L)

# PageTemplateFile has .filename.
from z3c.ptcompat import (
    PageTemplateFile,
    ViewPageTemplateFile,
    )

# PythonExpr has .text, the text of the expression.
from zope.tales.pythonexpr import PythonExpr

# TrustedZopeContext has self.contexts, a dict with template, view, context,
# request, etc.
from zope.pagetemplate.engine import TrustedZopeContext

# TALInterpreter has self.sourceFile, a filename of a page template.
from zope.tal.talinterpreter import TALInterpreter

from zope.browserpage.simpleviewclass import simple

def find_important_info():
    stack = inspect.stack()
    try:
        important_classes = set([
            PythonExpr,
            TrustedZopeContext,
            TALInterpreter,
            ViewPageTemplateFile,
            simple
            ])
        important_objects = {}
        metadata = {}  # cls -> (filename, lineno, funcname)

        for frame, filename, lineno, func_name, context, lineidx in stack:
            try:
                if (filename.startswith('<doctest ') and
                    "doctest" not in important_objects):
                    # Very fragile inspection of the state of the doctest
                    # runner.  So, enclosed in a try-except so it will at
                    # least fail gracefully if it fails.
                    try:
                        line = frame.f_back.f_locals['example'].source
                    except KeyboardInterrupt:
                        pass
                    except Exception:
                        line = "# cannot get line of code"
                    important_objects["doctest"] = (filename, line)
                    metadata["doctest"] = (filename, lineno, func_name)
                if 'self' in frame.f_locals:
                    fself = frame.f_locals['self']
                    for cls in list(important_classes):
                        if isinstance(fself, cls):
                            important_objects[cls] = fself
                            metadata[cls] = (filename, lineno, func_name)
                            important_classes.remove(cls)
            finally:
                del frame
    finally:
        del stack

    expressiontext = ''
    if PythonExpr in important_objects:
        expressiontext = important_objects[PythonExpr].text

    viewclassname = ''
    viewclassfilename = ''
    viewclasslineno = ''
    viewclassfunc = ''
    doctestname = ''
    doctestline = ''
    if simple in important_objects:
        cls = important_objects[simple].__class__
        if cls is not simple:
            viewclassname = cls.__mro__[1].__name__
            viewclassfilename, viewclasslineno, viewclassfunc = (
                metadata[simple])

    templatefilename = ''
    if ViewPageTemplateFile in important_objects:
        templatefilename = important_objects[ViewPageTemplateFile].filename
        templatefilename = templatefilename.split('/')[-1]

    requesturl = ''
    if TrustedZopeContext in important_objects:
        ptcontexts = important_objects[TrustedZopeContext].contexts
        requesturl = ptcontexts['request'].getURL()

    if "doctest" in important_objects:
        doctestname, doctestline = important_objects["doctest"]
    return ImportantInfo(expressiontext, viewclassname, templatefilename,
        requesturl, viewclassfilename, viewclasslineno, viewclassfunc,
        doctestname, doctestline)

need_page_titles = []
no_order_by = []

# Maps (category, filename, lineno) to WarningReport
other_warnings = {}

old_show_warning = warnings.showwarning
def launchpad_showwarning(message, category, filename, lineno, file=None,
                          line=None):
    if file is None:
        file = sys.stderr
    stream = StringIO.StringIO()
    old_show_warning(message, category, filename, lineno, stream, line=line)
    warning_message = stream.getvalue()
    important_info = find_important_info()

    if isinstance(message, UserWarning):
        args = message.args
        if args:
            arg = args[0]
            if arg.startswith('No page title in '):
                global need_page_titles
                need_page_titles.append(arg)
                return
            if arg == 'Getting a slice of an unordered set is unpredictable.':
                # find the page template and view class, if any
                # show these, plus the request.
                global no_order_by
                no_order_by.append(
                    WarningReport(warning_message, important_info)
                    )
                return
    other_warnings[(category, filename, lineno)] = WarningReport(
        warning_message, important_info)

def report_need_page_titles():
    global need_page_titles
    if need_page_titles:
        print
        print "The following pages need titles."
        for message in need_page_titles:
            print "   ", message

def report_no_order_by():
    global no_order_by
    if no_order_by:
        print
        print ("The following code has issues with"
               " ambiguous select results ordering.")
        for report in no_order_by:
            print
            print report

def report_other_warnings():
    global other_warnings
    if other_warnings:
        print
        print "General warnings."
        for warninginfo in other_warnings.itervalues():
            print
            print warninginfo

def report_warnings():
    report_need_page_titles()
    report_no_order_by()
    report_other_warnings()

def install_warning_handler():
    warnings.showwarning = launchpad_showwarning
    atexit.register(report_warnings)
