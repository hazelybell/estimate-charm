# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for `CommandSpawner`."""

__metaclass__ = type

from datetime import (
    datetime,
    timedelta,
    )
from fcntl import (
    F_GETFL,
    fcntl,
    )
from os import (
    fdopen,
    O_NONBLOCK,
    pipe,
    )

from pytz import utc
from testtools.matchers import LessThan

from lp.services.command_spawner import (
    CommandSpawner,
    OutputLineHandler,
    ReturnCodeReceiver,
    )
from lp.testing import TestCase
from lp.testing.fakemethod import FakeMethod


def make_pipe():
    """Create a pipe of `file` objects."""
    r, w = pipe()
    return fdopen(r, 'r'), fdopen(w, 'w')


def write_and_flush(pipe, text):
    """Write `text` into `pipe`, and flush."""
    pipe.write(text)
    pipe.flush()


class FakeProcess:
    """Fake `subprocess.Popen` result."""

    def __init__(self, returncode=None):
        self.returncode = returncode
        self.stdout, self.stdout_sink = make_pipe()
        self.stderr, self.stderr_sink = make_pipe()


def instrument_spawn(spawner, process):
    """Instrument `spawner` to spawn a fake process."""
    spawner._spawn = FakeMethod(result=process)


def is_nonblocking(this_file):
    """Is `this_file` in non-blocking mode?"""
    flags = fcntl(this_file, F_GETFL)
    return flags & O_NONBLOCK != 0


class TestCommandSpawner(TestCase):
    """Unit tests for `CommandSpawner`.

    Uses fake processes, so does not test all the way down to the bare metal.
    Commands are not actually run.
    """

    def _makeSpawnerAndProcess(self, returncode=None):
        """Create a `CommandSpawner` and instrument it with a `FakeProcess`.

        :return: A tuple of the spawner and the fake process it will "run."
        """
        spawner = CommandSpawner()
        process = FakeProcess(returncode=returncode)
        instrument_spawn(spawner, process)
        return spawner, process

    def test_starts_out_with_no_processes(self):
        spawner = CommandSpawner()
        self.assertEqual({}, spawner.running_processes)

    def test_completes_with_no_processes(self):
        spawner = CommandSpawner()
        spawner.complete()
        self.assertEqual({}, spawner.running_processes)

    def test_kill_works_with_no_processes(self):
        spawner = CommandSpawner()
        spawner.kill()
        self.assertEqual({}, spawner.running_processes)

    def test_start_adds_a_process(self):
        spawner, process = self._makeSpawnerAndProcess()
        spawner.start("/bin/true")
        self.assertEqual([process], spawner.running_processes.keys())

    def test_start_runs_its_command(self):
        spawner, process = self._makeSpawnerAndProcess()
        spawner.start("/bin/true")
        self.assertEqual([("/bin/true", )], spawner._spawn.extract_args())

    def test_output_is_nonblocking(self):
        spawner, process = self._makeSpawnerAndProcess()
        spawner.start("/bin/true")
        self.assertTrue(is_nonblocking(process.stdout))
        self.assertTrue(is_nonblocking(process.stderr))

    def test_can_add_multiple_processes(self):
        spawner = CommandSpawner()

        first_process = FakeProcess()
        instrument_spawn(spawner, first_process)
        spawner.start(["/bin/echo", "1"])

        second_process = FakeProcess()
        instrument_spawn(spawner, second_process)
        spawner.start(["/bin/echo", "2"])

        self.assertContentEqual(
            [first_process, second_process], spawner.running_processes)

    def test_kill_terminates_processes(self):
        spawner, process = self._makeSpawnerAndProcess()
        process.terminate = FakeMethod()
        spawner.start("/bin/cat")
        spawner.kill()
        self.assertNotEqual(0, process.terminate.call_count)

    def test_handles_output(self):
        spawner, process = self._makeSpawnerAndProcess()
        stdout_handler = FakeMethod()
        spawner.start("ls", stdout_handler=stdout_handler)
        write_and_flush(process.stdout_sink, "readme.txt\n")
        spawner.communicate()
        self.assertEqual([("readme.txt\n", )], stdout_handler.extract_args())

    def test_handles_error_output(self):
        spawner, process = self._makeSpawnerAndProcess()
        stderr_handler = FakeMethod()
        spawner.start("ls", stderr_handler=stderr_handler)
        write_and_flush(process.stderr_sink, "File not found.\n")
        spawner.communicate()
        self.assertEqual(
            [("File not found.\n", )], stderr_handler.extract_args())

    def test_does_not_call_completion_handler_until_completion(self):
        spawner, process = self._makeSpawnerAndProcess(returncode=None)
        completion_handler = FakeMethod()
        spawner.start("echo", completion_handler=completion_handler)
        spawner.communicate()
        self.assertEqual(0, completion_handler.call_count)

    def test_calls_completion_handler_on_success(self):
        spawner, process = self._makeSpawnerAndProcess(returncode=0)
        completion_handler = FakeMethod()
        spawner.start("echo", completion_handler=completion_handler)
        spawner.complete()
        self.assertEqual(1, completion_handler.call_count)

    def test_calls_completion_handler_on_failure(self):
        spawner, process = self._makeSpawnerAndProcess(returncode=1)
        completion_handler = FakeMethod()
        spawner.start("echo", completion_handler=completion_handler)
        spawner.complete()
        self.assertEqual(1, completion_handler.call_count)

    def test_does_not_call_completion_handler_twice(self):
        spawner, process = self._makeSpawnerAndProcess(returncode=0)
        completion_handler = FakeMethod()
        spawner.start("echo", completion_handler=completion_handler)
        spawner.complete()
        spawner.complete()
        self.assertEqual(1, completion_handler.call_count)

    def test_passes_return_code_to_completion_handler(self):
        spawner, process = self._makeSpawnerAndProcess(returncode=101)
        completion_handler = FakeMethod()
        spawner.start("echo", completion_handler=completion_handler)
        spawner.complete()
        self.assertEqual(((101, ), {}), completion_handler.calls[-1])

    def test_handles_output_before_completion(self):
        spawner, process = self._makeSpawnerAndProcess(returncode=0)
        handler = FakeMethod()
        spawner.start(
            "hello", stdout_handler=handler, completion_handler=handler)
        write_and_flush(process.stdout_sink, "Hello\n")
        spawner.complete()
        self.assertEqual([("Hello\n", ), (0, )], handler.extract_args())

    def test_handles_multiple_processes(self):
        spawner = CommandSpawner()
        handler = FakeMethod()

        first_process = FakeProcess(returncode=1)
        instrument_spawn(spawner, first_process)
        spawner.start(["/bin/echo", "1"], completion_handler=handler)

        second_process = FakeProcess(returncode=2)
        instrument_spawn(spawner, second_process)
        spawner.start(["/bin/echo", "2"], completion_handler=handler)

        spawner.complete()
        self.assertContentEqual([(1, ), (2, )], handler.extract_args())


class AcceptOutput:
    """Simple stdout or stderr handler."""

    def __call__(self, output):
        self.output = output


class TestCommandSpawnerAcceptance(TestCase):
    """Acceptance tests for `CommandSpawner`.

    This test spawns actual processes, so be careful:
     * Think about security when running commands.
     * Don't rely on nonstandard commands.
     * Don't hold up the test suite with slow commands.
    """

    def _makeSpawner(self):
        """Create a `CommandSpawner`, and make sure it gets cleaned up."""
        spawner = CommandSpawner()
        self.addCleanup(spawner.complete)
        self.addCleanup(spawner.kill)
        return spawner

    def test_command_can_be_string(self):
        spawner = self._makeSpawner()
        spawner.start("/bin/pwd")
        spawner.complete()

    def test_command_can_be_list(self):
        spawner = self._makeSpawner()
        spawner.start(["/bin/pwd"])
        spawner.complete()

    def test_calls_stdout_handler(self):
        spawner = self._makeSpawner()
        stdout_handler = AcceptOutput()
        spawner.start(["echo", "hi"], stdout_handler=stdout_handler)
        spawner.complete()
        self.assertEqual("hi\n", stdout_handler.output)

    def test_calls_completion_handler(self):
        spawner = self._makeSpawner()
        completion_handler = ReturnCodeReceiver()
        spawner.start("/bin/true", completion_handler=completion_handler)
        spawner.complete()
        self.assertEqual(0, completion_handler.returncode)

    def test_communicate_returns_after_event(self):
        spawner = self._makeSpawner()
        before = datetime.now(utc)
        spawner.start(["/bin/sleep", "10"])
        spawner.start("/bin/pwd")
        spawner.communicate()
        after = datetime.now(utc)
        self.assertThat(after - before, LessThan(timedelta(seconds=10)))

    def test_kill_terminates_processes(self):
        spawner = self._makeSpawner()
        spawner.start(["/bin/sleep", "10"])
        spawner.start(["/bin/sleep", "10"])
        before = datetime.now(utc)
        spawner.kill()
        spawner.complete()
        after = datetime.now(utc)
        self.assertThat(after - before, LessThan(timedelta(seconds=10)))

    def test_start_does_not_block(self):
        spawner = self._makeSpawner()
        before = datetime.now(utc)
        spawner.start(["/bin/sleep", "10"])
        after = datetime.now(utc)
        self.assertThat(after - before, LessThan(timedelta(seconds=10)))

    def test_subprocesses_run_in_parallel(self):
        spawner = self._makeSpawner()

        processes = 10
        seconds = 0.2
        for counter in xrange(processes):
            spawner.start(["/bin/sleep", str(seconds)])

        before = datetime.now(utc)
        spawner.complete()
        after = datetime.now(utc)

        sequential_time = timedelta(seconds=(seconds * processes))
        self.assertThat(after - before, LessThan(sequential_time))

    def test_integrates_with_outputlinehandler(self):
        spawner = self._makeSpawner()
        handler = OutputLineHandler(FakeMethod())
        spawner.start(["echo", "hello"], stdout_handler=handler)
        spawner.complete()
        self.assertEqual([("hello", )], handler.line_processor.extract_args())

    def test_integrates_with_returncodereceiver(self):
        spawner = self._makeSpawner()
        handler = ReturnCodeReceiver()
        spawner.start("/bin/true", completion_handler=handler)
        spawner.complete()
        self.assertEqual(0, handler.returncode)


class TestOutputLineHandler(TestCase):
    """Unit tests for `OutputLineHandler`."""

    def setUp(self):
        super(TestOutputLineHandler, self).setUp()
        self.handler = OutputLineHandler(FakeMethod())

    def _getLines(self):
        """Get the lines that were passed to `handler`'s line processor."""
        return [
            line
            for (line, ) in self.handler.line_processor.extract_args()]

    def test_processes_line(self):
        self.handler("x\n")
        self.assertEqual(["x"], self._getLines())

    def test_buffers_partial_line(self):
        self.handler("x")
        self.assertEqual([], self._getLines())

    def test_splits_lines(self):
        self.handler("a\nb\n")
        self.assertEqual(["a", "b"], self._getLines())

    def test_ignores_empty_output(self):
        self.handler("")
        self.assertEqual([], self._getLines())

    def test_finalize_ignores_empty_output(self):
        self.handler("")
        self.handler.finalize()
        self.assertEqual([], self._getLines())

    def test_ignores_empty_line(self):
        self.handler("\n")
        self.assertEqual([], self._getLines())

    def test_joins_partial_lines(self):
        self.handler("h")
        self.handler("i\n")
        self.assertEqual(["hi"], self._getLines())

    def test_joins_lines_across_multiple_calls(self):
        self.handler("h")
        self.handler("i")
        self.handler("!\n")
        self.assertEqual(["hi!"], self._getLines())

    def test_joins_lines_across_empty_calls(self):
        self.handler("h")
        self.handler("")
        self.handler("i\n")
        self.assertEqual(["hi"], self._getLines())

    def test_clears_buffer_after_joining_lines(self):
        self.handler("hi")
        self.handler("!\n")
        self.assertEqual(["hi!"], self._getLines())
        self.handler("!\n")
        self.assertEqual(["hi!", "!"], self._getLines())

    def test_finalize_processes_remaining_partial_line(self):
        self.handler("foo")
        self.handler.finalize()
        self.assertEqual(["foo"], self._getLines())

    def test_finalize_is_idempotent(self):
        self.handler("foo")
        self.handler.finalize()
        self.handler.finalize()
        self.assertEqual(["foo"], self._getLines())

    def test_finalize_joins_partial_lines(self):
        self.handler("h")
        self.handler("i")
        self.handler.finalize()
        self.assertEqual(["hi"], self._getLines())

    def test_adds_prefix(self):
        self.handler.prefix = "->"
        self.handler("here\n")
        self.assertEqual(["->here"], self._getLines())

    def test_finalize_adds_prefix(self):
        self.handler.prefix = "->"
        self.handler("here")
        self.handler.finalize()
        self.assertEqual(["->here"], self._getLines())

    def test_empty_lines_are_ignored_despite_prefix(self):
        self.handler.prefix = "->"
        self.handler("\n")
        self.assertEqual([], self._getLines())
