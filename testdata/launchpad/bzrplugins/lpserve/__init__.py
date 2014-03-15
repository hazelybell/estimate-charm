# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Bazaar plugin to run the smart server on Launchpad.

Cribbed from bzrlib.builtins.cmd_serve from Bazaar 0.16.
"""

__metaclass__ = type

__all__ = [
    'cmd_launchpad_server',
    'cmd_launchpad_forking_service',
    ]


import errno
import fcntl
import logging
import os
import resource
import shlex
import shutil
import signal
import socket
import sys
import tempfile
import threading
import time

from bzrlib import (
    commands,
    errors,
    lockdir,
    osutils,
    trace,
    ui,
    )
from bzrlib.commands import (
    Command,
    register_command,
    )
from bzrlib.option import (
    Option,
    RegistryOption,
    )
from bzrlib.transport import (
    get_transport,
    transport_server_registry,
    )


class cmd_launchpad_server(Command):
    """Run a Bazaar server that maps Launchpad branch URLs to the internal
    file-system format.
    """

    aliases = ['lp-serve']

    takes_options = [
        Option(
            'inet',
            help="serve on stdin/out for use from inetd or sshd"),
        Option(
            'port',
            help=(
                "listen for connections on nominated port of the form "
                "[hostname:]portnumber. Passing 0 as the port number will "
                "result in a dynamically allocated port. Default port is "
                " 4155."),
            type=str),
        Option(
            'upload-directory',
            help=(
                "upload branches to this directory. Defaults to "
                "config.codehosting.hosted_branches_root."),
            type=unicode),
        Option(
            'mirror-directory',
            help=(
                "serve branches from this directory. Defaults to "
                "config.codehosting.mirrored_branches_root.")),
        Option(
            'codehosting-endpoint',
            help=(
                "the url of the internal XML-RPC server. Defaults to "
                "config.codehosting.codehosting_endpoint."),
            type=unicode),
        RegistryOption(
            'protocol', help="Protocol to serve.",
            lazy_registry=('bzrlib.transport', 'transport_server_registry'),
            value_switches=True),
        ]

    takes_args = ['user_id']

    def run_server(self, smart_server):
        """Run the given smart server."""
        # for the duration of this server, no UI output is permitted.
        # note that this may cause problems with blackbox tests. This should
        # be changed with care though, as we dont want to use bandwidth
        # sending progress over stderr to smart server clients!
        old_factory = ui.ui_factory
        try:
            ui.ui_factory = ui.SilentUIFactory()
            smart_server.serve()
        finally:
            ui.ui_factory = old_factory

    def get_host_and_port(self, port):
        """Return the host and port to run the smart server on.

        If 'port' is None, None will be returned for the host and port.

        If 'port' has a colon in it, the string before the colon will be
        interpreted as the host.

        :param port: A string of the port to run the server on.
        :return: A tuple of (host, port), where 'host' is a host name or IP,
            and port is an integer TCP/IP port.
        """
        host = None
        if port is not None:
            if ':' in port:
                host, port = port.split(':')
            port = int(port)
        return host, port

    def run(self, user_id, port=None, branch_directory=None,
            codehosting_endpoint_url=None, inet=False, protocol=None):
        from lp.codehosting.bzrutils import install_oops_handler
        from lp.codehosting.vfs import get_lp_server, hooks
        install_oops_handler(user_id)
        four_gig = int(4e9)
        resource.setrlimit(resource.RLIMIT_AS, (four_gig, four_gig))
        seen_new_branch = hooks.SetProcTitleHook()
        if protocol is None:
            protocol = transport_server_registry.get()
        lp_server = get_lp_server(
            int(user_id), codehosting_endpoint_url, branch_directory,
            seen_new_branch.seen)
        lp_server.start_server()
        try:
            old_lockdir_timeout = lockdir._DEFAULT_TIMEOUT_SECONDS
            lp_transport = get_transport(lp_server.get_url())
            host, port = self.get_host_and_port(port)
            lockdir._DEFAULT_TIMEOUT_SECONDS = 0
            try:
                protocol(lp_transport, host, port, inet)
            finally:
                lockdir._DEFAULT_TIMEOUT_SECONDS = old_lockdir_timeout
        finally:
            lp_server.stop_server()


register_command(cmd_launchpad_server)


class LPForkingService(object):
    """A service that can be asked to start a new bzr subprocess via fork.

    The basic idea is that bootstrapping time is long. Most of this is time
    spent during import of all needed libraries (lp.*).  For example, the
    original 'lp-serve' command could take 2.5s just to start up, before any
    actual actions could be performed.

    This class provides a service sitting on a socket, which can then be
    requested to fork and run a given bzr command.

    Clients connect to the socket and make a single request, which then
    receives a response. The possible requests are:

        "hello\n":  Trigger a heartbeat to report that the program is still
                    running, and write status information to the log file.
        "quit\n":   Stop the service, but do so 'nicely', waiting for children
                    to exit, etc. Once this is received the service will stop
                    taking new requests on the port.
        "fork-env <command>\n<env>\nend\n": Request a new subprocess to be
            started.  <command> is the bzr command to be run, such as "rocks"
            or "lp-serve --inet 12".
            The immediate response will be the path-on-disk to a directory
            full of named pipes (fifos) that will be the stdout/stderr/stdin
            (named accordingly) of the new process.
            If a client holds the socket open, when the child process exits,
            the exit status (as given by 'wait()') will be written to the
            socket.

            Note that one of the key bits is that the client will not be
            started with exec*, we just call 'commands.run_bzr*()' directly.
            This way, any modules that are already loaded will not need to be
            loaded again. However, care must be taken with any global-state
            that should be reset.

            fork-env allows you to supply environment variables such as
            "BZR_EMAIL: joe@foo.com" which will be set in os.environ before
            the command is run.
    """

    # Design decisions. These are bits where we could have chosen a different
    # method/implementation and weren't sure what would be best. Documenting
    # the current decision, and the alternatives.
    #
    # [Decision #1]
    #   Serve on a named AF_UNIX socket.
    #       1) It doesn't make sense to serve to arbitrary hosts, we only want
    #          the local host to make requests. (Since the client needs to
    #          access the named fifos on the current filesystem.)
    #       2) You can set security parameters on a filesystem path (g+rw,
    #          a-rw).
    # [Decision #2]
    #   SIGCHLD
    #       We want to quickly detect that children have exited so that we can
    #       inform the client process quickly. At the moment, we register a
    #       SIGCHLD handler that doesn't do anything. However, it means that
    #       when we get the signal, if we are currently blocked in something
    #       like '.accept()', we will jump out temporarily. At that point the
    #       main loop will check if any children have exited. We could have
    #       done this work as part of the signal handler, but that felt 'racy'
    #       doing any serious work in a signal handler.
    #       If we just used socket.timeout as the indicator to go poll for
    #       children exiting, it slows the disconnect by as much as the full
    #       timeout. (So a timeout of 1.0s will cause the process to hang by
    #       that long until it determines that a child has exited, and can
    #       close the connection.)
    #       The current flow means that we'll notice exited children whenever
    #       we finish the current work.
    # [Decision #3]
    #   Child vs Parent actions.
    #       There are several actions that are done when we get a new request.
    #       We have to create the fifos on disk, fork a new child, connect the
    #       child to those handles, and inform the client of the new path (not
    #       necessarily in that order.) It makes sense to wait to send the
    #       path message until after the fifos have been created. That way the
    #       client can just try to open them immediately, and the
    #       client-and-child will be synchronized by the open() calls.
    #       However, should the client be the one doing the mkfifo, should the
    #       server? Who should be sending the message? Should we fork after
    #       the mkfifo or before?
    #       The current thoughts:
    #           1) Try to do work in the child when possible. This should
    #              allow for 'scaling' because the server is single-threaded.
    #           2) We create the directory itself in the server, because that
    #              allows the server to monitor whether the client failed to
    #              clean up after itself or not.
    #           3) Otherwise we create the fifos in the client, and then send
    #              the message back.
    # [Decision #4]
    #   Exit information
    #       Inform the client that the child has exited on the socket they
    #       used to request the fork.
    #       1) Arguably they could see that stdout and stderr have been
    #          closed, and thus stop reading. In testing, I wrote a client
    #          which uses select.poll() over stdin/stdout/stderr and used that
    #          to ferry the content to the appropriate local handle. However
    #          for the FIFOs, when the remote end closed, I wouldn't see any
    #          corresponding information on the local end. There obviously
    #          wasn't any data to be read, so they wouldn't show up as
    #          'readable' (for me to try to read, and get 0 bytes, indicating
    #          it was closed). I also wasn't seeing POLLHUP, which seemed to
    #          be the correct indicator.  As such, we decided to inform the
    #          client on the socket that they originally made the fork
    #          request, rather than just closing the socket immediately.
    #       2) We could have had the forking server close the socket, and only
    #          the child hold the socket open. When the child exits, then the
    #          OS naturally closes the socket.
    #          If we want the returncode, then we should put that as bytes on
    #          the socket before we exit. Having the child do the work means
    #          that in error conditions, it could easily die before being able
    #          to write anything (think SEGFAULT, etc). The forking server is
    #          already 'wait'() ing on its children. So that we don't get
    #          zombies, and with wait3() we can get the rusage (user time,
    #          memory consumption, etc.)
    #          As such, it seems reasonable that the server can then also
    #          report back when a child is seen as exiting.
    # [Decision #5]
    #   cleanup once connected
    #       The child process blocks during 'open()' waiting for the client to
    #       connect to its fifos. Once the client has connected, the child
    #       then deletes the temporary directory and the fifos from disk. This
    #       means that there isn't much left for diagnosis, but it also means
    #       that the client won't leave garbage around if it crashes, etc.
    #       Note that the forking service itself still monitors the paths
    #       created, and will delete garbage if it sees that a child failed to
    #       do so.
    # [Decision #6]
    #   os._exit(retcode) in the child
    #       Calling sys.exit(retcode) raises an exception, which then bubbles
    #       up the stack and runs exit functions (and finally statements).
    #       When I tried using it originally, I would see the current child
    #       bubble all the way up the stack (through the server code that it
    #       fork() through), and then get to main() returning code 0. The
    #       process would still exit nonzero. My guess is that something in
    #       the atexit functions was failing, but that it was happening after
    #       logging, etc had been shut down.
    #       Any global state from the child process should be flushed before
    #       run_bzr_* has exited (which we *do* wait for), and any other
    #       global state is probably a remnant from the service process. Which
    #       will be cleaned up by the service itself, rather than the child.
    #       There is some concern that log files may not get flushed, so we
    #       currently call sys.exitfunc() first. The main problem is that I
    #       don't know any way to *remove* a function registered via
    #       'atexit()' so if the forking service has some state, we my try to
    #       clean it up incorrectly.
    #       Note that the bzr script itself uses sys.exitfunc(); os._exit() in
    #       the 'bzr' main script, as the teardown time of all the python
    #       state was quite noticeable in real-world runtime. As such, bzrlib
    #       should be pretty safe, or it would have been failing for people
    #       already.
    # [Decision #7]
    #   prefork vs max children vs ?
    #       For simplicity it seemed easiest to just fork when requested. Over
    #       time, I realized it would be easy to allow running an arbitrary
    #       command (no harder than just running one command), so it seemed
    #       reasonable to switch over. If we go the prefork route, then we'll
    #       need a way to tell the pre-forked children what command to run.
    #       This could be as easy as just adding one more fifo that they wait
    #       on in the same directory.
    #       For now, I've chosen not to limit the number of forked children. I
    #       don't know what a reasonable value is, and probably there are
    #       already limitations at play. (If Conch limits connections, then it
    #       will already be doing all the work, etc.)
    # [Decision #8]
    #   nicer errors on the request socket
    #       This service is meant to be run only on the local system. As such,
    #       we don't try to be extra defensive about leaking information to
    #       the one connecting to the socket. (We should still watch out what
    #       we send across the per-child fifos, since those are connected to
    #       remote clients.) Instead we try to be helpful, and tell them as
    #       much as we know about what went wrong.

    DEFAULT_PATH = '/var/run/launchpad_forking_service.sock'

    # Permissions on the master socket (rw-rw----)
    DEFAULT_PERMISSIONS = 00660

    # Wait no more than 5 minutes for children.
    WAIT_FOR_CHILDREN_TIMEOUT = 5 * 60

    SOCKET_TIMEOUT = 1.0
    SLEEP_FOR_CHILDREN_TIMEOUT = 1.0

    # No request should take longer than this to be read.
    WAIT_FOR_REQUEST_TIMEOUT = 1.0

    # If we get a fork() request, but nobody connects, just exit.
    # On a heavily loaded server it could take a few seconds, but it
    # should never take minutes.
    CHILD_CONNECT_TIMEOUT = 120

    _fork_function = os.fork

    def __init__(self, path=DEFAULT_PATH, perms=DEFAULT_PERMISSIONS):
        self.master_socket_path = path
        self._perms = perms
        self._start_time = None
        self._should_terminate = threading.Event()
        # We address these locally, in case of shutdown socket may be gc'd
        # before we are
        self._socket_timeout = socket.timeout
        self._socket_error = socket.error
        # Map from pid => (temp_path_for_handles, request_socket)
        self._child_processes = {}
        self._children_spawned = 0
        self._child_connect_timeout = self.CHILD_CONNECT_TIMEOUT

    def _create_master_socket(self):
        self._server_socket = socket.socket(
            socket.AF_UNIX, socket.SOCK_STREAM)
        self._server_socket.bind(self.master_socket_path)
        if self._perms is not None:
            os.chmod(self.master_socket_path, self._perms)
        self._server_socket.listen(5)
        self._server_socket.settimeout(self.SOCKET_TIMEOUT)
        trace.mutter('set socket timeout to: %s' % (self.SOCKET_TIMEOUT,))

    def _cleanup_master_socket(self):
        self._server_socket.close()
        try:
            os.remove(self.master_socket_path)
        except (OSError, IOError):
            # If we don't delete it, then we get 'address already in
            # use' failures.
            trace.mutter('failed to cleanup: %s' % (self.master_socket_path,))

    def _handle_sigchld(self, signum, frm):
        # We don't actually do anything here, we just want an interrupt
        # (EINTR) on socket.accept() when SIGCHLD occurs.
        pass

    def _handle_sigterm(self, signum, frm):
        # Unregister this as the default handler, 2 SIGTERMs will exit us.
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        # SIGTERM should also generate EINTR on our wait loop, so this
        # should be enough.
        self._should_terminate.set()

    def _register_signals(self):
        """Register a SIGCHILD and SIGTERM handler.

        If we have a trigger for SIGCHILD then we can quickly respond to
        clients when their process exits. The main risk is getting more EAGAIN
        errors elsewhere.

        SIGTERM allows us to cleanup nicely before we exit.
        """
        signal.signal(signal.SIGCHLD, self._handle_sigchld)
        signal.signal(signal.SIGTERM, self._handle_sigterm)

    def _unregister_signals(self):
        signal.signal(signal.SIGCHLD, signal.SIG_DFL)
        signal.signal(signal.SIGTERM, signal.SIG_DFL)

    def _compute_paths(self, base_path):
        stdin_path = os.path.join(base_path, 'stdin')
        stdout_path = os.path.join(base_path, 'stdout')
        stderr_path = os.path.join(base_path, 'stderr')
        return (stdin_path, stdout_path, stderr_path)

    def _create_child_file_descriptors(self, base_path):
        stdin_path, stdout_path, stderr_path = self._compute_paths(base_path)
        os.mkfifo(stdin_path)
        os.mkfifo(stdout_path)
        os.mkfifo(stderr_path)

    def _set_blocking(self, fd):
        """Change the file descriptor to unset the O_NONBLOCK flag."""
        flags = fcntl.fcntl(fd, fcntl.F_GETFD)
        flags = flags & (~os.O_NONBLOCK)
        fcntl.fcntl(fd, fcntl.F_SETFD, flags)

    def _open_handles(self, base_path):
        """Open the given file handles.

        This will attempt to open all of these file handles, but will not
        block while opening them, timing out after self._child_connect_timeout
        seconds.

        :param base_path: The directory where all FIFOs are located.
        :return: (stdin_fid, stdout_fid, stderr_fid).
        """
        stdin_path, stdout_path, stderr_path = self._compute_paths(base_path)
        # These open calls will block until another process connects (which
        # must connect in the same order)
        fids = []
        to_open = [(stdin_path, os.O_RDONLY), (stdout_path, os.O_WRONLY),
                   (stderr_path, os.O_WRONLY)]
        # If we set it to 0, we won't get an alarm, so require some time > 0.
        signal.alarm(max(1, self._child_connect_timeout))
        tstart = time.time()
        for path, flags in to_open:
            try:
                fids.append(os.open(path, flags))
            except OSError:
                # In production code, signal.alarm will generally just kill
                # us. But if something installs a signal handler for SIGALRM,
                # do what we can to die gracefully.
                error = ('After %.3fs we failed to open %s, exiting'
                         % (time.time() - tstart, path,))
                trace.warning(error)
                for fid in fids:
                    try:
                        os.close(fid)
                    except OSError:
                        pass
                raise errors.BzrError(error)
        # If we get to here, that means all the handles were opened
        # successfully, so cancel the wakeup call.
        signal.alarm(0)
        return fids

    def _cleanup_fifos(self, base_path):
        """Remove the FIFO objects and directory from disk."""
        stdin_path, stdout_path, stderr_path = self._compute_paths(base_path)
        # Now that we've opened the handles, delete everything so that
        # we don't leave garbage around.  Because the open() is done in
        # blocking mode, we know that someone has already connected to
        # them, and we don't want anyone else getting confused and
        # connecting.
        # See [Decision #5].
        os.remove(stdin_path)
        os.remove(stdout_path)
        os.remove(stderr_path)
        os.rmdir(base_path)

    def _bind_child_file_descriptors(self, base_path):
        # Note: by this point bzrlib has opened stderr for logging
        # (as part of starting the service process in the first place).
        # As such, it has a stream handler that writes to stderr.
        # logging tries to flush and close that, but the file is already
        # closed.
        # This just supresses that exception.
        stdin_fid, stdout_fid, stderr_fid = self._open_handles(base_path)
        logging.raiseExceptions = False
        sys.stdin.close()
        sys.stdout.close()
        sys.stderr.close()
        os.dup2(stdin_fid, 0)
        os.dup2(stdout_fid, 1)
        os.dup2(stderr_fid, 2)
        sys.stdin = os.fdopen(stdin_fid, 'rb')
        sys.stdout = os.fdopen(stdout_fid, 'wb')
        sys.stderr = os.fdopen(stderr_fid, 'wb')
        ui.ui_factory.stdin = sys.stdin
        ui.ui_factory.stdout = sys.stdout
        ui.ui_factory.stderr = sys.stderr
        self._cleanup_fifos(base_path)

    def _close_child_file_descriptors(self):
        sys.stdin.close()
        sys.stderr.close()
        sys.stdout.close()

    def become_child(self, command_argv, path):
        """We are in the spawned child code, do our magic voodoo."""
        retcode = 127  # Failed in a bad way, poor cleanup, etc.
        try:
            # Stop tracking new signals
            self._unregister_signals()
            # Reset the start time
            trace._bzr_log_start_time = time.time()
            trace.mutter('%d starting %r'
                         % (os.getpid(), command_argv))
            self._bind_child_file_descriptors(path)
            retcode = self._run_child_command(command_argv)
        finally:
            # We force os._exit() here, because we don't want to unwind
            # the stack, which has complex results. (We can get it to
            # unwind back to the cmd_launchpad_forking_service code, and
            # even back to main() reporting thereturn code, but after
            # that, suddenly the return code changes from a '0' to a
            # '1', with no logging of info.
            os._exit(retcode)

    def _run_child_command(self, command_argv):
        # This is the point where we would actually want to do something with
        # our life
        # TODO: We may want to consider special-casing the 'lp-serve'
        # command.  As that is the primary use-case for this service, it
        # might be interesting to have an already-instantiated instance,
        # where we can just pop on an extra argument and be ready to go.
        # However, that would probably only really be measurable if we
        # prefork. As it looks like ~200ms is 'fork()' time, but only
        # 50ms is run-the-command time.
        retcode = commands.run_bzr_catch_errors(command_argv)
        self._close_child_file_descriptors()
        trace.mutter('%d finished %r'
                     % (os.getpid(), command_argv))
        # TODO: Should we call sys.exitfunc() here? it allows atexit
        #       functions to fire, however, some of those may be still
        #       around from the parent process, which we don't really want.
        sys.exitfunc()
        # See [Decision #6]
        return retcode

    @staticmethod
    def command_to_argv(command_str):
        """Convert a 'foo bar' style command to [u'foo', u'bar']"""
        # command_str must be a utf-8 string
        return [s.decode('utf-8') for s in shlex.split(command_str)]

    @staticmethod
    def parse_env(env_str):
        """Convert the environment information into a dict.

        :param env_str: A string full of environment variable declarations.
            Each key is simple ascii "key: value\n"
            The string must end with "end\n".
        :return: A dict of environment variables
        """
        env = {}
        if not env_str.endswith('end\n'):
            raise ValueError('Invalid env-str: %r' % (env_str,))
        env_str = env_str[:-5]
        if not env_str:
            return env
        env_entries = env_str.split('\n')
        for entry in env_entries:
            key, value = entry.split(': ', 1)
            env[key] = value
        return env

    def fork_one_request(self, conn, client_addr, command_argv, env):
        """Fork myself and serve a request."""
        temp_name = tempfile.mkdtemp(prefix='lp-forking-service-child-')
        # Now that we've set everything up, send the response to the
        # client we create them first, so the client can start trying to
        # connect to them, while we fork and have the child do the same.
        self._children_spawned += 1
        pid = self._fork_function()
        if pid == 0:
            pid = os.getpid()
            trace.mutter('%d spawned' % (pid,))
            self._server_socket.close()
            for env_var, value in env.iteritems():
                osutils.set_or_unset_env(env_var, value)
            # See [Decision #3]
            self._create_child_file_descriptors(temp_name)
            conn.sendall('ok\n%d\n%s\n' % (pid, temp_name))
            conn.close()
            self.become_child(command_argv, temp_name)
            trace.warning('become_child returned!!!')
            sys.exit(1)
        else:
            self._child_processes[pid] = (temp_name, conn)
            self.log(client_addr, 'Spawned process %s for %r: %s'
                            % (pid, command_argv, temp_name))

    def main_loop(self):
        self._start_time = time.time()
        self._should_terminate.clear()
        self._register_signals()
        self._create_master_socket()
        trace.note('Listening on socket: %s' % (self.master_socket_path,))
        try:
            try:
                self._do_loop()
            finally:
                # Stop talking to others, we are shutting down
                self._cleanup_master_socket()
        except KeyboardInterrupt:
            # SIGINT received, try to shutdown cleanly
            pass
        trace.note('Shutting down. Waiting up to %.0fs for %d child processes'
                   % (self.WAIT_FOR_CHILDREN_TIMEOUT,
                      len(self._child_processes)))
        self._shutdown_children()
        trace.note('Exiting')

    def _do_loop(self):
        while not self._should_terminate.isSet():
            try:
                conn, client_addr = self._server_socket.accept()
            except self._socket_timeout:
                pass  # Run shutdown and children checks.
            except self._socket_error as e:
                if e.args[0] == errno.EINTR:
                    pass  # Run shutdown and children checks.
                elif e.args[0] != errno.EBADF:
                    # We can get EBADF here while we are shutting down
                    # So we just ignore it for now
                    pass
                else:
                    # Log any other failure mode
                    trace.warning("listening socket error: %s", e)
            else:
                self.log(client_addr, 'connected')
                # TODO: We should probably trap exceptions coming out of
                # this and log them, so that we don't kill the service
                # because of an unhandled error.
                # Note: settimeout is used so that a malformed request
                # doesn't cause us to hang forever.  Also note that the
                # particular implementation means that a malicious
                # client could probably send us one byte every once in a
                # while, and we would just keep trying to read it.
                # However, as a local service, we aren't worrying about
                # it.
                conn.settimeout(self.WAIT_FOR_REQUEST_TIMEOUT)
                try:
                    self.serve_one_connection(conn, client_addr)
                except self._socket_timeout as e:
                    trace.log_exception_quietly()
                    self.log(
                        client_addr, 'request timeout failure: %s' % (e,))
                    conn.sendall('FAILURE\nrequest timed out\n')
                    conn.close()
                except Exception as e:
                    trace.log_exception_quietly()
                    self.log(client_addr, 'trapped a failure while handling'
                                          ' connection: %s' % (e,))
            self._poll_children()

    def log(self, client_addr, message):
        """Log a message to the trace log.

        Include the information about what connection is being served.
        """
        if client_addr is not None:
            # Note, we don't use conn.getpeername() because if a client
            # disconnects before we get here, that raises an exception
            conn_info = '[%s] ' % (client_addr,)
        else:
            conn_info = ''
        trace.mutter('%s%s' % (conn_info, message))

    def log_information(self):
        """Log the status information.

        This includes stuff like number of children, and ... ?
        """
        self._poll_children()
        self.log(None, 'Running for %.3fs' % (time.time() - self._start_time))
        self.log(None, '%d children currently running (spawned %d total)'
                       % (len(self._child_processes), self._children_spawned))
        # Read the current information about memory consumption, etc.
        self.log(None, 'Self: %s'
                       % (resource.getrusage(resource.RUSAGE_SELF),))
        # This seems to be the sum of all rusage for all children that have
        # been collected (not for currently running children, or ones we
        # haven't "wait"ed on.) We may want to read /proc/PID/status, since
        # 'live' information is probably more useful.
        self.log(None, 'Finished children: %s'
                       % (resource.getrusage(resource.RUSAGE_CHILDREN),))

    def _poll_children(self):
        """See if children are still running, etc.

        One interesting hook here would be to track memory consumption, etc.
        """
        while self._child_processes:
            try:
                c_id, exit_code, rusage = os.wait3(os.WNOHANG)
            except OSError as e:
                if e.errno == errno.ECHILD:
                    # TODO: We handle this right now because the test suite
                    #       fakes a child, since we wanted to test some code
                    #       without actually forking anything
                    trace.mutter('_poll_children() called, and'
                        ' self._child_processes indicates there are'
                        ' children, but os.wait3() says there are not.'
                        ' current_children: %s' % (self._child_processes,))
                    return
            if c_id == 0:
                # No more children stopped right now
                return
            c_path, sock = self._child_processes.pop(c_id)
            trace.mutter('%s exited %s and usage: %s'
                         % (c_id, exit_code, rusage))
            # Cleanup the child path, before mentioning it exited to the
            # caller. This avoids a race condition in the test suite.
            if os.path.exists(c_path):
                # The child failed to cleanup after itself, do the work here
                trace.warning('Had to clean up after child %d: %s\n'
                              % (c_id, c_path))
                shutil.rmtree(c_path, ignore_errors=True)
            # See [Decision #4]
            try:
                sock.sendall('exited\n%s\n' % (exit_code,))
            except (self._socket_timeout, self._socket_error) as e:
                # The client disconnected before we wanted them to,
                # no big deal
                trace.mutter('%s\'s socket already closed: %s' % (c_id, e))
            else:
                sock.close()

    def _wait_for_children(self, secs):
        start = time.time()
        end = start + secs
        while self._child_processes:
            self._poll_children()
            if secs > 0 and time.time() > end:
                break
            time.sleep(self.SLEEP_FOR_CHILDREN_TIMEOUT)

    def _shutdown_children(self):
        self._wait_for_children(self.WAIT_FOR_CHILDREN_TIMEOUT)
        if self._child_processes:
            trace.warning('Children still running: %s'
                % ', '.join(map(str, self._child_processes)))
            for c_id in self._child_processes:
                trace.warning('sending SIGINT to %d' % (c_id,))
                os.kill(c_id, signal.SIGINT)
            # We sent the SIGINT signal, see if they exited
            self._wait_for_children(self.SLEEP_FOR_CHILDREN_TIMEOUT)
        if self._child_processes:
            # No? Then maybe something more powerful
            for c_id in self._child_processes:
                trace.warning('sending SIGKILL to %d' % (c_id,))
                os.kill(c_id, signal.SIGKILL)
            # We sent the SIGKILL signal, see if they exited
            self._wait_for_children(self.SLEEP_FOR_CHILDREN_TIMEOUT)
        if self._child_processes:
            for c_id, (c_path, sock) in self._child_processes.iteritems():
                # TODO: We should probably put something into this message?
                #       However, the likelyhood is very small that this isn't
                #       already closed because of SIGKILL + _wait_for_children
                #       And I don't really know what to say...
                sock.close()
                if os.path.exists(c_path):
                    trace.warning('Cleaning up after immortal child %d: %s\n'
                                  % (c_id, c_path))
                    shutil.rmtree(c_path)

    def _parse_fork_request(self, conn, client_addr, request):
        if request.startswith('fork-env '):
            while not request.endswith('end\n'):
                request += osutils.read_bytes_from_socket(conn)
            command, env = request[9:].split('\n', 1)
        else:
            command = request[5:].strip()
            env = 'end\n'  # No env set.
        try:
            command_argv = self.command_to_argv(command)
            env = self.parse_env(env)
        except Exception as e:
            # TODO: Log the traceback?
            self.log(client_addr, 'command or env parsing failed: %r'
                                  % (str(e),))
            conn.sendall('FAILURE\ncommand or env parsing failed: %r'
                         % (str(e),))
        else:
            return command_argv, env
        return None, None

    def serve_one_connection(self, conn, client_addr):
        request = ''
        while '\n' not in request:
            request += osutils.read_bytes_from_socket(conn)
        # telnet likes to use '\r\n' rather than '\n', and it is nice to have
        # an easy way to debug.
        request = request.replace('\r\n', '\n')
        self.log(client_addr, 'request: %r' % (request,))
        if request == 'hello\n':
            conn.sendall('ok\nyep, still alive\n')
            self.log_information()
            conn.close()
        elif request == 'quit\n':
            self._should_terminate.set()
            conn.sendall('ok\nquit command requested... exiting\n')
            conn.close()
        elif request.startswith('child_connect_timeout '):
            try:
                value = int(request.split(' ', 1)[1])
            except ValueError as e:
                conn.sendall('FAILURE: %r\n' % (e,))
            else:
                self._child_connect_timeout = value
                conn.sendall('ok\n')
            conn.close()
        elif request.startswith('fork ') or request.startswith('fork-env '):
            command_argv, env = self._parse_fork_request(conn, client_addr,
                                                         request)
            if command_argv is not None:
                # See [Decision #7]
                # TODO: Do we want to limit the number of children? And/or
                #       prefork additional instances? (the design will need to
                #       change if we prefork and run arbitrary commands.)
                self.fork_one_request(conn, client_addr, command_argv, env)
                # We don't close the conn like other code paths, since we use
                # it again later.
            else:
                conn.close()
        else:
            self.log(client_addr, 'FAILURE: unknown request: %r' % (request,))
            # See [Decision #8]
            conn.sendall('FAILURE\nunknown request: %r\n' % (request,))
            conn.close()


class cmd_launchpad_forking_service(Command):
    """Launch a long-running process, where you can ask for new processes.

    The process will block on a given AF_UNIX socket waiting for requests to
    be made.  When a request is made, it will fork itself and redirect
    stdout/in/err to fifos on the filesystem, and start running the requested
    command.  The caller will be informed where those file handles can be
    found.  Thus it only makes sense that the process connecting to the port
    must be on the same system.
    """

    aliases = ['lp-service']

    takes_options = [Option('path',
                        help='Listen for connections at PATH',
                        type=str),
                     Option('perms',
                        help='Set the mode bits for the socket, interpreted'
                             ' as an octal integer (same as chmod)'),
                     Option('preload',
                        help="Do/don't preload libraries before startup."),
                     Option('children-timeout', type=int, argname='SEC',
                        help="Only wait SEC seconds for children to exit"),
                     Option('pid-file', type=unicode,
                        help='Write the process PID to this file.')
                    ]

    def _preload_libraries(self):
        for pyname in libraries_to_preload:
            try:
                __import__(pyname)
            except ImportError as e:
                trace.mutter('failed to preload %s: %s' % (pyname, e))

    def _daemonize(self, pid_filename):
        """Turn this process into a child-of-init daemon.

        Upon request, we relinquish our control and switch to daemon mode,
        writing out the final pid of the daemon process.
        """
        # If fork fails, it will bubble out naturally and be reported by the
        # cmd logic
        pid = os.fork()
        if pid > 0:
            # Original process exits cleanly
            os._exit(0)

        # Disconnect from the parent process
        os.setsid()

        # fork again, to truly become a daemon.
        pid = os.fork()
        if pid > 0:
            os._exit(0)

        # Redirect file handles
        stdin = open('/dev/null', 'r')
        os.dup2(stdin.fileno(), sys.stdin.fileno())
        stdout = open('/dev/null', 'a+')
        os.dup2(stdout.fileno(), sys.stdout.fileno())
        stderr = open('/dev/null', 'a+', 0)
        os.dup2(stderr.fileno(), sys.stderr.fileno())

        # Now that we are a daemon, let people know what pid is running
        f = open(pid_filename, 'wb')
        try:
            f.write('%d\n' % (os.getpid(),))
        finally:
            f.close()

    def run(self, path=None, perms=None, preload=True,
            children_timeout=LPForkingService.WAIT_FOR_CHILDREN_TIMEOUT,
            pid_file=None):
        if pid_file is not None:
            self._daemonize(pid_file)
        if path is None:
            path = LPForkingService.DEFAULT_PATH
        if perms is None:
            perms = LPForkingService.DEFAULT_PERMISSIONS
        if preload:
            # We 'note' this because it often takes a fair amount of time.
            trace.note('Preloading %d modules' % (len(libraries_to_preload),))
            self._preload_libraries()
        service = LPForkingService(path, perms)
        service.WAIT_FOR_CHILDREN_TIMEOUT = children_timeout
        service.main_loop()
        if pid_file is not None:
            try:
                os.remove(pid_file)
            except (OSError, IOError) as e:
                trace.mutter('Failed to cleanup pid_file: %s\n%s'
                             % (pid_file, e))

register_command(cmd_launchpad_forking_service)


class cmd_launchpad_replay(Command):
    """Write input from stdin back to stdout or stderr.

    This is a hidden command, primarily available for testing
    cmd_launchpad_forking_service.
    """

    hidden = True

    def run(self):
        # Just read line-by-line from stdin, and write out to stdout or stderr
        # depending on the prefix
        for line in sys.stdin:
            channel, contents = line.split(' ', 1)
            channel = int(channel)
            if channel == 1:
                sys.stdout.write(contents)
                sys.stdout.flush()
            elif channel == 2:
                sys.stderr.write(contents)
                sys.stderr.flush()
            else:
                raise RuntimeError('Invalid channel request.')
        return 0

register_command(cmd_launchpad_replay)

# This list was generated by "run lsprof"ing a spawned child, and
# looking for <module ...> times, which indicate that an import
# occurred.  Another option is to run "bzr lp-serve --profile-imports"
# manually, and observe what was expensive to import.  It doesn't seem
# very easy to get this right automatically.
libraries_to_preload = [
    'bzrlib.errors',
    'bzrlib.repofmt.groupcompress_repo',
    'bzrlib.repository',
    'bzrlib.smart',
    'bzrlib.smart.protocol',
    'bzrlib.smart.request',
    'bzrlib.smart.server',
    'bzrlib.smart.vfs',
    'bzrlib.transport.local',
    'bzrlib.transport.readonly',
    'lp.codehosting.bzrutils',
    'lp.codehosting.vfs',
    'lp.codehosting.vfs.branchfs',
    'lp.codehosting.vfs.branchfsclient',
    'lp.codehosting.vfs.hooks',
    'lp.codehosting.vfs.transport',
    ]


def load_tests(standard_tests, module, loader):
    standard_tests.addTests(loader.loadTestsFromModuleNames(
        [__name__ + '.' + x for x in [
            'test_lpserve',
        ]]))
    return standard_tests
