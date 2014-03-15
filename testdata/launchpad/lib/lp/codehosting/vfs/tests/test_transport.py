# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the Launchpad code hosting Bazaar transport."""

__metaclass__ = type

from bzrlib.tests import per_transport
from bzrlib.transport import (
    chroot,
    get_transport,
    Transport,
    )
from bzrlib.transport.local import LocalTransport
from bzrlib.urlutils import local_path_to_url

from lp.codehosting.inmemory import InMemoryFrontend
from lp.codehosting.tests.helpers import TestResultWrapper
from lp.codehosting.vfs.branchfs import LaunchpadInternalServer
from lp.services.twistedsupport.xmlrpc import DeferredBlockingProxy


class TestingServer(LaunchpadInternalServer):
    """A Server that provides instances of LaunchpadTransport for testing.

    See the comment in `_transportFactory` about what we actually test and
    `TestLaunchpadTransportImplementation` for the actual TestCase class.
    """

    def __init__(self):
        """Initialize the server.

        We register ourselves with the scheme lp-testing=${id(self)}:/// using
        an in-memory XML-RPC client and backed onto a LocalTransport.
        """
        frontend = InMemoryFrontend()
        branchfs = frontend.getCodehostingEndpoint()
        branch = frontend.getLaunchpadObjectFactory().makeAnyBranch()
        self._branch_path = branch.unique_name
        # XXX: JonathanLange bug=276972 2008-10-07: This should back on to a
        # MemoryTransport, but a bug in Bazaar's implementation makes it
        # unreliable for tests that involve particular errors.
        LaunchpadInternalServer.__init__(
            self, 'lp-testing-%s:///' % id(self),
            DeferredBlockingProxy(branchfs),
            LocalTransport(local_path_to_url('.')))
        self._chroot_servers = []

    def get_bogus_url(self):
        return self._scheme + 'bogus'

    def _transportFactory(self, url):
        """See `LaunchpadInternalServer._transportFactory`.

        As `LaunchpadTransport` 'acts all kinds of crazy' above the .bzr
        directory of a branch (forbidding file or directory creation at some
        levels, enforcing naming restrictions at others), we test a
        LaunchpadTransport chrooted into the .bzr directory of a branch.
        """
        if not url.startswith(self._scheme):
            raise AssertionError("Wrong transport scheme.")
        root_transport = LaunchpadInternalServer._transportFactory(
            self, self._scheme)
        relpath = root_transport.relpath(url)
        bzrdir_transport = root_transport.clone(
            self._branch_path).clone('.bzr')
        bzrdir_transport.ensure_base()
        chroot_server = chroot.ChrootServer(bzrdir_transport)
        chroot_server.start_server()
        self._chroot_servers.append(chroot_server)
        return get_transport(chroot_server.get_url()).clone(relpath)

    def tearDown(self):
        """See `LaunchpadInternalServer.tearDown`.

        In addition to calling the overridden method, we tear down any
        ChrootServer instances we've set up.
        """
        for chroot_server in self._chroot_servers:
            chroot_server.stop_server()
        LaunchpadInternalServer.tearDown(self)


class TestLaunchpadTransportImplementation(per_transport.TransportTests):
    """Implementation tests for `LaunchpadTransport`.

    We test the transport chrooted to the .bzr directory of a branch -- see
    `TestingServer._transportFactory` for more.
    """
    # TransportTests tests that get_transport() returns an instance of
    # `transport_class`, but the instances we're actually testing are
    # instances of ChrootTransport wrapping instances of SynchronousAdapter
    # which wraps the LaunchpadTransport we're actually interested in.  This
    # doesn't seem interesting to check, so we just set transport_class to
    # the base Transport class.
    transport_class = Transport

    def setUp(self):
        """Arrange for `get_transport` to return wrapped LaunchpadTransports.
        """
        self.transport_server = TestingServer
        super(TestLaunchpadTransportImplementation, self).setUp()

    def run(self, result=None):
        """Run the test, with the result wrapped so that it knows about skips.
        """
        if result is None:
            result = self.defaultTestResult()
        super(TestLaunchpadTransportImplementation, self).run(
            TestResultWrapper(result))
