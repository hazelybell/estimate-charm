# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""timeout.py tests.
"""

__metaclass__ = type

from cStringIO import StringIO
from SimpleXMLRPCServer import (
    SimpleXMLRPCRequestHandler,
    SimpleXMLRPCServer,
    )
import socket
from textwrap import dedent
import threading
import time
import urllib2
import xmlrpclib

from zope.interface import implements

from lp.services.log.logger import FakeLogger
from lp.services.timeout import (
    get_default_timeout_function,
    set_default_timeout_function,
    TimeoutError,
    TransportWithTimeout,
    urlfetch,
    with_timeout,
    )
from lp.testing import TestCase
from lp.testing.layers import BaseLayer


@with_timeout()
def no_default_timeout(): pass


class EchoOrWaitXMLRPCReqHandler(SimpleXMLRPCRequestHandler):
    """The request handler will respond to 'echo' requests normally but will
    hang indefinitely for all other requests.  This allows us to show a
    successful request followed by one that times out.
    """
    def _dispatch(self, method, params):
        if method == 'echo':
            return params[0]
        else:
            # Will hang until the client closes its end of the socket.
            self.connection.settimeout(None)
            self.connection.recv(1024)


class MySimpleXMLRPCServer(SimpleXMLRPCServer):
    """Create a simple XMLRPC server to listen for requests."""
    allow_reuse_address = True
    def serve_2_requests(self):
        for i in range(2):
            self.handle_request()
        self.server_close()
    def handle_error(self, request, address):
        pass


class TestTimeout(TestCase):

    def test_timeout_succeeds(self):
        """After decorating a function 'with_timeout', as long as that function
        finishes before the supplied timeout, it should function normally.
        """
        wait_evt = threading.Event()
        @with_timeout(timeout=0.5)
        def wait_100ms():
            """Function that waits for a supplied number of seconds."""
            wait_evt.wait(0.1)
            return "Succeeded."
        self.assertEqual("Succeeded.", wait_100ms())

    def test_timeout_overrun(self):
        """If the operation cannot be completed in the allotted time, a
        TimeoutError is raised.
        """
        # We use interlocked events to help ensure the thread will have exited
        # by the time this thread returns from the test.
        # The wait_for_event thread waits for us to set the event (though it
        # gets a timeout in the middle), and then we wait for it to wake up and
        # inform us that it is about to exit.
        wait_evt = threading.Event()
        stopping_evt = threading.Event()
        @with_timeout(timeout=0.5)
        def wait_for_event():
            """Function that waits for a supplied number of seconds."""
            wait_evt.wait()
            stopping_evt.set()
        self.assertRaises(TimeoutError, wait_for_event)
        wait_evt.set()
        stopping_evt.wait()

    def test_timeout_with_failing_function(self):
        """Other exceptions are reported correctly to the caller."""
        @with_timeout(timeout=0.5)
        def call_with_error():
            raise RuntimeError("This exception will be raised in the caller.")
        self.assertRaises(RuntimeError, call_with_error)

    def test_timeout_with_cleanup(self):
        """Since we want to time out operations involving an external resource
        (subprocess, remote site), we need a way to clean-up these resources
        once they time out. To this end, the with_timeout decorator accepts a
        callable parameter (named 'cleanup') that will be invoked if the
        operation times out.
        """
        old_timeout = socket.getdefaulttimeout()
        self.addCleanup(socket.setdefaulttimeout, old_timeout)
        socket.setdefaulttimeout(5)
        sockets = socket.socketpair()
        closed = []
        def close_socket():
            closed.append(True)
            sockets[0].shutdown(socket.SHUT_RDWR)

        @with_timeout(cleanup=close_socket, timeout=0.5)
        def block():
            """This will block indefinitely."""
            sockets[0].recv(1024)
        self.assertRaises(TimeoutError, block)
        self.assertEqual([True], closed)

    def test_timeout_with_string_cleanup(self):
        """The cleanup parameter can also be a string in which case it will be
        interpreted as the name of an instance method.
        """
        class expirable_socket(object):
            def __init__(self):
                self.closed = False
                self.sockets = socket.socketpair()

            @with_timeout(cleanup="shutdown", timeout=0.5)
            def block(self):
                self.sockets[0].recv(1024)

            def shutdown(self):
                self.closed = True
                self.sockets[0].shutdown(socket.SHUT_RDWR)

        a_socket = expirable_socket()
        self.assertRaises(TimeoutError, a_socket.block)
        self.assertIs(True, a_socket.closed)

    def test_invalid_string_without_method(self):
        """It's an error to use a string cleanup when the function isn't a
        method."""
        def do_definition():
            @with_timeout(cleanup='not_a_method', timeout=0.5)
            def a_function(): pass
        self.assertRaises(TypeError, do_definition)

    def test_timeout_uses_default(self):
        """If the timeout parameter isn't provided, it will default to the value
        returned by the function installed as "default_timeout_function". A
        function is used because it's useful for the timeout value to be
        determined dynamically. For example, if you want to limit the
        overall processing to 30s and you already did 14s, you want that timeout
        to be 16s.

        By default, there is no default_timeout_function.
        """
        self.assertIs(None, get_default_timeout_function())

    def test_timeout_requires_value_when_no_default(self):
        """When there is no default timeout function, it's an error not to
        provide a default timeout argument.
        """
        e = self.assertRaises(AssertionError, no_default_timeout)
        self.assertEqual(
            "no timeout set and there is no default timeout function.",
            str(e))

    def test_set_default_timeout(self):
        """the set_default_timeout_function() takes a function that should return
        the number of seconds to wait.
        """
        using_default = []
        def my_default_timeout():
            using_default.append(True)
            return 1
        set_default_timeout_function(my_default_timeout)
        self.addCleanup(set_default_timeout_function, None)
        no_default_timeout()
        self.assertEqual([True], using_default)

    def make_test_socket(self):
        """One common use case for timing out is when making an HTTP request to
        an external site to fetch content. To this end, the timeout module has
        a urlfetch() function that retrieve a URL using custom urllib2 handlers
        that will timeout using the default timeout function and clean-up the
        socket properly.
        """
        sock = socket.socket()
        sock.settimeout(2)
        sock.bind(('127.0.0.1', 0))

        # Use 1s as default timeout.
        set_default_timeout_function(lambda: 1)
        self.addCleanup(set_default_timeout_function, None)
        http_server_url = 'http://%s:%d/' % sock.getsockname()
        return sock, http_server_url

    def test_urlfetch_raises_urllib2_exceptions(self):
        """Normal urllib2 exceptions are raised."""
        sock, http_server_url = self.make_test_socket()

        e = self.assertRaises(urllib2.URLError, urlfetch, http_server_url)
        self.assertIn('Connection refused', str(e))

    def test_urlfetch_timeout_after_listen(self):
        """After the listen() is called, connections will hang until accept()
        is called, so a TimeoutError will be raised.
        """
        sock, http_server_url = self.make_test_socket()
        sock.listen(1)
        self.assertRaises(TimeoutError, urlfetch, http_server_url)

        # The client socket was closed properly, as we can see by calling
        # recv() twice on the connected socket. The first recv() returns the
        # request data sent by the client, the second one will block until the
        # client closes its end of the connection. If the client closes its
        # socket, '' is received, otherwise a socket timeout will occur.
        client_sock, client_addr = sock.accept()
        self.assertStartsWith(client_sock.recv(1024), "GET / HTTP/1.1")
        self.assertEqual('', client_sock.recv(1024))

    def test_urlfetch_slow_server(self):
        """The function also times out if the server replies very slowly.
        (Do the server part in a separate thread.)
        """
        sock, http_server_url = self.make_test_socket()
        sock.listen(1)
        stop_event = threading.Event()
        def slow_reply():
            (client_sock, client_addr) = sock.accept()
            content = 'You are veeeeryyy patient!'
            client_sock.sendall(dedent("""\
                HTTP/1.0 200 Ok
                Content-Type: text/plain
                Content-Length: %d\n\n""" % len(content)))

            # Send the body of the reply very slowly, so that
            # it times out in read() and not urlopen.
            for c in content:
                client_sock.send(c)
                if stop_event.wait(0.05):
                    break
            client_sock.close()
        slow_thread = threading.Thread(target=slow_reply)
        slow_thread.start()
        saved_threads = set(threading.enumerate())
        self.assertRaises(TimeoutError, urlfetch, http_server_url)
        # Note that the cleanup also takes care of leaving no worker thread behind.
        remaining_threads = set(threading.enumerate()).difference(saved_threads)
        self.assertEqual(set(), remaining_threads)
        stop_event.set()
        slow_thread.join()

    def test_urlfetch_returns_the_content(self):
        """When the request succeeds, the result content is returned."""
        sock, http_server_url = self.make_test_socket()
        sock.listen(1)
        def success_result():
            (client_sock, client_addr) = sock.accept()
            client_sock.sendall(dedent("""\
                HTTP/1.0 200 Ok
                Content-Type: text/plain
                Content-Length: 8

                Success."""))
            client_sock.close()
        t = threading.Thread(target=success_result)
        t.start()
        self.assertEqual('Success.', urlfetch(http_server_url))
        t.join()

    def test_urlfetch_only_supports_http_urls(self):
        """urlfetch() only supports http urls:"""
        set_default_timeout_function(lambda: 1)
        self.addCleanup(set_default_timeout_function, None)
        e = self.assertRaises(AssertionError, urlfetch, 'ftp://localhost')
        self.assertEqual('only http is supported.', str(e))

    def test_xmlrpc_transport(self):
        """ Another use case for timeouts is communicating with external
        systems using XMLRPC.  In order to allow timeouts using XMLRPC we
        provide a transport that is timeout-aware.  The Transport is used for
        XMLRPC over HTTP.
        """
        # Create a socket bound to a random port, just to obtain a free port.
        set_default_timeout_function(lambda: 1)
        self.addCleanup(set_default_timeout_function, None)
        sock, http_server_url = self.make_test_socket()
        addr, port = sock.getsockname()
        sock.close()
        server = MySimpleXMLRPCServer(('127.0.0.1', port),
            requestHandler=EchoOrWaitXMLRPCReqHandler,
            logRequests=False)
        server_thread = threading.Thread(target=server.serve_2_requests)
        server_thread.start()
        proxy = xmlrpclib.ServerProxy(http_server_url,
                                      transport=TransportWithTimeout())
        self.assertEqual('Successful test message.',
                         proxy.echo('Successful test message.'))
        self.assertRaises(TimeoutError,
                          proxy.no_response, 'Unsuccessful test message.')
        server_thread.join()
