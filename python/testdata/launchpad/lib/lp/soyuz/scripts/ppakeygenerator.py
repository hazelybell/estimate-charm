# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__all__ = [
    'PPAKeyGenerator',
    ]

from zope.component import getUtility

from lp.archivepublisher.interfaces.archivesigningkey import (
    IArchiveSigningKey,
    )
from lp.registry.interfaces.person import IPersonSet
from lp.services.scripts.base import (
    LaunchpadCronScript,
    LaunchpadScriptFailure,
    )
from lp.soyuz.interfaces.archive import IArchiveSet


class PPAKeyGenerator(LaunchpadCronScript):

    usage = '%prog [-p PPA owner]'
    description = 'Generate a GPG signing key for PPAs.'

    def add_my_options(self):
        self.parser.add_option(
            "-p", "--ppa", dest="archive_owner_name",
            help="Name of the PPA owner to create the key.")

    def generateKey(self, archive):
        """Generate a signing key for the given archive."""
        self.logger.info(
            "Generating signing key for %s" % archive.displayname)
        archive_signing_key = IArchiveSigningKey(archive)
        archive_signing_key.generateSigningKey()
        self.logger.info("Key %s" % archive.signing_key.fingerprint)

    def main(self):
        """Generate signing keys for the selected PPAs."""
        owner_name = self.options.archive_owner_name

        if owner_name is not None:
            owner = getUtility(IPersonSet).getByName(owner_name)
            if owner is None:
                raise LaunchpadScriptFailure(
                    "No person named '%s' could be found." % owner_name)
            if owner.archive is None:
                raise LaunchpadScriptFailure(
                    "Person named '%s' has no PPA." % owner_name)
            if owner.archive.signing_key is not None:
                raise LaunchpadScriptFailure(
                    "%s already has a signing_key (%s)"
                    % (owner.archive.displayname,
                       owner.archive.signing_key.fingerprint))
            archives = [owner.archive]
        else:
            archive_set = getUtility(IArchiveSet)
            archives = list(archive_set.getPPAsPendingSigningKey())

        for archive in archives:
            self.generateKey(archive)
            self.txn.commit()
