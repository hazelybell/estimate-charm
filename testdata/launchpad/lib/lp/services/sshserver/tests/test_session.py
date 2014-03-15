# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for generic SSH session support."""

__metaclass__ = type

from twisted.conch.interfaces import ISession
from twisted.conch.ssh import connection

from lp.services.sshserver.session import DoNothingSession
from lp.testing import TestCase


class MockSSHSession:
    """Just enough of SSHSession to allow checking of reporting to stderr."""

    def __init__(self, log):
        self.log = log

    def writeExtended(self, channel, data):
        self.log.append(('writeExtended', channel, data))


class MockProcessTransport:
    """Mock transport used to fake speaking with child processes that are
    mocked out in tests.
    """

    def __init__(self, executable):
        self._executable = executable
        self.log = []
        self.session = MockSSHSession(self.log)

    def closeStdin(self):
        self.log.append(('closeStdin',))

    def loseConnection(self):
        self.log.append(('loseConnection',))

    def signalProcess(self, signal):
        self.log.append(('signalProcess', signal))

    def write(self, data):
        self.log.append(('write', data))


class TestDoNothing(TestCase):
    """Tests for DoNothingSession."""

    def setUp(self):
        super(TestDoNothing, self).setUp()
        self.session = DoNothingSession(None)

    def test_getPtyIsANoOp(self):
        # getPty is called on the way to establishing a shell. Since we don't
        # give out shells, it should be a no-op. Raising an exception would
        # log an OOPS, so we won't do that.
        self.assertEqual(None, self.session.getPty(None, None, None))

    def test_openShellNotImplemented(self):
        # openShell closes the connection.
        protocol = MockProcessTransport('bash')
        self.session.openShell(protocol)
        self.assertEqual(
            [('writeExtended', connection.EXTENDED_DATA_STDERR,
              'No shells on this server.\r\n'),
             ('loseConnection',)],
            protocol.log)

    def test_windowChangedNotImplemented(self):
        # windowChanged raises a NotImplementedError. It doesn't matter what
        # we pass it.
        self.assertRaises(NotImplementedError,
                          self.session.windowChanged, None)

    def test_providesISession(self):
        # DoNothingSession must provide ISession.
        self.failUnless(ISession.providedBy(self.session),
                        "DoNothingSession doesn't implement ISession")

    def test_closedDoesNothing(self):
        # closed is a no-op.
        self.assertEqual(None, self.session.closed())

    def test_execCommandNotImplemented(self):
        # DoNothingSession.execCommand spawns the appropriate process.
        protocol = MockProcessTransport('bash')
        command = 'cat /etc/hostname'
        self.session.execCommand(protocol, command)
        self.assertEqual(
            [('writeExtended', connection.EXTENDED_DATA_STDERR,
              'Not allowed to execute commands on this server.\r\n'),
             ('loseConnection',)],
            protocol.log)

    def test_eofReceivedDoesNothingWhenNoCommand(self):
        # When no process has been created, 'eofReceived' is a no-op.
        self.assertEqual(None, self.session.eofReceived())
