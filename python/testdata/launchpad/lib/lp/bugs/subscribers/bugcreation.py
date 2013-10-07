# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'at_least_one_task',
    ]

from lp.bugs.interfaces.bug import CreatedBugWithNoBugTasksError


def at_least_one_task(bug, event):
    """Make sure that the created bug has at least one task.

    CreatedBugWithNoBugTasksError is raised it if the bug has no tasks.
    """
    if len(bug.bugtasks) == 0:
        raise CreatedBugWithNoBugTasksError(
            "The bug has to affect at least one product or distribution.")
