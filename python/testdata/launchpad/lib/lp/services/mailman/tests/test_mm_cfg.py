# Copyright 20010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
"""Test the Launchpad defaults monekypatch and mm_cfg."""

__metaclass__ = type
__all__ = []

import os

from Mailman import (
    mm_cfg,
    Utils,
    )

from lp.services.config import config
from lp.services.mailman.config import configure_prefix
from lp.services.mailman.monkeypatches import monkey_patch
from lp.testing import TestCase
from lp.testing.layers import FunctionalLayer


class TestMMCfgDefaultsTestCase(TestCase):
    """Test launchapd default overrides."""

    layer = FunctionalLayer

    def test_common_values(self):
        # Launchpad's boolean and string parameters.
        self.assertEqual('unused_mailman_site_list', mm_cfg.MAILMAN_SITE_LIST)
        self.assertEqual(None, mm_cfg.MTA)
        self.assertEqual(3, mm_cfg.DEFAULT_GENERIC_NONMEMBER_ACTION)
        self.assertEqual(False, mm_cfg.DEFAULT_SEND_REMINDERS)
        self.assertEqual(True, mm_cfg.DEFAULT_SEND_WELCOME_MSG)
        self.assertEqual(False, mm_cfg.DEFAULT_SEND_GOODBYE_MSG)
        self.assertEqual(False, mm_cfg.DEFAULT_DIGESTABLE)
        self.assertEqual(False, mm_cfg.DEFAULT_BOUNCE_NOTIFY_OWNER_ON_DISABLE)
        self.assertEqual(False, mm_cfg.DEFAULT_BOUNCE_NOTIFY_OWNER_ON_REMOVAL)
        self.assertEqual(True, mm_cfg.VERP_PERSONALIZED_DELIVERIES)
        self.assertEqual(False, mm_cfg.DEFAULT_FORWARD_AUTO_DISCARDS)
        self.assertEqual(False, mm_cfg.DEFAULT_BOUNCE_PROCESSING)

    def test_qrunners(self):
        # The queue runners used by Launchpad.
        runners = [pair[0] for pair in mm_cfg.QRUNNERS if pair[1] == 1]
        expected = [
            'ArchRunner', 'BounceRunner', 'IncomingRunner', 'OutgoingRunner',
            'VirginRunner', 'RetryRunner', 'XMLRPCRunner']
        self.assertEqual(expected, runners)

    def test_global_pipeline(self):
        # The ordered list of handlers used by Launchpad.
        # NB. This is a very important list when debuggin were a message
        # has been touched.
        expected = [
            'LaunchpadMember', 'SpamDetect', 'Approve', 'Replybot',
            'LPStanding', 'LPModerate', 'LPSize',
            'MimeDel', 'Scrubber', 'Emergency', 'Tagger', 'CalcRecips',
            'AvoidDuplicates', 'Cleanse', 'CleanseDKIM', 'CookHeaders',
            'LaunchpadHeaders', 'ToDigest', 'ToArchive', 'ToUsenet',
            'AfterDelivery', 'Acknowledge', 'ToOutgoing']
        self.assertEqual(expected, mm_cfg.GLOBAL_PIPELINE)


class TestMMCfgLaunchpadConfigTestCase(TestCase):
    """Test launchapd default overrides.

    The mailman config is generated from the selected launchpad config.
    The config will either be the test runner or the app server depending
    on the what was previously used when mailman was run. The config must
    be created in setup to ensure predicable values.
    """

    layer = FunctionalLayer

    def setUp(self):
        super(TestMMCfgLaunchpadConfigTestCase, self).setUp()
        # Generate a mailman config using this environment's config.
        mailman_path = configure_prefix(config.mailman.build_prefix)
        monkey_patch(mailman_path, config)
        reload(mm_cfg)

    def test_mail_server(self):
        # Launchpad's smtp config values.
        host, port = config.mailman.smtp.split(':')
        self.assertEqual(host, mm_cfg.SMTPHOST)
        self.assertEqual(int(port), mm_cfg.SMTPPORT)

    def test_smtp_max_config(self):
        # Mailman SMTP max limits are configured from the LP config.
        self.assertEqual(
            config.mailman.smtp_max_rcpts,
            mm_cfg.SMTP_MAX_RCPTS)
        self.assertEqual(
            config.mailman.smtp_max_sesions_per_connection,
            mm_cfg.SMTP_MAX_SESSIONS_PER_CONNECTION)

    def test_xmlrpc_server(self):
        # Launchpad's smtp config values.
        self.assertEqual(
            config.mailman.xmlrpc_url,
            mm_cfg.XMLRPC_URL)
        self.assertEqual(
            config.mailman.xmlrpc_runner_sleep,
            mm_cfg.XMLRPC_SLEEPTIME)
        self.assertEqual(
            config.mailman.subscription_batch_size,
            mm_cfg.XMLRPC_SUBSCRIPTION_BATCH_SIZE)
        self.assertEqual(
            config.mailman.shared_secret,
            mm_cfg.LAUNCHPAD_SHARED_SECRET)

    def test_messge_footer(self):
        # Launchpad's email footer.
        self.assertEqual(
            config.mailman.list_help_header,
            mm_cfg.LIST_HELP_HEADER)
        self.assertEqual(
            config.mailman.list_owner_header_template,
            mm_cfg.LIST_SUBSCRIPTION_HEADERS)
        self.assertEqual(
            config.mailman.archive_url_template,
            mm_cfg.LIST_ARCHIVE_HEADER_TEMPLATE)
        self.assertEqual(
            config.mailman.list_owner_header_template,
            mm_cfg.LIST_OWNER_HEADER_TEMPLATE)
        self.assertEqual(
            "-- \n"
            "Mailing list: $list_owner\n"
            "Post to     : $list_post\n"
            "Unsubscribe : $list_unsubscribe\n"
            "More help   : $list_help\n",
            mm_cfg.DEFAULT_MSG_FOOTER)

    def test_message_rules(self):
        # Launchpad's rules for handling messages.
        self.assertEqual(
            config.mailman.soft_max_size,
            mm_cfg.LAUNCHPAD_SOFT_MAX_SIZE)
        self.assertEqual(
            config.mailman.hard_max_size,
            mm_cfg.LAUNCHPAD_HARD_MAX_SIZE)
        self.assertEqual(
            config.mailman.register_bounces_every,
            mm_cfg.REGISTER_BOUNCES_EVERY)

    def test_archive_setup(self):
        # Launchpad's rules for setting up list archives.
        self.assertTrue('-add' in mm_cfg.PUBLIC_EXTERNAL_ARCHIVER)
        self.assertTrue('-spammode' in mm_cfg.PUBLIC_EXTERNAL_ARCHIVER)
        self.assertTrue('-umask 022'in mm_cfg.PUBLIC_EXTERNAL_ARCHIVER)
        self.assertTextMatchesExpressionIgnoreWhitespace(
            '-dbfile /var/tmp'
            '/mailman/archives/private/%\(listname\)s.mbox/mhonarc.db',
            mm_cfg.PUBLIC_EXTERNAL_ARCHIVER)
        self.assertTextMatchesExpressionIgnoreWhitespace(
            '-outdir /var/tmp/mailman/mhonarc/%\(listname\)s',
            mm_cfg.PUBLIC_EXTERNAL_ARCHIVER)
        self.assertTextMatchesExpressionIgnoreWhitespace(
            '-definevar ML-NAME=%\(listname\)s',
            mm_cfg.PUBLIC_EXTERNAL_ARCHIVER)
        self.assertTextMatchesExpressionIgnoreWhitespace(
            '-rcfile /var/tmp/mailman/data/lp-mhonarc-common.mrc',
            mm_cfg.PUBLIC_EXTERNAL_ARCHIVER)
        self.assertTextMatchesExpressionIgnoreWhitespace(
            '-stderr /var/tmp/mailman/logs/mhonarc',
            mm_cfg.PUBLIC_EXTERNAL_ARCHIVER)
        self.assertTextMatchesExpressionIgnoreWhitespace(
            '-stdout /var/tmp/mailman/logs/mhonarc',
            mm_cfg.PUBLIC_EXTERNAL_ARCHIVER)
        self.assertEqual(
            mm_cfg.PRIVATE_EXTERNAL_ARCHIVER, mm_cfg.PUBLIC_EXTERNAL_ARCHIVER)


class TestMHonArchMRC(TestCase):
    """Test the archive configuration."""

    layer = FunctionalLayer

    def test_html_disabled(self):
        # HTML messages are ignored because of CVE-2010-4524.
        mrc_path = os.path.join(
            config.root, 'lib', 'lp', 'services', 'mailman', 'monkeypatches',
            'lp-mhonarc-common.mrc')
        with open(mrc_path) as mrc_file:
            self.mrc = mrc_file.read()
        mime_excs = (
            '<MIMEExcs> '
            'text/html '
            'text/x-html '
            '</MIMEExcs> ')
        self.assertTextMatchesExpressionIgnoreWhitespace(
            mime_excs, self.mrc)


class TestSiteTemplates(TestCase):
    """Test launchapd site templates."""

    layer = FunctionalLayer

    def test_postheld(self):
        postheld_dict = {
            'listname': 'fake-list',
            'hostname': 'lists.launchpad.net',
            'reason': 'XXX',
            'sender': 'test@canonical.com',
            'subject': "YYY",
            'admindb_url': 'http://lists.launchpad.net/fake/admin',
            }
        text, file_name = Utils.findtext('postheld.txt', dict=postheld_dict)
        self.assertTrue(
            file_name.endswith('/lib/mailman/templates/site/en/postheld.txt'))
        self.assertEqual(
            "Your mail to 'fake-list' with the subject\n\n"
            "    YYY\n\n"
            "Is being held until the list moderator can review it for "
            "approval.\n\nThe reason it is being held:\n\n"
            "    XXX\n\n"
            "Either the message will get posted to the list, or you will "
            "receive\nnotification of the moderator's decision.\n",
            text)
