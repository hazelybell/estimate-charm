# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for DiffView."""

from lp.code.browser.diff import PreviewDiffFormatterAPI
from lp.testing import TestCaseWithFactory
from lp.testing.layers import LaunchpadFunctionalLayer


class TestFormatterAPI(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def test_empty_conflicts(self):
        """'has conflicts' does not appear if conflicts is empty string."""
        diff = self.factory.makePreviewDiff(conflicts=u'')
        self.assertEqual('', diff.conflicts)
        formatter = PreviewDiffFormatterAPI(diff)
        self.assertNotIn('has conflicts', formatter.link(None))

    def test_none_conflicts(self):
        """'has conflicts' does not appear if conflicts is None."""
        diff = self.factory.makePreviewDiff(conflicts=None)
        self.assertIs(None, diff.conflicts)
        formatter = PreviewDiffFormatterAPI(diff)
        self.assertNotIn('has conflicts', formatter.link(None))

    def test_with_conflicts(self):
        """'has conflicts' appears if conflicts is a non-empty string."""
        diff = self.factory.makePreviewDiff(conflicts=u'bork')
        self.assertEqual('bork', diff.conflicts)
        formatter = PreviewDiffFormatterAPI(diff)
        self.assertIn('has conflicts', formatter.link(None))
