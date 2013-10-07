# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the modified branches script."""

__metaclass__ = type

from datetime import datetime
import os

import pytz

from lp.code.enums import BranchType
from lp.codehosting.scripts.modifiedbranches import ModifiedBranchesScript
from lp.codehosting.vfs import branch_id_to_path
from lp.services.config import config
from lp.services.scripts.base import LaunchpadScriptFailure
from lp.testing import (
    TestCase,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestModifiedBranchesLocations(TestCaseWithFactory):
    """Test the ModifiedBranchesScript.branch_locations method."""

    layer = DatabaseFunctionalLayer

    def test_branch(self):
        # A branch location is the physical disk directory.
        branch = self.factory.makeAnyBranch(branch_type=BranchType.HOSTED)
        script = ModifiedBranchesScript('modified-branches', test_args=[])
        location = script.branch_location(branch)
        path = branch_id_to_path(branch.id)
        self.assertEqual(
            os.path.join(config.codehosting.mirrored_branches_root, path),
            location)


class TestModifiedBranchesLastModifiedEpoch(TestCase):
    """Test the calculation of the last modifed date."""

    def test_no_args(self):
        # The script needs one of --since or --last-hours to be specified.
        script = ModifiedBranchesScript(
            'modified-branches', test_args=[])
        self.assertRaises(
            LaunchpadScriptFailure,
            script.get_last_modified_epoch)

    def test_both_args(self):
        # We don't like it if both --since and --last-hours are specified.
        script = ModifiedBranchesScript(
            'modified-branches',
            test_args=['--since=2009-03-02', '--last-hours=12'])
        self.assertRaises(
            LaunchpadScriptFailure,
            script.get_last_modified_epoch)

    def test_modified_since(self):
        # The --since parameter is parsed into a datetime using the fairly
        # standard YYYY-MM-DD format.
        script = ModifiedBranchesScript(
            'modified-branches', test_args=['--since=2009-03-02'])
        self.assertEqual(
            datetime(2009, 3, 2, tzinfo=pytz.UTC),
            script.get_last_modified_epoch())

    def test_modified_since_bad_format(self):
        # Passing in a bad format string for the --since parameter errors.
        script = ModifiedBranchesScript(
            'modified-branches', test_args=['--since=2009-03'])
        self.assertRaises(
            LaunchpadScriptFailure,
            script.get_last_modified_epoch)

    def test_modified_last_hours(self):
        # If last_hours is specified, that number of hours is removed from the
        # current timestamp to work out the selection epoch.
        script = ModifiedBranchesScript(
            'modified-branches', test_args=['--last-hours=12'])
        # Override the script's now_timestamp to have a definitive test.
        # 3pm on the first of January.
        script.now_timestamp = datetime(2009, 1, 1, 15, tzinfo=pytz.UTC)
        # The last modified should be 3am on the same day.
        self.assertEqual(
            datetime(2009, 1, 1, 3, tzinfo=pytz.UTC),
            script.get_last_modified_epoch())


class TestModifiedBranchesStripPrefix(TestCase):
    """Test the prefix stripping."""

    def test_no_args(self):
        # The prefix defaults for '/srv/' for the ease of the main callers.
        # Still need to pass in one of --since or --last-hours.
        script = ModifiedBranchesScript(
            'modified-branches', test_args=['--last-hours=12'])
        self.assertEqual('/srv/', script.options.strip_prefix)

    def test_override(self):
        # The default can be overrided with the --strip-prefix option.
        # Still need to pass in one of --since or --last-hours.
        script = ModifiedBranchesScript(
            'modified-branches',
            test_args=['--last-hours=12', '--strip-prefix=foo'])
        self.assertEqual('foo', script.options.strip_prefix)

    def test_prefix_is_stripped(self):
        # If the location starts with the prefix, it is stripped.
        script = ModifiedBranchesScript(
            'modified-branches', test_args=['--last-hours=12'])
        # Override the append_suffix as we aren't testing that here.
        script.options.append_suffix = ''
        location = script.process_location('/srv/testing')
        self.assertEqual('testing', location)

    def test_non_matching_location_unchanged(self):
        # If the location doesn't match, it is left unchanged.
        script = ModifiedBranchesScript(
            'modified-branches', test_args=['--last-hours=12'])
        # Override the append_suffix as we aren't testing that here.
        script.options.append_suffix = ''
        location = script.process_location('/var/testing')
        self.assertEqual('/var/testing', location)


class TestModifiedBranchesAppendSuffix(TestCase):
    """Test the suffix appending."""

    def test_no_args(self):
        # The suffix defaults for '/**' for the ease of the main callers.
        # Still need to pass in one of --since or --last-hours.
        script = ModifiedBranchesScript(
            'modified-branches', test_args=['--last-hours=12'])
        self.assertEqual('/**', script.options.append_suffix)

    def test_override(self):
        # The default can be overrided with the --append-suffix option.
        # Still need to pass in one of --since or --last-hours.
        script = ModifiedBranchesScript(
            'modified-branches',
            test_args=['--last-hours=12', '--append-suffix=foo'])
        self.assertEqual('foo', script.options.append_suffix)

    def test_suffix_appended(self):
        # The suffix is appended to all branch locations.
        script = ModifiedBranchesScript(
            'modified-branches', test_args=['--last-hours=12'])
        location = script.process_location('/var/testing')
        self.assertEqual('/var/testing/**', location)


class TestModifiedBranchesUpdateLocations(TestCase):
    """Test the path splitting an reassebly adding to locations."""

    def setUp(self):
        super(TestModifiedBranchesUpdateLocations, self).setUp()
        self.script = ModifiedBranchesScript(
            'modified-branches', test_args=['--last-hours=12'])

    def test_locations_initially_empty(self):
        # The locations starts out as an empty set.
        self.assertEqual(set(), self.script.locations)

    def test_single_path_element(self):
        # Adding a single element should just add that.
        self.script.update_locations('foo')
        self.assertEqual(set(['foo']), self.script.locations)

    def test_single_root_element(self):
        # If the single element starts with a /, the locations do not include
        # an empty string.
        self.script.update_locations('/foo')
        self.assertEqual(set(['/foo']), self.script.locations)

    def test_multi_path_element(self):
        # Adding a "real" path will also include all the parents.
        self.script.update_locations('foo/bar/baz')
        expected = set(['foo', 'foo/bar', 'foo/bar/baz'])
        self.assertEqual(expected, self.script.locations)

    def test_duplicates(self):
        # Adding paths with common parentage doesn't cause duplicates.
        self.script.update_locations('foo/bar/baz')
        self.script.update_locations('foo/bar/who')
        expected = set(['foo', 'foo/bar', 'foo/bar/baz', 'foo/bar/who'])
        self.assertEqual(expected, self.script.locations)
