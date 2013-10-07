# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Classes for managing the NameBlacklist table."""

__metaclass__ = type
__all__ = [
    'NameBlacklist',
    'NameBlacklistSet',
    ]


from storm.locals import (
    Int,
    Reference,
    Unicode,
    )
from zope.interface import implements

from lp.registry.interfaces.nameblacklist import (
    INameBlacklist,
    INameBlacklistSet,
    )
from lp.registry.model.person import Person
from lp.services.database.interfaces import IStore
from lp.services.database.stormbase import StormBase


class NameBlacklist(StormBase):
    """Class for the NameBlacklist table."""

    implements(INameBlacklist)

    __storm_table__ = 'NameBlacklist'

    id = Int(primary=True)
    regexp = Unicode(name='regexp', allow_none=False)
    comment = Unicode(name='comment', allow_none=True)
    admin_id = Int(name='admin', allow_none=True)
    admin = Reference(admin_id, Person.id)


class NameBlacklistSet:
    """Class for creating and retrieving NameBlacklist objects."""

    implements(INameBlacklistSet)

    def getAll(self):
        """See `INameBlacklistSet`."""
        store = IStore(NameBlacklist)
        return store.find(NameBlacklist).order_by(NameBlacklist.regexp)

    def create(self, regexp, comment=None, admin=None):
        """See `INameBlacklistSet`."""
        nameblacklist = NameBlacklist()
        nameblacklist.regexp = regexp
        nameblacklist.comment = comment
        nameblacklist.admin = admin
        store = IStore(NameBlacklist)
        store.add(nameblacklist)
        return nameblacklist

    def get(self, id):
        """See `INameBlacklistSet`."""
        try:
            id = int(id)
        except ValueError:
            return None
        store = IStore(NameBlacklist)
        return store.find(NameBlacklist, NameBlacklist.id == id).one()

    def getByRegExp(self, regexp):
        """See `INameBlacklistSet`."""
        store = IStore(NameBlacklist)
        return store.find(NameBlacklist, NameBlacklist.regexp == regexp).one()
