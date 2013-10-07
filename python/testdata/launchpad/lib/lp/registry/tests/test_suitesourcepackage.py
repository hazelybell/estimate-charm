# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for ISuiteSourcePackage."""

__metaclass__ = type

from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.model.suitesourcepackage import SuiteSourcePackage
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


class TestSuiteSourcePackage(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_construction(self):
        # A SuiteSourcePackage is constructed from an `IDistroSeries`, a
        # `PackagePublishingPocket` enum and an `ISourcePackageName`. These
        # are all provided as attributes.
        distroseries = self.factory.makeDistroSeries()
        pocket = PackagePublishingPocket.RELEASE
        sourcepackagename = self.factory.makeSourcePackageName()
        ssp = SuiteSourcePackage(distroseries, pocket, sourcepackagename)
        self.assertEqual(distroseries, ssp.distroseries)
        self.assertEqual(pocket, ssp.pocket)
        self.assertEqual(sourcepackagename, ssp.sourcepackagename)

    def test_sourcepackage(self):
        # A SuiteSourcePackage has a `sourcepackage` property, which is an
        # ISourcePackage that represents the sourcepackagename, distroseries
        # pair.
        ssp = self.factory.makeSuiteSourcePackage()
        package = ssp.distroseries.getSourcePackage(ssp.sourcepackagename)
        self.assertEqual(package, ssp.sourcepackage)

    def test_suite(self):
        # The `suite` property of a `SuiteSourcePackage` is a string of the
        # distro series name followed by the pocket suffix.
        ssp = self.factory.makeSuiteSourcePackage()
        self.assertEqual(ssp.distroseries.getSuite(ssp.pocket), ssp.suite)

    def test_distribution(self):
        # The `distribution` property of a `SuiteSourcePackage` is the
        # distribution that the object's distroseries is associated with.
        ssp = self.factory.makeSuiteSourcePackage()
        self.assertEqual(ssp.distroseries.distribution, ssp.distribution)

    def test_path(self):
        # The `path` property of a `SuiteSourcePackage` is a string that has
        # the distribution name followed by the suite followed by the source
        # package name, separated by slashes.
        ssp = self.factory.makeSuiteSourcePackage()
        self.assertEqual(
            '%s/%s/%s' % (
                ssp.distribution.name, ssp.suite, ssp.sourcepackagename.name),
            ssp.path)

    def test_repr(self):
        # The repr of a `SuiteSourcePackage` includes the path and clearly
        # refers to the type of the object.
        ssp = self.factory.makeSuiteSourcePackage()
        self.assertEqual('<SuiteSourcePackage %s>' % ssp.path, repr(ssp))

    def test_equality(self):
        ssp1 = self.factory.makeSuiteSourcePackage()
        ssp2 = SuiteSourcePackage(
            ssp1.distroseries, ssp1.pocket, ssp1.sourcepackagename)
        self.assertEqual(ssp1, ssp2)

    def test_displayname(self):
        # A suite source package has a display name.
        ssp = self.factory.makeSuiteSourcePackage()
        self.assertEqual(
            '%s in %s' % (ssp.sourcepackagename.name, ssp.suite),
            ssp.displayname)
