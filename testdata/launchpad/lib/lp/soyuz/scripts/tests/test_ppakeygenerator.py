# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""`PPAKeyGenerator` script class tests."""

__metaclass__ = type

from zope.component import getUtility

from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.interfaces.gpg import IGPGKeySet
from lp.registry.interfaces.person import IPersonSet
from lp.services.scripts.base import LaunchpadScriptFailure
from lp.soyuz.interfaces.archive import IArchiveSet
from lp.soyuz.scripts.ppakeygenerator import PPAKeyGenerator
from lp.testing import TestCase
from lp.testing.faketransaction import FakeTransaction
from lp.testing.layers import LaunchpadZopelessLayer


class TestPPAKeyGenerator(TestCase):
    layer = LaunchpadZopelessLayer

    def _fixArchiveForKeyGeneration(self, archive):
        """Override the given archive distribution to 'ubuntutest'.

        This is necessary because 'ubuntutest' is the only distribution in
        the sampledata that contains a usable publishing configuration.
        """
        ubuntutest = getUtility(IDistributionSet).getByName('ubuntutest')
        archive.distribution = ubuntutest

    def _getKeyGenerator(self, ppa_owner_name=None, txn=None):
        """Return a `PPAKeyGenerator` instance.

        Monkey-patch the script object with a fake transaction manager
        and also make it use an alternative (fake and lighter) procedure
        to generate keys for each PPA.
        """
        test_args = []

        if ppa_owner_name is not None:
            test_args.extend(['-p', ppa_owner_name])

        key_generator = PPAKeyGenerator(
            name='ppa-generate-keys', test_args=test_args)

        if txn is None:
            txn = FakeTransaction()
        key_generator.txn = txn

        def fake_key_generation(archive):
            a_key = getUtility(IGPGKeySet).get(1)
            archive.signing_key = a_key

        key_generator.generateKey = fake_key_generation

        return key_generator

    def testPersonNotFound(self):
        """Raises an error if the specified person does not exist."""
        key_generator = self._getKeyGenerator(ppa_owner_name='biscuit')
        self.assertRaisesWithContent(
            LaunchpadScriptFailure,
            "No person named 'biscuit' could be found.",
            key_generator.main)

    def testPersonHasNoPPA(self):
        """Raises an error if the specified person does not have a PPA. """
        key_generator = self._getKeyGenerator(ppa_owner_name='name16')
        self.assertRaisesWithContent(
            LaunchpadScriptFailure,
            "Person named 'name16' has no PPA.",
            key_generator.main)

    def testPPAAlreadyHasSigningKey(self):
        """Raises an error if the specified PPA already has a signing_key."""
        cprov = getUtility(IPersonSet).getByName('cprov')
        a_key = getUtility(IGPGKeySet).get(1)
        cprov.archive.signing_key = a_key

        key_generator = self._getKeyGenerator(ppa_owner_name='cprov')
        self.assertRaisesWithContent(
            LaunchpadScriptFailure,
            ("PPA for Celso Providelo already has a signing_key (%s)" %
             cprov.archive.signing_key.fingerprint),
            key_generator.main)

    def testGenerateKeyForASinglePPA(self):
        """Signing key generation for a single PPA.

        The 'signing_key' for the specified PPA is generated and
        the transaction is committed once.
        """
        cprov = getUtility(IPersonSet).getByName('cprov')
        self._fixArchiveForKeyGeneration(cprov.archive)

        self.assertTrue(cprov.archive.signing_key is None)

        txn = FakeTransaction()
        key_generator = self._getKeyGenerator(ppa_owner_name='cprov', txn=txn)
        key_generator.main()

        self.assertTrue(cprov.archive.signing_key is not None)
        self.assertEquals(txn.commit_count, 1)

    def testGenerateKeyForAllPPA(self):
        """Signing key generation for all PPAs.

        The 'signing_key' for all 'pending-signing-key' PPAs are generated
        and the transaction is committed once for each PPA.
        """
        archives = list(getUtility(IArchiveSet).getPPAsPendingSigningKey())

        for archive in archives:
            self._fixArchiveForKeyGeneration(archive)
            self.assertTrue(archive.signing_key is None)

        txn = FakeTransaction()
        key_generator = self._getKeyGenerator(txn=txn)
        key_generator.main()

        for archive in archives:
            self.assertTrue(archive.signing_key is not None)

        self.assertEquals(txn.commit_count, len(archives))
