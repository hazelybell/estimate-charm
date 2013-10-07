# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from datetime import (
    datetime,
    timedelta,
    )
from operator import attrgetter

from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.blueprints.browser.person_upcomingwork import (
    GenericWorkItem,
    getWorkItemsDueBefore,
    WorkItemContainer,
    )
from lp.blueprints.enums import (
    SpecificationPriority,
    SpecificationWorkItemStatus,
    )
from lp.testing import (
    anonymous_logged_in,
    BrowserTestCase,
    TestCase,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.pages import (
    extract_text,
    find_tag_by_id,
    find_tags_by_class,
    )
from lp.testing.views import create_initialized_view


class Test_getWorkItemsDueBefore(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(Test_getWorkItemsDueBefore, self).setUp()
        self.today = datetime.today().date()
        current_milestone = self.factory.makeMilestone(
            dateexpected=self.today)
        self.current_milestone = current_milestone
        self.future_milestone = self.factory.makeMilestone(
            product=current_milestone.product,
            dateexpected=datetime(2060, 1, 1))
        self.team = self.factory.makeTeam()

    def test_basic(self):
        spec = self.factory.makeSpecification(
            product=self.current_milestone.product,
            assignee=self.team.teamowner, milestone=self.current_milestone)
        workitem = self.factory.makeSpecificationWorkItem(
            title=u'workitem 1', specification=spec)
        bugtask = self.factory.makeBug(
            milestone=self.current_milestone).bugtasks[0]
        removeSecurityProxy(bugtask).assignee = self.team.teamowner

        workitems = getWorkItemsDueBefore(
            self.team, self.current_milestone.dateexpected, user=None)

        self.assertEqual(
            [self.current_milestone.dateexpected], workitems.keys())
        containers = workitems[self.current_milestone.dateexpected]
        # We have one container for the work item from the spec and another
        # one for the bugtask.
        self.assertEqual(2, len(containers))
        [workitem_container, bugtask_container] = containers

        self.assertEqual(1, len(bugtask_container.items))
        self.assertEqual(bugtask, bugtask_container.items[0].actual_workitem)

        self.assertEqual(1, len(workitem_container.items))
        self.assertEqual(
            workitem, workitem_container.items[0].actual_workitem)

    def test_foreign_container(self):
        # This spec is targeted to a person who's not a member of our team, so
        # only those workitems that are explicitly assigned to a member of our
        # team will be returned.
        spec = self.factory.makeSpecification(
            product=self.current_milestone.product,
            milestone=self.current_milestone,
            assignee=self.factory.makePerson())
        self.factory.makeSpecificationWorkItem(
            title=u'workitem 1', specification=spec)
        workitem = self.factory.makeSpecificationWorkItem(
            title=u'workitem 2', specification=spec,
            assignee=self.team.teamowner)

        workitems = getWorkItemsDueBefore(
            self.team, self.current_milestone.dateexpected, user=None)

        self.assertEqual(
            [self.current_milestone.dateexpected], workitems.keys())
        containers = workitems[self.current_milestone.dateexpected]
        self.assertEqual(1, len(containers))
        [container] = containers
        self.assertEqual(1, len(container.items))
        self.assertEqual(workitem, container.items[0].actual_workitem)

    def test_future_container(self):
        spec = self.factory.makeSpecification(
            product=self.current_milestone.product,
            assignee=self.team.teamowner)
        # This workitem is targeted to a future milestone so it won't be in
        # our results below.
        self.factory.makeSpecificationWorkItem(
            title=u'workitem 1', specification=spec,
            milestone=self.future_milestone)
        current_wi = self.factory.makeSpecificationWorkItem(
            title=u'workitem 2', specification=spec,
            milestone=self.current_milestone)

        workitems = getWorkItemsDueBefore(
            self.team, self.current_milestone.dateexpected, user=None)

        self.assertEqual(
            [self.current_milestone.dateexpected], workitems.keys())
        containers = workitems[self.current_milestone.dateexpected]
        self.assertEqual(1, len(containers))
        [container] = containers
        self.assertEqual(1, len(container.items))
        self.assertEqual(current_wi, container.items[0].actual_workitem)

    def test_multiple_milestone_separation(self):
        # A single blueprint with workitems targetted to multiple
        # milestones is processed so that the same blueprint appears
        # in both with only the relevant work items.
        spec = self.factory.makeSpecification(
            product=self.current_milestone.product,
            assignee=self.team.teamowner)
        current_workitem = self.factory.makeSpecificationWorkItem(
            title=u'workitem 1', specification=spec,
            milestone=self.current_milestone)
        future_workitem = self.factory.makeSpecificationWorkItem(
            title=u'workitem 2', specification=spec,
            milestone=self.future_milestone)

        workitems = getWorkItemsDueBefore(
            self.team, self.future_milestone.dateexpected, user=None)

        # Both milestone dates are present in the returned results.
        self.assertContentEqual(
            [self.current_milestone.dateexpected,
             self.future_milestone.dateexpected],
            workitems.keys())

        # Current milestone date has a single specification
        # with only the matching work item.
        containers_current = workitems[self.current_milestone.dateexpected]
        self.assertContentEqual(
            [spec], [container.spec for container in containers_current])
        self.assertContentEqual(
            [current_workitem],
            [item.actual_workitem for item in containers_current[0].items])

        # Future milestone date has the same specification
        # containing only the work item targetted to future.
        containers_future = workitems[self.future_milestone.dateexpected]
        self.assertContentEqual(
            [spec],
            [container.spec for container in containers_future])
        self.assertContentEqual(
            [future_workitem],
            [item.actual_workitem for item in containers_future[0].items])


class TestGenericWorkItem(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestGenericWorkItem, self).setUp()
        today = datetime.today().date()
        self.milestone = self.factory.makeMilestone(dateexpected=today)

    def test_from_bugtask(self):
        bugtask = self.factory.makeBug(milestone=self.milestone).bugtasks[0]
        workitem = GenericWorkItem.from_bugtask(bugtask)
        self.assertEqual(workitem.assignee, bugtask.assignee)
        self.assertEqual(workitem.status, bugtask.status)
        self.assertEqual(workitem.priority, bugtask.importance)
        self.assertEqual(workitem.target, bugtask.target)
        self.assertEqual(workitem.title, bugtask.bug.description)
        self.assertEqual(workitem.actual_workitem, bugtask)

    def test_from_workitem(self):
        workitem = self.factory.makeSpecificationWorkItem(
            milestone=self.milestone)
        generic_wi = GenericWorkItem.from_workitem(workitem)
        self.assertEqual(generic_wi.assignee, workitem.assignee)
        self.assertEqual(generic_wi.status, workitem.status)
        self.assertEqual(generic_wi.priority, workitem.specification.priority)
        self.assertEqual(generic_wi.target, workitem.specification.target)
        self.assertEqual(generic_wi.title, workitem.title)
        self.assertEqual(generic_wi.actual_workitem, workitem)


class TestWorkItemContainer(TestCase):

    class MockWorkItem:

        def __init__(self, is_complete, is_postponed):
            self.is_complete = is_complete

            if is_postponed:
                self.status = SpecificationWorkItemStatus.POSTPONED
            else:
                self.status = None

    def test_percent_done_or_postponed(self):
        container = WorkItemContainer()
        container.append(self.MockWorkItem(True, False))
        container.append(self.MockWorkItem(False, False))
        container.append(self.MockWorkItem(False, True))
        self.assertEqual('67', container.percent_done_or_postponed)

    def test_has_incomplete_work(self):
        # If there are incomplete work items,
        # WorkItemContainer.has_incomplete_work will return True.
        container = WorkItemContainer()
        item = self.MockWorkItem(False, False)
        container.append(item)
        self.assertTrue(container.has_incomplete_work)
        item.is_complete = True
        self.assertFalse(container.has_incomplete_work)
        item.status = SpecificationWorkItemStatus.POSTPONED
        self.assertFalse(container.has_incomplete_work)
        item.is_complete = False
        self.assertFalse(container.has_incomplete_work)


class TestPersonUpcomingWork(BrowserTestCase):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestPersonUpcomingWork, self).setUp()
        self.today = datetime.today().date()
        self.tomorrow = self.today + timedelta(days=1)
        self.today_milestone = self.factory.makeMilestone(
            dateexpected=self.today)
        self.tomorrow_milestone = self.factory.makeMilestone(
            dateexpected=self.tomorrow)
        self.team = self.factory.makeTeam()

    def test_basic_for_team(self):
        """Check that the page shows the bugs/work items assigned to members
        of a team.
        """
        workitem1 = self.factory.makeSpecificationWorkItem(
            assignee=self.team.teamowner, milestone=self.today_milestone)
        workitem2 = self.factory.makeSpecificationWorkItem(
            assignee=self.team.teamowner, milestone=self.tomorrow_milestone)
        bugtask1 = self.factory.makeBug(
            milestone=self.today_milestone).bugtasks[0]
        bugtask2 = self.factory.makeBug(
            milestone=self.tomorrow_milestone).bugtasks[0]
        for bugtask in [bugtask1, bugtask2]:
            removeSecurityProxy(bugtask).assignee = self.team.teamowner

        browser = self.getViewBrowser(
            self.team, view_name='+upcomingwork', no_login=True)

        # Check that the two work items and bugtasks created above are shown
        # and grouped under the appropriate milestone date.
        groups = find_tags_by_class(browser.contents, 'workitems-group')
        self.assertEqual(2, len(groups))
        todays_group = extract_text(groups[0])
        tomorrows_group = extract_text(groups[1])
        self.assertStartsWith(
            todays_group, 'Work items due in %s' % self.today)
        self.assertIn(workitem1.title, todays_group)
        with anonymous_logged_in():
            self.assertIn(bugtask1.bug.title, todays_group)

        self.assertStartsWith(
            tomorrows_group, 'Work items due in %s' % self.tomorrow)
        self.assertIn(workitem2.title, tomorrows_group)
        with anonymous_logged_in():
            self.assertIn(bugtask2.bug.title, tomorrows_group)

    def test_no_xss_on_workitem_title(self):
        self.factory.makeSpecificationWorkItem(
            title=u"<script>window.alert('XSS')</script>",
            assignee=self.team.teamowner, milestone=self.today_milestone)

        browser = self.getViewBrowser(
            self.team, view_name='+upcomingwork', no_login=True)

        groups = find_tags_by_class(browser.contents, 'collapsible-body')
        self.assertEqual(1, len(groups))
        tbody = groups[0]
        title_td = tbody.findChildren('td')[0]
        self.assertEqual(
            "<td>\n<span>&lt;script&gt;window.alert('XSS')&lt;/script&gt;"
            "</span>\n</td>", str(title_td))

    def test_overall_progressbar(self):
        """Check that the per-date progress bar is present."""
        # Create two work items on separate specs. One of them is done and the
        # other is in progress.
        self.factory.makeSpecificationWorkItem(
            assignee=self.team.teamowner, milestone=self.today_milestone,
            status=SpecificationWorkItemStatus.DONE)
        self.factory.makeSpecificationWorkItem(
            assignee=self.team.teamowner, milestone=self.today_milestone,
            status=SpecificationWorkItemStatus.INPROGRESS)

        browser = self.getViewBrowser(
            self.team, view_name='+upcomingwork', no_login=True)

        # The progress bar for the due date of today_milestone will show that
        # 50% of the work is done (1 out of 2 work items).
        progressbar = find_tag_by_id(browser.contents, 'progressbar_0')
        self.assertEqual('50%', progressbar.get('width'))

    def test_container_progressbar(self):
        """Check that the per-blueprint progress bar is present."""
        # Create two work items on separate specs. One of them is done and the
        # other is in progress. Here we create the specs explicitly, using
        # different priorities to force spec1 to show up first on the page.
        spec1 = self.factory.makeSpecification(
            product=self.today_milestone.product,
            priority=SpecificationPriority.HIGH)
        spec2 = self.factory.makeSpecification(
            product=self.today_milestone.product,
            priority=SpecificationPriority.LOW)
        spec3 = self.factory.makeSpecification(
            product=self.today_milestone.product,
            priority=SpecificationPriority.LOW)
        self.factory.makeSpecificationWorkItem(
            specification=spec1, assignee=self.team.teamowner,
            milestone=self.today_milestone,
            status=SpecificationWorkItemStatus.DONE)
        self.factory.makeSpecificationWorkItem(
            specification=spec2, assignee=self.team.teamowner,
            milestone=self.today_milestone,
            status=SpecificationWorkItemStatus.INPROGRESS)
        self.factory.makeSpecificationWorkItem(
            specification=spec3, assignee=self.team.teamowner,
            milestone=self.today_milestone,
            status=SpecificationWorkItemStatus.POSTPONED)

        browser = self.getViewBrowser(
            self.team, view_name='+upcomingwork', no_login=True)

        # The progress bar of the first blueprint will be complete as the sole
        # work item there is done, while the other is going to be empty as the
        # sole work item is still in progress.
        container1_progressbar = find_tag_by_id(
            browser.contents, 'container_progressbar_0')
        container2_progressbar = find_tag_by_id(
            browser.contents, 'container_progressbar_1')
        container3_progressbar = find_tag_by_id(
            browser.contents, 'container_progressbar_2')
        self.assertEqual('100%', container1_progressbar.get('width'))
        self.assertEqual('0%', container2_progressbar.get('width'))
        self.assertEqual('100%', container3_progressbar.get('width'))

    def test_basic_for_person(self):
        """Check that the page shows the bugs/work items assigned to a person.
        """
        person = self.factory.makePerson()
        workitem = self.factory.makeSpecificationWorkItem(
            assignee=person, milestone=self.today_milestone)
        bugtask = self.factory.makeBug(
            milestone=self.tomorrow_milestone).bugtasks[0]
        removeSecurityProxy(bugtask).assignee = person

        browser = self.getViewBrowser(
            person, view_name='+upcomingwork', no_login=True)

        # Check that the two work items created above are shown and grouped
        # under the appropriate milestone date.
        groups = find_tags_by_class(browser.contents, 'workitems-group')
        self.assertEqual(2, len(groups))
        todays_group = extract_text(groups[0])
        tomorrows_group = extract_text(groups[1])
        self.assertStartsWith(
            todays_group, 'Work items due in %s' % self.today)
        self.assertIn(workitem.title, todays_group)

        self.assertStartsWith(
            tomorrows_group, 'Work items due in %s' % self.tomorrow)
        with anonymous_logged_in():
            self.assertIn(bugtask.bug.title, tomorrows_group)

    def test_non_public_specifications(self):
        """Work items for non-public specs are filtered correctly."""
        person = self.factory.makePerson()
        proprietary_spec = self.factory.makeSpecification(
            information_type=InformationType.PROPRIETARY)
        today_milestone = self.factory.makeMilestone(
            dateexpected=self.today, product=proprietary_spec.product)
        public_workitem = self.factory.makeSpecificationWorkItem(
            assignee=person, milestone=today_milestone)
        proprietary_workitem = self.factory.makeSpecificationWorkItem(
            assignee=person, milestone=today_milestone,
            specification=proprietary_spec)
        browser = self.getViewBrowser(
            person, view_name='+upcomingwork')
        self.assertIn(public_workitem.specification.name, browser.contents)
        self.assertNotIn(proprietary_workitem.specification.name,
                         browser.contents)
        browser = self.getViewBrowser(
            person, view_name='+upcomingwork',
            user=proprietary_workitem.specification.product.owner)
        self.assertIn(proprietary_workitem.specification.name,
                      browser.contents)


class TestPersonUpcomingWorkView(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestPersonUpcomingWorkView, self).setUp()
        self.today = datetime.today().date()
        self.tomorrow = self.today + timedelta(days=1)
        self.today_milestone = self.factory.makeMilestone(
            dateexpected=self.today)
        self.tomorrow_milestone = self.factory.makeMilestone(
            dateexpected=self.tomorrow)
        self.team = self.factory.makeTeam()

    def test_workitem_counts(self):
        self.factory.makeSpecificationWorkItem(
            assignee=self.team.teamowner, milestone=self.today_milestone)
        self.factory.makeSpecificationWorkItem(
            assignee=self.team.teamowner, milestone=self.today_milestone)
        self.factory.makeSpecificationWorkItem(
            assignee=self.team.teamowner, milestone=self.tomorrow_milestone)

        view = create_initialized_view(self.team, '+upcomingwork')
        self.assertEqual(2, view.workitem_counts[self.today])
        self.assertEqual(1, view.workitem_counts[self.tomorrow])

    def test_bugtask_counts(self):
        bugtask1 = self.factory.makeBug(
            milestone=self.today_milestone).bugtasks[0]
        bugtask2 = self.factory.makeBug(
            milestone=self.tomorrow_milestone).bugtasks[0]
        bugtask3 = self.factory.makeBug(
            milestone=self.tomorrow_milestone).bugtasks[0]
        for bugtask in [bugtask1, bugtask2, bugtask3]:
            removeSecurityProxy(bugtask).assignee = self.team.teamowner

        view = create_initialized_view(self.team, '+upcomingwork')
        self.assertEqual(1, view.bugtask_counts[self.today])
        self.assertEqual(2, view.bugtask_counts[self.tomorrow])

    def test_milestones_per_date(self):
        another_milestone_due_today = self.factory.makeMilestone(
            dateexpected=self.today)
        self.factory.makeSpecificationWorkItem(
            assignee=self.team.teamowner, milestone=self.today_milestone)
        self.factory.makeSpecificationWorkItem(
            assignee=self.team.teamowner,
            milestone=another_milestone_due_today)
        self.factory.makeSpecificationWorkItem(
            assignee=self.team.teamowner, milestone=self.tomorrow_milestone)

        view = create_initialized_view(self.team, '+upcomingwork')
        self.assertEqual(
            sorted([self.today_milestone, another_milestone_due_today],
                   key=attrgetter('displayname')),
            view.milestones_per_date[self.today])
        self.assertEqual(
            [self.tomorrow_milestone],
            view.milestones_per_date[self.tomorrow])

    def test_work_item_containers_are_sorted_by_date(self):
        self.factory.makeSpecificationWorkItem(
            assignee=self.team.teamowner, milestone=self.today_milestone)
        self.factory.makeSpecificationWorkItem(
            assignee=self.team.teamowner, milestone=self.tomorrow_milestone)

        view = create_initialized_view(self.team, '+upcomingwork')
        self.assertEqual(2, len(view.work_item_containers))
        self.assertEqual(
            [self.today, self.tomorrow],
            [date for date, containers in view.work_item_containers])
