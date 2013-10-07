# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""
Processes removals of packages that are scheduled for deletion.
"""
__metaclass__ = type

import datetime
import logging
import os

import pytz

from lp.archivepublisher.config import getPubConfig
from lp.archivepublisher.diskpool import DiskPool
from lp.services.database.constants import UTC_NOW
from lp.services.database.sqlbase import sqlvalues
from lp.soyuz.enums import ArchivePurpose
from lp.soyuz.interfaces.publishing import (
    IBinaryPackagePublishingHistory,
    inactive_publishing_status,
    ISourcePackagePublishingHistory,
    MissingSymlinkInPool,
    NotInPool,
    )
from lp.soyuz.model.publishing import (
    BinaryPackagePublishingHistory,
    SourcePackagePublishingHistory,
    )


def getDeathRow(archive, log, pool_root_override):
    """Return a Deathrow object for the archive supplied.

    :param archive: Use the publisher config for this archive to derive the
                    DeathRow object.
    :param log: Use this logger for script debug logging.
    :param pool_root_override: Use this pool root for the archive instead of
         the one provided by the publishing-configuration, it will be only
         used for PRIMARY archives.
    """
    log.debug("Grab publisher config.")
    pubconf = getPubConfig(archive)

    if (pool_root_override is not None and
        archive.purpose == ArchivePurpose.PRIMARY):
        pool_root = pool_root_override
    else:
        pool_root = pubconf.poolroot

    log.debug("Preparing on-disk pool representation.")

    diskpool_log = logging.getLogger("DiskPool")
    # Set the diskpool's log level to INFO to suppress debug output
    diskpool_log.setLevel(20)

    dp = DiskPool(pool_root, pubconf.temproot, diskpool_log)

    log.debug("Preparing death row.")
    return DeathRow(archive, dp, log)


class DeathRow:
    """A Distribution Archive Removal Processor.

    DeathRow will remove archive files from disk if they are marked for
    removal in the publisher tables, and if they are no longer referenced
    by other packages.
    """

    def __init__(self, archive, diskpool, logger):
        self.archive = archive
        self.diskpool = diskpool
        self._removeFile = diskpool.removeFile
        self.logger = logger

    def reap(self, dry_run=False):
        """Reap packages that should be removed from the distribution.

        Looks through all packages that are in condemned states and
        have scheduleddeletiondate is in the past, try to remove their
        files from the archive pool (which may be impossible if they are
        used by other packages which are published), and mark them as
        removed."""
        if dry_run:
            # Don't actually remove the files if we are dry running
            def _mockRemoveFile(cn, sn, fn):
                self.logger.debug("(Not really!) removing %s %s/%s" %
                                  (cn, sn, fn))
                fullpath = self.diskpool.pathFor(cn, sn, fn)
                if not os.path.exists(fullpath):
                    raise NotInPool
                return os.lstat(fullpath).st_size
            self._removeFile = _mockRemoveFile

        source_files, binary_files = self._collectCondemned()
        records = self._tryRemovingFromDisk(source_files, binary_files)
        self._markPublicationRemoved(records)

    def _collectCondemned(self):
        """Return the condemned source and binary publications as a tuple.

        Return all the `SourcePackagePublishingHistory` and
        `BinaryPackagePublishingHistory` records that are eligible for
        removal ('condemned') where the source/binary package that they
        refer to is not published somewhere else.

        Both sources and binaries are lists.
        """
        sources = SourcePackagePublishingHistory.select("""
            SourcePackagePublishingHistory.archive = %s AND
            SourcePackagePublishingHistory.scheduleddeletiondate < %s AND
            SourcePackagePublishingHistory.dateremoved IS NULL AND
            NOT EXISTS (
              SELECT 1 FROM sourcepackagepublishinghistory as spph
              WHERE
                  SourcePackagePublishingHistory.sourcepackagerelease =
                      spph.sourcepackagerelease AND
                  spph.archive = %s AND
                  spph.status NOT IN %s)
        """ % sqlvalues(self.archive, UTC_NOW, self.archive,
                        inactive_publishing_status), orderBy="id")
        self.logger.debug("%d Sources" % sources.count())

        binaries = BinaryPackagePublishingHistory.select("""
            BinaryPackagePublishingHistory.archive = %s AND
            BinaryPackagePublishingHistory.scheduleddeletiondate < %s AND
            BinaryPackagePublishingHistory.dateremoved IS NULL AND
            NOT EXISTS (
              SELECT 1 FROM binarypackagepublishinghistory as bpph
              WHERE
                  BinaryPackagePublishingHistory.binarypackagerelease =
                      bpph.binarypackagerelease AND
                  bpph.archive = %s AND
                  bpph.status NOT IN %s)
        """ % sqlvalues(self.archive, UTC_NOW, self.archive,
                        inactive_publishing_status), orderBy="id")
        self.logger.debug("%d Binaries" % binaries.count())

        return (sources, binaries)

    def canRemove(self, publication_class, filename, file_md5):
        """Check if given (filename, MD5) can be removed from the pool.

        Check the archive reference-counter implemented in:
        `SourcePackagePublishingHistory` or
        `BinaryPackagePublishingHistory`.

        Only allow removal of unnecessary files.
        """
        clauses = []
        clauseTables = []

        if ISourcePackagePublishingHistory.implementedBy(
            publication_class):
            clauses.append("""
                SourcePackagePublishingHistory.archive = %s AND
                SourcePackagePublishingHistory.dateremoved is NULL AND
                SourcePackagePublishingHistory.sourcepackagerelease =
                    SourcePackageReleaseFile.sourcepackagerelease AND
                SourcePackageReleaseFile.libraryfile = LibraryFileAlias.id
            """ % sqlvalues(self.archive))
            clauseTables.append('SourcePackageReleaseFile')
        elif IBinaryPackagePublishingHistory.implementedBy(
            publication_class):
            clauses.append("""
                BinaryPackagePublishingHistory.archive = %s AND
                BinaryPackagePublishingHistory.dateremoved is NULL AND
                BinaryPackagePublishingHistory.binarypackagerelease =
                    BinaryPackageFile.binarypackagerelease AND
                BinaryPackageFile.libraryfile = LibraryFileAlias.id
            """ % sqlvalues(self.archive))
            clauseTables.append('BinaryPackageFile')
        else:
            raise AssertionError("%r is not supported." % publication_class)

        clauses.append("""
           LibraryFileAlias.content = LibraryFileContent.id AND
           LibraryFileAlias.filename = %s AND
           LibraryFileContent.md5 = %s
        """ % sqlvalues(filename, file_md5))
        clauseTables.extend(
            ['LibraryFileAlias', 'LibraryFileContent'])

        all_publications = publication_class.select(
            " AND ".join(clauses), clauseTables=clauseTables)

        right_now = datetime.datetime.now(pytz.timezone('UTC'))
        for pub in all_publications:
            # Deny removal if any reference is still active.
            if pub.status not in inactive_publishing_status:
                return False
            # Deny removal if any reference wasn't dominated yet.
            if pub.scheduleddeletiondate is None:
                return False
            # Deny removal if any reference is still in 'quarantine'.
            if pub.scheduleddeletiondate > right_now:
                return False

        return True

    def _tryRemovingFromDisk(self, condemned_source_files,
                             condemned_binary_files):
        """Take the list of publishing records provided and unpublish them.

        You should only pass in entries you want to be unpublished because
        this will result in the files being removed if they're not otherwise
        in use.
        """
        bytes = 0
        condemned_files = set()
        condemned_records = set()
        considered_files = set()
        details = {}

        def checkPubRecord(pub_record, publication_class):
            """Check if the publishing record can be removed.

            It can only be removed if all files in its context are not
            referred to any other 'published' publishing records.

            See `canRemove` for more information.
            """
            for pub_file in pub_record.files:
                filename = pub_file.libraryfilealiasfilename
                file_md5 = pub_file.libraryfilealias.content.md5

                self.logger.debug("Checking %s (%s)" % (filename, file_md5))

                # Calculating the file path in pool.
                pub_file_details = (
                    pub_file.libraryfilealiasfilename,
                    pub_file.sourcepackagename,
                    pub_file.componentname,
                    )
                file_path = self.diskpool.pathFor(*pub_file_details)

                # Check if the LibraryFileAlias in question was already
                # verified. If the verification was already made and the
                # file is condemned queue the publishing record for removal
                # otherwise just continue the iteration.
                if (filename, file_md5) in considered_files:
                    self.logger.debug("Already verified.")
                    if file_path in condemned_files:
                        condemned_records.add(pub_file.publishing_record)
                    continue
                considered_files.add((filename, file_md5))

                # Check if the removal is allowed, if not continue.
                if not self.canRemove(publication_class, filename, file_md5):
                    self.logger.debug("Cannot remove.")
                    continue

                # Update local containers, in preparation to file removal.
                details.setdefault(file_path, pub_file_details)
                condemned_files.add(file_path)
                condemned_records.add(pub_file.publishing_record)

        # Check source and binary publishing records.
        for pub_record in condemned_source_files:
            checkPubRecord(pub_record, SourcePackagePublishingHistory)
        for pub_record in condemned_binary_files:
            checkPubRecord(pub_record, BinaryPackagePublishingHistory)

        self.logger.info(
            "Removing %s files marked for reaping" % len(condemned_files))

        for condemned_file in sorted(condemned_files, reverse=True):
            file_name, source_name, component_name = details[condemned_file]
            try:
                bytes += self._removeFile(
                    component_name, source_name, file_name)
            except NotInPool as info:
                # It's safe for us to let this slide because it means that
                # the file is already gone.
                self.logger.debug(str(info))
            except MissingSymlinkInPool as info:
                # This one is a little more worrying, because an expected
                # symlink has vanished from the pool/ (could be a code
                # mistake) but there is nothing we can do about it at this
                # point.
                self.logger.warn(str(info))

        self.logger.info("Total bytes freed: %s" % bytes)

        return condemned_records

    def _markPublicationRemoved(self, condemned_records):
        # Now that the os.remove() calls have been made, simply let every
        # now out-of-date record be marked as removed.
        self.logger.debug("Marking %s condemned packages as removed." %
                          len(condemned_records))
        for record in condemned_records:
            record.dateremoved = UTC_NOW
