# Copyright 2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Mock Swift test fixture."""

__metaclass__ = type
__all__ = ['SwiftFixture']

import os.path
import shutil
import socket
import tempfile
import time

from fixtures import FunctionFixture
from s4 import hollow
from swiftclient import client as swiftclient
import testtools.content
import testtools.content_type
from txfixtures.tachandler import TacTestFixture

from lp.services.config import config


class SwiftFixture(TacTestFixture):

    tacfile = os.path.join(os.path.dirname(__file__), 'hollow.tac')
    pidfile = None
    logfile = None
    root = None
    daemon_port = None

    def setUp(self, spew=False, umask=None):
        # Pick a random, free port.
        if self.daemon_port is None:
            sock = socket.socket()
            sock.bind(('', 0))
            self.daemon_port = sock.getsockname()[1]
            sock.close()
            self.logfile = os.path.join(
                config.root, 'logs', 'hollow-%s.log' % self.daemon_port)
            self.pidfile = os.path.join(
                config.root, 'logs', 'hollow-%s.pid' % self.daemon_port)
        assert self.daemon_port is not None

        super(SwiftFixture, self).setUp(
            spew, umask,
            os.path.join(config.root, 'bin', 'py'),
            os.path.join(config.root, 'bin', 'twistd'))

    def cleanUp(self):
        if self.logfile is not None and os.path.exists(self.logfile):
            self.addDetail(
                'log-file', testtools.content.content_from_stream(
                    open(self.logfile, 'r'), testtools.content_type.UTF8_TEXT))
            os.unlink(self.logfile)
        super(SwiftFixture, self).cleanUp()

    def setUpRoot(self):
        # Create a root directory.
        if self.root is None or not os.path.isdir(self.root):
            root_fixture = FunctionFixture(tempfile.mkdtemp, shutil.rmtree)
            self.useFixture(root_fixture)
            self.root = root_fixture.fn_result
            os.chmod(self.root, 0o700)
        assert os.path.isdir(self.root)

        # Pass on options to the daemon.
        os.environ['HOLLOW_ROOT'] = self.root
        os.environ['HOLLOW_PORT'] = str(self.daemon_port)

    def connect(
        self, tenant_name=hollow.DEFAULT_TENANT_NAME,
        username=hollow.DEFAULT_USERNAME, password=hollow.DEFAULT_PASSWORD):
        """Return a valid connection to our mock Swift"""
        port = self.daemon_port
        client = swiftclient.Connection(
            authurl="http://localhost:%d/keystone/v2.0/" % port,
            auth_version="2.0", tenant_name=tenant_name,
            user=username, key=password,
            retries=0, insecure=True)
        return client

    def startup(self):
        self.setUp()

    def shutdown(self):
        self.cleanUp()
        while self._hasDaemonStarted():
            time.sleep(0.1)
