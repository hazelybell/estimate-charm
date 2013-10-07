# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from launchpadlib.testing.helpers import salgado_with_full_permissions
import transaction

from lp.testing import TestCaseWithFactory
from lp.testing.layers import AppServerLayer


class TestLaunchpadLib(TestCaseWithFactory):
    """Tests for the launchpadlib client for the REST API."""

    layer = AppServerLayer

    def setUp(self):
        super(TestLaunchpadLib, self).setUp()
        self.launchpad = salgado_with_full_permissions.login()
        self.project = self.launchpad.projects['firefox']

    def verifyAttributes(self, element):
        """Verify that launchpadlib can parse the element's attributes."""
        attribute_names = (element.lp_attributes
            + element.lp_entries + element.lp_collections)
        for name in attribute_names:
            getattr(element, name)

    def test_project(self):
        """Test project attributes."""
        self.verifyAttributes(self.project)

    def test_person(self):
        """Test person attributes."""
        self.verifyAttributes(self.launchpad.me)

    def test_bug(self):
        """Test bug attributes."""
        self.verifyAttributes(self.launchpad.bugs[1])

    def test_branch(self):
        """Test branch attributes."""
        branch_name = self.factory.makeBranch().unique_name
        transaction.commit()
        branch = self.launchpad.branches.getByUniqueName(
            unique_name=branch_name)
        self.verifyAttributes(branch)

    def test_milestone(self):
        """Test milestone attributes."""
        # launchpadlib can only slice and not subscript
        # so project.milestones[0] doesn't work.
        milestone = self.project.active_milestones[:1][0]
        self.verifyAttributes(milestone)
