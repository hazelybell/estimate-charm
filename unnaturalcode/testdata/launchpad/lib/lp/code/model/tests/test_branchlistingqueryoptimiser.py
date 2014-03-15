# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the branch listing query optimiser."""

__metaclass__ = type

from storm.store import Store
from zope.component import getUtility

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.code.enums import BranchType
from lp.code.interfaces.branch import IBranchListingQueryOptimiser
from lp.code.model.branchlistingqueryoptimiser import (
    BranchListingQueryOptimiser,
    )
from lp.code.tests.helpers import make_linked_package_branch
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


class TestBranchListingQueryOptimiser(TestCaseWithFactory):
    """Test that the utility is registered, and provides the interface."""

    layer = DatabaseFunctionalLayer

    def test_registered_correctly(self):
        # Check that the utility is correctly registered, and that what we get
        # back provides the interface fully.
        utility = getUtility(IBranchListingQueryOptimiser)
        self.assertProvides(utility, IBranchListingQueryOptimiser)


class TestGetProductSeriesForBranches(TestCaseWithFactory):
    """Test getting series associated with branches."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        # Log in as an admin as we are setting series branches, which is a
        # protected activity.
        super(TestGetProductSeriesForBranches, self).setUp(
            'admin@canonical.com')
        self.product = self.factory.makeProduct()
        self.branches = [
            self.factory.makeProductBranch(product=self.product)
            for x in range(3)]
        self.branch_ids = [branch.id for branch in self.branches]

    def assertSeriesBranches(self, expected, branch_ids=None):
        """Assert that the expected series are returned."""
        if branch_ids is None:
            branch_ids = self.branch_ids
        series = BranchListingQueryOptimiser.getProductSeriesForBranches(
            branch_ids)
        self.assertEqual(expected, list(series))

    def test_no_series_set(self):
        """If there are no series branches."""
        self.assertSeriesBranches([])

    def test_current_dev_focus(self):
        """A series with a branch associated is returned."""
        dev_focus = self.product.development_focus
        dev_focus.branch = self.branches[0]
        self.assertSeriesBranches([self.product.development_focus])

    def test_result_ordering(self):
        """Series are ordered alphabetically in the results."""
        gamma = self.product.newSeries(
            self.product.owner, "gamma", "summary", self.branches[0])
        beta = self.product.newSeries(
            self.product.owner, "beta", "summary", self.branches[1])
        alpha = self.product.newSeries(
            self.product.owner, "alpha", "summary", self.branches[2])
        self.assertSeriesBranches([alpha, beta, gamma])

    def test_multiple_series_for_single_branch(self):
        """A single branch can be assiciated with multiple series.

        Make sure that all the associated series get returned.
        """
        branch = self.branches[0]
        gamma = self.product.newSeries(
            self.product.owner, "gamma", "summary", branch)
        beta = self.product.newSeries(
            self.product.owner, "beta", "summary", branch)
        alpha = self.product.newSeries(
            self.product.owner, "alpha", "summary", branch)
        self.assertSeriesBranches([alpha, beta, gamma])

    def test_non_associated_series_not_returned(self):
        """Only series with associated branches are returned."""
        branch = self.branches[0]
        gamma = self.product.newSeries(
            self.product.owner, "gamma", "summary", branch)
        beta = self.product.newSeries(
            self.product.owner, "beta", "summary")
        self.assertSeriesBranches([gamma])

    def test_import_branches_also_linked(self):
        """Series with import branches are returned."""
        vcs_imports = getUtility(ILaunchpadCelebrities).vcs_imports
        branch = self.factory.makeProductBranch(
            owner=vcs_imports, product=self.product,
            branch_type=BranchType.IMPORTED)
        dev_focus = self.product.development_focus
        dev_focus.branch = branch
        self.assertSeriesBranches([dev_focus], [branch.id])


class TestGetOfficialSourcePackageLinksForBranches(TestCaseWithFactory):
    """Test getting official package links associated with branches."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        # Log in an admin as we are setting official branches, which is a
        # protected activity.
        super(TestGetOfficialSourcePackageLinksForBranches, self).setUp(
            'admin@canonical.com')

    def test_with_branches(self):
        # Test the selection of the links.
        # Make two package branches that we care about.
        b1 = make_linked_package_branch(self.factory)
        b2 = make_linked_package_branch(self.factory)
        # And two we don't.
        make_linked_package_branch(self.factory)
        make_linked_package_branch(self.factory)
        links = (BranchListingQueryOptimiser.
                 getOfficialSourcePackageLinksForBranches([b1.id, b2.id]))
        self.assertEqual(
            sorted([b1, b2]),
            sorted([link.branch for link in links]))

    def test_objects_loaded(self):
        # Traversing through the source package and the distribution should
        # not cause more queries.

        b1 = make_linked_package_branch(self.factory)
        store = Store.of(b1)
        # Constructing a distribution causes the "ubuntu" celebrity to be
        # created which hits the database. So load it now.
        store.flush()
        store.reset()
        getUtility(ILaunchpadCelebrities).ubuntu

        (link, ) = self.assertStatementCount(
            1, BranchListingQueryOptimiser.
            getOfficialSourcePackageLinksForBranches, [b1.id])
        # Accessing the source package doesn't hit the database.
        sp = self.assertStatementCount(0, getattr, link, "sourcepackage")
        # Getting the distribution from the source package doesn't hit the
        # database.
        self.assertStatementCount(0, getattr, sp, "distribution")
        # Nor does getting the path or displayname.
        self.assertStatementCount(0, getattr, sp, "displayname")
        self.assertStatementCount(0, getattr, sp, "path")
