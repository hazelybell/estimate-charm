# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Long-poll event adapter tests."""

__metaclass__ = type

from zope.interface import implements

from lp.services.longpoll.adapters.event import (
    generate_event_key,
    LongPollEvent,
    )
from lp.services.longpoll.interfaces import ILongPollEvent
from lp.services.longpoll.testing import (
    capture_longpoll_emissions,
    LongPollEventRecord,
    )
from lp.testing import TestCase
from lp.testing.layers import LaunchpadFunctionalLayer
from lp.testing.matchers import Contains


class FakeEvent(LongPollEvent):

    implements(ILongPollEvent)

    @property
    def event_key(self):
        return "event-key-%s" % self.source


class TestLongPollEvent(TestCase):

    layer = LaunchpadFunctionalLayer

    def test_interface(self):
        event = FakeEvent("source")
        self.assertProvides(event, ILongPollEvent)

    def test_event_key(self):
        # event_key is not implemented in LongPollEvent; subclasses must
        # provide it.
        event = LongPollEvent("source")
        self.assertRaises(NotImplementedError, getattr, event, "event_key")

    def test_emit(self):
        # LongPollEvent.emit() sends the given data to `event_key`.
        event = FakeEvent("source")
        event_data = {"hello": 1234}
        with capture_longpoll_emissions() as log:
            event.emit(**event_data)
        expected_message = LongPollEventRecord(
            event_key=event.event_key,
            data=dict(event_data, event_key=event.event_key))
        self.assertThat(log, Contains(expected_message))


class TestFunctions(TestCase):

    def test_generate_event_key_no_components(self):
        self.assertRaises(
            AssertionError, generate_event_key)

    def test_generate_event_key(self):
        self.assertEqual(
            "longpoll.event.event-name",
            generate_event_key("event-name"))
        self.assertEqual(
            "longpoll.event.source-name.event-name",
            generate_event_key("source-name", "event-name"))
        self.assertEqual(
            "longpoll.event.type-name.source-name.event-name",
            generate_event_key("type-name", "source-name", "event-name"))

    def test_generate_event_key_stringifies_components(self):
        self.assertEqual(
            "longpoll.event.job.1234.COMPLETED",
            generate_event_key("job", 1234, "COMPLETED"))
