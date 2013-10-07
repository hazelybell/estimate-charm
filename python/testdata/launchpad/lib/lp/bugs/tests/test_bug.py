# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for lp.bugs.model.Bug."""

__metaclass__ = type

from lazr.lifecycle.snapshot import Snapshot
from zope.component import getUtility
from zope.interface import providedBy
from zope.security.proxy import removeSecurityProxy

from lp.bugs.enums import BugNotificationLevel
from lp.bugs.interfaces.bug import (
    CreateBugParams,
    IBugSet,
    )
from lp.bugs.interfaces.bugtask import (
    BugTaskImportance,
    BugTaskStatus,
    IllegalTarget,
    UserCannotEditBugTaskAssignee,
    UserCannotEditBugTaskImportance,
    UserCannotEditBugTaskMilestone,
    )
from lp.testing import (
    person_logged_in,
    StormStatementRecorder,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestBugSubscriptionMethods(TestCaseWithFactory):
    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBugSubscriptionMethods, self).setUp()
        self.bug = self.factory.makeBug()
        self.person = self.factory.makePerson()

    def test_is_muted_returns_true_for_muted_users(self):
        # Bug.isMuted() will return True if the person passed to it is muted.
        with person_logged_in(self.person):
            self.bug.mute(self.person, self.person)
            self.assertEqual(True, self.bug.isMuted(self.person))

    def test_is_muted_returns_false_for_direct_subscribers(self):
        # Bug.isMuted() will return False if the user has a
        # regular subscription.
        with person_logged_in(self.person):
            self.bug.subscribe(
                self.person, self.person, level=BugNotificationLevel.METADATA)
            self.assertEqual(False, self.bug.isMuted(self.person))

    def test_is_muted_returns_false_for_non_subscribers(self):
        # Bug.isMuted() will return False if the user has no
        # subscription.
        with person_logged_in(self.person):
            self.assertEqual(False, self.bug.isMuted(self.person))

    def test_mute_team_fails(self):
        # Muting a subscription for an entire team doesn't work.
        with person_logged_in(self.person):
            team = self.factory.makeTeam(owner=self.person)
            self.assertRaises(AssertionError,
                              self.bug.mute, team, team)

    def test_mute_mutes_user(self):
        # Bug.mute() adds a BugMute record for the person passed to it.
        with person_logged_in(self.person):
            self.bug.mute(self.person, self.person)
            naked_bug = removeSecurityProxy(self.bug)
            bug_mute = naked_bug._getMutes(self.person).one()
            self.assertEqual(self.bug, bug_mute.bug)
            self.assertEqual(self.person, bug_mute.person)

    def test_mute_mutes_muter(self):
        # When exposed in the web API, the mute method regards the
        # first, `person` argument as optional, and the second
        # `muted_by` argument is supplied from the request.  In this
        # case, the person should be the muter.
        with person_logged_in(self.person):
            self.bug.mute(None, self.person)
            self.assertTrue(self.bug.isMuted(self.person))

    def test_mute_mutes_user_with_existing_subscription(self):
        # Bug.mute() will not touch the existing subscription.
        with person_logged_in(self.person):
            subscription = self.bug.subscribe(
                self.person, self.person,
                level=BugNotificationLevel.METADATA)
            self.bug.mute(self.person, self.person)
            self.assertTrue(self.bug.isMuted(self.person))
            self.assertEqual(
                BugNotificationLevel.METADATA,
                subscription.bug_notification_level)

    def test_unmute_unmutes_user(self):
        # Bug.unmute() will remove a muted subscription for the user
        # passed to it.
        with person_logged_in(self.person):
            self.bug.mute(self.person, self.person)
            self.assertTrue(self.bug.isMuted(self.person))
            self.bug.unmute(self.person, self.person)
            self.assertFalse(self.bug.isMuted(self.person))

    def test_unmute_returns_direct_subscription(self):
        # Bug.unmute() returns the previously muted direct subscription, if
        # any.
        with person_logged_in(self.person):
            self.bug.mute(self.person, self.person)
            self.assertEqual(True, self.bug.isMuted(self.person))
            self.assertEqual(None, self.bug.unmute(self.person, self.person))
            self.assertEqual(False, self.bug.isMuted(self.person))
            subscription = self.bug.subscribe(
                self.person, self.person,
                level=BugNotificationLevel.METADATA)
            self.bug.mute(self.person, self.person)
            self.assertEqual(True, self.bug.isMuted(self.person))
            self.assertEqual(
                subscription, self.bug.unmute(self.person, self.person))

    def test_unmute_mutes_unmuter(self):
        # When exposed in the web API, the unmute method regards the
        # first, `person` argument as optional, and the second
        # `unmuted_by` argument is supplied from the request.  In this
        # case, the person should be the muter.
        with person_logged_in(self.person):
            self.bug.mute(self.person, self.person)
            self.bug.unmute(None, self.person)
            self.assertFalse(self.bug.isMuted(self.person))

    def test_double_unmute(self):
        # If unmute is called when not muted, it is a no-op.
        with person_logged_in(self.person):
            self.bug.mute(self.person, self.person)
            subscriptions = self.bug.unmute(self.person, self.person)
            sec_subscriptions = self.bug.unmute(self.person, self.person)
            self.assertEqual(sec_subscriptions, subscriptions)


class TestBugSnapshotting(TestCaseWithFactory):
    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBugSnapshotting, self).setUp()
        self.bug = self.factory.makeBug()
        self.person = self.factory.makePerson()

    def test_bug_snapshot_does_not_include_messages(self):
        # A snapshot of a bug does not include its messages or
        # attachments (which get the messages from the database).  If it
        # does, the webservice can become unusable if changes are made
        # to bugs with many comments, such as bug 1. See, for instance,
        # bug 744888.  This test is primarily to keep the problem from
        # slipping in again.  To do so, we resort to somewhat
        # extraordinary measures.  In addition to verifying that the
        # snapshot does not have the attributes that currently trigger
        # the problem, we also actually look at the SQL that is
        # generated by creating the snapshot.  With this, we can verify
        # that the Message table is not included.  This is ugly, but
        # this has a chance of fighting against future eager loading
        # optimizations that might trigger the problem again.
        with person_logged_in(self.person):
            with StormStatementRecorder() as recorder:
                Snapshot(self.bug, providing=providedBy(self.bug))
            sql_statements = recorder.statements
        # This uses "self" as a marker to show that the attribute does not
        # exist.  We do not use hasattr because it eats exceptions.
        #self.assertTrue(getattr(snapshot, 'messages', self) is self)
        #self.assertTrue(getattr(snapshot, 'attachments', self) is self)
        for sql in sql_statements:
            # We are going to be aggressive about looking for the problem in
            # the SQL.  We'll split the SQL up by whitespace, and then look
            # for strings that start with "message".  If that is too
            # aggressive in the future from some reason, please do adjust the
            # test appropriately.
            sql_tokens = sql.lower().split()
            self.assertEqual(
                [token for token in sql_tokens
                 if token.startswith('message')],
                [])
            self.assertEqual(
                [token for token in sql_tokens
                 if token.startswith('bugactivity')],
                [])


class TestBugCreation(TestCaseWithFactory):
    """Tests for bug creation."""

    layer = DatabaseFunctionalLayer

    def createBug(self, owner=None, title="A bug",
                  comment="Nothing important.", **kwargs):
        with person_logged_in(owner):
            params = CreateBugParams(
                owner=owner, title=title, comment=comment, **kwargs)
            bug = getUtility(IBugSet).createBug(params)
        return bug

    def test_CreateBugParams_accepts_target(self):
        # The initial bug task's target can be set using
        # CreateBugParams.
        owner = self.factory.makePerson()
        target = self.factory.makeProduct(owner=owner)
        bug = self.createBug(owner=owner, target=target)
        self.assertEqual(bug.default_bugtask.target, target)

    def test_CreateBugParams_rejects_series_target(self):
        # createBug refuses attempts to create a bug with a series
        # target. A non-series task must be created first.
        owner = self.factory.makePerson()
        target = self.factory.makeProductSeries(owner=owner)
        self.assertRaises(
            IllegalTarget, self.createBug, owner=owner, target=target)

    def test_CreateBugParams_accepts_importance(self):
        # The importance of the initial bug task can be set using
        # CreateBugParams
        owner = self.factory.makePerson()
        target = self.factory.makeProduct(owner=owner)
        bug = self.createBug(
            owner=owner, target=target, importance=BugTaskImportance.HIGH)
        self.assertEqual(
            BugTaskImportance.HIGH, bug.default_bugtask.importance)

    def test_CreateBugParams_accepts_assignee(self):
        # The assignee of the initial bug task can be set using
        # CreateBugParams
        owner = self.factory.makePerson()
        target = self.factory.makeProduct(owner=owner)
        bug = self.createBug(owner=owner, target=target, assignee=owner)
        self.assertEqual(owner, bug.default_bugtask.assignee)

    def test_CreateBugParams_accepts_milestone(self):
        # The milestone of the initial bug task can be set using
        # CreateBugParams
        owner = self.factory.makePerson()
        target = self.factory.makeProduct(owner=owner)
        milestone = self.factory.makeMilestone(product=target)
        bug = self.createBug(owner=owner, target=target, milestone=milestone)
        self.assertEqual(milestone, bug.default_bugtask.milestone)

    def test_CreateBugParams_accepts_status(self):
        # The status of the initial bug task can be set using
        # CreateBugParams
        owner = self.factory.makePerson()
        target = self.factory.makeProduct(owner=owner)
        bug = self.createBug(
            owner=owner, target=target, status=BugTaskStatus.TRIAGED)
        self.assertEqual(BugTaskStatus.TRIAGED, bug.default_bugtask.status)

    def test_CreateBugParams_rejects_not_allowed_importance_changes(self):
        # createBug() will reject any importance value passed by users
        # who don't have the right to set the importance.
        person = self.factory.makePerson()
        target = self.factory.makeProduct()
        self.assertRaises(
            UserCannotEditBugTaskImportance,
            self.createBug, owner=person, target=target,
            importance=BugTaskImportance.HIGH)

    def test_CreateBugParams_rejects_not_allowed_assignee_changes(self):
        # createBug() will reject any importance value passed by users
        # who don't have the right to set the assignee.
        person = self.factory.makePerson()
        person_2 = self.factory.makePerson()
        target = self.factory.makeProduct()
        # Setting the target's bug supervisor means that
        # canTransitionToAssignee() will return False for `person` if
        # another Person is passed as `assignee`.
        with person_logged_in(target.owner):
            target.bug_supervisor = target.owner
        self.assertRaises(
            UserCannotEditBugTaskAssignee,
            self.createBug, owner=person, target=target, assignee=person_2)

    def test_CreateBugParams_rejects_not_allowed_milestone_changes(self):
        # createBug() will reject any importance value passed by users
        # who don't have the right to set the milestone.
        person = self.factory.makePerson()
        target = self.factory.makeProduct()
        self.assertRaises(
            UserCannotEditBugTaskMilestone,
            self.createBug, owner=person, target=target,
            milestone=self.factory.makeMilestone(product=target))

    def test_createBug_cve(self):
        cve = self.factory.makeCVE('1999-1717')
        target = self.factory.makeProduct()
        person = self.factory.makePerson()
        bug = self.createBug(owner=person, target=target, cve=cve)
        self.assertEqual([cve], [cve_link.cve for cve_link in bug.cve_links])

    def test_createBug_subscribers(self):
        # Bugs normally start with just the reporter subscribed.
        person = self.factory.makePerson()
        target = self.factory.makeProduct()
        bug = self.createBug(owner=person, target=target)
        self.assertContentEqual([person], bug.getDirectSubscribers())
