# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
from zope.component import (
    getSiteManager,
    getUtility,
    )
from zope.interface import (
    implements,
    Interface,
    )
from zope.security.proxy import removeSecurityProxy

from lp.app.interfaces.security import IAuthorization
from lp.app.security import (
    AuthorizationBase,
    DelegatedAuthorization,
    )
from lp.registry.enums import PersonVisibility
from lp.registry.interfaces.person import IPerson
from lp.registry.interfaces.role import IPersonRoles
from lp.registry.interfaces.teammembership import (
    ITeamMembershipSet,
    TeamMembershipStatus,
    )
from lp.security import PublicOrPrivateTeamsExistence
from lp.testing import (
    person_logged_in,
    TestCase,
    TestCaseWithFactory,
    )
from lp.testing.fakemethod import FakeMethod
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    ZopelessDatabaseLayer,
    )


def registerFakeSecurityAdapter(interface, permission, adapter=None):
    """Register an instance of FakeSecurityAdapter.

    Create a factory for an instance of FakeSecurityAdapter and register
    it as an adapter for the given interface and permission name.
    """
    if adapter is None:
        adapter = FakeSecurityAdapter()

    def adapter_factory(adaptee):
        return adapter

    getSiteManager().registerAdapter(
        adapter_factory, (interface,), IAuthorization, permission)
    return adapter


class FakeSecurityAdapter(AuthorizationBase):

    def __init__(self, adaptee=None):
        super(FakeSecurityAdapter, self).__init__(adaptee)
        self.checkAuthenticated = FakeMethod()
        self.checkUnauthenticated = FakeMethod()


class IDummy(Interface):
    """Marker interface to test forwarding."""


class Dummy:
    """An implementation of IDummy."""
    implements(IDummy)


class TestAuthorizationBase(TestCaseWithFactory):

    layer = ZopelessDatabaseLayer

    def test_checkAuthenticated_for_full_fledged_account(self):
        # AuthorizationBase.checkAuthenticated should delegate to
        # checkAuthenticated() when the given account can be adapted
        # into an IPerson.
        full_fledged_account = self.factory.makePerson().account
        adapter = FakeSecurityAdapter()
        adapter.checkAuthenticated(IPerson(full_fledged_account))
        self.assertVectorEqual(
            (1, adapter.checkAuthenticated.call_count),
            (0, adapter.checkUnauthenticated.call_count))

    def test_forwardCheckAuthenticated_object_changes(self):
        # Requesting a check for the same permission on a different object.
        permission = self.factory.getUniqueString()
        next_adapter = registerFakeSecurityAdapter(
            IDummy, permission)

        adapter = FakeSecurityAdapter()
        adapter.permission = permission
        adapter.usedfor = None
        adapter.checkPermissionIsRegistered = FakeMethod(result=True)

        adapter.forwardCheckAuthenticated(None, Dummy())

        self.assertVectorEqual(
            (1, adapter.checkPermissionIsRegistered.call_count),
            (1, next_adapter.checkAuthenticated.call_count))

    def test_forwardCheckAuthenticated_permission_changes(self):
        # Requesting a check for a different permission on the same object.
        next_permission = self.factory.getUniqueString()
        next_adapter = registerFakeSecurityAdapter(
            IDummy, next_permission)

        adapter = FakeSecurityAdapter(Dummy())
        adapter.permission = self.factory.getUniqueString()
        adapter.usedfor = IDummy
        adapter.checkPermissionIsRegistered = FakeMethod(result=True)

        adapter.forwardCheckAuthenticated(None, permission=next_permission)

        self.assertVectorEqual(
            (1, adapter.checkPermissionIsRegistered.call_count),
            (1, next_adapter.checkAuthenticated.call_count))

    def test_forwardCheckAuthenticated_both_change(self):
        # Requesting a check for a different permission and a different
        # object.
        next_permission = self.factory.getUniqueString()
        next_adapter = registerFakeSecurityAdapter(
            IDummy, next_permission)

        adapter = FakeSecurityAdapter()
        adapter.permission = self.factory.getUniqueString()
        adapter.usedfor = None
        adapter.checkPermissionIsRegistered = FakeMethod(result=True)

        adapter.forwardCheckAuthenticated(None, Dummy(), next_permission)

        self.assertVectorEqual(
            (1, adapter.checkPermissionIsRegistered.call_count),
            (1, next_adapter.checkAuthenticated.call_count))

    def test_forwardCheckAuthenticated_no_forwarder(self):
        # If the requested forwarding adapter does not exist, return False.
        adapter = FakeSecurityAdapter()
        adapter.permission = self.factory.getUniqueString()
        adapter.usedfor = IDummy
        adapter.checkPermissionIsRegistered = FakeMethod(result=True)

        self.assertFalse(
            adapter.forwardCheckAuthenticated(None, Dummy()))


class TestDelegatedAuthorization(TestCase):
    """Tests for `DelegatedAuthorization`."""

    def test_checkAuthenticated(self):
        # DelegatedAuthorization.checkAuthenticated() punts the checks back up
        # to the security policy by generating (object, permission) tuples.
        # The security policy is in a much better position to, well, apply
        # policy.
        obj, delegated_obj = object(), object()
        authorization = DelegatedAuthorization(
            obj, delegated_obj, "dedicatemyselfto.Evil")
        # By default DelegatedAuthorization.checkAuthenticated() ignores its
        # user argument, so we pass None in below, but it is required for
        # IAuthorization, and may be useful for subclasses.
        self.assertEqual(
            [(delegated_obj, "dedicatemyselfto.Evil")],
            list(authorization.checkAuthenticated(None)))

    def test_checkUnauthenticated(self):
        # DelegatedAuthorization.checkUnauthenticated() punts the checks back
        # up to the security policy by generating (object, permission) tuples.
        # The security policy is in a much better position to, well, apply
        # policy.
        obj, delegated_obj = object(), object()
        authorization = DelegatedAuthorization(
            obj, delegated_obj, "dedicatemyselfto.Evil")
        self.assertEqual(
            [(delegated_obj, "dedicatemyselfto.Evil")],
            list(authorization.checkUnauthenticated()))


class TestPublicOrPrivateTeamsExistence(TestCaseWithFactory):
    """Tests for the PublicOrPrivateTeamsExistence security adapter."""

    layer = DatabaseFunctionalLayer

    def test_members_of_parent_teams_get_limited_view(self):
        team_owner = self.factory.makePerson()
        private_team = self.factory.makeTeam(
            owner=team_owner, visibility=PersonVisibility.PRIVATE)
        public_team = self.factory.makeTeam(owner=team_owner)
        team_user = self.factory.makePerson()
        other_user = self.factory.makePerson()
        with person_logged_in(team_owner):
            public_team.addMember(team_user, team_owner)
            public_team.addMember(private_team, team_owner)
        checker = PublicOrPrivateTeamsExistence(
            removeSecurityProxy(private_team))
        self.assertTrue(checker.checkAuthenticated(IPersonRoles(team_user)))
        self.assertFalse(checker.checkAuthenticated(IPersonRoles(other_user)))

    def test_members_of_pending_parent_teams_get_limited_view(self):
        team_owner = self.factory.makePerson()
        private_team = self.factory.makeTeam(
            owner=team_owner, visibility=PersonVisibility.PRIVATE)
        public_team = self.factory.makeTeam(owner=team_owner)
        team_user = self.factory.makePerson()
        other_user = self.factory.makePerson()
        with person_logged_in(team_owner):
            public_team.addMember(team_user, team_owner)
            getUtility(ITeamMembershipSet).new(
               private_team,
               public_team,
               TeamMembershipStatus.INVITED,
               team_owner)
        checker = PublicOrPrivateTeamsExistence(
            removeSecurityProxy(private_team))
        self.assertTrue(checker.checkAuthenticated(IPersonRoles(team_user)))
        self.assertFalse(checker.checkAuthenticated(IPersonRoles(other_user)))
