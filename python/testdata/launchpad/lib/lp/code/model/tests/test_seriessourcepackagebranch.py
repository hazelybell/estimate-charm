# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Model tests for distro series source package branch links."""

__metaclass__ = type

from lp.code.model.seriessourcepackagebranch import (
    SeriesSourcePackageBranchSet,
    )
from lp.code.tests.helpers import make_linked_package_branch
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


class TestSeriesSourcePackageBranchSet(TestCaseWithFactory):
    """Tests for `SeriesSourcePackageBranchSet`."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.link_set = SeriesSourcePackageBranchSet()

    def makeLinkedPackageBranch(self, distribution, sourcepackagename):
        """Make a new package branch and make it official."""
        return make_linked_package_branch(
            self.factory, distribution, sourcepackagename)

    def test_findForDistributionSourcePackage(self):
        # Make sure that the find method finds official links for all distro
        # series for the distribution source package.
        distro_source_package = self.factory.makeDistributionSourcePackage()
        distribution = distro_source_package.distribution
        sourcepackagename = distro_source_package.sourcepackagename

        # Make two package branches in different series of the same distro.
        b1 = self.makeLinkedPackageBranch(distribution, sourcepackagename)
        b2 = self.makeLinkedPackageBranch(distribution, sourcepackagename)

        # Make one more on same source package on different distro.
        self.makeLinkedPackageBranch(None, sourcepackagename)

        # Make one more on different source package, same different distro.
        self.makeLinkedPackageBranch(distribution, None)

        # And one more unrelated linked package branch.
        self.makeLinkedPackageBranch(None, None)

        links = self.link_set.findForDistributionSourcePackage(
            distro_source_package)
        self.assertEqual(
            sorted([b1, b2]), sorted([link.branch for link in links]))

    def test_delete(self):
        # SeriesSourcePackageBranchSet.delete removes the link between a
        # particular branch and a (distro_series, pocket, sourcepackagename)
        # tupled.
        distro_series = self.factory.makeDistroSeries()
        sourcepackagename = self.factory.makeSourcePackageName()
        sourcepackage = self.factory.makeSourcePackage(
            sourcepackagename=sourcepackagename, distroseries=distro_series)
        branch_release = self.factory.makePackageBranch(
            distroseries=distro_series, sourcepackagename=sourcepackagename)
        branch_updates = self.factory.makePackageBranch(
            distroseries=distro_series, sourcepackagename=sourcepackagename)
        self.link_set.new(
            distro_series, PackagePublishingPocket.RELEASE, sourcepackagename,
            branch_release, branch_release.owner)
        self.link_set.new(
            distro_series, PackagePublishingPocket.UPDATES, sourcepackagename,
            branch_updates, branch_updates.owner)
        self.link_set.delete(sourcepackage, PackagePublishingPocket.UPDATES)
        links = self.link_set.findForSourcePackage(sourcepackage)
        self.assertEqual(
            sorted([branch_release]), sorted([link.branch for link in links]))
