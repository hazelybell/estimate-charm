# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for merging translations."""

__metaclass__ = type


from lazr.lifecycle.event import ObjectModifiedEvent
from lazr.lifecycle.snapshot import Snapshot
import transaction
from zope.component import getUtility
from zope.event import notify

from lp.registry.interfaces.packaging import IPackagingUtil
from lp.services.features.testing import FeatureFixture
from lp.services.job.interfaces.job import (
    IRunnableJob,
    JobStatus,
    )
from lp.services.job.tests import block_on_job
from lp.testing import (
    celebrity_logged_in,
    EventRecorder,
    person_logged_in,
    TestCaseWithFactory,
    verifyObject,
    )
from lp.testing.layers import (
    CeleryJobLayer,
    LaunchpadZopelessLayer,
    )
from lp.translations.interfaces.potemplate import IPOTemplate
from lp.translations.interfaces.side import TranslationSide
from lp.translations.interfaces.translationpackagingjob import (
    ITranslationPackagingJobSource,
    )
from lp.translations.model.potemplate import POTemplateSubset
from lp.translations.model.translationpackagingjob import (
    TranslationMergeJob,
    TranslationPackagingJob,
    TranslationSplitJob,
    TranslationTemplateChangeJob,
    )
from lp.translations.model.translationsharingjob import (
    TranslationSharingJob,
    TranslationSharingJobDerived,
    )
from lp.translations.tests.test_translationsplitter import (
    make_shared_potmsgset,
    )


def make_translation_merge_job(factory, not_ubuntu=False):
    singular = factory.getUniqueString()
    upstream_pofile = factory.makePOFile(side=TranslationSide.UPSTREAM)
    upstream_potmsgset = factory.makePOTMsgSet(
        upstream_pofile.potemplate, singular)
    upstream = factory.makeCurrentTranslationMessage(
        pofile=upstream_pofile, potmsgset=upstream_potmsgset)
    if not_ubuntu:
        distroseries = factory.makeDistroSeries()
    else:
        distroseries = factory.makeUbuntuDistroSeries()
    package_potemplate = factory.makePOTemplate(
        distroseries=distroseries, name=upstream_pofile.potemplate.name)
    package_pofile = factory.makePOFile(
        potemplate=package_potemplate, language=upstream_pofile.language)
    package_potmsgset = factory.makePOTMsgSet(
        package_pofile.potemplate, singular)
    factory.makeCurrentTranslationMessage(
        pofile=package_pofile, potmsgset=package_potmsgset,
        translations=upstream.translations)
    productseries = upstream_pofile.potemplate.productseries
    distroseries = package_pofile.potemplate.distroseries
    sourcepackagename = package_pofile.potemplate.sourcepackagename
    return TranslationMergeJob.create(
        productseries=productseries, distroseries=distroseries,
        sourcepackagename=sourcepackagename)


def get_msg_sets(productseries=None, distroseries=None,
               sourcepackagename=None):
    msg_sets = []
    for template in POTemplateSubset(
        productseries=productseries, distroseries=distroseries,
        sourcepackagename=sourcepackagename):
        msg_sets.extend(template.getPOTMsgSets())
    return msg_sets


def get_translations(productseries=None, distroseries=None,
                    sourcepackagename=None):
    msg_sets = get_msg_sets(
        productseries=productseries, distroseries=distroseries,
        sourcepackagename=sourcepackagename)
    translations = set()
    for msg_set in msg_sets:
        translations.update(msg_set.getAllTranslationMessages())
    return translations


def count_translations(job):
    tm = get_translations(productseries=job.productseries)
    tm.update(get_translations(
        sourcepackagename=job.sourcepackagename,
        distroseries=job.distroseries))
    return len(tm)


class JobFinder:

    def __init__(self, productseries, sourcepackage, job_class,
                 potemplate=None):
        if potemplate is None:
            self.productseries = productseries
            self.sourcepackagename = sourcepackage.sourcepackagename
            self.distroseries = sourcepackage.distroseries
            self.potemplate = None
        else:
            self.potemplate = potemplate
        self.job_type = job_class.class_job_type

    def find(self):
        if self.potemplate is None:
            return list(TranslationSharingJobDerived.iterReady([
              TranslationSharingJob.productseries_id == self.productseries.id,
              (TranslationSharingJob.sourcepackagename_id ==
               self.sourcepackagename.id),
              TranslationSharingJob.distroseries_id == self.distroseries.id,
              TranslationSharingJob.job_type == self.job_type,
              ]))
        else:
            return list(
                TranslationSharingJobDerived.iterReady([
                    TranslationSharingJob.potemplate_id == self.potemplate.id,
                    TranslationSharingJob.job_type == self.job_type,
                    ]))


class TestTranslationPackagingJob(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def test_interface(self):
        """Should implement ITranslationPackagingJobSource."""
        verifyObject(ITranslationPackagingJobSource, TranslationPackagingJob)


class TestTranslationMergeJob(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def test_interface(self):
        """TranslationMergeJob must implement IRunnableJob."""
        job = make_translation_merge_job(self.factory)
        verifyObject(IRunnableJob, job)

    def test_run_merges_msgset(self):
        """Run should merge msgsets."""
        job = make_translation_merge_job(self.factory)
        self.becomeDbUser('rosettaadmin')
        product_msg = get_msg_sets(productseries=job.productseries)
        package_msg = get_msg_sets(
            sourcepackagename=job.sourcepackagename,
            distroseries=job.distroseries)
        self.assertNotEqual(package_msg, product_msg)
        job.run()
        product_msg = get_msg_sets(productseries=job.productseries)
        package_msg = get_msg_sets(
            sourcepackagename=job.sourcepackagename,
            distroseries=job.distroseries)
        self.assertEqual(package_msg, product_msg)

    def test_run_merges_translations(self):
        """Run should merge translations."""
        job = make_translation_merge_job(self.factory)
        self.becomeDbUser('rosettaadmin')
        self.assertEqual(2, count_translations(job))
        job.run()
        self.assertEqual(1, count_translations(job))

    def test_skips_non_ubuntu_distros(self):
        """Run should ignore non-Ubuntu distributions."""
        job = make_translation_merge_job(self.factory, not_ubuntu=True)
        self.becomeDbUser('rosettaadmin')
        self.assertEqual(2, count_translations(job))
        job.run()
        self.assertEqual(2, count_translations(job))

    def test_create_packaging_makes_job(self):
        """Creating a Packaging should make a TranslationMergeJob."""
        productseries = self.factory.makeProductSeries()
        sourcepackage = self.factory.makeSourcePackage()
        finder = JobFinder(productseries, sourcepackage, TranslationMergeJob)
        self.assertEqual([], finder.find())
        sourcepackage.setPackaging(productseries, productseries.owner)
        self.assertNotEqual([], finder.find())
        # Ensure no constraints were violated.
        transaction.commit()

    def test_getNextJobStatus(self):
        """Should find next packaging job."""
        #suppress job creation.
        with EventRecorder():
            packaging = self.factory.makePackagingLink()
        self.assertIs(None, TranslationMergeJob.getNextJobStatus(packaging))
        TranslationMergeJob.forPackaging(packaging)
        self.assertEqual(
            JobStatus.WAITING,
            TranslationMergeJob.getNextJobStatus(packaging))

    def test_getNextJobStatus_wrong_packaging(self):
        """Jobs on wrong packaging should be ignored."""
        #suppress job creation.
        with EventRecorder():
            packaging = self.factory.makePackagingLink()
        self.factory.makePackagingLink(
            productseries=packaging.productseries)
        self.assertIs(None, TranslationMergeJob.getNextJobStatus(packaging))
        self.factory.makePackagingLink()
        self.factory.makePackagingLink(
            distroseries=packaging.distroseries)
        self.assertIs(None, TranslationMergeJob.getNextJobStatus(packaging))
        TranslationMergeJob.create(
            sourcepackagename=packaging.sourcepackagename,
            distroseries=packaging.distroseries,
            productseries=self.factory.makeProductSeries())
        self.assertIs(None, TranslationMergeJob.getNextJobStatus(packaging))

    def test_getNextJobStatus_wrong_type(self):
        """Only TranslationMergeJobs should result."""
        #suppress job creation.
        with EventRecorder():
            packaging = self.factory.makePackagingLink()
        TranslationSplitJob.forPackaging(packaging)
        self.assertIs(
            None, TranslationMergeJob.getNextJobStatus(packaging))

    def test_getNextJobStatus_status(self):
        """Only RUNNING and WAITING jobs should influence status."""
        #suppress job creation.
        with EventRecorder():
            packaging = self.factory.makePackagingLink()
        job = TranslationMergeJob.forPackaging(packaging)
        job.start()
        self.assertEqual(JobStatus.RUNNING,
            TranslationMergeJob.getNextJobStatus(packaging))
        job.fail()
        self.assertIs(None, TranslationMergeJob.getNextJobStatus(packaging))
        job2 = TranslationMergeJob.forPackaging(packaging)
        job2.start()
        job2.complete()
        job3 = TranslationMergeJob.forPackaging(packaging)
        job3.suspend()
        self.assertIs(None, TranslationMergeJob.getNextJobStatus(packaging))

    def test_getNextJobStatus_order(self):
        """Status should order by id."""
        with EventRecorder():
            packaging = self.factory.makePackagingLink()
        job = TranslationMergeJob.forPackaging(packaging)
        job.start()
        TranslationMergeJob.forPackaging(packaging)
        self.assertEqual(JobStatus.RUNNING,
            TranslationMergeJob.getNextJobStatus(packaging))


class TestTranslationSplitJob(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def test_run_splits_translations(self):
        upstream_item, ubuntu_item = make_shared_potmsgset(self.factory)
        job = TranslationSplitJob.create(
            upstream_item.potemplate.productseries,
            ubuntu_item.potemplate.distroseries,
            ubuntu_item.potemplate.sourcepackagename,
        )
        self.assertEqual(upstream_item.potmsgset, ubuntu_item.potmsgset)
        job.run()
        self.assertNotEqual(upstream_item.potmsgset, ubuntu_item.potmsgset)

    def test_deletePackaging_makes_job(self):
        """Creating a Packaging should make a TranslationMergeJob."""
        packaging = self.factory.makePackagingLink()
        finder = JobFinder(
            packaging.productseries, packaging.sourcepackage,
            TranslationSplitJob)
        self.assertEqual([], finder.find())
        user = self.factory.makePerson(karma=200)
        with person_logged_in(user):
            getUtility(IPackagingUtil).deletePackaging(
                packaging.productseries, packaging.sourcepackagename,
                packaging.distroseries)
        (job,) = finder.find()
        self.assertIsInstance(job, TranslationSplitJob)


class TestTranslationTemplateChangeJob(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def test_modifyPOTemplate_makes_job(self):
        """Creating a Packaging should make a TranslationMergeJob."""
        potemplate = self.factory.makePOTemplate()
        finder = JobFinder(
            None, None, TranslationTemplateChangeJob, potemplate)
        self.assertEqual([], finder.find())
        with person_logged_in(potemplate.owner):
            snapshot = Snapshot(potemplate, providing=IPOTemplate)
            potemplate.name = self.factory.getUniqueString()
            notify(ObjectModifiedEvent(potemplate, snapshot, ["name"]))

        (job,) = finder.find()
        self.assertIsInstance(job, TranslationTemplateChangeJob)

    def test_splits_and_merges(self):
        """Changing a template makes the translations split and then
        re-merged in the new target sharing set."""
        potemplate = self.factory.makePOTemplate(name='template')
        other_ps = self.factory.makeProductSeries(
            product=potemplate.productseries.product)
        old_shared = self.factory.makePOTemplate(name='template',
                                                 productseries=other_ps)
        new_shared = self.factory.makePOTemplate(name='renamed',
                                                 productseries=other_ps)

        # Set up shared POTMsgSets and translations.
        potmsgset = self.factory.makePOTMsgSet(potemplate, sequence=1)
        potmsgset.setSequence(old_shared, 1)
        self.factory.makeCurrentTranslationMessage(potmsgset=potmsgset)

        # This is the identical English message in the new_shared template.
        target_potmsgset = self.factory.makePOTMsgSet(
            new_shared, sequence=1, singular=potmsgset.singular_text)

        # Rename the template and confirm that messages are now shared
        # with new_shared instead of old_shared.
        potemplate.name = 'renamed'
        job = TranslationTemplateChangeJob.create(potemplate=potemplate)

        self.becomeDbUser('rosettaadmin')
        job.run()

        # New POTMsgSet is now different from the old one (it's been split),
        # but matches the target potmsgset (it's been merged into it).
        new_potmsgset = potemplate.getPOTMsgSets()[0]
        old_potmsgset = old_shared.getPOTMsgSets()[0]
        target_potmsgset = new_shared.getPOTMsgSets()[0]
        self.assertNotEqual(old_potmsgset, new_potmsgset)
        self.assertEqual(target_potmsgset, new_potmsgset)

        # Translations have been merged as well.
        self.assertContentEqual(
            [tm.translations for tm in potmsgset.getAllTranslationMessages()],
            [tm.translations
             for tm in new_potmsgset.getAllTranslationMessages()])


class TestViaCelery(TestCaseWithFactory):

    layer = CeleryJobLayer

    def test_TranslationMergeJob(self):
        """TranslationMergeJob runs under Celery."""
        self.useFixture(FeatureFixture({
            'jobs.celery.enabled_classes': 'TranslationMergeJob',
        }))
        job = make_translation_merge_job(self.factory)
        product_msg = get_msg_sets(productseries=job.productseries)
        package_msg = get_msg_sets(
            sourcepackagename=job.sourcepackagename,
            distroseries=job.distroseries)
        with block_on_job(self):
            transaction.commit()
        product_msg = get_msg_sets(productseries=job.productseries)
        package_msg = get_msg_sets(
            sourcepackagename=job.sourcepackagename,
            distroseries=job.distroseries)
        self.assertEqual(package_msg, product_msg)

    def test_TranslationSplitJob(self):
        """Ensure TranslationSplitJob runs under Celery."""
        self.useFixture(FeatureFixture({
            'jobs.celery.enabled_classes': 'TranslationSplitJob',
        }))
        upstream_item, ubuntu_item = make_shared_potmsgset(self.factory)
        TranslationSplitJob.create(
            upstream_item.potemplate.productseries,
            ubuntu_item.potemplate.distroseries,
            ubuntu_item.potemplate.sourcepackagename,
        )
        self.assertEqual(upstream_item.potmsgset, ubuntu_item.potmsgset)
        with block_on_job(self):
            transaction.commit()
        self.assertNotEqual(upstream_item.potmsgset, ubuntu_item.potmsgset)

    def test_TranslationTemplateChangeJob(self):
        """Ensure TranslationTemplateChangeJob runs under Celery."""
        self.useFixture(FeatureFixture({
            'jobs.celery.enabled_classes': 'TranslationTemplateChangeJob',
        }))
        potemplate = self.factory.makePOTemplate(name='template')
        other_ps = self.factory.makeProductSeries(
            product=potemplate.productseries.product)
        old_shared = self.factory.makePOTemplate(name='template',
                                                 productseries=other_ps)
        new_shared = self.factory.makePOTemplate(name='renamed',
                                                 productseries=other_ps)

        # Set up shared POTMsgSets and translations.
        potmsgset = self.factory.makePOTMsgSet(potemplate, sequence=1)
        potmsgset.setSequence(old_shared, 1)
        self.factory.makeCurrentTranslationMessage(potmsgset=potmsgset)

        # This is the identical English message in the new_shared template.
        target_potmsgset = self.factory.makePOTMsgSet(
            new_shared, sequence=1, singular=potmsgset.singular_text)

        # Rename the template and confirm that messages are now shared
        # with new_shared instead of old_shared.
        with celebrity_logged_in('admin'):
            potemplate.name = 'renamed'
        TranslationTemplateChangeJob.create(potemplate=potemplate)

        with block_on_job(self):
            transaction.commit()

        # New POTMsgSet is now different from the old one (it's been split),
        # but matches the target potmsgset (it's been merged into it).
        new_potmsgset = potemplate.getPOTMsgSets()[0]
        old_potmsgset = old_shared.getPOTMsgSets()[0]
        target_potmsgset = new_shared.getPOTMsgSets()[0]
        self.assertNotEqual(old_potmsgset, new_potmsgset)
        self.assertEqual(target_potmsgset, new_potmsgset)

        # Translations have been merged as well.
        self.assertContentEqual(
            [tm.translations for tm in potmsgset.getAllTranslationMessages()],
            [tm.translations
             for tm in new_potmsgset.getAllTranslationMessages()])
