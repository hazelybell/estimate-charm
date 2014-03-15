# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type


from lp.bugs.browser.bugtarget import BugsPatchesView
from lp.bugs.browser.bugtask import (
    BugListingPortletStatsView,
    DISPLAY_BUG_STATUS_FOR_PATCHES,
    )
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.testing import (
    login,
    TestCaseWithFactory,
    )
from lp.testing.layers import LaunchpadFunctionalLayer


class TestBugTargetPatchCountBase(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestBugTargetPatchCountBase, self).setUp()
        login('foo.bar@canonical.com')
        self.product = self.factory.makeProduct()

    def makeBugWithPatch(self, status):
        bug = self.factory.makeBug(
            target=self.product, owner=self.product.owner)
        self.factory.makeBugAttachment(bug=bug, is_patch=True)
        bug.default_bugtask.transitionToStatus(status, user=bug.owner)


class TestBugTargetPatchView(TestBugTargetPatchCountBase):

    def test_status_of_bugs_with_patches_shown(self):
        # Bugs with patches that have the status FIXRELEASED, INVALID,
        # WONTFIX, UNKNOWN, EXPIRED are not shown in the +patches view; all
        # other bugs are shown.
        number_of_bugs_shown = 0
        for bugtask_status in DISPLAY_BUG_STATUS_FOR_PATCHES:
            if DISPLAY_BUG_STATUS_FOR_PATCHES[bugtask_status]:
                number_of_bugs_shown += 1
            self.makeBugWithPatch(bugtask_status)
            view = BugsPatchesView(self.product, LaunchpadTestRequest())
            batched_tasks = view.batchedPatchTasks()
            self.assertEqual(
                batched_tasks.batch.listlength, number_of_bugs_shown,
                "Unexpected number of bugs with patches displayed for status "
                "%s" % bugtask_status)


class TestBugListingPortletStatsView(TestBugTargetPatchCountBase):

    def test_bugs_with_patches_count(self):
        # Bugs with patches that have the status FIXRELEASED, INVALID,
        # WONTFIX, or UNKNOWN are not counted in
        # BugListingPortletStatsView.bugs_with_patches_count, bugs
        # with all other statuses are counted.
        number_of_bugs_shown = 0
        for bugtask_status in DISPLAY_BUG_STATUS_FOR_PATCHES:
            if DISPLAY_BUG_STATUS_FOR_PATCHES[bugtask_status]:
                number_of_bugs_shown += 1
            self.makeBugWithPatch(bugtask_status)
            view = BugListingPortletStatsView(
                self.product, LaunchpadTestRequest())
            self.assertEqual(
                view.bugs_with_patches_count, number_of_bugs_shown,
                "Unexpected number of bugs with patches displayed for status "
                "%s" % bugtask_status)
