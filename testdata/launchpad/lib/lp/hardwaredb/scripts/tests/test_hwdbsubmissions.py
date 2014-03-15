# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for hwdbsubmissions script."""

__metaclass__ = type

from tempfile import mktemp

from storm.store import Store
import transaction

from lp.hardwaredb.interfaces.hwdb import HWSubmissionProcessingStatus
from lp.hardwaredb.scripts.hwdbsubmissions import (
    ProcessingLoopForPendingSubmissions,
    ProcessingLoopForReprocessingBadSubmissions,
    )
from lp.testing import TestCaseWithFactory
from lp.testing.layers import (
    DatabaseLayer,
    LaunchpadScriptLayer,
    )
from lp.testing.matchers import Contains
from lp.testing.script import run_script


class TestProcessingLoops(TestCaseWithFactory):
    layer = LaunchpadScriptLayer

    def _makePendingSubmissionsLoop(self):
        """Parameters don't matter for these tests."""
        return ProcessingLoopForPendingSubmissions(None, None, 0, False)

    def test_PendingSubmissions_submitted_found(self):
        # The PendingSubmissions loop finds submitted entries.
        submission = self.factory.makeHWSubmission(
            status=HWSubmissionProcessingStatus.SUBMITTED)
        loop = self._makePendingSubmissionsLoop()
        # The sample data already contains one submission which we ignore.
        submissions = loop.getUnprocessedSubmissions(2)
        self.assertEqual([submission], submissions[1:])

    def test_PendingSubmissions_processed_not_found(self):
        # The PendingSubmissions loop ignores processed entries.
        submission = self.factory.makeHWSubmission(
            status=HWSubmissionProcessingStatus.PROCESSED)
        loop = self._makePendingSubmissionsLoop()
        # The sample data already contains one submission which we ignore.
        submissions = loop.getUnprocessedSubmissions(2)
        self.assertEqual([], submissions[1:])
        self.assertNotEqual([submission], submissions)

    def test_PendingSubmissions_invalid_not_found(self):
        # The PendingSubmissions loop ignores invalid entries.
        submission = self.factory.makeHWSubmission(
            status=HWSubmissionProcessingStatus.INVALID)
        loop = self._makePendingSubmissionsLoop()
        # The sample data already contains one submission which we ignore.
        submissions = loop.getUnprocessedSubmissions(2)
        self.assertEqual([], submissions[1:])
        self.assertNotEqual([submission], submissions)

    def test_PendingSubmissions_respects_chunk_size(self):
        # Only the requested number of entries are returned.
        self.factory.makeHWSubmission(
            status=HWSubmissionProcessingStatus.SUBMITTED)
        self.factory.makeHWSubmission(
            status=HWSubmissionProcessingStatus.SUBMITTED)
        loop = self._makePendingSubmissionsLoop()
        # The sample data already contains one submission.
        submissions = loop.getUnprocessedSubmissions(2)
        self.assertEqual(2, len(submissions))

    def _makeBadSubmissionsLoop(self, start=0):
        """Parameters don't matter for these tests."""
        return ProcessingLoopForReprocessingBadSubmissions(
            start, None, None, 0, False)

    def test_BadSubmissions_invalid_found(self):
        # The BadSubmissions loop finds invalid entries.
        submission = self.factory.makeHWSubmission(
            status=HWSubmissionProcessingStatus.INVALID)
        loop = self._makeBadSubmissionsLoop()
        submissions = loop.getUnprocessedSubmissions(2)
        self.assertEqual([submission], submissions)

    def test_BadSubmissions_processed_not_found(self):
        # The BadSubmissions loop ignores processed entries.
        self.factory.makeHWSubmission(
            status=HWSubmissionProcessingStatus.PROCESSED)
        loop = self._makeBadSubmissionsLoop()
        submissions = loop.getUnprocessedSubmissions(2)
        self.assertEqual([], submissions)

    def test_BadSubmissions_submitted_not_found(self):
        # The BadSubmissions loop ignores submitted entries.
        self.factory.makeHWSubmission(
            status=HWSubmissionProcessingStatus.SUBMITTED)
        loop = self._makeBadSubmissionsLoop()
        submissions = loop.getUnprocessedSubmissions(2)
        self.assertEqual([], submissions)

    def test_BadSubmissions_respects_chunk_size(self):
        # Only the requested number of entries are returned.
        self.factory.makeHWSubmission(
            status=HWSubmissionProcessingStatus.INVALID)
        self.factory.makeHWSubmission(
            status=HWSubmissionProcessingStatus.INVALID)
        loop = self._makeBadSubmissionsLoop()
        # The sample data already contains one submission.
        submissions = loop.getUnprocessedSubmissions(1)
        self.assertEqual(1, len(submissions))

    def test_BadSubmissions_respects_start(self):
        # It is possible to request a start id. Previous entries are ignored.
        submission1 = self.factory.makeHWSubmission(
            status=HWSubmissionProcessingStatus.INVALID)
        submission2 = self.factory.makeHWSubmission(
            status=HWSubmissionProcessingStatus.INVALID)
        self.assertTrue(submission1.id < submission2.id)
        loop = self._makeBadSubmissionsLoop(submission2.id)
        # The sample data already contains one submission.
        submissions = loop.getUnprocessedSubmissions(2)
        self.assertEqual([submission2], submissions)
        DatabaseLayer.force_dirty_database()

    def test_run_reprocessing_script_no_params(self):
        # cronscripts/reprocess-hwdb-submissions.py needs at least the
        # parameter --start-file
        retcode, stdout, stderr = run_script(
            'cronscripts/reprocess-hwdb-submissions.py', [])
        self.assertThat(
            stderr, Contains('Option --start-file not specified.'))
        DatabaseLayer.force_dirty_database()

    def test_run_reprocessing_script_startfile_does_not_exist(self):
        # If the specified start file does not exist,
        # cronscripts/reprocess-hwdb-submissions.py reports an error.
        does_not_exist = mktemp()
        retcode, stdout, stderr = run_script(
            'cronscripts/reprocess-hwdb-submissions.py',
            ['--start-file', does_not_exist])
        self.assertThat(
            stderr, Contains('Cannot access file %s' % does_not_exist))
        DatabaseLayer.force_dirty_database()

    def test_run_reprocessing_script_startfile_without_integer(self):
        # If the specified start file contains any non-integer string,
        # cronscripts/reprocess-hwdb-submissions.py reports an error.
        start_file_name = mktemp()
        start_file = open(start_file_name, 'w')
        start_file.write('nonsense')
        start_file.close()
        retcode, stdout, stderr = run_script(
            'cronscripts/reprocess-hwdb-submissions.py',
            ['--start-file', start_file_name])
        self.assertThat(
            stderr,
            Contains('%s must contain only an integer' % start_file_name))
        DatabaseLayer.force_dirty_database()

    def test_run_reprocessing_script_startfile_with_negative_integer(self):
        # If the specified start file contains any non-integer string,
        # cronscripts/reprocess-hwdb-submissions.py reports an error.
        start_file_name = mktemp()
        start_file = open(start_file_name, 'w')
        start_file.write('-1')
        start_file.close()
        retcode, stdout, stderr = run_script(
            'cronscripts/reprocess-hwdb-submissions.py',
            ['--start-file', start_file_name])
        self.assertThat(
            stderr,
            Contains('%s must contain a positive integer' % start_file_name))
        DatabaseLayer.force_dirty_database()

    def test_run_reprocessing_script_max_submission_not_integer(self):
        # If the parameter --max-submissions is not an integer,
        # cronscripts/reprocess-hwdb-submissions.py reports an error.
        retcode, stdout, stderr = run_script(
            'cronscripts/reprocess-hwdb-submissions.py',
            ['--max-submissions', 'nonsense'])
        expected = "Invalid value for --max_submissions specified: 'nonsense'"
        self.assertThat(stderr, Contains(expected))
        DatabaseLayer.force_dirty_database()

    def test_run_reprocessing_script_two_batches(self):
        # cronscripts/reprocess-hwdb-submissions.py begings to process
        # submissions with IDs starting at the value stored in the
        # file given as the parameter --start-file. When is has
        # finished processing the number of submissions specified by
        # --max-submissions, it stores the ID of the last prcessed
        # submission in start-file.
        new_submissions = []
        for count in range(5):
            new_submissions.append(
                self.factory.makeHWSubmission(
                    status=HWSubmissionProcessingStatus.INVALID))

        start_file_name = mktemp()
        start_file = open(start_file_name, 'w')
        start_file.write('%i' % new_submissions[1].id)
        start_file.close()
        transaction.commit()
        Store.of(new_submissions[0]).invalidate()

        retcode, stdout, stderr = run_script(
            'cronscripts/reprocess-hwdb-submissions.py',
            ['--max-submissions', '2', '--start-file', start_file_name])

        # We started with the ID of the second submission created abvoe,
        # so the first submission still has the status INVALID.
        self.assertEqual(
            HWSubmissionProcessingStatus.INVALID,
            new_submissions[0].status)
        # We processed two submissions, they now have the status
        # PROCESSED.
        self.assertEqual(
            HWSubmissionProcessingStatus.PROCESSED,
            new_submissions[1].status)
        self.assertEqual(
            HWSubmissionProcessingStatus.PROCESSED,
            new_submissions[2].status)
        # The  following submissions were not yet touched,
        self.assertEqual(
            HWSubmissionProcessingStatus.INVALID,
            new_submissions[3].status)
        self.assertEqual(
            HWSubmissionProcessingStatus.INVALID,
            new_submissions[4].status)

        # The start file now contains the ID of the 4th submission.
        new_start = int(open(start_file_name).read())
        self.assertEqual(new_submissions[3].id, new_start)

        # When we run the script again, for only one submission,
        # the 4th submission is processed.
        transaction.abort()
        Store.of(new_submissions[0]).invalidate()
        retcode, stdout, stderr = run_script(
            'cronscripts/reprocess-hwdb-submissions.py',
            ['--max-submissions', '1', '--start-file', start_file_name])
        self.assertEqual(
            HWSubmissionProcessingStatus.PROCESSED,
            new_submissions[3].status)
        self.assertEqual(
            HWSubmissionProcessingStatus.INVALID,
            new_submissions[4].status)
