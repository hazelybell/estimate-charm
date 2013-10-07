# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Standard validators.

validators in here should be dead simple, as they are mirrored inside
PostgreSQL as stored procedures.

See README.txt for discussion
"""

__metaclass__ = type

from zope.formlib.exception import (
    WidgetInputErrorView as Z3WidgetInputErrorView,
    )
from zope.formlib.interfaces import IWidgetInputError
from zope.interface import (
    implements,
    Interface,
    )
from zope.schema.interfaces import ValidationError

from lp.services.webapp.escaping import html_escape


__all__ = ['LaunchpadValidationError']


class ILaunchpadValidationError(IWidgetInputError):
    def snippet():
        """Render as an HTML error message, as per IWidgetInputErrorView"""


class LaunchpadValidationError(ValidationError):
    """A LaunchpadValidationError may be raised from a schema field
    validation method.

    It is used return a meaningful error message to the user. The message
    may contain XHTML markup suitable for inclusion in an inline tag
    such as <span>.

    >>> LaunchpadValidationError('<br/>oops').snippet()
    u'&lt;br/&gt;oops'

    >>> from lp.services.webapp.escaping import structured
    >>> LaunchpadValidationError(
    ...     structured('<a title="%s">Ok</a>', '<evil/>')).snippet()
    u'<a title="&lt;evil/&gt;">Ok</a>'
    """
    implements(ILaunchpadValidationError)

    def __init__(self, message, already_escaped=False):
        """Create a LaunchpadValidationError instance.

        `message` should be an HTML quoted string. Extra arguments
        will be HTML quoted and merged into the message using standard
        Python string interpolation.
        """
        if not already_escaped:
            message = html_escape(message)
        # We stuff our message into self.args (a list) because this
        # is an exception, and exceptions use self.args (and the form
        # machinery expects it to be here).
        self.args = [message]

    def snippet(self):
        """Render as an HTML error message, as per IWidgetInputErrorView."""
        return self.args[0]

    def doc(self):
        """Some code expect the error message being rendered by this
        method.
        """
        return self.snippet()


class ILaunchpadWidgetInputErrorView(Interface):

    def snippet():
        """Convert a widget input error to an html snippet

        If the error implements provides a snippet() method, just return it.
        Otherwise, fall back to the default Z3 mechanism
        """


class WidgetInputErrorView(Z3WidgetInputErrorView):
    """Display an input error as a snippet of text.

    This is used to override the default Z3 one which blindly HTML encodes
    error messages.
    """
    implements(ILaunchpadWidgetInputErrorView)

    def snippet(self):
        """Convert a widget input error to an html snippet

        If the error implements provides a snippet() method, just return it.
        Otherwise return the error message.

        >>> from zope.formlib.interfaces import WidgetInputError
        >>> from lp.services.webapp.escaping import structured
        >>> bold_error = LaunchpadValidationError(structured("<b>Foo</b>"))
        >>> err = WidgetInputError("foo", "Foo", bold_error)
        >>> view = WidgetInputErrorView(err, None)
        >>> view.snippet()
        u'<b>Foo</b>'

        >>> class TooSmallError(object):
        ...     def doc(self):
        ...         return "Foo input < 1"
        >>> err = WidgetInputError("foo", "Foo", TooSmallError())
        >>> view = WidgetInputErrorView(err, None)
        >>> view.snippet()
        u'Foo input &lt; 1'
        """
        if (hasattr(self.context, 'errors') and
                ILaunchpadValidationError.providedBy(self.context.errors)):
            return self.context.errors.snippet()
        return html_escape(self.context.doc())
