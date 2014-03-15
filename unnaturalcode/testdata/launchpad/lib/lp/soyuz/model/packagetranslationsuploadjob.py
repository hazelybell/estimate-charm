# Copyright 2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'PackageTranslationsUploadJob',
    ]

from lazr.delegates import delegates
import simplejson
from zope.component import getUtility
from zope.interface import (
    classProvides,
    implements,
    )

from lp.services.config import config
from lp.services.database.interfaces import IStore
from lp.services.job.interfaces.job import JobType
from lp.services.job.model.job import (
    EnumeratedSubclass,
    Job,
    )
from lp.services.job.runner import BaseRunnableJob
from lp.services.librarian.interfaces import ILibraryFileAliasSet
from lp.services.mail.sendmail import format_address_for_person
from lp.soyuz.interfaces.packagetranslationsuploadjob import (
    IPackageTranslationsUploadJob,
    IPackageTranslationsUploadJobSource,
    )
from lp.soyuz.model.sourcepackagerelease import SourcePackageRelease


class PackageTranslationsUploadJobDerived(BaseRunnableJob):

    __metaclass__ = EnumeratedSubclass

    delegates(IPackageTranslationsUploadJob)
    classProvides(IPackageTranslationsUploadJobSource)
    config = config.IPackageTranslationsUploadJobSource

    def __init__(self, job):
        assert job.base_job_type == JobType.UPLOAD_PACKAGE_TRANSLATIONS
        self.job = job
        self.context = self

    @classmethod
    def create(cls, sourcepackagerelease, libraryfilealias, requester):
        job = Job(
            base_job_type=JobType.UPLOAD_PACKAGE_TRANSLATIONS,
            requester=requester,
            base_json_data=simplejson.dumps(
                {'sourcepackagerelease': sourcepackagerelease.id,
                 'libraryfilealias': libraryfilealias.id}))
        derived = cls(job)
        derived.celeryRunOnCommit()
        return derived

    @classmethod
    def iterReady(cls):
        jobs = IStore(Job).find(
            Job, Job.id.is_in(Job.ready_jobs),
            Job.base_job_type == JobType.UPLOAD_PACKAGE_TRANSLATIONS)
        return (cls(job) for job in jobs)

    def getErrorRecipients(self):
        if self.requester is not None:
            return [format_address_for_person(self.requester)]
        return []


class PackageTranslationsUploadJob(PackageTranslationsUploadJobDerived):

    implements(IPackageTranslationsUploadJob)
    classProvides(IPackageTranslationsUploadJobSource)

    @property
    def sourcepackagerelease_id(self):
        return simplejson.loads(self.base_json_data)['sourcepackagerelease']

    @property
    def libraryfilealias_id(self):
        return simplejson.loads(self.base_json_data)['libraryfilealias']

    @property
    def sourcepackagerelease(self):
        return SourcePackageRelease.get(self.sourcepackagerelease_id)

    @property
    def libraryfilealias(self):
        return getUtility(ILibraryFileAliasSet)[self.libraryfilealias_id]

    def run(self):
        sourcepackagerelease = self.sourcepackagerelease
        libraryfilealias = self.libraryfilealias
        importer = sourcepackagerelease.creator
        sourcepackagerelease.attachTranslationFiles(libraryfilealias, True,
                                                    importer=importer)
