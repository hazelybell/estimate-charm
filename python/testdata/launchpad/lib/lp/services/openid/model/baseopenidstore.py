# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""OpenIDStore implementation for the SSO server's OpenID provider."""

__metaclass__ = type
__all__ = [
    'BaseStormOpenIDStore',
    'BaseStormOpenIDAssociation',
    'BaseStormOpenIDNonce',
    ]

from operator import attrgetter
import time

from openid.association import Association
from openid.store import nonce
from openid.store.interface import OpenIDStore
from storm.properties import (
    Int,
    RawStr,
    Unicode,
    )

from lp.services.database.interfaces import IMasterStore


class BaseStormOpenIDAssociation:
    """Database representation of a stored OpenID association."""

    __storm_primary__ = ('server_url', 'handle')

    server_url = Unicode()
    handle = Unicode()
    secret = RawStr()
    issued = Int()
    lifetime = Int()
    assoc_type = Unicode()

    def __init__(self, server_url, association):
        super(BaseStormOpenIDAssociation, self).__init__()
        self.server_url = server_url.decode('UTF-8')
        self.handle = association.handle.decode('ASCII')
        self.update(association)

    def update(self, association):
        assert self.handle == association.handle.decode('ASCII'), (
            "Association handle does not match (expected %r, got %r" %
            (self.handle, association.handle))
        self.secret = association.secret
        self.issued = association.issued
        self.lifetime = association.lifetime
        self.assoc_type = association.assoc_type.decode('ASCII')

    def as_association(self):
        """Return an equivalent openid-python `Association` object."""
        return Association(
            self.handle.encode('ASCII'), self.secret, self.issued,
            self.lifetime, self.assoc_type.encode('ASCII'))


class BaseStormOpenIDNonce:
    """Database representation of a stored OpenID nonce."""
    __storm_primary__ = ('server_url', 'timestamp', 'salt')

    server_url = Unicode()
    timestamp = Int()
    salt = Unicode()

    def __init__(self, server_url, timestamp, salt):
        super(BaseStormOpenIDNonce, self).__init__()
        self.server_url = server_url
        self.timestamp = timestamp
        self.salt = salt


class BaseStormOpenIDStore(OpenIDStore):
    """An association store for the OpenID Provider."""

    OpenIDAssociation = BaseStormOpenIDAssociation
    OpenIDNonce = BaseStormOpenIDNonce

    def storeAssociation(self, server_url, association):
        """See `OpenIDStore`."""
        store = IMasterStore(self.Association)
        db_assoc = store.get(
            self.Association, (server_url.decode('UTF-8'),
                               association.handle.decode('ASCII')))
        if db_assoc is None:
            db_assoc = self.Association(server_url, association)
            store.add(db_assoc)
        else:
            db_assoc.update(association)

    def getAssociation(self, server_url, handle=None):
        """See `OpenIDStore`."""
        store = IMasterStore(self.Association)
        server_url = server_url.decode('UTF-8')
        if handle is None:
            result = store.find(self.Association, server_url=server_url)
        else:
            handle = handle.decode('ASCII')
            result = store.find(
                self.Association, server_url=server_url, handle=handle)

        db_associations = list(result)
        associations = []
        for db_assoc in db_associations:
            assoc = db_assoc.as_association()
            if assoc.getExpiresIn() == 0:
                store.remove(db_assoc)
            else:
                associations.append(assoc)

        if len(associations) == 0:
            return None
        associations.sort(key=attrgetter('issued'))
        return associations[-1]

    def removeAssociation(self, server_url, handle):
        """See `OpenIDStore`."""
        store = IMasterStore(self.Association)
        assoc = store.get(self.Association, (
                server_url.decode('UTF-8'), handle.decode('ASCII')))
        if assoc is None:
            return False
        store.remove(assoc)
        return True

    def useNonce(self, server_url, timestamp, salt):
        """See `OpenIDStore`."""
        # If the nonce is too far from the present time, it is not valid.
        if abs(timestamp - time.time()) > nonce.SKEW:
            return False

        server_url = server_url.decode('UTF-8')
        salt = salt.decode('ASCII')

        store = IMasterStore(self.Nonce)
        old_nonce = store.get(self.Nonce, (server_url, timestamp, salt))
        if old_nonce is not None:
            # The nonce has already been seen, so reject it.
            return False
        # Record the nonce so it can't be used again.
        store.add(self.Nonce(server_url, timestamp, salt))
        return True

    def cleanupAssociations(self):
        """See `OpenIDStore`."""
        store = IMasterStore(self.Association)
        now = int(time.time())
        expired = store.find(
            self.Association,
            self.Association.issued + self.Association.lifetime < now)
        count = expired.count()
        if count > 0:
            expired.remove()
        return count
