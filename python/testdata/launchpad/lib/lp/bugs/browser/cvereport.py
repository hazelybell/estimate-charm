# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Views to generate CVE reports (as in distro & distroseries/+cve pages)."""

__metaclass__ = type

__all__ = [
    'BugTaskCve',
    'CVEReportView',
    ]

from zope.component import getUtility

from lp.bugs.browser.bugtask import BugTaskListingItem
from lp.bugs.interfaces.bugtask import (
    IBugTaskSet,
    RESOLVED_BUGTASK_STATUSES,
    )
from lp.bugs.interfaces.bugtasksearch import BugTaskSearchParams
from lp.bugs.interfaces.cve import ICveSet
from lp.registry.interfaces.person import IPersonSet
from lp.services.helpers import shortlist
from lp.services.webapp import LaunchpadView
from lp.services.webapp.escaping import structured
from lp.services.webapp.publisher import canonical_url


class BugTaskCve:
    """An object that represents BugTasks and CVEs related to a single bug."""
    def __init__(self):
        self.bugtasks = []
        self.cves = []

    @property
    def bug(self):
        """Return the bug which this BugTaskCve represents."""
        # All the bugtasks we have should represent the same bug.
        assert self.bugtasks, "No bugtasks added before calling bug!"
        return self.bugtasks[0].bug


def get_cve_display_data(cve):
    """Return the data we need for display for the given CVE."""
    return {
        'displayname': cve.displayname,
        'url': canonical_url(cve),
        }

cve_link_template = (
    '<a style="text-decoration: none" href="%s">'
    '<img src="/@@/link" alt="" />'
    '<span style="text-decoration: underline">%s</span></a>')


class CVEReportView(LaunchpadView):
    """View that builds data to be displayed in CVE reports."""

    @property
    def page_title(self):
        return 'CVE reports for %s' % self.context.title

    def setContextForParams(self, params):
        """Update the search params for the context for a specific view."""
        raise NotImplementedError

    def initialize(self):
        """See `LaunchpadView`."""
        super(CVEReportView, self).initialize()
        search_params = BugTaskSearchParams(
            self.user, has_cve=True)
        bugtasks = shortlist(
            self.context.searchTasks(search_params),
            longest_expected=600)

        if not bugtasks:
            self.open_cve_bugtasks = []
            self.resolved_cve_bugtasks = []
            return

        bugtask_set = getUtility(IBugTaskSet)
        badge_properties = bugtask_set.getBugTaskBadgeProperties(bugtasks)
        people = bugtask_set.getBugTaskPeople(bugtasks)

        open_bugtaskcves = {}
        resolved_bugtaskcves = {}
        for bugtask in bugtasks:
            badges = badge_properties[bugtask]
            # Wrap the bugtask in a BugTaskListingItem, to avoid db
            # queries being issues when trying to render the badges.
            bugtask = BugTaskListingItem(
                bugtask,
                has_bug_branch=badges['has_branch'],
                has_specification=badges['has_specification'],
                has_patch=badges['has_patch'],
                tags=(),
                people=people)
            if bugtask.status in RESOLVED_BUGTASK_STATUSES:
                current_bugtaskcves = resolved_bugtaskcves
            else:
                current_bugtaskcves = open_bugtaskcves
            if bugtask.bug.id not in current_bugtaskcves:
                current_bugtaskcves[bugtask.bug.id] = BugTaskCve()
            current_bugtaskcves[bugtask.bug.id].bugtasks.append(bugtask)

        bugcves = getUtility(ICveSet).getBugCvesForBugTasks(
            bugtasks, get_cve_display_data)
        for bug, cve in bugcves:
            if bug.id in open_bugtaskcves:
                open_bugtaskcves[bug.id].cves.append(cve)
            if bug.id in resolved_bugtaskcves:
                resolved_bugtaskcves[bug.id].cves.append(cve)

        # Order the dictionary items by bug ID and then store only the
        # bugtaskcve objects.
        self.open_cve_bugtasks = [
            bugtaskcve for bug, bugtaskcve
            in sorted(open_bugtaskcves.items())]
        self.resolved_cve_bugtasks = [
            bugtaskcve for bug, bugtaskcve
            in sorted(resolved_bugtaskcves.items())]

        # The page contains links to the bug task assignees:
        # Pre-load the related Person and ValidPersonCache records
        assignee_ids = [task.assigneeID for task in bugtasks]
        list(getUtility(IPersonSet).getPrecachedPersonsFromIDs(
            assignee_ids, need_validity=True))

    def renderCVELinks(self, cves):
        """Render the CVE links related to the given bug.

        Doing this in a TAL expression is too inefficient for thousands
        of CVEs.
        """
        return '<br />\n'.join(
            structured(
                cve_link_template, cve['url'], cve['displayname']).escapedtext
            for cve in cves)
