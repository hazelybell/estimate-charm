# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Long-poll life-cycle adapters."""

from __future__ import absolute_import

__metaclass__ = type
__all__ = []

from lazr.lifecycle.interfaces import (
    IObjectCreatedEvent,
    IObjectDeletedEvent,
    IObjectModifiedEvent,
    )
from storm.base import Storm
from storm.info import (
    get_cls_info,
    get_obj_info,
    )
from zope.component import adapter
from zope.interface.interfaces import IAttribute
from zope.security.proxy import removeSecurityProxy

from lp.services.longpoll.adapters.event import (
    generate_event_key,
    LongPollEvent,
    )
from lp.services.longpoll.interfaces import (
    ILongPollEvent,
    long_poll_event,
    )


def gen_primary_key(model_instance):
    """Generate the primary key values for the given model instance."""
    cls_info = get_obj_info(model_instance).cls_info
    for primary_key_column in cls_info.primary_key:
        yield primary_key_column.__get__(model_instance)


def get_primary_key(model_instance):
    """Return the primary key for the given model instance.

    If the primary key contains only one value it is returned, otherwise all
    the primary key values are returned in a tuple.
    """
    pkey = tuple(gen_primary_key(model_instance))
    return pkey[0] if len(pkey) == 1 else pkey


@long_poll_event(Storm)
class LongPollStormEvent(LongPollEvent):
    """A `ILongPollEvent` for events of `Storm` objects.

    This class knows how to construct a stable event key given a Storm object.
    """

    @property
    def event_key(self):
        """See `ILongPollEvent`.

        Constructs the key from the table name and primary key values of the
        Storm model object.
        """
        cls_info = get_obj_info(self.source).cls_info
        return generate_event_key(
            cls_info.table.name.lower(),
            *gen_primary_key(self.source))


@long_poll_event(type(Storm))
class LongPollStormCreationEvent(LongPollEvent):
    """A `ILongPollEvent` for events of `Storm` *classes*.

    This class knows how to construct a stable event key given a Storm class.
    """

    @property
    def event_key(self):
        """See `ILongPollEvent`.

        Constructs the key from the table name of the Storm class.
        """
        cls_info = get_cls_info(self.source)
        return generate_event_key(
            cls_info.table.name.lower())


@adapter(Storm, IObjectCreatedEvent)
def object_created(model_instance, object_event):
    """Subscription handler for `Storm` creation events."""
    model_class = removeSecurityProxy(model_instance).__class__
    event = ILongPollEvent(model_class)
    event.emit(what="created", id=get_primary_key(model_instance))


@adapter(Storm, IObjectDeletedEvent)
def object_deleted(model_instance, object_event):
    """Subscription handler for `Storm` deletion events."""
    event = ILongPollEvent(model_instance)
    event.emit(what="deleted", id=get_primary_key(model_instance))


@adapter(Storm, IObjectModifiedEvent)
def object_modified(model_instance, object_event):
    """Subscription handler for `Storm` modification events."""
    edited_fields = object_event.edited_fields
    if edited_fields is not None and len(edited_fields) != 0:
        edited_field_names = sorted(
            (field.__name__ if IAttribute.providedBy(field) else field)
            for field in edited_fields)
        event = ILongPollEvent(model_instance)
        event.emit(
            what="modified", edited_fields=edited_field_names,
            id=get_primary_key(model_instance))
