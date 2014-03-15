# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the BugActivity code."""

__metaclass__ = type

from lazr.lifecycle.event import ObjectModifiedEvent
from lazr.lifecycle.snapshot import Snapshot

from lp.bugs.interfaces.bug import IBug
from lp.bugs.subscribers.bugactivity import what_changed
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestWhatChanged(TestCaseWithFactory):
    """Tests for the what_changed function."""

    layer = DatabaseFunctionalLayer

    def test_what_changed_works_with_fieldnames(self):
        # When what_changed is passed an ObjectModifiedEvent with a list
        # of fieldnames in its edited_fields property, it will deal with
        # those fields appropriately.
        bug = self.factory.makeBug()
        bug_before_modification = Snapshot(bug, providing=IBug)
        with person_logged_in(bug.owner):
            bug.setPrivate(True, bug.owner)
        event = ObjectModifiedEvent(
            bug, bug_before_modification, ['private'])
        expected_changes = {'private': ['False', 'True']}
        changes = what_changed(event)
        self.assertEqual(expected_changes, changes)

    def test_what_changed_works_with_field_instances(self):
        # Sometimes something will pass what_changed an
        # ObjectModifiedEvent where the edited_fields list contains
        # field instances. what_changed handles that correctly, too.
        bug = self.factory.makeBug()
        bug_before_modification = Snapshot(bug, providing=IBug)
        with person_logged_in(bug.owner):
            bug.setPrivate(True, bug.owner)
        event = ObjectModifiedEvent(
            bug, bug_before_modification, [IBug['private']])
        expected_changes = {'private': ['False', 'True']}
        changes = what_changed(event)
        self.assertEqual(expected_changes, changes)
