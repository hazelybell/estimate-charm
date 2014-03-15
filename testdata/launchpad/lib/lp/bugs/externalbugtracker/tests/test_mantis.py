# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the Mantis BugTracker."""

__metaclass__ = type

import urllib2

from testtools.matchers import (
    Equals,
    Is,
    )

from lp.bugs.externalbugtracker import UnparsableBugData
from lp.bugs.externalbugtracker.mantis import (
    Mantis,
    MantisBugBatchParser,
    )
from lp.services.log.logger import BufferLogger
from lp.testing import (
    monkey_patch,
    TestCase,
    )
from lp.testing.fakemethod import FakeMethod
from lp.testing.layers import ZopelessLayer


class TestMantisBugBatchParser(TestCase):
    """Test the MantisBugBatchParser class."""

    def setUp(self):
        super(TestMantisBugBatchParser, self).setUp()
        self.logger = BufferLogger()

    def test_empty(self):
        data = []
        parser = MantisBugBatchParser(data, self.logger)
        exc = self.assertRaises(
            UnparsableBugData,
            parser.getBugs)
        self.assertThat(
            str(exc), Equals("Missing header line"))

    def test_missing_headers(self):
        data = ['some,headers']
        parser = MantisBugBatchParser(data, self.logger)
        exc = self.assertRaises(
            UnparsableBugData,
            parser.getBugs)
        self.assertThat(
            str(exc),
            Equals("CSV header ['some', 'headers'] missing fields:"
                   " ['id', 'status', 'resolution']"))

    def test_missing_some_headers(self):
        data = ['some,headers,status,resolution']
        parser = MantisBugBatchParser(data, self.logger)
        exc = self.assertRaises(
            UnparsableBugData,
            parser.getBugs)
        self.assertThat(
            str(exc),
            Equals("CSV header ['some', 'headers', 'status', 'resolution'] "
                   "missing fields: ['id']"))

    def test_no_bugs(self):
        data = ['other,fields,id,status,resolution']
        parser = MantisBugBatchParser(data, self.logger)
        self.assertThat(parser.getBugs(), Equals({}))

    def test_passing(self):
        data = [
            'ignored,id,resolution,status',
            'foo,42,not,complete',
            'boo,13,,confirmed',
            ]
        parser = MantisBugBatchParser(data, self.logger)
        bug_42 = dict(
            id=42, status='complete', resolution='not', ignored='foo')
        bug_13 = dict(
            id=13, status='confirmed', resolution='', ignored='boo')
        self.assertThat(parser.getBugs(), Equals({42: bug_42, 13: bug_13}))

    def test_incomplete_line(self):
        data = [
            'ignored,id,resolution,status',
            '42,not,complete',
            ]
        parser = MantisBugBatchParser(data, self.logger)
        self.assertThat(parser.getBugs(), Equals({}))
        log = self.logger.getLogBuffer()
        self.assertThat(
            log,
            Equals("WARNING Line ['42', 'not', 'complete'] incomplete.\n"))

    def test_non_integer_id(self):
        data = [
            'ignored,id,resolution,status',
            'foo,bar,not,complete',
            ]
        parser = MantisBugBatchParser(data, self.logger)
        self.assertThat(parser.getBugs(), Equals({}))
        log = self.logger.getLogBuffer()
        self.assertThat(
            log, Equals("WARNING Encountered invalid bug ID: 'bar'.\n"))


class TestMantisBugTracker(TestCase):
    """Tests for various methods of the Manits bug tracker."""

    layer = ZopelessLayer

    def test_csv_data_on_post_404(self):
        # If the 'view_all_set.php' request raises a 404, then the csv_data
        # attribute is None.
        base_url = "http://example.com/"

        fail_404 = urllib2.HTTPError('url', 404, 'Not Found', None, None)

        with monkey_patch(Mantis, urlopen=FakeMethod(failure=fail_404)):
            bugtracker = Mantis(base_url)
            self.assertThat(bugtracker.csv_data, Is(None))
