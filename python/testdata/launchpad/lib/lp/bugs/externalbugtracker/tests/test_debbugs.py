# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the Debian bugtracker"""

import email.message
import errno
import os

from testtools.matchers import (
    Equals,
    IsInstance,
    raises,
    )

from lp.bugs.externalbugtracker.debbugs import (
    DebBugs,
    DebBugsDatabaseNotFound,
    )
from lp.bugs.interfaces.bugtask import (
    BugTaskImportance,
    BugTaskStatus,
    )
from lp.bugs.scripts.debbugs import (
    SummaryParseError,
    SummaryVersionError,
    )
from lp.testing import TestCase


class TestDebBugs(TestCase):

    def setUp(self):
        super(TestDebBugs, self).setUp()
        self.tempdir = self.makeTemporaryDirectory()

    def get_tracker(self):
        return DebBugs("http://testing.invalid", db_location=self.tempdir)

    def make_bug_summary(self, bug_id, format_version=2, headers=None):
        """Create a bug summary file on disk"""
        bucket_name = "%02d" % (int(bug_id) % 100,)
        bucket = os.path.join(self.tempdir, "db-h", bucket_name)
        try:
            os.makedirs(bucket)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise
        m = email.message.Message()
        # For whatever reason Date is a unix timestamp not an email datestamp
        m["Date"] = "1000000000"
        if format_version > 1:
            m["Format-Version"] = str(format_version)
        m["Message-Id"] = "<%s@testing.invalid>" % (bug_id,)
        if headers is not None:
            for h in headers:
                m[h] = headers[h]
        with open(os.path.join(bucket, "%s.summary" % (bug_id,)), "wb") as f:
            f.write(m.as_string())

    def test_no_db_dir(self):
        err = self.assertRaises(DebBugsDatabaseNotFound, self.get_tracker)
        self.assertThat(err.url, Equals(self.tempdir))

    def check_status(self, bug_id, expect_status):
        tracker = self.get_tracker()
        remote_status = tracker.getRemoteStatus(bug_id)
        lp_status = tracker.convertRemoteStatus(remote_status)
        self.assertThat(lp_status, Equals(expect_status))

    def test_status_missing(self):
        self.make_bug_summary("1")
        self.check_status("1", BugTaskStatus.NEW)

    def test_status_upstream(self):
        self.make_bug_summary("1", headers={"Tags": "upstream"})
        self.check_status("1", BugTaskStatus.CONFIRMED)

    def test_status_forwarded_to(self):
        self.make_bug_summary("1", headers={
            "Forwarded-To": "https://bugs.launchpad.net/ubuntu/+bug/1",
            })
        self.check_status("1", BugTaskStatus.CONFIRMED)

    def test_status_moreinfo(self):
        self.make_bug_summary("1", headers={"Tags": "moreinfo"})
        self.check_status("1", BugTaskStatus.INCOMPLETE)

    def test_status_wontfix(self):
        self.make_bug_summary("1", headers={"Tags": "upstream wontfix"})
        self.check_status("1", BugTaskStatus.WONTFIX)

    def test_status_done(self):
        self.make_bug_summary("1", headers={
            "Done": "A Maintainer <a.maintainer@example.com>",
            })
        self.check_status("1", BugTaskStatus.FIXRELEASED)

    def test_severity_missing(self):
        """Without severity set importance is set to unknown"""
        self.make_bug_summary("1")
        tracker = self.get_tracker()
        severity = tracker.getRemoteImportance("1")
        importance = tracker.convertRemoteImportance(severity)
        self.assertThat(importance, Equals(BugTaskImportance.UNKNOWN))

    def test_severity_ignored(self):
        """Severity exists in debbugs but is ignored by launchpad"""
        self.make_bug_summary("1", headers={"Severity": "normal"})
        tracker = self.get_tracker()
        severity = tracker.getRemoteImportance("1")
        importance = tracker.convertRemoteImportance(severity)
        self.assertThat(importance, Equals(BugTaskImportance.UNKNOWN))

    def test_format_version_1(self):
        """Initial format without version marker is rejected"""
        self.make_bug_summary("1", format_version=1)
        tracker = self.get_tracker()
        self.assertThat(lambda: tracker.getRemoteStatus("1"),
            raises(SummaryParseError))
        tracker.getRemoteImportance("1")

    def test_format_version_3(self):
        """Updated format with different escaping is not rejected"""
        self.make_bug_summary("1", format_version=3)
        tracker = self.get_tracker()
        tracker.getRemoteStatus("1")
        tracker.getRemoteImportance("1")

    def test_format_version_4(self):
        """A hypothetical summary format version 4 is rejected"""
        self.make_bug_summary("1", format_version=4)
        tracker = self.get_tracker()
        self.assertThat(lambda: tracker.getRemoteStatus("1"),
            raises(SummaryVersionError))
        tracker.getRemoteImportance("1")

    def test_non_ascii_v2(self):
        """Format-Version 2 RFC 1522 encoding on headers should not break"""
        self.make_bug_summary("1", headers={
            "Submitter": "=?UTF-8?Q?Jes=C3=BAs?= <jesus@example.com>",
            "Subject": "Add =?UTF-8?Q?Jes=C3=BAs?= as a Debian Maintainer",
            "Package": "debian-maintainers",
            })
        tracker = self.get_tracker()
        self.assertThat(tracker.getRemoteStatus("1"), IsInstance(str))
        self.assertThat(tracker.getRemoteImportance("1"), IsInstance(str))

    def test_non_ascii_v3(self):
        """Format-Version 2 UTF-8 encoding on headers should not break"""
        self.make_bug_summary("1", format_version=3, headers={
            "Submitter": "Jes\xc3\xbas <jesus@example.com>",
            "Subject": "Add Jes\xc3\xbas as a Debian Maintainer",
            "Package": "debian-maintainers",
            })
        tracker = self.get_tracker()
        self.assertThat(tracker.getRemoteStatus("1"), IsInstance(str))
        self.assertThat(tracker.getRemoteImportance("1"), IsInstance(str))
