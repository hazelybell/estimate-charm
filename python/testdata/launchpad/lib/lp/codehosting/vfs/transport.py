# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Transport utilities for the codehosting system.

The code hosting filesystem is implemented using Bazaar transports. This
module contains utilities for implementing virtual filesystems using
bzrlib.transport classes.
"""

__metaclass__ = type
__all__ = [
    'AsyncVirtualServer',
    'AsyncVirtualTransport',
    'get_chrooted_transport',
    'get_readonly_transport',
    'SynchronousAdapter',
    'TranslationError',
    ]


from bzrlib import urlutils
from bzrlib.errors import (
    BzrError,
    InProcessTransport,
    NoSuchFile,
    TransportNotPossible,
    )
from bzrlib.transport import (
    chroot,
    get_transport,
    register_transport,
    Server,
    Transport,
    unregister_transport,
    )
from twisted.internet import defer
from twisted.python.failure import Failure

from lp.services.twistedsupport import (
    extract_result,
    gatherResults,
    no_traceback_failures,
    )


class TranslationError(BzrError):
    """Raised when we cannot translate a virtual URL fragment.

    In particular, this is raised when there is some intrinsic deficiency in
    the path itself.
    """

    _fmt = ("Could not translate %(virtual_url_fragment)r. %(reason)s")

    def __init__(self, virtual_url_fragment, reason=None):
        BzrError.__init__(self)
        self.virtual_url_fragment = virtual_url_fragment
        if reason is not None:
            self.reason = str(reason)
        else:
            self.reason = ''


def get_chrooted_transport(url, mkdir=False):
    """Return a chrooted transport serving `url`."""
    transport = get_transport(url)
    if mkdir:
        transport.create_prefix()
    chroot_server = chroot.ChrootServer(transport)
    chroot_server.start_server()
    return get_transport(chroot_server.get_url())


def get_readonly_transport(transport):
    """Wrap `transport` in a readonly transport."""
    if transport.base.startswith('readonly+'):
        return transport
    return get_transport('readonly+' + transport.base)


class AsyncVirtualTransport(Transport):
    """A transport for a virtual file system.

    Assumes that it has a 'server' which implements 'translateVirtualPath'.
    This method is expected to take an absolute virtual path and translate it
    into a real transport and a path on that transport.
    """

    def __init__(self, server, url):
        self.server = server
        Transport.__init__(self, url)

    def external_url(self):
        # There's no real external URL to this transport. It's heavily
        # dependent on the process.
        raise InProcessTransport(self)

    def _abspath(self, relpath):
        """Return the absolute, escaped path to `relpath` without the schema.
        """
        return urlutils.joinpath(
            self.base[len(self.server.get_url())-1:], relpath)

    def _getUnderylingTransportAndPath(self, relpath):
        """Return the underlying transport and path for `relpath`."""
        virtual_url_fragment = self._abspath(relpath)
        return self.server.translateVirtualPath(virtual_url_fragment)

    def _translateError(self, failure):
        """Translate 'failure' into something suitable for a transport.

        This method is called as an errback by `_call`. Use it to translate
        errors from the server into something that users of the transport
        might expect. This could include translating vfs-specific errors into
        bzrlib errors (e.g. "couldn\'t translate" into `NoSuchFile`) or
        translating underlying paths into virtual paths.

        :param failure: A `twisted.python.failure.Failure`.
        """
        failure.trap(TranslationError)
        return Failure(NoSuchFile(failure.value.virtual_url_fragment))

    def _call(self, method_name, relpath, *args, **kwargs):
        """Call a method on the backing transport, translating relative,
        virtual paths to filesystem paths.

        If 'relpath' translates to a path that we only have read-access to,
        then the method will be called on the backing transport decorated with
        'readonly+'.
        """
        def call_method((transport, path)):
            method = getattr(transport, method_name)
            try:
                return method(path, *args, **kwargs)
            except BaseException as e:
                # It's much cheaper to explicitly construct a Failure than to
                # let Deferred build automatically, because the automatic one
                # will capture the traceback and perform an expensive
                # stringification on it.
                return Failure(e)

        deferred = self._getUnderylingTransportAndPath(relpath)
        deferred.addCallback(call_method)
        deferred.addErrback(self._translateError)
        return deferred

    # Transport methods
    def abspath(self, relpath):
        return urlutils.join(self.base, relpath)

    def append_file(self, relpath, f, mode=None):
        return self._call('append_file', relpath, f, mode)

    def clone(self, relpath=None):
        if relpath is None:
            return self.__class__(self.server, self.base)
        else:
            return self.__class__(
                self.server, urlutils.join(self.base, relpath))

    def delete(self, relpath):
        return self._call('delete', relpath)

    def delete_tree(self, relpath):
        return self._call('delete_tree', relpath)

    def get(self, relpath):
        return self._call('get', relpath)

    def get_bytes(self, relpath):
        return self._call('get_bytes', relpath)

    def has(self, relpath):
        return self._call('has', relpath)

    def iter_files_recursive(self):
        deferred = self._getUnderylingTransportAndPath('.')
        @no_traceback_failures
        def iter_files((transport, path)):
            return transport.clone(path).iter_files_recursive()
        deferred.addCallback(iter_files)
        return deferred

    def listable(self):
        deferred = self._getUnderylingTransportAndPath('.')
        @no_traceback_failures
        def listable((transport, path)):
            return transport.listable()
        deferred.addCallback(listable)
        return deferred

    def list_dir(self, relpath):
        return self._call('list_dir', relpath)

    def lock_read(self, relpath):
        return self._call('lock_read', relpath)

    def lock_write(self, relpath):
        return self._call('lock_write', relpath)

    def mkdir(self, relpath, mode=None):
        return self._call('mkdir', relpath, mode)

    def open_write_stream(self, relpath, mode=None):
        return self._call('open_write_stream', relpath, mode)

    def put_file(self, relpath, f, mode=None):
        return self._call('put_file', relpath, f, mode)

    def local_realPath(self, relpath):
        # This method should return an absolute path (not URL) that points to
        # `relpath` and dereferences any symlinks. The absolute path should be
        # on this transport.
        #
        # Here, we assume that the underlying transport has no symlinks
        # (Bazaar transports cannot create symlinks). This means that we can
        # just return the absolute path.
        return defer.succeed(self._abspath(relpath))

    def readv(self, relpath, offsets, adjust_for_latency=False,
              upper_limit=None):
        return self._call(
            'readv', relpath, offsets, adjust_for_latency, upper_limit)

    def rename(self, rel_from, rel_to):
        to_deferred = self._getUnderylingTransportAndPath(rel_to)
        from_deferred = self._getUnderylingTransportAndPath(rel_from)
        deferred = gatherResults([to_deferred, from_deferred])

        @no_traceback_failures
        def check_transports_and_rename(
            ((to_transport, to_path), (from_transport, from_path))):
            if to_transport.base != from_transport.base:
                return Failure(TransportNotPossible(
                    'cannot move between underlying transports'))
            return getattr(from_transport, 'rename')(from_path, to_path)

        deferred.addCallback(check_transports_and_rename)
        return deferred

    def rmdir(self, relpath):
        return self._call('rmdir', relpath)

    def stat(self, relpath):
        return self._call('stat', relpath)

    def writeChunk(self, relpath, offset, data):
        return self._call('writeChunk', relpath, offset, data)


class SynchronousAdapter(Transport):
    """Converts an asynchronous transport to a synchronous one."""

    def __init__(self, async_transport):
        self._async_transport = async_transport

    @property
    def base(self):
        return self._async_transport.base

    def _abspath(self, relpath):
        return self._async_transport._abspath(relpath)

    def get_segment_parameters(self):
        return self._async_transport.get_segment_parameters()

    def set_segment_parameter(self, name, value):
        return self._async_transport.set_segment_parameter(name, value)

    def clone(self, offset=None):
        """See `bzrlib.transport.Transport`."""
        cloned_async = self._async_transport.clone(offset)
        return SynchronousAdapter(cloned_async)

    def external_url(self):
        """See `bzrlib.transport.Transport`."""
        raise InProcessTransport(self)

    def abspath(self, relpath):
        """See `bzrlib.transport.Transport`."""
        return self._async_transport.abspath(relpath)

    def append_file(self, relpath, f, mode=None):
        """See `bzrlib.transport.Transport`."""
        return extract_result(
            self._async_transport.append_file(relpath, f, mode))

    def delete(self, relpath):
        """See `bzrlib.transport.Transport`."""
        return extract_result(self._async_transport.delete(relpath))

    def delete_tree(self, relpath):
        """See `bzrlib.transport.Transport`."""
        return extract_result(self._async_transport.delete_tree(relpath))

    def get(self, relpath):
        """See `bzrlib.transport.Transport`."""
        return extract_result(self._async_transport.get(relpath))

    def get_bytes(self, relpath):
        """See `bzrlib.transport.Transport`."""
        return extract_result(self._async_transport.get_bytes(relpath))

    def has(self, relpath):
        """See `bzrlib.transport.Transport`."""
        return extract_result(self._async_transport.has(relpath))

    def iter_files_recursive(self):
        """See `bzrlib.transport.Transport`."""
        return extract_result(
            self._async_transport.iter_files_recursive())

    def listable(self):
        """See `bzrlib.transport.Transport`."""
        return extract_result(self._async_transport.listable())

    def list_dir(self, relpath):
        """See `bzrlib.transport.Transport`."""
        return extract_result(self._async_transport.list_dir(relpath))

    def lock_read(self, relpath):
        """See `bzrlib.transport.Transport`."""
        return extract_result(self._async_transport.lock_read(relpath))

    def lock_write(self, relpath):
        """See `bzrlib.transport.Transport`."""
        return extract_result(self._async_transport.lock_write(relpath))

    def mkdir(self, relpath, mode=None):
        """See `bzrlib.transport.Transport`."""
        return extract_result(self._async_transport.mkdir(relpath, mode))

    def open_write_stream(self, relpath, mode=None):
        """See `bzrlib.transport.Transport`."""
        return extract_result(
            self._async_transport.open_write_stream(relpath, mode))

    def put_file(self, relpath, f, mode=None):
        """See `bzrlib.transport.Transport`."""
        return extract_result(
            self._async_transport.put_file(relpath, f, mode))

    def local_realPath(self, relpath):
        """See `bzrlib.transport.Transport`."""
        return extract_result(
            self._async_transport.local_realPath(relpath))

    def readv(self, relpath, offsets, adjust_for_latency=False,
              upper_limit=None):
        """See `bzrlib.transport.Transport`."""
        return extract_result(
            self._async_transport.readv(
                relpath, offsets, adjust_for_latency, upper_limit))

    def rename(self, rel_from, rel_to):
        """See `bzrlib.transport.Transport`."""
        return extract_result(
            self._async_transport.rename(rel_from, rel_to))

    def rmdir(self, relpath):
        """See `bzrlib.transport.Transport`."""
        return extract_result(self._async_transport.rmdir(relpath))

    def stat(self, relpath):
        """See `bzrlib.transport.Transport`."""
        return extract_result(self._async_transport.stat(relpath))

    def writeChunk(self, relpath, offset, data):
        """See `bzrlib.transport.Transport`."""
        return extract_result(
            self._async_transport.writeChunk(relpath, offset, data))


class AsyncVirtualServer(Server):
    """Bazaar `Server` for translating paths asynchronously.

    :ivar asyncTransportFactory: A callable that takes a Server and a URL and
        returns an `AsyncVirtualTransport` instance. Subclasses should set
        this callable if they need to hook into any filesystem operations.
    """

    asyncTransportFactory = AsyncVirtualTransport

    def __init__(self, scheme):
        """Construct an `AsyncVirtualServer`.

        :param scheme: The URL scheme to use.
        """
        # bzrlib's Server class does not have a constructor, so we cannot
        # safely upcall it.
        self._scheme = scheme
        self._is_started = False

    def _transportFactory(self, url):
        """Create a transport for this server pointing at `url`.

        This constructs a regular Bazaar `Transport` from the "asynchronous
        transport" factory specified in the `asyncTransportFactory` instance
        variable.
        """
        assert url.startswith(self.get_url())
        return SynchronousAdapter(self.asyncTransportFactory(self, url))

    def translateVirtualPath(self, virtual_url_fragment):
        """Translate 'virtual_url_fragment' into a transport and sub-fragment.

        :param virtual_url_fragment: A virtual URL fragment to be translated.

        :raise NoSuchFile: If `virtual_path` is maps to a path that could
            not be found.
        :raise PermissionDenied: if the path is forbidden.

        :return: (transport, path_on_transport)
        """
        raise NotImplementedError(self.translateVirtualPath)

    def get_url(self):
        """Return the URL of this server."""
        return self._scheme

    def start_server(self):
        """See Server.start_server."""
        register_transport(self.get_url(), self._transportFactory)
        self._is_started = True

    def stop_server(self):
        """See Server.stop_server."""
        if not self._is_started:
            return
        self._is_started = False
        unregister_transport(self.get_url(), self._transportFactory)
