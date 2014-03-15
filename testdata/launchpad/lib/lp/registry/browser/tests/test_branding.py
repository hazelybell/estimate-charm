# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for Branding."""

__metaclass__ = type

from lp.registry.browser.branding import BrandingChangeView
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


class TestBrandingChangeView(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBrandingChangeView, self).setUp()
        self.context = self.factory.makePerson(name='cow')
        self.view = BrandingChangeView(self.context, LaunchpadTestRequest())

    def test_common_attributes(self):
        # The canonical URL of a GPG key is ssh-keys
        label = 'Change the images used to represent Cow in Launchpad'
        self.assertEqual(label, self.view.label)
        self.assertEqual('Change branding', self.view.page_title)
