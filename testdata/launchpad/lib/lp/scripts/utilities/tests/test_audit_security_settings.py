# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests the security.cfg auditor."""

__metaclass__ = type

from lp.scripts.utilities.settingsauditor import SettingsAuditor
from lp.testing import TestCase
from lp.testing.layers import BaseLayer


class TestAuditSecuritySettings(TestCase):

    layer = BaseLayer

    def setUp(self):
        super(TestAuditSecuritySettings, self).setUp()
        self.test_settings = (
            '# This is the header.\n'
            '[good]\n'
            'public.foo = SELECT\n'
            'public.bar = SELECT, INSERT\n'
            'public.baz = SELECT\n'
            '\n'
            '[bad]\n'
            'public.foo = SELECT\n'
            'public.bar = SELECT, INSERT\n'
            'public.bar = SELECT\n'
            'public.baz = SELECT')

    def test_getHeader(self):
        sa = SettingsAuditor(self.test_settings)
        header = sa._getHeader()
        self.assertEqual(
            header,
            '# This is the header.\n')

    def test_extract_config_blocks(self):
        test_settings = self.test_settings.replace(
            '# This is the header.\n', '')
        sa = SettingsAuditor(test_settings)
        sa._separateConfigBlocks()
        self.assertContentEqual(
            ['[good]', '[bad]'],
            sa.config_blocks.keys())

    def test_audit_block(self):
        sa = SettingsAuditor('')
        test_block = (
            '[bad]\n'
            'public.foo = SELECT\n'
            'public.bar = SELECT, INSERT\n'
            'public.bar = SELECT\n'
            'public.baz = SELECT\n')
        sa.config_blocks = {'[bad]': test_block}
        sa.config_labels = ['[bad]']
        sa._processBlocks()
        expected = (
            '[bad]\n'
            'public.bar = SELECT\n'
            'public.bar = SELECT, INSERT\n'
            'public.baz = SELECT\n'
            'public.foo = SELECT')
        self.assertEqual(expected, sa.config_blocks['[bad]'])
        expected_error = '[bad]\n\tDuplicate setting found: public.bar'
        self.assertTrue(expected_error in sa.error_data)

    def test_audit(self):
        sa = SettingsAuditor(self.test_settings)
        new_settings = sa.audit()
        expected_settings = (
            '# This is the header.\n'
            '[good]\n'
            'public.bar = SELECT, INSERT\n'
            'public.baz = SELECT\n'
            'public.foo = SELECT\n'
            '\n'
            '[bad]\n'
            'public.bar = SELECT\n'
            'public.bar = SELECT, INSERT\n'
            'public.baz = SELECT\n'
            'public.foo = SELECT')
        self.assertEqual(expected_settings, new_settings)

    def test_comments_stipped(self):
        sa = SettingsAuditor('')
        test_data = (
            '#[foo]\n'
            '#public.foo = SELECT\n')
        data = sa._strip(test_data)
        self.assertEqual('', data)


