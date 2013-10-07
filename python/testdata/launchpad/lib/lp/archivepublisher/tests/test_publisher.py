# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for publisher class."""

__metaclass__ = type


import bz2
import crypt
import gzip
import hashlib
import os
import shutil
import stat
import tempfile
from textwrap import dedent
import time

from debian.deb822 import Release
import transaction
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.archivepublisher.config import getPubConfig
from lp.archivepublisher.diskpool import DiskPool
from lp.archivepublisher.interfaces.archivesigningkey import (
    IArchiveSigningKey,
    )
from lp.archivepublisher.publishing import (
    getPublisher,
    I18nIndex,
    Publisher,
    )
from lp.archivepublisher.utils import RepositoryIndexFile
from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.interfaces.distroseries import IDistroSeries
from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.pocket import (
    PackagePublishingPocket,
    pocketsuffix,
    )
from lp.registry.interfaces.series import SeriesStatus
from lp.services.config import config
from lp.services.database.constants import UTC_NOW
from lp.services.gpg.interfaces import IGPGHandler
from lp.services.log.logger import (
    BufferLogger,
    DevNullLogger,
    )
from lp.services.utils import file_exists
from lp.soyuz.enums import (
    ArchivePurpose,
    ArchiveStatus,
    BinaryPackageFormat,
    PackagePublishingStatus,
    )
from lp.soyuz.interfaces.archive import IArchiveSet
from lp.soyuz.tests.test_publishing import TestNativePublishingBase
from lp.testing import TestCaseWithFactory
from lp.testing.fakemethod import FakeMethod
from lp.testing.gpgkeys import gpgkeysdir
from lp.testing.keyserver import KeyServerTac
from lp.testing.layers import ZopelessDatabaseLayer


RELEASE = PackagePublishingPocket.RELEASE
BACKPORTS = PackagePublishingPocket.BACKPORTS


class TestPublisherBase(TestNativePublishingBase):
    """Basic setUp for `TestPublisher` classes.

    Extends `TestNativePublishingBase` already.
    """

    def setUp(self):
        """Override cprov PPA distribution to 'ubuntutest'."""
        TestNativePublishingBase.setUp(self)

        # Override cprov's PPA distribution, because we can't publish
        # 'ubuntu' in the current sampledata.
        cprov = getUtility(IPersonSet).getByName('cprov')
        naked_archive = removeSecurityProxy(cprov.archive)
        naked_archive.distribution = self.ubuntutest


class TestPublisher(TestPublisherBase):
    """Testing `Publisher` behaviour."""

    def assertDirtyPocketsContents(self, expected, dirty_pockets):
        contents = [(str(dr_name), pocket.name) for dr_name, pocket in
                    dirty_pockets]
        self.assertEqual(expected, contents)

    def assertReleaseContentsMatch(self, release, filename, contents):
        for hash_name, hash_func in (
            ('md5sum', hashlib.md5),
            ('sha1', hashlib.sha1),
            ('sha256', hashlib.sha256)):
            self.assertTrue(hash_name in release)
            entries = [entry for entry in release[hash_name]
                       if entry['name'] == filename]
            self.assertEqual(1, len(entries))
            self.assertEqual(hash_func(contents).hexdigest(),
                             entries[0][hash_name])
            self.assertEqual(str(len(contents)), entries[0]['size'])

    def parseRelease(self, release_path):
        with open(release_path) as release_file:
            return Release(release_file)

    def parseI18nIndex(self, i18n_index_path):
        with open(i18n_index_path) as i18n_index_file:
            return I18nIndex(i18n_index_file)

    def testInstantiate(self):
        """Publisher should be instantiatable"""
        Publisher(self.logger, self.config, self.disk_pool,
                  self.ubuntutest.main_archive)

    def testPublishing(self):
        """Test the non-careful publishing procedure.

        With one PENDING record, respective pocket *dirtied*.
        """
        publisher = Publisher(
            self.logger, self.config, self.disk_pool,
            self.ubuntutest.main_archive)

        pub_source = self.getPubSource(filecontent='Hello world')

        publisher.A_publish(False)
        self.layer.txn.commit()

        pub_source.sync()
        self.assertDirtyPocketsContents(
            [('breezy-autotest', 'RELEASE')], publisher.dirty_pockets)
        self.assertEqual(PackagePublishingStatus.PUBLISHED, pub_source.status)

        # file got published
        foo_path = "%s/main/f/foo/foo_666.dsc" % self.pool_dir
        with open(foo_path) as foo_file:
            self.assertEqual('Hello world', foo_file.read().strip())

    def testDeletingPPA(self):
        """Test deleting a PPA"""
        ubuntu_team = getUtility(IPersonSet).getByName('ubuntu-team')
        test_archive = getUtility(IArchiveSet).new(
            distribution=self.ubuntutest, owner=ubuntu_team,
            purpose=ArchivePurpose.PPA, name='testing')

        # Create some source and binary publications, including an
        # orphaned NBS binary.
        spph = self.factory.makeSourcePackagePublishingHistory(
            archive=test_archive)
        bpph = self.factory.makeBinaryPackagePublishingHistory(
            archive=test_archive)
        orphaned_bpph = self.factory.makeBinaryPackagePublishingHistory(
            archive=test_archive)
        bpb = orphaned_bpph.binarypackagerelease.build
        bpb.current_source_publication.supersede()
        dead_spph = self.factory.makeSourcePackagePublishingHistory(
            archive=test_archive)
        dead_spph.supersede()
        dead_bpph = self.factory.makeBinaryPackagePublishingHistory(
            archive=test_archive)
        dead_bpph.supersede()

        publisher = getPublisher(test_archive, None, self.logger)
        publisher.setupArchiveDirs()

        self.assertTrue(os.path.exists(publisher._config.archiveroot))

        # Create a file inside archiveroot to ensure we're recursive.
        open(os.path.join(
            publisher._config.archiveroot, 'test_file'), 'w').close()
        # And a meta file
        os.makedirs(publisher._config.metaroot)
        open(os.path.join(publisher._config.metaroot, 'test'), 'w').close()

        publisher.deleteArchive()
        root_dir = os.path.join(
            publisher._config.distroroot, test_archive.owner.name,
            test_archive.name)
        self.assertFalse(os.path.exists(root_dir))
        self.assertFalse(os.path.exists(publisher._config.metaroot))
        self.assertEqual(ArchiveStatus.DELETED, test_archive.status)
        self.assertEqual(False, test_archive.publish)
        self.assertEqual(u'testing-deletedppa', test_archive.name)

        # All of the archive's active publications have been marked
        # DELETED, and dateremoved has been set early because they've
        # already been removed from disk.
        for pub in (spph, bpph, orphaned_bpph):
            self.assertEqual(PackagePublishingStatus.DELETED, pub.status)
            self.assertEqual(u'janitor', pub.removed_by.name)
            self.assertIsNot(None, pub.dateremoved)

        # The SUPERSEDED publications now have dateremoved set, even
        # though p-d-r hasn't run over them.
        for pub in (dead_spph, dead_bpph):
            self.assertIs(None, pub.scheduleddeletiondate)
            self.assertIsNot(None, pub.dateremoved)

        # Trying to delete it again won't fail, in the corner case where
        # some admin manually deleted the repo.
        publisher.deleteArchive()

    def testDeletingPPAWithoutMetaData(self):
        ubuntu_team = getUtility(IPersonSet).getByName('ubuntu-team')
        test_archive = getUtility(IArchiveSet).new(
            distribution=self.ubuntutest, owner=ubuntu_team,
            purpose=ArchivePurpose.PPA)
        logger = BufferLogger()
        publisher = getPublisher(test_archive, None, logger)
        publisher.setupArchiveDirs()

        self.assertTrue(os.path.exists(publisher._config.archiveroot))

        # Create a file inside archiveroot to ensure we're recursive.
        open(os.path.join(
            publisher._config.archiveroot, 'test_file'), 'w').close()

        publisher.deleteArchive()
        root_dir = os.path.join(
            publisher._config.distroroot, test_archive.owner.name,
            test_archive.name)
        self.assertFalse(os.path.exists(root_dir))
        self.assertNotIn('WARNING', logger.getLogBuffer())
        self.assertNotIn('ERROR', logger.getLogBuffer())

    def testDeletingPPARename(self):
        a1 = self.factory.makeArchive(purpose=ArchivePurpose.PPA, name='test')
        getPublisher(a1, None, self.logger).deleteArchive()
        self.assertEqual('test-deletedppa', a1.name)
        a2 = self.factory.makeArchive(
            purpose=ArchivePurpose.PPA, name='test', owner=a1.owner)
        getPublisher(a2, None, self.logger).deleteArchive()
        self.assertEqual('test-deletedppa1', a2.name)

    def testPublishPartner(self):
        """Test that a partner package is published to the right place."""
        archive = self.ubuntutest.getArchiveByComponent('partner')
        pub_config = getPubConfig(archive)
        pub_config.setupArchiveDirs()
        disk_pool = DiskPool(
            pub_config.poolroot, pub_config.temproot, self.logger)
        publisher = Publisher(
            self.logger, pub_config, disk_pool, archive)
        self.getPubSource(archive=archive, filecontent="I am partner")

        publisher.A_publish(False)

        # Did the file get published in the right place?
        self.assertEqual(
            "/var/tmp/archive/ubuntutest-partner/pool", pub_config.poolroot)
        foo_path = "%s/main/f/foo/foo_666.dsc" % pub_config.poolroot
        with open(foo_path) as foo_file:
            self.assertEqual("I am partner", foo_file.read().strip())

        # Check that the index is in the right place.
        publisher.C_writeIndexes(False)
        self.assertEqual(
            "/var/tmp/archive/ubuntutest-partner/dists", pub_config.distsroot)
        index_path = os.path.join(
            pub_config.distsroot, 'breezy-autotest', 'partner', 'source',
            'Sources.gz')
        with open(index_path) as index_file:
            self.assertTrue(index_file)

        # Check the release file is in the right place.
        publisher.D_writeReleaseFiles(False)
        release_path = os.path.join(
            pub_config.distsroot, 'breezy-autotest', 'Release')
        with open(release_path) as release_file:
            self.assertTrue(release_file)

    def testPartnerReleasePocketPublishing(self):
        """Test partner package RELEASE pocket publishing.

        Publishing partner packages to the RELEASE pocket in a stable
        distroseries is always allowed, so check for that here.
        """
        archive = self.ubuntutest.getArchiveByComponent('partner')
        self.ubuntutest['breezy-autotest'].status = SeriesStatus.CURRENT
        pub_config = getPubConfig(archive)
        pub_config.setupArchiveDirs()
        disk_pool = DiskPool(
            pub_config.poolroot, pub_config.temproot, self.logger)
        publisher = Publisher(self.logger, pub_config, disk_pool, archive)
        self.getPubSource(
            archive=archive, filecontent="I am partner",
            status=PackagePublishingStatus.PENDING)

        publisher.A_publish(force_publishing=False)

        # The pocket was dirtied:
        self.assertDirtyPocketsContents(
            [('breezy-autotest', 'RELEASE')], publisher.dirty_pockets)
        # The file was published:
        foo_path = "%s/main/f/foo/foo_666.dsc" % pub_config.poolroot
        with open(foo_path) as foo_file:
            self.assertEqual('I am partner', foo_file.read().strip())

        # Nothing to test from these two calls other than that they don't blow
        # up as there is an assertion in the code to make sure it's not
        # publishing out of a release pocket in a stable distroseries,
        # excepting PPA and partner which are allowed to do that.
        publisher.C_writeIndexes(is_careful=False)
        publisher.D_writeReleaseFiles(is_careful=False)

    def testPublishingSpecificDistroSeries(self):
        """Test the publishing procedure with the suite argument.

        To publish a specific distroseries.
        """
        publisher = Publisher(
            self.logger, self.config, self.disk_pool,
            self.ubuntutest.main_archive,
            allowed_suites=[('hoary-test', PackagePublishingPocket.RELEASE)])

        pub_source = self.getPubSource(filecontent='foo')
        pub_source2 = self.getPubSource(
            sourcename='baz', filecontent='baz',
            distroseries=self.ubuntutest['hoary-test'])

        publisher.A_publish(force_publishing=False)
        self.layer.txn.commit()

        pub_source.sync()
        pub_source2.sync()
        self.assertDirtyPocketsContents(
            [('hoary-test', 'RELEASE')], publisher.dirty_pockets)
        self.assertEqual(
            PackagePublishingStatus.PUBLISHED, pub_source2.status)
        self.assertEqual(PackagePublishingStatus.PENDING, pub_source.status)

    def testPublishingSpecificPocket(self):
        """Test the publishing procedure with the suite argument.

        To publish a specific pocket.
        """
        publisher = Publisher(
            self.logger, self.config, self.disk_pool,
            self.ubuntutest.main_archive,
            allowed_suites=[('breezy-autotest',
                             PackagePublishingPocket.UPDATES)])

        self.ubuntutest['breezy-autotest'].status = (
            SeriesStatus.CURRENT)

        pub_source = self.getPubSource(
            filecontent='foo',
            pocket=PackagePublishingPocket.UPDATES)

        pub_source2 = self.getPubSource(
            sourcename='baz', filecontent='baz',
            pocket=PackagePublishingPocket.BACKPORTS)

        publisher.A_publish(force_publishing=False)
        self.layer.txn.commit()

        pub_source.sync()
        pub_source2.sync()
        self.assertDirtyPocketsContents(
            [('breezy-autotest', 'UPDATES')], publisher.dirty_pockets)
        self.assertEqual(PackagePublishingStatus.PUBLISHED, pub_source.status)
        self.assertEqual(PackagePublishingStatus.PENDING, pub_source2.status)

    def testNonCarefulPublishing(self):
        """Test the non-careful publishing procedure.

        With one PUBLISHED record, no pockets *dirtied*.
        """
        publisher = Publisher(
            self.logger, self.config, self.disk_pool,
            self.ubuntutest.main_archive)

        self.getPubSource(status=PackagePublishingStatus.PUBLISHED)

        # a new non-careful publisher won't find anything to publish, thus
        # no pockets will be *dirtied*.
        publisher.A_publish(False)

        self.assertDirtyPocketsContents([], publisher.dirty_pockets)
        # nothing got published
        foo_path = "%s/main/f/foo/foo_666.dsc" % self.pool_dir
        self.assertEqual(False, os.path.exists(foo_path))

    def testCarefulPublishing(self):
        """Test the careful publishing procedure.

        With one PUBLISHED record, pocket gets *dirtied*.
        """
        publisher = Publisher(
            self.logger, self.config, self.disk_pool,
            self.ubuntutest.main_archive)

        self.getPubSource(
            filecontent='Hello world',
            status=PackagePublishingStatus.PUBLISHED)

        # A careful publisher run will re-publish the PUBLISHED records,
        # then we will have a corresponding dirty_pocket entry.
        publisher.A_publish(True)

        self.assertDirtyPocketsContents(
            [('breezy-autotest', 'RELEASE')], publisher.dirty_pockets)
        # file got published
        foo_path = "%s/main/f/foo/foo_666.dsc" % self.pool_dir
        with open(foo_path) as foo_file:
            self.assertEqual('Hello world', foo_file.read().strip())

    def testPublishingOnlyConsidersOneArchive(self):
        """Publisher procedure should only consider the target archive.

        Ignore pending publishing records targeted to another archive.
        Nothing gets published, no pockets get *dirty*
        """
        publisher = Publisher(
            self.logger, self.config, self.disk_pool,
            self.ubuntutest.main_archive)

        ubuntu_team = getUtility(IPersonSet).getByName('ubuntu-team')
        test_archive = getUtility(IArchiveSet).new(
            owner=ubuntu_team, purpose=ArchivePurpose.PPA)

        pub_source = self.getPubSource(
            sourcename="foo", filename="foo_1.dsc", filecontent='Hello world',
            status=PackagePublishingStatus.PENDING, archive=test_archive)

        publisher.A_publish(False)
        self.layer.txn.commit()

        self.assertDirtyPocketsContents([], publisher.dirty_pockets)
        self.assertEqual(PackagePublishingStatus.PENDING, pub_source.status)

        # nothing got published
        foo_path = "%s/main/f/foo/foo_1.dsc" % self.pool_dir
        self.assertEqual(False, os.path.exists(foo_path))

    def testPublishingWorksForOtherArchives(self):
        """Publisher also works as expected for another archives."""
        ubuntu_team = getUtility(IPersonSet).getByName('ubuntu-team')
        test_archive = getUtility(IArchiveSet).new(
            distribution=self.ubuntutest, owner=ubuntu_team,
            purpose=ArchivePurpose.PPA)

        test_pool_dir = tempfile.mkdtemp()
        test_temp_dir = tempfile.mkdtemp()
        test_disk_pool = DiskPool(test_pool_dir, test_temp_dir, self.logger)

        publisher = Publisher(
            self.logger, self.config, test_disk_pool,
            test_archive)

        pub_source = self.getPubSource(
            sourcename="foo", filename="foo_1.dsc",
            filecontent='I am supposed to be a embargoed archive',
            status=PackagePublishingStatus.PENDING, archive=test_archive)

        publisher.A_publish(False)
        self.layer.txn.commit()

        pub_source.sync()
        self.assertDirtyPocketsContents(
            [('breezy-autotest', 'RELEASE')], publisher.dirty_pockets)
        self.assertEqual(PackagePublishingStatus.PUBLISHED, pub_source.status)

        # nothing got published
        foo_path = "%s/main/f/foo/foo_1.dsc" % test_pool_dir
        with open(foo_path) as foo_file:
            self.assertEqual(
                'I am supposed to be a embargoed archive',
                foo_file.read().strip())

        # remove locally created dir
        shutil.rmtree(test_pool_dir)

    def testPublishingSkipsObsoleteFuturePrimarySeries(self):
        """Publisher skips OBSOLETE/FUTURE series in PRIMARY archives."""
        publisher = Publisher(
            self.logger, self.config, self.disk_pool,
            self.ubuntutest.main_archive)
        # Remove security proxy so that the publisher can call our fake
        # method.
        publisher.distro = removeSecurityProxy(publisher.distro)

        for status in (SeriesStatus.OBSOLETE, SeriesStatus.FUTURE):
            naked_breezy_autotest = publisher.distro['breezy-autotest']
            naked_breezy_autotest.status = status
            naked_breezy_autotest.publish = FakeMethod(result=set())

            publisher.A_publish(False)

            self.assertEqual(0, naked_breezy_autotest.publish.call_count)

    def testPublishingConsidersObsoleteFuturePPASeries(self):
        """Publisher does not skip OBSOLETE/FUTURE series in PPA archives."""
        ubuntu_team = getUtility(IPersonSet).getByName('ubuntu-team')
        test_archive = getUtility(IArchiveSet).new(
            distribution=self.ubuntutest, owner=ubuntu_team,
            purpose=ArchivePurpose.PPA)
        publisher = Publisher(
            self.logger, self.config, self.disk_pool, test_archive)
        # Remove security proxy so that the publisher can call our fake
        # method.
        publisher.distro = removeSecurityProxy(publisher.distro)

        for status in (SeriesStatus.OBSOLETE, SeriesStatus.FUTURE):
            naked_breezy_autotest = publisher.distro['breezy-autotest']
            naked_breezy_autotest.status = status
            naked_breezy_autotest.publish = FakeMethod(result=set())

            publisher.A_publish(False)

            self.assertEqual(1, naked_breezy_autotest.publish.call_count)

    def testPublisherBuilderFunctions(self):
        """Publisher can be initialized via provided helper function.

        In order to simplify the top-level publication scripts, one for
        'main_archive' publication and other for 'PPA', we have a specific
        helper function: 'getPublisher'
        """
        # Stub parameters.
        allowed_suites = [
            ('breezy-autotest', PackagePublishingPocket.RELEASE)]

        distro_publisher = getPublisher(
            self.ubuntutest.main_archive, allowed_suites, self.logger)

        # check the publisher context, pointing to the 'main_archive'
        self.assertEqual(
            self.ubuntutest.main_archive, distro_publisher.archive)
        self.assertEqual(
            '/var/tmp/archive/ubuntutest/dists',
            distro_publisher._config.distsroot)
        self.assertEqual(
            [('breezy-autotest', PackagePublishingPocket.RELEASE)],
            distro_publisher.allowed_suites)

        # Check that the partner archive is built in a different directory
        # to the primary archive.
        partner_archive = getUtility(IArchiveSet).getByDistroPurpose(
            self.ubuntutest, ArchivePurpose.PARTNER)
        distro_publisher = getPublisher(
            partner_archive, allowed_suites, self.logger)
        self.assertEqual(partner_archive, distro_publisher.archive)
        self.assertEqual('/var/tmp/archive/ubuntutest-partner/dists',
            distro_publisher._config.distsroot)
        self.assertEqual('/var/tmp/archive/ubuntutest-partner/pool',
            distro_publisher._config.poolroot)

        # lets setup an Archive Publisher
        cprov = getUtility(IPersonSet).getByName('cprov')
        archive_publisher = getPublisher(
            cprov.archive, allowed_suites, self.logger)

        # check the publisher context, pointing to the given PPA archive
        self.assertEqual(
            cprov.archive, archive_publisher.archive)
        self.assertEqual(
            u'/var/tmp/ppa.test/cprov/ppa/ubuntutest/dists',
            archive_publisher._config.distsroot)
        self.assertEqual(
            [('breezy-autotest', PackagePublishingPocket.RELEASE)],
            archive_publisher.allowed_suites)

    def testPendingArchive(self):
        """Check Pending Archive Lookup.

        IArchiveSet.getPendingPPAs should only return the archives with
        publications in PENDING state.
        """
        archive_set = getUtility(IArchiveSet)
        person_set = getUtility(IPersonSet)
        ubuntu = getUtility(IDistributionSet)['ubuntu']

        spiv = person_set.getByName('spiv')
        archive_set.new(
            owner=spiv, distribution=ubuntu, purpose=ArchivePurpose.PPA)
        name16 = person_set.getByName('name16')
        archive_set.new(
            owner=name16, distribution=ubuntu, purpose=ArchivePurpose.PPA)

        self.getPubSource(
            sourcename="foo", filename="foo_1.dsc", filecontent='Hello world',
            status=PackagePublishingStatus.PENDING, archive=spiv.archive)

        self.getPubSource(
            sourcename="foo", filename="foo_1.dsc", filecontent='Hello world',
            status=PackagePublishingStatus.PUBLISHED, archive=name16.archive)

        self.assertEqual(4, ubuntu.getAllPPAs().count())

        pending_archives = ubuntu.getPendingPublicationPPAs()
        self.assertEqual(1, pending_archives.count())
        pending_archive = pending_archives[0]
        self.assertEqual(spiv.archive.id, pending_archive.id)

    def testDeletingArchive(self):
        # IArchiveSet.getPendingPPAs should return archives that have a
        # status of DELETING.
        ubuntu = getUtility(IDistributionSet)['ubuntu']

        archive = self.factory.makeArchive()
        old_num_pending_archives = ubuntu.getPendingPublicationPPAs().count()
        archive.status = ArchiveStatus.DELETING
        new_num_pending_archives = ubuntu.getPendingPublicationPPAs().count()
        self.assertEqual(
            1 + old_num_pending_archives, new_num_pending_archives)

    def _checkCompressedFile(self, archive_publisher, compressed_file_path,
                             uncompressed_file_path):
        """Assert that a compressed file is equal to its uncompressed version.

        Check that a compressed file, such as Packages.gz and Sources.gz,
        and bz2 variations, matches its uncompressed partner.  The file
        paths are relative to breezy-autotest/main under the
        archive_publisher's configured dist root. 'breezy-autotest' is
        our test distroseries name.

        The contents of the uncompressed file is returned as a list of lines
        in the file.
        """
        index_compressed_path = os.path.join(
            archive_publisher._config.distsroot, 'breezy-autotest', 'main',
            compressed_file_path)
        index_path = os.path.join(
            archive_publisher._config.distsroot, 'breezy-autotest', 'main',
            uncompressed_file_path)

        if index_compressed_path.endswith('.gz'):
            index_compressed_contents = gzip.GzipFile(
                filename=index_compressed_path).read().splitlines()
        elif index_compressed_path.endswith('.bz2'):
            index_compressed_contents = bz2.BZ2File(
                filename=index_compressed_path).read().splitlines()
        else:
            raise AssertionError(
                'Unsupported compression: %s' % compressed_file_path)

        with open(index_path, 'r') as index_file:
            index_contents = index_file.read().splitlines()

        self.assertEqual(index_contents, index_compressed_contents)

        return index_contents

    def testPPAArchiveIndex(self):
        """Building Archive Indexes from PPA publications."""
        allowed_suites = []

        cprov = getUtility(IPersonSet).getByName('cprov')
        cprov.archive.publish_debug_symbols = True

        archive_publisher = getPublisher(
            cprov.archive, allowed_suites, self.logger)

        # Pending source and binary publications.
        # The binary description explores index formatting properties.
        pub_source = self.getPubSource(
            sourcename="foo", filename="foo_1.dsc", filecontent='Hello world',
            status=PackagePublishingStatus.PENDING, archive=cprov.archive)
        self.getPubBinaries(
            pub_source=pub_source,
            description="   My leading spaces are normalised to a single "
                        "space but not trailing.  \n    It does nothing, "
                        "though",
            with_debug=True)

        # Ignored (deleted) source publication that will not be listed in
        # the index and a pending 'udeb' binary package.
        ignored_source = self.getPubSource(
            status=PackagePublishingStatus.DELETED,
            archive=cprov.archive)
        self.getPubBinaries(
            pub_source=ignored_source, binaryname='bingo',
            description='nice udeb', format=BinaryPackageFormat.UDEB)[0]

        archive_publisher.A_publish(False)
        self.layer.txn.commit()
        archive_publisher.C_writeIndexes(False)

        # A compressed and uncompressed Sources file are written;
        # ensure that they are the same after uncompressing the former.
        index_contents = self._checkCompressedFile(
            archive_publisher, os.path.join('source', 'Sources.bz2'),
            os.path.join('source', 'Sources'))

        index_contents = self._checkCompressedFile(
            archive_publisher, os.path.join('source', 'Sources.gz'),
            os.path.join('source', 'Sources'))

        self.assertEqual(
            ['Package: foo',
             'Binary: foo-bin',
             'Version: 666',
             'Section: base',
             'Maintainer: Foo Bar <foo@bar.com>',
             'Architecture: all',
             'Standards-Version: 3.6.2',
             'Format: 1.0',
             'Directory: pool/main/f/foo',
             'Files:',
             ' 3e25960a79dbc69b674cd4ec67a72c62 11 foo_1.dsc',
             'Checksums-Sha1:',
             ' 7b502c3a1f48c8609ae212cdfb639dee39673f5e 11 foo_1.dsc',
             'Checksums-Sha256:',
             ' 64ec88ca00b268e5ba1a35678a1b5316d212f4f366b2477232534a8aeca37f'
             '3c 11 foo_1.dsc',

             ''],
            index_contents)

        # A compressed and an uncompressed Packages file are written;
        # ensure that they are the same after uncompressing the former.
        index_contents = self._checkCompressedFile(
            archive_publisher, os.path.join('binary-i386', 'Packages.bz2'),
            os.path.join('binary-i386', 'Packages'))

        index_contents = self._checkCompressedFile(
            archive_publisher, os.path.join('binary-i386', 'Packages.gz'),
            os.path.join('binary-i386', 'Packages'))

        self.assertEqual(
            ['Package: foo-bin',
             'Source: foo',
             'Priority: standard',
             'Section: base',
             'Installed-Size: 100',
             'Maintainer: Foo Bar <foo@bar.com>',
             'Architecture: all',
             'Version: 666',
             'Filename: pool/main/f/foo/foo-bin_666_all.deb',
             'Size: 18',
             'MD5sum: 008409e7feb1c24a6ccab9f6a62d24c5',
             'SHA1: 30b7b4e583fa380772c5a40e428434628faef8cf',
             'SHA256: 006ca0f356f54b1916c24c282e6fd19961f4356441401f4b0966f2a'
             '00bb3e945',
             'Description: Foo app is great',
             ' My leading spaces are normalised to a single space but not '
             'trailing.  ',
             ' It does nothing, though',
             ''],
            index_contents)

        # A compressed and an uncompressed Packages file are written for
        # 'debian-installer' section for each architecture. It will list
        # the 'udeb' files.
        index_contents = self._checkCompressedFile(
            archive_publisher,
            os.path.join('debian-installer', 'binary-i386', 'Packages.bz2'),
            os.path.join('debian-installer', 'binary-i386', 'Packages'))

        index_contents = self._checkCompressedFile(
            archive_publisher,
            os.path.join('debian-installer', 'binary-i386', 'Packages.gz'),
            os.path.join('debian-installer', 'binary-i386', 'Packages'))

        self.assertEqual(
            ['Package: bingo',
             'Source: foo',
             'Priority: standard',
             'Section: base',
             'Installed-Size: 100',
             'Maintainer: Foo Bar <foo@bar.com>',
             'Architecture: all',
             'Version: 666',
             'Filename: pool/main/f/foo/bingo_666_all.udeb',
             'Size: 18',
             'MD5sum: 008409e7feb1c24a6ccab9f6a62d24c5',
             'SHA1: 30b7b4e583fa380772c5a40e428434628faef8cf',
             'SHA256: 006ca0f356f54b1916c24c282e6fd19961f4356441401f4b0966f2a'
             '00bb3e945',
             'Description: Foo app is great',
             ' nice udeb',
             ''],
            index_contents)

        # 'debug' too, when publish_debug_symbols is enabled.
        index_contents = self._checkCompressedFile(
            archive_publisher,
            os.path.join('debug', 'binary-i386', 'Packages.bz2'),
            os.path.join('debug', 'binary-i386', 'Packages'))

        index_contents = self._checkCompressedFile(
            archive_publisher,
            os.path.join('debug', 'binary-i386', 'Packages.gz'),
            os.path.join('debug', 'binary-i386', 'Packages'))

        self.assertEqual(
            ['Package: foo-bin-dbgsym',
             'Source: foo',
             'Priority: standard',
             'Section: base',
             'Installed-Size: 100',
             'Maintainer: Foo Bar <foo@bar.com>',
             'Architecture: all',
             'Version: 666',
             'Filename: pool/main/f/foo/foo-bin-dbgsym_666_all.ddeb',
             'Size: 18',
             'MD5sum: 008409e7feb1c24a6ccab9f6a62d24c5',
             'SHA1: 30b7b4e583fa380772c5a40e428434628faef8cf',
             'SHA256: 006ca0f356f54b1916c24c282e6fd19961f4356441401f4b0966f2a'
             '00bb3e945',
             'Description: Foo app is great',
             ' My leading spaces are normalised to a single space but not '
             'trailing.  ',
             ' It does nothing, though',
             ''],
            index_contents)

        # We always regenerate all Releases file for a given suite.
        self.assertTrue(
            ('breezy-autotest', PackagePublishingPocket.RELEASE) in
            archive_publisher.release_files_needed)

        # remove PPA root
        shutil.rmtree(config.personalpackagearchive.root)

    def checkDirtyPockets(self, publisher, expected):
        """Check dirty_pockets contents of a given publisher."""
        sorted_dirty_pockets = sorted(list(publisher.dirty_pockets))
        self.assertEqual(expected, sorted_dirty_pockets)

    def testDirtyingPocketsWithDeletedPackages(self):
        """Test that dirtying pockets with deleted packages works.

        The publisher run should make dirty pockets where there are
        outstanding deletions, so that the domination process will
        work on the deleted publications.
        """
        allowed_suites = []
        publisher = getPublisher(
            self.ubuntutest.main_archive, allowed_suites, self.logger)

        publisher.A2_markPocketsWithDeletionsDirty()
        self.checkDirtyPockets(publisher, expected=[])

        # Make a published source, a deleted source in the release
        # pocket, a source that's been removed from disk and one that's
        # waiting to be deleted, each in different pockets.  The deleted
        # source in the release pocket should not be processed.  We'll
        # also have a binary waiting to be deleted.
        self.getPubSource(
            pocket=PackagePublishingPocket.RELEASE,
            status=PackagePublishingStatus.PUBLISHED)

        self.getPubSource(
            pocket=PackagePublishingPocket.RELEASE,
            status=PackagePublishingStatus.DELETED)

        self.getPubSource(
            scheduleddeletiondate=UTC_NOW,
            dateremoved=UTC_NOW,
            pocket=PackagePublishingPocket.UPDATES,
            status=PackagePublishingStatus.DELETED)

        self.getPubSource(
            pocket=PackagePublishingPocket.SECURITY,
            status=PackagePublishingStatus.DELETED)

        self.getPubBinaries(
            pocket=PackagePublishingPocket.BACKPORTS,
            status=PackagePublishingStatus.DELETED)

        # Run the deletion detection.
        publisher.A2_markPocketsWithDeletionsDirty()

        # Only the pockets with pending deletions are marked as dirty.
        expected_dirty_pockets = [
            ('breezy-autotest', PackagePublishingPocket.RELEASE),
            ('breezy-autotest', PackagePublishingPocket.SECURITY),
            ('breezy-autotest', PackagePublishingPocket.BACKPORTS),
            ]
        self.checkDirtyPockets(publisher, expected=expected_dirty_pockets)

        # If the distroseries is CURRENT, then the release pocket is not
        # marked as dirty.
        self.ubuntutest['breezy-autotest'].status = (
            SeriesStatus.CURRENT)

        publisher.dirty_pockets = set()
        publisher.A2_markPocketsWithDeletionsDirty()

        expected_dirty_pockets = [
            ('breezy-autotest', PackagePublishingPocket.SECURITY),
            ('breezy-autotest', PackagePublishingPocket.BACKPORTS),
            ]
        self.checkDirtyPockets(publisher, expected=expected_dirty_pockets)

    def testDeletionDetectionRespectsAllowedSuites(self):
        """Check if the deletion detection mechanism respects allowed_suites.

        The deletion detection should not request publications of pockets
        that were not specified on the command-line ('allowed_suites').

        This issue is reported as bug #241452, when running the publisher
        only for a specific suite, in most of cases an urgent security
        release, only pockets with pending deletion that match the
        specified suites should be marked as dirty.
        """
        allowed_suites = [
            ('breezy-autotest', PackagePublishingPocket.SECURITY),
            ('breezy-autotest', PackagePublishingPocket.UPDATES),
            ]
        publisher = getPublisher(
            self.ubuntutest.main_archive, allowed_suites, self.logger)

        publisher.A2_markPocketsWithDeletionsDirty()
        self.checkDirtyPockets(publisher, expected=[])

        # Create pending deletions in RELEASE, BACKPORTS, SECURITY and
        # UPDATES pockets.
        self.getPubSource(
            pocket=PackagePublishingPocket.RELEASE,
            status=PackagePublishingStatus.DELETED)

        self.getPubBinaries(
            pocket=PackagePublishingPocket.BACKPORTS,
            status=PackagePublishingStatus.DELETED)[0]

        self.getPubSource(
            pocket=PackagePublishingPocket.SECURITY,
            status=PackagePublishingStatus.DELETED)

        self.getPubBinaries(
            pocket=PackagePublishingPocket.UPDATES,
            status=PackagePublishingStatus.DELETED)[0]

        publisher.A2_markPocketsWithDeletionsDirty()
        # Only the pockets with pending deletions in the allowed suites
        # are marked as dirty.
        self.checkDirtyPockets(publisher, expected=allowed_suites)

    def testReleaseFile(self):
        """Test release file writing.

        The release file should contain the MD5, SHA1 and SHA256 for each
        index created for a given distroseries.
        """
        publisher = Publisher(
            self.logger, self.config, self.disk_pool,
            self.ubuntutest.main_archive)

        self.getPubSource(filecontent='Hello world')

        publisher.A_publish(False)
        publisher.C_doFTPArchive(False)

        self.assertIn(
            ('breezy-autotest', PackagePublishingPocket.RELEASE),
            publisher.release_files_needed)

        publisher.D_writeReleaseFiles(False)

        release = self.parseRelease(os.path.join(
            self.config.distsroot, 'breezy-autotest', 'Release'))

        # Primary archive distroseries Release 'Origin' contains
        # the distribution displayname.
        self.assertEqual('ubuntutest', release['origin'])

        # The Label: field should be set to the archive displayname
        self.assertEqual('ubuntutest', release['label'])

        arch_release_path = os.path.join(
            self.config.distsroot, 'breezy-autotest',
            'main', 'source', 'Release')
        with open(arch_release_path) as arch_release_file:
            self.assertReleaseContentsMatch(
                release, 'main/source/Release', arch_release_file.read())

        # Primary archive architecture Release files 'Origin' contain the
        # distribution displayname.
        arch_release = self.parseRelease(arch_release_path)
        self.assertEqual('ubuntutest', arch_release['origin'])

    def testReleaseFileForPPA(self):
        """Test release file writing for PPA

        The release file should contain the MD5, SHA1 and SHA256 for each
        index created for a given distroseries.

        Note that the individuals indexes have exactly the same content
        as the ones generated by apt-ftparchive (see previous test), however
        the position in the list is different (earlier) because we do not
        generate/list debian-installer (d-i) indexes in NoMoreAptFtpArchive
        approach.

        Another difference between the primary repositories and PPAs is that
        PPA Release files for the distroseries and its architectures have a
        distinct 'Origin:' value.  The origin is specific to each PPA, using
        the pattern 'LP-PPA-%(owner_name)s'.  This allows proper pinning of
        the PPA packages.
        """
        allowed_suites = []
        cprov = getUtility(IPersonSet).getByName('cprov')
        cprov.archive.displayname = u'PPA for Celso Provid\xe8lo'
        archive_publisher = getPublisher(
            cprov.archive, allowed_suites, self.logger)

        self.getPubSource(filecontent='Hello world', archive=cprov.archive)

        archive_publisher.A_publish(False)
        self.layer.txn.commit()
        archive_publisher.C_writeIndexes(False)
        archive_publisher.D_writeReleaseFiles(False)

        release = self.parseRelease(os.path.join(
            archive_publisher._config.distsroot, 'breezy-autotest',
            'Release'))
        self.assertEqual('LP-PPA-cprov', release['origin'])

        # The Label: field should be set to the archive displayname
        self.assertEqual(u'PPA for Celso Provid\xe8lo', release['label'])

        arch_sources_path = os.path.join(
            archive_publisher._config.distsroot, 'breezy-autotest',
            'main', 'source', 'Sources')
        with open(arch_sources_path) as arch_sources_file:
            self.assertReleaseContentsMatch(
                release, 'main/source/Sources', arch_sources_file.read())

        arch_release_path = os.path.join(
            archive_publisher._config.distsroot, 'breezy-autotest',
            'main', 'source', 'Release')
        with open(arch_release_path) as arch_release_file:
            self.assertReleaseContentsMatch(
                release, 'main/source/Release', arch_release_file.read())

        # Architecture Release files also have a distinct Origin: for PPAs.
        arch_release = self.parseRelease(arch_release_path)
        self.assertEqual('LP-PPA-cprov', arch_release['origin'])

    def testReleaseFileForNamedPPA(self):
        # Named PPA have a distint Origin: field, so packages from it can
        # be pinned if necessary.

        # Create a named-ppa for Celso.
        cprov = getUtility(IPersonSet).getByName('cprov')
        named_ppa = getUtility(IArchiveSet).new(
            owner=cprov, name='testing', distribution=self.ubuntutest,
            purpose=ArchivePurpose.PPA)

        # Setup the publisher for it and publish its repository.
        allowed_suites = []
        archive_publisher = getPublisher(
            named_ppa, allowed_suites, self.logger)
        self.getPubSource(filecontent='Hello world', archive=named_ppa)

        archive_publisher.A_publish(False)
        self.layer.txn.commit()
        archive_publisher.C_writeIndexes(False)
        archive_publisher.D_writeReleaseFiles(False)

        # Check the distinct Origin: field content in the main Release file
        # and the component specific one.
        release = self.parseRelease(os.path.join(
            archive_publisher._config.distsroot, 'breezy-autotest',
            'Release'))
        self.assertEqual('LP-PPA-cprov-testing', release['origin'])

        arch_release = self.parseRelease(os.path.join(
            archive_publisher._config.distsroot, 'breezy-autotest',
            'main/source/Release'))
        self.assertEqual('LP-PPA-cprov-testing', arch_release['origin'])

    def testReleaseFileForPartner(self):
        """Test Release file writing for Partner archives.

        Signed Release files must reference an uncompressed Sources and
        Packages file.
        """
        archive = self.ubuntutest.getArchiveByComponent('partner')
        allowed_suites = []
        publisher = getPublisher(archive, allowed_suites, self.logger)

        self.getPubSource(filecontent='Hello world', archive=archive)

        publisher.A_publish(False)
        publisher.C_writeIndexes(False)
        publisher.D_writeReleaseFiles(False)

        # Open the release file that was just published inside the
        # 'breezy-autotest' distroseries.
        release = self.parseRelease(os.path.join(
            publisher._config.distsroot, 'breezy-autotest', 'Release'))

        # The Release file must contain lines ending in "Packages",
        # "Packages.gz", "Sources" and "Sources.gz".
        self.assertTrue('md5sum' in release)
        self.assertTrue([entry for entry in release['md5sum']
                         if entry['name'].endswith('Packages.gz')])
        self.assertTrue([entry for entry in release['md5sum']
                         if entry['name'].endswith('Packages')])
        self.assertTrue([entry for entry in release['md5sum']
                         if entry['name'].endswith('Sources.gz')])
        self.assertTrue([entry for entry in release['md5sum']
                         if entry['name'].endswith('Sources')])

        # Partner archive architecture Release files 'Origin' contain
        # a string
        arch_release = self.parseRelease(os.path.join(
            publisher._config.distsroot, 'breezy-autotest',
            'partner/source/Release'))
        self.assertEqual('Canonical', arch_release['origin'])

        # The Label: field should be set to the archive displayname
        self.assertEqual('Partner archive', release['label'])

    def testReleaseFileForNotAutomaticBackports(self):
        # Test Release file writing for series with NotAutomatic backports.
        publisher = Publisher(
            self.logger, self.config, self.disk_pool,
            self.ubuntutest.main_archive)
        self.getPubSource(filecontent='Hello world', pocket=RELEASE)
        self.getPubSource(filecontent='Hello world', pocket=BACKPORTS)

        publisher.A_publish(True)
        publisher.C_writeIndexes(False)

        def get_release(pocket):
            release_path = os.path.join(
                publisher._config.distsroot,
                'breezy-autotest%s' % pocketsuffix[pocket], 'Release')
            with open(release_path) as release_file:
                return release_file.read().splitlines()

        # When backports_not_automatic is unset, no Release files have
        # NotAutomatic: yes.
        self.assertEqual(False, self.breezy_autotest.backports_not_automatic)
        publisher.D_writeReleaseFiles(False)
        self.assertNotIn("NotAutomatic: yes", get_release(RELEASE))
        self.assertNotIn("NotAutomatic: yes", get_release(BACKPORTS))

        # But with the flag set, -backports Release files gain
        # NotAutomatic: yes and ButAutomaticUpgrades: yes.
        self.breezy_autotest.backports_not_automatic = True
        publisher.D_writeReleaseFiles(False)
        self.assertNotIn("NotAutomatic: yes", get_release(RELEASE))
        self.assertIn("NotAutomatic: yes", get_release(BACKPORTS))
        self.assertIn("ButAutomaticUpgrades: yes", get_release(BACKPORTS))

    def testReleaseFileForI18n(self):
        """Test Release file writing for translated package descriptions."""
        publisher = Publisher(
            self.logger, self.config, self.disk_pool,
            self.ubuntutest.main_archive)
        self.getPubSource(filecontent='Hello world')

        # Make sure that apt-ftparchive generates i18n/Translation-en* files.
        ds = self.ubuntutest.getSeries('breezy-autotest')
        ds.include_long_descriptions = False

        publisher.A_publish(False)
        publisher.C_doFTPArchive(False)
        publisher.D_writeReleaseFiles(False)

        i18n_index = os.path.join(
            self.config.distsroot, 'breezy-autotest', 'main', 'i18n', 'Index')

        # The i18n/Index file has been generated.
        self.assertTrue(os.path.exists(i18n_index))

        # It is listed correctly in Release.
        release = self.parseRelease(os.path.join(
            self.config.distsroot, 'breezy-autotest', 'Release'))
        with open(i18n_index) as i18n_index_file:
            self.assertReleaseContentsMatch(
                release, 'main/i18n/Index', i18n_index_file.read())

    def testCreateSeriesAliasesNoAlias(self):
        """createSeriesAliases has nothing to do by default."""
        publisher = Publisher(
            self.logger, self.config, self.disk_pool,
            self.ubuntutest.main_archive)
        publisher.createSeriesAliases()
        self.assertEqual([], os.listdir(self.config.distsroot))

    def _assertPublishesSeriesAlias(self, publisher, expected):
        publisher.A_publish(False)
        publisher.C_writeIndexes(False)
        publisher.createSeriesAliases()
        self.assertTrue(os.path.exists(os.path.join(
            self.config.distsroot, expected)))
        for pocket, suffix in pocketsuffix.items():
            path = os.path.join(self.config.distsroot, "devel%s" % suffix)
            expected_path = os.path.join(
                self.config.distsroot, expected + suffix)
            # A symlink for the RELEASE pocket exists.  Symlinks for other
            # pockets only exist if the respective targets exist.
            if not suffix or os.path.exists(expected_path):
                self.assertTrue(os.path.islink(path))
                self.assertEqual(expected + suffix, os.readlink(path))
            else:
                self.assertFalse(os.path.islink(path))

    def testCreateSeriesAliasesChangesAlias(self):
        """createSeriesAliases tracks the latest published series."""
        publisher = Publisher(
            self.logger, self.config, self.disk_pool,
            self.ubuntutest.main_archive)
        self.ubuntutest.development_series_alias = "devel"
        # Oddly, hoary-test has a higher version than breezy-autotest.
        self.getPubSource(distroseries=self.ubuntutest["breezy-autotest"])
        self._assertPublishesSeriesAlias(publisher, "breezy-autotest")
        hoary_pub = self.getPubSource(
            distroseries=self.ubuntutest["hoary-test"])
        self._assertPublishesSeriesAlias(publisher, "hoary-test")
        hoary_pub.requestDeletion(self.ubuntutest.owner)
        self._assertPublishesSeriesAlias(publisher, "breezy-autotest")

    def testHtaccessForPrivatePPA(self):
        # A htaccess file is created for new private PPA's.

        ppa = self.factory.makeArchive(
            distribution=self.ubuntutest, private=True)
        ppa.buildd_secret = "geheim"

        # Set up the publisher for it and publish its repository.
        # setupArchiveDirs is what actually configures the htaccess file.
        getPublisher(ppa, [], self.logger).setupArchiveDirs()
        pubconf = getPubConfig(ppa)
        htaccess_path = os.path.join(pubconf.htaccessroot, ".htaccess")
        self.assertTrue(os.path.exists(htaccess_path))
        with open(htaccess_path, 'r') as htaccess_f:
            self.assertEqual(dedent("""
                AuthType           Basic
                AuthName           "Token Required"
                AuthUserFile       %s/.htpasswd
                Require            valid-user
                """) % pubconf.htaccessroot,
                htaccess_f.read())

        htpasswd_path = os.path.join(pubconf.htaccessroot, ".htpasswd")

        # Read it back in.
        with open(htpasswd_path, "r") as htpasswd_f:
            file_contents = htpasswd_f.readlines()

        self.assertEqual(1, len(file_contents))

        # The first line should be the buildd_secret.
        [user, password] = file_contents[0].strip().split(":", 1)
        self.assertEqual("buildd", user)
        # We can re-encrypt the buildd_secret and it should match the
        # one in the .htpasswd file.
        encrypted_secret = crypt.crypt(ppa.buildd_secret, password)
        self.assertEqual(encrypted_secret, password)

    def testWriteSuiteI18n(self):
        """Test i18n/Index writing."""
        publisher = Publisher(
            self.logger, self.config, self.disk_pool,
            self.ubuntutest.main_archive)
        i18n_root = os.path.join(
            self.config.distsroot, 'breezy-autotest', 'main', 'i18n')

        # Write a zero-length Translation-en file and compressed versions of
        # it.
        translation_en_index = RepositoryIndexFile(
            os.path.join(i18n_root, 'Translation-en'), self.config.temproot)
        translation_en_index.close()

        all_files = set()
        publisher._writeSuiteI18n(
            self.ubuntutest['breezy-autotest'],
            PackagePublishingPocket.RELEASE, 'main', all_files)

        # i18n/Index has the correct contents.
        translation_en = os.path.join(i18n_root, 'Translation-en.bz2')
        with open(translation_en) as translation_en_file:
            translation_en_contents = translation_en_file.read()
        i18n_index = self.parseI18nIndex(os.path.join(i18n_root, 'Index'))
        self.assertTrue('sha1' in i18n_index)
        self.assertEqual(1, len(i18n_index['sha1']))
        self.assertEqual(hashlib.sha1(translation_en_contents).hexdigest(),
                         i18n_index['sha1'][0]['sha1'])
        self.assertEqual(str(len(translation_en_contents)),
                         i18n_index['sha1'][0]['size'])

        # i18n/Index is scheduled for inclusion in Release.
        self.assertEqual(1, len(all_files))
        self.assertEqual(
            os.path.join('main', 'i18n', 'Index'), all_files.pop())

    def testWriteSuiteI18nMissingDirectory(self):
        """i18n/Index is not generated when the i18n directory is missing."""
        publisher = Publisher(
            self.logger, self.config, self.disk_pool,
            self.ubuntutest.main_archive)
        i18n_root = os.path.join(
            self.config.distsroot, 'breezy-autotest', 'main', 'i18n')

        publisher._writeSuiteI18n(
            self.ubuntutest['breezy-autotest'],
            PackagePublishingPocket.RELEASE, 'main', set())

        self.assertFalse(os.path.exists(os.path.join(i18n_root, 'Index')))

    def testWriteSuiteI18nEmptyDirectory(self):
        """i18n/Index is not generated when the i18n directory is empty."""
        publisher = Publisher(
            self.logger, self.config, self.disk_pool,
            self.ubuntutest.main_archive)
        i18n_root = os.path.join(
            self.config.distsroot, 'breezy-autotest', 'main', 'i18n')

        os.makedirs(i18n_root)

        publisher._writeSuiteI18n(
            self.ubuntutest['breezy-autotest'],
            PackagePublishingPocket.RELEASE, 'main', set())

        self.assertFalse(os.path.exists(os.path.join(i18n_root, 'Index')))


class TestArchiveIndices(TestPublisherBase):
    """Tests for the native publisher's index generation.

    Verifies that all Packages/Sources/Release files are generated when
    appropriate.
    """

    def runStepC(self, publisher):
        """Run the index generation step of the publisher."""
        publisher.C_writeIndexes(False)

    def assertIndices(self, publisher, suites, present=(), absent=()):
        """Assert that the given suites have correct indices."""
        for series, pocket in suites:
            self.assertIndicesForSuite(
                publisher, series, pocket, present, absent)

    def assertIndicesForSuite(self, publisher, series, pocket,
                              present=(), absent=()):
        """Assert that the suite has correct indices.

        Checks that the architecture tags in 'present' have Packages and
        Release files and are in the series' Release file, and confirms
        that those in 'absent' are not.
        """

        self.assertTrue(
            (series.name, pocket) in publisher.release_files_needed)

        arch_template = os.path.join(
            publisher._config.distsroot, series.getSuite(pocket), '%s/%s')

        release_template = os.path.join(arch_template, 'Release')
        packages_template = os.path.join(arch_template, 'Packages')
        sources_template = os.path.join(arch_template, 'Sources')
        release_path = os.path.join(
            publisher._config.distsroot, series.getSuite(pocket), 'Release')
        with open(release_path) as release_file:
            release_content = release_file.read()

        for comp in ('main', 'restricted', 'universe', 'multiverse'):
            # Check that source indices are present.
            for path in (release_template, sources_template):
                self.assertTrue(os.path.exists(path % (comp, 'source')))

            # Check that wanted binary indices are present.
            for arch_tag in present:
                arch = 'binary-' + arch_tag
                for path in (release_template, packages_template):
                    self.assertTrue(os.path.exists(path % (comp, arch)))
                self.assertTrue(arch in release_content)

            # Check that unwanted binary indices are absent.
            for arch_tag in absent:
                arch = 'binary-' + arch_tag
                self.assertFalse(os.path.exists(arch_template % (comp, arch)))
                self.assertFalse(arch in release_content)

    def testAllIndicesArePublished(self):
        """Test that indices are created for all components and archs."""
        # Dirty breezy-autotest with a source. Even though there are no
        # new binaries in the suite, all its indices will still be published.
        self.getPubSource()
        self.getPubSource(pocket=PackagePublishingPocket.PROPOSED)

        # Override the series status to FROZEN, which allows publication
        # of all pockets.
        self.ubuntutest.getSeries('breezy-autotest').status = (
            SeriesStatus.FROZEN)

        self.config = getPubConfig(self.ubuntutest.main_archive)
        publisher = Publisher(
            self.logger, self.config, self.disk_pool,
            self.ubuntutest.main_archive)

        publisher.A_publish(False)
        self.runStepC(publisher)
        publisher.D_writeReleaseFiles(False)

        self.assertIndices(
            publisher, [
                (self.breezy_autotest, PackagePublishingPocket.RELEASE),
                (self.breezy_autotest, PackagePublishingPocket.PROPOSED),
            ], present=['hppa', 'i386'])

    def testNoIndicesForDisabledArchitectures(self):
        """Test that no indices are created for disabled archs."""
        self.getPubBinaries()

        ds = self.ubuntutest.getSeries('breezy-autotest')
        ds.getDistroArchSeries('i386').enabled = False
        self.config = getPubConfig(self.ubuntutest.main_archive)

        publisher = Publisher(
            self.logger, self.config, self.disk_pool,
            self.ubuntutest.main_archive)

        publisher.A_publish(False)
        self.runStepC(publisher)
        publisher.D_writeReleaseFiles(False)

        self.assertIndicesForSuite(
            publisher, self.breezy_autotest, PackagePublishingPocket.RELEASE,
            present=['hppa'], absent=['i386'])

    def testWorldAndGroupReadablePackagesAndSources(self):
        """Test Packages.gz and Sources.gz files are world readable."""
        publisher = Publisher(
            self.logger, self.config, self.disk_pool,
            self.ubuntutest.main_archive, allowed_suites=[])

        self.getPubSource(filecontent='Hello world')
        publisher.A_publish(False)
        self.runStepC(publisher)

        # Find a Sources.gz and Packages.gz that were just published
        # in the breezy-autotest distroseries.
        sourcesgz_file = os.path.join(
            publisher._config.distsroot, 'breezy-autotest', 'main',
            'source', 'Sources.gz')
        packagesgz_file = os.path.join(
            publisher._config.distsroot, 'breezy-autotest', 'main',
            'binary-i386', 'Packages.gz')

        # What permissions are set on those files?
        for file in (sourcesgz_file, packagesgz_file):
            mode = stat.S_IMODE(os.stat(file).st_mode)
            self.assertEqual(
                (stat.S_IROTH | stat.S_IRGRP),
                (mode & (stat.S_IROTH | stat.S_IRGRP)),
                "%s is not world/group readable." % file)


class TestFtparchiveIndices(TestArchiveIndices):
    """Tests for the apt-ftparchive publisher's index generation."""

    def runStepC(self, publisher):
        """Run the apt-ftparchive index generation step of the publisher."""
        publisher.C_doFTPArchive(False)


class TestPublisherRepositorySignatures(TestPublisherBase):
    """Testing `Publisher` signature behaviour."""

    archive_publisher = None

    def tearDown(self):
        """Purge the archive root location. """
        super(TestPublisherRepositorySignatures, self).tearDown()
        if self.archive_publisher is not None:
            shutil.rmtree(self.archive_publisher._config.distsroot)

    def setupPublisher(self, archive):
        """Setup a `Publisher` instance for the given archive."""
        allowed_suites = []
        self.archive_publisher = getPublisher(
            archive, allowed_suites, self.logger)

    def _publishArchive(self, archive):
        """Publish a test source in the given archive.

        Publish files in pool, generate archive indexes and release files.
        """
        self.setupPublisher(archive)
        self.getPubSource(archive=archive)

        self.archive_publisher.A_publish(False)
        transaction.commit()
        self.archive_publisher.C_writeIndexes(False)
        self.archive_publisher.D_writeReleaseFiles(False)

    @property
    def suite_path(self):
        return os.path.join(
            self.archive_publisher._config.distsroot, 'breezy-autotest')

    @property
    def release_file_path(self):
        return os.path.join(self.suite_path, 'Release')

    @property
    def release_file_signature_path(self):
        return os.path.join(self.suite_path, 'Release.gpg')

    @property
    def public_key_path(self):
        return os.path.join(
            self.archive_publisher._config.distsroot, 'key.gpg')

    def testRepositorySignatureWithNoSigningKey(self):
        """Check publisher behaviour when signing repositories.

        Repository signing procedure is skipped for archive with no
        'signing_key'.
        """
        cprov = getUtility(IPersonSet).getByName('cprov')
        self.assertTrue(cprov.archive.signing_key is None)

        self._publishArchive(cprov.archive)

        # Release file exist but it doesn't have any signature.
        self.assertTrue(os.path.exists(self.release_file_path))
        self.assertFalse(os.path.exists(self.release_file_signature_path))

    def testRepositorySignatureWithSigningKey(self):
        """Check publisher behaviour when signing repositories.

        When the 'signing_key' is available every modified suite Release
        file gets signed with a detached signature name 'Release.gpg'.
        """
        cprov = getUtility(IPersonSet).getByName('cprov')
        self.assertTrue(cprov.archive.signing_key is None)

        # Start the test keyserver, so the signing_key can be uploaded.
        tac = KeyServerTac()
        tac.setUp()

        # Set a signing key for Celso's PPA.
        key_path = os.path.join(gpgkeysdir, 'ppa-sample@canonical.com.sec')
        IArchiveSigningKey(cprov.archive).setSigningKey(key_path)
        self.assertTrue(cprov.archive.signing_key is not None)

        self._publishArchive(cprov.archive)

        # Both, Release and Release.gpg exist.
        self.assertTrue(os.path.exists(self.release_file_path))
        self.assertTrue(os.path.exists(self.release_file_signature_path))

        # Release file signature is correct and was done by Celso's PPA
        # signing_key.
        with open(self.release_file_path) as release_file:
            with open(self.release_file_signature_path) as release_file_sig:
                signature = getUtility(IGPGHandler).getVerifiedSignature(
                    release_file.read(), release_file_sig.read())
        self.assertEqual(
            cprov.archive.signing_key.fingerprint, signature.fingerprint)

        # All done, turn test-keyserver off.
        tac.tearDown()


class TestPublisherLite(TestCaseWithFactory):
    """Lightweight unit tests for the publisher."""

    layer = ZopelessDatabaseLayer

    def makePublishableSeries(self, root_dir):
        """Create a `DistroSeries` ready for publishing.

        :param root_dir: A temporary directory for use as an archive root.
        """
        distro = self.factory.makeDistribution(publish_root_dir=root_dir)
        return self.factory.makeDistroSeries(
            distribution=distro, status=SeriesStatus.FROZEN)

    def getReleaseFileDir(self, root, distroseries, suite):
        """Locate the directory where a Release file should be.

        :param root: Archive root directory.
        :param distroseries: Published distroseries.
        :param suite: Published suite.
        """
        return os.path.join(
            root, distroseries.distribution.name, 'dists', suite)

    def makePublishablePackage(self, series):
        """Create a source publication ready for publishing."""
        return self.factory.makeSourcePackagePublishingHistory(
            distroseries=series, status=PackagePublishingStatus.PENDING)

    def makePublisher(self, archive_or_series):
        """Create a publisher for a given archive or distroseries."""
        if IDistroSeries.providedBy(archive_or_series):
            archive_or_series = archive_or_series.main_archive
        return getPublisher(archive_or_series, None, DevNullLogger())

    def makeFakeReleaseData(self):
        """Create a fake `debian.deb822.Release`.

        The object's dump method will write arbitrary text.  For testing
        purposes, the fake object will compare equal to a string holding
        this same text, encoded in the requested encoding.
        """
        class FakeReleaseData(unicode):
            def dump(self, output_file, encoding):
                output_file.write(self.encode(encoding))

        return FakeReleaseData(self.factory.getUniqueUnicode())

    def test_writeReleaseFile_dumps_release_file(self):
        # _writeReleaseFile writes a Release file for a suite.
        root = unicode(self.makeTemporaryDirectory())
        series = self.makePublishableSeries(root)
        spph = self.makePublishablePackage(series)
        suite = series.name + pocketsuffix[spph.pocket]
        releases_dir = self.getReleaseFileDir(root, series, suite)
        os.makedirs(releases_dir)
        release_data = self.makeFakeReleaseData()
        release_path = os.path.join(releases_dir, "Release")

        self.makePublisher(series)._writeReleaseFile(suite, release_data)

        self.assertTrue(file_exists(release_path))
        self.assertEqual(
            release_data.encode('utf-8'), file(release_path).read())

    def test_writeReleaseFile_creates_directory_if_necessary(self):
        # If the suite is new and its release directory does not exist
        # yet, _writeReleaseFile will create it.
        root = unicode(self.makeTemporaryDirectory())
        series = self.makePublishableSeries(root)
        spph = self.makePublishablePackage(series)
        suite = series.name + pocketsuffix[spph.pocket]
        release_data = self.makeFakeReleaseData()
        release_path = os.path.join(
            self.getReleaseFileDir(root, series, suite), "Release")

        self.makePublisher(series)._writeReleaseFile(suite, release_data)

        self.assertTrue(file_exists(release_path))

    def test_syncTimestamps_makes_timestamps_match_latest(self):
        root = unicode(self.makeTemporaryDirectory())
        series = self.makePublishableSeries(root)
        location = self.getReleaseFileDir(root, series, series.name)
        os.makedirs(location)
        now = time.time()
        path_times = (("a", now), ("b", now - 1), ("c", now - 2))
        for path, timestamp in path_times:
            with open(os.path.join(location, path), "w"):
                pass
            os.utime(os.path.join(location, path), (timestamp, timestamp))

        paths = [path for path, _ in path_times]
        self.makePublisher(series)._syncTimestamps(series.name, set(paths))

        timestamps = set(
            os.stat(os.path.join(location, path)).st_mtime for path in paths)
        self.assertEqual(1, len(timestamps))
        # The filesystem may round off subsecond parts of timestamps.
        self.assertEqual(int(now), int(list(timestamps)[0]))

    def test_subcomponents(self):
        primary = self.factory.makeArchive(purpose=ArchivePurpose.PRIMARY)
        self.assertEqual(
            ['debian-installer'],
            self.makePublisher(primary).subcomponents)
        primary.publish_debug_symbols = True
        self.assertEqual(
            ['debian-installer', 'debug'],
            self.makePublisher(primary).subcomponents)

        partner = self.factory.makeArchive(purpose=ArchivePurpose.PARTNER)
        self.assertEqual([], self.makePublisher(partner).subcomponents)
