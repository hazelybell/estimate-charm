# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the expire-archive-files.py script. """

from datetime import (
    datetime,
    timedelta,
    )

import pytz
from zope.component import getUtility

from lp.registry.interfaces.distribution import IDistributionSet
from lp.services.config import config
from lp.services.log.logger import BufferLogger
from lp.soyuz.enums import ArchivePurpose
from lp.soyuz.scripts.expire_archive_files import ArchiveExpirer
from lp.soyuz.tests.test_publishing import SoyuzTestPublisher
from lp.testing import TestCaseWithFactory
from lp.testing.dbuser import switch_dbuser
from lp.testing.layers import LaunchpadZopelessLayer


class ArchiveExpiryTestBase(TestCaseWithFactory):
    """base class for the expire-archive-files.py script tests."""
    layer = LaunchpadZopelessLayer
    dbuser = config.binaryfile_expire.dbuser

    def setUp(self):
        """Set up some test publications."""
        super(ArchiveExpiryTestBase, self).setUp()
        # Configure the test publisher.
        switch_dbuser("launchpad")
        self.stp = SoyuzTestPublisher()
        self.stp.prepareBreezyAutotest()

        # Prepare some date properties for the tests to use.
        self.now = datetime.now(pytz.UTC)
        self.under_threshold_date = self.now - timedelta(days=29)
        self.over_threshold_date = self.now - timedelta(days=31)

    def getScript(self, test_args=None):
        """Return a ArchiveExpirer instance."""
        if test_args is None:
            test_args = []
        test_args.extend(['--expire-after', '30'])
        script = ArchiveExpirer("test expirer", test_args=test_args)
        script.logger = BufferLogger()
        script.txn = self.layer.txn
        return script

    def runScript(self):
        """Run the expiry script and return."""
        script = self.getScript()
        switch_dbuser(self.dbuser)
        script.main()

    def _setUpExpirablePublications(self, archive=None):
        """Helper to set up two publications that are both expirable."""
        if archive is None:
            archive = self.archive
        pkg5 = self.stp.getPubSource(
            sourcename="pkg5", architecturehintlist="i386", archive=archive,
            dateremoved=self.over_threshold_date)
        other_source = pkg5.copyTo(
            pkg5.distroseries, pkg5.pocket, self.archive2)
        other_source.dateremoved = self.over_threshold_date
        [pub] = self.stp.getPubBinaries(
            pub_source=pkg5, dateremoved=self.over_threshold_date,
            archive=archive)
        [other_binary] = pub.copyTo(
            pub.distroarchseries.distroseries, pub.pocket, self.archive2)
        other_binary.dateremoved = self.over_threshold_date
        return pkg5, pub

    def assertBinaryExpired(self, publication):
        self.assertNotEqual(
            publication.binarypackagerelease.files[0].libraryfile.expires,
            None,
            "lfa.expires should be set, but it's not.")

    def assertBinaryNotExpired(self, publication):
        self.assertEqual(
            publication.binarypackagerelease.files[0].libraryfile.expires,
            None,
            "lfa.expires should be None, but it's not.")

    def assertSourceExpired(self, publication):
        self.assertNotEqual(
            publication.sourcepackagerelease.files[0].libraryfile.expires,
            None,
            "lfa.expires should be set, but it's not.")

    def assertSourceNotExpired(self, publication):
        self.assertEqual(
            publication.sourcepackagerelease.files[0].libraryfile.expires,
            None,
            "lfa.expires should be None, but it's not.")


class ArchiveExpiryCommonTests(object):
    """Common source/binary expiration test cases.

    These will be shared irrespective of archive type (ppa/partner).
    """

    def testNoExpirationWithNoDateremoved(self):
        """Test that no expiring happens if no dateremoved set."""
        pkg1 = self.stp.getPubSource(
            sourcename="pkg1", architecturehintlist="i386",
            archive=self.archive, dateremoved=None)
        [pub] = self.stp.getPubBinaries(
            pub_source=pkg1, dateremoved=None, archive=self.archive)

        self.runScript()
        self.assertSourceNotExpired(pkg1)
        self.assertBinaryNotExpired(pub)

    def testNoExpirationWithDateUnderThreshold(self):
        """Test no expiring if dateremoved too recent."""
        pkg2 = self.stp.getPubSource(
            sourcename="pkg2", architecturehintlist="i386",
            archive=self.archive, dateremoved=self.under_threshold_date)
        [pub] = self.stp.getPubBinaries(
            pub_source=pkg2, dateremoved=self.under_threshold_date,
            archive=self.archive)

        self.runScript()
        self.assertSourceNotExpired(pkg2)
        self.assertBinaryNotExpired(pub)

    def testExpirationWithDateOverThreshold(self):
        """Test expiring works if dateremoved old enough."""
        pkg3 = self.stp.getPubSource(
            sourcename="pkg3", architecturehintlist="i386",
            archive=self.archive, dateremoved=self.over_threshold_date)
        [pub] = self.stp.getPubBinaries(
            pub_source=pkg3, dateremoved=self.over_threshold_date,
            archive=self.archive)

        self.runScript()
        self.assertSourceExpired(pkg3)
        self.assertBinaryExpired(pub)

    def testNoExpirationWithDateOverThresholdAndOtherValidPublication(self):
        """Test no expiry if dateremoved old enough but other publication."""
        pkg4 = self.stp.getPubSource(
            sourcename="pkg4", architecturehintlist="i386",
            archive=self.archive, dateremoved=self.over_threshold_date)
        other_source = pkg4.copyTo(
            pkg4.distroseries, pkg4.pocket, self.archive2)
        other_source.dateremoved = None
        [pub] = self.stp.getPubBinaries(
            pub_source=pkg4, dateremoved=self.over_threshold_date,
            archive=self.archive)
        [other_binary] = pub.copyTo(
            pub.distroarchseries.distroseries, pub.pocket, self.archive2)
        other_binary.dateremoved = None

        self.runScript()
        self.assertSourceNotExpired(pkg4)
        self.assertBinaryNotExpired(pub)

    def testNoExpirationWithDateOverThresholdAndOtherPubUnderThreshold(self):
        """Test no expiring.

        Test no expiring if dateremoved old enough but other publication
        not over date threshold.
        """
        pkg5 = self.stp.getPubSource(
            sourcename="pkg5", architecturehintlist="i386",
            archive=self.archive, dateremoved=self.over_threshold_date)
        other_source = pkg5.copyTo(
            pkg5.distroseries, pkg5.pocket, self.archive2)
        other_source.dateremoved = self.under_threshold_date
        [pub] = self.stp.getPubBinaries(
            pub_source=pkg5, dateremoved=self.over_threshold_date,
            archive=self.archive)
        [other_binary] = pub.copyTo(
            pub.distroarchseries.distroseries, pub.pocket, self.archive2)
        other_binary.dateremoved = self.under_threshold_date

        self.runScript()
        self.assertSourceNotExpired(pkg5)
        self.assertBinaryNotExpired(pub)

    def testNoExpirationWithDateOverThresholdAndOtherPubOverThreshold(self):
        """Test expiring works.

        Test expiring works if dateremoved old enough and other publication
        is over date threshold.
        """
        source, binary = self._setUpExpirablePublications()
        self.runScript()
        self.assertSourceExpired(source)
        self.assertBinaryExpired(binary)

    def testDryRun(self):
        """Test that when dryrun is specified, nothing is expired."""
        source, binary = self._setUpExpirablePublications()
        # We have to commit here otherwise when the script aborts it
        # will remove the test publications we just created.
        self.layer.txn.commit()
        script = self.getScript(['--dry-run'])
        switch_dbuser(self.dbuser)
        script.main()
        self.assertSourceNotExpired(source)
        self.assertBinaryNotExpired(binary)

    def testDoesNotAffectPrimary(self):
        """Test that expiry does not happen for non-PPA publications."""
        ubuntu_archive = getUtility(IDistributionSet)['ubuntu'].main_archive
        source, binary = self._setUpExpirablePublications(ubuntu_archive)
        self.runScript()
        self.assertSourceNotExpired(source)
        self.assertBinaryNotExpired(binary)


class TestPPAExpiry(ArchiveExpiryTestBase, ArchiveExpiryCommonTests):
    """Test the expire-archive-files.py script.

    Here we make use of the common test cases defined in the base class but
    also add tests specific to PPAs (excluding particular PPAs from expiry
    based on a "black list" or on the fact that PPA is private).
    """

    def setUp(self):
        """Set up some test publications."""
        super(TestPPAExpiry, self).setUp()
        # Prepare two PPAs for the tests to use.
        self.archive = self.factory.makeArchive()
        self.archive2 = self.factory.makeArchive()

    def testBlacklistingWorks(self):
        """Test that blacklisted PPAs are not expired."""
        source, binary = self._setUpExpirablePublications(
            archive=self.archive)
        script = self.getScript()
        script.blacklist = [self.archive.owner.name, ]
        switch_dbuser(self.dbuser)
        script.main()
        self.assertSourceNotExpired(source)
        self.assertBinaryNotExpired(binary)

    def testWhitelistingWorks(self):
        """Test that whitelisted private PPAs are expired anyway."""
        p3a = self.factory.makeArchive(private=True)
        source, binary = self._setUpExpirablePublications(archive=p3a)
        script = self.getScript()
        script.whitelist = ['%s/%s' % (p3a.owner.name, p3a.name)]
        switch_dbuser(self.dbuser)
        script.main()
        self.assertSourceExpired(source)
        self.assertBinaryExpired(binary)

    def testPrivatePPAsNotExpired(self):
        """Test that private PPAs are not expired."""
        self.archive.private = True
        source, binary = self._setUpExpirablePublications()
        self.runScript()
        self.assertSourceNotExpired(source)
        self.assertBinaryNotExpired(binary)


class TestPartnerExpiry(ArchiveExpiryTestBase, ArchiveExpiryCommonTests):
    """Test the expire-archive-files.py script on partner archives."""

    def setUp(self):
        """Set up the partner archives under test."""
        super(TestPartnerExpiry, self).setUp()
        # Prepare two partner archives for the tests to use.
        self.archive = self.factory.makeArchive(
            purpose=ArchivePurpose.PARTNER)
        self.archive2 = self.factory.makeArchive(
            purpose=ArchivePurpose.PARTNER)
