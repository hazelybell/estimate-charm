# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Base class to implement the Launchpad security policy."""

__metaclass__ = type

__all__ = [
    'AnonymousAuthorization',
    'AuthorizationBase',
    'DelegatedAuthorization',
    ]

from itertools import (
    izip,
    repeat,
    )

from zope.component import queryAdapter
from zope.interface import implements
from zope.security.permission import checkPermission

from lp.app.interfaces.security import IAuthorization


class AuthorizationBase:
    implements(IAuthorization)
    permission = None
    usedfor = None

    def __init__(self, obj):
        self.obj = obj

    def checkUnauthenticated(self):
        """See `IAuthorization.checkUnauthenticated`.

        :return: True or False.
        """
        return False

    def checkAuthenticated(self, user):
        """Return True if the given person has the given permission.

        This method is implemented by security adapters that have not
        been updated to work in terms of IAccount.

        :return: True or False.
        """
        return False

    def checkPermissionIsRegistered(self, obj, permission):
        """Pass through to checkPermission.

        To be replaced during testing.
        """
        return checkPermission(obj, permission)

    def _checkAndFetchNext(self, obj, permission):
        assert obj is not None or permission is not None, (
            "Please specify either an object or permission to forward to.")
        if obj is None:
            obj = self.obj
        if permission is None:
            permission = self.permission
        # This will raise ValueError if the permission doesn't exist.
        self.checkPermissionIsRegistered(obj, permission)
        return queryAdapter(obj, IAuthorization, permission)

    def forwardCheckAuthenticated(self, user,
                                  obj=None, permission=None):
        """Forward request to another security adapter.

        Find a matching adapter and call checkAuthenticated on it. Intended
        to be used in checkAuthenticated.

        :param user: The IRolesPerson object that was passed in.
        :param obj: The object to check the permission for. If None, use
            the same object as this adapter.
        :param permission: The permission to check. If None, use the same
            permission as this adapter.
        :return: True or False.
        """
        next_adapter = self._checkAndFetchNext(obj, permission)
        if next_adapter is None:
            return False
        else:
            return next_adapter.checkAuthenticated(user)

    def forwardCheckUnauthenticated(self, obj=None, permission=None):
        """Forward request to another security adapter.

        Find a matching adapter and call checkUnauthenticated on it. Intended
        to be used in checkUnauthenticated.

        :param user: The IRolesPerson object that was passed in.
        :param obj: The object to check the permission for. If None, use
            the same object as this adapter.
        :param permission: The permission to check. If None, use the same
            permission as this adapter.
        :return: True or False.
        """
        next_adapter = self._checkAndFetchNext(obj, permission)
        if next_adapter is None:
            return False
        else:
            return next_adapter.checkUnauthenticated()


class AnonymousAuthorization(AuthorizationBase):
    """Allow any authenticated and unauthenticated user access."""
    permission = 'launchpad.View'

    def checkUnauthenticated(self):
        """Any unauthorized user can see this object."""
        return True

    def checkAuthenticated(self, user):
        """Any authorized user can see this object."""
        return True


class DelegatedAuthorization(AuthorizationBase):

    def __init__(self, obj, forwarded_object=None, permission=None):
        super(DelegatedAuthorization, self).__init__(obj)
        self.forwarded_object = forwarded_object
        if permission is not None:
            self.permission = permission

    def iter_objects(self):
        """Iterator of objects used for authentication checking.

        If an object is provided when the class is instantiated, it will be
        used.  Otherwise this method must be overridden to provide the objects
        to be used.
        """
        if self.forwarded_object is None:
            raise ValueError(
                "Either set forwarded_object or override iter_objects.")
        yield self.forwarded_object

    def checkAuthenticated(self, user):
        """See `IAuthorization`."""
        return izip(self.iter_objects(), repeat(self.permission))

    def checkUnauthenticated(self):
        """See `IAuthorization`."""
        return izip(self.iter_objects(), repeat(self.permission))
