# Copyright 2011-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test copying of custom package uploads for a new `DistroSeries`."""

__metaclass__ = type

from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.interfaces.series import SeriesStatus
from lp.soyuz.enums import (
    PackageUploadCustomFormat,
    PackageUploadStatus,
    )
from lp.soyuz.scripts.custom_uploads_copier import CustomUploadsCopier
from lp.testing import TestCaseWithFactory
from lp.testing.fakemethod import FakeMethod
from lp.testing.layers import (
    LaunchpadZopelessLayer,
    ZopelessLayer,
    )


def list_custom_uploads(distroseries):
    """Return a list of all `PackageUploadCustom`s for `distroseries`."""
    return sum(
        [
            list(upload.customfiles)
            for upload in distroseries.getPackageUploads()],
        [])


class FakeDistroSeries:
    """Fake `DistroSeries` for test copiers that don't really need one."""


class FakeLibraryFileAlias:
    def __init__(self, filename):
        self.filename = filename


class FakeUpload:
    def __init__(self, customformat, filename):
        self.customformat = customformat
        self.libraryfilealias = FakeLibraryFileAlias(filename)


class CommonTestHelpers:
    """Helper(s) for these tests."""
    def makeVersion(self):
        """Create a fake version string."""
        return "%d.%d-%s" % (
            self.factory.getUniqueInteger(),
            self.factory.getUniqueInteger(),
            self.factory.getUniqueString())


class TestCustomUploadsCopierLite(TestCaseWithFactory, CommonTestHelpers):
    """Light-weight low-level tests for `CustomUploadsCopier`."""

    layer = ZopelessLayer

    def test_isCopyable_matches_copyable_types(self):
        # isCopyable checks a custom upload's customformat field to
        # determine whether the upload is a candidate for copying.  It
        # approves only those whose customformats are in copyable_types.
        uploads = [
            FakeUpload(custom_type, None)
            for custom_type in PackageUploadCustomFormat.items]

        copier = CustomUploadsCopier(FakeDistroSeries())
        copied_uploads = filter(copier.isCopyable, uploads)
        self.assertContentEqual(
            CustomUploadsCopier.copyable_types,
            [upload.customformat for upload in copied_uploads])

    def test_getKey_calls_correct_custom_upload_method(self):
        # getKey calls the getSeriesKey method on the correct custom upload.
        class FakeCustomUpload:
            @classmethod
            def getSeriesKey(cls, tarfile_path):
                return "dummy"

        copier = CustomUploadsCopier(FakeDistroSeries())
        copier.copyable_types = {
            PackageUploadCustomFormat.DEBIAN_INSTALLER: FakeCustomUpload,
            }
        custom_format, series_key = copier.getKey(
            FakeUpload(PackageUploadCustomFormat.DEBIAN_INSTALLER, "anything"))
        self.assertEqual(
            PackageUploadCustomFormat.DEBIAN_INSTALLER, custom_format)
        self.assertEqual("dummy", series_key)

    def test_getKey_returns_None_on_name_mismatch(self):
        # If extractSeriesKey returns None, getKey also returns None.
        copier = CustomUploadsCopier(FakeDistroSeries())
        copier.extractSeriesKey = FakeMethod()
        self.assertIsNone(
            copier.getKey(FakeUpload(
                PackageUploadCustomFormat.DEBIAN_INSTALLER,
                "bad-filename.tar")))


class TestCustomUploadsCopier(TestCaseWithFactory, CommonTestHelpers):
    """Heavyweight `CustomUploadsCopier` tests."""

    # Alas, PackageUploadCustom relies on the Librarian.
    layer = LaunchpadZopelessLayer

    def makeUpload(self, distroseries=None, archive=None, pocket=None,
                   custom_type=PackageUploadCustomFormat.DEBIAN_INSTALLER,
                   version=None, arch=None, component=None):
        """Create a `PackageUploadCustom`."""
        if distroseries is None:
            distroseries = self.factory.makeDistroSeries()
        package_name = self.factory.getUniqueString("package")
        if version is None:
            version = self.makeVersion()
        if custom_type == PackageUploadCustomFormat.DDTP_TARBALL:
            if component is None:
                component = self.factory.getUniqueString()
            filename = "%s.tar.gz" % "_".join(
                [package_name, component, version])
        else:
            if arch is None:
                arch = self.factory.getUniqueString()
            filename = "%s.tar.gz" % "_".join([package_name, version, arch])
        package_upload = self.factory.makeCustomPackageUpload(
            distroseries=distroseries, archive=archive, pocket=pocket,
            custom_type=custom_type, filename=filename)
        return package_upload.customfiles[0]

    def test_copies_custom_upload(self):
        # CustomUploadsCopier copies custom uploads from one series to
        # another.
        current_series = self.factory.makeDistroSeries()
        original_upload = self.makeUpload(current_series, arch='alpha')
        new_series = self.factory.makeDistroSeries(
            distribution=current_series.distribution,
            previous_series=current_series)
        self.factory.makeDistroArchSeries(
            distroseries=new_series, architecturetag='alpha')

        CustomUploadsCopier(new_series).copy(current_series)

        [copied_upload] = list_custom_uploads(new_series)
        self.assertEqual(
            original_upload.libraryfilealias, copied_upload.libraryfilealias)

    def test_is_idempotent(self):
        # It's safe to perform the same copy more than once; the uploads
        # get copied only once.
        current_series = self.factory.makeDistroSeries()
        self.makeUpload(current_series)
        new_series = self.factory.makeDistroSeries(
            distribution=current_series.distribution,
            previous_series=current_series)

        copier = CustomUploadsCopier(new_series)
        copier.copy(current_series)
        uploads_after_first_copy = list_custom_uploads(new_series)
        copier.copy(current_series)
        uploads_after_redundant_copy = list_custom_uploads(new_series)

        self.assertEqual(
            uploads_after_first_copy, uploads_after_redundant_copy)

    def test_getCandidateUploads_filters_by_distroseries(self):
        # getCandidateUploads ignores uploads for other distroseries.
        source_series = self.factory.makeDistroSeries()
        matching_upload = self.makeUpload(source_series)
        nonmatching_upload = self.makeUpload()
        copier = CustomUploadsCopier(FakeDistroSeries())
        candidate_uploads = copier.getCandidateUploads(source_series)
        self.assertContentEqual([matching_upload], candidate_uploads)
        self.assertNotIn(nonmatching_upload, candidate_uploads)

    def test_getCandidateUploads_filters_upload_types(self):
        # getCandidateUploads returns only uploads of the types listed
        # in copyable_types; other types of upload are ignored.
        source_series = self.factory.makeDistroSeries()
        for custom_format in PackageUploadCustomFormat.items:
            self.makeUpload(source_series, custom_type=custom_format)

        copier = CustomUploadsCopier(FakeDistroSeries())
        candidate_uploads = copier.getCandidateUploads(source_series)
        copied_types = [upload.customformat for upload in candidate_uploads]
        self.assertContentEqual(
            CustomUploadsCopier.copyable_types, copied_types)

    def test_getCandidateUploads_ignores_other_attachments(self):
        # A PackageUpload can have multiple PackageUploadCustoms
        # attached, potentially of different types.  getCandidateUploads
        # ignores PackageUploadCustoms of types that aren't supposed to
        # be copied, even if they are attached to PackageUploads that
        # also have PackageUploadCustoms that do need to be copied.
        source_series = self.factory.makeDistroSeries()
        package_upload = self.factory.makePackageUpload(
            distroseries=source_series, archive=source_series.main_archive)
        library_file = self.factory.makeLibraryFileAlias()
        matching_upload = package_upload.addCustom(
            library_file, PackageUploadCustomFormat.DEBIAN_INSTALLER)
        nonmatching_upload = package_upload.addCustom(
            library_file, PackageUploadCustomFormat.ROSETTA_TRANSLATIONS)
        copier = CustomUploadsCopier(FakeDistroSeries())
        candidates = copier.getCandidateUploads(source_series)
        self.assertContentEqual([matching_upload], candidates)
        self.assertNotIn(nonmatching_upload, candidates)

    def test_getCandidateUploads_orders_newest_to_oldest(self):
        # getCandidateUploads returns its PackageUploadCustoms ordered
        # from newest to oldest.
        # XXX JeroenVermeulen 2011-08-17, bug=827967: Should compare by
        # Debian version string, not id.
        source_series = self.factory.makeDistroSeries()
        for counter in xrange(5):
            self.makeUpload(source_series)
        copier = CustomUploadsCopier(FakeDistroSeries())
        candidate_ids = [
            upload.id for upload in copier.getCandidateUploads(source_series)]
        self.assertEqual(sorted(candidate_ids, reverse=True), candidate_ids)

    def test_getCandidateUploads_filters_by_pocket(self):
        # getCandidateUploads ignores uploads for other pockets.
        source_series = self.factory.makeDistroSeries()
        matching_upload = self.makeUpload(
            source_series, pocket=PackagePublishingPocket.PROPOSED)
        nonmatching_upload = self.makeUpload(
            source_series, pocket=PackagePublishingPocket.BACKPORTS)
        copier = CustomUploadsCopier(FakeDistroSeries())
        candidate_uploads = copier.getCandidateUploads(
            source_series, PackagePublishingPocket.PROPOSED)
        self.assertContentEqual([matching_upload], candidate_uploads)
        self.assertNotIn(nonmatching_upload, candidate_uploads)

    def test_getKey_includes_format_and_architecture(self):
        # The key returned by getKey consists of custom upload type,
        # and architecture.
        source_series = self.factory.makeDistroSeries()
        upload = self.makeUpload(
            source_series, custom_type=PackageUploadCustomFormat.DIST_UPGRADER,
            arch='mips')
        copier = CustomUploadsCopier(FakeDistroSeries())
        expected_key = (PackageUploadCustomFormat.DIST_UPGRADER, 'mips')
        self.assertEqual(expected_key, copier.getKey(upload))

    def test_getKey_ddtp_includes_format_and_component(self):
        # The key returned by getKey for a ddtp-tarball upload consists of
        # custom upload type, and component.
        source_series = self.factory.makeDistroSeries()
        upload = self.makeUpload(
            source_series, custom_type=PackageUploadCustomFormat.DDTP_TARBALL,
            component='restricted')
        copier = CustomUploadsCopier(FakeDistroSeries())
        expected_key = (PackageUploadCustomFormat.DDTP_TARBALL, 'restricted')
        self.assertEqual(expected_key, copier.getKey(upload))

    def test_getLatestUploads_indexes_uploads_by_key(self):
        # getLatestUploads returns a dict of uploads, indexed by keys
        # returned by getKey.
        source_series = self.factory.makeDistroSeries()
        upload = self.makeUpload(source_series)
        copier = CustomUploadsCopier(FakeDistroSeries())
        self.assertEqual(
            {copier.getKey(upload): upload},
            copier.getLatestUploads(source_series))

    def test_getLatestUploads_filters_superseded_uploads(self):
        # getLatestUploads returns only the latest upload for a given
        # distroseries, type, package, and architecture.  Any older
        # uploads with the same distroseries, type, package name, and
        # architecture are ignored.
        source_series = self.factory.makeDistroSeries()
        uploads = [
            self.makeUpload(
                source_series, version='1.0.%d' % counter, arch='ppc')
            for counter in xrange(3)]

        copier = CustomUploadsCopier(FakeDistroSeries())
        self.assertContentEqual(
            uploads[-1:], copier.getLatestUploads(source_series).values())

    def test_getLatestUploads_bundles_versions(self):
        # getLatestUploads sees an upload as superseding an older one
        # for the same distroseries, type, package name, and
        # architecture even if they have different versions.
        source_series = self.factory.makeDistroSeries()
        uploads = [
            self.makeUpload(source_series, arch='i386')
            for counter in xrange(2)]
        copier = CustomUploadsCopier(FakeDistroSeries())
        self.assertContentEqual(
            uploads[-1:], copier.getLatestUploads(source_series).values())

    def test_isObsolete_returns_False_if_no_equivalent_in_target(self):
        # isObsolete returns False if the upload in question has no
        # equivalent in the target series.
        source_series = self.factory.makeDistroSeries()
        upload = self.makeUpload(source_series)
        target_series = self.factory.makeDistroSeries()
        copier = CustomUploadsCopier(target_series)
        self.assertFalse(
            copier.isObsolete(upload, copier.getLatestUploads(target_series)))

    def test_isObsolete_returns_False_if_target_has_older_equivalent(self):
        # isObsolete returns False if the target has an equivlalent of
        # the upload in question, but it's older than the version the
        # source series has.
        source_series = self.factory.makeDistroSeries()
        target_series = self.factory.makeDistroSeries()
        self.makeUpload(target_series, arch='ppc64')
        source_upload = self.makeUpload(source_series, arch='ppc64')
        copier = CustomUploadsCopier(target_series)
        self.assertFalse(
            copier.isObsolete(
                source_upload, copier.getLatestUploads(target_series)))

    def test_isObsolete_returns_True_if_target_has_newer_equivalent(self):
        # isObsolete returns False if the target series already has a
        # newer equivalent of the upload in question (as would be the
        # case, for instance, if the upload had already been copied).
        source_series = self.factory.makeDistroSeries()
        source_upload = self.makeUpload(source_series, arch='alpha')
        target_series = self.factory.makeDistroSeries()
        self.makeUpload(target_series, arch='alpha')
        copier = CustomUploadsCopier(target_series)
        self.assertTrue(
            copier.isObsolete(
                source_upload, copier.getLatestUploads(target_series)))

    def test_isForValidDAS_returns_False_with_dead_arch(self):
        source_series = self.factory.makeDistroSeries()
        source_upload = self.makeUpload(source_series, arch='alpha')
        target_series = self.factory.makeDistroSeries()
        copier = CustomUploadsCopier(target_series)
        self.assertFalse(copier.isForValidDAS(source_upload))

    def test_isForValidDAS_returns_False_with_disabled_arch(self):
        source_series = self.factory.makeDistroSeries()
        source_upload = self.makeUpload(source_series, arch='alpha')
        target_series = self.factory.makeDistroSeries()
        self.factory.makeDistroArchSeries(
            distroseries=target_series, architecturetag='alpha', enabled=False)
        copier = CustomUploadsCopier(target_series)
        self.assertFalse(copier.isForValidDAS(source_upload))

    def test_isForValidDAS_returns_True(self):
        source_series = self.factory.makeDistroSeries()
        source_upload = self.makeUpload(source_series, arch='alpha')
        target_series = self.factory.makeDistroSeries()
        self.factory.makeDistroArchSeries(
            distroseries=target_series, architecturetag='alpha')
        copier = CustomUploadsCopier(target_series)
        self.assertTrue(copier.isForValidDAS(source_upload))

    def test_isForValidDAS_returns_True_for_DDTP(self):
        source_series = self.factory.makeDistroSeries()
        source_upload = self.makeUpload(
            source_series, custom_type=PackageUploadCustomFormat.DDTP_TARBALL)
        target_series = self.factory.makeDistroSeries()
        copier = CustomUploadsCopier(target_series)
        self.assertTrue(copier.isForValidDAS(source_upload))

    def test_copyUpload_creates_upload(self):
        # copyUpload creates a new upload that's very similar to the
        # original, but for the target series.
        original_upload = self.makeUpload()
        target_series = self.factory.makeDistroSeries()
        copier = CustomUploadsCopier(
            target_series, target_archive=target_series.main_archive)
        copied_upload = copier.copyUpload(original_upload)
        self.assertEqual([copied_upload], list_custom_uploads(target_series))
        original_pu = original_upload.packageupload
        copied_pu = copied_upload.packageupload
        self.assertNotEqual(original_pu, copied_pu)
        self.assertEqual(
            original_upload.customformat, copied_upload.customformat)
        self.assertEqual(
            original_upload.libraryfilealias, copied_upload.libraryfilealias)
        self.assertEqual(original_pu.changesfile, copied_pu.changesfile)

    def test_copyUpload_copies_into_release_pocket(self):
        # copyUpload copies the original upload into the release pocket,
        # even though the original is more likely to be in another
        # pocket.
        original_upload = self.makeUpload(
            pocket=PackagePublishingPocket.UPDATES)
        target_series = self.factory.makeDistroSeries()
        copier = CustomUploadsCopier(target_series)
        copied_pu = copier.copyUpload(original_upload).packageupload
        self.assertEqual(PackagePublishingPocket.RELEASE, copied_pu.pocket)

    def test_copyUpload_to_updates_pocket(self):
        # copyUpload copies an upload between pockets in the same series if
        # requested.
        series = self.factory.makeDistroSeries(status=SeriesStatus.CURRENT)
        original_upload = self.makeUpload(
            distroseries=series, pocket=PackagePublishingPocket.PROPOSED)
        copier = CustomUploadsCopier(
            series, target_pocket=PackagePublishingPocket.UPDATES)
        copied_pu = copier.copyUpload(original_upload).packageupload
        self.assertEqual(PackagePublishingPocket.UPDATES, copied_pu.pocket)

    def test_copyUpload_accepts_upload(self):
        # Uploads created by copyUpload are automatically accepted.
        original_upload = self.makeUpload()
        target_series = self.factory.makeDistroSeries()
        copier = CustomUploadsCopier(target_series)
        copied_pu = copier.copyUpload(original_upload).packageupload
        self.assertEqual(PackageUploadStatus.ACCEPTED, copied_pu.status)

    def test_copyUpload_unapproves_uefi_from_different_archive(self):
        # Copies of UEFI custom uploads to a primary archive are set to
        # UNAPPROVED, since they will normally end up being signed.
        target_series = self.factory.makeDistroSeries()
        archive = self.factory.makeArchive(
            distribution=target_series.distribution)
        original_upload = self.makeUpload(
            archive=archive, custom_type=PackageUploadCustomFormat.UEFI)
        copier = CustomUploadsCopier(
            target_series, target_archive=target_series.main_archive)
        copied_pu = copier.copyUpload(original_upload).packageupload
        self.assertEqual(PackageUploadStatus.UNAPPROVED, copied_pu.status)

    def test_copyUpload_approves_uefi_from_same_archive(self):
        # Copies of UEFI custom uploads within the same archive are
        # automatically accepted, since they have already been signed.
        original_upload = self.makeUpload(
            custom_type=PackageUploadCustomFormat.UEFI)
        target_series = self.factory.makeDistroSeries()
        copier = CustomUploadsCopier(target_series)
        copied_pu = copier.copyUpload(original_upload).packageupload
        self.assertEqual(PackageUploadStatus.ACCEPTED, copied_pu.status)

    def test_copyUpload_approves_uefi_to_ppa(self):
        # Copies of UEFI custom uploads to a PPA are automatically accepted,
        # since PPAs have much more limited upload permissions than the main
        # archive, and in any case PPAs do not have an upload approval
        # workflow.
        original_upload = self.makeUpload(
            custom_type=PackageUploadCustomFormat.UEFI)
        target_series = self.factory.makeDistroSeries()
        target_archive = self.factory.makeArchive(
            distribution=target_series.distribution)
        copier = CustomUploadsCopier(
            target_series, target_archive=target_archive)
        copied_pu = copier.copyUpload(original_upload).packageupload
        self.assertEqual(PackageUploadStatus.ACCEPTED, copied_pu.status)

    def test_copyUpload_archive_None_copies_within_archive(self):
        # If CustomUploadsCopier was created with no target archive,
        # copyUpload copies an upload to the same archive as the original
        # upload.
        original_upload = self.makeUpload()
        original_pu = original_upload.packageupload
        target_series = self.factory.makeDistroSeries()
        copier = CustomUploadsCopier(target_series)
        copied_pu = copier.copyUpload(original_upload).packageupload
        self.assertEqual(PackageUploadStatus.ACCEPTED, copied_pu.status)
        self.assertEqual(original_pu.archive, copied_pu.archive)

    def test_copyUpload_to_specified_archive(self):
        # If CustomUploadsCopier was created with a target archive,
        # copyUpload copies an upload to that archive.
        series = self.factory.makeDistroSeries()
        original_upload = self.makeUpload(distroseries=series)
        archive = self.factory.makeArchive(distribution=series.distribution)
        copier = CustomUploadsCopier(series, target_archive=archive)
        copied_pu = copier.copyUpload(original_upload).packageupload
        self.assertEqual(PackageUploadStatus.ACCEPTED, copied_pu.status)
        self.assertEqual(archive, copied_pu.archive)

    def test_copyUpload_from_ppa_to_main_archive(self):
        # copyUpload can copy uploads from a PPA to the main archive.
        series = self.factory.makeDistroSeries()
        archive = self.factory.makeArchive(distribution=series.distribution)
        original_upload = self.makeUpload(distroseries=series, archive=archive)
        copier = CustomUploadsCopier(
            series, target_archive=series.main_archive)
        copied_pu = copier.copyUpload(original_upload).packageupload
        self.assertEqual(PackageUploadStatus.ACCEPTED, copied_pu.status)
        self.assertEqual(series.main_archive, copied_pu.archive)
