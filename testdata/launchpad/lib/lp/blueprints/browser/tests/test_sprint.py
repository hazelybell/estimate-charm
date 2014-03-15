# Copyright 2011-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for Sprint pages and views."""

__metaclass__ = type

from testtools.matchers import Equals

from lp.app.enums import InformationType
from lp.testing import BrowserTestCase
from lp.testing._webservice import QueryCollector
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.matchers import (
    BrowsesWithQueryLimit,
    HasQueryCount,
    )


class TestSprintIndex(BrowserTestCase):

    layer = DatabaseFunctionalLayer

    def test_query_count(self):
        sprint = self.factory.makeSprint()
        for x in range(30):
            sprint.attend(
                self.factory.makePerson(),
                sprint.time_starts, sprint.time_ends, True)
        self.assertThat(sprint, BrowsesWithQueryLimit(18, sprint.owner))

    def test_blueprint_listing_query_count(self):
        """Set a maximum number of queries for sprint blueprint lists."""
        sprint = self.factory.makeSprint()
        for count in range(10):
            blueprint = self.factory.makeSpecification()
            link = blueprint.linkSprint(sprint, blueprint.owner)
            link.acceptBy(sprint.owner)
        with QueryCollector() as recorder:
            self.getViewBrowser(sprint)
        self.assertThat(recorder, HasQueryCount(Equals(30)))

    def test_proprietary_blueprint_listing_query_count(self):
        """Set a maximum number of queries for sprint blueprint lists."""
        sprint = self.factory.makeSprint()
        for count in range(10):
            blueprint = self.factory.makeSpecification(
                information_type=InformationType.PROPRIETARY)
            link = blueprint.linkSprint(sprint, blueprint.owner)
            link.acceptBy(sprint.owner)
        with QueryCollector() as recorder:
            self.getViewBrowser(sprint)
        self.assertThat(recorder, HasQueryCount(Equals(22)))
