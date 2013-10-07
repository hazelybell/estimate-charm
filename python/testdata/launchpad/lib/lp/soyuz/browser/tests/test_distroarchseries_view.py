# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from lp.services.webapp.servers import LaunchpadTestRequest
from lp.soyuz.browser.distroarchseries import DistroArchSeriesAdminView
from lp.testing import (
    login,
    TestCaseWithFactory,
    )
from lp.testing.layers import LaunchpadFunctionalLayer
from lp.testing.sampledata import LAUNCHPAD_ADMIN


class TestDistroArchSeriesView(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        """Create a distroarchseries for the tests and login as an admin."""
        super(TestDistroArchSeriesView, self).setUp()
        self.das = self.factory.makeDistroArchSeries()
        # Login as an admin to ensure access to the view's context
        # object.
        login(LAUNCHPAD_ADMIN)

    def initialize_admin_view(self, enabled=True):
        # Initialize the admin view with the supplied params.
        method = 'POST'
        form = {
            'field.actions.update': 'update',
            }

        if enabled:
            form['field.enabled'] = 'on'
        else:
            form['field.enabled'] = 'off'

        view = DistroArchSeriesAdminView(
            self.das, LaunchpadTestRequest(method=method, form=form))
        view.initialize()
        return view

    def test_enabling_enabled_flag(self):
        view = self.initialize_admin_view(enabled=False)
        self.assertEqual(0, len(view.errors))
        self.assertFalse(view.context.enabled)

    def test_disabling_enabled_flag(self):
        view = self.initialize_admin_view(enabled=True)
        self.assertEqual(0, len(view.errors))
        self.assertTrue(view.context.enabled)
