# -*- coding: utf-8 -*-
# NOTE: The first line above must stay first; do not move the copyright
# notice to the top.  See http://www.python.org/dev/peps/pep-0263/.
#
# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test SourcePackageRelease."""

__metaclass__ = type

from textwrap import dedent

import transaction
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.buildmaster.enums import BuildStatus
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.services.tarfile_helpers import LaunchpadWriteTarFile
from lp.soyuz.enums import (
    ArchivePurpose,
    PackagePublishingStatus,
    SourcePackageFormat,
    )
from lp.soyuz.interfaces.publishing import active_publishing_status
from lp.soyuz.interfaces.sourcepackageformat import (
    ISourcePackageFormatSelectionSet,
    )
from lp.soyuz.scripts.packagecopier import do_copy
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.dbuser import dbuser
from lp.testing.layers import (
    LaunchpadFunctionalLayer,
    LaunchpadZopelessLayer,
    ZopelessDatabaseLayer,
    )
from lp.translations.interfaces.translationimportqueue import (
    ITranslationImportQueue,
    )


class TestSourcePackageRelease(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def test_uploader_no_uploader(self):
        spr = self.factory.makeSourcePackageRelease()
        self.assertIs(None, spr.uploader)

    def test_uploader_dsc_package(self):
        owner = self.factory.makePerson()
        key = self.factory.makeGPGKey(owner)
        spr = self.factory.makeSourcePackageRelease(dscsigningkey=key)
        self.assertEqual(owner, spr.uploader)

    def test_uploader_recipe(self):
        recipe_build = self.factory.makeSourcePackageRecipeBuild()
        spr = self.factory.makeSourcePackageRelease(
            source_package_recipe_build=recipe_build)
        self.assertEqual(recipe_build.requester, spr.uploader)

    def test_user_defined_fields(self):
        release = self.factory.makeSourcePackageRelease(
                user_defined_fields=[
                    ("Python-Version", ">= 2.4"),
                    ("Other", "Bla")])
        self.assertEquals([
            ["Python-Version", ">= 2.4"],
            ["Other", "Bla"]], release.user_defined_fields)

    def test_homepage_default(self):
        # By default, no homepage is set.
        spr = self.factory.makeSourcePackageRelease()
        self.assertEquals(None, spr.homepage)

    def test_homepage_empty(self):
        # The homepage field can be empty.
        spr = self.factory.makeSourcePackageRelease(homepage="")
        self.assertEquals("", spr.homepage)

    def test_homepage_set_invalid(self):
        # As the homepage field is inherited from the DSCFile, the URL
        # does not have to be valid.
        spr = self.factory.makeSourcePackageRelease(homepage="<invalid<url")
        self.assertEquals("<invalid<url", spr.homepage)

    def test_aggregate_changelog(self):
        # If since_version is passed the "changelog" entry returned
        # should contain the changelogs for all releases *since*
        # that version and up to and including the context SPR.
        changelog = self.factory.makeChangelog(
            spn="foo", versions=["1.3",  "1.2",  "1.1",  "1.0"])
        expected_changelog = dedent(u"""\
            foo (1.3) unstable; urgency=low

              * 1.3.

            foo (1.2) unstable; urgency=low

              * 1.2.

            foo (1.1) unstable; urgency=low

              * 1.1.""")
        spph = self.factory.makeSourcePackagePublishingHistory(
            sourcepackagename="foo", version="1.3", changelog=changelog)
        transaction.commit()  # Yay, librarian.

        observed = spph.sourcepackagerelease.aggregate_changelog(
            since_version="1.0")
        self.assertEqual(expected_changelog, observed)

    def test_aggregate_changelog_invalid_utf8(self):
        # aggregate_changelog copes with invalid UTF-8.
        changelog_main = dedent(u"""\
            foo (1.0) unstable; urgency=low

              * 1.0 (héllo).""").encode("ISO-8859-1")
        changelog_trailer = (
            u" -- Føo Bær <foo@example.com>  "
            u"Tue, 01 Jan 1970 01:50:41 +0000").encode("ISO-8859-1")
        changelog_text = changelog_main + b"\n\n" + changelog_trailer
        changelog = self.factory.makeLibraryFileAlias(content=changelog_text)
        spph = self.factory.makeSourcePackagePublishingHistory(
            sourcepackagename="foo", version="1.0", changelog=changelog)
        transaction.commit()
        observed = spph.sourcepackagerelease.aggregate_changelog(
            since_version=None)
        self.assertEqual(changelog_main.decode("UTF-8", "replace"), observed)


class TestGetActiveArchSpecificPublications(TestCaseWithFactory):

    layer = ZopelessDatabaseLayer

    def makeSPR(self):
        """Create a `SourcePackageRelease`."""
        # Return an un-proxied SPR.  This test is for script code; it
        # won't get proxied objects in real life.
        return removeSecurityProxy(self.factory.makeSourcePackageRelease())

    def makeBPPHs(self, spr, number=1):
        """Create `BinaryPackagePublishingHistory` object(s).

        Each of the publications will be active and architecture-specific.
        Each will be for the same archive, distroseries, and pocket.

        Since the tests need to create a pocket mismatch, it is guaranteed
        that the BPPHs are for the UPDATES pocket.
        """
        das = self.factory.makeDistroArchSeries()
        distroseries = das.distroseries
        archive = distroseries.main_archive
        pocket = PackagePublishingPocket.UPDATES

        bpbs = [
            self.factory.makeBinaryPackageBuild(
                source_package_release=spr, distroarchseries=das)
            for counter in range(number)]
        bprs = [
            self.factory.makeBinaryPackageRelease(
                build=bpb, architecturespecific=True)
            for bpb in bpbs]

        return [
            removeSecurityProxy(
                self.factory.makeBinaryPackagePublishingHistory(
                    archive=archive, distroarchseries=das, pocket=pocket,
                    binarypackagerelease=bpr,
                    status=PackagePublishingStatus.PUBLISHED))
            for bpr in bprs]

    def test_getActiveArchSpecificPublications_finds_only_matches(self):
        spr = self.makeSPR()
        bpphs = self.makeBPPHs(spr, 5)

        # This BPPH will match our search.
        match = bpphs[0]

        distroseries = match.distroseries
        distro = distroseries.distribution

        # These BPPHs will not match our search, each because they fail
        # one search parameter.
        bpphs[1].archive = self.factory.makeArchive(
            distribution=distro, purpose=ArchivePurpose.PARTNER)
        bpphs[2].distroarchseries = self.factory.makeDistroArchSeries(
            distroseries=self.factory.makeDistroSeries(distribution=distro))
        bpphs[3].pocket = PackagePublishingPocket.SECURITY
        bpphs[4].binarypackagerelease.architecturespecific = False

        self.assertContentEqual(
            [match], spr.getActiveArchSpecificPublications(
                match.archive, match.distroseries, match.pocket))

    def test_getActiveArchSpecificPublications_detects_absence(self):
        spr = self.makeSPR()
        distroseries = spr.upload_distroseries
        result_set = spr.getActiveArchSpecificPublications(
            distroseries.main_archive, distroseries,
            self.factory.getAnyPocket())
        self.assertFalse(result_set.any())

    def test_getActiveArchSpecificPublications_filters_status(self):
        spr = self.makeSPR()
        bpphs = self.makeBPPHs(spr, len(PackagePublishingStatus.items))
        for bpph, status in zip(bpphs, PackagePublishingStatus.items):
            bpph.status = status
        by_status = dict((bpph.status, bpph) for bpph in bpphs)
        self.assertContentEqual(
            [by_status[status] for status in active_publishing_status],
            spr.getActiveArchSpecificPublications(
                bpphs[0].archive, bpphs[0].distroseries, bpphs[0].pocket))


class TestSourcePackageReleaseGetBuildByArch(TestCaseWithFactory):
    """Tests for SourcePackageRelease.getBuildByArch()."""

    layer = ZopelessDatabaseLayer

    def test_can_find_build_in_derived_distro_parent(self):
        # If a derived distribution inherited its binaries from its
        # parent then getBuildByArch() should look in the parent to find
        # the build.
        dsp = self.factory.makeDistroSeriesParent()
        parent_archive = dsp.parent_series.main_archive

        # Create a built, published package in the parent archive.
        spr = self.factory.makeSourcePackageRelease(
            architecturehintlist='any')
        parent_source_pub = self.factory.makeSourcePackagePublishingHistory(
            sourcepackagerelease=spr, archive=parent_archive,
            distroseries=dsp.parent_series)
        das = self.factory.makeDistroArchSeries(
            distroseries=dsp.parent_series, supports_virtualized=True)
        orig_build = spr.createBuild(
            das, PackagePublishingPocket.RELEASE, parent_archive,
            status=BuildStatus.FULLYBUILT)
        bpr = self.factory.makeBinaryPackageRelease(build=orig_build)
        self.factory.makeBinaryPackagePublishingHistory(
            binarypackagerelease=bpr, distroarchseries=das,
            archive=parent_archive)

        # Make an architecture in the derived series with the same
        # archtag as the parent.
        das_derived = self.factory.makeDistroArchSeries(
            dsp.derived_series, architecturetag=das.architecturetag,
            processor=das.processor, supports_virtualized=True)
        # Now copy the package to the derived series, with binary.
        derived_archive = dsp.derived_series.main_archive
        getUtility(ISourcePackageFormatSelectionSet).add(
            dsp.derived_series, SourcePackageFormat.FORMAT_1_0)

        do_copy(
            [parent_source_pub], derived_archive, dsp.derived_series,
            PackagePublishingPocket.RELEASE, include_binaries=True,
            check_permissions=False)

        # Searching for the build in the derived series architecture
        # should automatically pick it up from the parent.
        found_build = spr.getBuildByArch(das_derived, derived_archive)
        self.assertEqual(orig_build, found_build)


class TestFindBuildsByArchitecture(TestCaseWithFactory):
    """Tests for SourcePackageRelease.findBuildsByArchitecture."""

    layer = ZopelessDatabaseLayer

    def test_finds_build_with_matching_pub(self):
        # findBuildsByArchitecture finds builds for a source package
        # release.  In particular, an arch-independent BPR is published in
        # multiple architectures.  But findBuildsByArchitecture only counts
        # the publication for the same architecture it was built in.
        distroseries = self.factory.makeDistroSeries()
        archive = distroseries.main_archive
        # The series has a nominated arch-indep architecture.
        distroseries.nominatedarchindep = self.factory.makeDistroArchSeries(
            distroseries=distroseries)

        bpb = self.factory.makeBinaryPackageBuild(
            distroarchseries=distroseries.nominatedarchindep)
        bpr = self.factory.makeBinaryPackageRelease(
            build=bpb, architecturespecific=False)
        spr = bpr.build.source_package_release

        # The series also has other architectures.
        self.factory.makeDistroArchSeries(distroseries=distroseries)

        # makeBinaryPackagePublishingHistory will actually publish an
        # arch-indep BPR everywhere.
        self.factory.makeBinaryPackagePublishingHistory(
            binarypackagerelease=bpr, archive=archive,
            distroarchseries=distroseries.nominatedarchindep)

        naked_spr = removeSecurityProxy(spr)
        self.assertEqual(
            {distroseries.nominatedarchindep.architecturetag: bpr.build},
            naked_spr.findBuildsByArchitecture(distroseries, archive))


class TestSourcePackageReleaseTranslationFiles(TestCaseWithFactory):
    """Tests for attachTranslationFiles on a different layer."""

    layer = LaunchpadZopelessLayer

    def makeTranslationsLFA(self):
        """Create an LibraryFileAlias containing dummy translation data."""
        test_tar_content = {
            'source/po/foo.pot': 'Foo template',
            'source/po/eo.po': 'Foo translation',
            }
        tarfile_content = LaunchpadWriteTarFile.files_to_string(
            test_tar_content)
        return self.factory.makeLibraryFileAlias(content=tarfile_content)

    def test_attachTranslationFiles__no_translation_sharing(self):
        # If translation sharing is disabled,
        # SourcePackageRelease.attachTranslationFiles() creates a job
        # in the translation import queue.
        spr = self.factory.makeSourcePackageRelease()
        self.assertFalse(spr.sourcepackage.has_sharing_translation_templates)
        lfa = self.makeTranslationsLFA()
        transaction.commit()
        with dbuser('upload_package_translations_job'):
            spr.attachTranslationFiles(lfa, True, spr.maintainer)
        translation_import_queue = getUtility(ITranslationImportQueue)
        entries_in_queue = translation_import_queue.getAllEntries(
                target=spr.sourcepackage).count()
        self.assertEqual(2, entries_in_queue)

    def test_attachTranslationFiles__translation_sharing(self):
        # If translation sharing is enabled,
        # SourcePackageRelease.attachTranslationFiles() only attaches
        # templates.
        spr = self.factory.makeSourcePackageRelease()
        sourcepackage = spr.sourcepackage
        productseries = self.factory.makeProductSeries()
        self.factory.makePOTemplate(productseries=productseries)
        with person_logged_in(sourcepackage.distroseries.owner):
            sourcepackage.setPackaging(
                productseries, sourcepackage.distroseries.owner)
        self.assertTrue(sourcepackage.has_sharing_translation_templates)
        lfa = self.makeTranslationsLFA()
        transaction.commit()
        with dbuser('upload_package_translations_job'):
            spr.attachTranslationFiles(lfa, True, spr.maintainer)
        translation_import_queue = getUtility(ITranslationImportQueue)
        entries = translation_import_queue.getAllEntries(
                target=sourcepackage)
        self.assertEqual(1, entries.count())
        self.assertTrue(entries[0].path.endswith('.pot'))
