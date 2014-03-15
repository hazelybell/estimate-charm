# Copyright 2010-2013 Canonical Ltd. This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'HARDCODED_TRANSLATIONTEMPLATESBUILD_SCORE',
    'TranslationTemplatesBuildJob',
    ]

from datetime import timedelta
import logging

from storm.store import Store
from zope.component import getUtility
from zope.interface import (
    classProvides,
    implements,
    )
from zope.security.proxy import removeSecurityProxy

from lp.buildmaster.enums import BuildFarmJobType
from lp.buildmaster.interfaces.buildfarmbranchjob import IBuildFarmBranchJob
from lp.buildmaster.model.buildfarmjob import BuildFarmJobOld
from lp.buildmaster.model.buildqueue import BuildQueue
from lp.code.interfaces.branchjob import IRosettaUploadJobSource
from lp.code.model.branchjob import (
    BranchJob,
    BranchJobDerived,
    BranchJobType,
    )
from lp.services.config import config
from lp.services.database.bulk import load_related
from lp.services.database.interfaces import (
    IMasterStore,
    IStore,
    )
from lp.translations.interfaces.translationtemplatesbuild import (
    ITranslationTemplatesBuildSource,
    )
from lp.translations.interfaces.translationtemplatesbuildjob import (
    ITranslationTemplatesBuildJobSource,
    )
from lp.translations.pottery.detect_intltool import is_intltool_structure


HARDCODED_TRANSLATIONTEMPLATESBUILD_SCORE = 2510


class TranslationTemplatesBuildJob(BuildFarmJobOld, BranchJobDerived):
    """An `IBuildFarmJob` implementation that generates templates.

    Implementation-wise, this is actually a `BranchJob`.
    """
    implements(IBuildFarmBranchJob)
    class_job_type = BranchJobType.TRANSLATION_TEMPLATES_BUILD

    classProvides(ITranslationTemplatesBuildJobSource)

    duration_estimate = timedelta(seconds=10)

    def score(self):
        """See `IBuildFarmJob`."""
        # Hard-code score for now.  Most PPA jobs start out at 2505;
        # TranslationTemplateBuildJobs are fast so we want them at a
        # higher priority.
        return HARDCODED_TRANSLATIONTEMPLATESBUILD_SCORE

    def cleanUp(self):
        """See `IBuildFarmJob`."""
        # This class is not itself database-backed.  But it delegates to
        # one that is.  We can't call its SQLObject destroySelf method
        # though, because then the BuildQueue and the BranchJob would
        # both try to delete the attached Job.
        Store.of(self.context).remove(self.context)

    @property
    def build(self):
        """Return a TranslationTemplateBuild for this build job."""
        build_id = self.context.metadata.get('build_id', None)
        if build_id is None:
            return None
        else:
            return getUtility(ITranslationTemplatesBuildSource).getByID(
                int(build_id))

    @classmethod
    def _hasPotteryCompatibleSetup(cls, branch):
        """Does `branch` look as if pottery can generate templates for it?

        :param branch: A `Branch` object.
        """
        bzr_branch = removeSecurityProxy(branch).getBzrBranch()
        return is_intltool_structure(bzr_branch.basis_tree())

    @classmethod
    def generatesTemplates(cls, branch):
        """See `ITranslationTemplatesBuildJobSource`."""
        logger = logging.getLogger('translation-templates-build')
        if branch.private:
            # We don't support generating template from private branches
            # at the moment.
            logger.debug("Branch %s is private.", branch.unique_name)
            return False

        utility = getUtility(IRosettaUploadJobSource)
        if not utility.providesTranslationFiles(branch):
            # Nobody asked for templates generated from this branch.
            logger.debug(
                    "No templates requested for branch %s.",
                    branch.unique_name)
            return False

        if not cls._hasPotteryCompatibleSetup(branch):
            # Nothing we could do with this branch if we wanted to.
            logger.debug(
                "Branch %s is not pottery-compatible.", branch.unique_name)
            return False

        # Yay!  We made it.
        return True

    @classmethod
    def create(cls, branch, testing=False):
        """See `ITranslationTemplatesBuildJobSource`."""
        logger = logging.getLogger('translation-templates-build')

        build = getUtility(ITranslationTemplatesBuildSource).create(
            branch)
        logger.debug("Made TranslationTemplatesBuild %s.", build.id)

        specific_job = build.makeJob()
        if testing:
            removeSecurityProxy(specific_job)._constructed_build = build
        logger.debug("Made %s.", specific_job)

        duration_estimate = cls.duration_estimate

        build_queue_entry = BuildQueue(
            estimated_duration=duration_estimate,
            job_type=BuildFarmJobType.TRANSLATIONTEMPLATESBUILD,
            job=specific_job.job, processor=build.processor)
        IMasterStore(BuildQueue).add(build_queue_entry)

        logger.debug("Made BuildQueue %s.", build_queue_entry.id)

        return specific_job

    @classmethod
    def scheduleTranslationTemplatesBuild(cls, branch):
        """See `ITranslationTemplatesBuildJobSource`."""
        logger = logging.getLogger('translation-templates-build')
        if not config.rosetta.generate_templates:
            # This feature is disabled by default.
            logging.debug("Templates generation is disabled.")
            return

        try:
            if cls.generatesTemplates(branch):
                # This branch is used for generating templates.
                logger.info(
                    "Requesting templates build for branch %s.",
                    branch.unique_name)
                cls.create(branch)
        except Exception as e:
            logger.error(e)
            raise

    @classmethod
    def getByJob(cls, job):
        """See `IBuildFarmJob`.

        Overridden here to search via a BranchJob, rather than a Job.
        """
        store = IStore(BranchJob)
        branch_job = store.find(BranchJob, BranchJob.job == job).one()
        if branch_job is None:
            return None
        else:
            return cls(branch_job)

    @classmethod
    def getByJobs(cls, jobs):
        """See `IBuildFarmJob`.

        Overridden here to search via a BranchJob, rather than a Job.
        """
        store = IStore(BranchJob)
        job_ids = [job.id for job in jobs]
        branch_jobs = store.find(
            BranchJob, BranchJob.jobID.is_in(job_ids))
        return [cls(branch_job) for branch_job in branch_jobs]

    @classmethod
    def preloadJobsData(cls, jobs):
        # Circular imports.
        from lp.code.model.branch import Branch
        from lp.registry.model.product import Product
        from lp.code.model.branchcollection import GenericBranchCollection
        from lp.services.job.model.job import Job
        contexts = [job.context for job in jobs]
        load_related(Job, contexts, ['jobID'])
        branches = load_related(Branch, contexts, ['branchID'])
        GenericBranchCollection.preloadDataForBranches(branches)
        load_related(Product, branches, ['productID'])

    @classmethod
    def getByBranch(cls, branch):
        """See `ITranslationTemplatesBuildJobSource`."""
        store = IStore(BranchJob)
        branch_job = store.find(BranchJob, BranchJob.branch == branch).one()
        if branch_job is None:
            return None
        else:
            return cls(branch_job)
