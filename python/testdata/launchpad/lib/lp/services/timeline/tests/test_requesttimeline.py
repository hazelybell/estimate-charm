# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests of requesttimeline."""

__metaclass__ = type

import testtools
from timeline.timeline import Timeline
from zope.publisher.browser import TestRequest

from lp.services import webapp
from lp.services.timeline.requesttimeline import (
    get_request_timeline,
    set_request_timeline,
    )


class TestRequestTimeline(testtools.TestCase):

    # These disabled tests are for the desired API using request annotations.
    # bug=623199 describes some issues with why this doesn't work.
    def disabled_test_new_request_get_request_timeline_works(self):
        req = TestRequest()
        timeline = get_request_timeline(req)
        self.assertIsInstance(timeline, Timeline)

    def disabled_test_same_timeline_repeated_calls(self):
        req = TestRequest()
        timeline = get_request_timeline(req)
        self.assertEqual(timeline, get_request_timeline(req))

    def disabled_test_set_timeline(self):
        req = TestRequest()
        timeline = Timeline()
        set_request_timeline(req, timeline)
        self.assertEqual(timeline, get_request_timeline(req))

    # Tests while adapter._local contains the timeline --start---
    # Delete when bug=623199 is fixed and the timeline store moved to
    # annotations.
    def test_new_request_get_request_timeline_uses_webapp(self):
        req = TestRequest()
        timeline = get_request_timeline(req)
        self.assertIsInstance(timeline, Timeline)
        self.assertTrue(webapp.adapter._local.request_timeline is timeline)

    def test_same_timeline_repeated_calls(self):
        req = TestRequest()
        timeline = get_request_timeline(req)
        self.assertEqual(timeline, get_request_timeline(req))

    def test_set_timeline(self):
        req = TestRequest()
        timeline = Timeline()
        set_request_timeline(req, timeline)
        self.assertEqual(timeline, get_request_timeline(req))
    # Tests while adapter._local contains the timeline ---end---
