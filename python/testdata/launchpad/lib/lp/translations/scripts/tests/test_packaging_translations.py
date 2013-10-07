# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the merge_translations script."""


from textwrap import dedent

from testtools.matchers import MatchesRegex
import transaction

from lp.services.scripts.tests import run_script
from lp.testing import TestCaseWithFactory
from lp.testing.layers import ZopelessAppServerLayer
from lp.translations.model.translationpackagingjob import TranslationSplitJob
from lp.translations.tests.test_translationpackagingjob import (
    make_translation_merge_job,
    )


class TestMergeTranslations(TestCaseWithFactory):

    layer = ZopelessAppServerLayer

    def test_merge_translations(self):
        job = make_translation_merge_job(self.factory)
        TranslationSplitJob.create(
            job.productseries, job.distroseries, job.sourcepackagename)
        transaction.commit()
        retcode, stdout, stderr = run_script(
            'cronscripts/process-job-source.py',
            ['ITranslationPackagingJobSource'],
            expect_returncode=0)
        matcher = MatchesRegex(dedent("""\
            INFO    Creating lockfile: /var/lock/launchpad-process-job-source-ITranslationPackagingJobSource.lock
            INFO    Running synchronously.
            INFO    Running <.*?TranslationMergeJob.*?> \(ID .*\) in status Waiting
            INFO    Merging .* and .* in Ubuntu Distroseries.*
            INFO    Deleted POTMsgSets: 1.  TranslationMessages: 1.
            INFO    Running <.*?TranslationSplitJob.*?> \(ID .*\) in status Waiting
            INFO    Splitting .* and .* in Ubuntu Distroseries.*
            INFO    1 entries split.
            INFO    Ran 1 TranslationMergeJob jobs.
            INFO    Ran 1 TranslationSplitJob jobs.
            """))
        self.assertThat(stderr, matcher)
        self.assertEqual('', stdout)
