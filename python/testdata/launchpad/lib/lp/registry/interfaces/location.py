# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Location interface.

An object can have a location, which includes geographic coordinates and a
time zone.
"""

__metaclass__ = type

__all__ = [
    'IHasLocation',
    'ILocationRecord',
    'IObjectWithLocation',
    'IPersonLocation',
    'ISetLocation',
    ]

from lazr.lifecycle.snapshot import doNotSnapshot
from lazr.restful.declarations import (
    call_with,
    export_write_operation,
    exported,
    operation_for_version,
    operation_parameters,
    REQUEST_USER,
    )
from lazr.restful.interface import copy_field
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Bool,
    Choice,
    Datetime,
    Float,
    Object,
    )

from lp import _


class IHasLocation(Interface):
    """An interface supported by objects with a defined location."""

    latitude = exported(
        doNotSnapshot(
            Float(title=_("The latitude of this object."),
                  required=False, readonly=True)),
        ('devel', dict(exported=False)),
        exported=True)
    longitude = exported(
        doNotSnapshot(
            Float(title=_("The longitude of this object."),
                  required=False, readonly=True)),
        ('devel', dict(exported=False)),
        exported=True)
    time_zone = exported(doNotSnapshot(
        Choice(title=_('The time zone of this object.'),
               required=False, readonly=True,
               vocabulary='TimezoneName')))


class IObjectWithLocation(Interface):
    """An interface supported by objects with a defined location."""

    location = Attribute("An ILocation for this object.")


class ILocationRecord(IHasLocation):
    """A location record, which may be attached to a particular object.

    The location record contains additional information such as the date the
    location data was recorded, and by whom.
    """

    last_modified_by = Attribute(
        "The person who last provided this location information.")
    date_last_modified = Datetime(
        title=_("The date this information was last updated."))
    visible = Bool(
        title=_("Is this location record visible?"),
        required=False, readonly=False, default=True)


class ISetLocation(Interface):
    """An interface for setting the location and time zone of an object."""

    @call_with(user=REQUEST_USER)
    @operation_parameters(
        latitude=copy_field(IHasLocation['latitude'], required=True),
        longitude=copy_field(IHasLocation['longitude'], required=True),
        time_zone=copy_field(IHasLocation['time_zone'], required=True))
    @export_write_operation()
    @operation_for_version('beta')
    def setLocation(latitude, longitude, time_zone, user):
        """Specify the location and time zone of a person."""


class IPersonLocation(ILocationRecord):
    """A location record for a person."""

    # Can't use IPerson as the schema here because of circular dependencies.
    person = Object(title=_("Person"), schema=Interface)
