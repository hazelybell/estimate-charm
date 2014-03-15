# Copyright 2011-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for BugTaskSet."""

__metaclass__ = type

from zope.component import getUtility

from lp.bugs.interfaces.bug import IBugSet
from lp.bugs.interfaces.bugtask import IBugTaskSet
from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.product import IProductSet
from lp.services.webapp.interfaces import ILaunchBag
from lp.testing import (
    login,
    TestCase,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestCountsForProducts(TestCase):
    """Test BugTaskSet.getOpenBugTasksPerProduct"""

    layer = DatabaseFunctionalLayer

    def test_open_product_counts(self):
        # IBugTaskSet.getOpenBugTasksPerProduct() will return a dictionary
        # of product_id:count entries for bugs in an open status that
        # the user given as a parameter is allowed to see. If a product,
        # such as id=3 does not have any open bugs, it will not appear
        # in the result.
        launchbag = getUtility(ILaunchBag)
        login('foo.bar@canonical.com')
        foobar = launchbag.user

        productset = getUtility(IProductSet)
        products = [productset.get(id) for id in (3, 5, 20)]
        sample_person = getUtility(IPersonSet).getByEmail('test@canonical.com')
        bugtask_counts = getUtility(IBugTaskSet).getOpenBugTasksPerProduct(
            sample_person, products)
        res = sorted(bugtask_counts.items())
        self.assertEqual(
            'product_id=%d count=%d' % tuple(res[0]),
            'product_id=5 count=1')
        self.assertEqual(
            'product_id=%d count=%d' % tuple(res[1]),
            'product_id=20 count=2')

        # A Launchpad admin will get a higher count for the product with id=20
        # because he can see the private bug.
        bugtask_counts = getUtility(IBugTaskSet).getOpenBugTasksPerProduct(
            foobar, products)
        res = sorted(bugtask_counts.items())
        self.assertEqual(
            'product_id=%d count=%d' % tuple(res[0]),
            'product_id=5 count=1')
        self.assertEqual(
            'product_id=%d count=%d' % tuple(res[1]),
            'product_id=20 count=3')

        # Someone subscribed to the private bug on the product with id=20
        # will also have it added to the count.
        karl = getUtility(IPersonSet).getByName('karl')
        bugtask_counts = getUtility(IBugTaskSet).getOpenBugTasksPerProduct(
            karl, products)
        res = sorted(bugtask_counts.items())
        self.assertEqual(
            'product_id=%d count=%d' % tuple(res[0]),
            'product_id=5 count=1')
        self.assertEqual(
            'product_id=%d count=%d' % tuple(res[1]),
            'product_id=20 count=3')


class TestSortingBugTasks(TestCase):
    """Bug tasks need to sort in a very particular order."""

    layer = DatabaseFunctionalLayer

    def test_sortingorder(self):
        """We want product tasks, then ubuntu, then distro-related.

        In the distro-related tasks we want a distribution-task first, then
        distroseries-tasks for that same distribution. The distroseries tasks
        should be sorted by distroseries version.
        """
        login('foo.bar@canonical.com')
        bug_one = getUtility(IBugSet).get(1)
        tasks = bug_one.bugtasks
        task_names = [task.bugtargetdisplayname for task in tasks]
        self.assertEqual(task_names, [
            u'Mozilla Firefox',
            'mozilla-firefox (Ubuntu)',
            'mozilla-firefox (Debian)',
        ])
