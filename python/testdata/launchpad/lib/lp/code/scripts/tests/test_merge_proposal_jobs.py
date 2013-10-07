#! /usr/bin/python
#
# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the sendbranchmail script"""

from testtools.matchers import MatchesRegex
import transaction

from lp.code.model.tests.test_branchmergeproposaljobs import (
    make_runnable_incremental_diff_job,
    )
from lp.services.job.interfaces.job import JobStatus
from lp.services.scripts.tests import run_script
from lp.testing import TestCaseWithFactory
from lp.testing.layers import ZopelessAppServerLayer


class TestMergeProposalJobScript(TestCaseWithFactory):

    layer = ZopelessAppServerLayer

    def test_script_runs(self):
        """Ensure merge-proposal-jobs script runs."""
        job = make_runnable_incremental_diff_job(self)
        transaction.commit()
        retcode, stdout, stderr = run_script(
            'cronscripts/process-job-source.py',
            ['--log-twisted', 'IBranchMergeProposalJobSource'])
        self.assertEqual(0, retcode)
        self.assertEqual('', stdout)
        matches_expected = MatchesRegex(
            'INFO    Creating lockfile: /var/lock/launchpad-process-job-'
            'source-IBranchMergeProposalJobSource.lock\n'
            'INFO    Running through Twisted.\n'
            'Log opened.\n'
            'INFO    Log opened.\n'
            'ProcessPool stats:\n'
            'INFO    ProcessPool stats:\n'
            '\tworkers: 0\n'
            'INFO    \tworkers: 0\n'
            '(.|\n)*'
            'INFO    Running '
            '<GENERATE_INCREMENTAL_DIFF job for merge .*?> \(ID %d\).\n'
            '(.|\n)*'
            'INFO    STOPPING: \'\'\n'
            'Main loop terminated.\n'
            'INFO    Main loop terminated.\n'
            'INFO    Ran 1 GenerateIncrementalDiffJob jobs.\n' % job.job.id)
        self.assertThat(stderr, matches_expected)
        self.assertEqual(JobStatus.COMPLETED, job.status)
