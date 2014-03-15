# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the login helpers."""

__metaclass__ = type

from zope.authentication.interfaces import IUnauthenticatedPrincipal
from zope.component import getUtility
from zope.security.management import getInteraction

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.services.webapp.interaction import get_current_principal
from lp.services.webapp.interfaces import IOpenLaunchBag
from lp.testing import (
    ANONYMOUS,
    anonymous_logged_in,
    celebrity_logged_in,
    login,
    login_as,
    login_celebrity,
    login_person,
    login_team,
    logout,
    person_logged_in,
    TestCaseWithFactory,
    with_anonymous_login,
    with_celebrity_logged_in,
    with_person_logged_in,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestLoginHelpers(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def getLoggedInPerson(self):
        """Return the currently logged-in person.

        If no one is logged in, return None. If there is an anonymous user
        logged in, then return ANONYMOUS. Otherwise, return the logged-in
        `IPerson`.
        """
        # I don't really know the canonical way of asking for "the logged-in
        # person", so instead I'm using all the ways I can find and making
        # sure they match each other. -- jml
        by_launchbag = getUtility(IOpenLaunchBag).user
        principal = get_current_principal()
        if principal is None:
            return None
        elif IUnauthenticatedPrincipal.providedBy(principal):
            if by_launchbag is None:
                return ANONYMOUS
            else:
                raise ValueError(
                    "Unauthenticated principal, but launchbag thinks "
                    "%r is logged in." % (by_launchbag,))
        else:
            by_principal = principal.person
            self.assertEqual(by_launchbag, by_principal)
            return by_principal

    def assertLoggedIn(self, person):
        """Assert that 'person' is logged in."""
        self.assertEqual(person, self.getLoggedInPerson())

    def assertLoggedOut(self):
        """Assert that no one is currently logged in."""
        self.assertIs(None, get_current_principal())
        self.assertIs(None, getUtility(IOpenLaunchBag).user)

    def test_not_logged_in(self):
        # After logout has been called, we are not logged in.
        logout()
        self.assertLoggedOut()

    def test_logout_twice(self):
        # Logging out twice don't harm anybody none.
        logout()
        logout()
        self.assertLoggedOut()

    def test_login_person_actually_logs_in(self):
        # login_person changes the currently logged in person.
        person = self.factory.makePerson()
        logout()
        login_person(person)
        self.assertLoggedIn(person)

    def test_login_different_person_overrides(self):
        # Calling login_person a second time with a different person changes
        # the currently logged in user.
        a = self.factory.makePerson()
        b = self.factory.makePerson()
        logout()
        login_person(a)
        login_person(b)
        self.assertLoggedIn(b)

    def test_login_person_with_team(self):
        # Calling login_person with a team raises a nice error.
        team = self.factory.makeTeam()
        e = self.assertRaises(ValueError, login_person, team)
        self.assertEqual(str(e), "Got team, expected person: %r" % (team,))

    def test_login_with_email(self):
        # login() logs a person in by email.
        email = 'test-email@example.com'
        person = self.factory.makePerson(email=email)
        logout()
        login(email)
        self.assertLoggedIn(person)

    def test_login_anonymous(self):
        # login as 'ANONYMOUS' logs in as the anonymous user.
        logout()
        login(ANONYMOUS)
        self.assertLoggedIn(ANONYMOUS)

    def test_login_team(self):
        # login_team() logs in as a member of the given team.
        team = self.factory.makeTeam()
        logout()
        login_team(team)
        person = self.getLoggedInPerson()
        self.assertTrue(person.inTeam(team))

    def test_login_team_with_person(self):
        # Calling login_team() with a person instead of a team raises a nice
        # error.
        person = self.factory.makePerson()
        logout()
        e = self.assertRaises(ValueError, login_team, person)
        self.assertEqual(str(e), "Got person, expected team: %r" % (person,))

    def test_login_team_returns_logged_in_person(self):
        # login_team returns the logged-in person.
        team = self.factory.makeTeam()
        logout()
        person = login_team(team)
        self.assertLoggedIn(person)

    def test_login_as_person(self):
        # login_as() logs in as a person if it's given a person.
        person = self.factory.makePerson()
        logout()
        login_as(person)
        self.assertLoggedIn(person)

    def test_login_as_team(self):
        # login_as() logs in as a member of a team if it's given a team.
        team = self.factory.makeTeam()
        logout()
        login_as(team)
        person = self.getLoggedInPerson()
        self.assertTrue(person.inTeam(team))

    def test_login_as_anonymous(self):
        # login_as(ANONYMOUS) logs in as the anonymous user.
        logout()
        login_as(ANONYMOUS)
        self.assertLoggedIn(ANONYMOUS)

    def test_login_as_None(self):
        # login_as(None) logs in as the anonymous user.
        logout()
        login_as(None)
        self.assertLoggedIn(ANONYMOUS)

    def test_login_celebrity(self):
        # login_celebrity logs in a celebrity.
        logout()
        login_celebrity('vcs_imports')
        vcs_imports = getUtility(ILaunchpadCelebrities).vcs_imports
        person = self.getLoggedInPerson()
        self.assertTrue(person.inTeam(vcs_imports))

    def test_login_nonexistent_celebrity(self):
        # login_celebrity raises ValueError when called with a non-existent
        # celebrity.
        logout()
        e = self.assertRaises(ValueError, login_celebrity, 'nonexistent')
        self.assertEqual(str(e), "No such celebrity: 'nonexistent'")

    def test_person_logged_in(self):
        # The person_logged_in context manager runs with a person logged in.
        person = self.factory.makePerson()
        with person_logged_in(person):
            self.assertLoggedIn(person)

    def test_person_logged_in_restores_person(self):
        # Once outside of the person_logged_in context, the originally
        # logged-in person is re-logged in.
        a = self.factory.makePerson()
        login_as(a)
        b = self.factory.makePerson()
        with person_logged_in(b):
            self.assertLoggedIn(b)
        self.assertLoggedIn(a)

    def test_person_logged_in_restores_participation(self):
        # Once outside of the person_logged_in context, the original
        # participation (e.g., request) is used.  This can be important for
        # yuixhr test fixtures, in particular.
        a = self.factory.makePerson()
        login_as(a)
        participation = getInteraction().participations[0]
        b = self.factory.makePerson()
        with person_logged_in(b):
            self.assertLoggedIn(b)
        self.assertIs(participation, getInteraction().participations[0])

    def test_person_logged_in_restores_logged_out(self):
        # If we are logged out before the person_logged_in context, then we
        # are logged out afterwards.
        person = self.factory.makePerson()
        logout()
        with person_logged_in(person):
            pass
        self.assertLoggedOut()

    def test_person_logged_in_restores_person_even_when_raises(self):
        # Once outside of the person_logged_in context, the originially
        # logged-in person is re-logged in.
        a = self.factory.makePerson()
        login_as(a)
        b = self.factory.makePerson()
        try:
            with person_logged_in(b):
                1 / 0
        except ZeroDivisionError:
            pass
        self.assertLoggedIn(a)

    def test_team_logged_in(self):
        # person_logged_in also works when given teams.
        team = self.factory.makeTeam()
        with person_logged_in(team):
            person = self.getLoggedInPerson()
        self.assertTrue(person.inTeam(team))

    def test_team_logged_in_provides_person(self):
        # person_logged_in makes the logged-in person available through
        # the context manager.
        team = self.factory.makeTeam()
        with person_logged_in(team) as p:
            person = self.getLoggedInPerson()
        self.assertEqual(p, person)

    def test_celebrity_logged_in(self):
        # celebrity_logged_in runs in a context where a celebrity is logged
        # in.
        vcs_imports = getUtility(ILaunchpadCelebrities).vcs_imports
        with celebrity_logged_in('vcs_imports'):
            person = self.getLoggedInPerson()
        self.assertTrue(person.inTeam(vcs_imports))

    def test_celebrity_logged_in_provides_person(self):
        vcs_imports = getUtility(ILaunchpadCelebrities).vcs_imports
        with celebrity_logged_in('vcs_imports') as p:
            person = self.getLoggedInPerson()
        self.assertEqual(p, person)

    def test_celebrity_logged_in_restores_person(self):
        # Once outside of the celebrity_logged_in context, the originally
        # logged-in person is re-logged in.
        person = self.factory.makePerson()
        login_as(person)
        with celebrity_logged_in('vcs_imports'):
            pass
        self.assertLoggedIn(person)

    def test_with_celebrity_logged_in(self):
        # with_celebrity_logged_in decorates a function so that it runs with
        # the given person logged in.
        vcs_imports = getUtility(ILaunchpadCelebrities).vcs_imports

        @with_celebrity_logged_in('vcs_imports')
        def f():
            return self.getLoggedInPerson()

        login_as(None)
        person = f()
        self.assertTrue(person.inTeam, vcs_imports)

    def test_with_person_logged_in(self):
        person = self.factory.makePerson()

        @with_person_logged_in(person)
        def f():
            return self.getLoggedInPerson()

        login_as(None)
        logged_in = f()
        self.assertEqual(person, logged_in)

    def test_with_anonymous_log_in(self):
        # with_anonymous_login logs in as the anonymous user.
        @with_anonymous_login
        def f():
            return self.getLoggedInPerson()
        person = f()
        self.assertEqual(ANONYMOUS, person)

    def test_anonymous_log_in(self):
        # anonymous_logged_in is a context logged in as anonymous.
        with anonymous_logged_in():
            self.assertLoggedIn(ANONYMOUS)
