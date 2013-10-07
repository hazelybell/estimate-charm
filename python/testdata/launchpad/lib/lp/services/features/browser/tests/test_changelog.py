# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for feature flag change log views."""


__metaclass__ = type

from zope.component import getUtility

from lp.services.features.changelog import ChangeLog
from lp.services.webapp.authorization import check_permission
from lp.services.webapp.interfaces import ILaunchpadRoot
from lp.testing import (
    login_celebrity,
    login_person,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.pages import find_tag_by_id
from lp.testing.views import create_view


diff = (
    "-bugs.feature_%(idx)s team:testers 10 on\n"
    "+bugs.feature_%(idx)s team:testers 10 off")


class TestChangeLogView(TestCaseWithFactory):
    """Test the feature flag ChangeLog view."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestChangeLogView, self).setUp()
        self.root = getUtility(ILaunchpadRoot)
        self.person = self.factory.makePerson()

    def makeFeatureFlagChanges(self):
        for i in range(0, 11):
            ChangeLog.append(
                diff % dict(idx=i), 'comment %s' % i, self.person)

    def test_anonymous_no_access(self):
        # Anonymous users cannot access the view.
        view = create_view(self.root, name='+feature-changelog')
        self.assertFalse(check_permission('launchpad.Edit', view))

    def test_logged_on_user_no_access(self):
        # Login users cannot access the view.
        login_person(self.factory.makePerson())
        view = create_view(self.root, name='+feature-changelog')
        self.assertFalse(check_permission('launchpad.Edit', view))

    def test_registry_experts_access(self):
        # Registry expert members can access the view.
        login_celebrity('registry_experts')
        view = create_view(self.root, name='+feature-changelog')
        self.assertTrue(check_permission('launchpad.Edit', view))

    def test_admin_access(self):
        # Admin members can access the view.
        login_celebrity('admin')
        view = create_view(self.root, name='+feature-changelog')
        self.assertTrue(check_permission('launchpad.Edit', view))

    def test_batched_page_title(self):
        # The view provides a page_title and label.
        view = create_view(self.root, name='+feature-changelog')
        self.assertEqual(
            view.label, view.page_title)
        self.assertEqual(
            'Feature flag changelog', view.page_title)

    def test_batched_changes(self):
        # The view provides a batched iterator of changes.
        self.makeFeatureFlagChanges()
        view = create_view(self.root, name='+feature-changelog')
        batch = view.changes
        self.assertEqual('change', batch._singular_heading)
        self.assertEqual('changes', batch._plural_heading)
        self.assertEqual(10, batch.default_size)
        self.assertEqual(None, batch.currentBatch().nextBatch().nextBatch())

    def test_page_batched_changes(self):
        self.makeFeatureFlagChanges()
        member = login_celebrity('admin')
        view = create_view(
            self.root, name='+feature-changelog', principal=member)
        tag = find_tag_by_id(view.render(), 'changes')
        self.assertTrue('table', tag.name)
