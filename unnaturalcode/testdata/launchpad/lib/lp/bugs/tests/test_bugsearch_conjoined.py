# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test for the exclude_conjoined_tasks param for BugTaskSearchParams."""

__metaclass__ = type

__all__ = []

from storm.store import Store
from testtools.matchers import Equals
from zope.component import getUtility

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.bugs.interfaces.bugtask import (
    BugTaskStatus,
    IBugTaskSet,
    )
from lp.bugs.interfaces.bugtasksearch import BugTaskSearchParams
from lp.registry.interfaces.series import SeriesStatus
from lp.testing import (
    person_logged_in,
    StormStatementRecorder,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.matchers import HasQueryCount


class TestSearchBase(TestCaseWithFactory):
    """Tests of exclude_conjoined_tasks param."""

    def makeBug(self, milestone):
        bug = self.factory.makeBug(target=milestone.target)
        with person_logged_in(milestone.target.owner):
            bug.default_bugtask.transitionToMilestone(
                milestone, milestone.target.owner)
        return bug


class TestProjectExcludeConjoinedMasterSearch(TestSearchBase):
    """Tests of exclude_conjoined_tasks param for project milestones."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestProjectExcludeConjoinedMasterSearch, self).setUp()
        self.bugtask_set = getUtility(IBugTaskSet)
        self.product = self.factory.makeProduct()
        self.milestone = self.factory.makeMilestone(
            product=self.product, name='foo')
        self.bug_count = 2
        self.bugs = [
            self.makeBug(self.milestone)
            for i in range(self.bug_count)]
        self.params = BugTaskSearchParams(
            user=None, milestone=self.milestone, exclude_conjoined_tasks=True)

    def test_search_results_count_simple(self):
        # Verify number of results with no conjoined masters.
        self.assertEqual(
            self.bug_count,
            self.bugtask_set.search(self.params).count())

    def test_search_query_count(self):
        # Verify query count.
        Store.of(self.milestone).flush()
        with StormStatementRecorder() as recorder:
            list(self.bugtask_set.search(self.params))
        # 1 query for the tasks, 1 query for the product (target) eager
        # loading.
        self.assertThat(recorder, HasQueryCount(Equals(4)))

    def test_search_results_count_with_other_productseries_tasks(self):
        # Test with zero conjoined masters and bugtasks targeted to
        # productseries that are not the development focus.
        productseries = self.factory.makeProductSeries(product=self.product)
        extra_bugtasks = 0
        for bug in self.bugs:
            extra_bugtasks += 1
            bugtask = self.factory.makeBugTask(bug=bug, target=productseries)
            with person_logged_in(self.product.owner):
                bugtask.transitionToMilestone(
                    self.milestone, self.product.owner)
            self.assertEqual(
                self.bug_count + extra_bugtasks,
                self.bugtask_set.search(self.params).count())

    def test_search_results_count_with_conjoined_masters(self):
        # Test with increasing numbers of conjoined masters.
        # The conjoined masters will exclude the conjoined slaves from
        # the results.
        tasks = list(self.bugtask_set.search(self.params))
        for bug in self.bugs:
            # The product bugtask is in the results before the conjoined
            # master is added.
            self.assertIn(
                (bug.id, self.product),
                [(task.bug.id, task.product) for task in tasks])
            self.factory.makeBugTask(
                bug=bug, target=self.product.development_focus)
            tasks = list(self.bugtask_set.search(self.params))
            # The product bugtask is excluded from the results.
            self.assertEqual(self.bug_count, len(tasks))
            self.assertNotIn(
                (bug.id, self.product),
                [(task.bug.id, task.product) for task in tasks])

    def test_search_results_count_with_wontfix_conjoined_masters(self):
        # Test that conjoined master bugtasks in the WONTFIX status
        # don't cause the bug to be excluded.
        masters = [
            self.factory.makeBugTask(
                bug=bug, target=self.product.development_focus)
            for bug in self.bugs]
        tasks = list(self.bugtask_set.search(self.params))
        wontfix_masters_count = 0
        for bugtask in masters:
            wontfix_masters_count += 1
            self.assertNotIn(
                (bugtask.bug.id, self.product),
                [(task.bug.id, task.product) for task in tasks])
            with person_logged_in(self.product.owner):
                bugtask.transitionToStatus(
                    BugTaskStatus.WONTFIX, self.product.owner)
            tasks = list(self.bugtask_set.search(self.params))
            self.assertEqual(self.bug_count + wontfix_masters_count,
                             len(tasks))
            self.assertIn(
                (bugtask.bug.id, self.product),
                [(task.bug.id, task.product) for task in tasks])


class TestProjectGroupExcludeConjoinedMasterSearch(TestSearchBase):
    """Tests of exclude_conjoined_tasks param for project group milestones."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestProjectGroupExcludeConjoinedMasterSearch, self).setUp()
        self.bugtask_set = getUtility(IBugTaskSet)
        self.projectgroup = self.factory.makeProject()
        self.bug_count = 2
        self.bug_products = {}
        for i in range(self.bug_count):
            product = self.factory.makeProduct(project=self.projectgroup)
            product_milestone = self.factory.makeMilestone(
                product=product, name='foo')
            bug = self.makeBug(product_milestone)
            self.bug_products[bug] = product
        self.milestone = self.projectgroup.getMilestone('foo')
        self.params = BugTaskSearchParams(
            user=None, milestone=self.milestone, exclude_conjoined_tasks=True)

    def test_search_results_count_simple(self):
        # Verify number of results with no conjoined masters.
        self.assertEqual(
            self.bug_count,
            self.bugtask_set.search(self.params).count())

    def test_search_query_count(self):
        # Verify query count.
        Store.of(self.projectgroup).flush()
        with StormStatementRecorder() as recorder:
            list(self.bugtask_set.search(self.params))
        # 1 query for the tasks, 1 query for the product (target) eager
        # loading.
        self.assertThat(recorder, HasQueryCount(Equals(4)))

    def test_search_results_count_with_other_productseries_tasks(self):
        # Test with zero conjoined masters and bugtasks targeted to
        # productseries that are not the development focus.
        extra_bugtasks = 0
        for bug, product in self.bug_products.items():
            extra_bugtasks += 1
            productseries = self.factory.makeProductSeries(product=product)
            bugtask = self.factory.makeBugTask(bug=bug, target=productseries)
            with person_logged_in(product.owner):
                bugtask.transitionToMilestone(
                    product.getMilestone(self.milestone.name), product.owner)
            self.assertEqual(
                self.bug_count + extra_bugtasks,
                self.bugtask_set.search(self.params).count())

    def test_search_results_count_with_conjoined_masters(self):
        # Test with increasing numbers of conjoined masters.
        tasks = list(self.bugtask_set.search(self.params))
        for bug, product in self.bug_products.items():
            self.assertIn(
                (bug.id, product),
                [(task.bug.id, task.product) for task in tasks])
            self.factory.makeBugTask(
                bug=bug, target=product.development_focus)
            tasks = list(self.bugtask_set.search(self.params))
            self.assertEqual(
                self.bug_count,
                self.bugtask_set.search(self.params).count())
            self.assertNotIn(
                (bug.id, product),
                [(task.bug.id, task.product) for task in tasks])

    def test_search_results_count_with_irrelevant_conjoined_masters(self):
        # Verify that a conjoined master in one project of the project
        # group doesn't cause a bugtask on another project in the group
        # to be excluded from the project group milestone's bugs.
        extra_bugtasks = 0
        for bug, product in self.bug_products.items():
            extra_bugtasks += 1
            other_product = self.factory.makeProduct(
                project=self.projectgroup)
            # Create a new milestone with the same name.
            other_product_milestone = self.factory.makeMilestone(
                product=other_product,
                name=bug.default_bugtask.milestone.name)
            # Add bugtask on the new product and select the milestone.
            other_product_bugtask = self.factory.makeBugTask(
                bug=bug, target=other_product)
            with person_logged_in(other_product.owner):
                other_product_bugtask.transitionToMilestone(
                    other_product_milestone, other_product.owner)
            # Add conjoined master for the milestone on the new product.
            self.factory.makeBugTask(
                bug=bug, target=other_product.development_focus)
            # The bug count should not change, since we are just adding
            # bugtasks on existing bugs.
            self.assertEqual(
                self.bug_count + extra_bugtasks,
                self.bugtask_set.search(self.params).count())

    def test_search_results_count_with_wontfix_conjoined_masters(self):
        # Test that conjoined master bugtasks in the WONTFIX status
        # don't cause the bug to be excluded.
        masters = [
            self.factory.makeBugTask(
                bug=bug, target=product.development_focus)
            for bug, product in self.bug_products.items()]
        unexcluded_count = 0
        for bugtask in masters:
            unexcluded_count += 1
            with person_logged_in(product.owner):
                bugtask.transitionToStatus(
                    BugTaskStatus.WONTFIX, bugtask.target.owner)
            self.assertEqual(
                self.bug_count + unexcluded_count,
                self.bugtask_set.search(self.params).count())


class TestDistributionExcludeConjoinedMasterSearch(TestSearchBase):
    """Tests of exclude_conjoined_tasks param for distribution milestones."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestDistributionExcludeConjoinedMasterSearch, self).setUp()
        self.bugtask_set = getUtility(IBugTaskSet)
        self.distro = getUtility(ILaunchpadCelebrities).ubuntu
        self.milestone = self.factory.makeMilestone(
            distribution=self.distro, name='foo')
        self.bug_count = 2
        self.bugs = [
            self.makeBug(self.milestone)
            for i in range(self.bug_count)]
        self.params = BugTaskSearchParams(
            user=None, milestone=self.milestone, exclude_conjoined_tasks=True)

    def test_search_results_count_simple(self):
        # Verify number of results with no conjoined masters.
        self.assertEqual(
            self.bug_count,
            self.bugtask_set.search(self.params).count())

    def test_search_query_count(self):
        # Verify query count.
        # 1. Query all the distroseries to determine the distro's
        #    currentseries.
        # 2. Query the bugtasks.
        Store.of(self.milestone).flush()
        with StormStatementRecorder() as recorder:
            list(self.bugtask_set.search(self.params))
        self.assertThat(recorder, HasQueryCount(Equals(4)))

    def test_search_results_count_with_other_productseries_tasks(self):
        # Test with zero conjoined masters and bugtasks targeted to
        # productseries that are not the development focus.
        distroseries = self.factory.makeDistroSeries(
            distribution=self.distro, status=SeriesStatus.SUPPORTED)
        extra_bugtasks = 0
        for bug in self.bugs:
            extra_bugtasks += 1
            bugtask = self.factory.makeBugTask(bug=bug, target=distroseries)
            with person_logged_in(self.distro.owner):
                bugtask.transitionToMilestone(
                    self.milestone, self.distro.owner)
            self.assertEqual(
                self.bug_count + extra_bugtasks,
                self.bugtask_set.search(self.params).count())

    def test_search_results_count_with_conjoined_masters(self):
        # Test with increasing numbers of conjoined masters.
        tasks = list(self.bugtask_set.search(self.params))
        for bug in self.bugs:
            # The distro bugtask is in the results before the conjoined
            # master is added.
            self.assertIn(
                (bug.id, self.distro),
                [(task.bug.id, task.distribution) for task in tasks])
            self.factory.makeBugTask(
                bug=bug, target=self.distro.currentseries)
            tasks = list(self.bugtask_set.search(self.params))
            # The product bugtask is excluded from the results.
            self.assertEqual(self.bug_count, len(tasks))
            self.assertNotIn(
                (bug.id, self.distro),
                [(task.bug.id, task.distribution) for task in tasks])

    def test_search_results_count_with_wontfix_conjoined_masters(self):
        # Test that conjoined master bugtasks in the WONTFIX status
        # don't cause the bug to be excluded.
        masters = [
            self.factory.makeBugTask(
                bug=bug, target=self.distro.currentseries)
            for bug in self.bugs]
        wontfix_masters_count = 0
        tasks = list(self.bugtask_set.search(self.params))
        for bugtask in masters:
            wontfix_masters_count += 1
            # The distro bugtask is still excluded by the conjoined
            # master.
            self.assertNotIn(
                (bugtask.bug.id, self.distro),
                [(task.bug.id, task.distribution) for task in tasks])
            with person_logged_in(self.distro.owner):
                bugtask.transitionToStatus(
                    BugTaskStatus.WONTFIX, self.distro.owner)
            tasks = list(self.bugtask_set.search(self.params))
            self.assertEqual(
                self.bug_count + wontfix_masters_count,
                self.bugtask_set.search(self.params).count())
            # The distro bugtask is no longer excluded by the conjoined
            # master, since its status is WONTFIX.
            self.assertIn(
                (bugtask.bug.id, self.distro),
                [(task.bug.id, task.distribution) for task in tasks])
