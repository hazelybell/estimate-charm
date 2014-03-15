# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""`TranslationTemplatesBuild` class."""

__metaclass__ = type
__all__ = [
    'TranslationTemplatesBuild',
    ]

import pytz
from storm.locals import (
    Bool,
    DateTime,
    Int,
    Reference,
    Storm,
    )
from zope.component import getUtility
from zope.interface import (
    classProvides,
    implements,
    )

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.buildmaster.enums import (
    BuildFarmJobType,
    BuildStatus,
    )
from lp.buildmaster.interfaces.buildfarmjob import IBuildFarmJobSource
from lp.buildmaster.model.buildfarmjob import BuildFarmJobMixin
from lp.code.model.branch import Branch
from lp.code.model.branchcollection import GenericBranchCollection
from lp.code.model.branchjob import (
    BranchJob,
    BranchJobType,
    )
from lp.registry.model.product import Product
from lp.services.database.bulk import load_related
from lp.services.database.decoratedresultset import DecoratedResultSet
from lp.services.database.enumcol import DBEnum
from lp.services.database.interfaces import IStore
from lp.translations.interfaces.translationtemplatesbuild import (
    ITranslationTemplatesBuild,
    ITranslationTemplatesBuildSource,
    )
from lp.translations.model.translationtemplatesbuildjob import (
    TranslationTemplatesBuildJob,
    )


class TranslationTemplatesBuild(BuildFarmJobMixin, Storm):
    """A `BuildFarmJob` extension for translation templates builds."""

    implements(ITranslationTemplatesBuild)
    classProvides(ITranslationTemplatesBuildSource)

    __storm_table__ = 'TranslationTemplatesBuild'

    job_type = BuildFarmJobType.TRANSLATIONTEMPLATESBUILD

    id = Int(name='id', primary=True)
    build_farm_job_id = Int(name='build_farm_job', allow_none=False)
    build_farm_job = Reference(build_farm_job_id, 'BuildFarmJob.id')
    branch_id = Int(name='branch', allow_none=False)
    branch = Reference(branch_id, 'Branch.id')

    processor_id = Int(name='processor')
    processor = Reference(processor_id, 'Processor.id')
    virtualized = Bool(name='virtualized')

    date_created = DateTime(
        name='date_created', tzinfo=pytz.UTC, allow_none=False)
    date_started = DateTime(name='date_started', tzinfo=pytz.UTC)
    date_finished = DateTime(name='date_finished', tzinfo=pytz.UTC)
    date_first_dispatched = DateTime(
        name='date_first_dispatched', tzinfo=pytz.UTC)

    builder_id = Int(name='builder')
    builder = Reference(builder_id, 'Builder.id')

    status = DBEnum(name='status', enum=BuildStatus, allow_none=False)

    log_id = Int(name='log')
    log = Reference(log_id, 'LibraryFileAlias.id')

    failure_count = Int(name='failure_count', allow_none=False)

    @property
    def title(self):
        return u'Translation template build for %s' % (
            self.branch.displayname)

    def __init__(self, build_farm_job, branch, processor):
        super(TranslationTemplatesBuild, self).__init__()
        self.build_farm_job = build_farm_job
        self.branch = branch
        self.status = BuildStatus.NEEDSBUILD
        self.processor = processor

    def makeJob(self):
        """See `IBuildFarmJobOld`."""
        store = IStore(BranchJob)

        # Pass public HTTP URL for the branch.
        metadata = {
            'branch_url': self.branch.composePublicURL(),
            'build_id': self.id,
            }
        branch_job = BranchJob(
            self.branch, BranchJobType.TRANSLATION_TEMPLATES_BUILD, metadata)
        store.add(branch_job)
        return TranslationTemplatesBuildJob(branch_job)

    @classmethod
    def _getStore(cls, store=None):
        """Return `store` if given, or the default."""
        if store is None:
            return IStore(cls)
        else:
            return store

    @classmethod
    def _getBuildArch(cls):
        """Returns an `IProcessor` to queue a translation build for."""
        # XXX Danilo Segan bug=580429: we hard-code processor to the Ubuntu
        # default processor architecture.  This stops the buildfarm from
        # accidentally dispatching the jobs to private builders.
        ubuntu = getUtility(ILaunchpadCelebrities).ubuntu
        return ubuntu.currentseries.nominatedarchindep.processor

    @classmethod
    def create(cls, branch):
        """See `ITranslationTemplatesBuildSource`."""
        processor = cls._getBuildArch()
        build_farm_job = getUtility(IBuildFarmJobSource).new(
            BuildFarmJobType.TRANSLATIONTEMPLATESBUILD)
        build = TranslationTemplatesBuild(build_farm_job, branch, processor)
        store = cls._getStore()
        store.add(build)
        store.flush()
        return build

    @classmethod
    def getByID(cls, build_id, store=None):
        """See `ITranslationTemplatesBuildSource`."""
        store = cls._getStore(store)
        match = store.find(
            TranslationTemplatesBuild,
            TranslationTemplatesBuild.id == build_id)
        return match.one()

    @classmethod
    def getByBuildFarmJob(cls, buildfarmjob, store=None):
        """See `ITranslationTemplatesBuildSource`."""
        store = cls._getStore(store)
        match = store.find(
            TranslationTemplatesBuild, build_farm_job_id=buildfarmjob.id)
        return match.one()

    @classmethod
    def getByBuildFarmJobs(cls, buildfarmjobs, store=None):
        """See `ITranslationTemplatesBuildSource`."""
        store = cls._getStore(store)
        rows = store.find(
            TranslationTemplatesBuild,
            TranslationTemplatesBuild.build_farm_job_id.is_in(
                bfj.id for bfj in buildfarmjobs))
        return DecoratedResultSet(rows, pre_iter_hook=cls.preloadBuildsData)

    @classmethod
    def preloadBuildsData(cls, builds):
        # Circular imports.
        from lp.services.librarian.model import LibraryFileAlias
        # Load the related branches, products.
        branches = load_related(
            Branch, builds, ['branch_id'])
        load_related(
            Product, branches, ['productID'])
        # Preload branches cached associated product series and
        # suite source packages for all the related branches.
        GenericBranchCollection.preloadDataForBranches(branches)
        load_related(LibraryFileAlias, builds, ['log_id'])

    @classmethod
    def findByBranch(cls, branch, store=None):
        """See `ITranslationTemplatesBuildSource`."""
        store = cls._getStore(store)
        return store.find(
            TranslationTemplatesBuild,
            TranslationTemplatesBuild.branch == branch)

    @property
    def log_url(self):
        """See `IBuildFarmJob`."""
        if self.log is None:
            return None
        return self.log.http_url
