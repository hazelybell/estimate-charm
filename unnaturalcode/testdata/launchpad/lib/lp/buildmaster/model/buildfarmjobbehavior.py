# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Base and idle BuildFarmJobBehavior classes."""

__metaclass__ = type

__all__ = [
    'BuildFarmJobBehaviorBase',
    ]

import datetime
import gzip
import logging
import os
import os.path
import tempfile

import transaction
from twisted.internet import defer
from zope.component import getUtility

from lp.buildmaster.enums import (
    BuildFarmJobType,
    BuildStatus,
    )
from lp.services.config import config
from lp.services.helpers import filenameToContentType
from lp.services.librarian.interfaces import ILibraryFileAliasSet
from lp.services.librarian.utils import copy_and_close


SLAVE_LOG_FILENAME = 'buildlog'


class BuildFarmJobBehaviorBase:
    """Ensures that all behaviors inherit the same initialization.

    All build-farm job behaviors should inherit from this.
    """

    def __init__(self, buildfarmjob):
        """Store a reference to the job_type with which we were created."""
        self.buildfarmjob = buildfarmjob
        self._builder = None

    @property
    def build(self):
        return self.buildfarmjob.build

    def setBuilder(self, builder, slave):
        """The builder should be set once and not changed."""
        self._builder = builder
        self._slave = slave

    def verifyBuildRequest(self, logger):
        """The default behavior is a no-op."""
        pass

    def updateSlaveStatus(self, raw_slave_status, status):
        """See `IBuildFarmJobBehavior`.

        The default behavior is that we don't add any extra values."""
        pass

    def getBuildCookie(self):
        """See `IPackageBuild`."""
        return '%s-%s' % (self.build.job_type.name, self.build.id)

    def getUploadDirLeaf(self, build_cookie, now=None):
        """See `IPackageBuild`."""
        if now is None:
            now = datetime.datetime.now()
        timestamp = now.strftime("%Y%m%d-%H%M%S")
        return '%s-%s' % (timestamp, build_cookie)

    def transferSlaveFileToLibrarian(self, file_sha1, filename, private):
        """Transfer a file from the slave to the librarian.

        :param file_sha1: The file's sha1, which is how the file is addressed
            in the slave XMLRPC protocol. Specially, the file_sha1 'buildlog'
            will cause the build log to be retrieved and gzipped.
        :param filename: The name of the file to be given to the librarian
            file alias.
        :param private: True if the build is for a private archive.
        :return: A Deferred that calls back with a librarian file alias.
        """
        out_file_fd, out_file_name = tempfile.mkstemp(suffix=".buildlog")
        out_file = os.fdopen(out_file_fd, "r+")

        def got_file(ignored, filename, out_file, out_file_name):
            try:
                # If the requested file is the 'buildlog' compress it
                # using gzip before storing in Librarian.
                if file_sha1 == 'buildlog':
                    out_file = open(out_file_name)
                    filename += '.gz'
                    out_file_name += '.gz'
                    gz_file = gzip.GzipFile(out_file_name, mode='wb')
                    copy_and_close(out_file, gz_file)
                    os.remove(out_file_name.replace('.gz', ''))

                # Reopen the file, seek to its end position, count and seek
                # to beginning, ready for adding to the Librarian.
                out_file = open(out_file_name)
                out_file.seek(0, 2)
                bytes_written = out_file.tell()
                out_file.seek(0)

                library_file = getUtility(ILibraryFileAliasSet).create(
                    filename, bytes_written, out_file,
                    contentType=filenameToContentType(filename),
                    restricted=private)
            finally:
                # Remove the temporary file.  getFile() closes the file
                # object.
                os.remove(out_file_name)

            return library_file.id

        d = self._slave.getFile(file_sha1, out_file)
        d.addCallback(got_file, filename, out_file, out_file_name)
        return d

    def getLogFileName(self):
        """Return the preferred file name for this job's log."""
        return 'buildlog.txt'

    def getLogFromSlave(self, queue_item):
        """Return a Deferred which fires when the log is in the librarian."""
        d = self.transferSlaveFileToLibrarian(
            SLAVE_LOG_FILENAME, self.getLogFileName(), self.build.is_private)
        return d

    @defer.inlineCallbacks
    def storeLogFromSlave(self, build_queue=None):
        """See `IBuildFarmJob`."""
        lfa_id = yield self.getLogFromSlave(
            build_queue or self.build.buildqueue_record)
        self.build.setLog(lfa_id)
        transaction.commit()

    # The list of build status values for which email notifications are
    # allowed to be sent. It is up to each callback as to whether it will
    # consider sending a notification but it won't do so if the status is not
    # in this list.
    ALLOWED_STATUS_NOTIFICATIONS = ['OK', 'PACKAGEFAIL', 'CHROOTFAIL']

    def handleStatus(self, bq, status, slave_status):
        """See `IBuildFarmJobBehavior`."""
        if bq != self.build.buildqueue_record:
            raise AssertionError(
                "%r != %r" % (bq, self.build.buildqueue_record))
        from lp.buildmaster.manager import BUILDD_MANAGER_LOG_NAME
        logger = logging.getLogger(BUILDD_MANAGER_LOG_NAME)
        notify = status in self.ALLOWED_STATUS_NOTIFICATIONS
        method = getattr(self, '_handleStatus_' + status, None)
        if method is None:
            logger.critical(
                "Unknown BuildStatus '%s' for builder '%s'"
                % (status, self.build.buildqueue_record.builder.url))
            return
        logger.info(
            'Processing finished %s build %s (%s) from builder %s'
            % (status, self.getBuildCookie(),
               self.build.buildqueue_record.specific_job.build.title,
               self.build.buildqueue_record.builder.name))
        d = method(slave_status, logger, notify)
        return d

    @defer.inlineCallbacks
    def _handleStatus_OK(self, slave_status, logger, notify):
        """Handle a package that built successfully.

        Once built successfully, we pull the files, store them in a
        directory, store build information and push them through the
        uploader.
        """
        build = self.build
        filemap = slave_status['filemap']

        # If this is a binary package build, discard it if its source is
        # no longer published.
        if build.job_type == BuildFarmJobType.PACKAGEBUILD:
            build = build.buildqueue_record.specific_job.build
            if not build.current_source_publication:
                yield self._slave.clean()
                build.updateStatus(BuildStatus.SUPERSEDED)
                self.build.buildqueue_record.destroySelf()
                return

        # Explode before collect a binary that is denied in this
        # distroseries/pocket/archive
        assert build.archive.canModifySuite(
            build.distro_series, build.pocket), (
                "%s (%s) can not be built for pocket %s in %s: illegal status"
                % (build.title, build.id, build.pocket.name, build.archive))

        # Ensure we have the correct build root as:
        # <BUILDMASTER_ROOT>/incoming/<UPLOAD_LEAF>/<TARGET_PATH>/[FILES]
        root = os.path.abspath(config.builddmaster.root)

        # Create a single directory to store build result files.
        upload_leaf = self.getUploadDirLeaf(self.getBuildCookie())
        grab_dir = os.path.join(root, "grabbing", upload_leaf)
        logger.debug("Storing build result at '%s'" % grab_dir)

        # Build the right UPLOAD_PATH so the distribution and archive
        # can be correctly found during the upload:
        #       <archive_id>/distribution_name
        # for all destination archive types.
        upload_path = os.path.join(
            grab_dir, str(build.archive.id), build.distribution.name)
        os.makedirs(upload_path)

        successful_copy_from_slave = True
        filenames_to_download = {}
        for filename in filemap:
            logger.info("Grabbing file: %s" % filename)
            out_file_name = os.path.join(upload_path, filename)
            # If the evaluated output file name is not within our
            # upload path, then we don't try to copy this or any
            # subsequent files.
            if not os.path.realpath(out_file_name).startswith(upload_path):
                successful_copy_from_slave = False
                logger.warning(
                    "A slave tried to upload the file '%s' "
                    "for the build %d." % (filename, build.id))
                break
            filenames_to_download[filemap[filename]] = out_file_name
        yield self._slave.getFiles(filenames_to_download)

        status = (
            BuildStatus.UPLOADING if successful_copy_from_slave
            else BuildStatus.FAILEDTOUPLOAD)
        # XXX wgrant: The builder should be set long before here, but
        # currently isn't.
        build.updateStatus(
            status, builder=build.buildqueue_record.builder,
            slave_status=slave_status)
        transaction.commit()

        yield self.storeLogFromSlave()

        # We only attempt the upload if we successfully copied all the
        # files from the slave.
        if successful_copy_from_slave:
            logger.info(
                "Gathered %s %d completely. Moving %s to uploader queue."
                % (build.__class__.__name__, build.id, upload_leaf))
            target_dir = os.path.join(root, "incoming")
        else:
            logger.warning(
                "Copy from slave for build %s was unsuccessful.", build.id)
            if notify:
                build.notify(
                    extra_info='Copy from slave was unsuccessful.')
            target_dir = os.path.join(root, "failed")

        if not os.path.exists(target_dir):
            os.mkdir(target_dir)

        yield self._slave.clean()
        self.build.buildqueue_record.destroySelf()
        transaction.commit()

        # Move the directory used to grab the binaries into
        # the incoming directory so the upload processor never
        # sees half-finished uploads.
        os.rename(grab_dir, os.path.join(target_dir, upload_leaf))

    @defer.inlineCallbacks
    def _handleStatus_generic_fail(self, status, slave_status, logger, notify):
        """Handle a generic build failure.

        The build, not the builder, has failed. Set its status, store
        available information, and remove the queue entry.
        """
        # XXX wgrant: The builder should be set long before here, but
        # currently isn't.
        self.build.updateStatus(
            status, builder=self.build.buildqueue_record.builder,
            slave_status=slave_status)
        transaction.commit()
        yield self.storeLogFromSlave()
        if notify:
            self.build.notify()
        yield self._slave.clean()
        self.build.buildqueue_record.destroySelf()
        transaction.commit()

    def _handleStatus_PACKAGEFAIL(self, slave_status, logger, notify):
        """Handle a package that had failed to build."""
        return self._handleStatus_generic_fail(
            BuildStatus.FAILEDTOBUILD, slave_status, logger, notify)

    def _handleStatus_DEPFAIL(self, slave_status, logger, notify):
        """Handle a package that had missing dependencies."""
        return self._handleStatus_generic_fail(
            BuildStatus.MANUALDEPWAIT, slave_status, logger, notify)

    def _handleStatus_CHROOTFAIL(self, slave_status, logger, notify):
        """Handle a package that had failed when unpacking the CHROOT."""
        return self._handleStatus_generic_fail(
            BuildStatus.CHROOTWAIT, slave_status, logger, notify)

    def _handleStatus_BUILDERFAIL(self, slave_status, logger, notify):
        """Handle builder failures.

        Fail the builder, and reset the job.
        """
        self.build.buildqueue_record.builder.failBuilder(
            "Builder returned BUILDERFAIL when asked for its status")
        self.build.buildqueue_record.reset()
        transaction.commit()

    @defer.inlineCallbacks
    def _handleStatus_ABORTED(self, slave_status, logger, notify):
        """Handle aborted builds.

        If the build was explicitly cancelled, then mark it as such.
        Otherwise, the build has failed in some unexpected way; we'll
        reset it it and clean up the slave.
        """
        if self.build.status == BuildStatus.CANCELLING:
            yield self.storeLogFromSlave()
            self.build.buildqueue_record.cancel()
        else:
            self._builder.handleFailure(logger)
            self.build.buildqueue_record.reset()
        transaction.commit()
        yield self._slave.clean()

    @defer.inlineCallbacks
    def _handleStatus_GIVENBACK(self, slave_status, logger, notify):
        """Handle automatic retry requested by builder.

        GIVENBACK pseudo-state represents a request for automatic retry
        later, the build records is delayed by reducing the lastscore to
        ZERO.
        """
        yield self._slave.clean()
        self.build.buildqueue_record.reset()
        transaction.commit()
