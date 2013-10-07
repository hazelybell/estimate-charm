# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = ['PackageCopyRequest', 'PackageCopyRequestSet']

import itertools

from storm.locals import (
    Bool,
    DateTime,
    Enum,
    Int,
    Reference,
    Storm,
    Unicode,
    )
from zope.interface import implements

from lp.registry.interfaces.person import validate_public_person
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.services.database.constants import UTC_NOW
from lp.services.database.interfaces import IStore
from lp.soyuz.enums import PackageCopyStatus
from lp.soyuz.interfaces.packagecopyrequest import (
    IPackageCopyRequest,
    IPackageCopyRequestSet,
    )


def _construct_enum_mapping(db_item_cls):
    """Helper function, constructs DBItem to storm enumeration mappings."""
    return dict(zip(db_item_cls.items, itertools.count(1)))


class PackageCopyRequest(Storm):
    """See `IPackageCopyRequest`."""
    implements(IPackageCopyRequest)
    __storm_table__ = 'PackageCopyRequest'
    id = Int(primary=True)

    target_archive_id = Int(name='target_archive', allow_none=False)
    target_archive = Reference(target_archive_id, 'Archive.id')
    target_distroseries_id = Int(name='target_distroseries', allow_none=True)
    target_distroseries = Reference(target_distroseries_id, 'DistroSeries.id')
    target_component_id = Int(name='target_component', allow_none=True)
    target_component = Reference(target_component_id, 'Component.id')
    target_pocket = Enum(map=_construct_enum_mapping(PackagePublishingPocket))

    copy_binaries = Bool(allow_none=False, default=False)

    source_archive_id = Int(name='source_archive', allow_none=False)
    source_archive = Reference(source_archive_id, 'Archive.id')
    source_distroseries_id = Int(name='source_distroseries', allow_none=True)
    source_distroseries = Reference(source_distroseries_id, 'DistroSeries.id')
    source_component_id = Int(name='source_component', allow_none=True)
    source_component = Reference(source_component_id, 'Component.id')
    source_pocket = Enum(map=_construct_enum_mapping(PackagePublishingPocket))

    requester_id = Int(name='requester', allow_none=False)
    requester = Reference(requester_id, 'Person.id')

    requester_id = Int(
        name='requester', allow_none=False, validator=validate_public_person)
    requester = Reference(requester_id, 'Person.id')

    status = Enum(
        allow_none=False, map=_construct_enum_mapping(PackageCopyStatus))
    reason = Unicode(allow_none=True)

    date_created = DateTime(allow_none=False, default=UTC_NOW)
    date_started = DateTime(allow_none=True)
    date_completed = DateTime(allow_none=True)

    def __str__(self):
        """See `IPackageCopyRequest`."""

        def get_name_or_nothing(property_name, nothing='-'):
            """Helper method, returns property value if set or 'nothing'."""
            property = getattr(self, property_name, None)

            # Return straight-away if property is not set.
            if property is None:
                return nothing

            # Does the property have a name?
            name = getattr(property, 'name', None)
            if name is not None:
                return str(name)

            # Does the property have a title?
            title = getattr(property, 'title', None)
            if title is not None:
                return str(title)

            # Return the string representation of the property as a last
            # resort.
            return str(property)

        result = (
            "Package copy request\n"
            "source = %s/%s/%s/%s\ntarget = %s/%s/%s/%s\n"
            "copy binaries: %s\nrequester: %s\nstatus: %s\n"
            "date created: %s\ndate started: %s\ndate completed: %s" %
            (get_name_or_nothing('source_archive'),
             get_name_or_nothing('source_distroseries'),
             get_name_or_nothing('source_component'),
             get_name_or_nothing('source_pocket'),
             get_name_or_nothing('target_archive'),
             get_name_or_nothing('target_distroseries'),
             get_name_or_nothing('target_component'),
             get_name_or_nothing('target_pocket'),
             get_name_or_nothing('copy_binaries'),
             get_name_or_nothing('requester'),
             get_name_or_nothing('status'),
             get_name_or_nothing('date_created'),
             get_name_or_nothing('date_started'),
             get_name_or_nothing('date_completed')))
        return result

    def markAsInprogress(self):
        """See `IPackageCopyRequest`."""
        self.status = PackageCopyStatus.INPROGRESS
        self.date_started = UTC_NOW

    def markAsCompleted(self):
        """See `IPackageCopyRequest`."""
        self.status = PackageCopyStatus.COMPLETE
        self.date_completed = UTC_NOW

    def markAsFailed(self):
        """See `IPackageCopyRequest`."""
        self.status = PackageCopyStatus.FAILED
        self.date_completed = UTC_NOW

    def markAsCanceling(self):
        """See `IPackageCopyRequest`."""
        self.status = PackageCopyStatus.CANCELING

    def markAsCancelled(self):
        """See `IPackageCopyRequest`."""
        self.status = PackageCopyStatus.CANCELLED
        self.date_completed = UTC_NOW


def _set_location_data(pcr, location, prefix):
    """Copies source/target package location data to copy requests."""
    # Set the archive first, must be present.
    assert location.archive is not None, (
        '%s archive must be set in package location' % prefix)
    setattr(pcr, '%s_archive' % prefix, location.archive)
    # Now set the optional data if present.
    optional_location_data = ('distroseries', 'component', 'pocket')
    for datum_name in optional_location_data:
        value = getattr(location, datum_name, None)
        if value is not None:
            setattr(pcr, '%s_%s' % (prefix, datum_name), value)


class PackageCopyRequestSet:
    """See `IPackageCopyRequestSet`."""
    implements(IPackageCopyRequestSet)

    def new(self, source, target, requester, copy_binaries=False, reason=None):
        """See `IPackageCopyRequestSet`."""
        pcr = PackageCopyRequest()
        for location_data in ((source, 'source'), (target, 'target')):
            _set_location_data(pcr, *location_data)
        pcr.requester = requester
        if copy_binaries == True:
            pcr.copy_binaries = True
        if reason is not None:
            pcr.reason = reason

        pcr.status = PackageCopyStatus.NEW
        IStore(PackageCopyRequest).add(pcr)
        return pcr

    def getByPersonAndStatus(self, requester, status=None):
        """See `IPackageCopyRequestSet`."""
        base_clauses = (PackageCopyRequest.requester == requester,)
        if status is not None:
            optional_clauses = (PackageCopyRequest.status == status,)
        else:
            optional_clauses = ()
        return IStore(PackageCopyRequest).find(
            PackageCopyRequest, *(base_clauses + optional_clauses))

    def getByTargetDistroSeries(self, distroseries):
        """See `IPackageCopyRequestSet`."""
        return IStore(PackageCopyRequest).find(
            PackageCopyRequest,
            PackageCopyRequest.target_distroseries == distroseries)

    def getBySourceDistroSeries(self, distroseries):
        """See `IPackageCopyRequestSet`."""
        return IStore(PackageCopyRequest).find(
            PackageCopyRequest,
            PackageCopyRequest.source_distroseries == distroseries)

    def getByTargetArchive(self, archive):
        """See `IPackageCopyRequestSet`."""
        return IStore(PackageCopyRequest).find(
            PackageCopyRequest,
            PackageCopyRequest.target_archive == archive)
