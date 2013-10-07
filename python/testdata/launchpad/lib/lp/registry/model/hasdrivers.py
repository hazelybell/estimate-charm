# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Common implementations for IHasDrivers."""

__metaclass__ = type

__all__ = [
    'HasDriversMixin',
    ]

from lp.registry.interfaces.role import IPersonRoles


class HasDriversMixin:

    def personHasDriverRights(self, person):
        """See `IHasDrivers`."""
        person_roles = IPersonRoles(person)
        return (person_roles.isOneOfDrivers(self) or
                person_roles.isOwner(self) or
                person_roles.in_admin)
