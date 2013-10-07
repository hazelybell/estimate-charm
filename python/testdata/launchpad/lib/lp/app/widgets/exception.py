# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from z3c.ptcompat import ViewPageTemplateFile
from zope.formlib.interfaces import (
    IWidgetInputError,
    IWidgetInputErrorView,
    WidgetInputError as _WidgetInputError,
    )
from zope.interface import implements


class WidgetInputError(_WidgetInputError):
    """A customized WidgetInputError to work around a bug in Z3
    (The snippet method fails if errors is a list of ValidationError objects)

    TODO: Pull this out after next sync with upstream Zope3 - this is now
    fixed upstream -- StuartBishop 20050520

    """
    implements(IWidgetInputError)

    def __init__(self, field_name, widget_title, errors):
        """Initialize Error

        `errors` is a ``ValidationError`` or a list of ValidationError objects

        """
        if not isinstance(errors, list):
            errors = [errors]
        _WidgetInputError.__init__(self, field_name, widget_title, errors)

    def doc(self):
        """Returns a string that represents the error message."""
        return ', '.join([v.doc() for v in self.errors])


class WidgetInputErrorView(object):
    """Rendering of IWidgetInputError"""
    implements(IWidgetInputErrorView)

    def __init__(self, context, request):
        self.context = context
        self.request = request

    snippet = ViewPageTemplateFile('templates/error.pt')
