# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests of the HWDB submissions parser."""

from cStringIO import StringIO
from datetime import datetime
import logging
import os
from textwrap import dedent
import xml.etree.cElementTree as etree

import pytz
from zope.testing.loghandler import Handler

from lp.hardwaredb.scripts.hwdbsubmissions import (
    ROOT_UDI,
    SubmissionParser,
    )
from lp.services.config import config
from lp.testing import (
    TestCase,
    validate_mock_class,
    )
from lp.testing.layers import BaseLayer


class SubmissionParserTestParseSoftware(SubmissionParser):
    """A Variant used to test SubmissionParser._parseSoftware.

    This class can be used to test the regular case of
    submission data.
    """

    def __init__(self, test, logger=None):
        super(SubmissionParserTestParseSoftware, self).__init__(logger)
        self.test = test

    def _parseLSBRelease(self, node):
        self.test.assertEqual(node.tag, 'lsbrelease')
        return 'parsed lsb release'

    def _parsePackages(self, node):
        self.test.assertEqual(node.tag, 'packages')
        return 'parsed packages'

    def _parseXOrg(self, node):
        self.test.assertEqual(node.tag, 'xorg')
        return 'parsed xorg'


class SubmissionParserTestParseSoftwareNoXorgNode(SubmissionParser):
    """A Variant used to test SubmissionParser._parseSoftware.

    This class is intended to test submission data that does not contain
    a <xorg> node.
    """

    def __init__(self, test, logger=None):
        super(SubmissionParserTestParseSoftwareNoXorgNode, self).__init__(
            logger)
        self.test = test

    def _parseLSBRelease(self, node):
        self.test.assertEqual(node.tag, 'lsbrelease')
        return 'parsed lsb release'

    def _parsePackages(self, node):
        self.test.assertEqual(node.tag, 'packages')
        return 'parsed packages'


class SubmissionParserTestParseSoftwareNoPackagesNode(SubmissionParser):
    """A Variant used to test SubmissionParser._parseSoftware.

    This class is intended to test submission data that does not contain
    a <packages> node.
    """

    def __init__(self, test, logger=None):
        super(SubmissionParserTestParseSoftwareNoPackagesNode, self).__init__(
            logger)
        self.test = test

    def _parseLSBRelease(self, node):
        self.test.assertEqual(node.tag, 'lsbrelease')
        return 'parsed lsb release'

    def _parseXOrg(self, node):
        self.test.assertEqual(node.tag, 'xorg')
        return 'parsed xorg'


class TestHWDBSubmissionParser(TestCase):
    """Tests of the HWDB submission parser."""

    layer = BaseLayer

    def setUp(self):
        """Setup the test environment."""
        super(TestHWDBSubmissionParser, self).setUp()
        self.log = logging.getLogger('test_hwdb_submission_parser')
        self.log.setLevel(logging.INFO)
        self.handler = Handler(self)
        self.handler.add(self.log.name)
        self.udev_root_device = {
            'P': '/devices/LNXSYSTM:00',
            'E': {'SUBSYSTEM': 'acpi'},
            }
        self.udev_pci_device = {
            'P': '/devices/pci0000:00/0000:00:1f.2',
            'E': {
                'SUBSYSTEM': 'pci',
                'PCI_CLASS': '10601',
                'PCI_ID': '8086:27C5',
                'PCI_SUBSYS_ID': '10CF:1387',
                'PCI_SLOT_NAME': '0000:00:1f.2',
                }
            }
        self.udev_usb_device = {
            'P': '/devices/pci0000:00/0000:00:1d.1/usb3/3-2',
            'E': {
                'SUBSYSTEM': 'usb',
                'DEVTYPE': 'usb_device',
                'PRODUCT': '46d/a01/1013',
                'TYPE': '0/0/0',
                },
            }
        self.udev_usb_interface = {
            'P': '/devices/pci0000:00/0000:00:1d.1/usb3/3-2/3-2:1.1',
            'E': {
                'SUBSYSTEM': 'usb',
                'DEVTYPE': 'usb_interface',
                'PRODUCT': '46d/a01/1013',
                'TYPE': '0/0/0',
                'INTERFACE': '1/2/0',
                },
            }

        self.udev_scsi_device = {
            'P': '/devices/pci0000:00/0000:00:1f.1/host4/target4:0:0/4:0:0:0',
            'E': {
                'SUBSYSTEM': 'scsi',
                'DEVTYPE': 'scsi_device',
                },
            }

        self.sysfs_scsi_device = {
            'vendor': 'MATSHITA',
            'model': 'DVD-RAM UJ-841S',
            'type': '5',
            }

    def getTimestampETreeNode(self, time_string):
        """Return an Elementtree node for an XML tag with a timestamp."""
        return etree.Element('date_created', value=time_string)

    def testTimeConversion(self):
        """Test of the conversion of a "time string" into datetime object."""
        # Year, month, day, hour, minute, second are required.
        # We assume that such a value without timezone information is UTC.
        parser = SubmissionParser(self.log)
        utc_tz = pytz.timezone('UTC')

        time_node = self.getTimestampETreeNode('2008-01-02T03:04:05')
        self.assertEqual(parser._getValueAttributeAsDateTime(time_node),
                         datetime(2008, 1, 2, 3, 4, 5, tzinfo=utc_tz))

        # The timezone value 'Z' means UTC
        time_node = self.getTimestampETreeNode('2008-01-02T03:04:05Z')
        self.assertEqual(parser._getValueAttributeAsDateTime(time_node),
                         datetime(2008, 1, 2, 3, 4, 5, tzinfo=utc_tz))

        # A time zone offset is added to the given time, so that the resulting
        # time stamp is in UTC.
        time_node = self.getTimestampETreeNode('2008-01-02T03:04:05+01:00')
        self.assertEqual(parser._getValueAttributeAsDateTime(time_node),
                         datetime(2008, 1, 2, 2, 4, 5, tzinfo=utc_tz))

        time_node = self.getTimestampETreeNode('2008-01-02T03:04:05-01:00')
        self.assertEqual(parser._getValueAttributeAsDateTime(time_node),
                         datetime(2008, 1, 2, 4, 4, 5, tzinfo=utc_tz))

        # time values may be given with microsecond resolution.
        time_node = self.getTimestampETreeNode('2008-01-02T03:04:05.123')
        self.assertEqual(parser._getValueAttributeAsDateTime(time_node),
                         datetime(2008, 1, 2, 3, 4, 5, 123000, tzinfo=utc_tz))

        time_node = self.getTimestampETreeNode('2008-01-02T03:04:05.123456')
        self.assertEqual(parser._getValueAttributeAsDateTime(time_node),
                         datetime(2008, 1, 2, 3, 4, 5, 123456, tzinfo=utc_tz))

        # The time zone offset may be given with "minute resolution".
        time_node = self.getTimestampETreeNode('2008-01-02T03:04:05+00:01')
        self.assertEqual(parser._getValueAttributeAsDateTime(time_node),
                         datetime(2008, 1, 2, 3, 3, 5, tzinfo=utc_tz))

        time_node = self.getTimestampETreeNode('2008-01-02T03:04:05-00:01')
        self.assertEqual(parser._getValueAttributeAsDateTime(time_node),
                         datetime(2008, 1, 2, 3, 5, 5, tzinfo=utc_tz))

        # Leap seconds are rounded down to 59.999999 seconds.
        time_node = self.getTimestampETreeNode('2008-01-02T23:59:60.999')
        self.assertEqual(parser._getValueAttributeAsDateTime(time_node),
                         datetime(2008, 1, 2, 23, 59, 59, 999999,
                                  tzinfo=utc_tz))

        # "Negative" time values raise a ValueError.
        time_node = self.getTimestampETreeNode('-1000-01-02/03:04:05')
        parser.submission_key = 'testing negative time stamps'
        self.assertRaises(
            ValueError, parser._getValueAttributeAsDateTime, time_node)

        # Time values with years values with five or more digits raise
        # a ValueError.
        time_node = self.getTimestampETreeNode('12345-01-02/03:04:05')
        parser.submission_key = 'testing negative time stamps'
        self.assertRaises(
            ValueError, parser._getValueAttributeAsDateTime, time_node)

    def testSummary(self):
        node = etree.fromstring("""
            <summary>
                <live_cd value="False"/>
                <system_id value="f982bb1ab536469cebfd6eaadcea0ffc"/>
                <distribution value="Ubuntu"/>
                <distroseries value="7.04"/>
                <architecture value="amd64"/>
                <private value="False"/>
                <contactable value="False"/>
                <date_created value="2007-09-28T16:09:20.126842"/>
                <client name="hwtest" version="0.9">
                    <plugin name="architecture_info" version="1.1"/>
                    <plugin name="find_network_controllers" version="2.34"/>
                </client>
            </summary>
            """)
        parser = SubmissionParser(self.log)
        summary = parser._parseSummary(node)
        expected_data = {
            'live_cd': False,
            'system_id': 'f982bb1ab536469cebfd6eaadcea0ffc',
            'distribution': 'Ubuntu',
            'distroseries': '7.04',
            'architecture': 'amd64',
            'private': False,
            'contactable': False,
            'date_created': datetime(2007, 9, 28, 16, 9, 20, 126842,
                                     tzinfo=pytz.UTC),
            'client': {
                'name': 'hwtest',
                'version': '0.9',
                'plugins': [
                    {'name': 'architecture_info',
                     'version': '1.1'},
                    {'name': 'find_network_controllers',
                     'version': '2.34'}]},
            }
        self.assertEqual(
            summary, expected_data,
            'SubmissionParser.parseSummary returned an unexpected result')

    def testSummaryNodeWithKernelRelease(self):
        """The <summary> node may contain the sub-node <kernel-release>."""
        node = etree.fromstring("""
            <summary>
                <live_cd value="False"/>
                <system_id value="f982bb1ab536469cebfd6eaadcea0ffc"/>
                <distribution value="Ubuntu"/>
                <distroseries value="7.04"/>
                <architecture value="amd64"/>
                <private value="False"/>
                <contactable value="False"/>
                <date_created value="2007-09-28T16:09:20.126842"/>
                <client name="hwtest" version="0.9">
                    <plugin name="architecture_info" version="1.1"/>
                    <plugin name="find_network_controllers" version="2.34"/>
                </client>
                <kernel-release value="2.6.28-15-generic"/>
            </summary>
            """)
        parser = SubmissionParser(self.log)
        summary = parser._parseSummary(node)
        expected_data = {
            'live_cd': False,
            'system_id': 'f982bb1ab536469cebfd6eaadcea0ffc',
            'distribution': 'Ubuntu',
            'distroseries': '7.04',
            'architecture': 'amd64',
            'private': False,
            'contactable': False,
            'date_created': datetime(2007, 9, 28, 16, 9, 20, 126842,
                                     tzinfo=pytz.UTC),
            'client': {
                'name': 'hwtest',
                'version': '0.9',
                'plugins': [
                    {
                        'name': 'architecture_info',
                        'version': '1.1',
                        },
                    {
                        'name': 'find_network_controllers',
                        'version': '2.34'
                        }
                    ]
                },
            'kernel-release': '2.6.28-15-generic',
            }
        self.assertEqual(
            summary, expected_data,
            'SubmissionParser.parseSummary returned an unexpected result')

    def _runPropertyTest(self, xml):
        parser = SubmissionParser(self.log)
        node = etree.fromstring(xml)
        return parser._parseProperty(node)

    def testBooleanPropertyTypes(self):
        """Test the parsing result for a boolean property."""
        for property_type in ('bool', 'dbus.Boolean'):
            for value in (True, False):
                xml = ('<property type="%s" name="foo">%s</property>'
                       % (property_type, value))
                result = self._runPropertyTest(xml)
                self.assertEqual(
                    result, ('foo', (value, property_type)),
                    'Invalid parsing result for boolean property type %s, '
                        'expected %s, got %s'
                    % (property_type, value, result))

    def testStringPropertyTypes(self):
        """String properties are converted into (name, (value, type))."""
        xml_template = '<property type="%s" name="foo">some text</property>'
        for property_type in ('str', 'dbus.String', 'dbus.UTF8String'):
            xml = xml_template % property_type
            result = self._runPropertyTest(xml)
            self.assertEqual(
                result, ('foo', ('some text', property_type)),
                'Invalid parsing result for string property type %s, '
                'expected "some text", got "%s"'
                    % (property_type, result))

    def testStringPropertyEncoding(self):
        """Different encodings are properly handled."""
        xml_template = '''<?xml version="1.0" encoding="%s"?>
                          <property type="str" name="foo">%s</property>'''
        umlaut = u'\xe4'
        parser = SubmissionParser()
        for encoding in ('utf-8', 'iso-8859-1'):
            xml = xml_template % (encoding, umlaut.encode(encoding))
            tree = etree.parse(StringIO(xml))
            node = tree.getroot()
            result = parser._parseProperty(node)
            self.assertEqual(result, ('foo', (umlaut, 'str')),
                'Invalid parsing result for string encoding %s, '
                'expected am umlaut (\xe4), got %s'
                    % (encoding, repr(result)))

    def testIntegerPropertyTypes(self):
        """Int properties are converted into (name, (value, type_string)).

        type(value) is int or long, depending on the value.
        """
        xml_template = '<property name="inttest" type="%s">123</property>'
        for property_type in ('dbus.Byte', 'dbus.Int16', 'dbus.Int32',
                              'dbus.Int64', 'dbus.UInt16', 'dbus.UInt32',
                              'dbus.UInt64', 'int', 'long'):
            xml = xml_template % property_type
            result = self._runPropertyTest(xml)
            self.assertEqual(result, ('inttest', (123, property_type)),
                             'Invalid parsing result for integer property '
                             'type %s' % property_type)
        # If the value is too large for an int, a Python long is returned.
        xml = """
            <property name="inttest" type="long">
                12345678901234567890
            </property>"""
        properties = self._runPropertyTest(xml)
        self.assertEqual(properties,
                         ('inttest', (12345678901234567890L, 'long')),
                         'Invalid parsing result for integer property with '
                             'a large value')

    def testFloatPropertyTypes(self):
        """Float properties are converted into ('name', (value, type_string)).

        type(value) is float.
        """
        xml_template = ('<property name="floattest" type="%s">'
                            '1.25</property>')
        for property_type in ('dbus.Double', 'float'):
            xml = xml_template % property_type
            result = self._runPropertyTest(xml)
            self.assertEqual(result, ('floattest', (1.25, property_type)),
                             'Invalid parsing result for float property'
                             'type: %s' % property_type)

    def testListPropertyTypes(self):
        """List properties are converted into ('name', a_list).

        a_list is a Python list, where the list elements represent the
        values of the <value> sub-nodes of the <property>.
        """
        xml_template = """
            <property name="listtest" type="%s">
                <value type="int">1</value>
                <value type="str">a</value>
                <value type="list">
                    <value type="int">2</value>
                    <value type="float">3.4</value>
                </value>
                <value type="dict">
                    <value name="one" type="int">2</value>
                    <value name="two" type="str">b</value>
                </value>
            </property>
            """
        for property_type in ('dbus.Array', 'list'):
            xml = xml_template % property_type
            result = self._runPropertyTest(xml)
            self.assertEqual(result,
                             ('listtest', ([(1, 'int'),
                                            ('a', 'str'),
                                            ([(2, 'int'),
                                              (3.4, 'float')], 'list'),
                                            ({'one': (2, 'int'),
                                              'two': ('b', 'str')}, 'dict')],
                                           property_type)),
                             'Invalid parsing result for list property: '
                             '%s' % xml)

    def testDictPropertyTypes(self):
        """Dict properties are converted into ('name', a_dict).

        a_dict is a Python dictionary, where the items represent the
        values of the <value> sub-nodes of the <property>.
        """
        xml_template = """
            <property name="dicttest" type="%s">
                <value name="one" type="int">1</value>
                <value name="two" type="str">a</value>
                <value name="three" type="list">
                    <value type="int">2</value>
                    <value type="float">3.4</value>
                </value>
                <value name="four" type="dict">
                    <value name="five" type="int">2</value>
                    <value name="six" type="str">b</value>
                </value>
            </property>
            """
        for property_type in ('dbus.Dictionary', 'dict'):
            xml = xml_template % property_type
            result = self._runPropertyTest(xml)
            self.assertEqual(
                result,
                ('dicttest', ({'one': (1, 'int'),
                               'two': ('a', 'str'),
                               'three': ([(2, 'int'),
                                          (3.4, 'float')], 'list'),
                               'four': ({'five': (2, 'int'),
                                         'six': ('b', 'str')}, 'dict')},
                              property_type)),
                'Invalid parsing result for dict property: %s' % xml)

    def testProperties(self):
        """A set of properties is converted into a dictionary."""
        node = etree.fromstring("""
            <container>
                <property name="one" type="int">1</property>
                <property name="two" type="str">a</property>
            </container>
            """)
        parser = SubmissionParser(self.log)
        result = parser._parseProperties(node)
        self.assertEqual(result,
                         {'one': (1, 'int'),
                          'two': ('a', 'str')},
                         'Invalid parsing result for a property set')

        # Duplicate property names raise a ValueError
        node = etree.fromstring("""
            <container>
                <property name="one" type="int">1</property>
                <property name="one" type="str">a</property>
            </container>
            """)
        self.assertRaises(ValueError, parser._parseProperties, node)

    def testDevice(self):
        """A device node is converted into a dictionary."""
        test = self

        def _parseProperties(self, node):
            test.assertTrue(isinstance(self, SubmissionParser))
            test.assertEqual(node.tag, 'device')
            return 'parsed properties'
        parser = SubmissionParser(self.log)
        parser._parseProperties = lambda node: _parseProperties(parser, node)

        node = etree.fromstring("""
            <device id="2" udi="/org/freedesktop/Hal/devices/acpi_CPU0"
                    parent="1">
                <property name="info.product" type="str">
                    Intel(R) Core(TM)2 CPU
                </property>
            </device>
            """)
        result = parser._parseDevice(node)
        self.assertEqual(result,
                         {'id': 2,
                          'udi': '/org/freedesktop/Hal/devices/acpi_CPU0',
                          'parent': 1,
                          'properties': 'parsed properties'},
                         'Invalid parsing result for <device> (2)')

        # the attribute "parent" may be omitted.
        node = etree.fromstring("""
            <device id="1" udi="/org/freedesktop/Hal/devices/computer">
                <property name="info.product" type="str">Computer</property>
            </device>
            """)
        result = parser._parseDevice(node)
        self.assertEqual(result,
                         {'id': 1,
                          'udi': ROOT_UDI,
                          'parent': None,
                          'properties': 'parsed properties'},
                         'Invalid parsing result for <device> (1)')

    def testHal(self):
        """The <hal> node is converted into a Python dict."""
        test = self

        def _parseDevice(self, node):
            test.assertTrue(isinstance(self, SubmissionParser))
            test.assertEqual(node.tag, 'device')
            return 'parsed device node'
        parser = SubmissionParser(self.log)
        parser._parseDevice = lambda node: _parseDevice(parser, node)

        node = etree.fromstring("""
            <hal version="0.5.9.1">
                <device/>
                <device/>
            </hal>
            """)
        result = parser._parseHAL(node)
        self.assertEqual(result,
                         {'version': '0.5.9.1',
                          'devices': ['parsed device node',
                                      'parsed device node']},
                         'Invalid parsing result for <hal>')

    def testProcessors(self):
        """The <processors> node is converted into a Python list.

        The list elements represent the <processor> nodes.
        """
        test = self

        def _parseProperties(self, node):
            test.assertTrue(isinstance(self, SubmissionParser))
            test.assertEqual(node.tag, 'processor')
            return 'parsed properties'
        parser = SubmissionParser(self.log)
        parser._parseProperties = lambda node: _parseProperties(parser, node)

        node = etree.fromstring("""
            <processors>
                <processor id="123" name="0">
                    <property/>
                </processor>
                <processor id="124" name="1">
                    <property/>
                </processor>
            </processors>
            """)
        result = parser._parseProcessors(node)
        self.assertEqual(result,
                         [{'id': 123,
                           'name': '0',
                           'properties': 'parsed properties'},
                          {'id': 124,
                           'name': '1',
                           'properties': 'parsed properties'}],
                         'Invalid parsing result for <processors>')

    def testAliases(self):
        """The <aliases> node is converted into a Python list.

        The list elements represent the <alias> nodes.
        """
        parser = SubmissionParser(self.log)
        node = etree.fromstring("""
            <aliases>
                <alias target="1">
                    <vendor>Artec</vendor>
                    <model>Ultima 2000</model>
                </alias>
                <alias target="2">
                    <vendor>Medion</vendor>
                    <model>MD 4394</model>
                </alias>
            </aliases>
            """)
        result = parser._parseAliases(node)
        self.assertEqual(result,
                         [{'target': 1,
                           'vendor': 'Artec',
                           'model': 'Ultima 2000'},
                          {'target': 2,
                           'vendor': 'Medion',
                           'model': 'MD 4394'}],
                         'Invalid parsing result for <aliases>')

    def testUdev(self):
        """The content of the <udev> node is converted into a list of dicts.
        """
        parser = SubmissionParser(self.log)
        node = etree.fromstring("""
<udev>P: /devices/LNXSYSTM:00
E: UDEV_LOG=3
E: DEVPATH=/devices/LNXSYSTM:00
E: MODALIAS=acpi:LNXSYSTM:

P: /devices/pci0000:00/0000:00:1a.0
E: UDEV_LOG=3
E: DEVPATH=/devices/pci0000:00/0000:00:1a.0
S: char/189:256
</udev>
""")
        result = parser._parseUdev(node)
        self.assertEqual(
            [
                {
                    'P': '/devices/LNXSYSTM:00',
                    'E': {
                        'UDEV_LOG': '3',
                        'DEVPATH': '/devices/LNXSYSTM:00',
                        'MODALIAS': 'acpi:LNXSYSTM:',
                        },
                    'S': [],
                    'id': 1,
                    },
                {
                    'P': '/devices/pci0000:00/0000:00:1a.0',
                    'E': {
                        'UDEV_LOG': '3',
                        'DEVPATH': '/devices/pci0000:00/0000:00:1a.0',
                        },
                    'S': ['char/189:256'],
                    'id': 2,
                    },
                ],
            result,
            'Invalid parsing result for <udev>')

    def testUdevLineWithoutColon(self):
        """<udev> nodes with lines not in key: value format are rejected."""
        parser = SubmissionParser(self.log)
        parser.submission_key = 'Detect udev lines not in key:value format'
        node = etree.fromstring("""
<udev>P: /devices/LNXSYSTM:00
bad line
</udev>
""")
        result = parser._parseUdev(node)
        self.assertEqual(
            None, result,
            'Invalid parsing result for a <udev> node with a line not having '
            'the key: value format.')
        self.assertErrorMessage(
            parser.submission_key,
            "Line 1 in <udev>: No valid key:value data: 'bad line'")

    def testUdevPropertyLineWithoutEqualSign(self):
        """<udev> nodes with lines not in key: value format are rejected."""
        parser = SubmissionParser(self.log)
        parser.submission_key = (
            'Detect udev property lines not in key=value format')
        node = etree.fromstring("""
<udev>P: /devices/LNXSYSTM:00
E: bad property
</udev>
""")
        result = parser._parseUdev(node)
        self.assertEqual(
            None, result,
            'Invalid parsing result for a <udev> node with a property line '
            'not having the key=value format.')
        self.assertErrorMessage(
            parser.submission_key,
            "Line 1 in <udev>: Property without valid key=value data: "
            "'E: bad property'")

    def testUdevDataWithDuplicateKey(self):
        """<udev> nodes with lines not in key: value format are rejected."""
        parser = SubmissionParser(self.log)
        parser.submission_key = 'Detect duplactae attributes in udev data'
        node = etree.fromstring("""
<udev>P: /devices/LNXSYSTM:00
W:1
W:2
</udev>
""")
        result = parser._parseUdev(node)
        self.assertEqual(
            [
                {
                    'P': '/devices/LNXSYSTM:00',
                    'E': {},
                    'S': [],
                    'W': '2',
                    'id': 1,
                    },
                ],
            result,
            'Invalid parsing result for a <udev> node with a duplicate '
            'attribute.')
        self.assertWarningMessage(
            parser.submission_key,
            "Line 2 in <udev>: Duplicate attribute key: 'W:2'")

    def testDmi(self):
        """The content of the <udev> node is converted into a dictionary."""
        parser = SubmissionParser(self.log)
        node = etree.fromstring("""<dmi>/sys/class/dmi/id/bios_vendor:LENOVO
/sys/class/dmi/id/bios_version:7LETB9WW (2.19 )
/sys/class/dmi/id/sys_vendor:LENOVO
/sys/class/dmi/id/modalias:dmi:bvnLENOVO:bvr7LETB9WW
</dmi>""")
        result = parser._parseDmi(node)
        self.assertEqual(
            {
                '/sys/class/dmi/id/bios_vendor': 'LENOVO',
                '/sys/class/dmi/id/bios_version': '7LETB9WW (2.19 )',
                '/sys/class/dmi/id/sys_vendor': 'LENOVO',
                '/sys/class/dmi/id/modalias': 'dmi:bvnLENOVO:bvr7LETB9WW',
                },
            result,
            'Invalid parsing result for <dmi>.')

    def testDmiInvalidData(self):
        """<dmi> nodes with lines not in key:value format are rejected."""
        parser = SubmissionParser(self.log)
        parser.submission_key = 'Invalid DMI data'
        node = etree.fromstring("""<dmi>/sys/class/dmi/id/bios_vendor:LENOVO
invalid line
</dmi>""")
        result = parser._parseDmi(node)
        self.assertEqual(
            None, result,
            '<dmi> node with invalid data not deteced.')
        self.assertErrorMessage(
            parser.submission_key,
            "Line 1 in <dmi>: No valid key:value data: 'invalid line'")

    def testSysfsAttributes(self):
        """Test of SubmissionParser._parseSysfsAttributes().

        The content of the <sys-attributes> node is converted into
        a dictionary.
        """
        parser = SubmissionParser(self.log)
        node = etree.fromstring(dedent("""
            <sysfs-attributes>
            P: /devices/LNXSYSTM:00/LNXPWRBN:00/input/input0
            A: modalias=input:b0019v0000p0001e0000-e0,1,k74
            A: uniq=
            A: phys=LNXPWRBN/button/input0
            A: name=Power Button

            P: /devices/LNXSYSTM:00/device:00/PNP0A08:00/device:03
            A: uniq=
            A: phys=/video/input0
            A: name=Video Bus
            </sysfs-attributes>
            """))
        result = parser._parseSysfsAttributes(node)
        self.assertEqual(
            {
                '/devices/LNXSYSTM:00/LNXPWRBN:00/input/input0': {
                    'modalias': 'input:b0019v0000p0001e0000-e0,1,k74',
                    'uniq': '',
                    'phys': 'LNXPWRBN/button/input0',
                    'name': 'Power Button',
                    },
                '/devices/LNXSYSTM:00/device:00/PNP0A08:00/device:03': {
                    'uniq': '',
                    'phys': '/video/input0',
                    'name': 'Video Bus',
                    },

                },
            result,
            'Invalid parsing result of <sysfs-attributes> node.')

    def testSysfsAttributesLineWithoutKeyValueData(self):
        """Test of SubmissionParser._parseSysfsAttributes().

        Lines not in key: value format are rejected.
        """
        parser = SubmissionParser(self.log)
        parser.submission_key = (
            'Detect <sysfs-attributes> lines not in key:value format')
        node = etree.fromstring(dedent("""
            <sysfs-attributes>
            P: /devices/LNXSYSTM:00/LNXPWRBN:00/input/input0
            A: modalias=input:b0019v0000p0001e0000-e0,1,k74
            invalid line
            </sysfs-attributes>
            """))
        result = parser._parseSysfsAttributes(node)
        self.assertEqual(
            None, result,
            'Invalid parsing result of a <sysfs-attributes> node containing '
            'a line not in key:value format.')
        self.assertErrorMessage(
            parser.submission_key,
            "Line 3 in <sysfs-attributes>: No valid key:value data: "
            "'invalid line'")

    def testSysfsAttributesDuplicatePLine(self):
        """Test of SubmissionParser._parseSysfsAttributes().

        A line starting with "P:" must be the first line of a device block.
        """
        parser = SubmissionParser(self.log)
        parser.submission_key = (
            'Detect <sysfs-attributes> node with duplicate P: line')
        node = etree.fromstring(dedent("""
            <sysfs-attributes>
            P: /devices/LNXSYSTM:00/LNXPWRBN:00/input/input0
            A: modalias=input:b0019v0000p0001e0000-e0,1,k74
            P: /devices/LNXSYSTM:00/LNXPWRBN:00/input/input0
            </sysfs-attributes>
            """))
        result = parser._parseSysfsAttributes(node)
        self.assertEqual(
            None, result,
            'Invalid parsing result of a <sysfs-attributes> node containing '
            'a duplicate P: line.')
        self.assertErrorMessage(
            parser.submission_key,
            "Line 3 in <sysfs-attributes>: duplicate 'P' line found: "
            "'P: /devices/LNXSYSTM:00/LNXPWRBN:00/input/input0'")

    def testSysfsAttributesNoPLineAtDeviceStart(self):
        """Test of SubmissionParser._parseSysfsAttributes().

        The data for a device must start with a "P:" line.
        """
        parser = SubmissionParser(self.log)
        parser.submission_key = (
            'Detect <sysfs-attributes> node without leading P: line')
        node = etree.fromstring(dedent("""
            <sysfs-attributes>
            A: modalias=input:b0019v0000p0001e0000-e0,1,k74
            </sysfs-attributes>
            """))
        result = parser._parseSysfsAttributes(node)
        self.assertEqual(
            None, result,
            'Invalid parsing result of a <sysfs-attributes> node where a '
            'device block does not start with a "P": line.')
        self.assertErrorMessage(
            parser.submission_key,
            "Line 1 in <sysfs-attributes>: Block for a device does not "
            "start with 'P:': "
            "'A: modalias=input:b0019v0000p0001e0000-e0,1,k74'")

    def testSysfsAttributesNoAttributeKeyValue(self):
        """Test of SubmissionParser._parseSysfsAttributes().

        A line starting with "A:" must be in key=value format.
        """
        parser = SubmissionParser(self.log)
        parser.submission_key = (
            'Detect <sysfs-attributes> node with A: line not in key=value '
            'format')
        node = etree.fromstring(dedent("""
            <sysfs-attributes>
            P: /devices/LNXSYSTM:00/LNXPWRBN:00/input/input0
            A: equal sign is missing
            </sysfs-attributes>
            """))
        result = parser._parseSysfsAttributes(node)
        self.assertEqual(
            None, result,
            'Invalid parsing result of a <sysfs-attributes> node with A: '
            'line not in key=value format.')
        self.assertErrorMessage(
            parser.submission_key,
            "Line 2 in <sysfs-attributes>: Attribute line does not contain "
            "key=value data: 'A: equal sign is missing'")

    def testSysfsAttributesInvalidMainKey(self):
        """Test of SubmissionParser._parseSysfsAttributes().

        All lines must start with "P:" or "A:".
        """
        parser = SubmissionParser(self.log)
        parser.submission_key = (
            'Detect <sysfs-attributes> node with invalid main key.')
        node = etree.fromstring(dedent("""
            <sysfs-attributes>
            P: /devices/LNXSYSTM:00/LNXPWRBN:00/input/input0
            X: an invalid line
            </sysfs-attributes>
            """))
        result = parser._parseSysfsAttributes(node)
        self.assertEqual(
            None, result,
            'Invalid parsing result of a <sysfs-attributes> node containg '
            'a line that does not start with "A:" or "P:".')
        self.assertErrorMessage(
            parser.submission_key,
            "Line 2 in <sysfs-attributes>: Unexpected key: "
            "'X: an invalid line'")

    class MockSubmissionParserParseHardwareTest(SubmissionParser):
        """A SubmissionParser variant for testing checkCOnsistentData()

        All "method substitutes" return a valid result.
        """

        def __init__(self, logger=None, record_warnings=True):
            super(self.__class__, self).__init__(logger)
            self.hal_result = 'parsed HAL data'
            self.processors_result = 'parsed processor data'
            self.aliases_result = 'parsed alias data'
            self.udev_result = 'parsed udev data'
            self.dmi_result = 'parsed DMI data'
            self.sysfs_result = 'parsed sysfs data'

        def _parseHAL(self, hal_node):
            """See `SubmissionParser`."""
            return self.hal_result

        def _parseProcessors(self, processors_node):
            """See `SubmissionParser`."""
            return self.processors_result

        def _parseAliases(self, aliases_node):
            """See `SubmissionParser`."""
            return self.aliases_result

        def _parseUdev(self, udev_node):
            """See `SubmissionParser`."""
            return self.udev_result

        def _parseDmi(self, dmi_node):
            """See `SubmissionParser`."""
            return self.dmi_result

        def _parseSysfsAttributes(self, sysfs_node):
            """See `SubmissionParser`."""
            return self.sysfs_result

    validate_mock_class(MockSubmissionParserParseHardwareTest)

    def testHardware(self):
        """The <hardware> tag is converted into a dictionary."""
        parser = self.MockSubmissionParserParseHardwareTest(self.log)

        node = etree.fromstring("""
            <hardware>
                <hal/>
                <processors/>
                <aliases/>
                <udev/>
                <dmi/>
                <sysfs-attributes/>
            </hardware>
            """)
        result = parser._parseHardware(node)
        self.assertEqual({
            'hal': 'parsed HAL data',
            'processors': 'parsed processor data',
            'aliases': 'parsed alias data',
            'udev': 'parsed udev data',
            'dmi': 'parsed DMI data',
            'sysfs-attributes': 'parsed sysfs data',
            },
            result,
            'Invalid parsing result for <hardware>')

    def testHardware_no_sysfs_node(self):
        """If teh <sysfs-attributes> node is missing, parseHardware()
        returns a dicitionary where the entry for this node is None.
        """
        parser = self.MockSubmissionParserParseHardwareTest(self.log)

        node = etree.fromstring("""
            <hardware>
                <hal/>
                <processors/>
                <aliases/>
                <udev/>
                <dmi/>
            </hardware>
            """)
        result = parser._parseHardware(node)
        self.assertEqual({
            'hal': 'parsed HAL data',
            'processors': 'parsed processor data',
            'aliases': 'parsed alias data',
            'udev': 'parsed udev data',
            'dmi': 'parsed DMI data',
            'sysfs-attributes': None,
            },
            result,
            'Invalid parsing result for <hardware>')

    def test_parseHardware_sub_parsers_fail(self):
        """Test of SubmissionParser._parseHardware().

        If one of the sub-parsers returns None, _parseHardware() returns
        None.
        """
        node = etree.fromstring("""
            <hardware>
               <hal/>
                <processors/>
                <aliases/>
                <udev/>
                <dmi/>
                <sysfs-attributes/>
            </hardware>
            """)

        submission_parser = self.MockSubmissionParserParseHardwareTest()
        submission_parser.hal_result = None
        self.assertIs(None, submission_parser._parseHardware(node))

        submission_parser = self.MockSubmissionParserParseHardwareTest()
        submission_parser.processors_result = None
        self.assertIs(None, submission_parser._parseHardware(node))

        submission_parser = self.MockSubmissionParserParseHardwareTest()
        submission_parser.aliases_result = None
        self.assertIs(None, submission_parser._parseHardware(node))

        submission_parser = self.MockSubmissionParserParseHardwareTest()
        submission_parser.udev_result = None
        self.assertIs(None, submission_parser._parseHardware(node))

        submission_parser = self.MockSubmissionParserParseHardwareTest()
        submission_parser.dmi_result = None
        self.assertIs(None, submission_parser._parseHardware(node))

        submission_parser = self.MockSubmissionParserParseHardwareTest()
        submission_parser.sysfs_result = None
        self.assertIs(None, submission_parser._parseHardware(node))

    def testLsbRelease(self):
        """The <lsbrelease> node is converted into a Python dictionary.

        Each dict item represents a <property> sub-node.
        """
        node = etree.fromstring("""
            <lsbrelease>
                <property name="release" type="str">
                    7.04
                </property>
                <property name="codename" type="str">
                    feisty
                </property>
                <property name="distributor-id" type="str">
                    Ubuntu
                </property>
                <property name="description" type="str">
                    Ubuntu 7.04
                </property>
            </lsbrelease>
            """)
        parser = SubmissionParser(self.log)
        result = parser._parseLSBRelease(node)
        self.assertEqual(result,
                         {'distributor-id': ('Ubuntu', 'str'),
                          'release': ('7.04', 'str'),
                          'codename': ('feisty', 'str'),
                          'description': ('Ubuntu 7.04', 'str')},
                         'Invalid parsing result for <lsbrelease>')

    def testPackages(self):
        """The <packages> node is converted into a Python dictionary.

        Each dict item represents a <package> sub-node as
        (package_name, package_data), where package_data
        is a dictionary representing the <property> sub-nodes of a
        <package> node.
        """
        node = etree.fromstring("""
            <packages>
                <package name="metacity" id="1">
                    <property name="installed_size" type="int">
                        868352
                    </property>
                    <property name="section" type="str">
                        x11
                    </property>
                    <property name="summary" type="str">
                        A lightweight GTK2 based Window Manager
                    </property>
                    <property name="priority" type="str">
                        optional
                    </property>
                    <property name="source" type="str">
                        metacity
                    </property>
                    <property name="version" type="str">
                        1:2.18.2-0ubuntu1.1
                    </property>
                    <property name="size" type="int">
                        429128
                    </property>
                </package>
            </packages>
            """)
        parser = SubmissionParser(self.log)
        result = parser._parsePackages(node)
        self.assertEqual(result,
                         {'metacity':
                          {'id': 1,
                           'properties':
                            {'installed_size': (868352, 'int'),
                             'priority': ('optional', 'str'),
                             'section': ('x11', 'str'),
                             'size': (429128, 'int'),
                             'source': ('metacity', 'str'),
                             'summary':
                                 ('A lightweight GTK2 based Window Manager',
                                  'str'),
                             'version': ('1:2.18.2-0ubuntu1.1', 'str')}}},
                         'Invalid parsing result for <packages>')

    def testDuplicatePackage(self):
        """Two <package> nodes with the same name are rejected."""
        node = etree.fromstring("""
            <packages>
                <package name="foo" id="1">
                    <property name="size" type="int">10000</property>
                </package>
                <package name="foo" id="1">
                    <property name="size" type="int">10000</property>
                </package>
            </packages>
            """)
        self.assertRaises(ValueError, SubmissionParser()._parsePackages, node)

    def testXorg(self):
        """The <xorg> node is converted into a Python dictionary."""
        node = etree.fromstring("""
            <xorg version="1.1">
                <driver name="fglrx" version="1.23"
                        class="X.Org Video Driver" device="12"/>
                <driver name="kbd" version="1.2.1"
                        class="X.Org XInput driver" device="15"/>

            </xorg>
            """)
        parser = SubmissionParser(self.log)
        result = parser._parseXOrg(node)
        self.assertEqual(result,
                         {'version': '1.1',
                         'drivers': {'fglrx': {'name': 'fglrx',
                                               'version': '1.23',
                                               'class': 'X.Org Video Driver',
                                               'device': 12},
                                     'kbd': {'name': 'kbd',
                                             'version': '1.2.1',
                                             'class': 'X.Org XInput driver',
                                             'device': 15}}},
                         'Invalid parsing result for <xorg>')

    def testDuplicateXorgDriver(self):
        """Two <driver> nodes in <xorg> with the same name are rejected."""
        node = etree.fromstring("""
            <xorg>
                <driver name="mouse" class="X.Org XInput driver"/>
                <driver name="mouse" class="X.Org XInput driver"/>
            </xorg>
            """)
        self.assertRaises(ValueError, SubmissionParser()._parseXOrg, node)

    def test_parseSoftware(self):
        """Test SubmissionParser._parseSoftware

        Ensure that all sub-parsers are properly called.
        """
        parser = SubmissionParserTestParseSoftware(self)

        node = etree.fromstring("""
            <software>
                <lsbrelease/>
                <packages/>
                <xorg/>
            </software>
            """)
        result = parser._parseSoftware(node)
        self.assertEqual(result,
                         {'lsbrelease': 'parsed lsb release',
                          'packages': 'parsed packages',
                          'xorg': 'parsed xorg'},
                         'Invalid parsing result for <software>')

    def test_parseSoftware_without_xorg_node(self):
        """Test SubmissionParser._parseSoftware

        Ensure that _parseSoftware creates an entry in its
        result for <xorg> even if the submitted data does not
        contains this node.
        """
        parser = SubmissionParserTestParseSoftwareNoXorgNode(self)

        node = etree.fromstring("""
            <software>
                <lsbrelease/>
                <packages/>
            </software>
            """)
        result = parser._parseSoftware(node)
        self.assertEqual(
            result,
            {
                'lsbrelease': 'parsed lsb release',
                'packages': 'parsed packages',
                'xorg': {},
            },
            'Invalid parsing result for <software> without <xorg> sub-node')

    def test_parseSoftware_without_packages_node(self):
        """Test SubmissionParser._parseSoftware

        Ensure that _parseSoftware creates an entry in its
        result for <packages> even if the submitted data does not
        contains this node.
        """
        parser = SubmissionParserTestParseSoftwareNoPackagesNode(self)

        node = etree.fromstring("""
            <software>
                <lsbrelease/>
                <xorg/>
            </software>
            """)
        result = parser._parseSoftware(node)
        self.assertEqual(
            result,
            {
                'lsbrelease': 'parsed lsb release',
                'packages': {},
                'xorg': 'parsed xorg',
            },
            'Invalid parsing result for <software> without <packages> '
            'sub-node')

    def testMultipleChoiceQuestion(self):
        """The <questions> node is converted into a Python dictionary."""
        node = etree.fromstring("""
            <questions>
                <question name="detected_network_controllers"
                          plugin="find_network_controllers">
                    <target id="42">
                        <driver>ipw3945</driver>
                    </target>
                    <target id="43"/>
                    <command/>
                    <answer type="multiple_choice">pass</answer>
                    <answer_choices>
                        <value type="str">fail</value>
                        <value type="str">pass</value>
                        <value type="str">skip</value>
                    </answer_choices>
                    <comment>
                        The WLAN adapter drops the connection very frequently.
                    </comment>
                </question>
            </questions>
            """)
        parser = SubmissionParser()
        result = parser._parseQuestions(node)
        self.assertEqual(
            result,
            [{'name': 'detected_network_controllers',
              'plugin': 'find_network_controllers',
              'targets': [{'id': 42,
                           'drivers': ['ipw3945']},
                          {'id': 43,
                           'drivers': []}],
              'answer': {'type': 'multiple_choice',
                         'value': 'pass'},
              'answer_choices': [('fail', 'str'),
                                 ('pass', 'str'),
                                 ('skip', 'str')],
              'comment': 'The WLAN adapter drops the connection very '
                         'frequently.'}],
            'Invalid parsing result for multiple choice question')

    def testMeasurementQuestion(self):
        """The <questions> node is converted into a Python dictionary."""
        node = etree.fromstring("""
            <questions>
                <question name="harddisk_speed"
                          plugin="harddisk_speed">
                    <target id="87"/>
                    <command>hdparm -t /dev/sda</command>
                    <answer type="measurement" unit="MB/sec">38.4</answer>
                </question>
            </questions>
            """)
        parser = SubmissionParser()
        result = parser._parseQuestions(node)
        self.assertEqual(
            result,
            [{
              'name': 'harddisk_speed',
              'plugin': 'harddisk_speed',
              'answer': {'type': 'measurement',
                         'value': '38.4',
                         'unit': 'MB/sec'},
              'targets': [{'drivers': [],
                           'id': 87}],
              'command': 'hdparm -t /dev/sda'}],
            'Invalid parsing result for measurement question')

    def testContext(self):
        """The content of the <context> node is currently not processed.

        Instead, a log warning is issued.
        """
        parser = SubmissionParser(self.log)
        parser.submission_key = 'Test of <context> parsing'
        node = etree.fromstring('<context/>')
        parser._parseContext(node)
        self.assertEqual({}, parser._parseContext(node))
        self.assertWarningMessage(
            parser.submission_key,
            'Submission contains unprocessed <context> data.')

    class MockSubmissionParserMainParserTest(SubmissionParser):
        """A SubmissionParser variant for testing checkCOnsistentData()

        All "method substitutes" return a valid result.
        """

        def __init__(self, logger=None, record_warnings=True):
            SubmissionParser.__init__(self, logger)
            self.summary_result = 'parsed summary'
            self.hardware_result = 'parsed hardware'
            self.software_result = 'parsed software'
            self.questions_result = 'parsed questions'
            self.context_result = 'parsed context'

        def _parseSummary(self, summary_node):
            """See `SubmissionParser`."""
            return self.summary_result

        def _parseHardware(self, hardware_node):
            """See `SubmissionParser`."""
            return self.hardware_result

        def _parseSoftware(self, software_node):
            """See `SubmissionParser`."""
            return self.software_result

        def _parseQuestions(self, questions_node):
            """See `SubmissionParser`."""
            return self.questions_result

        def _parseContext(self, context_node):
            """See `SubmissionParser`."""
            return self.context_result

    validate_mock_class(MockSubmissionParserMainParserTest)

    def testMainParser(self):
        """Test SubmissionParser.parseMainSections

        Ensure that all sub-parsers are properly called.
        """
        parser = self.MockSubmissionParserMainParserTest()

        node = etree.fromstring("""
            <system>
                <summary/>
                <hardware/>
                <software/>
                <questions/>
                <context/>
            </system>
            """)

        expected_data = {
            'summary': 'parsed summary',
            'hardware': 'parsed hardware',
            'software': 'parsed software',
            'questions': 'parsed questions',
            'context': 'parsed context',
            }

        result = parser.parseMainSections(node)
        self.assertEqual(result, expected_data,
            'SubmissionParser.parseSubmission returned an unexpected result')

        parser = self.MockSubmissionParserMainParserTest()
        parser.summary_result = None
        self.assertIs(None, parser.parseMainSections(node))

        parser = self.MockSubmissionParserMainParserTest()
        parser.hardware_result = None
        self.assertIs(None, parser.parseMainSections(node))

        parser = self.MockSubmissionParserMainParserTest()
        parser.software_result = None
        self.assertIs(None, parser.parseMainSections(node))

        parser = self.MockSubmissionParserMainParserTest()
        parser.questions_result = None
        self.assertIs(None, parser.parseMainSections(node))

        parser = self.MockSubmissionParserMainParserTest()
        parser.context_result = None
        self.assertIs(None, parser.parseMainSections(node))

    def testSubmissionParser(self):
        """Test the entire parser."""
        sample_data_path = os.path.join(
            config.root, 'lib', 'lp', 'hardwaredb', 'scripts',
            'tests', 'hardwaretest.xml')
        sample_data = open(sample_data_path).read()
        parser = SubmissionParser()
        result = parser.parseSubmission(sample_data, 'parser test 1')
        self.assertNotEqual(result, None,
                            'Valid submission data rejected by '
                            'SubmissionParser.parseSubmission')

        # parseSubmission returns None, if the submitted data is not
        # well-formed XML...
        result = parser.parseSubmission(
            sample_data.replace('<summary', '<inconsitent_opening_tag'),
            'parser test 2')
        self.assertEqual(result, None,
                         'Not-well-formed XML data accepted by '
                         'SubmissionParser.parseSubmission')

        # ...or if RelaxNG validation fails...
        result = parser.parseSubmission(
            sample_data.replace('<summary', '<summary foo="bar"'),
            'parser test 3')
        self.assertEqual(result, None,
                         'XML data that does pass the Relax NG validation '
                         'accepted by SubmissionParser.parseSubmission')

        # ...or if the parser detects an inconsistency, like a
        # property set containing two properties with the same name.
        result = parser.parseSubmission(
            sample_data.replace(
                '<property name="info.parent"',
                """<property name="info.parent" type="dbus.String">
                       foo
                   </property>
                   <property name="info.parent"
                """,
                1),
            'parser test 4')
        self.assertEqual(result, None,
                         'XML data that does pass the Relax NG validation '
                         'accepted by SubmissionParser.parseSubmission')

    def testFindDuplicates(self):
        """Test of SubmissionParser._findDuplicates."""
        # If all_ids is empty before the call of _findDuplicates, all
        # elements of test_ids is copied to all_ids. Since test_ids does
        # not contains duplicates, the return value of _findDuplicates
        # is empty.
        all_ids = set()
        test_ids = [1, 2, 3]
        parser = SubmissionParser()
        result = parser._findDuplicates(all_ids, test_ids)
        self.assertEqual(result, set(),
                         '_findDuplicates found duplicates where none exist')
        self.assertEqual(all_ids, set((1, 2, 3)),
                         '_findDuplicates did not update all_ids properly'
                         'with unique elements (1, 2, 3)')

        # An element that appears both in all_ids and test_ids is included
        # in the return value.
        test_ids = [3, 4]
        result = parser._findDuplicates(all_ids, test_ids)
        self.assertEqual(result, set((3,)),
                         '_findDuplicates did not detect an element in '
                         'test_ids which already existed in all_ids')
        self.assertEqual(all_ids, set((1, 2, 3, 4)),
                         '_findDuplicates did not update all_ids with '
                         'test_ids (3, 4)')

        # If an element exists twice in test_ids, it is detected as a
        # duplicate.
        test_ids = [5, 5]
        result = parser._findDuplicates(all_ids, test_ids)
        self.assertEqual(result, set((5,)),
                         '_findDuplicates did not detect a element which '
                         'exists twice in test_ids')
        self.assertEqual(all_ids, set((1, 2, 3, 4, 5)),
                         '_findDuplicates did not update all_ids with a '
                         'duplicate element of test_ids')

    def testFindDuplicateIDs(self):
        """SubmissionParser.findDuplicateIDs lists duplicate IDS.

        The IDs of HAL devices, processors and packages should be
        unique.
        """
        devices = [{'id': 1},
                   {'id': 2}]
        processors = [{'id': 3},
                      {'id': 4}]
        packages = {'bzr': {'id': 5},
                    'python-dev': {'id': 6}}
        submission = {
            'hardware': {
                'hal': {'devices': devices},
                'processors': processors},
            'software': {'packages': packages}}

        parser = SubmissionParser()
        duplicates = parser.findDuplicateIDs(submission)
        self.assertEqual(
            duplicates, set(),
            'Duplicate IDs detected, where no duplicates exist.')

        for duplicate_entry in ({'id': 1},
                                {'id': 3},
                                {'id': 5}):
            devices.append(duplicate_entry)
            duplicates = parser.findDuplicateIDs(submission)
            self.assertEqual(
                duplicates, set((duplicate_entry['id'],)),
                'Duplicate ID %i in HAL devices not detected.'
                % duplicate_entry['id'])
            devices.pop()

            processors.append(duplicate_entry)
            duplicates = parser.findDuplicateIDs(submission)
            self.assertEqual(
                duplicates, set((duplicate_entry['id'],)),
                'Duplicate ID %i in processors not detected.'
                % duplicate_entry['id'])
            processors.pop()

            packages['python-xml'] = duplicate_entry
            duplicates = parser.findDuplicateIDs(submission)
            self.assertEqual(
                duplicates, set((duplicate_entry['id'],)),
                'Duplicate ID %i in packages not detected.'
                % duplicate_entry['id'])
            del packages['python-xml']

    def testFindDuplicateIDsUdev(self):
        """SubmissionParser.findDuplicateIDs lists duplicate IDS.

        The IDs of udev devices, processors and packages should be
        unique.
        """
        udev = [
            {'P': '/devices/LNXSYSTM:00'},
            {'P': '/devices/LNXSYSTM:00/ACPI_CPU:00'},
            ]
        sysfs_attributes = [
            {'P': '/devices/LNXSYSTM:00'},
            ]
        processors = [
            {'id': 1},
            {'id': 2},
            ]
        packages = {
            'bzr': {'id': 4},
            'python-dev': {'id': 6},
            }
        submission = {
            'hardware': {
                'udev': udev,
                'sysfs-attributes': sysfs_attributes,
                'processors': processors,
                },
            'software': {
                'packages': packages
                }
            }

        parser = SubmissionParser()
        duplicates = parser.findDuplicateIDs(submission)
        self.assertEqual(
            set(), duplicates,
            'Duplicate IDs for udev submission detected, where no duplicates '
            'exist.')

    def testFindDuplicateIDsDuplicateUdevNode(self):
        """SubmissionParser.findDuplicateIDs lists duplicate IDS.

        Two udev dictionaries with the same device['P'] value are
        invalid.
        """
        udev = [
            {'P': '/devices/LNXSYSTM:00'},
            {'P': '/devices/LNXSYSTM:00'},
            ]
        sysfs_attributes = [
            {'P': '/devices/LNXSYSTM:00'},
            ]
        processors = [
            {'id': 1},
            {'id': 2},
            ]
        packages = {
            'bzr': {'id': 4},
            'python-dev': {'id': 6},
            }
        submission = {
            'hardware': {
                'udev': udev,
                'sysfs-attributes': sysfs_attributes,
                'processors': processors,
                },
            'software': {
                'packages': packages
                }
            }

        parser = SubmissionParser()
        duplicates = parser.findDuplicateIDs(submission)
        self.assertEqual(
            set(('/devices/LNXSYSTM:00', )), duplicates,
            'Duplicate udev nodes not detected.')

    def testIDMap(self):
        """Test of SubmissionParser._getIDMap."""
        devices = [{'id': 1},
                   {'id': 2}]
        processors = [{'id': 3},
                      {'id': 4}]
        packages = {'bzr': {'id': 5},
                    'python-dev': {'id': 6}}
        submission = {
            'hardware': {
                'hal': {'devices': devices},
                'processors': processors},
            'software': {'packages': packages}}

        parser = SubmissionParser()
        result = parser._getIDMap(submission)
        self.assertEqual(result,
                         {1: devices[0],
                          2: devices[1],
                          3: processors[0],
                          4: processors[1],
                          5: packages['bzr'],
                          6: packages['python-dev']},
                         'Invalid result of SubmissionParser._getIDMap')

    def testIDMapUdev(self):
        """Test of SubmissionParser._getIDMap.

        Variant for submissions with udev data.
        """
        devices = [
            {'P': '/devices/LNXSYSTM:00'},
            {'P': '/devices/LNXSYSTM:00/ACPI_CPU:00'},
            ]
        processors = [
            {'id': 3},
            {'id': 4},
            ]
        packages = {
            'bzr': {'id': 5},
            }
        submission = {
            'hardware': {
                'udev': devices,
                'processors': processors,
                },
            'software': {
                'packages': packages
                }
            }

        parser = SubmissionParser()
        result = parser._getIDMap(submission)
        self.assertEqual(
            {
                '/devices/LNXSYSTM:00': devices[0],
                '/devices/LNXSYSTM:00/ACPI_CPU:00': devices[1],
                3: processors[0],
                4: processors[1],
                5: packages['bzr'],
                },
            result,
            'Invalid result of SubmissionParser._getIDMap')

    def testInvalidIDReferencesUdev(self):
        """Test of SubmissionParser.checkIDReferences.

        Variant for submissions containing udev data.
        """
        devices = [{'id': 1},
                   {'id': 2}]
        processors = [{'id': 3},
                      {'id': 4}]
        packages = {'bzr': {'id': 5},
                    'python-dev': {'id': 6}}
        processors = [{'id': 3},
                      {'id': 4}]
        questions = [{'targets': [{'id': 1}]},
                     {'targets': [{'id': 2},
                                  {'id': 3}]}]
        submission = {
            'hardware': {
                'hal': {'devices': devices},
                        'processors': processors},
            'software': {'packages': packages},
            'questions': questions}
        parser = SubmissionParser()
        invalid_ids = parser.findInvalidIDReferences(submission)
        self.assertEqual(invalid_ids, set(),
                         'Invalid ID references detected where none exist')

        questions.append({'targets': [{'id': -1}]})
        invalid_ids = parser.findInvalidIDReferences(submission)
        self.assertEqual(invalid_ids, set([-1]),
                         'Invalid ID reference not detected')

    DEVICE_2_UDI = '/org/freedesktop/Hal/devices/acpi_AC'
    DEVICE_3_UDI = '/org/freedesktop/Hal/devices/pci_8086_27c5'
    DEVICE_4_UDI = '/org/freedesktop/Hal/devices/usb_device_0_0_0000_00_1d_7'
    _udi_device_test_data = [
        {'udi': ROOT_UDI,
          'properties': {}},
         {'udi': DEVICE_2_UDI,
          'properties': {
              'info.parent': (ROOT_UDI,
                              'dbus.String')}}]

    def testUDIDeviceMap(self):
        """Test the creation of the mapping UDI -> device."""
        SSB_UDI = '/org/freedesktop/Hal/devices/ssb__null_'
        SSB_CHILD_UDI = '/org/freedesktop/Hal/devices/net_00_1a_73_a3_8f_a4_0'
        device1 = {
              'id': 1,
              'udi': ROOT_UDI,
              }
        device2 = {
            'id': 2,
            'udi': self.DEVICE_2_UDI,
            'properties': {
                'info.parent': (ROOT_UDI, 'str'),
                },
            }
        device3 = {
            'id': 3,
            'udi': SSB_UDI,
            'properties': {
                'info.parent': (ROOT_UDI, 'str'),
                },
            }
        device4 = {
            'id': 4,
            'udi': SSB_CHILD_UDI,
            'properties': {
                'info.parent': (SSB_UDI, 'str'),
                },
            }

        devices = [device1, device2]

        parser = SubmissionParser()
        udi_devices = parser.getUDIDeviceMap(devices)
        self.assertEqual(udi_devices,
                         {ROOT_UDI: device1,
                          self.DEVICE_2_UDI: device2},
                         'Invalid result of SubmissionParser.getUDIDeviceMap')

        # Generally, duplicate UDIs raise a ValueError.
        devices.append(device2)
        self.assertRaises(ValueError, parser.getUDIDeviceMap, devices)

        # Exceptions are devices with certain UDIs which are known
        # to appear sometimes more than once in HWDB submissions.
        devices = [device1, device2, device3, device4, device3, device4]
        udi_devices = parser.getUDIDeviceMap(devices)
        self.assertEqual(
            udi_devices,
            {
                ROOT_UDI: device1,
                self.DEVICE_2_UDI: device2,
                SSB_UDI: device3,
                SSB_CHILD_UDI: device4,
                },
            'Unexpected result of processing a device list with duplicate '
            'SSB UDIs')
        self.assertEqual(
            devices, [device1, device2, device3, device4],
            'Unexpected list of devices after removing duplicates.')

    def testIDUDIMaps(self):
        """Test of SubmissionParser._getIDUDIMaps."""
        device1 = {'id': 1,
                   'udi': ROOT_UDI}
        device2 = {'id': 2,
                   'udi': self.DEVICE_2_UDI}
        devices = [device1, device2]

        parser = SubmissionParser()
        id_to_udi, udi_to_id = parser._getIDUDIMaps(devices)
        self.assertEqual(id_to_udi,
                         {1: ROOT_UDI,
                          2: self.DEVICE_2_UDI},
                         '_getIDUDIMaps returned invalid ID -> UDI map')
        self.assertEqual(udi_to_id,
                         {ROOT_UDI: 1,
                          self.DEVICE_2_UDI: 2},
                         '_getIDUDIMaps returned invalid UDI -> ID map')

    def testUDIChildren(self):
        """Test of SubmissionParser.getUDIChildren."""
        device1 = {'id': 1,
                   'udi': ROOT_UDI,
                   'properties': {}}
        device2 = {'id': 2,
                   'udi': self.DEVICE_2_UDI,
                   'properties':
                       {'info.parent':
                            (ROOT_UDI, 'str')}}
        device3 = {'id': 3,
                   'udi': self.DEVICE_3_UDI,
                   'properties':
                       {'info.parent':
                            (ROOT_UDI, 'str')}}
        device4 = {'id': 4,
                   'udi': self.DEVICE_4_UDI,
                   'properties':
                       {'info.parent':
                            (self.DEVICE_2_UDI,
                             'str')}}
        devices = [device1, device2, device3, device4]

        parser = SubmissionParser()
        udi_device_map = parser.getUDIDeviceMap(devices)
        udi_children = parser.getUDIChildren(udi_device_map)
        expected_data = {ROOT_UDI: [device2, device3],
                         self.DEVICE_2_UDI: [device4]}

        # The order of the children lists returned by getUDIChildren
        # depends on the order of dict.items(), hence sort the children
        # lists before comparing them.
        for children in udi_children.values():
            children.sort()
        for children in expected_data.values():
            children.sort()

        self.assertEqual(udi_children, expected_data,
                         'Invalid result of SubmissionParser.getUDIChildren')

    def testUDIDeviceMapInvalidRootNode(self):
        """The root node of the devices must have a special UDI.

        getUDIChildren ensures that the only device without an info.parent
        property has the UDI /org/freedesktop/Hal/devices/computer (ROOT_UDI).
        """
        device1 = {'id': 1,
                   'udi': 'invalid_root_node',
                   'properties': {}}
        device2 = {'id': 2,
                   'udi': self.DEVICE_2_UDI,
                   'properties':
                       {'info.parent':
                            ('invalid_root_node', 'str')}}
        devices = [device1, device2]

        parser = SubmissionParser()
        udi_device_map = parser.getUDIDeviceMap(devices)
        self.assertRaises(ValueError, parser.getUDIChildren, udi_device_map)

    def testUDIDeviceMapMissingRootNode(self):
        """If no root node exists, getUDIChildren raises a ValueError."""
        device1 = {'id': 1,
                   'udi': self.DEVICE_2_UDI,
                   'properties':
                       {'info.parent':
                            (self.DEVICE_3_UDI, 'str')}}
        device2 = {'id': 2,
                   'udi': self.DEVICE_3_UDI,
                   'properties':
                       {'info.parent':
                            (self.DEVICE_2_UDI, 'str')}}
        devices = [device1, device2]

        parser = SubmissionParser()
        udi_device_map = parser.getUDIDeviceMap(devices)
        self.assertRaises(ValueError, parser.getUDIChildren, udi_device_map)

    CIRCULAR_UDI_1 = '/org/freedesktop/Hal/devices/nonsense_1'
    CIRCULAR_UDI_2 = '/org/freedesktop/Hal/devices/nonsense_2'

    def testParentChildInconsistency(self):
        """Test of SubmissionParser.checkHALDevicesParentChildConsistency."""
        device1 = {'id': 1,
                   'udi': ROOT_UDI,
                   'properties': {}}
        device2 = {'id': 2,
                   'udi': self.DEVICE_2_UDI,
                   'properties':
                       {'info.parent':
                            (ROOT_UDI, 'str')}}
        circular_device1 = {
            'id': 3,
            'udi': self.CIRCULAR_UDI_1,
                   'properties':
                       {'info.parent':
                            (self.CIRCULAR_UDI_2, 'str')}}
        circular_device2 = {
            'id': 4,
            'udi': self.CIRCULAR_UDI_2,
                   'properties':
                       {'info.parent':
                            (self.CIRCULAR_UDI_1, 'str')}}
        devices = [device1, device2, circular_device1, circular_device2]
        parser = SubmissionParser()
        udi_device_map = parser.getUDIDeviceMap(devices)
        udi_children = parser.getUDIChildren(udi_device_map)
        circular_udis = sorted(parser.checkHALDevicesParentChildConsistency(
            udi_children))
        self.assertEqual(circular_udis,
                         [self.CIRCULAR_UDI_1, self.CIRCULAR_UDI_2],
                         'Circular parent/child relationship in UDIs not '
                         'detected')

    def testCheckUdevDictsHavePathKey(self):
        """Test of SubmissionParser.checkNodesHavePathKey()"""
        # Each dict for a udev device must have a 'P' key.
        parser = SubmissionParser(self.log)
        devices = [
            {'P': '/devices/LNXSYSTM:00'},
            {'P': '/devices/LNXSYSTM:00/ACPI_CPU:00'},
            ]
        self.assertTrue(parser.checkUdevDictsHavePathKey(devices))

        parser = SubmissionParser(self.log)
        parser.submission_key = 'Submission having udev data without "P" key'
        devices = [
            {'P': '/devices/LNXSYSTM:00'},
            {},
            ]
        self.assertFalse(parser.checkUdevDictsHavePathKey(devices))

        self.assertErrorMessage(
            parser.submission_key, 'udev node found without a "P" key')

    def testCheckUdevPciProperties(self):
        """Test of SubmissionParser.checkUdevPciProperties()."""
        # udev PCI devices must have the properties PCI_CLASS, PCI_ID,
        # PCI_SUBSYS_ID, PCI_SLOT_NAME; other devices must not have
        # these properties.
        parser = SubmissionParser()
        self.assertTrue(parser.checkUdevPciProperties(
            [self.udev_root_device, self.udev_pci_device]))

    def testCheckUdevPciPropertiesNonPciDeviceWithPciProperties(self):
        """Test of SubmissionParser.checkUdevPciProperties().

        A non-PCI device having PCI properties makes a submission invalid.
        """
        self.udev_root_device['E']['PCI_SLOT_NAME'] = '0000:00:1f.2'
        parser = SubmissionParser(self.log)
        parser.submission_key = 'invalid non-PCI device'
        self.assertFalse(parser.checkUdevPciProperties(
            [self.udev_root_device, self.udev_pci_device]))
        self.assertErrorMessage(
            parser.submission_key,
            "Non-PCI udev device with PCI properties: set(['PCI_SLOT_NAME']) "
            "'/devices/LNXSYSTM:00'")

    def testCheckUdevPciPropertiesPciDeviceWithoutRequiredProperties(self):
        """Test of SubmissionParser.checkUdevPciProperties().

        A PCI device not having a required PCI property makes a submission
        invalid.
        """
        del self.udev_pci_device['E']['PCI_CLASS']
        parser = SubmissionParser(self.log)
        parser.submission_key = 'invalid PCI device'
        self.assertFalse(parser.checkUdevPciProperties(
            [self.udev_root_device, self.udev_pci_device]))
        self.assertErrorMessage(
            parser.submission_key,
            "PCI udev device without required PCI properties: "
            "set(['PCI_CLASS']) '/devices/pci0000:00/0000:00:1f.2'")

    def testCheckUdevPciPropertiesPciDeviceWithNonIntegerPciClass(self):
        """Test of SubmissionParser.checkUdevPciProperties().

        A PCI device with a non-integer class value makes a submission
        invalid.
        """
        self.udev_pci_device['E']['PCI_CLASS'] = 'not-an-integer'
        parser = SubmissionParser(self.log)
        parser.submission_key = 'invalid PCI class value'
        self.assertFalse(parser.checkUdevPciProperties(
            [self.udev_root_device, self.udev_pci_device]))
        self.assertErrorMessage(
            parser.submission_key,
            "Invalid udev PCI class: 'not-an-integer' "
            "'/devices/pci0000:00/0000:00:1f.2'")

    def testCheckUdevPciPropertiesPciDeviceWithInvalidPciClassValue(self):
        """Test of SubmissionParser.checkUdevPciProperties().

        A PCI device with invalid class data makes a submission
        invalid.
        """
        self.udev_pci_device['E']['PCI_CLASS'] = '1234567'
        parser = SubmissionParser(self.log)
        parser.submission_key = 'too large PCI class value'
        self.assertFalse(parser.checkUdevPciProperties(
            [self.udev_root_device, self.udev_pci_device]))
        self.assertErrorMessage(
            parser.submission_key,
            "Invalid udev PCI class: '1234567' "
            "'/devices/pci0000:00/0000:00:1f.2'")

    def testCheckUdevPciPropertiesPciDeviceWithInvalidDeviceID(self):
        """Test of SubmissionParser.checkUdevPciProperties().

        A PCI device with an invalid device ID makes a submission
        invalid.
        """
        self.udev_pci_device['E']['PCI_ID'] = 'not-an-id'
        parser = SubmissionParser(self.log)
        parser.submission_key = 'invalid PCI ID'
        self.assertFalse(parser.checkUdevPciProperties(
            [self.udev_root_device, self.udev_pci_device]))
        self.assertErrorMessage(
            parser.submission_key,
            "Invalid udev PCI device ID: 'not-an-id' "
            "'/devices/pci0000:00/0000:00:1f.2'")

    def testCheckUdevPciPropertiesPciDeviceWithInvalidSubsystemID(self):
        """Test of SubmissionParser.checkUdevPciProperties().

        A PCI device with an invalid subsystem ID makes a submission
        invalid.
        """
        self.udev_pci_device['E']['PCI_SUBSYS_ID'] = 'not-a-subsystem-id'
        parser = SubmissionParser(self.log)
        parser.submission_key = 'invalid PCI subsystem ID'
        self.assertFalse(parser.checkUdevPciProperties(
            [self.udev_root_device, self.udev_pci_device]))
        self.assertErrorMessage(
            parser.submission_key,
            "Invalid udev PCI device ID: 'not-a-subsystem-id' "
            "'/devices/pci0000:00/0000:00:1f.2'")

    def testCheckUdevUsbProperties(self):
        """Test of SubmissionParser.checkUdevUsbProperties().

        udev nodes for USB devices must define the three properties
        DEVTYPE, PRODUCT, TYPE or none of them.
        """
        parser = SubmissionParser()
        self.assertTrue(parser.checkUdevUsbProperties(
            [self.udev_root_device, self.udev_usb_device,
             self.udev_usb_interface]))

        for property_name in ('DEVTYPE', 'PRODUCT', 'TYPE'):
            del self.udev_usb_device['E'][property_name]
        self.assertTrue(parser.checkUdevUsbProperties(
            [self.udev_root_device, self.udev_usb_device,
             self.udev_usb_interface]))

    def testCheckUdevUsbProperties_missing_required_property(self):
        """Test of SubmissionParser.checkUdevUsbProperties().

        A USB device where some but not all of the properties DEVTYPE,
        PRODUCT, TYPE are defined makes a submission invalid.
        """
        for property_name in ('DEVTYPE', 'PRODUCT', 'TYPE'):
            saved_property = self.udev_usb_device['E'].pop(property_name)
            parser = SubmissionParser(self.log)
            parser.submission_key = (
                'USB device without %s property' % property_name)
            self.assertFalse(parser.checkUdevUsbProperties(
                [self.udev_root_device, self.udev_usb_device]))
            self.assertErrorMessage(
                parser.submission_key,
                "USB udev device found without required properties: "
                "set(['%s']) '/devices/pci0000:00/0000:00:1d.1/usb3/3-2'"
                % property_name)
            self.udev_usb_device['E'][property_name] = saved_property

    def testCheckUdevUsbProperties_with_invalid_product_id(self):
        """Test of SubmissionParser.checkUdevUsbProperties().

        A USB device with an invalid product ID makes a submission
        invalid.
        """
        self.udev_usb_device['E']['PRODUCT'] = 'not-a-valid-usb-product-id'
        parser = SubmissionParser(self.log)
        parser.submission_key = 'USB device with invalid product ID'
        self.assertFalse(parser.checkUdevUsbProperties(
            [self.udev_root_device, self.udev_usb_device]))
        self.assertErrorMessage(
            parser.submission_key,
            "USB udev device found with invalid product ID: "
            "'not-a-valid-usb-product-id' "
            "'/devices/pci0000:00/0000:00:1d.1/usb3/3-2'")

    def testCheckUdevUsbProperties_with_invalid_type_data(self):
        """Test of SubmmissionParser.checkUdevUsbProperties().

        A USB device with invalid type data makes a submission invalid.
        """
        self.udev_usb_device['E']['TYPE'] = 'no-type'
        parser = SubmissionParser(self.log)
        parser.submission_key = 'USB device with invalid type data'
        self.assertFalse(parser.checkUdevUsbProperties(
            [self.udev_root_device, self.udev_usb_device]))
        self.assertErrorMessage(
            parser.submission_key,
            "USB udev device found with invalid type data: 'no-type' "
            "'/devices/pci0000:00/0000:00:1d.1/usb3/3-2'")

    def testCheckUdevUsbProperties_with_invalid_devtype(self):
        """Test of SubmmissionParser.checkUdevUsbProperties().

        A udev USB device must have DEVTYPE set to 'usb_device' or
        'usb_interface'.
        """
        self.udev_usb_device['E']['DEVTYPE'] = 'nonsense'
        parser = SubmissionParser(self.log)
        parser.submission_key = 'USB device with invalid DEVTYPE'
        self.assertFalse(parser.checkUdevUsbProperties(
            [self.udev_root_device, self.udev_usb_device]))
        self.assertErrorMessage(
            parser.submission_key,
            "USB udev device found with invalid udev type data: 'nonsense' "
            "'/devices/pci0000:00/0000:00:1d.1/usb3/3-2'")

    def testCheckUdevUsbProperties_interface_without_interface_property(self):
        """Test of SubmmissionParser.checkUdevUsbProperties().

        A udev USB device for a USB interface have the property INTERFACE.
        """
        del self.udev_usb_interface['E']['INTERFACE']
        parser = SubmissionParser(self.log)
        parser.submission_key = 'USB interface without INTERFACE property'
        self.assertFalse(parser.checkUdevUsbProperties(
            [self.udev_root_device, self.udev_usb_interface]))
        self.assertErrorMessage(
            parser.submission_key,
            "USB interface udev device found without INTERFACE property: "
            "'/devices/pci0000:00/0000:00:1d.1/usb3/3-2/3-2:1.1'")

    def testCheckUdevUsbProperties_interface_invalid_interface_property(self):
        """Test of SubmmissionParser.checkUdevUsbProperties().

        The INTERFACE proeprty of A udev USB device for a USB interface
        must have value in the format main_class/sub_class/version
        """
        self.udev_usb_interface['E']['INTERFACE'] = 'nonsense'
        parser = SubmissionParser(self.log)
        parser.submission_key = 'USB interface with invalid INTERFACE data'
        self.assertFalse(parser.checkUdevUsbProperties(
            [self.udev_root_device, self.udev_usb_interface]))
        self.assertErrorMessage(
            parser.submission_key,
            "USB Interface udev device found with invalid INTERFACE "
            "property: 'nonsense' "
            "'/devices/pci0000:00/0000:00:1d.1/usb3/3-2/3-2:1.1'")

    def testCheckUdevScsiProperties(self):
        """Test of SubmissionParser.checkUdevScsiProperties()."""
        parser = SubmissionParser()
        sysfs_data = {
            self.udev_scsi_device['P']: self.sysfs_scsi_device,
            }
        self.assertTrue(
            parser.checkUdevScsiProperties(
                [self.udev_root_device, self.udev_scsi_device], sysfs_data))

    def testCheckUdevScsiProperties_data_is_none(self):
        """Test of SubmissionParser.checkUdevScsiProperties().

        checkUdevScsiProperties() even if no sysfs properties are
        available.
        """
        parser = SubmissionParser()
        self.assertTrue(
            parser.checkUdevScsiProperties(
                [self.udev_root_device, self.udev_scsi_device], None))

    def testCheckUdevScsiProperties_missing_devtype(self):
        """Test of SubmissionParser.checkUdevScsiProperties().

        Each udev SCSI node must define the DEVTYPE property.
        """
        del self.udev_scsi_device['E']['DEVTYPE']
        parser = SubmissionParser(self.log)
        parser.submission_key = 'udev SCSI device without DEVTYPE'
        sysfs_data = {
            self.udev_scsi_device['P']: self.sysfs_scsi_device,
            }
        self.assertFalse(
            parser.checkUdevScsiProperties(
                [self.udev_root_device, self.udev_scsi_device], sysfs_data))
        self.assertErrorMessage(
            parser.submission_key,
            "SCSI udev node found without DEVTYPE property: "
            "'/devices/pci0000:00/0000:00:1f.1/host4/target4:0:0/4:0:0:0'")

    def testCheckUdevScsiProperties_no_sysfs_data(self):
        """Test of SubmissionParser.checkUdevScsiProperties().

        Each udev SCSI node must have a corresponding sysfs node.
        """
        parser = SubmissionParser(self.log)
        parser.submission_key = 'udev SCSI device without sysfs data'
        sysfs_data = {}
        self.assertFalse(
            parser.checkUdevScsiProperties(
                [self.udev_root_device, self.udev_scsi_device], sysfs_data))
        self.assertErrorMessage(
            parser.submission_key,
            "SCSI udev device node found without related sysfs record: "
            "'/devices/pci0000:00/0000:00:1f.1/host4/target4:0:0/4:0:0:0'")

    def testCheckUdevScsiProperties_missing_sysfs_attributes(self):
        """Test of SubmissionParser.checkUdevScsiProperties().

        Each sysfs node for a udev SCSI node must have a the attribues
        vendor, model and type.
        """
        del self.sysfs_scsi_device['model']
        parser = SubmissionParser(self.log)
        parser.submission_key = 'udev SCSI device with incomplete sysfs data'
        sysfs_data = {
            self.udev_scsi_device['P']: self.sysfs_scsi_device,
            }
        self.assertFalse(
            parser.checkUdevScsiProperties(
                [self.udev_root_device, self.udev_scsi_device], sysfs_data))
        self.assertErrorMessage(
            parser.submission_key,
            "SCSI udev device found without required sysfs attributes: "
            "set(['model']) "
            "'/devices/pci0000:00/0000:00:1f.1/host4/target4:0:0/4:0:0:0'")

    class UdevTestSubmissionParser(SubmissionParser):
        """A variant of SubmissionParser that shortcuts udev related tests.

        All shortcut methods return True.
        """
        def checkUdevDictsHavePathKey(self, udev_nodes):
            """See `SubmissionParser`."""
            return True

        def checkUdevPciProperties(self, udev_data):
            """See `SubmissionParser`."""
            return True

        def checkUdevUsbProperties(self, udev_data):
            """See `SubmissionParser`."""
            return True

        def checkUdevScsiProperties(self, udev_data, sysfs_data):
            """See `SubmissionParser`."""
            return True

        def checkUdevDmiData(self, dmi_data):
            """See `SubmissionParser`."""
            return True

    validate_mock_class(UdevTestSubmissionParser)

    def testCheckConsistentUdevDeviceData(self):
        """Test of SubmissionParser.checkConsistentUdevDeviceData(),"""
        parser = self.UdevTestSubmissionParser()
        self.assertTrue(parser.checkConsistentUdevDeviceData(
            None, None, None))

    def testCheckConsistentUdevDeviceData_invalid_path_data(self):
        """Test of SubmissionParser.checkConsistentUdevDeviceData(),

        Detection of invalid path data lets the check fail.
        """
        class SubmissionParserUdevPathCheckFails(
            self.UdevTestSubmissionParser):
            """A SubmissionPaser where checkUdevDictsHavePathKey() fails."""

            def checkUdevDictsHavePathKey(self, udev_nodes):
                """See `SubmissionParser`."""
                return False

        validate_mock_class(SubmissionParserUdevPathCheckFails)

        parser = SubmissionParserUdevPathCheckFails()
        self.assertFalse(parser.checkConsistentUdevDeviceData(
            None, None, None))

    def testCheckConsistentUdevDeviceData_invalid_pci_data(self):
        """Test of SubmissionParser.checkConsistentUdevDeviceData(),

        Detection of invalid PCI data lets the check fail.
        """
        class SubmissionParserUdevPciCheckFails(
            self.UdevTestSubmissionParser):
            """A SubmissionPaser where checkUdevPciProperties() fails."""

            def checkUdevPciProperties(self, udev_data):
                """See `SubmissionParser`."""
                return False

        validate_mock_class(SubmissionParserUdevPciCheckFails)

        parser = SubmissionParserUdevPciCheckFails()
        self.assertFalse(parser.checkConsistentUdevDeviceData(
            None, None, None))

    def testCheckConsistentUdevDeviceData_invalid_usb_data(self):
        """Test of SubmissionParser.checkConsistentUdevDeviceData(),

        Detection of invalid USB data lets the check fail.
        """
        class SubmissionParserUdevUsbCheckFails(
            self.UdevTestSubmissionParser):
            """A SubmissionPaser where checkUdevUsbProperties() fails."""

            def checkUdevUsbProperties(self, udev_data):
                """See `SubmissionParser`."""
                return False

        validate_mock_class(SubmissionParserUdevUsbCheckFails)

        parser = SubmissionParserUdevUsbCheckFails()
        self.assertFalse(parser.checkConsistentUdevDeviceData(
            None, None, None))

    def testCheckConsistentUdevDeviceData_invalid_scsi_data(self):
        """Test of SubmissionParser.checkConsistentUdevDeviceData(),

        Detection of invalid SCSI data lets the check fail.
        """
        class SubmissionParserUdevUsbCheckFails(
            self.UdevTestSubmissionParser):
            """A SubmissionPaser where checkUdevScsiProperties() fails."""

            def checkUdevScsiProperties(self, udev_data, sysfs_data):
                """See `SubmissionParser`."""
                return False

        validate_mock_class(SubmissionParserUdevUsbCheckFails)

        parser = SubmissionParserUdevUsbCheckFails()
        self.assertFalse(parser.checkConsistentUdevDeviceData(
            None, None, None))

    def testCheckConsistentUdevDeviceData_invalid_dmi_data(self):
        """Test of SubmissionParser.checkConsistentUdevDeviceData(),

        Detection of invalid DMI data lets the check fail.
        """
        class SubmissionParserUdevUsbCheckFails(
            self.UdevTestSubmissionParser):
            """A SubmissionPaser where checkUdevDmiData() fails."""

            def checkUdevDmiData(self, dmi_data):
                """See `SubmissionParser`."""
                return False

        validate_mock_class(SubmissionParserUdevUsbCheckFails)

        parser = SubmissionParserUdevUsbCheckFails()
        self.assertFalse(parser.checkConsistentUdevDeviceData(
            None, None, None))

    class MockSubmissionParser(SubmissionParser):
        """A SubmissionParser variant for testing checkCOnsistentData()

        All "method substitutes" return a valid result.
        """

        def findDuplicateIDs(self, parsed_data):
            return set()

        def findInvalidIDReferences(self, parsed_data):
            return set()

        def getUDIDeviceMap(self, devices):
            return {}

        def getUDIChildren(self, udi_device_map):
            return {}

        def checkHALDevicesParentChildConsistency(self, udi_children):
            return []

        def checkConsistentUdevDeviceData(
            self, udev_data, sysfs_data, dmi_data):
            return True

    validate_mock_class(MockSubmissionParser)

    def assertErrorMessage(self, submission_key, log_message):
        """Search for message in the log entries for submission_key.

        assertErrorMessage requires that
        (a) a log message starts with "Parsing submisson <submission_key>:"
        (b) the error message passed as the parameter message appears
            in a log string that matches (a)
        (c) result, which is supposed to contain an object representing
            the result of parsing a submission, is None.
        (d) the log level is ERROR.

        If all four criteria match, assertErrormessage does not raise any
        exception.
        """
        expected_message = ('Parsing submission %s: %s'
                            % (submission_key, log_message))
        for r in self.handler.records:
            if r.levelno != logging.ERROR:
                continue
            candidate = r.getMessage()
            if candidate == expected_message:
                return
        raise AssertionError('No log message found: %s' % expected_message)

    def assertWarningMessage(self, submission_key, log_message):
        """Search for message in the log entries for submission_key.

        assertErrorMessage requires that
        (a) a log message starts with "Parsing submisson <submission_key>:"
        (b) the error message passed as the parameter message appears
            in a log string that matches (a)
        (c) result, which is supposed to contain an object representing
            the result of parsing a submission, is None.
        (d) the log level is WARNING.

        If all four criteria match, assertWarningMessage does not raise any
        exception.
        """
        expected_message = ('Parsing submission %s: %s'
                            % (submission_key, log_message))
        for r in self.handler.records:
            if r.levelno != logging.WARNING:
                continue
            candidate = r.getMessage()
            if candidate == expected_message:
                return
        raise AssertionError('No log message found: %s' % expected_message)

    def testConsistencyCheck(self):
        """Test of SubmissionParser.checkConsistency."""
        parser = self.MockSubmissionParser()
        result = parser.checkConsistency({'hardware':
                                              {'hal': {'devices': []}}})
        self.assertEqual(result, True,
                         'checkConsistency failed, but all partial checks '
                         'succeeded')

    def testConsistencyCheckValidUdevData(self):
        """Test of SubmissionParser.checkConsistency."""
        parser = self.MockSubmissionParser()
        self.assertTrue(parser.checkConsistency(
            {
                'hardware': {
                    'udev': None,
                    'sysfs-attributes': None,
                    'dmi': None,
                    }
                }
            ))

    def testConsistencyCheck_invalid_udev_data(self):
        """Test of SubmissionParser.checkConsistency."""
        class MockSubmissionParserBadUdevDeviceData(
            self.MockSubmissionParser):
            """A parser where checkConsistentUdevDeviceData() fails."""

            def checkConsistentUdevDeviceData(self, udev_data, sysfs_data,
                                              dmi_data):
                return False

        validate_mock_class(MockSubmissionParserBadUdevDeviceData)

        parser = MockSubmissionParserBadUdevDeviceData()
        self.assertFalse(parser.checkConsistency(
            {
                'hardware': {
                    'udev': None,
                    'sysfs-attributes': None,
                    'dmi': None,
                    }
                }
            ))

    def testConsistencyCheckWithDuplicateIDs(self):
        """SubmissionParser.checkConsistency detects duplicate IDs."""
        class MockSubmissionParserDuplicateIds(
            self.MockSubmissionParser):
            """A parser where findDuplicateIDs() fails."""

            def findDuplicateIDs(self, parsed_data):
                return set([1])

        validate_mock_class(MockSubmissionParserDuplicateIds)

        parser = MockSubmissionParserDuplicateIds(self.log)
        parser.submission_key = 'Consistency check detects duplicate IDs'
        result = parser.checkConsistency({'hardware':
                                              {'hal': {'devices': []}}})
        self.assertEqual(result, False,
                         'checkConsistency did not detect duplicate IDs')
        self.assertErrorMessage('Consistency check detects duplicate IDs',
                                'Duplicate IDs found: set([1])')

    def testConsistencyCheckWithInvalidIDReferences(self):
        """SubmissionParser.checkConsistency detects invalid ID references."""
        class MockSubmissionParserInvalidIDReferences(
            self.MockSubmissionParser):
            """A parser where findInvalidIDReferences() fails."""
            def findInvalidIDReferences(self, parsed_data):
                return set([1])

        validate_mock_class(MockSubmissionParserInvalidIDReferences)

        parser = MockSubmissionParserInvalidIDReferences(self.log)
        parser.submission_key = 'Consistency check detects invalid ID refs'
        result = parser.checkConsistency({'hardware':
                                              {'hal': {'devices': []}}})
        self.assertEqual(result, False,
                         'checkConsistency did not detect invalid ID refs')
        self.assertErrorMessage('Consistency check detects invalid ID refs',
                                'Invalid ID references found: set([1])')

    def testConsistencyCheckWithDuplicateUDI(self):
        """SubmissionParser.checkConsistency detects duplicate UDIs."""
        class MockSubmissionParserUDIDeviceMapFails(
            self.MockSubmissionParser):
            """A parser where getUDIDeviceMap() fails."""

            def getUDIDeviceMap(self, devices):
                raise ValueError(
                    'Duplicate UDI: /org/freedesktop/Hal/devices/computer')

        validate_mock_class(MockSubmissionParserUDIDeviceMapFails)

        parser = MockSubmissionParserUDIDeviceMapFails(self.log)
        parser.submission_key = 'Consistency check detects invalid ID refs'
        result = parser.checkConsistency({'hardware':
                                              {'hal': {'devices': []}}})
        self.assertEqual(result, False,
                         'checkConsistency did not detect duplicate UDIs')
        self.assertErrorMessage(
            'Consistency check detects invalid ID refs',
            'Duplicate UDI: /org/freedesktop/Hal/devices/computer')

    def testConsistencyCheckChildUDIWithoutParent(self):
        """SubmissionParser.checkConsistency detects "orphaned" devices."""
        class MockSubmissionParserUDIChildrenFails(
            self.MockSubmissionParser):
            """A parser where getUDIChildren() fails."""

            def getUDIChildren(self, udi_device_map):
                raise ValueError('Unknown parent UDI /foo in <device id="3">')

        validate_mock_class(MockSubmissionParserUDIChildrenFails)

        parser = MockSubmissionParserUDIChildrenFails(self.log)
        parser.submission_key = 'Consistency check detects invalid ID refs'
        result = parser.checkConsistency({'hardware':
                                              {'hal': {'devices': []}}})
        self.assertEqual(result, False,
                         'checkConsistency did not detect orphaned devices')
        self.assertErrorMessage(
            'Consistency check detects invalid ID refs',
            'Unknown parent UDI /foo in <device id="3">')

    def testConsistencyCheckCircularParentChildRelation(self):
        """SubmissionParser.checkConsistency detects "orphaned" devices."""
        class MockSubmissionParserHALDevicesParentChildConsistency(
            self.MockSubmissionParser):
            """A parser where checkHALDevicesParentChildConsistency() fails.
            """

            def checkHALDevicesParentChildConsistency(self, udi_children):
                return ['/foo', '/bar']

        validate_mock_class(
            MockSubmissionParserHALDevicesParentChildConsistency)

        parser = MockSubmissionParserHALDevicesParentChildConsistency(
            self.log)
        parser.submission_key = ('Consistency check detects circular '
                                 'parent-child relationships')
        result = parser.checkConsistency({'hardware':
                                              {'hal': {'devices': []}}})
        self.assertEqual(result, False,
                         'checkConsistency did not detect circular parent/'
                             'child relationship')
        self.assertErrorMessage(
            'Consistency check detects circular parent-child relationships',
            "Found HAL devices with circular parent/child "
                "relationship: ['/foo', '/bar']")
