# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Code for 'processing' 'uploads'. Also see nascentupload.py.

Uploads are directories in the 'incoming' queue directory. They may have
arrived manually from a distribution contributor, via a poppy upload, or
they may have come from a build.

Within an upload, we may find no changes file, one, or several. One is
the usual number. To process the upload, we process each changes file
in turn. These changes files may be within a structure of sub-directories,
in which case we extract information from the names of these, to calculate
which distribution and which PPA are being uploaded to.

To process a changes file, we make checks such as that the other files
referenced by it are present, formatting is valid, signatures are correct,
checksums match, and that the .changes file represents an upload which makes
sense, eg. it is not a binary for which we have no source, or an older
version than already exists in the same target distroseries pocket.

Depending on the outcome of these checks, the changes file will either be
accepted (and the information from it, and the referenced files, imported
into the database) or it won't (and the database will be unchanged). If not
accepted, a changes file might be 'failed' or 'rejected', where failed
changes files are dropped silently, but rejected ones generate a rejection
email back to the uploader.

There are several valid reasons to fail (the changes file is so mangled
that we can't read who we should send a rejection to, or it's not correctly
signed, so we can't be sure a rejection wouldn't be spam (it may not have
been uploaded by who it says it was uploaded by). In practice, in the code
as it stands, we also consider the processing of a changes file to have
failed if it generates an unexpected exception, and there are some known
cases where it does this and a rejection would have been more useful
(see bug 35965).

Each upload directory is saved after processing, in case it is needed for
debugging purposes. This is done by moving it to a directory inside the queue
directory, beside incoming, named after the result - 'failed', 'rejected' or
'accepted'. Where there are no changes files, the upload is considered failed,
and where there is more than one changes file, the upload is assigned the
worst of the results from the various changes files found (in the order
above, failed being worst).

"""

__metaclass__ = type

import os
import shutil
import stat
import sys

from contrib.glock import GlobalLock
from sqlobject import SQLObjectNotFound
from zope.component import getUtility

from lp.app.errors import NotFoundError
from lp.archiveuploader.nascentupload import (
    EarlyReturnUploadError,
    NascentUpload,
    )
from lp.archiveuploader.uploadpolicy import (
    BuildDaemonUploadPolicy,
    UploadPolicyError,
    )
from lp.archiveuploader.utils import UploadError
from lp.buildmaster.enums import BuildStatus
from lp.buildmaster.interfaces.buildfarmjob import ISpecificBuildFarmJobSource
from lp.code.interfaces.sourcepackagerecipebuild import (
    ISourcePackageRecipeBuild,
    )
from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.interfaces.person import IPersonSet
from lp.services.log.logger import BufferLogger
from lp.services.webapp.errorlog import (
    ErrorReportingUtility,
    ScriptRequest,
    )
from lp.soyuz.interfaces.archive import (
    IArchiveSet,
    NoSuchPPA,
    )


__all__ = [
    'UploadProcessor',
    'parse_build_upload_leaf_name',
    'parse_upload_path',
    ]

UPLOAD_PATH_ERROR_TEMPLATE = (
"""Launchpad failed to process the upload path '%(upload_path)s':

%(path_error)s

It is likely that you have a configuration problem with dput/dupload.
%(extra_info)s
""")


def parse_build_upload_leaf_name(name):
    """Parse the leaf directory name of a build upload.

    :param name: Directory name.
    :return: Tuple with build farm job id.
    """
    (job_type, job_id_str) = name.split("-")[-2:]
    try:
        return (job_type, int(job_id_str))
    except TypeError:
        raise ValueError


class UploadStatusEnum:
    """Possible results from processing an upload.

    ACCEPTED: all goes well, we commit nascentupload's changes to the db
    REJECTED: nascentupload gives a well-formed rejection error,
              we send a rejection email and rollback.
    FAILED: nascentupload code raises an exception, no email, rollback
    """
    ACCEPTED = 'accepted'
    REJECTED = 'rejected'
    FAILED = 'failed'


class UploadPathError(Exception):
    """This exception happened when parsing the upload path."""


class PPAUploadPathError(Exception):
    """Exception when parsing a PPA upload path."""


class UploadProcessor:
    """Responsible for processing uploads. See module docstring."""

    def __init__(self, base_fsroot, dry_run, no_mails, builds, keep,
                 policy_for_distro, ztm, log):
        """Create a new upload processor.

        :param base_fsroot: Root path for queue to use
        :param dry_run: Run but don't commit changes to database
        :param no_mails: Don't send out any emails
        :param builds: Interpret leaf names as build ids
        :param keep: Leave the files in place, don't move them away
        :param policy_for_distro: callback to obtain Policy object for a
            distribution
        :param ztm: Database transaction to use
        :param log: Logger to use for reporting
        """
        self.base_fsroot = base_fsroot
        self.dry_run = dry_run
        self.keep = keep
        self.last_processed_upload = None
        self.log = log
        self.no_mails = no_mails
        self.builds = builds
        self._getPolicyForDistro = policy_for_distro
        self.ztm = ztm

    def processUploadQueue(self, leaf_name=None):
        """Search for uploads, and process them.

        Uploads are searched for in the 'incoming' directory inside the
        base_fsroot.

        This method also creates the 'incoming', 'accepted', 'rejected', and
        'failed' directories inside the base_fsroot if they don't yet exist.
        """
        try:
            self.log.debug("Beginning processing")

            for subdir in ["incoming", "accepted", "rejected", "failed"]:
                full_subdir = os.path.join(self.base_fsroot, subdir)
                if not os.path.exists(full_subdir):
                    self.log.debug("Creating directory %s" % full_subdir)
                    os.mkdir(full_subdir)

            fsroot = os.path.join(self.base_fsroot, "incoming")
            uploads_to_process = self.locateDirectories(fsroot)
            self.log.debug("Checked in %s, found %s"
                           % (fsroot, uploads_to_process))
            for upload in uploads_to_process:
                self.log.debug("Considering upload %s" % upload)
                if leaf_name is not None and upload != leaf_name:
                    self.log.debug("Skipping %s -- does not match %s" % (
                        upload, leaf_name))
                    continue
                try:
                    handler = UploadHandler.forProcessor(self, fsroot, upload)
                except CannotGetBuild as e:
                    self.log.warn(e)
                else:
                    handler.process()
        finally:
            self.log.debug("Rolling back any remaining transactions.")
            self.ztm.abort()

    def locateDirectories(self, fsroot):
        """Return a list of upload directories in a given queue.

        This method operates on the queue atomically, i.e. it suppresses
        changes in the queue directory, like new uploads, by acquiring
        the shared upload_queue lockfile while the directory are listed.

        :param fsroot: path to a 'queue' directory to be inspected.

        :return: a list of upload directories found in the queue
            alphabetically sorted.
        """
        # Protecting listdir by a lock ensures that we only get completely
        # finished directories listed. See lp.poppy.hooks for the other
        # locking place.
        lockfile_path = os.path.join(fsroot, ".lock")
        fsroot_lock = GlobalLock(lockfile_path)
        mode = stat.S_IMODE(os.stat(lockfile_path).st_mode)

        # XXX cprov 20081024 bug=185731: The lockfile permission can only be
        # changed by its owner. Since we can't predict which process will
        # create it in production systems we simply ignore errors when trying
        # to grant the right permission. At least, one of the process will
        # be able to do so.
        try:
            os.chmod(lockfile_path, mode | stat.S_IWGRP)
        except OSError as err:
            self.log.debug('Could not fix the lockfile permission: %s' % err)

        try:
            fsroot_lock.acquire(blocking=True)
            dir_names = os.listdir(fsroot)
        finally:
            # Skip lockfile deletion, see similar code in lp.poppy.hooks.
            fsroot_lock.release(skip_delete=True)

        sorted_dir_names = sorted(
            dir_name
            for dir_name in dir_names
            if os.path.isdir(os.path.join(fsroot, dir_name)))

        return sorted_dir_names


class UploadHandler:
    """Handler for processing a single upload."""

    def __init__(self, processor, fsroot, upload):
        """Constructor.

        :param processor: The `UploadProcessor` that requested processing the
            upload.
        :param fsroot: Path to the directory containing the upload directory
        :param upload: Name of the directory containing the upload.
        """
        self.processor = processor
        self.fsroot = fsroot
        self.upload = upload
        self.upload_path = os.path.join(self.fsroot, self.upload)

    @staticmethod
    def forProcessor(processor, fsroot, upload, build=None):
        """Instantiate an UploadHandler subclass for a given upload.

        :param processor: The `UploadProcessor` that requested processing the
            upload.
        :param fsroot: Path to the directory containing the upload directory
        :param upload: Name of the directory containing the upload.
        :param build: Optional; the build that produced the upload.
        """
        if processor.builds:
            # Upload directories contain build results,
            # directories are named after job ids.
            return BuildUploadHandler(processor, fsroot, upload, build)
        else:
            assert build is None
            return UserUploadHandler(processor, fsroot, upload)

    def locateChangesFiles(self):
        """Locate .changes files in the upload directory.

        Return .changes files sorted with *_source.changes first. This
        is important to us, as in an upload containing several changes files,
        it's possible the binary ones will depend on the source ones, so
        the source ones should always be considered first.
        """
        changes_files = []

        for dirpath, dirnames, filenames in os.walk(self.upload_path):
            relative_path = dirpath[len(self.upload_path) + 1:]
            for filename in filenames:
                if filename.endswith(".changes"):
                    changes_files.append(
                        os.path.join(relative_path, filename))
        return self.orderFilenames(changes_files)

    def processChangesFile(self, changes_file, logger=None):
        """Process a single changes file.

        This is done by obtaining the appropriate upload policy (according
        to command-line options and the value in the .distro file beside
        the upload, if present), creating a NascentUpload object and calling
        its process method.

        We obtain the context for this processing from the relative path,
        within the upload folder, of this changes file. This influences
        our creation both of upload policy and the NascentUpload object.

        See nascentupload.py for the gory details.

        Returns a value from UploadStatusEnum, or re-raises an exception
        from NascentUpload.

        :param changes_file: filename of the changes file to process.
        :param logger: logger to use for processing.
        :return: an `UploadStatusEnum` value
        """
        if logger is None:
            logger = self.processor.log
        # Calculate the distribution from the path within the upload
        # Reject the upload since we could not process the path,
        # Store the exception information as a rejection message.
        relative_path = os.path.dirname(changes_file)
        upload_path_error = None
        try:
            (distribution, suite_name,
             archive) = parse_upload_path(relative_path)
        except UploadPathError as e:
            # pick some defaults to create the NascentUpload() object.
            # We will be rejecting the upload so it doesn matter much.
            distribution = getUtility(IDistributionSet)['ubuntu']
            suite_name = None
            archive = distribution.main_archive
            upload_path_error = UPLOAD_PATH_ERROR_TEMPLATE % (
                dict(upload_path=relative_path, path_error=str(e),
                     extra_info=(
                         "Please update your dput/dupload configuration "
                         "and then re-upload.")))
        except PPAUploadPathError as e:
            # Again, pick some defaults but leave a hint for the rejection
            # emailer that it was a PPA failure.
            distribution = getUtility(IDistributionSet)['ubuntu']
            suite_name = None
            # XXX cprov 20071212: using the first available PPA is not exactly
            # fine because it can confuse the code that sends rejection
            # messages if it relies only on archive.purpose (which should be
            # enough). On the other hand if we set an arbitrary owner it
            # will break nascentupload ACL calculations.
            archive = distribution.getAllPPAs()[0]
            upload_path_error = UPLOAD_PATH_ERROR_TEMPLATE % (
                dict(upload_path=relative_path, path_error=str(e),
                     extra_info=(
                         "Please check the documentation at "
                         "https://help.launchpad.net/Packaging/PPA#Uploading "
                         "and update your configuration.")))
        logger.debug("Finding fresh policy")
        policy = self._getPolicyForDistro(distribution)
        policy.archive = archive

        # DistroSeries overriding respect the following precedence:
        #  1. process-upload.py command-line option (-r),
        #  2. upload path,
        #  3. changesfile 'Distribution' field.
        if suite_name is not None:
            policy.setDistroSeriesAndPocket(suite_name)

        # The path we want for NascentUpload is the path to the folder
        # containing the changes file (and the other files referenced by it).
        changesfile_path = os.path.join(self.upload_path, changes_file)
        try:
            upload = NascentUpload.from_changesfile_path(
                changesfile_path, policy, self.processor.log)
        except UploadError as e:
            # We failed to parse the changes file, so we have no key or
            # Changed-By to notify of the rejection. Just log it and
            # move on.
            # XXX wgrant 2011-09-29 bug=499438: With some refactoring we
            # could do better here: if we have a signature then we have
            # somebody to email, even if the rest of the file is
            # corrupt.
            logger.info(
                "Failed to parse changes file '%s': %s" % (
                    os.path.join(self.upload_path, changes_file),
                    str(e)))
            return UploadStatusEnum.REJECTED

        # Reject source upload to buildd upload paths.
        first_path = relative_path.split(os.path.sep)[0]
        if (first_path.isdigit() and
            policy.name != BuildDaemonUploadPolicy.name):
            error_message = (
                "Invalid upload path (%s) for this policy (%s)" %
                (relative_path, policy.name))
            upload.reject(error_message)
            logger.error(error_message)

        # Reject upload with path processing errors.
        if upload_path_error is not None:
            upload.reject(upload_path_error)

        # Store processed NascentUpload instance, mostly used for tests.
        self.processor.last_processed_upload = upload

        try:
            logger.info("Processing upload %s" % upload.changes.filename)
            result = UploadStatusEnum.ACCEPTED

            try:
                self._processUpload(upload)
            except UploadPolicyError as e:
                upload.reject("UploadPolicyError escaped upload.process: "
                              "%s " % e)
                logger.debug(
                    "UploadPolicyError escaped upload.process", exc_info=True)
            except (KeyboardInterrupt, SystemExit):
                raise
            except EarlyReturnUploadError:
                # An error occurred that prevented further error collection,
                # add this fact to the list of errors.
                upload.reject(
                    "Further error processing not possible because of "
                    "a critical previous error.")
            except Exception as e:
                # In case of unexpected unhandled exception, we'll
                # *try* to reject the upload. This may fail and cause
                # a further exception, depending on the state of the
                # nascentupload objects. In that case, we've lost nothing,
                # the new exception will be handled by the caller just like
                # the one we caught would have been, by failing the upload
                # with no email.
                logger.exception("Unhandled exception processing upload")
                upload.reject("Unhandled exception processing upload: %s" % e)

            # XXX julian 2007-05-25 bug=29744:
            # When bug #29744 is fixed (zopeless mails should only be sent
            # when transaction is committed) this will cause any emails sent
            # sent by do_reject to be lost.
            notify = True
            if self.processor.dry_run or self.processor.no_mails:
                notify = False
            if upload.is_rejected:
                result = UploadStatusEnum.REJECTED
                upload.do_reject(notify)
                self.processor.ztm.abort()
            else:
                successful = self._acceptUpload(upload, notify)
                if not successful:
                    result = UploadStatusEnum.REJECTED
                    logger.info(
                        "Rejection during accept. Aborting partial accept.")
                    self.processor.ztm.abort()

            if upload.is_rejected:
                logger.info("Upload was rejected:")
                for msg in upload.rejections:
                    logger.info("\t%s" % msg)

            if self.processor.dry_run:
                logger.info("Dry run, aborting transaction.")
                self.processor.ztm.abort()
            else:
                logger.info(
                    "Committing the transaction and any mails associated "
                    "with this upload.")
                self.processor.ztm.commit()
        except:
            self.processor.ztm.abort()
            raise

        return result

    def removeUpload(self, logger):
        """Remove an upload that has succesfully been processed.

        This includes moving the given upload directory and moving the
        matching .distro file, if it exists.

        :param logger: The logger to use for logging results.
        """
        if self.processor.keep or self.processor.dry_run:
            logger.debug("Keeping contents untouched")
            return

        logger.debug("Removing upload directory %s", self.upload_path)
        shutil.rmtree(self.upload_path)

        distro_filename = self.upload_path + ".distro"
        if os.path.isfile(distro_filename):
            logger.debug("Removing distro file %s", distro_filename)
            os.remove(distro_filename)

    def moveProcessedUpload(self, destination, logger):
        """Move or remove the upload depending on the status of the upload.

        :param destination: An `UploadStatusEnum` value.
        :param logger: The logger to use for logging results.
        """
        if destination == "accepted":
            self.removeUpload(logger)
        else:
            self.moveUpload(destination, logger)

    def moveUpload(self, subdir_name, logger):
        """Move the upload to the named subdir of the root, eg 'accepted'.

        This includes moving the given upload directory and moving the
        matching .distro file, if it exists.

        :param subdir_name: Name of the subdirectory to move to.
        :param logger: The logger to use for logging results.
        """
        if self.processor.keep or self.processor.dry_run:
            logger.debug("Keeping contents untouched")
            return

        pathname = os.path.basename(self.upload_path)

        target_path = os.path.join(
            self.processor.base_fsroot, subdir_name, pathname)
        logger.debug("Moving upload directory %s to %s" %
            (self.upload_path, target_path))
        shutil.move(self.upload_path, target_path)

        distro_filename = self.upload_path + ".distro"
        if os.path.isfile(distro_filename):
            target_path = os.path.join(self.processor.base_fsroot,
                                       subdir_name,
                                       os.path.basename(distro_filename))
            logger.debug("Moving distro file %s to %s" % (distro_filename,
                                                            target_path))
            shutil.move(distro_filename, target_path)

    @staticmethod
    def orderFilenames(fnames):
        """Order filenames, sorting *_source.changes before others.

        Aside from that, a standard string sort.
        """

        def sourceFirst(filename):
            return (not filename.endswith("_source.changes"), filename)

        return sorted(fnames, key=sourceFirst)


class UserUploadHandler(UploadHandler):

    def process(self):
        """Process an upload's changes files, and move it to a new directory.

        The destination directory depends on the result of the processing
        of the changes files. If there are no changes files, the result
        is 'failed', otherwise it is the worst of the results from the
        individual changes files, in order 'failed', 'rejected', 'accepted'.
        """
        changes_files = self.locateChangesFiles()

        results = set()

        for changes_file in changes_files:
            self.processor.log.debug(
                "Considering changefile %s" % changes_file)
            try:
                results.add(self.processChangesFile(
                    changes_file, self.processor.log))
            except (KeyboardInterrupt, SystemExit):
                raise
            except:
                info = sys.exc_info()
                message = (
                    'Exception while processing upload %s' % self.upload_path)
                properties = [('error-explanation', message)]
                request = ScriptRequest(properties)
                error_utility = ErrorReportingUtility()
                error_utility.raising(info, request)
                self.processor.log.error(
                    '%s (%s)' % (message, request.oopsid))
                results.add(UploadStatusEnum.FAILED)
        if len(results) == 0:
            destination = UploadStatusEnum.FAILED
        else:
            for destination in [
                UploadStatusEnum.FAILED, UploadStatusEnum.REJECTED,
                UploadStatusEnum.ACCEPTED]:
                if destination in results:
                    break
        self.moveProcessedUpload(destination, self.processor.log)

    def _getPolicyForDistro(self, distribution):
        return self.processor._getPolicyForDistro(distribution, None)

    def _processUpload(self, upload):
        upload.process(None)

    def _acceptUpload(self, upload, notify):
        return upload.do_accept(notify=notify, build=None)


class CannotGetBuild(Exception):

    """Attempting to retrieve the build for this upload failed."""


class BuildUploadHandler(UploadHandler):

    def __init__(self, processor, fsroot, upload, build=None):
        """Constructor.

        See `UploadHandler`.
        :build: Optional build that produced this upload.  If not supplied,
            will be retrieved using the id in the upload.
        :raises: CannotGetBuild if the build could not be retrieved.
        """
        super(BuildUploadHandler, self).__init__(processor, fsroot, upload)
        self.build = build
        if self.build is None:
            self.build = self._getBuild()

    def _getPolicyForDistro(self, distribution):
        return self.processor._getPolicyForDistro(distribution, self.build)

    def _processUpload(self, upload):
        upload.process(self.build)

    def _acceptUpload(self, upload, notify):
        return upload.do_accept(notify=notify, build=self.build)

    def _getBuild(self):
        try:
            job_type, job_id = parse_build_upload_leaf_name(self.upload)
        except ValueError:
            raise CannotGetBuild(
                "Unable to extract build id from leaf name %s, skipping." %
                self.upload)
        try:
            return getUtility(ISpecificBuildFarmJobSource, job_type).getByID(
                job_id)
        except NotFoundError:
            raise CannotGetBuild(
                "Unable to find %s with id %d. Skipping." %
                (job_type, job_id))

    def process(self):
        """Process an upload that is the result of a build.

        The name of the leaf is the build id of the build.
        Build uploads always contain a single package per leaf.
        """
        logger = BufferLogger()
        if self.build.status != BuildStatus.UPLOADING:
            self.processor.log.warn(
                "Expected build status to be 'UPLOADING', was %s. Ignoring." %
                self.build.status.name)
            return
        try:
            # The recipe may have been deleted so we need to flag that here
            # and will handle below. We check so that we don't go to the
            # expense of doing an unnecessary upload. We don't just exit here
            # because we want the standard cleanup to occur.
            recipe_deleted = (ISourcePackageRecipeBuild.providedBy(self.build)
                and self.build.recipe is None)
            if recipe_deleted:
                result = UploadStatusEnum.FAILED
            else:
                self.processor.log.debug("Build %s found" % self.build.id)
                [changes_file] = self.locateChangesFiles()
                logger.debug("Considering changefile %s" % changes_file)
                result = self.processChangesFile(changes_file, logger)
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            info = sys.exc_info()
            message = (
                'Exception while processing upload %s' % self.upload_path)
            properties = [('error-explanation', message)]
            request = ScriptRequest(properties)
            error_utility = ErrorReportingUtility()
            error_utility.raising(info, request)
            logger.error('%s (%s)' % (message, request.oopsid))
            result = UploadStatusEnum.FAILED
        if (result != UploadStatusEnum.ACCEPTED or
            not self.build.verifySuccessfulUpload()):
            self.build.updateStatus(BuildStatus.FAILEDTOUPLOAD)
        if self.build.status != BuildStatus.FULLYBUILT:
            if recipe_deleted:
                # For a deleted recipe, no need to notify that uploading has
                # failed - we just log a warning.
                self.processor.log.warn(
                    "Recipe for build %s was deleted. Ignoring." %
                    self.upload)
            else:
                self.build.storeUploadLog(logger.getLogBuffer())
                self.build.notify(extra_info="Uploading build %s failed." %
                                  self.upload)
        else:
            self.build.notify()
        self.processor.ztm.commit()
        self.moveProcessedUpload(result, logger)


def _getDistributionAndSuite(parts, exc_type):
    """Return an `IDistribution` and a valid suite name for the given path.


    Helper function used within `parse_upload_path` for extracting and
    verifying the part of the upload path targeting a existing distribution
    and optionally one of its suite.

    It will fail with `AssertionError` if the given `parts` is not a list
    with one or two elements.

    :param parts: a list of path parts to be processed.
    :param exc_type: a specific Exception type that should be raised on
        errors.

    :return: a tuple containing a `IDistribution` and a suite name if it's
        appropriate. The suite name will be None if it wasn't present in the
        given path parts.

    :raises: the given `exc_type` if the corresponding distribution or suite
        could not be found.
    """
    # This assertion should never happens when this method is called from
    # 'parse_upload_path'.
    assert len(parts) <= 2, (
        "'%s' does not correspond to a [distribution[/suite]]."
        % '/'.join(parts))

    # Uploads with undefined distribution defaults to 'ubuntu'.
    if len(parts) == 0 or parts[0] is '':
        ubuntu = getUtility(IDistributionSet).getByName('ubuntu')
        return (ubuntu, None)

    distribution_name = parts[0]
    distribution = getUtility(IDistributionSet).getByName(distribution_name)
    if distribution is None:
        raise exc_type(
            "Could not find distribution '%s'." % distribution_name)

    if len(parts) == 1:
        return (distribution, None)

    suite_name = parts[1]
    try:
        distribution.getDistroSeriesAndPocket(suite_name, follow_aliases=True)
    except NotFoundError:
        raise exc_type("Could not find suite '%s'." % suite_name)

    return (distribution, suite_name)


def parse_upload_path(relative_path):
    """Locate the distribution and archive for the upload.

    We do this by analysing the path to which the user has uploaded,
    ie. the relative path within the upload folder to the changes file.

    The valid paths are:
    '' - default distro, ubuntu
    '<distroname>' - given distribution
    '~<personname>[/ppa_name]/<distroname>[/distroseriesname]' - given ppa,
    distribution and optionally a distroseries.  If ppa_name is not
    specified it will default to the one referenced by IPerson.archive.

    I raises UploadPathError if something was wrong when parsing it.

    On success it returns a tuple of IDistribution, suite-name,
    IArchive for the given path, where the second field can be None.
    """
    parts = relative_path.split(os.path.sep)

    first_path = parts[0]

    if (not first_path.startswith('~') and not first_path.isdigit()
        and len(parts) <= 2):
        # Distribution upload (<distro>[/distroseries]). Always targeted to
        # the corresponding primary archive.
        distribution, suite_name = _getDistributionAndSuite(
            parts, UploadPathError)
        archive = distribution.main_archive

    elif (first_path.startswith('~') and
          len(parts) >= 2 and
          len(parts) <= 4):
        # PPA upload (~<person>[/ppa_name]/<distro>[/distroseries]).

        # Skip over '~' from the person name.
        person_name = first_path[1:]
        person = getUtility(IPersonSet).getByName(person_name)
        if person is None:
            raise PPAUploadPathError(
                "Could not find person or team named '%s'." % person_name)

        ppa_name = parts[1]

        # Compatibilty feature for allowing unamed-PPA upload paths
        # for a certain period of time.
        if ppa_name == 'ubuntu':
            ppa_name = 'ppa'
            distribution_and_suite = parts[1:]
        else:
            distribution_and_suite = parts[2:]

        try:
            archive = person.getPPAByName(ppa_name)
        except NoSuchPPA:
            raise PPAUploadPathError(
                "Could not find a PPA named '%s' for '%s'."
                % (ppa_name, person_name))

        distribution, suite_name = _getDistributionAndSuite(
            distribution_and_suite, PPAUploadPathError)

    elif first_path.isdigit():
        # This must be a binary upload from a build slave.
        try:
            archive = getUtility(IArchiveSet).get(int(first_path))
        except SQLObjectNotFound:
            raise UploadPathError(
                "Could not find archive with id=%s." % first_path)
        distribution, suite_name = _getDistributionAndSuite(
            parts[1:], UploadPathError)
    else:
        # Upload path does not match anything we support.
        raise UploadPathError("Path format mismatch.")

    if not archive.enabled:
        raise PPAUploadPathError("%s is disabled." % archive.displayname)

    if archive.distribution != distribution:
        raise PPAUploadPathError(
            "%s only supports uploads to '%s' distribution."
            % (archive.displayname, archive.distribution.name))

    return (distribution, suite_name, archive)
