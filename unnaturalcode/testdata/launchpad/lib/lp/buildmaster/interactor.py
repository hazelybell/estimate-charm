# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'BuilderInteractor',
    'extract_vitals_from_db',
    ]

from collections import namedtuple
import logging
from urlparse import urlparse

import transaction
from twisted.internet import defer
from twisted.web import xmlrpc
from twisted.web.client import downloadPage
from zope.security.proxy import (
    isinstance as zope_isinstance,
    removeSecurityProxy,
    )

from lp.buildmaster.interfaces.builder import (
    BuildDaemonError,
    CannotFetchFile,
    CannotResumeHost,
    )
from lp.buildmaster.interfaces.buildfarmjobbehavior import (
    IBuildFarmJobBehavior,
    )
from lp.services import encoding
from lp.services.config import config
from lp.services.job.interfaces.job import JobStatus
from lp.services.twistedsupport import cancel_on_timeout
from lp.services.twistedsupport.processmonitor import ProcessWithTimeout
from lp.services.webapp import urlappend


class QuietQueryFactory(xmlrpc._QueryFactory):
    """XMLRPC client factory that doesn't splatter the log with junk."""
    noisy = False


class BuilderSlave(object):
    """Add in a few useful methods for the XMLRPC slave.

    :ivar url: The URL of the actual builder. The XML-RPC resource and
        the filecache live beneath this.
    """

    # WARNING: If you change the API for this, you should also change the APIs
    # of the mocks in soyuzbuilderhelpers to match. Otherwise, you will have
    # many false positives in your test run and will most likely break
    # production.

    def __init__(self, proxy, builder_url, vm_host, timeout, reactor):
        """Initialize a BuilderSlave.

        :param proxy: An XML-RPC proxy, implementing 'callRemote'. It must
            support passing and returning None objects.
        :param builder_url: The URL of the builder.
        :param vm_host: The VM host to use when resuming.
        """
        self.url = builder_url
        self._vm_host = vm_host
        self._file_cache_url = urlappend(builder_url, 'filecache')
        self._server = proxy
        self.timeout = timeout
        self.reactor = reactor

    @classmethod
    def makeBuilderSlave(cls, builder_url, vm_host, timeout, reactor=None,
                         proxy=None):
        """Create and return a `BuilderSlave`.

        :param builder_url: The URL of the slave buildd machine,
            e.g. http://localhost:8221
        :param vm_host: If the slave is virtual, specify its host machine
            here.
        :param reactor: Used by tests to override the Twisted reactor.
        :param proxy: Used By tests to override the xmlrpc.Proxy.
        """
        rpc_url = urlappend(builder_url.encode('utf-8'), 'rpc')
        if proxy is None:
            server_proxy = xmlrpc.Proxy(
                rpc_url, allowNone=True, connectTimeout=timeout)
            server_proxy.queryFactory = QuietQueryFactory
        else:
            server_proxy = proxy
        return cls(server_proxy, builder_url, vm_host, timeout, reactor)

    def _with_timeout(self, d):
        return cancel_on_timeout(d, self.timeout, self.reactor)

    def abort(self):
        """Abort the current build."""
        return self._with_timeout(self._server.callRemote('abort'))

    def clean(self):
        """Clean up the waiting files and reset the slave's internal state."""
        return self._with_timeout(self._server.callRemote('clean'))

    def echo(self, *args):
        """Echo the arguments back."""
        return self._with_timeout(self._server.callRemote('echo', *args))

    def info(self):
        """Return the protocol version and the builder methods supported."""
        return self._with_timeout(self._server.callRemote('info'))

    def status(self):
        """Return the status of the build daemon."""
        return self._with_timeout(self._server.callRemote('status'))

    def ensurepresent(self, sha1sum, url, username, password):
        # XXX: Nothing external calls this. Make it private.
        """Attempt to ensure the given file is present."""
        return self._with_timeout(self._server.callRemote(
            'ensurepresent', sha1sum, url, username, password))

    def getFile(self, sha_sum, file_to_write):
        """Fetch a file from the builder.

        :param sha_sum: The sha of the file (which is also its name on the
            builder)
        :param file_to_write: A file name or file-like object to write
            the file to
        :return: A Deferred that calls back when the download is done, or
            errback with the error string.
        """
        file_url = urlappend(self._file_cache_url, sha_sum).encode('utf8')
        # If desired we can pass a param "timeout" here but let's leave
        # it at the default value if it becomes obvious we need to
        # change it.
        return downloadPage(file_url, file_to_write, followRedirect=0)

    def getFiles(self, filemap):
        """Fetch many files from the builder.

        :param filemap: A Dictionary containing key values of the builder
            file name to retrieve, which maps to a value containing the
            file name or file object to write the file to.

        :return: A DeferredList that calls back when the download is done.
        """
        dl = defer.gatherResults([
            self.getFile(builder_file, filemap[builder_file])
            for builder_file in filemap])
        return dl

    def resume(self, clock=None):
        """Resume the builder in an asynchronous fashion.

        We use the builddmaster configuration 'socket_timeout' as
        the process timeout.

        :param clock: An optional twisted.internet.task.Clock to override
                      the default clock.  For use in tests.

        :return: a Deferred that returns a
            (stdout, stderr, subprocess exitcode) triple
        """
        url_components = urlparse(self.url)
        buildd_name = url_components.hostname.split('.')[0]
        resume_command = config.builddmaster.vm_resume_command % {
            'vm_host': self._vm_host,
            'buildd_name': buildd_name}
        # Twisted API requires string but the configuration provides unicode.
        resume_argv = [
            term.encode('utf-8') for term in resume_command.split()]
        d = defer.Deferred()
        p = ProcessWithTimeout(d, self.timeout, clock=clock)
        p.spawnProcess(resume_argv[0], tuple(resume_argv))
        return d

    def cacheFile(self, logger, libraryfilealias):
        """Make sure that the file at 'libraryfilealias' is on the slave.

        :param logger: A python `Logger` object.
        :param libraryfilealias: An `ILibraryFileAlias`.
        """
        url = libraryfilealias.http_url
        logger.info(
            "Asking builder on %s to ensure it has file %s (%s, %s)" % (
                self._file_cache_url, libraryfilealias.filename, url,
                libraryfilealias.content.sha1))
        return self.sendFileToSlave(libraryfilealias.content.sha1, url)

    def sendFileToSlave(self, sha1, url, username="", password=""):
        """Helper to send the file at 'url' with 'sha1' to this builder."""
        d = self.ensurepresent(sha1, url, username, password)

        def check_present((present, info)):
            if not present:
                raise CannotFetchFile(url, info)
        return d.addCallback(check_present)

    def build(self, buildid, builder_type, chroot_sha1, filemap, args):
        """Build a thing on this build slave.

        :param buildid: A string identifying this build.
        :param builder_type: The type of builder needed.
        :param chroot_sha1: XXX
        :param filemap: A dictionary mapping from paths to SHA-1 hashes of
            the file contents.
        :param args: A dictionary of extra arguments. The contents depend on
            the build job type.
        """
        return self._with_timeout(self._server.callRemote(
            'build', buildid, builder_type, chroot_sha1, filemap, args))


BuilderVitals = namedtuple(
    'BuilderVitals',
    ('name', 'url', 'virtualized', 'vm_host', 'builderok', 'manual',
     'build_queue'))

_BQ_UNSPECIFIED = object()


def extract_vitals_from_db(builder, build_queue=_BQ_UNSPECIFIED):
    if build_queue == _BQ_UNSPECIFIED:
        build_queue = builder.currentjob
    return BuilderVitals(
        builder.name, builder.url, builder.virtualized, builder.vm_host,
        builder.builderok, builder.manual, build_queue)


class BuilderInteractor(object):

    @staticmethod
    def makeSlaveFromVitals(vitals):
        if vitals.virtualized:
            timeout = config.builddmaster.virtualized_socket_timeout
        else:
            timeout = config.builddmaster.socket_timeout
        return BuilderSlave.makeBuilderSlave(
            vitals.url, vitals.vm_host, timeout)

    @staticmethod
    def getBuildBehavior(queue_item, builder, slave):
        if queue_item is None:
            return None
        behavior = IBuildFarmJobBehavior(queue_item.specific_job)
        behavior.setBuilder(builder, slave)
        return behavior

    @staticmethod
    @defer.inlineCallbacks
    def slaveStatus(slave):
        """Get the slave status for this builder.

        :return: A Deferred which fires when the slave dialog is complete.
            Its value is a dict containing at least builder_status, but
            potentially other values included by the current build
            behavior.
        """
        status_sentence = yield slave.status()
        status = {'builder_status': status_sentence[0]}

        # Extract detailed status and log information if present.
        # Although build_id is also easily extractable here, there is no
        # valid reason for anything to use it, so we exclude it.
        if status['builder_status'] == 'BuilderStatus.WAITING':
            status['build_status'] = status_sentence[1]
        else:
            if status['builder_status'] == 'BuilderStatus.BUILDING':
                status['logtail'] = status_sentence[2]
        defer.returnValue((status_sentence, status))

    @classmethod
    @defer.inlineCallbacks
    def rescueIfLost(cls, vitals, slave, expected_cookie, logger=None):
        """Reset the slave if its job information doesn't match the DB.

        This checks the build ID reported in the slave status against
        the given cookie. If it isn't building what we think it should
        be, the current build will be aborted and the slave cleaned in
        preparation for a new task.

        :return: A Deferred that fires when the dialog with the slave is
            finished.  Its return value is True if the slave is lost,
            False otherwise.
        """
        # 'ident_position' dict relates the position of the job identifier
        # token in the sentence received from status(), according to the
        # two statuses we care about. See lp:launchpad-buildd
        # for further information about sentence format.
        ident_position = {
            'BuilderStatus.BUILDING': 1,
            'BuilderStatus.ABORTING': 1,
            'BuilderStatus.WAITING': 2
            }

        # Determine the slave's current build cookie. For BUILDING, ABORTING
        # and WAITING we extract the string from the slave status
        # sentence, and for IDLE it is None.
        status_sentence = yield slave.status()
        status = status_sentence[0]
        if status not in ident_position.keys():
            slave_cookie = None
        else:
            slave_cookie = status_sentence[ident_position[status]]

        if slave_cookie == expected_cookie:
            # The master and slave agree about the current job. Continue.
            defer.returnValue(False)
        else:
            # The master and slave disagree. The master is our master,
            # so try to rescue the slave.
            # An IDLE slave doesn't need rescuing (SlaveScanner.scan
            # will rescue the DB side instead), and we just have to wait
            # out an ABORTING one.
            if status == 'BuilderStatus.WAITING':
                yield slave.clean()
            elif status == 'BuilderStatus.BUILDING':
                yield slave.abort()
            if logger:
                logger.info(
                    "Builder slave '%s' rescued from %r (expected %r)." %
                    (vitals.name, slave_cookie, expected_cookie))
            defer.returnValue(True)

    @classmethod
    def resumeSlaveHost(cls, vitals, slave):
        """Resume the slave host to a known good condition.

        Issues 'builddmaster.vm_resume_command' specified in the configuration
        to resume the slave.

        :raises: CannotResumeHost: if builder is not virtual or if the
            configuration command has failed.

        :return: A Deferred that fires when the resume operation finishes,
            whose value is a (stdout, stderr) tuple for success, or a Failure
            whose value is a CannotResumeHost exception.
        """
        if not vitals.virtualized:
            return defer.fail(CannotResumeHost('Builder is not virtualized.'))

        if not vitals.vm_host:
            return defer.fail(CannotResumeHost('Undefined vm_host.'))

        logger = cls._getSlaveScannerLogger()
        logger.info("Resuming %s (%s)" % (vitals.name, vitals.url))

        d = slave.resume()

        def got_resume_ok((stdout, stderr, returncode)):
            return stdout, stderr

        def got_resume_bad(failure):
            stdout, stderr, code = failure.value
            raise CannotResumeHost(
                "Resuming failed:\nOUT:\n%s\nERR:\n%s\n" % (stdout, stderr))

        return d.addCallback(got_resume_ok).addErrback(got_resume_bad)

    @classmethod
    @defer.inlineCallbacks
    def _startBuild(cls, build_queue_item, vitals, builder, slave, behavior,
                    logger):
        """Start a build on this builder.

        :param build_queue_item: A BuildQueueItem to build.
        :param logger: A logger to be used to log diagnostic information.

        :return: A Deferred that fires after the dispatch has completed whose
            value is None, or a Failure that contains an exception
            explaining what went wrong.
        """
        behavior.logStartBuild(logger)
        behavior.verifyBuildRequest(logger)

        # Set the build behavior depending on the provided build queue item.
        if not builder.builderok:
            raise BuildDaemonError(
                "Attempted to start a build on a known-bad builder.")

        # If we are building a virtual build, resume the virtual
        # machine.  Before we try and contact the resumed slave, we're
        # going to send it a message.  This is to ensure it's accepting
        # packets from the outside world, because testing has shown that
        # the first packet will randomly fail for no apparent reason.
        # This could be a quirk of the Xen guest, we're not sure.  We
        # also don't care about the result from this message, just that
        # it's sent, hence the "addBoth".  See bug 586359.
        if builder.virtualized:
            yield cls.resumeSlaveHost(vitals, slave)
            yield slave.echo("ping")

        yield behavior.dispatchBuildToSlave(build_queue_item.id, logger)

    @classmethod
    def resetOrFail(cls, vitals, slave, builder, logger, exception):
        """Handle "confirmed" build slave failures.

        Call this when there have been multiple failures that are not just
        the fault of failing jobs, or when the builder has entered an
        ABORTED state without having been asked to do so.

        In case of a virtualized/PPA buildd slave an attempt will be made
        to reset it (using `resumeSlaveHost`).

        Conversely, a non-virtualized buildd slave will be (marked as)
        failed straightaway (using `failBuilder`).

        :param logger: The logger object to be used for logging.
        :param exception: An exception to be used for logging.
        :return: A Deferred that fires after the virtual slave was resumed
            or immediately if it's a non-virtual slave.
        """
        error_message = str(exception)
        if vitals.virtualized:
            # Virtualized/PPA builder: attempt a reset, unless the failure
            # was itself a failure to reset.  (In that case, the slave
            # scanner will try again until we reach the failure threshold.)
            if not isinstance(exception, CannotResumeHost):
                logger.warn(
                    "Resetting builder: %s -- %s" % (
                        vitals.url, error_message),
                    exc_info=True)
                return cls.resumeSlaveHost(vitals, slave)
        else:
            # XXX: This should really let the failure bubble up to the
            # scan() method that does the failure counting.
            # Mark builder as 'failed'.
            logger.warn(
                "Disabling builder: %s -- %s" % (vitals.url, error_message))
            builder.failBuilder(error_message)
            transaction.commit()
        return defer.succeed(None)

    @classmethod
    @defer.inlineCallbacks
    def findAndStartJob(cls, vitals, builder, slave):
        """Find a job to run and send it to the buildd slave.

        :return: A Deferred whose value is the `IBuildQueue` instance
            found or None if no job was found.
        """
        logger = cls._getSlaveScannerLogger()
        # XXX This method should be removed in favour of two separately
        # called methods that find and dispatch the job.  It will
        # require a lot of test fixing.
        candidate = builder.acquireBuildCandidate()
        if candidate is None:
            logger.debug("No build candidates available for builder.")
            defer.returnValue(None)

        new_behavior = cls.getBuildBehavior(candidate, builder, slave)
        needed_bfjb = type(removeSecurityProxy(
            IBuildFarmJobBehavior(candidate.specific_job)))
        if not zope_isinstance(new_behavior, needed_bfjb):
            raise AssertionError(
                "Inappropriate IBuildFarmJobBehavior: %r is not a %r" %
                (new_behavior, needed_bfjb))
        yield cls._startBuild(
            candidate, vitals, builder, slave, new_behavior, logger)
        defer.returnValue(candidate)

    @staticmethod
    def extractBuildStatus(status_dict):
        """Read build status name.

        :param status_dict: build status dict from slaveStatus.
        :return: the unqualified status name, e.g. "OK".
        """
        status_string = status_dict['build_status']
        lead_string = 'BuildStatus.'
        assert status_string.startswith(lead_string), (
            "Malformed status string: '%s'" % status_string)
        return status_string[len(lead_string):]

    @classmethod
    @defer.inlineCallbacks
    def updateBuild(cls, vitals, slave, builder_factory, behavior_factory):
        """Verify the current build job status.

        Perform the required actions for each state.

        :return: A Deferred that fires when the slave dialog is finished.
        """
        # IDLE is deliberately not handled here, because it should be
        # impossible to get past rescueIfLost unless the slave matches
        # the DB, and this method isn't called unless the DB says
        # there's a job.
        statuses = yield cls.slaveStatus(slave)
        status_sentence, status_dict = statuses
        builder_status = status_dict['builder_status']
        if builder_status == 'BuilderStatus.BUILDING':
            # Build still building, collect the logtail.
            if vitals.build_queue.job.status != JobStatus.RUNNING:
                # XXX: This check should be removed once we confirm it's
                # not regularly hit.
                raise AssertionError(
                    "Job not running when assigned and slave building.")
            vitals.build_queue.logtail = encoding.guess(
                str(status_dict.get('logtail')))
            transaction.commit()
        elif builder_status == 'BuilderStatus.ABORTING':
            # Build is being aborted.
            vitals.build_queue.logtail = (
                "Waiting for slave process to be terminated")
            transaction.commit()
        elif builder_status == 'BuilderStatus.WAITING':
            # Build has finished. Delegate handling to the build itself.
            builder = builder_factory[vitals.name]
            behavior = behavior_factory(vitals.build_queue, builder, slave)
            behavior.updateSlaveStatus(status_sentence, status_dict)
            yield behavior.handleStatus(
                vitals.build_queue, cls.extractBuildStatus(status_dict),
                status_dict)
        else:
            raise AssertionError("Unknown status %s" % builder_status)

    @staticmethod
    def _getSlaveScannerLogger():
        """Return the logger instance from buildd-slave-scanner.py."""
        # XXX cprov 20071120: Ideally the Launchpad logging system
        # should be able to configure the root-logger instead of creating
        # a new object, then the logger lookups won't require the specific
        # name argument anymore. See bug 164203.
        logger = logging.getLogger('slave-scanner')
        return logger
