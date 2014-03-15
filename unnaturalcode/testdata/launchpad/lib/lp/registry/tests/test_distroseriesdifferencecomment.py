# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Model tests for the DistroSeriesDifferenceComment class."""

__metaclass__ = type

from datetime import timedelta
from random import randint

from storm.store import Store
from zope.component import getUtility

from lp.registry.interfaces.distroseriesdifferencecomment import (
    IDistroSeriesDifferenceComment,
    IDistroSeriesDifferenceCommentSource,
    )
from lp.testing import (
    TestCaseWithFactory,
    verifyObject,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    ZopelessDatabaseLayer,
    )
from lp.testing.matchers import Provides


def get_comment_source():
    """Get `IDistroSeriesDifferemtCommentSource` utility."""
    return getUtility(IDistroSeriesDifferenceCommentSource)


def flip_coin(*args):
    """Random comparison function.  Returns -1 or 1 randomly."""
    return 1 - 2 * randint(0, 1)


def randomize_list(original_list):
    """Sort a list (or other iterable) in random order.  Return list."""
    return sorted(original_list, cmp=flip_coin)


class DistroSeriesDifferenceCommentTestCase(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_implements_interface(self):
        # The implementation implements the interface correctly.
        dsd_comment = self.factory.makeDistroSeriesDifferenceComment()
        # Flush the store to ensure db constraints are triggered.
        Store.of(dsd_comment).flush()

        verifyObject(IDistroSeriesDifferenceComment, dsd_comment)

    def test_body_text(self):
        # The comment attribute returns the text of the comment.
        dsd_comment = self.factory.makeDistroSeriesDifferenceComment(
            comment="Wait until version 2.3")

        self.assertEqual("Wait until version 2.3", dsd_comment.body_text)

    def test_subject(self):
        # The subject of the message is set from the distro series diff
        # title.
        dsd_comment = self.factory.makeDistroSeriesDifferenceComment()

        self.assertEqual(
            dsd_comment.distro_series_difference.title,
            dsd_comment.message.subject)

    def test_comment_author(self):
        # The comment author just proxies the author from the message.
        dsd_comment = self.factory.makeDistroSeriesDifferenceComment()

        self.assertEqual(
            dsd_comment.message.owner, dsd_comment.comment_author)

    def test_comment_date(self):
        # The comment date attribute just proxies from the message.
        dsd_comment = self.factory.makeDistroSeriesDifferenceComment()

        self.assertEqual(
            dsd_comment.message.datecreated, dsd_comment.comment_date)

    def test_getForDifference(self):
        # The utility can get comments by id.
        dsd_comment = self.factory.makeDistroSeriesDifferenceComment()
        Store.of(dsd_comment).flush()

        self.assertEqual(
            dsd_comment, get_comment_source().getForDifference(
                dsd_comment.distro_series_difference, dsd_comment.id))

    def test_source_package_name_returns_package_name(self):
        # The comment "knows" the name of the source package it's for.
        package_name = self.factory.getUniqueUnicode()
        dsd = self.factory.makeDistroSeriesDifference(
            source_package_name_str=package_name)
        comment = self.factory.makeDistroSeriesDifferenceComment(dsd)
        self.assertEqual(package_name, comment.source_package_name)


class TestDistroSeriesDifferenceCommentSource(TestCaseWithFactory):

    layer = ZopelessDatabaseLayer

    def test_implements_interface(self):
        self.assertThat(
            get_comment_source(),
            Provides(IDistroSeriesDifferenceCommentSource))

    def test_getForDistroSeries_returns_result_set(self):
        series = self.factory.makeDistroSeries()
        source = get_comment_source()
        self.assertTrue(source.getForDistroSeries(series).is_empty())

    def test_getForDistroSeries_matches_on_distroseries(self):
        dsd = self.factory.makeDistroSeriesDifference()
        series = dsd.derived_series
        comment = self.factory.makeDistroSeriesDifferenceComment(dsd)
        source = get_comment_source()
        self.assertContentEqual([comment], source.getForDistroSeries(series))

    def test_getForDistroSeries_filters_by_distroseries(self):
        dsd = self.factory.makeDistroSeriesDifference()
        other_series = self.factory.makeDistroSeries()
        self.factory.makeDistroSeriesDifferenceComment(dsd)
        source = get_comment_source()
        self.assertContentEqual([], source.getForDistroSeries(other_series))

    def test_getForDistroSeries_matches_on_since(self):
        dsd = self.factory.makeDistroSeriesDifference()
        series = dsd.derived_series
        comment = self.factory.makeDistroSeriesDifferenceComment(dsd)
        source = get_comment_source()
        yesterday = comment.comment_date - timedelta(1)
        self.assertContentEqual(
            [comment], source.getForDistroSeries(series, since=yesterday))

    def test_getForDistroSeries_filters_by_since(self):
        dsd = self.factory.makeDistroSeriesDifference()
        series = dsd.derived_series
        comment = self.factory.makeDistroSeriesDifferenceComment(dsd)
        source = get_comment_source()
        tomorrow = comment.comment_date + timedelta(1)
        self.assertContentEqual(
            [], source.getForDistroSeries(series, since=tomorrow))

    def test_getForDistroSeries_orders_by_age(self):
        series = self.factory.makeDistroSeries()
        dsds = randomize_list([
            self.factory.makeDistroSeriesDifference(derived_series=series)
            for counter in xrange(5)])
        comments = [
            self.factory.makeDistroSeriesDifferenceComment(dsd)
            for dsd in dsds]
        source = get_comment_source()
        self.assertEqual(comments, list(source.getForDistroSeries(series)))

    def test_getForDistroSeries_matches_on_package_name(self):
        dsd = self.factory.makeDistroSeriesDifference()
        series = dsd.derived_series
        package_name = dsd.source_package_name.name
        comment = self.factory.makeDistroSeriesDifferenceComment(dsd)
        source = get_comment_source()
        self.assertContentEqual([comment], source.getForDistroSeries(
            series, source_package_name=package_name))

    def test_getForDistroSeries_filters_by_package_name(self):
        dsd = self.factory.makeDistroSeriesDifference()
        series = dsd.derived_series
        other_package = self.factory.getUniqueUnicode()
        self.factory.makeDistroSeriesDifferenceComment(dsd)
        source = get_comment_source()
        self.assertContentEqual([], source.getForDistroSeries(
            series, source_package_name=other_package))
