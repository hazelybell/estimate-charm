# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from doctest import DocTestSuite
import hashlib
import os
from textwrap import dedent
from unittest import TestLoader

import transaction

from lp.archiveuploader.tagfiles import parse_tagfile
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.services.features.testing import FeatureFixture
from lp.services.log.logger import DevNullLogger
from lp.services.tarfile_helpers import LaunchpadWriteTarFile
from lp.soyuz.enums import PackagePublishingStatus
from lp.soyuz.scripts.gina import ExecutionError
from lp.soyuz.scripts.gina.archive import (
    ArchiveComponentItems,
    PackagesMap,
    )
from lp.soyuz.scripts.gina.dominate import dominate_imported_source_packages
import lp.soyuz.scripts.gina.handlers
from lp.soyuz.scripts.gina.handlers import (
    BinaryPackagePublisher,
    ImporterHandler,
    SourcePackagePublisher,
    )
from lp.soyuz.scripts.gina.packages import (
    BinaryPackageData,
    SourcePackageData,
    )
from lp.soyuz.scripts.gina.runner import import_sourcepackages
from lp.testing import TestCaseWithFactory
from lp.testing.faketransaction import FakeTransaction
from lp.testing.layers import (
    LaunchpadZopelessLayer,
    ZopelessDatabaseLayer,
    )


class FakePackagesMap:
    def __init__(self, src_map):
        self.src_map = src_map


class TestGina(TestCaseWithFactory):

    layer = ZopelessDatabaseLayer

    def test_dominate_imported_source_packages_dominates_imports(self):
        # dominate_imported_source_packages dominates the source
        # packages that Gina imports.
        logger = DevNullLogger()
        txn = FakeTransaction()
        series = self.factory.makeDistroSeries()
        pocket = PackagePublishingPocket.RELEASE
        package = self.factory.makeSourcePackageName()

        # Realistic situation: there's an older, superseded publication;
        # a series of active ones; and a newer, pending publication
        # that's not in the Sources lists yet.
        # Gina dominates the Published ones and leaves the rest alone.
        old_spph = self.factory.makeSourcePackagePublishingHistory(
            distroseries=series, archive=series.main_archive,
            pocket=pocket, status=PackagePublishingStatus.SUPERSEDED,
            sourcepackagerelease=self.factory.makeSourcePackageRelease(
                sourcepackagename=package, version='1.0'))

        active_spphs = [
            self.factory.makeSourcePackagePublishingHistory(
                distroseries=series, archive=series.main_archive,
                pocket=pocket, status=PackagePublishingStatus.PUBLISHED,
                sourcepackagerelease=self.factory.makeSourcePackageRelease(
                    sourcepackagename=package, version=version))
            for version in ['1.1', '1.1.1', '1.1.1.1']]

        new_spph = self.factory.makeSourcePackagePublishingHistory(
            distroseries=series, archive=series.main_archive,
            pocket=pocket, status=PackagePublishingStatus.PENDING,
            sourcepackagerelease=self.factory.makeSourcePackageRelease(
                sourcepackagename=package, version='1.2'))

        spphs = [old_spph] + active_spphs + [new_spph]

        # Of the active publications, in this scenario, only one version
        # matches what Gina finds in the Sources list.  It stays
        # published; older active publications are superseded, newer
        # ones deleted.
        dominate_imported_source_packages(
            txn, logger, series.distribution.name, series.name, pocket,
            FakePackagesMap({package.name: [{'Version': '1.1.1'}]}))
        self.assertEqual([
            PackagePublishingStatus.SUPERSEDED,
            PackagePublishingStatus.SUPERSEDED,
            PackagePublishingStatus.PUBLISHED,
            PackagePublishingStatus.DELETED,
            PackagePublishingStatus.PENDING,
            ],
            [pub.status for pub in spphs])

    def test_dominate_imported_source_packages_dominates_deletions(self):
        # dominate_imported_source_packages dominates the source
        # packages that have been deleted from the Sources lists that
        # Gina imports.
        series = self.factory.makeDistroSeries()
        pocket = PackagePublishingPocket.RELEASE
        package = self.factory.makeSourcePackageName()
        pubs = [
            self.factory.makeSourcePackagePublishingHistory(
                archive=series.main_archive, distroseries=series,
                pocket=pocket, status=PackagePublishingStatus.PUBLISHED,
                sourcepackagerelease=self.factory.makeSourcePackageRelease(
                    sourcepackagename=package, version=version))
            for version in ['1.0', '1.1', '1.1a']]

        # In this scenario, 1.0 is a superseded release.
        pubs[0].supersede()
        logger = DevNullLogger()
        txn = FakeTransaction()
        dominate_imported_source_packages(
            txn, logger, series.distribution.name, series.name, pocket,
            FakePackagesMap({}))

        # The older, superseded release stays superseded; but the
        # releases that dropped out of the imported Sources list without
        # known successors are marked deleted.
        self.assertEqual([
            PackagePublishingStatus.SUPERSEDED,
            PackagePublishingStatus.DELETED,
            PackagePublishingStatus.DELETED,
            ],
            [pub.status for pub in pubs])


class TestSourcePackageData(TestCaseWithFactory):

    layer = ZopelessDatabaseLayer

    def test_unpack_dsc_with_vendor(self):
        # Some source packages unpack differently depending on dpkg's idea
        # of the "vendor", and in extreme cases may even fail with some
        # vendors.  gina always sets the vendor to the target distribution
        # name to ensure that it unpacks packages as if unpacking on that
        # distribution.
        archive_root = self.useTempDir()
        pool_dir = os.path.join(archive_root, "pool/main/f/foo")
        os.makedirs(pool_dir)

        # Synthesise a package that can be unpacked with DEB_VENDOR=debian
        # but not with DEB_VENDOR=ubuntu.
        with open(os.path.join(
            pool_dir, "foo_1.0.orig.tar.gz"), "wb+") as buffer:
            orig_tar = LaunchpadWriteTarFile(buffer)
            orig_tar.add_directory("foo-1.0")
            orig_tar.close()
            buffer.seek(0)
            orig_tar_contents = buffer.read()
        with open(os.path.join(
            pool_dir, "foo_1.0-1.debian.tar.gz"), "wb+") as buffer:
            debian_tar = LaunchpadWriteTarFile(buffer)
            debian_tar.add_file("debian/source/format", "3.0 (quilt)\n")
            debian_tar.add_file(
                "debian/patches/ubuntu.series", "--- corrupt patch\n")
            debian_tar.add_file("debian/rules", "")
            debian_tar.close()
            buffer.seek(0)
            debian_tar_contents = buffer.read()
        dsc_path = os.path.join(pool_dir, "foo_1.0-1.dsc")
        with open(dsc_path, "w") as dsc:
            dsc.write(dedent("""\
                Format: 3.0 (quilt)
                Source: foo
                Binary: foo
                Architecture: all
                Version: 1.0-1
                Maintainer: Foo Bar <foo.bar@canonical.com>
                Files:
                 %s %s foo_1.0.orig.tar.gz
                 %s %s foo_1.0-1.debian.tar.gz
                """ % (
                    hashlib.md5(orig_tar_contents).hexdigest(),
                    len(orig_tar_contents),
                    hashlib.md5(debian_tar_contents).hexdigest(),
                    len(debian_tar_contents))))

        dsc_contents = parse_tagfile(dsc_path)
        dsc_contents["Directory"] = pool_dir
        dsc_contents["Package"] = "foo"
        dsc_contents["Component"] = "main"
        dsc_contents["Section"] = "misc"

        sp_data = SourcePackageData(**dsc_contents)
        # Unpacking this in an Ubuntu context fails.
        self.assertRaises(
            ExecutionError, sp_data.do_package, "ubuntu", archive_root)
        # But all is well in a Debian context.
        sp_data.do_package("debian", archive_root)


class TestSourcePackagePublisher(TestCaseWithFactory):

    layer = ZopelessDatabaseLayer

    def test_publish_creates_published_publication(self):
        maintainer = self.factory.makePerson()
        series = self.factory.makeDistroSeries()
        section = self.factory.makeSection()
        pocket = PackagePublishingPocket.RELEASE
        spr = self.factory.makeSourcePackageRelease()

        publisher = SourcePackagePublisher(series, pocket, None)
        publisher.publish(spr, SourcePackageData(
            component='main', section=section.name, version='1.0',
            maintainer=maintainer.preferredemail, architecture='all',
            files='foo.py', binaries='foo.py'))

        [spph] = series.main_archive.getPublishedSources()
        self.assertEqual(PackagePublishingStatus.PUBLISHED, spph.status)


class TestBinaryPackagePublisher(TestCaseWithFactory):

    layer = ZopelessDatabaseLayer

    def test_publish_creates_published_publication(self):
        maintainer = self.factory.makePerson()
        series = self.factory.makeDistroArchSeries()
        section = self.factory.makeSection()
        pocket = PackagePublishingPocket.RELEASE
        bpr = self.factory.makeBinaryPackageRelease()

        publisher = BinaryPackagePublisher(series, pocket, None)
        publisher.publish(bpr, BinaryPackageData(
            component='main', section=section.name, version='1.0',
            maintainer=maintainer.preferredemail, architecture='all',
            files='foo.py', binaries='foo.py', size=128, installed_size=1024,
            md5sum='e83b5dd68079d727a494a469d40dc8db', description='test',
            summary='Test!'))

        [bpph] = series.main_archive.getAllPublishedBinaries()
        self.assertEqual(PackagePublishingStatus.PUBLISHED, bpph.status)


class TestRunner(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def test_import_sourcepackages_skip(self):
        # gina can be told to skip particular source versions by setting
        # soyuz.gina.skip_source_versions to a space-separated list of
        # $DISTRO/$NAME/$VERSION.
        series = self.factory.makeDistroSeries()

        archive_root = os.path.join(
            os.path.dirname(__file__), 'gina_test_archive')
        arch_component_items = ArchiveComponentItems(
            archive_root, 'lenny', ['main'], [], True)
        packages_map = PackagesMap(arch_component_items)
        importer_handler = ImporterHandler(
            transaction, series.distribution.name, series.name, archive_root,
            PackagePublishingPocket.RELEASE, None)

        def import_and_get_versions():
            import_sourcepackages(
                series.distribution.name, packages_map, archive_root,
                importer_handler)
            return [
                p.source_package_version
                for p in series.getPublishedSources('archive-copier')]

        # Our test archive has archive-copier 0.1.5 and 0.3.6 With
        # soyuz.gina.skip_source_versions set to
        # '$distro/archive-copier/0.1.5', an import will grab only
        # 0.3.6.
        skiplist = '%s/archive-copier/0.1.5' % series.distribution.name
        with FeatureFixture({'soyuz.gina.skip_source_versions': skiplist}):
            self.assertContentEqual(['0.3.6'], import_and_get_versions())

        # Importing again without the feature flag removed grabs both.
        self.assertContentEqual(['0.1.5', '0.3.6'], import_and_get_versions())


def test_suite():
    suite = TestLoader().loadTestsFromName(__name__)
    suite.addTest(DocTestSuite(lp.soyuz.scripts.gina.handlers))
    return suite
