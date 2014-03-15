# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for merging translations."""

__metaclass__ = type


import transaction

from lp.app.enums import ServiceUsage
from lp.services.config import config
from lp.services.features.testing import FeatureFixture
from lp.services.job.interfaces.job import (
    IJobSource,
    IRunnableJob,
    )
from lp.services.job.tests import block_on_job
from lp.testing import (
    TestCaseWithFactory,
    verifyObject,
    )
from lp.testing.dbuser import dbuser
from lp.testing.layers import (
    CeleryJobLayer,
    LaunchpadZopelessLayer,
    )
from lp.translations.interfaces.pofilestatsjob import IPOFileStatsJobSource
from lp.translations.interfaces.side import TranslationSide
from lp.translations.model import pofilestatsjob
from lp.translations.model.pofilestatsjob import POFileStatsJob


class TestPOFileStatsJob(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def test_job_interface(self):
        # Instances of POFileStatsJob are runnable jobs.
        verifyObject(IRunnableJob, POFileStatsJob(0))

    def test_source_interface(self):
        # The POFileStatsJob class is a source of POFileStatsJobs.
        verifyObject(IPOFileStatsJobSource, POFileStatsJob)
        verifyObject(IJobSource, POFileStatsJob)

    def test_run(self):
        # Running a job causes the POFile statistics to be updated.
        singular = self.factory.getUniqueString()
        pofile = self.factory.makePOFile(side=TranslationSide.UPSTREAM)
        # Create a message so we have something to have statistics about.
        self.factory.makePOTMsgSet(pofile.potemplate, singular)
        # The statistics start at 0.
        self.assertEqual(pofile.potemplate.messageCount(), 0)
        job = pofilestatsjob.schedule(pofile.id)
        # Just scheduling the job doesn't update the statistics.
        self.assertEqual(pofile.potemplate.messageCount(), 0)
        with dbuser('pofilestats'):
            job.run()
        # Now that the job ran, the statistics have been updated.
        self.assertEqual(pofile.potemplate.messageCount(), 1)

    def test_run_with_product(self):
        product = self.factory.makeProduct(
            translations_usage=ServiceUsage.LAUNCHPAD)
        productseries = self.factory.makeProductSeries(product=product)
        potemplate = self.factory.makePOTemplate(productseries=productseries)
        pofile = self.factory.makePOFile('en', potemplate)
        # Create a message so we have something to have statistics about.
        singular = self.factory.getUniqueString()
        self.factory.makePOTMsgSet(pofile.potemplate, singular)
        # The statistics are still at 0, even though there is a message.
        self.assertEqual(potemplate.messageCount(), 0)
        job = pofilestatsjob.schedule(pofile.id)
        # Just scheduling the job doesn't update the statistics.
        self.assertEqual(pofile.potemplate.messageCount(), 0)
        with dbuser('pofilestats'):
            job.run()
        # Now that the job ran, the statistics have been updated.
        self.assertEqual(pofile.potemplate.messageCount(), 1)

    def test_iterReady(self):
        # The POFileStatsJob class provides a way to iterate over the jobs
        # that are ready to run.  Initially, there aren't any.
        self.assertEqual(len(list(POFileStatsJob.iterReady())), 0)
        # We need a POFile to update.
        pofile = self.factory.makePOFile(side=TranslationSide.UPSTREAM)
        # If we schedule a job, then we'll get it back.
        job = pofilestatsjob.schedule(pofile.id)
        self.assertIs(list(POFileStatsJob.iterReady())[0], job)

    def test_second_job_is_scheduled(self):
        # If there is already one POFileStatsJob scheduled for a particular
        # POFile, then a second one is scheduled.
        self.assertEqual(len(list(POFileStatsJob.iterReady())), 0)
        # We need a POFile to update.
        pofile = self.factory.makePOFile(side=TranslationSide.UPSTREAM)
        # If we schedule a job, then there will be one scheduled.
        pofilestatsjob.schedule(pofile.id)
        self.assertIs(len(list(POFileStatsJob.iterReady())), 1)
        # If we attempt to schedule another job for the same POFile, a new job
        # is added.
        pofilestatsjob.schedule(pofile.id)
        self.assertIs(len(list(POFileStatsJob.iterReady())), 2)

    def assertJobUpdatesStats(self, pofile1, pofile2):
        # Create a single POTMsgSet and add it to only one of the POTemplates.
        self.factory.makeSuggestion(pofile1)
        self.factory.makeSuggestion(pofile2)
        # The statistics start at 0.
        self.assertEqual(pofile1.getStatistics(), (0, 0, 0, 0))
        self.assertEqual(pofile2.getStatistics(), (0, 0, 0, 0))
        job = pofilestatsjob.schedule(pofile1.id)
        # Just scheduling the job doesn't update the statistics.
        self.assertEqual(pofile1.getStatistics(), (0, 0, 0, 0))
        self.assertEqual(pofile2.getStatistics(), (0, 0, 0, 0))
        with dbuser('pofilestats'):
            job.run()
        # Now that the job ran, the statistics for the POFile have been
        # updated.
        self.assertEqual(pofile1.getStatistics(), (0, 0, 0, 1))
        # The statistics for the other POFile is also updated as a result of
        # running the job for the other POFile because they share
        # translations.
        self.assertEqual(pofile2.getStatistics(), (0, 0, 0, 1))

    def test_run_with_project_shared_template(self):
        # Create a product with two series and sharing POTemplates
        # in different series ('devel' and 'stable').
        product = self.factory.makeProduct(
            translations_usage=ServiceUsage.LAUNCHPAD)
        devel = self.factory.makeProductSeries(
            name='devel', product=product)
        stable = self.factory.makeProductSeries(
            name='stable', product=product)

        # POTemplate is a 'sharing' one if it has the same name ('messages').
        template1 = self.factory.makePOTemplate(devel, name='messages')
        template2 = self.factory.makePOTemplate(stable, name='messages')

        self.factory.makeLanguage('en-tt')
        pofile1 = self.factory.makePOFile('en-tt', template1)
        pofile2 = self.factory.makePOFile('en-tt', template2)

        self.assertJobUpdatesStats(pofile1, pofile2)

    def test_run_with_product_and_distro_translation_sharing(self):
        language = self.factory.makeLanguage('en-tt')
        distroseries = self.factory.makeUbuntuDistroSeries()
        distroseries.distribution.translation_focus = distroseries
        sourcepackagename = self.factory.makeSourcePackageName()
        sourcepackage = self.factory.makeSourcePackage(
            distroseries=distroseries,
            sourcepackagename=sourcepackagename)
        productseries = self.factory.makeProductSeries()
        sourcepackage.setPackaging(
            productseries, self.factory.makePerson())

        # Create template ready for sharing on the Ubuntu side.
        template1 = self.factory.makePOTemplate(
            distroseries=distroseries,
            sourcepackagename=sourcepackagename,
            name='messages')
        pofile1 = self.factory.makePOFile(
            language=language, potemplate=template1)

        # Create template ready for sharing on the upstream side.
        template2 = self.factory.makePOTemplate(
            productseries=productseries, name='messages')
        pofile2 = template2.getPOFileByLang(language.code)

        self.assertJobUpdatesStats(pofile1, pofile2)

    def test_run_with_distro_translation_sharing(self):
        language = self.factory.makeLanguage('en-tt')
        distroseries1 = self.factory.makeUbuntuDistroSeries()
        distroseries1.distribution.translation_focus = distroseries1
        sourcepackagename = self.factory.makeSourcePackageName()
        self.factory.makeSourcePackage(
            distroseries=distroseries1,
            sourcepackagename=sourcepackagename)
        distroseries2 = self.factory.makeUbuntuDistroSeries()
        distroseries2.distribution.translation_focus = distroseries2
        self.factory.makeSourcePackage(
            distroseries=distroseries2,
            sourcepackagename=sourcepackagename)

        template1 = self.factory.makePOTemplate(
            distroseries=distroseries1,
            sourcepackagename=sourcepackagename,
            name='messages')
        pofile1 = self.factory.makePOFile(
            language=language, potemplate=template1)

        template2 = self.factory.makePOTemplate(
            distroseries=distroseries2,
            sourcepackagename=sourcepackagename,
            name='messages')
        pofile2 = template2.getPOFileByLang(language.code)

        self.assertJobUpdatesStats(pofile1, pofile2)


class TestViaCelery(TestCaseWithFactory):

    layer = CeleryJobLayer

    def test_run(self):
        # POFileJob can run via Celery.
        self.useFixture(FeatureFixture(
            {'jobs.celery.enabled_classes': 'POFileStatsJob'}))
        # Running a job causes the POFile statistics to be updated.
        singular = self.factory.getUniqueString()
        pofile = self.factory.makePOFile(side=TranslationSide.UPSTREAM)
        # Create a message so we have something to have statistics about.
        self.factory.makePOTMsgSet(pofile.potemplate, singular)
        # The statistics start at 0.
        self.assertEqual(pofile.potemplate.messageCount(), 0)
        pofilestatsjob.schedule(pofile.id)
        with block_on_job():
            transaction.commit()
        # Now that the job ran, the statistics have been updated.
        self.assertEqual(pofile.potemplate.messageCount(), 1)
