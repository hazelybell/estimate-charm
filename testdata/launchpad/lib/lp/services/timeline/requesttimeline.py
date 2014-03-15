# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Manage a Timeline for a request."""

__all__ = [
    'get_request_timeline',
    'set_request_timeline',
    ]

__metaclass__ = type

from timeline import Timeline

# XXX RobertCollins 2010-09-01 bug=623199: Undesirable but pragmatic.
# Because of this bug, rather than using request.annotations we have
# to work in with the webapp.adapter request model, which is 
# different to that used by get_current_browser_request.
from lp.services import webapp


def get_request_timeline(request):
    """Get a `Timeline` for request.

    This should ideally return the request.annotations['timeline'], creating it
    if necessary. However due to bug 623199 it instead using the adapter
    context for 'requests'. Once bug 623199 is fixed it will instead use the
    request annotations.

    :param request: A zope/launchpad request object.
    :return: A timeline.timeline.Timeline object for the request.
    """
    try:
        return webapp.adapter._local.request_timeline
    except AttributeError:
        return set_request_timeline(request, Timeline())
    # Disabled code path: bug 623199, ideally we would use this code path.
    return request.annotations.setdefault('timeline', Timeline())


def set_request_timeline(request, timeline):
    """Explicitly set a timeline for request.

    This is used by code which wants to manually assemble a timeline.

    :param request: A zope/launchpad request object.
    :param timeline: A Timeline.
    """
    webapp.adapter._local.request_timeline = timeline
    return timeline
    # Disabled code path: bug 623199, ideally we would use this code path.
    request.annotations['timeline'] = timeline
