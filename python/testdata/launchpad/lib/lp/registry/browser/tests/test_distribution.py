# Copyright 2011-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for Distribution page."""

__metaclass__ = type

from fixtures import FakeLogger
from lazr.restful.interfaces import IJSONRequestCache
import soupmatchers
from testtools.matchers import (
    MatchesAny,
    Not,
    )
from zope.schema.vocabulary import SimpleVocabulary

from lp.app.browser.lazrjs import vocabulary_to_choice_edit_items
from lp.registry.enums import EXCLUSIVE_TEAM_POLICY
from lp.registry.interfaces.series import SeriesStatus
from lp.services.webapp import canonical_url
from lp.testing import (
    login_celebrity,
    login_person,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.views import create_initialized_view


class TestDistributionPage(TestCaseWithFactory):
    """A TestCase for the distribution index page."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestDistributionPage, self).setUp()
        self.distro = self.factory.makeDistribution(
            name="distro", displayname=u'distro')
        self.simple_user = self.factory.makePerson()
        # Use a FakeLogger fixture to prevent Memcached warnings to be
        # printed to stdout while browsing pages.
        self.useFixture(FakeLogger())

    def test_distributionpage_addseries_link(self):
        # An admin sees the +addseries link.
        self.admin = login_celebrity('admin')
        view = create_initialized_view(
            self.distro, '+index', principal=self.admin)
        series_matches = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                'link to add a series', 'a',
                attrs={'href':
                    canonical_url(self.distro, view_name='+addseries')},
                text='Add series'),
            soupmatchers.Tag(
                'Active series and milestones widget', 'h2',
                text='Active series and milestones'),
            )
        self.assertThat(view.render(), series_matches)

    def test_distributionpage_addseries_link_noadmin(self):
        # A non-admin does not see the +addseries link nor the series
        # header (since there is no series yet).
        login_person(self.simple_user)
        view = create_initialized_view(
            self.distro, '+index', principal=self.simple_user)
        add_series_match = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                'link to add a series', 'a',
                attrs={'href':
                    canonical_url(self.distro, view_name='+addseries')},
                text='Add series'))
        series_header_match = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                'Active series and milestones widget', 'h2',
                text='Active series and milestones'))
        self.assertThat(
            view.render(),
            Not(MatchesAny(add_series_match, series_header_match)))

    def test_distributionpage_series_list_noadmin(self):
        # A non-admin does see the series list when there is a series.
        self.factory.makeDistroSeries(distribution=self.distro,
            status=SeriesStatus.CURRENT)
        login_person(self.simple_user)
        view = create_initialized_view(
            self.distro, '+index', principal=self.simple_user)
        add_series_match = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                'link to add a series', 'a',
                attrs={'href':
                    canonical_url(self.distro, view_name='+addseries')},
                text='Add series'))
        series_header_match = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                'Active series and milestones widget', 'h2',
                text='Active series and milestones'))
        self.assertThat(view.render(), series_header_match)
        self.assertThat(view.render(), Not(add_series_match))


class TestDistributionView(TestCaseWithFactory):
    """Tests the DistributionView."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestDistributionView, self).setUp()
        self.distro = self.factory.makeDistribution(
            name="distro", displayname=u'distro')

    def test_view_data_model(self):
        # The view's json request cache contains the expected data.
        view = create_initialized_view(self.distro, '+index')
        cache = IJSONRequestCache(view.request)
        policy_items = [(item.name, item) for item in EXCLUSIVE_TEAM_POLICY]
        team_membership_policy_data = vocabulary_to_choice_edit_items(
            SimpleVocabulary.fromItems(policy_items),
            value_fn=lambda item: item.name)
        self.assertContentEqual(
            team_membership_policy_data,
            cache.objects['team_membership_policy_data'])
