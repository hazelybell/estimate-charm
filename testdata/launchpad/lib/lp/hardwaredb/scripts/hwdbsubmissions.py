# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Parse Hardware Database submissions.

Base classes, intended to be used both for the commercial certification
data and for the community test submissions.
"""

__metaclass__ = type
__all__ = [
           'SubmissionParser',
           'process_pending_submissions',
           'ProcessingLoopForPendingSubmissions',
           'ProcessingLoopForReprocessingBadSubmissions',
          ]

import bz2
from cStringIO import StringIO
from datetime import (
    datetime,
    timedelta,
    )
from logging import getLogger
import os
import re
import sys
import xml.etree.cElementTree as etree

import pytz
from zope.component import getUtility
from zope.interface import implements
from zope.security.proxy import removeSecurityProxy

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.hardwaredb.interfaces.hwdb import (
    HWBus,
    HWSubmissionProcessingStatus,
    IHWDeviceDriverLinkSet,
    IHWDeviceSet,
    IHWDriverSet,
    IHWSubmissionDeviceSet,
    IHWSubmissionSet,
    IHWVendorIDSet,
    IHWVendorNameSet,
    )
from lp.hardwaredb.model.hwdb import HWSubmission
from lp.services.config import config
from lp.services.librarian.interfaces.client import LibrarianServerError
from lp.services.looptuner import (
    ITunableLoop,
    LoopTuner,
    )
from lp.services.propertycache import cachedproperty
from lp.services.scripts.base import disable_oops_handler
from lp.services.webapp.errorlog import (
    ErrorReportingUtility,
    ScriptRequest,
    )
from lp.services.xml import RelaxNGValidator


_relax_ng_files = {
    '1.0': 'hardware-1_0.rng', }

_time_regex = re.compile(r"""
    ^(?P<year>\d\d\d\d)-(?P<month>\d\d)-(?P<day>\d\d)
    T(?P<hour>\d\d):(?P<minute>\d\d):(?P<second>\d\d)
    (?:\.(?P<second_fraction>\d{0,6}))?
    (?P<tz>
        (?:(?P<tz_sign>[-+])(?P<tz_hour>\d\d):(?P<tz_minute>\d\d))
        | Z)?$
    """,
    re.VERBOSE)

_broken_comment_nodes_re = re.compile('(<comment>.*?</comment>)', re.DOTALL)
_missing_udev_node_data = re.compile(
    '<info command="udevadm info --export-db">(.*?)</info>', re.DOTALL)
_missing_dmi_node_data = re.compile(
    r'<info command="grep -r \. /sys/class/dmi/id/ 2&gt;/dev/null">(.*?)'
    '</info>', re.DOTALL)
_udev_node_exists = re.compile('<hardware>.*?<udev>.*?</hardware>', re.DOTALL)
_dmi_node_exists = re.compile('<hardware>.*?<dmi>.*?</hardware>', re.DOTALL)

ROOT_UDI = '/org/freedesktop/Hal/devices/computer'
UDEV_ROOT_PATH = '/devices/LNXSYSTM:00'

# These UDIs appears in some submissions more than once.
KNOWN_DUPLICATE_UDIS = set((
    '/org/freedesktop/Hal/devices/ssb__null_',
    '/org/freedesktop/Hal/devices/uinput',
    '/org/freedesktop/Hal/devices/ignored-device',
    ))

# See include/linux/pci_ids.h in the Linux kernel sources for a complete
# list of PCI class and subclass codes.
PCI_CLASS_STORAGE = 1
PCI_SUBCLASS_STORAGE_SATA = 6

PCI_CLASS_BRIDGE = 6
PCI_SUBCLASS_BRIDGE_PCI = 4
PCI_SUBCLASS_BRIDGE_CARDBUS = 7

PCI_CLASS_SERIALBUS_CONTROLLER = 12
PCI_SUBCLASS_SERIALBUS_USB = 3

WARNING_NO_HAL_KERNEL_VERSION = 1
WARNING_NO_KERNEL_PACKAGE_DATA = 2

DB_FORMAT_FOR_VENDOR_ID = {
    'pci': '0x%04x',
    'usb_device': '0x%04x',
    'scsi': '%-8s',
    'scsi_device': '%-8s',
    }

DB_FORMAT_FOR_PRODUCT_ID = {
    'pci': '0x%04x',
    'usb_device': '0x%04x',
    'scsi': '%-16s',
    'scsi_device': '%-16s',
    }

UDEV_USB_DEVICE_PROPERTIES = set(('DEVTYPE', 'PRODUCT', 'TYPE'))
UDEV_USB_PRODUCT_RE = re.compile(
    '^[0-9a-f]{1,4}/[0-9a-f]{1,4}/[0-9a-f]{1,4}$', re.I)
UDEV_USB_TYPE_RE = re.compile('^[0-9]{1,3}/[0-9]{1,3}/[0-9]{1,3}$')
SYSFS_SCSI_DEVICE_ATTRIBUTES = set(('vendor', 'model', 'type'))


class SubmissionParser(object):
    """A Parser for the submissions to the hardware database."""

    def __init__(self, logger=None, record_warnings=True):
        if logger is None:
            logger = getLogger()
        self.logger = logger
        self.doc_parser = etree.XMLParser()
        self._logged_warnings = set()

        self.validator = {}
        directory = os.path.join(
            config.root, 'lib', 'lp', 'hardwaredb', 'scripts')
        for version, relax_ng_filename in _relax_ng_files.items():
            path = os.path.join(directory, relax_ng_filename)
            self.validator[version] = RelaxNGValidator(path)
        self._setMainSectionParsers()
        self._setHardwareSectionParsers()
        self._setSoftwareSectionParsers()
        self.record_warnings = record_warnings

    def _logError(self, message, submission_key, create_oops=True):
        """Log `message` for an error in submission submission_key`."""
        msg = 'Parsing submission %s: %s' % (submission_key, message)
        if not create_oops:
            with disable_oops_handler(self.logger):
                self.logger.error(msg)
        else:
            self.logger.error(msg)

    def _logWarning(self, message, warning_id=None):
        """Log `message` for a warning in submission submission_key`."""
        if not self.record_warnings:
            return
        if warning_id is None:
            issue_warning = True
        elif warning_id not in self._logged_warnings:
            issue_warning = True
            self._logged_warnings.add(warning_id)
        else:
            issue_warning = False
        if issue_warning:
            self.logger.warning(
                'Parsing submission %s: %s' % (self.submission_key, message))

    def fixFrequentErrors(self, submission):
        """Fixes for frequent formal errors in the submissions.
        """
        # A considerable number of reports for Lucid has ESC characters
        # in comment nodes. We don't need the comment nodes at all, so
        # we can simply empty them.
        submission = _broken_comment_nodes_re.sub('<comment/>', submission)

        # Submissions from Natty don't have the nodes <dmi> and <udev>
        # as children of the <hardware> node. Fortunately, they provide
        # this data in
        #
        #    <context>
        #        <info command="grep -r . /sys/class/dmi/id/ 2&gt;/dev/null">
        #        ...
        #        </info>
        #        <info command="udevadm info --export-db">
        #        ...
        #        </info>
        #    </context>
        #
        # We can try to find the two relevant <info> nodes inside <context>
        # and move their content into the proper subnodes of <hardware>.
        if _udev_node_exists.search(submission) is None:
            mo = _missing_udev_node_data.search(submission)
            if mo is not None:
                missing_data = mo.group(1)
                missing_data = '<udev>%s</udev>\n</hardware>' % missing_data
                submission = submission.replace('</hardware>', missing_data)
        if _dmi_node_exists.search(submission) is None:
            mo = _missing_dmi_node_data.search(submission)
            if mo is not None:
                missing_data = mo.group(1)
                missing_data = '<dmi>%s</dmi>\n</hardware>' % missing_data
                submission = submission.replace('</hardware>', missing_data)
        return submission

    def _getValidatedEtree(self, submission, submission_key):
        """Create an etree doc from the XML string submission and validate it.

        :return: an `lxml.etree` instance representation of a valid
            submission or None for invalid submissions.
        """
        submission = self.fixFrequentErrors(submission)
        try:
            tree = etree.parse(StringIO(submission), parser=self.doc_parser)
        except SyntaxError as error_value:
            self._logError(error_value, submission_key)
            return None

        submission_doc = tree.getroot()
        if submission_doc.tag != 'system':
            self._logError("root node is not '<system>'", submission_key)
            return None
        version = submission_doc.attrib.get('version', None)
        if not version in self.validator.keys():
            self._logError(
                'invalid submission format version: %s' % repr(version),
                submission_key)
            return None
        self.submission_format_version = version

        validator = self.validator[version]
        if not validator.validate(submission):
            self._logError(
                'Relax NG validation failed.\n%s' % validator.error_log,
                submission_key,
                create_oops=False)
            return None
        return submission_doc

    def _getValueAttributeAsBoolean(self, node):
        """Return the value of the attribute "value" as a boolean."""
        value = node.attrib['value']
        # Paranoia check: The Relax NG validation already ensures that the
        # attribute value is either 'True' or 'False'.
        assert value in ('True', 'False'), (
            'Parsing submission %s: Boolean value for attribute "value" '
            'expected in tag <%s>' % (self.submission_key, node.tag))
        return value == 'True'

    def _getValueAttributeAsString(self, node):
        """Return the value of the attribute "value"."""
        # The Relax NG validation ensures that the attribute exists.
        return node.attrib['value']

    def _getValueAttributeAsDateTime(self, time_node):
        """Convert a "value" attribute into a datetime object."""
        time_text = time_node.get('value')

        # we cannot use time.strptime: this function accepts neither fractions
        # of a second nor a time zone given e.g. as '+02:30'.
        mo = _time_regex.search(time_text)

        # The Relax NG schema allows a leading minus sign and year numbers
        # with more than four digits, which are not "covered" by _time_regex.
        if mo is None:
            raise ValueError(
                'Timestamp with unreasonable value: %s' % time_text)

        time_parts = mo.groupdict()

        year = int(time_parts['year'])
        month = int(time_parts['month'])
        day = int(time_parts['day'])
        hour = int(time_parts['hour'])
        minute = int(time_parts['minute'])
        second = int(time_parts['second'])
        second_fraction = time_parts['second_fraction']
        if second_fraction is not None:
            milliseconds = second_fraction + '0' * (6 - len(second_fraction))
            milliseconds = int(milliseconds)
        else:
            milliseconds = 0

        # The Relax NG validator accepts leap seconds, but the datetime
        # constructor rejects them. The time values submitted by the HWDB
        # client are not necessarily very precise, hence we can round down
        # to 59.999999 seconds without losing any real precision.
        if second > 59:
            second = 59
            milliseconds = 999999

        timestamp = datetime(year, month, day, hour, minute, second,
                             milliseconds, tzinfo=pytz.timezone('utc'))

        tz_sign = time_parts['tz_sign']
        tz_hour = time_parts['tz_hour']
        tz_minute = time_parts['tz_minute']
        if tz_sign in ('-', '+'):
            delta = timedelta(hours=int(tz_hour), minutes=int(tz_minute))
            if tz_sign == '-':
                timestamp = timestamp + delta
            else:
                timestamp = timestamp - delta
        return timestamp

    def _getClientData(self, client_node):
        """Parse the <client> node in the <summary> section.

        :return: A dictionary with keys 'name', 'version', 'plugins'.
                 Name and version describe the client program that
                 produced the submission. Pugins is a list with one
                 entry per client plugin; each entry is dictionary with
                 the keys 'name' and 'version'.
        """
        result = {'name': client_node.get('name'),
                  'version': client_node.get('version')}
        plugins = result['plugins'] = []
        for node in client_node.getchildren():
            # Ensured by the Relax NG validation: The only allowed sub-tag
            # of <client> is <plugin>, which has the attributes 'name' and
            # 'version'.
            plugins.append({'name': node.get('name'),
                            'version': node.get('version')})
        return result

    _parse_summary_section = {
        'live_cd': _getValueAttributeAsBoolean,
        'system_id': _getValueAttributeAsString,
        'distribution': _getValueAttributeAsString,
        'distroseries': _getValueAttributeAsString,
        'architecture': _getValueAttributeAsString,
        'private': _getValueAttributeAsBoolean,
        'contactable': _getValueAttributeAsBoolean,
        'date_created': _getValueAttributeAsDateTime,
        'client': _getClientData,
        'kernel-release': _getValueAttributeAsString,
        }

    def _parseSummary(self, summary_node):
        """Parse the <summary> part of a submission.

        :return: A dictionary with the keys 'live_cd', 'system_id',
                 'distribution', 'distroseries', 'architecture',
                 'private', 'contactable', 'date_created', 'client'.
                 See the sample XML file tests/hardwaretest.xml for
                 detailed description of the values.
        """
        summary = {}
        # The Relax NG validation ensures that we have exactly those
        # sub-nodes that are listed in _parse_summary_section.
        for node in summary_node.getchildren():
            parser = self._parse_summary_section[node.tag]
            summary[node.tag] = parser(self, node)
        return summary

    def _getValueAndType(self, node):
        """Return (value, type) of a <property> or <value> node."""
        type_ = node.get('type')
        if type_ in ('dbus.Boolean', 'bool'):
            value = node.text.strip()
            # Pure paranoia: The Relax NG validation ensures that <property>
            # and <value> tags have only the allowed values.
            assert value in ('True', 'False'), (
                'Parsing submission %s: Invalid bool value for <property> or '
                    '<value>: %s' % (self.submission_key, repr(value)))
            return (value == 'True', type_)
        elif type_ in ('str', 'dbus.String', 'dbus.UTF8String'):
            return (node.text.strip(), type_)
        elif type_ in ('dbus.Byte', 'dbus.Int16', 'dbus.Int32', 'dbus.Int64',
                       'dbus.UInt16', 'dbus.UInt32', 'dbus.UInt64', 'int',
                       'long'):
            value = node.text.strip()
            return (int(value), type_)
        elif type_ in ('dbus.Double', 'float'):
            value = node.text.strip()
            return (float(value), type_)
        elif type_ in ('dbus.Array', 'list'):
            value = []
            for sub_node in node.getchildren():
                value.append(self._getValueAndType(sub_node))
            return (value, type_)
        elif type_ in ('dbus.Dictionary', 'dict'):
            value = {}
            for sub_node in node.getchildren():
                value[sub_node.get('name')] = self._getValueAndType(sub_node)
            return (value, type_)
        else:
            # This should not happen: The Relax NG validation ensures
            # that we have only those values for type_ that appear in
            # the if/elif expressions above.
            raise AssertionError(
                'Parsing submission %s: Unexpected <property> or <value> '
                    'type: %s' % (self.submission_key, type_))

    def _parseProperty(self, property_node):
        """Parse a <property> node.

        :return: (name, (value, type)) of a property.
        """
        return (property_node.get('name'),
                self._getValueAndType(property_node))

    def _parseProperties(self, properties_node):
        """Parse <property> sub-nodes of properties_node.

        :return: A dictionary, where each key is the name of a property;
                 the values are the tuples (value, type) of a property.
        """
        properties = {}
        for property_node in properties_node.getchildren():
            # Paranoia check: The Relax NG schema ensures that a node
            # with <property> sub-nodes has no other sub-nodes
            assert property_node.tag == 'property', (
            'Parsing submission %s: Found <%s> node, expected <property>'
                % (self.submission_key, property_node.tag))
            property_name, property_value = self._parseProperty(property_node)
            if property_name in properties.keys():
                raise ValueError(
                    '<property name="%s"> found more than once in <%s>'
                    % (property_name, properties_node.tag))
            properties[property_name] = property_value
        return properties

    def _parseDevice(self, device_node):
        """Parse a HAL <device> node.

        :return: A dictionary d with the keys 'id', 'udi', 'parent',
                 'properties'. d['id'] is an ID of the device d['udi']
                 is the HAL UDI of the device; d['properties'] is a
                 dictionary with the properties of the device (see
                 _parseProperties for details).
        """
        # The Relax NG validation ensures that the attributes "id" and
        # "udi" exist; it also ensures that "id" contains an integer.
        device_data = {'id': int(device_node.get('id')),
                       'udi': device_node.get('udi')}
        parent = device_node.get('parent', None)
        if parent is not None:
            parent = int(parent.strip())
        device_data['parent'] = parent
        device_data['properties'] = self._parseProperties(device_node)
        return device_data

    def _parseHAL(self, hal_node):
        """Parse the <hal> section of a submission.

        :return: A list, where each entry is the result of a _parseDevice
                 call.
        """
        # The Relax NG validation ensures that <hal> has the attribute
        # "version"
        hal_data = {'version': hal_node.get('version')}
        hal_data['devices'] = devices = []
        for device_node in hal_node.getchildren():
            # Pure paranoia: The Relax NG validation ensures already
            # that we have only <device> tags within <hal>
            assert device_node.tag == 'device', (
                'Parsing submission %s: Unexpected tag <%s> in <hal>'
                % (self.submission_key, device_node.tag))
            devices.append(self._parseDevice(device_node))
        return hal_data

    def _parseProcessors(self, processors_node):
        """Parse the <processors> node.

        :return: A list of dictionaries, where each dictionary d contains
                 the data of a <processor> node. The dictionary keys are
                 'id', 'name', 'properties'. d['id'] is an ID of a
                 <processor> node, d['name'] its name, and d['properties']
                 contains the properties of a processor (see
                 _parseProperties for details).
        """
        result = []
        for processor_node in processors_node.getchildren():
            # Pure paranoia: The Relax NG valiation ensures already
            # the we have only <processor> as sub-tags of <processors>.
            assert processor_node.tag == 'processor', (
                'Parsing submission %s: Unexpected tag <%s> in <processors>'
                   % (self.submission_key, processors_node.tag))
            processor = {}
            # The RelaxNG validation ensures that the attribute "id" exists
            # and that it contains an integer.
            processor['id'] = int(processor_node.get('id'))
            processor['name'] = processor_node.get('name')
            processor['properties'] = self._parseProperties(processor_node)
            result.append(processor)
        return result

    def _parseAliases(self, aliases_node):
        """Parse the <aliases> node.

        :return: A list of dictionaries, where each dictionary d has the
                 keys 'id', 'vendor', 'model'. d['id'] is the ID of a
                 HAL device; d['vendor'] is an alternative vendor name of
                 the device; d['model'] is an alternative model name.

                 See tests/hardwaretest.xml more more details.
        """
        aliases = []
        for alias_node in aliases_node.getchildren():
            # Pure paranoia: The Relax NG valiation ensures already
            # the we have only <alias> tags within <aliases>
            assert alias_node.tag == 'alias', (
                'Parsing submission %s: Unexpected tag <%s> in <aliases>'
                    % (self.submission_key, alias_node.tag))
            # The RelaxNG validation ensures that the attribute "target"
            # exists and that it contains an integer.
            alias = {'target': int(alias_node.get('target'))}
            for sub_node in alias_node.getchildren():
                # The Relax NG svalidation ensures that we have exactly
                # two subnodes: <vendor> and <model>
                alias[sub_node.tag] = sub_node.text.strip()
            aliases.append(alias)
        return aliases

    def _parseUdev(self, udev_node):
        """Parse the <udev> node.

        :return: A list of dictionaries, where each dictionary
            describes a udev device.

        The <udev> node contains the output produced by
        "udevadm info --export-db". Each entry of the dictionaries
        represents the data of the key:value pairs as they appear
        in this data. The value of d['S'] is a list of strings,
        the value s['E'] is a dictionary containing the key=value
        pairs of the "E:" lines.
        """
        # We get the plain text as produced by "udevadm info --export-db"
        # This data looks like:
        #
        # P: /devices/LNXSYSTM:00
        # E: UDEV_LOG=3
        # E: DEVPATH=/devices/LNXSYSTM:00
        # E: MODALIAS=acpi:LNXSYSTM:
        #
        # P: /devices/LNXSYSTM:00/ACPI_CPU:00
        # E: UDEV_LOG=3
        # E: DEVPATH=/devices/LNXSYSTM:00/ACPI_CPU:00
        # E: DRIVER=processor
        # E: MODALIAS=acpi:ACPI_CPU:
        #
        # Data for different devices is separated by empty lines.
        # Each line for a device consists of key:value pairs.
        # The following keys are defined:
        #
        # A: udev_device_get_num_fake_partitions()
        # E: udev_device_get_properties_list_entry()
        # L: the device link priority (udev_device_get_devlink_priority())
        # N: the device node file name (udev_device_get_devnode())
        # P: the device path (udev_device_get_devpath())
        # R: udev_device_get_ignore_remove()
        # S: udev_get_dev_path()
        # W: udev_device_get_watch_handle()
        #
        # The key P is always present; the keys A, L, N, R, W appear at
        # most once per device; the keys E and S may appear more than
        # once.
        # The values of the E records have the format "key=value"
        #
        # See also the libudev reference manual:
        # http://www.kernel.org/pub/linux/utils/kernel/hotplug/libudev/
        # and the udev file udevadm-info.c, function print_record()

        udev_data = udev_node.text.split('\n')
        devices = []
        device = None
        line_number = 0
        device_id = 0

        for line_number, line in enumerate(udev_data):
            if len(line) == 0:
                device = None
                continue
            record = line.split(':', 1)
            if len(record) != 2:
                self._logError(
                    'Line %i in <udev>: No valid key:value data: %r'
                    % (line_number, line),
                    self.submission_key)
                return None

            key, value = record
            if device is None:
                device_id += 1
                device = {
                    'E': {},
                    'S': [],
                    'id': device_id,
                    }
                devices.append(device)
            # Some attribute lines have a space character after the
            # ':', others don't have it (see udevadm-info.c).
            value = value.lstrip()

            if key == 'E':
                property_data = value.split('=', 1)
                if len(property_data) != 2:
                    self._logError(
                        'Line %i in <udev>: Property without valid key=value '
                        'data: %r' % (line_number, line),
                        self.submission_key)
                    return None
                property_key, property_value = property_data
                device['E'][property_key] = property_value
            elif key == 'S':
                device['S'].append(value)
            else:
                if key in device:
                    self._logWarning(
                        'Line %i in <udev>: Duplicate attribute key: %r'
                        % (line_number, line),
                        self.submission_key)
                device[key] = value
        return devices

    def _parseDmi(self, dmi_node):
        """Parse the <dmi> node.

        :return: A dictionary containing the key:value pairs of the DMI data.
        """
        dmi_data = {}
        dmi_text = dmi_node.text.strip().split('\n')
        for line_number, line in enumerate(dmi_text):
            record = line.split(':', 1)
            if len(record) != 2:
                self._logError(
                    'Line %i in <dmi>: No valid key:value data: %r'
                    % (line_number, line),
                    self.submission_key)
                return None
            dmi_data[record[0]] = record[1]
        return dmi_data

    def _parseSysfsAttributes(self, sysfs_node):
        """Parse the <sysfs-attributes> node.

        :return: A dictionary {path: attrs, ...} where path is the
            path is the path of a sysfs directory, and where attrs
            is a dictionary containing attribute names and values.

        A sample of the input data:

        P: /devices/LNXSYSTM:00/LNXPWRBN:00/input/input0
        A: modalias=input:b0019v0000p0001e0000-e0,1,k74,ramlsfw
        A: uniq=
        A: phys=LNXPWRBN/button/input0
        A: name=Power Button

        P: /devices/LNXSYSTM:00/device:00/PNP0A08:00/device:03/input/input8
        A: modalias=input:b0019v0000p0006e0000-e0,1,kE0,E1,E3,F0,F1
        A: uniq=
        A: phys=/video/input0
        A: name=Video Bus

        Data for different devices is separated by empty lines. The data
        for each device starts with a line 'P: /devices/LNXSYSTM...',
        specifying the sysfs path of a device, followed by zero or more
        lines of the form 'A: key=value'
        """
        sysfs_lines = sysfs_node.text.split('\n')
        sysfs_data = {}
        attributes = None

        for line_number, line in enumerate(sysfs_lines):
            if len(line) == 0:
                attributes = None
                continue
            record = line.split(': ', 1)
            if len(record) != 2:
                self._logError(
                    'Line %i in <sysfs-attributes>: No valid key:value data: '
                    '%r' % (line_number, line),
                    self.submission_key)
                return None

            key, value = record
            if key == 'P':
                if attributes is not None:
                    self._logError(
                        "Line %i in <sysfs-attributes>: duplicate 'P' line "
                        "found: %r" % (line_number, line),
                        self.submission_key)
                    return None
                attributes = {}
                sysfs_data[value] = attributes
            elif key == 'A':
                if attributes is None:
                    self._logError(
                        "Line %i in <sysfs-attributes>: Block for a device "
                        "does not start with 'P:': %r" % (line_number, line),
                        self.submission_key)
                    return None
                attribute_data = value.split('=', 1)
                if len(attribute_data) != 2:
                    self._logError(
                        'Line %i in <sysfs-attributes>: Attribute line does '
                        'not contain key=value data: %r'
                        % (line_number, line),
                        self.submission_key)
                    return None
                attributes[attribute_data[0]] = attribute_data[1]
            else:
                self._logError(
                    'Line %i in <sysfs-attributes>: Unexpected key: %r'
                    % (line_number, line),
                    self.submission_key)
                return None
        return sysfs_data

    def _setHardwareSectionParsers(self):
        self._parse_hardware_section = {
            'hal': self._parseHAL,
            'processors': self._parseProcessors,
            'aliases': self._parseAliases,
            'udev': self._parseUdev,
            'dmi': self._parseDmi,
            'sysfs-attributes': self._parseSysfsAttributes,
            }

    def _parseHardware(self, hardware_node):
        """Parse the <hardware> part of a submission.

        :return: A dictionary with the keys 'hal', 'processors', 'aliases',
                 where the values are the parsing results of _parseHAL,
                 _parseProcessors, _parseAliases.
        """
        # Submissions from checkbox for Lucid, Maverick and Natty
        # unfortunately do not contain a <sysfs-attributes> node.
        # A default value here allows us to mark these submissions.
        # See also bug 835103.
        hardware_data = {
            'sysfs-attributes': None,
            }
        for node in hardware_node.getchildren():
            parser = self._parse_hardware_section[node.tag]
            result = parser(node)
            if result is None:
                return None
            hardware_data[node.tag] = result
        return hardware_data

    def _parseLSBRelease(self, lsb_node):
        """Parse the <lsb_release> part of a submission.

        :return: A dictionary with the content of the <properta> nodes
                 within the <lsb> node. See tests/hardwaretest.xml for
                 details.
        """
        return self._parseProperties(lsb_node)

    def _parsePackages(self, packages_node):
        """Parse the <packages> part of a submission.

        :return: A dictionary with one entry per <package> sub-node.
                 The key is the package name, the value a dictionary
                 containing the content of the <property> nodes within
                 <package>. See tests/hardwaretest.xml for more details.
        """
        packages = {}
        for package_node in packages_node.getchildren():
            # Pure paranoia: The Relax NG validation ensures already
            # that we have only <package> tags within <packages>.
            assert package_node.tag == 'package', (
                'Parsing submission %s: Unexpected tag <%s> in <packages>'
                % (self.submission_key, package_node.tag))
            package_name = package_node.get('name')
            if package_name in packages.keys():
                raise ValueError(
                    '<package name="%s"> appears more than once in <packages>'
                    % package_name)
            # The RelaxNG validation ensures that the attribute "id" exists
            # and that it contains an integer.
            package_data = {'id': int(package_node.get('id'))}
            package_data['properties'] = self._parseProperties(package_node)
            packages[package_name] = package_data
        return packages

    def _parseXOrg(self, xorg_node):
        """Parse the <xorg> part of a submission.

        :return: A dictionary with the keys 'version' and 'drivers'.
                 d['version'] is the xorg version; d['drivers'] is
                 a dictionary with one entry for each <driver> sub-node,
                 where the key is the driver name, the value is a dictionary
                 containing the attributes of the <driver> node. See
                 tests/hardwaretest.xml for more details.
        """
        xorg_data = {'version': xorg_node.get('version')}
        xorg_data['drivers'] = xorg_drivers = {}
        for driver_node in xorg_node.getchildren():
            # Pure paranoia: The Relax NG validation ensures already
            # that we have only <driver> tags within <xorg>.
            assert driver_node.tag == 'driver', (
                'Parsing submission %s: Unexpected tag <%s> in <xorg>'
                    % (self.submission_key, driver_node.tag))
            driver_info = dict(driver_node.attrib)
            if 'device' in driver_info:
                # The Relax NG validation ensures that driver_info['device']
                # consists of only digits, if present.
                driver_info['device'] = int(driver_info['device'])
            driver_name = driver_info['name']
            if driver_name in xorg_drivers.keys():
                raise ValueError(
                    '<driver name="%s"> appears more than once in <xorg>'
                    % driver_name)
            xorg_drivers[driver_name] = driver_info
        return xorg_data

    _parse_software_section = {
        'lsbrelease': _parseLSBRelease,
        'packages': _parsePackages,
        'xorg': _parseXOrg}

    def _setSoftwareSectionParsers(self):
        self._parse_software_section = {
            'lsbrelease': self._parseLSBRelease,
            'packages': self._parsePackages,
            'xorg': self._parseXOrg}

    def _parseSoftware(self, software_node):
        """Parse the <software> section of a submission.

        :return: A dictionary with the keys 'lsbrelease', 'packages',
                 'xorg', containing the parsing results of the respective
                 sub-nodes. The key 'lsbrelease' exists always; 'xorg'
                 and 'packages' are optional. See _parseLSBRelease,
                 _parsePackages, _parseXOrg for more details.
        """
        software_data = {}
        for node in software_node.getchildren():
            parser = self._parse_software_section[node.tag]
            result = parser(node)
            software_data[node.tag] = result
        # The nodes <packages> and <xorg> are optional. Ensure that
        # we have dummy entries in software_data for these nodes, if
        # the nodes do not appear in a submission in order to avoid
        # KeyErrors elsewhere in this module.
        for node_name in ('packages', 'xorg'):
            if node_name not in software_data:
                software_data[node_name] = {}
        return software_data

    def _parseQuestions(self, questions_node):
        """Parse the <questions> part of a submission.

        :return: A list, where each entry is a dictionary containing
                 the parsing result of the <question> sub-nodes.

                 Content of a list entry d (see tests/hardwaretest.xml
                 for a more detailed description):
                 d['name']:
                        The name of a question. (Always present)
                 d['plugin']:
                        The name of the client plugin which is
                        "responsible" for the question. (Optional)
                 d['targets']:
                        A list, where each entry is a dicitionary
                        describing a target device for this question.
                        This list is always present, but may be empty.

                        The contents of each list entry t is:

                        t['id']:
                                The ID of a HAL <device> node of a
                                target device.
                        t['drivers']:
                                A list of driver names, possibly empty.
                 d['answer']:
                        The answer to this question. The value is a
                        dictionary a:
                        a['value']:
                                The value of the answer. (Always present)

                                For questions of type muliple_choice,
                                the value should match one of the
                                entries of the answer_choices list,

                                For questions of type measurement, the
                                value is a numerical value.
                        a['type']:
                                This is either 'multiple_choice' or
                                'measurement'. (Always present)
                        a['unit']:
                                The unit of a measurement value.
                                (Optional)
                 d['answer_choices']:
                        A list of choices from which the user can select
                        an answer. This list is always present, but should
                        be empty for questions of type measurement.
                 d['command']:
                        The command line of a test script which was
                        run for this question. (Optional)
                 d['comment']:
                        A comment the user has typed when running the
                        client. (Optional)

                 A consistency check of the content of d is done in
                 method _checkSubmissionConsistency.
        """
        questions = []
        for question_node in questions_node.getchildren():
            # Pure paranoia: The Relax NG validation ensures already
            # that we have only <driver> tags within <xorg>
            assert question_node.tag == 'question', (
                'Parsing submission %s: Unexpected tag <%s> in <questions>'
                % (self.submission_key, question_node.tag))
            question = {'name': question_node.get('name')}
            plugin = question_node.get('plugin', None)
            if plugin is not None:
                question['plugin'] = plugin
            question['targets'] = targets = []
            answer_choices = []

            for sub_node in question_node.getchildren():
                sub_tag = sub_node.tag
                if sub_tag == 'answer':
                    question['answer'] = answer = {}
                    answer['type'] = sub_node.get('type')
                    if answer['type'] == 'multiple_choice':
                        question['answer_choices'] = answer_choices
                    unit = sub_node.get('unit', None)
                    if unit is not None:
                        answer['unit'] = unit
                    answer['value'] = sub_node.text.strip()
                elif sub_tag == 'answer_choices':
                    for value_node in sub_node.getchildren():
                        answer_choices.append(
                            self._getValueAndType(value_node))
                elif sub_tag == 'target':
                    # The Relax NG schema ensures that the attribute
                    # id exists and that it is an integer
                    target = {'id': int(sub_node.get('id'))}
                    target['drivers'] = drivers = []
                    for driver_node in sub_node.getchildren():
                        drivers.append(driver_node.text.strip())
                    targets.append(target)
                elif sub_tag in('comment', 'command'):
                    data = sub_node.text
                    if data is not None:
                        question[sub_tag] = data.strip()
                else:
                    # This should not happen: The Relax NG validation
                    # ensures that we have only those tags which appear
                    # in the if/elif expressions.
                    raise AssertionError(
                        'Parsing submission %s: Unexpected node <%s> in '
                        '<question>' % (self.submission_key, sub_tag))
            questions.append(question)
        return questions

    def _parseContext(self, context_node):
        """Parse the <context> part of a submission.

        We don't do anything real right now, but simply log a warning
        that this submission contains a <context> section, so that
        we can parse it again later, once we have the SQL tables needed
        to store the data.
        """
        self._logWarning('Submission contains unprocessed <context> data.')
        return {}

    def _setMainSectionParsers(self):
        self._parse_system = {
            'summary': self._parseSummary,
            'hardware': self._parseHardware,
            'software': self._parseSoftware,
            'questions': self._parseQuestions,
            'context': self._parseContext,
            }

    def parseMainSections(self, submission_doc):
        # The RelaxNG validation ensures that submission_doc has exactly
        # four sub-nodes and that the names of the sub-nodes appear in the
        # keys of self._parse_system.
        submission_data = {}
        try:
            for node in submission_doc.getchildren():
                parser = self._parse_system[node.tag]
                result = parser(node)
                if result is None:
                    return None
                submission_data[node.tag] = result
        except ValueError as value:
            self._logError(value, self.submission_key)
            return None
        return submission_data

    def parseSubmission(self, submission, submission_key):
        """Parse the data of a HWDB submission.

        :return: A dictionary with the keys 'summary', 'hardware',
                 'software', 'questions'. See _parseSummary,
                 _parseHardware, _parseSoftware, _parseQuestions for
                 the content.
        """
        self.submission_key = submission_key
        submission_doc = self._getValidatedEtree(submission, submission_key)
        if submission_doc is None:
            return None

        return self.parseMainSections(submission_doc)

    def _findDuplicates(self, all_ids, test_ids):
        """Search for duplicate elements in test_ids.

        :return: A set of those elements in the sequence test_ids that
        are elements of the set all_ids or that appear more than once
        in test_ids.

        all_ids is updated with test_ids.
        """
        duplicates = set()
        # Note that test_ids itself may contain an ID more than once.
        for test_id in test_ids:
            if test_id in all_ids:
                duplicates.add(test_id)
            else:
                all_ids.add(test_id)
        return duplicates

    def findDuplicateIDs(self, parsed_data):
        """Return the set of duplicate IDs.

        The IDs of devices, processors and software packages should be
        unique; this method returns a list of duplicate IDs found in a
        submission.
        """
        all_ids = set()
        if 'hal' in parsed_data['hardware']:
            duplicates = self._findDuplicates(
                all_ids,
                [device['id']
                 for device in parsed_data['hardware']['hal']['devices']])
        else:
            duplicates = self._findDuplicates(
                all_ids,
                [device['P']
                 for device in parsed_data['hardware']['udev']])
        duplicates.update(self._findDuplicates(
            all_ids,
            [processor['id']
             for processor in parsed_data['hardware']['processors']]))
        duplicates.update(self._findDuplicates(
            all_ids,
            [package['id']
             for package in parsed_data['software']['packages'].values()]))
        return duplicates

    def _getIDMap(self, parsed_data):
        """Return a dictionary ID -> devices, processors and packages."""
        id_map = {}
        if 'hal' in parsed_data['hardware']:
            hal_devices = parsed_data['hardware']['hal']['devices']
            for device in hal_devices:
                id_map[device['id']] = device
        else:
            udev_devices = parsed_data['hardware']['udev']
            for device in udev_devices:
                id_map[device['P']] = device

        for processor in parsed_data['hardware']['processors']:
            id_map[processor['id']] = processor

        for package in parsed_data['software']['packages'].values():
            id_map[package['id']] = package

        return id_map

    def findInvalidIDReferences(self, parsed_data):
        """Return the set of invalid references to IDs.

        The sub-tag <target> of <question> references a device, processor
        of package node by its ID; the submission must contain a <device>,
        <processor> or <software> tag with this ID. This method returns a
        set of those IDs mentioned in <target> nodes that have no
        corresponding device or processor node.
        """
        id_device_map = self._getIDMap(parsed_data)
        known_ids = set(id_device_map.keys())
        questions = parsed_data['questions']
        target_lists = [question['targets'] for question in questions]
        all_targets = []
        for target_list in target_lists:
            all_targets.extend(target_list)
        all_target_ids = set(target['id'] for target in all_targets)
        return all_target_ids.difference(known_ids)

    def getUDIDeviceMap(self, devices):
        """Return a dictionary which maps UDIs to HAL devices.

        Also check, if a UDI is used more than once.

        Generally, a duplicate UDI indicates a bad or bogus submission,
        but we have some UDIs where the duplicate UDI is caused by a
        bug in HAL, see
        http://lists.freedesktop.org/archives/hal/2009-April/013250.html
        In these cases, we simply remove the duplicates, otherwise, a
        ValueError is raised.
        """
        udi_device_map = {}
        duplicates = []
        for index in xrange(len(devices)):
            device = devices[index]
            udi = device['udi']
            if udi in udi_device_map:
                if 'info.parent' in device['properties']:
                    parent_udi = device['properties']['info.parent'][0]
                else:
                    parent_udi = None
                if (udi in KNOWN_DUPLICATE_UDIS or
                    parent_udi in KNOWN_DUPLICATE_UDIS):
                    duplicates.append(index)
                    continue
                else:
                    raise ValueError('Duplicate UDI: %s' % device['udi'])
            else:
                udi_device_map[udi] = device
        duplicates.reverse()
        for index in duplicates:
            devices.pop(index)
        return udi_device_map

    def _getIDUDIMaps(self, devices):
        """Return two mappings describing the relation between IDs and UDIs.

        :return: two dictionaries id_to_udi and udi_to_id, where
                 id_2_udi has IDs as keys and UDI as values, and where
                 udi_to_id has UDIs as keys and IDs as values.
        """
        id_to_udi = {}
        udi_to_id = {}
        for device in devices:
            id = device['id']
            udi = device['udi']
            id_to_udi[id] = udi
            udi_to_id[udi] = id
        return id_to_udi, udi_to_id

    def getUDIChildren(self, udi_device_map):
        """Build lists of all children of a UDI.

        :return: A dictionary that maps UDIs to lists of children.

        If any info.parent property points to a non-existing existing
        device, a ValueError is raised.
        """
        # Each HAL device references its parent device (HAL attribute
        # info.parent), except for the "root node", which has no parent.
        children = {}
        known_udis = set(udi_device_map.keys())
        for device in udi_device_map.values():
            parent_property = device['properties'].get('info.parent', None)
            if parent_property is not None:
                parent = parent_property[0]
                if not parent in known_udis:
                    raise ValueError(
                        'Unknown parent UDI %s in <device id="%s">'
                        % (parent, device['id']))
                if parent in children:
                    children[parent].append(device)
                else:
                    children[parent] = [device]
            else:
                # A node without a parent is a root node. Only one root node
                # is allowed, which must have the UDI
                # "/org/freedesktop/Hal/devices/computer".
                # Other nodes without a parent UDI indicate an error, as well
                # as a non-existing root node.
                if device['udi'] != ROOT_UDI:
                    raise ValueError(
                        'root device node found with unexpected UDI: '
                        '<device id="%s" udi="%s">' % (device['id'],
                                                       device['udi']))

        if not ROOT_UDI in children:
            raise ValueError('No root device found')
        return children

    def _removeChildren(self, udi, udi_test):
        """Remove recursively all children of the device named udi."""
        if udi in udi_test:
            children = udi_test[udi]
            for child in children:
                self._removeChildren(child['udi'], udi_test)
            del udi_test[udi]

    def checkHALDevicesParentChildConsistency(self, udi_children):
        """Ensure that HAL devices are represented in exactly one tree.

        :return: A list of those UDIs that are not "connected" to the root
                 node /org/freedesktop/Hal/devices/computer

        HAL devices "know" their parent device; each device has a parent,
        except the root element. This means that it is possible to traverse
        all existing devices, beginning at the root node.

        Several inconsistencies are possible:

        (a) we may have more than one root device (i.e., one without a
            parent)
        (b) we may have no root element
        (c) circular parent/child references may exist.

        (a) and (b) are already checked in _getUDIChildren; this method
        implements (c),
        """
        # If we build a copy of udi_children and if we remove, starting at
        # the root UDI, recursively all children from this copy, we should
        # get a dictionary, where all values are empty lists. Any remaining
        # nodes must have circular parent references.

        udi_test = {}
        for udi, children in udi_children.items():
            udi_test[udi] = children[:]
        self._removeChildren(ROOT_UDI, udi_test)
        return udi_test.keys()

    def checkUdevDictsHavePathKey(self, udev_nodes):
        """Ensure that each udev dictionary has a 'P' key.

        The 'P' (path) key identifies a device.
        """
        for node in udev_nodes:
            if not 'P' in node:
                self._logError('udev node found without a "P" key',
                               self.submission_key)
                return False
        return True

    PCI_PROPERTIES = set(
        ('PCI_CLASS', 'PCI_ID', 'PCI_SUBSYS_ID', 'PCI_SLOT_NAME'))
    pci_class_re = re.compile('^[0-9a-f]{1,6}$', re.I)
    pci_id_re = re.compile('^[0-9a-f]{4}:[0-9a-f]{4}$', re.I)

    def checkUdevPciProperties(self, udev_data):
        """Validation of udev PCI devices.

        :param udev_data: A list of dicitionaries describing udev
             devices, as returned by _parseUdev()
        :return: True if all checks pass, else False.

        Each PCI device must have the properties PCI_CLASS, PCI_ID,
        PCI_SUBSYS_ID, PCI_SLOT_NAME. Non-PCI devices must not have
        them.

        The value of PCI class must be a 24 bit integer in
        hexadecimal representation.

        The values of PCI_ID and PCI_SUBSYS_ID must be two 16 bit
        integers, separated by a ':'.
        """
        for device in udev_data:
            properties = device['E']
            property_names = set(properties)
            existing_pci_properties = property_names.intersection(
                self.PCI_PROPERTIES)
            subsystem = device['E'].get('SUBSYSTEM')
            if subsystem is None:
                self._logError(
                    'udev device without SUBSYSTEM property found.',
                    self.submission_key)
                return False
            if subsystem == 'pci':
                # Check whether any of the standard pci properties were
                # missing.
                if existing_pci_properties != self.PCI_PROPERTIES:
                    missing_properties = self.PCI_PROPERTIES.difference(
                            existing_pci_properties)

                    self._logError(
                        'PCI udev device without required PCI properties: '
                            '%r %r'
                            % (missing_properties, device['P']),
                        self.submission_key)
                    return False
                # Ensure that the pci class and ids for this device are
                # formally valid.
                if self.pci_class_re.search(properties['PCI_CLASS']) is None:
                    self._logError(
                        'Invalid udev PCI class: %r %r'
                            % (properties['PCI_CLASS'], device['P']),
                        self.submission_key)
                    return False
                for pci_id in (properties['PCI_ID'],
                               properties['PCI_SUBSYS_ID']):
                    if self.pci_id_re.search(pci_id) is None:
                        self._logError(
                            'Invalid udev PCI device ID: %r %r'
                                % (pci_id, device['P']),
                            self.submission_key)
                        return False
            else:
                if len(existing_pci_properties) > 0:
                    self._logError(
                        'Non-PCI udev device with PCI properties: %r %r'
                            % (existing_pci_properties, device['P']),
                        self.submission_key)
                    return False
        return True

    def checkUdevUsbProperties(self, udev_data):
        """Validation of udev USB devices.

        USB devices must either have the three properties DEVTYPE
        (value 'usb_device' or 'usb_interface'), PRODUCT and TYPE,
        or they must have none of them.

        PRODUCT must be a tuple of three integers in hexadecimal
        representation, separates by '/'. TYPE must be a a tuple of
        three integers in decimal representation, separated by '/'.
        usb_interface nodes must additionally have a property
        INTERFACE, containing three integers in the same format as
        TYPE.
        """
        for device in udev_data:
            subsystem = device['E'].get('SUBSYSTEM')
            if subsystem != 'usb':
                continue
            properties = device['E']
            property_names = set(properties)
            existing_usb_properties = property_names.intersection(
                UDEV_USB_DEVICE_PROPERTIES)

            if len(existing_usb_properties) == 0:
                continue

            if existing_usb_properties != UDEV_USB_DEVICE_PROPERTIES:
                missing_properties = UDEV_USB_DEVICE_PROPERTIES.difference(
                    existing_usb_properties)
                self._logError(
                    'USB udev device found without required properties: %r %r'
                    % (missing_properties, device['P']),
                    self.submission_key)
                return False
            if UDEV_USB_PRODUCT_RE.search(properties['PRODUCT']) is None:
                self._logError(
                    'USB udev device found with invalid product ID: %r %r'
                    % (properties['PRODUCT'], device['P']),
                    self.submission_key)
                return False
            if UDEV_USB_TYPE_RE.search(properties['TYPE']) is None:
                self._logError(
                    'USB udev device found with invalid type data: %r %r'
                    % (properties['TYPE'], device['P']),
                    self.submission_key)
                return False

            device_type = properties['DEVTYPE']
            if device_type not in ('usb_device', 'usb_interface'):
                self._logError(
                    'USB udev device found with invalid udev type data: %r %r'
                    % (device_type, device['P']),
                    self.submission_key)
                return False
            if device_type == 'usb_interface':
                interface_type = properties.get('INTERFACE')
                if interface_type is None:
                    self._logError(
                        'USB interface udev device found without INTERFACE '
                        'property: %r'
                        % device['P'],
                        self.submission_key)
                    return False
                if UDEV_USB_TYPE_RE.search(interface_type) is None:
                    self._logError(
                        'USB Interface udev device found with invalid '
                        'INTERFACE property: %r %r'
                        % (interface_type, device['P']),
                        self.submission_key)
                    return False
        return True

    def checkUdevScsiProperties(self, udev_data, sysfs_data):
        """Validation of udev SCSI devices.

        Each udev node where SUBSYSTEM is 'scsi' should have the
        property DEVTYPE; nodes where DEVTYPE is 'scsi_device'
        should have a corresponding sysfs node, and this node should
        define the attributes 'vendor', 'model', 'type'.
        """
        # Broken submissions from Lucid, Maverick and Natty. We'll have
        # to deal with incomplete data for SCSI devices in this case if
        # we don't want to drop the entire submission, so just pretend
        # that things are fine.
        # See also bug 835103.
        if sysfs_data is None:
            return True
        for device in udev_data:
            subsystem = device['E'].get('SUBSYSTEM')
            if subsystem != 'scsi':
                continue
            properties = device['E']
            if 'DEVTYPE' not in properties:
                self._logError(
                    'SCSI udev node found without DEVTYPE property: %r'
                    % device['P'],
                    self.submission_key)
                return False
            if properties['DEVTYPE'] == 'scsi_device':
                device_path = device['P']
                if device_path not in sysfs_data:
                    self._logError(
                        'SCSI udev device node found without related '
                        'sysfs record: %r' % device_path,
                        self.submission_key)
                    return False
                sysfs_attributes = sysfs_data[device_path]
                sysfs_attribute_names = set(sysfs_attributes)
                if SYSFS_SCSI_DEVICE_ATTRIBUTES.intersection(
                    sysfs_attribute_names) != SYSFS_SCSI_DEVICE_ATTRIBUTES:
                    missing_attributes = (
                        SYSFS_SCSI_DEVICE_ATTRIBUTES.difference(
                            sysfs_attribute_names))
                    self._logError(
                        'SCSI udev device found without required sysfs '
                        'attributes: %r %r'
                        % (missing_attributes, device_path),
                        self.submission_key)
                    return False
        return True

    def checkUdevDmiData(self, dmi_data):
        """Consistency check for DMI data.

        All keys of the dictionary dmi_data should start with
        '/sys/class/dmi/id/'.
        """
        for dmi_key in dmi_data:
            if not dmi_key.startswith('/sys/class/dmi/id/'):
                self._logError(
                    'Invalid DMI key: %r' % dmi_key, self.submission_key)
                return False
        return True

    def checkConsistentUdevDeviceData(self, udev_data, sysfs_data, dmi_data):
        """Consistency checks for udev data."""
        return (
            self.checkUdevDictsHavePathKey(udev_data) and
            self.checkUdevPciProperties(udev_data) and
            self.checkUdevUsbProperties(udev_data) and
            self.checkUdevScsiProperties(udev_data, sysfs_data) and
            self.checkUdevDmiData(dmi_data))

    def checkConsistency(self, parsed_data):
        """Run consistency checks on the submitted data.

        :return: True, if the data looks consistent, otherwise False.
        :param: parsed_data: parsed submission data, as returned by
                             parseSubmission
        """
        if ('udev' in parsed_data['hardware']
            and not self.checkConsistentUdevDeviceData(
                parsed_data['hardware']['udev'],
                parsed_data['hardware']['sysfs-attributes'],
                parsed_data['hardware']['dmi'],)):
            return False
        duplicate_ids = self.findDuplicateIDs(parsed_data)
        if duplicate_ids:
            self._logError('Duplicate IDs found: %s' % duplicate_ids,
                           self.submission_key)
            return False

        invalid_id_references = self.findInvalidIDReferences(parsed_data)
        if invalid_id_references:
            self._logError(
                'Invalid ID references found: %s' % invalid_id_references,
                self.submission_key)
            return False

        if 'hal' in parsed_data['hardware']:
            try:
                udi_device_map = self.getUDIDeviceMap(
                    parsed_data['hardware']['hal']['devices'])
                udi_children = self.getUDIChildren(udi_device_map)
            except ValueError as value:
                self._logError(value, self.submission_key)
                return False

            circular = self.checkHALDevicesParentChildConsistency(
                udi_children)
            if circular:
                self._logError('Found HAL devices with circular parent/child '
                               'relationship: %s' % circular,
                               self.submission_key)
                return False

        return True

    def buildDeviceList(self, parsed_data):
        """Create a list of devices from a submission."""
        if 'hal' in parsed_data['hardware']:
            return self.buildHalDeviceList(parsed_data)
        else:
            return self.buildUdevDeviceList(parsed_data)

    def buildHalDeviceList(self, parsed_data):
        """Create a list of devices from the HAL data of a submission."""
        self.devices = {}
        for hal_data in parsed_data['hardware']['hal']['devices']:
            udi = hal_data['udi']
            self.devices[udi] = HALDevice(hal_data['id'], udi,
                                          hal_data['properties'], self)
        for device in self.devices.values():
            parent_udi = device.parent_udi
            if parent_udi is not None:
                self.devices[parent_udi].addChild(device)
        return True

    def buildUdevDeviceList(self, parsed_data):
        """Create a list of devices from the udev data of a submission."""
        self.devices = {}
        sysfs_data = parsed_data['hardware']['sysfs-attributes']
        dmi_data = parsed_data['hardware']['dmi']
        for udev_data in parsed_data['hardware']['udev']:
            device_path = udev_data['P']
            if sysfs_data is not None:
                sysfs_data_for_device = sysfs_data.get(device_path)
            else:
                # broken Lucid, Maverick and Natty submissions.
                # See also bug 835103.
                sysfs_data_for_device = None
            if device_path == UDEV_ROOT_PATH:
                device = UdevDevice(
                    self, udev_data, sysfs_data=sysfs_data_for_device,
                    dmi_data=dmi_data)
            else:
                device = UdevDevice(
                    self, udev_data, sysfs_data=sysfs_data_for_device)
            self.devices[device_path] = device

        # The parent-child relations are derived from the path names of
        # the devices. If A and B are the path names of two devices,
        # the device with path name A is an ancestor of the device with
        # path name B, iff B.startswith(A). If C is the set of the path
        # names of all ancestors of A, the element with the longest path
        # name belongs to the parent of A.
        #
        # There is one exception to this rule: The root node has the
        # the path name '/devices/LNXSYSTM:00', while the path names
        # of PCI devices start with '/devices/pci'. We'll temporarily
        # change the path name of the root device so that the rule
        # holds for all devices.
        if UDEV_ROOT_PATH not in self.devices:
            self._logError('No udev root device defined', self.submission_key)
            return False
        self.devices['/devices'] = self.devices[UDEV_ROOT_PATH]
        del self.devices[UDEV_ROOT_PATH]

        path_names = sorted(self.devices, key=len, reverse=True)
        for path_index, path_name in enumerate(path_names[:-1]):
            # Ensure that the last ancestor of each device is our
            # root node.
            if not path_name.startswith('/devices'):
                self._logError(
                    'Invalid device path name: %r' % path_name,
                    self.submission_key)
                return False
            for parent_path in path_names[path_index + 1:]:
                if path_name.startswith(parent_path):
                    self.devices[parent_path].addChild(
                        self.devices[path_name])
                    break
        self.devices[UDEV_ROOT_PATH] = self.devices['/devices']
        del self.devices['/devices']
        return True

    @cachedproperty
    def kernel_package_name(self):
        """The kernel package name for the submission."""
        if ROOT_UDI in self.devices:
            root_hal_device = self.devices[ROOT_UDI]
            kernel_version = root_hal_device.getProperty(
                'system.kernel.version')
        else:
            kernel_version = self.parsed_data['summary'].get('kernel-release')
        if kernel_version is None:
            self._logWarning(
                'Submission does not provide property system.kernel.version '
                'for /org/freedesktop/Hal/devices/computer or a summary '
                'sub-node <kernel-release>.')
            return None
        kernel_package_name = 'linux-image-' + kernel_version
        packages = self.parsed_data['software']['packages']
        # The submission is not required to provide any package data...
        if packages and kernel_package_name not in packages:
            # ...but if we have it, we want it to be consistent with
            # the HAL root node property.
            self._logWarning(
                'Inconsistent kernel version data: According to HAL the '
                'kernel is %s, but the submission does not know about a '
                'kernel package %s'
                % (kernel_version, kernel_package_name))
            return None
        return kernel_package_name

    def processSubmission(self, submission):
        """Process a submisson.

        :return: True, if the submission could be sucessfully processed,
            otherwise False.
        :param submission: An IHWSubmission instance.
        """
        raw_submission = submission.raw_submission
        # This script runs once per day and can need a few hours to run.
        # Short-lived Librarian server failures or a server restart should
        # not break this script, so let's wait for 10 minutes for a
        # response from the Librarian.
        raw_submission.open(timeout=600)
        submission_data = raw_submission.read(timeout=600)
        raw_submission.close()

        # We assume that the data has been sent bzip2-compressed,
        # but this is not checked when the data is submitted.
        expanded_data = None
        try:
            expanded_data = bz2.decompress(submission_data)
        except IOError:
            # An IOError is raised, if the data is not BZip2-compressed.
            # We assume in this case that valid uncompressed data has been
            # submitted. If this assumption is wrong, parseSubmission()
            # or checkConsistency() will complain, hence we don't check
            # anything else here.
            pass
        if expanded_data is not None:
            submission_data = expanded_data

        parsed_data = self.parseSubmission(
            submission_data, submission.submission_key)
        if parsed_data is None:
            return False
        self.parsed_data = parsed_data
        if not self.checkConsistency(parsed_data):
            return False
        if not self.buildDeviceList(parsed_data):
            return False
        self.root_device.createDBData(submission, None)
        return True

    @property
    def root_device(self):
        """The HALDevice of UdevDevice node of the root device."""
        # checkConsistency ensures that we have either a device with the
        # key ROOT_UDI or a device with the key UDEV_ROOT_PATH.
        if ROOT_UDI in self.devices:
            return self.devices[ROOT_UDI]
        else:
            return self.devices[UDEV_ROOT_PATH]


class BaseDevice:
    """A base class to represent device data from HAL and udev."""

    def __init__(self, parser):
        self.children = []
        self.parser = parser
        self.parent = None

    # Translation of the HAL info.bus/info.subsystem property and the
    # udev property SUBSYSTEM to HWBus enumerated buses.
    subsystem_hwbus = {
        'pcmcia': HWBus.PCMCIA,
        'usb_device': HWBus.USB,
        'ide': HWBus.IDE,
        'serio': HWBus.SERIAL,
        }

    def addChild(self, child):
        """Add a child device and set the child's parent."""
        assert type(child) == type(self)
        self.children.append(child)
        child.parent = self

    # Translation of subclasses of the PCI class storage to HWBus
    # enumerated buses. The Linux kernel accesses IDE and SATA disks
    # and CDROM drives via the SCSI system; we want to know the real bus
    # of the drive. See for example the file include/linux/pci_ids.h
    # in the Linux kernel sources for a list of PCI device classes and
    # subclasses. Note that the subclass 4 (RAID) is missing. While it
    # may make sense to declare a RAID storage class for PCI devices,
    # "RAID" does not tell us anything about the bus of the storage
    # devices.
    pci_storage_subclass_hwbus = {
        0: HWBus.SCSI,
        1: HWBus.IDE,
        2: HWBus.FLOPPY,
        3: HWBus.IPI,  # Intelligent Peripheral Interface.
        5: HWBus.ATA,
        6: HWBus.SATA,
        7: HWBus.SAS,
        }

    @property
    def device_id(self):
        """A unique ID for this device."""
        raise NotImplementedError

    @property
    def pci_class(self):
        """The PCI device class of the device or None for Non-PCI devices."""
        raise NotImplementedError

    @property
    def pci_subclass(self):
        """The PCI device sub-class of the device or None for Non-PCI devices.
        """
        raise NotImplementedError

    @property
    def usb_vendor_id(self):
        """The USB vendor ID of the device or None for Non-USB devices."""
        raise NotImplementedError

    @property
    def usb_product_id(self):
        """The USB product ID of the device or None for Non-USB devices."""
        raise NotImplementedError

    @property
    def scsi_vendor(self):
        """The SCSI vendor name of the device or None for Non-SCSI devices."""
        raise NotImplementedError

    @property
    def scsi_model(self):
        """The SCSI model name of the device or None for Non-SCSI devices."""
        raise NotImplementedError

    @property
    def vendor(self):
        """The vendor of this device."""
        raise NotImplementedError

    @property
    def product(self):
        """The vendor of this device."""
        raise NotImplementedError

    @property
    def vendor_id(self):
        """The vendor ID of this device."""
        raise NotImplementedError

    @property
    def product_id(self):
        """The product ID of this device."""
        raise NotImplementedError

    @property
    def vendor_id_for_db(self):
        """The vendor ID in the representation needed for the HWDB tables.

        USB and PCI IDs are represented in the database in hexadecimal,
        while the IDs provided by HAL are integers.

        The SCSI vendor name is right-padded with spaces to 8 bytes.
        """
        bus = self.raw_bus
        format = DB_FORMAT_FOR_VENDOR_ID.get(bus)
        if format is None:
            return self.vendor_id
        else:
            return format % self.vendor_id

    @property
    def product_id_for_db(self):
        """The product ID in the representation needed for the HWDB tables.

        USB and PCI IDs are represented in the database in hexadecimal,
        while the IDs provided by HAL are integers.

        The SCSI product name is right-padded with spaces to 16 bytes.
        """
        bus = self.raw_bus
        format = DB_FORMAT_FOR_PRODUCT_ID.get(bus)
        if format is None:
            return self.product_id
        else:
            return format % self.product_id

    @property
    def driver_name(self):
        """The name of the driver contolling this device. May be None."""
        raise NotImplementedError

    @property
    def scsi_controller(self):
        """Return the SCSI host controller for this device."""
        raise NotImplementedError

    def translateScsiBus(self):
        """Return the real bus of a device where raw_bus=='scsi'.

        The kernel uses the SCSI layer to access storage devices
        connected via the USB, IDE, SATA buses. See `is_real_device`
        for more details. This method determines the real bus
        of a device accessed via the kernel's SCSI subsystem.
        """
        scsi_controller = self.scsi_controller
        if scsi_controller is None:
            return None

        scsi_controller_bus = scsi_controller.raw_bus
        if scsi_controller_bus == 'pci':
            if (scsi_controller.pci_class != PCI_CLASS_STORAGE):
                # This is not a storage class PCI device? This
                # indicates a bug somewhere in HAL or in the hwdb
                # client, or a fake submission.
                device_class = scsi_controller.pci_class
                self.parser._logWarning(
                    'A (possibly fake) SCSI device %s is connected to '
                    'PCI device %s that has the PCI device class %s; '
                    'expected class 1 (storage).'
                    % (self.device_id, scsi_controller.device_id,
                       device_class))
                return None
            pci_subclass = scsi_controller.pci_subclass
            return self.pci_storage_subclass_hwbus.get(pci_subclass)
        elif scsi_controller_bus in ('usb', 'usb_interface'):
            # USB storage devices have the following HAL device hierarchy:
            # - HAL node for the USB device. info.bus == 'usb_device',
            #   device class == 0, device subclass == 0
            # - HAL node for the USB storage interface. info.bus == 'usb',
            #   interface class 8, interface subclass 6
            #   (see http://www.usb.org/developers/devclass_docs
            #   /usb_msc_overview_1.2.pdf)
            # - HAL node for the (fake) SCSI host. raw_bus is None
            # - HAL node for the (fake) SCSI device. raw_bus == 'scsi'
            # - HAL node for the mass storage device
            #
            # Physically, the storage device can be:
            # (1) a genuine USB device, like a memory stick
            # (2) a IDE/SATA hard disk, connected to a USB -> SATA/IDE
            #     bridge
            # (3) a card reader
            # There is no formal way to distinguish cases (1) and (2):
            # The device and interface classes are in both cases
            # identical; the only way to figure out, if we have a USB
            # hard disk enclosure or a USB memory stick would be to
            # look at the vendor or product names, or to look up some
            # external data sources. Of course, we can also ask the
            # submitter in the future.
            #
            # The cases (1) and (2) differ from (3) in the property
            # the property storage.removable. For (1) and (2), this
            # property is False, for (3) it is True. Since we do not
            # store at present any device characteristics in the HWDB,
            # so there is no point to distinguish between (1), (2) on
            # one side and (3) on the other side. Distinguishing
            # between (1) and (2) might be more interesting, because
            # a hard disk is clearly a separate device, but as written,
            # it is hard to distinguish between (1) and (2)
            #
            # To sum up: we cannot get any interesting and reliable
            # information about the details of USB storage device,
            # so we'll treat those devices as "black boxes".
            return None
        else:
            return HWBus.SCSI

    def translatePciBus(self):
        # Cardbus (aka PCCard, sometimes also incorrectly called
        # PCMCIA) devices are treated as PCI devices by the kernel.
        # We can detect PCCards by checking that the parent device
        # is a PCI bridge (device class 6) for the Cardbus (device
        # subclass 7).
        # XXX Abel Deuring 2005-05-14 How can we detect ExpressCards?
        # I do not have any such card at present...
        parent_class = self.parent.pci_class
        parent_subclass = self.parent.pci_subclass
        if (parent_class == PCI_CLASS_BRIDGE
            and parent_subclass == PCI_SUBCLASS_BRIDGE_CARDBUS):
            return HWBus.PCCARD
        else:
            return HWBus.PCI

    @property
    def is_root_device(self):
        """Return True is this is the root node of all devicese, else False.
        """
        raise NotImplementedError

    @property
    def raw_bus(self):
        """Return the device bus as specified by HAL or udev."""
        raise NotImplementedError

    @property
    def real_bus(self):
        """Return the bus this device connects to on the host side.

        :return: A bus as enumerated in HWBus or None, if the bus
            cannot be determined.
        """
        device_bus = self.raw_bus
        result = self.subsystem_hwbus.get(device_bus)
        if result is not None:
            return result

        if device_bus in ('scsi', 'scsi_device'):
            return self.translateScsiBus()
        elif device_bus == 'pci':
            return self.translatePciBus()
        elif self.is_root_device:
            # The computer itself. In Hardy, HAL provides no info.bus
            # for the machine itself; older versions set info.bus to
            # 'unknown', hence it is better to use the machine's
            # UDI.
            return HWBus.SYSTEM
        else:
            self.parser._logWarning(
                'Unknown bus %r for device %s' % (device_bus, self.device_id))
            return None

    @property
    def is_real_device(self):
        """True, if the HAL device correspends to a real device.

        In many cases HAL has more than one device entry for the
        same physical device. We are only interested in real, physical,
        devices but not in the fine details, how HAL represents different
        aspects of them.

        For example, the HAL device node hiearchy for a SATA disk and
        its host controller looks like this:

        HAL device node of the host controller
            udi: .../pci_8086_27c5
            HAL properties:
                info.bus: pci
                pci.device_class: 1 (storage)
                pci.device_subclass: 6 (SATA)
                info.linux.driver: ahci

        HAL device node of the "output aspect" of the host controller
            udi: .../pci_8086_27c5_scsi_host
            HAL properties:
                info.bus: n/a
                info.driver: n/a
                info.parent: .../pci_8086_27c5

        HAL device node of a hard disk.
            udi: .../pci_8086_27c5_scsi_host_scsi_device_lun0
            HAL properties:
                info.bus: scsi
                info.driver: sd
                info.parent: .../pci_8086_27c5_scsi_host

        HAL device node of the "storage aspect" of the hard disk
            udi: .../storage_serial_1ATA_Hitachi_HTS541616J9SA00_SB...
            HAL properties
                info.driver: n/a
                info.parent: .../pci_8086_27c5_scsi_host_scsi_device_lun0

        HAL device node of a disk partition:
            udi: .../volume_uuid_0ee803cf_...
            HAL properties
                info.driver: n/a
                info.parent: .../storage_serial_1ATA_Hitachi_HTS541616J...

        (optionally more nodes for more partitions)

        HAL device node of the "generic SCSI aspect" of the hard disk:
            udi: .../pci_8086_27c5_scsi_host_scsi_device_lun0_scsi_generic
                info.driver: n/a
                info.parent: .../pci_8086_27c5_scsi_host_scsi_device_lun0

        This disk is _not_ a SCSI disk, but a SATA disk. In other words,
        the SCSI details are in this case just an artifact of the Linux
        kernel, which uses its SCSI subsystem as a "central hub" to access
        IDE, SATA, USB, IEEE1394 storage devices. The only interesting
        detail for us is that the sd driver is involved in accesses to the
        disk.

        Heuristics:

        - Most real devices have the property info.bus; we consider only
          those devices to be real which have this property set.

        - As written above, the SCSI bus often appears as an artifact;
          for PCI host controllers, their properties pci.device_class
          and pci.device_subclass tell us if we have a real SCSI host
          controller: pci.device_class == 1 means a storage controller,
          pci.device_subclass == 0 means a SCSI controller. This works
          too for PCCard controllers, which use the PCI device class
          numbers too.

        - The value "usb_device" of the HAL property info.bus identifies
          USB devices, with one exception: The USB host controller, which
          itself has an info.bus property with the value "pci", has a
          sub-device with info.bus='usb_device' for its "output aspect".
          These sub-devices can be identified by the device class their
          parent and by their USB vendor/product IDs, which are 0:0.

        Several info.bus/info.subsystem values always relate to HAL nodes
        which describe only "aspects" of physical devcies which are
        represented by other HAL nodes:

          - bus is None for a number of "virtual components", like
            /org/freedesktop/Hal/devices/computer_alsa_timer or
            /org/freedesktop/Hal/devices/computer_oss_sequencer, so
            we ignore them. (The real sound devices appear with
            other UDIs in HAL.)

            XXX Abel Deuring 20080425: This ignores a few components
            like laptop batteries or the CPU, where info.bus is None.
            Since these components are not the most important ones
            for the HWDB, we'll ignore them for now. Bug 237038.

          - 'disk' is used udev submissions for a node related to the
            sd or sr driver of (real or fake) SCSI block devices.

          - info.bus == 'drm' is used by the HAL for the direct
            rendering interface of a graphics card.

          - info.bus == 'dvb' is used by HAL for the "input aspect"
            of DVB receivers

          - info.bus == 'memstick_host' is used by HAL for the "output aspect"
            of memory sticks.

          - info.bus == 'net' is used by the HAL version in
            Intrepid for the "output aspects" of network devices.

          - 'partition' is used in udev submissions for a node
            related to disk partition

          - 'scsi_disk' is used in udev submissions for a sub-node of
            the real device node.

            info.bus == 'scsi_generic' is used by the HAL version in
            Intrepid for a HAL node representing the generic
            interface of a SCSI device.

            info.bus == 'scsi_host' is used by the HAL version in
            Intrepid for real and "fake" SCSI host controllers.
            (On Hardy, these nodes have no info.bus property.)
            HAL nodes with this bus value are sub-nodes for the
            "SCSI aspect" of another HAL node which represents the
            real device.

            'scsi_target' is used in udev data for SCSI target nodes,
            the parent of a SCSI device (or LUN) node.

            'spi_transport' (SCSI Parallel Transport) is used in
            udev data for a sub-node of real SCSI devices.

            info.bus == 'sound' is used by the HAL version in
            Intrepid for "aspects" of sound devices.

            info.bus == 'ssb' is used for "aspects" of Broadcom
            Ethernet and WLAN devices, but like 'usb', they do not
            represent separate devices.

            info.bus == 'tty' is used for the "output aspect"
            of serial output devices (RS232, modems etc). It appears
            for USB and PCI devices as well as for legacy devices
            like the 8250/16450/16550 controllers.

            info.bus == 'usb' is used for end points of USB devices;
            the root node of a USB device has info.bus == 'usb_device'.

            'usb_interface' is used in udv submissions for interface
            nodes of USB devices.

            info.bus == 'video4linux' is used for the "input aspect"
            of video devices.

            'ac97' is used in submissions with udev data for a sub-node
            of sound devices.

            'hid' is used in submissions with udev data for a sub-node
            of USB input devices.

            'drm_minor', 'pci_express', 'tifm_adapter', 'gameport',
            'spi_host', 'tifm', 'wlan' are used in submissions with
            udev data for sub-nodes of PCI devices.

            'pcmcia_socket' is used in submissions with udev data for
            a sub-node of PC Card and PCMCIA bridges.

            'ieee80211'  is used in submissions with udev data for
            sub-nodes IEEE 802.11 WLAN devices.

            'host', 'link' are used in submissions with udev data for
            sub.nodes of bluetooth devices.

            'usb_host' and 'usbmon' are used in submissions with udev
            data for sub-nodes of USB controllers.

            'usb_endpoint', 'usb-serial', 'lirc' are used in
            submissions with udev data for sub-nodes of USB devices.

            'enclosure' is used in submissions with udev data for a
            sub.node of SCSI devices.

            'graphics' is used  in submissions with udev data for a
            sub-node of graphics cards.

            'hwmon' is is used  in submissions with udev data in
            many sub-nodes.

            'sas_phy', 'sas_device', 'sas_end_device', 'sas_port',
            'sas_host' is used in submissions with udev data for
            details of SAS controllers.

            'mISDN' is used  in submissions with udev data for the
            I/O aspects of ISDN adapters.

            'pvrusb2' is used  in submissions with udev data for the
            input aspect of some DVB adapters.

            'memstick' is used  in submissions with udev data for the
            I/O aspect of memory stick controllers.

            'bttv-sub' is used  in submissions with udev data for the
            I/O aspects of some TV receivers.

            'scsi_tape' is used  in submissions with udev data for
            details of SCSI tape drives.
            """
        # The root node is always a real device, but its raw_bus
        # property can have different values: None or 'Unknown' in
        # submissions with HAL data, 'acpi' for submissions with udev
        # data.
        if self.is_root_device:
            return True

        bus = self.raw_bus
        # This set of buses is only used once; it's easier to have it
        # here than to put it elsewhere and have to document its
        # location and purpose.
        if bus in (None, 'ac97', 'bttv-sub', 'disk', 'drm', 'drm_minor',
                   'dvb', 'enclosure', 'gameport', 'graphics', 'hid', 'host',
                   'hwmon', 'ieee80211', 'link', 'lirc', 'mISDN', 'memstick',
                   'memstick_host', 'net', 'partition', 'pci_express',
                   'pcmcia_socket', 'pvrusb2', 'sas_device', 'sas_end_device',
                   'sas_host', 'sas_phy', 'sas_port', 'scsi_disk',
                   'scsi_generic', 'scsi_host', 'scsi_tape', 'scsi_target',
                   'sound', 'spi_host', 'spi_transport', 'ssb', 'tifm',
                   'tifm_adapter', 'tty', 'usb', 'usb-serial', 'usb_endpoint',
                   'usb_host', 'usb_interface', 'usbmon', 'video4linux',
                   'wlan'):
            return False
        elif bus == 'usb_device':
            vendor_id = self.usb_vendor_id
            product_id = self.usb_product_id
            if vendor_id == 0 and product_id == 0:
                # double-check: The parent device should be a PCI host
                # controller, identifiable by its device class and subclass.
                # XXX Abel Deuring 2008-04-28 Bug=237039: This ignores other
                # possible bridges, like ISA->USB..
                parent = self.parent
                parent_bus = parent.raw_bus
                parent_class = parent.pci_class
                parent_subclass = parent.pci_subclass
                if (parent_bus == 'pci'
                    and parent_class == PCI_CLASS_SERIALBUS_CONTROLLER
                    and parent_subclass == PCI_SUBCLASS_SERIALBUS_USB):
                    return False
                else:
                    self.parser._logWarning(
                        'USB device found with vendor ID==0, product ID==0, '
                        'where the parent device does not look like a USB '
                        'host controller: %s' % self.device_id)
                    return False
            return True
        elif bus in ('scsi', 'scsi_device'):
            # Ensure consistency with HALDevice.real_bus
            return self.real_bus is not None
        else:
            return True

    def getRealChildren(self):
        """Return the list of real child devices of this devices.

        The list of real child devices consists of the direct child
        devices of this device where child.is_real_device == True, and
        of the (recursively collected) list of real sub-devices of
        those child devices where child.is_real_device == False.
        """
        result = []
        for sub_device in self.children:
            if sub_device.is_real_device:
                # XXX Abel Deuring 2008-05-06: IEEE1394 devices are a bit
                # nasty: The standard does not define any specification
                # for product IDs or product names, hence HAL often
                # uses the value 0 for the property ieee1394.product_id
                # and a value like "Unknown (0x00d04b)" for
                # ieee.product, where 0x00d04b is the vendor ID. I have
                # currently no idea how to find or generate something
                # that could be used as the product ID, so IEEE1394
                # devices are at present simply dropped from the list of
                # devices. Otherwise, we'd pollute the HWDB with
                # unreliable data. Bug 237044.
                if sub_device.raw_bus != 'ieee1394':
                    result.append(sub_device)
            else:
                result.extend(sub_device.getRealChildren())
        return result

    @property
    def has_reliable_data(self):
        """Can this device be stored in the HWDB?

        Devices are identifed by (bus, vendor_id, product_id).
        At present we cannot generate reliable vendor and/or product
        IDs for devices with the following values of the HAL
        property info.bus resp. info.subsystem.

        info.bus == 'backlight' is used by the HAL version in
        Intrepid for the LC display. Useful vendor and product names
        are not available.

        info.bus == 'bluetooth': HAL does not provide any vendor/product
        ID data, so we can't store these devices in HWDevice.

        info.bus == 'input' is used by the HAL version in
        Intrepid for quite different devices like keyboards, mice,
        special laptop switches and buttons, sometimes with odd
        product names like "Video Bus".

        info.bus == 'misc' and info.bus == 'unknown' are obviously
        not very useful, except for the computer itself, which has
        the bus 'unknown'.

        info.bus in ('mmc', 'mmc_host') is used for SD/MMC cards resp.
        the "output aspect" of card readers. We do not not have at
        present enough background information to properly extract a
        vendor and product ID from these cards.

        info.bus == 'platform' is used for devices like the i8042
        which controls keyboard and mouse; HAL has no vendor
        information for these devices, so there is no point to
        treat them as real devices.

        info.bus == 'pnp' is used for components like the ancient
        AT DMA controller or the keyboard. Like for the bus
        'platform', HAL does not provide any vendor data.

        info.bus == 'power_supply' is used by the HAL version in
        Intrepid for AC adapters an laptop batteries. We don't have
        at present enough information about possible problems with
        missing vendor/product information in order to store the
        data reliably in the HWDB.

        raw_bus == 'acpi' is used in udev data for the main system,
        for CPUs, power supply etc. Except for the main sytsem, none
        of them provides a vendor or product id, so we ignore them.

        raw_bus == 'video_output', 'thermal', 'vtconsole', 'bdi',
        'mem', 'ppp', 'vc', 'dmi', 'hidraw', 'hwmon', 'heci', 'rfkill',
        'i2c-adapter', 'ttm', 'ppdev', 'printer', 'cardman_4040', 'msr',
        'ieee1394_protocol', 'dahdi', 'atm', 'asus_oled', 'pktcdvd' is
        used in submissions with udev data for virtual devices.

        'pci_bus' is used in submissions with udev data for a node
        describing a PCI bus.

        'leds' is used in submissions with udev data to describe LEDs.

        XXX Abel Deuring 2008-05-06: IEEE1394 devices are a bit
        nasty: The standard does not define any specification
        for product IDs or product names, hence HAL often uses
        the value 0 for the property ieee1394.product_id and a
        value like "Unknown (0x00d04b)" for ieee.product, where
        0x00d04b is the vendor ID. I have currently no idea how
        to find or generate something that could be used as the
        product ID, so IEEE1394 devices are at present simply
        not stored in the HWDB. Otherwise, we'd pollute the HWDB
        with unreliable data. Bug #237044.

        While PCMCIA devices have a manufacturer ID, at least its
        value as provided by HAL in pcmcia.manf_id it is not very
        reliable. The HAL property pcmcia.prod_id1 is too not
        reliable. Sometimes it contains a useful vendor name like
        "O2Micro" or "ATMEL", but sometimes useless values like
        "IEEE 802.11b". See for example
        drivers/net/wireless/atmel_cs.c in the Linux kernel sources.

        Provided that a device is not excluded by the above criteria,
        ensure that we have vendor ID, product ID and product name.
        """
        bus = self.raw_bus
        if bus in ('unknown', 'acpi') and not self.is_root_device:
            # The root node is course a real device; storing data
            # about other devices with the bus "unkown" is pointless.
            return False
        if bus in ('asus_oled', 'atm', 'backlight', 'bdi', 'bluetooth',
                    'cardman_4040', 'dahdi', 'dmi', 'heci', 'hidraw', 'hwmon',
                   'i2c-adapter', 'ieee1394', 'ieee1394_protocol', 'input',
                   'leds', 'mem', 'misc', 'mmc', 'mmc_host', 'msr', 'pci_bus',
                   'pcmcia', 'pktcdvd', 'platform', 'pnp', 'power_supply',
                   'ppdev', 'ppp', 'printer', 'rfkill', 'thermal', 'ttm',
                   'vc', 'video_output', 'vtconsole'):
            return False

        # We identify devices by bus, vendor ID and product ID;
        # additionally, we need a product name. If any of these
        # are not available, we can't store information for this
        # device.
        if (self.real_bus is None or self.vendor_id is None
            or self.product_id is None or self.product is None):
            # Many IDE devices don't provide useful vendor and product
            # data. We don't want to clutter the log with warnings
            # about this problem -- there is nothing we can do to fix
            # it.
            if self.real_bus != HWBus.IDE:
                self.parser._logWarning(
                    'A %s that is supposed to be a real device does '
                    'not provide bus, vendor ID, product ID or product name: '
                    '%r %r %r %r %s'
                    % (self.__class__.__name__, self.real_bus, self.vendor_id,
                       self.product_id, self.product, self.device_id),
                    self.parser.submission_key)
            return False
        return True

    def getScsiVendorAndModelName(self):
        """Separate vendor and model name of SCSI decvices.

        SCSI devcies are identified by an 8 charcter vendor name
        and an 16 character model name. The Linux kernel use the
        the SCSI command set to access block devices connected
        via USB, IEEE1394 and ATA buses too.

        For ATA disks, the Linux kernel sets the vendor name to "ATA"
        and prepends the model name with the real vendor name, but only
        if the combined length if not larger than 16. Otherwise the
        real vendor name is omitted.

        This method provides a safe way to retrieve the  the SCSI vendor
        and model name.

        If the vendor name is 'ATA', and if the model name contains
        at least one ' ' character, the string before the first ' ' is
        returned as the vendor name, and the string after the first
        ' ' is returned as the model name.

        In all other cases, vendor and model name are returned unmodified.
        """
        vendor = self.scsi_vendor
        if vendor == 'ATA':
            # The assumption below that the vendor name does not
            # contain any spaces is not necessarily correct, but
            # it is hard to find a better heuristic to separate
            # the vendor name from the product name.
            splitted_name = self.scsi_model.split(' ', 1)
            if len(splitted_name) == 2:
                return {
                    'vendor': splitted_name[0],
                    'product': splitted_name[1],
                    }
        return {
            'vendor': vendor,
            'product': self.scsi_model,
            }

    def getDriver(self):
        """Return the HWDriver instance associated with this device.

        Create a HWDriver record, if it does not already exist.
        """
        # HAL and the HWDB client know at present only about kernel
        # drivers, so there is currently no need to search for
        # for user space printer drivers, for example.
        if self.driver_name is not None:
            db_driver_set = getUtility(IHWDriverSet)
            return db_driver_set.getOrCreate(
                self.parser.kernel_package_name, self.driver_name)
        else:
            return None

    def ensureVendorIDVendorNameExists(self):
        """Ensure that a useful HWVendorID record for self.vendor_id exists.

        A vendor ID is associated with a vendor name. For many devices
        we rely on the information from the submission to create this
        association in the HWVendorID table.

        We do _not_ use the submitted vendor name for USB, PCI and
        PCCard devices, because we can get them from independent
        sources. See l/c/l/doc/hwdb-device-tables.txt.
        """
        bus = self.real_bus
        if (self.vendor is not None and
            bus not in (HWBus.PCI, HWBus.PCCARD, HWBus.USB)):
            hw_vendor_id_set = getUtility(IHWVendorIDSet)
            hw_vendor_id = hw_vendor_id_set.getByBusAndVendorID(
                bus, self.vendor_id_for_db)
            if hw_vendor_id is None:
                hw_vendor_name_set = getUtility(IHWVendorNameSet)
                hw_vendor_name = hw_vendor_name_set.getByName(self.vendor)
                if hw_vendor_name is None:
                    hw_vendor_name = hw_vendor_name_set.create(self.vendor)
                hw_vendor_id_set.create(
                    self.real_bus, self.vendor_id_for_db, hw_vendor_name)

    def createDBData(self, submission, parent_submission_device):
        """Create HWDB records for this HAL device and its children.

        A HWDevice record for (bus, vendor ID, product ID) of this
        device and a HWDeviceDriverLink record (device, None) are
        created, if they do not already exist.

        A HWSubmissionDevice record is created for (HWDeviceDriverLink,
        submission).

        HWSubmissionDevice records and missing HWDeviceDriverLink
        records for known drivers of this device are created.

        createDBData is called recursively for all real child devices.

        This method may only be called, if self.real_device == True.
        """
        assert self.is_real_device, ('HALDevice.createDBData must be called '
                                     'for real devices only.')
        if not self.has_reliable_data:
            return
        bus = self.real_bus
        vendor_id = self.vendor_id_for_db
        product_id = self.product_id_for_db
        product_name = self.product

        self.ensureVendorIDVendorNameExists()

        db_device = getUtility(IHWDeviceSet).getOrCreate(
            bus, vendor_id, product_id, product_name)
        # Create a HWDeviceDriverLink record without an associated driver
        # for each real device. This will allow us to relate tests and
        # bugs to a device in general as well as to a specific
        # combination of a device and a driver.
        device_driver_link = getUtility(IHWDeviceDriverLinkSet).getOrCreate(
            db_device, None)
        submission_device = getUtility(IHWSubmissionDeviceSet).create(
            device_driver_link, submission, parent_submission_device,
            self.id)
        self.createDBDriverData(submission, db_device, submission_device)

    def createDBDriverData(self, submission, db_device, submission_device):
        """Create HWDB records for drivers of this device and its children.

        This method creates HWDeviceDriverLink and HWSubmissionDevice
        records for this device and its children.
        """
        driver = self.getDriver()
        if driver is not None:
            device_driver_link_set = getUtility(IHWDeviceDriverLinkSet)
            device_driver_link = device_driver_link_set.getOrCreate(
                db_device, driver)
            submission_device = getUtility(IHWSubmissionDeviceSet).create(
                device_driver_link, submission, submission_device, self.id)
        for sub_device in self.children:
            if sub_device.is_real_device:
                sub_device.createDBData(submission, submission_device)
            else:
                sub_device.createDBDriverData(submission, db_device,
                                              submission_device)


class HALDevice(BaseDevice):
    """The representation of a HAL device node."""

    def __init__(self, id, udi, properties, parser):
        """HALDevice constructor.

        :param id: The ID of the HAL device in the submission data as
            specified in <device id=...>.
        :type id: int
        :param udi: The UDI of the HAL device.
        :type udi: string
        :param properties: The HAL properties of the device.
        :type properties: dict
        :param parser: The parser processing a submission.
        :type parser: SubmissionParser
        """
        super(HALDevice, self).__init__(parser)
        self.id = id
        self.udi = udi
        self.properties = properties

    def getProperty(self, property_name):
        """Return the HAL property property_name.

        Note that there is no check of the property type.
        """
        if property_name not in self.properties:
            return None
        name, type_ = self.properties[property_name]
        return name

    @property
    def parent_udi(self):
        """The UDI of the parent device."""
        return self.getProperty('info.parent')

    @property
    def device_id(self):
        """See `BaseDevice`."""
        return self.udi

    @property
    def pci_class(self):
        """See `BaseDevice`."""
        return self.getProperty('pci.device_class')

    @property
    def pci_subclass(self):
        """The PCI device sub-class of the device or None for Non-PCI devices.
        """
        return self.getProperty('pci.device_subclass')

    @property
    def usb_vendor_id(self):
        """See `BaseDevice`."""
        return self.getProperty('usb_device.vendor_id')

    @property
    def usb_product_id(self):
        """See `BaseDevice`."""
        return self.getProperty('usb_device.product_id')

    @property
    def scsi_vendor(self):
        """See `BaseDevice`."""
        return self.getProperty('scsi.vendor')

    @property
    def scsi_model(self):
        """See `BaseDevice`."""
        return self.getProperty('scsi.model')

    @property
    def driver_name(self):
        """See `BaseDevice`."""
        return self.getProperty('info.linux.driver')

    @property
    def raw_bus(self):
        """See `BaseDevice`."""
        # Older versions of HAL stored this value in the property
        # info.bus; newer versions store it in info.subsystem.
        #
        # Note that info.bus is gone for all devices except the
        # USB bus. For USB devices, the property info.bus returns more
        # detailed data: info.subsystem has the value 'usb' for all
        # HAL nodes belonging to USB devices, while info.bus has the
        # value 'usb_device' for the root node of a USB device, and the
        # value 'usb' for sub-nodes of a USB device. We use these
        # different value to to find the root USB device node, hence
        # try to read info.bus first.
        result = self.getProperty('info.bus')
        if result is not None:
            return result
        return self.getProperty('info.subsystem')

    @property
    def is_root_device(self):
        """See `BaseDevice`."""
        return self.udi == ROOT_UDI

    def getVendorOrProduct(self, type_):
        """Return the vendor or product of this device.

        :return: The vendor or product data for this device.
        :param type_: 'vendor' or 'product'
        """
        # HAL does not store vendor data very consistently. Try to find
        # the data in several places.
        assert type_ in ('vendor', 'product'), (
            'Unexpected value of type_: %r' % type_)

        bus = self.raw_bus
        if self.udi == ROOT_UDI:
            # HAL sets info.product to "Computer", provides no property
            # info.vendor and raw_bus is "unknown", hence the logic
            # below does not work properly.
            return self.getProperty('system.hardware.' + type_)
        elif bus == 'scsi':
            return self.getScsiVendorAndModelName()[type_]
        else:
            result = self.getProperty('info.' + type_)
            if result is None:
                if bus is None:
                    return None
                else:
                    return self.getProperty('%s.%s' % (bus, type_))
            else:
                return result

    @property
    def vendor(self):
        """See `BaseDevice`."""
        return self.getVendorOrProduct('vendor')

    @property
    def product(self):
        """See `BaseDevice`."""
        return self.getVendorOrProduct('product')

    def getVendorOrProductID(self, type_):
        """Return the vendor or product ID for this device.

        :return: The vendor or product ID for this device.
        :param type_: 'vendor' or 'product'
        """
        assert type_ in ('vendor', 'product'), (
            'Unexpected value of type_: %r' % type_)
        bus = self.raw_bus
        if self.udi == ROOT_UDI:
            # HAL does not provide IDs for a system itself, we use the
            # vendor resp. product name instead.
            return self.getVendorOrProduct(type_)
        elif bus is None:
            return None
        elif bus == 'scsi' or self.udi == ROOT_UDI:
            # The SCSI specification does not distinguish between a
            # vendor/model ID and vendor/model name: the SCSI INQUIRY
            # command returns an 8 byte string as the vendor name and
            # a 16 byte string as the model name. We use these strings
            # as the vendor/product name as well as the vendor/product
            # ID.
            #
            # Similary, HAL does not provide a vendor or product ID
            # for the host system itself, so we use the vendor resp.
            # product name as the vendor/product ID for systems too.
            return self.getVendorOrProduct(type_)
        else:
            return self.getProperty('%s.%s_id' % (bus, type_))

    @property
    def vendor_id(self):
        """See `BaseDevice`."""
        return self.getVendorOrProductID('vendor')

    @property
    def product_id(self):
        """See `BaseDevice`."""
        return self.getVendorOrProductID('product')

    @property
    def scsi_controller(self):
        """See `BaseDevice`."""
        # While SCSI devices from valid submissions should have a
        # parent and a grandparent, we can't be sure for bogus or
        # broken submissions.
        if self.raw_bus != 'scsi':
            return None
        parent = self.parent
        if parent is None:
            self.parser._logWarning(
                'Found SCSI device without a parent: %s.' % self.device_id)
            return None
        grandparent = parent.parent
        if grandparent is None:
            self.parser._logWarning(
                'Found SCSI device without a grandparent: %s.'
                % self.device_id)
            return None
        return grandparent


class UdevDevice(BaseDevice):
    """The representation of a udev device node."""

    def __init__(self, parser, udev_data, sysfs_data=None, dmi_data=None):
        """HALDevice constructor.

        :param udevdata: The udev data for this device
        :param sysfs_data: sysfs data for this device.
        :param parser: The parser processing a submission.
        :type parser: SubmissionParser
        """
        super(UdevDevice, self).__init__(parser)
        self.udev = udev_data
        self.sysfs = sysfs_data
        self.dmi = dmi_data

    @property
    def device_id(self):
        """See `BaseDevice`."""
        return self.udev['P']

    @property
    def root_device_ids(self):
        """The vendor and product IDs of the root device."""
        return {
            'vendor': self.dmi.get('/sys/class/dmi/id/sys_vendor'),
            'product': self.dmi.get('/sys/class/dmi/id/product_name')
            }

    @property
    def is_pci(self):
        """True, if this is a PCI device, else False."""
        return self.udev['E'].get('SUBSYSTEM') == 'pci'

    @property
    def pci_class_info(self):
        """Parse the udev property PCI_SUBSYS_ID.

        :return: (PCI class, PCI sub-class, version) for a PCI device
            or (None, None, None) for other devices.
        """
        if self.is_pci:
            # SubmissionParser.checkConsistentUdevDeviceData() ensures
            # that PCI_CLASS is a 24 bit integer in hexadecimal
            # representation.
            # Bits 16..23 of the number are the man PCI class,
            # bits 8..15 are the sub-class, bits 0..7 are the version.
            class_info = int(self.udev['E']['PCI_CLASS'], 16)
            return (class_info >> 16, (class_info >> 8) & 0xFF,
                    class_info & 0xFF)
        else:
            return (None, None, None)

    @property
    def pci_class(self):
        """See `BaseDevice`."""
        return self.pci_class_info[0]

    @property
    def pci_subclass(self):
        """See `BaseDevice`."""
        return self.pci_class_info[1]

    @property
    def pci_ids(self):
        """The PCI vendor and product IDs.

        :return: A dictionary containing the vendor and product IDs.
            The IDs are set to None for Non-PCI devices.
        """
        if self.is_pci:
            # SubmissionParser.checkUdevPciProperties() ensures that
            # each PCI device has the property PCI_ID and that is
            # consists of two 4-digit hexadecimal numbers, separated
            # by a ':'.
            id_string = self.udev['E']['PCI_ID']
            ids = id_string.split(':')
            return {
                'vendor': int(ids[0], 16),
                'product': int(ids[1], 16),
                }
        else:
            return  {
                'vendor': None,
                'product': None,
                }

    @property
    def is_usb(self):
        """True, if this is a USB device, else False."""
        return self.udev['E'].get('SUBSYSTEM') == 'usb'

    @property
    def usb_ids(self):
        """The vendor ID, product ID, product version for USB devices.

        :return: A dictionary containing the vendor and product IDs and
            the product version for USB devices.
            The IDs are set to None for Non-USB devices.
        """
        if self.is_usb:
            # udev represents USB device IDs as strings
            # vendor_id/product_id/version, where each part is
            # a hexadecimal number.
            # SubmissionParser.checkUdevUsbProperties() ensures that
            # the string PRODUCT is in the format required below.
            product_info = self.udev['E']['PRODUCT'].split('/')
            return {
                'vendor': int(product_info[0], 16),
                'product': int(product_info[1], 16),
                'version': int(product_info[2], 16),
                }
        else:
            return {
                'vendor': None,
                'product': None,
                'version': None,
                }

    @property
    def usb_vendor_id(self):
        """See `BaseDevice`."""
        return self.usb_ids['vendor']

    @property
    def usb_product_id(self):
        """See `BaseDevice`."""
        return self.usb_ids['product']

    @property
    def is_scsi_device(self):
        """True, if this is a SCSI device, else False."""
        # udev sets the property SUBSYSTEM to "scsi" for a number of
        # different nodes: SCSI hosts, SCSI targets and SCSI devices.
        # They are distiguished by the property DEVTYPE.

        # Hack for broken submissions from Lucid, Maverick and Natty:
        # If we don't have sysfs information, pretend that no SCSI
        # related node corresponds to a real device.
        # See also bug 835103.
        if self.sysfs is None:
            return False
        properties = self.udev['E']
        return (properties.get('SUBSYSTEM') == 'scsi' and
                properties.get('DEVTYPE') == 'scsi_device')

    @property
    def scsi_vendor(self):
        """The SCSI vendor name of the device or None for Non-SCSI devices."""
        if self.is_scsi_device:
            # SubmissionParser.checkUdevScsiProperties() ensures that
            # each SCSI device has a record in self.sysfs and that
            # the attribute 'vendor' exists.
            return self.sysfs['vendor']
        else:
            return None

    @property
    def scsi_model(self):
        """The SCSI model name of the device or None for Non-SCSI devices."""
        if self.is_scsi_device:
            # SubmissionParser.checkUdevScsiProperties() ensures that
            # each SCSI device has a record in self.sysfs and that
            # the attribute 'model' exists.
            return self.sysfs['model']
        else:
            return None

    @property
    def raw_bus(self):
        """See `BaseDevice`."""
        # udev specifies the property SUBSYSTEM for most devices;
        # some devices have additionally the more specific property
        # DEVTYPE. DEVTYPE is preferable.
        # The root device has the subsystem/bus value "acpi", which
        # is a bit nonsensical.
        if self.is_root_device:
            return None
        properties = self.udev['E']
        devtype = properties.get('DEVTYPE')
        if devtype is not None:
            return devtype
        subsystem = properties.get('SUBSYSTEM')
        # A real mess: The main node of a SCSI device has
        # SUBSYSTEM = 'scsi' and DEVTYPE = 'scsi_device', while
        # a sub-node has SUBSYSTEM='scsi_device'. We don't want
        # the two to be confused. The latter node is not of any
        # interest for us, so we return None. This ensures that
        # is_real_device returns False for the sub-node.
        if subsystem != 'scsi_device':
            return subsystem
        else:
            return None

    @property
    def is_root_device(self):
        """See `BaseDevice`."""
        return self.udev['P'] == UDEV_ROOT_PATH

    def getVendorOrProduct(self, type_):
        """Return the vendor or product of this device.

        :return: The vendor or product data for this device.
        :param type_: 'vendor' or 'product'
        """
        assert type_ in ('vendor', 'product'), (
            'Unexpected value of type_: %r' % type_)

        bus = self.raw_bus
        if self.is_root_device:
            # udev does not known about any product information for
            # the root device. We use DMI data instead.
            return self.root_device_ids[type_]
        elif bus == 'scsi_device':
            return self.getScsiVendorAndModelName()[type_]
        elif bus in ('pci', 'usb_device'):
            # XXX Abel Deuring 2009-10-13, bug 450480: udev does not
            # provide human-readable vendor and product names for
            # USB and PCI devices. We should retrieve these from
            # http://www.linux-usb.org/usb.ids and
            # http://pciids.sourceforge.net/v2.2/pci.ids
            return 'Unknown'
        else:
            # We don't process yet other devices than complete systems,
            # PCI, USB devices and those devices that are represented
            # in udev as SCSI devices: real SCSI devices, and
            # IDE/ATA/SATA devices.
            return None

    @property
    def vendor(self):
        """See `BaseDevice`."""
        return self.getVendorOrProduct('vendor')

    @property
    def product(self):
        """See `BaseDevice`."""
        return self.getVendorOrProduct('product')

    def getVendorOrProductID(self, type_):
        """Return the vendor or product ID of this device.

        :return: The vendor or product ID for this device.
        :param type_: 'vendor' or 'product'
        """
        assert type_ in ('vendor', 'product'), (
            'Unexpected value of type_: %r' % type_)

        bus = self.raw_bus
        if self.is_root_device:
            # udev does not known about any product information for
            # the root device. We use DMI data instead.
            if type_ == 'vendor':
                return self.dmi.get('/sys/class/dmi/id/sys_vendor')
            else:
                return self.dmi.get('/sys/class/dmi/id/product_name')
        elif bus == 'scsi_device':
            return self.getScsiVendorAndModelName()[type_]
        elif bus == 'pci':
            return self.pci_ids[type_]
        elif bus == 'usb_device':
            return self.usb_ids[type_]
        else:
            # We don't process yet other devices than complete systems,
            # PCI, USB devices and those devices that are represented
            # in udev as SCSI devices: real SCSI devices, and
            # IDE/ATA/SATA devices.
            return None

    @property
    def vendor_id(self):
        """See `BaseDevice`."""
        return self.getVendorOrProductID('vendor')

    @property
    def product_id(self):
        """See `BaseDevice`."""
        return self.getVendorOrProductID('product')

    @property
    def driver_name(self):
        """See `BaseDevice`."""
        return self.udev['E'].get('DRIVER')

    @property
    def scsi_controller(self):
        """See `BaseDevice`."""
        if self.raw_bus != 'scsi_device':
            return None

        # While SCSI devices from valid submissions should have four
        # ancestors, we can't be sure for bogus or broken submissions.
        try:
            controller = self.parent.parent.parent
        except AttributeError:
            controller = None
        if controller is None:
            self.parser._logWarning(
                'Found a SCSI device without a sufficient number of '
                'ancestors: %s' % self.device_id)
            return None
        return controller

    @property
    def id(self):
        return self.udev['id']


class ProcessingLoopBase(object):
    """An `ITunableLoop` for processing HWDB submissions."""

    implements(ITunableLoop)

    def __init__(self, transaction, logger, max_submissions, record_warnings):
        self.transaction = transaction
        self.logger = logger
        self.max_submissions = max_submissions
        self.valid_submissions = 0
        self.invalid_submissions = 0
        self.finished = False
        self.janitor = getUtility(ILaunchpadCelebrities).janitor
        self.record_warnings = record_warnings

    def _validateSubmission(self, submission):
        submission.status = HWSubmissionProcessingStatus.PROCESSED
        self.valid_submissions += 1

    def _invalidateSubmission(self, submission):
        submission.status = HWSubmissionProcessingStatus.INVALID
        self.invalid_submissions += 1

    def isDone(self):
        """See `ITunableLoop`."""
        return self.finished

    def reportOops(self, error_explanation):
        """Create an OOPS report and the OOPS ID."""
        info = sys.exc_info()
        properties = [('error-explanation', error_explanation)]
        request = ScriptRequest(properties)
        error_utility = ErrorReportingUtility()
        error_utility.raising(info, request)
        self.logger.error('%s (%s)' % (error_explanation, request.oopsid))

    def getUnprocessedSubmissions(self, chunk_size):
        raise NotImplementedError

    def __call__(self, chunk_size):
        """Process a batch of yet unprocessed HWDB submissions."""
        # chunk_size is a float; we compare it below with an int value,
        # which can lead to unexpected results. Since it is also used as
        # a limit for an SQL query, convert it into an integer.
        chunk_size = int(chunk_size)
        submissions = self.getUnprocessedSubmissions(chunk_size)
        # Listify the submissions, since we'll have to loop over each
        # one anyway. This saves a COUNT query for getting the number of
        # submissions
        submissions = list(submissions)
        if len(submissions) < chunk_size:
            self.finished = True

        # Note that we must either change the status of each submission
        # in the loop below or we must abort the submission processing
        # entirely: getUtility(IHWSubmissionSet).getByStatus() above
        # returns the oldest submissions first, so if one submission
        # would remain in the status SUBMITTED, it would be returned
        # in the next loop run again, leading to a potentially endless
        # loop.
        for submission in submissions:
            try:
                parser = SubmissionParser(self.logger, self.record_warnings)
                success = parser.processSubmission(submission)
                if success:
                    self._validateSubmission(submission)
                else:
                    self._invalidateSubmission(submission)
            except (KeyboardInterrupt, SystemExit):
                # We should never catch these exceptions.
                raise
            except LibrarianServerError:
                # LibrarianServerError is raised when the server could
                # not be reaches for 30 minutes.
                #
                # In this case we can neither validate nor invalidate the
                # submission. Moreover, the attempt to process the next
                # submission will most likely also fail, so we should give
                # up for now.
                #
                # This exception is raised before any data for the current
                # submission is processed, hence we can commit submissions
                # processed in previous runs of this loop without causing
                # any inconsistencies.
                self.transaction.commit()

                self.reportOops(
                    'Could not reach the Librarian while processing HWDB '
                    'submission %s' % submission.submission_key)
                raise
            except Exception:
                self.transaction.abort()
                self.reportOops(
                    'Exception while processing HWDB submission %s'
                    % submission.submission_key)

                self._invalidateSubmission(submission)
                # Ensure that this submission is marked as bad, even if
                # further submissions in this batch raise an exception.
                self.transaction.commit()

            self.start = submission.id + 1
            if self.max_submissions is not None:
                if self.max_submissions <= (
                    self.valid_submissions + self.invalid_submissions):
                    self.finished = True
                    break
        self.transaction.commit()


class ProcessingLoopForPendingSubmissions(ProcessingLoopBase):

    def getUnprocessedSubmissions(self, chunk_size):
        submissions = getUtility(IHWSubmissionSet).getByStatus(
            HWSubmissionProcessingStatus.SUBMITTED,
            user=self.janitor
            )[:chunk_size]
        submissions = list(submissions)
        return submissions


class ProcessingLoopForReprocessingBadSubmissions(ProcessingLoopBase):

    def __init__(self, start, transaction, logger,
                 max_submissions, record_warnings):
        super(ProcessingLoopForReprocessingBadSubmissions, self).__init__(
            transaction, logger, max_submissions, record_warnings)
        self.start = start

    def getUnprocessedSubmissions(self, chunk_size):
        submissions = getUtility(IHWSubmissionSet).getByStatus(
            HWSubmissionProcessingStatus.INVALID, user=self.janitor)
        submissions = removeSecurityProxy(submissions).find(
            HWSubmission.id >= self.start)
        submissions = list(submissions[:chunk_size])
        return submissions


def process_pending_submissions(transaction, logger, max_submissions=None,
                                record_warnings=True):
    """Process pending submissions.

    Parse pending submissions, store extracted data in HWDB tables and
    mark them as either PROCESSED or INVALID.
    """
    loop = ProcessingLoopForPendingSubmissions(
        transaction, logger, max_submissions, record_warnings)
    # It is hard to predict how long it will take to parse a submission.
    # we don't want to last a DB transaction too long but we also
    # don't want to commit more often than necessary. The LoopTuner
    # handles this for us. The loop's run time will be approximated to
    # 2 seconds, but will never handle more than 50 submissions.
    loop_tuner = LoopTuner(
                loop, 2, minimum_chunk_size=1, maximum_chunk_size=50)
    loop_tuner.run()
    logger.info(
        'Processed %i valid and %i invalid HWDB submissions'
        % (loop.valid_submissions, loop.invalid_submissions))


def reprocess_invalid_submissions(start, transaction, logger,
                                  max_submissions=None, record_warnings=True):
    """Reprocess invalid submissions.

    Parse submissions that have been marked as invalid. A newer
    variant of the parser might be able to process them.
    """
    loop = ProcessingLoopForReprocessingBadSubmissions(
        start, transaction, logger, max_submissions, record_warnings)
    # It is hard to predict how long it will take to parse a submission.
    # we don't want to last a DB transaction too long but we also
    # don't want to commit more often than necessary. The LoopTuner
    # handles this for us. The loop's run time will be approximated to
    # 2 seconds, but will never handle more than 50 submissions.
    loop_tuner = LoopTuner(
                loop, 2, minimum_chunk_size=1, maximum_chunk_size=50)
    loop_tuner.run()
    logger.info(
        'Processed %i valid and %i invalid HWDB submissions'
        % (loop.valid_submissions, loop.invalid_submissions))
    logger.info('last processed: %i' % loop.start)
    return loop.start
