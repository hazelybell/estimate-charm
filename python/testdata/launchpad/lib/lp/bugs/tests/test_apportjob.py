# Copyright 2010-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for ApportJobs."""

__metaclass__ = type

import os

from sqlobject import SQLObjectNotFound
import transaction
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.bugs.interfaces.apportjob import (
    ApportJobType,
    IApportJob,
    IProcessApportBlobJob,
    IProcessApportBlobJobSource,
    )
from lp.bugs.model.apportjob import (
    ApportJob,
    ApportJobDerived,
    )
from lp.bugs.utilities.filebugdataparser import (
    FileBugData,
    FileBugDataParser,
    )
from lp.services.config import config
from lp.services.features.testing import FeatureFixture
from lp.services.job.interfaces.job import JobStatus
from lp.services.job.tests import block_on_job
from lp.services.librarian.interfaces import ILibraryFileAliasSet
from lp.services.scripts.tests import run_script
from lp.services.temporaryblobstorage.interfaces import (
    ITemporaryStorageManager,
    )
from lp.services.webapp.interfaces import ILaunchpadRoot
from lp.testing import (
    login_person,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    CeleryJobLayer,
    LaunchpadFunctionalLayer,
    LaunchpadZopelessLayer,
    )
from lp.testing.views import create_initialized_view


class ApportJobTestCase(TestCaseWithFactory):
    """Test case for basic ApportJob gubbins."""

    layer = LaunchpadZopelessLayer

    def test_instantiate(self):
        # ApportJob.__init__() instantiates a ApportJob instance.
        blob = self.factory.makeBlob()

        metadata = ('some', 'arbitrary', 'metadata')
        apport_job = ApportJob(
            blob, ApportJobType.PROCESS_BLOB, metadata)

        self.assertEqual(blob, apport_job.blob)
        self.assertEqual(ApportJobType.PROCESS_BLOB, apport_job.job_type)

        # When we actually access the ApportJob's metadata it gets
        # unserialized from JSON, so the representation returned by
        # apport_job.metadata will be different from what we originally
        # passed in.
        metadata_expected = [u'some', u'arbitrary', u'metadata']
        self.assertEqual(metadata_expected, apport_job.metadata)
        self.assertProvides(apport_job, IApportJob)


class ApportJobDerivedTestCase(TestCaseWithFactory):
    """Test case for the ApportJobDerived class."""

    layer = LaunchpadZopelessLayer

    def test_create_explodes(self):
        # ApportJobDerived.create() will blow up because it needs to be
        # subclassed to work properly.
        blob = self.factory.makeBlob()
        self.assertRaises(
            AttributeError, ApportJobDerived.create, blob)


class ProcessApportBlobJobTestCase(TestCaseWithFactory):
    """Test case for the ProcessApportBlobJob class."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(ProcessApportBlobJobTestCase, self).setUp()

        # Create a BLOB using existing testing data.

        self.blob = self.factory.makeBlob(blob_file='extra_filebug_data.msg')
        transaction.commit()  # We need the blob available from the Librarian.

    def _assertFileBugDataMatchesDict(self, filebug_data, data_dict):
        """Asser that the data in a FileBugData object matches a dict."""
        self.assertEqual(
            filebug_data.initial_summary, data_dict['initial_summary'],
            "Initial summaries do not match")
        self.assertEqual(
            filebug_data.initial_tags, data_dict['initial_tags'],
            "Values for initial_tags do not match")
        self.assertEqual(
            filebug_data.private, data_dict['private'],
            "Values for private do not match")
        self.assertEqual(
            filebug_data.subscribers, data_dict['subscribers'],
            "Values for subscribers do not match")
        self.assertEqual(
            filebug_data.extra_description,
            data_dict['extra_description'],
            "Values for extra_description do not match")
        self.assertEqual(
            filebug_data.comments, data_dict['comments'],
            "Values for comments do not match")
        self.assertEqual(
            filebug_data.hwdb_submission_keys,
            data_dict['hwdb_submission_keys'],
            "Values for hwdb_submission_keys do not match")

        # The attachments list of the data_dict dict will be of
        # the same length as the attachments list in the filebug_data
        # object.
        self.assertEqual(
            len(filebug_data.attachments),
            len(data_dict['attachments']),
            "Lengths of attachment lists do not match.")

        # The attachments list of the data_dict dict is a list of dicts
        # containing data about the attachments to add to the bug once
        # it has been filed.
        for attachment_dict in data_dict['attachments']:
            file_alias_id = attachment_dict['file_alias_id']
            file_alias = getUtility(ILibraryFileAliasSet)[file_alias_id]
            attachment = filebug_data.attachments[
                data_dict['attachments'].index(attachment_dict)]

            if attachment.get('content', None) is not None:
                # If the FileBugData is coming from the parser directly,
                # the attachments won't have been processed, so we check
                # the unprocessed data against what the
                # ProcessApportBlobJob has stored in the librarian.
                file_content = attachment['content'].read()
                librarian_file_content = file_alias.read()
                self.assertEqual(
                    file_content, librarian_file_content,
                    "File content values do not match for attachment %s and "
                    "LibrarianFileAlias %s" % (
                        attachment['filename'], file_alias.filename))
                self.assertEqual(
                    attachment['filename'], file_alias.filename,
                    "Filenames do not match for attachment %s and "
                    "LibrarianFileAlias %s" % (
                        attachment['filename'], file_alias.id))
                self.assertEqual(
                    attachment['content_type'], file_alias.mimetype,
                    "Content types do not match for attachment %s and "
                    "LibrarianFileAlias %s" % (
                        attachment['filename'], file_alias.id))

            if attachment.get('file_alias', None) is not None:
                # If the attachment has a file_alias item, it will contain
                # the LibrarianFileAlias referenced by the attachment's
                # file_alias_id.
                self.assertEqual(
                    file_alias,
                    attachment['file_alias'],
                    "The attachment's file alias doesn't match it's "
                    "file_alias_id")

    def test_interface(self):
        # ProcessApportBlobJob instances provide IProcessApportBlobJobSource.
        job = getUtility(IProcessApportBlobJobSource).create(self.blob)
        self.assertProvides(job, IProcessApportBlobJob)

    def test_run(self):
        # IProcessApportBlobJobSource.run() extracts salient data from an
        # Apport BLOB and stores it in the job's metadata attribute.
        job = getUtility(IProcessApportBlobJobSource).create(self.blob)
        job.run()
        transaction.commit()

        # Once the job has been run, its metadata will contain a dict
        # called processed_data, which will contain the data parsed from
        # the BLOB.
        processed_data = job.metadata.get('processed_data', None)
        self.assertNotEqual(
            None, processed_data,
            "processed_data should not be None after the job has run.")

        # The items in the processed_data dict represent the salient
        # information parsed out of the BLOB. We can use our
        # FileBugDataParser to check that the items recorded in the
        # processed_data dict are correct.
        self.blob.file_alias.open()
        data_parser = FileBugDataParser(self.blob.file_alias)
        filebug_data = data_parser.parse()
        self._assertFileBugDataMatchesDict(filebug_data, processed_data)

    def test_getByBlobUUID(self):
        # IProcessApportBlobJobSource.getByBlobUUID takes a BLOB UUID as a
        # parameter and returns any jobs for that BLOB.
        uuid = self.blob.uuid

        job = getUtility(IProcessApportBlobJobSource).create(self.blob)
        job_from_uuid = getUtility(
            IProcessApportBlobJobSource).getByBlobUUID(uuid)
        self.assertEqual(
            job, job_from_uuid,
            "Job returend by getByBlobUUID() did not match original job.")
        self.assertEqual(
            self.blob, job_from_uuid.blob,
            "BLOB referenced by Job returned by getByBlobUUID() did not "
            "match original BLOB.")

        # If the UUID doesn't exist, getByBlobUUID() will raise a
        # SQLObjectNotFound error.
        self.assertRaises(
            SQLObjectNotFound,
            getUtility(IProcessApportBlobJobSource).getByBlobUUID, 'foobar')

    def test_create_job_creates_only_one(self):
        # IProcessApportBlobJobSource.create() will create only one
        # ProcessApportBlobJob for a given BLOB, no matter how many
        # times it is called.
        blobjobsource = getUtility(IProcessApportBlobJobSource)
        current_jobs = list(blobjobsource.iterReady())
        self.assertEqual(
            0, len(current_jobs),
            "There should be no ProcessApportBlobJobs. Found %s" %
            len(current_jobs))

        job = blobjobsource.create(self.blob)
        current_jobs = list(blobjobsource.iterReady())
        self.assertEqual(
            1, len(current_jobs),
            "There should be only one ProcessApportBlobJob. Found %s" %
            len(current_jobs))

        blobjobsource.create(self.blob)  # Another job.
        current_jobs = list(blobjobsource.iterReady())
        self.assertEqual(
            1, len(current_jobs),
            "There should be only one ProcessApportBlobJob. Found %s" %
            len(current_jobs))

        # If the job is complete, it will no longer show up in the list
        # of ready jobs. However, it won't be possible to create a new
        # job to process the BLOB because each BLOB can only have one
        # IProcessApportBlobJobSource.
        job.job.start()
        job.job.complete()
        current_jobs = list(blobjobsource.iterReady())
        self.assertEqual(
            0, len(current_jobs),
            "There should be no ready ProcessApportBlobJobs. Found %s" %
            len(current_jobs))

        yet_another_job = blobjobsource.create(self.blob)
        current_jobs = list(blobjobsource.iterReady())
        self.assertEqual(
            0, len(current_jobs),
            "There should be no new ProcessApportBlobJobs. Found %s" %
            len(current_jobs))

        # In fact, yet_another_job will be the same job as before, since
        # it's attached to the same BLOB.
        self.assertEqual(job.id, yet_another_job.id, "Jobs do not match.")

    def test_cronscript_succeeds(self):
        # The process-apport-blobs cronscript will run all pending
        # ProcessApportBlobJobs.
        getUtility(IProcessApportBlobJobSource).create(self.blob)
        transaction.commit()

        retcode, stdout, stderr = run_script(
            'cronscripts/process-job-source.py',
            ['IProcessApportBlobJobSource'], expect_returncode=0)
        self.assertEqual('', stdout)
        self.assertIn(
            'INFO    Ran 1 ProcessApportBlobJob jobs.\n', stderr)

    def test_getFileBugData(self):
        # The IProcessApportBlobJobSource.getFileBugData() method
        # returns the +filebug data parsed from the blob as a
        # FileBugData object.
        job = getUtility(IProcessApportBlobJobSource).create(self.blob)
        job.run()
        transaction.commit()

        # Rather irritatingly, the filebug_data object is wrapped in a
        # security proxy, so we remove it for the purposes of this
        # comparison.
        filebug_data = job.getFileBugData()
        self.assertTrue(
            isinstance(removeSecurityProxy(filebug_data), FileBugData),
            "job.getFileBugData() should return a FileBugData instance.")

        # The attributes of the FileBugData match the data stored in the
        # processed_data dict.
        processed_data = job.metadata.get('processed_data', None)
        self._assertFileBugDataMatchesDict(filebug_data, processed_data)


class TestViaCelery(TestCaseWithFactory):

    layer = CeleryJobLayer

    def test_ProcessApportBlobJob(self):
        # ProcessApportBlobJob runs under Celery.
        blob = self.factory.makeBlob(blob_file='extra_filebug_data.msg')
        self.useFixture(FeatureFixture(
            {'jobs.celery.enabled_classes': 'ProcessApportBlobJob'}))
        with block_on_job(self):
            job = getUtility(IProcessApportBlobJobSource).create(blob)
            transaction.commit()

        # Once the job has been run, its metadata will contain a dict
        # called processed_data, which will contain the data parsed from
        # the BLOB.
        processed_data = job.metadata.get('processed_data', None)
        self.assertIsNot(
            None, processed_data,
            "processed_data should not be None after the job has run.")


class TestTemporaryBlobStorageAddView(TestCaseWithFactory):
    """Test case for the TemporaryBlobStorageAddView."""

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestTemporaryBlobStorageAddView, self).setUp()

        # Create a BLOB using existing testing data.
        testfiles = os.path.join(config.root, 'lib/lp/bugs/tests/testfiles')
        blob_file = open(
            os.path.join(testfiles, 'extra_filebug_data.msg'))
        self.blob_data = blob_file.read()
        blob_file.close()

        person = self.factory.makePerson()
        self.product = self.factory.makeProduct()
        login_person(person)

    def _create_blob_and_job_using_storeblob(self):
        """Helper method to create a BLOB and ProcessApportBlobJob."""
        view = create_initialized_view(
            getUtility(ILaunchpadRoot), '+storeblob')

        # The view's store_blob method stores the blob in the database
        # and returns its UUID.
        blob_uuid = view.store_blob(self.blob_data)
        transaction.commit()

        return blob_uuid

    def _create_and_traverse_filebug_view(self, blob_uuid):
        """Create a +filebug view for a given blob id and return it."""
        view = create_initialized_view(
            self.product, '+filebug', path_info='/%s' % blob_uuid)

        # We need to call publishTraverse() on the view to ensure that
        # the extra_data_token attribute gets populated.
        view.publishTraverse(view.request, blob_uuid)
        return view

    def test_blob_has_been_processed(self):
        # Using the TemporaryBlobStorageAddView to upload a new BLOB
        # will show blob as being processed
        blob_uuid = self._create_blob_and_job_using_storeblob()
        blob = getUtility(ITemporaryStorageManager).fetch(blob_uuid)

        self.assertFalse(
            blob.hasBeenProcessed(),
            "BLOB should not be processed, but indicates it has.")

    def test_blob_get_processed_data(self):
        # Using the TemporaryBlobStorageAddView to upload a new BLOB
        # should indicate there two attachments were processed.
        blob_uuid = self._create_blob_and_job_using_storeblob()
        blob = getUtility(ITemporaryStorageManager).fetch(blob_uuid)
        job = getUtility(IProcessApportBlobJobSource).getByBlobUUID(blob_uuid)
        job.job.start()
        job.job.complete()
        job.run()
        blob_meta = blob.getProcessedData()

        self.assertEqual(
            len(blob_meta['attachments']), 2,
            "BLOB metadata: %s" % str(blob_meta))

    def test_adding_blob_adds_job(self):
        # Using the TemporaryBlobStorageAddView to upload a new BLOB
        # will add a new ProcessApportBlobJob for that BLOB.
        blob_uuid = self._create_blob_and_job_using_storeblob()
        blob = getUtility(ITemporaryStorageManager).fetch(blob_uuid)
        job = getUtility(IProcessApportBlobJobSource).getByBlobUUID(blob_uuid)

        self.assertEqual(
            blob, job.blob,
            "BLOB attached to Job returned by getByBlobUUID() did not match "
            "expected BLOB.")

    def test_filebug_extra_data_processing_job(self):
        # The +filebug view can retrieve the ProcessApportBlobJob for a
        # given BLOB UUID. This is available via its
        # extra_data_processing_job property.
        blob_uuid = self._create_blob_and_job_using_storeblob()
        view = self._create_and_traverse_filebug_view(blob_uuid)

        job = getUtility(IProcessApportBlobJobSource).getByBlobUUID(blob_uuid)
        job_from_view = view.extra_data_processing_job
        self.assertEqual(job, job_from_view, "Jobs didn't match.")

        # If a no UUID is passed to +filebug, its
        # extra_data_processing_job property will return None.
        view = create_initialized_view(self.product, '+filebug')
        job_from_view = view.extra_data_processing_job
        self.assertEqual(
            None, job_from_view,
            "Job returned by extra_data_processing_job should be None.")

    def test_filebug_extra_data_to_process(self):
        # The +filebug view has a property, extra_data_to_process, which
        # indicates whether or not an Apport blob has been processed.
        blob_uuid = self._create_blob_and_job_using_storeblob()
        view = self._create_and_traverse_filebug_view(blob_uuid)

        job_from_view = view.extra_data_processing_job

        # Because the job hasn't yet been run the view's extra_data_to_process
        # property will return True.
        self.assertEqual(
            JobStatus.WAITING, job_from_view.job.status,
            "Job should be WAITING, is in fact %s" %
            job_from_view.job.status.title)
        self.assertTrue(
            view.extra_data_to_process,
            "view.extra_data_to_process should be True while job is WAITING.")

        # If the job is started bug hasn't completed, extra_data_to_process
        # will remain True.
        job_from_view.job.start()
        self.assertEqual(
            JobStatus.RUNNING, job_from_view.job.status,
            "Job should be RUNNING, is in fact %s" %
            job_from_view.job.status.title)
        self.assertTrue(
            view.extra_data_to_process,
            "view.extra_data_to_process should be True while job is RUNNING.")

        # Once the job is complete, extra_data_to_process will be False
        job_from_view.job.complete()
        self.assertEqual(
            JobStatus.COMPLETED, job_from_view.job.status,
            "Job should be COMPLETED, is in fact %s" %
            job_from_view.job.status.title)
        self.assertFalse(
            view.extra_data_to_process,
            "view.extra_data_to_process should be False when job is "
            "COMPLETED.")

        # If there's no job - for example if someone visits the +filebug
        # page normally, example - extra_data_to_process will always be
        # False.
        view = create_initialized_view(self.product, '+filebug')
        self.assertEqual(
            None, view.extra_data_processing_job,
            "extra_data_processing_job should be None when there's no job "
            "for a view.")
        self.assertFalse(
            view.extra_data_to_process,
            "view.extra_data_to_process should be False when there is no "
            "job.")
