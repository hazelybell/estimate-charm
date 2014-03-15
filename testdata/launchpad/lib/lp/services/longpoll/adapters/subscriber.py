# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Long poll adapters."""

__metaclass__ = type
__all__ = [
    "generate_subscribe_key",
    "LongPollApplicationRequestSubscriber",
    ]

from uuid import uuid4

from lazr.restful.interfaces import IJSONRequestCache
from zope.component import (
    adapts,
    getUtility,
    )
from zope.interface import implements
from zope.publisher.interfaces import IApplicationRequest

from lp.services.config import config
from lp.services.longpoll.interfaces import ILongPollSubscriber
from lp.services.messaging.interfaces import IMessageSession


def generate_subscribe_key():
    """Generate a suitable new, unique, subscribe key."""
    return "longpoll.subscribe.%s" % uuid4()


class LongPollApplicationRequestSubscriber:

    adapts(IApplicationRequest)
    implements(ILongPollSubscriber)

    def __init__(self, request):
        self.request = request

    @property
    def subscribe_key(self):
        objects = IJSONRequestCache(self.request).objects
        if "longpoll" in objects:
            return objects["longpoll"]["key"]
        return None

    def subscribe(self, event):
        cache = IJSONRequestCache(self.request)
        if "longpoll" not in cache.objects:
            cache.objects["longpoll"] = {
                "uri": config.txlongpoll.uri,
                "key": generate_subscribe_key(),
                "subscriptions": [],
                }
        session = getUtility(IMessageSession)
        subscribe_queue = session.getConsumer(self.subscribe_key)
        producer = session.getProducer(event.event_key)
        producer.associateConsumer(subscribe_queue)
        cache.objects["longpoll"]["subscriptions"].append(event.event_key)
