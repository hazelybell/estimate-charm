# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the lp-serve plugin."""

__metaclass__ = type

from bzrlib import errors
from bzrlib.plugins.lpserve.test_lpserve import TestCaseWithSubprocess
from bzrlib.smart import medium
from bzrlib.transport import remote

from lp.testing.fixture import CaptureOops
from lp.testing.layers import LaunchpadLayer


class TestLaunchpadServe(TestCaseWithSubprocess):
    """Tests for the lp-serve plugin.

    Most of the helper methods here are copied from bzrlib.tests and
    bzrlib.tests.blackbox.test_serve in bzr.dev r4445. They have since been
    modified for the Launchpad environment.
    """

    # The oops tests need rabbit available
    layer = LaunchpadLayer

    def assertFinishedCleanly(self, result):
        """Assert that a server process finished cleanly."""
        self.assertEqual((0, '', ''), tuple(result))

    def finish_lpserve_subprocess(self, process):
        """Shut down the server process.

        :return: A tuple of (retcode, stdout, stderr).
        """
        # Shutdown the server: the server should shut down when it cannot read
        # from stdin anymore.
        process.stdin.close()
        # Hide stdin from the subprocess module, so it won't fail to close it.
        process.stdin = None
        # Finish the process without asserting anything about the return code.
        # We'll leave that to assertFinishedCleanly.
        stdout_and_stderr = self.finish_bzr_subprocess(process, retcode=None)
        return (
            process.returncode,
            stdout_and_stderr[0],
            stdout_and_stderr[1],
            )

    def start_server_inet(self, user_id=None):
        """Start an lp-serve server subprocess.

        Copied from `bzrlib.tests.test_serve`.

        :param user_id: The database id of the user to run as. If not
            provided, defaults to 1.

        :return: a tuple with the bzr process handle for passing to
            finish_lpserve_subprocess, a client for the server, and a
            transport.
        """
        # Serve from the current directory
        if user_id is None:
            user_id = 1
        process = self.start_bzr_subprocess(
            ['lp-serve', '--inet', str(user_id)])

        # Connect to the server.
        # The transport needs a URL, but we don't have one for our server, so
        # we're just going to give it this nearly-arbitrary-yet-well-formed
        # one.
        url = 'bzr://localhost/'
        client_medium = medium.SmartSimplePipesClientMedium(
            process.stdout, process.stdin, url)
        transport = remote.RemoteTransport(url, medium=client_medium)
        return process, transport

    def test_successful_start_then_stop(self):
        # We can start and stop the lpserve process.
        process, transport = self.start_server_inet()
        result = self.finish_lpserve_subprocess(process)
        self.assertFinishedCleanly(result)

    def test_successful_start_then_stop_logs_no_oops(self):
        # Starting and stopping the lp-serve process leaves no OOPS.
        capture = self.useFixture(CaptureOops())
        process, transport = self.start_server_inet()
        self.finish_lpserve_subprocess(process)
        capture.sync()
        self.assertEqual([], capture.oopses)

    def test_unexpected_error_logs_oops(self):
        # If an unexpected error is raised in the plugin, then an OOPS is
        # recorded.
        capture = self.useFixture(CaptureOops())
        process, transport = self.start_server_inet()
        # This will trigger an error, because the XML-RPC server is not
        # running, and any filesystem access tries to get at the XML-RPC
        # server. If this *doesn'* raise, then the test is no longer valid and
        # we need a new way of triggering errors in the smart server.
        self.assertRaises(
            errors.UnknownErrorFromSmartServer,
            transport.list_dir, 'foo/bar/baz')
        result = self.finish_lpserve_subprocess(process)
        self.assertFinishedCleanly(result)
        capture.sync()
        self.assertEqual(1, len(capture.oopses))
        self.assertEqual(
            '[Errno 111] Connection refused', capture.oopses[0]['value'],
            capture.oopses)


def test_suite():
    from bzrlib import tests
    from bzrlib.plugins import lpserve

    loader = tests.TestLoader()
    suite = loader.loadTestsFromName(__name__)
    suite = lpserve.load_tests(suite, lpserve, loader)
    return suite
