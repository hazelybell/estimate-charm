# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Simple paste-y session manager tuned for the needs of launchpad-loggerhead.
"""

import pickle

from paste.auth.cookie import (
    AuthCookieHandler,
    AuthCookieSigner,
    )


class MyAuthCookieSigner(AuthCookieSigner):
    """Fix a bug in AuthCookieSigner."""

    def sign(self, content):
        # XXX 2008-01-13 Michael Hudson: paste.auth.cookie generates bogus
        # cookies when the value is long:
        # http://trac.pythonpaste.org/pythonpaste/ticket/257.  This is fixed
        # now, so when a new version is released and packaged we can remove
        # this class.
        r = AuthCookieSigner.sign(self, content)
        return r.replace('\n', '')


class SessionHandler(object):
    """Middleware that provides a cookie-based session.

    The session dict is stored, pickled (and HMACed), in a cookie, so don't
    store very much in the session!
    """

    def __init__(self, application, session_var, secret=None):
        """Initialize a SessionHandler instance.

        :param application: This is the wrapped application which will have
            access to the ``environ[session_var]`` dictionary managed by this
            middleware.
        :param session_var: The key under which to store the session
            dictionary in the environment.
        :param secret: A secret value used for signing the cookie.  If not
            supplied, a new secret will be used for each instantiation of the
            SessionHandler.
        """
        self.application = application
        self.cookie_handler = AuthCookieHandler(
            self._process, scanlist=[session_var],
            signer=MyAuthCookieSigner(secret))
        self.session_var = session_var

    def __call__(self, environ, start_response):
        # We need to put the request through the cookie handler first, so we
        # can access the validated string in the environ in `_process` below.
        return self.cookie_handler(environ, start_response)

    def _process(self, environ, start_response):
        """Process a request.

        AuthCookieHandler takes care of getting the text value of the session
        in and out of the cookie (and validating the text using HMAC) so we
        just need to convert that string to and from a real dictionary using
        pickle.
        """
        if self.session_var in environ:
            session = pickle.loads(environ[self.session_var])
        else:
            session = {}
        existed = bool(session)
        environ[self.session_var] = session
        def response_hook(status, response_headers, exc_info=None):
            session = environ.pop(self.session_var)
            # paste.auth.cookie does not delete cookies (see
            # http://trac.pythonpaste.org/pythonpaste/ticket/139).  A
            # reasonable workaround is to make the value empty.  Therefore,
            # we explicitly set the value in the session (to be encrypted)
            # if the value is non-empty *or* if it was non-empty at the start
            # of the request.
            if existed or session:
                environ[self.session_var] = pickle.dumps(session)
            return start_response(status, response_headers, exc_info)
        return self.application(environ, response_hook)
