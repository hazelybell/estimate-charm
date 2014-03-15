# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

import logging
import os
import textwrap

from bzrlib.branch import Branch
from bzrlib.bzrdir import (
    BzrDir,
    format_registry,
    )
from bzrlib.urlutils import join as urljoin
from testtools.deferredruntest import (
    assert_fails_with,
    AsynchronousDeferredRunTest,
    flush_logged_errors,
    )
from twisted.internet import (
    defer,
    error,
    reactor,
    )
from twisted.protocols.basic import NetstringParseError
from zope.component import getUtility

from lp.code.enums import BranchType
from lp.code.interfaces.branchlookup import IBranchLookup
from lp.code.interfaces.codehosting import LAUNCHPAD_SERVICES
from lp.codehosting.puller import (
    get_lock_id_for_branch_id,
    scheduler,
    )
from lp.codehosting.puller.tests import PullerBranchTestCase
from lp.codehosting.puller.worker import get_canonical_url_for_branch_name
from lp.services.config import config
from lp.services.twistedsupport.tests.test_processmonitor import (
    makeFailure,
    ProcessTestsMixin,
    suppress_stderr,
    )
from lp.services.webapp import errorlog
from lp.testing import (
    reset_logging,
    TestCase,
    )
from lp.testing.layers import ZopelessAppServerLayer


class FakeCodehostingEndpointProxy:

    def __init__(self):
        self.calls = []

    def callRemote(self, method_name, *args):
        method = getattr(self, '_remote_%s' % method_name, self._default)
        deferred = method(*args)

        def append_to_log(pass_through):
            self.calls.append((method_name,) + tuple(args))
            return pass_through

        deferred.addCallback(append_to_log)
        return deferred

    def _default(self, *args):
        return defer.succeed(None)

    def _remote_acquireBranchToPull(self, *args):
        return defer.succeed(0)


class TestJobScheduler(TestCase):

    def setUp(self):
        super(TestJobScheduler, self).setUp()
        self.masterlock = 'master.lock'

    def tearDown(self):
        reset_logging()
        if os.path.exists(self.masterlock):
            os.unlink(self.masterlock)
        super(TestJobScheduler, self).tearDown()

    def makeJobScheduler(self, branch_type_names=()):
        return scheduler.JobScheduler(
            FakeCodehostingEndpointProxy(), logging.getLogger(),
            branch_type_names)

    def testManagerCreatesLocks(self):
        manager = self.makeJobScheduler()
        manager.lockfilename = self.masterlock
        manager.lock()
        self.failUnless(os.path.exists(self.masterlock))
        manager.unlock()

    def testManagerEnforcesLocks(self):
        manager = self.makeJobScheduler()
        manager.lockfilename = self.masterlock
        manager.lock()
        anothermanager = self.makeJobScheduler()
        anothermanager.lockfilename = self.masterlock
        self.assertRaises(scheduler.LockError, anothermanager.lock)
        self.failUnless(os.path.exists(self.masterlock))
        manager.unlock()

    def test_run_calls_acquireBranchToPull(self):
        manager = self.makeJobScheduler(('MIRRORED',))
        manager.run()
        self.assertEqual(
            [('acquireBranchToPull', ('MIRRORED',))],
            manager.codehosting_endpoint.calls)


class TestPullerWireProtocol(TestCase):
    """Tests for the `PullerWireProtocol`.

    Some of the docstrings and comments in this class refer to state numbers
    -- see the docstring of `PullerWireProtocol` for what these mean.
    """

    run_tests_with = AsynchronousDeferredRunTest

    class StubTransport:
        def loseConnection(self):
            pass

    class StubPullerProtocol:

        def __init__(self):
            self.calls = []
            self.failure = None

        def do_method(self, *args):
            self.calls.append(('method',) + args)

        def do_raise(self):
            return 1 / 0

        def unexpectedError(self, failure):
            self.failure = failure

    def setUp(self):
        super(TestPullerWireProtocol, self).setUp()
        self.puller_protocol = self.StubPullerProtocol()
        self.protocol = scheduler.PullerWireProtocol(self.puller_protocol)
        self.protocol.makeConnection(self.StubTransport())

    def convertToNetstring(self, string):
        """Encode `string` as a netstring."""
        return '%d:%s,' % (len(string), string)

    def sendToProtocol(self, *arguments):
        """Send each element of `arguments` to the protocol as a netstring."""
        for argument in arguments:
            self.protocol.dataReceived(self.convertToNetstring(str(argument)))

    def assertUnexpectedErrorCalled(self, exception_type):
        """Assert that the puller protocol's unexpectedError has been called.

        The failure is asserted to contain an exception of type
        `exception_type`."""
        self.failUnless(self.puller_protocol.failure is not None)
        self.failUnless(
            self.puller_protocol.failure.check(exception_type))

    def assertProtocolInState0(self):
        """Assert that the protocol is in state 0."""
        return self.protocol._current_command is None

    def test_methodDispatch(self):
        # The wire protocol object calls the named method on the
        # puller_protocol.
        self.sendToProtocol('method')
        # The protocol is now in state [1]
        self.assertEqual(self.puller_protocol.calls, [])
        self.sendToProtocol(0)
        # As we say we are not passing any arguments, the protocol executes
        # the command straight away.
        self.assertEqual(self.puller_protocol.calls, [('method',)])
        self.assertProtocolInState0()

    def test_methodDispatchWithArguments(self):
        # The wire protocol waits for the given number of arguments before
        # calling the method.
        self.sendToProtocol('method', 1)
        # The protocol is now in state [2]
        self.assertEqual(self.puller_protocol.calls, [])
        self.sendToProtocol('arg')
        # We've now passed in the declared number of arguments so the protocol
        # executes the command.
        self.assertEqual(self.puller_protocol.calls, [('method', 'arg')])
        self.assertProtocolInState0()

    def test_commandRaisesException(self):
        # If a command raises an exception, the puller_protocol's
        # unexpectedError method is called with the corresponding failure.
        self.sendToProtocol('raise', 0)
        self.assertUnexpectedErrorCalled(ZeroDivisionError)
        self.assertProtocolInState0()

    def test_nonIntegerArgcount(self):
        # Passing a non integer where there should be an argument count is an
        # error.
        self.sendToProtocol('method', 'not-an-int')
        self.assertUnexpectedErrorCalled(ValueError)

    def test_unrecognizedMessage(self):
        # The protocol notifies the listener as soon as it receives an
        # unrecognized command name.
        self.sendToProtocol('foo')
        self.assertUnexpectedErrorCalled(scheduler.BadMessage)

    def test_invalidNetstring(self):
        # The protocol terminates the session if it receives an unparsable
        # netstring.
        self.protocol.dataReceived('foo')
        self.assertUnexpectedErrorCalled(NetstringParseError)


class TestPullerMonitorProtocol(ProcessTestsMixin, TestCase):
    """Tests for the process protocol used by the job manager."""

    run_tests_with = AsynchronousDeferredRunTest

    class StubPullerListener:
        """Stub listener object that records calls."""

        def __init__(self):
            self.calls = []

        def startMirroring(self):
            self.calls.append('startMirroring')

        def branchChanged(self, stacked_on_url, revid_before, revid_after,
                          control_string, branch_string, repository_string):
            self.calls.append(
                ('branchChanged', stacked_on_url, revid_before, revid_after,
                 control_string, branch_string, repository_string))

        def mirrorFailed(self, message, oops):
            self.calls.append(('mirrorFailed', message, oops))

        def log(self, message):
            self.calls.append(('log', message))

    def makeProtocol(self):
        return scheduler.PullerMonitorProtocol(
            self.termination_deferred, self.listener, self.clock)

    def setUp(self):
        self.listener = self.StubPullerListener()
        super(TestPullerMonitorProtocol, self).setUp()

    def assertProtocolSuccess(self):
        """Assert that the protocol saw no unexpected errors."""
        self.assertEqual(None, self.protocol._termination_failure)

    def test_startMirroring(self):
        """Receiving a startMirroring message notifies the listener."""
        self.protocol.do_startMirroring()
        self.assertEqual(['startMirroring'], self.listener.calls)
        self.assertProtocolSuccess()

    def test_branchChanged(self):
        """Receiving a branchChanged message notifies the listener."""
        self.protocol.do_startMirroring()
        self.listener.calls = []
        self.protocol.do_branchChanged('', 'rev1', 'rev2', '', '', '')
        self.assertEqual(
            [('branchChanged', '', 'rev1', 'rev2', '', '', '')],
            self.listener.calls)
        self.assertProtocolSuccess()

    def test_mirrorFailed(self):
        """Receiving a mirrorFailed message notifies the listener."""
        self.protocol.do_startMirroring()
        self.listener.calls = []
        self.protocol.do_mirrorFailed('Error Message', 'OOPS')
        self.assertEqual(
            [('mirrorFailed', 'Error Message', 'OOPS')], self.listener.calls)
        self.assertProtocolSuccess()

    def test_log(self):
        self.protocol.do_log('message')
        self.assertEqual(
            [('log', 'message')], self.listener.calls)

    def assertMessageResetsTimeout(self, callable, *args):
        """Assert that sending the message resets the protocol timeout."""
        self.assertTrue(2 < config.supermirror.worker_timeout)
        # Advance until the timeout has nearly elapsed.
        self.clock.advance(config.supermirror.worker_timeout - 1)
        # Send the message.
        callable(*args)
        # Advance past the timeout.
        self.clock.advance(2)
        # Check that we still succeeded.
        self.assertProtocolSuccess()

    def test_progressMadeResetsTimeout(self):
        """Receiving 'progressMade' resets the timeout."""
        self.assertMessageResetsTimeout(self.protocol.do_progressMade)

    def test_startMirroringResetsTimeout(self):
        """Receiving 'startMirroring' resets the timeout."""
        self.assertMessageResetsTimeout(self.protocol.do_startMirroring)

    def test_branchChangedDoesNotResetTimeout(self):
        """Receiving 'branchChanged' doesn't reset the timeout.

        It's possible that in pathological cases, the worker process might
        hang around even after it has said that it's finished. When that
        happens, we want to kill it quickly so that we can continue mirroring
        other branches.
        """
        self.protocol.do_startMirroring()
        self.clock.advance(config.supermirror.worker_timeout - 1)
        self.protocol.do_branchChanged('', '', '', '', '', '')
        self.clock.advance(2)
        return assert_fails_with(
            self.termination_deferred, error.TimeoutError)

    def test_mirrorFailedDoesNotResetTimeout(self):
        """Receiving 'mirrorFailed' doesn't reset the timeout.

        mirrorFailed doesn't reset the timeout for the same reasons as
        mirrorSucceeded.
        """
        self.protocol.do_startMirroring()
        self.clock.advance(config.supermirror.worker_timeout - 1)
        self.protocol.do_mirrorFailed('error message', 'OOPS')
        self.clock.advance(2)
        return assert_fails_with(
            self.termination_deferred, error.TimeoutError)

    def test_terminatesWithError(self):
        """When the child process terminates with an unexpected error, raise
        an error that includes the contents of stderr and the exit condition.
        """
        def check_failure(failure):
            self.assertEqual('error message', failure.error)
            return failure

        self.termination_deferred.addErrback(check_failure)

        self.protocol.errReceived('error message')
        self.simulateProcessExit(clean=False)

        return assert_fails_with(
            self.termination_deferred, error.ProcessTerminated)

    def test_stderrFailsProcess(self):
        """If the process prints to stderr, then the Deferred fires an
        errback, even if it terminated successfully.
        """
        def fail_if_succeeded(ignored):
            self.fail("stderr did not cause failure")

        self.termination_deferred.addCallback(fail_if_succeeded)

        def check_failure(failure):
            failure.trap(Exception)
            self.assertEqual('error message', failure.error)

        self.termination_deferred.addErrback(check_failure)

        self.protocol.errReceived('error message')
        self.simulateProcessExit()

        return self.termination_deferred

    def test_prematureFailureWithoutStderr(self):
        # If the worker dies without reporting failure and doesn't have any
        # output on standard error, then we report failure using the reason we
        # have for the worker's death.
        self.protocol.do_startMirroring()
        self.simulateProcessExit(clean=False)
        return assert_fails_with(
            self.termination_deferred, error.ProcessTerminated)

    def test_errorBeforeStatusReport(self):
        # If the subprocess exits before reporting success or failure, the
        # puller master should record failure.
        self.protocol.do_startMirroring()
        self.protocol.errReceived('traceback')
        self.simulateProcessExit(clean=False)
        self.assertEqual(
            self.listener.calls,
            ['startMirroring', ('mirrorFailed', 'traceback', None)])
        return assert_fails_with(
            self.termination_deferred, error.ProcessTerminated)

    @suppress_stderr
    def test_errorBeforeStatusReportAndFailingMirrorFailed(self):
        # If the subprocess exits before reporting success or failure, *and*
        # the attempt to record failure fails, there's not much we can do but
        # we should still not hang.  In keeping with the general policy, we
        # fire the termination deferred with the first thing to go wrong --
        # the process termination in this case -- and log.err() the failed
        # attempt to call mirrorFailed().

        runtime_error_failure = makeFailure(RuntimeError)

        class FailingMirrorFailedStubPullerListener(self.StubPullerListener):
            def mirrorFailed(self, message, oops):
                return runtime_error_failure

        self.protocol.listener = FailingMirrorFailedStubPullerListener()
        self.listener = self.protocol.listener
        self.protocol.errReceived('traceback')
        self.simulateProcessExit(clean=False)
        self.assertEqual(
            flush_logged_errors(RuntimeError), [runtime_error_failure])
        return assert_fails_with(
            self.termination_deferred, error.ProcessTerminated)


class TestPullerMaster(TestCase):

    run_tests_with = AsynchronousDeferredRunTest

    def setUp(self):
        super(TestPullerMaster, self).setUp()
        self.status_client = FakeCodehostingEndpointProxy()
        self.arbitrary_branch_id = 1
        self.eventHandler = scheduler.PullerMaster(
            self.arbitrary_branch_id, 'arbitrary-source', 'arbitrary-dest',
            BranchType.HOSTED, None, logging.getLogger(), self.status_client)

    def test_unexpectedError(self):
        """The puller master logs an OOPS when it receives an unexpected
        error.
        """
        fail = makeFailure(RuntimeError, 'error message')
        self.eventHandler.unexpectedError(fail)
        oops = self.oopses[-1]
        self.assertEqual(fail.getTraceback(), oops['tb_text'])
        self.assertEqual('error message', oops['value'])
        self.assertEqual('RuntimeError', oops['type'])
        self.assertEqual(
            get_canonical_url_for_branch_name(
                self.eventHandler.unique_name), oops['url'])

    def test_startMirroring(self):
        # startMirroring does not send a message to the endpoint.
        deferred = defer.maybeDeferred(self.eventHandler.startMirroring)

        def checkMirrorStarted(ignored):
            self.assertEqual([], self.status_client.calls)

        return deferred.addCallback(checkMirrorStarted)

    def test_branchChanged(self):
        (stacked_on_url, revid_before, revid_after, control_string,
         branch_string, repository_string
         ) = list(self.factory.getUniqueString() for i in range(6))
        deferred = defer.maybeDeferred(self.eventHandler.startMirroring)

        def branchChanged(*ignored):
            self.status_client.calls = []
            return self.eventHandler.branchChanged(
                stacked_on_url, revid_before, revid_after, control_string,
                branch_string, repository_string)
        deferred.addCallback(branchChanged)

        def checkMirrorCompleted(ignored):
            self.assertEqual(
                [('branchChanged', LAUNCHPAD_SERVICES,
                  self.arbitrary_branch_id, stacked_on_url, revid_after,
                  control_string, branch_string, repository_string)],
                self.status_client.calls)
        return deferred.addCallback(checkMirrorCompleted)

    def test_mirrorFailed(self):
        arbitrary_error_message = 'failed'

        deferred = defer.maybeDeferred(self.eventHandler.startMirroring)

        def mirrorFailed(ignored):
            self.status_client.calls = []
            return self.eventHandler.mirrorFailed(
                arbitrary_error_message, 'oops')
        deferred.addCallback(mirrorFailed)

        def checkMirrorFailed(ignored):
            self.assertEqual(
                [('mirrorFailed', self.arbitrary_branch_id,
                  arbitrary_error_message)],
                self.status_client.calls)
        return deferred.addCallback(checkMirrorFailed)


class TestPullerMasterSpawning(TestCase):

    run_tests_with = AsynchronousDeferredRunTest

    def setUp(self):
        super(TestPullerMasterSpawning, self).setUp()
        self.eventHandler = self.makePullerMaster('HOSTED')
        self.patch(reactor, 'spawnProcess', self.spawnProcess)
        self.commands_spawned = []

    def makePullerMaster(self, branch_type_name, default_stacked_on_url=None):
        if default_stacked_on_url is None:
            default_stacked_on_url = self.factory.getUniqueURL()
        return scheduler.PullerMaster(
            branch_id=self.factory.getUniqueInteger(),
            source_url=self.factory.getUniqueURL(),
            unique_name=self.factory.getUniqueString(),
            branch_type_name=branch_type_name,
            default_stacked_on_url=default_stacked_on_url,
            logger=logging.getLogger(),
            client=FakeCodehostingEndpointProxy())

    def spawnProcess(self, protocol, executable, arguments, env):
        self.commands_spawned.append(arguments)

    def test_passes_default_stacked_on_url(self):
        # If a default_stacked_on_url is passed into the master then that
        # URL is sent to the command line.
        url = self.factory.getUniqueURL()
        master = self.makePullerMaster('MIRRORED', default_stacked_on_url=url)
        master.run()
        self.assertEqual(
            [url], [arguments[-1] for arguments in self.commands_spawned])

    def test_default_stacked_on_url_not_set(self):
        # If a default_stacked_on_url is passed into the master as '' then
        # the empty string is passed as an argument to the script.
        master = self.makePullerMaster('MIRRORED', default_stacked_on_url='')
        master.run()
        self.assertEqual(
            [''], [arguments[-1] for arguments in self.commands_spawned])


# The common parts of all the worker scripts.  See
# TestPullerMasterIntegration.makePullerMaster for more.
script_header = """\
from optparse import OptionParser
from lp.codehosting.puller.worker import PullerWorkerProtocol
import sys, time
parser = OptionParser()
(options, arguments) = parser.parse_args()
(source_url, destination_url, branch_id, unique_name,
 branch_type_name, default_stacked_on_url) = arguments
from bzrlib import branch
branch = branch.Branch.open(destination_url)
protocol = PullerWorkerProtocol(sys.stdout)
"""


class TestPullerMasterIntegration(PullerBranchTestCase):
    """Tests for the puller master that launch sub-processes."""

    layer = ZopelessAppServerLayer
    run_tests_with = AsynchronousDeferredRunTest.make_factory(timeout=10)

    def setUp(self):
        super(TestPullerMasterIntegration, self).setUp()
        self.makeCleanDirectory(config.codehosting.mirrored_branches_root)
        self.bzr_tree = self.make_branch_and_tree('src-branch')
        url = urljoin(self.serveOverHTTP(), 'src-branch')
        self.bzr_tree.commit('rev1')
        branch_id = self.factory.makeAnyBranch(
            branch_type=BranchType.MIRRORED, url=url).id
        self.layer.txn.commit()
        self.db_branch = getUtility(IBranchLookup).get(branch_id)
        self.client = FakeCodehostingEndpointProxy()

    def _dumpError(self, failure):
        # XXX: JonathanLange 2007-10-17: It would be nice if we didn't have to
        # do this manually, and instead the test automatically gave us the
        # full error.
        error = getattr(failure, 'error', 'No stderr stored.')
        print error
        return failure

    def makePullerMaster(self, cls=scheduler.PullerMaster, script_text=None,
                         use_header=True):
        """Construct a PullerMaster suited to the test environment.

        :param cls: The class of the PullerMaster to construct, defaulting to
            the base PullerMaster.
        :param script_text: If passed, set up the master to run a custom
            script instead of 'scripts/mirror-branch.py'.  The passed text
            will be passed through textwrap.dedent() and appended to
            `script_header` (see above) which means the text can refer to the
            worker command line arguments, the destination branch and an
            instance of PullerWorkerProtocol.
        """
        puller_master = cls(
            self.db_branch.id, str(self.db_branch.url),
            self.db_branch.unique_name[1:], self.db_branch.branch_type.name,
            '', logging.getLogger(), self.client)
        puller_master.destination_url = os.path.abspath('dest-branch')
        if script_text is not None:
            script = open('script.py', 'w')
            if use_header:
                script.write(script_header)
            script.write(textwrap.dedent(script_text))
            script.close()
            puller_master.path_to_script = os.path.abspath('script.py')
        return puller_master

    def doDefaultMirroring(self):
        """Run the subprocess to do the mirroring and check that it succeeded.
        """
        revision_id = self.bzr_tree.branch.last_revision()

        puller_master = self.makePullerMaster()
        deferred = puller_master.mirror()

        def check_authserver_called(ignored):
            default_format = format_registry.get('default')()
            control_string = default_format.get_format_string()
            branch_string = \
                default_format.get_branch_format().get_format_string()
            repository_string = \
                default_format.repository_format.get_format_string()
            self.assertEqual(
                [('branchChanged', LAUNCHPAD_SERVICES, self.db_branch.id, '',
                  revision_id, control_string, branch_string,
                  repository_string)],
                self.client.calls)
            return ignored
        deferred.addCallback(check_authserver_called)

        def check_branch_mirrored(ignored):
            self.assertEqual(
                revision_id,
                Branch.open(puller_master.destination_url).last_revision())
            return ignored
        deferred.addCallback(check_branch_mirrored)

        return deferred

    # XXX gary 2011-11-15 bug 890816: This is a fragile test.
    def DISABLE_test_mirror(self):
        # Actually mirror a branch using a worker sub-process.
        #
        # This test actually launches a worker process and makes sure that it
        # runs successfully and that we report the successful run.
        return self.doDefaultMirroring().addErrback(self._dumpError)

    def test_stderrLoggedToOOPS(self):
        # When the child process prints to stderr and exits cleanly, the
        # contents of stderr are logged in an OOPS report.
        oops_logged = []

        def new_oops_raising((type, value, tb), request):
            oops_logged.append((type, value, tb))

        old_oops_raising = errorlog.globalErrorUtility.raising
        errorlog.globalErrorUtility.raising = new_oops_raising

        def restore_oops():
            errorlog.globalErrorUtility.raising = old_oops_raising

        self.addCleanup(restore_oops)

        expected_output = 'foo\nbar'
        stderr_script = """
        import sys
        sys.stderr.write(%r)
        """ % (expected_output,)
        master = self.makePullerMaster(
            script_text=stderr_script, use_header=False)
        deferred = master.run()

        def check_oops_report(ignored):
            self.assertEqual(1, len(oops_logged))
            oops = oops_logged[0]
            self.assertEqual(scheduler.UnexpectedStderr, oops[0])
            last_line = expected_output.splitlines()[-1]
            self.assertEqual(
                'Unexpected standard error from subprocess: %s' % last_line,
                str(oops[1]))
            self.assertEqual(expected_output, oops[2])

        return deferred.addCallback(check_oops_report)

    def test_lock_with_magic_id(self):
        # When the subprocess locks a branch, it is locked with the right ID.
        class PullerMonitorProtocolWithLockID(
            scheduler.PullerMonitorProtocol):
            """Subclass of PullerMonitorProtocol with a lock_id method.

            This protocol defines a method that records on the listener the
            lock id reported by the subprocess.
            """

            def do_lock_id(self, id):
                """Record the lock id on the listener."""
                self.listener.lock_ids.append(id)

        class PullerMasterWithLockID(scheduler.PullerMaster):
            """A subclass of PullerMaster that allows recording of lock ids.
            """

            protocol_class = PullerMonitorProtocolWithLockID

        check_lock_id_script = """
        branch.lock_write()
        protocol.mirrorFailed('a', 'b')
        protocol.sendEvent(
            'lock_id', branch.control_files._lock.peek().get('user'))
        sys.stdout.flush()
        branch.unlock()
        """

        puller_master = self.makePullerMaster(
            PullerMasterWithLockID, check_lock_id_script)
        puller_master.lock_ids = []

        # We need to create a branch at the destination_url, so that the
        # subprocess can actually create a lock.
        BzrDir.create_branch_convenience(puller_master.destination_url)

        deferred = puller_master.mirror().addErrback(self._dumpError)

        def checkID(ignored):
            self.assertEqual(
                puller_master.lock_ids,
                [get_lock_id_for_branch_id(puller_master.branch_id)])

        return deferred.addCallback(checkID)

    def _run_with_destination_locked(self, func, lock_id_delta=0):
        """Run the function `func` with the destination branch locked.

        :param func: The function that is to be run with the destination
            branch locked.  It will be called no arguments and is expected to
            return a deferred.
        :param lock_id_delta: By default, the destination branch will be
            locked as if by another worker process for the same branch.  If
            lock_id_delta != 0, the lock id will be different, so the worker
            should not break it.
        """

        # Lots of moving parts :/

        # We launch two subprocesses, one that locks the branch, tells us that
        # its done so and waits to be killed (we need to do the locking in a
        # subprocess to get the lock id to be right, see the above test).

        # When the first process tells us that it has locked the branch, we
        # run the provided function.  When the deferred this returns is called
        # or erred back, we keep hold of the result and send a signal to kill
        # the first process and wait for it to die.

        class LockingPullerMonitorProtocol(scheduler.PullerMonitorProtocol):
            """Extend PullerMonitorProtocol with a 'branchLocked' method."""

            def do_branchLocked(self):
                """Notify the listener that the branch is now locked."""
                self.listener.branchLocked()

            def connectionMade(self):
                """Record the protocol instance on the listener.

                Normally the PullerMaster doesn't need to find the protocol
                again, but we need to to be able to kill the subprocess after
                the test has completed.
                """
                self.listener.protocol = self

        class LockingPullerMaster(scheduler.PullerMaster):
            """Extend PullerMaster for the purposes of the test."""

            protocol_class = LockingPullerMonitorProtocol

            # This is where the result of the deferred returned by 'func' will
            # be stored.  We need to store seen_final_result and final_result
            # separately because we don't have any control over what
            # final_result may be (in the successful case at the time of
            # writing it is None).
            seen_final_result = False
            final_result = None

            def branchLocked(self):
                """Called when the subprocess has locked the branch.

                When this has happened, we can proceed with the main part of
                the test.
                """
                branch_locked_deferred.callback(None)

        lock_and_wait_script = """
        branch.lock_write()
        protocol.sendEvent('branchLocked')
        sys.stdout.flush()
        time.sleep(3600)
        """

        # branch_locked_deferred will be called back when the subprocess locks
        # the branch.
        branch_locked_deferred = defer.Deferred()

        # So we add the function passed in as a callback to
        # branch_locked_deferred.
        def wrapper(ignore):
            return func()
        branch_locked_deferred.addCallback(wrapper)

        # When it is done, successfully or not, we store the result on the
        # puller master and kill the locking subprocess.
        def cleanup(result):
            locking_puller_master.seen_final_result = True
            locking_puller_master.final_result = result
            try:
                locking_puller_master.protocol.transport.signalProcess('INT')
            except error.ProcessExitedAlready:
                # We can only get here if the locking subprocess somehow
                # manages to crash between locking the branch and being killed
                # by us.  In that case, locking_process_errback below will
                # cause the test to fail, so just do nothing here.
                pass
        branch_locked_deferred.addBoth(cleanup)

        locking_puller_master = self.makePullerMaster(
            LockingPullerMaster, lock_and_wait_script)
        locking_puller_master.branch_id += lock_id_delta

        # We need to create a branch at the destination_url, so that the
        # subprocess can actually create a lock.
        BzrDir.create_branch_convenience(
            locking_puller_master.destination_url)

        # Because when the deferred returned by 'func' is done we kill the
        # locking subprocess, we know that when the subprocess is done, the
        # test is done (note that this also applies if the locking script
        # fails to start up properly for some reason).
        locking_process_deferred = locking_puller_master.mirror()

        def locking_process_callback(ignored):
            # There's no way the process should have exited normally!
            self.fail("Subprocess exited normally!?")

        def locking_process_errback(failure):
            # Exiting abnormally is expected, but there are two sub-cases:
            if not locking_puller_master.seen_final_result:
                # If the locking subprocess exits abnormally before we send
                # the signal to kill it, that's bad.
                return failure
            else:
                # Afterwards, though that's the whole point :)
                # Return the result of the function passed in.
                return locking_puller_master.final_result

        return locking_process_deferred.addCallbacks(
            locking_process_callback, locking_process_errback)

    def test_mirror_with_destination_self_locked(self):
        # If the destination branch was locked by another worker, the worker
        # should break the lock and mirror the branch regardless.
        deferred = self._run_with_destination_locked(self.doDefaultMirroring)
        return deferred.addErrback(self._dumpError)

    def test_mirror_with_destination_locked_by_another(self):
        # When the destination branch is locked with a different lock it, the
        # worker should *not* break the lock and instead fail.

        # We have to use a custom worker script to lower the time we wait for
        # the lock for (the default is five minutes, too long for a test!)
        lower_timeout_script = """
        from bzrlib import lockdir
        lockdir._DEFAULT_TIMEOUT_SECONDS = 2.0
        from lp.code.enums import BranchType
        from lp.codehosting.puller.worker import (
            PullerWorker, install_worker_ui_factory)
        branch_type = BranchType.items[branch_type_name]
        install_worker_ui_factory(protocol)
        PullerWorker(
            source_url, destination_url, int(branch_id), unique_name,
            branch_type, default_stacked_on_url, protocol).mirror()
        """

        def mirror_fails_to_unlock():
            puller_master = self.makePullerMaster(
                script_text=lower_timeout_script)
            deferred = puller_master.mirror()

            def check_mirror_failed(ignored):
                self.assertEqual(len(self.client.calls), 1)
                mirror_failed_call = self.client.calls[0]
                self.assertEqual(
                    mirror_failed_call[:2],
                    ('mirrorFailed', self.db_branch.id))
                self.assertTrue(
                    "Could not acquire lock" in mirror_failed_call[2])
                return ignored

            deferred.addCallback(check_mirror_failed)
            return deferred

        deferred = self._run_with_destination_locked(
            mirror_fails_to_unlock, 1)

        return deferred.addErrback(self._dumpError)
