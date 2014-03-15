# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for product views."""

__metaclass__ = type

from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


class TestProjectBranches(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestProjectBranches, self).setUp()
        self.project = self.factory.makeProject()
        self.product = self.factory.makeProduct(project=self.project)

    def test_has_branches_with_no_branches(self):
        # If there are no product branches on the project's products, then
        # has branches returns False.
        self.assertFalse(self.project.has_branches())

    def test_has_branches_with_branches(self):
        # If a product has a branch, then the product's project returns
        # true for has_branches.
        self.factory.makeProductBranch(product=self.product)
        self.assertTrue(self.project.has_branches())
