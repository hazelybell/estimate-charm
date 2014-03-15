# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the JSON serializer."""

__metaclass__ = type

from datetime import timedelta

from lazr.restful.interfaces import IJSONPublishable

from lp.services.webservice.json import StrJSONSerializer
from lp.testing import TestCase
from lp.testing.layers import FunctionalLayer


class TestStrJSONSerializer(TestCase):
    layer = FunctionalLayer

    def test_toDataForJSON(self):
        serializer = StrJSONSerializer(
            timedelta(days=2, hours=2, seconds=5))
        self.assertEquals(
            '2 days, 2:00:05',
            serializer.toDataForJSON('application/json'))

    def test_timedelta_users_StrJSONSerializer(self):
        delta = timedelta(seconds=5)
        serializer = IJSONPublishable(delta)
        self.assertEquals('0:00:05',
            serializer.toDataForJSON('application/json'))
