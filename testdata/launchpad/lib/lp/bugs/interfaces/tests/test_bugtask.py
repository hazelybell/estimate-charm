# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for BugTask interfaces."""

__metaclass__ = type

from lp.bugs.interfaces.bugtask import (
    BugTaskStatus,
    BugTaskStatusSearch,
    BugTaskStatusSearchDisplay,
    get_bugtask_status,
    normalize_bugtask_status,
    )
from lp.testing import TestCase


class TestFunctions(TestCase):

    def test_get_bugtask_status(self):
        # Compose a map of BugTaskStatusSearch members from their values.
        expected = dict(
            (status.value, status)
            for status in BugTaskStatusSearch.items)
        # Update the expected status map - overwriting some entries - from
        # BugTaskStatus members and their values.
        expected.update(
            (status.value, status)
            for status in BugTaskStatus.items)
        # Compose a map of statuses as discovered by value for each member of
        # BugTaskStatusSearch.
        observed = dict(
            (status.value, get_bugtask_status(status.value))
            for status in BugTaskStatusSearch.items)
        # Update the expected status map with statuses discovered by value for
        # each member of BugTaskStatus.
        observed.update(
            (status.value, get_bugtask_status(status.value))
            for status in BugTaskStatus.items)
        self.assertEqual(expected, observed)

    def test_normalize_bugtask_status_from_BugTaskStatus(self):
        expected = {
            BugTaskStatus.CONFIRMED: BugTaskStatus.CONFIRMED,
            BugTaskStatus.EXPIRED: BugTaskStatus.EXPIRED,
            BugTaskStatus.FIXCOMMITTED: BugTaskStatus.FIXCOMMITTED,
            BugTaskStatus.FIXRELEASED: BugTaskStatus.FIXRELEASED,
            BugTaskStatus.INCOMPLETE: BugTaskStatus.INCOMPLETE,
            BugTaskStatus.INPROGRESS: BugTaskStatus.INPROGRESS,
            BugTaskStatus.INVALID: BugTaskStatus.INVALID,
            BugTaskStatus.NEW: BugTaskStatus.NEW,
            BugTaskStatus.OPINION: BugTaskStatus.OPINION,
            BugTaskStatus.TRIAGED: BugTaskStatus.TRIAGED,
            BugTaskStatus.UNKNOWN: BugTaskStatus.UNKNOWN,
            BugTaskStatus.WONTFIX: BugTaskStatus.WONTFIX,
            }
        observed = dict(
            (status, normalize_bugtask_status(status))
            for status in BugTaskStatus.items)
        self.assertEqual(expected, observed)

    def test_normalize_bugtask_status_from_BugTaskStatusSearch(self):
        expected = {
            BugTaskStatusSearch.CONFIRMED: BugTaskStatus.CONFIRMED,
            BugTaskStatusSearch.EXPIRED: BugTaskStatus.EXPIRED,
            BugTaskStatusSearch.FIXCOMMITTED: BugTaskStatus.FIXCOMMITTED,
            BugTaskStatusSearch.FIXRELEASED: BugTaskStatus.FIXRELEASED,
            BugTaskStatusSearch.INCOMPLETE: BugTaskStatus.INCOMPLETE,
            BugTaskStatusSearch.INCOMPLETE_WITH_RESPONSE:
                BugTaskStatusSearch.INCOMPLETE_WITH_RESPONSE,
            BugTaskStatusSearch.INCOMPLETE_WITHOUT_RESPONSE:
                BugTaskStatusSearch.INCOMPLETE_WITHOUT_RESPONSE,
            BugTaskStatusSearch.INPROGRESS: BugTaskStatus.INPROGRESS,
            BugTaskStatusSearch.INVALID: BugTaskStatus.INVALID,
            BugTaskStatusSearch.NEW: BugTaskStatus.NEW,
            BugTaskStatusSearch.OPINION: BugTaskStatus.OPINION,
            BugTaskStatusSearch.TRIAGED: BugTaskStatus.TRIAGED,
            BugTaskStatusSearch.WONTFIX: BugTaskStatus.WONTFIX,
            }
        observed = dict(
            (status, normalize_bugtask_status(status))
            for status in BugTaskStatusSearch.items)
        self.assertEqual(expected, observed)

    def test_normalize_bugtask_status_from_BugTaskStatusSearchDisplay(self):
        expected = {
            BugTaskStatusSearchDisplay.CONFIRMED: BugTaskStatus.CONFIRMED,
            BugTaskStatusSearchDisplay.EXPIRED: BugTaskStatus.EXPIRED,
            BugTaskStatusSearchDisplay.FIXCOMMITTED:
                BugTaskStatus.FIXCOMMITTED,
            BugTaskStatusSearchDisplay.FIXRELEASED:
                BugTaskStatus.FIXRELEASED,
            BugTaskStatusSearchDisplay.INCOMPLETE_WITH_RESPONSE:
                BugTaskStatusSearch.INCOMPLETE_WITH_RESPONSE,
            BugTaskStatusSearchDisplay.INCOMPLETE_WITHOUT_RESPONSE:
                BugTaskStatusSearch.INCOMPLETE_WITHOUT_RESPONSE,
            BugTaskStatusSearchDisplay.INPROGRESS: BugTaskStatus.INPROGRESS,
            BugTaskStatusSearchDisplay.INVALID: BugTaskStatus.INVALID,
            BugTaskStatusSearchDisplay.NEW: BugTaskStatus.NEW,
            BugTaskStatusSearchDisplay.OPINION: BugTaskStatus.OPINION,
            BugTaskStatusSearchDisplay.TRIAGED: BugTaskStatus.TRIAGED,
            BugTaskStatusSearchDisplay.WONTFIX: BugTaskStatus.WONTFIX,
            }
        observed = dict(
            (status, normalize_bugtask_status(status))
            for status in BugTaskStatusSearchDisplay.items)
        self.assertEqual(expected, observed)
