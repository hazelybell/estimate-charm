# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for IBranchCloud provider."""

__metaclass__ = type

from datetime import (
    datetime,
    timedelta,
    )

import pytz
from storm.locals import Store
import transaction
from zope.component import getUtility

from lp.code.interfaces.branch import IBranchCloud
from lp.code.model.revision import RevisionCache
from lp.code.tests.helpers import (
    make_project_branch_with_revisions,
    remove_all_sample_data_branches,
    )
from lp.testing import (
    TestCaseWithFactory,
    time_counter,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestBranchCloud(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        remove_all_sample_data_branches()
        self._branch_cloud = getUtility(IBranchCloud)

    def getProductsWithInfo(self, num_products=None):
        """Get product cloud information."""
        # Since we use the slave store to get the information, we need to
        # commit the transaction to make the information visible to the slave.
        transaction.commit()
        cloud_info = self._branch_cloud.getProductsWithInfo(num_products)

        def add_utc(value):
            # Since Storm's Max function does not take into account the
            # type that it is aggregating, the last commit time is not
            # timezone-aware.  Whack the UTC timezone on it here for
            # easier comparing in the tests.
            return value.replace(tzinfo=pytz.UTC)

        return [
            (name, commits, authors, add_utc(last_commit))
            for name, commits, authors, last_commit in cloud_info]

    def makeBranch(self, product=None, last_commit_date=None, private=False,
                   revision_count=None):
        """Make a product branch with a particular last commit date"""
        if revision_count is None:
            revision_count = 5
        delta = timedelta(days=1)
        if last_commit_date is None:
            # By default we create revisions that are within the last 30 days.
            date_generator = time_counter(
                datetime.now(pytz.UTC) - timedelta(days=25), delta)
        else:
            start_date = last_commit_date - delta * (revision_count - 1)
            date_generator = time_counter(start_date, delta)
        branch = make_project_branch_with_revisions(
            self.factory, date_generator, product, private, revision_count)
        return branch

    def test_empty_with_no_branches(self):
        # getProductsWithInfo returns an empty result set if there are no
        # branches in the database.
        self.assertEqual([], self.getProductsWithInfo())

    def test_empty_products_not_counted(self):
        # getProductsWithInfo doesn't include products that don't have any
        # branches.
        #
        # Note that this is tested implicitly by test_empty_with_no_branches,
        # since there are such products in the sample data.
        self.factory.makeProduct()
        self.assertEqual([], self.getProductsWithInfo())

    def test_empty_branches_not_counted(self):
        # getProductsWithInfo doesn't consider branches that lack revision
        # data, 'empty branches', to contribute to the count of branches on a
        # product.
        self.factory.makeProductBranch()
        self.assertEqual([], self.getProductsWithInfo())

    def test_private_branches_not_counted(self):
        # getProductsWithInfo doesn't count private branches.
        self.makeBranch(private=True)
        self.assertEqual([], self.getProductsWithInfo())

    def test_revisions_counted(self):
        # getProductsWithInfo includes products that public revisions.
        last_commit_date = datetime.now(pytz.UTC) - timedelta(days=5)
        product = self.factory.makeProduct()
        self.makeBranch(product=product, last_commit_date=last_commit_date)
        self.assertEqual(
            [(product.name, 5, 1, last_commit_date)],
            self.getProductsWithInfo())

    def test_only_recent_revisions_counted(self):
        # If the revision cache has revisions for the project, but they are
        # over 30 days old, we don't count them.
        product = self.factory.makeProduct()
        date_generator = time_counter(
            datetime.now(pytz.UTC) - timedelta(days=33),
            delta=timedelta(days=2))
        store = Store.of(product)
        for i in range(4):
            revision = self.factory.makeRevision(
                revision_date=date_generator.next())
            cache = RevisionCache(revision)
            cache.product = product
            store.add(cache)
        self.assertEqual(
            [(product.name, 2, 2, revision.revision_date)],
            self.getProductsWithInfo())

    def test_sorted_by_commit_count(self):
        # getProductsWithInfo returns a result set sorted so that the products
        # with the most commits come first.
        product1 = self.factory.makeProduct()
        for i in range(3):
            self.makeBranch(product=product1)
        product2 = self.factory.makeProduct()
        for i in range(5):
            self.makeBranch(product=product2)
        self.assertEqual(
            [product2.name, product1.name],
            [name for name, commits, count, last_commit
             in self.getProductsWithInfo()])

    def test_limit(self):
        # If num_products is passed to getProductsWithInfo, it limits the
        # number of products in the result set. The products with the fewest
        # branches are discarded first.
        product1 = self.factory.makeProduct()
        for i in range(3):
            self.makeBranch(product=product1)
        product2 = self.factory.makeProduct()
        for i in range(5):
            self.makeBranch(product=product2)
        product3 = self.factory.makeProduct()
        for i in range(7):
            self.makeBranch(product=product3)
        self.assertEqual(
            [product3.name, product2.name],
            [name for name, commits, count, last_commit
             in self.getProductsWithInfo(num_products=2)])
