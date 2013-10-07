# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'html_escape',
    'html_unescape',
    'structured',
    ]

from lazr.restful.utils import get_current_browser_request
from zope.i18n import (
    Message,
    translate,
    )
from zope.interface import implements

from lp.services.webapp.interfaces import IStructuredString


HTML_REPLACEMENTS = (
    ('&', '&amp;'), ('<', '&lt;'), ('>', '&gt;'), ('"', '&quot;'),
    ("'", '&#x27;'))


def html_escape(message):
    """Performs translation and sanitizes any HTML present in the message.

    DO NOT USE THIS DIRECTLY UNLESS YOU ARE SURE YOU NEED TO.

    There is rarely a good reason to use this directly instead of going via
    structured().

    A plain string message will be sanitized ("&", "<" and ">" are
    converted to HTML-safe sequences).  Passing a message that
    provides the `IStructuredString` interface will return a unicode
    string that has been properly escaped.  Passing an instance of a
    Zope internationalized message will cause the message to be
    translated, then santizied.

    :param message: This may be a string, `zope.i18n.Message`,
        `zope.i18n.MessageID`, or an instance of `IStructuredString`.
    """
    if IStructuredString.providedBy(message):
        return message.escapedtext
    else:
        # It is possible that the message is wrapped in an
        # internationalized object, so we need to translate it
        # first. See bug #54987.
        raw = unicode(translate_if_i18n(message))
        for needle, replacement in HTML_REPLACEMENTS:
            raw = raw.replace(needle, replacement)
        return raw


def html_unescape(message):
    """Reverses the transformation performed by html_escape.

    DO NOT USE THIS EXCEPT IN LEGACY CODE.

    Converts the 5 entities references produced by html_escape into their
    original form. There is almost no reason to ever do this.
    """
    s = message.replace('&lt;', '<')
    s = s.replace('&gt;', '>')
    s = s.replace('&quot;', '"')
    s = s.replace('&#x27;', "'")
    s = s.replace('&amp;', '&')
    return s


def translate_if_i18n(obj_or_msgid):
    """Translate an internationalized object, returning the result.

    Returns any other type of object untouched.
    """
    if isinstance(obj_or_msgid, Message):
        return translate(obj_or_msgid, context=get_current_browser_request())
    else:
        # Just text (or something unknown).
        return obj_or_msgid


class structured:

    implements(IStructuredString)

    def __init__(self, text, *reps, **kwreps):
        text = unicode(translate_if_i18n(text))
        self.text = text
        if reps and kwreps:
            raise TypeError(
                "You must provide either positional arguments or keyword "
                "arguments to structured(), not both.")
        if reps:
            self.escapedtext = text % tuple(html_escape(rep) for rep in reps)
        elif kwreps:
            self.escapedtext = text % dict(
                (k, html_escape(v)) for k, v in kwreps.iteritems())
        else:
            self.escapedtext = text

    def __repr__(self):
        return "<structured-string '%s'>" % self.text
