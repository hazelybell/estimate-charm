# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for ISeriesSourcePackageBranch."""

__metaclass__ = type

from datetime import datetime

import pytz
import transaction
from zope.component import getUtility

from lp.code.interfaces.seriessourcepackagebranch import (
    IFindOfficialBranchLinks,
    ISeriesSourcePackageBranch,
    )
from lp.code.model.seriessourcepackagebranch import (
    SeriesSourcePackageBranchSet,
    )
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


class TestSeriesSourcePackageBranch(TestCaseWithFactory):
    """Tests for `ISeriesSourcePackageBranch`."""

    layer = DatabaseFunctionalLayer

    def test_new_sets_attributes(self):
        # SeriesSourcePackageBranchSet.new sets all the defined attributes on
        # the interface.
        distroseries = self.factory.makeDistroSeries()
        sourcepackagename = self.factory.makeSourcePackageName()
        registrant = self.factory.makePerson()
        branch = self.factory.makeAnyBranch()
        now = datetime.now(pytz.UTC)
        sspb = SeriesSourcePackageBranchSet.new(
            distroseries, PackagePublishingPocket.RELEASE, sourcepackagename,
            branch, registrant, now)
        self.assertEqual(distroseries, sspb.distroseries)
        self.assertEqual(PackagePublishingPocket.RELEASE, sspb.pocket)
        self.assertEqual(sourcepackagename, sspb.sourcepackagename)
        self.assertEqual(branch, sspb.branch)
        self.assertEqual(registrant, sspb.registrant)
        self.assertEqual(now, sspb.date_created)

    def test_new_inserts_into_db(self):
        # SeriesSourcePackageBranchSet.new inserts the new object into the
        # database, giving it an ID.
        distroseries = self.factory.makeDistroSeries()
        sourcepackagename = self.factory.makeSourcePackageName()
        registrant = self.factory.makePerson()
        branch = self.factory.makeAnyBranch()
        sspb = SeriesSourcePackageBranchSet.new(
            distroseries, PackagePublishingPocket.RELEASE, sourcepackagename,
            branch, registrant)
        transaction.commit()
        self.assertIsNot(sspb.id, None)

    def test_new_returns_ISeriesSourcePackageBranch(self):
        # SeriesSourcePackageBranchSet.new returns an
        # ISeriesSourcePackageBranch, know what I mean?
        distroseries = self.factory.makeDistroSeries()
        sourcepackagename = self.factory.makeSourcePackageName()
        registrant = self.factory.makePerson()
        branch = self.factory.makeAnyBranch()
        sspb = SeriesSourcePackageBranchSet.new(
            distroseries, PackagePublishingPocket.RELEASE, sourcepackagename,
            branch, registrant)
        self.assertProvides(sspb, ISeriesSourcePackageBranch)

    def test_findForSourcePackage(self):
        # IFindOfficialBranchLinks.findForSourcePackage returns an empty
        # result set if there are no links from that source package.
        series_set = getUtility(IFindOfficialBranchLinks)
        package = self.factory.makeSourcePackage()
        self.assertEqual([], list(series_set.findForSourcePackage(package)))

    def test_findForSourcePackage_non_empty(self):
        # IFindOfficialBranchLinks.findForSourcePackage returns a result
        # set of links from the source package. Each link is an
        # ISeriesSourcePackageBranch.
        branch = self.factory.makePackageBranch()
        package = branch.sourcepackage
        SeriesSourcePackageBranchSet.new(
            package.distroseries, PackagePublishingPocket.RELEASE,
            package.sourcepackagename, branch, self.factory.makePerson())
        find_branch_links = getUtility(IFindOfficialBranchLinks)
        [link] = list(find_branch_links.findForSourcePackage(package))
        self.assertEqual(PackagePublishingPocket.RELEASE, link.pocket)
        self.assertEqual(branch, link.branch)
        self.assertEqual(link.distroseries, package.distroseries)
        self.assertEqual(link.sourcepackagename, package.sourcepackagename)

    def test_findForBranch(self):
        # IFindOfficialBranchLinks.findForBranch returns a result set of
        # links from the branch to source packages & pockets. Each link is an
        # ISeriesSourcePackageBranch.
        branch = self.factory.makePackageBranch()
        package = branch.sourcepackage
        SeriesSourcePackageBranchSet.new(
            package.distroseries, PackagePublishingPocket.RELEASE,
            package.sourcepackagename, branch, self.factory.makePerson())
        find_branch_links = getUtility(IFindOfficialBranchLinks)
        [link] = list(find_branch_links.findForBranch(branch))
        self.assertEqual(PackagePublishingPocket.RELEASE, link.pocket)
        self.assertEqual(branch, link.branch)
        self.assertEqual(link.distroseries, package.distroseries)
        self.assertEqual(link.sourcepackagename, package.sourcepackagename)

    def test_delete(self):
        # `delete` ensures that there is no branch associated with that
        # sourcepackage and pocket.
        branch = self.factory.makePackageBranch()
        package = branch.sourcepackage
        SeriesSourcePackageBranchSet.new(
            package.distroseries, PackagePublishingPocket.RELEASE,
            package.sourcepackagename, branch, self.factory.makePerson())
        SeriesSourcePackageBranchSet.delete(
            package, PackagePublishingPocket.RELEASE)
        find_branch_links = getUtility(IFindOfficialBranchLinks)
        self.assertEqual(
            [], list(find_branch_links.findForSourcePackage(package)))
