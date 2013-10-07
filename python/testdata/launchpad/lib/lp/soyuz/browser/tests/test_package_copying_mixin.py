# Copyright 2011-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for `PackageCopyingMixin`."""

__metaclass__ = type

from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.services.propertycache import cachedproperty
from lp.soyuz.browser.archive import (
    copy_asynchronously,
    render_cannotcopy_as_html,
    )
from lp.soyuz.enums import SourcePackageFormat
from lp.soyuz.interfaces.archive import CannotCopy
from lp.soyuz.interfaces.packagecopyjob import IPlainPackageCopyJobSource
from lp.soyuz.interfaces.sourcepackageformat import (
    ISourcePackageFormatSelectionSet,
    )
from lp.testing import (
    TestCase,
    TestCaseWithFactory,
    )
from lp.testing.layers import LaunchpadFunctionalLayer


def find_spph_copy(archive, spph):
    """Find copy of `spph`'s package as copied into `archive`"""
    spr = spph.sourcepackagerelease
    return archive.getPublishedSources(
        name=spr.sourcepackagename.name, version=spr.version).one()


class TestPackageCopyingMixinLight(TestCase):
    """Test lightweight functions and methods.

    This test does not run in a layer and does not access the database.
    """

    unique_number = 1

    def getUniqueString(self):
        """Return an arbitrary string."""
        self.unique_number += 1
        return "string_%d_" % self.unique_number

    def test_render_cannotcopy_as_html_lists_errors(self):
        # render_cannotcopy_as_html includes a CannotCopy error message
        # into its HTML notice.
        message = self.getUniqueString()
        html_text = render_cannotcopy_as_html(CannotCopy(message)).escapedtext
        self.assertIn(message, html_text)

    def test_render_cannotcopy_as_html_escapes_error(self):
        # render_cannotcopy_as_html escapes error messages.
        message = "x<>y"
        html_text = render_cannotcopy_as_html(CannotCopy(message)).escapedtext
        self.assertNotIn(message, html_text)
        self.assertIn("x&lt;&gt;y", html_text)


class TestPackageCopyingMixinIntegration(TestCaseWithFactory):
    """Integration tests for `PackageCopyingMixin`."""

    layer = LaunchpadFunctionalLayer

    @cachedproperty
    def person(self):
        """Create a single person who gets blamed for everything.

        Creating SPPHs, Archives etc. in the factory creates lots of
        `Person`s, which turns out to be really slow.  Tests that don't
        care who's who can use this single person for all uninteresting
        Person fields.
        """
        return self.factory.makePerson()

    def makeDistribution(self):
        """Create a `Distribution`, but quickly by reusing a single Person."""
        return self.factory.makeDistribution(
            owner=self.person, registrant=self.person)

    def makeDistroSeries(self, previous_series=None):
        """Create a `DistroSeries`, but quickly by reusing a single Person."""
        return self.factory.makeDistroSeries(
            distribution=self.makeDistribution(),
            previous_series=previous_series,
            registrant=self.person)

    def makeSPPH(self):
        """Create a `SourcePackagePublishingHistory` quickly."""
        archive = self.factory.makeArchive(
            owner=self.person, distribution=self.makeDistribution())
        return self.factory.makeSourcePackagePublishingHistory(
            maintainer=self.person, creator=self.person, archive=archive)

    def makeDerivedSeries(self):
        """Create a derived `DistroSeries`, quickly."""
        parent_series = self.makeDistroSeries()
        derived_series = self.makeDistroSeries()
        self.factory.makeDistroSeriesParent(
            parent_series=parent_series, derived_series=derived_series)
        getUtility(ISourcePackageFormatSelectionSet).add(
            derived_series, SourcePackageFormat.FORMAT_1_0)
        return derived_series

    def getUploader(self, archive, spn):
        """Get person with upload rights for the given package and archive."""
        uploader = archive.owner
        removeSecurityProxy(archive).newPackageUploader(uploader, spn)
        return uploader

    def test_copy_asynchronously_does_not_copy_packages(self):
        # copy_asynchronously does not copy packages into the destination
        # archive; that happens later, asynchronously.
        spph = self.makeSPPH()
        dest_series = self.makeDerivedSeries()
        archive = dest_series.distribution.main_archive
        pocket = self.factory.getAnyPocket()
        copy_asynchronously(
            [spph], archive, dest_series, pocket, include_binaries=False,
            check_permissions=False, person=self.factory.makePerson())
        self.assertEqual(None, find_spph_copy(archive, spph))

    def test_copy_asynchronously_creates_copy_jobs(self):
        # copy_asynchronously creates PackageCopyJobs.
        spph = self.makeSPPH()
        dest_series = self.makeDerivedSeries()
        pocket = self.factory.getAnyPocket()
        archive = dest_series.distribution.main_archive
        copy_asynchronously(
            [spph], archive, dest_series, pocket, include_binaries=False,
            check_permissions=False, person=self.factory.makePerson())
        jobs = list(getUtility(IPlainPackageCopyJobSource).getActiveJobs(
            archive))
        self.assertEqual(1, len(jobs))
        job = jobs[0]
        spr = spph.sourcepackagerelease
        self.assertEqual(spr.sourcepackagename.name, job.package_name)
        self.assertEqual(spr.version, job.package_version)
        self.assertEqual(dest_series, job.target_distroseries)

    def test_copy_asynchronously_handles_no_dest_series(self):
        # If dest_series is None, copy_asynchronously creates jobs that will
        # copy each source into the same distroseries in the target archive.
        distribution = self.makeDistribution()
        series_one = self.factory.makeDistroSeries(
            distribution=distribution, registrant=self.person)
        series_two = self.factory.makeDistroSeries(
            distribution=distribution, registrant=self.person)
        spph_one = self.factory.makeSourcePackagePublishingHistory(
            distroseries=series_one, sourcepackagename="one",
            maintainer=self.person, creator=self.person)
        spph_two = self.factory.makeSourcePackagePublishingHistory(
            distroseries=series_two, sourcepackagename="two",
            maintainer=self.person, creator=self.person)
        pocket = self.factory.getAnyPocket()
        target_archive = self.factory.makeArchive(
            owner=self.person, distribution=distribution)
        copy_asynchronously(
            [spph_one, spph_two], target_archive, None, pocket,
            include_binaries=False, check_permissions=False,
            person=self.person)
        jobs = list(getUtility(IPlainPackageCopyJobSource).getActiveJobs(
            target_archive))
        self.assertEqual(2, len(jobs))
        self.assertContentEqual(
            [("one", spph_one.distroseries), ("two", spph_two.distroseries)],
            [(job.package_name, job.target_distroseries) for job in jobs])

    def test_copy_asynchronously_may_allow_copy(self):
        # In a normal working situation, copy_asynchronously allows a
        # copy.
        spph = self.makeSPPH()
        pocket = PackagePublishingPocket.RELEASE
        dest_series = self.makeDerivedSeries()
        dest_archive = dest_series.main_archive
        spn = spph.sourcepackagerelease.sourcepackagename
        notification = copy_asynchronously(
            [spph], dest_archive, dest_series, pocket, False,
            person=self.getUploader(dest_archive, spn))
        self.assertIn("Requested", notification.escapedtext)

    def test_copy_asynchronously_checks_permissions(self):
        # Unless told not to, copy_asynchronously does a permissions
        # check.
        spph = self.makeSPPH()
        pocket = self.factory.getAnyPocket()
        dest_series = self.makeDistroSeries()
        self.assertRaises(
            CannotCopy,
            copy_asynchronously,
            [spph], dest_series.main_archive, dest_series, pocket, False)
