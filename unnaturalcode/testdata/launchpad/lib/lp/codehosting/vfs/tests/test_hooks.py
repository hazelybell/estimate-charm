# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the hooks in lp.codehosting.vfs.hooks."""

__metaclass__ = type

from lp.codehosting.vfs.hooks import SetProcTitleHook
from lp.testing import TestCase


class FakeSetProcTitleModule:
    """A fake for the setproctitle module.

    The `setproctitle` module (obviously) has global effects, so can't really
    be used in unit tests.  Instances of this class can be used as a safe
    replacement.
    """

    def __init__(self, initial_title):
        self.title = initial_title

    def getproctitle(self):
        return self.title

    def setproctitle(self, new_title):
        self.title = new_title


class TestSetProcTitleHook(TestCase):
    """Tests for `SetProcTitleHook`."""

    def test_hook_once(self):
        # Calling the hook once records the passed branch identifier in the
        # process title.
        initial_title = self.factory.getUniqueString()
        setproctitle_mod = FakeSetProcTitleModule(initial_title)
        branch_url = self.factory.getUniqueString()
        hook = SetProcTitleHook(setproctitle_mod)
        hook.seen(branch_url)
        self.assertEqual(
            initial_title + " BRANCH:" + branch_url,
            setproctitle_mod.getproctitle())

    def test_hook_twice(self):
        # Calling the hook twice replaces the first branch identifier in the
        # process title.
        initial_title = self.factory.getUniqueString()
        setproctitle_mod = FakeSetProcTitleModule(initial_title)
        branch_url1 = self.factory.getUniqueString()
        branch_url2 = self.factory.getUniqueString()
        hook = SetProcTitleHook(setproctitle_mod)
        hook.seen(branch_url1)
        hook.seen(branch_url2)
        self.assertEqual(
            initial_title + " BRANCH:" + branch_url2,
            setproctitle_mod.getproctitle())
