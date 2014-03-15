# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests of the HWDB submissions parser."""

from datetime import datetime
import logging
import os
import re

from zope.testing.loghandler import Handler

from lp.hardwaredb.scripts.hwdbsubmissions import SubmissionParser
from lp.services.config import config
from lp.services.scripts.logger import OopsHandler
from lp.testing import TestCase
from lp.testing.layers import BaseLayer


class TestHWDBSubmissionRelaxNGValidation(TestCase):
    """Tests of the Relax NG validation of the HWDB submission parser."""

    layer = BaseLayer

    submission_count = 0

    def setUp(self):
        """Setup the test environment."""
        super(TestHWDBSubmissionRelaxNGValidation, self).setUp()
        self.log = logging.getLogger('test_hwdb_submission_parser')
        self.log.setLevel(logging.INFO)
        self.handler = Handler(self)
        self.handler.add(self.log.name)

        sample_data_path = os.path.join(
            config.root, 'lib', 'lp', 'hardwaredb', 'scripts',
            'tests', 'hardwaretest.xml')
        self.sample_data = open(sample_data_path).read()

    def runValidator(self, sample_data):
        """Run the Relax NG validator.

        Create a unique submission ID to ensure that an error message
        expected in a test is indeed created by this test.
        """
        self.submission_count += 1
        submission_id = 'submission_%i' % self.submission_count
        result = SubmissionParser(self.log)._getValidatedEtree(sample_data,
                                                               submission_id)
        return result, submission_id

    def insertSampledata(self, data, insert_text, where, after=False):
        """Insert text into the sample data `data`.

        Insert the text `insert_text` before the first occurrence of
        `where` in `data`.
        """
        insert_position = data.find(where)
        if after:
            insert_position += len(where)
        return data[:insert_position] + insert_text + data[insert_position:]

    def replaceSampledata(self, data, replace_text, from_text, to_text):
        """Replace text in the sample data `data`.

        Search for the first occurrence of `from_text` in data, and for the
        first occurrence of `to_text` (after `from_text`) in `data`.
        Replace the text between `from_text` and `to_text` by `replace_text`.
        The strings `from_text` are `to_text` are part of the text which is
        replaced.
        """
        start_replace = data.find(from_text)
        end_replace = data.find(to_text, start_replace) + len(to_text)
        return data[:start_replace] + replace_text + data[end_replace:]

    def testNoXMLData(self):
        """The raw submission data must be XML."""
        sample_data = 'No XML'
        result, submission_id = self.runValidator(sample_data)
        self.handler.assertLogsMessage(
            "Parsing submission %s: "
                "syntax error: line 1, column 0" % submission_id,
            logging.ERROR)
        self.assertEqual(result, None, 'Expected detection of non-XML data')

    def testInvalidRootNode(self):
        """The root node must be <system>."""
        sample_data = '<?xml version="1.0" ?><nosystem/>'
        result, submission_id = self.runValidator(sample_data)
        self.handler.assertLogsMessage(
            "Parsing submission %s: root node is not '<system>'"
                % submission_id,
            logging.ERROR)
        self.assertEqual(result, None,
                         'Invalid root node not detected')

    def testBadDataInCommentNode(self):
        """Many submissions contain ESC symbols in <comment> nodes.

        The cElementTree parser does not accept this; The processing
        script deals with this by emptying all <comment> nodes before
        building the element tree. (Note that we don't process data
        from this node at all.)
        """
        bad_comment_node = "\n<comment>\x1b</comment>"
        sample_data = self.replaceSampledata(
            self.sample_data, bad_comment_node, "<comment>", "</comment>")
        validated, submission_id = self.runValidator(sample_data)
        self.assertTrue(validated is not None)

    def test_fixFrequentErrors_two_comments(self):
        # The regular expression used in fixFrequentErrors() does not
        # delete the content between two <comment> nodes.
        two_comments = "<comment></comment>something else<comment></comment>"
        parser = SubmissionParser()
        self.assertEqual(
            '<comment/>something else<comment/>',
            parser.fixFrequentErrors(two_comments),
            'Bad regular expression in fixFrequentErrors()')

    def test_bad_data_does_not_oops(self):
        # If the processing cronscript gets bad data, it should log it, but
        # it should not create an Oops.
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text=('<dmi>'
                '/sys/class/dmi/id/bios_vendor:Dell Inc.'
                '/sys/class/dmi/id/bios_version:A12'
                '</dmi>'),
            where='<hardware>',
            after=True)
        # Add the OopsHandler to the log, because we want to make sure this
        # doesn't create an Oops report (which a high value log would cause).
        self.assertEqual([], self.oopses)
        logging.getLogger('test_hwdb_submission_parser').addHandler(
            OopsHandler(self.log.name))
        result, submission_id = self.runValidator(sample_data)
        self.assertEqual([], self.oopses)

    def testInvalidFormatVersion(self):
        """The attribute `format` of the root node must be `1.0`."""
        sample_data = '<?xml version="1.0" ?><system version="nonsense"/>'
        result, submission_id = self.runValidator(sample_data)
        self.handler.assertLogsMessage(
            "Parsing submission %s: invalid submission format version: "
                "'nonsense'" % submission_id,
            logging.ERROR)
        self.assertEqual(result, None,
                         'Unknown submission format version not detected')

    def testMissingFormatVersion(self):
        """The root node must have the attribute `version`."""
        sample_data = '<?xml version="1.0" ?><system/>'
        result, submission_id = self.runValidator(sample_data)
        self.handler.assertLogsMessage(
            "Parsing submission %s: invalid submission format version: None"
                % submission_id,
            logging.ERROR)
        self.assertEqual(result, None,
                         'Missing submission format attribute not detected')

    def _setEncoding(self, encoding):
        """Set the encoding in the sample data to `encoding`."""
        return self.replaceSampledata(
            data=self.sample_data,
            replace_text='<?xml version="1.0" encoding="%s"?>' % encoding,
            from_text='<?xml',
            to_text='?>')

    def testAsciiEncoding(self):
        """Validation of ASCII encoded XML data.

        Bytes with bit 7 set must be detected as invalid.
        """
        sample_data_ascii_encoded = self._setEncoding('US-ASCII')
        result, submission_id = self.runValidator(sample_data_ascii_encoded)
        self.assertNotEqual(result, None,
                            'Valid submission with ASCII encoding rejected')

        tag_with_umlaut = u'<architecture value="\xc4"/>'
        tag_with_umlaut = tag_with_umlaut.encode('iso-8859-1')
        sample_data = self.replaceSampledata(
            data=sample_data_ascii_encoded,
            replace_text=tag_with_umlaut,
            from_text='<architecture',
            to_text='/>')
        result, submission_id = self.runValidator(sample_data)
        self.assertEqual(result, None,
                         'Invalid submission with ASCII encoding accepted')
        self.handler.assertLogsMessage(
            "Parsing submission %s: "
                "not well-formed (invalid token): line 28, column 25"
                % submission_id,
            logging.ERROR)

    def testISO8859_1_Encoding(self):
        """XML data with ISO-8859-1 may have bytes with bit 7 set."""
        sample_data_iso_8859_1_encoded = self._setEncoding('ISO-8859-1')
        tag_with_umlaut = '<architecture value="\xc4"/>'
        sample_data = self.replaceSampledata(
            data=sample_data_iso_8859_1_encoded,
            replace_text=tag_with_umlaut,
            from_text='<architecture',
            to_text='/>')
        result, submission_id = self.runValidator(sample_data)
        self.assertNotEqual(result, None,
                            'Valid submission with ISO-8859-1 encoding '
                                'rejected')

    def testUTF8Encoding(self):
        """UTF-8 encoded data is properly detected and parsed."""
        sample_data_utf8_encoded = self._setEncoding('UTF-8')
        umlaut = u'\xc4'.encode('utf8')
        tag = '<architecture value="%s"/>'
        tag_with_valid_utf8 = tag % umlaut
        sample_data = self.replaceSampledata(
            data=sample_data_utf8_encoded,
            replace_text=tag_with_valid_utf8,
            from_text='<architecture',
            to_text='/>')
        result, submission_id = self.runValidator(sample_data)
        self.assertNotEqual(result, None,
                            'Valid submission with UTF-8 encoding rejected')

        # Broken UTF8 encoding is detected.
        tag_with_broken_utf8 = tag % umlaut[0]
        sample_data = self.replaceSampledata(
            data=tag_with_broken_utf8,
            replace_text=tag_with_broken_utf8,
            from_text='<architecture',
            to_text='/>')
        result, submission_id = self.runValidator(sample_data)
        self.assertEqual(result, None,
                         'Invalid submissison with UTF-8 encoding accepted')
        self.handler.assertLogsMessage(
            "Parsing submission %s: "
                "not well-formed (invalid token): line 1, column 21"
                % submission_id,
            logging.ERROR)

    # Using self.log.assertLogsMessage, the usual way to assert the
    # existence of an error or warning in the log data, leads to
    # quite unreadable code for many tests in this module:
    #
    # The error messages produced by the Relax NG validator and logged
    # in self.log are often several lines long, and contain "context
    # information" which is not of much interest for a functional test.
    # Moreover, many lines of the messages are more than 80 characters
    # long.

    def assertErrorMessage(self, submission_key, result, messages, test):
        """Search for message in the log entries for submission_key.

        assertErrorMessage requires that
        (a) a log message starts with "Parsing submisson <submission_key>:"
        (b) the error message passed as the parameter message appears
            in a log string that matches (a)
        (c) result, which is supposed to contain an object representing
            the result of parsing a submission, is None.

        If all three criteria match, assertErrormessage does not raise any
        exception.
        """
        self.assertEqual(
            result, None,
            'The test %s failed: The parsing result is not None.' % test)
        if isinstance(messages, basestring):
            messages = (messages, )
        last_log_messages = []
        for r in self.handler.records:
            if r.levelno != logging.ERROR:
                continue
            candidate = r.getMessage()
            if candidate.startswith('Parsing submission %s:'
                                    % submission_key):
                for message in messages:
                    if re.search(
                        '(:\d+: element .*?: )?Relax-NG validity error : %s$'
                        % re.escape(message),
                        candidate, re.MULTILINE):
                        return
                else:
                    last_log_messages.append(candidate)
        expected_messages = ' or '.join(
            repr(message) for message in messages)
        failmsg = [
            "No error log message for submission %s (testing %s) contained %s"
                % (submission_key, test, expected_messages)]
        if last_log_messages:
            failmsg.append('Log messages for the submission:')
            failmsg.extend(last_log_messages)
        else:
            failmsg.append('No messages logged for this submission')

        self.fail('\n'.join(failmsg))

    def testAssertErrorMessage(self):
        """Test the assertErrorMessage method."""
        log_template = ('Parsing submission %s:\n'
                        '-:%i: element node_name: Relax-NG validity error :'
                        ' %s')
        self.log.error(log_template % ('assert_test_1', 123, 'log message 1'))
        self.log.error(log_template % ('assert_test_1', 234, 'log message 2'))
        self.log.error(log_template % ('assert_test_2', 345, 'log message 2'))
        self.log.error(log_template % ('assert_test_2', 456, 'log message 3'))

        # assertErrorMessage requires that
        # (a) a log message starts with "Parsing submisson <submission-key>:"
        # (b) the error message passed as the parameter message appears
        #     in a log string that matches (a)
        # (c) result, which is supposed to contain an object representing
        #     the result of parsing a submission, is None.

        # If all three criteria match, assertErrorMessage does not raise any
        # exception
        self.assertErrorMessage('assert_test_1', None, 'log message 1',
                                'assertErrorMessage test 1')

        # If a log message does not exist for a given submission,
        # assertErrorMessage raises failureExeception.
        self.assertRaises(
            self.failureException, self.assertErrorMessage, 'assert_test_1',
            None, 'log message 3', 'assertErrorMessage test 2')

        # If the parameter result is not None, assertErrorMessage
        # assertErrorMessage raises failureExeception.
        self.assertRaises(
            self.failureException, self.assertErrorMessage, 'assert_test_1',
            {}, 'log message 1', 'assertErrorMessage test 3')

    def testSubtagsOfSystem(self):
        """The root node <system> requires a fixed set of sub-tags."""
        # The omission of any of these tags leads to an error during
        # the Relax NG validation.
        sub_tags = ('summary', 'hardware', 'software', 'questions')
        for tag in sub_tags:
            sample_data = self.replaceSampledata(
                data=self.sample_data,
                replace_text='',
                from_text='<%s>' % tag,
                to_text='</%s>' % tag)
            result, submission_id = self.runValidator(sample_data)
            self.assertErrorMessage(
                submission_id, result,
                'Expecting an element %s, got nothing' % tag,
                'missing sub-tag <%s> of <system>' % tag)

        # Adding any other tag as a subnode of <system> makes the
        # submission data invalid.
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text='<nonsense/>',
            where='</system>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Element system has extra content: nonsense',
            'invalid sub-tag of <system>')

        # Repeating one of the allowed sub-tags of <system> makes the
        # submission data invalid.
        for tag in sub_tags:
            sample_data = self.insertSampledata(
                data=self.sample_data,
                insert_text='<%s/>' % tag,
                where='</system>')
            result, submission_id = self.runValidator(sample_data)
            self.assertErrorMessage(
                submission_id, result,
                'Extra element %s in interleave' % tag,
                'duplicate sub-tag <%s> of <system>' % tag)

    def testSummaryRequiredTags(self):
        """The <summary> section requires a fixed set of sub-tags.

        If any of these tags is omitted, the submission data becomes invalid.
        """
        for tag in ('live_cd', 'system_id', 'distribution', 'distroseries',
                    'architecture', 'private', 'contactable', 'date_created'):
            sample_data = self.replaceSampledata(
                data=self.sample_data,
                replace_text='',
                from_text='<%s' % tag,
                to_text='/>')
            result, submission_id = self.runValidator(sample_data)
            self.assertErrorMessage(
                submission_id, result,
                'Expecting an element %s, got nothing' % tag,
                'missing sub-tag <%s> of <summary>' % tag)

        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='',
            from_text='<client',
            to_text='</client>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Expecting an element client, got nothing',
            'missing sub-tag <client> of <summary>')

    def testAdditionalSummaryTags(self):
        """Arbitrary tags are forbidden as sub-tags of <summary>.

        The only allowed tags are specified by the Relax NG schema:
        live_cd, system_id, distribution, distroseries, architecture,
        private, contactable, date_created (tested in
        testSummaryRequiredTags()), and the optional tag <kernel-release>.
        """
        # we can add the tag <kernel-release>
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text='<kernel-release value="2.6.28-15-generic"/>',
            where='</summary>')
        result, submission_id = self.runValidator(sample_data)
        self.assertNotEqual(
            result, None,
            'Valid submission containing a <kernel-release> tag rejected.')

        # Adding any other tag is not possible.
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text='<nonsense/>',
            where='</summary>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Element summary has extra content: nonsense',
            'invalid sub-tag <nonsense/> of <summary>')

    def testSummaryValidationOfBooleanSubtags(self):
        """Validation of boolean tags in the <summary> section.

        These tags may only have the attribute 'value', and the
        value of this attribute must be 'True' or 'False'.
        """
        # The only allowed values for the "boolean" tags (live_cd, private,
        # contactable) are 'True' and 'False'. In self.sample_data, 'False'
        # is set for all three tags. In all three tags, the value may also
        # be 'True'.
        for tag in ('live_cd', 'private', 'contactable'):
            sample_data = self.sample_data.replace(
                '<%s value="False"/>' % tag,
                '<%s value="True"/>' % tag)
            result, submission_id = self.runValidator(sample_data)
            self.assertNotEqual(result, None,
                                'Valid boolean sub-tag <%s value="False"> '
                                    'of <summary> rejected')

            # Other values than 'True' and 'False' are rejected by the
            # Relax NG validation.
            sample_data = self.sample_data.replace(
                '<%s value="False"/>' % tag,
                '<%s value="nonsense"/>' % tag)
            result, submission_id = self.runValidator(sample_data)
            self.assertErrorMessage(
                submission_id, result,
                'Element %s failed to validate attributes' % tag,
                'boolean sub-tags of <summary>: invalid attribute '
                    'value of <%s>' % tag)

    def testDateCreatedParsing(self):
        """Parsing of the date_created value.

        The parser expects a valid datetime value (ISO format) in the
        date_created tag, like

        "2007-01-01T01:02:03.400000"
        "2007-01-01T01:02:03Z"
        "2007-01-01T01:02:03:600+01:00"

        The fractional part of the seconds is optional as well as the
        time zone information ('Z' for UTC or an offset in hh:mm).
        """
        self.assertValidDateTime('2007-09-28T16:09:20.126842',
                                  datetime(2007, 9, 28, 16, 9, 20, 126842))

        # The Relax NG validator detects missing digits in the numbers for
        # year, month, day, hour, minute, second.
        missing_digits = (
            '200-09-28T16:09:20.126842',
            '2007-9-28T16:09:20.126842',
            '2007-09-8T16:09:20.126842',
            '2007-09-28T6:09:20.126842',
            '2007-09-28T16:9:20.126842',
            '2007-09-28T16:09:2.126842')
        for invalid_datetime in missing_digits:
            self.assertDateErrorIsDetected(invalid_datetime)

        # Only digits are allowed in date and time numbers.
        no_digits = (
            'x007-09-28T16:09:20.126842',
            '2007-x9-28T16:09:20.126842',
            '2007-09-x8T16:09:20.126842',
            '2007-09-28Tx6:09:20.126842',
            '2007-09-28T16:x9:20.126842',
            '2007-09-28T16:09:x0.126842',
            '2007-09-28T16:09:20.x26842')
        for invalid_datetime in no_digits:
            self.assertDateErrorIsDetected(invalid_datetime)

        # The "separator symbol" between year, month, day must be a '-'
        self.assertDateErrorIsDetected('2007 09-28T16:09:20.126842')
        self.assertDateErrorIsDetected('2007-09 28T16:09:20.126842')

        # The "separator symbol" between hour, minute, second must be a ':'
        self.assertDateErrorIsDetected('2007-09-28T16 09:20.126842')
        self.assertDateErrorIsDetected('2007-09-28T16:09 20.126842')

        # The fractional part may be shorter than 6 digits...
        self.assertValidDateTime('2007-09-28T16:09:20.1',
                                 datetime(2007, 9, 28, 16, 9, 20, 100000))

        # ...or it may be omitted...
        self.assertValidDateTime('2007-09-28T16:09:20',
                                 datetime(2007, 9, 28, 16, 9, 20))

        # ...but it may not have more than 6 digits.
        self.assertDateErrorIsDetected('2007-09-28T16:09 20.1234567')

        # A timezone may be specified. 'Z' means UTC
        self.assertValidDateTime('2007-09-28T16:09:20.123456Z',
                                 datetime(2007, 9, 28, 16, 9, 20, 123456))
        self.assertValidDateTime('2007-09-28T16:09:20.123456+02:00',
                                 datetime(2007, 9, 28, 14, 9, 20, 123456))
        self.assertValidDateTime('2007-09-28T16:09:20.123456-01:00',
                                 datetime(2007, 9, 28, 17, 9, 20, 123456))

        # Other values than 'Z', '+hh:mm' or '-hh:mm' in the timezone part
        # are detected as errors.
        self.assertDateErrorIsDetected('2007-09-28T16:09:20.1234567x')
        self.assertDateErrorIsDetected('2007-09-28T16:09:20.1234567+01')
        self.assertDateErrorIsDetected('2007-09-28T16:09:20.1234567+01:')
        self.assertDateErrorIsDetected('2007-09-28T16:09:20.1234567+01:2')
        self.assertDateErrorIsDetected('2007-09-28T16:09:20.1234567+0:30')

        # The values for month, day, hour, minute, timzone must be in their
        # respective valid range.
        wrong_range = (
            '2007-00-28T16:09:20.126842',
            '2007-13-28T16:09:20.126842',
            '2007-09-00T16:09:20.126842',
            '2007-02-29T16:09:20.126842',
            '2007-09-28T24:09:20.126842',
            '2007-09-28T16:60:20.126842',
            '2007-09-28T16:09:60',
            '2007-09-28T16:09:20.126842+24:00',
            '2007-09-28T16:09:20.126842-24:00')
        for invalid_datetime in wrong_range:
            self.assertDateErrorIsDetected(invalid_datetime)

        # Leap seconds (a second appended to a day) pass the Relax NG
        # validation properly...
        sample_data = self.sample_data.replace(
            '<date_created value="2007-09-28T16:09:20.126842"/>',
            '<date_created value="2007-09-28T23:59:60.999"/>')
        result, submission_id = self.runValidator(sample_data)

        # ...but the datetime function rejects them.
        self.assertRaises(ValueError, datetime, 2007, 12, 31, 23, 59, 60, 999)

        # Two leap seconds are rejected by the Relax NG validator.
        self.assertDateErrorIsDetected('2007-09-28T23:59:61')

    def assertDateErrorIsDetected(self, invalid_datetime):
        """Run a single test for an invalid datetime."""
        sample_data = self.sample_data.replace(
            '<date_created value="2007-09-28T16:09:20.126842"/>',
            '<date_created value="%s"/>' % invalid_datetime)
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            "Type dateTime doesn't allow value '%s'" % invalid_datetime,
            'invalid datetime %s' % invalid_datetime)

    def assertValidDateTime(self, datetime_as_string, datetime_expected):
        """Run a single test for a valid datetime."""
        sample_data = self.sample_data.replace(
            '<date_created value="2007-09-28T16:09:20.126842"/>',
            '<date_created value="%s"/>' % datetime_as_string)
        result, submission_id = self.runValidator(sample_data)
        self.assertNotEqual(result, None,
                            'valid datetime %s rejected' % datetime_as_string)

    def testClientTagAttributes(self):
        """Validation of <client> tag attributes.

        The <client> tag requires the attributes 'name' and 'version';
        other attributes are not allowed.
        """
        # The omission of either of the required attributes is detected by
        # the Relax NG validation
        for only_attribute in ('name', 'version'):
            sample_data = self.sample_data.replace(
                '<client name="hwtest" version="0.9">',
                '<client %s="some_value">' % only_attribute)
            result, submission_id = self.runValidator(sample_data)
            self.assertErrorMessage(
                submission_id, result,
                'Element client failed to validate attributes',
                'missing required attribute in <client>')

        # Other attributes are rejected by the Relax NG validation.
        sample_data = self.sample_data.replace(
            '<client name="hwtest" version="0.9">',
            '<client name="hwtest" version="0.9" foo="bar">')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Invalid attribute foo for element client',
            'testing invalid attribute in <client>')

    def testSubTagsOfClient(self):
        """The only allowed sub-tag of <client> is <plugin>."""
        sample_data = self.sample_data.replace(
            '<client name="hwtest" version="0.9">',
            '<client name="hwtest" version="0.9"><nonsense/>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Element client has extra content: nonsense',
            'invalid sub-tag of <client>')

    def testClientPluginAttributes(self):
        """Validation of <plugin> tag attributes.

        The <plugin> tag requires the attributes 'name' and 'version';
        other attributes are not allowed.
        """
        # The omission of either of the required attributes is detected by
        # by the Relax NG validation
        for only_attribute in ('name', 'version'):
            tag = '<plugin %s="some_value"/>' % only_attribute
            sample_data = self.sample_data.replace(
                '<plugin name="architecture_info" version="1.1"/>', tag)
            result, submission_id = self.runValidator(sample_data)
            self.assertErrorMessage(
                submission_id, result,
                'Element plugin failed to validate attributes',
                'missing client plugin attributes: %s' % tag)

        # Other attributes are rejected by the Relax NG validation.
        sample_data = self.sample_data.replace(
            '<plugin name="architecture_info" version="1.1"/>',
            '<plugin name="architecture_info" version="1.1" foo="bar"/>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Invalid attribute foo for element plugin',
            'invalid attribute in client plugin')

    def testHardwareSubTagHalOrUdev(self):
        """The <hardware> tag requires data about hardware devices.

        This data is stored either in the sub-tag <hal> or in the
        three tags <udev>, <dmi>, <sysfs-attributes>.
        """
        # Omitting <hal> leads to an error.
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='',
            from_text='<hal',
            to_text='</hal>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Expecting an element hal, got nothing',
            'missing tag <hal> in <hardware>')

        # But we may replace <hal> by the three tags <udev>, <dmi>,
        #<sysfs-attributes>.
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text="""
               <udev>some text</udev>
               <dmi>some text</dmi>
               <sysfs-attributes>some text</sysfs-attributes>
            """,
            from_text='<hal',
            to_text='</hal>')
        result, submission_id = self.runValidator(sample_data)
        self.assertNotEqual(
            result, None,
            'submission with valid <udev>, <dmi>, <sysfs-attributes> tags '
            'rejected')

    def testHardwareSubTagUdevIncomplete(self):
        """The <hardware> tag has a fixed set of allowed sub-tags.

        Valid sub-tags are <hal>, <udev>, <dmi>, <sysfs-attributes>,
        <processors>, <aliases>. <aliases> is optional, <processors>
        is required, and either <hal> or all three tags <udev>, <dmi>,
        <sysfs-attributes> must be present.
        """
        # Omitting one of the tags <udev>, <dmi> makes the data invalid.
        # Omitting <sysfs-attributes> is tolerated.
        all_tags = ['udev', 'dmi', 'sysfs-attributes']
        for index, missing_tag in enumerate(all_tags):
            test_tags = all_tags[:]
            del test_tags[index]
            replace_text = [
                '<%s>text</%s>' % (tag, tag) for tag in test_tags]
            replace_text = ''.join(replace_text)
            sample_data = self.replaceSampledata(
                data=self.sample_data,
                replace_text=replace_text,
                from_text='<hal',
                to_text='</hal>')
            result, submission_id = self.runValidator(sample_data)
            if missing_tag != 'sysfs-attributes':
                self.assertErrorMessage(
                    submission_id, result,
                    'Expecting an element %s, got nothing' % missing_tag,
                    'missing tag <%s> in <hardware>' % missing_tag)
            else:
                self.assertFalse(result is None)

    def testHardwareSubTagHalMixedWithUdev(self):
        """Mixing <hal> with <udev>, <dmi>, <sysfs-attributes> is impossible.
        """
        # A submission containing the tag <hal> as well as one of <udev>,
        # <dmi>, <sysfs-attributes> is invalid.
        for tag in ['udev', 'dmi', 'sysfs-attributes']:
            sample_data = self.insertSampledata(
                data=self.sample_data,
                insert_text='<%s>some text</%s>' % (tag, tag),
                where='<hal')
            result, submission_id = self.runValidator(sample_data)
            self.assertErrorMessage(
                submission_id, result,
                'Invalid sequence in interleave',
                '<hal> mixed with <%s> in <hardware>' % tag)

    def testHardwareOtherSubTags(self):
        """The <hardware> tag has a fixed set of allowed sub-tags.
        """
        # The <processors> tag must not be omitted.
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='',
            from_text='<processors',
            to_text='</processors>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Expecting an element processors, got nothing',
            '<processor> tag omitted')

        # The <aliases> tag may be omitted.
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='',
            from_text='<aliases',
            to_text='</aliases>')
        result, submission_id = self.runValidator(sample_data)
        self.assertNotEqual(result, None,
                            'submission without <aliases> rejected')

        # Other subtags are not allowed in <hardware>.
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text='<nonsense/>',
            where='</hardware>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Element hardware has extra content: nonsense',
            'invalid subtag of <hardware>')

    def testHalAttributes(self):
        """Validation of <hal> tag attributes.

        The <hal> tag must have the 'version' attribute; other attributes are
        not allowed.
        """
        sample_data = self.sample_data.replace(
            '<hal version="0.5.8.1">', '<hal>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Element hal failed to validate attributes',
            'missing version attribute of <hal>')

        sample_data = self.sample_data.replace(
            '<hal version="0.5.8.1">',
            '<hal version="0.5.8.1" foo="bar">')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Invalid attribute foo for element hal',
            'invalid attribute in <hal>')

    def testHalSubtags(self):
        """Validation of sub-tags of <hal>.

        <hal> must contain at least one <device> sub-tag. All other sub-tags
        are invalid.
        """
        # If the two <device> sub-tag of the sample data are removed, the
        # submission becomes invalid.
        sample_data = self.sample_data
        for count in range(2):
            sample_data = self.replaceSampledata(
                data=sample_data,
                replace_text='',
                from_text='<device',
                to_text='</device>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Expecting an element device, got nothing',
            'missing <device> sub-tag in <hal>')

        # Any other tag than <device> within <hal> is not allowed.
        sample_data = self.sample_data
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text='<nonsense/>',
            where='</hal>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Expecting element device, got nonsense',
            'invalid sub-tag in <hal>')

    def testDeviceAttributes(self):
        """Validation of the attributes of the <device> tag.

        <device> must have the attributes 'id' and 'udi'; the attribute
        'parent' is optional. The latter is already shown by

            <device id="130" udi="/org/freedesktop/Hal/devices/computer">

        in the standard sample data.

        The values of 'id' and 'parent' must be integers. "id" must not
        be emtpy.
        """
        for only_attribute in ('id', 'udi'):
            sample_data = self.replaceSampledata(
                data=self.sample_data,
                replace_text='<device %s="2">' % only_attribute,
                from_text='<device',
                to_text='>')
            result, submission_id = self.runValidator(sample_data)
            self.assertErrorMessage(
                submission_id, result,
                'Element device failed to validate attributes',
                'missing attribute in <device>')

        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='<device id="NoInteger" udi="foo">',
            from_text='<device',
            to_text='>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            "Type integer doesn't allow value 'NoInteger'",
            "invalid content of the 'id' attribute of <device>")

        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='<device id="" udi="foo">',
            from_text='<device',
            to_text='>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            "Invalid attribute id for element device",
            "empty 'id' attribute of <device>")

        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='<device id="1" parent="NoInteger" udi="foo">',
            from_text='<device',
            to_text='>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Invalid attribute parent for element device',
            "invalid content of the 'parent' attribute of <device>")

    def testDeviceContent(self):
        """<device> tags may only contain <property> tags."""
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text="<nonsense/>",
            where="</device>")
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Expecting element property, got nonsense',
            'invalid subtag of <device>')

    # Tests for the <property> and the <value> tag.
    #
    # Both tags are very similar: They have an attribute 'type'
    # and they have a "value", where "value" is, depending on the type
    # attribute, either represented by CDATA content or by a <value>
    # sub-tag.
    #
    # The main difference between the <value> and <property> tags is
    # their location: The <property> tag is a sub-tag of tags like <device>,
    # <processor> or <software>, while <value> is a sub-tag of <property>,
    # when the <property> has one of the types 'list', 'dbus.Array', 'dict',
    # or 'dbus.Dictionary'.
    #
    # If <value> is a sub-tag of a list-like <property> or <value>, it
    # has a 'type' attribute and a value as described above; if <value>
    # is a sub-tag of a dict-like <property> or <value>, it has a 'type'
    # and a 'name' attribute and a value as described above.
    #
    # Allowed types are: 'dbus.Boolean', 'bool', 'dbus.String',
    # 'dbus.UTF8String', 'str', 'dbus.Byte', 'dbus.Int16', 'dbus.Int32',
    # 'dbus.Int64', 'dbus.UInt16', 'dbus.UInt32', 'dbus.UInt64', 'int',
    # 'long', 'dbus.Double', 'float', 'dbus.Array', 'list',
    # 'dbus.Dictionary', 'dict'.

    def _testPropertyMissingNameAttribute(self, property):
        """The name attribute is required for all property variants."""
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text=property,
            where='</device>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Element device has extra content: property',
            'testing missing name attribute in %s' % property)

    def _testBooleanProperty(self, content_type):
        """Validation of a boolean type property or value."""
        for value in ('True', 'False'):
            tag = ('<property name="foo" type="%s">%s</property>'
                   % (content_type, value))
            sample_data = self.insertSampledata(
                data=self.sample_data,
                insert_text=tag,
                where='</device>')
            result, submission_id = self.runValidator(sample_data)
            self.assertNotEqual(
                result, None, 'Valid boolean property tag %s rejected' % tag)

        # Other content than 'True' and 'False' is rejected by the Relax NG
        # validation.
        tag = '<property name="foo" type="%s">0</property>' % content_type
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text=tag,
            where='</device>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Element property failed to validate content',
            'invalid boolean property: %s' % tag)

        tag = '<property type="%s">False</property>' % content_type
        self._testPropertyMissingNameAttribute(tag)

        # Sub-tags are not allowed.
        tag = '<property name="foo" type="%s">False<nonsense/></property>'
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text=tag,
            where='</device>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Element property failed to validate content',
            'sub-tag in boolean property: %s' % tag)

    def testBooleanProperties(self):
        for content_type in ('dbus.Boolean', 'bool'):
            self._testBooleanProperty(content_type)

    def _testStringProperty(self, property_type):
        """Validation of a string property."""
        self._testPropertyMissingNameAttribute(
            '<property type="%s">blah</property>' % property_type)

        # Sub-tags are not allowed.
        tag = '<property name="foo" type="%s">False<nonsense/></property>'
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text=tag,
            where='</device>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Element property failed to validate content',
            'sub-tags of string-like <property type="%s">' % property_type)

    def testStringProperties(self):
        """Validation of string properties."""
        for property_type in ('dbus.String', 'dbus.UTF8String', 'str'):
            self._testStringProperty(property_type)

    def _testEmptyIntegerContent(self, property_type, relax_ng_type):
        """Detection of an empty property with integer content."""
        tag = '<property name="foo" type="%s"/>' % property_type
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text=tag,
            where='</device>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Error validating datatype %s' % relax_ng_type,
            'empty content of <property type="%s">' % relax_ng_type)

    def _testInvalidIntegerContent(self,  property_type, relax_ng_type):
        """Detection of invalid content of a property with integer content."""
        tag = '<property name="foo" type="%s">X</property>' % property_type
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text=tag,
            where='</device>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            "Type %s doesn't allow value 'X'" % relax_ng_type,
            'invalid content of <property type="%s">' % relax_ng_type)

    def _testMinMaxIntegerValue(self, property_type, relax_ng_type,
                                valid_value, invalid_value):
        """Detection of integer values outside of the allowed range."""
        tag_template = '<property name="foo" type="%s">%i</property>'
        tag = tag_template % (property_type, valid_value)
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text=tag,
            where='</device>')
        result, submission_id = self.runValidator(sample_data)
        self.assertNotEqual(result, None,
                            'Valid integer value in %s rejected' % tag)

        tag = tag_template % (property_type, invalid_value)
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text=tag,
            where='</device>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
                "Type %s doesn't allow value '%i'"
                % (relax_ng_type, invalid_value),
            'min or max values of <property type="%s"> (%s, %s)'
                % (relax_ng_type, valid_value, invalid_value))

    def _testIntegerProperty(self, property_type, relax_ng_type, min_value,
                             max_value):
        """Validation of an integer property."""
        self._testPropertyMissingNameAttribute(
            '<property type="%s">1</property>' % property_type)

        # Empty content is detected as invalid.
        self._testEmptyIntegerContent(property_type, relax_ng_type)

        # Non-digit content is detected as invalid.
        self._testInvalidIntegerContent(property_type, relax_ng_type)

        # A value smaller than the minimum allowed value is detected as
        # invalid.
        if min_value is not None:
            self._testMinMaxIntegerValue(
                property_type, relax_ng_type, min_value, min_value - 1)

        # A value larger than the maximum allowed value is detected as
        # invalid.
        if max_value is not None:
            self._testMinMaxIntegerValue(
                property_type, relax_ng_type, max_value, max_value + 1)

    def testIntegerProperties(self):
        """Validation of integer properties."""
        type_info = (('dbus.Byte', 'unsignedByte', 0, 255),
                     ('dbus.Int16', 'short', -2 ** 15, 2 ** 15 - 1),
                     ('dbus.Int32', 'int', -2 ** 31, 2 ** 31 - 1),
                     ('dbus.Int64', 'long', -2 ** 63, 2 ** 63 - 1),
                     ('dbus.UInt16', 'unsignedShort', 0, 2 ** 16 - 1),
                     ('dbus.UInt32', 'unsignedInt', 0, 2 ** 32 - 1),
                     ('dbus.UInt64', 'unsignedLong', 0, 2 ** 64 - 1),
                     ('long', 'integer', None, None),
                     ('int', 'long', -2 ** 63, 2 ** 63 - 1))
        for property_type, relax_ng_type, min_value, max_value in type_info:
            self._testIntegerProperty(
                property_type, relax_ng_type, min_value, max_value)

    def _testEmptyDecimalContent(self, property_type):
        """Detection of an empty property with number content."""
        tag = '<property name="foo" type="%s"/>' % property_type
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text=tag,
            where='</device>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            "Type decimal doesn't allow value ''",
            'empty decimal type property %s' % property_type)

    def _testInvalidDecimalContent(self,  property_type):
        """Detection of invalid content of a property with number content."""
        tag = '<property name="foo" type="%s">X</property>' % property_type
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text=tag,
            where='</device>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            "Type decimal doesn't allow value 'X'",
            'invalid content in decimal type prperty %s' % property_type)

    def _testDecimalProperty(self, property_type):
        """Validation of an integer property."""
        self._testPropertyMissingNameAttribute(
            '<property type="%s">1</property>' % property_type)

        # Empty content is detected as invalid.
        self._testEmptyDecimalContent(property_type)

        # Non-digit content is detected as invalid.
        self._testInvalidDecimalContent(property_type)

    def testDecimalProperties(self):
        """Validation of dbus.Double and float properties."""
        for property_type in ('dbus.Double', 'float'):
            self._testDecimalProperty(property_type)

    def _testListAndDictPropertyCDataContent(self, property_type):
        """List and dict properties may not have CDATA content."""
        tag = '<property name="foo" type="%s">X</property>' % property_type
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text=tag,
            where='</device>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Element property has extra content: text',
            'testing CDATA content of <property type="%s">' % property_type)

    def assertAcceptsEmptyProperty(self, property_type):
        """Validation of empty list properties."""
        tag = '<property name="foo" type="%s"></property>' % property_type
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text=tag,
            where='</device>')
        result, submission_id = self.runValidator(sample_data)
        self.assertNotEqual(
            result, None,
            'Valid submission with empty <property type="%s"> rejected'
                % property_type)

    def assertRejectsNonValueSubtag(self, property_type):
        """Other sub-tags than <value> are not allowed in lists and dicts."""
        tag = '<property name="foo" type="%s"><nonsense/></property>'
        tag = tag % property_type
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text=tag,
            where='</device>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Expecting element value, got nonsense',
            'invalid subtag of <property type="%s">' % property_type)

    def _wrapValue(self, value_tag, property_type):
        """Wrap a <value> tag into a <property> tag."""
        return ('<property name="bar" type="%s">%s</property>'
                % (property_type, value_tag))

    def _testBooleanValueTagValues(self, property_type, tag_template):
        """Validation of the CDATA values of a <value> tag."""
        # The only allowed values are True and False.
        for cdata_value in ('True', 'False'):
            tag = tag_template % cdata_value
            tag = self._wrapValue(tag, property_type)
            sample_data = self.insertSampledata(
                data=self.sample_data,
                insert_text=tag,
                where='</device>')
            result, submission_id = self.runValidator(sample_data)
            self.assertNotEqual(result, None)
        # Any other text in the <value> tag is invalid.
        tag = tag_template % 'nonsense'
        tag = self._wrapValue(tag, property_type)
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text=tag,
            where='</device>')
        result, submission_id = self.runValidator(sample_data)
        self.assertEqual(result, None)
        self.assertErrorMessage(
            submission_id,
            'Error validating value ')
        # An empty <value> tag is invalid.
        tag = tag_template % ''
        tag = self._wrapValue(tag, property_type)
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text=tag,
            where='</device>')
        result, submission_id = self.runValidator(sample_data)
        self.assertEqual(result, None)
        self.assertErrorMessage(
            submission_id,
            'ERROR:RELAXNGV:ERR_UNSUPPORTED_ENCODING: '
                'Error validating value ')

    def _setupValueTagTemplates(self, value_type):
        """Return templates for value tags with/without a name attribute."""
        tag_with_name = '<value name="foo" type="%s">%%s</value>' % value_type
        tag_without_name = '<value type="%s">%%s</value>' % value_type
        return tag_with_name, tag_without_name

    def assertValidatesTextValue(self, value_type, needs_name_attribute,
                               valid_content, invalid_content,
                               property_template):
        """Validation of tags with CData values"""
        tag_with_name, tag_without_name = self._setupValueTagTemplates(
            value_type)
        if needs_name_attribute:
            tag = tag_without_name % valid_content[0]
            tag = property_template % tag
            sample_data = self.insertSampledata(
                data=self.sample_data,
                insert_text=tag,
                where='</device>')
            result, submission_id = self.runValidator(sample_data)
            self.assertErrorMessage(
                submission_id, result,
                'Element device has extra content: property',
                'missing name attribute in value tag %s' % tag)
        else:
            tag = tag_with_name % valid_content[0]
            tag = property_template % tag
            sample_data = self.insertSampledata(
                data=self.sample_data,
                insert_text=tag,
                where='</device>')
            result, submission_id = self.runValidator(sample_data)
            self.assertErrorMessage(
                submission_id, result,
                'Element device has extra content: property',
                'invalid name attribute in value tag %s' % tag)

        if needs_name_attribute:
            template = tag_with_name
        else:
            template = tag_without_name
        template = property_template % template
        for value in valid_content:
            tag = template % value
            sample_data = self.insertSampledata(
                data=self.sample_data,
                insert_text=tag,
                where='</device>')
            result, submission_id = self.runValidator(sample_data)
            self.assertNotEqual(
                result, None,
                'Valid submission with tag %s rejected' % tag)
        for value, expected_error in invalid_content:
            tag = template % value
            sample_data = self.insertSampledata(
                data=self.sample_data,
                insert_text=tag,
                where='</device>')
            result, submission_id = self.runValidator(sample_data)
            self.assertErrorMessage(
                submission_id, result, expected_error,
                'invalid content of value tag %s' % tag)

    def _setupContainerTag(self, tag, name, container_type):
        """Setup a template for a property or value tag with sub-tags.

        tag must be either 'property' or 'value'

        name is the value of the name attribute of the template, or
        None, if the template shall not have the attribute name.

        container_type must be one of 'list', 'dbus.List', 'dict',
        'dbus.Dictionary'.

        Return: A tag template for this property/value type and a flag,
        if value tags within this tag need a name attribute.
        """
        if name is not None:
            container_template = (
                '<%s name="%s" type="%s">' % (tag, name, container_type))
        else:
            container_template = '<%s type="%s">' % (tag, container_type)
        container_template = container_template + '%s' + '</%s>' % tag
        if container_type in ('dbus.Dictionary', 'dict'):
            needs_name_attribute = True
        elif container_type in ('dbus.Array', 'list'):
            needs_name_attribute = False
        else:
            raise AssertionError(
                '_setupPropertyTag called for invalid property type:'
                % container_type)
        return container_template, needs_name_attribute

    def _testBooleanValueTags(self, property_type):
        """Validation of boolean-like <value> tags."""
        property_template, needs_name_attribute = (
            self._setupContainerTag('property', 'foor', property_type))
        valid_content = ('True', 'False')
        invalid_content = (
            ('nonsense', 'Element property has extra content: value'),
            ('', 'Element property has extra content: value'),
            ('<nonsense/>', 'Value element value has child elements'))
        for value_type in ('dbus.Boolean', 'bool'):
            self.assertValidatesTextValue(value_type, needs_name_attribute,
                                          valid_content, invalid_content,
                                          property_template)

    def _testStringValueTags(self, property_type):
        """Validation of string-like <value> tags."""
        property_template, needs_name_attribute = (
            self._setupContainerTag('property', 'foo', property_type))
        valid_content = ('any text', '')
        invalid_content = (
            ('<nonsense/>', 'Element value has extra content: nonsense'),)
        for value_type in ('dbus.String', 'str'):
            self.assertValidatesTextValue(value_type, needs_name_attribute,
                                          valid_content, invalid_content,
                                          property_template)

    def _makeSampleDataForValueTag(self, property_type, value_type, value):
        property_template, needs_name_attribute = (
            self._setupContainerTag('property', 'foo', property_type))
        value_template_with_name, value_template_without_name = (
            self._setupValueTagTemplates(value_type))
        if needs_name_attribute:
            value_tag = value_template_with_name % value
        else:
            value_tag = value_template_without_name % value
        property_tag = property_template % value_tag
        return self.insertSampledata(
            data=self.sample_data,
            insert_text=property_tag,
            where='</device>')

    def _testIntegerLimit(self, property_type, value_type, relax_ng_type,
                          allowed, disallowed):
        """Validation of the smallest or largest value of an int type."""
        sample_data = self._makeSampleDataForValueTag(
            property_type, value_type, allowed)
        result, submission_id = self.runValidator(sample_data)
        self.assertNotEqual(
            result, None,
            'Testing integer limits: Valid submission for property type %s '
                'value type %s, value %s rejected'
                % (property_type, value_type, allowed))

        sample_data = self._makeSampleDataForValueTag(
            property_type, value_type, disallowed)
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            "Type %s doesn't allow value '%s'" % (relax_ng_type, disallowed),
            'invalid value %s of value type %s in property type %s'
                % (disallowed, value_type, property_type))

    def _testIntegerValueTag(self, property_type, value_type, relax_ng_type,
                             min_allowed, max_allowed):
        """Valudation of a <value> tag wwith integral content."""
        property_template, needs_name_attribute = (
            self._setupContainerTag('property', 'foo', property_type))
        valid_content = ('0', '1')
        invalid_content = (
            (
                '', (
                    # libxml2 version 1.6.31 (Hardy) message:
                    'Error validating datatype %s' % relax_ng_type,
                    # libxml2 version 2.6.32 (Intrepid) message:
                    "Type %s doesn't allow value ''" % relax_ng_type,
                    )
                ),
            (
                '1.1', "Type %s doesn't allow value '1.1'" % relax_ng_type
                ),
            (
                'nonsense',
                "Type %s doesn't allow value 'nonsense'" % relax_ng_type
                ),
            (
                '<nonsense/>',
                'Datatype element value has child elements'
                )
            )
        self.assertValidatesTextValue(value_type, needs_name_attribute,
                                      valid_content, invalid_content,
                                      property_template)
        if min_allowed is not None:
            self._testIntegerLimit(property_type, value_type, relax_ng_type,
                                   min_allowed, min_allowed - 1)
        if max_allowed is not None:
            self._testIntegerLimit(property_type, value_type, relax_ng_type,
                                   max_allowed, max_allowed + 1)

    def _testIntegerValueTags(self, property_type):
        """Validation of <value> tags with integral content."""
        int_types = (
            ('dbus.Byte', 'unsignedByte', 0, 255),
            ('dbus.Int16', 'short', -32768, 32767),
            ('dbus.Int32', 'int', -2 ** 31, 2 ** 31 - 1),
            ('dbus.Int64', 'long', -2 ** 63, 2 ** 63 - 1),
            ('dbus.UInt16', 'unsignedShort', 0, 2 ** 16 - 1),
            ('dbus.UInt32', 'unsignedInt', 0, 2 ** 32 - 1),
            ('dbus.UInt64', 'unsignedLong', 0, 2 ** 64 - 1),
            ('int', 'long', -2 ** 63, 2 ** 63 - 1),
            ('long', 'integer', None, None))
        for value_type, relax_ng_type, min_allowed, max_allowed in int_types:
            self._testIntegerValueTag(property_type, value_type,
                                      relax_ng_type, min_allowed, max_allowed)

    def _testFloatValueTag(self, property_type, value_type):
        """Validation of a <value> tag with float-number content."""
        property_template, needs_name_attribute = (
            self._setupContainerTag('property', 'foo', property_type))
        valid_content = ('0', '1', '1.1', '-2.34')
        invalid_content = (('', "Type decimal doesn't allow value ''"),
                           ('nonsense', "Type decimal doesn't allow "
                                            "value 'nonsense'"),
                           ('<nonsense/>',
                            'Datatype element value has child elements'))
        self.assertValidatesTextValue(value_type, needs_name_attribute,
                                      valid_content, invalid_content,
                                      property_template)

    def _testFloatValueTags(self, property_type):
        """Validation of <value> tags with float-number content."""
        float_types = ('dbus.Double', 'float')
        for value_type in float_types:
            self._testFloatValueTag(property_type, value_type)

    def _testListOrDictValueTag(self, property_type, value_type):
        """Validation of a list or dict-like value tag."""
        property_template, needs_name_attribute = self._setupContainerTag(
            'property', 'foo', property_type)
        if needs_name_attribute:
            value_template, needs_name_attribute = self._setupContainerTag(
                'value', 'bar', value_type)
        else:
            value_template, needs_name_attribute = self._setupContainerTag(
                'value', None, value_type)
        template = property_template % value_template

        # CDATA content is not allowed.
        tag = template % 'nonsense'
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text=tag,
            where='</device>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Element value has extra content: text',
            'CDATA in <value type="%s">' % value_type)

        # Lists and dicts may be empty.
        tag = template % ''
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text=tag,
            where='</device>')
        result, submission_id = self.runValidator(sample_data)
        self.assertNotEqual(
            result, None, 'empty tag <value type="%s">' % value_type)

        # Other sub-tags than <value> are invalid.
        tag = template % '<nonsense/>'
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text=tag,
            where='</device>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Element value has extra content: nonsense',
            'CDATA in <value type="%s">' % value_type)

        if needs_name_attribute:
            # Dict-like <value> tags need nested <value> tags with the
            # attribute name.
            tag = template % '<value type="int" name="baz">1</value>'
            sample_data = self.insertSampledata(
                data=self.sample_data,
                insert_text=tag,
                where='</device>')
            result, submission_id = self.runValidator(sample_data)
            self.assertNotEqual(
                result, None,
                'valid <value> tag inside <value type="%s">' % value_type)

            tag = template % '<value type="int">1</value>'
            sample_data = self.insertSampledata(
                data=self.sample_data,
                insert_text=tag,
                where='</device>')
            result, submission_id = self.runValidator(sample_data)
            self.assertErrorMessage(
                submission_id, result,
                'Element value has extra content: value',
                'invalid <value> tag inside <value type="%s">' % value_type)
        else:
            # List-like <value> tags need nested <value> tags without the
            # attribute name.
            tag = template % '<value type="int">1</value>'
            sample_data = self.insertSampledata(
                data=self.sample_data,
                insert_text=tag,
                where='</device>')
            result, submission_id = self.runValidator(sample_data)
            self.assertNotEqual(
                result, None,
                'valid <value> tag inside <value type="%s">' % value_type)

            tag = template % '<value type="int" nam="baz">1</value>'
            sample_data = self.insertSampledata(
                data=self.sample_data,
                insert_text=tag,
                where='</device>')
            result, submission_id = self.runValidator(sample_data)
            self.assertErrorMessage(
                submission_id, result,
                'Element value has extra content: value',
                'invalid <value> tag inside <value type="%s">' % value_type)

    def _testListAndDictValueTags(self, property_type):
        """Validation of list and dict-like values."""
        for value_type in ('list', 'dbus.Array', 'dict', 'dbus.Dictionary'):
            self._testListOrDictValueTag(property_type, value_type)

    def _testValueTags(self, property_type):
        """Tests of <value> sub-tags of <property type="property_type">."""
        self._testBooleanValueTags(property_type)
        self._testStringValueTags(property_type)
        self._testIntegerValueTags(property_type)
        self._testFloatValueTags(property_type)
        self._testListAndDictValueTags(property_type)

    def _testListOrDictProperty(self, property_type):
        """Validation of a list property."""
        self._testListAndDictPropertyCDataContent(property_type)
        self.assertAcceptsEmptyProperty(property_type)
        self.assertRejectsNonValueSubtag(property_type)
        self._testValueTags(property_type)

    def testListAndDictProperties(self):
        """Validation of dbus.Array and list properties."""
        for property_type in ('dbus.Array', 'list', 'dbus.Dictionary',
                              'dict'):
            self._testListOrDictProperty(property_type)

    def testProcessorsTag(self):
        """Validation of the <processors> tag.

        This tag has no attributes. The only allowed sub-tag is <processor>.
        At least one <processor> tag must be present.
        """
        sample_data = self.sample_data.replace(
            '<processors>', '<processors foo="bar">')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Invalid attribute foo for element processors',
            'invalid attribute of <processors>')

        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text='<nonsense/>',
            where='</processors>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Expecting element processor, got nonsense',
            'invalid sub-tag of <processors>')

        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='',
            from_text='<processor id',
            to_text='</processor>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Expecting an element processor, got nothing',
            'missing sub-tags of <processors>')

    def testProcessorTag(self):
        """Validation of the <processors> tag."""
        # The attributes "id" and "name" are required.
        sample_data = self.sample_data.replace(
            '<processor id="123" name="0">', '<processor id="123">')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Element processor failed to validate attributes',
            'missing attribute "name" of <processor>')

        sample_data = self.sample_data.replace(
            '<processor id="123" name="0">', '<processor name="0">')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Element processor failed to validate attributes',
            'missing attribute "id" attribute of <processor>')

        # "id" must not be empty.
        sample_data = self.sample_data.replace(
            '<processor id="123" name="0">', '<processor id="" name="0">')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Invalid attribute id for element processor',
            'empty attribute "id" of <processor>')

        # "id" must have integer content.
        sample_data = self.sample_data.replace(
            '<processor id="123" name="0">',
            '<processor id="noInteger" name="0">')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Invalid attribute id for element processor',
            'invalid content of attribute "name" of <processor>')

        # other attributes are invalid.
        sample_data = self.sample_data.replace(
            '<processor id="123" name="0">',
            '<processor id="123" name="0" foo="bar">')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Invalid attribute foo for element processor',
            'invalid attribute of <processor>')

        # Other sub-tags than <property> are invalid.
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text='<nonsense/>',
            where='</processor>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Expecting element property, got nonsense',
            'invalid sub-tag of <processor>')

        # At least one <property> tag must be present
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='<processor id="123" name="0"/>',
            from_text='<processor id="123" name="0">',
            to_text='</processor>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Expecting an element property, got nothing',
            'missing sub-tags of <processor>')

    def testAliasesTag(self):
        """Validation of the <aliases> tag."""
        # The <aliases> tag has no attributes.
        sample_data = self.sample_data.replace(
            '<aliases>', '<aliases foo="bar">')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Extra element aliases in interleave',
            'invalid attribute of <aliases>')

        # The <aliases> tag may be omittied.
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='',
            from_text='<aliases>',
            to_text='</aliases>')
        result, submission_id = self.runValidator(sample_data)
        self.assertNotEqual(result, None, 'omitted tag <aliases>')

        # The <aliases> may be empty.
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='<aliases/>',
            from_text='<aliases>',
            to_text='</aliases>')
        result, submission_id = self.runValidator(sample_data)
        self.assertNotEqual(result, None, 'empty tag <aliases>')

        # Other sub-tags than <alias> are invalid.
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text='<nonsense/>',
            where='</aliases>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Extra element aliases in interleave',
            'invalid sub-tag of <aliases>')

    def testAliasTagAttributes(self):
        """Validation of the <alias> tag."""
        # The attribute target is required.
        # Note that the expected error message from the validator
        # is identical to the last error message expected in
        # testAliasesTag: libxml2's Relax NG validator is sometimes
        # not as informative as one might wish.
        sample_data = self.sample_data.replace(
            '<alias target="65">', '<alias>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Extra element aliases in interleave',
            'missing attribute of <alias>')

        # Other attributes are not allowed. We get again the same
        # quite unspecific error message as above.
        sample_data = self.sample_data.replace(
            '<alias target="65">', '<alias target="65" foo="bar">')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Extra element aliases in interleave',
            'invalid attribute of <alias>')

    def testAliasTagContent(self):
        # The <alias> tag requires exactly two sub-tags: <vendor> and
        # <model>. Omitting either of them is forbidden. Again, we get
        # same error message from the validator.
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='',
            from_text='<vendor>',
            to_text='</vendor>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Extra element aliases in interleave',
            'missing sub-tag <vendor> of <alias>')
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='',
            from_text='<model>',
            to_text='</model>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Extra element aliases in interleave',
            'missing sub-tag <model> of <alias>')

        # Other sub-tags are not allowed.
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text='<nonsense/>',
            where='</alias>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Extra element aliases in interleave',
            'invalid sub-tag of <alias>')

        # CDATA content not allowed.
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text='nonsense',
            where='</alias>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Extra element aliases in interleave',
            'invalid sub-tag of <alias>')

    def testAliasVendorTag(self):
        """Validation of the <vendor> tag in <alias>."""
        # The tag may not have any attributes. As for the <alias> tag,
        # we don't get very specific error messages.
        sample_data = self.sample_data.replace(
            '<vendor>', '<vendor foo="bar">')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Extra element aliases in interleave',
            'invalid attribute of <vendor>')

        # <vendor> may not have any sub-tags.
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text='<nonsense/>',
            where='</vendor>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Extra element aliases in interleave',
            'invalid sub-tag of <alias>')

    def testAliasModelTag(self):
        """Validation of the <model> tag in <alias>."""
        # The tag may not have any attributes. As for the <alias> tag,
        # we don't get very specific error messages.
        sample_data = self.sample_data.replace(
            '<model>', '<model foo="bar">')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Extra element aliases in interleave',
            'invalid attribute of <model>')

        # <model> may not have any sub-tags.
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text='<nonsense/>',
            where='</model>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Extra element aliases in interleave',
            'invalid sub-tag of <alias>')

    def testSoftwareTagAttributes(self):
        """Test the attribute validation of the <software> tag."""
        # <software> has no attributes.
        sample_data = self.sample_data.replace(
            '<software>', '<software foo="bar">')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Invalid attribute foo for element software',
            'detection of invalid attribute of <software>')

    def testAllowedSubtagsOfSoftware(self):
        """Test the validation of allowed sub-tags of <software>."""
        # <software> has three allowed sub-tags: <lsbrelease>, <packages>
        # <xorg>.
        # <lsbrelease> is required.
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='',
            from_text='<lsbrelease',
            to_text='</lsbrelease>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Expecting an element lsbrelease, got nothing',
            'omission of required tag <lsbrelease> not detected')

        # <packages> is optional.
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='',
            from_text='<packages',
            to_text='</packages>')
        result, submission_id = self.runValidator(sample_data)
        self.assertNotEqual(
            result, None,
            'omission of optional tag <packages> treated as invalid')

        # <xorg> is optional.
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='',
            from_text='<xorg',
            to_text='</xorg>')
        result, submission_id = self.runValidator(sample_data)
        self.assertNotEqual(
            result, None,
            'omission of required tag <xorg> treated as invalid')

    def testInvalidContentOfSoftwareTag(self):
        """Test the validation of invalid content of <software>."""
        # Sub-tags other than <lsbrelease>, <packages>, <xorg> are
        # rejected.
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text='<nonsense/>',
            where='</software>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Element software has extra content: nonsense',
            'detection invalid sub-tag of <software>')

        # CDATA content is not allowed
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text='nonsense',
            where='</software>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Element software has extra content: text',
            'invalid CDATA content of <software>')

    def testLsbreleaseTagAttributes(self):
        """Test the validation of the <lsbrelease> attributes."""
        # <lsbrelease> has no attributes.
        sample_data = self.sample_data.replace(
            '<lsbrelease>', '<lsbrelease foo="bar">')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Invalid attribute foo for element lsbrelease',
            'detection of invalid attribute of <lsbrelease>')

    def testLsbreleaseTagValidSubtag(self):
        """Test the validation of <lsbrelease> sub-tags."""
        # <lsbrelease> requires at least one <property> sub-tag,
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='<lsbrelease/>',
            from_text='<lsbrelease>',
            to_text='</lsbrelease>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Expecting an element property, got nothing',
            'omission of required sub-tag <property> of <lsbrelease> '
                'not detected')

    def testLsbreleaseTagInvalidContent(self):
        """Test of the validation of invalid <lsbrelease> content."""
        # Sub-tags other than <property> are not allowed.
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text='<nonsense/>',
            where='</lsbrelease>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Expecting element property, got nonsense',
            'detection of invalid sub-tag of <lsbrelease>')

        # CDATA content is not allowed.
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text='nonsense',
            where='</lsbrelease>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Expecting an element got text',
            'detection of invalid CDATA content of <lsbrelease>')

    def testPackagesTagAttributes(self):
        """Test of the validation of <packages> tag attributes."""
        # This tag has no attributes.
        sample_data = self.sample_data.replace(
            '<packages>', '<packages foo="bar">')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Extra element packages in interleave',
            'detection of invalid attribute of <packages>')

    def testEmptyPackagesTag(self):
        """Test of the validation of <packages> tag attributes."""
        # <packages> may be empty.
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='',
            from_text='<package name=',
            to_text='</package>')
        result, submission_id = self.runValidator(sample_data)
        self.assertNotEqual(result, None,
                            'empty <packages> tag treated as invalid')

    def testPackagesTagWithInvalidContent(self):
        """Test the validation of <packages> tag attributes."""
        # Any sub-tag except <package> is invalid.
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text='<nonsense/>',
            where='</packages>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Extra element packages in interleave',
            'detection of invalid sub-tag of <packages>')

        # CDATA content is invalid.
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text='nonsense',
            where='</packages>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Extra element packages in interleave',
            'detection of invalid CDATA in <packages>')

    def testPackageTagAttributes(self):
        """Test the validation of <package> tag attributes."""
        # The attribute "name" is required.
        sample_data = self.sample_data.replace(
            '<package name="metacity" id="200">', '<package id="200">')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Extra element packages in interleave',
            'detection of missing required attribute name in <package>')

        # The attribute "id" is required.
        sample_data = self.sample_data.replace(
            '<package name="metacity" id="200">', '<package name="metacity">')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Extra element packages in interleave',
            'detection of missing required attribute id in <package>')

        # The attribute "id" must not be empty.
        sample_data = self.sample_data.replace(
            '<package name="metacity" id="200">',
            '<package name="metacity" id="">')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Extra element packages in interleave',
            'detection of empty required attribute id in <package>')

        # The attribute "id" must have integer content.
        sample_data = self.sample_data.replace(
            '<package name="metacity" id="200">',
            '<package name="metacity" id="noInteger">')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Extra element packages in interleave',
            'detection of non-integer content of attribute id in <package>')

        # Other attributes are not allowed.
        sample_data = self.sample_data.replace(
            '<package name="metacity" id="200">',
            '<package name="metacity" id="200" foo="bar">')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Extra element packages in interleave',
            'detection of invalid attributes in <package>')

    def testPackageTagSubtags(self):
        """Test the validation of sub-tags of <package>."""
        # Sub-tags other than <property> are not allowed.
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text='<nonsense/>',
            where='</package>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Extra element packages in interleave',
            'detection of invalid sub-tags of <package>')

        # At least one <property> tag is required
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='<package name="metacity" id="200"/>',
            from_text='<package name="metacity" id="200">',
            to_text='</package>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Extra element packages in interleave',
            'detection of invalid empty <package> tag')

    def testPackageTagCData(self):
        """Test the validation of CDATA content in <package>."""
        # CDATA content is not allowed.
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text='nonsense',
            where='</package>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Extra element packages in interleave',
            'detection of invalid CDATA in <package>')

    def testXorgTagAttributes(self):
        """Test the validation of <xorg> attributes."""
        # The <xorg> tag requires an attribute name.
        sample_data = self.sample_data.replace(
            '<xorg version="1.3.0">', '<xorg>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Extra element xorg in interleave',
            'detection of missing attribute version of <xorg>')

        # other attributes are invalid.
        sample_data = self.sample_data.replace(
            '<xorg version="1.3.0">', '<xorg version="1.3.0" foo="bar">')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Extra element xorg in interleave',
            'detection of invalid attribute of <xorg>')

    def testXorgTagSubTags(self):
        """Test the validation of <xorg> sub-tags."""
        # the only allowed sub-tag is <driver>.
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text='<nonsense/>',
            where='</xorg>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Extra element xorg in interleave',
            'detection of invalid sub-tag of <xorg>')

        # <xorg> may be empty
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='<xorg version="1.2.3"/>',
            from_text='<xorg',
            to_text='</xorg>')
        result, submission_id = self.runValidator(sample_data)
        self.assertNotEqual(result, None,
                            'invalid empty <xorg> tag not detected')

    def testXorgTagCData(self):
        """Test the validation of <xorg> CDATA content."""
        # CDATA content is not allowed.
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text='nonsense',
            where='</xorg>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Extra element xorg in interleave',
            'detection of invalid CDATA content of <xorg>')

    def _getXorgDriverTag(self, attributes):
        """Build a <driver> tag with attributes specified in "attributes." """
        attributes = attributes.items()
        attributes = [
            '%s="%s"' % attribute for attribute in attributes]
        attributes = ' '.join(attributes)
        return '<driver %s/>' % attributes

    def testXorgDriverTagRequiredAttributes(self):
        """Test the validation of attributes of <driver> within <xorg>.

        The attributes "name" and "class" are required.
        """
        all_attributes = {
            'name': 'fglrx',
            'version': '1.23',
            'class': 'X.Org Video Driver',
            'device': '12'}
        for omit in ('name', 'class'):
            # Remove a required attribute from the attribute dictionary
            # and build a <driver> tag with these attributes.
            test_attributes = all_attributes.copy()
            del test_attributes[omit]
            driver_tag = self._getXorgDriverTag(test_attributes)
            sample_data = self.replaceSampledata(
                data=self.sample_data,
                replace_text=driver_tag,
                from_text='<driver name="fglrx"',
                to_text='/>')
            result, submission_id = self.runValidator(sample_data)
            self.assertErrorMessage(
                submission_id, result,
                'Extra element xorg in interleave',
                'detection of missing required attribute %s of <driver> '
                    'in <xorg>' % omit)

    def testXorgDriverTagOptionalAttributes(self):
        """Test the validation of attributes of <driver> within <xorg>.

        The attributes "device" and "version" are optional.
        """
        all_attributes = {
            'name': 'fglrx',
            'version': '1.23',
            'class': 'X.Org Video Driver',
            'device': '12'}
        for omit in ('version', 'device'):
            # Remove an optional attribute from the attribute dictionary
            # and build a <driver> tag with these attributes.
            test_attributes = all_attributes.copy()
            del test_attributes[omit]
            driver_tag = self._getXorgDriverTag(test_attributes)
            sample_data = self.replaceSampledata(
                data=self.sample_data,
                replace_text=driver_tag,
                from_text='<driver name="fglrx"',
                to_text='/>')
            result, submission_id = self.runValidator(sample_data)
            self.assertNotEqual(
                submission_id, result,
                'omitted optional attribute %s of <driver> in <xorg> '
                    'treated as invalid' % omit)

    def testXorgDriverTagInvalidAttributes(self):
        """Test the validation of attributes of <driver> within <xorg>.

        Attributes other than name, version, class, device are invalid.
        """
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='<driver name="fglrx" version="1.23" foo="bar"/>',
            from_text='<driver name="fglrx"',
            to_text='/>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Extra element xorg in interleave',
            'detection of invalid attribute for <driver> in <xorg>')

    def testXorgDriverTagSubtags(self):
        """Test the validation of sub-tags of <driver> within <xorg>."""
        # Sub-tags are not allowed.
        driver_tag = ('<driver device="12" version="1.23" name="fglrx" '
                      'class="X.Org Video Driver"><nonsense/></driver>')
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text=driver_tag,
            from_text='<driver name="fglrx"',
            to_text='/>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Extra element xorg in interleave',
            'detection of invalid sub-tag of <driver> in <xorg>')

    def testXorgDriverTagCData(self):
        """Test the validation of sub-tags of <driver> within <xorg>."""
        # CDATA is not allowed.
        driver_tag = ('<driver device="12" version="1.23" name="fglrx" '
                      'class="X.Org Video Driver">nonsense</driver>')
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text=driver_tag,
            from_text='<driver name="fglrx"',
            to_text='/>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Extra element xorg in interleave',
            'detection of invalid CDATA content of <driver> in <xorg>')

    def testQuestionsTagAttributes(self):
        """Test the validation of <questions> tag attributes."""
        # This tag has no attributes.
        sample_data = self.sample_data.replace(
            '<questions>', '<questions foo="bar">')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Invalid attribute foo for element questions',
            'detection of invalid attributes of <questions>')

    def testQuestionsTagAttributesSubTags(self):
        """Test the validation of the <questions> sub-tags."""
        # The only allowed sub-tag is <question>.
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text='<nonsense/>',
            where='</questions>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Expecting element question, got nonsense',
            'invalid sub-tag of <questions>')

        # The <questions> tag may be empty.
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='<questions/>',
            from_text='<questions>',
            to_text='</questions>')
        result, submission_id = self.runValidator(sample_data)
        self.assertNotEqual(result, None,
                            'Empty tag <questions> not treated as valid.')

    def testQuestionsTagCData(self):
        """Test the validation of CDATA in <questions> tag."""
        # CDATA content is not allowed.
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text='nonsense',
            where='</questions>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Expecting an element got text',
             'detection of invalid CDATA content of <questions>')

    def testQuestionTagValidAttributes(self):
        """Test the validation of valid <question> tag attributes."""
        # The attribute "name" is required.
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='<question plugin="foo">',
            from_text='<question name',
            to_text='>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Element questions has extra content: question',
            'detection of missing attribute "name" in <question>')

        # The attribute "plugin" is optional.
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='<question name="foo">',
            from_text='<question name',
            to_text='>')
        result, submission_id = self.runValidator(sample_data)
        self.assertNotEqual(
            result, None,
            '<question> tag without attribute "plugin" was treated as '
                'invalid')

    def testQuestionTagInvalidAttributes(self):
        """Test the validation of invalid <question> tag attributes."""
        # Other attributes are not allowed.
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='<question plugin="foo" bar="baz">',
            from_text='<question name',
            to_text='>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Invalid attribute bar for element question',
            'detection of invalid attribute in <question>.')

    def testQuestionTagValidSubtags(self):
        """Test the validation of valid <question> tag sub-tags."""
        # The sub-tag <command> is optional.
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='<question name="foo">',
            from_text='<question name',
            to_text='>')
        result, submission_id = self.runValidator(sample_data)
        self.assertNotEqual(
            result, None,
            'Omitting sub-tag <command> of <question> was treated as invalid')

        # The sub-tag <answer> is required; <answer_choices>, which follows
        # the first <answer> tag in the sample data, is invalid without
        # an accompanying <answer> tag.
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='',
            from_text='<answer type',
            to_text='</answer>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Expecting element answer, got answer_choices',
            'detection of omitted sub-tag <answer> of <question> (1)')

        # Omitting both <answer> and <answer_choice> is invalid too, but
        # results in a different error message.
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='',
            from_text='<answer type',
            to_text='</answer_choices>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Expecting an element answer, got nothing',
            'detection of omitted sub-tag <answer> of <question> (2)')

        # A tag <answer type="multiple_choice"> must have an accompanying
        # <answer_choices> tag.
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='',
            from_text='<answer_choices>',
            to_text='</answer_choices>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Expecting an element answer_choices, got nothing',
            'detection of omitted sub-tag <answer_choices> of <question>')

        # The sub-tag <target> is optional; it may appear more than once.
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='',
            from_text='<target',
            to_text='</target>')
        sample_data = sample_data.replace('<target id="43"/>', '')
        result, submission_id = self.runValidator(sample_data)
        self.assertNotEqual(
            result, None,
            'Omitting sub-tag <target> of <anwser> treated as invalid.')

        # The sub-tag <comment> is optional.
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='',
            from_text='<comment>',
            to_text='</comment>')
        result, submission_id = self.runValidator(sample_data)
        self.assertNotEqual(
            result, None,
            'Omitting sub-tag <comment> of <anwser> treated as invalid.')

    def testQuestionTagInValidSubtags(self):
        """Test the validation of invalid <question> tag sub-tags."""
        # other sub-tags are invalid.
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text='<nonsense/>',
            where='</question>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Element question has extra content: nonsense',
            'detection of omitted sub-tag <answer_choices> of <question>')

    def testAnswerCommandTag(self):
        """Test the validation of the <command> tag."""
        # No attributes are allowed.
        sample_data = self.sample_data.replace(
            '<command/>', '<command foo="bar"/>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Extra element command in interleave',
            'detection of invalid attributes of <command>')

        # No sub-tags are allowed.
        sample_data = self.sample_data.replace(
            '<command/>', '<command><nonsense/></command>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Extra element command in interleave',
             'detection of invalid sub-tags of <command>')

    def testAnswerTagAttributes(self):
        """Test the validation of <answer> tag attributes."""
        # The attribute "type" is required.
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='<answer>',
            from_text='<answer',
            to_text='>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Element answer failed to validate content',
             'detection of <answer> element without required attribute')

        # The only allowed values for the attribute type are:
        # "multiple_choice" and "measurement"
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='<answer type="nonsense">',
            from_text='<answer',
            to_text='>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Element answer failed to validate content',
            'detection of <answer> with wrong value of attribute type')

        # Tags of type measurement have the optional attribute unit.
        # The parser must check if the value of unit is reasonable
        # for a particular test or if the attribute may be omitted for
        # a particular test.
        sample_data = self.sample_data.replace(
            '<answer type="measurement" unit="MB/sec">38.4</answer>',
            '<answer type="measurement">38.4</answer>')
        result, submission_id = self.runValidator(sample_data)
        self.assertNotEqual(
            result, None,
            'measurement answer without required attribute unit treated '
                'as valid')

        # Other attributes are invalid.
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='<answer type="multiple_choice" foo="bar">',
            from_text='<answer',
            to_text='>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Element answer failed to validate attributes',
            'detection of <answer> with invalid attribute "foo"')

    def testAnswerTagContent(self):
        """Test the validation of <answer> content."""
        # Tags of type multiple_choice can have any text content. The
        # consistency check, if the text matches one of the
        # <answer_choices>, must be done by class SubmissionParser at
        # a later stage than the Relax NG validation.
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='<answer type="multiple_choice">nonsense</answer>',
            from_text='<answer',
            to_text='</answer>')
        result, submission_id = self.runValidator(sample_data)
        self.assertNotEqual(
            result, None,
            'Multiple choice answer with wrong content unexpctedly treated '
                'as invalid.')

        # Tags of type measurement must have numerical content.
        sample_data = self.sample_data.replace(
            '<answer type="measurement" unit="MB/sec">38.4</answer>',
            '<answer type="measurement" unit="MB/sec">nonsense</answer>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            "Type decimal doesn't allow value 'nonsense'",
            'detection of <answer> with invalid attribute')

        # Sub-tags are not allowed.
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='<answer type="multiple_choice">'
                             'pass<nonsense/></answer>',
            from_text='<answer',
            to_text='</answer>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Datatype element answer has child elements',
            'detection of <answer> with invalid attribute')

    def testAnswerChoicesTagAttributes(self):
        """Test the validation of <answer_choices> attributes."""
        # This tag has no attributes.
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='<answer_choices foo="bar">',
            from_text='<answer_choices',
            to_text='>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Invalid attribute foo for element answer_choices',
            'detection of invalid <answer_choices> attributes')

    def testAnswerChoicesTagCData(self):
        """Test the validation of <answer_choices> CDATA content."""
        # CDATA content is invalid.
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text='nonsense',
            where='</answer_choices>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Expecting an element got text',
            'detection of invalid CDATA in <answer_choices>')

    def testAnswerChoicesTagSubTags(self):
        """Test the validation of <answer_choices> sub-tags."""
        # The only allowed sub-tag is <value>
        sample_data = self.insertSampledata(
            data=self.sample_data,
            insert_text='<nonsense/>',
            where='</answer_choices>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Expecting element value, got nonsense',
            'detection of invalid sub-tag of <answer_choices>')

    def testTargetTagAttributes(self):
        """Test the validation of <target> tag attributes."""
        # This tag has the required attribute "id".
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='<target>',
            from_text='<target',
            to_text='>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Element target failed to validate attributes',
            'detection of missing attribute "id" for <target>')

        # "id" must not be empty.
        sample_data = self.sample_data.replace('<target id="42">',
                                               '<target>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Element target failed to validate attributes',
            'detection of empty attribute "id" for <target>')

        # "id" must have integer content.
        sample_data = self.sample_data.replace('<target id="42">',
                                               '<target>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Element target failed to validate attributes',
            'detection of <target> attribute "id" with non-integer content')

        # Other attributes are not allowed.
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='<target id="1" foo="bar">',
            from_text='<target',
            to_text='>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Invalid attribute foo for element target',
            'detection of invalid <target> attribute')

    def testTargetTagCData(self):
        """Test the validation of <target> tag CDATA content."""
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='<target id="2">nonsense</target>',
            from_text='<target',
            to_text='</target>')
        result, submission_id = self.runValidator(sample_data)
        self.assertEqual(
            result, None,
            'CDATA content of <target> treated as valid')

    def testTargetTagValidSubtag(self):
        """Test the validation of the valid <target> sub-tag <driver>."""
        # The only allowed sub-tag is <driver>.
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='<target id="42"><driver>foo</driver></target>',
            from_text='<target',
            to_text='</target>')
        result, submission_id = self.runValidator(sample_data)
        self.assertNotEqual(
            result, None,
            'Valid <driver> sub-tag of <target> treated as invalid')

    def testTargetTagInvalidSubtag(self):
        """Test the validation of an invalid <target> sub-tag."""
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='<target id="42"><nonsense/></target>',
            from_text='<target',
            to_text='</target>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Element target has extra content: nonsense',
            'detection of invalid sub-tag <nonsense> of <target>')

    def testTargetDriverTag(self):
        """Test the validation of the <driver> sub-tag of <target>."""
        # This tag has no attributes.
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text=(
                '<target id="42"><driver bar="baz">foo</driver></target>'),
            from_text='<target',
            to_text='</target>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Invalid attribute bar for element driver',
            'detection of invalid attribute of <driver> in <target>')

        # Sub-tags are not allowed.
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text=(
                '<target id="42"><driver>foo<nonsense/></driver></target>'),
            from_text='<target',
            to_text='</target>')
        result, submission_id = self.runValidator(sample_data)
        self.assertErrorMessage(
            submission_id, result,
            'Element driver has extra content: nonsense',
            'detection of invalid sub-tag <nonsense> of <driver> in <target>')

    def testMissingContextNode(self):
        """Validation of the <context> node."""
        # The default sample data contains this node. It is not a
        # required node, we can omit it without making the data
        # invalid.
        sample_data = self.replaceSampledata(
            data=self.sample_data,
            replace_text='',
            from_text='<context>',
            to_text='</context>')
        result, submission_id = self.runValidator(sample_data)
        self.assertNotEqual(
            result, None,
            'Submission without a <context> node did not validate.')

    def testContextNodeAttributes(self):
        """Validation of the <context> node attributes."""
        # This node must not have any attributes.
        sample_data = self.sample_data.replace(
            '<context>', '<context foo="bar">')
        result, submission_id = self.runValidator(sample_data)
        self.assertEqual(
            result, None,
            'Submission data containing a <context> node with attribute '
            'not detected as being invalid.')
        self.assertErrorMessage(
            submission_id, result,
            'Extra element context in interleave',
            'detection of invalid attribute of <context>')

    def testContextSubnodes(self):
        """Validation of sub-nodes of <context>."""
        # This node may only have the sub-node <info>.
        sample_data = self.sample_data.replace(
            '<context>', '<context><nonsense/>')
        result, submission_id = self.runValidator(sample_data)
        self.assertEqual(
            result, None,
            'Submission data containing a <context> node with a subnode '
            'not detected as being invalid.')
        self.assertErrorMessage(
            submission_id, result,
            'Extra element context in interleave',
            'detection of invalid sub-node of <context>')

    def testContextNodeCData(self):
        """Validation of the <context> node containing CData."""
        # this node must not have any CData content
        sample_data = self.sample_data.replace(
            '<context>', '<context>nonsense')
        result, submission_id = self.runValidator(sample_data)
        self.assertEqual(
            result, None,
            'Submission data containing a <context> node with CData '
            'content not detected as being invalid.')
        self.assertErrorMessage(
            submission_id, result,
            'Extra element context in interleave',
            'detection of invalid sub-node of <context>')

    def testInfoNodeAttributes(self):
        """Validation of <info> attributes."""
        # The attribute "command" is required.
        sample_data = self.sample_data.replace(
            '<info command="dmidecode">', '<info>')
        result, submission_id = self.runValidator(sample_data)
        self.assertEqual(
            result, None,
            'Submission data containing a <context> node with CData '
            'content not detected as being invalid.')
        self.assertErrorMessage(
            submission_id, result,
            'Extra element context in interleave',
            'detection of missing attribute "command" of <info> failed')
        # Other attributes are not allowed.
        sample_data = self.sample_data.replace(
            '<info command="dmidecode">',
            '<info command="dmidecode" foo="bar">')
        result, submission_id = self.runValidator(sample_data)
        self.assertEqual(
            result, None,
            'Submission data containing a <context> node with CData '
            'content not detected as being invalid.')
        self.assertErrorMessage(
            submission_id, result,
            'Extra element context in interleave',
            'detection of missing attribute "command" of <info> failed')

    def testInfoNodeSubnodes(self):
        """Validation of an <info> containing a sub-node."""
        # Sub-nodes are not allowed for <info>
        sample_data = self.sample_data.replace(
            '<info command="dmidecode">',
            '<info command="dmidecode"><nonsense/>')
        result, submission_id = self.runValidator(sample_data)
        self.assertEqual(
            result, None,
            'Submission data containing a <context> node with CData '
            'content not detected as being invalid.')
        self.assertErrorMessage(
            submission_id, result,
            'Extra element context in interleave',
            'detection of an invalid sub.node of <info> failed')

    def test_natty_reports_validate(self):
        # HWDB submissions from Natty can be processed.
        # the raw data from these reports would be passed directly
        # to the RelaxNG validator, they would fail, because they
        # do not have the sub-nodes <dmi> and <udev> inside <hardware>.
        # The data is stored instead in the nodes
        # <info command="grep -r . /sys/class/dmi/id/ 2&gt;/dev/null">
        # and <info command="udevadm info --export-db">
        #
        # The method SubmissionParser.fixFrequentErrors() (called by
        # _getValidatedEtree()) creates the missing nodes, so that
        # _getValidatedEtree() succeeds.
        sample_data_path = os.path.join(
            config.root, 'lib', 'lp', 'hardwaredb', 'scripts',
            'tests', 'hardwaretest-natty.xml')
        sample_data = open(sample_data_path).read()
        result, submission_id = self.runValidator(sample_data)
        self.assertTrue(result is None)
