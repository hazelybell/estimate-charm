# Copyright 2010-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from datetime import (
    datetime,
    timedelta,
    )
from operator import attrgetter
import unittest

import pytz
from storm.expr import Or
from testtools.matchers import Equals
from testtools.testcase import ExpectedException
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.app.interfaces.services import IService
from lp.bugs.errors import InvalidSearchParameters
from lp.bugs.interfaces.bugattachment import BugAttachmentType
from lp.bugs.interfaces.bugtarget import IBugTarget
from lp.bugs.interfaces.bugtask import (
    BugTaskImportance,
    BugTaskStatus,
    BugTaskStatusSearch,
    IBugTaskSet,
    )
from lp.bugs.interfaces.bugtasksearch import (
    BugBlueprintSearch,
    BugBranchSearch,
    BugTaskSearchParams,
    )
from lp.bugs.model.bug import Bug
from lp.bugs.model.bugsummary import BugSummary
from lp.bugs.model.bugtask import BugTask
from lp.bugs.model.bugtaskflat import BugTaskFlat
from lp.bugs.model.bugtasksearch import (
    _build_status_clause,
    _build_tag_search_clause,
    _process_order_by,
    get_bug_bulk_privacy_filter_terms,
    get_bug_privacy_filter_terms,
    )
from lp.hardwaredb.interfaces.hwdb import (
    HWBus,
    IHWDeviceSet,
    )
from lp.registry.enums import SharingPermission
from lp.registry.interfaces.distribution import (
    IDistribution,
    IDistributionSet,
    )
from lp.registry.interfaces.distributionsourcepackage import (
    IDistributionSourcePackage,
    )
from lp.registry.interfaces.distroseries import IDistroSeries
from lp.registry.interfaces.person import (
    IPerson,
    IPersonSet,
    )
from lp.registry.interfaces.product import IProduct
from lp.registry.interfaces.sourcepackage import ISourcePackage
from lp.registry.model.person import Person
from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import convert_storm_clause_to_string
from lp.services.searchbuilder import (
    all,
    any,
    greater_than,
    not_equals,
    )
from lp.soyuz.interfaces.archive import ArchivePurpose
from lp.soyuz.interfaces.component import IComponentSet
from lp.soyuz.interfaces.publishing import PackagePublishingStatus
from lp.testing import (
    admin_logged_in,
    login_person,
    logout,
    normalize_whitespace,
    person_logged_in,
    StormStatementRecorder,
    TestCase,
    TestCaseWithFactory,
    )
from lp.testing.dbuser import dbuser
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    )
from lp.testing.matchers import HasQueryCount


class TestProcessOrderBy(TestCase):

    def assertOrderForParams(self, expected, user=None, product=None,
                             distribution=None, **kwargs):
        params = BugTaskSearchParams(user, **kwargs)
        if product:
            params.setProduct(product)
        if distribution:
            params.setProduct(distribution)
        self.assertEqual(
            expected,
            convert_storm_clause_to_string(_process_order_by(params)[0]))

    def test_tiebreaker(self):
        # Requests for ambiguous sorts get a disambiguator of BugTask.id
        # glued on.
        self.assertOrderForParams(
            'BugTaskFlat.importance DESC, BugTaskFlat.bugtask',
            orderby='-importance')

    def test_tiebreaker_direction(self):
        # The tiebreaker direction is the reverse of the primary
        # direction. This is mostly to retain the old default sort order
        # of (-importance, bugtask), and could probably be reversed if
        # someone wants to.
        self.assertOrderForParams(
            'BugTaskFlat.importance, BugTaskFlat.bugtask DESC',
            orderby='importance')

    def test_tiebreaker_in_unique_context(self):
        # The tiebreaker is Bug.id if the context is unique, so we'll
        # find no more than a single task for each bug. This applies to
        # searches within a product, distribution source package, or
        # source package.
        self.assertOrderForParams(
            'BugTaskFlat.importance DESC, BugTaskFlat.bug',
            orderby='-importance',
            product='foo')

    def test_tiebreaker_in_duplicated_context(self):
        # If the context can have multiple tasks for a single bug, we
        # still use BugTask.id.
        self.assertOrderForParams(
            'BugTaskFlat.importance DESC, BugTaskFlat.bug',
            orderby='-importance',
            distribution='foo')


class SearchTestBase:

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(SearchTestBase, self).setUp()
        self.bugtask_set = getUtility(IBugTaskSet)

    def assertSearchFinds(self, params, expected_bugtasks):
        # Run a search for the given search parameters and check if
        # the result matches the expected bugtasks.
        search_result = self.runSearch(params)
        expected = self.resultValuesForBugtasks(expected_bugtasks)
        self.assertEqual(expected, search_result)

    def subscribeToTarget(self, subscriber):
        # Subscribe the given person to the search target.
        with person_logged_in(subscriber):
            self.searchtarget.addSubscription(
                subscriber, subscribed_by=subscriber)


class OnceTests:
    """A mixin class with tests that don't need to be run for all targets."""

    def test_private_bug_in_search_result_anonymous_users(self):
        # Private bugs are not included in search results for anonymous users.
        with person_logged_in(self.owner):
            self.bugtasks[-1].bug.setPrivate(True, self.owner)
        params = self.getBugTaskSearchParams(user=None)
        self.assertSearchFinds(params, self.bugtasks[:-1])

    def test_private_bug_in_search_result_unauthorised_users(self):
        # Private bugs are not included in search results for ordinary users.
        with person_logged_in(self.owner):
            self.bugtasks[-1].bug.setPrivate(True, self.owner)
        user = self.factory.makePerson()
        params = self.getBugTaskSearchParams(user=user)
        self.assertSearchFinds(params, self.bugtasks[:-1])

    def test_private_bug_in_search_result_subscribers(self):
        # If the user is subscribed to the bug, it is included in the
        # search result.
        with person_logged_in(self.owner):
            self.bugtasks[-1].bug.setPrivate(True, self.owner)
        user = self.factory.makePerson()
        admin = getUtility(IPersonSet).getByEmail('foo.bar@canonical.com')
        with person_logged_in(admin):
            bug = self.bugtasks[-1].bug
            bug.subscribe(user, self.owner)
        params = self.getBugTaskSearchParams(user=user)
        self.assertSearchFinds(params, self.bugtasks)

    def test_private_bug_in_search_result_admins(self):
        # Private bugs are included in search results for admins.
        with person_logged_in(self.owner):
            self.bugtasks[-1].bug.setPrivate(True, self.owner)
        admin = getUtility(IPersonSet).getByEmail('foo.bar@canonical.com')
        params = self.getBugTaskSearchParams(user=admin)
        self.assertSearchFinds(params, self.bugtasks)

    def test_search_by_bug_reporter(self):
        # Search results can be limited to bugs filed by a given person.
        bugtask = self.bugtasks[0]
        reporter = bugtask.bug.owner
        params = self.getBugTaskSearchParams(
            user=None, bug_reporter=reporter)
        self.assertSearchFinds(params, [bugtask])

    def test_search_by_bug_commenter(self):
        # Search results can be limited to bugs having a comment from a
        # given person.
        # Note that this does not include the bug description (which is
        # stored as the first comment of a bug.) Hence, if we let the
        # reporter of our first test bug comment on the second test bug,
        # a search for bugs having comments from this person retruns only
        # the second bug.
        commenter = self.bugtasks[0].bug.owner
        expected = self.bugtasks[1]
        with person_logged_in(commenter):
            expected.bug.newMessage(owner=commenter, content='a comment')
        params = self.getBugTaskSearchParams(
            user=None, bug_commenter=commenter)
        self.assertSearchFinds(params, [expected])

    def test_search_by_person_affected_by_bug(self):
        # Search results can be limited to bugs which affect a given person.
        affected_user = self.factory.makePerson()
        expected = self.bugtasks[0]
        with person_logged_in(affected_user):
            expected.bug.markUserAffected(affected_user)
        params = self.getBugTaskSearchParams(
            user=None, affected_user=affected_user)
        self.assertSearchFinds(params, [expected])

    def test_search_by_bugtask_assignee(self):
        # Search results can be limited to bugtask assigned to a given
        # person.
        assignee = self.factory.makePerson()
        expected = self.bugtasks[0]
        with person_logged_in(assignee):
            expected.transitionToAssignee(assignee)
        params = self.getBugTaskSearchParams(user=None, assignee=assignee)
        self.assertSearchFinds(params, [expected])

    def test_search_by_bug_subscriber(self):
        # Search results can be limited to bugs to which a given person
        # is subscribed.
        subscriber = self.factory.makePerson()
        expected = self.bugtasks[0]
        with person_logged_in(subscriber):
            expected.bug.subscribe(subscriber, subscribed_by=subscriber)
        params = self.getBugTaskSearchParams(user=None, subscriber=subscriber)
        self.assertSearchFinds(params, [expected])

    def test_search_by_bug_attachment(self):
        # Search results can be limited to bugs having attachments of
        # a given type.
        with person_logged_in(self.owner):
            self.bugtasks[0].bug.addAttachment(
                owner=self.owner, data='filedata', comment='a comment',
                filename='file1.txt', is_patch=False)
            self.bugtasks[1].bug.addAttachment(
                owner=self.owner, data='filedata', comment='a comment',
                filename='file1.txt', is_patch=True)
        # We can search for bugs with non-patch attachments...
        params = self.getBugTaskSearchParams(
            user=None, attachmenttype=BugAttachmentType.UNSPECIFIED)
        self.assertSearchFinds(params, self.bugtasks[:1])
        # ... for bugs with patches...
        params = self.getBugTaskSearchParams(
            user=None, attachmenttype=BugAttachmentType.PATCH)
        self.assertSearchFinds(params, self.bugtasks[1:2])
        # and for bugs with patches or attachments
        params = self.getBugTaskSearchParams(
            user=None, attachmenttype=any(
                BugAttachmentType.PATCH,
                BugAttachmentType.UNSPECIFIED))
        self.assertSearchFinds(params, self.bugtasks[:2])

    def setUpFullTextSearchTests(self):
        # Set text fields indexed by Bug.fti, or
        # MessageChunk.fti to values we can search for.
        for bugtask, number in zip(self.bugtasks, ('one', 'two', 'three')):
            commenter = self.bugtasks[0].bug.owner
            with person_logged_in(commenter):
                bugtask.bug.title = 'bug title %s' % number
                bugtask.bug.newMessage(
                    owner=commenter, content='comment %s' % number)

    def test_fulltext_search(self):
        # Full text searches find text indexed by Bug.fti.
        self.setUpFullTextSearchTests()
        params = self.getBugTaskSearchParams(
            user=None, searchtext=u'one title')
        self.assertSearchFinds(params, self.bugtasks[:1])

    def test_fast_fulltext_search(self):
        # Fast full text searches find text indexed by Bug.fti...
        # Note that a valid tsquery expression with stemmed words must
        # be specified.
        self.setUpFullTextSearchTests()
        params = self.getBugTaskSearchParams(
            user=None, fast_searchtext=u'one&titl')
        self.assertSearchFinds(params, self.bugtasks[:1])

    def test_tags(self):
        # Search results can be limited to bugs having given tags.
        with person_logged_in(self.owner):
            self.bugtasks[0].bug.tags = ['tag1', 'tag2']
            self.bugtasks[1].bug.tags = ['tag1', 'tag3']
        params = self.getBugTaskSearchParams(
            user=None, tag=any('tag2', 'tag3'))
        self.assertSearchFinds(params, self.bugtasks[:2])

        params = self.getBugTaskSearchParams(
            user=None, tag=all('tag2', 'tag3'))
        self.assertSearchFinds(params, [])

        params = self.getBugTaskSearchParams(
            user=None, tag=all('tag1', 'tag3'))
        self.assertSearchFinds(params, self.bugtasks[1:2])

        params = self.getBugTaskSearchParams(
            user=None, tag=all('tag1', '-tag3'))
        self.assertSearchFinds(params, self.bugtasks[:1])

        params = self.getBugTaskSearchParams(
            user=None, tag=all('-tag1'))
        self.assertSearchFinds(params, self.bugtasks[2:])

        params = self.getBugTaskSearchParams(
            user=None, tag=all('*'))
        self.assertSearchFinds(params, self.bugtasks[:2])

        params = self.getBugTaskSearchParams(
            user=None, tag=all('-*'))
        self.assertSearchFinds(params, self.bugtasks[2:])

    def test_date_closed(self):
        # Search results can be filtered by the date_closed time
        # of a bugtask.
        with person_logged_in(self.owner):
            self.bugtasks[2].transitionToStatus(
                BugTaskStatus.FIXRELEASED, self.owner)
        utc_now = datetime.now(pytz.timezone('UTC'))
        self.assertTrue(utc_now >= self.bugtasks[2].date_closed)
        params = self.getBugTaskSearchParams(
            user=None, date_closed=greater_than(utc_now - timedelta(days=1)))
        self.assertSearchFinds(params, self.bugtasks[2:])
        params = self.getBugTaskSearchParams(
            user=None, date_closed=greater_than(utc_now + timedelta(days=1)))
        self.assertSearchFinds(params, [])

    def test_created_since(self):
        # Search results can be limited to bugtasks created after a
        # given time.
        one_day_ago = self.bugtasks[0].datecreated - timedelta(days=1)
        two_days_ago = self.bugtasks[0].datecreated - timedelta(days=2)
        with person_logged_in(self.owner):
            self.bugtasks[0].datecreated = two_days_ago
        params = self.getBugTaskSearchParams(
            user=None, created_since=one_day_ago)
        self.assertSearchFinds(params, self.bugtasks[1:])

    def test_created_before(self):
        # Search results can be limited to bugtasks created before a
        # given time.
        one_day_ago = self.bugtasks[0].datecreated - timedelta(days=1)
        two_days_ago = self.bugtasks[0].datecreated - timedelta(days=2)
        with person_logged_in(self.owner):
            self.bugtasks[0].datecreated = two_days_ago
        params = self.getBugTaskSearchParams(
            user=None, created_before=one_day_ago)
        self.assertSearchFinds(params, self.bugtasks[:1])

    def test_modified_since(self):
        # Search results can be limited to bugs modified after a
        # given time.
        one_day_ago = (
            self.bugtasks[0].bug.date_last_updated - timedelta(days=1))
        two_days_ago = (
            self.bugtasks[0].bug.date_last_updated - timedelta(days=2))
        bug = self.bugtasks[0].bug
        removeSecurityProxy(bug).date_last_updated = two_days_ago
        params = self.getBugTaskSearchParams(
            user=None, modified_since=one_day_ago)
        self.assertSearchFinds(params, self.bugtasks[1:])

    def test_branches_linked(self):
        # Search results can be limited to bugs with or without linked
        # branches.
        with person_logged_in(self.owner):
            branch = self.factory.makeBranch()
            self.bugtasks[0].bug.linkBranch(branch, self.owner)
        params = self.getBugTaskSearchParams(
            user=None, linked_branches=BugBranchSearch.BUGS_WITH_BRANCHES)
        self.assertSearchFinds(params, self.bugtasks[:1])
        params = self.getBugTaskSearchParams(
            user=None, linked_branches=BugBranchSearch.BUGS_WITHOUT_BRANCHES)
        self.assertSearchFinds(params, self.bugtasks[1:])

    def test_blueprints_linked(self):
        # Search results can be limited to bugs with or without linked
        # blueprints.
        with person_logged_in(self.owner):
            blueprint = self.factory.makeSpecification()
            blueprint.linkBug(self.bugtasks[0].bug)
        params = self.getBugTaskSearchParams(
            user=None, linked_blueprints=(
                BugBlueprintSearch.BUGS_WITH_BLUEPRINTS))
        self.assertSearchFinds(params, self.bugtasks[:1])
        params = self.getBugTaskSearchParams(
            user=None, linked_blueprints=(
                BugBlueprintSearch.BUGS_WITHOUT_BLUEPRINTS))
        self.assertSearchFinds(params, self.bugtasks[1:])

    def test_limit_search_to_one_bug(self):
        # Search results can be limited to a given bug.
        params = self.getBugTaskSearchParams(
            user=None, bug=self.bugtasks[0].bug)
        self.assertSearchFinds(params, self.bugtasks[:1])
        other_bug = self.factory.makeBug()
        params = self.getBugTaskSearchParams(user=None, bug=other_bug)
        self.assertSearchFinds(params, [])

    def test_filter_by_status(self):
        # Search results can be limited to bug tasks with a given status.
        params = self.getBugTaskSearchParams(
            user=None, status=BugTaskStatus.FIXCOMMITTED)
        self.assertSearchFinds(params, self.bugtasks[2:])
        params = self.getBugTaskSearchParams(
            user=None, status=any(BugTaskStatus.NEW, BugTaskStatus.TRIAGED))
        self.assertSearchFinds(params, self.bugtasks[:2])
        params = self.getBugTaskSearchParams(
            user=None, status=BugTaskStatus.WONTFIX)
        self.assertSearchFinds(params, [])

    def test_filter_by_importance(self):
        # Search results can be limited to bug tasks with a given importance.
        params = self.getBugTaskSearchParams(
            user=None, importance=BugTaskImportance.HIGH)
        self.assertSearchFinds(params, self.bugtasks[:1])
        params = self.getBugTaskSearchParams(
            user=None,
            importance=any(BugTaskImportance.HIGH, BugTaskImportance.LOW))
        self.assertSearchFinds(params, self.bugtasks[:2])
        params = self.getBugTaskSearchParams(
            user=None, importance=BugTaskImportance.MEDIUM)
        self.assertSearchFinds(params, [])

    def test_filter_by_information_types(self):
        # Search results can be filtered by information_type.
        with person_logged_in(self.owner):
            self.bugtasks[2].bug.transitionToInformationType(
                InformationType.PRIVATESECURITY, self.owner)
        params = self.getBugTaskSearchParams(
            user=self.owner,
            information_type=InformationType.PRIVATESECURITY)
        self.assertSearchFinds(params, [self.bugtasks[2]])
        params = self.getBugTaskSearchParams(
            user=self.owner,
            information_type=InformationType.PUBLICSECURITY)
        self.assertSearchFinds(params, [])

    def test_omit_duplicate_bugs(self):
        # Duplicate bugs can optionally be excluded from search results.
        # The default behaviour is to include duplicates.
        duplicate_bug = self.bugtasks[0].bug
        master_bug = self.bugtasks[1].bug
        with person_logged_in(self.owner):
            duplicate_bug.markAsDuplicate(master_bug)
        params = self.getBugTaskSearchParams(user=None)
        self.assertSearchFinds(params, self.bugtasks)
        # If we explicitly pass the parameter omit_duplicates=False, we get
        # the same result.
        params = self.getBugTaskSearchParams(user=None, omit_dupes=False)
        self.assertSearchFinds(params, self.bugtasks)
        # If omit_duplicates is set to True, the first task bug is omitted.
        params = self.getBugTaskSearchParams(user=None, omit_dupes=True)
        self.assertSearchFinds(params, self.bugtasks[1:])

    def test_has_cve(self):
        # Search results can be limited to bugs linked to a CVE.
        with person_logged_in(self.owner):
            cve = self.factory.makeCVE('2010-0123')
            self.bugtasks[0].bug.linkCVE(cve, self.owner)
        params = self.getBugTaskSearchParams(user=None, has_cve=True)
        self.assertSearchFinds(params, self.bugtasks[:1])

    def test_sort_by_milestone_name(self):
        expected = self.setUpMilestoneSorting()
        params = self.getBugTaskSearchParams(
            user=None, orderby='milestone_name')
        self.assertSearchFinds(params, expected)
        expected.reverse()
        params = self.getBugTaskSearchParams(
            user=None, orderby='-milestone_name')
        self.assertSearchFinds(params, expected)

    def test_sort_by_bug_reporter(self):
        params = self.getBugTaskSearchParams(user=None, orderby='reporter')
        expected = sorted(self.bugtasks, key=lambda task: task.bug.owner.name)
        self.assertSearchFinds(params, expected)
        expected.reverse()
        params = self.getBugTaskSearchParams(user=None, orderby='-reporter')
        self.assertSearchFinds(params, expected)

    def test_sort_by_bug_assignee(self):
        with person_logged_in(self.owner):
            self.bugtasks[2].transitionToAssignee(
                self.factory.makePerson(name="assignee-1"))
            self.bugtasks[1].transitionToAssignee(
                self.factory.makePerson(name="assignee-2"))
        expected = [self.bugtasks[2], self.bugtasks[1], self.bugtasks[0]]
        params = self.getBugTaskSearchParams(user=None, orderby='assignee')
        self.assertSearchFinds(params, expected)
        expected.reverse()
        params = self.getBugTaskSearchParams(user=None, orderby='-assignee')
        self.assertSearchFinds(params, expected)

    def test_sort_by_bug_title(self):
        params = self.getBugTaskSearchParams(user=None, orderby='title')
        expected = sorted(self.bugtasks, key=lambda task: task.bug.title)
        self.assertSearchFinds(params, expected)
        expected.reverse()
        params = self.getBugTaskSearchParams(user=None, orderby='-title')
        self.assertSearchFinds(params, expected)

    def test_sort_by_tag(self):
        with person_logged_in(self.owner):
            self.bugtasks[2].bug.tags = ['tag-a', 'tag-d']
            self.bugtasks[1].bug.tags = ['tag-b', 'tag-c']
        params = self.getBugTaskSearchParams(user=None, orderby='tag')
        expected = [self.bugtasks[2], self.bugtasks[1], self.bugtasks[0]]
        self.assertSearchFinds(params, expected)
        expected.reverse()
        params = self.getBugTaskSearchParams(user=None, orderby='-tag')
        self.assertSearchFinds(params, expected)

    def test_sort_by_linked_specification(self):
        with person_logged_in(self.owner):
            spec_1 = self.factory.makeSpecification(
                name='spec-1', owner=self.owner)
            spec_1.linkBug(self.bugtasks[2].bug)
            spec_1_1 = self.factory.makeSpecification(
                name='spec-1-1', owner=self.owner)
            spec_1_1.linkBug(self.bugtasks[2].bug)
            spec_2 = self.factory.makeSpecification(
                name='spec-2', owner=self.owner)
            spec_2.linkBug(self.bugtasks[1].bug)
        params = self.getBugTaskSearchParams(
            user=None, orderby='specification')
        expected = [self.bugtasks[2], self.bugtasks[1], self.bugtasks[0]]
        self.assertSearchFinds(params, expected)
        expected.reverse()
        params = self.getBugTaskSearchParams(
            user=None, orderby='-specification')
        self.assertSearchFinds(params, expected)

    def test_sort_by_information_type(self):
        with person_logged_in(self.owner):
            self.bugtasks[0].bug.transitionToInformationType(
                InformationType.USERDATA, self.owner)
            self.bugtasks[1].bug.transitionToInformationType(
                InformationType.PUBLIC, self.owner)
            self.bugtasks[2].bug.transitionToInformationType(
                InformationType.USERDATA, self.owner)
            # Importance is secondary sort key.
            self.bugtasks[2].importance = BugTaskImportance.MEDIUM

        expected = [self.bugtasks[1], self.bugtasks[0], self.bugtasks[2]]
        params = self.getBugTaskSearchParams(
            user=self.owner, orderby='information_type')
        self.assertSearchFinds(params, expected)
        expected.reverse()
        params = self.getBugTaskSearchParams(
            user=self.owner, orderby='-information_type')
        self.assertSearchFinds(params, expected)


class TargetTests:
    """Tests which are useful for every target."""

    def test_aggregate_by_target(self):
        # BugTaskSet.search supports returning the counts for each target (as
        # long as only one type of target was selected).
        if self.group_on is None:
            # Not a useful/valid permutation.
            return
        self.getBugTaskSearchParams(user=None, multitarget=True)
        # The test data has 3 bugs for searchtarget and 6 for searchtarget2.
        user = self.factory.makePerson()
        expected = {(self.targetToGroup(self.searchtarget),): 3,
            (self.targetToGroup(self.searchtarget2),): 6}
        actual = self.bugtask_set.countBugs(
            user, (self.searchtarget, self.searchtarget2),
            group_on=self.group_on)
        self.assertEqual(expected, actual)

    def test_search_all_bugtasks_for_target(self):
        # BugTaskSet.search() returns all bug tasks for a given bug
        # target, if only the bug target is passed as a search parameter.
        params = self.getBugTaskSearchParams(user=None)
        self.assertSearchFinds(params, self.bugtasks)

    def _findBugtaskForOtherProduct(self, bugtask, main_product):
        # Return the bugtask for the product that is not related to the
        # main bug target.
        #
        # The default bugtasks of this test suite are created by
        # ObjectFactory.makeBugTask() as follows:
        # - a new bug is created having a new product as the target.
        # - another bugtask is created for self.searchtarget (or,
        #   when self.searchtarget is a milestone, for the product
        #   of the milestone)
        # This method returns the bug task for the product that is not
        # related to the main bug target.
        bug = bugtask.bug
        for other_task in bug.bugtasks:
            other_target = other_task.target
            if (IProduct.providedBy(other_target)
                and other_target != main_product):
                return other_task
        self.fail(
            'No bug task found for a product that is not the target of '
            'the main test bugtask.')

    def findBugtaskForOtherProduct(self, bugtask):
        # Return the bugtask for the product that is not related to the
        # main bug target.
        #
        # This method must ober overridden for product related tests.
        return self._findBugtaskForOtherProduct(bugtask, None)

    def test_search_by_structural_subscriber(self):
        # Search results can be limited to bugs with a bug target to which
        # a given person has a structural subscription.
        subscriber = self.factory.makePerson()
        # If the given person is not subscribed, no bugtasks are returned.
        params = self.getBugTaskSearchParams(
            user=None, structural_subscriber=subscriber)
        self.assertSearchFinds(params, [])
        # When the person is subscribed, all bugtasks are returned.
        self.subscribeToTarget(subscriber)
        params = self.getBugTaskSearchParams(
            user=None, structural_subscriber=subscriber)
        self.assertSearchFinds(params, self.bugtasks)

        # Searching for a structural subscriber does not return a bugtask,
        # if the person is subscribed to another target than the main
        # bug target.
        other_subscriber = self.factory.makePerson()
        other_bugtask = self.findBugtaskForOtherProduct(self.bugtasks[0])
        other_target = other_bugtask.target
        with person_logged_in(other_subscriber):
            other_target.addSubscription(
                other_subscriber, subscribed_by=other_subscriber)
        params = self.getBugTaskSearchParams(
            user=None, structural_subscriber=other_subscriber)
        self.assertSearchFinds(params, [])

    def test_has_no_upstream_bugtask(self):
        # Search results can be limited to bugtasks of bugs that do
        # not have a related upstream task.
        #
        # All bugs created in makeBugTasks() have at least one
        # bug task for a product: The default bug task created
        # by lp.testing.factory.Factory.makeBug() if neither a
        # product nor a distribution is specified. For distribution
        # related tests we need another bug which does not have
        # an upstream (aka product) bug task, otherwise the set of
        # bugtasks returned for a search for has_no_upstream_bugtask
        # would always be empty.
        if (IDistribution.providedBy(self.searchtarget) or
            ISourcePackage.providedBy(self.searchtarget) or
            IDistributionSourcePackage.providedBy(self.searchtarget)):
            if IDistribution.providedBy(self.searchtarget):
                bug = self.factory.makeBug(target=self.searchtarget)
                expected = [bug.default_bugtask]
            else:
                dsp = self.factory.makeDistributionSourcePackage(
                    distribution=self.searchtarget.distribution)
                bug = self.factory.makeBug(target=dsp)
                bugtask = self.factory.makeBugTask(
                    bug=bug, target=self.searchtarget)
                expected = [bugtask]
        elif IDistroSeries.providedBy(self.searchtarget):
            bug = self.factory.makeBug(target=self.searchtarget.distribution)
            bugtask = self.factory.makeBugTask(
                bug=bug, target=self.searchtarget)
            expected = [bugtask]
        else:
            # Bugs without distribution related bugtasks have always at
            # least one product related bugtask, hence a
            # has_no_upstream_bugtask search will always return an
            # empty result set.
            expected = []
        params = self.getBugTaskSearchParams(
            user=None, has_no_upstream_bugtask=True)
        self.assertSearchFinds(params, expected)

    def changeStatusOfBugTaskForOtherProduct(self, bugtask, new_status):
        # Change the status of another bugtask of the same bug to the
        # given status.
        other_task = self.findBugtaskForOtherProduct(bugtask)
        with person_logged_in(other_task.target.owner):
            other_task.transitionToStatus(new_status, other_task.target.owner)

    def test_upstream_status(self):
        # Search results can be filtered by the status of an upstream
        # bug task.
        #
        # The bug task status of the default test data has only bug tasks
        # with status NEW for the "other" product, hence all bug tasks
        # will be returned in a search for bugs that are open upstream.
        params = self.getBugTaskSearchParams(user=None, open_upstream=True)
        self.assertSearchFinds(params, self.bugtasks)
        # A search for tasks resolved upstream does not yield any bugtask.
        params = self.getBugTaskSearchParams(
            user=None, resolved_upstream=True)
        self.assertSearchFinds(params, [])
        # But if we set upstream bug tasks to "fix committed" or "fix
        # released", the related bug tasks for our test target appear in
        # the search result.
        self.changeStatusOfBugTaskForOtherProduct(
            self.bugtasks[0], BugTaskStatus.FIXCOMMITTED)
        self.changeStatusOfBugTaskForOtherProduct(
            self.bugtasks[1], BugTaskStatus.FIXRELEASED)
        self.assertSearchFinds(params, self.bugtasks[:2])
        # A search for bug tasks open upstream now returns only one
        # test task.
        params = self.getBugTaskSearchParams(user=None, open_upstream=True)
        self.assertSearchFinds(params, self.bugtasks[2:])


class DeactivatedProductBugTaskTestCase(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(DeactivatedProductBugTaskTestCase, self).setUp()
        self.person = self.factory.makePerson()
        self.active_product = self.factory.makeProduct()
        self.inactive_product = self.factory.makeProduct()
        bug = self.factory.makeBug(
            target=self.active_product, description="Monkeys are bad.")
        self.active_bugtask = self.factory.makeBugTask(
            bug=bug,
            target=self.active_product)
        self.inactive_bugtask = self.factory.makeBugTask(
            bug=bug,
            target=self.inactive_product)
        with person_logged_in(self.person):
            self.active_bugtask.transitionToAssignee(self.person)
            self.inactive_bugtask.transitionToAssignee(self.person)
        admin = getUtility(IPersonSet).getByEmail('admin@canonical.com')
        with person_logged_in(admin):
            self.inactive_product.active = False

    def test_deactivated_listings_not_seen(self):
        # Someone without permission to see deactiveated projects does
        # not see bugtasks for deactivated projects.
        bugtask_set = getUtility(IBugTaskSet)
        param = BugTaskSearchParams(user=None, searchtext=u'Monkeys')
        results = bugtask_set.search(param, _noprejoins=True)
        self.assertEqual([self.active_bugtask], list(results))


class ProductAndDistributionTests:
    """Tests which are useful for distributions and products."""

    def makeSeries(self):
        """Return a series for the main bug target of this class."""
        raise NotImplementedError

    def test_search_by_bug_nomination(self):
        # Search results can be limited to bugs nominated to a given
        # series.
        series1 = self.makeSeries()
        series2 = self.makeSeries()
        nominator = self.factory.makePerson()
        with person_logged_in(self.owner):
            self.bugtasks[0].bug.addNomination(nominator, series1)
            self.bugtasks[1].bug.addNomination(nominator, series2)
        params = self.getBugTaskSearchParams(user=None, nominated_for=series1)
        self.assertSearchFinds(params, self.bugtasks[:1])


class ProjectGroupAndDistributionTests:
    """Tests which are useful for project groups and distributions."""

    def setUpStructuralSubscriptions(self):
        # Subscribe a user to the search target of this test and to
        # another target.
        raise NotImplementedError

    def test_unique_results_for_multiple_structural_subscriptions(self):
        # Searching for a subscriber who is more than once subscribed to a
        # bug task returns this bug task only once.
        subscriber = self.setUpStructuralSubscriptions()
        params = self.getBugTaskSearchParams(
            user=None, structural_subscriber=subscriber)
        self.assertSearchFinds(params, self.bugtasks)


class DistributionAndDistroSeriesTests:
    """Tests which are useful for distributions and their series."""

    def makeBugInComponent(self, archive, series, component):
        pub = self.factory.makeSourcePackagePublishingHistory(
            archive=archive, distroseries=series, component=component,
            status=PackagePublishingStatus.PUBLISHED)
        return self.factory.makeBugTask(
            target=self.searchtarget.getSourcePackage(pub.sourcepackagename))

    def test_search_by_component(self):
        series = self.getCurrentSeries()
        distro = series.distribution
        self.factory.makeArchive(
            distribution=distro, purpose=ArchivePurpose.PARTNER)

        main = getUtility(IComponentSet)['main']
        main_task = self.makeBugInComponent(
            distro.main_archive, series, main)
        universe = getUtility(IComponentSet)['universe']
        universe_task = self.makeBugInComponent(
            distro.main_archive, series, universe)
        partner = getUtility(IComponentSet)['partner']
        partner_task = self.makeBugInComponent(
            distro.getArchiveByComponent('partner'), series, partner)

        # Searches for a single component work.
        params = self.getBugTaskSearchParams(user=None, component=main)
        self.assertSearchFinds(params, [main_task])
        params = self.getBugTaskSearchParams(user=None, component=universe)
        self.assertSearchFinds(params, [universe_task])

        # Non-primary-archive component searches also work.
        params = self.getBugTaskSearchParams(user=None, component=partner)
        self.assertSearchFinds(params, [partner_task])

        # A combination of archives works.
        params = self.getBugTaskSearchParams(
            user=None, component=any(partner, main))
        self.assertSearchFinds(params, [main_task, partner_task])


class BugTargetTestBase:
    """A base class for the bug target mixin classes.

    :ivar searchtarget: A bug context to search within.
    :ivar searchtarget2: A sibling bug context for testing cross-context
        searches. Created on demand when
        getBugTaskSearchParams(multitarget=True) is called.
    :ivar bugtasks2: Bugtasks created for searchtarget2. Twice as many are
        made as for searchtarget.
    :ivar group_on: The columns to group on when calling countBugs. None
        if the target being testing is not sensible/implemented for counting
        bugs. For instance, grouping by project group may be interesting but
        at the time of writing is not implemented.
    """

    def makeBugTasks(self, bugtarget=None, bugtasks=None, owner=None):
        if bugtasks is None:
            self.bugtasks = []
            bugtasks = self.bugtasks
        if bugtarget is None:
            bugtarget = self.searchtarget
        if owner is None:
            owner = self.owner
        with person_logged_in(owner):
            bugtasks.append(
                self.factory.makeBugTask(target=bugtarget))
            bugtasks[-1].importance = BugTaskImportance.HIGH
            bugtasks[-1].transitionToStatus(
                BugTaskStatus.TRIAGED, owner)

            bugtasks.append(
                self.factory.makeBugTask(target=bugtarget))
            bugtasks[-1].importance = BugTaskImportance.LOW
            bugtasks[-1].transitionToStatus(
                BugTaskStatus.NEW, owner)

            bugtasks.append(
                self.factory.makeBugTask(target=bugtarget))
            bugtasks[-1].importance = BugTaskImportance.CRITICAL
            bugtasks[-1].transitionToStatus(
                BugTaskStatus.FIXCOMMITTED, owner)

    def getBugTaskSearchParams(self, multitarget=False, *args, **kw):
        """Return a BugTaskSearchParams object for the given parameters.

        Also, set the bug target.

        :param multitarget: If True multiple targets are used using any(
            self.searchtarget, self.searchtarget2).
        """
        params = BugTaskSearchParams(*args, **kw)
        if multitarget and getattr(self, 'searchtarget2', None) is None:
            self.setUpTarget2()
        if not multitarget:
            target = self.searchtarget
        else:
            target = any(self.searchtarget, self.searchtarget2)
        self.setBugParamsTarget(params, target)
        return params

    def targetToGroup(self, target):
        """Convert a search target to a group_on result."""
        return target.id


class BugTargetWithBugSuperVisor:
    """A base class for bug targets which have a bug supervisor."""

    def test_search_by_bug_supervisor(self):
        # We can search for bugs by bug supervisor.
        # We have by default no bug supervisor set, so searching for
        # bugs by supervisor returns no data.
        supervisor = self.factory.makeTeam(owner=self.owner)
        params = self.getBugTaskSearchParams(
            user=None, bug_supervisor=supervisor)
        self.assertSearchFinds(params, [])

        # If we appoint a bug supervisor, searching for bug tasks
        # by supervisor will return all bugs for our test target.
        self.setSupervisor(supervisor)
        self.assertSearchFinds(params, self.bugtasks)

    def setSupervisor(self, supervisor):
        """Set the bug supervisor for the bug task target."""
        with person_logged_in(self.owner):
            self.searchtarget.bug_supervisor = supervisor


class ProductTarget(BugTargetTestBase, ProductAndDistributionTests,
                    BugTargetWithBugSuperVisor):
    """Use a product as the bug target."""

    def setUp(self):
        super(ProductTarget, self).setUp()
        self.group_on = (BugSummary.product_id,)
        self.searchtarget = self.factory.makeProduct()
        self.owner = self.searchtarget.owner
        self.makeBugTasks()

    def setUpTarget2(self):
        self.searchtarget2 = self.factory.makeProduct()
        self.bugtasks2 = []
        self.makeBugTasks(bugtarget=self.searchtarget2,
            bugtasks=self.bugtasks2, owner=self.searchtarget2.owner)
        self.makeBugTasks(bugtarget=self.searchtarget2,
            bugtasks=self.bugtasks2, owner=self.searchtarget2.owner)

    def setBugParamsTarget(self, params, target):
        params.setProduct(target)

    def makeSeries(self):
        """See `ProductAndDistributionTests`."""
        return self.factory.makeProductSeries(product=self.searchtarget)

    def findBugtaskForOtherProduct(self, bugtask):
        # Return the bugtask for the product that is not related to the
        # main bug target.
        return self._findBugtaskForOtherProduct(bugtask, self.searchtarget)

    def setUpMilestoneSorting(self):
        with person_logged_in(self.owner):
            milestone_1 = self.factory.makeMilestone(
                product=self.searchtarget, name='1.0')
            milestone_2 = self.factory.makeMilestone(
                product=self.searchtarget, name='2.0')
            self.bugtasks[1].transitionToMilestone(milestone_1, self.owner)
            self.bugtasks[2].transitionToMilestone(milestone_2, self.owner)
        return self.bugtasks[1:] + self.bugtasks[:1]


class ProductSeriesTarget(BugTargetTestBase):
    """Use a product series as the bug target."""

    def setUp(self):
        super(ProductSeriesTarget, self).setUp()
        self.group_on = (BugSummary.productseries_id,)
        self.searchtarget = self.factory.makeProductSeries()
        self.owner = self.searchtarget.owner
        self.makeBugTasks()

    def setUpTarget2(self):
        self.searchtarget2 = self.factory.makeProductSeries(
            product=self.searchtarget.product)
        self.bugtasks2 = []
        self.makeBugTasks(bugtarget=self.searchtarget2,
            bugtasks=self.bugtasks2, owner=self.searchtarget2.owner)
        self.makeBugTasks(bugtarget=self.searchtarget2,
            bugtasks=self.bugtasks2, owner=self.searchtarget2.owner)

    def setBugParamsTarget(self, params, target):
        params.setProductSeries(target)

    def changeStatusOfBugTaskForOtherProduct(self, bugtask, new_status):
        # Change the status of another bugtask of the same bug to the
        # given status.
        #
        # This method is called by SearchTestBase.test_upstream_status().
        # A search for bugs which are open or closed upstream has an
        # odd behaviour when the search target is a product series: In
        # this case, all bugs with an open or closed bug task for _any_
        # product are returned, including bug tasks for the main product
        # of the series. Hence we must set the status for all products
        # in order to avoid a failure of test_upstream_status().
        for other_task in bugtask.related_tasks:
            other_target = other_task.target
            if IProduct.providedBy(other_target):
                with person_logged_in(other_target.owner):
                    other_task.transitionToStatus(
                        new_status, other_target.owner)

    def findBugtaskForOtherProduct(self, bugtask):
        # Return the bugtask for the product that not related to the
        # main bug target.
        return self._findBugtaskForOtherProduct(
            bugtask, self.searchtarget.product)

    def setUpMilestoneSorting(self):
        with person_logged_in(self.owner):
            milestone_1 = self.factory.makeMilestone(
                productseries=self.searchtarget, name='1.0')
            milestone_2 = self.factory.makeMilestone(
                productseries=self.searchtarget, name='2.0')
            self.bugtasks[1].transitionToMilestone(milestone_1, self.owner)
            self.bugtasks[2].transitionToMilestone(milestone_2, self.owner)
        return self.bugtasks[1:] + self.bugtasks[:1]


class ProjectGroupTarget(BugTargetTestBase, BugTargetWithBugSuperVisor,
                         ProjectGroupAndDistributionTests):
    """Use a project group as the bug target."""

    def setUp(self):
        super(ProjectGroupTarget, self).setUp()
        self.group_on = None
        self.searchtarget = self.factory.makeProject()
        self.owner = self.searchtarget.owner
        self.makeBugTasks()

    def setUpTarget2(self):
        self.searchtarget2 = self.factory.makeProject()
        self.bugtasks2 = []
        self.makeBugTasks(bugtarget=self.searchtarget2,
            bugtasks=self.bugtasks2, owner=self.searchtarget2.owner)
        self.makeBugTasks(bugtarget=self.searchtarget2,
            bugtasks=self.bugtasks2, owner=self.searchtarget2.owner)

    def setBugParamsTarget(self, params, target):
        params.setProject(target)

    def makeBugTasks(self, bugtarget=None, bugtasks=None, owner=None):
        """Create bug tasks for the search target."""
        if bugtasks is None:
            self.bugtasks = []
            bugtasks = self.bugtasks
        if bugtarget is None:
            bugtarget = self.searchtarget
        if owner is None:
            owner = self.owner
        self.products = []
        with person_logged_in(owner):
            product = self.factory.makeProduct(owner=owner)
            self.products.append(product)
            product.project = self.searchtarget
            bugtasks.append(
                self.factory.makeBugTask(target=product))
            bugtasks[-1].importance = BugTaskImportance.HIGH
            bugtasks[-1].transitionToStatus(
                BugTaskStatus.TRIAGED, owner)

            product = self.factory.makeProduct(owner=owner)
            self.products.append(product)
            product.project = self.searchtarget
            bugtasks.append(
                self.factory.makeBugTask(target=product))
            bugtasks[-1].importance = BugTaskImportance.LOW
            bugtasks[-1].transitionToStatus(
            BugTaskStatus.NEW, owner)

            product = self.factory.makeProduct(owner=owner)
            self.products.append(product)
            product.project = self.searchtarget
            bugtasks.append(
                self.factory.makeBugTask(target=product))
            bugtasks[-1].importance = BugTaskImportance.CRITICAL
            bugtasks[-1].transitionToStatus(
                BugTaskStatus.FIXCOMMITTED, owner)

    def setSupervisor(self, supervisor):
        """Set the bug supervisor for the bug task targets."""
        with person_logged_in(self.owner):
            # We must set the bug supervisor for each bug task target
            for bugtask in self.bugtasks:
                bugtask.target.bug_supervisor = supervisor

    def findBugtaskForOtherProduct(self, bugtask):
        # Return the bugtask for the product that not related to the
        # main bug target.
        bug = bugtask.bug
        for other_task in bug.bugtasks:
            other_target = other_task.target
            if (IProduct.providedBy(other_target)
                and other_target not in self.products):
                return other_task
        self.fail(
            'No bug task found for a product that is not the target of '
            'the main test bugtask.')

    def setUpStructuralSubscriptions(self):
        # See `ProjectGroupAndDistributionTests`.
        subscriber = self.factory.makePerson()
        self.subscribeToTarget(subscriber)
        with person_logged_in(subscriber):
            self.bugtasks[0].target.addSubscription(
                subscriber, subscribed_by=subscriber)
        return subscriber

    def setUpMilestoneSorting(self):
        with person_logged_in(self.owner):
            milestone_1 = self.factory.makeMilestone(
                product=self.bugtasks[1].target, name='1.0')
            milestone_2 = self.factory.makeMilestone(
                product=self.bugtasks[2].target, name='2.0')
            self.bugtasks[1].transitionToMilestone(milestone_1, self.owner)
            self.bugtasks[2].transitionToMilestone(milestone_2, self.owner)
        return self.bugtasks[1:] + self.bugtasks[:1]


class MilestoneTarget(BugTargetTestBase):
    """Use a milestone as the bug target."""

    def setUp(self):
        super(MilestoneTarget, self).setUp()
        self.product = self.factory.makeProduct()
        self.group_on = (BugSummary.milestone_id,)
        self.searchtarget = self.factory.makeMilestone(product=self.product)
        self.owner = self.product.owner
        self.makeBugTasks(bugtarget=self.product)

    def setUpTarget2(self):
        self.searchtarget2 = self.factory.makeMilestone(product=self.product)
        self.bugtasks2 = []
        self.makeBugTasks(bugtarget=self.product,
            bugtasks=self.bugtasks2, owner=self.product.owner,
            searchtarget=self.searchtarget2)
        self.makeBugTasks(bugtarget=self.product,
            bugtasks=self.bugtasks2, owner=self.product.owner,
            searchtarget=self.searchtarget2)

    def setBugParamsTarget(self, params, target):
        params.milestone = target

    def makeBugTasks(self, bugtarget=None, bugtasks=None, owner=None,
        searchtarget=None):
        """Create bug tasks for a product and assign them to a milestone."""
        super(MilestoneTarget, self).makeBugTasks(bugtarget=bugtarget,
            bugtasks=bugtasks, owner=owner)
        if bugtasks is None:
            bugtasks = self.bugtasks
        if owner is None:
            owner = self.owner
        if searchtarget is None:
            searchtarget = self.searchtarget
        with person_logged_in(owner):
            for bugtask in bugtasks:
                bugtask.transitionToMilestone(searchtarget, owner)

    def findBugtaskForOtherProduct(self, bugtask):
        # Return the bugtask for the product that not related to the
        # main bug target.
        return self._findBugtaskForOtherProduct(bugtask, self.product)

    def setUpMilestoneSorting(self):
        # Setup for a somewhat pointless test: All bugtasks are already
        # assigned to same milestone. This means essentially that the
        # search result should be ordered by the secondary sort order,
        # BugTask.importance.
        # Note that reversing the sort direction of milestone does not
        # affect the sort direction of the bug ID.
        return sorted(self.bugtasks, key=lambda bugtask: bugtask.importance)


class DistributionTarget(BugTargetTestBase, ProductAndDistributionTests,
                         BugTargetWithBugSuperVisor,
                         ProjectGroupAndDistributionTests,
                         DistributionAndDistroSeriesTests):
    """Use a distribution as the bug target."""

    def setUp(self):
        super(DistributionTarget, self).setUp()
        self.group_on = (BugSummary.distribution_id,)
        self.searchtarget = self.factory.makeDistribution()
        self.owner = self.searchtarget.owner
        self.makeBugTasks()

    def setUpTarget2(self):
        self.searchtarget2 = self.factory.makeDistribution()
        self.bugtasks2 = []
        self.makeBugTasks(bugtarget=self.searchtarget2,
            bugtasks=self.bugtasks2, owner=self.searchtarget2.owner)
        self.makeBugTasks(bugtarget=self.searchtarget2,
            bugtasks=self.bugtasks2, owner=self.searchtarget2.owner)

    def setBugParamsTarget(self, params, target):
        params.setDistribution(target)

    def makeSeries(self):
        """See `ProductAndDistributionTests`."""
        return self.factory.makeDistroSeries(distribution=self.searchtarget)

    def getCurrentSeries(self):
        if self.searchtarget.currentseries is None:
            self.makeSeries()
        return self.searchtarget.currentseries

    def setUpStructuralSubscriptions(self):
        # See `ProjectGroupAndDistributionTests`.
        subscriber = self.factory.makePerson()
        sourcepackage = self.factory.makeDistributionSourcePackage(
            distribution=self.searchtarget)
        self.bugtasks.append(self.factory.makeBugTask(target=sourcepackage))
        self.subscribeToTarget(subscriber)
        with person_logged_in(subscriber):
            sourcepackage.addSubscription(
                subscriber, subscribed_by=subscriber)
        return subscriber

    def setUpMilestoneSorting(self):
        with person_logged_in(self.owner):
            milestone_1 = self.factory.makeMilestone(
                distribution=self.searchtarget, name='1.0')
            milestone_2 = self.factory.makeMilestone(
                distribution=self.searchtarget, name='2.0')
            self.bugtasks[1].transitionToMilestone(milestone_1, self.owner)
            self.bugtasks[2].transitionToMilestone(milestone_2, self.owner)
        return self.bugtasks[1:] + self.bugtasks[:1]


class DistroseriesTarget(BugTargetTestBase, ProjectGroupAndDistributionTests,
                         DistributionAndDistroSeriesTests):
    """Use a distro series as the bug target."""

    def setUp(self):
        super(DistroseriesTarget, self).setUp()
        self.group_on = (BugSummary.distroseries_id,)
        self.searchtarget = self.factory.makeDistroSeries()
        self.owner = self.searchtarget.owner
        self.makeBugTasks()

    def setUpTarget2(self):
        self.searchtarget2 = self.factory.makeDistroSeries(
            distribution=self.searchtarget.distribution)
        self.bugtasks2 = []
        self.makeBugTasks(bugtarget=self.searchtarget2,
            bugtasks=self.bugtasks2, owner=self.searchtarget2.owner)
        self.makeBugTasks(bugtarget=self.searchtarget2,
            bugtasks=self.bugtasks2, owner=self.searchtarget2.owner)

    def setBugParamsTarget(self, params, target):
        params.setDistroSeries(target)

    def getCurrentSeries(self):
        return self.searchtarget

    def setUpMilestoneSorting(self):
        with person_logged_in(self.owner):
            milestone_1 = self.factory.makeMilestone(
                distribution=self.searchtarget.distribution, name='1.0')
            milestone_2 = self.factory.makeMilestone(
                distribution=self.searchtarget.distribution, name='2.0')
            self.bugtasks[1].transitionToMilestone(milestone_1, self.owner)
            self.bugtasks[2].transitionToMilestone(milestone_2, self.owner)
        return self.bugtasks[1:] + self.bugtasks[:1]

    def setUpStructuralSubscriptions(self, subscribe_search_target=True):
        # See `ProjectGroupAndDistributionTests`.
        # Users can search for series and package subscriptions. Users
        # subscribe to packages at the distro level.
        subscriber = self.factory.makePerson()
        if subscribe_search_target:
            self.subscribeToTarget(subscriber)
        # Create a bug in a package in the series being searched.
        sourcepackage = self.factory.makeSourcePackage(
            distroseries=self.searchtarget)
        self.bugtasks.append(self.factory.makeBugTask(target=sourcepackage))
        # Create a bug in another series for the same package.
        other_series = self.factory.makeDistroSeries(
            distribution=self.searchtarget.distribution)
        other_sourcepackage = self.factory.makeSourcePackage(
            distroseries=other_series,
            sourcepackagename=sourcepackage.sourcepackagename)
        self.factory.makeBugTask(target=other_sourcepackage)
        # Create a bug in the same distrubution package.
        dsp = self.searchtarget.distribution.getSourcePackage(
            sourcepackage.name)
        self.factory.makeBugTask(target=dsp)
        # Subscribe to the DSP to search both DSPs and SPs.
        with person_logged_in(subscriber):
            dsp.addSubscription(
                subscriber, subscribed_by=subscriber)
        return subscriber

    def test_subordinate_structural_subscribers(self):
        # Searching for a subscriber who is subscribed to only subordinate
        # objects will match those objects
        subscriber = self.setUpStructuralSubscriptions(
            subscribe_search_target=False)
        params = self.getBugTaskSearchParams(
            user=None, structural_subscriber=subscriber)
        self.assertSearchFinds(params, [self.bugtasks[-1]])


class UpstreamFilterTests:
    """A mixin class with tests related to restircted upstream filtering.

    Classes derived from this class must also derive from SearchTestBase.

    These tests make sense only for the targets SourcePackage
    DistributionSourcePackage.
    """

    def setUpUpstreamTests(self, upstream_target):
        # The default test bugs have two tasks for DistributionSourcePackage
        # tests: one task for the DSP and another task for a product;
        # they have three tasks for SourcePackage tests: for a product,
        # for a DSP and for a sourcepackage.
        # Tests in this class are about searching bug tasks, where the
        # bug has a task for any upstream target or for a given upstream
        # target and where the bug task for the upstream target has certain
        # properties.
        with person_logged_in(self.searchtarget.distribution.owner):
            self.searchtarget.distribution.official_malone = True
        for existing_task in self.bugtasks:
            bug = existing_task.bug
            self.factory.makeBugTask(bug, target=upstream_target)

    def addWatch(self, bug, target=None):
        # Add a bug watch to the bugtask for the given target. If no
        # target is specified, the bug watch is added to the default
        # bugtask, which is a different product for each bug.
        if target is None:
            task = bug.bugtasks[0]
        else:
            for task in bug.bugtasks:
                if task.target == target:
                    break
        with person_logged_in(task.target.owner):
            watch = self.factory.makeBugWatch(bug=bug)
            task.bugwatch = watch

    def test_pending_bugwatch_elsewhere__no_upstream_specified(self):
        # By default, those bugs are returned where
        #   - an upstream task exists
        #   - the upstream product does not use LP for bug tracking
        #   - the bug task has no bug watch.
        # All test bugs fulfill this condition.
        upstream_target = self.factory.makeProduct()
        self.setUpUpstreamTests(upstream_target)
        params = self.getBugTaskSearchParams(
            user=None, pending_bugwatch_elsewhere=True)
        self.assertSearchFinds(params, self.bugtasks)
        # If a bug watch is added to only one of the product related
        # bug tasks, the bug is still returned.
        self.addWatch(self.bugtasks[0].bug)
        self.addWatch(self.bugtasks[1].bug, target=upstream_target)
        self.assertSearchFinds(params, self.bugtasks)
        # If bugwatches are added to the other product related bug task
        # too, the bugs are not included in the search result.
        self.addWatch(self.bugtasks[0].bug, target=upstream_target)
        self.addWatch(self.bugtasks[1].bug)
        self.assertSearchFinds(params, self.bugtasks[2:])

    def test_pending_bugwatch_elsewhere__upstream_product(self):
        # If an upstream target using Malone is specified, a search
        # returns all bugs with a bug task for this target, if the
        # task does not have a bug watch.
        upstream_target = self.factory.makeProduct()
        self.setUpUpstreamTests(upstream_target)
        # The first bug task of all test bugs is targeted to its
        # own Product instance.
        bug = self.bugtasks[0].bug
        single_bugtask_product = bug.bugtasks[0].target
        params = self.getBugTaskSearchParams(
            user=None, pending_bugwatch_elsewhere=True,
            upstream_target=single_bugtask_product)
        self.assertSearchFinds(params, self.bugtasks[:1])
        # If a bug watch is added to this task, the search returns an
        # empty result set.
        self.addWatch(self.bugtasks[0].bug)
        self.assertSearchFinds(params, [])

    def test_pending_bugwatch_elsewhere__upstream_product_uses_lp(self):
        # If an upstream target not using Malone is specified, a search
        # alsways returns an empty result set.
        upstream_target = self.factory.makeProduct()
        self.setUpUpstreamTests(upstream_target)
        with person_logged_in(upstream_target.owner):
            upstream_target.official_malone = True
        params = self.getBugTaskSearchParams(
            user=None, pending_bugwatch_elsewhere=True,
            upstream_target=upstream_target)
        self.assertSearchFinds(params, [])

    def test_pending_bugwatch_elsewhere__upstream_distribution(self):
        # If an upstream target not using Malone is specified, a search
        # alsways returns an empty result set.
        upstream_target = self.factory.makeDistribution()
        self.setUpUpstreamTests(upstream_target)
        params = self.getBugTaskSearchParams(
            user=None, pending_bugwatch_elsewhere=True,
            upstream_target=upstream_target)
        self.assertSearchFinds(params, self.bugtasks)

    def test_has_no_upstream_bugtask__target_specified(self):
        # The target of the default bugtask of the first test bug
        # (a product) does not appear in other bugs, thus a search
        # returns all other bugtasks if we specify the search parameters
        # has_no_upstream_bugtask and use the target described above
        # as the upstream_target.
        bug = self.bugtasks[0].bug
        upstream_target = bug.bugtasks[0].target
        params = self.getBugTaskSearchParams(
            user=None, has_no_upstream_bugtask=True,
            upstream_target=upstream_target)
        self.assertSearchFinds(params, self.bugtasks[1:])
        # If a new distribution is specified as the upstream target,
        # all bugs are returned, since there are no tasks for this
        # distribution.
        upstream_target = self.factory.makeDistribution()
        params = self.getBugTaskSearchParams(
            user=None, has_no_upstream_bugtask=True,
            upstream_target=upstream_target)
        self.assertSearchFinds(params, self.bugtasks)
        # When we add bugtasks for this distribution, the search returns
        # an empty result.
        self.setUpUpstreamTests(upstream_target)
        self.assertSearchFinds(params, [])

    def test_open_upstream(self):
        # It is possible to search for bugs with open upstream bugtasks.
        bug = self.bugtasks[2].bug
        upstream_task = bug.bugtasks[0]
        upstream_owner = upstream_task.target.owner
        with person_logged_in(upstream_owner):
            upstream_task.transitionToStatus(
                BugTaskStatus.FIXRELEASED, upstream_owner)
        params = self.getBugTaskSearchParams(user=None, open_upstream=True)
        self.assertSearchFinds(params, self.bugtasks[:2])

    def test_open_upstream__upstream_product_specified(self):
        # A search for bugs having an open upstream bugtask can be
        # limited to a specific upstream product.
        bug = self.bugtasks[2].bug
        upstream_task = bug.bugtasks[0]
        upstream_product = upstream_task.target
        params = self.getBugTaskSearchParams(
            user=None, open_upstream=True, upstream_target=upstream_product)
        self.assertSearchFinds(params, self.bugtasks[2:])
        upstream_owner = upstream_product.owner
        with person_logged_in(upstream_owner):
            upstream_task.transitionToStatus(
                BugTaskStatus.FIXRELEASED, upstream_owner)
        self.assertSearchFinds(params, [])

    def test_open_upstream__upstream_distribution_specified(self):
        # A search for bugs having an open upstream bugtask can be
        # limited to a specific upstream distribution.
        upstream_distro = self.factory.makeDistribution()
        params = self.getBugTaskSearchParams(
            user=None, open_upstream=True, upstream_target=upstream_distro)
        self.assertSearchFinds(params, [])
        bug = self.bugtasks[0].bug
        distro_task = self.factory.makeBugTask(
            bug=bug, target=upstream_distro)
        self.assertSearchFinds(params, self.bugtasks[:1])
        with person_logged_in(upstream_distro.owner):
            distro_task.transitionToStatus(
                BugTaskStatus.FIXRELEASED, upstream_distro.owner)
        self.assertSearchFinds(params, [])

    def test_resolved_upstream(self):
        # It is possible to search for bugs with resolved upstream bugtasks.
        bug = self.bugtasks[2].bug
        upstream_task = bug.bugtasks[0]
        upstream_owner = upstream_task.target.owner
        with person_logged_in(upstream_owner):
            upstream_task.transitionToStatus(
                BugTaskStatus.FIXRELEASED, upstream_owner)
        params = self.getBugTaskSearchParams(user=None, resolved_upstream=True)
        self.assertSearchFinds(params, self.bugtasks[2:])

    def test_resolved_upstream__upstream_product_specified(self):
        # A search for bugs having a resolved upstream bugtask can be
        # limited to a specific upstream product.
        bug = self.bugtasks[2].bug
        upstream_task = bug.bugtasks[0]
        upstream_product = upstream_task.target
        params = self.getBugTaskSearchParams(
            user=None, resolved_upstream=True,
            upstream_target=upstream_product)
        self.assertSearchFinds(params, [])
        upstream_owner = upstream_product.owner
        for bug in [task.bug for task in self.bugtasks]:
            upstream_task = bug.bugtasks[0]
            upstream_owner = upstream_task.owner
            with person_logged_in(upstream_owner):
                upstream_task.transitionToStatus(
                BugTaskStatus.FIXRELEASED, upstream_owner)
        self.assertSearchFinds(params, self.bugtasks[2:])

    def test_resolved_upstream__upstream_distribution_specified(self):
        # A search for bugs having an open upstream bugtask can be
        # limited to a specific upstream distribution.
        upstream_distro = self.factory.makeDistribution()
        params = self.getBugTaskSearchParams(
            user=None, resolved_upstream=True,
            upstream_target=upstream_distro)
        self.assertSearchFinds(params, [])
        bug = self.bugtasks[0].bug
        distro_task = self.factory.makeBugTask(
            bug=bug, target=upstream_distro)
        self.assertSearchFinds(params, [])
        with person_logged_in(upstream_distro.owner):
            distro_task.transitionToStatus(
                BugTaskStatus.FIXRELEASED, upstream_distro.owner)
        self.assertSearchFinds(params, self.bugtasks[:1])


class SourcePackageTarget(BugTargetTestBase, UpstreamFilterTests):
    """Use a source package as the bug target."""

    def setUp(self):
        super(SourcePackageTarget, self).setUp()
        self.group_on = (BugSummary.sourcepackagename_id,)
        self.searchtarget = self.factory.makeSourcePackage()
        self.owner = self.searchtarget.distroseries.owner
        self.makeBugTasks()

    def setUpTarget2(self):
        self.searchtarget2 = self.factory.makeSourcePackage(
            distroseries=self.searchtarget.distroseries)
        self.bugtasks2 = []
        self.makeBugTasks(bugtarget=self.searchtarget2,
            bugtasks=self.bugtasks2,
            owner=self.searchtarget2.distroseries.owner)
        self.makeBugTasks(bugtarget=self.searchtarget2,
            bugtasks=self.bugtasks2,
            owner=self.searchtarget2.distroseries.owner)

    def setBugParamsTarget(self, params, target):
        params.setSourcePackage(target)

    def subscribeToTarget(self, subscriber):
        # Subscribe the given person to the search target.
        # Source packages do not support structural subscriptions,
        # so we subscribe to the distro series instead.
        with person_logged_in(subscriber):
            self.searchtarget.distroseries.addSubscription(
                subscriber, subscribed_by=subscriber)

    def targetToGroup(self, target):
        return target.sourcepackagename.id

    def setUpMilestoneSorting(self):
        with person_logged_in(self.owner):
            milestone_1 = self.factory.makeMilestone(
                distribution=self.searchtarget.distribution, name='1.0')
            milestone_2 = self.factory.makeMilestone(
                distribution=self.searchtarget.distribution, name='2.0')
            self.bugtasks[1].transitionToMilestone(milestone_1, self.owner)
            self.bugtasks[2].transitionToMilestone(milestone_2, self.owner)
        return self.bugtasks[1:] + self.bugtasks[:1]


class DistributionSourcePackageTarget(BugTargetTestBase,
                                      BugTargetWithBugSuperVisor,
                                      UpstreamFilterTests):
    """Use a distribution source package as the bug target."""

    def setUp(self):
        super(DistributionSourcePackageTarget, self).setUp()
        self.group_on = (BugSummary.sourcepackagename_id,)
        self.searchtarget = self.factory.makeDistributionSourcePackage()
        self.owner = self.searchtarget.distribution.owner
        self.makeBugTasks()

    def setUpTarget2(self):
        self.searchtarget2 = self.factory.makeDistributionSourcePackage(
            distribution=self.searchtarget.distribution)
        self.bugtasks2 = []
        self.makeBugTasks(bugtarget=self.searchtarget2,
            bugtasks=self.bugtasks2,
            owner=self.searchtarget2.distribution.owner)
        self.makeBugTasks(bugtarget=self.searchtarget2,
            bugtasks=self.bugtasks2,
            owner=self.searchtarget2.distribution.owner)

    def setBugParamsTarget(self, params, target):
        params.setSourcePackage(target)

    def setSupervisor(self, supervisor):
        """Set the bug supervisor for the bug task target."""
        with person_logged_in(self.owner):
            self.searchtarget.distribution.bug_supervisor = supervisor

    def targetToGroup(self, target):
        return target.sourcepackagename.id

    def setUpMilestoneSorting(self):
        with person_logged_in(self.owner):
            milestone_1 = self.factory.makeMilestone(
                distribution=self.searchtarget.distribution, name='1.0')
            milestone_2 = self.factory.makeMilestone(
                distribution=self.searchtarget.distribution, name='2.0')
            self.bugtasks[1].transitionToMilestone(milestone_1, self.owner)
            self.bugtasks[2].transitionToMilestone(milestone_2, self.owner)
        return self.bugtasks[1:] + self.bugtasks[:1]


bug_targets_mixins = (
    DistributionTarget,
    DistributionSourcePackageTarget,
    DistroseriesTarget,
    MilestoneTarget,
    ProductSeriesTarget,
    ProductTarget,
    ProjectGroupTarget,
    SourcePackageTarget,
    )


class MultipleParams:
    """A mixin class for tests with more than one search parameter object.

    BugTaskSet.search() can be called with more than one
    BugTaskSearchParams instances, while BugTaskSet.searchBugIds()
    accepts exactly one instance.
    """

    def setUpTwoSearchParams(self, orderby=None):
        # Prepare the test data for the tests in this class.
        params1 = self.getBugTaskSearchParams(
            user=None, status=BugTaskStatus.FIXCOMMITTED, orderby=orderby)
        subscriber = self.factory.makePerson()
        self.subscribeToTarget(subscriber)
        params2 = self.getBugTaskSearchParams(
            user=None, status=BugTaskStatus.NEW,
            structural_subscriber=subscriber, orderby=orderby)
        return params1, params2

    def test_two_param_objects(self):
        # We can pass more than one BugTaskSearchParams instance to
        # BugTaskSet.search().
        params1, params2 = self.setUpTwoSearchParams()
        search_result = self.runSearch(params1, params2)
        expected = self.resultValuesForBugtasks(self.bugtasks[1:])
        self.assertEqual(expected, search_result)

    def test_two_param_objects_sorting_needs_extra_join(self):
        # If result ordering needs an extra join, the join
        # is added to the union of the result sets for the two
        # BugTaskSearchParams instances.
        params1, params2 = self.setUpTwoSearchParams(orderby='reporter')
        search_result = self.runSearch(params1, params2)

        def sortkey(bugtask):
            return bugtask.owner.name

        expected_bugtasks = sorted(self.bugtasks[1:], key=sortkey)
        expected = self.resultValuesForBugtasks(expected_bugtasks)
        self.assertEqual(expected, search_result)


class PreloadBugtaskTargets(MultipleParams):
    """Preload bug targets during a BugTaskSet.search() query."""

    def runSearch(self, params, *args):
        """Run BugTaskSet.search() and preload bugtask target objects."""
        return list(self.bugtask_set.search(params, *args, _noprejoins=False))

    def resultValuesForBugtasks(self, expected_bugtasks):
        return expected_bugtasks


class NoPreloadBugtaskTargets(MultipleParams):
    """Do not preload bug targets during a BugTaskSet.search() query."""

    def runSearch(self, params, *args):
        """Run BugTaskSet.search() without preloading bugtask targets."""
        return list(self.bugtask_set.search(params, *args, _noprejoins=True))

    def resultValuesForBugtasks(self, expected_bugtasks):
        return expected_bugtasks


class QueryBugIDs:
    """Search bug IDs."""

    def runSearch(self, params, *args):
        """Run BugTaskSet.searchBugIds()."""
        return list(self.bugtask_set.searchBugIds(params))

    def resultValuesForBugtasks(self, expected_bugtasks):
        return [bugtask.bug.id for bugtask in expected_bugtasks]


class TestMilestoneDueDateFiltering(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def test_milestone_date_filters(self):
        today = datetime.today().date()
        ten_days_ago = today - timedelta(days=10)
        ten_days_from_now = today + timedelta(days=10)
        current_milestone = self.factory.makeMilestone(dateexpected=today)
        old_milestone = self.factory.makeMilestone(
            dateexpected=ten_days_ago)
        future_milestone = self.factory.makeMilestone(
            dateexpected=ten_days_from_now)
        current_milestone_bug = self.factory.makeBug(
            milestone=current_milestone)
        self.factory.makeBug(milestone=old_milestone)
        self.factory.makeBug(milestone=future_milestone)
        # Search for bugs whose milestone.dateexpected is between yesterday
        # and tomorrow.  This will return only the one task targeted to
        # current_milestone.
        params = BugTaskSearchParams(
            user=None,
            milestone_dateexpected_after=today - timedelta(days=1),
            milestone_dateexpected_before=today + timedelta(days=1))
        result = getUtility(IBugTaskSet).search(params)
        self.assertEqual(
            current_milestone_bug.bugtasks, list(result))


class TestBugTaskSetStatusSearchClauses(TestCase):
    # BugTaskSets contain a utility function that generates SQL WHERE clauses
    # used to find sets of bugs.  These tests exercise that utility function.

    def searchClause(self, status_spec):
        return convert_storm_clause_to_string(
            _build_status_clause(BugTask._status, status_spec))

    def test_simple_queries(self):
        # WHERE clauses for simple status values are straightforward.
        self.assertEqual(
            'BugTask.status = 10',
            self.searchClause(BugTaskStatus.NEW))
        self.assertEqual(
            'BugTask.status = 16',
            self.searchClause(BugTaskStatus.OPINION))
        self.assertEqual(
            'BugTask.status = 22',
            self.searchClause(BugTaskStatus.INPROGRESS))

    def test_INCOMPLETE_query(self):
        # Since we don't really store INCOMPLETE in the DB but instead store
        # values with finer shades of meaning, asking for INCOMPLETE will
        # result in a clause that actually matches multiple statuses.
        self.assertEqual(
            'BugTask.status IN (13, 14)',
            self.searchClause(BugTaskStatus.INCOMPLETE))

    def test_BugTaskStatusSearch_INCOMPLETE_query(self):
        # BugTaskStatusSearch.INCOMPLETE is treated as
        # BugTaskStatus.INCOMPLETE.
        self.assertEqual(
            'BugTask.status IN (13, 14)',
            self.searchClause(BugTaskStatusSearch.INCOMPLETE))

    def test_negative_query(self):
        # If a negative is requested then the WHERE clause is simply wrapped
        # in a "NOT".
        status = BugTaskStatus.INCOMPLETE
        base_query = self.searchClause(status)
        expected_negative_query = 'NOT ({0})'.format(base_query)
        self.assertEqual(
            expected_negative_query,
            self.searchClause(not_equals(status)))

    def test_any_query(self):
        # An "any" object may be passed in containing a set of statuses to
        # return.  The resulting SQL uses IN in an effort to be optimal.
        self.assertEqual(
            'BugTask.status IN (10, 16)',
            self.searchClause(any(BugTaskStatus.NEW, BugTaskStatus.OPINION)))

    def test_any_query_with_INCOMPLETE(self):
        # Since INCOMPLETE is not a single-value status (see above) an "any"
        # query that includes INCOMPLETE will cause more enum values to be
        # included in the IN clause than were given.  Note that we go to a bit
        # of effort to generate an IN expression instead of a series of
        # ORed-together equality checks.
        self.assertEqual(
            'BugTask.status IN (10, 13, 14)',
            self.searchClause(
                any(BugTaskStatus.NEW, BugTaskStatus.INCOMPLETE)))

    def test_any_query_with_BugTaskStatusSearch_INCOMPLETE(self):
        # BugTaskStatusSearch.INCOMPLETE is treated as
        # BugTaskStatus.INCOMPLETE.
        self.assertEqual(
            'BugTask.status IN (10, 13, 14)',
            self.searchClause(
                any(BugTaskStatus.NEW, BugTaskStatusSearch.INCOMPLETE)))

    def test_all_query(self):
        # Since status is single-valued, asking for "all" statuses in a set
        # doesn't make any sense.
        with ExpectedException(InvalidSearchParameters):
            self.searchClause(
                all(BugTaskStatus.NEW, BugTaskStatus.INCOMPLETE))

    def test_bad_value(self):
        # If an unrecognized status is provided then an error is raised.
        with ExpectedException(InvalidSearchParameters):
            self.searchClause('this-is-not-a-status')


class TestBugTaskTagSearchClauses(TestCase):

    def searchClause(self, tag_spec):
        return convert_storm_clause_to_string(
            _build_tag_search_clause(tag_spec))

    def assertEqualIgnoringWhitespace(self, expected, observed):
        return self.assertEqual(
            normalize_whitespace(expected),
            normalize_whitespace(observed))

    def test_empty(self):
        # Specifying no tags is valid. _build_tag_search_clause will
        # return None, which compiles to 'NULL' here but will be ignored
        # by bugtasksearch.
        self.assertEqual(self.searchClause(any()), 'NULL')
        self.assertEqual(self.searchClause(all()), 'NULL')

    def test_single_tag_presence_any(self):
        # The WHERE clause to test for the presence of a single
        # tag where at least one tag is desired.
        expected_query = (
            """EXISTS
                 (SELECT 1 FROM BugTag
                   WHERE BugTag.bug = BugTaskFlat.bug
                     AND BugTag.tag IN ('fred'))""")
        self.assertEqualIgnoringWhitespace(
            expected_query,
            self.searchClause(any(u'fred')))

    def test_single_tag_presence_all(self):
        # The WHERE clause to test for the presence of a single
        # tag where all tags are desired.
        expected_query = (
            """EXISTS
                 (SELECT 1 FROM BugTag
                   WHERE BugTag.bug = BugTaskFlat.bug
                     AND BugTag.tag = 'fred')""")
        self.assertEqualIgnoringWhitespace(
            expected_query,
            self.searchClause(all(u'fred')))

    def test_single_tag_absence_any(self):
        # The WHERE clause to test for the absence of a single
        # tag where at least one tag is desired.
        expected_query = (
            """NOT EXISTS
                 (SELECT 1 FROM BugTag
                   WHERE BugTag.bug = BugTaskFlat.bug
                     AND BugTag.tag = 'fred')""")
        self.assertEqualIgnoringWhitespace(
            expected_query,
            self.searchClause(any(u'-fred')))

    def test_single_tag_absence_all(self):
        # The WHERE clause to test for the absence of a single
        # tag where all tags are desired.
        expected_query = (
            """NOT EXISTS
                 (SELECT 1 FROM BugTag
                   WHERE BugTag.bug = BugTaskFlat.bug
                     AND BugTag.tag IN ('fred'))""")
        self.assertEqualIgnoringWhitespace(
            expected_query,
            self.searchClause(all(u'-fred')))

    def test_tag_presence(self):
        # The WHERE clause to test for the presence of tags. Should be
        # the same for an `any` query or an `all` query.
        expected_query = (
            """EXISTS
                 (SELECT 1 FROM BugTag
                   WHERE BugTag.bug = BugTaskFlat.bug)""")
        self.assertEqualIgnoringWhitespace(
            expected_query,
            self.searchClause(any(u'*')))
        self.assertEqualIgnoringWhitespace(
            expected_query,
            self.searchClause(all(u'*')))

    def test_tag_absence(self):
        # The WHERE clause to test for the absence of tags. Should be
        # the same for an `any` query or an `all` query.
        expected_query = (
            """NOT EXISTS
                 (SELECT 1 FROM BugTag
                   WHERE BugTag.bug = BugTaskFlat.bug)""")
        self.assertEqualIgnoringWhitespace(
            expected_query,
            self.searchClause(any(u'-*')))
        self.assertEqualIgnoringWhitespace(
            expected_query,
            self.searchClause(all(u'-*')))

    def test_multiple_tag_presence_any(self):
        # The WHERE clause to test for the presence of *any* of
        # several tags.
        self.assertEqualIgnoringWhitespace(
            """EXISTS
                 (SELECT 1 FROM BugTag
                   WHERE BugTag.bug = BugTaskFlat.bug
                     AND BugTag.tag IN ('bob', 'fred'))""",
            self.searchClause(any(u'fred', u'bob')))
        # In an `any` query, a positive wildcard is dominant over
        # other positive tags because "bugs with one or more tags" is
        # a superset of "bugs with a specific tag".
        self.assertEqualIgnoringWhitespace(
            """EXISTS
                 (SELECT 1 FROM BugTag
                   WHERE BugTag.bug = BugTaskFlat.bug)""",
            self.searchClause(any(u'fred', u'*')))

    def test_multiple_tag_absence_any(self):
        # The WHERE clause to test for the absence of *any* of several
        # tags.
        self.assertEqualIgnoringWhitespace(
            """NOT
                 (EXISTS
                  (SELECT 1 FROM BugTag
                   WHERE BugTag.bug = BugTaskFlat.bug
                     AND BugTag.tag = 'bob')
                  AND EXISTS
                  (SELECT 1 FROM BugTag
                   WHERE BugTag.bug = BugTaskFlat.bug
                     AND BugTag.tag = 'fred'))""",
            self.searchClause(any(u'-fred', u'-bob')))
        # In an `any` query, a negative wildcard is superfluous in the
        # presence of other negative tags because "bugs without a
        # specific tag" is a superset of "bugs without any tags".
        self.assertEqualIgnoringWhitespace(
            """NOT EXISTS
                 (SELECT 1 FROM BugTag
                  WHERE BugTag.bug = BugTaskFlat.bug
                    AND BugTag.tag = 'fred')""",
            self.searchClause(any(u'-fred', u'-*')))

    def test_multiple_tag_presence_all(self):
        # The WHERE clause to test for the presence of *all* specified
        # tags.
        self.assertEqualIgnoringWhitespace(
            """EXISTS
               (SELECT 1 FROM BugTag
                WHERE BugTag.bug = BugTaskFlat.bug
                  AND BugTag.tag = 'bob')
               AND EXISTS
               (SELECT 1 FROM BugTag
                WHERE BugTag.bug = BugTaskFlat.bug
                  AND BugTag.tag = 'fred')""",
            self.searchClause(all(u'fred', u'bob')))
        # In an `all` query, a positive wildcard is superfluous in the
        # presence of other positive tags because "bugs with a
        # specific tag" is a subset of (i.e. more specific than) "bugs
        # with one or more tags".
        self.assertEqualIgnoringWhitespace(
            """EXISTS
                 (SELECT 1 FROM BugTag
                   WHERE BugTag.bug = BugTaskFlat.bug
                     AND BugTag.tag = 'fred')""",
            self.searchClause(all(u'fred', u'*')))

    def test_multiple_tag_absence_all(self):
        # The WHERE clause to test for the absence of all specified
        # tags.
        self.assertEqualIgnoringWhitespace(
            """NOT EXISTS
                 (SELECT 1 FROM BugTag
                   WHERE BugTag.bug = BugTaskFlat.bug
                     AND BugTag.tag IN ('bob', 'fred'))""",
            self.searchClause(all(u'-fred', u'-bob')))
        # In an `all` query, a negative wildcard is dominant over
        # other negative tags because "bugs without any tags" is a
        # subset of (i.e. more specific than) "bugs without a specific
        # tag".
        self.assertEqualIgnoringWhitespace(
            """NOT EXISTS
                 (SELECT 1 FROM BugTag
                   WHERE BugTag.bug = BugTaskFlat.bug)""",
            self.searchClause(all(u'-fred', u'-*')))

    def test_mixed_tags_any(self):
        # The WHERE clause to test for the presence of one or more
        # specific tags or the absence of one or more other specific
        # tags.
        self.assertEqualIgnoringWhitespace(
            """EXISTS
                  (SELECT 1 FROM BugTag
                    WHERE BugTag.bug = BugTaskFlat.bug
                      AND BugTag.tag IN ('fred'))
                OR NOT EXISTS
                  (SELECT 1 FROM BugTag
                    WHERE BugTag.bug = BugTaskFlat.bug
                      AND BugTag.tag = 'bob')""",
            self.searchClause(any(u'fred', u'-bob')))
        self.assertEqualIgnoringWhitespace(
            """EXISTS
                  (SELECT 1 FROM BugTag
                    WHERE BugTag.bug = BugTaskFlat.bug
                      AND BugTag.tag IN ('eric', 'fred'))
                OR NOT
                  (EXISTS
                    (SELECT 1 FROM BugTag
                    WHERE BugTag.bug = BugTaskFlat.bug
                      AND BugTag.tag = 'bob')
                   AND EXISTS
                   (SELECT 1 FROM BugTag
                    WHERE BugTag.bug = BugTaskFlat.bug
                      AND BugTag.tag = 'harry'))""",
            self.searchClause(any(u'fred', u'-bob', u'eric', u'-harry')))
        # The positive wildcard is dominant over other positive tags.
        self.assertEqualIgnoringWhitespace(
            """EXISTS
                  (SELECT 1 FROM BugTag
                    WHERE BugTag.bug = BugTaskFlat.bug)
                OR NOT
                  (EXISTS
                   (SELECT 1 FROM BugTag
                    WHERE BugTag.bug = BugTaskFlat.bug
                      AND BugTag.tag = 'bob')
                   AND EXISTS
                   (SELECT 1 FROM BugTag
                    WHERE BugTag.bug = BugTaskFlat.bug
                      AND BugTag.tag = 'harry'))""",
            self.searchClause(any(u'fred', u'-bob', u'*', u'-harry')))
        # The negative wildcard is superfluous in the presence of
        # other negative tags.
        self.assertEqualIgnoringWhitespace(
            """EXISTS
                  (SELECT 1 FROM BugTag
                    WHERE BugTag.bug = BugTaskFlat.bug
                      AND BugTag.tag IN ('eric', 'fred'))
                OR NOT EXISTS
                  (SELECT 1 FROM BugTag
                    WHERE BugTag.bug = BugTaskFlat.bug
                      AND BugTag.tag = 'bob')""",
            self.searchClause(any(u'fred', u'-bob', u'eric', u'-*')))
        # The negative wildcard is not superfluous in the absence of
        # other negative tags.
        self.assertEqualIgnoringWhitespace(
            """EXISTS
                  (SELECT 1 FROM BugTag
                    WHERE BugTag.bug = BugTaskFlat.bug
                      AND BugTag.tag IN ('eric', 'fred'))
                OR NOT EXISTS
                  (SELECT 1 FROM BugTag
                    WHERE BugTag.bug = BugTaskFlat.bug)""",
            self.searchClause(any(u'fred', u'-*', u'eric')))
        # The positive wildcard is dominant over other positive tags,
        # and the negative wildcard is superfluous in the presence of
        # other negative tags.
        self.assertEqualIgnoringWhitespace(
            """EXISTS
                  (SELECT 1 FROM BugTag
                    WHERE BugTag.bug = BugTaskFlat.bug)
                OR NOT EXISTS
                  (SELECT 1 FROM BugTag
                    WHERE BugTag.bug = BugTaskFlat.bug
                      AND BugTag.tag = 'harry')""",
            self.searchClause(any(u'fred', u'-*', u'*', u'-harry')))

    def test_mixed_tags_all(self):
        # The WHERE clause to test for the presence of one or more
        # specific tags and the absence of one or more other specific
        # tags.
        self.assertEqualIgnoringWhitespace(
            """EXISTS
                  (SELECT 1 FROM BugTag
                    WHERE BugTag.bug = BugTaskFlat.bug
                      AND BugTag.tag = 'fred')
                AND NOT EXISTS
                  (SELECT 1 FROM BugTag
                    WHERE BugTag.bug = BugTaskFlat.bug
                      AND BugTag.tag IN ('bob'))""",
            self.searchClause(all(u'fred', u'-bob')))
        self.assertEqualIgnoringWhitespace(
            """EXISTS
                 (SELECT 1 FROM BugTag
                  WHERE BugTag.bug = BugTaskFlat.bug
                    AND BugTag.tag = 'eric')
                AND EXISTS
                 (SELECT 1 FROM BugTag
                  WHERE BugTag.bug = BugTaskFlat.bug
                    AND BugTag.tag = 'fred')
                AND NOT EXISTS
                  (SELECT 1 FROM BugTag
                    WHERE BugTag.bug = BugTaskFlat.bug
                      AND BugTag.tag IN ('bob', 'harry'))""",
            self.searchClause(all(u'fred', u'-bob', u'eric', u'-harry')))
        # The positive wildcard is superfluous in the presence of
        # other positive tags.
        self.assertEqualIgnoringWhitespace(
            """EXISTS
                  (SELECT 1 FROM BugTag
                    WHERE BugTag.bug = BugTaskFlat.bug
                      AND BugTag.tag = 'fred')
                AND NOT EXISTS
                  (SELECT 1 FROM BugTag
                    WHERE BugTag.bug = BugTaskFlat.bug
                      AND BugTag.tag IN ('bob', 'harry'))""",
            self.searchClause(all(u'fred', u'-bob', u'*', u'-harry')))
        # The positive wildcard is not superfluous in the absence of
        # other positive tags.
        self.assertEqualIgnoringWhitespace(
            """EXISTS
                  (SELECT 1 FROM BugTag
                    WHERE BugTag.bug = BugTaskFlat.bug)
                AND NOT EXISTS
                  (SELECT 1 FROM BugTag
                    WHERE BugTag.bug = BugTaskFlat.bug
                      AND BugTag.tag IN ('bob', 'harry'))""",
            self.searchClause(all(u'-bob', u'*', u'-harry')))
        # The negative wildcard is dominant over other negative tags.
        self.assertEqualIgnoringWhitespace(
            """EXISTS
                 (SELECT 1 FROM BugTag
                  WHERE BugTag.bug = BugTaskFlat.bug
                    AND BugTag.tag = 'eric')
               AND EXISTS
                 (SELECT 1 FROM BugTag
                  WHERE BugTag.bug = BugTaskFlat.bug
                    AND BugTag.tag = 'fred')
               AND NOT EXISTS
                 (SELECT 1 FROM BugTag
                  WHERE BugTag.bug = BugTaskFlat.bug)""",
            self.searchClause(all(u'fred', u'-bob', u'eric', u'-*')))
        # The positive wildcard is superfluous in the presence of
        # other positive tags, and the negative wildcard is dominant
        # over other negative tags.
        self.assertEqualIgnoringWhitespace(
            """EXISTS
                  (SELECT 1 FROM BugTag
                    WHERE BugTag.bug = BugTaskFlat.bug
                      AND BugTag.tag = 'fred')
                AND NOT EXISTS
                  (SELECT 1 FROM BugTag
                    WHERE BugTag.bug = BugTaskFlat.bug)""",
            self.searchClause(all(u'fred', u'-*', u'*', u'-harry')))

    def test_mixed_wildcards(self):
        # The WHERE clause to test for the presence of tags or the
        # absence of tags.
        self.assertEqualIgnoringWhitespace(
            """EXISTS
                  (SELECT 1 FROM BugTag
                    WHERE BugTag.bug = BugTaskFlat.bug)
                OR NOT EXISTS
                  (SELECT 1 FROM BugTag
                    WHERE BugTag.bug = BugTaskFlat.bug)""",
            self.searchClause(any(u'*', u'-*')))
        # The WHERE clause to test for the presence of tags and the
        # absence of tags.
        self.assertEqualIgnoringWhitespace(
            """EXISTS
                  (SELECT 1 FROM BugTag
                    WHERE BugTag.bug = BugTaskFlat.bug)
                AND NOT EXISTS
                  (SELECT 1 FROM BugTag
                    WHERE BugTag.bug = BugTaskFlat.bug)""",
            self.searchClause(all(u'*', u'-*')))


class TestBugTaskHardwareSearch(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def test_search_results_without_duplicates(self):
        # Searching for hardware related bugtasks returns each
        # matching task exactly once, even if devices from more than
        # one HWDB submission match the given criteria.
        new_submission = self.factory.makeHWSubmission(
            emailaddress=u'test@canonical.com')
        device = getUtility(IHWDeviceSet).getByDeviceID(
            HWBus.PCI, '0x10de', '0x0455')
        with dbuser('hwdb-submission-processor'):
            self.factory.makeHWSubmissionDevice(
                new_submission, device, None, None, 1)
        search_params = BugTaskSearchParams(
            user=None, hardware_bus=HWBus.PCI, hardware_vendor_id='0x10de',
            hardware_product_id='0x0455', hardware_owner_is_bug_reporter=True)
        ubuntu = getUtility(IDistributionSet).getByName('ubuntu')
        bugtasks = ubuntu.searchTasks(search_params)
        self.assertEqual(
            [1, 2],
            [bugtask.bug.id for bugtask in bugtasks])


class TestBugTaskSearch(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def login(self):
        # Log in as an arbitrary person.
        person = self.factory.makePerson()
        login_person(person)
        self.addCleanup(logout)
        return person

    def makeBugTarget(self):
        """Make an arbitrary bug target with no tasks on it."""
        return IBugTarget(self.factory.makeProduct())

    def test_no_tasks(self):
        # A brand new bug target has no tasks.
        target = self.makeBugTarget()
        self.assertEqual([], list(target.searchTasks(None)))

    def test_new_task_shows_up(self):
        # When we create a new bugtask on the target, it shows up in
        # searchTasks.
        target = self.makeBugTarget()
        self.login()
        task = self.factory.makeBugTask(target=target)
        self.assertEqual([task], list(target.searchTasks(None)))

    def test_modified_since_excludes_earlier_bugtasks(self):
        # When we search for bug tasks that have been modified since a certain
        # time, tasks for bugs that have not been modified since then are
        # excluded.
        target = self.makeBugTarget()
        self.login()
        task = self.factory.makeBugTask(target=target)
        date = task.bug.date_last_updated + timedelta(days=1)
        result = target.searchTasks(None, modified_since=date)
        self.assertEqual([], list(result))

    def test_modified_since_includes_later_bugtasks(self):
        # When we search for bug tasks that have been modified since a certain
        # time, tasks for bugs that have been modified since then are
        # included.
        target = self.makeBugTarget()
        self.login()
        task = self.factory.makeBugTask(target=target)
        date = task.bug.date_last_updated - timedelta(days=1)
        result = target.searchTasks(None, modified_since=date)
        self.assertEqual([task], list(result))

    def test_modified_since_includes_later_bugtasks_excludes_earlier(self):
        # When we search for bugs that have been modified since a certain
        # time, tasks for bugs that have been modified since then are
        # included, tasks that have not are excluded.
        target = self.makeBugTarget()
        self.login()
        task1 = self.factory.makeBugTask(target=target)
        date = task1.bug.date_last_updated
        bug1 = removeSecurityProxy(task1.bug)
        bug1.date_last_updated -= timedelta(days=1)
        task2 = self.factory.makeBugTask(target=target)
        bug2 = removeSecurityProxy(task2.bug)
        bug2.date_last_updated += timedelta(days=1)
        result = target.searchTasks(None, modified_since=date)
        self.assertEqual([task2], list(result))

    def test_private_bug_view_permissions_cached(self):
        """Private bugs from a search know the user can see the bugs."""
        target = self.makeBugTarget()
        person = self.login()
        self.factory.makeBug(target=target, owner=person,
            information_type=InformationType.USERDATA)
        self.factory.makeBug(target=target, owner=person,
            information_type=InformationType.USERDATA)
        self.factory.makeBug(target=target, owner=person,
            information_type=InformationType.USERDATA)
        # Search style and parameters taken from the milestone index view
        # where the issue was discovered.
        login_person(person)
        tasks = target.searchTasks(BugTaskSearchParams(
            person, omit_dupes=True, orderby=['status', '-importance', 'id']))
        # We must have found the bugs.
        self.assertEqual(3, tasks.count())
        # Cache in the storm cache the account->person lookup so its not
        # distorting what we're testing.
        IPerson(person.account, None)
        # The should take 2 queries - one for the tasks, one for the related
        # products (eager loaded targets).
        has_expected_queries = HasQueryCount(Equals(4))
        # No extra queries should be issued to access a regular attribute
        # on the bug that would normally trigger lazy evaluation for security
        # checking.  Note that the 'id' attribute does not trigger a check.
        with StormStatementRecorder() as recorder:
            [task.getConjoinedMaster for task in tasks]
            self.assertThat(recorder, has_expected_queries)

    def test_omit_targeted_default_is_false(self):
        # The default value of omit_targeted is false so bugs targeted
        # to a series are not hidden.
        target = self.factory.makeDistroSeries()
        self.login()
        task1 = self.factory.makeBugTask(target=target)
        default_result = target.searchTasks(None)
        self.assertEqual([task1], list(default_result))

    def test_created_since_excludes_earlier_bugtasks(self):
        # When we search for bug tasks that have been created since a certain
        # time, tasks for bugs that have not been created since then are
        # excluded.
        target = self.makeBugTarget()
        self.login()
        task = self.factory.makeBugTask(target=target)
        date = task.datecreated + timedelta(days=1)
        result = target.searchTasks(None, created_since=date)
        self.assertEqual([], list(result))

    def test_created_since_includes_later_bugtasks(self):
        # When we search for bug tasks that have been created since a certain
        # time, tasks for bugs that have been created since then are
        # included.
        target = self.makeBugTarget()
        self.login()
        task = self.factory.makeBugTask(target=target)
        date = task.datecreated - timedelta(days=1)
        result = target.searchTasks(None, created_since=date)
        self.assertEqual([task], list(result))

    def test_created_since_includes_later_bugtasks_excludes_earlier(self):
        # When we search for bugs that have been created since a certain
        # time, tasks for bugs that have been created since then are
        # included, tasks that have not are excluded.
        target = self.makeBugTarget()
        self.login()
        task1 = self.factory.makeBugTask(target=target)
        date = task1.datecreated
        task1.datecreated -= timedelta(days=1)
        task2 = self.factory.makeBugTask(target=target)
        task2.datecreated += timedelta(days=1)
        result = target.searchTasks(None, created_since=date)
        self.assertEqual([task2], list(result))


class BugTaskSetSearchTest(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_explicit_blueprint_specified(self):
        # If the linked_blueprints is an integer id, then only bugtasks for
        # bugs that are linked to that blueprint are returned.
        bug1 = self.factory.makeBug()
        blueprint1 = self.factory.makeBlueprint()
        with person_logged_in(blueprint1.owner):
            blueprint1.linkBug(bug1)
        bug2 = self.factory.makeBug()
        blueprint2 = self.factory.makeBlueprint()
        with person_logged_in(blueprint2.owner):
            blueprint2.linkBug(bug2)
        self.factory.makeBug()
        params = BugTaskSearchParams(
            user=None, linked_blueprints=blueprint1.id)
        tasks = set(getUtility(IBugTaskSet).search(params))
        self.assertContentEqual(bug1.bugtasks, tasks)


class TargetLessTestCase(TestCaseWithFactory):
    """Test that do not call setTarget() in the BugTaskSearchParams."""

    layer = DatabaseFunctionalLayer

    def test_project_group_structural_subscription(self):
        # Search results can be limited to bugs without a bug target to which
        # a given person has a structural subscription.
        subscriber = self.factory.makePerson()
        product = self.factory.makeProduct()
        self.factory.makeBug(target=product)
        with person_logged_in(product.owner):
            project_group = self.factory.makeProject(owner=product.owner)
            product.project = project_group
        with person_logged_in(subscriber):
            project_group.addBugSubscription(subscriber, subscriber)
        params = BugTaskSearchParams(
            user=None, structural_subscriber=subscriber)
        bugtask_set = getUtility(IBugTaskSet)
        found_bugtasks = bugtask_set.search(params)
        self.assertEqual(1, found_bugtasks.count())


class BaseGetBugPrivacyFilterTermsTests:

    layer = DatabaseFunctionalLayer

    def test_public(self):
        bug = self.factory.makeBug()
        people = [bug.owner, self.factory.makePerson()]
        self.assertContentEqual(people, self.getVisiblePeople(bug, people))

    def makePrivacyScenario(self):
        self.owner = self.factory.makePerson()
        login_person(self.owner)
        self.bug = self.factory.makeBug(
            owner=self.owner, information_type=InformationType.USERDATA)
        self.grantee_member = self.factory.makePerson()
        self.grantee_team = self.factory.makeTeam(
            members=[self.grantee_member])
        self.grantee_person = self.factory.makePerson()
        self.other_person = self.factory.makePerson()

        self.people = [
            self.owner, self.grantee_team, self.grantee_member,
            self.grantee_person, self.other_person]
        self.expected_people = [
            self.owner, self.grantee_team, self.grantee_member,
            self.grantee_person]

    def assertPrivacyRespected(self):
        self.assertContentEqual(
            [], self.getVisiblePeople(self.bug, [self.other_person]))
        self.assertContentEqual(
            self.expected_people, self.getVisiblePeople(self.bug, self.people))

    def test_artifact_grant(self):
        # People and teams with AccessArtifactGrants can see the bug.
        self.makePrivacyScenario()

        getUtility(IService, 'sharing').ensureAccessGrants(
            [self.grantee_team, self.grantee_person], self.owner,
            bugs=[self.bug], ignore_permissions=True)

        self.assertPrivacyRespected()

    def test_policy_grant(self):
        # People and teams with AccessPolicyGrants can see the bug.
        self.makePrivacyScenario()

        with admin_logged_in():
            for princ in (self.grantee_team, self.grantee_person):
                getUtility(IService, 'sharing').sharePillarInformation(
                    self.bug.default_bugtask.target, princ, self.owner,
                    {InformationType.USERDATA: SharingPermission.ALL})

        self.assertPrivacyRespected()

    def test_admin(self):
        # People and teams in the admin team can see the bug.
        self.makePrivacyScenario()

        admins = getUtility(ILaunchpadCelebrities).admin
        with admin_logged_in():
            for princ in (self.grantee_team, self.grantee_person):
                admins.addMember(princ, admins)
            self.grantee_team.acceptInvitationToBeMemberOf(admins, None)

        self.assertPrivacyRespected()


class TestGetBugPrivacyFilterTerms(BaseGetBugPrivacyFilterTermsTests,
                                   TestCaseWithFactory):

    def getVisiblePeople(self, bug, people):
        return IStore(Bug).find(
            Person,
            Person.id.is_in(map(attrgetter('id'), people)),
            BugTaskFlat.bug_id == bug.id,
            Or(*get_bug_privacy_filter_terms(Person.id)))


class TestGetBugBulkPrivacyFilterTerms(BaseGetBugPrivacyFilterTermsTests,
                                       TestCaseWithFactory):

    def getVisiblePeople(self, bug, people):
        return IStore(Bug).find(
            Person,
            Person.id.is_in(map(attrgetter('id'), people)),
            get_bug_bulk_privacy_filter_terms(Person.id, bug.id))


def test_suite():
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()
    for bug_target_search_type_class in (
        PreloadBugtaskTargets, NoPreloadBugtaskTargets, QueryBugIDs):
        class_name = 'Test%s' % bug_target_search_type_class.__name__
        class_bases = (
            bug_target_search_type_class, ProductTarget, OnceTests,
            SearchTestBase, TestCaseWithFactory)
        test_class = type(class_name, class_bases, {})
        suite.addTest(loader.loadTestsFromTestCase(test_class))

        for target_mixin in bug_targets_mixins:
            class_name = 'Test%s%s' % (
                bug_target_search_type_class.__name__,
                target_mixin.__name__)
            mixins = [
                target_mixin, bug_target_search_type_class]
            class_bases = (
                tuple(mixins)
                + (TargetTests, SearchTestBase, TestCaseWithFactory))
            # Dynamically build a test class from the target mixin class,
            # from the search type mixin class, from the mixin class
            # having all tests and from a unit test base class.
            test_class = type(class_name, class_bases, {})
            # Add the new unit test class to the suite.
            suite.addTest(loader.loadTestsFromTestCase(test_class))
    suite.addTest(loader.loadTestsFromName(__name__))
    return suite
