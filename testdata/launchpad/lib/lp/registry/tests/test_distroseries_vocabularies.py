# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for distroseries vocabularies in `lp.registry.vocabularies`."""

__metaclass__ = type

from datetime import (
    datetime,
    timedelta,
    )

from pytz import utc
from testtools.matchers import (
    Equals,
    Not,
    )
from zope.component import getUtility
from zope.schema.interfaces import (
    ITokenizedTerm,
    IVocabularyFactory,
    )
from zope.security.proxy import removeSecurityProxy

from lp.registry.interfaces.distroseries import IDistroSeriesSet
from lp.registry.vocabularies import (
    DistroSeriesDerivationVocabulary,
    DistroSeriesDifferencesVocabulary,
    )
from lp.services.database.sqlbase import flush_database_caches
from lp.services.webapp.vocabulary import IHugeVocabulary
from lp.testing import (
    StormStatementRecorder,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.matchers import (
    Contains,
    HasQueryCount,
    Provides,
    )


class TestDistroSeriesDerivationVocabulary(TestCaseWithFactory):
    """Tests for `DistroSeriesDerivationVocabulary`."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestDistroSeriesDerivationVocabulary, self).setUp()
        self.all_distroseries = getUtility(IDistroSeriesSet).search()
        self.all_series_with_arch = [
            series for series in self.all_distroseries
            if series.architecturecount != 0]

    def test_registration(self):
        # DistroSeriesDerivationVocabulary is registered as a named
        # utility for IVocabularyFactory.
        self.assertEqual(
            getUtility(IVocabularyFactory, name="DistroSeriesDerivation"),
            DistroSeriesDerivationVocabulary)

    def test_interface(self):
        # DistroSeriesDerivationVocabulary instances provide IHugeVocabulary.
        distroseries = self.factory.makeDistroSeries()
        vocabulary = DistroSeriesDerivationVocabulary(distroseries)
        self.assertProvides(vocabulary, IHugeVocabulary)

    def test_distribution_with_non_derived_series(self):
        # Given a distribution with series, none of which are derived, the
        # vocabulary factory returns a vocabulary for all distroseries in all
        # distributions *except* the given distribution.
        distroseries = self.factory.makeDistroSeries()
        vocabulary = DistroSeriesDerivationVocabulary(distroseries)
        expected_distroseries = (
            set(self.all_series_with_arch).difference(
                distroseries.distribution.series))
        observed_distroseries = set(term.value for term in vocabulary)
        self.assertEqual(expected_distroseries, observed_distroseries)

    def test_distribution_with_non_derived_series_no_arch(self):
        # Only the parents with DistroArchSeries configured in LP are
        # returned in the DistroSeriesDerivationVocabulary if no other
        # derived distroseries are present in the distribution.
        distroseries = self.factory.makeDistroSeries()
        vocabulary = DistroSeriesDerivationVocabulary(distroseries)
        another_parent_no_arch = self.factory.makeDistroSeries()
        observed_distroseries = set(term.value for term in vocabulary)

        self.assertNotIn(another_parent_no_arch, observed_distroseries)

    def makeDistroSeriesWithDistroArch(self, *args, **kwargs):
        # Helper method to create a distroseries with a
        # DistroArchSeries.
        distroseries = self.factory.makeDistroSeries(*args, **kwargs)
        self.factory.makeDistroArchSeries(distroseries=distroseries)
        return distroseries

    def test_distribution_with_derived_series(self):
        # Given a distribution with series, one or more of which are derived,
        # the vocabulary factory returns a vocabulary for all distroseries of
        # the distribution from which the derived series have been
        # derived with distroarchseries setup in LP.
        parent_distroseries = self.makeDistroSeriesWithDistroArch()
        self.makeDistroSeriesWithDistroArch()
        distroseries = self.factory.makeDistroSeries()
        self.factory.makeDistroSeriesParent(
            derived_series=distroseries, parent_series=parent_distroseries)
        vocabulary = DistroSeriesDerivationVocabulary(distroseries)
        expected_distroseries = set(parent_distroseries.distribution.series)
        observed_distroseries = set(term.value for term in vocabulary)
        self.assertContentEqual(expected_distroseries, observed_distroseries)

    def test_distribution_with_derived_series_no_arch(self):
        # Distroseries with no DistroArchSeries can be parents if this
        # is not the first derivation in the distribution.
        parent_distroseries = self.makeDistroSeriesWithDistroArch()
        another_parent_no_arch = self.factory.makeDistroSeries(
            distribution=parent_distroseries.distribution)
        distroseries = self.factory.makeDistroSeries()
        self.factory.makeDistroSeriesParent(
            derived_series=distroseries, parent_series=parent_distroseries)
        vocabulary = DistroSeriesDerivationVocabulary(distroseries)
        observed_distroseries = set(term.value for term in vocabulary)

        self.assertIn(another_parent_no_arch, observed_distroseries)

    def test_distribution_with_derived_series_from_multiple_parents(self):
        # Given a distribution with series, one or more of which are derived
        # from multiple parents, the vocabulary factory returns a vocabulary
        # for all distroseries of the distribution*s* from which the derived
        # series have been derived.
        parent_distroseries = self.makeDistroSeriesWithDistroArch()
        another_parent_distroseries = self.makeDistroSeriesWithDistroArch()
        self.makeDistroSeriesWithDistroArch(
            distribution=parent_distroseries.distribution)
        distroseries = self.factory.makeDistroSeries()
        self.factory.makeDistroSeriesParent(
            derived_series=distroseries, parent_series=parent_distroseries)
        self.factory.makeDistroSeriesParent(
            derived_series=distroseries,
            parent_series=another_parent_distroseries)
        vocabulary = DistroSeriesDerivationVocabulary(distroseries)
        expected_distroseries = set(
            parent_distroseries.distribution.series).union(
                set(another_parent_distroseries.distribution.series))
        observed_distroseries = set(term.value for term in vocabulary)
        self.assertEqual(expected_distroseries, observed_distroseries)

    def test_distribution_with_derived_series_of_self(self):
        # Given a distribution with series derived from other of its series
        # (which shouldn't happen), the vocabulary factory returns a
        # vocabulary for all distroseries in all distributions *except* the
        # given distribution.
        parent_distroseries = self.makeDistroSeriesWithDistroArch()
        distroseries = self.factory.makeDistroSeries(
            distribution=parent_distroseries.distribution)
        self.factory.makeDistroSeriesParent(
            derived_series=distroseries, parent_series=parent_distroseries)
        vocabulary = DistroSeriesDerivationVocabulary(distroseries)
        expected_distroseries = (
            set(self.all_series_with_arch).difference(
                distroseries.distribution.series))
        observed_distroseries = set(term.value for term in vocabulary)
        self.assertEqual(expected_distroseries, observed_distroseries)

    def test_distroseries(self):
        # Given a distroseries, the vocabulary factory returns the vocabulary
        # the same as for its distribution.
        distroseries = self.makeDistroSeriesWithDistroArch()
        vocabulary = DistroSeriesDerivationVocabulary(distroseries)
        expected_distroseries = (
            set(self.all_series_with_arch).difference(
                distroseries.distribution.series))
        observed_distroseries = set(term.value for term in vocabulary)
        self.assertEqual(expected_distroseries, observed_distroseries)

    def test_ordering(self):
        # The vocabulary is sorted by distribution display name then by the
        # date the distroseries was created, newest first.
        now = datetime.now(utc)
        two_days_ago = now - timedelta(2)
        six_days_ago = now - timedelta(7)

        aaa = self.factory.makeDistribution(displayname="aaa")
        aaa_series_older = self.makeDistroSeriesWithDistroArch(
            name="aaa-series-older", distribution=aaa)
        removeSecurityProxy(aaa_series_older).date_created = six_days_ago
        aaa_series_newer = self.makeDistroSeriesWithDistroArch(
            name="aaa-series-newer", distribution=aaa)
        removeSecurityProxy(aaa_series_newer).date_created = two_days_ago

        bbb = self.factory.makeDistribution(displayname="bbb")
        bbb_series_older = self.makeDistroSeriesWithDistroArch(
            name="bbb-series-older", distribution=bbb)
        removeSecurityProxy(bbb_series_older).date_created = six_days_ago
        bbb_series_newer = self.makeDistroSeriesWithDistroArch(
            name="bbb-series-newer", distribution=bbb)
        removeSecurityProxy(bbb_series_newer).date_created = two_days_ago

        ccc = self.factory.makeDistribution(displayname="ccc")
        ccc_series = self.makeDistroSeriesWithDistroArch(distribution=ccc)

        vocabulary = DistroSeriesDerivationVocabulary(ccc_series)
        expected_distroseries = [
            aaa_series_newer, aaa_series_older,
            bbb_series_newer, bbb_series_older]
        observed_distroseries = list(term.value for term in vocabulary)
        # observed_distroseries will contain distroseries from the sample
        # data, so we must only look at the set of distroseries we have
        # created.
        observed_distroseries = [
            series for series in observed_distroseries
            if series in expected_distroseries]
        self.assertEqual(expected_distroseries, observed_distroseries)

    def test_queries_for_distribution_with_non_derived_series(self):
        for index in range(10):
            self.factory.makeDistroSeries()
        distribution = self.factory.makeDistribution()
        distroseries = self.factory.makeDistroSeries(
            distribution=distribution)
        flush_database_caches()
        # Reload distroseries and distribution; these will reasonably already
        # be loaded before using the vocabulary.
        distroseries.distribution
        # Getting terms issues two queries: one to search for parent serieses
        # (of which there are none) and a second for all serieses.
        with StormStatementRecorder() as recorder:
            DistroSeriesDerivationVocabulary(distroseries).terms
            self.assertThat(recorder, HasQueryCount(Equals(2)))

    def test_queries_for_distribution_with_derived_series(self):
        for index in range(10):
            self.factory.makeDistroSeries()
        distribution = self.factory.makeDistribution()
        parent_distroseries = self.factory.makeDistroSeries()
        distroseries = self.factory.makeDistroSeries(
            distribution=distribution)
        self.factory.makeDistroSeriesParent(
            derived_series=distroseries, parent_series=parent_distroseries)
        flush_database_caches()
        # Reload distroseries and distribution; these will reasonably already
        # be loaded before using the vocabulary.
        distroseries.distribution
        # Getting terms issues 2 queries to find parent serieses.
        with StormStatementRecorder() as recorder:
            DistroSeriesDerivationVocabulary(distroseries).terms
            self.assertThat(recorder, HasQueryCount(Equals(2)))

    def test_no_duplicates(self):
        # No duplicates are present in the returned vocabulary.
        distroseries = self.makeDistroSeriesWithDistroArch()
        vocabulary = DistroSeriesDerivationVocabulary(distroseries)
        expected_distroseries = (
            set(self.all_series_with_arch).difference(
                distroseries.distribution.series))
        observed_distroseries = [term.value for term in vocabulary]

        self.assertContentEqual(
            expected_distroseries,
            observed_distroseries)


class TestDistroSeriesDifferencesVocabulary(TestCaseWithFactory):
    """Tests for `DistroSeriesDifferencesVocabulary`."""

    layer = DatabaseFunctionalLayer

    def test_registration(self):
        # DistroSeriesDifferencesVocabulary is registered as a named utility
        # for IVocabularyFactory.
        self.assertEqual(
            getUtility(IVocabularyFactory, name="DistroSeriesDifferences"),
            DistroSeriesDifferencesVocabulary)

    def test_interface(self):
        # DistroSeriesDifferencesVocabulary instances provide IHugeVocabulary.
        distroseries = self.factory.makeDistroSeries()
        vocabulary = DistroSeriesDifferencesVocabulary(distroseries)
        self.assertProvides(vocabulary, IHugeVocabulary)

    def test_non_derived_distroseries(self):
        # The vocabulary is empty for a non-derived series.
        distroseries = self.factory.makeDistroSeries()
        vocabulary = DistroSeriesDifferencesVocabulary(distroseries)
        self.assertContentEqual([], vocabulary)

    def test_derived_distroseries(self):
        # The vocabulary contains all DSDs for a derived series.
        distroseries = self.factory.makeDistroSeries()
        dsds = [
            self.factory.makeDistroSeriesDifference(
                derived_series=distroseries),
            self.factory.makeDistroSeriesDifference(
                derived_series=distroseries),
            ]
        vocabulary = DistroSeriesDifferencesVocabulary(distroseries)
        self.assertContentEqual(
            dsds, (term.value for term in vocabulary))

    def test_derived_distroseries_not_other_distroseries(self):
        # The vocabulary contains all DSDs for a derived series and not for
        # another series.
        distroseries1 = self.factory.makeDistroSeries()
        distroseries2 = self.factory.makeDistroSeries()
        dsds = [
            self.factory.makeDistroSeriesDifference(
                derived_series=distroseries1),
            self.factory.makeDistroSeriesDifference(
                derived_series=distroseries1),
            self.factory.makeDistroSeriesDifference(
                derived_series=distroseries2),
            self.factory.makeDistroSeriesDifference(
                derived_series=distroseries2),
            ]
        vocabulary = DistroSeriesDifferencesVocabulary(distroseries1)
        self.assertContentEqual(
            (dsd for dsd in dsds if dsd.derived_series == distroseries1),
            (term.value for term in vocabulary))

    def test_contains_difference(self):
        # The vocabulary can be tested for membership.
        difference = self.factory.makeDistroSeriesDifference()
        vocabulary = DistroSeriesDifferencesVocabulary(
            difference.derived_series)
        self.assertThat(vocabulary, Contains(difference))

    def test_does_not_contain_difference(self):
        # The vocabulary can be tested for non-membership.
        difference = self.factory.makeDistroSeriesDifference()
        vocabulary = DistroSeriesDifferencesVocabulary(
            self.factory.makeDistroSeries())
        self.assertThat(vocabulary, Not(Contains(difference)))

    def test_does_not_contain_something_else(self):
        # The vocabulary can be tested for non-membership of something that's
        # not a DistroSeriesDifference.
        distroseries = self.factory.makeDistroSeries()
        vocabulary = DistroSeriesDifferencesVocabulary(distroseries)
        self.assertThat(vocabulary, Not(Contains("foobar")))

    def test_size(self):
        # The vocabulary can report its size.
        difference = self.factory.makeDistroSeriesDifference()
        vocabulary = DistroSeriesDifferencesVocabulary(
            difference.derived_series)
        self.assertEqual(1, len(vocabulary))

    def test_getTerm(self):
        # A term can be obtained from a given value.
        difference = self.factory.makeDistroSeriesDifference()
        vocabulary = DistroSeriesDifferencesVocabulary(
            difference.derived_series)
        term = vocabulary.getTerm(difference)
        self.assertThat(term, Provides(ITokenizedTerm))
        self.assertEqual(difference, term.value)
        self.assertEqual(str(difference.id), term.token)

    def test_getTermByToken(self):
        # A term can be obtained from a given token.
        difference = self.factory.makeDistroSeriesDifference()
        vocabulary = DistroSeriesDifferencesVocabulary(
            difference.derived_series)
        term = vocabulary.getTermByToken(str(difference.id))
        self.assertEqual(difference, term.value)

    def test_getTermByToken_not_found(self):
        # LookupError is raised when the token cannot be found.
        distroseries = self.factory.makeDistroSeries()
        difference = self.factory.makeDistroSeriesDifference()
        vocabulary = DistroSeriesDifferencesVocabulary(distroseries)
        self.assertRaises(
            LookupError, vocabulary.getTermByToken, str(difference.id))

    def test_getTermByToken_invalid(self):
        # LookupError is raised when the token is not valid (i.e. a string
        # containing only digits).
        distroseries = self.factory.makeDistroSeries()
        vocabulary = DistroSeriesDifferencesVocabulary(distroseries)
        self.assertRaises(LookupError, vocabulary.getTermByToken, "foobar")
