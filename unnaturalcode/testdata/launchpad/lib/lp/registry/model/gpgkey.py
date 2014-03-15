# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = ['GPGKey', 'GPGKeySet']

from sqlobject import (
    BoolCol,
    ForeignKey,
    IntCol,
    SQLObjectNotFound,
    StringCol,
    )
from zope.component import getUtility
from zope.interface import implements

from lp.registry.interfaces.gpg import (
    IGPGKey,
    IGPGKeySet,
    )
from lp.services.database.enumcol import EnumCol
from lp.services.database.sqlbase import (
    SQLBase,
    sqlvalues,
    )
from lp.services.gpg.interfaces import (
    GPGKeyAlgorithm,
    IGPGHandler,
    )


class GPGKey(SQLBase):
    implements(IGPGKey)

    _table = 'GPGKey'
    _defaultOrder = ['owner', 'keyid']

    owner = ForeignKey(dbName='owner', foreignKey='Person', notNull=True)

    keyid = StringCol(dbName='keyid', notNull=True)
    fingerprint = StringCol(dbName='fingerprint', notNull=True)

    keysize = IntCol(dbName='keysize', notNull=True)

    algorithm = EnumCol(dbName='algorithm', notNull=True,
                        enum=GPGKeyAlgorithm)

    active = BoolCol(dbName='active', notNull=True)

    can_encrypt = BoolCol(dbName='can_encrypt', notNull=False)

    @property
    def keyserverURL(self):
        return getUtility(
            IGPGHandler).getURLForKeyInServer(self.fingerprint, public=True)

    @property
    def displayname(self):
        return '%s%s/%s' % (self.keysize, self.algorithm.title, self.keyid)


class GPGKeySet:
    implements(IGPGKeySet)

    def new(self, ownerID, keyid, fingerprint, keysize,
            algorithm, active=True, can_encrypt=False):
        """See `IGPGKeySet`"""
        return GPGKey(owner=ownerID, keyid=keyid,
                      fingerprint=fingerprint, keysize=keysize,
                      algorithm=algorithm, active=active,
                      can_encrypt=can_encrypt)

    def activate(self, requester, key, can_encrypt):
        """See `IGPGKeySet`."""
        fingerprint = key.fingerprint
        lp_key = self.getByFingerprint(fingerprint)
        if lp_key:
            # Then the key already exists, so let's reactivate it.
            lp_key.active = True
            lp_key.can_encrypt = can_encrypt
            return lp_key, False
        ownerID = requester.id
        keyid = key.keyid
        keysize = key.keysize
        algorithm = GPGKeyAlgorithm.items[key.algorithm]
        lp_key = self.new(
            ownerID, keyid, fingerprint, keysize, algorithm,
            can_encrypt=can_encrypt)
        return lp_key, True

    def get(self, key_id, default=None):
        """See `IGPGKeySet`"""
        try:
            return GPGKey.get(key_id)
        except SQLObjectNotFound:
            return default

    def getByFingerprint(self, fingerprint, default=None):
        """See `IGPGKeySet`"""
        result = GPGKey.selectOneBy(fingerprint=fingerprint)
        if result is None:
            return default
        return result

    def getGPGKeysForPeople(self, people):
        """See `IGPGKeySet`"""
        return GPGKey.select("""
            GPGKey.owner IN %s AND
            GPGKey.active = True
            """ % sqlvalues([person.id for person in people]))

    def getGPGKeys(self, ownerid=None, active=True):
        """See `IGPGKeySet`"""
        if active is False:
            query = """
                active = false
                AND fingerprint NOT IN
                    (SELECT fingerprint FROM LoginToken
                     WHERE fingerprint IS NOT NULL
                           AND requester = %s
                           AND date_consumed is NULL
                    )
                """ % sqlvalues(ownerid)
        else:
            query = 'active=true'

        if ownerid:
            query += ' AND owner=%s' % sqlvalues(ownerid)

        return GPGKey.select(query, orderBy='id')

