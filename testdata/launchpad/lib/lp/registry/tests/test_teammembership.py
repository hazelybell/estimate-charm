# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

import bz2
from datetime import (
    datetime,
    timedelta,
    )
import os
import pickle
import re
import subprocess
from unittest import TestLoader

from fixtures import TempDir
import pytz
from testtools.content import text_content
from testtools.matchers import Equals
import transaction
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.registry.enums import (
    TeamMembershipPolicy,
    TeamMembershipRenewalPolicy,
    )
from lp.registry.interfaces.accesspolicy import (
    IAccessArtifactGrantSource,
    IAccessArtifactSource,
    )
from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.teammembership import (
    CyclicalTeamMembershipError,
    ITeamMembershipSet,
    TeamMembershipStatus,
    )
from lp.registry.model.teammembership import (
    find_team_participations,
    TeamMembership,
    TeamParticipation,
    )
from lp.registry.scripts.teamparticipation import (
    check_teamparticipation_circular,
    check_teamparticipation_consistency,
    ConsistencyError,
    fetch_team_participation_info,
    fix_teamparticipation_consistency,
    )
from lp.services.config import config
from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import (
    cursor,
    flush_database_caches,
    flush_database_updates,
    sqlvalues,
    )
from lp.services.features.testing import FeatureFixture
from lp.services.job.tests import block_on_job
from lp.services.log.logger import BufferLogger
from lp.testing import (
    login,
    login_celebrity,
    login_person,
    person_logged_in,
    StormStatementRecorder,
    TestCase,
    TestCaseWithFactory,
    )
from lp.testing.dbuser import dbuser
from lp.testing.layers import (
    CeleryJobLayer,
    DatabaseFunctionalLayer,
    DatabaseLayer,
    LaunchpadZopelessLayer,
    )
from lp.testing.mail_helpers import pop_notifications
from lp.testing.matchers import HasQueryCount
from lp.testing.systemdocs import (
    default_optionflags,
    LayeredDocFileSuite,
    setUp,
    tearDown,
    )


class TestTeamMembershipSetScripts(TestCaseWithFactory):
    """Separate Testcase to separate out examples required dbuser switches.

    This uses the LaunchpadZopelessLayer to provide switch_dbuser.
    """

    layer = LaunchpadZopelessLayer

    def test_handleMembershipsExpiringToday_permissions(self):
        # Create two teams, a control team and and a team to be the control's
        # administrator.
        adminteam = self.factory.makeTeam()
        adminteam.setContactAddress(None)
        team = self.factory.makeTeam(owner=adminteam)
        with person_logged_in(team.teamowner):
            team.renewal_policy = TeamMembershipRenewalPolicy.ONDEMAND
            team.defaultrenewalperiod = 10

        # Create a person to be in the control team.
        person = self.factory.makePerson()
        team.addMember(person, team.teamowner)
        membershipset = getUtility(ITeamMembershipSet)
        teammembership = membershipset.getByPersonAndTeam(person, team)

        # Set expiration time to now
        now = datetime.now(pytz.UTC)
        removeSecurityProxy(teammembership).dateexpires = now

        janitor = getUtility(ILaunchpadCelebrities).janitor
        with dbuser(config.expiredmembershipsflagger.dbuser):
            membershipset.handleMembershipsExpiringToday(janitor)
        self.assertEqual(
            TeamMembershipStatus.EXPIRED, teammembership.status)


class TestTeamMembershipSet(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestTeamMembershipSet, self).setUp()
        login('test@canonical.com')
        self.membershipset = getUtility(ITeamMembershipSet)
        self.personset = getUtility(IPersonSet)

    def test_membership_creation(self):
        marilize = self.personset.getByName('marilize')
        ubuntu_team = self.personset.getByName('ubuntu-team')
        membership = self.membershipset.new(
            marilize, ubuntu_team, TeamMembershipStatus.APPROVED, marilize)
        self.assertEqual(
            membership,
            self.membershipset.getByPersonAndTeam(marilize, ubuntu_team))
        self.assertEqual(membership.status, TeamMembershipStatus.APPROVED)

    def test_active_membership_creation_stores_proponent_and_reviewer(self):
        """Memberships created in any active state have the reviewer stored.

        The date_joined, reviewer_comment, date_reviewed and attributes
        related to the proponent are also stored, but everything related to
        acknowledger will be left empty.
        """
        marilize = self.personset.getByName('marilize')
        ubuntu_team = self.personset.getByName('ubuntu-team')
        membership = self.membershipset.new(
            marilize, ubuntu_team, TeamMembershipStatus.APPROVED,
            ubuntu_team.teamowner, comment="I like her")
        self.assertEqual(ubuntu_team.teamowner, membership.proposed_by)
        self.assertEqual(membership.proponent_comment, "I like her")
        now = datetime.now(pytz.UTC)
        self.failUnless(membership.date_proposed <= now)
        self.failUnless(membership.datejoined <= now)
        self.assertEqual(ubuntu_team.teamowner, membership.reviewed_by)
        self.assertEqual(membership.reviewer_comment, "I like her")
        self.failUnless(membership.date_reviewed <= now)
        self.assertEqual(membership.acknowledged_by, None)

    def test_membership_creation_stores_proponent(self):
        """Memberships created in the proposed state have proponent stored.

        The proponent_comment and date_proposed are also stored, but
        everything related to reviewer and acknowledger will be left empty.
        """
        marilize = self.personset.getByName('marilize')
        ubuntu_team = self.personset.getByName('ubuntu-team')
        membership = self.membershipset.new(
            marilize, ubuntu_team, TeamMembershipStatus.PROPOSED, marilize,
            comment="I'd like to join")
        self.assertEqual(marilize, membership.proposed_by)
        self.assertEqual(membership.proponent_comment, "I'd like to join")
        self.failUnless(
            membership.date_proposed <= datetime.now(pytz.UTC))
        self.assertEqual(membership.reviewed_by, None)
        self.assertEqual(membership.acknowledged_by, None)

    def test_admin_membership_creation(self):
        ubuntu_team = self.personset.getByName('ubuntu-team')
        no_priv = self.personset.getByName('no-priv')
        membership = self.membershipset.new(
            no_priv, ubuntu_team, TeamMembershipStatus.ADMIN, no_priv)
        self.assertEqual(
            membership,
            self.membershipset.getByPersonAndTeam(no_priv, ubuntu_team))
        self.assertEqual(membership.status, TeamMembershipStatus.ADMIN)

    def test_handleMembershipsExpiringToday(self):
        # Create a couple new teams, with one being a member of the other and
        # make Sample Person an approved member of both teams.
        login('foo.bar@canonical.com')
        foobar = self.personset.getByName('name16')
        sample_person = self.personset.getByName('name12')
        ubuntu_dev = self.personset.newTeam(
            foobar, 'ubuntu-dev', 'Ubuntu Developers')
        motu = self.personset.newTeam(foobar, 'motu', 'Ubuntu MOTU')
        ubuntu_dev.addMember(motu, foobar, force_team_add=True)
        ubuntu_dev.addMember(sample_person, foobar)
        motu.addMember(sample_person, foobar)

        # Now we need to cheat and set the expiration date of both memberships
        # manually because otherwise we would only be allowed to set an
        # expiration date in the future.
        now = datetime.now(pytz.UTC)
        sample_person_on_motu = removeSecurityProxy(
            self.membershipset.getByPersonAndTeam(sample_person, motu))
        sample_person_on_motu.dateexpires = now
        sample_person_on_ubuntu_dev = removeSecurityProxy(
            self.membershipset.getByPersonAndTeam(sample_person, ubuntu_dev))
        sample_person_on_ubuntu_dev.dateexpires = now
        flush_database_updates()
        self.assertEqual(
            sample_person_on_ubuntu_dev.status, TeamMembershipStatus.APPROVED)
        self.assertEqual(
            sample_person_on_motu.status, TeamMembershipStatus.APPROVED)
        self.membershipset.handleMembershipsExpiringToday(foobar)
        flush_database_caches()

        # Now Sample Person is not direct nor indirect member of ubuntu-dev
        # or motu.
        self.assertEqual(
            sample_person_on_ubuntu_dev.status, TeamMembershipStatus.EXPIRED)
        self.failIf(sample_person.inTeam(ubuntu_dev))
        self.assertEqual(
            sample_person_on_motu.status, TeamMembershipStatus.EXPIRED)
        self.failIf(sample_person.inTeam(motu))

    def test_deactivateActiveMemberships(self):
        superteam = self.factory.makeTeam(name='super')
        targetteam = self.factory.makeTeam(name='target')
        member = self.factory.makePerson()
        login_celebrity('admin')
        targetteam.join(superteam, targetteam.teamowner)
        targetteam.addMember(member, targetteam.teamowner)
        targetteam.teamowner.join(superteam, targetteam.teamowner)
        self.membershipset.deactivateActiveMemberships(
            targetteam, comment='test', reviewer=targetteam.teamowner)
        membership = self.membershipset.getByPersonAndTeam(member, targetteam)
        self.assertEqual('test', membership.last_change_comment)
        self.assertEqual(targetteam.teamowner, membership.last_changed_by)
        self.assertEqual([], list(targetteam.allmembers))
        self.assertEqual(
            [superteam], list(targetteam.teamowner.teams_participated_in))
        self.assertEqual([], list(member.teams_participated_in))


class TeamParticipationTestCase(TestCaseWithFactory):
    """Tests for team participation using 5 teams."""
    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TeamParticipationTestCase, self).setUp()
        login('foo.bar@canonical.com')
        person_set = getUtility(IPersonSet)
        self.foo_bar = person_set.getByEmail('foo.bar@canonical.com')
        self.no_priv = person_set.getByName('no-priv')
        self.team1 = person_set.newTeam(self.foo_bar, 'team1', 'team1')
        self.team2 = person_set.newTeam(self.foo_bar, 'team2', 'team2')
        self.team3 = person_set.newTeam(self.foo_bar, 'team3', 'team3')
        self.team4 = person_set.newTeam(self.foo_bar, 'team4', 'team4')
        self.team5 = person_set.newTeam(self.foo_bar, 'team5', 'team5')

    def assertParticipantsEquals(self, participant_names, team):
        """Assert that the participants names in team are the expected ones.
        """
        self.assertEquals(
            sorted(participant_names),
            sorted([participant.name for participant in team.allmembers]))

    def getTeamParticipationCount(self):
        return IStore(TeamParticipation).find(TeamParticipation).count()


class TestTeamParticipationQuery(TeamParticipationTestCase):
    """A test case for teammembership.test_find_team_participations."""

    def test_find_team_participations(self):
        # The correct team participations are found and the query count is 1.
        self.team1.addMember(self.no_priv, self.foo_bar)
        self.team2.addMember(self.no_priv, self.foo_bar)
        self.team1.addMember(self.team2, self.foo_bar, force_team_add=True)

        people = [self.team1, self.team2]
        with StormStatementRecorder() as recorder:
            people_teams = find_team_participations(people)
        self.assertThat(recorder, HasQueryCount(Equals(1)))
        self.assertContentEqual([self.team1, self.team2], people_teams.keys())
        self.assertContentEqual([self.team1], people_teams[self.team1])
        self.assertContentEqual(
            [self.team1, self.team2], people_teams[self.team2])

    def test_find_team_participations_limited_teams(self):
        # The correct team participations are found and the query count is 1.
        self.team1.addMember(self.no_priv, self.foo_bar)
        self.team2.addMember(self.no_priv, self.foo_bar)
        self.team1.addMember(self.team2, self.foo_bar, force_team_add=True)

        people = [self.foo_bar, self.team2]
        teams = [self.team1, self.team2]
        with StormStatementRecorder() as recorder:
            people_teams = find_team_participations(people, teams)
        self.assertThat(recorder, HasQueryCount(Equals(1)))
        self.assertContentEqual(
            [self.foo_bar, self.team2], people_teams.keys())
        self.assertContentEqual(
            [self.team1, self.team2], people_teams[self.foo_bar])
        self.assertContentEqual(
            [self.team1, self.team2], people_teams[self.team2])

    def test_find_team_participations_no_query(self):
        # Check that no database query is made unless necessary.
        people = [self.foo_bar, self.team2]
        teams = [self.foo_bar]
        with StormStatementRecorder() as recorder:
            people_teams = find_team_participations(people, teams)
        self.assertThat(recorder, HasQueryCount(Equals(0)))
        self.assertContentEqual([self.foo_bar], people_teams.keys())
        self.assertContentEqual([self.foo_bar], people_teams[self.foo_bar])


class TestTeamParticipationHierarchy(TeamParticipationTestCase):
    """Participation management tests using 5 nested teams.

    Create a team hierarchy with 5 teams and one person (no-priv) as
    member of the last team in the chain.
        team1
           team2
              team3
                 team4
                    team5
                       no-priv
    """
    layer = DatabaseFunctionalLayer

    def setUp(self):
        """Setup the team hierarchy."""
        super(TestTeamParticipationHierarchy, self).setUp()
        self.team5.addMember(self.no_priv, self.foo_bar)
        self.team1.addMember(self.team2, self.foo_bar, force_team_add=True)
        self.team2.addMember(self.team3, self.foo_bar, force_team_add=True)
        self.team3.addMember(self.team4, self.foo_bar, force_team_add=True)
        self.team4.addMember(self.team5, self.foo_bar, force_team_add=True)

    def testTeamParticipationSetUp(self):
        """Make sure that the TeamParticipation are sane after setUp."""
        self.assertParticipantsEquals(
            ['name16', 'no-priv', 'team2', 'team3', 'team4', 'team5'],
            self.team1)
        self.assertParticipantsEquals(
            ['name16', 'no-priv', 'team3', 'team4', 'team5'], self.team2)
        self.assertParticipantsEquals(
            ['name16', 'no-priv', 'team4', 'team5'], self.team3)
        self.assertParticipantsEquals(
            ['name16', 'no-priv', 'team5'], self.team4)
        self.assertParticipantsEquals(
            ['name16', 'no-priv'], self.team5)

    def testSevereHierarchyByRemovingTeam3FromTeam2(self):
        """Make sure that the participations is updated correctly when
        the hierarchy is severed in the two.

        This is similar to what was experienced in bug 261915.
        """
        previous_count = self.getTeamParticipationCount()
        self.team2.setMembershipData(
            self.team3, TeamMembershipStatus.DEACTIVATED, self.foo_bar)
        self.assertParticipantsEquals(['name16', 'team2'], self.team1)
        self.assertParticipantsEquals(['name16'], self.team2)
        self.assertParticipantsEquals(
            ['name16', 'no-priv', 'team4', 'team5'], self.team3)
        self.assertParticipantsEquals(
            ['name16', 'no-priv', 'team5'], self.team4)
        self.assertParticipantsEquals(['name16', 'no-priv'], self.team5)
        self.assertEqual(
            previous_count - 8,
            self.getTeamParticipationCount())

    def testRemovingLeafTeam(self):
        """Make sure that participations are updated correctly when removing
        the leaf team.
        """
        previous_count = self.getTeamParticipationCount()
        self.team4.setMembershipData(
            self.team5, TeamMembershipStatus.DEACTIVATED, self.foo_bar)
        self.assertParticipantsEquals(
            ['name16', 'team2', 'team3', 'team4'], self.team1)
        self.assertParticipantsEquals(
            ['name16', 'team3', 'team4'], self.team2)
        self.assertParticipantsEquals(['name16', 'team4'], self.team3)
        self.assertParticipantsEquals(['name16'], self.team4)
        self.assertParticipantsEquals(['name16', 'no-priv'], self.team5)
        self.assertEqual(
            previous_count - 8,
            self.getTeamParticipationCount())


class TestTeamParticipationTree(TeamParticipationTestCase):
    """Participation management tests using 5 nested teams

    Create a team hierarchy looking like this:
        team1
           team2
              team5
              team3
                 team4
                    team5
                       no-priv
    """
    layer = DatabaseFunctionalLayer

    def setUp(self):
        """Setup the team hierarchy."""
        super(TestTeamParticipationTree, self).setUp()
        self.team5.addMember(self.no_priv, self.foo_bar)
        self.team1.addMember(self.team2, self.foo_bar, force_team_add=True)
        self.team2.addMember(self.team3, self.foo_bar, force_team_add=True)
        self.team2.addMember(self.team5, self.foo_bar, force_team_add=True)
        self.team3.addMember(self.team4, self.foo_bar, force_team_add=True)
        self.team4.addMember(self.team5, self.foo_bar, force_team_add=True)

    def tearDown(self):
        super(TestTeamParticipationTree, self).tearDown()
        self.layer.force_dirty_database()

    def testTeamParticipationSetUp(self):
        """Make sure that the TeamParticipation are sane after setUp."""
        self.assertParticipantsEquals(
            ['name16', 'no-priv', 'team2', 'team3', 'team4', 'team5'],
            self.team1)
        self.assertParticipantsEquals(
            ['name16', 'no-priv', 'team3', 'team4', 'team5'], self.team2)
        self.assertParticipantsEquals(
            ['name16', 'no-priv', 'team4', 'team5'], self.team3)
        self.assertParticipantsEquals(
            ['name16', 'no-priv', 'team5'], self.team4)
        self.assertParticipantsEquals(
            ['name16', 'no-priv'], self.team5)

    def testRemoveTeam3FromTeam2(self):
        previous_count = self.getTeamParticipationCount()
        self.team2.setMembershipData(
            self.team3, TeamMembershipStatus.DEACTIVATED, self.foo_bar)
        self.assertParticipantsEquals(
            ['name16', 'no-priv', 'team2', 'team5'], self.team1)
        self.assertParticipantsEquals(
            ['name16', 'no-priv', 'team5'], self.team2)
        self.assertParticipantsEquals(
            ['name16', 'no-priv', 'team4', 'team5'], self.team3)
        self.assertParticipantsEquals(
            ['name16', 'no-priv', 'team5'], self.team4)
        self.assertParticipantsEquals(['name16', 'no-priv'], self.team5)
        self.assertEqual(
            previous_count - 4,
            self.getTeamParticipationCount())

    def testRemoveTeam5FromTeam4(self):
        previous_count = self.getTeamParticipationCount()
        self.team4.setMembershipData(
            self.team5, TeamMembershipStatus.DEACTIVATED, self.foo_bar)
        self.assertParticipantsEquals(
            ['name16', 'no-priv', 'team2', 'team3', 'team4', 'team5'],
            self.team1)
        self.assertParticipantsEquals(
            ['name16', 'no-priv', 'team3', 'team4', 'team5'], self.team2)
        self.assertParticipantsEquals(
            ['name16', 'team4'], self.team3)
        self.assertParticipantsEquals(['name16'], self.team4)
        self.assertParticipantsEquals(['name16', 'no-priv'], self.team5)
        self.assertEqual(
            previous_count - 4,
            self.getTeamParticipationCount())


class TestParticipationCleanup(TeamParticipationTestCase):
    """Test deletion of a member from a team with many superteams.
    Create a team hierarchy looking like this:
        team1
           team2
              team3
                 team4
                    team5
                       no-priv
    """

    def setUp(self):
        """Setup the team hierarchy."""
        super(TestParticipationCleanup, self).setUp()
        self.team1.addMember(self.team2, self.foo_bar, force_team_add=True)
        self.team2.addMember(self.team3, self.foo_bar, force_team_add=True)
        self.team3.addMember(self.team4, self.foo_bar, force_team_add=True)
        self.team4.addMember(self.team5, self.foo_bar, force_team_add=True)
        self.team5.addMember(self.no_priv, self.foo_bar)

    def testMemberRemoval(self):
        """Remove the member from the last team.

        The number of db queries should be constant not O(depth).
        """
        self.assertStatementCount(
            9,
            self.team5.setMembershipData, self.no_priv,
            TeamMembershipStatus.DEACTIVATED, self.team5.teamowner)


class TestTeamParticipationMesh(TeamParticipationTestCase):
    """Participation management tests using two roots and some duplicated
    branches.

    Create a team hierarchy looking like this:
        team1     team6
           \     /  |
            team2   |
           /    |   |
        team3   |   |
             \  |  /
              team4
                 team5
                    no-priv
    """
    layer = DatabaseFunctionalLayer

    def setUp(self):
        """Setup the team hierarchy."""
        super(TestTeamParticipationMesh, self).setUp()
        self.team6 = getUtility(IPersonSet).newTeam(
            self.foo_bar, 'team6', 'team6')
        self.team5.addMember(self.no_priv, self.foo_bar)
        self.team1.addMember(self.team2, self.foo_bar, force_team_add=True)
        self.team2.addMember(self.team3, self.foo_bar, force_team_add=True)
        self.team2.addMember(self.team4, self.foo_bar, force_team_add=True)
        self.team3.addMember(self.team4, self.foo_bar, force_team_add=True)
        self.team4.addMember(self.team5, self.foo_bar, force_team_add=True)
        self.team6.addMember(self.team2, self.foo_bar, force_team_add=True)
        self.team6.addMember(self.team4, self.foo_bar, force_team_add=True)

    def tearDown(self):
        super(TestTeamParticipationMesh, self).tearDown()
        self.layer.force_dirty_database()

    def testTeamParticipationSetUp(self):
        """Make sure that the TeamParticipation are sane after setUp."""
        self.assertParticipantsEquals(
            ['name16', 'no-priv', 'team2', 'team3', 'team4', 'team5'],
            self.team1)
        self.assertParticipantsEquals(
            ['name16', 'no-priv', 'team3', 'team4', 'team5'], self.team2)
        self.assertParticipantsEquals(
            ['name16', 'no-priv', 'team4', 'team5'], self.team3)
        self.assertParticipantsEquals(
            ['name16', 'no-priv', 'team5'], self.team4)
        self.assertParticipantsEquals(['name16', 'no-priv'], self.team5)
        self.assertParticipantsEquals(
            ['name16', 'no-priv', 'team2', 'team3', 'team4', 'team5'],
            self.team6)

    def testRemoveTeam3FromTeam2(self):
        previous_count = self.getTeamParticipationCount()
        self.team2.setMembershipData(
            self.team3, TeamMembershipStatus.DEACTIVATED, self.foo_bar)
        self.assertParticipantsEquals(
            ['name16', 'no-priv', 'team2', 'team4', 'team5'], self.team1)
        self.assertParticipantsEquals(
            ['name16', 'no-priv', 'team4', 'team5'], self.team2)
        self.assertParticipantsEquals(
            ['name16', 'no-priv', 'team4', 'team5'], self.team3)
        self.assertParticipantsEquals(
            ['name16', 'no-priv', 'team5'], self.team4)
        self.assertParticipantsEquals(['name16', 'no-priv'], self.team5)
        self.assertParticipantsEquals(
            ['name16', 'no-priv', 'team2', 'team4', 'team5'], self.team6)
        self.assertEqual(
            previous_count - 3,
            self.getTeamParticipationCount())

    def testRemoveTeam5FromTeam4(self):
        previous_count = self.getTeamParticipationCount()
        self.team4.setMembershipData(
            self.team5, TeamMembershipStatus.DEACTIVATED, self.foo_bar)
        self.assertParticipantsEquals(
            ['name16', 'team2', 'team3', 'team4'], self.team1)
        self.assertParticipantsEquals(
            ['name16', 'team3', 'team4'], self.team2)
        self.assertParticipantsEquals(['name16', 'team4'], self.team3)
        self.assertParticipantsEquals(['name16'], self.team4)
        self.assertParticipantsEquals(['name16', 'no-priv'], self.team5)
        self.assertParticipantsEquals(
            ['name16', 'team2', 'team3', 'team4'], self.team6)
        self.assertEqual(
            previous_count - 10,
            self.getTeamParticipationCount())

    def testTeam3_deactivateActiveMemberships(self):
        # Removing all the members of team2 will not remove memberships
        # to super teams from other paths.
        non_member = self.factory.makePerson()
        self.team3.addMember(non_member, self.foo_bar, force_team_add=True)
        previous_count = self.getTeamParticipationCount()
        membershipset = getUtility(ITeamMembershipSet)
        membershipset.deactivateActiveMemberships(
            self.team3, 'gone', self.foo_bar)
        self.assertEqual([], list(self.team3.allmembers))
        self.assertParticipantsEquals(
            ['name16', 'no-priv', 'team2', 'team3', 'team4', 'team5'],
            self.team1)
        self.assertParticipantsEquals(
            ['name16', 'no-priv', 'team3', 'team4', 'team5'], self.team2)
        self.assertParticipantsEquals(
            [], self.team3)
        self.assertParticipantsEquals(
            ['name16', 'no-priv', 'team5'], self.team4)
        self.assertParticipantsEquals(['name16', 'no-priv'], self.team5)
        self.assertParticipantsEquals(
            ['name16', 'no-priv', 'team2', 'team3', 'team4', 'team5'],
            self.team6)
        self.assertEqual(previous_count - 8, self.getTeamParticipationCount())


class TestTeamMembership(TestCaseWithFactory):
    layer = DatabaseFunctionalLayer

    def test_teams_not_kicked_from_themselves_bug_248498(self):
        """The self-participation of a team must not be removed.

        Performing the following steps would cause a team's self-participation
        to be removed, but it shouldn't.

            1. propose team A as a member of team B
            2. propose team B as a member of team A
            3. approve team A as a member of team B
            4. decline team B as a member of team A

        This test will make sure that doesn't happen in the future.
        """
        login('test@canonical.com')
        person = self.factory.makePerson()
        login_person(person)  # Now login with the future owner of the teams.
        teamA = self.factory.makeTeam(
            person, membership_policy=TeamMembershipPolicy.MODERATED)
        teamB = self.factory.makeTeam(
            person, membership_policy=TeamMembershipPolicy.MODERATED)
        self.failUnless(
            teamA.inTeam(teamA), "teamA is not a participant of itself")
        self.failUnless(
            teamB.inTeam(teamB), "teamB is not a participant of itself")

        teamA.join(teamB, requester=person)
        teamB.join(teamA, requester=person)
        teamB.setMembershipData(teamA, TeamMembershipStatus.APPROVED, person)
        teamA.setMembershipData(teamB, TeamMembershipStatus.DECLINED, person)

        self.failUnless(teamA.hasParticipationEntryFor(teamA),
                        "teamA is not a participant of itself")
        self.failUnless(teamB.hasParticipationEntryFor(teamB),
                        "teamB is not a participant of itself")

    def test_membership_status_changes_are_immediately_flushed_to_db(self):
        """Any changes to a membership status must be imediately flushed.

        Sometimes we may change multiple team memberships in the same
        transaction (e.g. when expiring memberships). If there are multiple
        memberships for a given member changed in this way, we need to
        ensure each change is flushed to the database so that subsequent ones
        operate on the correct data.
        """
        login('foo.bar@canonical.com')
        tm = TeamMembership.selectFirstBy(
            status=TeamMembershipStatus.APPROVED, orderBy='id')
        tm.setStatus(TeamMembershipStatus.DEACTIVATED,
                     getUtility(IPersonSet).getByName('name16'))
        # Bypass SQLObject to make sure the update was really flushed to the
        # database.
        cur = cursor()
        cur.execute("SELECT status FROM teammembership WHERE id = %d" % tm.id)
        [new_status] = cur.fetchone()
        self.assertEqual(new_status, TeamMembershipStatus.DEACTIVATED.value)


class TestTeamMembershipSetStatus(TestCaseWithFactory):
    """Test the behaviour of TeamMembership's setStatus()."""
    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestTeamMembershipSetStatus, self).setUp()
        login('foo.bar@canonical.com')
        self.foobar = getUtility(IPersonSet).getByName('name16')
        self.no_priv = getUtility(IPersonSet).getByName('no-priv')
        self.ubuntu_team = getUtility(IPersonSet).getByName('ubuntu-team')
        self.admins = getUtility(IPersonSet).getByName('admins')
        # Create a bunch of arbitrary teams to use in the tests.
        self.team1 = self.factory.makeTeam(self.foobar)
        self.team2 = self.factory.makeTeam(self.foobar)
        self.team3 = self.factory.makeTeam(self.foobar)

    def test_proponent_is_stored(self):
        for status in [TeamMembershipStatus.DEACTIVATED,
                       TeamMembershipStatus.EXPIRED,
                       TeamMembershipStatus.DECLINED]:
            tm = TeamMembership(
                person=self.no_priv, team=self.ubuntu_team, status=status)
            self.failIf(
                tm.proposed_by, "There can be no proponent at this point.")
            self.failIf(
                tm.date_proposed, "There can be no proposed date this point.")
            self.failIf(tm.proponent_comment,
                        "There can be no proponent comment at this point.")
            tm.setStatus(
                TeamMembershipStatus.PROPOSED, self.foobar,
                "Did it 'cause I can")
            self.failUnlessEqual(tm.proposed_by, self.foobar)
            self.failUnlessEqual(tm.proponent_comment, "Did it 'cause I can")
            self.failUnless(
                tm.date_proposed <= datetime.now(pytz.UTC))
            # Destroy the membership so that we can create another in a
            # different state.
            tm.destroySelf()

    def test_acknowledger_is_stored(self):
        for status in [TeamMembershipStatus.APPROVED,
                       TeamMembershipStatus.INVITATION_DECLINED]:
            tm = TeamMembership(
                person=self.admins, team=self.ubuntu_team,
                status=TeamMembershipStatus.INVITED)
            self.failIf(
                tm.acknowledged_by,
                "There can be no acknowledger at this point.")
            self.failIf(
                tm.date_acknowledged,
                "There can be no accepted date this point.")
            self.failIf(tm.acknowledger_comment,
                        "There can be no acknowledger comment at this point.")
            tm.setStatus(status, self.foobar, "Did it 'cause I can")
            self.failUnlessEqual(tm.acknowledged_by, self.foobar)
            self.failUnlessEqual(
                tm.acknowledger_comment, "Did it 'cause I can")
            self.failUnless(
                tm.date_acknowledged <= datetime.now(pytz.UTC))
            # Destroy the membership so that we can create another in a
            # different state.
            tm.destroySelf()

    def test_reviewer_is_stored(self):
        transitions_mapping = {
            TeamMembershipStatus.DEACTIVATED: [TeamMembershipStatus.APPROVED],
            TeamMembershipStatus.EXPIRED: [TeamMembershipStatus.APPROVED],
            TeamMembershipStatus.PROPOSED: [
                TeamMembershipStatus.APPROVED, TeamMembershipStatus.DECLINED],
            TeamMembershipStatus.DECLINED: [TeamMembershipStatus.APPROVED],
            TeamMembershipStatus.INVITATION_DECLINED: [
                TeamMembershipStatus.APPROVED]}
        for status, new_statuses in transitions_mapping.items():
            for new_status in new_statuses:
                tm = TeamMembership(
                    person=self.no_priv, team=self.ubuntu_team, status=status)
                self.failIf(
                    tm.reviewed_by,
                    "There can be no approver at this point.")
                self.failIf(
                    tm.date_reviewed,
                    "There can be no approved date this point.")
                self.failIf(
                    tm.reviewer_comment,
                    "There can be no approver comment at this point.")
                tm.setStatus(new_status, self.foobar, "Did it 'cause I can")
                self.failUnlessEqual(tm.reviewed_by, self.foobar)
                self.failUnlessEqual(
                    tm.reviewer_comment, "Did it 'cause I can")
                self.failUnless(
                    tm.date_reviewed <= datetime.now(pytz.UTC))

                # Destroy the membership so that we can create another in a
                # different state.
                tm.destroySelf()

    def test_datejoined(self):
        """TeamMembership.datejoined stores the date in which this membership
        was made active for the first time.
        """
        tm = TeamMembership(
            person=self.no_priv, team=self.ubuntu_team,
            status=TeamMembershipStatus.PROPOSED)
        self.failIf(
            tm.datejoined, "There can be no datejoined at this point.")
        tm.setStatus(TeamMembershipStatus.APPROVED, self.foobar)
        now = datetime.now(pytz.UTC)
        self.failUnless(tm.datejoined <= now)

        # We now set the status to deactivated and change datejoined to a
        # date in the past just so that we can easily show it's not changed
        # again by setStatus().
        one_minute_ago = now - timedelta(minutes=1)
        tm.setStatus(TeamMembershipStatus.DEACTIVATED, self.foobar)
        tm.datejoined = one_minute_ago
        tm.setStatus(TeamMembershipStatus.APPROVED, self.foobar)
        self.failUnless(tm.datejoined <= one_minute_ago)

    def test_no_cyclical_membership_allowed(self):
        """No status change can create cyclical memberships."""
        # Invite team2 as member of team1 and team1 as member of team2. This
        # is not a problem because that won't make any team an active member
        # of the other.
        self.team1.addMember(self.team2, self.no_priv)
        self.team2.addMember(self.team1, self.no_priv)
        team1_on_team2 = getUtility(ITeamMembershipSet).getByPersonAndTeam(
            self.team1, self.team2)
        team2_on_team1 = getUtility(ITeamMembershipSet).getByPersonAndTeam(
            self.team2, self.team1)
        self.failUnlessEqual(
            team1_on_team2.status, TeamMembershipStatus.INVITED)
        self.failUnlessEqual(
            team2_on_team1.status, TeamMembershipStatus.INVITED)

        # Now make team1 an active member of team2.  From this point onwards,
        # team2 cannot be made an active member of team1.
        team1_on_team2.setStatus(TeamMembershipStatus.APPROVED, self.foobar)
        flush_database_updates()
        self.failUnlessEqual(
            team1_on_team2.status, TeamMembershipStatus.APPROVED)
        self.assertRaises(
            CyclicalTeamMembershipError, team2_on_team1.setStatus,
            TeamMembershipStatus.APPROVED, self.foobar)
        self.failUnlessEqual(
            team2_on_team1.status, TeamMembershipStatus.INVITED)

        # It is possible to change the state of team2's membership on team1
        # to another inactive state, though.
        team2_on_team1.setStatus(
            TeamMembershipStatus.INVITATION_DECLINED, self.foobar)
        self.failUnlessEqual(
            team2_on_team1.status, TeamMembershipStatus.INVITATION_DECLINED)

    def test_no_cyclical_participation_allowed(self):
        """No status change can create cyclical participation."""
        # Invite team1 as a member of team3 and forcibly add team2 as member
        # of team1 and team3 as member of team2.
        self.team3.addMember(self.team1, self.no_priv)
        self.team1.addMember(self.team2, self.foobar, force_team_add=True)
        self.team2.addMember(self.team3, self.foobar, force_team_add=True)

        # Since team2 is a member of team1 and team3 is a member of team2, we
        # can't make team1 a member of team3.
        team1_on_team3 = getUtility(ITeamMembershipSet).getByPersonAndTeam(
            self.team1, self.team3)
        self.assertRaises(
            CyclicalTeamMembershipError, team1_on_team3.setStatus,
            TeamMembershipStatus.APPROVED, self.foobar)

    def test_invited_member_can_be_made_admin(self):
        self.team2.addMember(self.team1, self.no_priv)
        team1_on_team2 = getUtility(ITeamMembershipSet).getByPersonAndTeam(
            self.team1, self.team2)
        self.assertEqual(team1_on_team2.status, TeamMembershipStatus.INVITED)
        team1_on_team2.setStatus(TeamMembershipStatus.ADMIN, self.foobar)
        self.assertEqual(team1_on_team2.status, TeamMembershipStatus.ADMIN)

    def test_deactivated_member_can_be_made_admin(self):
        self.team2.addMember(self.team1, self.foobar, force_team_add=True)
        team1_on_team2 = getUtility(ITeamMembershipSet).getByPersonAndTeam(
            self.team1, self.team2)
        self.assertEqual(team1_on_team2.status, TeamMembershipStatus.APPROVED)
        team1_on_team2.setStatus(
            TeamMembershipStatus.DEACTIVATED, self.foobar)
        self.assertEqual(
            team1_on_team2.status, TeamMembershipStatus.DEACTIVATED)
        team1_on_team2.setStatus(TeamMembershipStatus.ADMIN, self.foobar)
        self.assertEqual(team1_on_team2.status, TeamMembershipStatus.ADMIN)

    def test_expired_member_can_be_made_admin(self):
        self.team2.addMember(self.team1, self.foobar, force_team_add=True)
        team1_on_team2 = getUtility(ITeamMembershipSet).getByPersonAndTeam(
            self.team1, self.team2)
        self.assertEqual(team1_on_team2.status, TeamMembershipStatus.APPROVED)
        team1_on_team2.setStatus(TeamMembershipStatus.EXPIRED, self.foobar)
        self.assertEqual(team1_on_team2.status, TeamMembershipStatus.EXPIRED)
        team1_on_team2.setStatus(TeamMembershipStatus.ADMIN, self.foobar)
        self.assertEqual(team1_on_team2.status, TeamMembershipStatus.ADMIN)

    def test_declined_member_can_be_made_admin(self):
        self.team2.membership_policy = TeamMembershipPolicy.MODERATED
        self.team1.join(self.team2, requester=self.foobar)
        team1_on_team2 = getUtility(ITeamMembershipSet).getByPersonAndTeam(
            self.team1, self.team2)
        self.assertEqual(team1_on_team2.status, TeamMembershipStatus.PROPOSED)
        team1_on_team2.setStatus(TeamMembershipStatus.DECLINED, self.foobar)
        self.assertEqual(team1_on_team2.status, TeamMembershipStatus.DECLINED)
        team1_on_team2.setStatus(TeamMembershipStatus.ADMIN, self.foobar)
        self.assertEqual(team1_on_team2.status, TeamMembershipStatus.ADMIN)

    def test_invited_member_can_be_declined(self):
        # A team can decline an invited member.
        self.team2.addMember(self.team1, self.no_priv)
        tm = getUtility(ITeamMembershipSet).getByPersonAndTeam(
            self.team1, self.team2)
        tm.setStatus(
            TeamMembershipStatus.INVITATION_DECLINED, self.team2.teamowner)
        self.assertEqual(TeamMembershipStatus.INVITATION_DECLINED, tm.status)

    def test_declined_member_can_be_invited(self):
        # A team can re-invite a declined member.
        self.team2.addMember(
            self.team1, self.no_priv, status=TeamMembershipStatus.PROPOSED,
            force_team_add=True)
        tm = getUtility(ITeamMembershipSet).getByPersonAndTeam(
            self.team1, self.team2)
        tm.setStatus(
            TeamMembershipStatus.DECLINED, self.team1.teamowner)
        tm.setStatus(
            TeamMembershipStatus.INVITED, self.team1.teamowner)
        self.assertEqual(TeamMembershipStatus.INVITED, tm.status)

    def test_add_approved(self):
        # Adding an approved team is a no-op.
        member_team = self.factory.makeTeam()
        self.team1.addMember(
            member_team, self.team1.teamowner)
        with person_logged_in(member_team.teamowner):
            member_team.acceptInvitationToBeMemberOf(self.team1, 'alright')
        self.team1.addMember(
            member_team, self.team1.teamowner)
        tm = getUtility(ITeamMembershipSet).getByPersonAndTeam(
            member_team, self.team1)
        self.assertEqual(TeamMembershipStatus.APPROVED, tm.status)
        self.team1.addMember(
            member_team, member_team.teamowner)
        self.assertEqual(TeamMembershipStatus.APPROVED, tm.status)

    def test_add_admin(self):
        # Adding an admin team is a no-op.
        member_team = self.factory.makeTeam()
        self.team1.addMember(
            member_team, self.team1.teamowner,
            status=TeamMembershipStatus.ADMIN, force_team_add=True)
        self.team1.addMember(
            member_team, self.team1.teamowner)
        tm = getUtility(ITeamMembershipSet).getByPersonAndTeam(
            member_team, self.team1)
        self.assertEqual(TeamMembershipStatus.ADMIN, tm.status)
        self.team1.addMember(
            member_team, member_team.teamowner)
        self.assertEqual(TeamMembershipStatus.ADMIN, tm.status)

    def test_implicit_approval(self):
        # Inviting a proposed person is an implicit approval.
        member_team = self.factory.makeTeam()
        self.team1.addMember(
            member_team, self.team1.teamowner,
            status=TeamMembershipStatus.PROPOSED, force_team_add=True)
        self.team1.addMember(
            member_team, self.team1.teamowner)
        tm = getUtility(ITeamMembershipSet).getByPersonAndTeam(
            member_team, self.team1)
        self.assertEqual(TeamMembershipStatus.APPROVED, tm.status)

    def test_retractTeamMembership_invited(self):
        # A team can retract a membership invitation.
        self.team2.addMember(self.team1, self.no_priv)
        self.team1.retractTeamMembership(self.team2, self.team1.teamowner)
        tm = getUtility(ITeamMembershipSet).getByPersonAndTeam(
            self.team1, self.team2)
        self.assertEqual(TeamMembershipStatus.INVITATION_DECLINED, tm.status)

    def test_retractTeamMembership_proposed(self):
        # A team can retract the proposed membership in a team.
        self.team2.membership_policy = TeamMembershipPolicy.MODERATED
        self.team1.join(self.team2, self.team1.teamowner)
        self.team1.retractTeamMembership(self.team2, self.team1.teamowner)
        tm = getUtility(ITeamMembershipSet).getByPersonAndTeam(
            self.team1, self.team2)
        self.assertEqual(TeamMembershipStatus.DECLINED, tm.status)

    def test_retractTeamMembership_active(self):
        # A team can retract the membership in a team.
        self.team1.join(self.team2, self.team1.teamowner)
        self.team1.retractTeamMembership(self.team2, self.team1.teamowner)
        tm = getUtility(ITeamMembershipSet).getByPersonAndTeam(
            self.team1, self.team2)
        self.assertEqual(TeamMembershipStatus.DEACTIVATED, tm.status)

    def test_retractTeamMembership_admin(self):
        # A team can retract the membership in a team.
        self.team1.join(self.team2, self.team1.teamowner)
        tm = getUtility(ITeamMembershipSet).getByPersonAndTeam(
            self.team1, self.team2)
        tm.setStatus(TeamMembershipStatus.ADMIN, self.team2.teamowner)
        self.team1.retractTeamMembership(self.team2, self.team1.teamowner)
        self.assertEqual(TeamMembershipStatus.DEACTIVATED, tm.status)


class TestTeamMembershipJobs(TestCaseWithFactory):
    """Test jobs associated with managing team membership."""
    layer = CeleryJobLayer

    def setUp(self):
        self.useFixture(FeatureFixture({
            'jobs.celery.enabled_classes': 'RemoveArtifactSubscriptionsJob',
        }))
        super(TestTeamMembershipJobs, self).setUp()

    def _make_subscribed_bug(self, grantee, target,
                             information_type=InformationType.USERDATA):
        owner = self.factory.makePerson()
        bug = self.factory.makeBug(
            owner=owner, target=target, information_type=information_type)
        with person_logged_in(owner):
            bug.subscribe(grantee, owner)
        return bug, owner

    def test_retract_unsubscribes_former_member(self):
        # When a team member is removed, any subscriptions to artifacts they
        # can no longer see are removed also.
        person_grantee = self.factory.makePerson()
        product = self.factory.makeProduct()
        # Make a bug the person_grantee is subscribed to.
        bug1, ignored = self._make_subscribed_bug(
            person_grantee, product,
            information_type=InformationType.USERDATA)

        # Make another bug and grant access to a team.
        team_grantee = self.factory.makeTeam(
            membership_policy=TeamMembershipPolicy.RESTRICTED,
            members=[person_grantee])
        bug2, bug2_owner = self._make_subscribed_bug(
            team_grantee, product,
            information_type=InformationType.PRIVATESECURITY)
        # Add a subscription for the person_grantee.
        with person_logged_in(bug2_owner):
            bug2.subscribe(person_grantee, bug2_owner)

        # Subscribing person_grantee to bugs creates an access grant so we
        # need to revoke the one to bug2 for our test.
        accessartifact_source = getUtility(IAccessArtifactSource)
        accessartifact_grant_source = getUtility(IAccessArtifactGrantSource)
        accessartifact_grant_source.revokeByArtifact(
            accessartifact_source.find([bug2]), [person_grantee])

        with person_logged_in(person_grantee):
            person_grantee.retractTeamMembership(team_grantee, person_grantee)
        with block_on_job(self):
            transaction.commit()

        # person_grantee is still subscribed to bug1.
        self.assertIn(
            person_grantee, removeSecurityProxy(bug1).getDirectSubscribers())
        # person_grantee is not subscribed to bug2 because they no longer have
        # access via a team.
        self.assertNotIn(
            person_grantee, removeSecurityProxy(bug2).getDirectSubscribers())


class TestTeamMembershipSendExpirationWarningEmail(TestCaseWithFactory):
    """Test the behaviour of sendExpirationWarningEmail()."""
    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestTeamMembershipSendExpirationWarningEmail, self).setUp()
        self.member = self.factory.makePerson(name='green')
        self.team = self.factory.makeTeam(name='red')
        login_person(self.team.teamowner)
        self.team.addMember(self.member, self.team.teamowner)
        self.tm = getUtility(ITeamMembershipSet).getByPersonAndTeam(
            self.member, self.team)
        pop_notifications()

    def test_error_raised_when_no_expiration(self):
        # An exception is raised if the membership does not have an
        # expiration date.
        self.assertEqual(None, self.tm.dateexpires)
        message = 'green in team red has no membership expiration date.'
        self.assertRaisesWithContent(
            AssertionError, message, self.tm.sendExpirationWarningEmail)

    def test_message_sent_for_future_expiration(self):
        # An email is sent to the user whose membership will expire.
        tomorrow = datetime.now(pytz.UTC) + timedelta(days=1)
        removeSecurityProxy(self.tm).dateexpires = tomorrow
        self.tm.sendExpirationWarningEmail()
        notifications = pop_notifications()
        self.assertEqual(1, len(notifications))
        message = notifications[0]
        self.assertEqual(
            'Your membership in red is about to expire', message['subject'])
        self.assertEqual(
            self.member.preferredemail.email, message['to'])

    def test_no_message_sent_for_expired_memberships(self):
        # Members whose membership has expired do not get a message.
        yesterday = datetime.now(pytz.UTC) - timedelta(days=1)
        removeSecurityProxy(self.tm).dateexpires = yesterday
        self.tm.sendExpirationWarningEmail()
        notifications = pop_notifications()
        self.assertEqual(0, len(notifications))

    def test_no_message_sent_for_non_active_users(self):
        # Non-active users do not get an expiration message.
        with person_logged_in(self.member):
            self.member.deactivate('Goodbye.')
        IStore(self.member).flush()
        now = datetime.now(pytz.UTC)
        removeSecurityProxy(self.tm).dateexpires = now + timedelta(days=1)
        self.tm.sendExpirationWarningEmail()
        notifications = pop_notifications()
        self.assertEqual(0, len(notifications))


class TestCheckTeamParticipationScript(TestCase):

    layer = DatabaseFunctionalLayer

    def _runScript(self, *args):
        cmd = ["cronscripts/check-teamparticipation.py"]
        cmd.extend(args)
        process = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        out, err = process.communicate()
        if out != "":
            self.addDetail("stdout", text_content(out))
        if err != "":
            self.addDetail("stderr", text_content(err))
        DatabaseLayer.force_dirty_database()
        return process.poll(), out, err

    def test_no_output_if_no_invalid_entries(self):
        """No output if there's no invalid teamparticipation entries."""
        code, out, err = self._runScript()
        self.assertEqual(0, code)
        self.assertEqual(0, len(out))
        self.assertEqual(0, len(err))

    def test_report_invalid_teamparticipation_entries(self):
        """The script reports missing/spurious TeamParticipation entries.

        As well as missing self-participation.
        """
        cur = cursor()
        # Create a new entry in the Person table and change its
        # self-participation entry, making that person a participant in a team
        # where it should not be as well as making that person not a member of
        # itself (as everybody should be).
        cur.execute("""
            INSERT INTO
                Person (id, name, displayname, creation_rationale)
                VALUES (9999, 'zzzzz', 'zzzzzz', 1);
            UPDATE TeamParticipation
                SET team = (
                    SELECT id
                    FROM Person
                    WHERE teamowner IS NOT NULL
                    ORDER BY name
                    LIMIT 1)
                WHERE person = 9999;
            """)
        # Now add the new person as a member of another team but don't create
        # the relevant TeamParticipation for that person on that team.
        cur.execute("""
            INSERT INTO
                TeamMembership (person, team, status)
                VALUES (9999,
                    (SELECT id
                        FROM Person
                        WHERE teamowner IS NOT NULL
                        ORDER BY name desc
                        LIMIT 1),
                    %s);
            """ % sqlvalues(TeamMembershipStatus.APPROVED))
        transaction.commit()

        code, out, err = self._runScript()
        self.assertEqual(0, code)
        self.assertEqual(0, len(out))
        self.failUnless(
            re.search('missing TeamParticipation entries for zzzzz', err))
        self.failUnless(
            re.search('spurious TeamParticipation entries for zzzzz', err))

    def test_report_circular_team_references(self):
        """The script reports circular references between teams.

        If that happens, though, the script will have to report the circular
        references and exit, to avoid an infinite loop when checking for
        missing/spurious TeamParticipation entries.
        """
        # Create two new teams and make them members of each other.
        cursor().execute("""
            INSERT INTO
                Person (id, name, displayname, teamowner)
                VALUES (9998, 'test-team1', 'team1', 1);
            INSERT INTO
                Person (id, name, displayname, teamowner)
                VALUES (9997, 'test-team2', 'team2', 1);
            INSERT INTO
                TeamMembership (person, team, status)
                VALUES (9998, 9997, %(approved)s);
            INSERT INTO
                TeamParticipation (person, team)
                VALUES (9998, 9997);
            INSERT INTO
                TeamMembership (person, team, status)
                VALUES (9997, 9998, %(approved)s);
            INSERT INTO
                TeamParticipation (person, team)
                VALUES (9997, 9998);
            """ % sqlvalues(approved=TeamMembershipStatus.APPROVED))
        transaction.commit()
        code, out, err = self._runScript()
        self.assertEqual(1, code)
        self.assertEqual(0, len(out))
        self.failUnless(re.search('Circular references found', err))

    # A script to create two new people, where both participate in the first,
    # and first is missing a self-participation.
    script_create_inconsistent_participation = """
        INSERT INTO
            Person (id, name, displayname, creation_rationale)
            VALUES (6969, 'bobby', 'Dazzler', 1);
        INSERT INTO
            Person (id, name, displayname, creation_rationale)
            VALUES (6970, 'nobby', 'Jazzler', 1);
        INSERT INTO
            TeamParticipation (person, team)
            VALUES (6970, 6969);
        DELETE FROM
            TeamParticipation
            WHERE person = 6969
              AND team = 6969;
        """

    def test_check_teamparticipation_consistency(self):
        """The script reports spurious participants of people.

        Teams can have multiple participants, but only the person should be a
        paricipant of him/herself.
        """
        cursor().execute(self.script_create_inconsistent_participation)
        transaction.commit()
        logger = BufferLogger()
        self.addDetail("log", logger.content)
        errors = check_teamparticipation_consistency(
            logger, fetch_team_participation_info(logger))
        errors_expected = [
            ConsistencyError("spurious", 6969, [6970]),
            ConsistencyError("missing", 6969, [6969]),
            ]
        self.assertContentEqual(errors_expected, errors)

    def test_fix_teamparticipation_consistency(self):
        """
        `fix_teamparticipation_consistency` takes an iterable of
        `ConsistencyError`s and attempts to repair the data.
        """
        cursor().execute(self.script_create_inconsistent_participation)
        transaction.commit()
        logger = BufferLogger()
        self.addDetail("log", logger.content)
        errors = check_teamparticipation_consistency(
            logger, fetch_team_participation_info(logger))
        self.assertNotEqual([], errors)
        fix_teamparticipation_consistency(logger, errors)
        errors = check_teamparticipation_consistency(
            logger, fetch_team_participation_info(logger))
        self.assertEqual([], errors)

    def test_load_and_save_team_participation(self):
        """The script can load and save participation info."""
        logger = BufferLogger()
        self.addDetail("log", logger.content)
        info = fetch_team_participation_info(logger)
        tempdir = self.useFixture(TempDir()).path
        filename_in = os.path.join(tempdir, "info.in")
        filename_out = os.path.join(tempdir, "info.out")
        fout = bz2.BZ2File(filename_in, "w")
        try:
            pickle.dump(info, fout, pickle.HIGHEST_PROTOCOL)
        finally:
            fout.close()
        code, out, err = self._runScript(
            "--load-participation-info", filename_in,
            "--save-participation-info", filename_out)
        self.assertEqual(0, code)
        fin = bz2.BZ2File(filename_out, "r")
        try:
            saved_info = pickle.load(fin)
        finally:
            fin.close()
        self.assertEqual(info, saved_info)


class TestCheckTeamParticipationScriptPerformance(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_queries(self):
        """The script does not overly tax the database.

        The whole check_teamparticipation() run executes a constant low number
        of queries.
        """
        # Create a deeply nested team and member structure.
        team = self.factory.makeTeam()
        for num in xrange(10):
            another_team = self.factory.makeTeam()
            another_person = self.factory.makePerson()
            with person_logged_in(team.teamowner):
                team.addMember(another_team, team.teamowner)
                team.addMember(another_person, team.teamowner)
            team = another_team
        transaction.commit()
        logger = BufferLogger()
        self.addDetail("log", logger.content)
        with StormStatementRecorder() as recorder:
            check_teamparticipation_circular(logger)
            check_teamparticipation_consistency(
                logger, fetch_team_participation_info(logger))
        self.assertThat(recorder, HasQueryCount(Equals(5)))


def test_suite():
    suite = TestLoader().loadTestsFromName(__name__)
    bug_249185 = LayeredDocFileSuite(
        'bug-249185.txt', optionflags=default_optionflags,
        layer=DatabaseFunctionalLayer, setUp=setUp, tearDown=tearDown)
    suite.addTest(bug_249185)
    return suite
