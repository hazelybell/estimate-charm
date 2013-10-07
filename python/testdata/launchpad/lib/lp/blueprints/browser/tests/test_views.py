# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""
Run the view tests.
"""

import logging
import os
import unittest

from fixtures import FakeLogger
from storm.store import Store
from testtools.matchers import LessThan

from lp.services.webapp import canonical_url
from lp.testing import (
    login,
    logout,
    TestCaseWithFactory,
    )
from lp.testing._webservice import QueryCollector
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.matchers import HasQueryCount
from lp.testing.sampledata import ADMIN_EMAIL
from lp.testing.systemdocs import (
    LayeredDocFileSuite,
    setUp,
    tearDown,
    )


class TestAssignments(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestAssignments, self).setUp()
        # Use a FakeLogger fixture to prevent Memcached warnings to be
        # printed to stdout while browsing pages.
        self.useFixture(FakeLogger())

    def invalidate_and_render(self, browser, dbobj, url):
        # Ensure caches have been flushed.
        store = Store.of(dbobj)
        store.flush()
        store.invalidate()
        browser.open(url)

    def check_query_counts_scaling_with_unique_people(self,
        target, targettype):
        """Check that a particular hasSpecifications target scales well.

        :param target: A spec target like a product.
        :param targettype: The parameter to pass to makeSpecification to
            associate the target. e.g. 'product'.
        """
        query_baseline = 40
        people = []
        for _ in range(10):
            people.append(self.factory.makePerson())
        specs = []
        for _ in range(10):
            specs.append(self.factory.makeSpecification(
                **{targettype: target}))
        collector = QueryCollector()
        collector.register()
        self.addCleanup(collector.unregister)
        url = canonical_url(target) + "/+assignments"
        viewer = self.factory.makePerson()
        browser = self.getUserBrowser(user=viewer)
        # Seed the cookie cache and any other cross-request state we may gain
        # in future.  See lp.services.webapp.serssion: _get_secret.
        browser.open(url)
        self.invalidate_and_render(browser, target, url)
        # Set a baseline
        self.assertThat(collector, HasQueryCount(LessThan(query_baseline)))
        no_assignees_count = collector.count
        # Assign many unique people, which shouldn't change the page queries.
        # Due to storm bug 619017 additional queries can be triggered when
        # revalidating people, so we allow -some- fuzz.
        login(ADMIN_EMAIL)
        for person, spec in zip(people, specs):
            spec.assignee = person
        logout()
        self.invalidate_and_render(browser, target, url)
        self.assertThat(
            collector, HasQueryCount(LessThan(no_assignees_count + 5)))

    def test_product_query_counts_scale_below_unique_people(self):
        self.check_query_counts_scaling_with_unique_people(
            self.factory.makeProduct(), 'product')

    def test_distro_query_counts_scale_below_unique_people(self):
        self.check_query_counts_scaling_with_unique_people(
            self.factory.makeDistribution(), 'distribution')


def test_suite():
    suite = unittest.TestLoader().loadTestsFromName(__name__)
    here = os.path.dirname(os.path.realpath(__file__))
    testsdir = os.path.abspath(here)

    # Add tests using default setup/teardown
    filenames = [filename
                 for filename in os.listdir(testsdir)
                 if filename.endswith('.txt')]
    # Sort the list to give a predictable order.
    filenames.sort()
    for filename in filenames:
        path = filename
        one_test = LayeredDocFileSuite(
            path, setUp=setUp, tearDown=tearDown,
            layer=DatabaseFunctionalLayer,
            stdout_logging_level=logging.WARNING)
        suite.addTest(one_test)

    return suite
