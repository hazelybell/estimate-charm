# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests of the HWDB submissions parser."""

import bz2
from copy import deepcopy
from cStringIO import StringIO
from datetime import datetime
import logging
import os

import pytz
from zope.component import getUtility
from zope.testing.loghandler import Handler

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.hardwaredb.interfaces.hwdb import (
    HWBus,
    HWSubmissionFormat,
    HWSubmissionProcessingStatus,
    IHWDeviceDriverLinkSet,
    IHWDeviceSet,
    IHWDriverSet,
    IHWSubmissionDeviceSet,
    IHWSubmissionSet,
    IHWVendorIDSet,
    IHWVendorNameSet,
    )
from lp.hardwaredb.scripts.hwdbsubmissions import (
    HALDevice,
    PCI_CLASS_BRIDGE,
    PCI_CLASS_SERIALBUS_CONTROLLER,
    PCI_CLASS_STORAGE,
    PCI_SUBCLASS_BRIDGE_CARDBUS,
    PCI_SUBCLASS_BRIDGE_PCI,
    PCI_SUBCLASS_SERIALBUS_USB,
    PCI_SUBCLASS_STORAGE_SATA,
    process_pending_submissions,
    SubmissionParser,
    UdevDevice,
    )
from lp.services.config import config
from lp.services.librarian.interfaces.client import LibrarianServerError
from lp.services.librarianserver.testing.server import fillLibrarianFile
from lp.testing import (
    TestCase,
    validate_mock_class,
    )
from lp.testing.dbuser import switch_dbuser
from lp.testing.layers import (
    BaseLayer,
    LaunchpadZopelessLayer,
    )


def evaluate_property(value):
    """Evaluate a property.

    This function does nothing in itself; passing it a property evaluates the
    property.  But it lets the code express that the evaluation is all that's
    needed, without assigning to an unused variable etc.
    """
    return value


class TestCaseHWDB(TestCase):
    """Common base class for HWDB processing tests."""

    layer = BaseLayer

    PCI_SUBCLASS_STORAGE_SCSI = 0

    UDI_COMPUTER = '/org/freedesktop/Hal/devices/computer'
    UDI_SATA_CONTROLLER = '/org/freedesktop/Hal/devices/pci_8086_27c5'
    UDI_SATA_CONTROLLER_SCSI = ('/org/freedesktop/Hal/devices/'
                               'pci_8086_27c5_scsi_host')
    UDI_SATA_DISK = ('org/freedesktop/Hal/devices/'
                     'pci_8086_27c5_scsi_host_scsi_device_lun0')
    UDI_USB_CONTROLLER_PCI_SIDE = '/org/freedesktop/Hal/devices/pci_8086_27cc'
    UDI_USB_CONTROLLER_USB_SIDE = ('/org/freedesktop/Hal/devices/'
                                   'usb_device_0_0_0000_00_1d_7')
    UDI_USB_CONTROLLER_USB_SIDE_RAW = ('/org/freedesktop/Hal/devices/'
                                   'usb_device_0_0_0000_00_1d_7_usbraw')
    UDI_USB_STORAGE = '/org/freedesktop/Hal/devices/usb_device_1307_163_07'
    UDI_USB_STORAGE_IF0 = ('/org/freedesktop/Hal/devices/'
                           'usb_device_1307_163_07_if0')
    UDI_USB_STORAGE_SCSI_HOST = ('/org/freedesktop/Hal/devices/'
                                 'usb_device_1307_163_07_if0scsi_host')
    UDI_USB_STORAGE_SCSI_DEVICE = ('/org/freedesktop/Hal/devices/'
                                   'usb_device_1307_163_07_if0'
                                   'scsi_host_scsi_device_lun0')
    UDI_USB_HUB = '/org/freedesktop/Hal/devices/usb_device_409_5a_noserial'
    UDI_USB_HUB_IF0 = ('/org/freedesktop/Hal/devices/'
                       'usb_dev_409_5a_noserial_if0')
    UDI_PCI_PCI_BRIDGE = '/org/freedesktop/Hal/devices/pci_8086_2448'
    UDI_PCI_PCCARD_BRIDGE = '/org/freedesktop/Hal/devices/pci_1217_7134'
    UDI_PCCARD_DEVICE = '/org/freedesktop/Hal/devices/pci_9004_6075'

    UDI_SCSI_CONTROLLER_PCI_SIDE = (
        '/org/freedesktop/Hal/devices/pci_9004_6075')
    UDI_SCSI_CONTROLLER_SCSI_SIDE = (
        '/org/freedesktop/Hal/devices/pci_9004_6075_scsi_host')
    UDI_SCSI_DISK = '/org/freedesktop/Hal/devices/scsi_disk'

    PCI_VENDOR_ID_INTEL = 0x8086
    PCI_VENDOR_ID_ADAPTEC = 0x9004
    PCI_PROD_ID_PCI_PCCARD_BRIDGE = 0x7134
    PCI_PROD_ID_PCCARD_DEVICE = 0x6075
    PCI_PROD_ID_USB_CONTROLLER = 0x27cc
    PCI_PROD_ID_AIC1480 = 0x6075

    USB_VENDOR_ID_NEC = 0x0409
    USB_PROD_ID_NEC_HUB = 0x005a

    USB_VENDOR_ID_USBEST = 0x1307
    USB_PROD_ID_USBBEST_MEMSTICK = 0x0163

    KERNEL_VERSION = '2.6.24-19-generic'
    KERNEL_PACKAGE = 'linux-image-' + KERNEL_VERSION

    def setUp(self):
        """Setup the test environment."""
        super(TestCaseHWDB, self).setUp()
        self.log = logging.getLogger('test_hwdb_submission_parser')
        self.log.setLevel(logging.INFO)
        self.handler = Handler(self)
        self.handler.add(self.log.name)

    def assertWarningMessage(self, submission_key, log_message):
        """Search for message in the log entries for submission_key.

        :raise: AssertionError if no log message exists that starts with
            "Parsing submission <submission_key>:" and that contains
            the text passed as the parameter message.
        """
        expected_message = 'Parsing submission %s: %s' % (
            submission_key, log_message)

        for record in self.handler.records:
            if record.levelno != logging.WARNING:
                continue
            candidate = record.getMessage()
            if candidate == expected_message:
                return
        raise AssertionError('No log message found: %s' % expected_message)

    def assertErrorMessage(self, submission_key, log_message):
        """Search for log_message in the log entries for submission_key.

        :raise: AssertionError if no log message exists that starts with
            "Parsing submission <submission_key>:" and that contains
            the text passed as the parameter message.
        """
        expected_message = 'Parsing submission %s: %s' % (
            submission_key, log_message)

        for record in self.handler.records:
            if record.levelno != logging.ERROR:
                continue
            candidate = record.getMessage()
            if candidate == expected_message:
                return
        raise AssertionError('No log message found: %s' % expected_message)


class TestHWDBSubmissionProcessing(TestCaseHWDB):
    """Tests for processing of HWDB submissions."""

    def test_buildDeviceList(self):
        """Test of SubmissionParser.buildDeviceList()."""
        class MockSubmissionParser(SubmissionParser):
            """A SubmissionParser variant for testing."""

            def __init__(self, hal_result, udev_result):
                super(MockSubmissionParser, self).__init__()
                self.hal_result = hal_result
                self.udev_result = udev_result

            def buildHalDeviceList(self, parsed_data):
                """See `SubmissionParser`."""
                return self.hal_result

            def buildUdevDeviceList(self, parsed_data):
                """See `SubmissionParser`."""
                return self.udev_result

        parsed_data_hal = {
            'hardware': {'hal': None}
            }

        parser = MockSubmissionParser(True, True)
        self.assertTrue(parser.buildDeviceList(parsed_data_hal))

        parser = MockSubmissionParser(False, True)
        self.assertFalse(parser.buildDeviceList(parsed_data_hal))

        parsed_data_udev = {
            'hardware': {'udev': None}
            }
        parser = MockSubmissionParser(True, True)
        self.assertTrue(parser.buildDeviceList(parsed_data_udev))

        parser = MockSubmissionParser(True, False)
        self.assertFalse(parser.buildDeviceList(parsed_data_udev))

    def test_buildHalDeviceList(self):
        """Test the creation of list HALDevice instances for a submission."""
        devices = [
            {
                'id': 1,
                'udi': self.UDI_COMPUTER,
                'properties': {},
                },
            {
                'id': 2,
                'udi': self.UDI_SATA_CONTROLLER,
                'properties': {
                    'info.parent': (self.UDI_COMPUTER, 'str')
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }
        parser = SubmissionParser(self.log)
        parser.buildHalDeviceList(parsed_data)
        self.assertEqual(len(parser.devices), len(devices),
                         'Numbers of devices in parser.devices and in '
                         'sample data are different')
        root_device = parser.devices[self.UDI_COMPUTER]
        self.assertEqual(root_device.id, 1,
                         'Unexpected value of root device ID.')
        self.assertEqual(root_device.udi, self.UDI_COMPUTER,
                         'Unexpected value of root device UDI.')
        self.assertEqual(root_device.properties,
                         devices[0]['properties'],
                         'Unexpected properties of root device.')
        child_device = parser.devices[self.UDI_SATA_CONTROLLER]
        self.assertEqual(child_device.id, 2,
                         'Unexpected value of child device ID.')
        self.assertEqual(child_device.udi, self.UDI_SATA_CONTROLLER,
                         'Unexpected value of child device UDI.')
        self.assertEqual(child_device.properties,
                         devices[1]['properties'],
                         'Unexpected properties of child device.')

        parent = parser.devices[self.UDI_COMPUTER]
        child = parser.devices[self.UDI_SATA_CONTROLLER]
        self.assertEqual(parent.children, [child],
                         'Child missing in parent.children.')
        self.assertEqual(child.parent, parent,
                         'Invalid value of child.parent.')

    def makeUdevDeviceParsedData(self, paths, sysfs_data=None):
        """Build test data that can be passed to buildUdevDevice()."""
        def makeUdevDevice(path):
            """Make a trivial UdevInstance with the given device path."""
            return {
                'P': path,
                'E': {}
                }
        udev_device_data = [makeUdevDevice(path) for path in paths]
        if sysfs_data is None:
            sysfs_data = {}
        parsed_data = {
            'hardware': {
                'udev': udev_device_data,
                'sysfs-attributes': sysfs_data,
                'dmi': {'/sys/class/dmi/id/sys_vendor': 'FUJITSU SIEMENS'},
                }
            }
        return parsed_data

    def test_buildUdevDeviceList(self):
        """Test the creation of UdevDevice instances for a submission."""
        root_device_path = '/devices/LNXSYSTM:00'
        pci_pci_bridge_path = '/devices/pci0000:00/0000:00:1c.0'
        pci_ethernet_controller_path = (
            '/devices/pci0000:00/0000:00:1c.0/0000:02:00.0')
        pci_usb_controller_path = '/devices/pci0000:00/0000:00:1d.7'
        pci_usb_controller_usb_hub_path = (
            '/devices/pci0000:00/0000:00:1d.7/usb1')
        usb_storage_device_path = '/devices/pci0000:00/0000:00:1d.7/usb1/1-1'
        udev_paths = (
            root_device_path, pci_pci_bridge_path,
            pci_ethernet_controller_path, pci_usb_controller_path,
            pci_usb_controller_usb_hub_path, usb_storage_device_path,
            )

        parsed_data = self.makeUdevDeviceParsedData(udev_paths)
        parser = SubmissionParser()
        self.assertTrue(parser.buildUdevDeviceList(parsed_data))

        self.assertEqual(len(udev_paths), len(parser.devices))
        for path in udev_paths:
            self.assertEqual(path, parser.devices[path].device_id)

        devices = parser.devices

        root_device = parser.devices[root_device_path]
        expected_children = set(
            (devices[pci_pci_bridge_path], devices[pci_usb_controller_path]))
        self.assertEqual(expected_children, set(root_device.children))

        pci_pci_bridge = devices[pci_pci_bridge_path]
        self.assertEqual(
            [devices[pci_ethernet_controller_path]], pci_pci_bridge.children)

        usb_controller = devices[pci_usb_controller_path]
        usb_hub = devices[pci_usb_controller_usb_hub_path]
        self.assertEqual([usb_hub], usb_controller.children)

        usb_storage = devices[usb_storage_device_path]
        self.assertEqual([usb_storage], usb_hub.children)

    def test_buildUdevDeviceList_root_node_has_dmi_data(self):
        """The root node of a udev submissions has DMI data."""
        root_device_path = '/devices/LNXSYSTM:00'
        pci_pci_bridge_path = '/devices/pci0000:00/0000:00:1c.0'
        udev_paths = (root_device_path, pci_pci_bridge_path)

        parsed_data = self.makeUdevDeviceParsedData(udev_paths)
        parser = SubmissionParser()
        parser.buildUdevDeviceList(parsed_data)

        self.assertEqual(
            {'/sys/class/dmi/id/sys_vendor': 'FUJITSU SIEMENS'},
            parser.devices[root_device_path].dmi)

        self.assertIs(None, parser.devices[pci_pci_bridge_path].dmi)

    def test_buildUdevDeviceList_sysfs_data(self):
        """Optional sysfs data is passed to UdevDevice instances."""
        root_device_path = '/devices/LNXSYSTM:00'
        pci_pci_bridge_path = '/devices/pci0000:00/0000:00:1c.0'
        pci_ethernet_controller_path = (
            '/devices/pci0000:00/0000:00:1c.0/0000:02:00.0')

        udev_paths = (
            root_device_path, pci_pci_bridge_path,
            pci_ethernet_controller_path)

        sysfs_data = {
            pci_pci_bridge_path: 'sysfs-data',
            }

        parsed_data = self.makeUdevDeviceParsedData(udev_paths, sysfs_data)
        parser = SubmissionParser()
        parser.buildUdevDeviceList(parsed_data)

        self.assertEqual(
            'sysfs-data', parser.devices[pci_pci_bridge_path].sysfs)

        self.assertIs(
            None, parser.devices[pci_ethernet_controller_path].sysfs)

    def test_buildUdevDeviceList_no_sysfs_data(self):
        """Sysfs data is not required (maverick and natty submissions)."""
        root_device_path = '/devices/LNXSYSTM:00'
        pci_pci_bridge_path = '/devices/pci0000:00/0000:00:1c.0'
        pci_ethernet_controller_path = (
            '/devices/pci0000:00/0000:00:1c.0/0000:02:00.0')

        udev_paths = (
            root_device_path, pci_pci_bridge_path,
            pci_ethernet_controller_path)

        sysfs_data = None

        parsed_data = self.makeUdevDeviceParsedData(udev_paths, sysfs_data)
        parser = SubmissionParser()
        parser.buildUdevDeviceList(parsed_data)

        self.assertIs(
            None, parser.devices[pci_pci_bridge_path].sysfs)

        self.assertIs(
            None, parser.devices[pci_ethernet_controller_path].sysfs)

    def test_buildUdevDeviceList_invalid_device_path(self):
        """Test the creation of UdevDevice instances for a submission.

        All device paths must start with '/devices'. Any other
        device path makes the submission invalid.
        """
        root_device_path = '/devices/LNXSYSTM:00'
        bad_device_path = '/nonsense'
        udev_paths = (root_device_path, bad_device_path)

        parsed_data = self.makeUdevDeviceParsedData(udev_paths)
        parser = SubmissionParser(self.log)
        parser.submission_key = 'udev device with invalid path'
        self.assertFalse(parser.buildUdevDeviceList(parsed_data))
        self.assertErrorMessage(
            parser.submission_key, "Invalid device path name: '/nonsense'")

    def test_buildUdevDeviceList_missing_root_device(self):
        """Test the creation of UdevDevice instances for a submission.

        Each submission must contain a udev node for the root device.
        """
        pci_pci_bridge_path = '/devices/pci0000:00/0000:00:1c.0'
        udev_paths = (pci_pci_bridge_path, )

        parsed_data = self.makeUdevDeviceParsedData(udev_paths)
        parser = SubmissionParser(self.log)
        parser.submission_key = 'no udev root device'
        self.assertFalse(parser.buildUdevDeviceList(parsed_data))
        self.assertErrorMessage(
            parser.submission_key, "No udev root device defined")

    def test_kernel_package_name_hal_data(self):
        """Test of SubmissionParser.kernel_package_name.

        Regular case.
        """
        parser = SubmissionParser(self.log)
        devices = [
            {
                'id': 1,
                'udi': self.UDI_COMPUTER,
                'properties': {
                    'system.kernel.version': (self.KERNEL_VERSION, 'str'),
                    },
                },
            ]
        parser.parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            'software': {
                'packages': {
                    self.KERNEL_PACKAGE: {},
                    },
                },
            }
        parser.buildDeviceList(parser.parsed_data)
        kernel_package = parser.kernel_package_name
        self.assertEqual(
            self.KERNEL_PACKAGE, kernel_package,
            'Unexpected value of SubmissionParser.kernel_package_name. '
            'Expected linux-image-2.6.24-19-generic, got %r' % kernel_package)

        self.assertEqual(
            0, len(self.handler.records),
            'One or more warning messages were logged by '
            'SubmissionParser.kernel_package_name, where zero was expected.')

    def test_kernel_package_hal_data_name_inconsistent(self):
        """Test of SubmissionParser.kernel_package_name.

        Test a name inconsistency.
        """
        parser = SubmissionParser(self.log)
        devices = [
            {
                'id': 1,
                'udi': self.UDI_COMPUTER,
                'properties': {
                    'system.kernel.version': (self.KERNEL_VERSION, 'str'),
                    },
                },
            ]
        parser.parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            'software': {
                'packages': {
                    'linux-image-from-obscure-external-source': {},
                    },
                },
            }
        parser.submission_key = 'Test of inconsistent kernel package name'
        parser.buildDeviceList(parser.parsed_data)
        kernel_package = parser.kernel_package_name
        self.assertIs(None, kernel_package)
        self.assertWarningMessage(
            parser.submission_key,
            'Inconsistent kernel version data: According to HAL the '
            'kernel is 2.6.24-19-generic, but the submission does not '
            'know about a kernel package linux-image-2.6.24-19-generic')
        # The warning appears only once per submission, even if the
        # property kernel_package_name is accessed more than once.
        num_warnings = len(self.handler.records)
        evaluate_property(parser.kernel_package_name)
        self.assertEqual(
            num_warnings, len(self.handler.records),
            'Warning for missing HAL property system.kernel.version '
            'repeated.')

    def test_kernel_package_name_hal_data_no_kernel_version_in_hal_data(self):
        """Test of SubmissionParser.kernel_package_name.

        Test without HAL property system.kernel.version.
        """
        parser = SubmissionParser(self.log)
        devices = [
            {
                'id': 1,
                'udi': self.UDI_COMPUTER,
                'properties': {},
                },
            ]
        parser.parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            'software': {
                'packages': {
                    'linux-image-from-obscure-external-source': {},
                    },
                },
            }
        parser.submission_key = 'Test: missing property system.kernel.version'
        parser.buildDeviceList(parser.parsed_data)
        self.assertIs(None, parser.kernel_package_name)
        self.assertWarningMessage(
            parser.submission_key,
            'Submission does not provide property system.kernel.version '
            'for /org/freedesktop/Hal/devices/computer or a summary '
            'sub-node <kernel-release>.')
        # The warning appears only once per submission, even if the
        # property kernel_package_name is accessed more than once.
        num_warnings = len(self.handler.records)
        evaluate_property(parser.kernel_package_name)
        self.assertEqual(
            num_warnings, len(self.handler.records),
            'Warning for missing HAL property system.kernel.version '
            'repeated.')

    def test_kernel_package_name_hal_data_no_package_data(self):
        """Test of SubmissionParser.kernel_package_name.

        Test without any package data. In this case,
        SubmissionParser.kernel_package_name is the value of the property
        system.kernel.version if the root HAL device. No further checks
        are done.
        """
        parser = SubmissionParser(self.log)
        devices = [
            {
                'id': 1,
                'udi': self.UDI_COMPUTER,
                'properties': {
                    'system.kernel.version': (self.KERNEL_VERSION, 'str'),
                    },
                },
            ]
        parser.parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            'software': {
                'packages': {},
                },
            }
        parser.submission_key = 'Test: missing property system.kernel.version'
        parser.buildDeviceList(parser.parsed_data)
        kernel_package = parser.kernel_package_name
        self.assertEqual(
            self.KERNEL_PACKAGE, kernel_package,
            'Unexpected result of SubmissionParser.getKernelPackageName, '
            'test without any package data. Expected None, got %r'
            % kernel_package)

    def test_kernel_package_name_udev_data(self):
        """Test of SubmissionParser.kernel_package_name for udev data.

        Variant for udev data, regular case.
        """
        parser = SubmissionParser(self.log)
        parser.parsed_data = {
            'hardware': {
                'udev': [
                    {'P': '/devices/LNXSYSTM:00'}
                    ],
                'sysfs-attributes': {},
                'dmi': {},
                },
            'software': {
                'packages': {
                    self.KERNEL_PACKAGE: {},
                    },
                },
            'summary': {
                'kernel-release': self.KERNEL_VERSION,
                },
            }
        parser.buildDeviceList(parser.parsed_data)
        kernel_package = parser.kernel_package_name
        self.assertEqual(
            self.KERNEL_PACKAGE, kernel_package,
            'Unexpected value of SubmissionParser.kernel_package_name. '
            'Expected linux-image-2.6.24-19-generic, got %r' % kernel_package)

        self.assertEqual(
            0, len(self.handler.records),
            'One or more warning messages were logged by '
            'SubmissionParser.kernel_package_name, where zero was expected.')

    def test_kernel_package_udev_data_name_inconsistent(self):
        """Test of SubmissionParser.kernel_package_name.

        Variant for udev data, name inconsistency.
        """
        parser = SubmissionParser(self.log)
        parser.parsed_data = {
            'hardware': {
                'udev': [
                    {'P': '/devices/LNXSYSTM:00'}
                    ],
                'sysfs-attributes': {},
                'dmi': {},
                },
            'software': {
                'packages': {
                    'linux-image-from-obscure-external-source': {},
                    },
                },
            'summary': {
                'kernel-release': self.KERNEL_VERSION,
                },
            }
        parser.submission_key = 'Test of inconsistent kernel package name'
        parser.buildDeviceList(parser.parsed_data)
        kernel_package = parser.kernel_package_name
        self.assertIs(None, kernel_package)
        self.assertWarningMessage(
            parser.submission_key,
            'Inconsistent kernel version data: According to HAL the '
            'kernel is 2.6.24-19-generic, but the submission does not '
            'know about a kernel package linux-image-2.6.24-19-generic')
        # The warning appears only once per submission, even if the
        # property kernel_package_name is accessed more than once.
        num_warnings = len(self.handler.records)
        evaluate_property(parser.kernel_package_name)
        self.assertEqual(
            num_warnings, len(self.handler.records),
            'Warning for missing HAL property system.kernel.version '
            'repeated.')

    def test_kernel_package_name_udev_data_no_kernel_version_in_summary(self):
        """Test of SubmissionParser.kernel_package_name.

        Test without the summary sub-node <kernel-release>.
        """
        parser = SubmissionParser(self.log)
        parser.parsed_data = {
            'hardware': {
                'udev': [
                    {'P': '/devices/LNXSYSTM:00'}
                    ],
                'sysfs-attributes': {},
                'dmi': {},
                },
            'software': {
                'packages': {
                    self.KERNEL_PACKAGE: {},
                    },
                },
            'summary': {},
            }
        parser.submission_key = 'Test: missing property system.kernel.version'
        parser.buildDeviceList(parser.parsed_data)
        self.assertIs(None, parser.kernel_package_name)
        self.assertWarningMessage(
            parser.submission_key,
            'Submission does not provide property system.kernel.version '
            'for /org/freedesktop/Hal/devices/computer or a summary '
            'sub-node <kernel-release>.')
        # The warning appears only once per submission, even if the
        # property kernel_package_name is accessed more than once.
        num_warnings = len(self.handler.records)
        evaluate_property(parser.kernel_package_name)
        self.assertEqual(
            num_warnings, len(self.handler.records),
            'Warning for missing HAL property system.kernel.version '
            'repeated.')

    def test_kernel_package_name_udev_data_no_package_data(self):
        """Test of SubmissionParser.kernel_package_name.

        Variant for udev data, test without any package data. In this case,
        SubmissionParser.kernel_package_name is the value of the property
        system.kernel.version if the root HAL device. No further checks
        are done.
        """
        parser = SubmissionParser(self.log)
        parser.parsed_data = {
            'hardware': {
                'udev': [
                    {'P': '/devices/LNXSYSTM:00'},
                    ],
                'sysfs-attributes': {},
                'dmi': {},
                },
            'software': {
                'packages': {},
                },
            'summary': {
                'kernel-release': self.KERNEL_VERSION,
                },
            }
        parser.submission_key = 'Test: missing property system.kernel.version'
        parser.buildDeviceList(parser.parsed_data)
        kernel_package = parser.kernel_package_name
        self.assertEqual(
            self.KERNEL_PACKAGE, kernel_package,
            'Unexpected result of SubmissionParser.getKernelPackageName, '
            'test without any package data. Expected None, got %r'
            % kernel_package)

    def testHALDeviceConstructor(self):
        """Test of the HALDevice constructor."""
        properties = {
            'info.bus': ('scsi', 'str'),
            }
        parser = SubmissionParser(self.log)
        device = HALDevice(1, '/some/udi/path', properties, parser)

        self.assertEqual(device.id, 1, 'Unexpected device ID')
        self.assertEqual(device.udi, '/some/udi/path',
                         'Unexpected device UDI.')
        self.assertEqual(device.properties, properties,
                         'Unexpected device properties.')
        self.assertEqual(device.parser, parser,
                         'Unexpected device parser.')

    def testHALDeviceGetProperty(self):
        """Test of HALDevice.getProperty."""
        properties = {
            'info.bus': ('scsi', 'str'),
            }
        parser = SubmissionParser(self.log)
        device = HALDevice(1, '/some/udi/path', properties, parser)

        # HALDevice.getProperty returns the value of a HAL property.
        # Note that the property type is _not_ returned
        self.assertEqual(device.getProperty('info.bus'), 'scsi',
            'Unexpected result of calling HALDevice.getProperty.')
        # If a property of the given name does not exist, None is returned.
        self.assertEqual(device.getProperty('does-not-exist'), None,
            'Unexpected result of calling HALDevice.getProperty for a '
            'non-existing property.')

    def testHALDeviceParentUDI(self):
        """Test of HALDevice.parent_udi."""
        properties = {
            'info.bus': ('scsi', 'str'),
            'info.parent': ('/another/udi', 'str'),
            }
        parser = SubmissionParser(self.log)
        device = HALDevice(1, '/some/udi/path', properties, parser)
        self.assertEqual(device.parent_udi, '/another/udi',
                         'Unexpected value of HALDevice.parent_udi.')

        properties = {
            'info.bus': ('scsi', 'str'),
            }
        parser = SubmissionParser(self.log)
        device = HALDevice(1, '/some/udi/path', properties, parser)
        self.assertEqual(device.parent_udi, None,
                         'Unexpected value of HALDevice.parent_udi, '
                         'when no parent information available.')

    def testHALDeviceDeviceId(self):
        """Test of HALDevice.device_id."""
        properties = {}
        parser = SubmissionParser(self.log)
        device = HALDevice(1, '/some/udi/path', properties, parser)
        self.assertEqual(
            '/some/udi/path', device.device_id,
            'Unexpected value of HALDevice.device_id')

    def testHALDevicePciClass(self):
        """Test of HALDevice.pci_class."""
        properties = {
            'pci.device_class': (1, 'int'),
            }
        parser = SubmissionParser(self.log)
        device = HALDevice(1, '/some/udi/path', properties, parser)
        self.assertEqual(
             1, device.pci_class,
            'Unexpected value of HALDevice.pci_class.')

        properties = {}
        parser = SubmissionParser(self.log)
        device = HALDevice(1, '/some/udi/path', properties, parser)
        self.assertEqual(
            None, device.pci_class,
            'Unexpected value of HALDevice.pci_class for Non-PCI device.')

    def testHALDevicePciSubClass(self):
        """Test of HALDevice.pci_subclass."""
        properties = {
            'pci.device_subclass': (1, 'int'),
            }
        parser = SubmissionParser(self.log)
        device = HALDevice(1, '/some/udi/path', properties, parser)
        self.assertEqual(
             1, device.pci_subclass,
            'Unexpected value of HALDevice.pci_subclass.')

        properties = {}
        parser = SubmissionParser(self.log)
        device = HALDevice(1, '/some/udi/path', properties, parser)
        self.assertEqual(
             None, device.pci_subclass,
            'Unexpected value of HALDevice.pci_sub_class for Non-PCI device.')

    def testHALDeviceUsbVendorId(self):
        """Test of HALDevice.usb_vendor_id."""
        properties = {
            'usb_device.vendor_id': (1, 'int'),
            }
        parser = SubmissionParser(self.log)
        device = HALDevice(1, '/some/udi/path', properties, parser)
        self.assertEqual(
             1, device.usb_vendor_id,
            'Unexpected value of HALDevice.usb_vendor_id.')

        properties = {}
        parser = SubmissionParser(self.log)
        device = HALDevice(1, '/some/udi/path', properties, parser)
        self.assertEqual(
             None, device.usb_vendor_id,
            'Unexpected value of HALDevice.usb_vendor_id for Non-USB device.')

    def testHALDeviceUsbProductId(self):
        """Test of HALDevice.usb_product_id."""
        properties = {
            'usb_device.product_id': (1, 'int'),
            }
        parser = SubmissionParser(self.log)
        device = HALDevice(1, '/some/udi/path', properties, parser)
        self.assertEqual(
             1, device.usb_product_id,
            'Unexpected value of HALDevice.usb_product_id.')

        properties = {}
        parser = SubmissionParser(self.log)
        device = HALDevice(1, '/some/udi/path', properties, parser)
        self.assertEqual(
             None, device.usb_product_id,
            'Unexpected value of HALDevice.usb_product_id for Non-USB '
            'device.')

    def testHALDeviceScsiVendor(self):
        """Test of HALDevice.scsi_vendor."""
        properties = {
            'scsi.vendor': ('SEAGATE', 'string'),
            }
        parser = SubmissionParser(self.log)
        device = HALDevice(1, '/some/udi/path', properties, parser)
        self.assertEqual(
             'SEAGATE', device.scsi_vendor,
            'Unexpected value of HALDevice.scsi_vendor.')

        properties = {}
        parser = SubmissionParser(self.log)
        device = HALDevice(1, '/some/udi/path', properties, parser)
        self.assertEqual(
             None, device.scsi_vendor,
            'Unexpected value of HALDevice.scsi_vendor for Non-SCSI device.')

    def testHALDeviceScsiModel(self):
        """Test of HALDevice.scsi_model."""
        properties = {
            'scsi.model': ('ST1234567', 'string'),
            }
        parser = SubmissionParser(self.log)
        device = HALDevice(1, '/some/udi/path', properties, parser)
        self.assertEqual(
             'ST1234567', device.scsi_model,
            'Unexpected value of HALDevice.scsi_model.')

        properties = {}
        parser = SubmissionParser(self.log)
        device = HALDevice(1, '/some/udi/path', properties, parser)
        self.assertEqual(
             None, device.scsi_model,
            'Unexpected value of HALDevice.scsi_model for Non-SCSI device.')

    def testHALDeviceDriverName(self):
        """Test of HALDevice.driver_name."""
        properties = {
            'info.linux.driver': ('ahci', 'string'),
            }
        parser = SubmissionParser(self.log)
        device = HALDevice(1, '/some/udi/path', properties, parser)
        self.assertEqual(
             'ahci', device.driver_name,
            'Unexpected value of HALDevice.driver_name.')

        properties = {}
        parser = SubmissionParser(self.log)
        device = HALDevice(1, '/some/udi/path', properties, parser)
        self.assertEqual(
             None, device.driver_name,
            'Unexpected value of HALDevice.driver_name for Non-SCSI device.')

    def testHalDeviceRawBus(self):
        """test of HALDevice.raw_bus."""
        properties = {
            'info.bus': ('scsi', 'str'),
            'info.parent': ('/another/udi', 'str'),
            }
        parser = SubmissionParser(self.log)
        device = HALDevice(1, '/some/udi/path', properties, parser)
        self.assertEqual(device.raw_bus, 'scsi',
                         'Unexpected value of HALDevice.raw_bus for '
                         'HAL property info.bus.')

        properties = {
            'info.subsystem': ('scsi', 'str'),
            'info.parent': ('/another/udi', 'str'),
            }
        parser = SubmissionParser(self.log)
        device = HALDevice(1, '/some/udi/path', properties, parser)
        self.assertEqual(device.raw_bus, 'scsi',
                         'Unexpected value of HALDevice.raw_bus for '
                         'HAL property info.bus.')

    def test_HALDevice_scsi_controller_usb_storage_device(self):
        """test of HALDevice.scsi_controller.

        The physical device is a USB storage device.
        """
        devices = [
            # The main node of the USB storage device.
            {
                'id': 1,
                'udi': self.UDI_USB_STORAGE,
                'properties': {
                    'info.bus': ('usb_device', 'str'),
                    },
                },
            # The storage interface of the USB device.
            {
                'id': 2,
                'udi': self.UDI_USB_STORAGE_IF0,
                'properties': {
                    'info.bus': ('usb', 'str'),
                    'info.parent': (self.UDI_USB_STORAGE, 'str'),
                    },
                },
            # The fake SCSI host of the storage device. Note that HAL does
            # _not_ provide the info.bus property.
            {
                'id': 3,
                'udi': self.UDI_USB_STORAGE_SCSI_HOST,
                'properties': {
                    'info.parent': (self.UDI_USB_STORAGE_IF0, 'str'),
                    },
                },
            # The fake SCSI disk.
            {
                'id': 3,
                'udi': self.UDI_USB_STORAGE_SCSI_DEVICE,
                'properties': {
                    'info.bus': ('scsi', 'str'),
                    'info.parent': (self.UDI_USB_STORAGE_SCSI_HOST, 'str'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }

        parser = SubmissionParser()
        parser.buildHalDeviceList(parsed_data)

        usb_fake_scsi_disk = parser.devices[self.UDI_USB_STORAGE_SCSI_DEVICE]
        usb_main_device = parser.devices[self.UDI_USB_STORAGE_IF0]
        self.assertEqual(usb_main_device, usb_fake_scsi_disk.scsi_controller)

    def test_HALDevice_scsi_controller_pci_controller(self):
        """test of HALDevice.scsi_controller.

        Variant for a SCSI device connected to a PCI controller.
        """
        devices = [
            # The PCI host controller.
            {
                'id': 1,
                'udi': self.UDI_SATA_CONTROLLER,
                'properties': {
                    'info.bus': ('pci', 'str'),
                    'pci.device_class': (PCI_CLASS_STORAGE, 'int'),
                    'pci.device_subclass': (PCI_SUBCLASS_STORAGE_SATA,
                                            'int'),
                    },
                },
            # The (fake or real) SCSI host of the storage device.
            {
                'id': 2,
                'udi': self.UDI_SATA_CONTROLLER_SCSI,
                'properties': {
                    'info.parent': (self.UDI_SATA_CONTROLLER, 'str'),
                    },
                },
            # The (possibly fake) SCSI disk.
            {
                'id': 3,
                'udi': self.UDI_SATA_DISK,
                'properties': {
                    'info.bus': ('scsi', 'str'),
                    'info.parent': (self.UDI_SATA_CONTROLLER_SCSI, 'str'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }

        parser = SubmissionParser()
        parser.buildHalDeviceList(parsed_data)

        scsi_device = parser.devices[self.UDI_SATA_DISK]
        controller = parser.devices[self.UDI_SATA_CONTROLLER]
        self.assertEqual(controller, scsi_device.scsi_controller)

    def test_HALDevice_scsi_controller_non_scsi_device(self):
        """test of HALDevice.scsi_controller.

        Variant for non-SCSI devices.
        """
        devices = [
            {
                'id': 1,
                'udi': self.UDI_COMPUTER,
                'properties': {},
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }

        parser = SubmissionParser()
        parser.buildHalDeviceList(parsed_data)

        device = parser.devices[self.UDI_COMPUTER]
        self.assertEqual(None, device.scsi_controller)

    def test_HALDevice_scsi_controller_no_grandparent(self):
        """test of HALDevice.scsi_controller.

        Variant for a SCSI device without a grandparent device.
        """
        devices = [
            # The (fake or real) SCSI host of the storage device.
            {
                'id': 1,
                'udi': self.UDI_SATA_CONTROLLER_SCSI,
                'properties': {},
                },
            # The (possibly fake) SCSI disk.
            {
                'id': 2,
                'udi': self.UDI_SATA_DISK,
                'properties': {
                    'info.bus': ('scsi', 'str'),
                    'info.parent': (self.UDI_SATA_CONTROLLER_SCSI, 'str'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }

        parser = SubmissionParser(self.log)
        parser.submission_key = 'SCSI device without grandparent device'
        parser.buildHalDeviceList(parsed_data)

        scsi_device = parser.devices[self.UDI_SATA_DISK]
        self.assertEqual(None, scsi_device.scsi_controller)
        self.assertWarningMessage(
            parser.submission_key,
            "Found SCSI device without a grandparent: %s."
            % self.UDI_SATA_DISK)

    def test_HALDevice_scsi_controller_no_parent(self):
        """test of HALDevice.scsi_controller.

        Variant for a SCSI device without a parent device.
        """
        devices = [
            # The (possibly fake) SCSI disk.
            {
                'id': 1,
                'udi': self.UDI_SATA_DISK,
                'properties': {
                    'info.bus': ('scsi', 'str'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }

        parser = SubmissionParser(self.log)
        parser.submission_key = 'SCSI device without parent device'
        parser.buildHalDeviceList(parsed_data)

        scsi_device = parser.devices[self.UDI_SATA_DISK]
        self.assertEqual(None, scsi_device.scsi_controller)
        self.assertWarningMessage(
            parser.submission_key,
            "Found SCSI device without a parent: %s." % self.UDI_SATA_DISK)

    def testHALDeviceGetRealBus(self):
        """Test of HALDevice.real_bus, generic case.

        For most buses as "seen" by HAL, HALDevice.real_bus returns a
        unique HWBus value.
        """
        for hal_bus, real_bus in (('usb_device', HWBus.USB),
                                  ('pcmcia', HWBus.PCMCIA),
                                  ('ide', HWBus.IDE),
                                  ('serio', HWBus.SERIAL),
                                 ):
            UDI_TEST_DEVICE = '/org/freedesktop/Hal/devices/test_device'
            devices = [
                {
                    'id': 1,
                    'udi': UDI_TEST_DEVICE,
                    'properties': {
                        'info.bus': (hal_bus, 'str'),
                        },
                    },
                ]
            parsed_data = {
                'hardware': {
                    'hal': {
                        'devices': devices,
                        },
                    },
                }
            parser = SubmissionParser(self.log)
            parser.buildHalDeviceList(parsed_data)
            test_device = parser.devices[UDI_TEST_DEVICE]
            test_bus = test_device.real_bus
            self.assertEqual(test_bus, real_bus,
                             'Unexpected result of HALDevice.real_bus for '
                             'HAL bus %s: %s.' % (hal_bus, test_bus.title))

    def testHALDeviceGetRealBusSystem(self):
        """Test of HALDevice.real_bus, for the tested machine itself."""

        devices = [
            {
                'id': 1,
                'udi': self.UDI_COMPUTER,
                'properties': {
                    'info.bus': ('unknown', 'str'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }
        parser = SubmissionParser(self.log)
        parser.buildHalDeviceList(parsed_data)
        test_device = parser.devices[self.UDI_COMPUTER]
        test_bus = test_device.real_bus
        self.assertEqual(test_bus, HWBus.SYSTEM,
                         'Unexpected result of HALDevice.real_bus for '
                         'a system: %s' % test_bus.title)

    def testHALDeviceGetRealBusScsiUsb(self):
        """Test of HALDevice.real_bus for info.bus=='scsi' and a USB device.

        Memory sticks, card readers and USB->IDE/SATA adapters use SCSI
        emulation; HALDevice.real_bus treats these devices as "black boxes",
        and thus returns None.
        """
        devices = [
            # The main node of the USB storage device.
            {
                'id': 1,
                'udi': self.UDI_USB_STORAGE,
                'properties': {
                    'info.bus': ('usb_device', 'str'),
                    },
                },
            # The storage interface of the USB device.
            {
                'id': 2,
                'udi': self.UDI_USB_STORAGE_IF0,
                'properties': {
                    'info.bus': ('usb', 'str'),
                    'info.parent': (self.UDI_USB_STORAGE, 'str'),
                    },
                },
            # The fake SCSI host of the storage device. Note that HAL does
            # _not_ provide the info.bus property.
            {
                'id': 3,
                'udi': self.UDI_USB_STORAGE_SCSI_HOST,
                'properties': {
                    'info.parent': (self.UDI_USB_STORAGE_IF0, 'str'),
                    },
                },
            # The fake SCSI disk.
            {
                'id': 3,
                'udi': self.UDI_USB_STORAGE_SCSI_DEVICE,
                'properties': {
                    'info.bus': ('scsi', 'str'),
                    'info.parent': (self.UDI_USB_STORAGE_SCSI_HOST, 'str'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }

        parser = SubmissionParser(self.log)
        parser.buildHalDeviceList(parsed_data)

        usb_fake_scsi_disk = parser.devices[self.UDI_USB_STORAGE_SCSI_DEVICE]
        self.assertEqual(usb_fake_scsi_disk.real_bus, None,
            'Unexpected result of HALDevice.real_bus for the fake SCSI '
            'disk HAL node of a USB storage device bus.')

    def testHALDeviceGetRealBusScsiPci(self):
        """Test of HALDevice.real_bus for info.bus=='scsi'.

        Many non-SCSI devices support the SCSI command, and the Linux
        kernel can treat them like SCSI devices. The real bus of these
        devices can be found by looking at the PCI class and subclass
        of the host controller of the possibly fake SCSI device.
        The real bus of these device can be IDE, ATA, SATA or SCSI.
        """
        devices = [
            # The PCI host controller.
            {
                'id': 1,
                'udi': self.UDI_SATA_CONTROLLER,
                'properties': {
                    'info.bus': ('pci', 'str'),
                    'pci.device_class': (PCI_CLASS_STORAGE, 'int'),
                    'pci.device_subclass': (PCI_SUBCLASS_STORAGE_SATA,
                                            'int'),
                    },
                },
            # The fake SCSI host of the storage device. Note that HAL does
            # _not_ provide the info.bus property.
            {
                'id': 2,
                'udi': self.UDI_SATA_CONTROLLER_SCSI,
                'properties': {
                    'info.parent': (self.UDI_SATA_CONTROLLER, 'str'),
                    },
                },
            # The (possibly fake) SCSI disk.
            {
                'id': 3,
                'udi': self.UDI_SATA_DISK,
                'properties': {
                    'info.bus': ('scsi', 'str'),
                    'info.parent': (self.UDI_SATA_CONTROLLER_SCSI, 'str'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }

        pci_subclass_bus = (
            (0, HWBus.SCSI),
            (1, HWBus.IDE),
            (2, HWBus.FLOPPY),
            (3, HWBus.IPI),
            (4, None),  # subclass RAID is ignored.
            (5, HWBus.ATA),
            (6, HWBus.SATA),
            (7, HWBus.SAS),
            )

        parser = SubmissionParser(self.log)
        parser.buildHalDeviceList(parsed_data)

        for device_subclass, expected_bus in pci_subclass_bus:
            devices[0]['properties']['pci.device_subclass'] = (
                device_subclass, 'int')
            fake_scsi_disk = parser.devices[self.UDI_SATA_DISK]
            found_bus = fake_scsi_disk.real_bus
            self.assertEqual(found_bus, expected_bus,
                'Unexpected result of HWDevice.real_bus for PCI storage '
                'class device, subclass %i: %r.' % (device_subclass,
                                                    found_bus))

    def testHALDeviceGetRealBusScsiDeviceWithoutGrandparent(self):
        """Test of HALDevice.real_bus for a device without a grandparent."""
        devices = [
            # A SCSI host conrtoller.
            {
                'id': 2,
                'udi': self.UDI_SATA_CONTROLLER_SCSI,
                'properties': {},
                },
            # A SCSI disk.
            {
                'id': 3,
                'udi': self.UDI_SCSI_DISK,
                'properties': {
                    'info.bus': ('scsi', 'str'),
                    'info.parent': (self.UDI_SATA_CONTROLLER_SCSI, 'str'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }
        parser = SubmissionParser(self.log)
        parser.submission_key = 'Test SCSI disk without a grandparent'
        parser.buildHalDeviceList(parsed_data)
        scsi_disk = parser.devices[self.UDI_SCSI_DISK]
        bus = scsi_disk.real_bus
        self.assertEqual(bus, None,
            'Unexpected result of HALDevice.real_bus for a SCSI device '
            'without a grandparent. Expected None, got %r' % bus)
        self.assertWarningMessage(parser.submission_key,
            'Found SCSI device without a grandparent: %s.'
             % self.UDI_SCSI_DISK)

    def testHALDeviceGetRealBusScsiDeviceWithoutParent(self):
        """Test of HALDevice.real_bus for a device without a parent."""
        devices = [
            {
                'id': 3,
                'udi': self.UDI_SCSI_DISK,
                'properties': {
                    'info.bus': ('scsi', 'str'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }
        parser = SubmissionParser(self.log)
        parser.submission_key = 'Test SCSI disk without a parent'
        parser.buildHalDeviceList(parsed_data)
        scsi_disk = parser.devices[self.UDI_SCSI_DISK]
        bus = scsi_disk.real_bus
        self.assertEqual(bus, None,
            'Unexpected result of HALDevice.real_bus for a SCSI device '
            'without a parent. Expected None, got %r' % bus)
        self.assertWarningMessage(parser.submission_key,
            'Found SCSI device without a parent: %s.'
             % self.UDI_SCSI_DISK)

    def testHALDeviceGetRealBusScsiDeviceWithBogusPciGrandparent(self):
        """Test of HALDevice.real_bus for a device with a bogus grandparent.

        The PCI device class must be PCI_CLASS_STORAGE.
        """
        devices = [
            # The PCI host controller. The PCI device class is invalid.
            {
                'id': 1,
                'udi': self.UDI_SATA_CONTROLLER,
                'properties': {
                    'info.bus': ('pci', 'str'),
                    'pci.device_class': (-1, 'int'),
                    'pci.device_subclass': (PCI_SUBCLASS_STORAGE_SATA, 'int'),
                    },
                },
            # The fake SCSI host of the storage device. Note that HAL does
            # _not_ provide the info.bus property.
            {
                'id': 2,
                'udi': self.UDI_SATA_CONTROLLER_SCSI,
                'properties': {
                    'info.parent': (self.UDI_SATA_CONTROLLER, 'str'),
                    },
                },
            # The (possibly fake) SCSI disk.
            {
                'id': 3,
                'udi': self.UDI_SATA_DISK,
                'properties': {
                    'info.bus': ('scsi', 'str'),
                    'info.parent': (self.UDI_SATA_CONTROLLER_SCSI, 'str'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }
        parser = SubmissionParser(self.log)
        parser.submission_key = (
            'Test SCSI disk with invalid controller device class')
        parser.buildHalDeviceList(parsed_data)
        scsi_disk = parser.devices[self.UDI_SATA_DISK]
        bus = scsi_disk.real_bus
        self.assertEqual(bus, None,
            'Unexpected result of HALDevice.real_bus for a SCSI device '
            'without a parent. Expected None, got %r' % bus)
        self.assertWarningMessage(parser.submission_key,
            'A (possibly fake) SCSI device %s is connected to PCI device '
            '%s that has the PCI device class -1; expected class 1 (storage).'
             % (self.UDI_SATA_DISK, self.UDI_SATA_CONTROLLER))

    def testHALDeviceGetRealBusPci(self):
        """Test of HALDevice.real_bus for info.bus=='pci'.

        If info.bus == 'pci', we may have a real PCI device or a PCCard.
        """
        # possible parent device for the tested device,
        parent_devices = [
            # The host itself.
            {
                'id': 1,
                'udi': self.UDI_COMPUTER,
                'properties': {
                    'info.bus': ('unknown', 'str'),
                    },
                },
            # A PCI->PCI bridge.
            {
                'id': 2,
                'udi': self.UDI_PCI_PCI_BRIDGE,
                'properties': {
                    'info.parent': (self.UDI_COMPUTER, 'str'),
                    'info.bus': ('pci', 'str'),
                    'pci.device_class': (PCI_CLASS_BRIDGE, 'int'),
                    'pci.device_subclass': (PCI_SUBCLASS_BRIDGE_PCI, 'int'),
                    },
                },
            # A PCI->PCCard bridge.
            {
                'id': 3,
                'udi': self.UDI_PCI_PCCARD_BRIDGE,
                'properties': {
                    'info.parent': (self.UDI_PCI_PCI_BRIDGE, 'str'),
                    'info.bus': ('pci', 'str'),
                    'pci.device_class': (PCI_CLASS_BRIDGE, 'int'),
                    'pci.device_subclass': (PCI_SUBCLASS_BRIDGE_CARDBUS,
                                            'int'),
                    },
                },
        ]
        tested_device = {
            'id': 4,
            'udi': self.UDI_PCCARD_DEVICE,
            'properties': {
                'info.bus': ('pci', 'str'),
                },
            }
        parsed_data = {
            'hardware': {
                'hal': {},
                },
            }
        expected_result_for_parent_device = {
            self.UDI_COMPUTER: HWBus.PCI,
            self.UDI_PCI_PCI_BRIDGE: HWBus.PCI,
            self.UDI_PCI_PCCARD_BRIDGE: HWBus.PCCARD,
            }

        parser = SubmissionParser(self.log)

        for parent_device in parent_devices:
            devices = parent_devices[:]
            tested_device['properties']['info.parent'] = (
                parent_device['udi'], 'str')
            devices.append(tested_device)
            parsed_data['hardware']['hal']['devices'] = devices
            parser.buildHalDeviceList(parsed_data)
            tested_hal_device = parser.devices[self.UDI_PCCARD_DEVICE]
            found_bus = tested_hal_device.real_bus
            expected_bus = expected_result_for_parent_device[
                parent_device['udi']]
            self.assertEqual(found_bus, expected_bus,
                             'Unexpected result of HWDevice.real_bus for a '
                             'PCI or PCCard device: Expected %r, got %r.'
                             % (expected_bus, found_bus))

    def testHALDeviceGetRealBusUnknown(self):
        """Test of HALDevice.real_bus for unknown values of info.bus."""
        devices = [
            {
                'id': 1,
                'udi': self.UDI_PCCARD_DEVICE,
                'properties': {
                    'info.bus': ('nonsense', 'str'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }

        parser = SubmissionParser(self.log)
        parser.submission_key = 'Test of unknown bus name'
        parser.buildHalDeviceList(parsed_data)
        found_bus = parser.devices[self.UDI_PCCARD_DEVICE].real_bus
        self.assertEqual(found_bus, None,
                         'Unexpected result of HWDevice.real_bus for an '
                         'unknown bus name: Expected None, got %r.'
                         % found_bus)
        self.assertWarningMessage(
            parser.submission_key,
            "Unknown bus 'nonsense' for device " + self.UDI_PCCARD_DEVICE)

    def test_HALDevice_is_root_device_for_root_device(self):
        """Test of HALDevice.is_root_device for the root device."""
        devices = [
            {
                'id': 1,
                'udi': self.UDI_COMPUTER,
                'properties': {},
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }

        parser = SubmissionParser()
        parser.submission_key = 'Test of HALDevice.is_root_device'
        parser.buildHalDeviceList(parsed_data)
        self.assertTrue(parser.devices[self.UDI_COMPUTER].is_root_device)

    def test_HALDevice_is_root_device_for_non_root_device(self):
        """Test of HALDevice.is_root_device for a non-root device."""
        devices = [
            {
                'id': 1,
                'udi': self.UDI_PCCARD_DEVICE,
                'properties': {},
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }

        parser = SubmissionParser()
        parser.submission_key = 'Test of HALDevice.is_root_device'
        parser.buildHalDeviceList(parsed_data)
        self.assertFalse(
            parser.devices[self.UDI_PCCARD_DEVICE].is_root_device)

    def renameInfoBusToInfoSubsystem(self, devices):
        """Rename the property info.bus in a device list to info.subsystem.

        Older HAL version store the device bus in the property info.bus;
        newer versions store the bus in info.subsystem.

        The parameter devices is a list of dictionaries as used in the
        methods below. This method replaces all dictionary entries with
        the key info.bus by entries with the key info.subsystem in order
        to allow easy testing of both variants.
        """
        for device in devices:
            if 'info.bus' in device['properties']:
                bus = device['properties']['info.bus']
                device['properties']['info.subsystem'] = bus
                del device['properties']['info.bus']

    def testHALDeviceRealDeviceRegularBus(self):
        """Test of HALDevice.is_real_device: regular info.bus property.

        See below for exceptions, if info.bus == 'usb_device' or if
        info.bus == 'usb'.
        """
        # If a HAL device has the property info.bus, it is considered
        # to be a real device.
        devices = [
            {
                'id': 1,
                'udi': self.UDI_USB_CONTROLLER_PCI_SIDE,
                'properties': {
                    'info.bus': ('pci', 'str'),
                    'pci.device_class': (PCI_CLASS_SERIALBUS_CONTROLLER,
                                         'int'),
                    'pci.device_subclass': (PCI_SUBCLASS_SERIALBUS_USB,
                                            'int'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }
        parser = SubmissionParser(self.log)
        parser.buildHalDeviceList(parsed_data)
        device = parser.devices[self.UDI_USB_CONTROLLER_PCI_SIDE]
        self.failUnless(device.is_real_device,
                        'Device with info.bus property not treated as a '
                        'real device.')
        self.renameInfoBusToInfoSubsystem(devices)
        parser.buildHalDeviceList(parsed_data)
        device = parser.devices[self.UDI_USB_CONTROLLER_PCI_SIDE]
        self.failUnless(device.is_real_device,
                        'Device with info.subsystem property not treated as '
                        'a real device.')

    def testHALDeviceRealDeviceNoBus(self):
        """Test of HALDevice.is_real_device: No info.bus property."""
        UDI_HAL_STORAGE_DEVICE = '/org/freedesktop/Hal/devices/storage...'
        devices = [
            {
                'id': 1,
                'udi': UDI_HAL_STORAGE_DEVICE,
                'properties': {},
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }

        parser = SubmissionParser(self.log)
        parser.buildHalDeviceList(parsed_data)
        device = parser.devices[UDI_HAL_STORAGE_DEVICE]
        self.failIf(device.is_real_device,
                    'Device without info.bus property treated as a '
                    'real device')

    def testHALDeviceRealDeviceHALBusValueIgnored(self):
        """Test of HALDevice.is_real_device: ignored values of info.bus.

        A HAL device is considered to not be a real device, if its
        info.bus proerty is 'drm', 'dvb', 'memstick_host', 'net',
        'scsi_generic', 'scsi_host', 'sound', 'ssb', 'tty', 'usb'
        or 'video4linux'.
        """
        devices = [
            {
                'id': 1,
                'udi': self.UDI_USB_HUB_IF0,
                'properties': {
                    'info.bus': ('usb', 'str'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }

        properties = devices[0]['properties']
        parser = SubmissionParser(self.log)

        ignored_buses = (
             'ac97', 'bttv-sub', 'disk', 'drm', 'drm_minor', 'dvb',
            'enclosure', 'gameport', 'graphics', 'hid', 'host', 'hwmon',
            'ieee80211', 'link', 'lirc', 'mISDN', 'memstick', 'memstick_host',
            'net', 'partition', 'pci_express', 'pcmcia_socket', 'pvrusb2',
            'sas_device', 'sas_end_device', 'sas_host', 'sas_phy', 'sas_port',
            'scsi_disk', 'scsi_generic', 'scsi_host', 'scsi_tape',
            'scsi_target', 'sound', 'spi_host', 'spi_transport', 'ssb',
            'tifm', 'tifm_adapter', 'tty', 'usb', 'usb-serial',
            'usb_endpoint', 'usb_host', 'usb_interface', 'usbmon',
            'video4linux', 'wlan')
        for tested_bus in ignored_buses:
            properties['info.bus'] = (tested_bus, 'str')
            parser.buildHalDeviceList(parsed_data)
            device = parser.devices[self.UDI_USB_HUB_IF0]
            self.failIf(
                device.is_real_device,
                'Device with info.bus=%s treated as a real device'
                % tested_bus)

        del properties['info.bus']
        for tested_bus in ignored_buses:
            properties['info.subsystem'] = (tested_bus, 'str')
            parser.buildHalDeviceList(parsed_data)
            device = parser.devices[self.UDI_USB_HUB_IF0]
            self.failIf(
                device.is_real_device,
                'Device with info.subsystem=%s treated as a real device'
                % tested_bus)

    def runTestHALDeviceRealDeviceScsiDevicesPciController(
        self, devices, bus_property_name):
        """Test of HALDevice.is_real_device: info.bus == 'scsi'.

        The (fake or real) SCSI device is connected to a PCI controller.
        Though the real bus may not be SCSI, all devices for the busses
        SCSI, IDE, ATA, SATA, SAS are treated as real devices.
        """
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }

        pci_subclass_bus = (
            (0, True),  # a real SCSI controller
            (1, True),  # an IDE device
            (4, False),  # subclass RAID is ignored.
            (5, True),  # an ATA device
            (6, True),  # a SATA device
            (7, True),  # a SAS device
            )

        parser = SubmissionParser(self.log)
        parser.buildHalDeviceList(parsed_data)

        for device_subclass, expected_is_real in pci_subclass_bus:
            devices[0]['properties']['pci.device_subclass'] = (
                device_subclass, 'int')
            scsi_device = parser.devices[self.UDI_SATA_DISK]
            found_is_real = scsi_device.is_real_device
            self.assertEqual(found_is_real, expected_is_real,
                'Unexpected result of HWDevice.is_real_device for a HAL SCSI '
                'connected to PCI controller, subclass %i: %r; testing '
                'property %s'
                % (device_subclass, found_is_real, bus_property_name))

    def testHALDeviceRealDeviceScsiDevicesPciController(self):
        """Test of HALDevice.is_real_device: info.bus == 'scsi'.

        The (fake or real) SCSI device is connected to a PCI controller.
        Though the real bus may not be SCSI, all devices for the busses
        SCSI, IDE, ATA, SATA, SAS are treated as real devices.
        """
        devices = [
            # The PCI host controller.
            {
                'id': 1,
                'udi': self.UDI_SATA_CONTROLLER,
                'properties': {
                    'info.bus': ('pci', 'str'),
                    'pci.device_class': (PCI_CLASS_STORAGE, 'int'),
                    'pci.device_subclass': (PCI_SUBCLASS_STORAGE_SATA, 'int'),
                    },
                },
            # The (possibly fake) SCSI host of the storage device.
            {
                'id': 3,
                'udi': self.UDI_SATA_CONTROLLER_SCSI,
                'properties': {
                    'info.parent': (self.UDI_SATA_CONTROLLER,
                                    'str'),
                    },
                },
            # The (possibly fake) SCSI disk.
            {
                'id': 3,
                'udi': self.UDI_SATA_DISK,
                'properties': {
                    'info.bus': ('scsi', 'str'),
                    'info.parent': (self.UDI_SATA_CONTROLLER_SCSI, 'str'),
                    },
                },
            ]

        self.runTestHALDeviceRealDeviceScsiDevicesPciController(
            devices, 'info.bus')
        self.renameInfoBusToInfoSubsystem(devices)
        self.runTestHALDeviceRealDeviceScsiDevicesPciController(
            devices, 'info.subsystem')

    def testHALDeviceRealDeviceScsiDeviceUsbStorage(self):
        """Test of HALDevice.is_real_device: info.bus == 'scsi'.

        USB storage devices are treated as SCSI devices by HAL;
        we do not consider them to be real devices.
        """
        devices = [
            # The main node of the USB storage device.
            {
                'id': 1,
                'udi': self.UDI_USB_STORAGE,
                'properties': {
                    'info.bus': ('usb_device', 'str'),
                    },
                },
            # The storage interface of the USB device.
            {
                'id': 2,
                'udi': self.UDI_USB_STORAGE_IF0,
                'properties': {
                    'info.bus': ('usb', 'str'),
                    'info.parent': (self.UDI_USB_STORAGE, 'str'),
                    },
                },
            # The fake SCSI host of the storage device. Note that HAL does
            # _not_ provide the info.bus property.
            {
                'id': 3,
                'udi': self.UDI_USB_STORAGE_SCSI_HOST,
                'properties': {
                    'info.parent': (self.UDI_USB_STORAGE_IF0, 'str'),
                    },
                },
            # The fake SCSI disk.
            {
                'id': 3,
                'udi': self.UDI_USB_STORAGE_SCSI_DEVICE,
                'properties': {
                    'info.bus': ('scsi', 'str'),
                    'info.parent': (self.UDI_USB_STORAGE_SCSI_HOST, 'str'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }

        parser = SubmissionParser(self.log)
        parser.buildHalDeviceList(parsed_data)

        scsi_device = parser.devices[self.UDI_USB_STORAGE_SCSI_DEVICE]
        self.failIf(scsi_device.is_real_device,
            'Unexpected result of HWDevice.is_real_device for a HAL SCSI '
            'device as a subdevice of a USB storage device.')

        self.renameInfoBusToInfoSubsystem(devices)
        scsi_device = parser.devices[self.UDI_USB_STORAGE_SCSI_DEVICE]
        self.failIf(scsi_device.is_real_device,
            'Unexpected result of HWDevice.is_real_device for a HAL SCSI '
            'device as a subdevice of a USB storage device.')

    def testHALDeviceRealDeviceRootDevice(self):
        """Test of HALDevice.is_real_device for the root node."""
        devices = [
            {
                'id': 1,
                'udi': self.UDI_COMPUTER,
                'properties': {},
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }

        parser = SubmissionParser(self.log)
        parser.buildHalDeviceList(parsed_data)
        device = parser.devices[self.UDI_COMPUTER]
        self.failUnless(device.is_real_device,
                        'Root device not treated as a real device')

    def testHALDeviceRealChildren(self):
        """Test of HALDevice.getRealChildren."""
        # An excerpt of a real world HAL device tree. We have three "real"
        # devices, and two "unreal" devices (ID 3 and 4)
        #
        # the host itself. Treated as a real device.
        devices = [
            {
                'id': 1,
                'udi': self.UDI_COMPUTER,
                'properties': {}
                },
            # A PCI->USB bridge.
            {
                'id': 2,
                'udi': self.UDI_USB_CONTROLLER_PCI_SIDE,
                'properties': {
                    'info.parent': (self.UDI_COMPUTER, 'str'),
                    'info.bus': ('pci', 'str'),
                    'pci.device_class': (PCI_CLASS_SERIALBUS_CONTROLLER,
                                         'int'),
                    'pci.device_subclass': (PCI_SUBCLASS_SERIALBUS_USB,
                                            'int'),
                 }
            },
            # The "output aspect" of the PCI->USB bridge. Not a real
            # device.
            {
                'id': 3,
                'udi': self.UDI_USB_CONTROLLER_USB_SIDE,
                'properties': {
                    'info.parent': (self.UDI_USB_CONTROLLER_PCI_SIDE, 'str'),
                    'info.bus': ('usb_device', 'str'),
                    'usb_device.vendor_id': (0, 'int'),
                    'usb_device.product_id': (0, 'int'),
                    },
                },
            # The HAL node for raw USB data access of the bridge. Not a
            # real device.
            {
                'id': 4,
                'udi': self.UDI_USB_CONTROLLER_USB_SIDE_RAW,
                'properties': {
                    'info.parent': (self.UDI_USB_CONTROLLER_USB_SIDE, 'str'),
                    },
                },
            # The HAL node of a USB device connected to the bridge.
            {
                'id': 5,
                'udi': self.UDI_USB_HUB,
                'properties': {
                    'info.parent': (self.UDI_USB_CONTROLLER_USB_SIDE, 'str'),
                    'info.bus': ('usb_device', 'str'),
                    'usb_device.vendor_id': (self.USB_VENDOR_ID_NEC, 'int'),
                    'usb_device.product_id': (self.USB_PROD_ID_NEC_HUB,
                                              'int'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }

        parser = SubmissionParser(self.log)
        parser.buildHalDeviceList(parsed_data)

        # The PCI-USB bridge is a child of the system.
        root_device = parser.devices[self.UDI_COMPUTER]
        pci_usb_bridge = parser.devices[self.UDI_USB_CONTROLLER_PCI_SIDE]
        self.assertEqual(root_device.getRealChildren(), [pci_usb_bridge],
                         'Unexpected list of real children of the root '
                         'device')

        # The "output aspect" of the PCI->USB bridge and the node for
        # raw USB access do not appear as childs of the PCI->USB bridge,
        # but the node for the USB device is considered to be a child
        # of the bridge.

        usb_device = parser.devices[self.UDI_USB_HUB]
        self.assertEqual(pci_usb_bridge.getRealChildren(), [usb_device],
                         'Unexpected list of real children of the PCI-> '
                         'USB bridge')

    def testHasReliableDataRegularCase(self):
        """Test of HALDevice.has_reliable_data, regular case."""
        devices = [
            {
                'id': 1,
                'udi': self.UDI_COMPUTER,
                'properties': {}
                },
            {
                'id': 2,
                'udi': self.UDI_SATA_CONTROLLER,
                'properties': {
                    'info.parent': (self.UDI_COMPUTER, 'str'),
                    'info.bus': ('pci', 'str'),
                    'pci.vendor_id': (self.PCI_VENDOR_ID_INTEL, 'int'),
                    'pci.product_id': (self.PCI_PROD_ID_PCI_PCCARD_BRIDGE,
                                       'int'),
                    'info.product': ('Intel PCCard bridge 1234', 'str'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }
        parser = SubmissionParser(self.log)
        parser.buildHalDeviceList(parsed_data)
        device = parser.devices[self.UDI_SATA_CONTROLLER]
        self.failUnless(
            device.has_reliable_data,
            'Regular device treated as not having reliable data.')

    def testHasReliableDataNotProcessible(self):
        """Test of HALDevice.has_reliable_data, bus without reliable data."""
        devices = [
            {
                'id': 1,
                'udi': self.UDI_SATA_CONTROLLER,
                'properties': {},
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }
        parser = SubmissionParser(self.log)
        properties = devices[0]['properties']
        for bus in ('asus_oled', 'atm', 'backlight', 'bdi', 'bluetooth',
                    'cardman_4040', 'dahdi', 'dmi', 'heci', 'hidraw',
                    'hwmon', 'i2c-adapter', 'ieee1394', 'ieee1394_protocol',
                    'input', 'leds', 'mem', 'misc', 'mmc', 'mmc_host', 'msr',
                    'pci_bus', 'pcmcia', 'pktcdvd', 'platform', 'pnp',
                    'power_supply', 'ppdev', 'ppp', 'printer', 'rfkill',
                    'thermal', 'ttm', 'vc', 'video_output', 'vtconsole'):
            properties['info.bus'] = (bus, 'str')
            parser.buildHalDeviceList(parsed_data)
            device = parser.devices[self.UDI_SATA_CONTROLLER]
            self.failIf(device.has_reliable_data,
                'Device with bus=%s treated as having reliable data.' % bus)

    def testHasReliableDataRootDevice(self):
        """Test of HALDevice.has_reliable_data, root device.

        The root device has the info.subsystem or info.bus property set
        to 'unknown'. While we treat other devices with ths bus value
        as useless, the root device is real.
        """
        devices = [
            {
                'id': 1,
                'udi': self.UDI_COMPUTER,
                'properties': {
                    'info.subsystem': ('unknown', 'str'),
                    'system.hardware.vendor': ('FUJITSU SIEMENS', 'str'),
                    'system.hardware.product': ('LIFEBOOK E8210', 'str'),
                },
            },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }
        parser = SubmissionParser(self.log)
        parser.buildHalDeviceList(parsed_data)
        device = parser.devices[self.UDI_COMPUTER]
        self.failUnless(
            device.has_reliable_data,
            "Root device not treated as having reliable data.")

    def testHasReliableDataForInsuffientData(self):
        """Test of HALDevice.has_reliable_data, insufficent device data.

        Test for a HAL device that should be processible but does
        not provide enough data. Aside from a bus, we need a vendor ID,
        a product ID and a product name.
        """
        devices = [
            {
                'id': 1,
                'udi': self.UDI_COMPUTER,
                'properties': {}
                },
            {
                'id': 2,
                'udi': self.UDI_SATA_CONTROLLER,
                'properties': {
                    'info.parent': (self.UDI_COMPUTER, 'str'),
                    'info.bus': ('pci', 'str'),
                    'pci.vendor_id': (self.PCI_VENDOR_ID_INTEL, 'int'),
                    'pci.product_id': (self.PCI_PROD_ID_PCI_PCCARD_BRIDGE,
                                       'int'),
                    'info.product': ('Intel PCCard bridge 1234', 'str'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }

        missing_data_log_message = (
            ('pci.vendor_id',
             "A HALDevice that is supposed to be a real device does not "
             "provide bus, vendor ID, product ID or product name: <DBItem "
             "HWBus.PCI, (1) PCI> None 28980 'Intel PCCard bridge 1234' "
             "/org/freedesktop/Hal/devices/pci_8086_27c5"
             ),
            ('pci.product_id',
             "A HALDevice that is supposed to be a real device does not "
             "provide bus, vendor ID, product ID or product name: "
             "<DBItem HWBus.PCI, (1) PCI> 32902 None 'Intel PCCard bridge "
             "1234' /org/freedesktop/Hal/devices/pci_8086_27c5"
             ),
            ('info.product',
             "A HALDevice that is supposed to be a real device does not "
             "provide bus, vendor ID, product ID or product name: "
             "<DBItem HWBus.PCI, (1) PCI> 32902 28980 None "
             "/org/freedesktop/Hal/devices/pci_8086_27c5"
             ),
            )

        for (missing_data, expected_log_message) in missing_data_log_message:
            test_parsed_data = deepcopy(parsed_data)
            test_device = test_parsed_data['hardware']['hal']['devices'][1]
            del test_device['properties'][missing_data]

            parser = SubmissionParser(self.log)
            submission_key = 'test_missing_%s' % missing_data
            parser.submission_key = submission_key
            parser.buildHalDeviceList(test_parsed_data)
            device = parser.devices[self.UDI_SATA_CONTROLLER]
            self.failIf(
                device.has_reliable_data,
                'Device with missing property %s treated as having reliable'
                'data.' % missing_data)
            self.assertWarningMessage(submission_key, expected_log_message)

    def testHasReliableDataIDEDevice(self):
        """Test of HALDevice.has_reliable_data, for IDE devices.

        Many IDE devices do not provide vendor and product IDs. This is
        a known problem and hence not worth a log message.
        """
        devices = [
            {
                'id': 1,
                'udi': self.UDI_COMPUTER,
                'properties': {}
                },
            {
                'id': 2,
                'udi': self.UDI_SATA_CONTROLLER,
                'properties': {
                    'info.parent': (self.UDI_COMPUTER, 'str'),
                    'info.bus': ('pci', 'str'),
                    'pci.vendor_id': (self.PCI_VENDOR_ID_INTEL, 'int'),
                    'pci.product_id': (self.PCI_PROD_ID_PCI_PCCARD_BRIDGE,
                                       'int'),
                    'info.product': ('Intel PCCard bridge 1234', 'str'),
                    },
                },
            {
                'id': 3,
                'udi': self.UDI_SATA_DISK,
                'properties': {
                    'info.parent': (self.UDI_SATA_CONTROLLER, 'str'),
                    'info.bus': ('ide', 'str'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }

        parser = SubmissionParser(self.log)
        parser.buildHalDeviceList(parsed_data)
        device = parser.devices[self.UDI_SATA_DISK]
        self.failIf(
            device.has_reliable_data,
            'IDE Device with missing properties vendor ID, product ID, '
            'product name treated as having reliabledata.')
        self.assertEqual(
            len(self.handler.records), 0,
            'Warning messages exist for processing an IDE device where '
            'no messages are expected.')

    def testHALDeviceSCSIVendorModelNameRegularCase(self):
        """Test of HALDevice.getScsiVendorAndModelName, regular case."""
        devices = [
            {
                'id': 1,
                'udi': self.UDI_SCSI_DISK,
                'properties': {
                    'info.bus': ('scsi', 'str'),
                    'scsi.vendor': ('SHARP', 'str'),
                    'scsi.model': ('JX250 SCSI', 'str'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }
        parser = SubmissionParser(self.log)
        parser.buildHalDeviceList(parsed_data)
        device = parser.devices[self.UDI_SCSI_DISK]
        vendor_model = device.getScsiVendorAndModelName()
        self.assertEqual(
            {
                'vendor': 'SHARP',
                'product': 'JX250 SCSI',
                },
            vendor_model,
            'Unexpected result of HWDevice.getScsiVendorAndModelName '
            'for a regular SCSI device. Expected vendor name SHARP, got %r.'
            % vendor_model)

    def testHALDeviceSCSIVendorModelNameATADiskShortModelName(self):
        """Test of HALDevice.getScsiVendorAndModelName, ATA disk (1).

        Test of an ATA disk with a short model name. The Linux kenrel
        sets the vendor name to "ATA" and inserts the real vendor
        name into the model string.
        """
        devices = [
            {
                'id': 1,
                'udi': self.UDI_SCSI_DISK,
                'properties': {
                    'info.bus': ('scsi', 'str'),
                    'scsi.vendor': ('ATA', 'str'),
                    'scsi.model': ('Hitachi HTS54161', 'str'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }
        parser = SubmissionParser(self.log)
        parser.buildHalDeviceList(parsed_data)
        device = parser.devices[self.UDI_SCSI_DISK]
        vendor_model = device.getScsiVendorAndModelName()
        self.assertEqual(
            {
                'vendor': 'Hitachi',
                'product': 'HTS54161',
                },
            vendor_model,
            'Unexpected result of HWDevice.getScsiVendorAndModelName '
            'for an ATA SCSI device: %r.'
            % vendor_model)

    def testHALDeviceSCSIVendorModelNameATADiskLongModelName(self):
        """Test of HALDevice.getScsiVendorAndModelName, ATA disk (2).

        Test of an ATA disk with a short model name. The Linux kenrel
        sets the vendor name to "ATA" and ignores the real vendor name,
        """
        devices = [
            {
                'id': 1,
                'udi': self.UDI_SCSI_DISK,
                'properties': {
                    'info.bus': ('scsi', 'str'),
                    'scsi.vendor': ('ATA', 'str'),
                    'scsi.model': ('HTC426060G9AT00', 'str'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }
        parser = SubmissionParser(self.log)
        parser.buildHalDeviceList(parsed_data)
        device = parser.devices[self.UDI_SCSI_DISK]
        vendor_product = device.getScsiVendorAndModelName()
        self.assertEqual(
            {
                'vendor': 'ATA',
                'product': 'HTC426060G9AT00',
                },
            vendor_product,
            'Unexpected result of HWDevice.getScsiVendorAndModelName '
            'for a reguale SCSI device: %r.'
            % vendor_product)

    def testHALDeviceVendorFromInfoVendor(self):
        """Test of HALDevice.vendor, regular case.

        The value is copied from info.vendor, if available."""
        devices = [
            {
                'id': 1,
                'udi': self.UDI_SATA_CONTROLLER,
                'properties': {
                    'info.bus': ('pci', 'str'),
                    'info.vendor': ('Intel Corporation', 'str'),
                    'pci.vendor': ('should not be used', 'str'),
                    }
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }
        parser = SubmissionParser(self.log)
        parser.buildHalDeviceList(parsed_data)
        found_vendor = parser.devices[self.UDI_SATA_CONTROLLER].vendor
        self.assertEqual(found_vendor, 'Intel Corporation',
                         'Unexpected result of HWDevice.vendor. '
                         'Expected Intel Corporation, got %r.'
                         % found_vendor)

    def testHALDeviceVendorFromBusVendor(self):
        """Test of HALDevice.vendor, value copied from ${bus}.vendor.

        If the property info.vendor does not exist, ${bus}.vendor
        is tried.
        """
        devices = [
            {
                'id': 1,
                'udi': self.UDI_SATA_CONTROLLER,
                'properties': {
                    'info.bus': ('pci', 'str'),
                    'pci.vendor': ('Intel Corporation', 'str'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }
        parser = SubmissionParser(self.log)
        parser.buildHalDeviceList(parsed_data)
        found_vendor = parser.devices[self.UDI_SATA_CONTROLLER].vendor
        self.assertEqual(found_vendor, 'Intel Corporation',
                         'Unexpected result of HWDevice.vendor, '
                         'if info.vendor does not exist. '
                         'Expected Intel Corporation, got %r.'
                         % found_vendor)

    def testHALDeviceVendorScsi(self):
        """Test of HALDevice.vendor for SCSI devices: regular case."""
        devices = [
            {
                'id': 1,
                'udi': self.UDI_SCSI_DISK,
                'properties': {
                    'info.bus': ('scsi', 'str'),
                    'scsi.vendor': ('SEAGATE', 'str'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }
        parser = SubmissionParser(self.log)
        parser.buildHalDeviceList(parsed_data)
        found_vendor = parser.devices[self.UDI_SCSI_DISK].vendor
        self.assertEqual(found_vendor, 'SEAGATE',
                         'Unexpected result of HWDevice.vendor '
                         'for SCSI device. Expected SEAGATE, got %r.'
                         % found_vendor)

    def testHALDeviceVendorScsiAta(self):
        """Test of HALDevice.vendor for SCSI devices: fake IDE/SATA disks."""
        devices = [
            {
                'id': 1,
                'udi': self.UDI_SCSI_DISK,
                'properties': {
                    'info.bus': ('scsi', 'str'),
                    'scsi.vendor': ('ATA', 'str'),
                    'scsi.model': ('Hitachi HTS54161', 'str'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }
        parser = SubmissionParser(self.log)
        parser.buildHalDeviceList(parsed_data)
        found_vendor = parser.devices[self.UDI_SCSI_DISK].vendor
        self.assertEqual(found_vendor, 'Hitachi',
                         'Unexpected result of HWDevice.vendor, for fake '
                         'SCSI device. Expected Hitachi, got %r.'
                         % found_vendor)

    def testHALDeviceVendorSystem(self):
        """Test of HALDevice.vendor for the machine itself."""
        # HAL does not provide info.vendor for the root UDI
        # /org/freedesktop/Hal/devices/computer, hence HALDevice.vendor
        # reads the vendor name from system.vendor
        devices = [
            {
                'id': 1,
                'udi': self.UDI_COMPUTER,
                'properties': {
                    'info.bus': ('unknown', 'str'),
                    'system.hardware.vendor': ('FUJITSU SIEMENS', 'str'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }
        parser = SubmissionParser(self.log)
        parser.buildHalDeviceList(parsed_data)
        found_vendor = parser.devices[self.UDI_COMPUTER].vendor
        self.assertEqual(found_vendor, 'FUJITSU SIEMENS',
                         'Unexpected result of HWDevice.vendor for a '
                         'system. Expected FUJITSU SIEMENS, got %r.'
                         % found_vendor)

    def testHALDeviceProductFromInfoProduct(self):
        """Test of HALDevice.product, regular case.

        The value is copied from info.product, if available."""
        # The product name is copied from the HAL property info.product,
        # if it is avaliable.
        devices = [
             {
                'id': 1,
                'udi': self.UDI_SATA_CONTROLLER,
                'properties': {
                    'info.bus': ('pci', 'str'),
                    'info.product': ('82801GBM/GHM SATA AHCI Controller',
                                     'str'),
                    'pci.product': ('should not be used', 'str'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }
        parser = SubmissionParser(self.log)
        parser.buildHalDeviceList(parsed_data)
        found_product = parser.devices[self.UDI_SATA_CONTROLLER].product
        self.assertEqual(found_product, '82801GBM/GHM SATA AHCI Controller',
                         'Unexpected result of HWDevice.product. '
                         'Expected 82801GBM/GHM SATA AHCI Controller, got %r.'
                         % found_product)

    def testHALDeviceProductFromBusProduct(self):
        """Test of HALDevice.product, value copied from ${bus}.product.

        If the property info.product does not exist, ${bus}.product
        """
        devices = [
            {
                'id': 1,
                'udi': self.UDI_SATA_CONTROLLER,
                'properties': {
                    'info.bus': ('pci', 'str'),
                    'pci.product': ('82801GBM/GHM SATA AHCI Controller',
                                    'str'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }
        parser = SubmissionParser(self.log)
        parser.buildHalDeviceList(parsed_data)
        found_product = parser.devices[self.UDI_SATA_CONTROLLER].product
        self.assertEqual(found_product, '82801GBM/GHM SATA AHCI Controller',
                         'Unexpected result of HWDevice.product, '
                         'if info.product does not exist. '
                         'Expected 82801GBM/GHM SATA AHCI Controller, got %r.'
                         % found_product)

    def testHALDeviceProductScsi(self):
        """Test of HALDevice.product for SCSI devices: regular case."""
        # The name of SCSI device is copied from the property scsi.model.
        devices = [
            {
                'id': 1,
                'udi': self.UDI_SCSI_DISK,
                'properties': {
                    'info.bus': ('scsi', 'str'),
                    'scsi.vendor': ('SEAGATE', 'str'),
                    'scsi.model': ('ST36530N', 'str'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }
        parser = SubmissionParser(self.log)
        parser.buildHalDeviceList(parsed_data)
        found_product = parser.devices[self.UDI_SCSI_DISK].product
        self.assertEqual(found_product, 'ST36530N',
                         'Unexpected result of HWDevice.product '
                         'for SCSI device. Expected ST36530N, got %r.'
                         % found_product)

    def testHALDeviceProductScsiAta(self):
        """Test of HALDevice.product for SCSI devices: fake IDE/SATA disks."""
        devices = [
            {
                'id': 1,
                'udi': self.UDI_SCSI_DISK,
                'properties': {
                    'info.bus': ('scsi', 'str'),
                    'scsi.vendor': ('ATA', 'str'),
                    'scsi.model': ('Hitachi HTS54161', 'str'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }
        parser = SubmissionParser(self.log)
        parser.buildHalDeviceList(parsed_data)
        found_product = parser.devices[self.UDI_SCSI_DISK].product
        self.assertEqual(found_product, 'HTS54161',
                         'Unexpected result of HWDevice.product, for fake '
                         'SCSI device. Expected HTS54161, got %r.'
                         % found_product)

    def testHALDeviceProductSystem(self):
        """Test of HALDevice.product for the machine itself."""
        # HAL sets info.product to "Computer" for the root UDI
        # /org/freedesktop/Hal/devices/computer, hence HALDevice.product
        # reads the product name from system.product.
        devices = [
            {
                'id': 1,
                'udi': self.UDI_COMPUTER,
                'properties': {
                    'info.bus': ('unknown', 'str'),
                    'system.hardware.product': ('LIFEBOOK E8210', 'str'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }
        parser = SubmissionParser(self.log)
        parser.buildHalDeviceList(parsed_data)
        found_product = parser.devices[self.UDI_COMPUTER].product
        self.assertEqual(found_product, 'LIFEBOOK E8210',
                         'Unexpected result of HWDevice.product, '
                         'if info.product does not exist. '
                         'Expected LIFEBOOK E8210, got %r.'
                         % found_product)

    def testHALDeviceVendorId(self):
        """Test of HALDevice.vendor_id.

        Many buses have a numerical vendor ID. Except for the special
        cases tested below, HWDevice.vendor_id returns the HAL property
        ${bus}.vendor_id.
        """
        devices = [
             {
                'id': 1,
                'udi': self.UDI_SATA_CONTROLLER,
                'properties': {
                    'info.bus': ('pci', 'str'),
                    'pci.vendor_id': (self.PCI_VENDOR_ID_INTEL, 'int'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }
        parser = SubmissionParser(self.log)
        parser.buildHalDeviceList(parsed_data)
        found_vendor_id = parser.devices[
            self.UDI_SATA_CONTROLLER].vendor_id
        self.assertEqual(found_vendor_id, self.PCI_VENDOR_ID_INTEL,
                         'Unexpected result of HWDevice.vendor_id. '
                         'Expected 0x8086, got 0x%x.'
                         % found_vendor_id)

    def testHALDeviceVendorIdScsi(self):
        """Test of HALDevice.vendor_id for SCSI devices.

        The SCSI specification does not know about a vendor ID,
        we use the vendor string as returned by INQUIRY command
        as the ID.
        """
        devices = [
            {
                'id': 1,
                'udi': self.UDI_SCSI_DISK,
                'properties': {
                    'info.bus': ('scsi', 'str'),
                    'scsi.vendor': ('SEAGATE', 'str'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }
        parser = SubmissionParser(self.log)
        parser.buildHalDeviceList(parsed_data)
        found_vendor_id = parser.devices[self.UDI_SCSI_DISK].vendor_id
        self.assertEqual(found_vendor_id, 'SEAGATE',
                         'Unexpected result of HWDevice.vendor_id for a. '
                         'SCSI device. Expected SEAGATE, got %r.'
                         % found_vendor_id)

    def testHALDeviceVendorIdScsiAta(self):
        """Test of HALDevice.vendor_id for SCSI devices: fake IDE/SATA disks.
        """
        devices = [
            {
                'id': 1,
                'udi': self.UDI_SCSI_DISK,
                'properties': {
                    'info.bus': ('scsi', 'str'),
                    'scsi.vendor': ('ATA', 'str'),
                    'scsi.model': ('Hitachi HTS54161', 'str'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }
        parser = SubmissionParser(self.log)
        parser.buildHalDeviceList(parsed_data)
        found_vendor_id = parser.devices[self.UDI_SCSI_DISK].vendor_id
        self.assertEqual(found_vendor_id, 'Hitachi',
                         'Unexpected result of HWDevice.vendor_id for a. '
                         'fake SCSI device. Expected Hitachi, got %r.'
                         % found_vendor_id)

    def testHALDeviceVendorIdSystem(self):
        """Test of HALDevice.vendor_id for the machine itself."""
        # HAL does not provide the property info.vendor_id for the
        # root UDI /org/freedesktop/Hal/devices/computer. We use
        # HALDevice.vendor instead.
        devices = [
            {
                'id': 1,
                'udi': self.UDI_COMPUTER,
                'properties': {
                    'info.bus': ('unknown', 'str'),
                    'system.hardware.vendor': ('FUJITSU SIEMENS', 'str'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }
        parser = SubmissionParser(self.log)
        parser.buildHalDeviceList(parsed_data)
        found_vendor_id = parser.devices[self.UDI_COMPUTER].vendor_id
        self.assertEqual(found_vendor_id, 'FUJITSU SIEMENS',
                         'Unexpected result of HWDevice.vendor_id for a '
                         'system. Expected FUJITSU SIEMENS, got %r.'
                         % found_vendor_id)

    def testHALDeviceProductId(self):
        """Test of HALDevice.product_id.

        Many buses have a numerical product ID. Except for the special
        cases tested below, HWDevice.product_id returns the HAL property
        ${bus}.product_id.
        """
        devices = [
             {
                'id': 1,
                'udi': self.UDI_SATA_CONTROLLER,
                'properties': {
                    'info.bus': ('pci', 'str'),
                    'pci.product_id': (0x27c5, 'int'),
                    },
                },
             ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }
        parser = SubmissionParser(self.log)
        parser.buildHalDeviceList(parsed_data)
        found_product_id = parser.devices[self.UDI_SATA_CONTROLLER].product_id
        self.assertEqual(found_product_id, 0x27c5,
                         'Unexpected result of HWDevice.product_id. '
                         'Expected 0x27c5, got 0x%x.'
                         % found_product_id)

    def testHALDeviceProductIdScsi(self):
        """Test of HALDevice.product_id for SCSI devices.

        The SCSI specification does not know about a product ID,
        we use the product string as returned by INQUIRY command
        as the ID.
        """
        devices = [
            {
                'id': 1,
                'udi': self.UDI_SCSI_DISK,
                'properties': {
                    'info.bus': ('scsi', 'str'),
                    'scsi.vendor': ('SEAGATE', 'str'),
                    'scsi.model': ('ST36530N', 'str'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }
        parser = SubmissionParser(self.log)
        parser.buildHalDeviceList(parsed_data)
        found_product_id = parser.devices[self.UDI_SCSI_DISK].product_id
        self.assertEqual(found_product_id, 'ST36530N',
                         'Unexpected result of HWDevice.product_id for a. '
                         'SCSI device. Expected ST35630N, got %r.'
                         % found_product_id)

    def testHALDeviceProductIdScsiAta(self):
        """Test of HALDevice.product_id for SCSI devices: fake IDE/SATA disks.
        """
        devices = [
            {
                'id': 1,
                'udi': self.UDI_SCSI_DISK,
                'properties': {
                    'info.bus': ('scsi', 'str'),
                    'scsi.vendor': ('ATA', 'str'),
                    'scsi.model': ('Hitachi HTS54161', 'str'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }
        parser = SubmissionParser(self.log)
        parser.buildHalDeviceList(parsed_data)
        found_product_id = parser.devices[self.UDI_SCSI_DISK].product_id
        self.assertEqual(found_product_id, 'HTS54161',
                         'Unexpected result of HWDevice.product_id for a. '
                         'fake SCSI device. Expected HTS54161, got %r.'
                         % found_product_id)

    def testHALDeviceProductIdSystem(self):
        """Test of HALDevice.product_id for the machine itself."""
        # HAL does not provide info.product_id for the root UDI
        # /org/freedesktop/Hal/devices/computer. We use
        # HALDevice.product instead.
        devices = [
            {
                'id': 1,
                'udi': self.UDI_COMPUTER,
                'properties': {
                    'info.bus': ('unknown', 'str'),
                    'system.hardware.product': ('LIFEBOOK E8210', 'str'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }
        parser = SubmissionParser(self.log)
        parser.buildHalDeviceList(parsed_data)
        found_product_id = parser.devices[self.UDI_COMPUTER].product_id
        self.assertEqual(found_product_id, 'LIFEBOOK E8210',
                         'Unexpected result of HWDevice.product_id for a '
                         'system. Expected LIFEBOOK E8210, got %r.'
                         % found_product_id)

    def testVendorIDForDB(self):
        """Test of HALDevice.vendor_id_for_db."""
        devices = [
            {
                'id': 1,
                'udi': self.UDI_SATA_DISK,
                'properties': {},
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }
        properties = devices[0]['properties']
        parser = SubmissionParser(self.log)
        # SCSI vendor names have a length of exactly 8 bytes; we use
        # this format for HWDevice.bus_product_id too.
        testdata = (('pci', (0x123, 'int'), '0x0123'),
                    ('usb_device', (0x234, 'int'), '0x0234'),
                    ('scsi', ('SEAGATE', 'str'), 'SEAGATE '),
                    )
        for bus, vendor_id, expected_vendor_id in testdata:
            properties['info.bus'] = (bus, 'str')
            if bus == 'scsi':
                properties['%s.vendor' % bus] = vendor_id
            else:
                properties['%s.vendor_id' % bus] = vendor_id
            parser.buildHalDeviceList(parsed_data)
            found_vendor_id = parser.devices[
                self.UDI_SATA_DISK].vendor_id_for_db
            self.assertEqual(found_vendor_id, expected_vendor_id,
                'Unexpected result of HWDevice.vendor_id_for_db for bus '
                '"%s". Expected %r, got %r.'
                % (bus, expected_vendor_id, found_vendor_id))

    def testVendorIDForDBSystem(self):
        """Test of HALDevice.vendor_id_for_db."""
        devices = [
            {
                'id': 1,
                'udi': self.UDI_COMPUTER,
                'properties': {
                    'system.hardware.vendor': ('FUJITSU SIEMENS', 'str'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }
        parser = SubmissionParser(self.log)
        parser.buildHalDeviceList(parsed_data)
        found_vendor_id = parser.devices[self.UDI_COMPUTER].vendor_id_for_db
        self.assertEqual(found_vendor_id, 'FUJITSU SIEMENS',
            'Unexpected result of HWDevice.vendor_id_for_db for system. '
            'Expected FUJITSU SIEMENS, got %r.' % found_vendor_id)

    def testProductIDForDB(self):
        """Test of HALDevice.product_id_for_db."""
        devices = [
            {
                'id': 1,
                'udi': self.UDI_SATA_DISK,
                'properties': {},
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }
        properties = devices[0]['properties']
        parser = SubmissionParser(self.log)
        # SCSI product names (called "model" in the SCSI specifications)
        # have a length of exactly 16 bytes; we use this format for
        # HWDevice.bus_product_id too.
        testdata = (('pci', (0x123, 'int'), '0x0123'),
                    ('usb_device', (0x234, 'int'), '0x0234'),
                    ('scsi', ('ST1234567890', 'str'), 'ST1234567890    '),
                   )
        for bus, product_id, expected_product_id in testdata:
            properties['info.bus'] = (bus, 'str')
            if bus == 'scsi':
                properties['%s.model' % bus] = product_id
            else:
                properties['%s.product_id' % bus] = product_id
            parser.buildHalDeviceList(parsed_data)
            found_product_id = parser.devices[
                self.UDI_SATA_DISK].product_id_for_db
            self.assertEqual(found_product_id, expected_product_id,
                'Unexpected result of HWDevice.product_id_for_db for bus '
                '"%s". Expected %r, got %r.'
                % (bus, expected_product_id, found_product_id))

    def testProductIDForDBSystem(self):
        """Test of HALDevice.product_id_for_db."""
        devices = [
            {
                'id': 1,
                'udi': self.UDI_COMPUTER,
                'properties': {
                    'system.hardware.product': ('E8210', 'str'),
                    },
                },
            ]
        parsed_data = {
            'hardware': {
                'hal': {
                    'devices': devices,
                    },
                },
            }
        parser = SubmissionParser(self.log)
        parser.buildHalDeviceList(parsed_data)
        found_product_id = parser.devices[self.UDI_COMPUTER].product_id_for_db
        self.assertEqual(found_product_id, 'E8210',
            'Unexpected result of HWDevice.product_id_for_db for system. '
            'Expected FUJITSU SIEMENS, got %r.' % found_product_id)


class TestHALDeviceUSBDevices(TestCaseHWDB):
    """Tests for HALDevice.is_real_device: USB devices."""

    def setUp(self):
        """Setup the test environment."""
        super(TestHALDeviceUSBDevices, self).setUp()
        self.usb_controller_pci_side = {
            'id': 1,
            'udi': self.UDI_USB_CONTROLLER_PCI_SIDE,
            'properties': {
                'info.bus': ('pci', 'str'),
                'pci.device_class': (PCI_CLASS_SERIALBUS_CONTROLLER, 'int'),
                'pci.device_subclass': (PCI_SUBCLASS_SERIALBUS_USB, 'int'),
                },
            }
        self.usb_controller_usb_side = {
            'id': 2,
            'udi': self.UDI_USB_CONTROLLER_USB_SIDE,
            'properties': {
                'info.parent': (self.UDI_USB_CONTROLLER_PCI_SIDE, 'str'),
                'info.bus': ('usb_device', 'str'),
                'usb_device.vendor_id': (0, 'int'),
                'usb_device.product_id': (0, 'int'),
                },
            }
        self.usb_storage_device = {
            'id': 3,
            'udi': self.UDI_USB_STORAGE,
            'properties': {
                'info.parent': (self.UDI_USB_CONTROLLER_USB_SIDE, 'str'),
                'info.bus': ('usb_device', 'str'),
                'usb_device.vendor_id': (self.USB_VENDOR_ID_USBEST, 'int'),
                'usb_device.product_id': (self.USB_PROD_ID_USBBEST_MEMSTICK,
                                          'int'),
                },
            }
        self.parsed_data = {
            'hardware': {
                'hal': {
                    'devices': [
                        self.usb_controller_pci_side,
                        self.usb_controller_usb_side,
                        self.usb_storage_device,
                        ],
                    },
                },
            }

    def renameInfoBusToInfoSubsystem(self):
        for device in self.parsed_data['hardware']['hal']['devices']:
            properties = device['properties']
            properties['info.subsystem'] = properties['info.bus']
            del properties['info.bus']

    def testUSBDeviceRegularCase(self):
        """Test of HALDevice.is_real_device: info.bus == 'usb_device'."""
        parser = SubmissionParser(self.log)
        parser.buildHalDeviceList(self.parsed_data)
        device = parser.devices[self.UDI_USB_STORAGE]
        self.failUnless(
            device.is_real_device,
            'Testing info.bus property: Regular USB Device not treated '
            'as a real device.')

        self.renameInfoBusToInfoSubsystem()
        parser.buildHalDeviceList(self.parsed_data)
        device = parser.devices[self.UDI_USB_STORAGE]
        self.failUnless(
            device.is_real_device,
            'Testing info.subsystem property: Regular USB Device not treated '
            'as a real device.')

    def testUSBHostController(self):
        """Test of HALDevice.is_real_device: info.bus == 'usb_device'.

        Special case: vendor ID and product ID of the device are zero;
        the parent device is a PCI/USB host controller.
        """

        parser = SubmissionParser(self.log)
        parser.buildHalDeviceList(self.parsed_data)
        device = parser.devices[self.UDI_USB_CONTROLLER_USB_SIDE]
        self.failIf(
            device.is_real_device,
            'Testing info.bus property: USB Device with vendor/product '
            'ID 0:0 property treated as a real device.')

        self.renameInfoBusToInfoSubsystem()
        parser.buildHalDeviceList(self.parsed_data)
        device = parser.devices[self.UDI_USB_CONTROLLER_USB_SIDE]
        self.failIf(
            device.is_real_device,
            'Testing info.subsystem property: USB Device with vendor/product '
            'ID 0:0 property treated as a real device.')

    def testUSBHostControllerInvalidParentClass(self):
        """Test of HALDevice.is_real_device: info.bus == 'usb_device'.

        Special case: vendor ID and product ID of the device are zero;
        the parent device cannot be identified as a PCI/USB host
        controller: Wrong PCI device class of the parent device.
        """
        parent_properties = self.usb_controller_pci_side['properties']
        parent_properties['pci.device_class'] = (PCI_CLASS_STORAGE, 'int')
        parser = SubmissionParser(self.log)
        parser.submission_key = 'USB device test 1'
        parser.buildHalDeviceList(self.parsed_data)
        device = parser.devices[self.UDI_USB_CONTROLLER_USB_SIDE]
        self.failIf(
            device.is_real_device,
            'Testing info.bus property: USB Device with vendor/product '
            'ID 0:0 property treated as a real device.')
        self.assertWarningMessage(
            parser.submission_key,
            'USB device found with vendor ID==0, product ID==0, where the '
            'parent device does not look like a USB host controller: '
            + self.UDI_USB_CONTROLLER_USB_SIDE)

        self.renameInfoBusToInfoSubsystem()
        parser.buildHalDeviceList(self.parsed_data)
        device = parser.devices[self.UDI_USB_CONTROLLER_USB_SIDE]
        self.failIf(
            device.is_real_device,
            'Testing info.subsystem property: USB Device with vendor/product '
            'ID 0:0 property treated as a real device.')
        self.assertWarningMessage(
            parser.submission_key,
            'USB device found with vendor ID==0, product ID==0, where the '
            'parent device does not look like a USB host controller: '
            + self.UDI_USB_CONTROLLER_USB_SIDE)

    def testUSBHostControllerInvalidParentSubClass(self):
        """Test of HALDevice.is_real_device: info.bus == 'usb_device'.

        Special case: vendor ID and product ID of the device are zero;
        the parent device cannot be identified as a PCI/USB host
        controller: Wrong PCI device subclass of the parent device.
        """
        parent_properties = self.usb_controller_pci_side['properties']
        parent_properties['pci.device_subclass'] = (1, 'int')
        parser = SubmissionParser(self.log)
        parser.submission_key = 'USB device test 2'
        parser.buildHalDeviceList(self.parsed_data)
        device = parser.devices[self.UDI_USB_CONTROLLER_USB_SIDE]
        self.failIf(
            device.is_real_device,
            'Testing info.bus property: USB Device with vendor/product '
            'ID 0:0 property treated as a real device.')
        self.assertWarningMessage(
            parser.submission_key,
            'USB device found with vendor ID==0, product ID==0, where the '
            'parent device does not look like a USB host controller: '
            + self.UDI_USB_CONTROLLER_USB_SIDE)

        self.renameInfoBusToInfoSubsystem()
        parser.buildHalDeviceList(self.parsed_data)
        device = parser.devices[self.UDI_USB_CONTROLLER_USB_SIDE]
        self.failIf(
            device.is_real_device,
            'Testing info.subsystem property: USB Device with vendor/product '
            'ID 0:0 property treated as a real device.')
        self.assertWarningMessage(
            parser.submission_key,
            'USB device found with vendor ID==0, product ID==0, where the '
            'parent device does not look like a USB host controller: '
            + self.UDI_USB_CONTROLLER_USB_SIDE)

    def testUSBHostControllerUnexpectedParentBus(self):
        """Test of HALDevice.is_real_device: info.bus == 'usb_device'.

        Special case: vendor ID and product ID of the device are zero;
        the parent device cannot be identified as a PCI/USB host
        controller: Wrong bus of the parent device.
        """
        parent_properties = self.usb_controller_pci_side['properties']
        parent_properties['info.bus'] = ('not pci', 'str')
        parser = SubmissionParser(self.log)
        parser.submission_key = 'USB device test 3'
        parser.buildHalDeviceList(self.parsed_data)
        device = parser.devices[self.UDI_USB_CONTROLLER_USB_SIDE]
        self.failIf(
            device.is_real_device,
            'Testing info.bus property: USB Device with vendor/product '
            'ID 0:0 property treated as a real device.')
        self.assertWarningMessage(
            parser.submission_key,
            'USB device found with vendor ID==0, product ID==0, where the '
            'parent device does not look like a USB host controller: '
            + self.UDI_USB_CONTROLLER_USB_SIDE)

        # All other devices which have an info.bus property return True
        # for HALDevice.is_real_device. The USB host controller in the
        # test data is an example.
        device = parser.devices[self.UDI_USB_CONTROLLER_PCI_SIDE]
        self.failUnless(
            device.is_real_device,
            'Testing info.bus property: Device with existing info.bus '
            'property not treated as a real device.')

        self.renameInfoBusToInfoSubsystem()
        parser.buildHalDeviceList(self.parsed_data)
        device = parser.devices[self.UDI_USB_CONTROLLER_USB_SIDE]
        self.failIf(
            device.is_real_device,
            'Testing info.subsystem property: USB Device with vendor/product '
            'ID 0:0 property treated as a real device.')
        self.assertWarningMessage(
            parser.submission_key,
            'USB device found with vendor ID==0, product ID==0, where the '
            'parent device does not look like a USB host controller: '
            + self.UDI_USB_CONTROLLER_USB_SIDE)

        device = parser.devices[self.UDI_USB_CONTROLLER_PCI_SIDE]
        self.failUnless(
            device.is_real_device,
            'Testing info.subsystem property: Device with existing info.bus '
            'property not treated as a real device.')


class TestUdevDevice(TestCaseHWDB):
    """Tests of class UdevDevice."""

    def setUp(self):
        """Setup the test environment."""
        super(TestUdevDevice, self).setUp()
        self.root_device = {
            'P': '/devices/LNXSYSTM:00',
            'E': {
                'UDEV_LOG': '3',
                'DEVPATH': '/devices/LNXSYSTM:00',
                'MODALIAS': 'acpi:LNXSYSTM:',
                'SUBSYSTEM': 'acpi',
                },
            'id': 1,
            }

        self.root_device_dmi_data = {
            '/sys/class/dmi/id/sys_vendor': 'FUJITSU SIEMENS',
            '/sys/class/dmi/id/product_name': 'LIFEBOOK E8210',
            }

        self.usb_device_data = {
            'P': '/devices/pci0000:00/0000:00:1d.1/usb3/3-2',
            'E': {
                'SUBSYSTEM': 'usb',
                'DEVTYPE': 'usb_device',
                'PRODUCT': '46d/a01/1013',
                'TYPE': '0/0/0',
                'DRIVER': 'usb',
                },
            }

        self.pci_pccard_bridge_path = (
            '/devices/pci0000:00/0000:00:1e.0/0000:08:03.0')
        self.pci_pccard_bridge = {
            'P': self.pci_pccard_bridge_path,
            'E': {
                'DRIVER': 'yenta_cardbus',
                'PCI_CLASS': '60700',
                'PCI_ID': '1217:7134',
                'PCI_SUBSYS_ID': '10CF:131E',
                'PCI_SLOT_NAME': '0000:08:03.0',
                'SUBSYSTEM': 'pci',
                }
            }

        self.pccard_scsi_controller_path = (
            '/devices/pci0000:00/0000:00:1e.0/0000:08:03.0/0000:09:00.0')
        self.pccard_scsi_controller_data = {
            'P': self.pccard_scsi_controller_path,
            'E': {
                'DRIVER': 'aic7xxx',
                'PCI_CLASS': '10000',
                'PCI_ID': '9004:6075',
                'PCI_SUBSYS_ID': '9004:7560',
                'SUBSYSTEM': 'pci',
                },
            }

        self.pci_scsi_controller_scsi_side_1 = {
            'P': ('/devices/pci0000:00/0000:00:1e.0/0000:08:03.0/'
                  '0000:09:00.0/host6'),
            'E': {
                'DEVTYPE': 'scsi_host',
                'SUBSYSTEM': 'scsi',
                },
            }

        self.pci_bridge_pccard_hierarchy_data = [
            {'udev_data': self.root_device},
            {'udev_data': self.pci_pccard_bridge},
            {'udev_data': self.pccard_scsi_controller_data},
            ]

        self.pci_scsi_controller_scsi_side_2 = {
            'P': ('/devices/pci0000:00/0000:00:1e.0/0000:08:03.0/'
                  '0000:09:00.0/host6/scsi_host/host6'),
            'E': {
                'SUBSYSTEM': 'scsi_host',
                },
            }

        self.scsi_scanner_target_data = {
            'P': ('/devices/pci0000:00/0000:00:1e.0/0000:08:03.0/'
                  '0000:09:00.0/host6/target6:0:1'),
            'E': {
                'DEVTYPE': 'scsi_target',
                'SUBSYSTEM': 'scsi'
                },
            }

        self.scsi_scanner_device_path = (
            '/devices/pci0000:00/0000:00:1e.0/0000:08:03.0/0000:09:00.0/'
            'host6/target6:0:1/6:0:1:0')
        self.scsi_scanner_device_data = {
            'P': self.scsi_scanner_device_path,
            'E': {
                'DEVTYPE': 'scsi_device',
                'SUBSYSTEM': 'scsi',
                },
            }

        self.scsi_scanner_device_sysfs_data = {
            'vendor': 'FUJITSU',
            'model': 'fi-5120Cdj',
            'type': '6',
            }

        self.scsi_scanner_device_data_2 = {
            'P': ('/devices/pci0000:00/0000:00:1e.0/0000:08:03.0/'
                  '0000:09:00.0/host6/target6:0:1/6:0:1:0/scsi_device/'
                  '6:0:1:0'),
            'E': {
                'SUBSYSTEM': 'scsi_device',
                },
        }

        self.scsi_scanner_scsi_generic = {
            'P': ('/devices/pci0000:00/0000:00:1e.0/0000:08:03.0/'
                  '0000:09:00.0/host6/target6:0:1/6:0:1:0/scsi_generic/sg2'),
            'E': {
                'SUBSYSTEM': 'scsi_generic',
                },
            }

        self.scsi_scanner_spi = {
            'P': ('/devices/pci0000:00/0000:00:1e.0/0000:08:03.0/'
                  '0000:09:00.0/host6/target6:0:1/spi_transport/target6:0:1'),
            'E': {
                'SUBSYSTEM': 'spi_transport',
                },
            }

        self.scsi_device_hierarchy_data = [
            {'udev_data': self.pccard_scsi_controller_data},
            {'udev_data': self.pci_scsi_controller_scsi_side_1},
            {'udev_data': self.pci_scsi_controller_scsi_side_2},
            {'udev_data': self.scsi_scanner_target_data},
            {
                'udev_data': self.scsi_scanner_device_data,
                'sysfs_data': self.scsi_scanner_device_sysfs_data,
                },
            {'udev_data': self.scsi_scanner_device_data_2},
            {'udev_data': self.scsi_scanner_scsi_generic},
            {'udev_data': self.scsi_scanner_spi},
            ]

        self.pci_ide_controller_path = '/devices/pci0000:00/0000:00:1f.1'
        self.pci_ide_controller = {
            'P': self.pci_ide_controller_path,
            'E': {
                'DRIVER': 'ata_piix',
                'PCI_CLASS': '1018A',
                'PCI_ID': '8086:27DF',
                'PCI_SUBSYS_ID': '10CF:1385',
                'SUBSYSTEM': 'pci',
                },
            }

        self.pci_ide_controller_scsi_side_1 = {
            'P': '/devices/pci0000:00/0000:00:1f.1/host4',
            'E': {
                'DEVTYPE': 'scsi_host',
                'SUBSYSTEM': 'scsi',
                },
            }

        self.pci_ide_controller_scsi_side_2 = {
            'P': '/devices/pci0000:00/0000:00:1f.1/host4/scsi_host/host4',
            'E': {
                'SUBSYSTEM': 'scsi_host',
                },
            }

        self.ide_device_target_data = {
            'P': '/devices/pci0000:00/0000:00:1f.1/host4/target4:0:0',
            'E': {
                'DEVTYPE': 'scsi_target',
                'SUBSYSTEM': 'scsi',
                },
            }

        self.ide_cdrom_device_path = (
            '/devices/pci0000:00/0000:00:1f.1/host4/target4:0:0/4:0:0:0')
        self.ide_cdrom_device_data = {
             'P': self.ide_cdrom_device_path,
             'E': {
                 'SUBSYSTEM': 'scsi',
                 'DEVTYPE': 'scsi_device',
                 'DRIVER': 'sr',
                 },
             }

        self.ide_cdrom_device_sysfs_data = {
             'vendor': 'MATSHITA',
             'model': 'DVD-RAM UJ-841S',
             'type': '5',
             }

        self.ide_cdrom_sr_data = {
            'P': ('/devices/pci0000:00/0000:00:1f.1/host4/target4:0:0/'
                  '4:0:0:0/block/sr0'),
            'E': {
                'DEVTYPE': 'disk',
                'SUBSYSTEM': 'block',
                },
            }

        self.ide_cdrom_device_data_2 = {
            'P': ('/devices/pci0000:00/0000:00:1f.1/host4/target4:0:0/'
                  '4:0:0:0/scsi_device/4:0:0:0'),
            'E': {
                'SUBSYSTEM': 'scsi_device',
                },
            }

        self.ide_cdrom_scsi_generic_data = {
            'P': ('/devices/pci0000:00/0000:00:1f.1/host4/target4:0:0/'
                  '4:0:0:0/scsi_generic/sg1'),
            'E': {
                'SUBSYSTEM': 'scsi_generic',
                },
            }

        self.ide_device_hierarchy_data = [
            {'udev_data': self.pci_ide_controller},
            {'udev_data': self.pci_ide_controller_scsi_side_1},
            {'udev_data': self.pci_ide_controller_scsi_side_2},
            {'udev_data': self.ide_device_target_data},
            {
                'udev_data': self.ide_cdrom_device_data,
                'sysfs_data': self.ide_cdrom_device_sysfs_data,
                },
            {'udev_data': self.ide_cdrom_sr_data},
            {'udev_data': self.ide_cdrom_device_data_2},
            {'udev_data': self.ide_cdrom_scsi_generic_data},
            ]

        self.pci_sata_controller_path = '/devices/pci0000:00/0000:00:1f.2'
        self.pci_sata_controller = {
            'P': self.pci_sata_controller_path,
            'E': {
                'PCI_CLASS': '10602',
                'PCI_ID': '8086:27C5',
                'PCI_SUBSYS_ID': '10CF:1387',
                'PCI_SLOT_NAME': '0000:00:1f.2',
                'SUBSYSTEM': 'pci',
                'DRIVER': 'ahci',
                }
            }

        self.pci_sata_controller_scsi_side_1 = {
            'P': '/devices/pci0000:00/0000:00:1f.2/host0',
            'E': {
                'DEVTYPE': 'scsi_host',
                'SUBSYSTEM': 'scsi',
                },
            }

        self.pci_sata_controller_scsi_side_2 = {
            'P': '/devices/pci0000:00/0000:00:1f.2/host0/scsi_host/host0',
            'E': {
                'SUBSYSTEM': 'scsi_host',
                },
            }

        self.sata_disk_target_data = {
            'P': '/devices/pci0000:00/0000:00:1f.2/host0/target0:0:0',
            'E': {
                'DEVTYPE': 'scsi_target',
                'SUBSYSTEM': 'scsi',
                },
            }

        self.sata_disk_device_path = (
            '/devices/pci0000:00/0000:00:1f.2/host0/target0:0:0/0:0:0:0')
        self.sata_disk_device_data = {
            'P': self.sata_disk_device_path,
            'E': {
                'DEVTYPE': 'scsi_device',
                'DRIVER': 'sd',
                'SUBSYSTEM': 'scsi',
                },
            }

        self.sata_disk_device_sysfs_data = {
            'vendor': 'ATA',
            'model': 'Hitachi HTS54251',
            'type': '0',
            }

        self.sata_disk_device_data_2 = {
            'P': ('/devices/pci0000:00/0000:00:1f.2/host0/target0:0:0/'
                  '0:0:0:0/scsi_device/0:0:0:0'),
            'E': {
                'SUBSYSTEM': 'scsi_device',
                },
            }

        self.sata_disk_device_scsi_disk_data = {
            'P': ('/devices/pci0000:00/0000:00:1f.2/host0/target0:0:0/'
                  '0:0:0:0/scsi_disk/0:0:0:0'),
            'E': {
                'SUBSYSTEM': 'scsi_disk',
                },
            }

        self.sata_disk_device_scsi_generic_data = {
            'P': ('/devices/pci0000:00/0000:00:1f.2/host0/target0:0:0/'
                  '0:0:0:0/scsi_generic/sg0'),
            'E': {
                'SUBSYSTEM': 'scsi_generic'
                },
            }

        self.sata_disk_block_data = {
            'P': ('/devices/pci0000:00/0000:00:1f.2/host0/target0:0:0/'
                  '0:0:0:0/block/sda'),
            'E': {
                'DEVTYPE': 'disk',
                'SUBSYSTEM': 'block',
                },
            }

        self.sata_disk_partition_data = {
            'P': ('/devices/pci0000:00/0000:00:1f.2/host0/target0:0:0/'
                  '0:0:0:0/block/sda/sda1'),
            'E': {
                'DEVTYPE': 'partition',
                'SUBSYSTEM': 'block',
                },
            }

        self.sata_device_hierarchy_data = [
            {'udev_data': self.pci_sata_controller},
            {'udev_data': self.pci_sata_controller_scsi_side_1},
            {'udev_data': self.pci_sata_controller_scsi_side_2},
            {'udev_data': self.sata_disk_target_data},
            {'udev_data': self.sata_disk_device_data},
            {
                'udev_data': self.sata_disk_device_data,
                'sysfs_data': self.sata_disk_device_sysfs_data,
                },
            {'udev_data': self.sata_disk_device_data_2},
            {'udev_data': self.sata_disk_device_scsi_disk_data},
            {'udev_data': self.sata_disk_device_scsi_generic_data},
            {'udev_data': self.sata_disk_block_data},
            {'udev_data': self.sata_disk_partition_data},
             ]

        self.usb_storage_usb_device_path = (
            '/devices/pci0000:00/0000:00:1d.7/usb1/1-1')
        self.usb_storage_usb_device_data = {
            'P': self.usb_storage_usb_device_path,
            'E': {
                'DEVTYPE': 'usb_device',
                'DRIVER': 'usb',
                'PRODUCT': '1307/163/100',
                'TYPE': '0/0/0',
                'SUBSYSTEM': 'usb',
                },
            }

        self.usb_storage_usb_interface = {
            'P': '/devices/pci0000:00/0000:00:1d.7/usb1/1-1/1-1:1.0',
            'E': {
                'DRIVER': 'usb-storage',
                'PRODUCT': '1307/163/100',
                'TYPE': '0/0/0',
                'INTERFACE': '8/6/80',
                'DEVTYPE': 'usb_interface',
                'SUBSYSTEM': 'usb',
                },
            }

        self.usb_storage_scsi_host_1 = {
            'P': '/devices/pci0000:00/0000:00:1d.7/usb1/1-1/1-1:1.0/host7',
            'E': {
                'DEVTYPE': 'scsi_host',
                'SUBSYSTEM': 'scsi',
                },
            }

        self.usb_storage_scsi_host_2 = {
            'P': ('/devices/pci0000:00/0000:00:1d.7/usb1/1-1/1-1:1.0/host7/'
                  'scsi_host/host7'),
            'E': {
                'SUBSYSTEM': 'scsi_host',
                },
            }

        self.usb_storage_scsi_target = {
            'P': ('/devices/pci0000:00/0000:00:1d.7/usb1/1-1/1-1:1.0/host7/'
                  'target7:0:0'),
            'E': {
                'DEVTYPE': 'scsi_target',
                'SUBSYSTEM': 'scsi',
                },
            }

        self.usb_storage_scsi_device_path = (
            '/devices/pci0000:00/0000:00:1d.7/usb1/1-1/1-1:1.0/host7/'
            'target7:0:0/7:0:0:0')
        self.usb_storage_scsi_device = {
            'P': self.usb_storage_scsi_device_path,
            'E': {
                'DEVTYPE': 'scsi_device',
                'DRIVER': 'sd',
                'SUBSYSTEM': 'scsi',
                },
            }

        self.usb_storage_scsi_device_sysfs = {
            'vendor': 'Ut163',
            'model': 'USB2FlashStorage',
            'type': '0',
            }

        self.usb_storage_scsi_device_2 = {
            'P': ('/devices/pci0000:00/0000:00:1d.7/usb1/1-1/1-1:1.0/host7/'
                  'target7:0:0/7:0:0:0/scsi_device/7:0:0:0'),
            'E': {
                'SUBSYSTEM': 'scsi_device',
                },
            }

        self.usb_storage_scsi_disk = {
            'P': ('/devices/pci0000:00/0000:00:1d.7/usb1/1-1/1-1:1.0/host7/'
                  'target7:0:0/7:0:0:0/scsi_disk/7:0:0:0'),
            'E': {
                'SUBSYSTEM': 'scsi_disk',
                },
            }

        self.usb_storage_scsi_generic = {
            'P': ('/devices/pci0000:00/0000:00:1d.7/usb1/1-1/1-1:1.0/host7/'
                  'target7:0:0/7:0:0:0/scsi_generic/sg3'),
            'E': {
                'SUBSYSTEM': 'scsi_generic',
                },
            }

        self.usb_storage_block_device_data = {
            'P': ('/devices/pci0000:00/0000:00:1d.7/usb1/1-1/1-1:1.0/host7/'
                  'target7:0:0/7:0:0:0/block/sdb'),
            'E': {
                'DEVTYPE': 'disk',
                'SUBSYSTEM': 'block',
                },
            }

        self.usb_storage_block_partition_data = {
            'P': ('/devices/pci0000:00/0000:00:1d.7/usb1/1-1/1-1:1.0/host7/'
                  'target7:0:0/7:0:0:0/block/sdb/sdb1'),
            'E': {
                'DEVTYPE': 'partition',
                'SUBSYSTEM': 'block',
                },
            }

        self.usb_storage_hierarchy_data = [
            {'udev_data': self.usb_storage_usb_device_data},
            {'udev_data': self.usb_storage_usb_interface},
            {'udev_data': self.usb_storage_scsi_host_1},
            {'udev_data': self.usb_storage_scsi_host_2},
            {'udev_data': self.usb_storage_scsi_target},
            {
                'udev_data': self.usb_storage_scsi_device,
                'sysfs_data': self.usb_storage_scsi_device_sysfs,
                },
            {'udev_data': self.usb_storage_scsi_device_2},
            {'udev_data': self.usb_storage_scsi_disk},
            {'udev_data': self.usb_storage_scsi_generic},
            {'udev_data': self.usb_storage_block_device_data},
            {'udev_data': self.usb_storage_block_partition_data},
            ]

        self.usb_hub_path = '/devices/pci0000:00/0000:00:1d.0/usb2'
        self.usb_hub = {
            'P': self.usb_hub_path,
            'E': {
                'DEVTYPE': 'usb_device',
                'DRIVER': 'usb',
                'PRODUCT': '0/0/0',
                'TYPE': '9/0/0',
                'SUBSYSTEM': 'usb',
                },
            }

        self.usb_hub_with_odd_parent_hierarchy_data = [
            {'udev_data': self.root_device},
            {'udev_data': self.usb_hub},
            ]

        self.no_subsystem_device_data = {
            'P': '/devices/pnp0/00:00',
            'E': {}
            }

        self.cpu_device_data = {
            'P': '/devices/LNXSYSTM:00/LNXCPU:00',
            'E': {
                'DRIVER': 'processor',
                'SUBSYSTEM': 'acpi',
                },
            }

        self.platform_device_data = {
            'P': '/devices/platform/dock.0',
            'E': {
                'SUBSYSTEM': 'platform',
                },
            }

    def test_device_device_id(self):
        """Test of UdevDevice.device_id."""
        device = UdevDevice(None, self.pci_sata_controller)
        self.assertEqual(
            '/devices/pci0000:00/0000:00:1f.2', device.device_id,
            'Unexpected value of UdevDevice.device_id.')

    def test_root_device_ids(self):
        device = UdevDevice(
            None, self.root_device, None, self.root_device_dmi_data)
        self.assertEqual(
            {
                'vendor': 'FUJITSU SIEMENS',
                'product': 'LIFEBOOK E8210',
                },
            device.root_device_ids)

        device = UdevDevice(
            None, self.root_device, None, {})
        self.assertEqual(
            {
                'vendor': None,
                'product': None,
                },
            device.root_device_ids)

    def test_is_pci(self):
        """Test of UdevDevice.is_pci."""
        device = UdevDevice(None, self.pci_sata_controller)
        self.assertTrue(device.is_pci)

        device = UdevDevice(None, self.root_device)
        self.assertFalse(device.is_pci)

    def test_pci_class_info(self):
        """Test of UdevDevice.pci_class_info"""
        device = UdevDevice(None, self.pci_sata_controller)
        self.assertEqual(
            (1, 6, 2), device.pci_class_info,
            'Invalid value of UdevDevice.pci_class_info for PCI device.')

        device = UdevDevice(None, self.root_device)
        self.assertEqual(
            (None, None, None), device.pci_class_info,
            'Invalid value of UdevDevice.pci_class_info for Non-PCI device.')

    def test_pci_class(self):
        """Test of UdevDevice.pci_class"""
        device = UdevDevice(None, self.pci_sata_controller)
        self.assertEqual(
            1, device.pci_class,
            'Invalid value of UdevDevice.pci_class for PCI device.')

        device = UdevDevice(None, self.root_device)
        self.assertEqual(
            None, device.pci_class,
            'Invalid value of UdevDevice.pci_class for Non-PCI device.')

    def test_pci_subclass(self):
        """Test of UdevDevice.pci_subclass"""
        device = UdevDevice(None, self.pci_sata_controller)
        self.assertEqual(
            6, device.pci_subclass,
            'Invalid value of UdevDevice.pci_class for PCI device.')

        device = UdevDevice(None, self.root_device)
        self.assertEqual(
            None, device.pci_class,
            'Invalid value of UdevDevice.pci_class for Non-PCI device.')

    def test_pci_ids(self):
        """Test of UdevDevice.pci_ids"""
        device = UdevDevice(None, self.pci_sata_controller)
        self.assertEqual(
            {'vendor': 0x8086,
             'product': 0x27C5,
             },
            device.pci_ids,
            'Invalid value of UdevDevice.pci_ids for PCI device.')

        device = UdevDevice(None, self.usb_device_data)
        self.assertEqual(
            {'vendor': None,
             'product': None,
             },
            device.pci_ids,
            'Invalid value of UdevDevice.pci_ids for Non-PCI device.')

    def test_is_usb(self):
        """Test of UdevDevice.is_usb"""
        device = UdevDevice(None, self.usb_device_data)
        self.assertTrue(device.is_usb)

        device = UdevDevice(None, self.pci_sata_controller)
        self.assertFalse(device.is_usb)

    def test_usb_ids(self):
        """Test of UdevDevice.usb_ids"""
        device = UdevDevice(None, self.usb_device_data)
        self.assertEqual(
            {
                'vendor': 0x46d,
                'product': 0xa01,
                'version': 0x1013,
                },
            device.usb_ids,
            'Invalid value of UdevDevice.usb_ids for USB device.')

        device = UdevDevice(None, self.root_device)
        self.assertEqual(
            {
                'vendor': None,
                'product': None,
                'version': None,
                },
            device.usb_ids,
            'Invalid value of UdevDevice.usb_ids for Non-USB device.')

    def test_usb_vendor_id(self):
        """Test of UdevDevice.usb_vendor_id"""
        device = UdevDevice(None, self.usb_device_data)
        self.assertEqual(
            0x46d, device.usb_vendor_id,
            'Invalid value of UdevDevice.usb_vendor_id for USB device.')

        device = UdevDevice(None, self.root_device)
        self.assertEqual(
            None, device.usb_vendor_id,
            'Invalid value of UdevDevice.usb_vendor_id for Non-USB device.')

    def test_usb_product_id(self):
        """Test of UdevDevice.usb_product_id"""
        device = UdevDevice(None, self.usb_device_data)
        self.assertEqual(
            0xa01, device.usb_product_id,
            'Invalid value of UdevDevice.usb_product_id for USB device.')

        device = UdevDevice(None, self.root_device)
        self.assertEqual(
            None, device.usb_product_id,
            'Invalid value of UdevDevice.usb_product_id for Non-USB device.')

    def test_is_scsi_device(self):
        """Test of UdevDevice.is_scsi_device."""
        device = UdevDevice(
            None, self.scsi_scanner_device_data,
            self.scsi_scanner_device_sysfs_data)
        self.assertTrue(device.is_scsi_device)

        device = UdevDevice(None, self.root_device)
        self.assertFalse(device.is_scsi_device)

    def test_is_scsi_device__no_sysfs_data(self):
        """Test of UdevDevice.is_scsi_device.

        If there is no sysfs data for a real SCSI device, is it not
        considered as a real SCSI device.

        Reason: Without sysfs data, we don't know the vendor and
        model name, making it impossible to store data about the
        device in the database.
        """
        device = UdevDevice(
            None, self.scsi_scanner_device_data, None)
        self.assertFalse(device.is_scsi_device)

    def test_scsi_vendor(self):
        """Test of UdevDevice.scsi_vendor."""
        device = UdevDevice(
            None, self.scsi_scanner_device_data,
            self.scsi_scanner_device_sysfs_data)
        self.assertEqual('FUJITSU', device.scsi_vendor)
        device = UdevDevice(None, self.root_device)
        self.assertEqual(None, device.scsi_vendor)

    def test_scsi_model(self):
        """Test of UdevDevice.scsi_model."""
        device = UdevDevice(
            None, self.scsi_scanner_device_data,
            self.scsi_scanner_device_sysfs_data)
        self.assertEqual('fi-5120Cdj', device.scsi_model)

        device = UdevDevice(None, self.root_device)
        self.assertEqual(None, device.scsi_model)

    def test_raw_bus(self):
        """Test of UdevDevice.raw_bus."""
        device = UdevDevice(None, self.root_device)
        self.assertEqual(None, device.raw_bus)

        device = UdevDevice(None, self.pci_sata_controller)
        self.assertEqual('pci', device.raw_bus)

        device = UdevDevice(None, self.usb_device_data)
        self.assertEqual('usb_device', device.raw_bus)

        device = UdevDevice(None, self.no_subsystem_device_data)
        self.assertEqual(None, device.raw_bus)

    def test_is_root_device(self):
        """Test of UdevDevice.is_root_device."""
        device = UdevDevice(None, self.root_device)
        self.assertTrue(device.is_root_device)

        device = UdevDevice(None, self.pci_sata_controller)
        self.assertFalse(device.is_root_device)

    def test_getVendorOrProduct(self):
        """Test of UdevDevice.getVendorOrProduct()."""
        device = UdevDevice(
            None, self.root_device, None, self.root_device_dmi_data)
        self.assertEqual(
            'FUJITSU SIEMENS', device.getVendorOrProduct('vendor'))
        self.assertEqual(
            'LIFEBOOK E8210', device.getVendorOrProduct('product'))
        self.assertRaises(
            AssertionError, device.getVendorOrProduct, 'nonsense')

        device = UdevDevice(None, self.pci_sata_controller)
        self.assertEqual('Unknown', device.getVendorOrProduct('vendor'))
        self.assertEqual('Unknown', device.getVendorOrProduct('product'))

        device = UdevDevice(None, self.usb_device_data)
        self.assertEqual('Unknown', device.getVendorOrProduct('vendor'))
        self.assertEqual('Unknown', device.getVendorOrProduct('product'))

        device = UdevDevice(
            None, self.scsi_scanner_device_data,
            self.scsi_scanner_device_sysfs_data)
        self.assertEqual('FUJITSU', device.getVendorOrProduct('vendor'))
        self.assertEqual('fi-5120Cdj', device.getVendorOrProduct('product'))

        device = UdevDevice(None, self.no_subsystem_device_data)
        self.assertEqual(None, device.getVendorOrProduct('vendor'))
        self.assertEqual(None, device.getVendorOrProduct('product'))

    def test_vendor(self):
        """Test of UdevDevice.vendor."""
        device = UdevDevice(
            None, self.root_device, None, self.root_device_dmi_data)
        self.assertEqual('FUJITSU SIEMENS', device.vendor)

    def test_product(self):
        """Test of UdevDevice.product."""
        device = UdevDevice(
            None, self.root_device, None, self.root_device_dmi_data)
        self.assertEqual('LIFEBOOK E8210', device.product)

    def test_getVendorOrProductID(self):
        """Test of UdevDevice.getVendorOrProduct()."""
        device = UdevDevice(
            None, self.root_device, None, self.root_device_dmi_data)
        self.assertEqual(
            'FUJITSU SIEMENS', device.getVendorOrProductID('vendor'))
        self.assertEqual(
            'LIFEBOOK E8210', device.getVendorOrProductID('product'))
        self.assertRaises(
            AssertionError, device.getVendorOrProductID, 'nonsense')

        device = UdevDevice(None, self.pci_sata_controller)
        self.assertEqual(0x8086, device.getVendorOrProductID('vendor'))
        self.assertEqual(0x27C5, device.getVendorOrProductID('product'))

        device = UdevDevice(None, self.usb_device_data)
        self.assertEqual(0x46d, device.getVendorOrProductID('vendor'))
        self.assertEqual(0xa01, device.getVendorOrProductID('product'))

        device = UdevDevice(
            None, self.scsi_scanner_device_data,
            self.scsi_scanner_device_sysfs_data)
        self.assertEqual('FUJITSU', device.getVendorOrProductID('vendor'))
        self.assertEqual('fi-5120Cdj', device.getVendorOrProductID('product'))

        device = UdevDevice(
            None, self.no_subsystem_device_data)
        self.assertEqual(None, device.getVendorOrProductID('vendor'))
        self.assertEqual(None, device.getVendorOrProductID('product'))

    def test_vendor_id(self):
        """Test of UdevDevice.vendor_id."""
        device = UdevDevice(
            None, self.root_device, None, self.root_device_dmi_data)
        self.assertEqual('FUJITSU SIEMENS', device.vendor_id)

    def test_product_id(self):
        """Test of UdevDevice.product_id."""
        device = UdevDevice(
            None, self.root_device, None, self.root_device_dmi_data)
        self.assertEqual('LIFEBOOK E8210', device.product_id)

    def test_vendor_id_for_db(self):
        """Test of UdevDevice.vendor_id_for_db."""
        device = UdevDevice(
            None, self.root_device, None, self.root_device_dmi_data)
        self.assertEqual('FUJITSU SIEMENS', device.vendor_id_for_db)

        device = UdevDevice(None, self.pci_sata_controller)
        self.assertEqual('0x8086', device.vendor_id_for_db)

        device = UdevDevice(None, self.usb_device_data)
        self.assertEqual('0x046d', device.vendor_id_for_db)

        device = UdevDevice(
            None, self.scsi_scanner_device_data,
            self.scsi_scanner_device_sysfs_data)
        self.assertEqual('FUJITSU ', device.vendor_id_for_db)

    def test_product_id_for_db(self):
        """Test of UdevDevice.product_id_for_db."""
        device = UdevDevice(
            None, self.root_device, None, self.root_device_dmi_data)
        self.assertEqual('LIFEBOOK E8210', device.product_id_for_db)

        device = UdevDevice(None, self.pci_sata_controller)
        self.assertEqual('0x27c5', device.product_id_for_db)

        device = UdevDevice(None, self.usb_device_data)
        self.assertEqual('0x0a01', device.product_id_for_db)

        device = UdevDevice(
            None, self.scsi_scanner_device_data,
            self.scsi_scanner_device_sysfs_data)
        self.assertEqual('fi-5120Cdj      ', device.product_id_for_db)

    def test_driver_name(self):
        """Test of UdevDevice.driver_name."""
        device = UdevDevice(None, self.pci_sata_controller)
        self.assertEqual('ahci', device.driver_name)

        device = UdevDevice(
            None, self.root_device, None, self.root_device_dmi_data)
        self.assertEqual(None, device.driver_name)

    def buildUdevDeviceHierarchy(self, device_data, parser=None):
        """Build a UdevDevice hierarchy from device_data.

        :param device_data: A sequence of arguments that are passed
            to the UdevDevice constructor. Each element must be a
            dictionary that can be used as a **kwargs argument.

            Element N of the sequence is the parent of element N+1.
        :param parser: A SubmissionParser instance to be passed to
            the constructor of UdevDevice.
        """
        devices = {}
        for kwargs in device_data:
            device = UdevDevice(parser, **kwargs)
            devices[device.device_id] = device

        # Build the parent-child relations so that the parent device
        # is that device which has the longest path matching the
        # start of the child's path.
        #
        # There is one exception of this rule: The root device has
        # the path "/devices/LNXSYSTM:00", but the paths of most of
        # our test deviies start with "/devices/pci". Well patch the
        # index temporarily in order to find children of the root
        # device.
        if '/devices/LNXSYSTM:00' in devices:
            devices['/devices'] = devices['/devices/LNXSYSTM:00']
            del devices['/devices/LNXSYSTM:00']

        device_paths = sorted(devices, key=len, reverse=True)
        for path_index, path in enumerate(device_paths):
            for parent_path in device_paths[path_index + 1:]:
                if path.startswith(parent_path):
                    devices[parent_path].addChild(devices[path])
                    break
        if '/devices' in devices:
            devices['/devices/LNXSYSTM:00'] = devices['/devices']
            del devices['/devices']
        return devices

    def test_scsi_controller(self):
        """Test of UdevDevice.scsi_controller for a PCI controller."""
        devices = self.buildUdevDeviceHierarchy(
            self.scsi_device_hierarchy_data)
        controller = devices[self.pccard_scsi_controller_path]
        scsi_device = devices[self.scsi_scanner_device_path]
        self.assertEqual(controller, scsi_device.scsi_controller)

    def test_scsi_controller_insufficient_anchestors(self):
        """Test of UdevDevice.scsi_controller for a PCI controller.

        If a SCSI device does not have a sufficient number of ancestors,
        UdevDevice.scsi_controller returns None.
        """
        parser = SubmissionParser(self.log)
        parser.submission_key = 'UdevDevice.scsi_controller ancestor missing'
        devices = self.buildUdevDeviceHierarchy(
            self.scsi_device_hierarchy_data[1:], parser)
        scsi_device = devices[self.scsi_scanner_device_path]
        self.assertEqual(None, scsi_device.scsi_controller)
        self.assertWarningMessage(
            parser.submission_key,
            'Found a SCSI device without a sufficient number of ancestors: '
            '/devices/pci0000:00/0000:00:1e.0/0000:08:03.0/0000:09:00.0/'
            'host6/target6:0:1/6:0:1:0')

    def test_scsi_controller_no_scsi_device(self):
        """Test of UdevDevice.scsi_controller for a PCI controller.

        For non-SCSI devices, this property is None.
        """
        device = UdevDevice(None, self.pci_sata_controller)
        self.assertEqual(None, device.scsi_controller)

    def test_translateScsiBus_real_scsi_device(self):
        """Test of UdevDevice.translateScsiBus() with a real SCSI device."""
        devices = self.buildUdevDeviceHierarchy(
            self.scsi_device_hierarchy_data)
        scsi_device = devices[self.scsi_scanner_device_path]
        self.assertEqual(
            HWBus.SCSI, scsi_device.translateScsiBus())

    def test_translateScsiBus_ide_device(self):
        """Test of UdevDevice.translateScsiBus() with an IDE device."""
        devices = self.buildUdevDeviceHierarchy(
            self.ide_device_hierarchy_data)
        ide_device = devices[self.ide_cdrom_device_path]
        self.assertEqual(HWBus.IDE, ide_device.translateScsiBus())

    def test_translateScsiBus_usb_device(self):
        """Test of UdevDevice.translateScsiBus() with a USB device."""
        devices = self.buildUdevDeviceHierarchy(
            self.usb_storage_hierarchy_data)
        usb_scsi_device = devices[self.usb_storage_scsi_device_path]
        self.assertEqual(None, usb_scsi_device.translateScsiBus())

    def test_translateScsiBus_non_scsi_device(self):
        """Test of UdevDevice.translateScsiBus() for a non-SCSI device."""
        device = UdevDevice(None, self.root_device)
        self.assertEqual(None, device.translateScsiBus())

    def test_translatePciBus(self):
        """Test of UdevDevice.translatePciBus()."""
        devices = self.buildUdevDeviceHierarchy(
            self.pci_bridge_pccard_hierarchy_data)
        pci_device = devices[self.pci_pccard_bridge_path]
        pccard_device = devices[self.pccard_scsi_controller_path]
        self.assertEqual(HWBus.PCI, pci_device.translatePciBus())
        self.assertEqual(HWBus.PCCARD, pccard_device.translatePciBus())

    def test_real_bus_usb_device(self):
        """Test of UdevDevice.real_bus for a USB device."""
        usb_device = UdevDevice(None, self.usb_device_data)
        self.assertEqual(HWBus.USB, usb_device.real_bus)

    def test_real_bus_usb_interface(self):
        """Test of UdevDevice.real_bus for a USB interface."""
        parser = SubmissionParser(self.log)
        parser.submission_key = 'UdevDevice.real_bus for a not-real device'
        usb_interface = UdevDevice(parser, self.usb_storage_usb_interface)
        self.assertEqual(None, usb_interface.real_bus)
        # UdevDevice.real_bus should only be accessed for real devices,
        # which a USB is not. Hence we get a warning.
        self.assertWarningMessage(
            parser.submission_key,
            "Unknown bus 'usb_interface' for device "
            "/devices/pci0000:00/0000:00:1d.7/usb1/1-1/1-1:1.0")

    def test_real_bus_pci(self):
        """Test of UdevDevice.real_bus for PCI devices."""
        devices = self.buildUdevDeviceHierarchy(
            self.pci_bridge_pccard_hierarchy_data)
        pci_device = devices[self.pci_pccard_bridge_path]
        pccard_device = devices[self.pccard_scsi_controller_path]
        self.assertEqual(HWBus.PCI, pci_device.real_bus)
        self.assertEqual(HWBus.PCCARD, pccard_device.real_bus)

    def test_real_bus_scsi(self):
        """Test of UdevDevice.real_bus for a SCSI device."""
        devices = self.buildUdevDeviceHierarchy(
            self.scsi_device_hierarchy_data)
        scsi_device = devices[self.scsi_scanner_device_path]
        self.assertEqual(HWBus.SCSI, scsi_device.real_bus)

    def test_real_bus_system(self):
        """Test of UdevDevice.real_bus for a system."""
        root_device = UdevDevice(None, self.root_device)
        self.assertEqual(HWBus.SYSTEM, root_device.real_bus)

    def test_is_real_device_root_device(self):
        """Test of UdevDevice._is_real_device for the root device."""
        root_device = UdevDevice(None, self.root_device)
        self.assertTrue(root_device.is_real_device)

    def test_is_real_device_pci_device(self):
        """Test of UdevDevice._is_real_device for a PCI device."""
        pci_device = UdevDevice(None, self.pci_sata_controller)
        self.assertTrue(pci_device.is_real_device)

    def test_is_real_device_scsi_device_related_nodes(self):
        """Test of UdevDevice._is_real_device for SCSI related nodes.

        A SCSI device and its controller are represented by several
        nodes which describe different aspects. Only the controller
        itself and the node representing the SCSI device are
        considered to be real devices.
        """
        devices = self.buildUdevDeviceHierarchy(
            self.scsi_device_hierarchy_data)
        real_devices = (
            self.pccard_scsi_controller_path, self.scsi_scanner_device_path
            )
        for device in devices.values():
            self.assertEqual(
                device.device_id in real_devices, device.is_real_device,
                'Invalid result of UdevDevice.is_real_device for %s '
                'Expected %s, got %s'
                % (device.device_id, device.device_id in real_devices,
                   device.is_real_device))

    def test_is_real_device_ide_device_related_nodes(self):
        """Test of UdevDevice._is_real_device for IDE related nodes.

        An IDE device and its controller are represented by several
        nodes which describe different aspects. Only the controller
        itself and the node representing the IDE device are
        considered to be real devices.
        """
        devices = self.buildUdevDeviceHierarchy(
            self.ide_device_hierarchy_data)
        real_devices = (
            self.pci_ide_controller_path, self.ide_cdrom_device_path,
            )
        for device in devices.values():
            self.assertEqual(
                device.device_id in real_devices, device.is_real_device,
                'Invalid result of UdevDevice.is_real_device for %s '
                'Expected %s, got %s'
                % (device.device_id, device.device_id in real_devices,
                   device.is_real_device))

    def test_is_real_device_ata_device_related_nodes(self):
        """Test of UdevDevice._is_real_device for IDE related nodes.

        An IDE device and its controller are represented by several
        nodes which describe different aspects. Only the controller
        itself and the node representing the IDE device are
        considered to be real devices.
        """
        devices = self.buildUdevDeviceHierarchy(
            self.sata_device_hierarchy_data)
        real_devices = (
            self.pci_sata_controller_path, self.sata_disk_device_path,
            )
        for device in devices.values():
            self.assertEqual(
                device.device_id in real_devices, device.is_real_device,
                'Invalid result of UdevDevice.is_real_device for %s '
                'Expected %s, got %s'
                % (device.device_id, device.device_id in real_devices,
                   device.is_real_device))

    def test_is_real_device_usb_storage_device_related_nodes(self):
        """Test of UdevDevice._is_real_device for USB storage related nodes.

        A USB storage device is represented by several nodes which
        describe different aspects. Only the main USB device is
        considered to be real devices.
        """
        devices = self.buildUdevDeviceHierarchy(
            self.usb_storage_hierarchy_data)
        for device in devices.values():
            self.assertEqual(
                device.device_id == self.usb_storage_usb_device_path,
                device.is_real_device,
                'Invalid result of UdevDevice.is_real_device for %s '
                'Expected %s, got %s'
                % (device.device_id,
                   device.device_id == self.usb_storage_usb_device_path,
                   device.is_real_device))

    def test_is_real_device_usb_hub_with_odd_parent(self):
        """Test of UdevDevice._is_real_device for USB storage related nodes.

        If called for USB hub node with vendor ID == 0 and product_id == 0
        which is not the child of a PCI device, we get a warning.
        """
        parser = SubmissionParser(self.log)
        parser.submission_key = (
            'UdevDevice.is_real_device, USB hub with odd parent.')
        devices = self.buildUdevDeviceHierarchy(
            self.usb_hub_with_odd_parent_hierarchy_data, parser)
        usb_hub = devices[self.usb_hub_path]
        self.assertFalse(usb_hub.is_real_device)
        self.assertWarningMessage(
            parser.submission_key,
            'USB device found with vendor ID==0, product ID==0, '
            'where the parent device does not look like a USB '
            'host controller: %s' % self.usb_hub_path)

    def test_has_reliable_data_system(self):
        """Test of UdevDevice.has_reliable_data for a system."""
        root_device = UdevDevice(
            None, self.root_device, dmi_data=self.root_device_dmi_data)
        self.assertTrue(root_device.has_reliable_data)

    def test_has_reliable_data_system_no_vendor_name(self):
        """Test of UdevDevice.has_reliable_data for a system.

        If the DMI data does not provide vendor name, has_reliable_data
        is False.
        """
        del self.root_device_dmi_data['/sys/class/dmi/id/sys_vendor']
        root_device = UdevDevice(
            None, self.root_device, dmi_data=self.root_device_dmi_data)
        parser = SubmissionParser(self.log)
        parser.submission_key = 'root device without vendor name'
        root_device.parser = parser
        self.assertFalse(root_device.has_reliable_data)
        self.assertWarningMessage(
            parser.submission_key,
            "A UdevDevice that is supposed to be a real device does not "
            "provide bus, vendor ID, product ID or product name: "
            "<DBItem HWBus.SYSTEM, (0) System> None 'LIFEBOOK E8210' "
            "'LIFEBOOK E8210' /devices/LNXSYSTM:00")

    def test_has_reliable_data_system_no_product_name(self):
        """Test of UdevDevice.has_reliable_data for a system.

        If the DMI data does not provide product name, has_reliable_data
        is False.
        """
        del self.root_device_dmi_data['/sys/class/dmi/id/product_name']
        root_device = UdevDevice(
            None, self.root_device, dmi_data=self.root_device_dmi_data)
        parser = SubmissionParser(self.log)
        parser.submission_key = 'root device without product name'
        root_device.parser = parser
        self.assertFalse(root_device.has_reliable_data)
        self.assertWarningMessage(
            parser.submission_key,
            "A UdevDevice that is supposed to be a real device does not "
            "provide bus, vendor ID, product ID or product name: "
            "<DBItem HWBus.SYSTEM, (0) System> 'FUJITSU SIEMENS' None None "
            "/devices/LNXSYSTM:00")

    def test_has_reliable_data_acpi_device(self):
        """Test of UdevDevice.has_reliable_data for an ACPI device.

        APCI devices are considered not to have reliable data. The only
        exception is the root device, see test_has_reliable_data_system.
        """
        acpi_device = UdevDevice(None, self.cpu_device_data)
        self.assertEqual('acpi', acpi_device.raw_bus)
        self.assertFalse(acpi_device.has_reliable_data)

    def test_has_reliable_data_platform_device(self):
        """Test of UdevDevice.has_reliable_data for a "platform" device.

        devices with raw_bus == 'platform' are considered not to have
        reliable data.
        """
        platform_device = UdevDevice(None, self.platform_device_data)
        self.assertFalse(platform_device.has_reliable_data)

    def test_has_reliable_data_pci_device(self):
        """Test of UdevDevice.has_reliable_data for a PCI device."""
        devices = self.buildUdevDeviceHierarchy(
            self.pci_bridge_pccard_hierarchy_data)
        pci_device = devices[self.pci_pccard_bridge_path]
        self.assertTrue(pci_device.has_reliable_data)

    def test_has_reliable_data_usb_device(self):
        """Test of UdevDevice.has_reliable_data for a USB device."""
        usb_device = UdevDevice(None, self.usb_storage_usb_device_data)
        self.assertTrue(usb_device.has_reliable_data)

    def test_has_reliable_data_scsi_device(self):
        """Test of UdevDevice.has_reliable_data for a SCSI device."""
        devices = self.buildUdevDeviceHierarchy(
            self.scsi_device_hierarchy_data)
        scsi_device = devices[self.scsi_scanner_device_path]
        self.assertTrue(scsi_device.has_reliable_data)

    def test_has_reliable_data_usb_interface_device(self):
        """Test of UdevDevice.has_reliable_data for a USB interface.

        UdevDevice.has_reliable_data should only be called for nodes
        where is_rel_device is True. If called for other nodes, we
        may get a warning because they do not provide reqired data,
        like a bus, vendor or product ID.
        """
        parser = SubmissionParser(self.log)
        parser.submission_key = (
            'UdevDevice.has_reliable_data for a USB interface')
        usb_interface = UdevDevice(parser, self.usb_storage_usb_interface)
        self.assertFalse(usb_interface.has_reliable_data)
        self.assertWarningMessage(
            parser.submission_key,
            'A UdevDevice that is supposed to be a real device does not '
            'provide bus, vendor ID, product ID or product name: None None '
            'None None /devices/pci0000:00/0000:00:1d.7/usb1/1-1/1-1:1.0')

    def test_warnings_not_suppressed(self):
        """Logging of warnings can be allowed."""
        parser = SubmissionParser(self.log)
        parser.submission_key = "log_with_warnings"
        parser._logWarning("This message is logged.")
        self.assertWarningMessage(
            parser.submission_key, "This message is logged.")

    def test_warnings_suppressed(self):
        """Logging of warnings can be suppressed."""
        number_of_existing_log_messages = len(self.handler.records)
        parser = SubmissionParser(self.log, record_warnings=False)
        parser.submission_key = "log_without_warnings"
        parser._logWarning("This message is not logged.")
        # No new warnings are recorded
        self.assertEqual(
            number_of_existing_log_messages, len(self.handler.records))

    def test_device_id(self):
        """Each UdevDevice has a property 'id'."""
        device = UdevDevice(None, self.root_device)
        self.assertEqual(1, device.id)


class TestHWDBSubmissionTablePopulation(TestCaseHWDB):
    """Tests of the HWDB popoluation with submitted data."""

    layer = LaunchpadZopelessLayer

    HAL_COMPUTER = {
        'id': 1,
        'udi': TestCaseHWDB.UDI_COMPUTER,
        'properties': {
            'system.hardware.vendor': ('Lenovo', 'str'),
            'system.hardware.product': ('T41', 'str'),
            'system.kernel.version': (TestCaseHWDB.KERNEL_VERSION, 'str'),
            },
        }

    HAL_PCI_PCCARD_BRIDGE = {
        'id': 2,
        'udi': TestCaseHWDB.UDI_PCI_PCCARD_BRIDGE,
        'properties': {
            'info.bus': ('pci', 'str'),
            'info.linux.driver': ('yenta_cardbus', 'str'),
            'info.parent': (TestCaseHWDB.UDI_COMPUTER, 'str'),
            'info.product': ('OZ711MP1/MS1 MemoryCardBus Controller', 'str'),
            'pci.device_class': (PCI_CLASS_BRIDGE, 'int'),
            'pci.device_subclass': (PCI_SUBCLASS_BRIDGE_CARDBUS, 'int'),
            'pci.vendor_id': (TestCaseHWDB.PCI_VENDOR_ID_INTEL, 'int'),
            'pci.product_id': (TestCaseHWDB.PCI_PROD_ID_PCI_PCCARD_BRIDGE,
                               'int'),
            },
        }

    HAL_PCCARD_DEVICE = {
        'id': 3,
        'udi': TestCaseHWDB.UDI_PCCARD_DEVICE,
        'properties': {
            'info.bus': ('pci', 'str'),
            'info.parent': (TestCaseHWDB.UDI_PCI_PCCARD_BRIDGE, 'str'),
            'info.product': ('ISL3890/ISL3886', 'str'),
            'pci.device_class': (PCI_CLASS_SERIALBUS_CONTROLLER, 'int'),
            'pci.device_subclass': (PCI_SUBCLASS_SERIALBUS_USB, 'int'),
            'pci.vendor_id': (TestCaseHWDB.PCI_VENDOR_ID_INTEL, 'int'),
            'pci.product_id': (TestCaseHWDB.PCI_PROD_ID_PCCARD_DEVICE, 'int'),
            },
        }

    HAL_USB_CONTROLLER_PCI_SIDE = {
        'id': 4,
        'udi': TestCaseHWDB.UDI_USB_CONTROLLER_PCI_SIDE,
        'properties': {
            'info.bus': ('pci', 'str'),
            'info.linux.driver': ('ehci_hcd', 'str'),
            'info.parent': (TestCaseHWDB.UDI_COMPUTER, 'str'),
            'info.product': ('82801G (ICH7 Family) USB2 EHCI Controller',
                             'str'),
            'pci.device_class': (PCI_CLASS_SERIALBUS_CONTROLLER, 'int'),
            'pci.device_subclass': (PCI_SUBCLASS_SERIALBUS_USB, 'int'),
            'pci.vendor_id': (TestCaseHWDB.PCI_VENDOR_ID_INTEL, 'int'),
            'pci.product_id': (TestCaseHWDB.PCI_PROD_ID_USB_CONTROLLER,
                               'int'),
            },
        }

    HAL_USB_CONTROLLER_USB_SIDE = {
        'id': 5,
        'udi': TestCaseHWDB.UDI_USB_CONTROLLER_USB_SIDE,
        'properties': {
            'info.bus': ('usb_device', 'str'),
            'info.linux.driver': ('usb', 'str'),
            'info.parent': (TestCaseHWDB.UDI_USB_CONTROLLER_PCI_SIDE, 'str'),
            'info.product': ('EHCI Host Controller', 'str'),
            'usb_device.vendor_id': (0, 'int'),
            'usb_device.product_id': (0, 'int'),
            },
        }

    HAL_USB_STORAGE_DEVICE = {
        'id': 6,
        'udi': TestCaseHWDB.UDI_USB_STORAGE,
        'properties': {
            'info.bus': ('usb_device', 'str'),
            'info.linux.driver': ('usb', 'str'),
            'info.parent': (TestCaseHWDB.UDI_USB_CONTROLLER_USB_SIDE, 'str'),
            'info.product': ('USB Mass Storage Device', 'str'),
            'usb_device.vendor_id': (TestCaseHWDB.USB_VENDOR_ID_USBEST,
                                     'int'),
            'usb_device.product_id': (
                TestCaseHWDB.USB_PROD_ID_USBBEST_MEMSTICK, 'int'),
            },
        }

    HAL_SCSI_CONTROLLER_PCI_SIDE = {
        'id': 7,
        'udi': TestCaseHWDB.UDI_SCSI_CONTROLLER_PCI_SIDE,
        'properties': {
            'info.bus': ('pci', 'str'),
            'info.linux.driver': ('aic7xxx', 'str'),
            'info.parent': (TestCaseHWDB.UDI_COMPUTER, 'str'),
            'info.product': ('AIC-1480 / APA-1480', 'str'),
            'pci.device_class': (PCI_CLASS_STORAGE, 'int'),
            'pci.device_subclass': (TestCaseHWDB.PCI_SUBCLASS_STORAGE_SCSI,
                                    'int'),
            'pci.vendor_id': (TestCaseHWDB.PCI_VENDOR_ID_ADAPTEC, 'int'),
            'pci.product_id': (TestCaseHWDB.PCI_PROD_ID_AIC1480, 'int'),
            },
        }

    HAL_SCSI_CONTROLLER_SCSI_SIDE = {
        'id': 8,
        'udi': TestCaseHWDB.UDI_SCSI_CONTROLLER_SCSI_SIDE,
        'properties': {
            'info.bus': ('scsi_host', 'str'),
            'info.parent': (TestCaseHWDB.UDI_SCSI_CONTROLLER_PCI_SIDE, 'str'),
            'info.linux.driver': ('sd', 'str'),
            }
        }

    HAL_SCSI_STORAGE_DEVICE = {
        'id': 9,
        'udi': TestCaseHWDB.UDI_SCSI_DISK,
        'properties': {
            'info.bus': ('scsi', 'str'),
            'info.linux.driver': ('sd', 'str'),
            'info.parent': (TestCaseHWDB.UDI_SCSI_CONTROLLER_SCSI_SIDE,
                            'str'),
            'scsi.vendor': ('WDC', 'str'),
            'scsi.model': ('WD12345678', 'str'),
            },
        }

    parsed_data = {
        'hardware': {
            'hal': {},
            },
        'software': {
            'packages': {
                TestCaseHWDB.KERNEL_PACKAGE: {},
                },
            },
        }

    def setUp(self):
        """Setup the test environment."""
        super(TestHWDBSubmissionTablePopulation, self).setUp()
        self.log = logging.getLogger('test_hwdb_submission_parser')
        self.log.setLevel(logging.INFO)
        self.handler = Handler(self)
        self.handler.add(self.log.name)
        switch_dbuser('hwdb-submission-processor')

    def getLogData(self):
        messages = [record.getMessage() for record in self.handler.records]
        return '\n'.join(messages)

    def setHALDevices(self, devices):
        self.parsed_data['hardware']['hal']['devices'] = devices

    def testGetDriverNoDriverInfo(self):
        """Test of HALDevice.getDriver()."""
        devices = [
            self.HAL_COMPUTER,
            ]
        self.setHALDevices(devices)
        parser = SubmissionParser(self.log)
        parser.buildDeviceList(self.parsed_data)
        device = parser.devices[self.UDI_COMPUTER]
        self.assertEqual(device.getDriver(), None,
            'HALDevice.getDriver found a driver where none is expected.')

    def testGetDriverWithDriverInfo(self):
        """Test of HALDevice.getDriver()."""
        devices = [
            self.HAL_COMPUTER,
            self.HAL_PCI_PCCARD_BRIDGE,
            ]
        self.setHALDevices(devices)
        parser = SubmissionParser(self.log)
        parser.parsed_data = self.parsed_data
        parser.buildDeviceList(self.parsed_data)
        device = parser.devices[self.UDI_PCI_PCCARD_BRIDGE]
        driver = device.getDriver()
        self.assertNotEqual(driver, None,
            'HALDevice.getDriver did not find a driver where one '
            'is expected.')
        self.assertEqual(driver.name, 'yenta_cardbus',
            'Unexpected result for driver.name. Got %r, expected '
            'yenta_cardbus.' % driver.name)
        self.assertEqual(driver.package_name, self.KERNEL_PACKAGE,
            'Unexpected result for driver.package_name. Got %r, expected '
            'linux-image-2.6.24-19-generic' % driver.name)

    def testEnsureVendorIDVendorNameExistsRegularCase(self):
        """Test of ensureVendorIDVendorNameExists(self), regular case."""
        devices = [
            self.HAL_COMPUTER,
            ]
        self.setHALDevices(devices)
        parser = SubmissionParser(self.log)
        parser.parsed_data = self.parsed_data
        parser.buildDeviceList(self.parsed_data)

        # The database does not know yet about the vendor name
        # 'Lenovo'...
        vendor_name_set = getUtility(IHWVendorNameSet)
        vendor_name = vendor_name_set.getByName('Lenovo')
        self.assertEqual(vendor_name, None,
                         'Expected None looking up vendor name "Lenovo" in '
                         'HWVendorName, got %r.' % vendor_name)

        # ...as well as the vendor ID (which is identical to the vendor
        # name for systems).
        vendor_id_set = getUtility(IHWVendorIDSet)
        vendor_id = vendor_id_set.getByBusAndVendorID(HWBus.SYSTEM, 'Lenovo')
        self.assertEqual(vendor_id, None,
                         'Expected None looking up vendor ID "Lenovo" in '
                         'HWVendorID, got %r.' % vendor_id)

        # HALDevice.ensureVendorIDVendorNameExists() creates these
        # records.
        hal_system = parser.devices[self.UDI_COMPUTER]
        hal_system.ensureVendorIDVendorNameExists()

        vendor_name = vendor_name_set.getByName('Lenovo')
        self.assertEqual(vendor_name.name, 'Lenovo',
                         'Expected to find vendor name "Lenovo" in '
                         'HWVendorName, got %r.' % vendor_name.name)

        vendor_id = vendor_id_set.getByBusAndVendorID(HWBus.SYSTEM, 'Lenovo')
        self.assertEqual(vendor_id.vendor_id_for_bus, 'Lenovo',
                         'Expected "Lenovo" as vendor_id_for_bus, '
                         'got %r.' % vendor_id.vendor_id_for_bus)
        self.assertEqual(vendor_id.bus, HWBus.SYSTEM,
                         'Expected HWBUS.SYSTEM as bus, got %s.'
                         % vendor_id.bus.title)

    def runTestEnsureVendorIDVendorNameExistsVendorNameUnknown(
        self, devices, test_bus, test_vendor_id, test_udi):
        """Test of ensureVendorIDVendorNameExists(self), special case.

        A HWVendorID record is not created by
        HALDevice.ensureVendorIDVendorNameExists for certain buses.
        """
        self.setHALDevices(devices)
        parser = SubmissionParser(self.log)
        parser.parsed_data = self.parsed_data
        parser.buildDeviceList(self.parsed_data)

        hal_device = parser.devices[test_udi]
        hal_device.ensureVendorIDVendorNameExists()

        vendor_id_set = getUtility(IHWVendorIDSet)
        vendor_id = vendor_id_set.getByBusAndVendorID(
            test_bus, test_vendor_id)
        self.assertEqual(vendor_id, None,
            'Expected None looking up vendor ID %s for bus %s in HWVendorID, '
            'got %r.' % (test_vendor_id, test_bus.title, vendor_id))

    def testEnsureVendorIDVendorNameExistsVendorPCI(self):
        """Test of ensureVendorIDVendorNameExists(self), PCI bus."""
        devices = [
            self.HAL_COMPUTER,
            self.HAL_PCI_PCCARD_BRIDGE
            ]
        self.runTestEnsureVendorIDVendorNameExistsVendorNameUnknown(
            devices, HWBus.PCI, '0x8086', self.UDI_PCI_PCCARD_BRIDGE)

    def testEnsureVendorIDVendorNameExistsVendorPCCARD(self):
        """Test of ensureVendorIDVendorNameExists(self), PCCARD bus."""
        devices = [
            self.HAL_COMPUTER,
            self.HAL_PCI_PCCARD_BRIDGE,
            self.HAL_PCCARD_DEVICE,
            ]
        self.runTestEnsureVendorIDVendorNameExistsVendorNameUnknown(
            devices, HWBus.PCCARD, '0x8086', self.UDI_PCCARD_DEVICE)

    def testEnsureVendorIDVendorNameExistVendorUSB(self):
        """Test of ensureVendorIDVendorNameExists(self), USB bus."""
        devices = [
            self.HAL_COMPUTER,
            self.HAL_USB_CONTROLLER_PCI_SIDE,
            self.HAL_USB_CONTROLLER_USB_SIDE,
            self.HAL_USB_STORAGE_DEVICE,
            ]
        self.runTestEnsureVendorIDVendorNameExistsVendorNameUnknown(
            devices, HWBus.USB, '0x1307', self.UDI_USB_STORAGE)

    def testEnsureVendorIDVendorNameExistVendorSCSI(self):
        """Test of ensureVendorIDVendorNameExists(self), SCSI bus."""
        devices = [
            self.HAL_COMPUTER,
            self.HAL_SCSI_CONTROLLER_PCI_SIDE,
            self.HAL_SCSI_CONTROLLER_SCSI_SIDE,
            self.HAL_SCSI_STORAGE_DEVICE,
            ]

        self.setHALDevices(devices)
        parser = SubmissionParser(self.log)
        parser.parsed_data = self.parsed_data
        parser.buildDeviceList(self.parsed_data)

        # The database does not know yet about the vendor name
        # 'WDC'...
        vendor_name_set = getUtility(IHWVendorNameSet)
        vendor_name = vendor_name_set.getByName('WDC')
        self.assertEqual(vendor_name, None,
                         'Expected None looking up vendor name "WDC" in '
                         'HWVendorName, got %r.' % vendor_name)

        # ...as well as the vendor ID (which is identical to the vendor
        # name for SCSI devices).
        vendor_id_set = getUtility(IHWVendorIDSet)
        # Note that we must provide a string with exactly 8 characters
        # as the vendor ID of a SCSI device.
        vendor_id = vendor_id_set.getByBusAndVendorID(HWBus.SCSI, 'WDC     ')
        self.assertEqual(vendor_id, None,
                         'Expected None looking up vendor ID "WDC     " in '
                         'HWVendorID for the SCSI bus, got %r.' % vendor_id)

        # HALDevice.ensureVendorIDVendorNameExists() creates these
        # records.
        scsi_disk = parser.devices[self.UDI_SCSI_DISK]
        scsi_disk.ensureVendorIDVendorNameExists()

        vendor_name = vendor_name_set.getByName('WDC')
        self.assertEqual(vendor_name.name, 'WDC',
                         'Expected to find vendor name "WDC" in '
                         'HWVendorName, got %r.' % vendor_name.name)

        vendor_id = vendor_id_set.getByBusAndVendorID(HWBus.SCSI, 'WDC     ')
        self.assertEqual(vendor_id.vendor_id_for_bus, 'WDC     ',
                         'Expected "WDC     " as vendor_id_for_bus, '
                         'got %r.' % vendor_id.vendor_id_for_bus)
        self.assertEqual(vendor_id.bus, HWBus.SCSI,
                         'Expected HWBUS.SCSI as bus, got %s.'
                         % vendor_id.bus.title)

    def testCreateDBDataForSimpleDevice(self):
        """Test of HALDevice.createDBData.

        Test for a HAL device without driver data.
        """
        devices = [
            self.HAL_COMPUTER,
            ]
        self.setHALDevices(devices)

        parser = SubmissionParser(self.log)
        parser.buildDeviceList(self.parsed_data)

        submission_set = getUtility(IHWSubmissionSet)
        submission = submission_set.getBySubmissionKey('test_submission_id_1')

        hal_device = parser.devices[self.UDI_COMPUTER]
        hal_device.createDBData(submission, None)

        # HALDevice.createDBData created a HWDevice record.
        vendor_id_set = getUtility(IHWVendorIDSet)
        vendor_id = vendor_id_set.getByBusAndVendorID(HWBus.SYSTEM, 'Lenovo')
        hw_device_set = getUtility(IHWDeviceSet)
        hw_device = hw_device_set.getByDeviceID(
            hal_device.real_bus, hal_device.vendor_id,
            hal_device.product_id)
        self.assertEqual(hw_device.bus_vendor, vendor_id,
            'Expected vendor ID (HWBus.SYSTEM, Lenovo) as the vendor ID, '
            'got %s %r' % (hw_device.bus_vendor.bus,
                           hw_device.bus_vendor.vendor_name.name))
        self.assertEqual(hw_device.bus_product_id, 'T41',
            'Expected product ID T41, got %r.' % hw_device.bus_product_id)
        self.assertEqual(hw_device.name, 'T41',
            'Expected device name T41, got %r.' % hw_device.name)

        # One HWDeviceDriverLink record is created...
        device_driver_link_set = getUtility(IHWDeviceDriverLinkSet)
        device_driver_link = device_driver_link_set.getByDeviceAndDriver(
            hw_device, None)
        self.assertEqual(device_driver_link.device, hw_device,
            'Expected HWDevice record for Lenovo T41 in HWDeviceDriverLink, '
            'got %s %r'
            % (device_driver_link.device.bus_vendor.bus,
               device_driver_link.device.bus_vendor.vendor_name.name))
        self.assertEqual(device_driver_link.driver, None,
            'Expected None as driver in HWDeviceDriverLink')

        # ...and one HWSubmissionDevice record linking the HWDeviceSriverLink
        # to the submission.
        submission_device_set = getUtility(IHWSubmissionDeviceSet)
        submission_devices = submission_device_set.getDevices(submission)
        self.assertEqual(len(list(submission_devices)), 1,
            'Unexpected number of submission devices: %i, expected 1.'
            % len(list(submission_devices)))
        submission_device = submission_devices[0]
        self.assertEqual(
            submission_device.device_driver_link, device_driver_link,
            'Invalid device_driver_link field in HWSubmissionDevice.')
        self.assertEqual(
            submission_device.parent, None,
            'Invalid parent field in HWSubmissionDevice.')
        self.assertEqual(
            submission_device.hal_device_id, 1,
            'Invalid haL-device_id field in HWSubmissionDevice.')

    def testCreateDBDataForDeviceWithOneDriver(self):
        """Test of HALDevice.createDBData.

        Test of a HAL device with one driver.
        """
        devices = [
            self.HAL_COMPUTER,
            self.HAL_PCI_PCCARD_BRIDGE,
            ]
        self.setHALDevices(devices)

        parser = SubmissionParser(self.log)
        parser.buildDeviceList(self.parsed_data)
        parser.parsed_data = self.parsed_data

        submission_set = getUtility(IHWSubmissionSet)
        submission = submission_set.getBySubmissionKey('test_submission_id_1')

        hal_root_device = parser.devices[self.UDI_COMPUTER]
        hal_root_device.createDBData(submission, None)

        # We now have a HWDevice record for the PCCard bridge...
        device_set = getUtility(IHWDeviceSet)
        pccard_bridge = device_set.getByDeviceID(
            HWBus.PCI, '0x%04x' % self.PCI_VENDOR_ID_INTEL,
            '0x%04x' % self.PCI_PROD_ID_PCI_PCCARD_BRIDGE)

        # ...and a HWDriver record for the yenta_cardbus driver.
        driver_set = getUtility(IHWDriverSet)
        yenta_driver = driver_set.getByPackageAndName(
            self.KERNEL_PACKAGE, 'yenta_cardbus')
        self.assertEqual(
            yenta_driver.name, 'yenta_cardbus',
            'Unexpected driver name: %r' % yenta_driver.name)
        self.assertEqual(
            yenta_driver.package_name, self.KERNEL_PACKAGE,
            'Unexpected package name: %r' % yenta_driver.package_name)

        # The PCCard bridge has one HWDeviceDriverLink record without
        # an associated driver...
        device_driver_link_set = getUtility(IHWDeviceDriverLinkSet)
        pccard_link_no_driver = device_driver_link_set.getByDeviceAndDriver(
            pccard_bridge, None)
        self.assertEqual(
            pccard_link_no_driver.device, pccard_bridge,
            'Unexpected value of pccard_link_no_driver.device')
        self.assertEqual(
            pccard_link_no_driver.driver, None,
            'Unexpected value of pccard_link_no_driver.driver')

        # ...and another one with the yenta driver.
        pccard_link_yenta = device_driver_link_set.getByDeviceAndDriver(
            pccard_bridge, yenta_driver)
        self.assertEqual(
            pccard_link_yenta.device, pccard_bridge,
            'Unexpected value of pccard_dd_link_yenta.device')
        self.assertEqual(
            pccard_link_yenta.driver, yenta_driver,
            'Unexpected value of pccard_dd_link_yenta.driver')

        # Finally, we have three HWSubmissionDevice records for this
        # submission: one for the computer itself, and two referring
        # to the HWDeviceDriverLink records for the PCCard bridge.

        submission_device_set = getUtility(IHWSubmissionDeviceSet)
        submission_devices = submission_device_set.getDevices(submission)
        (submitted_pccard_bridge_no_driver,
         submitted_pccard_bridge_yenta,
         submitted_system) = submission_devices

        self.assertEqual(
            submitted_pccard_bridge_no_driver.device_driver_link,
            pccard_link_no_driver,
            'Unexpected value of HWSubmissionDevice.device_driver_link for '
            'first submitted device')
        self.assertEqual(
            submitted_pccard_bridge_yenta.device_driver_link,
            pccard_link_yenta,
            'Unexpected value of HWSubmissionDevice.device_driver_link for '
            'second submitted device')

        # The parent field of the HWSubmisionDevice record represents
        # the device hiearchy.
        self.assertEqual(
            submitted_system.parent, None,
            'Unexpected value of HWSubmissionDevice.parent for the root '
            'node.')
        self.assertEqual(
            submitted_pccard_bridge_no_driver.parent, submitted_system,
            'Unexpected value of HWSubmissionDevice.parent for the '
            'PCCard bridge node without a driver.')
        self.assertEqual(
            submitted_pccard_bridge_yenta.parent,
            submitted_pccard_bridge_no_driver,
            'Unexpected value of HWSubmissionDevice.parent for the '
            'PCCard bridge node with the yenta driver.')

        # HWSubmissionDevice.hal_device_id stores the ID of the device
        # as defined in the submitted data.
        self.assertEqual(submitted_pccard_bridge_no_driver.hal_device_id, 2,
            'Unexpected value of HWSubmissionDevice.hal_device_id for the '
            'PCCard bridge node without a driver.')
        self.assertEqual(submitted_pccard_bridge_yenta.hal_device_id, 2,
            'Unexpected value of HWSubmissionDevice.hal_device_id for the '
            'PCCard bridge node with the yenta driver.')

    def testCreateDBDataForDeviceWithTwoDrivers(self):
        """Test of HALDevice.createDBData.

        Test for a HAL device with two drivers.
        """
        devices = [
            self.HAL_COMPUTER,
            self.HAL_USB_CONTROLLER_PCI_SIDE,
            self.HAL_USB_CONTROLLER_USB_SIDE
            ]
        self.setHALDevices(devices)

        parser = SubmissionParser(self.log)
        parser.buildDeviceList(self.parsed_data)
        parser.parsed_data = self.parsed_data

        submission_set = getUtility(IHWSubmissionSet)
        submission = submission_set.getBySubmissionKey('test_submission_id_1')

        hal_root_device = parser.devices[self.UDI_COMPUTER]
        hal_root_device.createDBData(submission, None)

        # The USB controller has a HWDevice record.
        device_set = getUtility(IHWDeviceSet)
        usb_controller = device_set.getByDeviceID(
            HWBus.PCI, '0x%04x' % self.PCI_VENDOR_ID_INTEL,
            '0x%04x' % self.PCI_PROD_ID_USB_CONTROLLER)

        # HWDriver records for the ehci_hcd and the usb driver were
        # created...
        driver_set = getUtility(IHWDriverSet)
        ehci_hcd_driver = driver_set.getByPackageAndName(
            self.KERNEL_PACKAGE, 'ehci_hcd')
        usb_driver = driver_set.getByPackageAndName(
            self.KERNEL_PACKAGE, 'usb')

        # ...as well as HWDeviceDriverLink records.
        device_driver_link_set = getUtility(IHWDeviceDriverLinkSet)
        usb_ctrl_link_no_driver = device_driver_link_set.getByDeviceAndDriver(
            usb_controller, None)
        usb_ctrl_link_ehci_hcd = device_driver_link_set.getByDeviceAndDriver(
            usb_controller, ehci_hcd_driver)
        usb_ctrl_link_usb = device_driver_link_set.getByDeviceAndDriver(
            usb_controller, usb_driver)

        # Three HWDeviceDriverLink records exist for the USB controller.
        submission_device_set = getUtility(IHWSubmissionDeviceSet)
        submission_devices = submission_device_set.getDevices(submission)
        (submitted_usb_controller_no_driver,
         submitted_usb_controller_ehci_hcd,
         submitted_usb_controller_usb,
         submitted_system) = submission_devices

        # The first record is for the controller without a driver...
        self.assertEqual(
            submitted_usb_controller_no_driver.device_driver_link,
            usb_ctrl_link_no_driver,
            'Unexpected value for '
            'submitted_usb_controller_no_driver.device_driver_link')

        # ...the second record for the controller and the ehci_hcd
        # driver...
        self.assertEqual(
            submitted_usb_controller_ehci_hcd.device_driver_link,
            usb_ctrl_link_ehci_hcd,
            'Unexpected value for '
            'submitted_usb_controller_ehci_hcd.device_driver_link')

        # ...and the third record is for the controller and the usb
        # driver.
        self.assertEqual(
            submitted_usb_controller_usb.device_driver_link,
            usb_ctrl_link_usb,
            'Unexpected value for '
            'submitted_usb_controller_usb.device_driver_link')

        # The first and second HWSubmissionDevice record are related to
        # the submitted HAL device node with the ID 4...
        self.assertEqual(
            submitted_usb_controller_no_driver.hal_device_id, 4,
            'Unexpected value for '
            'submitted_usb_controller_no_driver.hal_device_id')
        self.assertEqual(
            submitted_usb_controller_ehci_hcd.hal_device_id, 4,
            'Unexpected value for '
            'submitted_usb_controller_ehci_hcd.hal_device_id')

        # ...and the third HWSubmissionDevice record is related to
        # the submitted HAL device node with the ID 5.
        self.assertEqual(
            submitted_usb_controller_usb.hal_device_id, 5,
            'Unexpected value for '
            'submitted_usb_controller_usb.hal_device_id')

    def createSubmissionData(self, data, compress, submission_key,
                             private=False):
        """Create a submission."""
        if compress:
            data = bz2.compress(data)
        switch_dbuser('launchpad')
        submission = getUtility(IHWSubmissionSet).createSubmission(
            date_created=datetime(2007, 9, 9, tzinfo=pytz.timezone('UTC')),
            format=HWSubmissionFormat.VERSION_1,
            private=private,
            contactable=False,
            submission_key=submission_key,
            emailaddress=u'test@canonical.com',
            distroarchseries=None,
            raw_submission=StringIO(data),
            filename='hwinfo.xml',
            filesize=len(data),
            system_fingerprint='A Machine Name')
        switch_dbuser('hwdb-submission-processor')
        return submission

    def getSampleData(self, filename):
        """Return the submission data of a short valid submission."""
        sample_data_path = os.path.join(
            config.root, 'lib', 'lp', 'hardwaredb', 'scripts',
            'tests', 'simple_valid_hwdb_submission.xml')
        return open(sample_data_path).read()

    def assertSampleDeviceCreated(
        self, bus, vendor_id, product_id, driver_name, submission):
        """Assert that data for the device exists in HWDB tables."""
        device = getUtility(IHWDeviceSet).getByDeviceID(
            bus, vendor_id, product_id)
        self.assertNotEqual(
            device, None,
            'No entry in HWDevice found for bus %s, vendor %s, product %s'
            % (bus, vendor_id, product_id))
        # We have one device_driver_link entry without a driver for
        # each device...
        device_driver_link_set = getUtility(IHWDeviceDriverLinkSet)
        device_driver_link = device_driver_link_set.getByDeviceAndDriver(
            device, None)
        self.assertNotEqual(
            device_driver_link, None,
            'No driverless entry in HWDeviceDriverLink for bus %s, '
            'vendor %s, product %s'
            % (bus, vendor_id, product_id))
        #...and an associated HWSubmissionDevice record.
        submission_devices = getUtility(IHWSubmissionDeviceSet).getDevices(
            submission)
        device_driver_links_in_submission = [
            submission_device.device_driver_link
            for submission_device in submission_devices]
        self.failUnless(
            device_driver_link in device_driver_links_in_submission,
            'No entry in HWSubmissionDevice for bus %s, '
            'vendor %s, product %s, submission %s'
            % (bus, vendor_id, product_id, submission.submission_key))
        # If the submitted data mentioned a driver for this device,
        # we have also a HWDeviceDriverLink record for the (device,
        # driver) tuple.
        if driver_name is not None:
            driver = getUtility(IHWDriverSet).getByPackageAndName(
                self.KERNEL_PACKAGE, driver_name)
            self.assertNotEqual(
                driver, None,
                'No HWDriver record found for package %s, driver %s'
                % (self.KERNEL_PACKAGE, driver_name))
            device_driver_link = device_driver_link_set.getByDeviceAndDriver(
                device, driver)
            self.assertNotEqual(
                device_driver_link, None,
                'No entry in HWDeviceDriverLink for bus %s, '
                'vendor %s, product %s, driver %s'
                % (bus, vendor_id, product_id, driver_name))
            self.failUnless(
                device_driver_link in device_driver_links_in_submission,
                'No entry in HWSubmissionDevice for bus %s, '
                'vendor %s, product %s, driver %s, submission %s'
                % (bus, vendor_id, product_id, driver_name,
                   submission.submission_key))

    def assertAllSampleDevicesCreated(self, submission):
        """Assert that the devices from the sample submission are processed.

        The test data contains two devices: A system and a PCI device.
        The system has no associated drivers; the PCI device is
        associated with the ahci driver.
        """
        for bus, vendor_id, product_id, driver in (
            (HWBus.SYSTEM, 'FUJITSU SIEMENS', 'LIFEBOOK E8210', None),
            (HWBus.PCI, '0x8086', '0x27c5', 'ahci'),
            ):
            self.assertSampleDeviceCreated(
                bus, vendor_id, product_id, driver, submission)

    def testProcessSubmissionValidData(self):
        """Test of SubmissionParser.processSubmission().

        Regular case: Process valid compressed submission data.
        """
        submission_key = 'submission-1'
        submission_data = self.getSampleData(
            'simple_valid_hwdb_submission.xml')
        submission = self.createSubmissionData(
            submission_data, False, submission_key)
        parser = SubmissionParser(self.log)
        result = parser.processSubmission(submission)
        self.failUnless(result,
                        'Simple valid uncompressed submission could not be '
                        'processed. Logged errors:\n%s'
                        % self.getLogData())
        self.assertAllSampleDevicesCreated(submission)

    def testProcessSubmissionValidBzip2CompressedData(self):
        """Test of SubmissionParser.processSubmission().

        Regular case: Process valid compressed submission data.
        """
        submission_key = 'submission-2'
        submission_data = self.getSampleData(
            'simple_valid_hwdb_submission.xml')
        submission = self.createSubmissionData(
            submission_data, True, submission_key)
        parser = SubmissionParser(self.log)
        result = parser.processSubmission(submission)
        self.failUnless(result,
                        'Simple valid compressed submission could not be '
                        'processed. Logged errors:\n%s'
                        % self.getLogData())
        self.assertAllSampleDevicesCreated(submission)

    def testProcessSubmissionInvalidData(self):
        """Test of SubmissionParser.processSubmission().

        If a submission contains formally invalid data, it is rejected.
        """
        submission_key = 'submission-3'
        submission_data = """<?xml version="1.0" ?>
        <foo>
           This does not pass the RelaxNG validation.
        </foo>
        """
        submission = self.createSubmissionData(
            submission_data, True, submission_key)
        parser = SubmissionParser(self.log)
        result = parser.processSubmission(submission)
        self.failIf(result, 'Formally invalid submission treated as valid.')

    def testProcessSubmissionInconsistentData(self):
        """Test of SubmissionParser.processSubmission().

        If a submission contains inconsistent data, it is rejected.
        """
        submission_key = 'submission-4'
        submission_data = self.getSampleData(
            'simple_valid_hwdb_submission.xml')

        # The property "info.parent" of a HAL device node must
        # reference another existing device.
        submission_data = submission_data.replace(
            """<property name="info.parent" type="str">
          /org/freedesktop/Hal/devices/computer
        </property>""",
            """<property name="info.parent" type="str">
          /nonsense/udi
        </property>""")

        submission = self.createSubmissionData(
            submission_data, True, submission_key)
        parser = SubmissionParser(self.log)
        result = parser.processSubmission(submission)
        self.failIf(
            result, 'Submission with inconsistent data treated as valid.')

    def test_processSubmission_udev_data(self):
        """Test of SubmissionParser.processSubmission().

        Variant with udev data.
        """
        class MockSubmissionParser(SubmissionParser):
            """A variant that shortcuts parseSubmission().
            """
            def parseSubmission(self, submission, submission_key):
                """See `SubmissionParser`."""
                udev_root_device = {
                    'P': '/devices/LNXSYSTM:00',
                    'E': {'SUBSYSTEM': 'acpi'},
                    'id': 1,
                    }
                udev_pci_device = {
                    'P': '/devices/pci0000:00/0000:00:1f.2',
                    'E': {
                        'SUBSYSTEM': 'pci',
                        'PCI_CLASS': '10601',
                        'PCI_ID': '8086:27C5',
                        'PCI_SUBSYS_ID': '10CF:1387',
                        'PCI_SLOT_NAME': '0000:08:03.0',
                        },
                    'id': 2,
                    }
                root_device_dmi_data = {
                    '/sys/class/dmi/id/sys_vendor': 'FUJITSU SIEMENS',
                    '/sys/class/dmi/id/product_name': 'LIFEBOOK E8210',
                    }
                parsed_data = {
                    'hardware': {
                        'udev': [udev_root_device, udev_pci_device],
                        'sysfs-attributes': {},
                        'dmi': root_device_dmi_data,
                        'processors': [],
                        },
                    'software': {'packages': {}},
                    'questions': [],
                    }
                self.submission_key = submission_key
                return parsed_data

        validate_mock_class(MockSubmissionParser)

        submission_key = 'submission-with-udev-data'
        submission = self.createSubmissionData(
            'does not matter', False, submission_key)
        parser = MockSubmissionParser()

        self.assertTrue(parser.processSubmission(submission))

        device_set = getUtility(IHWDeviceSet)
        device_1 = device_set.getByDeviceID(HWBus.PCI, '0x8086', '0x27c5')
        self.assertEqual(HWBus.PCI, device_1.bus)
        self.assertEqual('0x8086', device_1.vendor_id)
        self.assertEqual('0x27c5', device_1.bus_product_id)

        device_2 = device_set.getByDeviceID(
            HWBus.SYSTEM, 'FUJITSU SIEMENS', 'LIFEBOOK E8210')
        self.assertEqual(HWBus.SYSTEM, device_2.bus)
        self.assertEqual('FUJITSU SIEMENS', device_2.vendor_id)
        self.assertEqual('LIFEBOOK E8210', device_2.bus_product_id)

        submission_device_set = getUtility(IHWSubmissionDeviceSet)
        submission_devices = submission_device_set.getDevices(submission)
        submission_device_1, submission_device_2 = submission_devices

        self.assertEqual(device_1, submission_device_1.device)
        self.assertEqual(submission_device_2, submission_device_1.parent)

        self.assertEqual(device_2, submission_device_2.device)
        self.assertIs(None, submission_device_2.parent)

    def test_processSubmission_buildDeviceList_failing(self):
        """Test of SubmissionParser.processSubmission().

        If the method buildDeviceList() fails for a submission, it is
        rejected.
        """
        def no(*args, **kw):
            return False

        submission_key = 'builddevicelist-fails'
        submission_data = self.getSampleData(
            'simple_valid_hwdb_submission.xml')
        submission = self.createSubmissionData(
            submission_data, False, submission_key)
        parser = SubmissionParser()
        parser.buildDeviceList = no
        self.assertFalse(parser.processSubmission(submission))

    def testProcessSubmissionRealData(self):
        """Test of SubmissionParser.processSubmission().

        Test with data from a real submission.
        """
        submission_data = self.getSampleData('real_hwdb_submission.xml.bz2')
        submission_key = 'submission-5'
        submission = self.createSubmissionData(
            submission_data, False, submission_key)
        parser = SubmissionParser(self.log)
        result = parser.processSubmission(submission)
        self.failUnless(
            result,
            'Real submission data not processed. Logged errors:\n%s'
            % self.getLogData())

    def test_root_device(self):
        """Test o SubmissionParser.root_device."""
        submission_parser = SubmissionParser()
        submission_parser.devices = {
            '/org/freedesktop/Hal/devices/computer': 'A HAL device',
            }
        self.assertEqual('A HAL device', submission_parser.root_device)

        submission_parser = SubmissionParser()
        submission_parser.devices = {
            '/devices/LNXSYSTM:00': 'A udev device',
            }
        self.assertEqual('A udev device', submission_parser.root_device)

    def testPendingSubmissionProcessing(self):
        """Test of process_pending_submissions().

        Run process_pending_submissions with three submissions; one
        of the submisisons contains invalid data.
        """
        # We have already one submisson with the status SUBMITTED in the
        # DB sample data; let's fill the associated Librarian file with
        # some test data.
        submission_set = getUtility(IHWSubmissionSet)
        submission = submission_set.getBySubmissionKey(
            'test_submission_id_1')
        submission_data = self.getSampleData(
            'simple_valid_hwdb_submission.xml')
        fillLibrarianFile(submission.raw_submission.id, submission_data)

        submission_data = self.getSampleData('real_hwdb_submission.xml.bz2')
        submission_key = 'submission-6'
        self.createSubmissionData(submission_data, False, submission_key)

        submission_key = 'private-submission'
        self.createSubmissionData(submission_data, False, submission_key,
                                  private=True)

        submission_key = 'submission-7'
        submission_data = """<?xml version="1.0" ?>
        <foo>
           This does not pass the RelaxNG validation.
        </foo>
        """
        self.createSubmissionData(submission_data, False, submission_key)
        process_pending_submissions(self.layer.txn, self.log)

        janitor = getUtility(ILaunchpadCelebrities).janitor
        valid_submissions = submission_set.getByStatus(
            HWSubmissionProcessingStatus.PROCESSED, user=janitor)
        valid_submission_keys = [
            submission.submission_key for submission in valid_submissions]
        self.assertEqual(
            valid_submission_keys,
            [u'test_submission_id_1', u'sample-submission', u'submission-6',
             u'private-submission'],
            'Unexpected set of valid submissions: %r' % valid_submission_keys)

        invalid_submissions = submission_set.getByStatus(
            HWSubmissionProcessingStatus.INVALID, user=janitor)
        invalid_submission_keys = [
            submission.submission_key for submission in invalid_submissions]
        self.assertEqual(
            invalid_submission_keys, [u'submission-7'],
            'Unexpected set of invalid submissions: %r'
            % invalid_submission_keys)

        new_submissions = submission_set.getByStatus(
            HWSubmissionProcessingStatus.SUBMITTED, user=janitor)
        new_submission_keys = [
            submission.submission_key for submission in new_submissions]
        self.assertEqual(
            new_submission_keys, [],
            'Unexpected set of new submissions: %r' % new_submission_keys)

        messages = [record.getMessage() for record in self.handler.records]
        messages = '\n'.join(messages)
        self.assertEqual(
            messages,
            "Parsing submission submission-7: root node is not '<system>'\n"
            "Processed 3 valid and 1 invalid HWDB submissions",
            'Unexpected log messages: %r' % messages)

    def testOopsLogging(self):
        """Test if OOPSes are properly logged."""
        def processSubmission(self, submission):
            x = 1
            x = x / 0
        process_submission_regular = SubmissionParser.processSubmission
        SubmissionParser.processSubmission = processSubmission

        process_pending_submissions(self.layer.txn, self.log)

        error_report = self.oopses[0]
        self.assertEqual('ZeroDivisionError', error_report['type'])
        self.assertStartsWith(
                error_report['req_vars']['error-explanation'],
                'Exception while processing HWDB')

        messages = [record.getMessage() for record in self.handler.records]
        messages = '\n'.join(messages)
        expected_message = (
            'Exception while processing HWDB submission '
            'test_submission_id_1 (OOPS-')
        self.failUnless(
                messages.startswith(expected_message),
                'Unexpected log message: %r' % messages)

        SubmissionParser.processSubmission = process_submission_regular

    def testProcessingLoopExceptionHandling(self):
        """Test of the exception handling of ProcessingLoop.__call__()"""
        def processSubmission(self, submission):
            """Force failures during submission processing."""
            if submission.submission_key == 'submission-2':
                raise LibrarianServerError('Librarian does not respond')
            else:
                return True

        process_submission_regular = SubmissionParser.processSubmission
        SubmissionParser.processSubmission = processSubmission

        self.createSubmissionData(data='whatever', compress=False,
                                  submission_key='submission-1')
        self.createSubmissionData(data='whatever', compress=False,
                                  submission_key='submission-2')

        # When we call process_pending_submissions(), submission-2 will
        # cause an exception
        self.assertRaises(
            LibrarianServerError, process_pending_submissions,
            self.layer.txn, self.log)
        error_report = self.oopses[0]
        self.assertEqual('LibrarianServerError', error_report['type'])
        self.assertEqual('Librarian does not respond', error_report['value'])

        messages = [record.getMessage() for record in self.handler.records]
        messages = '\n'.join(messages)
        expected_message = (
            'Could not reach the Librarian while processing HWDB '
            'submission submission-2 (OOPS-')
        self.failUnless(
                messages.startswith(expected_message),
                'Unexpected log messages: %r' % messages)

        # Though processing the second submission caused an exception,
        # the first one has been corretly marked as being processed...
        self.layer.txn.begin()
        submission_set = getUtility(IHWSubmissionSet)
        submission_1 = submission_set.getBySubmissionKey('submission-1')
        self.assertEqual(
            submission_1.status, HWSubmissionProcessingStatus.PROCESSED,
            'Unexpected status of submission 1: %s' % submission_1.status)

        # ... while the second submission has the status SUBMITTED.
        submission_set = getUtility(IHWSubmissionSet)
        submission_2 = submission_set.getBySubmissionKey('submission-2')
        self.assertEqual(
            submission_2.status, HWSubmissionProcessingStatus.SUBMITTED,
            'Unexpected status of submission 1: %s' % submission_2.status)

        SubmissionParser.processSubmission = process_submission_regular
