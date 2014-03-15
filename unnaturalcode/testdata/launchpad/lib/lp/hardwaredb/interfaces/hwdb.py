# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces related to the hardware database."""

__metaclass__ = type

__all__ = [
    'HWBus',
    'HWSubmissionFormat',
    'HWSubmissionKeyNotUnique',
    'HWSubmissionMissingFields',
    'HWSubmissionProcessingStatus',
    'IHWDBApplication',
    'IHWDevice',
    'IHWDeviceClass',
    'IHWDeviceClassSet',
    'IHWDeviceDriverLink',
    'IHWDeviceDriverLinkSet',
    'IHWDeviceNameVariant',
    'IHWDeviceNameVariantSet',
    'IHWDeviceSet',
    'IHWDriver',
    'IHWDriverName',
    'IHWDriverPackageName',
    'IHWDriverSet',
    'IHWSubmission',
    'IHWSubmissionBug',
    'IHWSubmissionBugSet',
    'IHWSubmissionForm',
    'IHWSubmissionSet',
    'IHWSubmissionDevice',
    'IHWSubmissionDeviceSet',
    'IHWSystemFingerprint',
    'IHWSystemFingerprintSet',
    'IHWVendorID',
    'IHWVendorIDSet',
    'IHWVendorName',
    'IHWVendorNameSet',
    'IllegalQuery',
    'ParameterError',
    ]

import httplib

from lazr.enum import (
    DBEnumeratedType,
    DBItem,
    )
from lazr.restful.declarations import (
    call_with,
    error_status,
    export_as_webservice_entry,
    export_destructor_operation,
    export_read_operation,
    export_write_operation,
    exported,
    operation_parameters,
    operation_returns_collection_of,
    operation_returns_entry,
    REQUEST_USER,
    )
from lazr.restful.fields import (
    CollectionField,
    Reference,
    )
from lazr.restful.interface import copy_field
from zope.component import getUtility
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    ASCIILine,
    Bool,
    Bytes,
    Choice,
    Datetime,
    Int,
    List,
    TextLine,
    )

from lp import _
from lp.app.interfaces.launchpad import IPrivacy
from lp.app.validators import LaunchpadValidationError
from lp.app.validators.email import valid_email
from lp.app.validators.name import valid_name
from lp.registry.interfaces.distribution import IDistribution
from lp.registry.interfaces.distroseries import IDistroSeries
from lp.registry.interfaces.person import IPerson
from lp.registry.interfaces.product import License
from lp.services.webapp.interfaces import ILaunchpadApplication
from lp.soyuz.interfaces.distroarchseries import IDistroArchSeries


def validate_new_submission_key(submission_key):
    """Check, if submission_key already exists in HWDBSubmission."""
    if not valid_name(submission_key):
        raise LaunchpadValidationError(
            'Submission key can contain only lowercase alphanumerics.')
    submission_set = getUtility(IHWSubmissionSet)
    if submission_set.submissionIdExists(submission_key):
        raise LaunchpadValidationError(
            'Submission key already exists.')
    return True


def validate_email_address(emailaddress):
    """Validate an email address.

    Returns True for valid addresses, else raises LaunchpadValidationError.
    The latter allows convenient error handling by LaunchpadFormView.
    """
    if not valid_email(emailaddress):
        raise LaunchpadValidationError(
            'Invalid email address')
    return True


class HWSubmissionKeyNotUnique(Exception):
    """Prevent two or more submission with identical submission_key."""


class HWSubmissionMissingFields(Exception):
    """Indicate that the HWDB client sent incomplete data."""


class HWSubmissionProcessingStatus(DBEnumeratedType):
    """The status of a submission to the hardware database."""

    INVALID = DBItem(0, """
        Invalid submission

        The submitted data could not be parsed.
        """)

    SUBMITTED = DBItem(1, """
        Submitted

        The submitted data has not yet been processed.
        """)

    PROCESSED = DBItem(2, """
        Processed

        The submitted data has been processed.
        """)


class HWSubmissionFormat(DBEnumeratedType):
    """The format version of the submitted data."""

    VERSION_1 = DBItem(1, "Version 1")


class IHWSubmission(Interface, IPrivacy):
    """Raw submission data for the hardware database.

    See doc/hwdb.txt for details about the attributes.
    """
    export_as_webservice_entry(publish_web_link=False)

    date_created = exported(
        Datetime(
            title=_(u'Date Created'), required=True, readonly=True))
    date_submitted = exported(
        Datetime(
            title=_(u'Date Submitted'), required=True, readonly=True))
    format = exported(
        Choice(
            title=_(u'Format Version'), required=True,
            vocabulary=HWSubmissionFormat, readonly=True))
    status = exported(
        Choice(
            title=_(u'Submission Status'), required=True,
            vocabulary=HWSubmissionProcessingStatus, readonly=True))
    # This is redefined from IPrivacy.private because the attribute is
    # is required.
    private = exported(
        Bool(
            title=_(u'Private Submission'), required=True))
    contactable = exported(
        Bool(
            title=_(u'Contactable'), required=True, readonly=True))
    submission_key = exported(
        TextLine(
            title=_(u'Unique Submission ID'), required=True, readonly=True))
    owner = exported(
        Reference(
            IPerson, title=_(u"The owner of this submission"), readonly=True))
    distroarchseries = Attribute(
        _(u'The DistroArchSeries'))
    raw_submission = exported(
        Bytes(title=_(u'The raw submission data'), required=True,
              readonly=True))
    system_fingerprint = Attribute(
        _(u'The system this submmission was made on'))
    raw_emailaddress = TextLine(
        title=_('Email address'), required=True)

    devices = exported(
        CollectionField(
            title=_(u"The HWSubmissionDevice records for this submission."),
            value_type=Reference(schema=Interface)))


class IHWSubmissionForm(Interface):
    """The schema used to build the HW submission form."""

    date_created = Datetime(
        title=_(u'Date Created'), required=True)
    format = Choice(
        title=_(u'Format Version'), required=True,
        vocabulary=HWSubmissionFormat)
    private = Bool(
        title=_(u'Private Submission'), required=True)
    contactable = Bool(
        title=_(u'Contactable'), required=True)
    submission_key = ASCIILine(
        title=_(u'Unique Submission Key'), required=True,
        constraint=validate_new_submission_key)
    emailaddress = TextLine(
            title=_(u'Email address'), required=True,
            constraint=validate_email_address)
    distribution = TextLine(
        title=_(u'Distribution'), required=True)
    distroseries = TextLine(
        title=_(u'Distribution Release'), required=True)
    architecture = TextLine(
        title=_(u'Processor Architecture'), required=True)
    system = TextLine(
        title=_(u'System name'), required=True)
    submission_data = Bytes(
        title=_(u'Submission data'), required=True)


class IHWSubmissionSet(Interface):
    """The set of HWDBSubmissions."""

    def createSubmission(date_created, format, private, contactable,
                         submission_key, emailaddress, distroarchseries,
                         raw_submission, filename, filesize, system):
        """Store submitted raw hardware information in a Librarian file.

        If a submission with an identical submission_key already exists,
        an HWSubmissionKeyNotUnique exception is raised."""

    def getBySubmissionKey(submission_key, user=None):
        """Return the submission with the given submission key, or None.

        If a submission is marked as private, it is only returned if
        user == HWSubmission.owner, of if user is an admin.
        """

    def getByFingerprintName(name, user=None):
        """Return the submissions for the given system fingerprint string.

        If a submission is marked as private, it is only returned if
        user == HWSubmission.owner, or if user is an admin.
        """

    def getByOwner(owner, user=None):
        """Return the submissions for the given person.

        If a submission is marked as private, it is only returned if
        user == HWSubmission.owner, or if user is an admin.
        """

    def submissionIdExists(submission_key):
        """Return True, if a record with ths ID exists, else return False."""

    def getByStatus(status, user=None):
        """Return the submissions with the given status.

        :param status: A status as enumerated in
            `HWSubmissionProcessingStatus`.
        :param user: The `IPerson` running the query.
        :return: The submissions having the given status.

        If no user is specified, only public submissions are returned.
        If a regular user is specified, public submissions and private
        submissions owned by the user are returned.
        For admins and for the janitor, all submissions with the given
        status are returned.
        """

    def search(user=None, device=None, driver=None, distribution=None,
               distroseries=None, architecture=None, owner=None,
               created_before=None, created_after=None,
               submitted_before=None, submitted_after=None):
        """Return the submissions matiching the given parmeters.

        :param user: The `IPerson` running the query. Private submissions
            are returned only if the person running the query is the
            owner or an admin.
        :param device: Limit results to submissions containing this
            `IHWDevice`.
        :param driver: Limit results to submissions containing devices
            that use this `IHWDriver`.
        :param distribution: Limit results to submissions made for
            this `IDistribution`.
        :param distroseries: Limit results to submissions made for
            this `IDistroSeries`.
        :param architecture: Limit results to submissions made for
            a specific architecture.
        :param owner: Limit results to submissions from this person.
        :param created_before: Exclude results created after this
            date.
        :param created_after: Exclude results created before or on
            this date.
        :param submitted_before: Exclude results submitted after this
            date.
        :param submitted_after: Exclude results submitted before or on
            this date.

        Only one of :distribution: or :distroseries: may be supplied.
        """

    def numSubmissionsWithDevice(bus=None, vendor_id=None, product_id=None,
                                 driver_name=None, package_name=None,
                                 distro_target=None):
        """Count the number of submissions mentioning a device or a driver.

        :return: A tuple (submissions_with_device, all_submissions)
            where submissions_with_device is the number of submissions having
            the given device or driver and matching the distro_target
            criterion and where all_submissions is the number of submissions
            matching the distro_target criterion.
        :param bus: The `HWBus` of the device (optional).
        :param vendor_id: The vendor ID of the device (optional).
        :param product_id: The product ID of the device (optional).
        :param driver_name: The name of the driver used for the device
            (optional).
        :param package_name: The name of the package the driver is a part of.
            (optional).
        :param distro_target: Limit the count to submissions made for the
            given distribution, distroseries or distroarchseries.
            (optional).

        At least each of bus, vendor_id, product_id must not be None or
        driver_name must not be None.
        """

    def numOwnersOfDevice(bus=None, vendor_id=None, product_id=None,
                          driver_name=None, package_name=None,
                          distro_target=None):
        """The number of people owning a device or using a driver.

        :return: A tuple (device_owners, all_hardware_reporters)
            where device_owners is the number of people who made a HWDB
            submission containing the given device or driver, optionally
            limited to submissions made for the given distro_target.
            all_hardware_reporters is the number of persons who made
            a HWDB submission, optionally limited to submission made
            on the given distro_target installation.
        :param bus: The `HWBus` of the device (optional).
        :param vendor_id: The vendor ID of the device (optional).
        :param product_id: The product ID of the device (optional).
        :param driver_name: The name of the driver used for the device
            (optional).
        :param package_name: The name of the package the driver is a part of.
            (optional).
        :param distro_target: Limit the count to submissions made for the
            given distribution, distroseries or distroarchseries.
            (optional).

        At least each of bus, vendor_id, product_id must not be None or
        driver_name must not be None.
        """

    def deviceDriverOwnersAffectedByBugs(
        bus=None, vendor_id=None, product_id=None, driver_name=None,
        package_name=None, bug_ids=None, bug_tags=None, affected_by_bug=False,
        subscribed_to_bug=False, user=None):
        """Return persons affected by given bugs and owning a given device.

        :param bus: The `HWBus` of the device.
        :param vendor_id: The vendor ID of the device.
        :param product_id: The product ID of the device.
        :param driver_name: Limit the search to devices controlled by the
            given driver.
        :param package_name: Limit the search to devices controlled by a
            driver from the given package.
        :param bug_ids: A sequence of bug IDs for which affected device
            owners are looked up.
        :param bug_tags: A sequence of bug tags.
        :param affected_by_bug: If True, those persons are looked up that
            have marked themselves as being affected by a one of the bugs
            matching the bug criteria.
        :param subscribed_to_bug: If True, those persons are looked up that
            are subscribed to a bug matching one of the bug criteria.
        :param user: The person making the query.

        `bug_ids` must be a non-empty sequence of bug IDs, or `bug_tags`
        must be a non-empty sequence of bug tags.

        The parameters `bus`, `vendor_id`, `product_id` must not be None, or
        `driver_name` must not be None.

        By default, only those persons are returned which have reported a
        bug matching the given bug conditions.

        Owners of private submissions are returned only if user is the
        owner of the private submission or if user is an admin.
        """

    def hwInfoByBugRelatedUsers(
        bug_ids=None, bug_tags=None, affected_by_bug=False,
        subscribed_to_bug=False, user=None):
        """Return a list of owners and devices related to given bugs.

        Actually returns a list of tuples where the tuple is of the form,
        (person name, bus name, vendor id, product id).`

        :param bug_ids: A sequence of bug IDs for which affected
            are looked up.
        :param bug_tags: A sequence of bug tags
        :param affected_by_bug: If True, those persons are looked up that
            have marked themselves as being affected by a one of the bugs
            matching the bug criteria.
        :param subscribed_to_bug: If True, those persons are looked up that
            are subscribed to a bug matching one of the bug criteria.
        :param user: The person making the query.
        """


class IHWSystemFingerprint(Interface):
    """Identifiers of a computer system."""

    fingerprint = Attribute(u'A unique identifier of a system')


class IHWSystemFingerprintSet(Interface):
    """The set of HWSystemFingerprints."""

    def getByName(fingerprint):
        """Lookup an IHWSystemFingerprint by its value.

        Return None, if a fingerprint `fingerprint` does not exist."""

    def createFingerprint(fingerprint):
        """Create an entry in the fingerprint list.

        Return the new entry."""


class IHWDriver(Interface):
    """Information about a device driver."""
    export_as_webservice_entry(publish_web_link=False)

    id = exported(
        Int(title=u'Driver ID', required=True, readonly=True))

    package_name = exported(
        TextLine(
            title=u'Package Name', required=False,
            description=_("The name of the package written without spaces in "
                          "lowercase letters and numbers."),
            default=u''))

    name = exported(
        TextLine(
            title=u'Driver Name', required=True,
            description=_("The name of the driver written without spaces in "
                          "lowercase letters and numbers.")))

    license = exported(
        Choice(
            title=u'License of the Driver', required=False,
            vocabulary=License))

    @operation_parameters(
        distribution=Reference(
            IDistribution,
            title=u'A Distribution',
            description=(
                u'If specified, the result set is limited to sumbissions '
                'made for the given distribution.'),
            required=False),
        distroseries=Reference(
            IDistroSeries,
            title=u'A Distribution Series',
            description=(
                u'If specified, the result set is limited to sumbissions '
                'made for the given distribution series.'),
            required=False),
        architecture=TextLine(
            title=u'A processor architecture',
            description=(
                u'If specified, the result set is limited to sumbissions '
                'made for the given architecture.'),
            required=False),
        owner=copy_field(IHWSubmission['owner']))
    @operation_returns_collection_of(IHWSubmission)
    @export_read_operation()
    def getSubmissions(distribution=None, distroseries=None,
                       architecture=None, owner=None):
        """List all submissions which mention this driver.

        :param distribution: Limit results to submissions for this
            `IDistribution`.
        :param distroseries: Limit results to submissions for this
            `IDistroSeries`.
        :param architecture: Limit results to submissions for this
            architecture.
        :param owner: Limit results to submissions from this person.

        Only submissions matching all given criteria are returned.
        Only one of :distribution: or :distroseries: may be supplied.
        """


class IHWDriverSet(Interface):
    """The set of device drivers."""

    def create(package_name, name, license):
        """Create a new IHWDriver instance.

        :param package_name: The name of the packages containing the driver.
        :param name: The name of the driver.
        :param license: The license of the driver.
        :return: The new IHWDriver instance.
        """

    def getByPackageAndName(package_name, name):
        """Return an IHWDriver instance for the given parameters.

        :param package_name: The name of the packages containing the driver.
        :param name: The name of the driver.
        :return: An IHWDriver instance or None, if no record exists for
            the given parameters.
        """

    def getOrCreate(package_name, name, license=None):
        """Return an IHWDriver instance or create one.

        :param package_name: The name of the packages containing the driver.
        :param name: The name of the driver.
        :param license: The license of the driver.
        :return: An IHWDriver instance or None, if no record exists for
            the given parameters.
        """

    def search(package_name=None, name=None):
        """Return the drivers matching the given parameters.

        :param package_name: The name of the packages containing the driver.
            If package_name is not given or None, the result set is
            not limited to a specific package name.
            If package_name == '', those records are returned where
            record.package_name == '' or record.package_name is None.
            Otherwise only records matching the given name are returned.
        :param name: The name of the driver.
            If name is not given or None, the result set is not limited to
            a specific driver name.
            Otherwise only records matching the given name are returned.
        :return: A sequence of IHWDriver instances.
        """

    def getByID(id):
        """Return an IHWDriver record with the given database ID.

        :param id: The database ID.
        :return: An IHWDriver instance.
        """

    def all_driver_names():
        """Return all known distinct driver names appearing in HWDriver."""

    def all_package_names():
        """Return all known distinct package names appearing in HWDriver."""


class IHWDriverName(Interface):
    """A driver name as appearing in `IHWDriver`.
    """
    export_as_webservice_entry(publish_web_link=False)

    name = exported(
        TextLine(
            title=u'Driver Name', required=True, readonly=True,
            description=_("The name of a driver as it appears in "
                          "IHWDriver.")))


class IHWDriverPackageName(Interface):
    """A driver name as appearing in `IHWDriver`.
    """
    export_as_webservice_entry(publish_web_link=False)

    package_name = exported(
        TextLine(
            title=u'Package Name', required=True, readonly=True,
            description=_("The name of a package as it appears in "
                          "IHWDriver.")))


# Identification of a hardware device.
#
# In theory, a tuple (bus, vendor ID, product ID) should identify
# a device unambiguously. In practice, there are several cases where
# this tuple can identify more than one device:
#
# - A USB chip or chipset may be used in different devices.
#   A real world example:
#     - Plustek sold different scanner models with the USB ID
#       0x7b3/0x0017. Some of these scanners have for example a
#       different maximum scan size.
#
# Hence we identify a device by tuple (bus, vendor ID, product ID,
# variant). In the example above, we might use (HWBus.USB, '0x7b3',
# '0x0017', 'OpticPro UT12') and (HWBus.USB, '0x7b3', '0x0017',
# 'OpticPro UT16')

class HWBus(DBEnumeratedType):
    """The bus that connects a device to a computer."""

    SYSTEM = DBItem(0, 'System')

    PCI = DBItem(1, 'PCI')

    USB = DBItem(2, 'USB')

    IEEE1394 = DBItem(3, 'IEEE1394')

    SCSI = DBItem(4, 'SCSI')

    PARALLEL = DBItem(5, 'Parallel Port')

    SERIAL = DBItem(6, 'Serial port')

    IDE = DBItem(7, 'IDE')

    ATA = DBItem(8, 'ATA')

    FLOPPY = DBItem(9, 'Floppy')

    IPI = DBItem(10, 'IPI')

    SATA = DBItem(11, 'SATA')

    SAS = DBItem(12, 'SAS')

    PCCARD = DBItem(13, 'PC Card (32 bit)')

    PCMCIA = DBItem(14, 'PCMCIA (16 bit)')


class IHWVendorName(Interface):
    """A list of vendor names."""
    name = TextLine(title=u'Vendor Name', required=True)


class IHWVendorNameSet(Interface):
    """The set of vendor names."""
    def create(name):
        """Create and return a new vendor name.

        :return: A new IHWVendorName instance.

        An IntegrityError is raised, if the name already exists.
        """

    def getByName(name):
        """Return the IHWVendorName record for the given name.

        :param name: The vendor name.
        :return: An IHWVendorName instance where IHWVendorName.name==name
            or None, if no such instance exists.
        """


class IHWVendorID(Interface):
    """A list of vendor IDs for different busses associated with vendor names.
    """
    export_as_webservice_entry(publish_web_link=False)
    id = exported(
        Int(title=u'The Database ID', required=True, readonly=True))

    bus = exported(
        Choice(
            title=u'The bus that connects a device to a computer',
            required=True, vocabulary=HWBus))

    vendor_id_for_bus = exported(
        TextLine(title=u'Vendor ID', required=True),
        exported_as='vendor_id')

    vendor_name = Attribute('Vendor Name')


class IHWVendorIDSet(Interface):
    """The set of vendor IDs."""
    def create(bus, vendor_id, name):
        """Create a vendor ID.

        :param bus: the HWBus instance for this bus.
        :param vendor_id: a string containing the bus ID. Numeric IDs
            are represented as a hexadecimal string, prepended by '0x'.
        :param name: The IHWVendorName instance with the vendor name.
        :return: A new IHWVendorID instance.
        """

    def getByBusAndVendorID(bus, vendor_id):
        """Return an IHWVendorID instance for the given bus and vendor_id.

        :param bus: An HWBus instance.
        :param vendor_id: A string containing the vendor ID. Numeric IDs
            must be represented as a hexadecimal string, prepended by '0x'.
        :return: The found IHWVendorID instance or None, if no instance
            for the given bus and vendor ID exists.
        """

    def get(id):
        """Return an IHWVendorID record with the given database ID.

        :param id: The database ID.
        :return: An IHWVendorID instance.
        """

    def idsForBus(bus):
        """Return all known IHWVendorID records with the given bus.

        :param bus: A HWBus instance.
        :return: A sequence of IHWVendorID instances.
        """


class IHWDeviceClass(Interface):
    """The capabilities of a device."""
    export_as_webservice_entry(publish_web_link=False)

    id = Int(title=u'Device class ID', required=True, readonly=True)
    device = Reference(schema=Interface)
    main_class = exported(
        Int(
            title=u'The main class of this device', required=True,
            readonly=True))
    sub_class = exported(
        Int(
            title=u'The sub class of this device', required=False,
            readonly=True))

    @export_destructor_operation()
    def delete():
        """Delete this record."""


class IHWDeviceClassSet(Interface):
    """The set of IHWDeviceClass records."""

    def get(id):
        """Return an `IHWDeviceClass` record with the given database ID.

        :param id: The database ID.
        :return: An `IHWDeviceClass` instance.
        """


VENDOR_ID_DESCRIPTION = u"""Allowed values of the vendor ID depend on the
bus of the device.

Vendor IDs of PCI, PCCard and USB devices are hexadecimal string
representations of 16 bit integers in the format '0x01ab': The prefix
'0x', followed by exactly 4 digits; where a digit is one of the
characters 0..9, a..f. The characters A..F are not allowed.

SCSI vendor IDs are strings with exactly 8 characters. Shorter names are
right-padded with space (0x20) characters.

IDs for other buses may be arbitrary strings.
"""

PRODUCT_ID_DESCRIPTION = u"""Allowed values of the product ID depend on the
bus of the device.

Product IDs of PCI, PCCard and USB devices are hexadecimal string
representations of 16 bit integers in the format '0x01ab': The prefix
'0x', followed by exactly 4 digits; where a digit is one of the
characters 0..9, a..f. The characters A..F are not allowed.

SCSI product IDs are strings with exactly 16 characters. Shorter names are
right-padded with space (0x20) characters.

IDs for other buses may be arbitrary strings.
"""


class IHWDevice(Interface):
    """Core information to identify a device."""
    export_as_webservice_entry(publish_web_link=False)

    id = exported(
        Int(title=u'Device ID', required=True, readonly=True))

    bus_vendor = Attribute(u'Ths bus and vendor of the device')

    bus_product_id = exported(
        TextLine(title=u'The product identifier of the device',
                 required=True, description=PRODUCT_ID_DESCRIPTION))

    variant = exported(
        TextLine(title=u'A string that distiguishes different '
                        'devices with identical vendor/product IDs',
                 required=True))

    name = exported(
        TextLine(title=u'The human readable name of the device.',
                 required=True))

    submissions = Int(title=u'The number of submissions with the device',
                      required=True)

    bus = exported(
        Choice(title=u'The bus of the device.', vocabulary=HWBus,
               readonly=True))

    vendor_id = exported(
        TextLine(title=u'The vendor iD.', readonly=True,
                 description=VENDOR_ID_DESCRIPTION))

    vendor_name = exported(
        TextLine(title=u'The vendor name.', readonly=True))

    @operation_parameters(
        driver=Reference(
            IHWDriver,
            title=u'A driver used for this device in a submission',
            description=(
                u'If specified, the result set is limited to sumbissions '
                'made for the given distribution, distroseries or '
                'distroarchseries.'),
            required=False),
        distribution=Reference(
            IDistribution,
            title=u'A Distribution',
            description=(
                u'If specified, the result set is limited to sumbissions '
                'made for the given distribution.'),
            required=False),
        distroseries=Reference(
            IDistroSeries,
            title=u'A Distribution Series',
            description=(
                u'If specified, the result set is limited to sumbissions '
                'made for the given distribution series.'),
            required=False),
        architecture=TextLine(
            title=u'A processor architecture',
            description=(
                u'If specified, the result set is limited to submissions '
                'made for the given architecture.'),
            required=False),
        owner=copy_field(IHWSubmission['owner']))
    @operation_returns_collection_of(IHWSubmission)
    @export_read_operation()
    def getSubmissions(driver=None, distribution=None,
                       distroseries=None, architecture=None, owner=None):
        """List all submissions which mention this device.

        :param driver: Limit results to devices that use the given
            `IHWDriver`.
        :param distribution: Limit results to submissions for this
            `IDistribution`.
        :param distroseries: Limit results to submissions for this
            `IDistroSeries`.
        :param architecture: Limit results to submissions for this
            architecture.
        :param owner: Limit results to submissions from this person.

        Only submissions matching all given criteria are returned.
        Only one of :distribution: or :distroseries: may be supplied.
        """

    drivers = exported(
        CollectionField(
            title=_(u"The IHWDriver records related to this device."),
            value_type=Reference(schema=IHWDriver)))

    classes = exported(
        CollectionField(
            title=_(u"The device classes this device belongs to."),
            value_type=Reference(schema=IHWDeviceClass)))

    @operation_parameters(
        main_class=copy_field(IHWDeviceClass['main_class']),
        sub_class=copy_field(IHWDeviceClass['sub_class']))
    @export_write_operation()
    @operation_returns_entry(IHWDeviceClass)
    def getOrCreateDeviceClass(main_class, sub_class=None):
        """Return an `IHWDeviceClass` record or create a new one.

        :param main_class: The main class to be added.
        :param sub_class: The sub-class to added (otpional).
        :return: An `IHWDeviceClass` record.

        main_class and sub_class are integers specifying the class
        of the device, or, in the case of USB devices, the class
        of an interface.

        `IHWDeviceClass` records must be unique; if this method is called
        to create a new record with data of an already existing record,
        the existing record is returned.
        """

    @operation_parameters(
        main_class=copy_field(IHWDeviceClass['main_class']),
        sub_class=copy_field(IHWDeviceClass['sub_class']))
    @export_write_operation()
    def removeDeviceClass(main_class, sub_class=None):
        """Add an `IHWDeviceClass` record.

        :param main_class: The main class to be added.
        :param sub_class: The sub-class to added.
        """


# Fix cyclic reference.
IHWDeviceClass['device'].schema = IHWDevice


class IHWDeviceSet(Interface):
    """The set of devices."""

    def create(bus, vendor_id, product_id, product_name, variant=None):
        """Create a new device entry.

        :param bus: A bus name as enumerated in HWBus.
        :param vendor_id: The vendor ID for the bus.
        :param product_id: The product ID.
        :param product_name: The human readable product name.
        :param variant: A string that allows to distinguish different devices
                        with identical product/vendor IDs.
        :return: A new IHWDevice instance.
        """

    def getByDeviceID(bus, vendor_id, product_id, variant=None):
        """Return an IHWDevice record.

        :param bus: The bus name of the device as enumerated in HWBus.
        :param vendor_id: The vendor ID of the device.
        :param product_id: The product ID of the device.
        :param variant: A string that allows to distinguish different devices
                        with identical product/vendor IDs.
        :return: An IHWDevice instance.
        """

    def getOrCreate(bus, vendor_id, product_id, product_name, variant=None):
        """Return an IHWDevice record or create one.

        :param bus: The bus name of the device as enumerated in HWBus.
        :param vendor_id: The vendor ID of the device.
        :param product_id: The product ID of the device.
        :param product_name: The human readable product name.
        :param variant: A string that allows to distinguish different devices
                        with identical product/vendor IDs.
        :return: An IHWDevice instance.

        Return an existing IHWDevice record matching the given
        parameters or create a new one, if no existing record
        matches.
        """

    def getByID(id):
        """Return an IHWDevice record with the given database ID.

        :param id: The database ID.
        :return: An IHWDevice instance.
        """

    def search(bus, vendor_id, product_id=None):
        """Return HWDevice records matching the given parameters.

        :param vendor_id: The vendor ID of the device.
        :param product_id: The product ID of the device.
        :return: A sequence of IHWDevice instances.
        """


class IHWDeviceNameVariant(Interface):
    """Variants of a device name.

    We identify devices by (bus, vendor_id, product_id[, variant]),
    but many OEM products are sold by different vendors under different
    names. Users might want to look up device data by giving the
    vendor and product name as seen in a store; this table provides
    the "alias names" required for such a lookup.
    """
    vendor_name = Attribute(u'Vendor Name')

    product_name = TextLine(title=u'Product Name', required=True)

    device = Attribute(u'The device which has this name')

    submissions = Int(
        title=u'The number of submissions with this name variant',
        required=True)


class IHWDeviceNameVariantSet(Interface):
    """The set of device name variants."""

    def create(device, vendor_name, product_name):
        """Create a new IHWDeviceNameVariant instance.

        :param device: An IHWDevice instance.
        :param vendor_name: The alternative vendor name for the device.
        :param product_name: The alternative product name for the device.
        :return: The new IHWDeviceNameVariant.
        """


class IHWDeviceDriverLink(Interface):
    """Link a device with a driver."""

    device = Attribute(u'The Device.')

    driver = Attribute(u'The Driver.')


class IHWDeviceDriverLinkSet(Interface):
    """The set of device driver links."""

    def create(device, driver):
        """Create a new IHWDeviceDriver instance.

        :param device: The IHWDevice instance to be linked.
        :param driver: The IHWDriver instance to be linked.
        :return: The new IHWDeviceDriver instance.
        """

    def getByDeviceAndDriver(device, driver):
        """Return an IHWDeviceDriver instance.

        :param device: An IHWDevice instance.
        :param driver: An IHWDriver instance.
        :return: The IHWDeviceDriver instance matching the given
            parameters or None, if no existing instance matches.
        """
    def getOrCreate(device, driver):
        """Return an IHWDeviceDriverLink record or create one.

        :param device: The IHWDevice instance to be linked.
        :param driver: The IHWDriver instance to be linked.
        :return: An IHWDeviceDriverLink instance.

        Return an existing IHWDeviceDriverLink record matching te given
        parameters or create a new one, if no exitsing record
        matches.
        """


class IHWSubmissionDevice(Interface):
    """Link a submission to a IHWDeviceDriver row."""
    export_as_webservice_entry(publish_web_link=False)

    id = exported(
        Int(title=u'HWSubmissionDevice ID', required=True, readonly=True))

    device_driver_link = Attribute(u'A device and driver appearing in a '
                                    'submission.')

    submission = Attribute(u'The submission the device and driver are '
                            'mentioned in.')

    parent = exported(
        # This is a reference to IHWSubmissionDevice itself, but we can
        # access the class only when the class has been defined.
        Reference(Interface, required=True))

    hal_device_id = exported(
        Int(
            title=u'The ID of the HAL node of this device in the submitted '
                'data',
            required=True))

    device = exported(
        Reference(
            IHWDevice,
            title=u'The device'))

    driver = exported(
        Reference(
            IHWDriver,
            title=u'The driver used for this device in this submission'))


# Fix cyclic references.
IHWSubmissionDevice['parent'].schema = IHWSubmissionDevice
IHWSubmission['devices'].value_type.schema = IHWSubmissionDevice


class IHWSubmissionDeviceSet(Interface):
    """The set of IHWSubmissionDevices."""

    def create(device_driver_link, submission, parent):
        """Create a new IHWSubmissionDevice instance.

        :param device_driver_link: An IHWDeviceDriverLink instance.
        :param submission: The submission the device/driver combination
            is mentioned in.
        :param parent: The parent of this device in the device tree in
            the submission.
        :return: The new IHWSubmissionDevice instance.
        """

    def getDevices(submission):
        """Return the IHWSubmissionDevice records of a submission

        :return: A sequence of IHWSubmissionDevice records.
        :param submission: An IHWSubmission instance.
        """

    def get(id):
        """Return an IHWSubmissionDevice record with the given database ID.

        :param id: The database ID.
        :return: An IHWSubmissionDevice instance.
        """

    def numDevicesInSubmissions(
        bus=None, vendor_id=None, product_id=None, driver_name=None,
        package_name=None, distro_target=None):
        """Count how often a device or a driver appears in HWDB submissions.

        :return: The number how often the given device appears in HWDB
            submissions.
        :param bus: The `HWBus` of the device (optional).
        :param vendor_id: The vendor ID of the device (optional).
        :param product_id: The product ID of the device (optional).
        :param driver_name: Limit the count to devices controlled by the given
            driver (optional).
        :param package_name: Limit the count to devices controlled by a driver
            from the given package (optional).
        :param distro_target: Limit the count to devices appearing in HWDB
            submissions made for the given distribution, distroseries
            or distroarchseries (optional).

        At least each of bus, vendor_id, product_id must not be None or
        driver_name must not be None.
        """


class IHWSubmissionBug(Interface):
    """Link a HWDB submission to a bug."""

    submission = Attribute(u'The HWDB submission referenced in a bug '
                              'report.')

    bug = Attribute(u'The bug the HWDB submission is referenced in.')


class IHWSubmissionBugSet(Interface):
    """The set of IHWSubmissionBugs."""

    def create(hwsubmission, bug):
        """Create a new IHWSubmissionBug instance.

        :return: The new IHWSubmissionBug instance.
        :param hwsubmission: An IHWSubmission instance.
        :param bug: An IBug instance.
        """

    def remove(hwsubmission, bug):
        """Remove the link between `hwsubmission` and `bug`.

        :param hwsubmission: An IHWSubmission instance.
        :param bug: An IBug instance.
        """

    def submissionsForBug(bug, user=None):
        """Return the HWDB submissions linked to the bug `bug`.

        :return: A sequence of HWDB submissions linked to `bug`.
        :param user: The user making the request.

        Only those submissions are returned which the user can access.
        Public submissions are always included; private submisisons only
        if the user is the owner or an admin.
        """


class IHWDBApplication(ILaunchpadApplication):
    """Hardware database application application root."""

    export_as_webservice_entry('hwdb', publish_web_link=False)

    @operation_parameters(
        bus=Choice(
            title=u'The device bus', vocabulary=HWBus, required=True),
        vendor_id=TextLine(
            title=u'The vendor ID', required=True,
            description=VENDOR_ID_DESCRIPTION),
        product_id=TextLine(
            title=u'The product ID', required=False,
            description=PRODUCT_ID_DESCRIPTION))
    @operation_returns_collection_of(IHWDevice)
    @export_read_operation()
    def devices(bus, vendor_id, product_id=None):
        """Return the set of devices."""

    @operation_parameters(
        package_name=TextLine(
            title=u'The name of the package containing the driver.',
            required=False,
            description=(
                u'If package_name is omitted, all driver records '
                'returned, optionally limited to those matching the '
                'parameter name. If package_name is '' (empty string), '
                'those records are returned where package_name is '' or '
                'None.')),
        name=TextLine(
            title=u'The name of the driver.', required=False,
            description=(
                u'If name is omitted, all driver records are '
                'returned, optionally limited to those matching the '
                'parameter package_name.')))
    @operation_returns_collection_of(IHWDriver)
    @export_read_operation()
    def drivers(package_name=None, name=None):
        """Return the set of drivers."""

    @operation_parameters(
        bus=Choice(
            title=u'A Device Bus.', vocabulary=HWBus, required=True))
    @operation_returns_collection_of(IHWVendorID)
    @export_read_operation()
    def vendorIDs(bus):
        """Return the known vendor IDs for the given bus.

        :param bus: A `HWBus` value.
        :return: A list of strings with vendor IDs fr this bus,
        """

    driver_names = exported(
        CollectionField(
            title=u'Driver Names',
            description=(
                u'All known distinct driver names appearing in HWDriver'),
            value_type=Reference(schema=IHWDriverName),
            readonly=True))

    package_names = exported(
        CollectionField(
            title=u'Package Names',
            description=(
                u'All known distinct package names appearing in '
                'HWDriver.'),
            value_type=Reference(schema=IHWDriverPackageName),
            readonly=True))

    @operation_parameters(
        device=Reference(
            IHWDevice,
            title=u'A Device',
            description=(
                u'If specified, the result set is limited to submissions '
                u'containing this device.'),
            required=False),
        driver=Reference(
            IHWDriver,
            title=u'A Driver',
            description=(
                u'If specified, the result set is limited to submissions '
                u'containing devices that use this driver.'),
            required=False),
        distribution=Reference(
            IDistribution,
            title=u'A Distribution',
            description=(
                u'If specified, the result set is limited to submissions '
                u'made for this distribution.'),
            required=False),
        distroseries=Reference(
            IDistroSeries,
            title=u'A Distribution Series',
            description=(
                u'If specified, the result set is limited to submissions '
                u'made for the given distribution series.'),
            required=False),
        architecture=TextLine(
            title=u'A processor architecture',
            description=(
                u'If specified, the result set is limited to sumbissions '
                'made for a specific architecture.'),
            required=False),
        owner=Reference(
            IPerson,
            title=u'Person',
            description=(
                u'If specified, the result set is limited to sumbissions '
                'from this person.'),
            required=False),
        created_before=Datetime(
            title=u'Created Before',
            description=(
                u'If specified, exclude results created after this date.'),
            required=False),
        created_after=Datetime(
            title=u'Created After',
            description=(
                u'If specified, exclude results created before or on '
                'this date.'),
            required=False),
        submitted_before=Datetime(
            title=u'Created Before',
            description=(
                u'If specified, exclude results submitted after this date.'),
            required=False),
        submitted_after=Datetime(
            title=u'Created After',
            description=(
                u'If specified, Exclude results submitted before or on '
                'this date.'),
            required=False))
    @call_with(user=REQUEST_USER)
    @operation_returns_collection_of(IHWSubmission)
    @export_read_operation()
    def search(user=None, device=None, driver=None, distribution=None,
               distroseries=None, architecture=None, owner=None,
               created_before=None, created_after=None,
               submitted_before=None, submitted_after=None):
        """Return the submissions matiching the given parmeters.

        :param user: The `IPerson` running the query. Private submissions
            are returned only if the person running the query is the
            owner or an admin.
        :param device: Limit results to submissions containing this
            `IHWDevice`.
        :param driver: Limit results to submissions containing devices
            that use this `IHWDriver`.
        :param distribution: Limit results to submissions made for
            this `IDistribution`.
        :param distroseries: Limit results to submissions made for
            this `IDistroSeries`.
        :param architecture: Limit results to submissions made for
            a specific architecture.
        :param owner: Limit results to submissions from this person.
        :param created_before: Exclude results created after this
            date.
        :param created_after: Exclude results created before or on
            this date.
        :param submitted_before: Exclude results submitted after this
            date.
        :param submitted_after: Exclude results submitted before or on
            this date.

        Only one of :distribution: or :distroseries: may be supplied.
        """

    @operation_parameters(
        bus=Choice(
            title=u'The device bus', vocabulary=HWBus, required=False),
        vendor_id=TextLine(
            title=u'The vendor ID', description=VENDOR_ID_DESCRIPTION,
             required=False),
        product_id=TextLine(
            title=u'The product ID', description=PRODUCT_ID_DESCRIPTION,
            required=False),
        driver_name=TextLine(
            title=u'A driver name', required=False,
            description=u'If specified, the count is limited to devices '
                        'controlled by this driver.'),
        package_name=TextLine(
            title=u'A package name', required=False,
            description=u'If specified, the count is limited to devices '
                        u'controlled by a driver from this package.'),
        distribution=Reference(
            IDistribution,
            title=u'A Distribution',
            description=(
                u'If specified, the result set is limited to submissions '
                u'made for this distribution.'),
            required=False),
        distroseries=Reference(
            IDistroSeries,
            title=u'A Distribution Series',
            description=(
                u'If specified, the result set is limited to submissions '
                u'made for the given distribution series.'),
            required=False),
        distroarchseries=Reference(
            IDistroArchSeries,
            title=u'A Distribution Series',
            description=(
                u'If specified, the result set is limited to submissions '
                u'made for the given distroarchseries.'),
            required=False))
    @export_read_operation()
    def numSubmissionsWithDevice(
        bus=None, vendor_id=None, product_id=None, driver_name=None,
        package_name=None, distribution=None, distroseries=None,
        distroarchseries=None):
        """Count the number of submissions mentioning a device  or a driver.

        Returns a dictionary {'submissions_with_device: n1,
        'all_submissions': n2}, where submissions_with_device is the number
        of submissions having the given device or driver and matching the
        distro target criterion and where all_submissions is the number of
        submissions matching the distro target criterion.

        :param bus: The `HWBus` of the device (optional).
        :param vendor_id: The vendor ID of the device (optional).
        :param product_id: The product ID of the device (optional).
        :param driver_name: The name of the driver used for the device
            (optional).
        :param package_name: The name of the package the driver is a part of.
            (optional).
        :param distribution: Limit the count to submissions made for the
            given distribution, distroseries or distroarchseries.
            (optional).
        :param distroseries: Limit the count to submissions made for the
            given distroseries.
            (optional).
        :param distroarchseries: Limit the count to submissions made for the
            given distroarchseries.
            (optional).

        You may specify at most one of the parameters distribution,
        distroseries or distroarchseries.

        At least each of bus, vendor_id, product_id must not be None or
        driver_name must not be None.
        """

    @operation_parameters(
        bus=Choice(
            title=u'The device bus', vocabulary=HWBus, required=False),
        vendor_id=TextLine(
            title=u'The vendor ID', description=VENDOR_ID_DESCRIPTION,
             required=False),
        product_id=TextLine(
            title=u'The product ID', description=PRODUCT_ID_DESCRIPTION,
            required=False),
        driver_name=TextLine(
            title=u'A driver name', required=False,
            description=u'If specified, the count is limited to devices '
                        u'controlled by this driver.'),
        package_name=TextLine(
            title=u'A package name', required=False,
            description=u'If specified, the count is limited to devices '
                        u'controlled by a driver from this package.'),
        distribution=Reference(
            IDistribution,
            title=u'A Distribution',
            description=(
                u'If specified, the result set is limited to submissions '
                u'made for this distribution.'),
            required=False),
        distroseries=Reference(
            IDistroSeries,
            title=u'A Distribution Series',
            description=(
                u'If specified, the result set is limited to submissions '
                u'made for the given distribution series.'),
            required=False),
        distroarchseries=Reference(
            IDistroArchSeries,
            title=u'A Distribution Series',
            description=(
                u'If specified, the result set is limited to submissions '
                u'made for the given distroarchseries.'),
            required=False))
    @export_read_operation()
    def numOwnersOfDevice(
        bus=None, vendor_id=None, product_id=None, driver_name=None,
        package_name=None, distribution=None, distroseries=None,
        distroarchseries=None):
        """The number of people owning a device or using a driver.

        Returns a dictionary {'owners': n1, 'all_submitters': n2}
        where owners is the number of people who made a HWDB
        submission containing the given device or driver, optionally
        limited to submissions made for the given distro target.
        all_submitters is the number of persons who made
        a HWDB submission, optionally limited to submission made
        on the given distro target installation.

        :param bus: The `HWBus` of the device (optional).
        :param vendor_id: The vendor ID of the device (optional).
        :param product_id: The product ID of the device (optional).
        :param driver_name: The name of the driver used for the device
            (optional).
        :param package_name: The name of the package the driver is a part of.
            (optional).
        :param distribution: Limit the count to submissions made for the
            given distribution, distroseries or distroarchseries.
            (optional).
        :param distroseries: Limit the count to submissions made for the
            given distroseries.
            (optional).
        :param distroarchseries: Limit the count to submissions made for the
            given distroarchseries.
            (optional).

        You may specify at most one of the parameters distribution,
        distroseries or distroarchseries.

        At least each of bus, vendor_id, product_id must not be None or
        driver_name must not be None.
        """

    @operation_parameters(
        bus=Choice(
            title=u'The device bus', vocabulary=HWBus, required=False),
        vendor_id=TextLine(
            title=u'The vendor ID', description=VENDOR_ID_DESCRIPTION,
             required=False),
        product_id=TextLine(
            title=u'The product ID', description=PRODUCT_ID_DESCRIPTION,
            required=False),
        driver_name=TextLine(
            title=u'A driver name', required=False,
            description=u'If specified, the count is limited to devices '
                        u'controlled by this driver.'),
        package_name=TextLine(
            title=u'A package name', required=False,
            description=u'If specified, the count is limited to devices '
                        u'controlled by a driver from this package.'),
        distribution=Reference(
            IDistribution,
            title=u'A Distribution',
            description=(
                u'If specified, the result set is limited to submissions '
                u'made for this distribution.'),
            required=False),
        distroseries=Reference(
            IDistroSeries,
            title=u'A Distribution Series',
            description=(
                u'If specified, the result set is limited to submissions '
                u'made for the given distribution series.'),
            required=False),
        distroarchseries=Reference(
            IDistroArchSeries,
            title=u'A Distribution Series',
            description=(
                u'If specified, the result set is limited to submissions '
                u'made for the given distroarchseries.'),
            required=False))
    @export_read_operation()
    def numDevicesInSubmissions(
        bus=None, vendor_id=None, product_id=None, driver_name=None,
        package_name=None, distribution=None, distroseries=None,
        distroarchseries=None):
        """Count how often a device or a driver appears in HWDB submissions.

        :return: The number how often the given device appears in HWDB
            submissions.
        :param bus: The `HWBus` of the device (optional).
        :param vendor_id: The vendor ID of the device (optional).
        :param product_id: The product ID of the device (optional).
        :param driver_name: Limit the count to devices controlled by the given
            driver (optional).
        :param package_name: Limit the count to devices controlled by a driver
            from the given package (optional).
        :param distribution: Limit the count to submissions made for the
            given distribution, distroseries or distroarchseries.
            (optional).
        :param distroseries: Limit the count to submissions made for the
            given distroseries.
            (optional).
        :param distroarchseries: Limit the count to submissions made for the
            given distroarchseries.
            (optional).

        You may specify at most one of the parameters distribution,
        distroseries or distroarchseries.

        At least each of bus, vendor_id, product_id must not be None or
        driver_name must not be None.
        """

    @operation_parameters(
        bus=Choice(
            title=u'The device bus', vocabulary=HWBus, required=False),
        vendor_id=TextLine(
            title=u'The vendor ID', description=VENDOR_ID_DESCRIPTION,
             required=False),
        product_id=TextLine(
            title=u'The product ID', description=PRODUCT_ID_DESCRIPTION,
            required=False),
        driver_name=TextLine(
            title=u'A driver name', required=False,
            description=u'If specified, the search is limited to devices '
                        u'controlled by this driver.'),
        package_name=TextLine(
            title=u'A package name', required=False,
            description=u'If specified, the search is limited to devices '
                        u'controlled by a driver from this package.'),
        bug_ids=List(title=u'A set of bug IDs',
             description=u'Search submitters, subscribers or affected users '
                         u'of bugs with these IDs.',
             value_type=Int(),
             required=False),
        bug_tags=List(title=u'A set of bug tags',
             description=u'Search submitters, subscribers or affected users '
                         u'of bugs having one of these tags.',
             value_type=TextLine(),
             required=False),
        affected_by_bug=Bool(
            title=u'Search for users affected by a bug',
            description=u'If true, those device owners are looked up which '
                        u'are affected by one of the selected bugs.',
            required=False),
        subscribed_to_bug=Bool(
            title=u'Search for users who subscribed to a bug',
            description=u'If true, those device owners are looked up which '
                        u'to one of the selected bugs.',
            required=False))
    @call_with(user=REQUEST_USER)
    @operation_returns_collection_of(IPerson)
    @export_read_operation()
    def deviceDriverOwnersAffectedByBugs(
        bus, vendor_id, product_id, driver_name=None, package_name=None,
        bug_ids=None, bug_tags=None, affected_by_bug=False,
        subscribed_to_bug=False, user=None):
        """Return persons affected by given bugs and owning a given device.

        :param bus: The `HWBus` of the device.
        :param vendor_id: The vendor ID of the device.
        :param product_id: The product ID of the device.
        :param driver_name: Limit the search to devices controlled by the
            given driver.
        :param package_name: Limit the search to devices controlled by a
            driver from the given package.
        :param bug_ids: A sequence of bug IDs for which affected
            are looked up.
        :param bug_tags: A sequence of bug tags
        :param affected_by_bug: If True, those persons are looked up that
            have marked themselves as being affected by a one of the bugs
            matching the bug criteria.
        :param subscribed_to_bug: If True, those persons are looked up that
            are subscribed to a bug matching one of the bug criteria.
        :param user: The person making the query.

        bug_ids must be a non-empty sequence of bug IDs, or bug_tags
        must be a non-empty sequence of bug tags.

        The parameters bus, vendor_id, product_id must not be None, or
        driver_name must not be None.

        By default, only those persons are returned which have reported a
        bug matching the given bug conditions.

        Owners of private submissions are returned only if user is the
        owner of the private submission or if user is an admin.
        """

    @operation_parameters(
        bug_ids=List(title=u'A set of bug IDs',
             description=u'Search for devices and their owners related to '
                         u'bugs with these IDs.',
             value_type=Int(),
             required=False),
        bug_tags=List(title=u'A set of bug tags',
             description=u'Search for devices and their owners related to '
                         u'bugs having one of these tags.',
             value_type=TextLine(),
             required=False),
        affected_by_bug=Bool(
            title=u'Search for users affected by a bug',
            description=u'If true, those device owners are looked up which '
                        u'are affected by one of the selected bugs.',
            required=False),
        subscribed_to_bug=Bool(
            title=u'Search for users who subscribed to a bug',
            description=u'If true, those device owners are looked up which '
                        u'to one of the selected bugs.',
            required=False))
    @call_with(user=REQUEST_USER)
    @export_read_operation()
    def hwInfoByBugRelatedUsers(
        bug_ids=None, bug_tags=None, affected_by_bug=False,
        subscribed_to_bug=False, user=None):
        """Return a list of owners and devices related to given bugs.

        Actually returns a list of tuples where the tuple is of the form,
        (person name, bus name, vendor id, product id).`

        :param bug_ids: A sequence of bug IDs for which affected
            are looked up.
        :param bug_tags: A sequence of bug tags
        :param affected_by_bug: If True, those persons are looked up that
            have marked themselves as being affected by a one of the bugs
            matching the bug criteria.
        :param subscribed_to_bug: If True, those persons are looked up that
            are subscribed to a bug matching one of the bug criteria.
        :param user: The person making the query.
        """


@error_status(httplib.BAD_REQUEST)
class IllegalQuery(Exception):
    """Exception raised when trying to run an illegal submissions query."""


@error_status(httplib.BAD_REQUEST)
class ParameterError(Exception):
    """Exception raised when a method parameter does not match a constrint."""
