# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from zope.component import getUtility

from lp.bugs.interfaces.bugtracker import IBugTrackerSet
from lp.services.webapp.publisher import canonical_url
from lp.testing import login_person
from lp.testing.breadcrumbs import BaseBreadcrumbTestCase


class TestBugTaskBreadcrumb(BaseBreadcrumbTestCase):

    def setUp(self):
        super(TestBugTaskBreadcrumb, self).setUp()
        product = self.factory.makeProduct(
            name='crumb-tester', displayname="Crumb Tester")
        self.bug = self.factory.makeBug(target=product, title='borked')
        self.bugtask = self.bug.default_bugtask
        self.bugtask_url = canonical_url(self.bugtask, rootsite='bugs')

    def test_bugtask(self):
        crumbs = self.getBreadcrumbsForObject(self.bugtask)
        last_crumb = crumbs[-1]
        self.assertEquals(self.bugtask_url, last_crumb.url)
        self.assertEquals("Bug #%d" % self.bug.id, last_crumb.text)
        self.assertEquals(
            u"Bug #%d \u201cborked\u201d" % self.bug.id, last_crumb.detail)

    def test_bugtask_child(self):
        crumbs = self.getBreadcrumbsForObject(
            self.bugtask, view_name='+activity')
        self.assertEquals(crumbs[-1].url, "%s/+activity" % self.bugtask_url)
        self.assertEquals(crumbs[-2].url, self.bugtask_url)
        self.assertEquals(crumbs[-2].text, "Bug #%d" % self.bug.id)

    def test_bugtask_comment(self):
        login_person(self.bug.owner)
        comment = self.factory.makeBugComment(
            bug=self.bug, owner=self.bug.owner,
            subject="test comment subject", body="test comment body")
        expected_breadcrumbs = [
            ('Crumb Tester', 'http://launchpad.dev/crumb-tester'),
            ('Bugs', 'http://bugs.launchpad.dev/crumb-tester'),
            ('Bug #%s' % self.bug.id,
             'http://bugs.launchpad.dev/crumb-tester/+bug/%s' % self.bug.id),
            ('Comment #1',
             'http://bugs.launchpad.dev/crumb-tester/+bug/%s/comments/1' % (
                self.bug.id)),
            ]
        self.assertBreadcrumbs(expected_breadcrumbs, comment)


class TestBugTrackerBreadcrumbs(BaseBreadcrumbTestCase):

    def setUp(self):
        super(TestBugTrackerBreadcrumbs, self).setUp()
        self.bug_tracker_set = getUtility(IBugTrackerSet)
        self.bug_tracker_set_url = canonical_url(
            self.bug_tracker_set, rootsite='bugs')
        self.bug_tracker = self.factory.makeBugTracker()
        self.bug_tracker_url = canonical_url(
            self.bug_tracker, rootsite='bugs')

    def test_bug_tracker_set(self):
        # Check TestBugTrackerSetBreadcrumb.
        expected_breadcrumbs = [
            ('Bug trackers', self.bug_tracker_set_url),
            ]
        self.assertBreadcrumbs(expected_breadcrumbs, self.bug_tracker_set)

    def test_bug_tracker(self):
        # Check TestBugTrackerBreadcrumb (and
        # TestBugTrackerSetBreadcrumb).
        expected_breadcrumbs = [
            ('Bug trackers', self.bug_tracker_set_url),
            (self.bug_tracker.title, self.bug_tracker_url),
            ]
        self.assertBreadcrumbs(expected_breadcrumbs, self.bug_tracker)


class BugsVHostBreadcrumbTestCase(BaseBreadcrumbTestCase):

    def test_person(self):
        person = self.factory.makePerson(name='snarf')
        person_bugs_url = canonical_url(person, rootsite='bugs')
        crumbs = self.getBreadcrumbsForObject(person, rootsite='bugs')
        last_crumb = crumbs[-1]
        self.assertEquals(person_bugs_url, last_crumb.url)
        self.assertEquals("Bugs", last_crumb.text)

    def test_bugtarget(self):
        project = self.factory.makeProduct(name='fnord')
        project_bugs_url = canonical_url(project, rootsite='bugs')
        crumbs = self.getBreadcrumbsForObject(project, rootsite='bugs')
        last_crumb = crumbs[-1]
        self.assertEquals(project_bugs_url, last_crumb.url)
        self.assertEquals("Bugs", last_crumb.text)
