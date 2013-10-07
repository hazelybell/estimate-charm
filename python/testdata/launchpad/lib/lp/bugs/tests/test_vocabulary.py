# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the bug domain vocabularies."""

__metaclass__ = type

from lp.bugs.vocabularies import (
    BugTaskMilestoneVocabulary,
    UsesBugsDistributionVocabulary,
    )
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class UsesBugsDistributionVocabularyTestCase(TestCaseWithFactory):
    """Test that the vocabulary behaves as expected."""
    layer = DatabaseFunctionalLayer

    def test_init_with_distribution(self):
        # When the context is adaptable to IDistribution, the distribution
        # property is the distribution.
        distribution = self.factory.makeDistribution()
        vocabulary = UsesBugsDistributionVocabulary(distribution)
        self.assertEqual(distribution, vocabulary.context)
        self.assertEqual(distribution, vocabulary.distribution)

    def test_init_without_distribution(self):
        # When the context is not adaptable to IDistribution, the
        # distribution property is None
        thing = self.factory.makeProduct()
        vocabulary = UsesBugsDistributionVocabulary(thing)
        self.assertEqual(thing, vocabulary.context)
        self.assertEqual(None, vocabulary.distribution)

    def test_contains_distros_that_use_bugs(self):
        # The vocabulary contains distributions that also use
        # Launchpad to track bugs.
        distro_less_bugs = self.factory.makeDistribution()
        distro_uses_bugs = self.factory.makeDistribution()
        with person_logged_in(distro_uses_bugs.owner):
            distro_uses_bugs.official_malone = True
        vocabulary = UsesBugsDistributionVocabulary()
        self.assertFalse(
            distro_less_bugs in vocabulary,
            "Vocabulary contains distros that do not use Launchpad Bugs.")
        self.assertTrue(
            distro_uses_bugs in vocabulary,
            "Vocabulary missing distros that use Launchpad Bugs.")

    def test_contains_context_distro(self):
        # The vocabulary contains the context distro even it it does not
        # use Launchpad to track bugs. The distro may have tracked bugs
        # in the past so it is a legitimate choise for historic data.
        distro_less_bugs = self.factory.makeDistribution()
        vocabulary = UsesBugsDistributionVocabulary(distro_less_bugs)
        self.assertFalse(distro_less_bugs.official_malone)
        self.assertTrue(
            distro_less_bugs in vocabulary,
            "Vocabulary missing context distro.")

    def test_contains_missing_context(self):
        # The vocabulary does not contain the context if the
        # context is not adaptable to a distribution.
        thing = self.factory.makeProduct()
        vocabulary = UsesBugsDistributionVocabulary(thing)
        self.assertFalse(
            thing in vocabulary,
            "Vocabulary contains a non-distribution.")


class TestBugTaskMilestoneVocabulary(TestCaseWithFactory):
    """Test that the BugTaskMilestoneVocabulary behaves as expected."""
    layer = DatabaseFunctionalLayer

    def _assert_milestones(self, target, milestone):
        bugtask = self.factory.makeBugTask(target=target)
        vocabulary = BugTaskMilestoneVocabulary(bugtask)
        self.assertEqual(
            [term.title for term in vocabulary], [milestone.displayname])

    def testUpstreamBugTaskMilestoneVocabulary(self):
        """Test of MilestoneVocabulary for a upstraem bugtask."""
        product = self.factory.makeProduct()
        milestone = self.factory.makeMilestone(product=product)
        # Only active milestones are returned.
        self.factory.makeMilestone(product=product, active=False)
        self._assert_milestones(product, milestone)

    def testProductseriesBugTaskMilestoneVocabulary(self):
        """Test of MilestoneVocabulary for a productseries."""
        series = self.factory.makeProductSeries()
        milestone = self.factory.makeMilestone(productseries=series)
        # Only active milestones are returned.
        self.factory.makeMilestone(productseries=series, active=False)
        self._assert_milestones(series, milestone)

    def testDistributionBugTaskMilestoneVocabulary(self):
        """Test of MilestoneVocabulary for a distribution."""
        distro = self.factory.makeDistribution()
        milestone = self.factory.makeMilestone(distribution=distro)
        # Only active milestones are returned.
        self.factory.makeMilestone(distribution=distro, active=False)
        self._assert_milestones(distro, milestone)

    def testDistroseriesBugTaskMilestoneVocabulary(self):
        """Test of MilestoneVocabulary for a distroseries."""
        distroseries = self.factory.makeDistroSeries()
        milestone = self.factory.makeMilestone(distroseries=distroseries)
        # Only active milestones are returned.
        self.factory.makeMilestone(distroseries=distroseries, active=False)
        self._assert_milestones(distroseries, milestone)

    def testDistributionSourcePackageBugTaskMilestoneVocabulary(self):
        """Test of MilestoneVocabulary for a distro source package."""
        distro = self.factory.makeDistribution()
        milestone = self.factory.makeMilestone(distribution=distro)
        # Only active milestones are returned.
        self.factory.makeMilestone(distribution=distro, active=False)
        distro_sourcepackage = self.factory.makeDistributionSourcePackage(
            distribution=distro)
        self._assert_milestones(distro_sourcepackage, milestone)

    def testSourcePackageBugTaskMilestoneVocabulary(self):
        """Test of MilestoneVocabulary for a sourcepackage."""
        distroseries = self.factory.makeDistroSeries()
        milestone = self.factory.makeMilestone(distroseries=distroseries)
        # Only active milestones are returned.
        self.factory.makeMilestone(distroseries=distroseries, active=False)
        sourcepackage = self.factory.makeSourcePackage(
            distroseries=distroseries)
        self._assert_milestones(sourcepackage, milestone)
