# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the code test helpers found in helpers.py."""

__metaclass__ = type

from datetime import (
    datetime,
    timedelta,
    )

import pytz
from zope.component import getUtility

from lp.code.interfaces.branchcollection import IAllBranches
from lp.code.tests.helpers import make_project_cloud_data
from lp.registry.interfaces.product import IProductSet
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


class TestMakeProjectCloudData(TestCaseWithFactory):
    # Make sure that make_project_cloud_data works.

    layer = DatabaseFunctionalLayer

    def test_single_project(self):
        # Make a single project with one commit from one person.
        now = datetime.now(pytz.UTC)
        commit_time = now - timedelta(days=2)
        make_project_cloud_data(self.factory, [
                ('fooix', 1, 1, commit_time),
                ])
        # Make sure we have a new project called fooix.
        fooix = getUtility(IProductSet).getByName('fooix')
        self.assertIsNot(None, fooix)
        # There should be one branch with one commit.
        [branch] = list(
            getUtility(IAllBranches).inProduct(fooix).getBranches(
                eager_load=False))
        self.assertEqual(1, branch.revision_count)
        self.assertEqual(commit_time, branch.getTipRevision().revision_date)
