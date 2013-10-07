# Copyright 2011-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test publisher configs handling.

Publisher configuration provides archive-dependent filesystem paths.
"""

__metaclass__ = type

from zope.component import getUtility

from lp.archivepublisher.config import getPubConfig
from lp.registry.interfaces.distribution import IDistributionSet
from lp.services.config import config
from lp.soyuz.enums import ArchivePurpose
from lp.soyuz.interfaces.archive import IArchiveSet
from lp.testing import TestCaseWithFactory
from lp.testing.layers import ZopelessDatabaseLayer


class TestGetPubConfig(TestCaseWithFactory):

    layer = ZopelessDatabaseLayer

    def setUp(self):
        super(TestGetPubConfig, self).setUp()
        self.ubuntutest = getUtility(IDistributionSet)['ubuntutest']
        self.root = "/var/tmp/archive"

    def test_getPubConfig_returns_None_if_no_publisherconfig_found(self):
        archive = self.factory.makeDistribution(no_pubconf=True).main_archive
        self.assertEqual(None, getPubConfig(archive))

    def test_primary_config(self):
        # Primary archive configuration is correct.
        primary_config = getPubConfig(self.ubuntutest.main_archive)
        self.assertEqual(self.root, primary_config.distroroot)
        archiveroot = self.root + "/ubuntutest"
        self.assertEqual(archiveroot, primary_config.archiveroot)
        self.assertEqual(archiveroot + "/pool", primary_config.poolroot)
        self.assertEqual(archiveroot + "/dists", primary_config.distsroot)
        self.assertEqual(
            archiveroot + "-overrides", primary_config.overrideroot)
        self.assertEqual(archiveroot + "-cache", primary_config.cacheroot)
        self.assertEqual(archiveroot + "-misc", primary_config.miscroot)
        self.assertEqual(
            archiveroot + "-germinate", primary_config.germinateroot)
        self.assertEqual(
            self.root + "/ubuntutest-temp", primary_config.temproot)
        self.assertEqual(archiveroot + "-uefi", primary_config.uefiroot)

    def test_partner_config(self):
        # Partner archive configuration is correct.
        # The publisher config for PARTNER contains only 'partner' in its
        # components.  This prevents non-partner being published in the
        # partner archive.
        partner_archive = getUtility(IArchiveSet).getByDistroAndName(
            self.ubuntutest, "partner")
        partner_config = getPubConfig(partner_archive)
        self.root = "/var/tmp/archive"
        self.assertEqual(self.root, partner_config.distroroot)
        archiveroot = self.root + "/ubuntutest-partner"
        self.assertEqual(archiveroot, partner_config.archiveroot)
        self.assertEqual(archiveroot + "/pool", partner_config.poolroot)
        self.assertEqual(archiveroot + "/dists", partner_config.distsroot)
        self.assertIsNone(partner_config.overrideroot)
        self.assertIsNone(partner_config.cacheroot)
        self.assertIsNone(partner_config.miscroot)
        self.assertIsNone(partner_config.germinateroot)
        self.assertEqual(
            self.root + "/ubuntutest-temp", partner_config.temproot)
        self.assertEqual(archiveroot + "-uefi", partner_config.uefiroot)

    def test_copy_config(self):
        # In the case of copy archives (used for rebuild testing) the
        # archiveroot is of the form
        # DISTROROOT/DISTRONAME-ARCHIVENAME/DISTRONAME.
        copy_archive = getUtility(IArchiveSet).new(
            purpose=ArchivePurpose.COPY, owner=self.ubuntutest.owner,
            distribution=self.ubuntutest, name="rebuildtest99")
        copy_config = getPubConfig(copy_archive)
        self.assertEqual(self.root, copy_config.distroroot)
        archiveroot = self.root + "/ubuntutest-rebuildtest99/ubuntutest"
        self.assertEqual(archiveroot, copy_config.archiveroot)
        self.assertEqual(archiveroot + "/pool", copy_config.poolroot)
        self.assertEqual(archiveroot + "/dists", copy_config.distsroot)
        self.assertEqual(
            archiveroot + "-overrides", copy_config.overrideroot)
        self.assertEqual(archiveroot + "-cache", copy_config.cacheroot)
        self.assertEqual(archiveroot + "-misc", copy_config.miscroot)
        self.assertEqual(
            archiveroot + "-germinate", copy_config.germinateroot)
        self.assertEqual(archiveroot + "-temp", copy_config.temproot)
        self.assertIsNone(copy_config.uefiroot)


class TestGetPubConfigPPA(TestCaseWithFactory):

    layer = ZopelessDatabaseLayer

    def setUp(self):
        super(TestGetPubConfigPPA, self).setUp()
        self.ubuntutest = getUtility(IDistributionSet)['ubuntutest']
        self.ppa = self.factory.makeArchive(
            distribution=self.ubuntutest, purpose=ArchivePurpose.PPA)
        self.ppa_config = getPubConfig(self.ppa)

    def test_ppa_root_matches_config(self):
        # The base publication location is set by Launchpad configuration.
        self.assertEqual(
            config.personalpackagearchive.root, self.ppa_config.distroroot)

    def test_ppa_config(self):
        # PPA configuration matches the PPA repository topology:
        #   <PPA_BASE_DIR>/<PERSONNAME>/<DISTRIBUTION>
        # Some paths are not used in the PPA workflow, so they are set to
        # None in order that they won't get created.
        self.assertEqual("/var/tmp/ppa.test/", self.ppa_config.distroroot)
        archiveroot = "%s%s/%s/ubuntutest" % (
            self.ppa_config.distroroot, self.ppa.owner.name, self.ppa.name)
        self.assertEqual(archiveroot, self.ppa_config.archiveroot)
        self.assertEqual(archiveroot + "/pool", self.ppa_config.poolroot)
        self.assertEqual(archiveroot + "/dists", self.ppa_config.distsroot)
        self.assertIsNone(self.ppa_config.overrideroot)
        self.assertIsNone(self.ppa_config.cacheroot)
        self.assertIsNone(self.ppa_config.miscroot)
        self.assertIsNone(self.ppa_config.germinateroot)
        self.assertEqual(
            "/var/tmp/archive/ubuntutest-temp", self.ppa_config.temproot)
        uefiroot = "/var/tmp/ppa-signing-keys.test/uefi/%s/%s" % (
            self.ppa.owner.name, self.ppa.name)
        self.assertEqual(uefiroot, self.ppa_config.uefiroot)

    def test_private_ppa_separate_root(self):
        # Private PPAs are published to a different location.
        self.assertNotEqual(
            config.personalpackagearchive.private_root,
            config.personalpackagearchive.root)

    def test_private_ppa_config(self):
        # Private PPA configuration uses the separate base location.
        p3a = self.factory.makeArchive(
            owner=self.ppa.owner, name="myprivateppa",
            distribution=self.ubuntutest, purpose=ArchivePurpose.PPA)
        p3a.private = True
        p3a.buildd_secret = "secret"
        p3a_config = getPubConfig(p3a)
        self.assertEqual(
            config.personalpackagearchive.private_root, p3a_config.distroroot)
        archiveroot = "%s/%s/%s/ubuntutest" % (
            p3a_config.distroroot, p3a.owner.name, p3a.name)
        self.assertEqual(archiveroot, p3a_config.archiveroot)
        self.assertEqual(archiveroot + "/pool", p3a_config.poolroot)
        self.assertEqual(archiveroot + "/dists", p3a_config.distsroot)
        self.assertIsNone(p3a_config.overrideroot)
        self.assertIsNone(p3a_config.cacheroot)
        self.assertIsNone(p3a_config.miscroot)
        self.assertIsNone(p3a_config.germinateroot)
        self.assertEqual(
            "/var/tmp/archive/ubuntutest-temp", p3a_config.temproot)
        # It's OK for the signing keys to be in the same location as for
        # public PPAs, as the owner/name namespace is shared.
        uefiroot = "/var/tmp/ppa-signing-keys.test/uefi/%s/%s" % (
            p3a.owner.name, p3a.name)
        self.assertEqual(uefiroot, p3a_config.uefiroot)
