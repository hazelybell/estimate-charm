# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for BugTargets."""

__metaclass__ = type

from zope.security.interfaces import ForbiddenAttribute

from lp.bugs.interfaces.bugtarget import ISeriesBugTarget
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class BugTargetBugFilingDuplicateSearchAlwaysOn:
    """A base class for tests of bug targets where dupes are always searched.
    """

    def test_enable_bugfiling_duplicate_search(self):
        # enable_bugfiling_duplicate_search is always True.
        self.assertTrue(self.bugtarget.enable_bugfiling_duplicate_search)

    def test_enable_bugfiling_duplicate_search_is_read_only(self):
        # enable_bugfiling_duplicate_search is a read-only attribute
        with person_logged_in(self.bugtarget.owner):
            self.assertRaises(
                ForbiddenAttribute, setattr, self.bugtarget,
                'enable_bugfiling_duplicate_search', False)


class TestDistribution(BugTargetBugFilingDuplicateSearchAlwaysOn,
                       TestCaseWithFactory):
    """Tests for distributions as bug targets."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestDistribution, self).setUp()
        self.bugtarget = self.factory.makeDistribution()

    def test_pillar(self):
        self.assertEqual(self.bugtarget, self.bugtarget.pillar)


class TestDistroSeries(BugTargetBugFilingDuplicateSearchAlwaysOn,
                       TestCaseWithFactory):
    """Tests for distributions as bug targets."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestDistroSeries, self).setUp()
        self.bugtarget = self.factory.makeDistroSeries()

    def test_bugtarget_parent(self):
        self.assertTrue(ISeriesBugTarget.providedBy(self.bugtarget))
        self.assertEqual(
            self.bugtarget.distribution, self.bugtarget.bugtarget_parent)

    def test_pillar(self):
        self.assertEqual(self.bugtarget.distribution, self.bugtarget.pillar)

    def test_series(self):
        self.assertEqual(self.bugtarget, self.bugtarget.series)


class TestProjectGroup(BugTargetBugFilingDuplicateSearchAlwaysOn,
                       TestCaseWithFactory):
    """Tests for distributions as bug targets."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestProjectGroup, self).setUp()
        self.bugtarget = self.factory.makeProject()


class BugTargetBugFilingDuplicateSearchSettable:
    """A base class for tests of bug targets where dupe search is settable.
    """

    def test_enable_bugfiling_duplicate_search_default(self):
        # The default value of enable_bugfiling_duplicate_search is True.
        self.assertTrue(self.bugtarget.enable_bugfiling_duplicate_search)

    def test_enable_bugfiling_duplicate_search_is_changeable(self):
        # The bug supervisor can change enable_bugfiling_duplicate_search.
        with person_logged_in(self.bug_supervisor):
            self.bugtarget.enable_bugfiling_duplicate_search = False
        self.assertFalse(self.bugtarget.enable_bugfiling_duplicate_search)


class TestProduct(BugTargetBugFilingDuplicateSearchSettable,
                  TestCaseWithFactory):
    """Tests for products as bug targets."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestProduct, self).setUp()
        self.bug_supervisor = self.factory.makePerson()
        self.bugtarget = self.factory.makeProduct(
            bug_supervisor=self.bug_supervisor)

    def test_pillar(self):
        self.assertEqual(self.bugtarget, self.bugtarget.pillar)


class TestDistributionSourcePackage(BugTargetBugFilingDuplicateSearchSettable,
                                    TestCaseWithFactory):
    """Tests for distributionsourcepackages as bug targets."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestDistributionSourcePackage, self).setUp()
        self.bug_supervisor = self.factory.makePerson()
        distribution = self.factory.makeDistribution(
            bug_supervisor=self.bug_supervisor)
        self.bugtarget = self.factory.makeDistributionSourcePackage(
            distribution=distribution)

    def test_pillar(self):
        self.assertEqual(self.bugtarget.distribution, self.bugtarget.pillar)


class BugTargetBugFilingDuplicateSearchInherited:
    """A base class for tests of bug targets where the dupe search policy
    is inherited from a parent object.
    """

    def test_enable_bugfiling_duplicate_search_default(self):
        # The default value of enable_bugfiling_duplicate_search is True.
        self.assertTrue(self.bugtarget.enable_bugfiling_duplicate_search)

    def test_enable_bugfiling_duplicate_search_changed_by_parent_change(self):
        # If enable_bugfiling_duplicate_search is changed for the parent
        # object, it is changed for the bug traget too.
        with person_logged_in(self.bug_supervisor):
            parent = self.bugtarget.bugtarget_parent
            parent.enable_bugfiling_duplicate_search = False
        self.assertFalse(self.bugtarget.enable_bugfiling_duplicate_search)


class TestProductSeries(BugTargetBugFilingDuplicateSearchInherited,
                        TestCaseWithFactory):
    """Tests for product serieses as bug targets."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestProductSeries, self).setUp()
        self.bug_supervisor = self.factory.makePerson()
        self.bugtarget = self.factory.makeProductSeries(
            product=self.factory.makeProduct(
                bug_supervisor=self.bug_supervisor))

    def test_bugtarget_parent(self):
        self.assertTrue(ISeriesBugTarget.providedBy(self.bugtarget))
        self.assertEqual(
            self.bugtarget.product, self.bugtarget.bugtarget_parent)

    def test_pillar(self):
        self.assertEqual(self.bugtarget.product, self.bugtarget.pillar)

    def test_series(self):
        self.assertEqual(self.bugtarget, self.bugtarget.series)


class TestSourcePackage(BugTargetBugFilingDuplicateSearchInherited,
                       TestCaseWithFactory):
    """Tests for product serieses as bug targets."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestSourcePackage, self).setUp()
        self.bug_supervisor = self.factory.makePerson()
        distribution = self.factory.makeDistribution(
            bug_supervisor=self.bug_supervisor)
        distroseries = self.factory.makeDistroSeries(
            distribution=distribution)
        self.bugtarget = self.factory.makeSourcePackage(
            distroseries=distroseries)

    def test_bugtarget_parent(self):
        self.assertTrue(ISeriesBugTarget.providedBy(self.bugtarget))
        self.assertEqual(
            self.bugtarget.distribution_sourcepackage,
            self.bugtarget.bugtarget_parent)

    def test_pillar(self):
        self.assertEqual(
            self.bugtarget.distroseries.distribution, self.bugtarget.pillar)

    def test_series(self):
        self.assertEqual(self.bugtarget.distroseries, self.bugtarget.series)
