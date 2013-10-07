# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the user vocabularies."""

__metaclass__ = type

from zope.component import getUtility
from zope.schema.vocabulary import getVocabularyRegistry

from lp.registry.enums import TeamMembershipPolicy
from lp.registry.interfaces.person import (
    IPersonSet,
    PersonVisibility,
    )
from lp.registry.model.person import Person
from lp.services.database.interfaces import IStore
from lp.testing import (
    ANONYMOUS,
    login,
    login_person,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestUserTeamsParticipationPlusSelfVocabulary(TestCaseWithFactory):
    """Test that the UserTeamsParticipationPlusSelf behaves as expected."""

    layer = DatabaseFunctionalLayer

    def _vocabTermValues(self):
        """Return the token values for the vocab."""
        vocabulary_registry = getVocabularyRegistry()
        vocab = vocabulary_registry.get(
            None, 'UserTeamsParticipationPlusSelf')
        return [term.value for term in vocab]

    def test_user_no_team(self):
        user = self.factory.makePerson()
        login_person(user)
        self.assertEqual([user], self._vocabTermValues())

    def test_user_teams(self):
        # The ordering goes user first, then alphabetical by team display
        # name.
        user = self.factory.makePerson()
        team_owner = self.factory.makePerson()
        login_person(team_owner)
        bravo = self.factory.makeTeam(owner=team_owner, displayname="Bravo")
        bravo.addMember(person=user, reviewer=team_owner)
        alpha = self.factory.makeTeam(owner=team_owner, displayname="Alpha")
        alpha.addMember(person=user, reviewer=team_owner)
        login_person(user)
        self.assertEqual([user, alpha, bravo], self._vocabTermValues())

    def test_user_no_private_teams(self):
        # Private teams are not shown in the vocabulary.
        user = self.factory.makePerson()
        team_owner = self.factory.makePerson()
        login_person(team_owner)
        team = self.factory.makeTeam(owner=team_owner)
        team.addMember(person=user, reviewer=team_owner)
        # Launchpad admin rights are needed to set private.
        login('foo.bar@canonical.com')
        team.visibility = PersonVisibility.PRIVATE
        login_person(user)
        self.assertEqual([user], self._vocabTermValues())

    def test_indirect_team_membership(self):
        # Indirect team membership is shown.
        user = self.factory.makePerson()
        team_owner = self.factory.makePerson()
        login_person(team_owner)
        bravo = self.factory.makeTeam(owner=team_owner, displayname="Bravo")
        bravo.addMember(person=user, reviewer=team_owner)
        alpha = self.factory.makeTeam(owner=team_owner, displayname="Alpha")
        alpha.addMember(
            person=bravo, reviewer=team_owner, force_team_add=True)
        login_person(user)
        self.assertEqual([user, alpha, bravo], self._vocabTermValues())


class TestAllUserTeamsParticipationPlusSelfVocabulary(TestCaseWithFactory):
    """Test that the AllUserTeamsParticipationPlusSelf behaves as expected."""

    layer = DatabaseFunctionalLayer

    def _vocabTermValues(self, context=None):
        """Return the token values for the vocab."""
        vocabulary_registry = getVocabularyRegistry()
        vocab = vocabulary_registry.get(
            context, 'AllUserTeamsParticipationPlusSelf')
        return [term.value for term in vocab]

    def test_user_no_private_teams(self):
        # Private teams are shown in the vocabulary.
        team_owner = self.factory.makePerson()
        team = self.factory.makeTeam(
            owner=team_owner, visibility=PersonVisibility.PRIVATE)
        login_person(team_owner)
        self.assertEqual([team_owner, team], self._vocabTermValues())

    def test_only_exclusive_teams_for_series_branches(self):
        # For series branches, only exclusive teams are permitted in the vocab.
        branch = self.factory.makeBranch()
        self.factory.makeProductSeries(branch=branch)
        team_owner = self.factory.makePerson()
        self.factory.makeTeam(
            owner=team_owner, membership_policy=TeamMembershipPolicy.OPEN)
        exclusive_team = self.factory.makeTeam(
            owner=team_owner, membership_policy=TeamMembershipPolicy.MODERATED)
        login_person(team_owner)
        self.assertEqual(
            [team_owner, exclusive_team], self._vocabTermValues(branch))

    def test_all_teams_for_non_series_branches(self):
        # For non series branches, all teams are permitted in the vocab.
        branch = self.factory.makeBranch()
        team_owner = self.factory.makePerson()
        inclusive_team = self.factory.makeTeam(
            owner=team_owner, membership_policy=TeamMembershipPolicy.OPEN)
        exclusive_team = self.factory.makeTeam(
            owner=team_owner, membership_policy=TeamMembershipPolicy.MODERATED)
        login_person(team_owner)
        self.assertContentEqual(
            [team_owner, exclusive_team, inclusive_team],
            self._vocabTermValues(branch))


class TestAllUserTeamsParticipationVocabulary(TestCaseWithFactory):
    """AllUserTeamsParticipation contains all teams joined by a user.

    This includes private teams.
    """

    layer = DatabaseFunctionalLayer

    def _vocabTermValues(self):
        """Return the token values for the vocab."""
        # XXX Abel Deuring 2010-05-21, bug 583502: We cannot simply iterate
        # over the items of AllUserTeamsPariticipationVocabulary, so
        # so iterate over all Persons and check membership.
        vocabulary_registry = getVocabularyRegistry()
        vocab = vocabulary_registry.get(None, 'AllUserTeamsParticipation')
        return [p for p in IStore(Person).find(Person) if p in vocab]

    def test_user_no_team(self):
        user = self.factory.makePerson()
        login_person(user)
        self.assertEqual([], self._vocabTermValues())

    def test_user_is_team_owner(self):
        user = self.factory.makePerson()
        login_person(user)
        team = self.factory.makeTeam(owner=user)
        self.assertEqual([team], self._vocabTermValues())

    def test_user_in_two_teams(self):
        user = self.factory.makePerson()
        login_person(user)
        team1 = self.factory.makeTeam(members=[user])
        team2 = self.factory.makeTeam(members=[user])
        self.assertContentEqual([team1, team2], set(self._vocabTermValues()))

    def test_user_in_private_teams(self):
        # Private teams are included in the vocabulary.
        user = self.factory.makePerson()
        team = self.factory.makeTeam(
            members=[user], visibility=PersonVisibility.PRIVATE)
        login_person(user)
        self.assertEqual([team], self._vocabTermValues())

    def test_teams_of_anonymous(self):
        # AllUserTeamsPariticipationVocabulary is empty for anoymous users.
        login(ANONYMOUS)
        self.assertEqual([], self._vocabTermValues())

    def test_commercial_admin(self):
        # The vocab does the membership check for commercial admins too.
        user = self.factory.makeCommercialAdmin()
        com_admins = getUtility(IPersonSet).getByName('commercial-admins')
        ppa_admins = getUtility(IPersonSet).getByName(
            'launchpad-ppa-self-admins')
        team1 = self.factory.makeTeam(members=[user])
        login_person(user)
        self.assertContentEqual(
            [com_admins, ppa_admins, team1], self._vocabTermValues())
