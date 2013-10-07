# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'TemporaryBlobStorage',
    'TemporaryStorageManager',
    ]


from cStringIO import StringIO
from datetime import timedelta
import uuid

from sqlobject import (
    ForeignKey,
    SQLObjectNotFound,
    StringCol,
    )
from zope.component import getUtility
from zope.interface import implements

from lp.services.config import config
from lp.services.database.constants import DEFAULT
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.sqlbase import SQLBase
from lp.services.job.interfaces.job import JobStatus
from lp.services.librarian.interfaces import ILibraryFileAliasSet
from lp.services.temporaryblobstorage.interfaces import (
    BlobTooLarge,
    ITemporaryBlobStorage,
    ITemporaryStorageManager,
    )
from lp.services.utils import utc_now


class TemporaryBlobStorage(SQLBase):
    """A temporary BLOB stored in Launchpad."""

    implements(ITemporaryBlobStorage)

    _table='TemporaryBlobStorage'

    uuid = StringCol(notNull=True, alternateID=True)
    file_alias = ForeignKey(
            dbName='file_alias', foreignKey='LibraryFileAlias', notNull=True,
            alternateID=True
            )
    date_created = UtcDateTimeCol(notNull=True, default=DEFAULT)

    @property
    def blob(self):
        self.file_alias.open()
        try:
            return self.file_alias.read()
        finally:
            self.file_alias.close()

    @property
    def _apport_job(self):
        # Imported here to avoid circular imports
        from lp.bugs.interfaces.apportjob import IProcessApportBlobJobSource
        try:
            job_for_blob = getUtility(
                IProcessApportBlobJobSource).getByBlobUUID(self.uuid)
        except SQLObjectNotFound:
            return None

        return job_for_blob

    def hasBeenProcessed(self):
        """See `ITemporaryBlobStorage`."""
        job_for_blob = self._apport_job
        if not job_for_blob:
            return False
        return (job_for_blob.job.status == JobStatus.COMPLETED)

    def getProcessedData(self):
        """See `ITemporaryBlobStorage`."""
        job_for_blob = self._apport_job
        if not job_for_blob:
            return None
        if 'processed_data' not in job_for_blob.metadata:
            return {}
        
        return job_for_blob.metadata['processed_data']

class TemporaryStorageManager:
    """A tool to create temporary BLOB's in Launchpad."""

    implements(ITemporaryStorageManager)

    def new(self, blob, expires=None):
        """See ITemporaryStorageManager."""
        if expires is None:
            # A week might be quite a long time, but it shouldn't hurt,
            # and it gives people enough time to create an account
            # before accessing the uploaded blob.
            expires = utc_now() + timedelta(weeks=1)

        # At this stage we could do some sort of throttling if we were
        # concerned about abuse of the temporary storage facility. For
        # example, we could check the number of rows in temporary storage,
        # or the total amount of space dedicated to temporary storage, and
        # return an error code if that volume was unacceptably high. But for
        # the moment we will just ensure the BLOB is not that LARGE.
        #
        # YAGNI? There are plenty of other ways to upload large chunks
        # of data to Launchpad that will hang around permanently. Size
        # limitations on uploads needs to be done in Zope3 to avoid DOS
        # attacks in general.
        max_blob_size = config.launchpad.max_blob_size
        if max_blob_size > 0 and len(blob) > max_blob_size:
            raise BlobTooLarge(len(blob))

        # create the BLOB and return the UUID

        new_uuid = str(uuid.uuid1())

        # We use a random filename, so only things that can look up the
        # secret can retrieve the original data (which is why we don't use
        # the UUID we return to the user as the filename, nor the filename
        # of the object they uploaded).
        secret = str(uuid.uuid1())

        file_alias = getUtility(ILibraryFileAliasSet).create(
                secret, len(blob), StringIO(blob),
                'application/octet-stream', expires
                )
        TemporaryBlobStorage(uuid=new_uuid, file_alias=file_alias)
        return new_uuid

    def fetch(self, uuid):
        """See ITemporaryStorageManager."""
        return TemporaryBlobStorage.selectOneBy(uuid=uuid)

    def delete(self, uuid):
        """See ITemporaryStorageManager."""
        blob = TemporaryBlobStorage.selectOneBy(uuid=uuid)
        if blob is not None:
            TemporaryBlobStorage.delete(blob.id)

    def default_temporary_blob_storage_list(self):
        """See `ITemporaryStorageManager`."""
        return []
