# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'notify_bugtask_edited',
    ]


from lp.bugs.adapters.bugdelta import BugDelta
from lp.bugs.subscribers.bug import (
    add_bug_change_notifications,
    send_bug_details_to_new_bug_subscribers,
    )
from lp.registry.interfaces.person import IPerson
from lp.services.database.sqlbase import block_implicit_flushes
from lp.services.webapp.publisher import canonical_url


@block_implicit_flushes
def notify_bugtask_edited(modified_bugtask, event):
    """Notify CC'd subscribers of this bug that something has changed
    on this task.

    modified_bugtask must be an IBugTask. event must be an
    IObjectModifiedEvent.
    """
    bugtask_delta = event.object.getDelta(event.object_before_modification)
    bug_delta = BugDelta(
        bug=event.object.bug,
        bugurl=canonical_url(event.object.bug),
        bugtask_deltas=bugtask_delta,
        user=IPerson(event.user))

    event_creator = IPerson(event.user)
    previous_subscribers = event.object_before_modification.bug_subscribers
    current_subscribers = event.object.bug_subscribers
    prev_subs_set = set(previous_subscribers)
    cur_subs_set = set(current_subscribers)
    new_subs = cur_subs_set.difference(prev_subs_set)

    add_bug_change_notifications(
        bug_delta, old_bugtask=event.object_before_modification,
        new_subscribers=new_subs)

    send_bug_details_to_new_bug_subscribers(
        event.object.bug, previous_subscribers, current_subscribers,
        event_creator=event_creator)
