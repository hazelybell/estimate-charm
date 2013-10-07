# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for merge_people."""

from datetime import datetime

import pytz
from testtools.matchers import MatchesStructure
import transaction
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.registry.interfaces.accesspolicy import (
    IAccessArtifactGrantSource,
    IAccessPolicyGrantSource,
    )
from lp.registry.interfaces.karma import IKarmaCacheManager
from lp.registry.interfaces.mailinglist import MailingListStatus
from lp.registry.interfaces.mailinglistsubscription import (
    MailingListAutoSubscribePolicy,
    )
from lp.registry.interfaces.person import (
    IPersonSet,
    TeamMembershipStatus,
    )
from lp.registry.interfaces.personnotification import IPersonNotificationSet
from lp.registry.personmerge import (
    _mergeMailingListSubscriptions,
    merge_people,
    )
from lp.registry.tests.test_person import KarmaTestMixin
from lp.services.config import config
from lp.services.database.sqlbase import cursor
from lp.services.identity.interfaces.emailaddress import (
    EmailAddressStatus,
    IEmailAddressSet,
    )
from lp.soyuz.enums import ArchiveStatus
from lp.testing import (
    celebrity_logged_in,
    login_person,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.dbuser import dbuser
from lp.testing.layers import DatabaseFunctionalLayer


class TestMergePeople(TestCaseWithFactory, KarmaTestMixin):
    """Test cases for PersonSet merge."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestMergePeople, self).setUp()
        self.person_set = getUtility(IPersonSet)

    def _do_premerge(self, from_person, to_person):
        # Do the pre merge work performed by the LoginToken.
        with celebrity_logged_in('admin'):
            email = from_person.preferredemail
            email.status = EmailAddressStatus.NEW
            email.person = to_person
        transaction.commit()

    def _do_merge(self, from_person, to_person, reviewer=None):
        # Perform the merge as the db user that will be used by the jobs.
        with dbuser(config.IPersonMergeJobSource.dbuser):
            merge_people(from_person, to_person, reviewer=reviewer)
        return from_person, to_person

    def _get_testable_account(self, person, date_created, openid_identifier):
        # Return a naked account with predictable attributes.
        account = removeSecurityProxy(person.account)
        account.date_created = date_created
        account.openid_identifier = openid_identifier
        return account

    def test_delete_no_notifications(self):
        team = self.factory.makeTeam()
        owner = team.teamowner
        transaction.commit()
        with dbuser(config.IPersonMergeJobSource.dbuser):
            merge_people(
                team, getUtility(ILaunchpadCelebrities).registry_experts,
                owner, delete=True)
        notification_set = getUtility(IPersonNotificationSet)
        notifications = notification_set.getNotificationsToSend()
        self.assertEqual(0, notifications.count())

    def test_openid_identifiers(self):
        # Verify that OpenId Identifiers are merged.
        duplicate = self.factory.makePerson()
        duplicate_identifier = removeSecurityProxy(
            duplicate.account).openid_identifiers.any().identifier
        person = self.factory.makePerson()
        person_identifier = removeSecurityProxy(
            person.account).openid_identifiers.any().identifier
        self._do_premerge(duplicate, person)
        login_person(person)
        duplicate, person = self._do_merge(duplicate, person)
        self.assertEqual(
            0,
            removeSecurityProxy(duplicate.account).openid_identifiers.count())

        merged_identifiers = [
            identifier.identifier for identifier in
                removeSecurityProxy(person.account).openid_identifiers]

        self.assertIn(duplicate_identifier, merged_identifiers)
        self.assertIn(person_identifier, merged_identifiers)

    def test_karmacache_transferred_to_user_has_no_karma(self):
        # Verify that the merged user has no KarmaCache entries,
        # and the karma total was transfered.
        self.cache_manager = getUtility(IKarmaCacheManager)
        product = self.factory.makeProduct()
        duplicate = self.factory.makePerson()
        self._makeKarmaCache(
            duplicate, product, [('bugs', 10)])
        self._makeKarmaTotalCache(duplicate, 15)
        # The karma changes invalidated duplicate instance.
        duplicate = self.person_set.get(duplicate.id)
        person = self.factory.makePerson()
        self._do_premerge(duplicate, person)
        login_person(person)
        duplicate, person = self._do_merge(duplicate, person)
        self.assertEqual([], duplicate.karma_category_caches)
        self.assertEqual(0, duplicate.karma)
        self.assertEqual(15, person.karma)

    def test_karmacache_transferred_to_user_has_karma(self):
        # Verify that the merged user has no KarmaCache entries,
        # and the karma total was summed.
        self.cache_manager = getUtility(IKarmaCacheManager)
        product = self.factory.makeProduct()
        duplicate = self.factory.makePerson()
        self._makeKarmaCache(
            duplicate, product, [('bugs', 10)])
        self._makeKarmaTotalCache(duplicate, 15)
        person = self.factory.makePerson()
        self._makeKarmaCache(
            person, product, [('bugs', 9)])
        self._makeKarmaTotalCache(person, 13)
        # The karma changes invalidated duplicate and person instances.
        duplicate = self.person_set.get(duplicate.id)
        person = self.person_set.get(person.id)
        self._do_premerge(duplicate, person)
        login_person(person)
        duplicate, person = self._do_merge(duplicate, person)
        self.assertEqual([], duplicate.karma_category_caches)
        self.assertEqual(0, duplicate.karma)
        self.assertEqual(28, person.karma)

    def test_person_date_created_preserved(self):
        # Verify that the oldest datecreated is merged.
        person = self.factory.makePerson()
        duplicate = self.factory.makePerson()
        oldest_date = datetime(
            2005, 11, 25, 0, 0, 0, 0, pytz.timezone('UTC'))
        removeSecurityProxy(duplicate).datecreated = oldest_date
        self._do_premerge(duplicate, person)
        login_person(person)
        duplicate, person = self._do_merge(duplicate, person)
        self.assertEqual(oldest_date, person.datecreated)

    def test_team_with_active_mailing_list_raises_error(self):
        # A team with an active mailing list cannot be merged.
        target_team = self.factory.makeTeam()
        test_team = self.factory.makeTeam()
        self.factory.makeMailingList(
            test_team, test_team.teamowner)
        self.assertRaises(
            AssertionError, merge_people, test_team, target_team, None)

    def test_team_with_inactive_mailing_list(self):
        # A team with an inactive mailing list can be merged.
        target_team = self.factory.makeTeam()
        test_team = self.factory.makeTeam()
        mailing_list = self.factory.makeMailingList(
            test_team, test_team.teamowner)
        mailing_list.deactivate()
        mailing_list.transitionToStatus(MailingListStatus.INACTIVE)
        test_team, target_team = self._do_merge(
            test_team, target_team, test_team.teamowner)
        self.assertEqual(target_team, test_team.merged)
        self.assertEqual(
            MailingListStatus.PURGED, test_team.mailing_list.status)
        emails = getUtility(IEmailAddressSet).getByPerson(target_team).count()
        self.assertEqual(0, emails)

    def test_team_with_purged_mailing_list(self):
        # A team with a purges mailing list can be merged.
        target_team = self.factory.makeTeam()
        test_team = self.factory.makeTeam()
        mailing_list = self.factory.makeMailingList(
            test_team, test_team.teamowner)
        mailing_list.deactivate()
        mailing_list.transitionToStatus(MailingListStatus.INACTIVE)
        mailing_list.purge()
        test_team, target_team = self._do_merge(
            test_team, target_team, test_team.teamowner)
        self.assertEqual(target_team, test_team.merged)

    def test_team_with_members(self):
        # Team members are removed before merging.
        target_team = self.factory.makeTeam()
        test_team = self.factory.makeTeam()
        former_member = self.factory.makePerson()
        with person_logged_in(test_team.teamowner):
            test_team.addMember(former_member, test_team.teamowner)
        test_team, target_team = self._do_merge(
            test_team, target_team, test_team.teamowner)
        self.assertEqual(target_team, test_team.merged)
        self.assertEqual([], list(former_member.super_teams))

    def test_team_without_super_teams_is_fine(self):
        # A team with no members and no super teams
        # merges without errors.
        test_team = self.factory.makeTeam()
        target_team = self.factory.makeTeam()
        login_person(test_team.teamowner)
        self._do_merge(test_team, target_team, test_team.teamowner)

    def test_team_with_super_teams(self):
        # A team with superteams can be merged, but the memberships
        # are not transferred.
        test_team = self.factory.makeTeam()
        super_team = self.factory.makeTeam()
        target_team = self.factory.makeTeam()
        login_person(test_team.teamowner)
        test_team.join(super_team, test_team.teamowner)
        test_team, target_team = self._do_merge(
            test_team, target_team, test_team.teamowner)
        self.assertEqual(target_team, test_team.merged)
        self.assertEqual([], list(target_team.super_teams))

    def test_merge_moves_branches(self):
        # When person/teams are merged, branches owned by the from person
        # are moved.
        person = self.factory.makePerson()
        branch = self.factory.makeBranch()
        duplicate = branch.owner
        self._do_premerge(branch.owner, person)
        login_person(person)
        duplicate, person = self._do_merge(duplicate, person)
        branches = person.getBranches()
        self.assertEqual(1, branches.count())

    def test_merge_with_duplicated_branches(self):
        # If both the from and to people have branches with the same name,
        # merging renames the duplicate from the from person's side.
        product = self.factory.makeProduct()
        from_branch = self.factory.makeBranch(name='foo', product=product)
        to_branch = self.factory.makeBranch(name='foo', product=product)
        mergee = to_branch.owner
        duplicate = from_branch.owner
        self._do_premerge(duplicate, mergee)
        login_person(mergee)
        duplicate, mergee = self._do_merge(duplicate, mergee)
        branches = [b.name for b in mergee.getBranches()]
        self.assertEqual(2, len(branches))
        self.assertContentEqual([u'foo', u'foo-1'], branches)

    def test_merge_moves_recipes(self):
        # When person/teams are merged, recipes owned by the from person are
        # moved.
        person = self.factory.makePerson()
        recipe = self.factory.makeSourcePackageRecipe()
        duplicate = recipe.owner
        # Delete the PPA, which is required for the merge to work.
        with person_logged_in(duplicate):
            recipe.owner.archive.status = ArchiveStatus.DELETED
        self._do_premerge(duplicate, person)
        login_person(person)
        duplicate, person = self._do_merge(duplicate, person)
        self.assertEqual(1, person.recipes.count())

    def test_merge_with_duplicated_recipes(self):
        # If both the from and to people have recipes with the same name,
        # merging renames the duplicate from the from person's side.
        merge_from = self.factory.makeSourcePackageRecipe(
            name=u'foo', description=u'FROM')
        merge_to = self.factory.makeSourcePackageRecipe(
            name=u'foo', description=u'TO')
        duplicate = merge_from.owner
        mergee = merge_to.owner
        # Delete merge_from's PPA, which is required for the merge to work.
        with person_logged_in(merge_from.owner):
            merge_from.owner.archive.status = ArchiveStatus.DELETED
        self._do_premerge(merge_from.owner, mergee)
        login_person(mergee)
        duplicate, mergee = self._do_merge(duplicate, mergee)
        recipes = mergee.recipes
        self.assertEqual(2, recipes.count())
        descriptions = [r.description for r in recipes]
        self.assertEqual([u'TO', u'FROM'], descriptions)
        self.assertEqual(u'foo-1', recipes[1].name)

    def assertSubscriptionMerges(self, target):
        # Given a subscription target, we want to make sure that subscriptions
        # that the duplicate person made are carried over to the merged
        # account.
        duplicate = self.factory.makePerson()
        with person_logged_in(duplicate):
            target.addSubscription(duplicate, duplicate)
        person = self.factory.makePerson()
        self._do_premerge(duplicate, person)
        login_person(person)
        duplicate, person = self._do_merge(duplicate, person)
        # The merged person has the subscription, and the duplicate person
        # does not.
        self.assertTrue(target.getSubscription(person) is not None)
        self.assertTrue(target.getSubscription(duplicate) is None)

    def assertConflictingSubscriptionDeletes(self, target):
        # Given a subscription target, we want to make sure that subscriptions
        # that the duplicate person made that conflict with existing
        # subscriptions in the merged account are deleted.
        duplicate = self.factory.makePerson()
        person = self.factory.makePerson()
        with person_logged_in(duplicate):
            target.addSubscription(duplicate, duplicate)
        with person_logged_in(person):
            # The description lets us show that we still have the right
            # subscription later.
            target.addBugSubscriptionFilter(person, person).description = (
                u'a marker')
        self._do_premerge(duplicate, person)
        login_person(person)
        duplicate, person = self._do_merge(duplicate, person)
        # The merged person still has the original subscription, as shown
        # by the marker name.
        self.assertEqual(
            target.getSubscription(person).bug_filters[0].description,
            u'a marker')
        # The conflicting subscription on the duplicate has been deleted.
        self.assertTrue(target.getSubscription(duplicate) is None)

    def test_merge_with_product_subscription(self):
        # See comments in assertSubscriptionMerges.
        self.assertSubscriptionMerges(self.factory.makeProduct())

    def test_merge_with_conflicting_product_subscription(self):
        # See comments in assertConflictingSubscriptionDeletes.
        self.assertConflictingSubscriptionDeletes(self.factory.makeProduct())

    def test_merge_with_project_subscription(self):
        # See comments in assertSubscriptionMerges.
        self.assertSubscriptionMerges(self.factory.makeProject())

    def test_merge_with_conflicting_project_subscription(self):
        # See comments in assertConflictingSubscriptionDeletes.
        self.assertConflictingSubscriptionDeletes(self.factory.makeProject())

    def test_merge_with_distroseries_subscription(self):
        # See comments in assertSubscriptionMerges.
        self.assertSubscriptionMerges(self.factory.makeDistroSeries())

    def test_merge_with_conflicting_distroseries_subscription(self):
        # See comments in assertConflictingSubscriptionDeletes.
        self.assertConflictingSubscriptionDeletes(
            self.factory.makeDistroSeries())

    def test_merge_with_milestone_subscription(self):
        # See comments in assertSubscriptionMerges.
        self.assertSubscriptionMerges(self.factory.makeMilestone())

    def test_merge_with_conflicting_milestone_subscription(self):
        # See comments in assertConflictingSubscriptionDeletes.
        self.assertConflictingSubscriptionDeletes(
            self.factory.makeMilestone())

    def test_merge_with_productseries_subscription(self):
        # See comments in assertSubscriptionMerges.
        self.assertSubscriptionMerges(self.factory.makeProductSeries())

    def test_merge_with_conflicting_productseries_subscription(self):
        # See comments in assertConflictingSubscriptionDeletes.
        self.assertConflictingSubscriptionDeletes(
            self.factory.makeProductSeries())

    def test_merge_with_distribution_subscription(self):
        # See comments in assertSubscriptionMerges.
        self.assertSubscriptionMerges(self.factory.makeDistribution())

    def test_merge_with_conflicting_distribution_subscription(self):
        # See comments in assertConflictingSubscriptionDeletes.
        self.assertConflictingSubscriptionDeletes(
            self.factory.makeDistribution())

    def test_merge_with_sourcepackage_subscription(self):
        # See comments in assertSubscriptionMerges.
        dsp = self.factory.makeDistributionSourcePackage()
        self.assertSubscriptionMerges(dsp)

    def test_merge_with_conflicting_sourcepackage_subscription(self):
        # See comments in assertConflictingSubscriptionDeletes.
        dsp = self.factory.makeDistributionSourcePackage()
        self.assertConflictingSubscriptionDeletes(dsp)

    def test_merge_accessartifactgrant(self):
        # AccessArtifactGrants are transferred; DB triggers complete.
        dupe = self.factory.makePerson()
        bug = self.factory.makeBug(
            information_type=InformationType.USERDATA)
        artifact = self.factory.makeAccessArtifact(concrete=bug)
        self.factory.makeAccessArtifactGrant(artifact, dupe)
        person = self.factory.makePerson()
        self._do_premerge(dupe, person)
        with person_logged_in(person):
            self._do_merge(dupe, person)
        source = getUtility(IAccessArtifactGrantSource)
        grantees = [
            grant.grantee for grant in source.findByArtifact([artifact])
            if grant.grantee == person]
        self.assertContentEqual([person], grantees)

    def test_merge_accesspolicygrants(self):
        # AccessPolicyGrants are transferred from the duplicate.
        person = self.factory.makePerson()
        grant = self.factory.makeAccessPolicyGrant()
        self._do_premerge(grant.grantee, person)

        source = getUtility(IAccessPolicyGrantSource)
        self.assertEqual(
            grant.grantee, source.findByPolicy([grant.policy]).one().grantee)
        with person_logged_in(person):
            self._do_merge(grant.grantee, person)
        self.assertEqual(
            person, source.findByPolicy([grant.policy]).one().grantee)

    def test_merge_accesspolicygrants_conflicts(self):
        # Conflicting AccessPolicyGrants are deleted.
        policy = self.factory.makeAccessPolicy()

        person = self.factory.makePerson()
        person_grantor = self.factory.makePerson()
        person_grant = self.factory.makeAccessPolicyGrant(
            grantee=person, grantor=person_grantor, policy=policy)
        person_grant_date = person_grant.date_created

        duplicate = self.factory.makePerson()
        duplicate_grantor = self.factory.makePerson()
        self.factory.makeAccessPolicyGrant(
            grantee=duplicate, grantor=duplicate_grantor, policy=policy)

        self._do_premerge(duplicate, person)
        with person_logged_in(person):
            self._do_merge(duplicate, person)

        # Only one grant for the policy exists: the retained person's.
        source = getUtility(IAccessPolicyGrantSource)
        self.assertThat(
            source.findByPolicy([policy]).one(),
            MatchesStructure.byEquality(
                policy=policy,
                grantee=person,
                date_created=person_grant_date))

    def test_mergeAsync(self):
        # mergeAsync() creates a new `PersonMergeJob`.
        from_person = self.factory.makePerson()
        to_person = self.factory.makePerson()
        login_person(from_person)
        job = self.person_set.mergeAsync(from_person, to_person, from_person)
        self.assertEqual(from_person, job.from_person)
        self.assertEqual(to_person, job.to_person)
        self.assertEqual(from_person, job.requester)

    def test_mergeProposedInvitedTeamMembership(self):
        # Proposed and invited memberships are declined.
        TMS = TeamMembershipStatus
        dupe_team = self.factory.makeTeam()
        test_team = self.factory.makeTeam()
        inviting_team = self.factory.makeTeam()
        proposed_team = self.factory.makeTeam()
        with celebrity_logged_in('admin'):
            # Login as a user who can work with all these teams.
            inviting_team.addMember(
                dupe_team, inviting_team.teamowner)
            proposed_team.addMember(
                dupe_team, dupe_team.teamowner, status=TMS.PROPOSED)
            self._do_merge(dupe_team, test_team, test_team.teamowner)
            self.assertEqual(0, inviting_team.invited_member_count)
            self.assertEqual(0, proposed_team.proposed_member_count)


class TestMergeMailingListSubscriptions(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        # Use the unsecured PersonSet so that private methods can be tested.
        self.from_person = self.factory.makePerson()
        self.to_person = self.factory.makePerson()
        self.cur = cursor()

    def test__mergeMailingListSubscriptions_no_subscriptions(self):
        _mergeMailingListSubscriptions(
            self.cur, self.from_person.id, self.to_person.id)
        self.assertEqual(0, self.cur.rowcount)

    def test__mergeMailingListSubscriptions_with_subscriptions(self):
        naked_person = removeSecurityProxy(self.from_person)
        naked_person.mailing_list_auto_subscribe_policy = (
            MailingListAutoSubscribePolicy.ALWAYS)
        self.team, self.mailing_list = self.factory.makeTeamAndMailingList(
            'test-mailinglist', 'team-owner')
        with person_logged_in(self.team.teamowner):
            self.team.addMember(
                self.from_person, reviewer=self.team.teamowner)
        transaction.commit()
        _mergeMailingListSubscriptions(
            self.cur, self.from_person.id, self.to_person.id)
        self.assertEqual(1, self.cur.rowcount)
