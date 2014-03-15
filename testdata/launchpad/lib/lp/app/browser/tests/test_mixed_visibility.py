# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from lp.app.browser.tales import TeamFormatterAPI
from lp.registry.interfaces.person import PersonVisibility
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestMixedVisibility(TestCaseWithFactory):
    layer = DatabaseFunctionalLayer

    def test_mixed_visibility(self):
        # If a viewer attempts to (or code on their behalf) get information
        # about a private team, with the feature flag enabled, an
        # informational OOPS is logged.
        team = self.factory.makeTeam(visibility=PersonVisibility.PRIVATE)
        viewer = self.factory.makePerson()
        with person_logged_in(viewer):
            self.assertEqual(
                u'<hidden>', TeamFormatterAPI(team).displayname(None))
        self.assertEqual(1, len(self.oopses))
        self.assertTrue(
            'MixedVisibilityError' in self.oopses[0]['tb_text'])
