# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Utilities for dealing with Bazaar.

Much of the code in here should be submitted upstream. The rest is code that
integrates between Bazaar's infrastructure and Launchpad's infrastructure.
"""

__metaclass__ = type
__all__ = [
    'add_exception_logging_hook',
    'DenyingServer',
    'get_branch_info',
    'get_branch_stacked_on_url',
    'get_stacked_on_url',
    'get_vfs_format_classes',
    'HttpAsLocalTransport',
    'identical_formats',
    'install_oops_handler',
    'is_branch_stackable',
    'server',
    'read_locked',
    'remove_exception_logging_hook',
    ]

from contextlib import contextmanager
import os
import sys

from bzrlib import (
    config,
    trace,
    )
from bzrlib.errors import (
    AppendRevisionsOnlyViolation,
    NotStacked,
    UnstackableBranchFormat,
    UnstackableRepositoryFormat,
    UnsupportedProtocol,
    )
from bzrlib.remote import (
    RemoteBranch,
    RemoteBzrDir,
    RemoteRepository,
    )
from bzrlib.transport import (
    get_transport,
    register_transport,
    unregister_transport,
    )
from bzrlib.transport.local import LocalTransport
from lazr.uri import URI

from lp.services.webapp.errorlog import (
    ErrorReportingUtility,
    ScriptRequest,
    )

# Exception classes which are not converted into OOPSes
NOT_OOPS_EXCEPTIONS = (AppendRevisionsOnlyViolation,)

def should_log_oops(exc):
    """Return true if exc should trigger an OOPS.
    """
    return not issubclass(exc, NOT_OOPS_EXCEPTIONS)


def is_branch_stackable(bzr_branch):
    """Return True if the bzr_branch is able to be stacked."""
    try:
        bzr_branch.get_stacked_on_url()
    except (UnstackableBranchFormat, UnstackableRepositoryFormat):
        return False
    except NotStacked:
        # This is fine.
        return True
    else:
        # If nothing is raised, then stackable (and stacked even).
        return True


def get_branch_stacked_on_url(a_bzrdir):
    """Return the stacked-on URL for the branch in this bzrdir.

    This method lets you figure out the stacked-on URL of a branch without
    opening the stacked-on branch. This lets us check for pathologically
    stacked branches.

    :raises NotBranchError: If there is no Branch.
    :raises NotStacked: If the Branch is not stacked.
    :raises UnstackableBranchFormat: If the Branch is of an unstackable
        format.
    :return: the stacked-on URL for the branch in this bzrdir.
    """
    # XXX: JonathanLange 2008-09-04: In a better world, this method would live
    # on BzrDir. Unfortunately, Bazaar lacks the configuration APIs to make
    # this possible (see below). Alternatively, Bazaar could provide us with a
    # way to open a Branch without opening the stacked-on branch.

    # XXX: MichaelHudson 2008-09-19, bug=271924:
    # RemoteBzrDir.find_branch_format opens the branch, which defeats the
    # purpose of this helper.
    if isinstance(a_bzrdir, RemoteBzrDir):
        a_bzrdir._ensure_real()
        a_bzrdir = a_bzrdir._real_bzrdir

    # XXX: JonathanLange 2008-09-04: In Bazaar 1.6, there's no way to get the
    # format of a branch from a generic BzrDir. Here, we just assume that if
    # you can't get the branch format using the newer API (i.e.
    # BzrDir.find_branch_format()), then the branch is not stackable. Bazaar
    # post-1.6 has added 'get_branch_format' to the pre-split-out formats,
    # which we could use instead.
    try:
        format = a_bzrdir.find_branch_format(None)
    except NotImplementedError:
        raise UnstackableBranchFormat(
            a_bzrdir._format, a_bzrdir.root_transport.base)
    if not format.supports_stacking():
        raise UnstackableBranchFormat(format, a_bzrdir.root_transport.base)
    branch_transport = a_bzrdir.get_branch_transport(None)
    # XXX: JonathanLange 2008-09-04: We should be using BranchConfig here, but
    # that requires opening the Branch. Bazaar should grow APIs to let us
    # safely access the branch configuration without opening the branch. Here
    # we read the 'branch.conf' and don't bother with the locations.conf or
    # bazaar.conf. This is OK for Launchpad since we don't ever want to have
    # local client configuration. It's not OK for Bazaar in general.
    branch_config = config.TransportConfig(
        branch_transport, 'branch.conf')
    stacked_on_url = branch_config.get_option('stacked_on_location')
    if not stacked_on_url:
        raise NotStacked(a_bzrdir.root_transport.base)
    return stacked_on_url


_exception_logging_hooks = []

_original_log_exception_quietly = trace.log_exception_quietly


def _hooked_log_exception_quietly():
    """Wrapper around `trace.log_exception_quietly` that calls hooks."""
    _original_log_exception_quietly()
    for hook in _exception_logging_hooks:
        hook()


def add_exception_logging_hook(hook_function):
    """Call 'hook_function' when bzr logs an exception.

    :param hook_function: A nullary callable that relies on sys.exc_info()
        for exception information.
    """
    if trace.log_exception_quietly == _original_log_exception_quietly:
        trace.log_exception_quietly = _hooked_log_exception_quietly
    _exception_logging_hooks.append(hook_function)


def remove_exception_logging_hook(hook_function):
    """Cease calling 'hook_function' whenever bzr logs an exception.

    :param hook_function: A nullary callable that relies on sys.exc_info()
        for exception information. It will be removed from the exception
        logging hooks.
    """
    _exception_logging_hooks.remove(hook_function)
    if len(_exception_logging_hooks) == 0:
        trace.log_exception_quietly == _original_log_exception_quietly


def make_oops_logging_exception_hook(error_utility, request):
    """Make a hook for logging OOPSes."""

    def log_oops():
        if should_log_oops(sys.exc_info()[0]):
            error_utility.raising(sys.exc_info(), request)
    return log_oops


class BazaarOopsRequest(ScriptRequest):
    """An OOPS request specific to bzr."""

    def __init__(self, user_id):
        """Construct a `BazaarOopsRequest`.

        :param user_id: The database ID of the user doing this.
        """
        data = [('user_id', user_id)]
        super(BazaarOopsRequest, self).__init__(data, URL=None)


def make_error_utility(pid=None):
    """Make an error utility for logging errors from bzr."""
    if pid is None:
        pid = os.getpid()
    error_utility = ErrorReportingUtility()
    error_utility.configure('bzr_lpserve')
    return error_utility


def install_oops_handler(user_id):
    """Install an OOPS handler for a bzr process.

    When installed, logs any exception passed to `log_exception_quietly`.

    :param user_id: The database ID of the user the process is running as.
    """
    error_utility = make_error_utility()
    request = BazaarOopsRequest(user_id)
    hook = make_oops_logging_exception_hook(error_utility, request)
    add_exception_logging_hook(hook)
    return hook


class HttpAsLocalTransport(LocalTransport):
    """A LocalTransport that works using http URLs.

    We have this because the Launchpad database has constraints on URLs for
    branches, disallowing file:/// URLs. bzrlib itself disallows
    file://localhost/ URLs.
    """

    def __init__(self, http_url):
        file_url = URI(
            scheme='file', host='', path=URI(http_url).path)
        return super(HttpAsLocalTransport, self).__init__(
            str(file_url))

    @classmethod
    def register(cls):
        """Register this transport."""
        register_transport('http://', cls)

    @classmethod
    def unregister(cls):
        """Unregister this transport."""
        unregister_transport('http://', cls)


class DenyingServer:
    """Temporarily prevent creation of transports for certain URL schemes."""

    _is_set_up = False

    def __init__(self, schemes):
        """Set up the instance.

        :param schemes: The schemes to disallow creation of transports for.
        """
        self.schemes = schemes

    def start_server(self):
        """Prevent transports being created for specified schemes."""
        for scheme in self.schemes:
            register_transport(scheme, self._deny)
        self._is_set_up = True

    def stop_server(self):
        """Re-enable creation of transports for specified schemes."""
        if not self._is_set_up:
            return
        self._is_set_up = False
        for scheme in self.schemes:
            unregister_transport(scheme, self._deny)

    def _deny(self, url):
        """Prevent creation of transport for 'url'."""
        raise AssertionError(
            "Creation of transport for %r is currently forbidden" % url)


def get_vfs_format_classes(branch):
    """Return the vfs classes of the branch, repo and bzrdir formats.

    'vfs' here means that it will return the underlying format classes of a
    remote branch.
    """
    if isinstance(branch, RemoteBranch):
        branch._ensure_real()
        branch = branch._real_branch
    repository = branch.repository
    if isinstance(repository, RemoteRepository):
        repository._ensure_real()
        repository = repository._real_repository
    bzrdir = branch.bzrdir
    if isinstance(bzrdir, RemoteBzrDir):
        bzrdir._ensure_real()
        bzrdir = bzrdir._real_bzrdir
    return (
        branch._format.__class__,
        repository._format.__class__,
        bzrdir._format.__class__,
        )


def identical_formats(branch_one, branch_two):
    """Check if two branches have the same bzrdir, repo, and branch formats.
    """
    return (get_vfs_format_classes(branch_one) ==
            get_vfs_format_classes(branch_two))


def get_stacked_on_url(branch):
    """Get the stacked-on URL for 'branch', or `None` if not stacked."""
    try:
        return branch.get_stacked_on_url()
    except (NotStacked, UnstackableBranchFormat):
        return None


def get_branch_info(branch):
    """Get information about the branch for branchChanged.

    :return: a dict containing 'stacked_on_url', 'last_revision_id',
        'control_string', 'branch_string', 'repository_string'.
    """
    info = {}
    info['stacked_on_url'] = get_stacked_on_url(branch)
    info['last_revision_id'] = branch.last_revision()
    # XXX: Aaron Bentley 2008-06-13
    # Bazaar does not provide a public API for learning about
    # format markers.  Fix this in Bazaar, then here.
    info['control_string'] = branch.bzrdir._format.get_format_string()
    info['branch_string'] = branch._format.get_format_string()
    info['repository_string'] = branch.repository._format.get_format_string()
    return info


@contextmanager
def read_locked(branch):
    branch.lock_read()
    try:
        yield
    finally:
        branch.unlock()


@contextmanager
def write_locked(branch):
    """Provide a context in which the branch is write-locked."""
    branch.lock_write()
    try:
        yield
    finally:
        branch.unlock()


@contextmanager
def server(server, no_replace=False):
    run_server = True
    if no_replace:
        try:
            get_transport(server.get_url())
        except UnsupportedProtocol:
            pass
        else:
            run_server = False
    if run_server:
        server.start_server()
    try:
        yield server
    finally:
        if run_server:
            server.stop_server()
