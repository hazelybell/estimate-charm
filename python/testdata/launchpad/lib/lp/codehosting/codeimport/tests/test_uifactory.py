# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for `LoggingUIFactory`."""

__metaclass__ = type

from lp.codehosting.codeimport.uifactory import LoggingUIFactory
from lp.services.log.logger import BufferLogger
from lp.testing import (
    FakeTime,
    TestCase,
    )


class TestLoggingUIFactory(TestCase):
    """Tests for `LoggingUIFactory`."""

    def setUp(self):
        TestCase.setUp(self)
        self.fake_time = FakeTime(12345)
        self.logger = BufferLogger()

    def makeLoggingUIFactory(self):
        """Make a `LoggingUIFactory` with fake time and contained output."""
        return LoggingUIFactory(
            time_source=self.fake_time.now, logger=self.logger)

    def test_first_progress_updates(self):
        # The first call to progress generates some output.
        factory = self.makeLoggingUIFactory()
        bar = factory.nested_progress_bar()
        bar.update("hi")
        self.assertEqual('INFO hi\n', self.logger.getLogBuffer())

    def test_second_rapid_progress_doesnt_update(self):
        # The second of two progress calls that are less than the factory's
        # interval apart does not generate output.
        factory = self.makeLoggingUIFactory()
        bar = factory.nested_progress_bar()
        bar.update("hi")
        self.fake_time.advance(factory.interval / 2)
        bar.update("there")
        self.assertEqual('INFO hi\n', self.logger.getLogBuffer())

    def test_second_slow_progress_updates(self):
        # The second of two progress calls that are more than the factory's
        # interval apart does generate output.
        factory = self.makeLoggingUIFactory()
        bar = factory.nested_progress_bar()
        bar.update("hi")
        self.fake_time.advance(factory.interval * 2)
        bar.update("there")
        self.assertEqual(
            'INFO hi\n'
            'INFO there\n',
            self.logger.getLogBuffer())

    def test_first_progress_on_new_bar_updates(self):
        # The first progress on a new progress task always generates output.
        factory = self.makeLoggingUIFactory()
        bar = factory.nested_progress_bar()
        bar.update("hi")
        self.fake_time.advance(factory.interval / 2)
        bar2 = factory.nested_progress_bar()
        bar2.update("there")
        self.assertEqual(
            'INFO hi\nINFO hi:there\n', self.logger.getLogBuffer())

    def test_update_with_count_formats_nicely(self):
        # When more details are passed to update, they are formatted nicely.
        factory = self.makeLoggingUIFactory()
        bar = factory.nested_progress_bar()
        bar.update("hi", 1, 8)
        self.assertEqual('INFO hi 1/8\n', self.logger.getLogBuffer())

    def test_report_transport_activity_reports_bytes_since_last_update(self):
        # If there is no call to _progress_updated for 'interval' seconds, the
        # next call to report_transport_activity will report however many
        # bytes have been transferred since the update.
        factory = self.makeLoggingUIFactory()
        bar = factory.nested_progress_bar()
        bar.update("hi", 1, 10)
        self.fake_time.advance(factory.interval / 2)
        # The bytes in this call will not be reported:
        factory.report_transport_activity(None, 1, 'read')
        self.fake_time.advance(factory.interval)
        bar.update("hi", 2, 10)
        self.fake_time.advance(factory.interval / 2)
        factory.report_transport_activity(None, 10, 'read')
        self.fake_time.advance(factory.interval)
        factory.report_transport_activity(None, 100, 'read')
        self.fake_time.advance(factory.interval * 2)
        # This call will cause output that does not include the transport
        # activity info.
        bar.update("hi", 3, 10)
        self.assertEqual(
            'INFO hi 1/10\n'
            'INFO hi 2/10\n'
            'INFO 110 bytes transferred | hi 2/10\n'
            'INFO hi 3/10\n',
            self.logger.getLogBuffer())

    def test_note(self):
        factory = self.makeLoggingUIFactory()
        factory.note("Banja Luka")
        self.assertEqual('INFO Banja Luka\n', self.logger.getLogBuffer())

    def test_show_error(self):
        factory = self.makeLoggingUIFactory()
        factory.show_error("Exploding Peaches")
        self.assertEqual(
            "ERROR Exploding Peaches\n", self.logger.getLogBuffer())

    def test_confirm_action(self):
        factory = self.makeLoggingUIFactory()
        self.assertTrue(factory.confirm_action(
            "How are you %(when)s?", "wellness", {"when": "today"}))

    def test_show_message(self):
        factory = self.makeLoggingUIFactory()
        factory.show_message("Peaches")
        self.assertEqual("INFO Peaches\n", self.logger.getLogBuffer())

    def test_get_username(self):
        factory = self.makeLoggingUIFactory()
        self.assertIs(
            None, factory.get_username("Who are you %(when)s?", when="today"))

    def test_get_password(self):
        factory = self.makeLoggingUIFactory()
        self.assertIs(
            None,
            factory.get_password("How is your %(drink)s", drink="coffee"))

    def test_show_warning(self):
        factory = self.makeLoggingUIFactory()
        factory.show_warning("Peaches")
        self.assertEqual("WARNING Peaches\n", self.logger.getLogBuffer())

    def test_show_warning_unicode(self):
        factory = self.makeLoggingUIFactory()
        factory.show_warning(u"Peach\xeas")
        self.assertEqual(
            "WARNING Peach\xc3\xaas\n", self.logger.getLogBuffer())

    def test_user_warning(self):
        factory = self.makeLoggingUIFactory()
        factory.show_user_warning('cross_format_fetch',
            from_format="athing", to_format="anotherthing")
        message = factory._user_warning_templates['cross_format_fetch'] % {
            "from_format": "athing",
            "to_format": "anotherthing",
            }
        self.assertEqual("WARNING %s\n" % message, self.logger.getLogBuffer())

    def test_clear_term(self):
        factory = self.makeLoggingUIFactory()
        factory.clear_term()
        self.assertEqual("", self.logger.getLogBuffer())
