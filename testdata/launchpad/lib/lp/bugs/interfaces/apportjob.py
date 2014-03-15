# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
"""Interfaces for using the Jobs system for Apport BLOB processing."""

__metaclass__ = type
__all__ = [
    'ApportJobType',
    'IApportJob',
    'IApportJobSource',
    'IProcessApportBlobJob',
    'IProcessApportBlobJobSource',
    ]

from lazr.enum import (
    DBEnumeratedType,
    DBItem,
    )
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Int,
    Object,
    )

from lp import _
from lp.services.job.interfaces.job import (
    IJob,
    IJobSource,
    IRunnableJob,
    )
from lp.services.temporaryblobstorage.interfaces import ITemporaryBlobStorage


class ApportJobType(DBEnumeratedType):
    """Values that IApportJob.job_type can take."""

    PROCESS_BLOB = DBItem(0, """
        Process a BLOB and extract salient data from it.

        This type of job extracts data from a BLOB so that it can be
        used in the bug-filing process.
        """)


class IApportJob(Interface):
    """A Job related to an Apport BLOB."""

    id = Int(
        title=_('DB ID'), required=True, readonly=True,
        description=_("The tracking number for this job."))

    blob = Object(
        title=_('The BLOB this job is about'),
        schema=ITemporaryBlobStorage, required=True)

    job = Object(title=_('The common Job attributes'), schema=IJob,
        required=True)

    metadata = Attribute('A dict of data about the job.')


class IApportJobSource(IJobSource):
    """An interface for acquiring IApportJobs."""

    def create(bug):
        """Create a new IApportJob for a bug."""

    def getByBlobUUID(uuid):
        """For a given BLOB UUID, return any jobs pertaining to that BLOB."""


class IProcessApportBlobJob(IRunnableJob):
    """A Job to process an Apport BLOB."""

    def getFileBugData():
        """Return the FileBugData parsed out of the blob by this job."""


class IProcessApportBlobJobSource(IApportJobSource):
    """Interface for acquiring ProcessApportBlobJobs."""
