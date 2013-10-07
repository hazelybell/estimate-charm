# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Long-poll infrastructure interfaces."""

__metaclass__ = type
__all__ = [
    "ILongPollEvent",
    "ILongPollSubscriber",
    "long_poll_event",
    ]

from zope.component import adapter
from zope.interface import (
    Attribute,
    classImplements,
    Interface,
    )


class ILongPollEvent(Interface):

    source = Attribute("The event source.")

    event_key = Attribute(
        "The key with which events will be emitted. Should be predictable "
        "and stable.")

    def emit(**data):
        """Emit the given data to `event_key`.

        :param data: Any data structures that can be dumped as JSON.
        """


class ILongPollSubscriber(Interface):

    subscribe_key = Attribute(
        "The key which the subscriber must know in order to be able "
        "to long-poll for subscribed events. Should be infeasible to "
        "guess, a UUID for example.")

    def subscribe(event):
        """Subscribe to the given event.

        :type event: ILongPollEvent
        """


def long_poll_event(source_spec):
    """Class decorator to declare an `ILongPollEvent`.

    :param source_spec: An interface or other specification understood by
        `zope.component` (a plain class can be passed too) that defines the
        source of an event. `IJob` or `storm.base.Storm` for example.
    """
    declare_adapter = adapter(source_spec)

    def declare_event(cls):
        classImplements(cls, ILongPollEvent)
        declare_adapter(cls)
        return cls

    return declare_event
