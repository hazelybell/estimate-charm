# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from datetime import (
    datetime,
    timedelta,
    )
import re
import urllib

from BeautifulSoup import BeautifulSoup
from lazr.lifecycle.event import ObjectModifiedEvent
from lazr.lifecycle.snapshot import Snapshot
from lazr.restful.interfaces import IJSONRequestCache
from pytz import UTC
import simplejson
import soupmatchers
from storm.store import Store
from testtools.matchers import (
    LessThan,
    Not,
    )
import transaction
from zope.component import (
    getMultiAdapter,
    getUtility,
    )
from zope.event import notify
from zope.interface import providedBy
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.bugs.adapters.bugchange import BugTaskStatusChange
from lp.bugs.browser.bugtask import (
    BugActivityItem,
    BugListingBatchNavigator,
    BugTaskEditView,
    BugTaskListingItem,
    BugTasksNominationsView,
    BugTasksTableView,
    )
from lp.bugs.enums import BugNotificationLevel
from lp.bugs.feed.bug import PersonBugsFeed
from lp.bugs.interfaces.bugactivity import IBugActivitySet
from lp.bugs.interfaces.bugnomination import IBugNomination
from lp.bugs.interfaces.bugtask import (
    BugTaskStatus,
    BugTaskStatusSearch,
    IBugTask,
    IBugTaskSet,
    )
from lp.bugs.model.bugtasksearch import orderby_expression
from lp.layers import (
    FeedsLayer,
    setFirstLayer,
    )
from lp.registry.enums import BugSharingPolicy
from lp.registry.interfaces.person import PersonVisibility
from lp.services.config import config
from lp.services.database.constants import UTC_NOW
from lp.services.features.testing import FeatureFixture
from lp.services.propertycache import get_property_cache
from lp.services.webapp import canonical_url
from lp.services.webapp.escaping import html_escape
from lp.services.webapp.interfaces import (
    ILaunchBag,
    ILaunchpadRoot,
    )
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.soyuz.interfaces.component import IComponentSet
from lp.testing import (
    ANONYMOUS,
    BrowserTestCase,
    celebrity_logged_in,
    login,
    login_person,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing._webservice import QueryCollector
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    )
from lp.testing.matchers import (
    BrowsesWithQueryLimit,
    HasQueryCount,
    )
from lp.testing.pages import find_tag_by_id
from lp.testing.sampledata import (
    ADMIN_EMAIL,
    NO_PRIVILEGE_EMAIL,
    USER_EMAIL,
    )
from lp.testing.views import create_initialized_view


def getFeedViewCache(target, feed_cls):
    """Return JSON cache for a feed's delegate view."""
    request = LaunchpadTestRequest(
        SERVER_URL='http://feeds.example.com/latest-bugs.atom')
    setFirstLayer(request, FeedsLayer)
    feed = feed_cls(target, request)
    delegate_view = feed._createView()
    delegate_view.initialize()
    return IJSONRequestCache(delegate_view.request)


class TestBugTaskView(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def invalidate_caches(self, obj):
        store = Store.of(obj)
        # Make sure everything is in the database.
        store.flush()
        # And invalidate the cache (not a reset, because that stops us using
        # the domain objects)
        store.invalidate()

    def test_rendered_query_counts_constant_with_team_memberships(self):
        login(ADMIN_EMAIL)
        task = self.factory.makeBugTask()
        person_no_teams = self.factory.makePerson()
        person_with_teams = self.factory.makePerson()
        for _ in range(10):
            self.factory.makeTeam(members=[person_with_teams])
        # count with no teams
        url = canonical_url(task)
        recorder = QueryCollector()
        recorder.register()
        self.addCleanup(recorder.unregister)
        self.invalidate_caches(task)
        self.getUserBrowser(url, person_no_teams)
        # This may seem large: it is; there is easily another 25% fat in
        # there.
        # If this test is run in isolation, the query count is 80.
        # Other tests in this TestCase could cache the
        # "SELECT id, product, project, distribution FROM PillarName ..."
        # query by previously browsing the task url, in which case the
        # query count is decreased by one.
        self.assertThat(recorder, HasQueryCount(LessThan(83)))
        count_with_no_teams = recorder.count
        # count with many teams
        self.invalidate_caches(task)
        self.getUserBrowser(url, person_with_teams)
        # Allow an increase of one because storm bug 619017 causes additional
        # queries, revalidating things unnecessarily. An increase which is
        # less than the number of new teams shows it is definitely not
        # growing per-team.
        self.assertThat(recorder, HasQueryCount(
            LessThan(count_with_no_teams + 3),
            ))

    def test_rendered_query_counts_constant_with_attachments(self):
        with celebrity_logged_in('admin'):
            browses_under_limit = BrowsesWithQueryLimit(
                85, self.factory.makePerson())

            # First test with a single attachment.
            task = self.factory.makeBugTask()
            self.factory.makeBugAttachment(bug=task.bug)
        self.assertThat(task, browses_under_limit)

        with celebrity_logged_in('admin'):
            # And now with 10.
            task = self.factory.makeBugTask()
            self.factory.makeBugTask(bug=task.bug)
            for i in range(10):
                self.factory.makeBugAttachment(bug=task.bug)
        self.assertThat(task, browses_under_limit)

    def makeLinkedBranchMergeProposal(self, sourcepackage, bug, owner):
        with person_logged_in(owner):
            f = self.factory
            target_branch = f.makePackageBranch(
                sourcepackage=sourcepackage, owner=owner)
            source_branch = f.makeBranchTargetBranch(
                target_branch.target, owner=owner)
            bug.linkBranch(source_branch, owner)
            return f.makeBranchMergeProposal(
                target_branch=target_branch,
                registrant=owner,
                source_branch=source_branch)

    def test_rendered_query_counts_reduced_with_branches(self):
        owner = self.factory.makePerson()
        ds = self.factory.makeDistroSeries()
        bug = self.factory.makeBug()
        sourcepackages = [
            self.factory.makeSourcePackage(distroseries=ds, publish=True)
            for i in range(5)]
        for sp in sourcepackages:
            self.factory.makeBugTask(bug=bug, owner=owner, target=sp)
        task = bug.default_bugtask
        url = canonical_url(task)
        recorder = QueryCollector()
        recorder.register()
        self.addCleanup(recorder.unregister)
        self.invalidate_caches(task)
        self.getUserBrowser(url, owner)
        # At least 20 of these should be removed.
        self.assertThat(recorder, HasQueryCount(LessThan(114)))
        count_with_no_branches = recorder.count
        for sp in sourcepackages:
            self.makeLinkedBranchMergeProposal(sp, bug, owner)
        self.invalidate_caches(task)
        self.getUserBrowser(url, owner)  # This triggers the query recorder.
        # Ideally this should be much fewer, but this tries to keep a win of
        # removing more than half of these.
        self.assertThat(
            recorder, HasQueryCount(LessThan(count_with_no_branches + 46)))

    def test_interesting_activity(self):
        # The interesting_activity property returns a tuple of interesting
        # `BugActivityItem`s.
        bug = self.factory.makeBug()
        view = create_initialized_view(
            bug.default_bugtask, name=u'+index', rootsite='bugs')

        def add_activity(what, old=None, new=None, message=None):
            getUtility(IBugActivitySet).new(
                bug, datetime.now(UTC), bug.owner, whatchanged=what,
                oldvalue=old, newvalue=new, message=message)
            del get_property_cache(view).interesting_activity

        # A fresh bug has no interesting activity.
        self.assertEqual((), view.interesting_activity)

        # Some activity is not considered interesting.
        add_activity("boring")
        self.assertEqual((), view.interesting_activity)

        # A description change is interesting.
        add_activity("description")
        self.assertEqual(1, len(view.interesting_activity))
        [activity] = view.interesting_activity
        self.assertEqual("description", activity.whatchanged)

    def test_rendered_query_counts_constant_with_activities(self):
        # More queries are not used for extra bug activities.
        task = self.factory.makeBugTask()

        def add_activity(what, who):
            getUtility(IBugActivitySet).new(
                task.bug, datetime.now(UTC), who, whatchanged=what)

        # Render the view with one activity.
        with celebrity_logged_in('admin'):
            browses_under_limit = BrowsesWithQueryLimit(
                83, self.factory.makePerson())
            person = self.factory.makePerson()
            add_activity("description", person)

        self.assertThat(task, browses_under_limit)

        # Render the view with many more activities by different people.
        with celebrity_logged_in('admin'):
            for _ in range(20):
                person = self.factory.makePerson()
                add_activity("description", person)

        self.assertThat(task, browses_under_limit)

    def test_rendered_query_counts_constant_with_milestones(self):
        # More queries are not used for extra milestones.
        products = []
        bug = self.factory.makeBug()

        with celebrity_logged_in('admin'):
            browses_under_limit = BrowsesWithQueryLimit(
                88, self.factory.makePerson())

        self.assertThat(bug, browses_under_limit)

        # Render the view with many milestones.
        with celebrity_logged_in('admin'):
            for _ in range(10):
                product = self.factory.makeProduct()
                products.append(product)
                self.factory.makeBugTask(bug=bug, target=product)
                self.factory.makeMilestone(product)

        self.assertThat(bug, browses_under_limit)

    def test_error_for_changing_target_with_invalid_status(self):
        # If a user moves a bug task with a restricted status (say,
        # Triaged) to a target where they do not have permission to set
        # that status, they will be unable to complete the retargeting
        # and will instead receive an error in the UI.
        person = self.factory.makePerson()
        product = self.factory.makeProduct(
            name='product1', owner=person, official_malone=True,
            bug_supervisor=person)
        product_2 = self.factory.makeProduct(
            name='product2', official_malone=True)
        bug = self.factory.makeBug(target=product, owner=person)
        # We need to commit here, otherwise all the sample data we
        # created gets destroyed when the transaction is rolled back.
        transaction.commit()
        with person_logged_in(person):
            form_data = {
                '%s.target' % product.name: 'product',
                '%s.target.product' % product.name: product_2.name,
                '%s.status' % product.name: BugTaskStatus.TRIAGED.title,
                '%s.actions.save' % product.name: 'Save Changes',
                }
            view = create_initialized_view(
                bug.default_bugtask, name=u'+editstatus',
                form=form_data)
            # The bugtask's target won't have changed, since an error
            # happend. The error will be listed in the view.
            self.assertEqual(1, len(view.errors))
            self.assertEqual(product, bug.default_bugtask.target)

    def test_changing_milestone_and_assignee_with_lifecycle(self):
        # Changing the milestone and assignee of a bugtask when the milestone
        # has a LIFECYCLE structsub is fine. Also see bug 1036882.
        subscriber = self.factory.makePerson()
        product = self.factory.makeProduct(official_malone=True)
        milestone = self.factory.makeMilestone(product=product)
        with person_logged_in(subscriber):
            structsub = milestone.addBugSubscription(subscriber, subscriber)
            structsub.bug_filters[0].bug_notification_level = (
                BugNotificationLevel.LIFECYCLE)
        bug = self.factory.makeBug(target=product)
        with person_logged_in(product.owner):
            form_data = {
                '%s.milestone' % product.name: milestone.id,
                '%s.assignee.option' % product.name:
                    '%s.assignee.assign_to_me' % product.name,
                '%s.assignee' % product.name: product.owner.name,
                '%s.actions.save' % product.name: 'Save Changes',
                }
            create_initialized_view(
                bug.default_bugtask, name='+editstatus', form=form_data)
            self.assertEqual(product.owner, bug.default_bugtask.assignee)
            self.assertEqual(milestone, bug.default_bugtask.milestone)

    def test_bugtag_urls_are_encoded(self):
        # The link to bug tags are encoded to protect against special chars.
        product = self.factory.makeProduct(name='foobar')
        bug = self.factory.makeBug(target=product, tags=['depends-on+987'])
        getUtility(ILaunchBag).add(bug.default_bugtask)
        view = create_initialized_view(bug.default_bugtask, name=u'+index')
        expected = [(u'depends-on+987',
            u'/foobar/+bugs?field.tag=depends-on%2B987')]
        self.assertEqual(expected, view.unofficial_tags)
        browser = self.getUserBrowser(canonical_url(bug), bug.owner)
        self.assertIn(
            'href="/foobar/+bugs?field.tag=depends-on%2B987"',
            browser.contents)

    def test_information_type(self):
        owner = self.factory.makePerson()
        bug = self.factory.makeBug(
            owner=owner, information_type=InformationType.USERDATA)
        login_person(owner)
        bugtask = self.factory.makeBugTask(bug=bug)
        view = create_initialized_view(bugtask, name="+index")
        self.assertEqual('Private', view.information_type)

    def test_duplicate_message_for_inactive_dupes(self):
        # A duplicate on an inactive project is not linked to.
        inactive_project = self.factory.makeProduct()
        inactive_bug = self.factory.makeBug(target=inactive_project)
        bug = self.factory.makeBug()
        with person_logged_in(bug.owner):
            bug.markAsDuplicate(inactive_bug)
        removeSecurityProxy(inactive_project).active = False
        browser = self.getUserBrowser(canonical_url(bug))
        contents = browser.contents
        self.assertIn(
            "This bug report is a duplicate of a bug on an inactive project.",
            contents)

        # Confirm there is no link to the duplicate bug.
        soup = BeautifulSoup(contents)
        tag = soup.find('a', attrs={'id': "duplicate-of"})
        self.assertIsNone(tag)

    def test_related_blueprints_is_hidden(self):
        # When a bug has no specifications linked, the Related blueprints
        # portlet is hidden.
        bug = self.factory.makeBug()
        browser = self.getUserBrowser(canonical_url(bug))
        self.assertNotIn('Related blueprints', browser.contents)

    def test_related_blueprints_is_shown(self):
        # When a bug has specifications linked, the Related blueprints portlet
        # is shown.
        bug = self.factory.makeBug()
        spec = self.factory.makeSpecification(title='My brilliant spec')
        with person_logged_in(spec.owner):
            spec.linkBug(bug)
        browser = self.getUserBrowser(canonical_url(bug))
        self.assertIn('Related blueprints', browser.contents)
        self.assertIn('My brilliant spec', browser.contents)


class TestBugTasksNominationsView(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBugTasksNominationsView, self).setUp()
        login(ADMIN_EMAIL)
        self.bug = self.factory.makeBug()
        self.view = BugTasksNominationsView(self.bug, LaunchpadTestRequest())

    def refresh(self):
        # The view caches, to see different scenarios, a refresh is needed.
        self.view = BugTasksNominationsView(self.bug, LaunchpadTestRequest())

    def test_current_user_affected_status(self):
        self.failUnlessEqual(
            None, self.view.current_user_affected_status)
        self.bug.markUserAffected(self.view.user, True)
        self.refresh()
        self.assertTrue(self.view.current_user_affected_status)
        self.bug.markUserAffected(self.view.user, False)
        self.refresh()
        self.assertFalse(self.view.current_user_affected_status)

    def test_current_user_affected_js_status(self):
        self.failUnlessEqual(
            'null', self.view.current_user_affected_js_status)
        self.bug.markUserAffected(self.view.user, True)
        self.refresh()
        self.failUnlessEqual(
            'true', self.view.current_user_affected_js_status)
        self.bug.markUserAffected(self.view.user, False)
        self.refresh()
        self.failUnlessEqual(
            'false', self.view.current_user_affected_js_status)

    def test_other_users_affected_count(self):
        # The number of other users affected does not change when the
        # logged-in user marked him or herself as affected or not.
        self.failUnlessEqual(
            1, self.view.other_users_affected_count)
        self.bug.markUserAffected(self.view.user, True)
        self.refresh()
        self.failUnlessEqual(
            1, self.view.other_users_affected_count)
        self.bug.markUserAffected(self.view.user, False)
        self.refresh()
        self.failUnlessEqual(
            1, self.view.other_users_affected_count)

    def test_other_users_affected_count_other_users(self):
        # The number of other users affected only changes when other
        # users mark themselves as affected.
        self.failUnlessEqual(
            1, self.view.other_users_affected_count)
        other_user_1 = self.factory.makePerson()
        self.bug.markUserAffected(other_user_1, True)
        self.refresh()
        self.failUnlessEqual(
            2, self.view.other_users_affected_count)
        other_user_2 = self.factory.makePerson()
        self.bug.markUserAffected(other_user_2, True)
        self.refresh()
        self.failUnlessEqual(
            3, self.view.other_users_affected_count)
        self.bug.markUserAffected(other_user_1, False)
        self.refresh()
        self.failUnlessEqual(
            2, self.view.other_users_affected_count)
        self.bug.markUserAffected(self.view.user, True)
        self.refresh()
        self.failUnlessEqual(
            2, self.view.other_users_affected_count)

    def makeDuplicate(self):
        user2 = self.factory.makePerson()
        self.bug2 = self.factory.makeBug()
        self.bug2.markUserAffected(user2, True)
        self.assertEqual(
            2, self.bug2.users_affected_count)
        self.bug2.markAsDuplicate(self.bug)
        # After this there are three users already affected: the creators of
        # the two bugs, plus user2.  The current user is not yet affected by
        # any of them.

    def test_counts_user_unaffected(self):
        self.useFixture(FeatureFixture(
            {'bugs.affected_count_includes_dupes.disabled': ''}))
        self.makeDuplicate()
        self.assertEqual(3, self.view.total_users_affected_count)
        self.assertEqual(
            "This bug affects 3 people. Does this bug affect you?",
            self.view.affected_statement)
        self.assertEqual(
            "This bug affects 3 people", self.view.anon_affected_statement)
        self.assertEqual(self.view.other_users_affected_count, 3)

    def test_counts_affected_by_duplicate(self):
        self.useFixture(FeatureFixture(
            {'bugs.affected_count_includes_dupes.disabled': ''}))
        self.makeDuplicate()
        # Now with you affected by the duplicate, but not the master.
        self.bug2.markUserAffected(self.view.user, True)
        self.refresh()
        self.assertEqual(
            "This bug affects 3 people. Does this bug affect you?",
            self.view.affected_statement)
        self.assertEqual(
            "This bug affects 4 people", self.view.anon_affected_statement)
        self.assertEqual(self.view.other_users_affected_count, 3)

    def test_counts_affected_by_master(self):
        self.useFixture(FeatureFixture(
            {'bugs.affected_count_includes_dupes.disabled': ''}))
        self.makeDuplicate()
        # And now with you also affected by the master.
        self.bug.markUserAffected(self.view.user, True)
        self.refresh()
        self.assertEqual(
            "This bug affects you and 3 other people",
            self.view.affected_statement)
        self.assertEqual(
            "This bug affects 4 people", self.view.anon_affected_statement)
        self.assertEqual(self.view.other_users_affected_count, 3)

    def test_counts_affected_by_duplicate_not_by_master(self):
        self.useFixture(FeatureFixture(
            {'bugs.affected_count_includes_dupes.disabled': ''}))
        self.makeDuplicate()
        self.bug2.markUserAffected(self.view.user, True)
        self.bug.markUserAffected(self.view.user, False)
        # You're not included in this count, even though you are affected by
        # the dupe.
        self.assertEqual(
            "This bug affects 3 people, but not you",
            self.view.affected_statement)
        # It would be reasonable for Anon to see this bug cluster affecting
        # either 3 or 4 people.  However at the moment the "No" answer on the
        # master is more authoritative than the "Yes" on the dupe.
        self.assertEqual(
            "This bug affects 3 people", self.view.anon_affected_statement)
        self.assertEqual(self.view.other_users_affected_count, 3)

    def test_total_users_affected_count_without_dupes(self):
        self.useFixture(FeatureFixture(
            {'bugs.affected_count_includes_dupes.disabled': 'on'}))
        self.makeDuplicate()
        self.refresh()
        # Does not count the two users of bug2, so just 1.
        self.assertEqual(1, self.view.total_users_affected_count)
        self.assertEqual(
            "This bug affects 1 person. Does this bug affect you?",
            self.view.affected_statement)
        self.assertEqual(
            "This bug affects 1 person", self.view.anon_affected_statement)
        self.assertEqual(1, self.view.other_users_affected_count)

    def test_affected_statement_no_one_affected(self):
        self.bug.markUserAffected(self.bug.owner, False)
        self.failUnlessEqual(
            0, self.view.other_users_affected_count)
        self.failUnlessEqual(
            "Does this bug affect you?", self.view.affected_statement)

    def test_affected_statement_only_you(self):
        self.view.context.markUserAffected(self.view.user, True)
        self.failUnless(self.bug.isUserAffected(self.view.user))
        self.view.context.markUserAffected(self.bug.owner, False)
        self.failUnlessEqual(
            0, self.view.other_users_affected_count)
        self.failUnlessEqual(
            "This bug affects you", self.view.affected_statement)

    def test_affected_statement_only_not_you(self):
        self.view.context.markUserAffected(self.view.user, False)
        self.failIf(self.bug.isUserAffected(self.view.user))
        self.view.context.markUserAffected(self.bug.owner, False)
        self.failUnlessEqual(
            0, self.view.other_users_affected_count)
        self.failUnlessEqual(
            "This bug doesn't affect you", self.view.affected_statement)

    def test_affected_statement_1_person_not_you(self):
        self.assertIs(None, self.bug.isUserAffected(self.view.user))
        self.failUnlessEqual(
            1, self.view.other_users_affected_count)
        self.failUnlessEqual(
            "This bug affects 1 person. Does this bug affect you?",
            self.view.affected_statement)

    def test_affected_statement_1_person_and_you(self):
        self.view.context.markUserAffected(self.view.user, True)
        self.failUnless(self.bug.isUserAffected(self.view.user))
        self.failUnlessEqual(
            1, self.view.other_users_affected_count)
        self.failUnlessEqual(
            "This bug affects you and 1 other person",
            self.view.affected_statement)

    def test_affected_statement_1_person_and_not_you(self):
        self.view.context.markUserAffected(self.view.user, False)
        self.failIf(self.bug.isUserAffected(self.view.user))
        self.failUnlessEqual(1, self.view.other_users_affected_count)
        self.failUnlessEqual(
            "This bug affects 1 person, but not you",
            self.view.affected_statement)

    def test_affected_statement_more_than_1_person_not_you(self):
        self.assertIs(None, self.bug.isUserAffected(self.view.user))
        other_user = self.factory.makePerson()
        self.view.context.markUserAffected(other_user, True)
        self.failUnlessEqual(2, self.view.other_users_affected_count)
        self.failUnlessEqual(
            "This bug affects 2 people. Does this bug affect you?",
            self.view.affected_statement)

    def test_affected_statement_more_than_1_person_and_you(self):
        self.view.context.markUserAffected(self.view.user, True)
        self.failUnless(self.bug.isUserAffected(self.view.user))
        other_user = self.factory.makePerson()
        self.view.context.markUserAffected(other_user, True)
        self.failUnlessEqual(2, self.view.other_users_affected_count)
        self.failUnlessEqual(
            "This bug affects you and 2 other people",
            self.view.affected_statement)

    def test_affected_statement_more_than_1_person_and_not_you(self):
        self.view.context.markUserAffected(self.view.user, False)
        self.failIf(self.bug.isUserAffected(self.view.user))
        other_user = self.factory.makePerson()
        self.view.context.markUserAffected(other_user, True)
        self.failUnlessEqual(2, self.view.other_users_affected_count)
        self.failUnlessEqual(
            "This bug affects 2 people, but not you",
            self.view.affected_statement)

    def test_anon_affected_statement_no_one_affected(self):
        self.bug.markUserAffected(self.bug.owner, False)
        self.failUnlessEqual(0, self.bug.users_affected_count)
        self.assertIs(None, self.view.anon_affected_statement)

    def test_anon_affected_statement_1_user_affected(self):
        self.failUnlessEqual(1, self.bug.users_affected_count)
        self.failUnlessEqual(
            "This bug affects 1 person", self.view.anon_affected_statement)

    def test_anon_affected_statement_2_users_affected(self):
        self.view.context.markUserAffected(self.view.user, True)
        self.failUnlessEqual(2, self.bug.users_affected_count)
        self.failUnlessEqual(
            "This bug affects 2 people", self.view.anon_affected_statement)


class TestBugTasksTableView(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBugTasksTableView, self).setUp()
        login(ADMIN_EMAIL)
        self.bug = self.factory.makeBug()
        self.view = BugTasksTableView(self.bug, LaunchpadTestRequest())

    def refresh(self):
        # The view caches, to see different scenarios, a refresh is needed.
        self.view = BugTasksNominationsView(self.bug, LaunchpadTestRequest())

    def test_not_many_bugtasks(self):
        for count in range(10 - len(self.bug.bugtasks) - 1):
            self.factory.makeBugTask(bug=self.bug)
        self.view.initialize()
        self.failIf(self.view.many_bugtasks)
        row_view = self.view._getTableRowView(
            self.bug.default_bugtask, False, False)
        self.failIf(row_view.many_bugtasks)

    def test_many_bugtasks(self):
        for count in range(10 - len(self.bug.bugtasks)):
            self.factory.makeBugTask(bug=self.bug)
        self.view.initialize()
        self.failUnless(self.view.many_bugtasks)
        row_view = self.view._getTableRowView(
            self.bug.default_bugtask, False, False)
        self.failUnless(row_view.many_bugtasks)

    def test_getTargetLinkTitle_product(self):
        # The target link title is always none for products.
        target = self.factory.makeProduct()
        bug_task = self.factory.makeBugTask(bug=self.bug, target=target)
        self.view.initialize()
        self.assertIs(None, self.view.getTargetLinkTitle(bug_task.target))

    def test_getTargetLinkTitle_productseries(self):
        # The target link title is always none for productseries.
        target = self.factory.makeProductSeries()
        bug_task = self.factory.makeBugTask(bug=self.bug, target=target)
        self.view.initialize()
        self.assertIs(None, self.view.getTargetLinkTitle(bug_task.target))

    def test_getTargetLinkTitle_distribution(self):
        # The target link title is always none for distributions.
        target = self.factory.makeDistribution()
        bug_task = self.factory.makeBugTask(bug=self.bug, target=target)
        self.view.initialize()
        self.assertIs(None, self.view.getTargetLinkTitle(bug_task.target))

    def test_getTargetLinkTitle_distroseries(self):
        # The target link title is always none for distroseries.
        target = self.factory.makeDistroSeries()
        bug_task = self.factory.makeBugTask(bug=self.bug, target=target)
        self.view.initialize()
        self.assertIs(None, self.view.getTargetLinkTitle(bug_task.target))

    def test_getTargetLinkTitle_unpublished_distributionsourcepackage(self):
        # The target link title states that the package is not published
        # in the current release.
        distribution = self.factory.makeDistribution(name='boy')
        spn = self.factory.makeSourcePackageName('badger')
        component = getUtility(IComponentSet)['universe']
        maintainer = self.factory.makePerson(name="jim")
        creator = self.factory.makePerson(name="tim")
        self.factory.makeSourcePackagePublishingHistory(
            distroseries=distribution.currentseries, version='2.0',
            component=component, sourcepackagename=spn,
            date_uploaded=datetime(2008, 7, 18, 10, 20, 30, tzinfo=UTC),
            maintainer=maintainer, creator=creator)
        target = distribution.getSourcePackage('badger')
        bug_task = self.factory.makeBugTask(
            bug=self.bug, target=target, publish=False)
        self.view.initialize()
        self.assertEqual({}, self.view.target_releases)
        self.assertEqual(
            'No current release for this source package in Boy',
            self.view.getTargetLinkTitle(bug_task.target))

    def test_getTargetLinkTitle_published_distributionsourcepackage(self):
        # The target link title states the information about the current
        # package in the distro.
        distribution = self.factory.makeDistribution(name='koi')
        distroseries = self.factory.makeDistroSeries(
            distribution=distribution)
        spn = self.factory.makeSourcePackageName('finch')
        component = getUtility(IComponentSet)['universe']
        maintainer = self.factory.makePerson(name="jim")
        creator = self.factory.makePerson(name="tim")
        self.factory.makeSourcePackagePublishingHistory(
            distroseries=distroseries, version='2.0',
            component=component, sourcepackagename=spn,
            date_uploaded=datetime(2008, 7, 18, 10, 20, 30, tzinfo=UTC),
            maintainer=maintainer, creator=creator)
        target = distribution.getSourcePackage('finch')
        bug_task = self.factory.makeBugTask(
            bug=self.bug, target=target, publish=False)
        self.view.initialize()
        self.assertTrue(target in self.view.target_releases.keys())
        self.assertEqual(
            'Latest release: 2.0, uploaded to universe on '
            '2008-07-18 10:20:30+00:00 by Tim (tim), maintained by Jim (jim)',
            self.view.getTargetLinkTitle(bug_task.target))

    def test_getTargetLinkTitle_published_sourcepackage(self):
        # The target link title states the information about the current
        # package in the distro.
        distroseries = self.factory.makeDistroSeries()
        spn = self.factory.makeSourcePackageName('bunny')
        component = getUtility(IComponentSet)['universe']
        maintainer = self.factory.makePerson(name="jim")
        creator = self.factory.makePerson(name="tim")
        self.factory.makeSourcePackagePublishingHistory(
            distroseries=distroseries, version='2.0',
            component=component, sourcepackagename=spn,
            date_uploaded=datetime(2008, 7, 18, 10, 20, 30, tzinfo=UTC),
            maintainer=maintainer, creator=creator)
        target = distroseries.getSourcePackage('bunny')
        bug_task = self.factory.makeBugTask(
            bug=self.bug, target=target, publish=False)
        self.view.initialize()
        self.assertTrue(target in self.view.target_releases.keys())
        self.assertEqual(
            'Latest release: 2.0, uploaded to universe on '
            '2008-07-18 10:20:30+00:00 by Tim (tim), maintained by Jim (jim)',
            self.view.getTargetLinkTitle(bug_task.target))

    def _get_object_type(self, task_or_nomination):
        if IBugTask.providedBy(task_or_nomination):
            return "bugtask"
        elif IBugNomination.providedBy(task_or_nomination):
            return "nomination"
        else:
            return "unknown"

    def test_bugtask_listing_for_inactive_projects(self):
        # Bugtasks should only be listed for active projects.

        product_foo = self.factory.makeProduct(name="foo")
        product_bar = self.factory.makeProduct(name="bar")
        foo_bug = self.factory.makeBug(target=product_foo)
        bugtask_set = getUtility(IBugTaskSet)
        bugtask_set.createTask(foo_bug, foo_bug.owner, product_bar)
        removeSecurityProxy(product_bar).active = False

        request = LaunchpadTestRequest()
        foo_bugtasks_and_nominations_view = getMultiAdapter(
            (foo_bug, request), name="+bugtasks-and-nominations-table")
        foo_bugtasks_and_nominations_view.initialize()

        task_and_nomination_views = (
            foo_bugtasks_and_nominations_view.getBugTaskAndNominationViews())
        actual_results = []
        for task_or_nomination_view in task_and_nomination_views:
            task_or_nomination = task_or_nomination_view.context
            actual_results.append((
                self._get_object_type(task_or_nomination),
                task_or_nomination.status.title,
                task_or_nomination.target.bugtargetdisplayname))
        # Only the one active project's task should be listed.
        self.assertEqual([("bugtask", "New", "Foo")], actual_results)

    def test_listing_with_no_bugtasks(self):
        # Test the situation when there are no bugtasks to show.

        product_foo = self.factory.makeProduct(name="foo")
        foo_bug = self.factory.makeBug(target=product_foo)
        removeSecurityProxy(product_foo).active = False

        request = LaunchpadTestRequest()
        foo_bugtasks_and_nominations_view = getMultiAdapter(
            (foo_bug, request), name="+bugtasks-and-nominations-table")
        foo_bugtasks_and_nominations_view.initialize()

        task_and_nomination_views = (
            foo_bugtasks_and_nominations_view.getBugTaskAndNominationViews())
        self.assertEqual([], task_and_nomination_views)

    def test_bugtarget_parent_shown_for_orphaned_series_tasks(self):
        # Test that a row is shown for the parent of a series task, even
        # if the parent doesn't actually have a task.
        series = self.factory.makeProductSeries()
        bug = self.factory.makeBug(series=series)
        self.assertEqual(2, len(bug.bugtasks))
        new_prod = self.factory.makeProduct()
        bug.getBugTask(series.product).transitionToTarget(new_prod, bug.owner)

        view = create_initialized_view(bug, "+bugtasks-and-nominations-table")
        subviews = view.getBugTaskAndNominationViews()
        self.assertEqual([
            (series.product, '+bugtasks-and-nominations-table-row'),
            (bug.getBugTask(series), '+bugtasks-and-nominations-table-row'),
            (bug.getBugTask(new_prod), '+bugtasks-and-nominations-table-row'),
            ], [(v.context, v.__name__) for v in subviews])

        content = subviews[0]()
        self.assertIn(
            'href="%s"' % canonical_url(
                series.product, path_only_if_possible=True),
            content)
        self.assertIn(series.product.displayname, content)

    def test_bugtask_listing_for_private_assignees(self):
        # Private assignees are rendered in the bug portal view.

        # Create a bugtask with a private assignee.
        product_foo = self.factory.makeProduct(name="foo")
        foo_bug = self.factory.makeBug(target=product_foo)
        assignee = self.factory.makeTeam(
            name="assignee", visibility=PersonVisibility.PRIVATE)
        foo_bug.default_bugtask.transitionToAssignee(assignee)

        # Render the view.
        request = LaunchpadTestRequest()
        any_person = self.factory.makePerson()
        login_person(any_person, request)
        foo_bugtasks_and_nominations_view = getMultiAdapter(
            (foo_bug, request), name="+bugtasks-and-nominations-table")
        foo_bugtasks_and_nominations_view.initialize()
        task_and_nomination_views = (
            foo_bugtasks_and_nominations_view.getBugTaskAndNominationViews())
        getUtility(ILaunchBag).add(foo_bug.default_bugtask)
        self.assertEqual(1, len(task_and_nomination_views))
        content = task_and_nomination_views[0]()

        # Check the result.
        soup = BeautifulSoup(content)
        tag = soup.find('label', attrs={'for': "foo.assignee.assigned_to"})
        tag_text = tag.renderContents().strip()
        self.assertEqual(assignee.unique_displayname, tag_text)


class TestBugTaskDeleteLinks(TestCaseWithFactory):
    """ Test that the delete icons/links are correctly rendered.

        Bug task deletion is protected by a feature flag.
        """

    layer = DatabaseFunctionalLayer

    def test_cannot_delete_only_bugtask(self):
        # The last bugtask cannot be deleted.
        bug = self.factory.makeBug()
        login_person(bug.owner)
        view = create_initialized_view(
            bug, name='+bugtasks-and-nominations-table')
        row_view = view._getTableRowView(bug.default_bugtask, False, False)
        self.assertFalse(row_view.user_can_delete_bugtask)
        del get_property_cache(row_view).user_can_delete_bugtask
        self.assertFalse(row_view.user_can_delete_bugtask)

    def test_can_delete_bugtask_if_authorised(self):
        # The bugtask can be deleted if the user if authorised.
        bug = self.factory.makeBug()
        bugtask = self.factory.makeBugTask(bug=bug)
        login_person(bugtask.owner)
        view = create_initialized_view(
            bug, name='+bugtasks-and-nominations-table',
            principal=bugtask.owner)
        row_view = view._getTableRowView(bugtask, False, False)
        self.assertTrue(row_view.user_can_delete_bugtask)

    def test_bugtask_delete_icon(self):
        # The bugtask delete icon is rendered correctly for those tasks the
        # user is allowed to delete.
        bug = self.factory.makeBug()
        bugtask_owner = self.factory.makePerson()
        bugtask = self.factory.makeBugTask(bug=bug, owner=bugtask_owner)
        login_person(bugtask.owner)
        getUtility(ILaunchBag).add(bug.default_bugtask)
        view = create_initialized_view(
            bug, name='+bugtasks-and-nominations-table',
            principal=bugtask.owner)
        # We render the bug task table rows - there are 2 bug tasks.
        subviews = view.getBugTaskAndNominationViews()
        self.assertEqual(2, len(subviews))
        default_bugtask_contents = subviews[0]()
        bugtask_contents = subviews[1]()
        # bugtask can be deleted because the user owns it.
        delete_icon = find_tag_by_id(
            bugtask_contents, 'bugtask-delete-task%d' % bugtask.id)
        delete_url = canonical_url(
            bugtask, rootsite='bugs', view_name='+delete')
        self.assertEqual(delete_url, delete_icon['href'])
        # default_bugtask cannot be deleted.
        delete_icon = find_tag_by_id(
            default_bugtask_contents,
            'bugtask-delete-task%d' % bug.default_bugtask.id)
        self.assertIsNone(delete_icon)

    def test_client_cache_contents(self):
        """ Test that the client cache contains the expected data.

        The cache data is used by the Javascript to enable the delete
        links to work as expected.
        """
        bug = self.factory.makeBug()
        bugtask_owner = self.factory.makePerson()
        bugtask = self.factory.makeBugTask(bug=bug, owner=bugtask_owner)
        login_person(bugtask.owner)
        getUtility(ILaunchBag).add(bug.default_bugtask)
        view = create_initialized_view(
            bug, name='+bugtasks-and-nominations-table',
            principal=bugtask.owner)
        view.render()
        cache = IJSONRequestCache(view.request)
        all_bugtask_data = cache.objects['bugtask_data']

        def check_bugtask_data(bugtask, can_delete):
            self.assertIn(bugtask.id, all_bugtask_data)
            bugtask_data = all_bugtask_data[bugtask.id]
            self.assertEqual(
                'task%d' % bugtask.id, bugtask_data['form_row_id'])
            self.assertEqual(
                'tasksummary%d' % bugtask.id, bugtask_data['row_id'])
            self.assertEqual(can_delete, bugtask_data['user_can_delete'])

        check_bugtask_data(bug.default_bugtask, False)
        check_bugtask_data(bugtask, True)


class TestBugTaskDeleteView(TestCaseWithFactory):
    """Test the bug task delete form."""

    layer = DatabaseFunctionalLayer

    def test_delete_view_rendering(self):
        # Test the view rendering, including confirmation message, cancel url.
        bug = self.factory.makeBug()
        bugtask = self.factory.makeBugTask(bug=bug)
        bug_url = canonical_url(bugtask.bug, rootsite='bugs')
        # Set up request so that the ReturnToReferrerMixin can correctly
        # extra the referer url.
        server_url = canonical_url(
            getUtility(ILaunchpadRoot), rootsite='bugs')
        extra = {'HTTP_REFERER': bug_url}
        login_person(bugtask.owner)
        view = create_initialized_view(
            bugtask, name='+delete', principal=bugtask.owner,
            server_url=server_url, **extra)
        contents = view.render()
        confirmation_message = find_tag_by_id(
            contents, 'confirmation-message')
        self.assertIsNotNone(confirmation_message)
        self.assertEqual(bug_url, view.cancel_url)

    def test_delete_action(self):
        # Test that the delete action works as expected.
        bug = self.factory.makeBug()
        bugtask = self.factory.makeBugTask(bug=bug)
        bugtask_url = canonical_url(bugtask, rootsite='bugs')
        target_name = bugtask.bugtargetdisplayname
        login_person(bugtask.owner)
        form = {'field.actions.delete_bugtask': 'Delete'}
        extra = {'HTTP_REFERER': bugtask_url}
        server_url = canonical_url(
            getUtility(ILaunchpadRoot), rootsite='bugs')
        view = create_initialized_view(
            bugtask, name='+delete', form=form, server_url=server_url,
            principal=bugtask.owner, **extra)
        self.assertEqual([bug.default_bugtask], bug.bugtasks)
        notifications = view.request.response.notifications
        self.assertEqual(1, len(notifications))
        expected = 'This bug no longer affects %s.' % target_name
        self.assertEqual(expected, notifications[0].message)

    def test_delete_only_bugtask(self):
        # Test that the deleting the only bugtask results in an error message.
        bug = self.factory.makeBug()
        login_person(bug.owner)
        form = {'field.actions.delete_bugtask': 'Delete'}
        view = create_initialized_view(
            bug.default_bugtask, name='+delete', form=form,
            principal=bug.owner)
        self.assertEqual([bug.default_bugtask], bug.bugtasks)
        notifications = view.request.response.notifications
        self.assertEqual(1, len(notifications))
        expected = ('Cannot delete only bugtask affecting: %s.'
            % bug.default_bugtask.target.bugtargetdisplayname)
        self.assertEqual(expected, notifications[0].message)

    def _create_bugtask_to_delete(self):
        bug = self.factory.makeBug()
        bugtask = self.factory.makeBugTask(bug=bug)
        target_name = bugtask.bugtargetdisplayname
        bugtask_url = canonical_url(bugtask, rootsite='bugs')
        return bug, bugtask, target_name, bugtask_url

    def test_ajax_delete_current_bugtask(self):
        # Test that deleting the current bugtask returns a JSON dict
        # containing the URL of the bug's default task to redirect to.
        bug, bugtask, target_name, bugtask_url = (
            self._create_bugtask_to_delete())
        login_person(bugtask.owner)
        # Set up the request so that we correctly simulate an XHR call
        # from the URL of the bugtask we are deleting.
        server_url = canonical_url(
            getUtility(ILaunchpadRoot), rootsite='bugs')
        extra = {
            'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest',
            'HTTP_REFERER': bugtask_url,
            }
        form = {'field.actions.delete_bugtask': 'Delete'}
        view = create_initialized_view(
            bugtask, name='+delete', server_url=server_url, form=form,
            principal=bugtask.owner, **extra)
        result_data = simplejson.loads(view.render())
        self.assertEqual([bug.default_bugtask], bug.bugtasks)
        notifications = simplejson.loads(
            view.request.response.getHeader('X-Lazr-Notifications'))
        self.assertEqual(1, len(notifications))
        expected = 'This bug no longer affects %s.' % target_name
        self.assertEqual(expected, notifications[0][1])
        self.assertEqual(
            'application/json',
            view.request.response.getHeader('content-type'))
        expected_url = canonical_url(bug.default_bugtask, rootsite='bugs')
        self.assertEqual(dict(bugtask_url=expected_url), result_data)

    def test_ajax_delete_only_bugtask(self):
        # Test that deleting the only bugtask returns an empty JSON response
        # with an error notification.
        bug = self.factory.makeBug()
        login_person(bug.owner)
        # Set up the request so that we correctly simulate an XHR call
        # from the URL of the bugtask we are deleting.
        server_url = canonical_url(
            getUtility(ILaunchpadRoot), rootsite='bugs')
        extra = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        form = {'field.actions.delete_bugtask': 'Delete'}
        view = create_initialized_view(
            bug.default_bugtask, name='+delete', server_url=server_url,
            form=form, principal=bug.owner, **extra)
        result_data = simplejson.loads(view.render())
        self.assertEqual([bug.default_bugtask], bug.bugtasks)
        notifications = simplejson.loads(
            view.request.response.getHeader('X-Lazr-Notifications'))
        self.assertEqual(1, len(notifications))
        expected = ('Cannot delete only bugtask affecting: %s.'
            % bug.default_bugtask.target.bugtargetdisplayname)
        self.assertEqual(expected, notifications[0][1])
        self.assertEqual(
            'application/json',
            view.request.response.getHeader('content-type'))
        self.assertEqual(None, result_data)

    def test_ajax_delete_non_current_bugtask(self):
        # Test that deleting the non-current bugtask returns the new bugtasks
        # table as HTML.
        bug, bugtask, target_name, bugtask_url = (
            self._create_bugtask_to_delete())
        default_bugtask_url = canonical_url(
            bug.default_bugtask, rootsite='bugs')
        login_person(bugtask.owner)
        # Set up the request so that we correctly simulate an XHR call
        # from the URL of the default bugtask, not the one we are
        # deleting.
        server_url = canonical_url(
            getUtility(ILaunchpadRoot), rootsite='bugs')
        extra = {
            'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest',
            'HTTP_REFERER': default_bugtask_url,
            }
        form = {'field.actions.delete_bugtask': 'Delete'}
        view = create_initialized_view(
            bugtask, name='+delete', server_url=server_url, form=form,
            principal=bugtask.owner, **extra)
        result_html = view.render()
        self.assertEqual([bug.default_bugtask], bug.bugtasks)
        notifications = view.request.response.notifications
        self.assertEqual(1, len(notifications))
        expected = 'This bug no longer affects %s.' % target_name
        self.assertEqual(expected, notifications[0].message)
        self.assertEqual(
            view.request.response.getHeader('content-type'), 'text/html')
        table = find_tag_by_id(result_html, 'affected-software')
        self.assertIsNotNone(table)
        [row] = table.tbody.findAll('tr', {'class': 'highlight'})
        target_link = row.find('a', {'class': 'sprite product'})
        self.assertIn(
            bug.default_bugtask.bugtargetdisplayname, target_link)


class TestBugTasksAndNominationsViewAlsoAffects(TestCaseWithFactory):
    """Tests the boolean methods on the view used to indicate whether the
       Also Affects... links should be allowed or not. These restrictions
       are only used for proprietary bugs. """

    layer = DatabaseFunctionalLayer

    def _createView(self, bug):
        request = LaunchpadTestRequest()
        return getMultiAdapter(
            (bug, request), name="+bugtasks-and-nominations-portal")

    def test_project_bug_cannot_affect_something_else(self):
        # A bug affecting a project cannot also affect another project or
        # package.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(
            bug_sharing_policy=BugSharingPolicy.PROPRIETARY_OR_PUBLIC)
        bug = self.factory.makeBug(
            target=product, owner=owner,
            information_type=InformationType.PROPRIETARY)
        with person_logged_in(owner):
            view = self._createView(bug)
            self.assertFalse(view.canAddProjectTask())
            self.assertFalse(view.canAddPackageTask())
            bug.transitionToInformationType(InformationType.USERDATA, owner)
            self.assertTrue(view.canAddProjectTask())
            self.assertTrue(view.canAddPackageTask())

    def test_distro_bug_cannot_affect_project(self):
        # A bug affecting a distro cannot also affect another project but it
        # could affect another package.
        distro = self.factory.makeDistribution()
        owner = self.factory.makePerson()
        bug = self.factory.makeBug(
            target=distro, owner=owner,
            information_type=InformationType.PRIVATESECURITY)
        # XXX wgrant 2012-08-30 bug=1041002: Distributions don't have
        # sharing policies yet, so it isn't possible to legitimately create
        # a Proprietary distro bug.
        removeSecurityProxy(bug).information_type = (
            InformationType.PROPRIETARY)
        with person_logged_in(owner):
            view = self._createView(bug)
            self.assertFalse(view.canAddProjectTask())
            self.assertTrue(view.canAddPackageTask())
            bug.transitionToInformationType(InformationType.USERDATA, owner)
            self.assertTrue(view.canAddProjectTask())
            self.assertTrue(view.canAddPackageTask())


class TestBugTaskEditViewStatusField(TestCaseWithFactory):
    """We show only those options as possible value in the status
    field that the user can select.
    """

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBugTaskEditViewStatusField, self).setUp()
        bug_supervisor = self.factory.makePerson(name='bug-supervisor')
        product = self.factory.makeProduct(bug_supervisor=bug_supervisor)
        self.bug = self.factory.makeBug(target=product)

    def getWidgetOptionTitles(self, widget):
        """Return the titles of options of the given choice widget."""
        return [item.value.title for item in widget.field.vocabulary]

    def test_status_field_items_for_anonymous(self):
        # Anonymous users see only the current value.
        login(ANONYMOUS)
        view = BugTaskEditView(
            self.bug.default_bugtask, LaunchpadTestRequest())
        view.initialize()
        self.assertEqual(
            ['New'], self.getWidgetOptionTitles(view.form_fields['status']))

    def test_status_field_items_for_ordinary_users(self):
        # Ordinary users can set the status to all values except Won't fix,
        # Expired, Triaged, Unknown.
        login(NO_PRIVILEGE_EMAIL)
        view = BugTaskEditView(
            self.bug.default_bugtask, LaunchpadTestRequest())
        view.initialize()
        self.assertEqual(
            ['New', 'Incomplete', 'Opinion', 'Invalid', 'Confirmed',
             'In Progress', 'Fix Committed', 'Fix Released'],
            self.getWidgetOptionTitles(view.form_fields['status']))

    def test_status_field_privileged_persons(self):
        # The bug target owner and the bug target supervisor can set
        # the status to any value except Unknown and Expired.
        for user in (
            self.bug.default_bugtask.pillar.owner,
            self.bug.default_bugtask.pillar.bug_supervisor):
            login_person(user)
            view = BugTaskEditView(
                self.bug.default_bugtask, LaunchpadTestRequest())
            view.initialize()
            self.assertEqual(
                ['New', 'Incomplete', 'Opinion', 'Invalid', "Won't Fix",
                 'Confirmed', 'Triaged', 'In Progress', 'Fix Committed',
                 'Fix Released'],
                self.getWidgetOptionTitles(view.form_fields['status']),
                'Unexpected set of settable status options for %s'
                % user.name)

    def test_status_field_bug_task_in_status_unknown(self):
        # If a bugtask has the status Unknown, this status is included
        # in the options.
        owner = self.bug.default_bugtask.pillar.owner
        login_person(owner)
        self.bug.default_bugtask.transitionToStatus(
            BugTaskStatus.UNKNOWN, owner)
        login(NO_PRIVILEGE_EMAIL)
        view = BugTaskEditView(
            self.bug.default_bugtask, LaunchpadTestRequest())
        view.initialize()
        self.assertEqual(
            ['New', 'Incomplete', 'Opinion', 'Invalid', 'Confirmed',
             'In Progress', 'Fix Committed', 'Fix Released', 'Unknown'],
            self.getWidgetOptionTitles(view.form_fields['status']))

    def test_status_field_bug_task_in_status_expired(self):
        # If a bugtask has the status Expired, this status is included
        # in the options.
        removeSecurityProxy(self.bug.default_bugtask)._status = (
            BugTaskStatus.EXPIRED)
        login(NO_PRIVILEGE_EMAIL)
        view = BugTaskEditView(
            self.bug.default_bugtask, LaunchpadTestRequest())
        view.initialize()
        self.assertEqual(
            ['New', 'Incomplete', 'Opinion', 'Invalid', 'Expired',
             'Confirmed', 'In Progress', 'Fix Committed', 'Fix Released'],
            self.getWidgetOptionTitles(view.form_fields['status']))


class TestBugTaskEditViewAssigneeField(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBugTaskEditViewAssigneeField, self).setUp()
        self.owner = self.factory.makePerson()
        self.product = self.factory.makeProduct(owner=self.owner)
        self.bugtask = self.factory.makeBug(
            target=self.product).default_bugtask

    def test_assignee_vocabulary_regular_user_with_bug_supervisor(self):
        # For regular users, the assignee vocabulary is
        # AllUserTeamsParticipation if there is a bug supervisor defined.
        login_person(self.owner)
        self.product.bug_supervisor = self.owner
        login(USER_EMAIL)
        view = BugTaskEditView(self.bugtask, LaunchpadTestRequest())
        view.initialize()
        self.assertEqual(
            'AllUserTeamsParticipation',
            view.form_fields['assignee'].field.vocabularyName)

    def test_assignee_vocabulary_regular_user_without_bug_supervisor(self):
        # For regular users, the assignee vocabulary is
        # ValidAssignee is there is not a bug supervisor defined.
        login_person(self.owner)
        self.product.bug_supervisor = None
        login(USER_EMAIL)
        view = BugTaskEditView(self.bugtask, LaunchpadTestRequest())
        view.initialize()
        self.assertEqual(
            'ValidAssignee',
            view.form_fields['assignee'].field.vocabularyName)

    def test_assignee_field_vocabulary_privileged_user(self):
        # Privileged users, like the bug task target owner, can
        # assign anybody.
        login_person(self.bugtask.target.owner)
        view = BugTaskEditView(self.bugtask, LaunchpadTestRequest())
        view.initialize()
        self.assertEqual(
            'ValidAssignee',
            view.form_fields['assignee'].field.vocabularyName)


class TestBugTaskEditView(TestCaseWithFactory):
    """Test the bug task edit form."""

    layer = DatabaseFunctionalLayer

    def test_retarget_already_exists_error(self):
        user = self.factory.makePerson()
        login_person(user)
        ubuntu = getUtility(ILaunchpadCelebrities).ubuntu
        dsp_1 = self.factory.makeDistributionSourcePackage(
            distribution=ubuntu, sourcepackagename='mouse')
        self.factory.makeSourcePackagePublishingHistory(
            distroseries=ubuntu.currentseries,
            sourcepackagename=dsp_1.sourcepackagename)
        bug_task_1 = self.factory.makeBugTask(target=dsp_1)
        dsp_2 = self.factory.makeDistributionSourcePackage(
            distribution=ubuntu, sourcepackagename='rabbit')
        self.factory.makeSourcePackagePublishingHistory(
            distroseries=ubuntu.currentseries,
            sourcepackagename=dsp_2.sourcepackagename)
        bug_task_2 = self.factory.makeBugTask(
            bug=bug_task_1.bug, target=dsp_2)
        form = {
            'ubuntu_rabbit.actions.save': 'Save Changes',
            'ubuntu_rabbit.status': 'In Progress',
            'ubuntu_rabbit.importance': 'High',
            'ubuntu_rabbit.assignee.option':
                'ubuntu_rabbit.assignee.assign_to_nobody',
            'ubuntu_rabbit.target': 'package',
            'ubuntu_rabbit.target.distribution': 'ubuntu',
            'ubuntu_rabbit.target.package': 'mouse',
            }
        view = create_initialized_view(
            bug_task_2, name='+editstatus', form=form, principal=user)
        self.assertEqual(1, len(view.errors))
        self.assertEqual(
            'A fix for this bug has already been requested for mouse in '
            'Ubuntu',
            view.errors[0])

    def setUpRetargetMilestone(self):
        """Setup a bugtask with a milestone and a product to retarget to."""
        first_product = self.factory.makeProduct(name='bunny')
        with person_logged_in(first_product.owner):
            first_product.official_malone = True
            bug = self.factory.makeBug(target=first_product)
            bug_task = bug.bugtasks[0]
            milestone = self.factory.makeMilestone(
                productseries=first_product.development_focus, name='1.0')
            bug_task.transitionToMilestone(milestone, first_product.owner)
        second_product = self.factory.makeProduct(name='duck')
        with person_logged_in(second_product.owner):
            second_product.official_malone = True
        return bug_task, second_product

    def test_retarget_product_with_milestone(self):
        # Milestones are always cleared when retargeting a product bug task.
        bug_task, second_product = self.setUpRetargetMilestone()
        user = self.factory.makePerson()
        login_person(user)
        form = {
            'bunny.status': 'In Progress',
            'bunny.assignee.option': 'bunny.assignee.assign_to_nobody',
            'bunny.target': 'product',
            'bunny.target.product': 'duck',
            'bunny.actions.save': 'Save Changes',
            }
        view = create_initialized_view(
            bug_task, name='+editstatus', form=form)
        self.assertEqual([], view.errors)
        self.assertEqual(second_product, bug_task.target)
        self.assertEqual(None, bug_task.milestone)
        notifications = view.request.response.notifications
        self.assertEqual(1, len(notifications))
        expected = ('The Bunny 1.0 milestone setting has been removed')
        self.assertTrue(notifications.pop().message.startswith(expected))

    def test_retarget_product_and_assign_milestone(self):
        # Milestones are always cleared when retargeting a product bug task.
        bug_task, second_product = self.setUpRetargetMilestone()
        login_person(bug_task.target.owner)
        milestone_id = bug_task.milestone.id
        bug_task.transitionToMilestone(None, bug_task.target.owner)
        form = {
            'bunny.status': 'In Progress',
            'bunny.assignee.option': 'bunny.assignee.assign_to_nobody',
            'bunny.target': 'product',
            'bunny.target.product': 'duck',
            'bunny.milestone': milestone_id,
            'bunny.actions.save': 'Save Changes',
            }
        view = create_initialized_view(
            bug_task, name='+editstatus', form=form)
        self.assertEqual([], view.errors)
        self.assertEqual(second_product, bug_task.target)
        self.assertEqual(None, bug_task.milestone)
        notifications = view.request.response.notifications
        self.assertEqual(1, len(notifications))
        expected = ('The milestone setting was ignored')
        self.assertTrue(notifications.pop().message.startswith(expected))

    def createNameChangingViewForSourcePackageTask(self, bug_task, new_name):
        login_person(bug_task.owner)
        form_prefix = '%s_%s_%s' % (
            bug_task.target.distroseries.distribution.name,
            bug_task.target.distroseries.name,
            bug_task.target.sourcepackagename.name)
        form = {
            form_prefix + '.sourcepackagename': new_name,
            form_prefix + '.actions.save': 'Save Changes',
            }
        view = create_initialized_view(
            bug_task, name='+editstatus', form=form)
        return view

    def test_retarget_sourcepackage(self):
        # The sourcepackagename of a SourcePackage task can be changed.
        ds = self.factory.makeDistroSeries()
        sp1 = self.factory.makeSourcePackage(distroseries=ds, publish=True)
        sp2 = self.factory.makeSourcePackage(distroseries=ds, publish=True)
        bug_task = self.factory.makeBugTask(target=sp1)

        view = self.createNameChangingViewForSourcePackageTask(
            bug_task, sp2.sourcepackagename.name)
        self.assertEqual([], view.errors)
        self.assertEqual(sp2, bug_task.target)
        notifications = view.request.response.notifications
        self.assertEqual(0, len(notifications))

    def test_retarget_sourcepackage_to_binary_name(self):
        # The sourcepackagename of a SourcePackage task can be changed
        # to a binarypackagename, which gets mapped back to the source.
        ds = self.factory.makeDistroSeries()
        das = self.factory.makeDistroArchSeries(distroseries=ds)
        sp1 = self.factory.makeSourcePackage(distroseries=ds, publish=True)
        # Now create a binary and its corresponding SourcePackage.
        bp = self.factory.makeBinaryPackagePublishingHistory(
            distroarchseries=das)
        bpr = bp.binarypackagerelease
        spn = bpr.build.source_package_release.sourcepackagename
        sp2 = self.factory.makeSourcePackage(
            distroseries=ds, sourcepackagename=spn, publish=True)
        bug_task = self.factory.makeBugTask(target=sp1)

        view = self.createNameChangingViewForSourcePackageTask(
            bug_task, bpr.binarypackagename.name)
        self.assertEqual([], view.errors)
        self.assertEqual(sp2, bug_task.target)
        notifications = view.request.response.notifications
        self.assertEqual(1, len(notifications))
        expected = html_escape(
            "'%s' is a binary package. This bug has been assigned to its "
            "source package '%s' instead."
            % (bpr.binarypackagename.name, spn.name))
        self.assertTrue(notifications.pop().message.startswith(expected))

    def test_retarget_sourcepackage_to_distroseries(self):
        # A SourcePackage task can be changed to a DistroSeries one.
        ds = self.factory.makeDistroSeries()
        sp = self.factory.makeSourcePackage(distroseries=ds, publish=True)
        bug_task = self.factory.makeBugTask(target=sp)

        view = self.createNameChangingViewForSourcePackageTask(
            bug_task, '')
        self.assertEqual([], view.errors)
        self.assertEqual(ds, bug_task.target)
        notifications = view.request.response.notifications
        self.assertEqual(0, len(notifications))


class BugTaskViewTestMixin():

    def _assert_shouldShowStructuralSubscriberWidget(self, show=True):
        view = create_initialized_view(
            self.target, name=u'+bugs', rootsite='bugs')
        self.assertEqual(show, view.shouldShowStructuralSubscriberWidget())

    def _assert_structural_subscriber_label(self, label):
        view = create_initialized_view(
            self.target, name=u'+bugs', rootsite='bugs')
        self.assertEqual(label, view.structural_subscriber_label)

    def test_mustache_cache_is_none_for_feed(self):
        """The mustache model should not be added to JSON cache for feeds."""
        cache = getFeedViewCache(self.target, PersonBugsFeed)
        self.assertIsNone(cache.objects.get('mustache_model'))

    def test_mustache_cache_is_none_for_advanced_form(self):
        """No mustache model for the advanced search form."""
        form = {'advanced': 1}
        view = create_initialized_view(
            self.target, name=u'+bugs', rootsite='bugs', form=form)
        cache = IJSONRequestCache(view.request)
        self.assertIsNone(cache.objects.get('mustache_model'))


class TestPersonBugs(TestCaseWithFactory, BugTaskViewTestMixin):
    """Test the bugs overview page for distributions."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestPersonBugs, self).setUp()
        self.target = self.factory.makePerson()

    def test_shouldShowStructuralSubscriberWidget(self):
        self._assert_shouldShowStructuralSubscriberWidget()

    def test_structural_subscriber_label(self):
        self._assert_structural_subscriber_label(
            'Project, distribution, package, or series subscriber')


class TestDistributionBugs(TestCaseWithFactory, BugTaskViewTestMixin):
    """Test the bugs overview page for distributions."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestDistributionBugs, self).setUp()
        self.target = self.factory.makeDistribution()

    def test_structural_subscriber_label(self):
        self._assert_structural_subscriber_label(
            'Package or series subscriber')

    def test_shouldShowStructuralSubscriberWidget(self):
        self._assert_shouldShowStructuralSubscriberWidget()


class TestDistroSeriesBugs(TestCaseWithFactory, BugTaskViewTestMixin):
    """Test the bugs overview page for distro series."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestDistroSeriesBugs, self).setUp()
        self.target = self.factory.makeDistroSeries()

    def test_shouldShowStructuralSubscriberWidget(self):
        self._assert_shouldShowStructuralSubscriberWidget()

    def test_structural_subscriber_label(self):
        self._assert_structural_subscriber_label('Package subscriber')


class TestDistributionSourcePackageBugs(TestCaseWithFactory,
                                        BugTaskViewTestMixin):
    """Test the bugs overview page for distribution source packages."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestDistributionSourcePackageBugs, self).setUp()
        self.target = self.factory.makeDistributionSourcePackage()

    def test_shouldShowStructuralSubscriberWidget(self):
        self._assert_shouldShowStructuralSubscriberWidget(show=False)


class TestDistroSeriesSourcePackageBugs(TestCaseWithFactory,
                                        BugTaskViewTestMixin):
    """Test the bugs overview page for distro series source packages."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestDistroSeriesSourcePackageBugs, self).setUp()
        self.target = self.factory.makeSourcePackage()

    def test_shouldShowStructuralSubscriberWidget(self):
        self._assert_shouldShowStructuralSubscriberWidget(show=False)


class TestProductBugs(TestCaseWithFactory, BugTaskViewTestMixin):
    """Test the bugs overview page for projects."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestProductBugs, self).setUp()
        self.target = self.factory.makeProduct()

    def test_shouldShowStructuralSubscriberWidget(self):
        self._assert_shouldShowStructuralSubscriberWidget()

    def test_structural_subscriber_label(self):
        self._assert_structural_subscriber_label('Series subscriber')


class TestProductSeriesBugs(TestCaseWithFactory, BugTaskViewTestMixin):
    """Test the bugs overview page for project series."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestProductSeriesBugs, self).setUp()
        self.target = self.factory.makeProductSeries()


class TestProjectGroupBugs(TestCaseWithFactory, BugTaskViewTestMixin):
    """Test the bugs overview page for project groups."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestProjectGroupBugs, self).setUp()
        self.owner = self.factory.makePerson(name='bob')
        self.target = self.factory.makeProject(
            name='container', owner=self.owner)

    def makeSubordinateProduct(self, tracks_bugs_in_lp):
        """Create a new product and add it to the project group."""
        product = self.factory.makeProduct(official_malone=tracks_bugs_in_lp)
        with person_logged_in(product.owner):
            product.project = self.target

    def test_empty_project_group(self):
        # An empty project group does not use Launchpad for bugs.
        view = create_initialized_view(
            self.target, name=u'+bugs', rootsite='bugs')
        self.assertFalse(self.target.hasProducts())
        self.assertFalse(view.should_show_bug_information)

    def test_project_group_with_subordinate_not_using_launchpad(self):
        # A project group with all subordinates not using Launchpad
        # will itself be marked as not using Launchpad for bugs.
        self.makeSubordinateProduct(False)
        self.assertTrue(self.target.hasProducts())
        view = create_initialized_view(
            self.target, name=u'+bugs', rootsite='bugs')
        self.assertFalse(view.should_show_bug_information)

    def test_project_group_with_subordinate_using_launchpad(self):
        # A project group with one subordinate using Launchpad
        # will itself be marked as using Launchpad for bugs.
        self.makeSubordinateProduct(True)
        self.assertTrue(self.target.hasProducts())
        view = create_initialized_view(
            self.target, name=u'+bugs', rootsite='bugs')
        self.assertTrue(view.should_show_bug_information)

    def test_project_group_with_mixed_subordinates(self):
        # A project group with one or more subordinates using Launchpad
        # will itself be marked as using Launchpad for bugs.
        self.makeSubordinateProduct(False)
        self.makeSubordinateProduct(True)
        self.assertTrue(self.target.hasProducts())
        view = create_initialized_view(
            self.target, name=u'+bugs', rootsite='bugs')
        self.assertTrue(view.should_show_bug_information)

    def test_project_group_has_no_portlets_if_not_using_LP(self):
        # A project group that has no projects using Launchpad will not have
        # bug portlets.
        self.makeSubordinateProduct(False)
        view = create_initialized_view(
            self.target, name=u'+bugs', rootsite='bugs', current_request=True)
        self.assertFalse(view.should_show_bug_information)
        contents = view.render()
        report_a_bug = find_tag_by_id(contents, 'bug-portlets')
        self.assertIs(None, report_a_bug)

    def test_project_group_has_portlets_link_if_using_LP(self):
        # A project group that has projects using Launchpad will have a
        # portlets.
        self.makeSubordinateProduct(True)
        view = create_initialized_view(
            self.target, name=u'+bugs', rootsite='bugs', current_request=True)
        self.assertTrue(view.should_show_bug_information)
        contents = view.render()
        report_a_bug = find_tag_by_id(contents, 'bug-portlets')
        self.assertIsNot(None, report_a_bug)

    def test_project_group_has_help_link_if_not_using_LP(self):
        # A project group that has no projects using Launchpad will have
        # a 'Getting started' help link.
        self.makeSubordinateProduct(False)
        view = create_initialized_view(
            self.target, name=u'+bugs', rootsite='bugs', current_request=True)
        contents = view.render()
        help_link = find_tag_by_id(contents, 'getting-started-help')
        self.assertIsNot(None, help_link)

    def test_project_group_has_no_help_link_if_using_LP(self):
        # A project group that has no projects using Launchpad will not have
        # a 'Getting started' help link.
        self.makeSubordinateProduct(True)
        view = create_initialized_view(
            self.target, name=u'+bugs', rootsite='bugs', current_request=True)
        contents = view.render()
        help_link = find_tag_by_id(contents, 'getting-started-help')
        self.assertIs(None, help_link)

    def test_shouldShowStructuralSubscriberWidget(self):
        self._assert_shouldShowStructuralSubscriberWidget()

    def test_structural_subscriber_label(self):
        self._assert_structural_subscriber_label(
            'Project or series subscriber')


class TestBugActivityItem(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setAttribute(self, obj, attribute, value):
        obj_before_modification = Snapshot(obj, providing=providedBy(obj))
        setattr(removeSecurityProxy(obj), attribute, value)
        notify(ObjectModifiedEvent(
            obj, obj_before_modification, [attribute],
            self.factory.makePerson()))

    def test_escapes_assignee(self):
        with celebrity_logged_in('admin'):
            task = self.factory.makeBugTask()
            self.setAttribute(
                task, 'assignee',
                self.factory.makePerson(displayname="Foo &<>", name='foo'))
        self.assertEquals(
            "nobody &#8594; Foo &amp;&lt;&gt; (foo)",
            BugActivityItem(task.bug.activity[-1]).change_details)

    def test_escapes_title(self):
        with celebrity_logged_in('admin'):
            bug = self.factory.makeBug(title="foo")
            self.setAttribute(bug, 'title', "bar &<>")
        self.assertEquals(
            "- foo<br />+ bar &amp;&lt;&gt;",
            BugActivityItem(bug.activity[-1]).change_details)


class TestCommentCollapseVisibility(TestCaseWithFactory):
    """Test for the conditions around display of collapsed/hidden comments."""

    layer = LaunchpadFunctionalLayer

    def makeBugWithComments(self, num_comments):
        """Create and return a bug with a lot of comments and activity."""
        bug = self.factory.makeBug()
        with person_logged_in(bug.owner):
            for i in range(num_comments):
                msg = self.factory.makeMessage(
                    owner=bug.owner, content="Message %i." % i)
                bug.linkMessage(msg, user=bug.owner)
        return bug

    def test_comments_hidden_message_truncation_only(self):
        bug = self.makeBugWithComments(20)
        url = canonical_url(bug.default_bugtask)
        browser = self.getUserBrowser(url=url)
        contents = browser.contents
        self.assertTrue("10 comments hidden" in contents)
        self.assertEqual(1, contents.count('comments hidden'))

    def test_comments_hidden_message_truncation_and_hidden(self):
        bug = self.makeBugWithComments(20)
        url = canonical_url(bug.default_bugtask)

        #Hide a comment
        comments = list(bug.messages)
        removeSecurityProxy(comments[-5]).visible = False

        browser = self.getUserBrowser(url=url)
        contents = browser.contents
        self.assertTrue("10 comments hidden" in browser.contents)
        self.assertTrue("1 comments hidden" in browser.contents)
        self.assertEqual(2, contents.count('comments hidden'))

    def test_comments_hidden_message_truncation_and_hidden_out_of_order(self):
        bug = self.makeBugWithComments(20)
        url = canonical_url(bug.default_bugtask)

        #Hide a comment
        comments = list(bug.messages)
        hidden_comment = comments[-5]
        removeSecurityProxy(hidden_comment).visible = False

        #Mess with ordering. This requires a transaction since the view will
        #re-fetch the comments.
        last_comment = comments[-1]
        removeSecurityProxy(hidden_comment).datecreated += timedelta(1)
        removeSecurityProxy(last_comment).datecreated += timedelta(2)
        transaction.commit()

        browser = self.getUserBrowser(url=url)
        contents = browser.contents
        self.assertTrue("10 comments hidden" in browser.contents)
        self.assertTrue("1 comments hidden" in browser.contents)
        self.assertEqual(2, contents.count('comments hidden'))


class TestBugTaskBatchedCommentsAndActivityView(TestCaseWithFactory):
    """Tests for the BugTaskBatchedCommentsAndActivityView class."""

    layer = LaunchpadFunctionalLayer

    def _makeNoisyBug(self, comments_only=False, number_of_comments=10,
                      number_of_changes=10):
        """Create and return a bug with a lot of comments and activity."""
        bug = self.factory.makeBug()
        with person_logged_in(bug.owner):
            if not comments_only:
                for i in range(number_of_changes):
                    change = BugTaskStatusChange(
                        bug.default_bugtask, UTC_NOW,
                        bug.default_bugtask.product.owner, 'status',
                        BugTaskStatus.NEW, BugTaskStatus.TRIAGED)
                    bug.addChange(change)
            for i in range(number_of_comments):
                msg = self.factory.makeMessage(
                    owner=bug.owner, content="Message %i." % i)
                bug.linkMessage(msg, user=bug.owner)
        return bug

    def _assertThatUnbatchedAndBatchedActivityMatch(self, unbatched_activity,
                                                    batched_activity):
        zipped_activity = zip(unbatched_activity, batched_activity)
        for index, items in enumerate(zipped_activity):
            unbatched_item, batched_item = items
            self.assertEqual(
                unbatched_item['comment'].index,
                batched_item['comment'].index,
                "The comments at index %i don't match. Expected to see "
                "comment %i, got comment %i instead." %
                (index, unbatched_item['comment'].index,
                batched_item['comment'].index))

    def test_offset(self):
        # BugTaskBatchedCommentsAndActivityView.offset returns the
        # current offset being used to select a batch of bug comments
        # and activity. If one is not specified, the offset will be the
        # view's visible_initial_comments count + 1 (so that comments
        # already shown on the page won't appear twice).
        bug_task = self.factory.makeBugTask()
        view = create_initialized_view(bug_task, '+batched-comments')
        self.assertEqual(view.visible_initial_comments + 1, view.offset)
        view = create_initialized_view(
            bug_task, '+batched-comments', form={'offset': 100})
        self.assertEqual(100, view.offset)

    def test_batch_size(self):
        # BugTaskBatchedCommentsAndActivityView.batch_size returns the
        # current batch_size being used to select a batch of bug comments
        # and activity or the default configured batch size if one has
        # not been specified.
        bug_task = self.factory.makeBugTask()
        view = create_initialized_view(bug_task, '+batched-comments')
        self.assertEqual(
            config.malone.comments_list_default_batch_size, view.batch_size)
        view = create_initialized_view(
            bug_task, '+batched-comments', form={'batch_size': 20})
        self.assertEqual(20, view.batch_size)

    def test_event_groups_only_returns_batch_size_results(self):
        # BugTaskBatchedCommentsAndActivityView._event_groups will
        # return only batch_size results.
        bug = self._makeNoisyBug(number_of_comments=20)
        view = create_initialized_view(
            bug.default_bugtask, '+batched-comments',
            form={'batch_size': 10, 'offset': 1})
        self.assertEqual(10, len([group for group in view._event_groups]))

    def test_event_groups_excludes_visible_recent_comments(self):
        # BugTaskBatchedCommentsAndActivityView._event_groups will
        # not return the last view comments - those covered by the
        # visible_recent_comments property.
        bug = self._makeNoisyBug(number_of_comments=20, comments_only=True)
        batched_view = create_initialized_view(
            bug.default_bugtask, '+batched-comments',
            form={'batch_size': 10, 'offset': 10})
        expected_length = 10 - batched_view.visible_recent_comments
        actual_length = len([group for group in batched_view._event_groups])
        self.assertEqual(
            expected_length, actual_length,
            "Expected %i comments, got %i." %
            (expected_length, actual_length))
        unbatched_view = create_initialized_view(
            bug.default_bugtask, '+index', form={'comments': 'all'})
        self._assertThatUnbatchedAndBatchedActivityMatch(
            unbatched_view.activity_and_comments[9:],
            batched_view.activity_and_comments)

    def test_activity_and_comments_matches_unbatched_version(self):
        # BugTaskBatchedCommentsAndActivityView extends BugTaskView in
        # order to add the batching logic and reduce rendering
        # overheads. The results of activity_and_comments is the same
        # for both.
        # We create a bug with comments only so that we can test the
        # contents of activity_and_comments properly. Trying to test it
        # with multiply different datatypes is fragile at best.
        bug = self._makeNoisyBug(comments_only=True, number_of_comments=20)
        # We create a batched view with an offset of 0 so that all the
        # comments are returned.
        batched_view = create_initialized_view(
            bug.default_bugtask, '+batched-comments',
            {'offset': 5, 'batch_size': 10})
        unbatched_view = create_initialized_view(
            bug.default_bugtask, '+index', form={'comments': 'all'})
        # It may look slightly confusing, but it's because the unbatched
        # view's activity_and_comments list is indexed from comment 1,
        # whereas the batched view indexes from zero for ease-of-coding.
        # Comment 0 is the original bug description and so is rarely
        # returned.
        self._assertThatUnbatchedAndBatchedActivityMatch(
            unbatched_view.activity_and_comments[4:],
            batched_view.activity_and_comments)


no_target_specified = object()


def make_bug_task_listing_item(
    factory, bugtask=None, target_context=no_target_specified):
    if bugtask is None:
        owner = factory.makePerson()
        bug = factory.makeBug(
            owner=owner, information_type=InformationType.PRIVATESECURITY)
        with person_logged_in(owner):
            bugtask = bug.default_bugtask
    else:
        owner = bugtask.bug.owner
    bugtask = removeSecurityProxy(bugtask)
    bug_task_set = getUtility(IBugTaskSet)
    bug_badge_properties = bug_task_set.getBugTaskBadgeProperties(
        [bugtask])
    badge_property = bug_badge_properties[bugtask]
    tags = bug_task_set.getBugTaskTags([bugtask])
    if tags != {}:
        tags = tags[bugtask.id]
    people = bug_task_set.getBugTaskPeople([bugtask])
    if target_context is no_target_specified:
        target_context = bugtask.target
    return owner, BugTaskListingItem(
        bugtask,
        badge_property['has_branch'],
        badge_property['has_specification'],
        badge_property['has_patch'],
        tags,
        people,
        target_context=target_context)


class TestBugTaskSearchListingView(BrowserTestCase):

    layer = DatabaseFunctionalLayer

    client_listing = soupmatchers.Tag(
        'client-listing', True, attrs={'id': 'client-listing'})

    def makeView(self, bugtask=None, size=None, memo=None, orderby=None,
                 forwards=True, cookie=None):
        """Make a BugTaskSearchListingView.

        :param bugtask: The task to use for searching.
        :param size: The size of the batches.  Required if forwards is False.
        :param memo: Batch identifier.
        :param orderby: The way to order the batch.
        :param forwards: If true, walk forwards from the memo.  Else walk
            backwards.

        """
        query_vars = {}
        if size is not None:
            query_vars['batch'] = size
        if memo is not None:
            query_vars['memo'] = memo
            if forwards:
                query_vars['start'] = memo
            else:
                query_vars['start'] = int(memo) - size
        if not forwards:
            query_vars['direction'] = 'backwards'
        query_string = urllib.urlencode(query_vars)
        request = LaunchpadTestRequest(
            QUERY_STRING=query_string, orderby=orderby, HTTP_COOKIE=cookie)
        if bugtask is None:
            bugtask = self.factory.makeBugTask()
        view = getMultiAdapter((bugtask.target, request), name='+bugs')
        view.initialize()
        return view

    def invalidate_caches(self, obj):
        store = Store.of(obj)
        store.flush()
        store.invalidate()

    def test_rendered_query_counts_constant_with_many_bugtasks(self):
        product = self.factory.makeProduct()
        url = canonical_url(product, view_name='+bugs')
        bug = self.factory.makeBug(target=product)
        buggy_product = self.factory.makeProduct()
        buggy_url = canonical_url(buggy_product, view_name='+bugs')
        for _ in range(10):
            self.factory.makeBug(target=buggy_product)
        recorder = QueryCollector()
        recorder.register()
        self.addCleanup(recorder.unregister)
        self.invalidate_caches(bug)
        # count with single task
        self.getUserBrowser(url)
        self.assertThat(recorder, HasQueryCount(LessThan(35)))
        # count with many tasks
        self.getUserBrowser(buggy_url)
        self.assertThat(recorder, HasQueryCount(LessThan(35)))

    def test_mustache_model_in_json(self):
        """The IJSONRequestCache should contain mustache_model.

        mustache_model should contain bugtasks, the BugTaskListingItem.model
        for each BugTask.
        """
        owner, item = make_bug_task_listing_item(self.factory)
        self.useContext(person_logged_in(owner))
        view = self.makeView(item.bugtask)
        cache = IJSONRequestCache(view.request)
        items = cache.objects['mustache_model']['items']
        self.assertEqual(1, len(items))
        self.assertEqual(item.model, items[0])

    def test_no_next_prev_for_single_batch(self):
        """The IJSONRequestCache should contain data about ajacent batches.

        mustache_model should contain items, the BugTaskListingItem.model
        for each BugTask.
        """
        owner, item = make_bug_task_listing_item(self.factory)
        self.useContext(person_logged_in(owner))
        view = self.makeView(item.bugtask)
        cache = IJSONRequestCache(view.request)
        self.assertIs(None, cache.objects.get('next'))
        self.assertIs(None, cache.objects.get('prev'))

    def test_next_for_multiple_batch(self):
        """The IJSONRequestCache should contain data about the next batch.

        mustache_model should contain items, the BugTaskListingItem.model
        for each BugTask.
        """
        task = self.factory.makeBugTask()
        self.factory.makeBugTask(target=task.target)
        view = self.makeView(task, size=1)
        cache = IJSONRequestCache(view.request)
        self.assertEqual({'memo': '1', 'start': 1}, cache.objects.get('next'))

    def test_prev_for_multiple_batch(self):
        """The IJSONRequestCache should contain data about the next batch.

        mustache_model should contain items, the BugTaskListingItem.model
        for each BugTask.
        """
        task = self.factory.makeBugTask()
        task2 = self.factory.makeBugTask(target=task.target)
        view = self.makeView(task2, size=1, memo=1)
        cache = IJSONRequestCache(view.request)
        self.assertEqual({'memo': '1', 'start': 0}, cache.objects.get('prev'))

    def test_provides_view_name(self):
        """The IJSONRequestCache should provide the view's name."""
        view = self.makeView()
        cache = IJSONRequestCache(view.request)
        self.assertEqual('+bugs', cache.objects['view_name'])
        person = self.factory.makePerson()
        commentview = getMultiAdapter(
            (person, LaunchpadTestRequest()), name='+commentedbugs')
        commentview.initialize()
        cache = IJSONRequestCache(commentview.request)
        self.assertEqual('+commentedbugs', cache.objects['view_name'])

    def test_default_order_by(self):
        """order_by defaults to '-importance in JSONRequestCache"""
        task = self.factory.makeBugTask()
        view = self.makeView(task)
        cache = IJSONRequestCache(view.request)
        self.assertEqual('-importance', cache.objects['order_by'])

    def test_order_by_importance(self):
        """order_by follows query params in JSONRequestCache"""
        task = self.factory.makeBugTask()
        view = self.makeView(task, orderby='importance')
        cache = IJSONRequestCache(view.request)
        self.assertEqual('importance', cache.objects['order_by'])

    def test_cache_has_all_batch_vars_defaults(self):
        """Cache has all the needed variables.

        order_by, memo, start, forwards.  These default to sane values.
        """
        task = self.factory.makeBugTask()
        view = self.makeView(task)
        cache = IJSONRequestCache(view.request)
        self.assertEqual('-importance', cache.objects['order_by'])
        self.assertIs(None, cache.objects['memo'])
        self.assertEqual(0, cache.objects['start'])
        self.assertTrue(cache.objects['forwards'])
        self.assertEqual(1, cache.objects['total'])

    def test_cache_has_all_batch_vars_specified(self):
        """Cache has all the needed variables.

        order_by, memo, start, forwards.  These are calculated appropriately.
        """
        task = self.factory.makeBugTask()
        view = self.makeView(task, memo=1, forwards=False, size=1)
        cache = IJSONRequestCache(view.request)
        self.assertEqual('1', cache.objects['memo'])
        self.assertEqual(0, cache.objects['start'])
        self.assertFalse(cache.objects['forwards'])
        self.assertEqual(0, cache.objects['last_start'])

    def test_cache_field_visibility(self):
        """Cache contains sane-looking field_visibility values."""
        task = self.factory.makeBugTask()
        view = self.makeView(task, memo=1, forwards=False, size=1)
        cache = IJSONRequestCache(view.request)
        field_visibility = cache.objects['field_visibility']
        self.assertTrue(field_visibility['show_id'])

    def test_cache_cookie_name(self):
        """The cookie name should be in cache for js code access."""
        task = self.factory.makeBugTask()
        view = self.makeView(task, memo=1, forwards=False, size=1)
        cache = IJSONRequestCache(view.request)
        cookie_name = cache.objects['cbl_cookie_name']
        self.assertEqual('anon-buglist-fields', cookie_name)

    def test_cache_field_visibility_matches_cookie(self):
        """Cache contains cookie-matching values for field_visibiliy."""
        task = self.factory.makeBugTask()
        cookie = (
            'anon-buglist-fields=show_datecreated=true&show_reporter=true'
            '&show_id=true&show_targetname=true'
            '&show_milestone_name=true&show_date_last_updated=true'
            '&show_assignee=true&show_heat=true&show_tag=true'
            '&show_importance=true&show_status=true'
            '&show_information_type=true')
        view = self.makeView(
            task, memo=1, forwards=False, size=1, cookie=cookie)
        cache = IJSONRequestCache(view.request)
        field_visibility = cache.objects['field_visibility']
        self.assertTrue(field_visibility['show_tag'])

    def test_exclude_unsupported_cookie_values(self):
        """Cookie values not present in defaults are ignored."""
        task = self.factory.makeBugTask()
        cookie = (
            'anon-buglist-fields=show_datecreated=true&show_reporter=true'
            '&show_id=true&show_targetname=true'
            '&show_milestone_name=true&show_date_last_updated=true'
            '&show_assignee=true&show_heat=true&show_tag=true'
            '&show_importance=true&show_status=true'
            '&show_information_type=true&show_title=true')
        view = self.makeView(
            task, memo=1, forwards=False, size=1, cookie=cookie)
        cache = IJSONRequestCache(view.request)
        field_visibility = cache.objects['field_visibility']
        self.assertNotIn('show_title', field_visibility)

    def test_add_defaults_to_cookie_values(self):
        """Where cookie values are missing, defaults are used"""
        task = self.factory.makeBugTask()
        cookie = (
            'anon-buglist-fields=show_datecreated=true&show_reporter=true'
            '&show_id=true&show_targetname=true'
            '&show_milestone_name=true&show_date_last_updated=true'
            '&show_assignee=true&show_heat=true&show_tag=true'
            '&show_importance=true&show_title=true'
            '&show_information_type=true')
        view = self.makeView(
            task, memo=1, forwards=False, size=1, cookie=cookie)
        cache = IJSONRequestCache(view.request)
        field_visibility = cache.objects['field_visibility']
        self.assertIn('show_status', field_visibility)

    def test_cache_field_visibility_defaults(self):
        """Cache contains sane-looking field_visibility_defaults values."""
        task = self.factory.makeBugTask()
        view = self.makeView(task, memo=1, forwards=False, size=1)
        cache = IJSONRequestCache(view.request)
        field_visibility_defaults = cache.objects['field_visibility_defaults']
        self.assertTrue(field_visibility_defaults['show_id'])

    def getBugtaskBrowser(self, title=None, no_login=False):
        """Return a browser for a new bugtask."""
        bugtask = self.factory.makeBugTask()
        with person_logged_in(bugtask.target.owner):
            bugtask.target.official_malone = True
            if title is not None:
                bugtask.bug.title = title
        browser = self.getViewBrowser(
            bugtask.target, '+bugs', rootsite='bugs', no_login=no_login)
        return bugtask, browser

    def assertHTML(self, browser, *tags, **kwargs):
        """Assert something about a browser's HTML."""
        matcher = soupmatchers.HTMLContains(*tags)
        if kwargs.get('invert', False):
            matcher = Not(matcher)
        self.assertThat(browser.contents, matcher)

    @staticmethod
    def getBugNumberTag(bug_task):
        """Bug numbers with a leading hash are unique to new rendering."""
        bug_number_re = re.compile(r'\#%d' % bug_task.bug.id)
        return soupmatchers.Tag('bugnumber', 'span', text=bug_number_re)

    def test_mustache_rendering(self):
        """If the flag is present, then all mustache features appear."""
        bug_task, browser = self.getBugtaskBrowser()
        bug_number = self.getBugNumberTag(bug_task)
        self.assertHTML(browser, self.client_listing, bug_number)

    def test_mustache_rendering_obfuscation(self):
        """For anonymous users, email addresses are obfuscated."""
        bug_task, browser = self.getBugtaskBrowser(title='a@example.com',
                no_login=True)
        self.assertNotIn('a@example.com', browser.contents)

    def getNavigator(self):
        request = LaunchpadTestRequest()
        navigator = BugListingBatchNavigator([], request, [], 1)
        cache = IJSONRequestCache(request)
        item = {
            'age': 'age1',
            'assignee': 'assignee1',
            'bugtarget': 'bugtarget1',
            'bugtarget_css': 'bugtarget_css1',
            'bug_heat_html': 'bug_heat_html1',
            'bug_url': 'bug_url1',
            'id': '3.14159',
            'importance': 'importance1',
            'importance_class': 'importance_class1',
            'information_type': 'User Data',
            'last_updated': 'updated1',
            'milestone_name': 'milestone_name1',
            'status': 'status1',
            'reporter': 'reporter1',
            'tags': [{'tag': 'tags1'}],
            'tag_urls': [{'url': '', 'tag': 'tags1'}],
            'title': 'title1',
        }
        item.update(navigator.field_visibility)
        cache.objects['mustache_model'] = {
            'items': [item],
        }
        mustache_model = cache.objects['mustache_model']
        return navigator, mustache_model

    def test_hiding_bug_number(self):
        """Hiding a bug number makes it disappear from the page."""
        navigator, mustache_model = self.getNavigator()
        self.assertIn('3.14159', navigator.mustache)
        mustache_model['items'][0]['show_id'] = False
        self.assertNotIn('3.14159', navigator.mustache)

    def test_hiding_status(self):
        """Hiding status makes it disappear from the page."""
        navigator, mustache_model = self.getNavigator()
        self.assertIn('status1', navigator.mustache)
        mustache_model['items'][0]['show_status'] = False
        self.assertNotIn('status1', navigator.mustache)

    def test_hiding_importance(self):
        """Hiding importance removes the text and CSS."""
        navigator, mustache_model = self.getNavigator()
        self.assertIn('importance1', navigator.mustache)
        self.assertIn('importance_class1', navigator.mustache)
        mustache_model['items'][0]['show_importance'] = False
        self.assertNotIn('importance1', navigator.mustache)
        self.assertNotIn('importance_class1', navigator.mustache)

    def test_show_information_type(self):
        """Showing information_type adds the text."""
        navigator, mustache_model = self.getNavigator()
        self.assertNotIn('User Data', navigator.mustache)
        mustache_model['items'][0]['show_information_type'] = True
        self.assertIn('User Data', navigator.mustache)

    def test_hiding_bugtarget(self):
        """Hiding bugtarget removes the text and CSS."""
        navigator, mustache_model = self.getNavigator()
        self.assertIn('bugtarget1', navigator.mustache)
        self.assertIn('bugtarget_css1', navigator.mustache)
        mustache_model['items'][0]['show_targetname'] = False
        self.assertNotIn('bugtarget1', navigator.mustache)
        self.assertNotIn('bugtarget_css1', navigator.mustache)

    def test_hiding_bug_heat(self):
        """Hiding bug heat removes the html and CSS."""
        navigator, mustache_model = self.getNavigator()
        self.assertIn('bug_heat_html1', navigator.mustache)
        self.assertIn('bug-heat-icons', navigator.mustache)
        mustache_model['items'][0]['show_heat'] = False
        self.assertNotIn('bug_heat_html1', navigator.mustache)
        self.assertNotIn('bug-heat-icons', navigator.mustache)

    def test_hiding_milstone_name(self):
        """Showing milestone name shows the text."""
        navigator, mustache_model = self.getNavigator()
        self.assertNotIn('milestone_name1', navigator.mustache)
        mustache_model['items'][0]['show_milestone_name'] = True
        self.assertIn('milestone_name1', navigator.mustache)

    def test_hiding_assignee(self):
        """Showing milestone name shows the text."""
        navigator, mustache_model = self.getNavigator()
        self.assertIn('show_assignee', navigator.field_visibility)
        self.assertNotIn('Assignee: assignee1', navigator.mustache)
        mustache_model['items'][0]['show_assignee'] = True
        self.assertIn('Assignee: assignee1', navigator.mustache)

    def test_hiding_age(self):
        """Showing age shows the text."""
        navigator, mustache_model = self.getNavigator()
        self.assertIn('show_datecreated', navigator.field_visibility)
        self.assertNotIn('age1', navigator.mustache)
        mustache_model['items'][0]['show_datecreated'] = True
        self.assertIn('age1', navigator.mustache)

    def test_hiding_tags(self):
        """Showing tags shows the text."""
        navigator, mustache_model = self.getNavigator()
        self.assertIn('show_tag', navigator.field_visibility)
        self.assertNotIn('tags1', navigator.mustache)
        mustache_model['items'][0]['show_tag'] = True
        self.assertIn('tags1', navigator.mustache)

    def test_hiding_reporter(self):
        """Showing reporter shows the text."""
        navigator, mustache_model = self.getNavigator()
        self.assertIn('show_reporter', navigator.field_visibility)
        self.assertNotIn('Reporter: reporter1', navigator.mustache)
        mustache_model['items'][0]['show_reporter'] = True
        self.assertIn('Reporter: reporter1', navigator.mustache)

    def test_hiding_last_updated(self):
        """Showing last_updated shows the text."""
        navigator, mustache_model = self.getNavigator()
        self.assertIn('show_date_last_updated', navigator.field_visibility)
        self.assertNotIn('Last updated updated1', navigator.mustache)
        mustache_model['items'][0]['show_date_last_updated'] = True
        self.assertIn('Last updated updated1', navigator.mustache)

    def test_sort_keys_in_json_cache(self):
        # The JSON cache of a search listing view provides a sequence
        # that describes all sort orders implemented by
        # BugTaskSet.search() and no sort orders that are not implemented.
        view = self.makeView()
        cache = IJSONRequestCache(view.request)
        json_sort_keys = cache.objects['sort_keys']
        json_sort_keys = set(key[0] for key in json_sort_keys)
        valid_keys = set(orderby_expression.keys())
        self.assertEqual(
            valid_keys, json_sort_keys,
            "Existing sort order values not available in JSON cache: %r; "
            "keys present in JSON cache but not defined: %r"
            % (valid_keys - json_sort_keys, json_sort_keys - valid_keys))

    def test_sort_keys_in_json_cache_data(self):
        # The entry 'sort_keys' in the JSON cache of a search listing
        # view is a sequence of 3-tuples (name, title, order), where
        # order is one of the string 'asc' or 'desc'.
        view = self.makeView()
        cache = IJSONRequestCache(view.request)
        json_sort_keys = cache.objects['sort_keys']
        for key in json_sort_keys:
            self.assertEqual(
                3, len(key), 'Invalid key length: %r' % (key, ))
            self.assertTrue(
                key[2] in ('asc', 'desc'),
                'Invalid order value: %r' % (key, ))

    def test_tags_encoded_in_model(self):
        # The tag name is encoded properly in the JSON.
        product = self.factory.makeProduct(name='foobar')
        bug = self.factory.makeBug(target=product, tags=['depends-on+987'])
        view = self.makeView(bugtask=bug.default_bugtask)
        cache = IJSONRequestCache(view.request)
        tags = cache.objects['mustache_model']['items'][0]['tags']
        expected_url = (
            canonical_url(product, view_name='+bugs') +
            '/?field.tag=depends-on%2B987')
        self.assertEqual(
            [{'url': expected_url, 'tag': u'depends-on+987'}], tags)


class TestBugTaskExpirableListingView(BrowserTestCase):
    """Test BugTaskExpirableListingView."""

    layer = LaunchpadFunctionalLayer

    def test_dynamic_bugs_expirable(self):
        """With dynamic listings enabled, expirable bugs listing works."""
        product = self.factory.makeProduct(official_malone=True)
        with person_logged_in(product.owner):
            product.enable_bug_expiration = True
        bug = self.factory.makeBug(
            target=product,
            status=BugTaskStatusSearch.INCOMPLETE_WITHOUT_RESPONSE)
        title = bug.title
        content = self.getMainContent(
            bug.default_bugtask.target, "+expirable-bugs")
        self.assertIn(title, str(content))


class TestBugListingBatchNavigator(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_mustache_listings_escaped(self):
        """Mustache template is encoded such that it has no unescaped tags."""
        navigator = BugListingBatchNavigator(
            [], LaunchpadTestRequest(), [], 0)
        self.assertNotIn('<', navigator.mustache_listings)
        self.assertNotIn('>', navigator.mustache_listings)


class TestBugTaskListingItem(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_model(self):
        """Model contains expected fields with expected values."""
        owner, item = make_bug_task_listing_item(self.factory)
        with person_logged_in(owner):
            model = item.model
            self.assertEqual('Undecided', model['importance'])
            self.assertEqual('importanceUNDECIDED', model['importance_class'])
            self.assertEqual('New', model['status'])
            self.assertEqual('statusNEW', model['status_class'])
            self.assertEqual(
                item.bug.information_type.title, model['information_type'])
            self.assertEqual(item.bug.title, model['title'])
            self.assertEqual(item.bug.id, model['id'])
            self.assertEqual(canonical_url(item.bugtask), model['bug_url'])
            self.assertEqual(item.bugtargetdisplayname, model['bugtarget'])
            self.assertEqual('sprite product', model['bugtarget_css'])
            self.assertEqual(item.bug_heat_html, model['bug_heat_html'])
            expected = ('<span alt="%s" title="%s" class="sprite private">'
                        '</span>') % (
                           InformationType.PRIVATESECURITY.title,
                           InformationType.PRIVATESECURITY.description,
                            )
            self.assertTextMatchesExpressionIgnoreWhitespace(
                expected, model['badges'])
            self.assertEqual(None, model['milestone_name'])
            item.bugtask.milestone = self.factory.makeMilestone(
                product=item.bugtask.target)
            milestone_name = item.milestone.displayname
            self.assertEqual(milestone_name, item.model['milestone_name'])

    def test_tag_urls_use_view_context(self):
        """urls contain the correct project group if target_context is None"""
        project_group = self.factory.makeProject()
        product = self.factory.makeProduct(project=project_group)
        bug = self.factory.makeBug(target=product)
        with person_logged_in(bug.owner):
            bug.tags = ['foo']
        owner, item = make_bug_task_listing_item(
            self.factory, bug.default_bugtask, target_context=project_group)
        url = item.model['tags'][0]['url']
        self.assertTrue(url.startswith(
            canonical_url(project_group, view_name="+bugs")))

    def test_urls_without_target_context(self):
        """urls contain the project if target_context is not None"""
        product = self.factory.makeProduct()
        bug = self.factory.makeBug(target=product)
        with person_logged_in(bug.owner):
            bug.tags = ['foo']
        owner, item = make_bug_task_listing_item(
            self.factory, bug.default_bugtask, target_context=None)
        url = item.model['tags'][0]['url']
        self.assertTrue(url.startswith(
            canonical_url(product, view_name="+bugs")))

    def test_model_assignee(self):
        """Model contains expected fields with expected values."""
        assignee = self.factory.makePerson(displayname='Example Person')
        bug = self.factory.makeBug()
        with person_logged_in(bug.owner):
            removeSecurityProxy(bug).default_bugtask.transitionToAssignee(
                assignee)
        owner, item = make_bug_task_listing_item(
            self.factory, bugtask=bug.default_bugtask)
        with person_logged_in(owner):
            self.assertEqual('Example Person', item.model['assignee'])

    def test_model_age(self):
        """Model contains bug age."""
        owner, item = make_bug_task_listing_item(self.factory)
        bug = removeSecurityProxy(item.bug)
        bug.datecreated = datetime.now(UTC) - timedelta(3, 0, 0)
        with person_logged_in(owner):
            self.assertEqual('3 days old', item.model['age'])

    def test_model_tags(self):
        """Model contains bug tags."""
        bug = self.factory.makeBug()
        tags = ['tag1', 'tag2']
        removeSecurityProxy(bug).tags = tags
        owner, item = make_bug_task_listing_item(
            self.factory, bug.default_bugtask)
        with person_logged_in(owner):
            self.assertEqual(2, len(item.model['tags']))
            self.assertTrue('tag' in item.model['tags'][0].keys())
            self.assertTrue('url' in item.model['tags'][0].keys())
            self.assertTrue('field.tag' in item.model['tags'][0]['url'])

    def test_model_reporter(self):
        """Model contains bug reporter."""
        owner, item = make_bug_task_listing_item(self.factory)
        with person_logged_in(owner):
            self.assertEqual(owner.displayname, item.model['reporter'])

    def test_model_last_updated_date_last_updated(self):
        """last_updated uses date_last_updated if newer."""
        owner, item = make_bug_task_listing_item(self.factory)
        with person_logged_in(owner):
            bug = removeSecurityProxy(item.bug)
            bug.date_last_updated = datetime(2001, 1, 1, tzinfo=UTC)
            bug.date_last_message = datetime(2000, 1, 1, tzinfo=UTC)
            self.assertEqual(
                'on 2001-01-01', item.model['last_updated'])

    def test_model_last_updated_date_last_message(self):
        """last_updated uses date_last_message if newer."""
        owner, item = make_bug_task_listing_item(self.factory)
        with person_logged_in(owner):
            bug = removeSecurityProxy(item.bug)
            bug.date_last_updated = datetime(2000, 1, 1, tzinfo=UTC)
            bug.date_last_message = datetime(2001, 1, 1, tzinfo=UTC)
            self.assertEqual(
                'on 2001-01-01', item.model['last_updated'])
