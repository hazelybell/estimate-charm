# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for the error presentation in worker.py."""

__metaclass__ = type

import httplib
import os
import socket
import tempfile
import urllib2

from bzrlib.errors import (
    BzrError,
    NotBranchError,
    ParamikoNotPresent,
    UnknownFormatError,
    UnsupportedFormatError,
    )
from lazr.uri import InvalidURIError

from lp.code.enums import BranchType
from lp.codehosting.puller.worker import (
    BadUrlLaunchpad,
    BadUrlScheme,
    BadUrlSsh,
    BranchMirrorer,
    PullerWorker,
    PullerWorkerProtocol,
    )
from lp.codehosting.safe_open import (
    BranchLoopError,
    BranchReferenceForbidden,
    )
from lp.testing import TestCase


class StubbedPullerWorkerProtocol(PullerWorkerProtocol):
    """A `PullerWorkerProtocol` that logs events without acting on them."""

    def __init__(self):
        self.calls = []

    def sendEvent(self, command, *args):
        """Capture and log events."""
        log_event = tuple([command] + list(args))
        self.calls.append(log_event)


class TestErrorCatching(TestCase):
    """Tests for presenting error messages in useful ways.

    These are testing the large collection of except: clauses in
    `PullerWorker.mirror`.
    """

    class CustomErrorOpener(BranchMirrorer):
        def __init__(self, exc):
            super(TestErrorCatching.CustomErrorOpener, self).__init__(None)
            self.exc = exc

        def open(self, url):
            raise self.exc

    def makeRaisingWorker(self, exception, branch_type=None):
        opener = self.CustomErrorOpener(exception)
        worker = PullerWorker(
            src='foo', dest='bar', branch_id=1,
            unique_name='owner/product/foo', branch_type=branch_type,
            default_stacked_on_url=None,
            protocol=StubbedPullerWorkerProtocol(), branch_mirrorer=opener)
        return worker

    def getMirrorFailureForException(self, exc=None, worker=None,
                                     branch_type=None):
        """Mirror the branch and return the error message.

        Runs mirror, checks that we receive exactly one error, and returns the
        str() of the error.
        """
        if worker is None:
            worker = self.makeRaisingWorker(
                exc, branch_type=branch_type)
        worker.mirror()
        self.assertEqual(
            2, len(worker.protocol.calls),
            "Expected startMirroring and mirrorFailed, got: %r"
            % (worker.protocol.calls,))
        startMirroring, mirrorFailed = worker.protocol.calls
        self.assertEqual(('startMirroring',), startMirroring)
        self.assertEqual('mirrorFailed', mirrorFailed[0])
        self.assertStartsWith(mirrorFailed[2], 'OOPS-')
        worker.protocol.calls = []
        return str(mirrorFailed[1])

    def testBadUrlBzrSshCaught(self):
        # The exception raised if the scheme of the source url is sftp or
        # bzr+ssh is caught and an informative error message is displayed to
        # the user.
        expected_msg = "Launchpad cannot mirror branches from SFTP "
        msg = self.getMirrorFailureForException(
            BadUrlSsh('sftp://example.com/foo'))
        self.assertTrue(msg.startswith(expected_msg))

    def testBadUrlLaunchpadCaught(self):
        # The exception raised if the host of the source url is launchpad.net
        # or a host in this domain is caught, and an informative error message
        # is displayed to the user.
        expected_msg = "Launchpad does not mirror branches from Launchpad."
        msg = self.getMirrorFailureForException(
            BadUrlLaunchpad('http://launchpad.dev/foo'))
        self.assertTrue(msg.startswith(expected_msg))

    def testHostedBranchReference(self):
        # A branch reference for a hosted branch must cause an error.
        expected_msg = (
            "Branch references are not allowed for branches of type Hosted.")
        msg = self.getMirrorFailureForException(
            BranchReferenceForbidden(),
            branch_type=BranchType.HOSTED)
        self.assertEqual(expected_msg, msg)

    def testLocalURL(self):
        # A file:// branch reference for a mirror branch must cause an error.
        expected_msg = (
            "Launchpad does not mirror file:// URLs.")
        msg = self.getMirrorFailureForException(
            BadUrlScheme('file', 'file:///sauces/sikrit'))
        self.assertEqual(expected_msg, msg)

    def testUnknownSchemeURL(self):
        # A branch reference to a URL with unknown scheme must cause an error.
        expected_msg = (
            "Launchpad does not mirror random:// URLs.")
        msg = self.getMirrorFailureForException(
            BadUrlScheme('random', 'random:///sauces/sikrit'))
        self.assertEqual(expected_msg, msg)

    def testHTTPError(self):
        # If the source branch requires HTTP authentication, say so in the
        # error message.
        msg = self.getMirrorFailureForException(
            urllib2.HTTPError(
                'http://something', httplib.UNAUTHORIZED,
                'Authorization Required', 'some headers',
                os.fdopen(tempfile.mkstemp()[0])))
        self.assertEqual("Authentication required.", msg)

    def testSocketErrorHandling(self):
        # If a socket error occurs accessing the source branch, say so in the
        # error message.
        msg = self.getMirrorFailureForException(socket.error('foo'))
        expected_msg = 'A socket error occurred:'
        self.assertTrue(msg.startswith(expected_msg))

    def testUnsupportedFormatErrorHandling(self):
        # If we don't support the format that the source branch is in, say so
        # in the error message.
        msg = self.getMirrorFailureForException(
            UnsupportedFormatError('Bazaar-NG branch, format 0.0.4'))
        expected_msg = 'Launchpad does not support branches '
        self.assertTrue(msg.startswith(expected_msg))

    def testUnknownFormatError(self):
        # If the format is completely unknown to us, say so in the error
        # message.
        msg = self.getMirrorFailureForException(
            UnknownFormatError(format='Bad format'))
        expected_msg = 'Unknown branch format: '
        self.assertTrue(msg.startswith(expected_msg))

    def testParamikoNotPresent(self):
        # If, somehow, we try to mirror a branch that requires SSH, we tell
        # the user we cannot do so.
        # XXX: JonathanLange 2008-06-25: It's bogus to assume that this is
        # the error we'll get if we try to mirror over SSH.
        msg = self.getMirrorFailureForException(
            ParamikoNotPresent('No module named paramiko'))
        expected_msg = ('Launchpad cannot mirror branches from SFTP and SSH '
                        'URLs. Please register a HTTP location for this '
                        'branch.')
        self.assertEqual(expected_msg, msg)

    def testNotBranchErrorMirrored(self):
        # Log a user-friendly message when we are asked to mirror a
        # non-branch.
        msg = self.getMirrorFailureForException(
            NotBranchError('http://example.com/not-branch'),
            branch_type=BranchType.MIRRORED)
        expected_msg = 'Not a branch: "http://example.com/not-branch".'
        self.assertEqual(expected_msg, msg)

    def testNotBranchErrorHosted(self):
        # The not-a-branch error message does *not* include an internal
        # lp-hosted:/// URL.  Instead, the path is translated to a
        # user-visible location.
        worker = self.makeRaisingWorker(
            NotBranchError('lp-hosted:///~user/project/branch'),
            branch_type=BranchType.HOSTED)
        msg = self.getMirrorFailureForException(worker=worker)
        expected_msg = 'Not a branch: "lp:%s".' % (worker.unique_name,)
        self.assertEqual(expected_msg, msg)

    def testNotBranchErrorImported(self):
        # The not-a-branch error message for import branch does not disclose
        # the internal URL. Since there is no user-visible URL to blame, we do
        # not display any URL at all.
        msg = self.getMirrorFailureForException(
            NotBranchError('http://canonical.example.com/internal/url'),
            branch_type=BranchType.IMPORTED)
        expected_msg = 'Not a branch.'
        self.assertEqual(expected_msg, msg)

    def testBranchLoopError(self):
        # BranchLoopError exceptions are caught.
        msg = self.getMirrorFailureForException(
            BranchLoopError())
        self.assertEqual("Circular branch reference.", msg)

    def testInvalidURIError(self):
        # When a branch reference contains an invalid URL, an InvalidURIError
        # is raised. The worker catches this and reports it to the scheduler.
        msg = self.getMirrorFailureForException(
            InvalidURIError("This is not a URL"))
        self.assertEqual(msg, "This is not a URL")

    def testBzrErrorHandling(self):
        msg = self.getMirrorFailureForException(
            BzrError('A generic bzr error'))
        expected_msg = 'A generic bzr error'
        self.assertEqual(msg, expected_msg)
