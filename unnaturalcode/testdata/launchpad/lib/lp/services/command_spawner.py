# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Execute commands in parallel sub-processes."""

__metaclass__ = type
__all__ = [
    'CommandSpawner',
    'OutputLineHandler',
    'ReturnCodeReceiver',
    ]

import errno
from fcntl import (
    F_GETFL,
    F_SETFL,
    fcntl,
    )
from os import O_NONBLOCK
import select
import subprocess


def get_process_output_files(process):
    """Return the files we watch for output coming from `process`."""
    return [
        process.stdout,
        process.stderr,
        ]


def make_files_nonblocking(files):
    """Put each of `files` in non-blocking mode.

    This allows the `CommandSpawner` to read all available output from a
    process without blocking until the process completes.
    """
    for this_file in files:
        fcntl(this_file, F_SETFL, fcntl(this_file, F_GETFL) | O_NONBLOCK)


def has_pending_output(poll_event):
    """Does the given event mask from `poll` indicate there's data to read?"""
    input_mask = (select.POLLIN | select.POLLPRI)
    return (poll_event & input_mask) != 0


def has_terminated(poll_event):
    """Does the given event mask from `poll` indicate process death?"""
    death_mask = (select.POLLERR | select.POLLHUP | select.POLLNVAL)
    return (poll_event & death_mask) != 0


STDOUT = 1
STDERR = 2
COMPLETION = 3


class CommandSpawner:
    """Simple manager to execute commands in parallel.

    Lets you run commands in sub-processes that will run simulaneously.
    The CommandSpawner looks for output from the running processes, and
    manages their cleanup.

    The typical usage pattern is:

    >>> spawner = CommandSpawner()
    >>> spawner.start(["echo", "One parallel process"])
    >>> spawner.start(["echo", "Another parallel process"])
    >>> spawner.complete()

    There are facilities for processing output and error output from the
    sub-processes, as well as dealing with success and failure.  You can
    pass callbacks to the `start` method, to be called when these events
    occur.

    As yet there is no facility for feeding input to the processes.
    """

    def __init__(self):
        self.running_processes = {}
        self.poll = select.poll()

    def start(self, command, stdout_handler=None, stderr_handler=None,
              completion_handler=None):
        """Run `command` in a sub-process.

        This starts the command, but does not wait for it to complete.
        Instead of waiting for completion, you can pass handlers that
        will be called when certain events occur.

        :param command: Command line to execute in a sub-process.  May be
            either a string (for a single executable name) or a list of
            strings (for an executable name plus arguments).
        :param stdout_handler: Callback to handle output received from the
            sub-process.  Must take the output as its sole argument.  May be
            called any number of times as output comes in.
        :param stderr_handler: Callback to handle error output received from
            the sub-process.  Must take the output as its sole argument.  May
            be called any number of times as output comes in.
        :param completion_handler: Callback to be invoked, exactly once, when
            the sub-process exits.  Must take `command`'s numeric return code
            as its sole argument.
        """
        process = self._spawn(command)
        handlers = {
            STDOUT: stdout_handler,
            STDERR: stderr_handler,
            COMPLETION: completion_handler,
        }
        self.running_processes[process] = handlers
        pipes = get_process_output_files(process)
        for pipe in pipes:
            self.poll.register(pipe, select.POLLIN | select.POLLPRI)
        make_files_nonblocking(pipes)

    def communicate(self):
        """Execute one iteration of the main event loop.  Blocks."""
        # Poll for output, but also wake up periodically to check for
        # completed processes.
        milliseconds = 1
        poll_result = self.poll.poll(milliseconds)

        # Map each file descriptor to its poll events.
        events_by_fd = dict(poll_result)

        # Iterate over a copy of the processes list: we may be removing
        # items from the original as processes complete.
        processes = self.running_processes.keys()
        for process in processes:
            self._service(process, events_by_fd)
            if process.returncode is not None:
                # Process has completed.  Remove it.
                try:
                    self._handle(process, COMPLETION, process.returncode)
                finally:
                    for pipe in get_process_output_files(process):
                        self.poll.unregister(pipe)
                    del self.running_processes[process]

    def complete(self):
        """Run `self.communicate` until all sub-processes have completed."""
        while len(self.running_processes) > 0:
            self.communicate()

    def kill(self):
        """Kill any remaining child processes.

        You'll still need to call `complete` to make sure that the child
        processes are cleaned up.  Until then, they will stay around as
        zombies.
        """
        for process in self.running_processes.iterkeys():
            process.terminate()

    def _spawn(self, command):
        """Spawn a sub-process for `command`.  Overridable in tests."""
        return subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            close_fds=True)

    def _handle(self, process, event, *args):
        """If we have a handler for `event` on `process`, call it."""
        process_handlers = self.running_processes[process]
        handler = process_handlers.get(event)
        if handler is not None:
            handler(*args)

    def _read(self, process, pipe_file, event):
        """Read output from `pipe_file`."""
        try:
            output = pipe_file.read()
        except IOError as e:
            # "Resource temporarily unavailable"--not an error really,
            # just means there's nothing to read.
            if e.errno != errno.EAGAIN:
                raise
        else:
            if len(output) > 0:
                self._handle(process, event, output)

    def _service(self, process, events_by_fd):
        """Service `process`."""
        stdout_events = events_by_fd.get(process.stdout.fileno(), 0)
        stderr_events = events_by_fd.get(process.stderr.fileno(), 0)
        if has_pending_output(stdout_events):
            self._read(process, process.stdout, STDOUT)
        if has_pending_output(stderr_events):
            self._read(process, process.stderr, STDERR)
        if has_terminated(stdout_events):
            process.wait()


class OutputLineHandler:
    """Collect and handle lines of output from a sub-process.

    Output received from a sub-process may not be neatly broken down by
    line.  This class collects them into lines and processes them one by
    one.  If desired, it can also add a prefix to each.
    """

    def __init__(self, line_processor, prefix=""):
        """Set up an output line handler.

        :param line_processor: A callback to be invoked for each line of
            output received.  Will receive exactly one argument: a single
            nonempty line of text, without the trailing newline.
        :param prefix: An optional string to be prefixed to each line of
            output before it is sent into the `line_processor`.
        """
        self.line_processor = line_processor
        self.prefix = prefix
        self.incomplete_buffer = ""

    def process_line(self, line):
        """Process a single line of output."""
        if line != "":
            self.line_processor("%s%s" % (self.prefix, line))

    def __call__(self, output):
        """Process multi-line output.

        Any trailing text not (yet) terminated with a newline is buffered.
        """
        lines = (self.incomplete_buffer + output).split("\n")
        if len(lines) > 0:
            self.incomplete_buffer = lines[-1]
            for line in lines[:-1]:
                self.process_line(line)

    def finalize(self):
        """Process the remaining incomplete line, if any."""
        if self.incomplete_buffer != "":
            self.process_line(self.incomplete_buffer)
            self.incomplete_buffer = ""


class ReturnCodeReceiver:
    """A minimal completion handler for `CommandSpawner` processes.

    Does nothing but collect the command's return code.

    :ivar returncode: The numerical return code retrieved from the
        process.  Stays None until the process completes.
    """

    returncode = None

    def __call__(self, returncode):
        self.returncode = returncode
