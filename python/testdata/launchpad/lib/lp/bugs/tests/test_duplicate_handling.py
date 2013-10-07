# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for bug duplicate validation."""

from textwrap import dedent

from zope.security.interfaces import ForbiddenAttribute

from lp.bugs.errors import InvalidDuplicateValue
from lp.services.webapp.escaping import html_escape
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


class TestDuplicateAttributes(TestCaseWithFactory):
    """Test bug attributes related to duplicate handling."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestDuplicateAttributes, self).setUp(user='test@canonical.com')

    def setDuplicateofDirectly(self, bug, duplicateof):
        """Helper method to set duplicateof directly."""
        bug.duplicateof = duplicateof

    def test_duplicateof_readonly(self):
        # Test that no one can set duplicateof directly.
        bug = self.factory.makeBug()
        dupe_bug = self.factory.makeBug()
        self.assertRaises(
            ForbiddenAttribute, self.setDuplicateofDirectly, bug, dupe_bug)


class TestMarkDuplicateValidation(TestCaseWithFactory):
    """Test for validation around marking bug duplicates."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestMarkDuplicateValidation, self).setUp(
            user='test@canonical.com')
        self.bug = self.factory.makeBug()
        self.dupe_bug = self.factory.makeBug()
        self.dupe_bug.markAsDuplicate(self.bug)
        self.possible_dupe = self.factory.makeBug()

    def assertDuplicateError(self, bug, duplicateof, msg):
        try:
            bug.markAsDuplicate(duplicateof)
        except InvalidDuplicateValue as err:
            self.assertEqual(str(err), msg)

    def test_error_on_duplicate_to_duplicate(self):
        # Test that a bug cannot be marked a duplicate of
        # a bug that is already itself a duplicate.
        msg = dedent(u"""
            Bug %s is already a duplicate of bug %s. You
            can only mark a bug report as duplicate of one that
            isn't a duplicate itself.
            """ % (
                self.dupe_bug.id, self.dupe_bug.duplicateof.id))
        self.assertDuplicateError(
            self.possible_dupe, self.dupe_bug, html_escape(msg))

    def test_error_duplicate_to_itself(self):
        # Test that a bug cannot be marked its own duplicate
        msg = html_escape(dedent(u"""
            You can't mark a bug as a duplicate of itself."""))
        self.assertDuplicateError(self.bug, self.bug, msg)


class TestMoveDuplicates(TestCaseWithFactory):
    """Test duplicates are moved when master bug is marked a duplicate."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestMoveDuplicates, self).setUp(user='test@canonical.com')

    def test_duplicates_are_moved(self):
        # Confirm that a bug with two duplicates can be marked
        # a duplicate of a new bug and that the duplicates will
        # be re-marked as duplicates of the new bug, too.
        bug = self.factory.makeBug()
        dupe_one = self.factory.makeBug()
        dupe_two = self.factory.makeBug()
        dupe_one.markAsDuplicate(bug)
        dupe_two.markAsDuplicate(bug)
        self.assertEqual(dupe_one.duplicateof, bug)
        self.assertEqual(dupe_two.duplicateof, bug)
        new_bug = self.factory.makeBug()
        bug.markAsDuplicate(new_bug)
        self.assertEqual(bug.duplicateof, new_bug)
        self.assertEqual(dupe_one.duplicateof, new_bug)
        self.assertEqual(dupe_two.duplicateof, new_bug)
