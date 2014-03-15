# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""ArchiveSigningKey implementation."""

__metaclass__ = type

__all__ = [
    'ArchiveSigningKey',
    ]


import os

import gpgme
from zope.component import getUtility
from zope.interface import implements

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.archivepublisher.config import getPubConfig
from lp.archivepublisher.interfaces.archivesigningkey import (
    IArchiveSigningKey,
    )
from lp.registry.interfaces.gpg import IGPGKeySet
from lp.services.config import config
from lp.services.gpg.interfaces import (
    GPGKeyAlgorithm,
    IGPGHandler,
    )


class ArchiveSigningKey:
    """`IArchive` adapter for manipulating its GPG key."""

    implements(IArchiveSigningKey)

    def __init__(self, archive):
        self.archive = archive

    @property
    def _archive_root_path(self):
        return getPubConfig(self.archive).archiveroot

    def getPathForSecretKey(self, key):
        """See `IArchiveSigningKey`."""
        return os.path.join(
            config.personalpackagearchive.signing_keys_root,
            "%s.gpg" % key.fingerprint)

    def exportSecretKey(self, key):
        """See `IArchiveSigningKey`."""
        assert key.secret, "Only secret keys should be exported."
        export_path = self.getPathForSecretKey(key)

        if not os.path.exists(os.path.dirname(export_path)):
            os.makedirs(os.path.dirname(export_path))

        export_file = open(export_path, 'w')
        export_file.write(key.export())
        export_file.close()

    def generateSigningKey(self):
        """See `IArchiveSigningKey`."""
        assert self.archive.signing_key is None, (
            "Cannot override signing_keys.")

        # Always generate signing keys for the default PPA, even if it
        # was not expecifically requested. The default PPA signing key
        # is then propagated to the context named-ppa.
        default_ppa = self.archive.owner.archive
        if self.archive != default_ppa:
            if default_ppa.signing_key is None:
                IArchiveSigningKey(default_ppa).generateSigningKey()
            self.archive.signing_key = default_ppa.signing_key
            return

        key_displayname = (
            "Launchpad PPA for %s" % self.archive.owner.displayname)
        secret_key = getUtility(IGPGHandler).generateKey(key_displayname)
        self._setupSigningKey(secret_key)

    def setSigningKey(self, key_path):
        """See `IArchiveSigningKey`."""
        assert self.archive.signing_key is None, (
            "Cannot override signing_keys.")
        assert os.path.exists(key_path), (
            "%s does not exist" % key_path)

        secret_key = getUtility(IGPGHandler).importSecretKey(
            open(key_path).read())
        self._setupSigningKey(secret_key)

    def _setupSigningKey(self, secret_key):
        """Mandatory setup for signing keys.

        * Export the secret key into the protected disk location.
        * Upload public key to the keyserver.
        * Store the public GPGKey reference in the database and update
          the context archive.signing_key.
        """
        self.exportSecretKey(secret_key)

        gpghandler = getUtility(IGPGHandler)
        pub_key = gpghandler.retrieveKey(secret_key.fingerprint)
        gpghandler.uploadPublicKey(pub_key.fingerprint)

        algorithm = GPGKeyAlgorithm.items[pub_key.algorithm]
        key_owner = getUtility(ILaunchpadCelebrities).ppa_key_guard
        self.archive.signing_key = getUtility(IGPGKeySet).new(
            key_owner, pub_key.keyid, pub_key.fingerprint, pub_key.keysize,
            algorithm, active=True, can_encrypt=pub_key.can_encrypt)

    def signRepository(self, suite):
        """See `IArchiveSigningKey`."""
        assert self.archive.signing_key is not None, (
            "No signing key available for %s" % self.archive.displayname)

        suite_path = os.path.join(self._archive_root_path, 'dists', suite)
        release_file_path = os.path.join(suite_path, 'Release')
        assert os.path.exists(release_file_path), (
            "Release file doesn't exist in the repository: %s"
            % release_file_path)

        secret_key_export = open(
            self.getPathForSecretKey(self.archive.signing_key)).read()

        gpghandler = getUtility(IGPGHandler)
        secret_key = gpghandler.importSecretKey(secret_key_export)

        release_file_content = open(release_file_path).read()
        signature = gpghandler.signContent(
            release_file_content, secret_key.fingerprint,
            mode=gpgme.SIG_MODE_DETACH)

        release_signature_file = open(
            os.path.join(suite_path, 'Release.gpg'), 'w')
        release_signature_file.write(signature)
        release_signature_file.close()
