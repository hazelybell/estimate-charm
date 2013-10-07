# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'noop',
    'pop_notifications'
    ]

# Force the correct celeryconfig to be used.
import lp.services.job.celeryjob

# Quiet lint unused import warning.
lp.services.job.celeryjob

from celery.task import task


@task
def pop_notifications():
    from lp.testing.mail_helpers import pop_notifications
    return pop_notifications()


@task
def noop():
    """Task that does nothing.

    Used to ensure that other tasks have completed.
    """
