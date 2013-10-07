# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""A real, socket connecting browser.

This browser performs actual socket connections to a real HTTP server.  This
is used in tests which utilize the AppServerLayer to run the app server in a
child process.  The Zope testing browser fakes its connections in-process, so
that's not good enough.

The browser provided here extends `zope.testbrowser.testing.Browser` by
providing a close() method that delegates to the underlying mechanize browser,
and it tracks all Browser instances to ensure that they are closed.  This
latter prevents open socket leaks even when the doctest doesn't explicitly
close or delete the browser instance.
"""
from lazr.uri._uri import URI


__metaclass__ = type
__all__ = [
    'Browser',
    'setUp',
    'tearDown',
    ]


import base64
import urllib2
import weakref

import transaction
from zope.testbrowser.browser import (
    Browser as _Browser,
    fix_exception_name,
    )

from lp.testing.pages import (
    extract_text,
    find_main_content,
    find_tag_by_id,
    print_feedback_messages,
    )


class SocketClosingOnErrorHandler(urllib2.BaseHandler):
    """A handler that ensures that the socket gets closed on errors.

    Interestingly enough <wink> without this, a 404 will cause mechanize to
    leak open socket objects.
    """
    # Ensure that this handler is the first default error handler to execute,
    # because right after this, the built-in default handler will raise an
    # exception.
    handler_order = 0

    # Copy signature from base class.
    def http_error_default(self, req, fp, code, msg, hdrs):
        """See `urllib2.BaseHandler`."""
        fp.close()


# To ensure that the mechanize browser doesn't leak socket connections past
# the end of the test, we manage a set of weak references to live browser
# objects.  The layer can then call a function here to ensure that all live
# browsers get properly closed.
_live_browser_set = set()


class Browser(_Browser):
    """A browser subclass that knows about basic auth."""

    def __init__(self, auth=None, mech_browser=None):
        super(Browser, self).__init__(mech_browser=mech_browser)
        # We have to add the error handler to the mechanize browser underlying
        # the Zope browser, because it's the former that's actually doing all
        # the work.
        self.mech_browser.add_handler(SocketClosingOnErrorHandler())
        if auth:
            # Unlike the higher level Zope test browser, we actually have to
            # encode the basic auth information.
            userpass = base64.encodestring(auth)
            self.addHeader('Authorization', 'Basic ' + userpass)
        _live_browser_set.add(weakref.ref(self, self._refclose))

    def _refclose(self, obj):
        """For weak reference cleanup."""
        self.close()

    def close(self):
        """Yay!  Zope browsers don't have a close() method."""
        self.mech_browser.close()

    def _changed(self):
        """Ensure the current transaction is committed.

        Because this browser is used in the AppServerLayer where it talks
        real-HTTP to a child process, we need to ensure that the parent
        process also gets its current transaction in sync with the child's
        changes.  The easiest way to do that is to just commit the current
        transaction.
        """
        super(Browser, self)._changed()
        transaction.commit()

    def _clickSubmit(self, form, control, coord):
        # XXX gary 2010-03-08 bug=98437
        # This change is taken from
        # https://bugs.launchpad.net/zope3/+bug/98437/comments/9 .  It
        # should be pushed upstream, per that comment.
        labels = control.get_labels()
        if labels:
            label = labels[0].text
        else:
            label = None
        self.mech_browser.form = form
        self._start_timer()
        try:
            self.mech_browser.submit(id=control.id, name=control.name,
                label=label, coord=coord)
        except Exception as e:
            fix_exception_name(e)
            raise
        self._stop_timer()

    @property
    def vhost(self):
        uri = URI(self.url)
        return '%s://%s' % (uri.scheme, uri.host)

    @property
    def rooturl(self):
        uri = URI(self.url)
        return '%s://%s:%s' % (uri.scheme, uri.host, uri.port)

    @property
    def urlpath(self):
        uri = URI(self.url)
        return uri.path


def setUp(test):
    """Set up appserver tests."""
    test.globs['Browser'] = Browser
    test.globs['browser'] = Browser()
    test.globs['find_tag_by_id'] = find_tag_by_id
    test.globs['find_main_content'] = find_main_content
    test.globs['print_feedback_messages'] = print_feedback_messages
    test.globs['extract_text'] = extract_text


def tearDown(test):
    """Tear down appserver tests."""
    for ref in _live_browser_set:
        browser = ref()
        if browser is not None:
            browser.close()
