# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the builders webservice ."""

__metaclass__ = type

from lp.testing import (
    api_url,
    logout,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.pages import LaunchpadWebServiceCaller


class TestBuildersCollection(TestCaseWithFactory):
    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBuildersCollection, self).setUp()
        self.webservice = LaunchpadWebServiceCaller()

    def test_getBuildQueueSizes(self):
        logout()
        results = self.webservice.named_get(
            '/builders', 'getBuildQueueSizes', api_version='devel')
        self.assertEquals(
            ['nonvirt', 'virt'], sorted(results.jsonBody().keys()))

    def test_getBuildersForQueue(self):
        g1 = self.factory.makeProcessor('g1')
        quantum = self.factory.makeProcessor('quantum')
        self.factory.makeBuilder(
            processor=quantum, name='quantum_builder1')
        self.factory.makeBuilder(
            processor=quantum, name='quantum_builder2')
        self.factory.makeBuilder(
            processor=quantum, name='quantum_builder3', virtualized=False)
        self.factory.makeBuilder(
            processor=g1, name='g1_builder', virtualized=False)

        logout()
        results = self.webservice.named_get(
            '/builders', 'getBuildersForQueue',
            processor=api_url(quantum), virtualized=True,
            api_version='devel').jsonBody()
        self.assertEquals(
            ['quantum_builder1', 'quantum_builder2'],
            sorted(builder['name'] for builder in results['entries']))


class TestBuilderEntry(TestCaseWithFactory):
    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBuilderEntry, self).setUp()
        self.webservice = LaunchpadWebServiceCaller()

    def test_exports_processor(self):
        processor = self.factory.makeProcessor('s1')
        builder = self.factory.makeBuilder(processor=processor)

        logout()
        entry = self.webservice.get(
            api_url(builder), api_version='devel').jsonBody()
        self.assertEndsWith(entry['processor_link'], '/+processors/s1')
