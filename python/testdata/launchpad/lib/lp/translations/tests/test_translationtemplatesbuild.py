# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""`TranslationTemplatesBuild` tests."""

__metaclass__ = type

from storm.store import Store
from zope.component import getUtility
from zope.interface.verify import verifyObject

from lp.buildmaster.interfaces.buildfarmjob import IBuildFarmJob
from lp.testing import TestCaseWithFactory
from lp.testing.dbuser import switch_dbuser
from lp.testing.layers import LaunchpadZopelessLayer
from lp.translations.interfaces.translationtemplatesbuild import (
    ITranslationTemplatesBuild,
    ITranslationTemplatesBuildSource,
    )
from lp.translations.model.translationtemplatesbuild import (
    TranslationTemplatesBuild,
    )


class TestTranslationTemplatesBuild(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def test_baseline(self):
        branch = self.factory.makeBranch()
        build = getUtility(ITranslationTemplatesBuildSource).create(branch)

        self.assertTrue(verifyObject(ITranslationTemplatesBuild, build))
        self.assertTrue(verifyObject(IBuildFarmJob, build))
        self.assertEqual(branch, build.branch)

    def test_permissions(self):
        # The branch scanner creates TranslationTemplatesBuilds.  It has
        # the database privileges it needs for that.
        branch = self.factory.makeBranch()
        switch_dbuser("branchscanner")
        build = getUtility(ITranslationTemplatesBuildSource).create(branch)

        # Writing the new objects to the database violates no access
        # restrictions.
        Store.of(build).flush()

    def test_created_by_buildjobsource(self):
        # ITranslationTemplatesBuildJobSource.create also creates a
        # TranslationTemplatesBuild.  This utility will become obsolete
        # later.
        source = getUtility(ITranslationTemplatesBuildSource)
        branch = self.factory.makeBranch()
        source.create(branch)

        builds = list(source.findByBranch(branch))
        self.assertEqual(1, len(builds))
        self.assertIsInstance(builds[0], TranslationTemplatesBuild)

    def test_findByBranch(self):
        source = getUtility(ITranslationTemplatesBuildSource)
        branch = self.factory.makeBranch()

        self.assertContentEqual([], source.findByBranch(branch))

        build = source.create(branch)

        by_branch = list(source.findByBranch(branch))
        self.assertEqual([build], by_branch)

    def test_get(self):
        source = getUtility(ITranslationTemplatesBuildSource)
        branch = self.factory.makeBranch()
        build = source.create(branch)

        self.assertEqual(build, source.getByID(build.id))

    def test_get_returns_none_if_not_found(self):
        source = getUtility(ITranslationTemplatesBuildSource)
        branch = self.factory.makeBranch()
        build = source.create(branch)

        self.assertIs(None, source.getByID(build.id + 999))

    def test_getByBuildFarmJob(self):
        source = getUtility(ITranslationTemplatesBuildSource)
        branch = self.factory.makeBranch()
        build = source.create(branch)

        self.assertEqual(build, source.getByBuildFarmJob(build.build_farm_job))

    def test_getByBuildFarmJobs(self):
        source = getUtility(ITranslationTemplatesBuildSource)
        build_farm_jobs = []
        builds = []
        for i in xrange(10):
            branch = self.factory.makeBranch()
            build = source.create(branch)
            builds.append(build)
            build_farm_jobs.append(build.build_farm_job)

        self.assertContentEqual(
            builds,
            source.getByBuildFarmJobs(build_farm_jobs))

    def test_getByBuildFarmJob_returns_none_if_not_found(self):
        source = getUtility(ITranslationTemplatesBuildSource)
        branch = self.factory.makeBranch()
        source.create(branch)

        another_job = self.factory.makeBinaryPackageBuild().build_farm_job
        self.assertIs(
            None,
            source.getByBuildFarmJob(another_job))
