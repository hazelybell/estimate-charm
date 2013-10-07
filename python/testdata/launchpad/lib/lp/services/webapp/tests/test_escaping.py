# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from lp.services.webapp.escaping import (
    html_escape,
    html_unescape,
    structured,
    )
from lp.testing import TestCase


class TestHtmlEscape(TestCase):

    def test_escapes_special_characters(self):
        # &, <, >, " and ' are transformed into equivalent entity
        # references, as they hold special significance in HTML.
        self.assertEqual('&amp;&lt;&gt;&quot;&#x27;', html_escape('&<>"\''))

    def test_structured_passed_through(self):
        # An IStructuredString escapes to the value of its .escapedtext.
        struct = structured('<b>%s</b>', '<i>It works!</i>')
        self.assertEqual(
            '<b>&lt;i&gt;It works!&lt;/i&gt;</b>', html_escape(struct))

    def test_unescape_works(self):
        # html_unescape undoes the 5 entity transformations performed by
        # html_escape.
        self.assertEqual('&<>"\'', html_unescape('&amp;&lt;&gt;&quot;&#x27;'))


class TestStructured(TestCase):

    def test_escapes_args(self):
        # Normal string arguments are escaped before they're inserted
        # into the formatted string.
        struct = structured(
            '<b>%s</b> %s', 'I am <i>escaped</i>!', '"& I\'m too."')
        self.assertEqual(
            '<b>I am &lt;i&gt;escaped&lt;/i&gt;!</b> '
            '&quot;&amp; I&#x27;m too.&quot;',
            struct.escapedtext)

    def test_structured_args_passed_through(self):
        # If an IStructuredString is used as an argument, its
        # .escapedtext is included verbatim. Other arguments are still
        # escaped.
        inner = structured('<b>%s</b>', '<i>some text</i>')
        outer = structured('<li>%s: %s</li>', 'First & last', inner)
        self.assertEqual(
            '<li>First &amp; last: <b>&lt;i&gt;some text&lt;/i&gt;</b></li>',
            outer.escapedtext)

    def test_kwargs(self):
        # Keyword args work too.
        inner = structured('<b>%s</b>', '<i>some text</i>')
        outer = structured(
            '<li>%(capt)s: %(body)s</li>', capt='First & last', body=inner)
        self.assertEqual(
            '<li>First &amp; last: <b>&lt;i&gt;some text&lt;/i&gt;</b></li>',
            outer.escapedtext)

    def test_mixing_kwargs_is_illegal(self):
        # Passing a combination of args and kwargs is illegal.
        self.assertRaises(
            TypeError, structured, '%s %(foo)s', 'bar', foo='foo')
