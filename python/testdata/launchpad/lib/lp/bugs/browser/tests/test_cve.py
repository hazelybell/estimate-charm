# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""CVE related tests."""

from operator import attrgetter
import re

from lp.bugs.browser.cvereport import BugTaskCve
from lp.bugs.interfaces.bugtask import (
    RESOLVED_BUGTASK_STATUSES,
    UNRESOLVED_BUGTASK_STATUSES,
    )
from lp.services.webapp.publisher import canonical_url
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.views import create_initialized_view


class TestCVEReportView(TestCaseWithFactory):
    """Tests for CveSet."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        """Create a few bugtasks and CVEs."""
        super(TestCVEReportView, self).setUp()
        distroseries = self.factory.makeDistroSeries()
        self.resolved_bugtasks = []
        self.unresolved_bugtasks = []
        self.cves = {}
        self.getCVE = self.cveGenerator().next
        with person_logged_in(distroseries.owner):
            for status in RESOLVED_BUGTASK_STATUSES:
                tasks, cves = self.makeBugTasksWithCve(status, distroseries)
                self.resolved_bugtasks.append(tasks)
                self.cves[tasks[0].bug] = cves
            for status in UNRESOLVED_BUGTASK_STATUSES:
                tasks, cves = self.makeBugTasksWithCve(status, distroseries)
                self.unresolved_bugtasks.append(tasks)
                self.cves[tasks[0].bug] = cves
        self.view = create_initialized_view(distroseries, '+cve')

    def makeBugTasksWithCve(self, status, distroseries):
        """Return two bugtasks for one bug linked to CVE."""
        task = self.factory.makeBugTask(
            target=self.factory.makeSourcePackage(distroseries=distroseries))
        task.transitionToStatus(status, distroseries.owner)
        bug = task.bug
        task_2 = self.factory.makeBugTask(
            target=self.factory.makeSourcePackage(distroseries=distroseries),
            bug=bug)
        task_2.transitionToStatus(status, distroseries.owner)
        cve_1 = self.getCVE()
        cve_2 = self.getCVE()
        bug.linkCVE(cve_1, distroseries.owner)
        bug.linkCVE(cve_2, distroseries.owner)
        return [task, task_2], (cve_1, cve_2)

    def cveGenerator(self):
        """A generator returning five CVEs cyclically."""
        NUM_CVES = 5
        cves = [
            self.factory.makeCVE('2000-%04i' % count)
            for count in range(NUM_CVES)]
        cve_index = 0
        while True:
            yield cves[cve_index]
            cve_index = (cve_index + 1) % NUM_CVES

    def test_render(self):
        # The rendered page contains all expected CVE links.
        html_data = self.view.render()
        cve_links = re.findall(
            r'<a style="text-decoration: none" '
            r'href="http://bugs.launchpad.dev/bugs/cve/\d{4}-\d{4}">'
            r'<img src="/@@/link" alt="" />'
            r'<span style="text-decoration: underline">CVE-\d{4}-\d{4}</span>'
            r'</a>',
            html_data)
        # We have two CVEs per bug, and one bug per bugtask status.
        expected = 2 * (
            len(RESOLVED_BUGTASK_STATUSES) + len(UNRESOLVED_BUGTASK_STATUSES))
        self.assertEqual(expected, len(cve_links))

    def test_open_resolved_cve_bugtasks(self):
        # The properties CVEReportView.open_cve_bugtasks and
        # CVEReportView.resolved_cve_bugtasks are lists of
        # BugTaskCve instances.
        for item in self.view.open_cve_bugtasks:
            self.assertIsInstance(item, BugTaskCve)
        for item in self.view.resolved_cve_bugtasks:
            self.assertIsInstance(item, BugTaskCve)

        open_bugs = [
            bugtaskcve.bug for bugtaskcve in self.view.open_cve_bugtasks]
        expected_open_bugs = [
            task.bug for task, task_2 in self.unresolved_bugtasks]
        self.assertEqual(expected_open_bugs, open_bugs)
        resolved_bugs = [
            bugtaskcve.bug for bugtaskcve in self.view.resolved_cve_bugtasks]
        expected_resolved_bugs = [
            task.bug for task, task_2 in self.resolved_bugtasks]
        self.assertEqual(expected_resolved_bugs, resolved_bugs)

        def unwrap_bugtask_listing_items(seq):
            return [
                [item1.bugtask, item2.bugtask] for item1, item2 in seq]

        open_bugtasks = [
            bugtaskcve.bugtasks
            for bugtaskcve in self.view.open_cve_bugtasks]
        open_bugtasks = unwrap_bugtask_listing_items(open_bugtasks)
        self.assertEqual(self.unresolved_bugtasks, open_bugtasks)
        resolved_bugtasks = [
            bugtaskcve.bugtasks
            for bugtaskcve in self.view.resolved_cve_bugtasks]
        resolved_bugtasks = unwrap_bugtask_listing_items(resolved_bugtasks)
        self.assertEqual(self.resolved_bugtasks, resolved_bugtasks)

        def get_cve_data_for_task(task):
            """Sort the CVEs for the given bug task by ID and return
            their display data."""
            cves = sorted(self.cves[task.bug], key=attrgetter('id'))
            return [
                {
                    'url': canonical_url(cve),
                    'displayname': cve.displayname,
                    }
                for cve in cves
                ]

        open_cves = [
            bugtaskcve.cves for bugtaskcve in self.view.open_cve_bugtasks]
        expected_open_cves = [
            get_cve_data_for_task(task)
            for task, task_2 in self.unresolved_bugtasks]
        self.assertEqual(expected_open_cves, open_cves)

        resolved_cves = [
            bugtaskcve.cves for bugtaskcve in self.view.resolved_cve_bugtasks]
        expected_resolved_cves = [
            get_cve_data_for_task(task)
            for task, task_2 in self.resolved_bugtasks]
        self.assertEqual(expected_resolved_cves, resolved_cves)

    def test_renderCVELinks(self):
        # renderCVELinks() takes a sequence of items with CVE related
        # data and returns an HTML representation with links to
        # Launchpad pages for the CVEs.
        result = self.view.renderCVELinks(
            [
                {
                    'displayname': 'CVE-2011-0123',
                    'url': 'http://bugs.launchpad.dev/bugs/cve/2011-0123',
                    },
                {
                    'displayname': 'CVE-2011-0456',
                    'url': 'http://bugs.launchpad.dev/bugs/cve/2011-0456',
                    },
                ])
        expected = (
            '<a style="text-decoration: none" '
            'href="http://bugs.launchpad.dev/bugs/cve/2011-0123">'
            '<img src="/@@/link" alt="" />'
            '<span style="text-decoration: underline">CVE-2011-0123</span>'
            '</a><br />\n'
            '<a style="text-decoration: none" '
            'href="http://bugs.launchpad.dev/bugs/cve/2011-0456">'
            '<img src="/@@/link" alt="" />'
            '<span style="text-decoration: underline">CVE-2011-0456</span>'
            '</a>')
        self.assertEqual(expected, result)
