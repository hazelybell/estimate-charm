# Copyright 2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from testtools.content import text_content
import transaction
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.services.features.testing import FeatureFixture
from lp.services.job.interfaces.job import JobStatus
from lp.services.job.tests import block_on_job
from lp.services.mail.sendmail import format_address_for_person
from lp.services.tarfile_helpers import LaunchpadWriteTarFile
from lp.soyuz.interfaces.packagetranslationsuploadjob import (
    IPackageTranslationsUploadJob,
    IPackageTranslationsUploadJobSource,
    )
from lp.soyuz.model.packagetranslationsuploadjob import (
    PackageTranslationsUploadJob,
    )
from lp.testing import (
    run_script,
    TestCaseWithFactory,
    verifyObject,
    )
from lp.testing.fakemethod import FakeMethod
from lp.testing.layers import (
    CeleryJobLayer,
    LaunchpadZopelessLayer,
    )
from lp.translations.interfaces.translationimportqueue import (
    ITranslationImportQueue,
    )


class LocalTestHelper(TestCaseWithFactory):

    def makeJob(self, spr_creator=None, archive=None,
                sourcepackagerelease=None, libraryfilealias=None,
                job_requester=None, tar_content=None):
        if spr_creator is None:
            creator = self.factory.makePerson()
        else:
            creator = self.factory.makePerson(name=spr_creator)
        if job_requester is None:
            requester = self.factory.makePerson()
        else:
            requester = self.factory.makePerson(name=job_requester)
        if archive is None:
            archive = self.factory.makeArchive()
        if sourcepackagerelease is None:
            sourcepackagerelease = self.factory.makeSourcePackageRelease(
                archive=archive, creator=creator)
        if libraryfilealias is None:
            libraryfilealias = self.makeTranslationsLFA(tar_content)
        return (sourcepackagerelease,
                getUtility(IPackageTranslationsUploadJobSource).create(
                    sourcepackagerelease, libraryfilealias, requester))

    def makeTranslationsLFA(self, tar_content=None):
        """Create an LibraryFileAlias containing dummy translation data."""
        if tar_content is None:
            tar_content = {
                'source/po/foo.pot': 'Foo template',
                'source/po/eo.po': 'Foo translation',
                }
        tarfile_content = LaunchpadWriteTarFile.files_to_string(
            tar_content)
        return self.factory.makeLibraryFileAlias(content=tarfile_content)


class TestPackageTranslationsUploadJob(LocalTestHelper):

    layer = LaunchpadZopelessLayer

    def test_job_implements_IPackageTranslationsUploadJob(self):
        _, job = self.makeJob()
        self.assertTrue(verifyObject(IPackageTranslationsUploadJob, job))

    def test_job_source_implements_IPackageTranslationsUploadJobSource(self):
        job_source = getUtility(IPackageTranslationsUploadJobSource)
        self.assertTrue(verifyObject(IPackageTranslationsUploadJobSource,
                                     job_source))

    def test_iterReady(self):
        _, job1 = self.makeJob()
        removeSecurityProxy(job1).job._status = JobStatus.COMPLETED
        _, job2 = self.makeJob()
        jobs = list(PackageTranslationsUploadJob.iterReady())
        self.assertEqual(1, len(jobs))

    def test_importer_is_creator(self):
        spr, job = self.makeJob(spr_creator="foobar")
        transaction.commit()
        job.run()
        translation_import_queue = getUtility(ITranslationImportQueue)
        entries_in_queue = translation_import_queue.getAllEntries(
            target=spr.sourcepackage)
        self.assertEqual(entries_in_queue[0].importer.name, "foobar")

    def test_getErrorRecipients_requester(self):
        spr, job = self.makeJob()
        email = format_address_for_person(job.requester)
        self.assertEquals([email], job.getErrorRecipients())
        removeSecurityProxy(job).requester = None
        self.assertEquals([], job.getErrorRecipients())


    def test_run(self):
        archive = self.factory.makeArchive()
        foo_pkg = self.factory.makeSourcePackageRelease(archive=archive)
        method = FakeMethod()
        removeSecurityProxy(foo_pkg).attachTranslationFiles = method
        spr, job = self.makeJob(archive=archive, sourcepackagerelease=foo_pkg)
        transaction.commit()
        job.run()
        self.assertEqual(method.call_count, 1)

    def test_smoke(self):
        tar_content = {
            'source/po/foobar.pot': 'FooBar template',
        }
        spr, job = self.makeJob(tar_content=tar_content)
        transaction.commit()
        out, err, exit_code = run_script(
            "LP_DEBUG_SQL=1 cronscripts/process-job-source.py -vv %s" % (
                IPackageTranslationsUploadJobSource.getName()))

        self.addDetail("stdout", text_content(out))
        self.addDetail("stderr", text_content(err))

        self.assertEqual(0, exit_code)
        translation_import_queue = getUtility(ITranslationImportQueue)
        entries_in_queue = translation_import_queue.getAllEntries(
            target=spr.sourcepackage)

        self.assertEqual(1, entries_in_queue.count())
        # Check if the file in tar_content is queued:
        self.assertTrue("po/foobar.pot", entries_in_queue[0].path)


class TestViaCelery(LocalTestHelper):
    """PackageTranslationsUploadJob runs under Celery."""

    layer = CeleryJobLayer

    def test_run(self):
        self.useFixture(FeatureFixture({
            'jobs.celery.enabled_classes': 'PackageTranslationsUploadJob',
        }))

        spr, job = self.makeJob()
        with block_on_job(self):
            transaction.commit()
        translation_import_queue = getUtility(ITranslationImportQueue)
        entries_in_queue = translation_import_queue.getAllEntries(
            target=spr.sourcepackage).count()
        self.assertEqual(2, entries_in_queue)
