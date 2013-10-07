# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""SSH session implementations for the codehosting SSH server."""

__metaclass__ = type
__all__ = [
    'launch_smart_server',
    ]

import os
import signal
import socket
import sys
import urlparse

from twisted.internet import (
    error,
    interfaces,
    process,
    )
from twisted.python import log
from zope.event import notify
from zope.interface import implements

from lp.codehosting import get_bzr_path
from lp.services.config import config
from lp.services.sshserver.events import AvatarEvent
from lp.services.sshserver.session import DoNothingSession


class BazaarSSHStarted(AvatarEvent):

    template = '[%(session_id)s] %(username)s started bzr+ssh session.'


class BazaarSSHClosed(AvatarEvent):

    template = '[%(session_id)s] %(username)s closed bzr+ssh session.'


class ForbiddenCommand(Exception):
    """Raised when a session is asked to execute a forbidden command."""


class _WaitForExit(process.ProcessReader):
    """Wait on a socket for the exit status."""

    def __init__(self, reactor, proc, sock):
        super(_WaitForExit, self).__init__(reactor, proc, 'exit',
                                           sock.fileno())
        self._sock = sock
        self.connected = 1

    def close(self):
        self._sock.close()

    def dataReceived(self, data):
        # TODO: how do we handle getting only *some* of the content?, Maybe we
        #       need to read more bytes first...

        # This is the only thing we do differently from the standard
        # ProcessReader. When we get data on this socket, we need to treat it
        # as a return code, or a failure.
        if not data.startswith('exited'):
            # Bad data, we want to signal that we are closing the connection
            # TODO: How?
            self.proc.childConnectionLost(self.name, "invalid data")
            self.close()
            # I don't know what to put here if we get bogus data, but I *do*
            # want to say that the process is now considered dead to me
            log.err('Got invalid exit information: %r' % (data,))
            exit_status = (255 << 8)
        else:
            exit_status = int(data.split('\n')[1])
        self.proc.processEnded(exit_status)


class ForkedProcessTransport(process.BaseProcess):
    """Wrap the forked process in a ProcessTransport so we can talk to it.

    Note that instantiating the class creates the fork and sets it up in the
    reactor.
    """

    implements(interfaces.IProcessTransport)

    # Design decisions
    # [Decision #a]
    #   Inherit from process.BaseProcess
    #       This seems slightly risky, as process.BaseProcess is actually
    #       imported from twisted.internet._baseprocess.BaseProcess. The
    #       real-world Process then actually inherits from process._BaseProcess
    #       I've also had to copy a fair amount from the actual Process
    #       command.
    #       One option would be to inherit from process.Process, and just
    #       override stuff like __init__ and reapProcess which I don't want to
    #       do in the same way. (Is it ok not to call your Base classes
    #       __init__ if you don't want to do that exact work?)
    def __init__(self, reactor, executable, args, environment, proto):
        process.BaseProcess.__init__(self, proto)
        # Map from standard file descriptor to the associated pipe
        self.pipes = {}
        pid, path, sock = self._spawn(executable, args, environment)
        self._fifo_path = path
        self.pid = pid
        self.process_sock = sock
        self._fifo_path = path
        self._connectSpawnToReactor(reactor)
        if self.proto is not None:
            self.proto.makeConnection(self)

    def _sendMessageToService(self, message):
        """Send a message to the Forking service and get the response"""
        path = config.codehosting.forking_daemon_socket
        client_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        log.msg('Connecting to Forking Service @ socket: %s for %r'
                % (path, message))
        try:
            client_sock.connect(path)
            client_sock.sendall(message)
            # We define the requests to be no bigger than 1kB. (For now)
            response = client_sock.recv(1024)
        except socket.error as e:
            # TODO: What exceptions should be raised?
            #       Raising the raw exception seems to kill the twisted reactor
            #       Note that if the connection is refused, we *could* just
            #       fall back on a regular 'spawnProcess' call.
            log.err('Connection failed: %s' % (e,))
            raise
        if response.startswith("FAILURE"):
            client_sock.close()
            raise RuntimeError('Failed to send message: %r' % (response,))
        return response, client_sock

    def _spawn(self, executable, args, environment):
        """Start the new process.

        This talks to the ForkingSessionService and requests a new process be
        started. Similar to what Process.__init__/_fork would do.

        :return: The pid, communication directory, and request socket.
        """
        assert executable == 'bzr', executable # Maybe .endswith()
        assert args[0] == 'bzr', args[0]
        message = ['fork-env %s\n' % (' '.join(args[1:]),)]
        for key, value in environment.iteritems():
            # XXX: Currently we only pass BZR_EMAIL, should we be passing
            #      everything else? Note that many won't be handled properly,
            #      since the process is already running.
            if key != 'BZR_EMAIL':
                continue
            message.append('%s: %s\n' % (key, value))
        message.append('end\n')
        message = ''.join(message)
        response, sock = self._sendMessageToService(message)
        try:
            ok, pid, path, tail = response.split('\n')
            assert ok == 'ok'
            assert tail == ''
            pid = int(pid)
            log.msg('Forking returned pid: %d, path: %s' % (pid, path))
        except:
            sock.close()
            raise
        return pid, path, sock

    def _openHandleFailures(self, call_on_failure, path, flags, proc_class,
                            reactor, child_fd):
        """Open the given path, adding a cleanup as appropriate.

        :param call_on_failure: A list holding (callback, args) tuples. We will
            append new entries for things that we open
        :param path: The path to open
        :param flags: Flags to pass to os.open
        :param proc_class: The ProcessWriter/ProcessReader class to wrap this
            connection.
        :param reactor: The Twisted reactor we are connecting to.
        :param child_fd: The child file descriptor number passed to proc_class
        """
        fd = os.open(path, flags)
        call_on_failure.append((os.close, fd))
        p = proc_class(reactor, self, child_fd, fd)
        # Now that p has been created, it will close fd for us. So switch the
        # cleanup to calling p.connectionLost()
        call_on_failure[-1] = (p.connectionLost, (None,))
        self.pipes[child_fd] = p

    def _connectSpawnToReactor(self, reactor):
        self._exiter = _WaitForExit(reactor, self, self.process_sock)
        call_on_failure = [(self._exiter.connectionLost, (None,))]
        stdin_path = os.path.join(self._fifo_path, 'stdin')
        stdout_path = os.path.join(self._fifo_path, 'stdout')
        stderr_path = os.path.join(self._fifo_path, 'stderr')
        try:
            self._openHandleFailures(call_on_failure, stdin_path, os.O_WRONLY,
                process.ProcessWriter, reactor, 0)
            self._openHandleFailures(call_on_failure, stdout_path, os.O_RDONLY,
                process.ProcessReader, reactor, 1)
            self._openHandleFailures(call_on_failure, stderr_path, os.O_RDONLY,
                process.ProcessReader, reactor, 2)
        except:
            exc_class, exc_value, exc_tb = sys.exc_info()
            for func, args in call_on_failure:
                try:
                    func(*args)
                except:
                    # Just log any exceptions at this point. This makes sure
                    # all cleanups get called so we don't get leaks. We know
                    # there is an active exception, or we wouldn't be here.
                    log.err()
            raise exc_class, exc_value, exc_tb
        self.pipes['exit'] = self._exiter

    def _getReason(self, status):
        # Copied from twisted.internet.process._BaseProcess
        exitCode = sig = None
        if os.WIFEXITED(status):
            exitCode = os.WEXITSTATUS(status)
        else:
            sig = os.WTERMSIG(status)
        if exitCode or sig:
            return error.ProcessTerminated(exitCode, sig, status)
        return error.ProcessDone(status)

    def signalProcess(self, signalID):
        """
        Send the given signal C{signalID} to the process. It'll translate a
        few signals ('HUP', 'STOP', 'INT', 'KILL', 'TERM') from a string
        representation to its int value, otherwise it'll pass directly the
        value provided

        @type signalID: C{str} or C{int}
        """
        # Copied from twisted.internet.process._BaseProcess
        if signalID in ('HUP', 'STOP', 'INT', 'KILL', 'TERM'):
            signalID = getattr(signal, 'SIG%s' % (signalID,))
        if self.pid is None:
            raise process.ProcessExitedAlready()
        os.kill(self.pid, signalID)

    # Implemented because conch.ssh.session uses it, the Process implementation
    # ignores writes if channel '0' is not available
    def write(self, data):
        self.pipes[0].write(data)

    def writeToChild(self, childFD, data):
        # Copied from twisted.internet.process.Process
        self.pipes[childFD].write(data)

    def closeChildFD(self, childFD):
        if childFD in self.pipes:
            self.pipes[childFD].loseConnection()

    def closeStdin(self):
        self.closeChildFD(0)

    def closeStdout(self):
        self.closeChildFD(1)

    def closeStderr(self):
        self.closeChildFD(2)

    def loseConnection(self):
        self.closeStdin()
        self.closeStdout()
        self.closeStderr()

    # Implemented because ProcessWriter/ProcessReader want to call it
    # Copied from twisted.internet.Process
    def childDataReceived(self, name, data):
        self.proto.childDataReceived(name, data)

    # Implemented because ProcessWriter/ProcessReader want to call it
    # Copied from twisted.internet.Process
    def childConnectionLost(self, childFD, reason):
        pipe = self.pipes.get(childFD)
        if pipe is not None:
            close = getattr(pipe, 'close', None)
            if close is not None:
                close()
            else:
                os.close(self.pipes[childFD].fileno())
            del self.pipes[childFD]
        try:
            self.proto.childConnectionLost(childFD)
        except:
            log.err()
        self.maybeCallProcessEnded()

    # Implemented because of childConnectionLost
    # Adapted from twisted.internet.Process
    # Note: Process.maybeCallProcessEnded() tries to reapProcess() at this
    #       point, but the daemon will be doing the reaping for us (we can't
    #       because the process isn't a direct child.)
    def maybeCallProcessEnded(self):
        if self.pipes:
            # Not done if we still have open pipes
            return
        if not self.lostProcess:
            return
        process.BaseProcess.maybeCallProcessEnded(self)
    # pauseProducing, present in process.py, not a IProcessTransport interface


class ExecOnlySession(DoNothingSession):
    """Conch session that only allows executing commands."""

    def __init__(self, avatar, reactor, environment=None):
        super(ExecOnlySession, self).__init__(avatar)
        self.reactor = reactor
        self.environment = environment
        self._transport = None

    @classmethod
    def getAvatarAdapter(klass, environment=None):
        from twisted.internet import reactor
        return lambda avatar: klass(avatar, reactor, environment)

    def closed(self):
        """See ISession."""
        if self._transport is not None:
            # XXX: JonathanLange 2010-04-15: This is something of an
            # abstraction violation. Apart from this line and its twin, this
            # class knows nothing about Bazaar.
            notify(BazaarSSHClosed(self.avatar))
            try:
                self._transport.signalProcess('HUP')
            except (OSError, process.ProcessExitedAlready):
                pass
            self._transport.loseConnection()

    def eofReceived(self):
        """See ISession."""
        if self._transport is not None:
            self._transport.closeStdin()

    def execCommand(self, protocol, command):
        """Executes `command` using `protocol` as the ProcessProtocol.

        See ISession.

        :param protocol: a ProcessProtocol, usually SSHSessionProcessProtocol.
        :param command: A whitespace-separated command line. The first token is
        used as the name of the executable, the rest are used as arguments.
        """
        try:
            executable, arguments = self.getCommandToRun(command)
        except ForbiddenCommand as e:
            self.errorWithMessage(protocol, str(e) + '\r\n')
            return
        log.msg('Running: %r, %r' % (executable, arguments))
        if self._transport is not None:
            log.err(
                "ERROR: %r already running a command on transport %r"
                % (self, self._transport))
        # XXX: JonathanLange 2008-12-23: This is something of an abstraction
        # violation. Apart from this line and its twin, this class knows
        # nothing about Bazaar.
        notify(BazaarSSHStarted(self.avatar))
        self._transport = self._spawn(protocol, executable, arguments,
                                      env=self.environment)

    def _spawn(self, protocol, executable, arguments, env):
        return self.reactor.spawnProcess(protocol, executable, arguments,
                                         env=env)

    def getCommandToRun(self, command):
        """Return the command that will actually be run given `command`.

        :param command: A command line to run.
        :return: `(executable, arguments)` where `executable` is the name of an
            executable and arguments is a sequence of command-line arguments
            with the name of the executable as the first value.
        """
        args = command.split()
        return args[0], args


class RestrictedExecOnlySession(ExecOnlySession):
    """Conch session that only allows specific commands to be executed."""

    def __init__(self, avatar, reactor, lookup_command_template,
            environment=None):
        """Construct a RestrictedExecOnlySession.

        :param avatar: See `ExecOnlySession`.
        :param reactor: See `ExecOnlySession`.
        :param lookup_command_template: Lookup the template for a command.
            A template is a Python format string for the actual command that
            will be run.  '%(user_id)s' will be replaced with the 'user_id'
            attribute of the current avatar. Should raise
            ForbiddenCommand if the command is not allowed.
        """
        ExecOnlySession.__init__(self, avatar, reactor, environment)
        self.lookup_command_template = lookup_command_template

    @classmethod
    def getAvatarAdapter(klass, lookup_command_template, environment=None):
        from twisted.internet import reactor
        return lambda avatar: klass(avatar, reactor, lookup_command_template,
            environment)

    def getCommandToRun(self, command):
        """As in ExecOnlySession, but only allow a particular command.

        :raise ForbiddenCommand: when `command` is not the allowed command.
        """
        executed_command_template = self.lookup_command_template(command)
        return ExecOnlySession.getCommandToRun(
            self, executed_command_template
            % {'user_id': self.avatar.user_id})


class ForkingRestrictedExecOnlySession(RestrictedExecOnlySession):
    """Use the Forking Service instead of spawnProcess."""

    def _simplifyEnvironment(self, env):
        """Pull out the bits of the environment we want to pass along."""
        env = {}
        for env_var in ['BZR_EMAIL']:
            if env_var in self.environment:
                env[env_var] = self.environment[env_var]
        return env

    def getCommandToFork(self, executable, arguments, env):
        assert executable.endswith('/bin/py')
        assert arguments[0] == executable
        assert arguments[1].endswith('/bzr')
        executable = 'bzr'
        arguments = arguments[1:]
        arguments[0] = 'bzr'
        env = self._simplifyEnvironment(env)
        return executable, arguments, env

    def _spawn(self, protocol, executable, arguments, env):
        # When spawning, adapt the idea of "bin/py .../bzr" to just using "bzr"
        # and the executable
        executable, arguments, env = self.getCommandToFork(executable,
                                                           arguments, env)
        return ForkedProcessTransport(self.reactor, executable,
                                      arguments, env, protocol)


def lookup_command_template(command):
    """Map a command to a command template.

    :param command: Command requested by the user
    :return: Command template
    :raise ForbiddenCommand: Raised when command isn't allowed
    """
    python_command = "%(root)s/bin/py %(bzr)s" % {
            'root': config.root,
            'bzr': get_bzr_path(),
            }
    args = " lp-serve --inet %(user_id)s"
    command_template = python_command + args

    if command == 'bzr serve --inet --directory=/ --allow-writes':
        return command_template
    # At the moment, only bzr branch serving is allowed.
    raise ForbiddenCommand("Not allowed to execute %r." % (command,))


def launch_smart_server(avatar):
    from twisted.internet import reactor

    environment = dict(os.environ)

    # Extract the hostname from the supermirror root config.
    hostname = urlparse.urlparse(config.codehosting.supermirror_root)[1]
    environment['BZR_EMAIL'] = '%s@%s' % (avatar.username, hostname)
    # TODO: Use a FeatureFlag to enable this in a more fine-grained approach.
    #       If the forking daemon has been spawned, then we can use it if the
    #       feature is set to true for the given user, etc.
    #       A global config is a good first step, but does require restarting
    #       the service to change the flag. 'config' doesn't support SIGHUP.
    #       For now, restarting the service is necessary to enabled/disable the
    #       forking daemon.
    if config.codehosting.use_forking_daemon:
        klass = ForkingRestrictedExecOnlySession
    else:
        klass = RestrictedExecOnlySession

    return klass(avatar, reactor, lookup_command_template,
        environment=environment)
