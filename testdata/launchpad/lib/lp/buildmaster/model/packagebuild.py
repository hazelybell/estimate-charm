# Copyright 2010-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'PackageBuildMixin',
    ]


from cStringIO import StringIO

from storm.locals import Store
from zope.component import getUtility

from lp.buildmaster.enums import BuildStatus
from lp.buildmaster.model.buildfarmjob import BuildFarmJobMixin
from lp.buildmaster.model.buildqueue import BuildQueue
from lp.services.helpers import filenameToContentType
from lp.services.librarian.browser import ProxiedLibraryFileAlias
from lp.services.librarian.interfaces import ILibraryFileAliasSet
from lp.soyuz.adapters.archivedependencies import (
    default_component_dependency_name,
    )
from lp.soyuz.interfaces.component import IComponentSet


class PackageBuildMixin(BuildFarmJobMixin):

    @property
    def current_component(self):
        """See `IPackageBuild`."""
        return getUtility(IComponentSet)[default_component_dependency_name]

    @property
    def upload_log_url(self):
        """See `IPackageBuild`."""
        if self.upload_log is None:
            return None
        return ProxiedLibraryFileAlias(self.upload_log, self).http_url

    @property
    def log_url(self):
        """See `IBuildFarmJob`."""
        if self.log is None:
            return None
        return ProxiedLibraryFileAlias(self.log, self).http_url

    @property
    def is_private(self):
        """See `IBuildFarmJob`"""
        return self.archive.private

    def estimateDuration(self):
        """See `IPackageBuild`."""
        raise NotImplementedError

    def updateStatus(self, status, builder=None, slave_status=None,
                     date_started=None, date_finished=None):
        super(PackageBuildMixin, self).updateStatus(
            status, builder=builder, slave_status=slave_status,
            date_started=date_started, date_finished=date_finished)

        if (status == BuildStatus.MANUALDEPWAIT and slave_status is not None
            and slave_status.get('dependencies') is not None):
            self.dependencies = unicode(slave_status.get('dependencies'))
        else:
            self.dependencies = None

    def verifySuccessfulUpload(self):
        """See `IPackageBuild`."""
        raise NotImplementedError

    def createUploadLog(self, content, filename=None):
        """Creates a file on the librarian for the upload log.

        :return: ILibraryFileAlias for the upload log file.
        """
        # The given content is stored in the librarian, restricted as
        # necessary according to the targeted archive's privacy.  The content
        # object's 'upload_log' attribute will point to the
        # `LibrarianFileAlias`.

        assert self.upload_log is None, (
            "Upload log information already exists and cannot be overridden.")

        if filename is None:
            filename = 'upload_%s_log.txt' % self.id
        contentType = filenameToContentType(filename)
        if isinstance(content, unicode):
            content = content.encode('utf-8')
        file_size = len(content)
        file_content = StringIO(content)
        restricted = self.is_private

        return getUtility(ILibraryFileAliasSet).create(
            filename, file_size, file_content, contentType=contentType,
            restricted=restricted)

    def storeUploadLog(self, content):
        """See `IPackageBuild`."""
        filename = "upload_%s_log.txt" % self.id
        library_file = self.createUploadLog(content, filename=filename)
        self.upload_log = library_file

    def notify(self, extra_info=None):
        """See `IPackageBuild`."""
        raise NotImplementedError

    def getUploader(self, changes):
        """See `IPackageBuild`."""
        raise NotImplementedError

    def queueBuild(self, suspended=False):
        """See `IPackageBuild`."""
        specific_job = self.makeJob()

        # This build queue job is to be created in a suspended state.
        if suspended:
            specific_job.job.suspend()

        duration_estimate = self.estimateDuration()
        job = specific_job.job
        processor = specific_job.processor
        queue_entry = BuildQueue(
            estimated_duration=duration_estimate,
            job_type=self.job_type,
            job=job, processor=processor,
            virtualized=specific_job.virtualized)
        Store.of(self).add(queue_entry)
        return queue_entry
