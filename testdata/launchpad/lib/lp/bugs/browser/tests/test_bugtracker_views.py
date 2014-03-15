# Copyright 2010-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for BugTracker views."""

__metaclass__ = type

from zope.component import getUtility

from lp.app.enums import InformationType
from lp.bugs.interfaces.bugtracker import IBugTrackerSet
from lp.services.webapp import canonical_url
from lp.testing import (
    admin_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.matchers import IsConfiguredBatchNavigator
from lp.testing.views import create_initialized_view


class TestBugTrackerView(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_related_projects(self):
        # Related products and projectgroups are shown by the view.
        tracker = self.factory.makeBugTracker()
        project_group = self.factory.makeProject() 
        product = self.factory.makeProduct()
        with admin_logged_in():
            project_group.bugtracker = tracker
            product.bugtracker = tracker
        view = create_initialized_view(tracker, name='+index')
        self.assertEqual([project_group, product], view.related_projects)

    def test_linked_projects_only_shows_active_projects(self):
        # Inactive projects are not shown as the related projects.
        tracker = self.factory.makeBugTracker()
        active_product = self.factory.makeProduct()
        inactive_product = self.factory.makeProduct()
        with admin_logged_in():
            active_product.bugtracker = tracker
            inactive_product.bugtracker = tracker
            inactive_product.active = False
        view = create_initialized_view(tracker, name='+index')
        self.assertEqual([active_product], view.related_projects)
            
    def test_bugtracker_with_private_project(self):
        tracker = self.factory.makeBugTracker()
        product = self.factory.makeProduct(
            information_type=InformationType.PROPRIETARY, name='foobar')
        with admin_logged_in():
            product.bugtracker = tracker
        view = create_initialized_view(tracker, name='+index')
        self.assertEqual([], view.related_projects)


class TestBugTrackerSetView(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_trackers_are_batch_navigators(self):
        trackers = getUtility(IBugTrackerSet)
        view = create_initialized_view(trackers, name='+index')
        matcher = IsConfiguredBatchNavigator('tracker', 'trackers')
        self.assertThat(view.active_trackers, matcher)
        self.assertThat(view.inactive_trackers, matcher)

    def test_page_is_batched(self):
        self.factory.makeBugTracker()
        self.factory.makeBugTracker()
        inactive_tracker1 = self.factory.makeBugTracker()
        inactive_tracker2 = self.factory.makeBugTracker()
        with admin_logged_in():
            inactive_tracker1.active = False
            inactive_tracker2.active = False
        trackers = getUtility(IBugTrackerSet)
        url = (canonical_url(trackers) +
            "/+index?active_batch=1&inactive_batch=1")
        browser = self.getUserBrowser(url)
        content = browser.contents
        # XXX RobertCollns 20100919 bug=642504. The support for multiple batches
        # isn't complete and the id for the nav links gets duplicated.
        #self.assertEqual('next',
        #    find_tag_by_id(content, 'upper-batch-nav-batchnav-next')['class'])
        #self.assertEqual('next',
        #    find_tag_by_id(content, 'lower-batch-nav-batchnav-next')['class'])
        # Instead we check the string appears.
        self.assertTrue('upper-batch-nav-batchnav-next' in content)

    def test_tracker_with_private_project(self):
        tracker = self.factory.makeBugTracker()
        product = self.factory.makeProduct(
            information_type=InformationType.PROPRIETARY, name='foobar')
        with admin_logged_in():
            product.bugtracker = tracker
        url = canonical_url(getUtility(IBugTrackerSet))
        browser = self.getUserBrowser(url)
        self.assertIn(tracker.name, browser.contents)
        self.assertNotIn('foobar', browser.contents)
