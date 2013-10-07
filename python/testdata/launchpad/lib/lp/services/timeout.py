# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Helpers to time out external operations."""

__metaclass__ = type
__all__ = [
    "get_default_timeout_function",
    "SafeTransportWithTimeout",
    "set_default_timeout_function",
    "TimeoutError",
    "TransportWithTimeout",
    "urlfetch",
    "with_timeout",
    ]

import httplib
import socket
import sys
from threading import Thread
import urllib2
from xmlrpclib import (
    SafeTransport,
    Transport,
    )


default_timeout_function = None


def get_default_timeout_function():
    """Return the function returning the default timeout value to use."""
    global default_timeout_function
    return default_timeout_function


def set_default_timeout_function(timeout_function):
    """Change the function returning the default timeout value to use."""
    global default_timeout_function
    default_timeout_function = timeout_function


class TimeoutError(Exception):
    """Exception raised when a function doesn't complete within time."""


class ThreadCapturingResult(Thread):
    """Thread subclass that saves the return value of its target.

    It also saves exceptions raised when invoking the target.
    """

    def __init__(self, target, args, kwargs, **opt):
        super(ThreadCapturingResult, self).__init__(**opt)
        self.target = target
        self.args = args
        self.kwargs = kwargs

    def run(self):
        """See `Thread`."""
        try:
            self.result = self.target(*self.args, **self.kwargs)
        except (SystemExit, KeyboardInterrupt):
            # Don't trap those.
            raise
        except Exception:
            self.exc_info = sys.exc_info()


class DefaultTimeout:
    """Descriptor returning the timeout computed by the default function."""

    def __get__(self, obj, type=None):
        global default_timeout_function
        if default_timeout_function is None:
            raise AssertionError(
                "no timeout set and there is no default timeout function.")
        return default_timeout_function()


class with_timeout:
    """Make sure the decorated function doesn't exceed a time out.

    This will execute the function in a separate thread. If the function
    doesn't complete in the timeout, a TimeoutError is raised. The clean-up
    function will be called to "stop" the thread. (If it's possible to do so.)
    """

    timeout = DefaultTimeout()

    def __init__(self, cleanup=None, timeout=None):
        """Creates the function decorator.

        :param cleanup: That may be a callable or a string. If it's a string,
            a method under that name will be looked up. That callable will
            be called if the timeout is exceeded.
        :param timeout: The number of seconds to wait for.
        """
        # If the cleanup function is specified by name, the function but be a
        # method, so defined in a class definition context.
        if isinstance(cleanup, basestring):
            frame = sys._getframe(1)
            f_locals = frame.f_locals

            # Try to make sure we were called from a class def.
            if f_locals is frame.f_globals or '__module__' not in f_locals:
                raise TypeError(
                    "when not wrapping a method, cleanup must be a callable.")
        self.cleanup = cleanup
        if timeout is not None:
            self.timeout = timeout

    def __call__(self, f):
        """Wraps the method."""
        def call_with_timeout(*args, **kwargs):
            # Ensure that we have a timeout before we start the thread
            timeout = self.timeout
            if getattr(timeout, '__call__', None):
                # timeout may be a method or a function on the calling
                # instance class.
                if args:
                    timeout = timeout(args[0])
                else:
                    timeout = timeout()
            t = ThreadCapturingResult(f, args, kwargs)
            t.start()
            t.join(timeout)
            if t.isAlive():
                if self.cleanup is not None:
                    if isinstance(self.cleanup, basestring):
                        # 'self' will be first positional argument.
                        getattr(args[0], self.cleanup)()
                    else:
                        self.cleanup()
                    # Collect cleaned-up worker thread.
                    t.join()
                raise TimeoutError("timeout exceeded.")
            if getattr(t, 'exc_info', None) is not None:
                exc_info = t.exc_info
                # Remove the cyclic reference for faster GC.
                del t.exc_info
                raise exc_info[0], exc_info[1], exc_info[2]
            return t.result

        return call_with_timeout


class CleanableHTTPHandler(urllib2.HTTPHandler):
    """Subclass of `urllib2.HTTPHandler` that can be cleaned-up."""

    def http_open(self, req):
        """See `urllib2.HTTPHandler`."""
        def connection_factory(*args, **kwargs):
            """Save the created connection so that we can clean it up."""
            self.__conn = httplib.HTTPConnection(*args, **kwargs)
            return self.__conn
        return self.do_open(connection_factory, req)

    def reset_connection(self):
        """Reset the underlying HTTP connection."""
        try:
            self.__conn.sock.shutdown(socket.SHUT_RDWR)
        except AttributeError:
            # It's possible that the other thread closed the socket
            # beforehand.
            pass
        self.__conn.close()


class URLFetcher:
    """Object fetching remote URLs with a time out."""

    @with_timeout(cleanup='cleanup')
    def fetch(self, url, data=None):
        """Fetch the URL using a custom HTTP handler supporting timeout."""
        assert url.startswith('http://'), "only http is supported."
        self.handler = CleanableHTTPHandler()
        opener = urllib2.build_opener(self.handler)
        return opener.open(url, data).read()

    def cleanup(self):
        """Reset the connection when the operation timed out."""
        self.handler.reset_connection()


def urlfetch(url, data=None):
    """Wrapper for `urllib2.urlopen()` that times out."""
    return URLFetcher().fetch(url, data)


class TransportWithTimeout(Transport):
    """Create a HTTP transport for XMLRPC with timeouts."""

    def make_connection(self, host):
        """Create the connection for the transport and save it."""
        self.conn = Transport.make_connection(self, host)
        return self.conn

    @with_timeout(cleanup='cleanup')
    def request(self, host, handler, request_body, verbose=0):
        """Make the request but using the with_timeout decorator."""
        return Transport.request(
            self, host, handler, request_body, verbose)

    def cleanup(self):
        """In the event of a timeout cleanup by closing the connection."""
        # py2.6 compatibility
        # In Python 2.6, xmlrpclib.Transport wraps its HTTPConnection in an
        # HTTP compatibility class. In 2.7 it just uses the conn directly.
        http_conn = getattr(self.conn, '_conn', self.conn)
        try:
            http_conn.sock.shutdown(socket.SHUT_RDWR)
        except AttributeError:
            # It's possible that the other thread closed the socket
            # beforehand.
            pass
        http_conn.close()


class SafeTransportWithTimeout(SafeTransport):
    """Create a HTTPS transport for XMLRPC with timeouts."""

    timeout = None

    def __init__(self, timeout=None):
        # Old style class call to super required.
        SafeTransport.__init__(self)
        self.timeout = timeout

    def make_connection(self, host):
        """Create the connection for the transport and save it."""
        self.conn = SafeTransport.make_connection(self, host)
        return self.conn

    @with_timeout(cleanup='cleanup', timeout=lambda self: self.timeout)
    def request(self, host, handler, request_body, verbose=0):
        """Make the request but using the with_timeout decorator."""
        return SafeTransport.request(
            self, host, handler, request_body, verbose)

    def cleanup(self):
        """In the event of a timeout cleanup by closing the connection."""
        try:
            self.conn._conn.sock.shutdown(socket.SHUT_RDWR)
        except AttributeError:
            # It's possible that the other thread closed the socket
            # beforehand.
            pass
        self.conn._conn.close()
