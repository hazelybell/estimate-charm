# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Common code for the puller tests."""

__metaclass__ = type

import os
import shutil
import socket
from StringIO import StringIO

from bzrlib.tests import TestCaseWithTransport
from bzrlib.tests.http_server import (
    HttpServer,
    TestingHTTPServer,
    TestingThreadingHTTPServer,
    )

from lp.codehosting.puller.worker import (
    BranchMirrorer,
    BranchMirrorerPolicy,
    PullerWorker,
    PullerWorkerProtocol,
    )
from lp.codehosting.safe_open import AcceptAnythingPolicy
from lp.codehosting.tests.helpers import LoomTestMixin
from lp.testing import TestCaseWithFactory


class AcceptAnythingBranchMirrorerPolicy(AcceptAnythingPolicy,
                                         BranchMirrorerPolicy):
    """A branch mirror policy that supports mirrorring from anywhere."""


class PullerWorkerMixin:
    """Mixin for tests that want to make PullerWorker objects.

    Assumes that it is mixed into a class that runs in a temporary directory,
    such as `TestCaseInTempDir` and that `get_transport` is provided as a
    method.
    """

    def makePullerWorker(self, src_dir=None, dest_dir=None, branch_type=None,
                         default_stacked_on_url=None, protocol=None,
                         policy=None):
        """Anonymous creation method for PullerWorker."""
        if protocol is None:
            protocol = PullerWorkerProtocol(StringIO())
        if branch_type is None:
            if policy is None:
                policy = AcceptAnythingBranchMirrorerPolicy()
            opener = BranchMirrorer(policy, protocol)
        else:
            opener = None
        return PullerWorker(
            src_dir, dest_dir, branch_id=1, unique_name='foo/bar/baz',
            branch_type=branch_type,
            default_stacked_on_url=default_stacked_on_url, protocol=protocol,
            branch_mirrorer=opener)


# XXX MichaelHudson, bug=564375: With changes to the SocketServer module in
# Python 2.6 the thread created in serveOverHTTP cannot be joined, because
# HttpServer.stop_server doesn't do enough to get the thread out of the select
# call in SocketServer.BaseServer.handle_request().  So what follows is
# slightly horrible code to use the version of handle_request from Python 2.5.
def fixed_handle_request(self):
    """Handle one request, possibly blocking. """
    try:
        request, client_address = self.get_request()
    except socket.error:
        return
    if self.verify_request(request, client_address):
        try:
            self.process_request(request, client_address)
        except:
            self.handle_error(request, client_address)
            self.close_request(request)


class FixedTHS(TestingHTTPServer):
    handle_request = fixed_handle_request


class FixedTTHS(TestingThreadingHTTPServer):
    handle_request = fixed_handle_request


class FixedHttpServer(HttpServer):
    http_server_class = {'HTTP/1.0': FixedTHS, 'HTTP/1.1': FixedTTHS}


class PullerBranchTestCase(TestCaseWithTransport, TestCaseWithFactory,
                           LoomTestMixin):
    """Some useful code for the more-integration-y puller tests."""

    def setUp(self):
        super(PullerBranchTestCase, self).setUp()
        self.disable_directory_isolation()

    def makeCleanDirectory(self, path):
        """Guarantee an empty branch upload area."""
        if os.path.exists(path):
            shutil.rmtree(path)
        os.makedirs(path)
        self.addCleanup(shutil.rmtree, path)

    def serveOverHTTP(self):
        """Serve the current directory over HTTP, returning the server URL."""
        http_server = FixedHttpServer()
        http_server.start_server()
        # Join cleanup added before the tearDown so the tearDown is executed
        # first as this tells the thread to die.  We then join explicitly as
        # the HttpServer.tearDown does not join.  There is a check in the
        # BaseLayer to make sure that threads are not left behind by the
        # tests, and the default behaviour of the HttpServer is to use daemon
        # threads and let the garbage collector get them, however this causes
        # issues with the test runner.
        self.addCleanup(http_server._server_thread.join)
        self.addCleanup(http_server.stop_server)
        return http_server.get_url().rstrip('/')
