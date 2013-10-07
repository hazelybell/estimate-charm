# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Hardware database related table classes."""

__all__ = [
    'HWDevice',
    'HWDeviceClass',
    'HWDeviceSet',
    'HWDeviceDriverLink',
    'HWDeviceDriverLinkSet',
    'HWDeviceNameVariant',
    'HWDeviceNameVariantSet',
    'HWDriver',
    'HWDriverName',
    'HWDriverPackageName',
    'HWDriverSet',
    'HWSubmission',
    'HWSubmissionBug',
    'HWSubmissionBugSet',
    'HWSubmissionSet',
    'HWSubmissionDevice',
    'HWSubmissionDeviceSet',
    'HWSystemFingerprint',
    'HWSystemFingerprintSet',
    'HWVendorID',
    'HWVendorIDSet',
    'HWVendorName',
    'HWVendorNameSet',
    'make_submission_device_statistics_clause',
    '_userCanAccessSubmissionStormClause',
    ]

import re

from sqlobject import (
    BoolCol,
    ForeignKey,
    IntCol,
    StringCol,
    )
from storm.expr import (
    Alias,
    And,
    Count,
    Not,
    Or,
    Select,
    )
from storm.store import Store
from zope.component import getUtility
from zope.interface import implements

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.app.validators.name import valid_name
from lp.bugs.model.bug import (
    Bug,
    BugAffectsPerson,
    BugTag,
    )
from lp.bugs.model.bugsubscription import BugSubscription
from lp.hardwaredb.interfaces.hwdb import (
    HWBus,
    HWSubmissionFormat,
    HWSubmissionKeyNotUnique,
    HWSubmissionProcessingStatus,
    IHWDevice,
    IHWDeviceClass,
    IHWDeviceClassSet,
    IHWDeviceDriverLink,
    IHWDeviceDriverLinkSet,
    IHWDeviceNameVariant,
    IHWDeviceNameVariantSet,
    IHWDeviceSet,
    IHWDriver,
    IHWDriverName,
    IHWDriverPackageName,
    IHWDriverSet,
    IHWSubmission,
    IHWSubmissionBug,
    IHWSubmissionBugSet,
    IHWSubmissionDevice,
    IHWSubmissionDeviceSet,
    IHWSubmissionSet,
    IHWSystemFingerprint,
    IHWSystemFingerprintSet,
    IHWVendorID,
    IHWVendorIDSet,
    IHWVendorName,
    IHWVendorNameSet,
    IllegalQuery,
    ParameterError,
    )
from lp.registry.interfaces.distribution import IDistribution
from lp.registry.interfaces.distroseries import IDistroSeries
from lp.registry.interfaces.person import (
    IPersonSet,
    validate_public_person,
    )
from lp.registry.interfaces.product import License
from lp.registry.model.distribution import Distribution
from lp.registry.model.distroseries import DistroSeries
from lp.registry.model.person import Person
from lp.registry.model.teammembership import TeamParticipation
from lp.services.database.constants import (
    DEFAULT,
    UTC_NOW,
    )
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.enumcol import EnumCol
from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import (
    SQLBase,
    sqlvalues,
    )
from lp.services.librarian.interfaces import ILibraryFileAliasSet
from lp.soyuz.interfaces.distroarchseries import IDistroArchSeries
from lp.soyuz.model.distroarchseries import DistroArchSeries

# The vendor name assigned to new, unknown vendor IDs. See
# HWDeviceSet.create().
UNKNOWN = 'Unknown'


class HWSubmission(SQLBase):
    """See `IHWSubmission`."""

    implements(IHWSubmission)

    _table = 'HWSubmission'

    date_created = UtcDateTimeCol(notNull=True, default=UTC_NOW)
    date_submitted = UtcDateTimeCol(notNull=True, default=UTC_NOW)
    format = EnumCol(enum=HWSubmissionFormat, notNull=True)
    status = EnumCol(enum=HWSubmissionProcessingStatus, notNull=True)
    private = BoolCol(notNull=True)
    contactable = BoolCol(notNull=True)
    submission_key = StringCol(notNull=True)
    owner = ForeignKey(dbName='owner', foreignKey='Person',
                       storm_validator=validate_public_person)
    distroarchseries = ForeignKey(dbName='distroarchseries',
                                  foreignKey='DistroArchSeries')
    raw_submission = ForeignKey(dbName='raw_submission',
                                foreignKey='LibraryFileAlias',
                                notNull=False, default=DEFAULT)
    system_fingerprint = ForeignKey(dbName='system_fingerprint',
                                    foreignKey='HWSystemFingerprint',
                                    notNull=True)
    raw_emailaddress = StringCol()

    @property
    def devices(self):
        return HWSubmissionDeviceSet().getDevices(submission=self)


class HWSubmissionSet:
    """See `IHWSubmissionSet`."""

    implements(IHWSubmissionSet)

    def createSubmission(self, date_created, format, private, contactable,
                         submission_key, emailaddress, distroarchseries,
                         raw_submission, filename, filesize,
                         system_fingerprint):
        """See `IHWSubmissionSet`."""
        assert valid_name(submission_key), "Invalid key %s" % submission_key

        submission_exists = HWSubmission.selectOneBy(
            submission_key=submission_key)
        if submission_exists is not None:
            raise HWSubmissionKeyNotUnique(
                'A submission with this ID already exists')

        personset = getUtility(IPersonSet)
        if emailaddress is not None:
            owner = personset.getByEmail(emailaddress)
        else:
            owner = None

        fingerprint = HWSystemFingerprint.selectOneBy(
            fingerprint=system_fingerprint)
        if fingerprint is None:
            fingerprint = HWSystemFingerprint(fingerprint=system_fingerprint)

        libraryfileset = getUtility(ILibraryFileAliasSet)
        libraryfile = libraryfileset.create(
            name=filename,
            size=filesize,
            file=raw_submission,
            # XXX: kiko 2007-09-20: The hwdb client sends us bzipped XML, but
            # arguably other clients could send us other formats. The right
            # way to do this is either to enforce the format in the browser
            # code, allow the client to specify the format, or use a
            # magic module to sniff what it is we got.
            contentType='application/x-bzip2',
            expires=None)

        return HWSubmission(
            date_created=date_created,
            format=format,
            status=HWSubmissionProcessingStatus.SUBMITTED,
            private=private,
            contactable=contactable,
            submission_key=submission_key,
            owner=owner,
            distroarchseries=distroarchseries,
            raw_submission=libraryfile,
            system_fingerprint=fingerprint,
            raw_emailaddress=emailaddress)

    def _userHasAccessClause(self, user):
        """Limit results of HWSubmission queries to rows the user can access.
        """
        admins = getUtility(ILaunchpadCelebrities).admin
        if user is None:
            return " AND NOT HWSubmission.private"
        elif not user.inTeam(admins):
            return """
                AND (NOT HWSubmission.private
                     OR EXISTS
                         (SELECT 1
                             FROM HWSubmission as HWAccess, TeamParticipation
                             WHERE HWAccess.id=HWSubmission.id
                                 AND HWAccess.private
                                 AND HWAccess.owner=TeamParticipation.team
                                 AND TeamParticipation.person=%i
                                 ))
                """ % user.id
        else:
            return ""

    def getBySubmissionKey(self, submission_key, user=None):
        """See `IHWSubmissionSet`."""
        return IStore(HWSubmission).find(
            HWSubmission,
            And(HWSubmission.submission_key == submission_key,
                _userCanAccessSubmissionStormClause(user))).one()

    def getByFingerprintName(self, name, user=None):
        """See `IHWSubmissionSet`."""
        fp = HWSystemFingerprintSet().getByName(name)
        query = """
            system_fingerprint=%s
            AND HWSystemFingerprint.id = HWSubmission.system_fingerprint
            """ % sqlvalues(fp)
        query = query + self._userHasAccessClause(user)

        return HWSubmission.select(
            query,
            clauseTables=['HWSystemFingerprint'],
            prejoinClauseTables=['HWSystemFingerprint'],
            orderBy=['-date_submitted',
                     'HWSystemFingerprint.fingerprint',
                     'submission_key'])

    def getByOwner(self, owner, user=None):
        """See `IHWSubmissionSet`."""
        query = """
            owner=%i
            AND HWSystemFingerprint.id = HWSubmission.system_fingerprint
            """ % owner.id
        query = query + self._userHasAccessClause(user)

        return HWSubmission.select(
            query,
            clauseTables=['HWSystemFingerprint'],
            prejoinClauseTables=['HWSystemFingerprint'],
            orderBy=['-date_submitted',
                     'HWSystemFingerprint.fingerprint',
                     'submission_key'])

    def submissionIdExists(self, submission_key):
        """See `IHWSubmissionSet`."""
        rows = HWSubmission.selectBy(submission_key=submission_key)
        return not rows.is_empty()

    def getByStatus(self, status, user=None):
        """See `IHWSubmissionSet`."""
        # Provide a stable order. Sorting by id, to get the oldest
        # submissions first. When date_submitted has an index, we could
        # sort by that first.
        return IStore(HWSubmission).find(
            HWSubmission, HWSubmission.status == status,
            _userCanAccessSubmissionStormClause(user)).order_by(
                HWSubmission.id)

    def search(self, user=None, device=None, driver=None, distribution=None,
               distroseries=None, architecture=None, owner=None,
               created_before=None, created_after=None,
               submitted_before=None, submitted_after=None):
        """See `IHWSubmissionSet`."""
        args = []
        if device is not None:
            args.append(HWDeviceDriverLink.device == HWDevice.id)
            args.append(HWDevice.id == device.id)
        if driver is not None:
            args.append(HWDeviceDriverLink.driver == HWDriver.id)
            args.append(HWDriver.id == driver.id)
        # HWDevice and HWDriver are linked to submissions via
        # HWDeviceDriverLink and HWSubmissionDevice.
        if args:
            args.append(HWSubmissionDevice.device_driver_link ==
                        HWDeviceDriverLink.id)
            args.append(HWSubmissionDevice.submission == HWSubmission.id)

        if (distribution is not None or distroseries is not None
            or architecture is not None):
            # We need to select a specific distribution, distroseries,
            # and/or processor architecture.
            if distribution and distroseries:
                raise IllegalQuery(
                    'Only one of `distribution` or '
                    '`distroseries` can be present.')
            args.append(HWSubmission.distroarchseries == DistroArchSeries.id)
            if architecture is not None:
                args.append(DistroArchSeries.architecturetag == architecture)
            if distribution is not None:
                args.append(DistroArchSeries.distroseries == DistroSeries.id)
                args.append(DistroSeries.distribution == Distribution.id)
                args.append(Distribution.id == distribution.id)
            if distroseries is not None:
                args.append(DistroArchSeries.distroseries == distroseries.id)
        if owner is not None:
            args.append(HWSubmission.owner == owner.id)
        if created_before is not None:
            args.append(HWSubmission.date_created <= created_before)
        if created_after is not None:
            args.append(HWSubmission.date_created > created_after)
        if submitted_before is not None:
            args.append(HWSubmission.date_submitted <= submitted_before)
        if submitted_after is not None:
            args.append(HWSubmission.date_submitted > submitted_after)

        # Many devices are associated with more than one driver, even
        # for one submission, hence we may have more than one
        # HWSubmissionDevice record and more than one HWDeviceDriverLink
        # for one device and one submission matching the WHERE clause
        # defined above. This leads to duplicate results without a
        # DISTINCT clause.
        return IStore(HWSubmission).find(
            HWSubmission,
            _userCanAccessSubmissionStormClause(user),
            *args).config(distinct=True).order_by(HWSubmission.id)

    def _submissionsSubmitterSelects(
        self, target_column, bus, vendor_id, product_id, driver_name,
        package_name, distro_target):
        """Return Select objects for statistical queries.

        :return: A tuple
            (select_device_related_records, select_all_records)
            where select_device_related_records is a Select instance
            returning target_column matching all other method
            parameters, and where select_all_records is a Select
            instance returning target_column and matching distro_target,
        :param target_column: The records returned by the Select instance.
        :param bus: The `HWBus` of the device.
        :param vendor_id: The vendor ID of the device.
        :param product_id: The product ID of the device.
        :param driver_name: The name of the driver used for the device
            (optional).
        :param package_name: The name of the package the driver is a part of.
            (optional).
        :param distro_target: Limit the result to submissions made for the
            given distribution, distroseries or distroarchseries.
            (optional).
        """
        tables, clauses = make_distro_target_clause(distro_target)
        if HWSubmission not in tables:
            tables.append(HWSubmission)
        clauses.append(
            HWSubmission.status == HWSubmissionProcessingStatus.PROCESSED)

        all_submissions = Select(
            columns=[target_column], tables=tables, where=And(*clauses),
            distinct=True)

        device_tables, device_clauses = (
            make_submission_device_statistics_clause(
                bus, vendor_id, product_id, driver_name, package_name, False))
        submission_ids = Select(
            columns=[HWSubmissionDevice.submissionID],
            tables=device_tables, where=And(*device_clauses))

        clauses.append(HWSubmission.id.is_in(submission_ids))
        submissions_with_device = Select(
            columns=[target_column], tables=tables, where=And(*clauses),
            distinct=True)

        return (submissions_with_device, all_submissions)

    def numSubmissionsWithDevice(
        self, bus=None, vendor_id=None, product_id=None, driver_name=None,
        package_name=None, distro_target=None):
        """See `IHWSubmissionSet`."""
        store = IStore(HWSubmission)
        submissions_with_device_select, all_submissions_select = (
            self._submissionsSubmitterSelects(
                Count(), bus, vendor_id, product_id, driver_name,
                package_name, distro_target))
        submissions_with_device = store.execute(
            submissions_with_device_select)
        all_submissions = store.execute(all_submissions_select)
        return (submissions_with_device.get_one()[0],
                all_submissions.get_one()[0])

    def numOwnersOfDevice(
        self, bus=None, vendor_id=None, product_id=None, driver_name=None,
        package_name=None, distro_target=None):
        """See `IHWSubmissionSet`."""
        store = IStore(HWSubmission)
        submitters_with_device_select, all_submitters_select = (
            self._submissionsSubmitterSelects(
                HWSubmission.raw_emailaddress, bus, vendor_id, product_id,
                driver_name, package_name, distro_target))

        submitters_with_device = store.execute(
            Select(
                columns=[Count()],
                tables=[Alias(submitters_with_device_select, 'addresses')]))
        all_submitters = store.execute(
            Select(
                columns=[Count()],
                tables=[Alias(all_submitters_select, 'addresses')]))

        return (submitters_with_device.get_one()[0],
                all_submitters.get_one()[0])

    def deviceDriverOwnersAffectedByBugs(
        self, bus=None, vendor_id=None, product_id=None, driver_name=None,
        package_name=None, bug_ids=None, bug_tags=None, affected_by_bug=False,
        subscribed_to_bug=False, user=None):
        """See `IHWSubmissionSet`."""
        store = IStore(HWSubmission)
        tables, clauses = make_submission_device_statistics_clause(
                bus, vendor_id, product_id, driver_name, package_name, False)
        tables.append(HWSubmission)
        clauses.append(HWSubmissionDevice.submission == HWSubmission.id)
        clauses.append(_userCanAccessSubmissionStormClause(user))

        if ((bug_ids is None or len(bug_ids) == 0) and
            (bug_tags is None or len(bug_tags) == 0)):
            raise ParameterError('bug_ids or bug_tags must be supplied.')

        tables.append(Bug)
        if bug_ids is not None and bug_ids is not []:
            clauses.append(Bug.id.is_in(bug_ids))

        if bug_tags is not None and bug_tags is not []:
            clauses.extend([
                Bug.id == BugTag.bugID, BugTag.tag.is_in(bug_tags)])
            tables.append(BugTag)

        # If we OR-combine the search for bug owners, subscribers
        # and affected people on SQL level, the query runs very slow.
        # So let's run the queries separately and join the results
        # on Python level.

        # This would be quicker still if we did it as a single query
        # using UNION.

        owner_query = Select(
            columns=[HWSubmission.ownerID], tables=tables,
            where=And(*(clauses + [Bug.ownerID == HWSubmission.ownerID])))
        user_ids = set(store.execute(owner_query))

        if subscribed_to_bug:
            subscriber_clauses = [
                BugSubscription.person_id == HWSubmission.ownerID,
                BugSubscription.bug == Bug.id,
                ]
            subscriber_query = Select(
                columns=[HWSubmission.ownerID],
                tables=tables + [BugSubscription],
                where=And(*(clauses + subscriber_clauses)))
            user_ids.update(store.execute(subscriber_query))

        if affected_by_bug:
            affected_clauses = [
                BugAffectsPerson.personID == HWSubmission.ownerID,
                BugAffectsPerson.bug == Bug.id,
                BugAffectsPerson.affected,
                ]
            affected_query = Select(
                columns=[HWSubmission.ownerID],
                tables=tables + [BugAffectsPerson],
                where=And(*(clauses + affected_clauses)))
            user_ids.update(store.execute(affected_query))

        # A "WHERE x IN (y, z...)" query needs at least one element
        # on the right side of IN.
        if len(user_ids) == 0:
            result = store.find(Person, False)
        else:
            user_ids = [row[0] for row in user_ids]
            result = store.find(Person, Person.id.is_in(user_ids))
        result.order_by(Person.displayname)
        return result

    def hwInfoByBugRelatedUsers(
        self, bug_ids=None, bug_tags=None, affected_by_bug=False,
        subscribed_to_bug=False, user=None):
        """See `IHWSubmissionSet`."""
        if ((bug_ids is None or len(bug_ids) == 0) and
            (bug_tags is None or len(bug_tags) == 0)):
            raise ParameterError('bug_ids or bug_tags must be supplied.')

        tables = [
            Person, HWSubmission, HWSubmissionDevice, HWDeviceDriverLink,
            HWDevice, HWVendorID, Bug, BugTag,
            ]

        clauses = [
            Person.id == HWSubmission.ownerID,
            HWSubmissionDevice.submission == HWSubmission.id,
            HWSubmissionDevice.device_driver_link == HWDeviceDriverLink.id,
            HWDeviceDriverLink.device == HWDevice.id,
            HWDevice.bus_vendor == HWVendorID.id]

        if bug_ids is not None and bug_ids is not []:
            clauses.append(Bug.id.is_in(bug_ids))

        if bug_tags is not None and bug_tags is not []:
            clauses.extend(
                [Bug.id == BugTag.bugID, BugTag.tag.is_in(bug_tags)])

        clauses.append(_userCanAccessSubmissionStormClause(user))

        person_clauses = [Bug.ownerID == HWSubmission.ownerID]
        if subscribed_to_bug:
            person_clauses.append(
                And(BugSubscription.person_id == HWSubmission.ownerID,
                    BugSubscription.bug == Bug.id))
            tables.append(BugSubscription)
        if affected_by_bug:
            person_clauses.append(
                And(BugAffectsPerson.personID == HWSubmission.ownerID,
                    BugAffectsPerson.bug == Bug.id,
                    BugAffectsPerson.affected))
            tables.append(BugAffectsPerson)
        clauses.append(Or(person_clauses))

        query = Select(
            columns=[
                Person.name, HWVendorID.bus,
                HWVendorID.vendor_id_for_bus, HWDevice.bus_product_id],
            tables=tables, where=And(*clauses), distinct=True,
            order_by=[HWVendorID.bus, HWVendorID.vendor_id_for_bus,
                      HWDevice.bus_product_id, Person.name])

        return [
            (person_name, HWBus.items[bus_id], vendor_id, product_id)
             for person_name, bus_id, vendor_id, product_id
             in IStore(HWSubmission).execute(query)]


class HWSystemFingerprint(SQLBase):
    """Identifiers of a computer system."""

    implements(IHWSystemFingerprint)

    _table = 'HWSystemFingerprint'

    fingerprint = StringCol(notNull=True)


class HWSystemFingerprintSet:
    """A set of identifiers of a computer system."""

    implements(IHWSystemFingerprintSet)

    def getByName(self, fingerprint):
        """See `IHWSystemFingerprintSet`."""
        return HWSystemFingerprint.selectOneBy(fingerprint=fingerprint)

    def createFingerprint(self, fingerprint):
        """See `IHWSystemFingerprintSet`."""
        return HWSystemFingerprint(fingerprint=fingerprint)


class HWVendorName(SQLBase):
    """See `IHWVendorName`."""

    implements(IHWVendorName)

    _table = 'HWVendorName'

    name = StringCol(notNull=True)


class HWVendorNameSet:
    """See `IHWVendorNameSet`."""

    implements(IHWVendorNameSet)

    def create(self, name):
        """See `IHWVendorNameSet`."""
        return HWVendorName(name=name)

    def getByName(self, name):
        """See `IHWVendorNameSet`."""
        return HWVendorName.selectOne(
            'ulower(name)=ulower(%s)' % sqlvalues(name))


four_hex_digits = re.compile('^0x[0-9a-f]{4}$')
six_hex_digits = re.compile('^0x[0-9a-f]{6}$')
# The regular expressions for the SCSI vendor and product IDs are not as
# "picky" as the specification requires. Considering the fact that for
# example Microtek sold at least one scanner model that returns '        '
# as the vendor ID, it seems reasonable to allows also somewhat broken
# looking IDs.
scsi_vendor = re.compile('^.{8}$')
scsi_product = re.compile('^.{16}$')

validVendorID = {
    HWBus.PCI: four_hex_digits,
    HWBus.PCCARD: four_hex_digits,
    HWBus.USB: four_hex_digits,
    HWBus.IEEE1394: six_hex_digits,
    HWBus.SCSI: scsi_vendor,
    }

validProductID = {
    HWBus.PCI: four_hex_digits,
    HWBus.PCCARD: four_hex_digits,
    HWBus.USB: four_hex_digits,
    HWBus.SCSI: scsi_product,
    }


def isValidVendorID(bus, id):
    """Check that the string id is a valid vendor ID for this bus.

    :return: True, if id is valid, otherwise False
    :param bus: A `HWBus` indicating the bus type of "id"
    :param id: A string with the ID

    Some busses have constraints for IDs, while some can use arbitrary
    values, for example the "fake" busses HWBus.SYSTEM and HWBus.SERIAL.

    We use a hexadecimal representation of integers like "0x123abc",
    i.e., the numbers have the prefix "0x"; for the digits > 9 we
    use the lower case characters a to f.

    USB and PCI IDs have always four digits; IEEE1394 IDs have always
    six digits.

    SCSI vendor IDs consist of eight bytes of ASCII data (0x20..0x7e);
    if a vendor name has less than eight characters, it is padded on the
    right with spaces (See http://t10.org/ftp/t10/drafts/spc4/spc4r14.pdf,
    page 45).
    """
    if bus not in validVendorID:
        return True
    return validVendorID[bus].search(id) is not None


def isValidProductID(bus, id):
    """Check that the string id is a valid product for this bus.

    :return: True, if id is valid, otherwise False
    :param bus: A `HWBus` indicating the bus type of "id"
    :param id: A string with the ID

    Some busses have constraints for IDs, while some can use arbitrary
    values, for example the "fake" busses HWBus.SYSTEM and HWBus.SERIAL.

    We use a hexadecimal representation of integers like "0x123abc",
    i.e., the numbers have the prefix "0x"; for the digits > 9 we
    use the lower case characters a to f.

    USB and PCI IDs have always four digits.

    Since IEEE1394 does not specify product IDs, there is no formal
    check of them.

    SCSI product IDs consist of 16 bytes of ASCII data (0x20..0x7e);
    if a product name has less than 16 characters, it is padded on the
    right with spaces.
    """
    if bus not in validProductID:
        return True
    return validProductID[bus].search(id) is not None


class HWVendorID(SQLBase):
    """See `IHWVendorID`."""

    implements(IHWVendorID)

    _table = 'HWVendorID'

    bus = EnumCol(enum=HWBus, notNull=True)
    vendor_id_for_bus = StringCol(notNull=True)
    vendor_name = ForeignKey(dbName='vendor_name', foreignKey='HWVendorName',
                             notNull=True)

    def _create(self, id, **kw):
        bus = kw.get('bus')
        if bus is None:
            raise TypeError('HWVendorID() did not get expected keyword '
                            'argument bus')
        vendor_id_for_bus = kw.get('vendor_id_for_bus')
        if vendor_id_for_bus is None:
            raise TypeError('HWVendorID() did not get expected keyword '
                            'argument vendor_id_for_bus')
        if not isValidVendorID(bus, vendor_id_for_bus):
            raise ParameterError(
                '%s is not a valid vendor ID for %s'
                % (repr(vendor_id_for_bus), bus.title))
        SQLBase._create(self, id, **kw)


class HWVendorIDSet:
    """See `IHWVendorIDSet`."""

    implements(IHWVendorIDSet)

    def create(self, bus, vendor_id, vendor_name):
        """See `IHWVendorIDSet`."""
        vendor_name = HWVendorName.selectOneBy(name=vendor_name.name)
        return HWVendorID(bus=bus, vendor_id_for_bus=vendor_id,
                          vendor_name=vendor_name)

    def getByBusAndVendorID(self, bus, vendor_id):
        """See `IHWVendorIDSet`."""
        if not isValidVendorID(bus, vendor_id):
            raise ParameterError(
                '%s is not a valid vendor ID for %s'
                % (repr(vendor_id), bus.title))
        return HWVendorID.selectOneBy(bus=bus, vendor_id_for_bus=vendor_id)

    def get(self, id):
        """See `IHWVendorIDSet`."""
        return IStore(HWVendorID).find(HWVendorID, HWVendorID.id == id).one()

    def idsForBus(self, bus):
        """See `IHWVendorIDSet`."""
        return IStore(HWVendorID).find(HWVendorID, bus=bus).order_by(
            HWVendorID.vendor_id_for_bus)


class HWDevice(SQLBase):
    """See `IHWDevice.`"""

    implements(IHWDevice)
    _table = 'HWDevice'

    # XXX Abel Deuring 2008-05-02: The columns bus_vendor and
    # bus_product_id are supposed to be immutable. However, if they
    # are defined as "immutable=True", the creation of a new HWDevice
    # instance leads to an AttributeError in sqlobject/main.py, line 814.
    bus_vendor = ForeignKey(dbName='bus_vendor_id', foreignKey='HWVendorID',
                            notNull=True, immutable=False)
    bus_product_id = StringCol(notNull=True, dbName='bus_product_id',
                               immutable=False)
    variant = StringCol(notNull=False)
    name = StringCol(notNull=True)
    submissions = IntCol(notNull=True)

    @property
    def bus(self):
        return self.bus_vendor.bus

    @property
    def vendor_id(self):
        return self.bus_vendor.vendor_id_for_bus

    @property
    def vendor_name(self):
        return self.bus_vendor.vendor_name.name

    def _create(self, id, **kw):
        bus_vendor = kw.get('bus_vendor')
        if bus_vendor is None:
            raise TypeError('HWDevice() did not get expected keyword '
                            'argument bus_vendor')
        bus_product_id = kw.get('bus_product_id')
        if bus_product_id is None:
            raise TypeError('HWDevice() did not get expected keyword '
                            'argument bus_product_id')
        if not isValidProductID(bus_vendor.bus, bus_product_id):
            raise ParameterError(
                '%s is not a valid product ID for %s'
                % (repr(bus_product_id), bus_vendor.bus.title))
        SQLBase._create(self, id, **kw)

    def getSubmissions(self, driver=None, distribution=None,
                       distroseries=None, architecture=None, owner=None):
        """See `IHWDevice.`"""
        return HWSubmissionSet().search(
            device=self, driver=driver, distribution=distribution,
            distroseries=distroseries, architecture=architecture, owner=owner)

    @property
    def drivers(self):
        """See `IHWDevice.`"""
        return IStore(HWDriver).find(
            HWDriver, HWDeviceDriverLink.driver == HWDriver.id,
            HWDeviceDriverLink.device == self).order_by(
                HWDriver.package_name, HWDriver.name)

    @property
    def classes(self):
        """See `IHWDevice.`"""
        return IStore(HWDeviceClass).find(
            HWDeviceClass,
            HWDeviceClass.device == self.id).order_by(
                HWDeviceClass.main_class, HWDeviceClass.sub_class)

    def getOrCreateDeviceClass(self, main_class, sub_class=None):
        """See `IHWDevice.`"""
        result_set = IStore(HWDeviceClass).find(
            HWDeviceClass,
            HWDeviceClass.device == self.id,
            HWDeviceClass.main_class == main_class,
            HWDeviceClass.sub_class == sub_class)
        existing_record = result_set.one()
        if existing_record is not None:
            return existing_record
        return HWDeviceClass(
            device=self, main_class=main_class, sub_class=sub_class)

    def removeDeviceClass(self, main_class, sub_class=None):
        """See `IHWDevice.`"""
        store = IStore(HWDeviceClass)
        result_set = store.find(
            HWDeviceClass,
            HWDeviceClass.device == self.id,
            HWDeviceClass.main_class == main_class,
            HWDeviceClass.sub_class == sub_class)
        existing_record = result_set.one()
        if existing_record is not None:
            store.remove(existing_record)


class HWDeviceSet:
    """See `IHWDeviceSet`."""

    implements(IHWDeviceSet)

    def create(self, bus, vendor_id, product_id, product_name, variant=None):
        """See `IHWDeviceSet`."""
        vendor_id_record = HWVendorID.selectOneBy(bus=bus,
                                                  vendor_id_for_bus=vendor_id)
        if vendor_id_record is None:
            # The vendor ID may be unknown for two reasons:
            #   - we do not have anything like a subscription to newly
            #     assigned PCI or USB vendor IDs, so we may get submissions
            #     with IDs we don't know about yet.
            #   - we may get submissions with invalid IDs.
            # In both cases, we create a new HWVendorID entry with the
            # vendor name 'Unknown'.
            unknown_vendor = HWVendorName.selectOneBy(name=UNKNOWN)
            if unknown_vendor is None:
                unknown_vendor = HWVendorName(name=UNKNOWN)
            vendor_id_record = HWVendorID(bus=bus,
                                          vendor_id_for_bus=vendor_id,
                                          vendor_name=unknown_vendor)
        return HWDevice(bus_vendor=vendor_id_record,
                        bus_product_id=product_id, name=product_name,
                        variant=variant, submissions=0)

    def getByDeviceID(self, bus, vendor_id, product_id, variant=None):
        """See `IHWDeviceSet`."""
        if not isValidProductID(bus, product_id):
            raise ParameterError(
                '%s is not a valid product ID for %s'
                % (repr(product_id), bus.title))
        bus_vendor = HWVendorIDSet().getByBusAndVendorID(bus, vendor_id)
        return HWDevice.selectOneBy(bus_vendor=bus_vendor,
                                    bus_product_id=product_id,
                                    variant=variant)

    def getOrCreate(self, bus, vendor_id, product_id, product_name,
                    variant=None):
        """See `IHWDeviceSet`."""
        device = self.getByDeviceID(bus, vendor_id, product_id, variant)
        if device is None:
            return self.create(bus, vendor_id, product_id, product_name,
                               variant)
        return device

    def getByID(self, id):
        """See `IHWDeviceSet`."""
        return IStore(HWDevice).find(HWDevice, HWDevice.id == id).one()

    def search(self, bus, vendor_id, product_id=None):
        """See `IHWDeviceSet`."""
        bus_vendor = HWVendorIDSet().getByBusAndVendorID(bus, vendor_id)
        args = []
        if product_id is not None:
            if not isValidProductID(bus, product_id):
                raise ParameterError(
                    '%s is not a valid product ID for %s'
                    % (repr(product_id), bus.title))
            args.append(HWDevice.bus_product_id == product_id)
        return IStore(HWDevice).find(
            HWDevice, HWDevice.bus_vendor == bus_vendor, *args).order_by(
                HWDevice.id)


class HWDeviceNameVariant(SQLBase):
    """See `IHWDeviceNameVariant`."""

    implements(IHWDeviceNameVariant)
    _table = 'HWDeviceNameVariant'

    vendor_name = ForeignKey(dbName='vendor_name', foreignKey='HWVendorName',
                             notNull=True)
    product_name = StringCol(notNull=True)
    device = ForeignKey(dbName='device', foreignKey='HWDevice', notNull=True)
    submissions = IntCol(notNull=True)


class HWDeviceNameVariantSet:
    """See `IHWDeviceNameVariantSet`."""

    implements(IHWDeviceNameVariantSet)

    def create(self, device, vendor_name, product_name):
        """See `IHWDeviceNameVariantSet`."""
        vendor_name_record = HWVendorName.selectOneBy(name=vendor_name)
        if vendor_name_record is None:
            vendor_name_record = HWVendorName(name=vendor_name)
        return HWDeviceNameVariant(device=device,
                                   vendor_name=vendor_name_record,
                                   product_name=product_name,
                                   submissions=0)


class HWDriver(SQLBase):
    """See `IHWDriver`."""

    implements(IHWDriver)
    _table = 'HWDriver'

    # XXX: Abel Deuring 2008-12-10 bug=306265: package_name should
    # be declared notNull=True. This fixes the ambiguity that
    # "package_name is None" as well as "package_name == ''" can
    # indicate "we don't know to which package this driver belongs",
    # moreover, it gives a more clear meaning to the parameter value
    #package_name='' in webservice API calls.
    package_name = StringCol(notNull=False)
    name = StringCol(notNull=True)
    license = EnumCol(enum=License, notNull=False)

    def getSubmissions(self, distribution=None, distroseries=None,
                       architecture=None, owner=None):
        """See `IHWDriver.`"""
        return HWSubmissionSet().search(
            driver=self, distribution=distribution,
            distroseries=distroseries, architecture=architecture, owner=owner)


class HWDriverSet:
    """See `IHWDriver`."""

    implements(IHWDriverSet)

    def create(self, package_name, name, license):
        """See `IHWDriverSet`."""
        if package_name is None:
            package_name = ''
        return HWDriver(package_name=package_name, name=name, license=license)

    def getByPackageAndName(self, package_name, name):
        """See `IHWDriverSet`."""
        store = IStore(HWDriver)
        if package_name in (None, ''):
            return store.find(
                HWDriver,
                Or(HWDriver.package_name == None,
                   HWDriver.package_name == ''),
                HWDriver.name == name).one()
        else:
            return store.find(
                HWDriver, HWDriver.package_name == package_name,
                HWDriver.name == name).one()

    def getOrCreate(self, package_name, name, license=None):
        """See `IHWDriverSet`."""
        # Bugs 306265, 369769: If the method parameter package_name is
        # None, and if no matching record exists, we create new records
        # with package_name = '', but we must also search for old records
        # where package_name == None in order to avoid the creation of
        # two records where on rcord has package_name=None and the other
        # package_name=''.
        driver = self.getByPackageAndName(package_name, name)

        if driver is None:
            return self.create(package_name, name, license)
        return driver

    def search(self, package_name=None, name=None):
        """See `IHWDriverSet`."""
        args = []
        if package_name is not None:
            if len(package_name) == 0:
                args.append(Or(HWDriver.package_name == None,
                               HWDriver.package_name == ''))
            else:
                args.append(HWDriver.package_name == package_name)
        if name != None:
            args.append(HWDriver.name == name)
        return IStore(HWDriver).find(HWDriver, *args).order_by(HWDriver.id)

    def getByID(self, id):
        """See `IHWDriverSet`."""
        return IStore(HWDriver).find(HWDriver, HWDriver.id == id).one()

    def all_driver_names(self):
        """See `IHWDriverSet`."""
        return IStore(HWDriverName).find(
            HWDriverName).order_by(HWDriverName.name)

    def all_package_names(self):
        """See `IHWDriverSet`."""
        # XXX Abel Deuring 2009-06-19 The clause package_name != None
        # can be removed once bug #306265 is fixed.
        result = IStore(HWDriverPackageName).find(
            HWDriverPackageName, HWDriverPackageName.package_name != None)
        result.order_by(HWDriverPackageName.package_name)
        return result


class HWDriverName(SQLBase):
    """See `IHWDriverName`."""

    implements(IHWDriverName)
    _table = 'HWDriverNames'

    name = StringCol(notNull=True)


class HWDriverPackageName(SQLBase):
    """See `IHWDriverPackageName`."""

    implements(IHWDriverPackageName)
    _table = 'HWDriverPackageNames'

    package_name = StringCol(notNull=True)


class HWDeviceDriverLink(SQLBase):
    """See `IHWDeviceDriverLink`."""

    implements(IHWDeviceDriverLink)
    _table = 'HWDeviceDriverLink'

    device = ForeignKey(dbName='device', foreignKey='HWDevice', notNull=True)
    driver = ForeignKey(dbName='driver', foreignKey='HWDriver', notNull=False)


class HWDeviceDriverLinkSet:
    """See `IHWDeviceDriverLinkSet`."""

    implements(IHWDeviceDriverLinkSet)

    def create(self, device, driver):
        """See `IHWDeviceDriverLinkSet`."""
        return HWDeviceDriverLink(device=device, driver=driver)

    def getByDeviceAndDriver(self, device, driver):
        """See `IHWDeviceDriverLink`."""
        return HWDeviceDriverLink.selectOneBy(device=device, driver=driver)

    def getOrCreate(self, device, driver):
        """See `IHWDeviceDriverLink`."""
        device_driver_link = self.getByDeviceAndDriver(device, driver)
        if device_driver_link is None:
            return self.create(device, driver)
        return device_driver_link


class HWDeviceClass(SQLBase):
    """See `IHWDeviceClass`."""
    implements(IHWDeviceClass)

    device = ForeignKey(dbName='device', foreignKey='HWDevice', notNull=True)
    main_class = IntCol(notNull=True)
    sub_class = IntCol(notNull=False)

    def delete(self):
        """See `IHWDeviceClass`."""
        store = Store.of(self)
        store.remove(self)


class HWDeviceClassSet:
    """See `IHWDeviceClassSet`."""
    implements(IHWDeviceClassSet)

    def get(self, id):
        """See `IHWDeviceClassSet`."""
        return IStore(HWDeviceClass).find(
            HWDeviceClass, HWDeviceClass.id == id).one()


class HWSubmissionDevice(SQLBase):
    """See `IHWSubmissionDevice`."""

    implements(IHWSubmissionDevice)
    _table = 'HWSubmissionDevice'

    device_driver_link = ForeignKey(dbName='device_driver_link',
                                    foreignKey='HWDeviceDriverLink',
                                    notNull=True)
    submission = ForeignKey(dbName='submission', foreignKey='HWSubmission',
                            notNull=True)
    parent = ForeignKey(dbName='parent', foreignKey='HWSubmissionDevice',
                        notNull=False)

    hal_device_id = IntCol(notNull=True)

    @property
    def device(self):
        """See `IHWSubmissionDevice`."""
        return self.device_driver_link.device

    @property
    def driver(self):
        """See `IHWSubmissionDevice`."""
        return self.device_driver_link.driver


class HWSubmissionDeviceSet:
    """See `IHWSubmissionDeviceSet`."""

    implements(IHWSubmissionDeviceSet)

    def create(self, device_driver_link, submission, parent, hal_device_id):
        """See `IHWSubmissionDeviceSet`."""
        return HWSubmissionDevice(device_driver_link=device_driver_link,
                                  submission=submission, parent=parent,
                                  hal_device_id=hal_device_id)

    def getDevices(self, submission):
        """See `IHWSubmissionDeviceSet`."""
        return HWSubmissionDevice.selectBy(
            submission=submission,
            orderBy=['parent', 'device_driver_link', 'hal_device_id'])

    def get(self, id):
        """See `IHWSubmissionDeviceSet`."""
        return IStore(HWSubmissionDevice).find(
            HWSubmissionDevice, HWSubmissionDevice.id == id).one()

    def numDevicesInSubmissions(
        self, bus=None, vendor_id=None, product_id=None, driver_name=None,
        package_name=None, distro_target=None):
        """See `IHWSubmissionDeviceSet`."""
        tables, where_clauses = make_submission_device_statistics_clause(
            bus, vendor_id, product_id, driver_name, package_name, False)

        distro_tables, distro_clauses = make_distro_target_clause(
            distro_target)
        if distro_clauses:
            tables.extend(distro_tables)
            where_clauses.extend(distro_clauses)
            where_clauses.append(
                HWSubmissionDevice.submission == HWSubmission.id)

        result = IStore(HWSubmissionDevice).execute(
            Select(
                columns=[Count()], tables=tables, where=And(*where_clauses)))
        return result.get_one()[0]


class HWSubmissionBug(SQLBase):
    """See `IHWSubmissionBug`."""

    implements(IHWSubmissionBug)
    _table = 'HWSubmissionBug'

    submission = ForeignKey(dbName='submission', foreignKey='HWSubmission',
                              notNull=True)
    bug = ForeignKey(dbName='bug', foreignKey='Bug', notNull=True)


class HWSubmissionBugSet:
    """See `IHWSubmissionBugSet`."""

    implements(IHWSubmissionBugSet)

    def create(self, submission, bug):
        """See `IHWSubmissionBugSet`."""
        store = Store.of(bug)
        existing_link = store.find(
            HWSubmissionBug,
            And(HWSubmissionBug.submission == submission,
                HWSubmissionBug.bug == bug)).one()
        if existing_link is not None:
            return existing_link
        return HWSubmissionBug(submission=submission, bug=bug)

    def remove(self, submission, bug):
        """See `IHWSubmissionBugSet`."""
        store = Store.of(bug)
        link = store.find(
            HWSubmissionBug,
            And(HWSubmissionBug.bug == bug,
                HWSubmissionBug.submission == submission.id)).one()
        if link is not None:
            store.remove(link)

    def submissionsForBug(self, bug, user=None):
        """See `IHWSubmissionBugSet`."""
        store = Store.of(bug)
        result = store.find(
            HWSubmission, And(HWSubmissionBug.bug == bug,
                              HWSubmissionBug.submission == HWSubmission.id,
                              _userCanAccessSubmissionStormClause(user)))
        result.order_by(HWSubmission.submission_key)
        return result


def make_submission_device_statistics_clause(
    bus, vendor_id, product_id, driver_name, package_name,
    device_ids_required):
    """Create a where expression and a table list for selecting devices.
    """
    tables = [HWSubmissionDevice, HWDeviceDriverLink]
    where_clauses = [
        HWSubmissionDevice.device_driver_link == HWDeviceDriverLink.id,
        ]

    if device_ids_required:
        if bus is None or vendor_id is None or product_id is None:
            raise ParameterError("Device IDs are required.")
    else:
        device_specified = [
            param
            for param in (bus, vendor_id, product_id)
            if param is not None]

        if len(device_specified) not in (0, 3):
            raise ParameterError(
                'Either specify bus, vendor_id and product_id or none of '
                'them.')
        if bus is None and driver_name is None:
            raise ParameterError(
                'Specify (bus, vendor_id, product_id) or driver_name.')
    if bus is not None:
        tables.extend([HWVendorID, HWDevice])
        where_clauses.extend([
            HWVendorID.bus == bus,
            HWVendorID.vendor_id_for_bus == vendor_id,
            HWDevice.bus_vendor == HWVendorID.id,
            HWDeviceDriverLink.device == HWDevice.id,
            HWDevice.bus_product_id == product_id])

    if driver_name is None and package_name is None:
        where_clauses.append(HWDeviceDriverLink.driver == None)
    else:
        tables.append(HWDriver)
        where_clauses.append(HWDeviceDriverLink.driver == HWDriver.id)
        if driver_name is not None:
            where_clauses.append(HWDriver.name == driver_name)
        if package_name is not None:
            if package_name == '':
                # XXX Abel Deuring, 2009-05-07, bug=306265. package_name
                # should be declared notNull=True. For now, we must query
                # for the empty string as well as for None.
                where_clauses.append(
                    Or(HWDriver.package_name == package_name,
                       HWDriver.package_name == None))
            else:
                where_clauses.append(HWDriver.package_name == package_name)

    return tables, where_clauses


def make_distro_target_clause(distro_target):
    """Create a where expression and a table list to limit results to a
    distro target.
    """
    if distro_target is not None:
        if IDistroArchSeries.providedBy(distro_target):
            return (
                [HWSubmission],
                [HWSubmission.distroarchseries == distro_target.id])
        elif IDistroSeries.providedBy(distro_target):
            return (
                [DistroArchSeries, HWSubmission],
                [
                    HWSubmission.distroarchseries == DistroArchSeries.id,
                    DistroArchSeries.distroseries == distro_target.id,
                    ])
        elif IDistribution.providedBy(distro_target):
            return (
                [DistroArchSeries, DistroSeries, HWSubmission],
                [
                    HWSubmission.distroarchseries == DistroArchSeries.id,
                    DistroArchSeries.distroseries == DistroSeries.id,
                    DistroSeries.distribution == distro_target.id,
                    ])
        else:
            raise ValueError(
                'Parameter distro_target must be an IDistribution, '
                'IDistroSeries or IDistroArchSeries')
    return ([], [])


def _userCanAccessSubmissionStormClause(user):
    """Limit results of HWSubmission queries to rows the user can access.
    """
    submission_is_public = Not(HWSubmission.private)
    admins = getUtility(ILaunchpadCelebrities).admin
    janitor = getUtility(ILaunchpadCelebrities).janitor
    if user is None:
        return submission_is_public
    elif user.inTeam(admins) or user == janitor:
        return True
    else:
        public = Not(HWSubmission.private)
        subselect = Select(
            TeamParticipation.teamID,
            And(HWSubmission.ownerID == TeamParticipation.teamID,
                TeamParticipation.personID == user.id,
                HWSubmission.private))
        has_access = HWSubmission.ownerID.is_in(subselect)
        return Or(public, has_access)
