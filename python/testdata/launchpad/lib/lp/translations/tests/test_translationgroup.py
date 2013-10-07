# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for `TranslationGroup` and related classes."""

__metaclass__ = type

from lazr.restfulclient.errors import Unauthorized
import transaction
from zope.component import getUtility

from lp.registry.interfaces.teammembership import (
    ITeamMembershipSet,
    TeamMembershipStatus,
    )
from lp.testing import (
    TestCaseWithFactory,
    WebServiceTestCase,
    )
from lp.testing.layers import ZopelessDatabaseLayer
from lp.translations.interfaces.translationgroup import ITranslationGroupSet


class TestTranslationGroupSet(TestCaseWithFactory):
    layer = ZopelessDatabaseLayer

    def _enrollInTeam(self, team, member):
        """Make `member` a member of `team`."""
        getUtility(ITeamMembershipSet).new(
            member, team, TeamMembershipStatus.APPROVED, team.teamowner)

    def _makeTranslationTeam(self, group, member, language_code):
        """Create translation team and enroll `member` in it."""
        team = self.factory.makeTeam()
        self.factory.makeTranslator(language_code, group=group, person=team)
        self._enrollInTeam(team, member)
        return team

    def test_getByPerson_distinct_membership(self):
        # A person can be in a translation team multiple times through
        # indirect membership, but a group using that team will show up
        # only once in getByPerson.
        group = self.factory.makeTranslationGroup()
        person = self.factory.makePerson()
        translation_team = self._makeTranslationTeam(group, person, 'nl')

        nested_team = self.factory.makeTeam()
        self._enrollInTeam(translation_team, nested_team)
        self._enrollInTeam(nested_team, person)

        self.assertEqual(
            [group],
            list(getUtility(ITranslationGroupSet).getByPerson(person)))

    def test_getByPerson_distinct_translationteam(self):
        # getByPerson returns a group only once even if the person is a
        # member of multiple translation teams in the group.
        group = self.factory.makeTranslationGroup()
        person = self.factory.makePerson()

        self._makeTranslationTeam(group, person, 'es')
        self._makeTranslationTeam(group, person, 'ca')

        self.assertEqual(
            [group],
            list(getUtility(ITranslationGroupSet).getByPerson(person)))


class TestWebService(WebServiceTestCase):

    def test_getByName(self):
        """getByName returns the TranslationGroup for the specified name."""
        group = self.factory.makeTranslationGroup()
        transaction.commit()
        ws_group = self.service.translation_groups.getByName(name=group.name)
        self.assertEqual(group.name, ws_group.name)

    def test_attrs(self):
        """TranslationGroup provides the expected attributes."""
        group = self.factory.makeTranslationGroup()
        transaction.commit()
        ws_group = self.wsObject(group)
        self.assertEqual(group.name, ws_group.name)
        self.assertEqual(group.title, ws_group.title)
        ws_group.name = 'foo'
        e = self.assertRaises(Unauthorized, ws_group.lp_save)
        self.assertIn("'name', 'launchpad.Edit'", str(e))

    def test_list_groups(self):
        """Listing translation groups works and is accurate."""
        translation_group_set = getUtility(ITranslationGroupSet)
        self.assertContentEqual(
            [group.name for group in translation_group_set],
            [group.name for group in self.service.translation_groups])
