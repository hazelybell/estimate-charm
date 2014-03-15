# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""CVE related tests."""

from zope.component import getUtility

from lp.bugs.interfaces.bugtasksearch import BugTaskSearchParams
from lp.bugs.interfaces.cve import ICveSet
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    verifyObject,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestCveSet(TestCaseWithFactory):
    """Tests for CveSet."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        """Create a few bugtasks and CVEs."""
        super(TestCveSet, self).setUp()
        self.distroseries = self.factory.makeDistroSeries()
        self.bugs = []
        self.cves = []
        self.cve_index = 0
        with person_logged_in(self.distroseries.owner):
            for count in range(4):
                task = self.factory.makeBugTask(target=self.distroseries)
                bug = task.bug
                self.bugs.append(bug)
                cve = self.makeCVE()
                self.cves.append(cve)
                bug.linkCVE(cve, self.distroseries.owner)

    def makeCVE(self):
        """Create a CVE."""
        self.cve_index += 1
        return self.factory.makeCVE('2000-%04i' % self.cve_index)

    def test_CveSet_implements_ICveSet(self):
        cveset = getUtility(ICveSet)
        self.assertTrue(verifyObject(ICveSet, cveset))

    def test_getBugCvesForBugTasks(self):
        # ICveSet.getBugCvesForBugTasks() returns tuples (bug, cve)
        # for the given bugtasks.
        bugtasks = self.distroseries.searchTasks(
            BugTaskSearchParams(self.distroseries.owner, has_cve=True))
        bug_cves = getUtility(ICveSet).getBugCvesForBugTasks(bugtasks)
        found_bugs = [bug for bug, cve in bug_cves]
        found_cves = [cve for bug, cve in bug_cves]
        self.assertEqual(self.bugs, found_bugs)
        self.assertEqual(self.cves, found_cves)

    def test_getBugCvesForBugTasks_with_mapper(self):
        # ICveSet.getBugCvesForBugTasks() takes a function f as an
        # optional argeument. This function is applied to each CVE
        # related to the given bugs; the method return a sequence of
        # tuples (bug, f(cve)).
        def cve_name(cve):
            return cve.displayname

        bugtasks = self.distroseries.searchTasks(
            BugTaskSearchParams(self.distroseries.owner, has_cve=True))
        bug_cves = getUtility(ICveSet).getBugCvesForBugTasks(
            bugtasks, cve_name)
        found_bugs = [bug for bug, cve in bug_cves]
        cve_data = [cve for bug, cve in bug_cves]
        self.assertEqual(self.bugs, found_bugs)
        expected = [
            u'CVE-2000-0001', u'CVE-2000-0002', u'CVE-2000-0003',
            u'CVE-2000-0004']
        self.assertEqual(expected, cve_data)
