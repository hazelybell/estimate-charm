# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for `lp.services.webapp.authorization`."""

__metaclass__ = type

from random import getrandbits
import StringIO

import transaction
from zope.component import (
    provideAdapter,
    provideUtility,
    )
from zope.interface import (
    classProvides,
    implements,
    Interface,
    )
from zope.security.interfaces import Unauthorized
import zope.testing.cleanup

from lp.app.interfaces.security import IAuthorization
from lp.app.security import AuthorizationBase
from lp.registry.interfaces.person import IPerson
from lp.registry.interfaces.role import IPersonRoles
from lp.services.database.interfaces import IStoreSelector
from lp.services.privacy.interfaces import IObjectPrivacy
from lp.services.webapp.authentication import LaunchpadPrincipal
from lp.services.webapp.authorization import (
    available_with_permission,
    check_permission,
    iter_authorization,
    LAUNCHPAD_SECURITY_POLICY_CACHE_KEY,
    LaunchpadSecurityPolicy,
    precache_permission_for_objects,
    )
from lp.services.webapp.interfaces import (
    AccessLevel,
    ILaunchpadContainer,
    ILaunchpadPrincipal,
    )
from lp.services.webapp.metazcml import ILaunchpadPermission
from lp.services.webapp.servers import (
    LaunchpadBrowserRequest,
    LaunchpadTestRequest,
    )
from lp.testing import (
    ANONYMOUS,
    login,
    TestCase,
    )
from lp.testing.factory import ObjectFactory
from lp.testing.fixture import ZopeAdapterFixture
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    ZopelessLayer,
    )


class Allow(AuthorizationBase):
    """An `IAuthorization` adapter allowing everything."""

    def checkUnauthenticated(self):
        return True

    def checkAuthenticated(self, user):
        return True


class Deny(AuthorizationBase):
    """An `IAuthorization` adapter denying everything."""

    def checkUnauthenticated(self):
        return False

    def checkAuthenticated(self, user):
        return False


class Explode(AuthorizationBase):
    """An `IAuthorization` adapter that explodes when used."""

    def checkUnauthenticated(self):
        raise NotImplementedError()

    def checkAuthenticated(self, user):
        raise NotImplementedError()


class Checker(AuthorizationBase):
    """See `IAuthorization`.

    Instances of this class record calls made to `IAuthorization` methods.
    """

    def __init__(self, obj, calls):
        AuthorizationBase.__init__(self, obj)
        self.calls = calls

    def checkUnauthenticated(self):
        """See `IAuthorization.checkUnauthenticated`.

        We record the call and then return False, arbitrarily chosen, to keep
        the policy from complaining.
        """
        self.calls.append('checkUnauthenticated')
        return False

    def checkAuthenticated(self, user):
        """See `IAuthorization.checkAuthenticated`.

        We record the call and then return False, arbitrarily chosen, to keep
        the policy from complaining.
        """
        self.calls.append(('checkAuthenticated', user))
        return False


class CheckerFactory:
    """Factory for `Checker` objects.

    Instances of this class are intended to be registered as adapters to
    `IAuthorization`.

    :ivar calls: Calls made to the methods of `Checker`s constructed by this
        instance.
    """

    def __init__(self):
        self.calls = []

    def __call__(self, obj):
        return Checker(obj, self.calls)


class Object:
    """An arbitrary object, adaptable to `IObjectPrivacy`.

    For simplicity we implement `IObjectPrivacy` directly."""
    implements(IObjectPrivacy)
    is_private = False


class AnotherObjectOne:
    """Another arbitrary object."""


class AnotherObjectTwo:
    """Another arbitrary object."""


class Delegate(AuthorizationBase):
    """An `IAuthorization` adapter that delegates."""

    permission = "making.Hay"
    object_one = AnotherObjectOne()
    object_two = AnotherObjectTwo()

    def checkUnauthenticated(self):
        yield self.object_one, self.permission
        yield self.object_two, self.permission

    def checkAuthenticated(self, user):
        yield self.object_one, self.permission
        yield self.object_two, self.permission


class PermissionAccessLevel:
    """A minimal implementation of `ILaunchpadPermission`."""
    implements(ILaunchpadPermission)
    access_level = 'read'


class FakePerson:
    """A minimal object to represent a person."""
    implements(IPerson, IPersonRoles)


class FakeLaunchpadPrincipal:
    """A minimal principal implementing `ILaunchpadPrincipal`"""
    implements(ILaunchpadPrincipal)
    person = FakePerson()
    scope = None
    access_level = ''


class FakeStore:
    """Enough of a store to fool the `block_implicit_flushes` decorator."""
    def block_implicit_flushes(self):
        pass

    def unblock_implicit_flushes(self):
        pass


class FakeStoreSelector:
    """A store selector that always returns a `FakeStore`."""
    classProvides(IStoreSelector)

    @staticmethod
    def get(name, flavor):
        return FakeStore()

    @staticmethod
    def push(dbpolicy):
        pass

    @staticmethod
    def pop():
        pass


class TestCheckPermissionCaching(TestCase):
    """Test the caching done by `LaunchpadSecurityPolicy.checkPermission`."""

    def setUp(self):
        """Register a new permission and a fake store selector."""
        zope.testing.cleanup.cleanUp()
        super(TestCheckPermissionCaching, self).setUp()
        self.factory = ObjectFactory()
        provideUtility(FakeStoreSelector, IStoreSelector)
        self.addCleanup(zope.testing.cleanup.cleanUp)

    def makeRequest(self):
        """Construct an arbitrary `LaunchpadBrowserRequest` object."""
        data = StringIO.StringIO()
        env = {}
        return LaunchpadBrowserRequest(data, env)

    def getObjectPermissionAndCheckerFactory(self):
        """Return an object, a permission and a `CheckerFactory` for them.

        :return: A tuple ``(obj, permission, checker_factory)``, such that
            ``queryAdapter(obj, IAuthorization, permission)`` will return a
            `Checker` created by ``checker_factory``.
        """
        permission = self.factory.getUniqueString()
        provideUtility(
            PermissionAccessLevel(), ILaunchpadPermission, permission)
        checker_factory = CheckerFactory()
        provideAdapter(
            checker_factory, [Object], IAuthorization, name=permission)
        return Object(), permission, checker_factory

    def test_checkPermission_cache_unauthenticated(self):
        # checkPermission caches the result of checkUnauthenticated for a
        # particular object and permission.
        request = self.makeRequest()
        policy = LaunchpadSecurityPolicy(request)
        obj, permission, checker_factory = (
            self.getObjectPermissionAndCheckerFactory())
        # When we call checkPermission for the first time, the security policy
        # calls the checker.
        policy.checkPermission(permission, obj)
        self.assertEqual(
            ['checkUnauthenticated'], checker_factory.calls)
        # A subsequent identical call does not call the checker.
        policy.checkPermission(permission, obj)
        self.assertEqual(
            ['checkUnauthenticated'], checker_factory.calls)

    def test_checkPermission_delegated_cache_unauthenticated(self):
        # checkPermission caches the result of checkUnauthenticated for a
        # particular object and permission, even if that object's
        # authorization has been delegated.
        request = self.makeRequest()
        policy = LaunchpadSecurityPolicy(request)
        # Delegate auth for Object to AnotherObject{One,Two}.
        permission = self.factory.getUniqueString()
        self.useFixture(
            ZopeAdapterFixture(Delegate, [Object], name=permission))
        # Allow auth to AnotherObjectOne.
        self.useFixture(
            ZopeAdapterFixture(
                Allow, [AnotherObjectOne], name=Delegate.permission))
        # Deny auth to AnotherObjectTwo.
        self.useFixture(
            ZopeAdapterFixture(
                Deny, [AnotherObjectTwo], name=Delegate.permission))
        # Calling checkPermission() populates the participation cache.
        objecttoauthorize = Object()
        policy.checkPermission(permission, objecttoauthorize)
        # It contains results for objecttoauthorize and the two objects that
        # its authorization was delegated to.
        cache = request.annotations[LAUNCHPAD_SECURITY_POLICY_CACHE_KEY]
        cache_expected = {
            objecttoauthorize: {permission: False},
            Delegate.object_one: {Delegate.permission: True},
            Delegate.object_two: {Delegate.permission: False},
            }
        self.assertEqual(cache_expected, dict(cache))

    def test_checkPermission_cache_authenticated(self):
        # checkPermission caches the result of checkAuthenticated for a
        # particular object and permission.
        principal = FakeLaunchpadPrincipal()
        request = self.makeRequest()
        request.setPrincipal(principal)
        policy = LaunchpadSecurityPolicy(request)
        obj, permission, checker_factory = (
            self.getObjectPermissionAndCheckerFactory())
        # When we call checkPermission for the first time, the security policy
        # calls the checker.
        policy.checkPermission(permission, obj)
        self.assertEqual(
            [('checkAuthenticated', principal.person)],
            checker_factory.calls)
        # A subsequent identical call does not call the checker.
        policy.checkPermission(permission, obj)
        self.assertEqual(
            [('checkAuthenticated', principal.person)],
            checker_factory.calls)

    def test_checkPermission_clearSecurityPolicyCache_resets_cache(self):
        # Calling clearSecurityPolicyCache on the request clears the cache.
        request = self.makeRequest()
        policy = LaunchpadSecurityPolicy(request)
        obj, permission, checker_factory = (
            self.getObjectPermissionAndCheckerFactory())
        # When we call checkPermission for the first time, the security policy
        # calls checkUnauthenticated on the checker.
        policy.checkPermission(permission, obj)
        self.assertEqual(
            ['checkUnauthenticated'], checker_factory.calls)
        request.clearSecurityPolicyCache()
        # After clearing the cache the policy calls checkUnauthenticated
        # again.
        policy.checkPermission(permission, obj)
        self.assertEqual(
            ['checkUnauthenticated', 'checkUnauthenticated'],
            checker_factory.calls)

    def test_checkPermission_setPrincipal_resets_cache(self):
        # Setting the principal on the request clears the cache of results
        # (this is important during login).
        principal = FakeLaunchpadPrincipal()
        request = self.makeRequest()
        policy = LaunchpadSecurityPolicy(request)
        obj, permission, checker_factory = (
            self.getObjectPermissionAndCheckerFactory())
        # When we call checkPermission before setting the principal, the
        # security policy calls checkUnauthenticated on the checker.
        policy.checkPermission(permission, obj)
        self.assertEqual(
            ['checkUnauthenticated'], checker_factory.calls)
        request.setPrincipal(principal)
        # After setting the principal, the policy calls checkAuthenticated
        # rather than finding a value in the cache.
        policy.checkPermission(permission, obj)
        self.assertEqual(
            ['checkUnauthenticated', ('checkAuthenticated',
                                      principal.person)],
            checker_factory.calls)

    def test_checkPermission_commit_clears_cache(self):
        # Committing a transaction clears the cache.
        request = self.makeRequest()
        policy = LaunchpadSecurityPolicy(request)
        obj, permission, checker_factory = (
            self.getObjectPermissionAndCheckerFactory())
        # When we call checkPermission before setting the principal, the
        # security policy calls checkUnauthenticated on the checker.
        policy.checkPermission(permission, obj)
        self.assertEqual(
            ['checkUnauthenticated'], checker_factory.calls)
        transaction.commit()
        # After committing a transaction, the policy calls
        # checkUnauthenticated again rather than finding a value in the cache.
        policy.checkPermission(permission, obj)
        self.assertEqual(
            ['checkUnauthenticated', 'checkUnauthenticated'],
            checker_factory.calls)


class TestLaunchpadSecurityPolicy_getPrincipalsAccessLevel(TestCase):

    def setUp(self):
        zope.testing.cleanup.cleanUp()
        cls = TestLaunchpadSecurityPolicy_getPrincipalsAccessLevel
        super(cls, self).setUp()
        self.principal = LaunchpadPrincipal(
            'foo.bar@canonical.com', 'foo', 'foo', object())
        self.security = LaunchpadSecurityPolicy()
        provideAdapter(
            adapt_loneobject_to_container, [ILoneObject], ILaunchpadContainer)
        self.addCleanup(zope.testing.cleanup.cleanUp)

    def test_no_scope(self):
        """Principal's access level is used when no scope is given."""
        self.principal.access_level = AccessLevel.WRITE_PUBLIC
        self.principal.scope = None
        self.failUnlessEqual(
            self.security._getPrincipalsAccessLevel(
                self.principal, LoneObject()),
            self.principal.access_level)

    def test_object_within_scope(self):
        """Principal's access level is used when object is within scope."""
        obj = LoneObject()
        self.principal.access_level = AccessLevel.WRITE_PUBLIC
        self.principal.scope = obj
        self.failUnlessEqual(
            self.security._getPrincipalsAccessLevel(self.principal, obj),
            self.principal.access_level)

    def test_object_not_within_scope(self):
        """READ_PUBLIC is used when object is /not/ within scope."""
        obj = LoneObject()
        obj2 = LoneObject()  # This is out of obj's scope.
        self.principal.scope = obj

        self.principal.access_level = AccessLevel.WRITE_PUBLIC
        self.failUnlessEqual(
            self.security._getPrincipalsAccessLevel(self.principal, obj2),
            AccessLevel.READ_PUBLIC)

        self.principal.access_level = AccessLevel.READ_PRIVATE
        self.failUnlessEqual(
            self.security._getPrincipalsAccessLevel(self.principal, obj2),
            AccessLevel.READ_PUBLIC)

        self.principal.access_level = AccessLevel.WRITE_PRIVATE
        self.failUnlessEqual(
            self.security._getPrincipalsAccessLevel(self.principal, obj2),
            AccessLevel.READ_PUBLIC)


class ILoneObject(Interface):
    """A marker interface for objects that only contain themselves."""


class LoneObject:
    implements(ILoneObject, ILaunchpadContainer)

    def isWithin(self, context):
        return self == context


def adapt_loneobject_to_container(loneobj):
    """Adapt a LoneObject to an `ILaunchpadContainer`."""
    return loneobj


class TestPrecachePermissionForObjects(TestCase):
    """Test the precaching of permissions."""

    layer = DatabaseFunctionalLayer

    def test_precaching_permissions(self):
        # The precache_permission_for_objects function updates the security
        # policy cache for the permission specified.
        class Boring(object):
            """A boring, but weakref-able object."""
        objects = [Boring(), Boring()]
        request = LaunchpadTestRequest()
        login(ANONYMOUS, request)
        precache_permission_for_objects(request, 'launchpad.View', objects)
        # Confirm that the objects have the permission set.
        self.assertTrue(check_permission('launchpad.View', objects[0]))
        self.assertTrue(check_permission('launchpad.View', objects[1]))

    def test_default_request(self):
        # If no request is provided, the current interaction is used.
        class Boring(object):
            """A boring, but weakref-able object."""
        obj = Boring()
        request = LaunchpadTestRequest()
        login(ANONYMOUS, request)
        precache_permission_for_objects(None, 'launchpad.View', [obj])
        self.assertTrue(check_permission('launchpad.View', obj))


class TestIterAuthorization(TestCase):
    """Tests for `iter_authorization`.

    In the tests (and their names) below, "normal" refers to a non-delegated
    authorization.
    """

    layer = ZopelessLayer

    def setUp(self):
        super(TestIterAuthorization, self).setUp()
        self.object = Object()
        self.principal = FakeLaunchpadPrincipal()
        self.permission = "docking.Permission"

    def allow(self):
        """Allow authorization for `Object` with `self.permission`."""
        self.useFixture(
            ZopeAdapterFixture(Allow, [Object], name=self.permission))

    def deny(self):
        """Deny authorization for `Object` with `self.permission`."""
        self.useFixture(
            ZopeAdapterFixture(Deny, [Object], name=self.permission))

    def explode(self):
        """Explode if auth for `Object` with `self.permission` is tried."""
        self.useFixture(
            ZopeAdapterFixture(Explode, [Object], name=self.permission))

    def delegate(self):
        # Delegate auth for Object to AnotherObject{One,Two}.
        self.useFixture(
            ZopeAdapterFixture(
                Delegate, [Object], name=self.permission))
        # Allow auth to AnotherObjectOne.
        self.useFixture(
            ZopeAdapterFixture(
                Allow, [AnotherObjectOne], name=Delegate.permission))
        # Deny auth to AnotherObjectTwo.
        self.useFixture(
            ZopeAdapterFixture(
                Deny, [AnotherObjectTwo], name=Delegate.permission))

    #
    # Non-delegated, non-cached checks.
    #

    def test_normal_unauthenticated_no_adapter(self):
        # Authorization is denied when there's no adapter.
        cache = {}
        expected = [False]
        observed = iter_authorization(
            self.object, self.permission, principal=None, cache=cache)
        self.assertEqual(expected, list(observed))
        # The cache is not updated when there's no adapter.
        self.assertEqual({}, cache)

    def test_normal_unauthenticated_allowed(self):
        # The result of the registered IAuthorization adapter is returned.
        self.allow()
        cache = {}
        expected = [True]
        observed = iter_authorization(
            self.object, self.permission, principal=None, cache=cache)
        self.assertEqual(expected, list(observed))
        # The cache is updated with the result.
        self.assertEqual({self.object: {self.permission: True}}, cache)

    def test_normal_unauthenticated_denied(self):
        # The result of the registered IAuthorization adapter is returned.
        self.deny()
        cache = {}
        expected = [False]
        observed = iter_authorization(
            self.object, self.permission, principal=None, cache=cache)
        self.assertEqual(expected, list(observed))
        # The cache is updated with the result.
        self.assertEqual({self.object: {self.permission: False}}, cache)

    def test_normal_authenticated_no_adapter(self):
        # Authorization is denied when there's no adapter.
        cache = {}
        expected = [False]
        observed = iter_authorization(
            self.object, self.permission, self.principal, cache=cache)
        self.assertEqual(expected, list(observed))
        # The cache is not updated when there's no adapter.
        self.assertEqual({}, cache)

    def test_normal_authenticated_allowed(self):
        # The result of the registered IAuthorization adapter is returned.
        self.allow()
        cache = {}
        expected = [True]
        observed = iter_authorization(
            self.object, self.permission, self.principal, cache=cache)
        self.assertEqual(expected, list(observed))
        # The cache is updated with the result.
        self.assertEqual({self.object: {self.permission: True}}, cache)

    def test_normal_authenticated_denied(self):
        # The result of the registered IAuthorization adapter is returned.
        self.deny()
        cache = {}
        expected = [False]
        observed = iter_authorization(
            self.object, self.permission, self.principal, cache=cache)
        self.assertEqual(expected, list(observed))
        # The cache is updated with the result.
        self.assertEqual({self.object: {self.permission: False}}, cache)

    #
    # Non-delegated, cached checks.
    #

    def test_normal_unauthenticated_no_adapter_cached(self):
        # Authorization is taken from the cache even if an adapter is not
        # registered. This situation - the cache holding a result for an
        # object+permission for which there is no IAuthorization adapter -
        # will not arise unless the cache is tampered with, so this test is
        # solely for documentation.
        token = getrandbits(32)
        expected = [token]
        observed = iter_authorization(
            self.object, self.permission, principal=None,
            cache={self.object: {self.permission: token}})
        self.assertEqual(expected, list(observed))

    def test_normal_unauthenticated_cached(self):
        # Authorization is taken from the cache regardless of the presence of
        # an adapter or its behaviour.
        self.explode()
        token = getrandbits(32)
        expected = [token]
        observed = iter_authorization(
            self.object, self.permission, principal=None,
            cache={self.object: {self.permission: token}})
        self.assertEqual(expected, list(observed))

    def test_normal_authenticated_no_adapter_cached(self):
        # Authorization is taken from the cache even if an adapter is not
        # registered. This situation - the cache holding a result for an
        # object+permission for which there is no IAuthorization adapter -
        # will not arise unless the cache is tampered with, so this test is
        # solely for documentation.
        token = getrandbits(32)
        expected = [token]
        observed = iter_authorization(
            self.object, self.permission, self.principal,
            cache={self.object: {self.permission: token}})
        self.assertEqual(expected, list(observed))

    def test_normal_authenticated_cached(self):
        # Authorization is taken from the cache regardless of the presence of
        # an adapter or its behaviour.
        self.explode()
        token = getrandbits(32)
        expected = [token]
        observed = iter_authorization(
            self.object, self.permission, principal=self.principal,
            cache={self.object: {self.permission: token}})
        self.assertEqual(expected, list(observed))

    #
    # Delegated checks.
    #

    def test_delegated_unauthenticated(self):
        # Authorization is delegated and we see the results of authorization
        # against the objects to which it has been delegated.
        self.delegate()
        cache = {}
        expected = [True, False]
        observed = iter_authorization(
            self.object, self.permission, principal=None, cache=cache)
        self.assertEqual(expected, list(observed))
        # The cache is updated with the result of the leaf checks and not the
        # delegated check.
        cache_expected = {
            Delegate.object_one: {Delegate.permission: True},
            Delegate.object_two: {Delegate.permission: False},
            }
        self.assertEqual(cache_expected, cache)

    def test_delegated_authenticated(self):
        # Authorization is delegated and we see the results of authorization
        # against the objects to which it has been delegated.
        self.delegate()
        cache = {}
        expected = [True, False]
        observed = iter_authorization(
            self.object, self.permission, self.principal, cache=cache)
        self.assertEqual(expected, list(observed))
        # The cache is updated with the result of the leaf checks and not the
        # delegated check.
        cache_expected = {
            Delegate.object_one: {Delegate.permission: True},
            Delegate.object_two: {Delegate.permission: False},
            }
        self.assertEqual(cache_expected, cache)


class AvailableWithPermissionObject:
    """ An object used to test available_with_permission."""

    implements(Interface)

    @available_with_permission('launchpad.Edit', 'foo')
    def test_function_foo(self, foo, bar=None):
        pass

    @available_with_permission('launchpad.Edit', 'bar')
    def test_function_bar(self, foo, bar=None):
        pass


class TestAvailableWithPermission(TestCase):
    """Test the available_with_permission decorator."""

    layer = DatabaseFunctionalLayer

    def test_authorized_first_arg(self):
        # Method invocation with context being the first non-kw argument.
        foo = Object()
        request = LaunchpadTestRequest()
        login(ANONYMOUS, request)
        precache_permission_for_objects(request, 'launchpad.Edit', [foo])
        obj_to_invoke = AvailableWithPermissionObject()
        bar = Object()
        obj_to_invoke.test_function_foo(foo, bar)

    def test_authorized_kw_arg(self):
        # Method invocation with context being a kw argument.
        bar = Object()
        request = LaunchpadTestRequest()
        login(ANONYMOUS, request)
        precache_permission_for_objects(request, 'launchpad.Edit', [bar])
        obj_to_invoke = AvailableWithPermissionObject()
        foo = Object()
        obj_to_invoke.test_function_bar(foo=foo, bar=bar)

    def test_unauthorized(self):
        # Unauthorized method invocation.
        foo = Object()
        request = LaunchpadTestRequest()
        login(ANONYMOUS, request)
        obj_to_invoke = AvailableWithPermissionObject()
        self.assertRaises(Unauthorized, obj_to_invoke.test_function_foo, foo)
