# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for CodeImportResult."""

__metaclass__ = type

from datetime import datetime

from pytz import UTC
from testtools.matchers import LessThan

from lp.code.interfaces.codeimportresult import ICodeImportResult
from lp.testing import TestCaseWithFactory
from lp.testing.layers import LaunchpadFunctionalLayer


class TestCodeImportResult(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def test_provides_interface(self):
        result = self.factory.makeCodeImportResult()
        self.assertProvides(result, ICodeImportResult)

    def test_date_created(self):
        result = self.factory.makeCodeImportResult()
        # date_created is "now", but there will have been a transaction
        # commit, so it won't be the same as UTC_NOW.
        self.assertThat(
            result.date_created,
            LessThan(datetime.utcnow().replace(tzinfo=UTC)))
        self.assertEqual(result.date_created, result.date_job_finished)

    def test_date_job_started(self):
        date = self.factory.getUniqueDate()
        result = self.factory.makeCodeImportResult(date_started=date)
        self.assertEqual(date, result.date_job_started)
