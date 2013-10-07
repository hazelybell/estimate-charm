# Copyright 2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    "IPackageTranslationsUploadJob",
    "IPackageTranslationsUploadJobSource",
    ]

from lp.services.job.interfaces.job import (
    IJobSource,
    IRunnableJob,
    )


class IPackageTranslationsUploadJobSource(IJobSource):
    """An interface for acquiring IPackageTranslationsUploadJob."""

    def create(sourcepackagerelease, libraryfilealias, requester):
        """Create new translations upload job for a source package release."""


class IPackageTranslationsUploadJob(IRunnableJob):
    """A `Job` that uploads and attaches files to a `ISourcePackageRelease`."""

    def getErrorRecipients():
        """Return a list of email-ids to notify about upload errors."""
