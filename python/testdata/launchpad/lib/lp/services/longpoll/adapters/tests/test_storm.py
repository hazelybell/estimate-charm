# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Long-poll event adapter tests."""

__metaclass__ = type

from lazr.lifecycle.event import (
    ObjectCreatedEvent,
    ObjectDeletedEvent,
    ObjectModifiedEvent,
    )
from storm.base import Storm
from storm.properties import Int
from zope.event import notify
from zope.interface import Attribute

from lp.services.longpoll.adapters.storm import (
    gen_primary_key,
    get_primary_key,
    )
from lp.services.longpoll.interfaces import ILongPollEvent
from lp.services.longpoll.testing import (
    capture_longpoll_emissions,
    LongPollEventRecord,
    )
from lp.testing import TestCase
from lp.testing.layers import LaunchpadFunctionalLayer
from lp.testing.matchers import Provides


class FakeStormClass(Storm):

    __storm_table__ = 'FakeTable'

    id = Int(primary=True)


class FakeStormCompoundPrimaryKeyClass(Storm):

    __storm_table__ = 'FakeTableWithCompoundPrimaryKey'
    __storm_primary__ = 'id1', 'id2'

    id1 = Int()
    id2 = Int()


class TestFunctions(TestCase):

    def test_gen_primary_key(self):
        # gen_primary_key() returns an iterable of values from the model
        # instance's primary key.
        storm_object = FakeStormClass()
        storm_object.id = 1234
        self.assertEqual([1234], list(gen_primary_key(storm_object)))

    def test_gen_primary_key_compound_key(self):
        # gen_primary_key() returns an iterable of values from the model
        # instance's primary key.
        storm_object = FakeStormCompoundPrimaryKeyClass()
        storm_object.id1 = 1234
        storm_object.id2 = 5678
        self.assertEqual([1234, 5678], list(gen_primary_key(storm_object)))

    def test_get_primary_key(self):
        # get_primary_key() returns the value of the model instance's primary
        # key.
        storm_object = FakeStormClass()
        storm_object.id = 1234
        self.assertEqual(1234, get_primary_key(storm_object))

    def test_get_primary_key_compound_key(self):
        # get_primary_key() returns a tuple of all the values in the model
        # instance's primary key when the model uses a compound primary key.
        storm_object = FakeStormCompoundPrimaryKeyClass()
        storm_object.id1 = 1234
        storm_object.id2 = 5678
        self.assertEqual((1234, 5678), get_primary_key(storm_object))


class TestStormLifecycle(TestCase):

    layer = LaunchpadFunctionalLayer

    def test_storm_event_adapter(self):
        storm_object = FakeStormClass()
        storm_object.id = 1234
        event = ILongPollEvent(storm_object)
        self.assertThat(event, Provides(ILongPollEvent))
        self.assertEqual(
            "longpoll.event.faketable.1234",
            event.event_key)

    def test_storm_creation_event_adapter(self):
        event = ILongPollEvent(FakeStormClass)
        self.assertThat(event, Provides(ILongPollEvent))
        self.assertEqual(
            "longpoll.event.faketable",
            event.event_key)

    def test_storm_object_created(self):
        storm_object = FakeStormClass()
        storm_object.id = 1234
        with capture_longpoll_emissions() as log:
            notify(ObjectCreatedEvent(storm_object))
        expected = LongPollEventRecord(
            "longpoll.event.faketable", {
                "event_key": "longpoll.event.faketable",
                "what": "created",
                "id": 1234,
                })
        self.assertEqual([expected], log)

    def test_storm_object_deleted(self):
        storm_object = FakeStormClass()
        storm_object.id = 1234
        with capture_longpoll_emissions() as log:
            notify(ObjectDeletedEvent(storm_object))
        expected = LongPollEventRecord(
            "longpoll.event.faketable.1234", {
                "event_key": "longpoll.event.faketable.1234",
                "what": "deleted",
                "id": 1234,
                })
        self.assertEqual([expected], log)

    def test_storm_object_modified(self):
        storm_object = FakeStormClass()
        storm_object.id = 1234
        with capture_longpoll_emissions() as log:
            object_event = ObjectModifiedEvent(
                storm_object, storm_object, ("itchy", "scratchy"))
            notify(object_event)
        expected = LongPollEventRecord(
            "longpoll.event.faketable.1234", {
                "event_key": "longpoll.event.faketable.1234",
                "what": "modified",
                "edited_fields": ["itchy", "scratchy"],
                "id": 1234,
                })
        self.assertEqual([expected], log)

    def test_storm_object_modified_no_edited_fields(self):
        # A longpoll event is not emitted unless edited_fields is populated.
        storm_object = FakeStormClass()
        storm_object.id = 1234
        with capture_longpoll_emissions() as log:
            notify(ObjectModifiedEvent(storm_object, storm_object, None))
        self.assertEqual([], log)
        with capture_longpoll_emissions() as log:
            notify(ObjectModifiedEvent(storm_object, storm_object, ()))
        self.assertEqual([], log)

    def test_storm_object_modified_edited_fields_are_zope_attributes(self):
        # The names of IAttribute fields in edited_fields are used in the
        # longpoll event.
        storm_object = FakeStormClass()
        storm_object.id = 1234
        with capture_longpoll_emissions() as log:
            object_event = ObjectModifiedEvent(
                storm_object, storm_object, ("foo", Attribute("bar")))
            notify(object_event)
        expected = LongPollEventRecord(
            "longpoll.event.faketable.1234", {
                "event_key": "longpoll.event.faketable.1234",
                "what": "modified",
                "edited_fields": ["bar", "foo"],
                "id": 1234,
                })
        self.assertEqual([expected], log)
