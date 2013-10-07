# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Things that help with testing of longpoll."""

__metaclass__ = type
__all__ = [
    "capture_longpoll_emissions",
    "LongPollEventRecord",
    ]

from collections import namedtuple
from contextlib import contextmanager
from functools import partial

from lp.services.longpoll.adapters import event


LongPollEventRecord = namedtuple(
    "LongPollEventRecord", ("event_key", "data"))


class LoggingRouter:
    """A test double for `IMessageProducer`.

    Saves messages as `LongPollEventRecord` tuples to a log.

    :param log: A callable accepting a single `LongPollEventRecord`.
    :param routing_key: See `IMessageSession.getProducer`.
    """

    def __init__(self, log, routing_key):
        self.log = log
        self.routing_key = routing_key

    def send(self, data):
        record = LongPollEventRecord(self.routing_key, data)
        self.log(record)


@contextmanager
def capture_longpoll_emissions():
    """Capture longpoll emissions while this context is in force.

    This returns a list in which `LongPollEventRecord` tuples will be
    recorded, in the order they're emitted.

    Note that normal event emission is *suppressed globally* while this
    context is in force; *all* events will be stored in the log.
    """
    log = []
    original_router_factory = event.router_factory
    event.router_factory = partial(LoggingRouter, log.append)
    try:
        yield log
    finally:
        event.router_factory = original_router_factory
