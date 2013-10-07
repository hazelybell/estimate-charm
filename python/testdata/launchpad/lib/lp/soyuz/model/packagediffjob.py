# Copyright 2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'PackageDiffJob',
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
from lp.soyuz.interfaces.packagediff import IPackageDiffSet
from lp.soyuz.interfaces.packagediffjob import (
    IPackageDiffJob,
    IPackageDiffJobSource,
    )


class PackageDiffJobDerived(BaseRunnableJob):

    __metaclass__ = EnumeratedSubclass

    delegates(IPackageDiffJob)
    classProvides(IPackageDiffJobSource)
    config = config.IPackageDiffJobSource

    def __init__(self, job):
        assert job.base_job_type == JobType.GENERATE_PACKAGE_DIFF
        self.job = job
        self.context = self

    @classmethod
    def create(cls, packagediff):
        job = Job(
            base_job_type=JobType.GENERATE_PACKAGE_DIFF,
            requester=packagediff.requester,
            base_json_data=simplejson.dumps({'packagediff': packagediff.id}))
        derived = cls(job)
        derived.celeryRunOnCommit()
        return derived

    @classmethod
    def iterReady(cls):
        jobs = IStore(Job).find(
            Job, Job.id.is_in(Job.ready_jobs),
            Job.base_job_type == JobType.GENERATE_PACKAGE_DIFF)
        return (cls(job) for job in jobs)


class PackageDiffJob(PackageDiffJobDerived):

    implements(IPackageDiffJob)
    classProvides(IPackageDiffJobSource)

    @property
    def packagediff_id(self):
        return simplejson.loads(self.base_json_data)['packagediff']

    @property
    def packagediff(self):
        return getUtility(IPackageDiffSet).get(self.packagediff_id)

    def run(self):
        packagediff = self.packagediff
        if packagediff is not None:
            packagediff.performDiff()
