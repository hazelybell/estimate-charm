# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""OpenPGP key interfaces."""

__metaclass__ = type

__all__ = [
    'IGPGKey',
    'IGPGKeySet',
    ]


from lazr.restful.declarations import (
    export_as_webservice_entry,
    exported,
    )
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Bool,
    Choice,
    Int,
    TextLine,
    )

from lp import _
from lp.registry.interfaces.role import IHasOwner
from lp.services.gpg.interfaces import (
    valid_fingerprint,
    valid_keyid,
    )


class IGPGKey(IHasOwner):
    """OpenPGP support"""

    export_as_webservice_entry('gpg_key')

    id = Int(title=_("Database id"), required=True, readonly=True)
    keysize = Int(title=_("Keysize"), required=True)
    algorithm = Choice(title=_("Algorithm"), required=True,
            vocabulary='GpgAlgorithm')
    keyid = exported(
        TextLine(title=_("OpenPGP key ID"), required=True,
                 constraint=valid_keyid, readonly=True))
    fingerprint = exported(
        TextLine(title=_("User Fingerprint"), required=True,
                 constraint=valid_fingerprint, readonly=True))
    active = Bool(title=_("Active"), required=True)
    displayname = Attribute("Key Display Name")
    keyserverURL = Attribute(
        "The URL to retrieve this key from the keyserver.")
    can_encrypt = Bool(title=_("Key can be used for encryption"),
                       required=True)
    owner = Int(title=_('Person'), required=True, readonly=True)
    ownerID = Int(title=_('Owner ID'), required=True, readonly=True)


class IGPGKeySet(Interface):
    """The set of GPGKeys."""

    def new(ownerID, keyid, fingerprint, keysize,
            algorithm, active=True, can_encrypt=True):
        """Create a new GPGKey pointing to the given Person."""

    def activate(requester, key, can_encrypt):
        """Activate 'key' for 'requester'.

        :return: A tuple of (IGPGKey, new), where 'new' is False if we have
            reactivated an existing key.
        """

    def get(key_id, default=None):
        """Return the GPGKey object for the given id.

        Return the given default if there's no object with the given id.
        """

    def getByFingerprint(fingerprint, default=None):
        """Return UNIQUE result for a given Key fingerprint including
        inactive ones.
        """

    def getGPGKeys(ownerid=None, active=True):
        """Return OpenPGP keys ordered by id.

        Optionally for a given owner and or a given status.
        """

    def getGPGKeysForPeople(people):
        """Return OpenPGP keys for a set of people."""
