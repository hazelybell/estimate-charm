# Copyright 2011-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Long-poll infrastructure."""

__metaclass__ = type
__all__ = [
    "emit",
    "subscribe",
    ]

from lazr.restful.utils import get_current_browser_request
from zope.component import getAdapter

from lp.services.longpoll.interfaces import (
    ILongPollEvent,
    ILongPollSubscriber,
    )


def subscribe(target, event_name=u"", request=None):
    """Convenience method to subscribe the current request.

    :param target: Something that can be adapted to `ILongPollEvent`.
    :param event_name: The name of the event to subscribe to. This is used to
        look up a named adapter from `target` to `ILongPollEvent`.
    :param request: The request for which to get an `ILongPollSubscriber`. It
        a request is not specified the currently active request is used.
    :return: The `ILongPollEvent` that has been subscribed to.
    """
    event = getAdapter(target, ILongPollEvent, name=event_name)
    if request is None:
        request = get_current_browser_request()
    subscriber = ILongPollSubscriber(request)
    subscriber.subscribe(event)
    return event


def emit(source, event_name=u"", **data):
    """Convenience method to emit a message for an event.

    :param source: Something that can be adapted to `ILongPollEvent`.
    :param event_name: The name of the event to subscribe to. This is used to
        look up a named adapter from `target` to `ILongPollEvent`.
    :param data: See `ILongPollEvent.emit`.
    :return: The `ILongPollEvent` that has been emitted.
    """
    event = getAdapter(source, ILongPollEvent, name=event_name)
    event.emit(**data)
    return event
