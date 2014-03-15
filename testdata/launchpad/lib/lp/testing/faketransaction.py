# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Fake transaction manager."""

__metaclass__ = type
__all__ = ['FakeTransaction']


class FakeTransaction:
    """Fake transaction manager.

    Use this instead of `transaction` (or the old Zopeless transaction
    manager) in tests if you don't really want to commit anything.

    Set `log_calls` to True to enable printing of commits and aborts.
    """
    commit_count = 0

    def __init__(self, log_calls=False):
        self.log_calls = log_calls

    def _log(self, call):
        """Print calls that are being made, if desired."""
        if self.log_calls:
            print call

    def begin(self):
        """Pretend to begin a transaction.  Does not log."""

    def commit(self):
        """Pretend to commit."""
        self.commit_count += 1
        self._log("COMMIT")

    def abort(self):
        """Pretend to roll back."""
        self._log("ABORT")
