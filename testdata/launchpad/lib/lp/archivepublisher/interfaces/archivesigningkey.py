# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""ArchiveSigningKey interface."""

__metaclass__ = type

__all__ = [
    'IArchiveSigningKey',
    ]

from zope.interface import Interface
from zope.schema import Object

from lp import _
from lp.soyuz.interfaces.archive import IArchive


class IArchiveSigningKey(Interface):
    """`ArchiveSigningKey` interface.

    `IArchive` adapter for operations using its 'signing_key'.

    Note that this adapter only works on zopeless mode for generating
    new signing keys.
    """

    archive = Object(
        title=_('Corresponding IArchive'), required=True, schema=IArchive)

    def getPathForSecretKey(key):
        """Return the absolute path to access a secret key export.

        Disk location specified in the configurarion, for storing a
        secret key, e.g.:

        /<ppa.signing_keys_root>/<FINGERPRINT>.gpg

        :param key: a secret `PymeKey` object to be exported.
        :return: path to the key export.
        """

    def exportSecretKey(key):
        """Export the given secret key into a private location.

        Place a ASCII armored export of the given secret key in the
        location specified by `getPathForSecretKey`.

        :param key: a secret `PymeKey` object to be exported.
        :raises AssertionError: if the given key is public.
        """

    def generateSigningKey():
        """Generate a new GPG secret/public key pair.

        For named-ppas, the existing signing-key for the default PPA
        owner by the same user/team is reused. The *trust* belongs to
        the archive maintainer (owner) not the archive itself.

        Default ppas get brand new keys via the following procedure.

         * Export the secret key in the configuration disk location;
         * Upload the public key to the configuration keyserver;
         * Store a reference for the public key in GPGKey table, which
           is set as the context archive 'signing_key'.

        :raises AssertionError: if the context archive already has a
            `signing_key`.
        :raises GPGUploadFailure: if the just-generated key could not be
            upload to the keyserver.
        """

    def setSigningKey(key_path):
        """Set a given secret key export as the context archive signing key.

        :raises AssertionError: if the context archive already has a
            `signing_key`.
        :raises AssertionError: if the given 'key_path' does not exist.
        """

    def signRepository(suite):
        """Sign the corresponding repository.

        :param suite: suite name to be signed.
        :raises AssertionError: if the context archive has no `signing_key`
            or there is no Release file in the given suite.
        """


