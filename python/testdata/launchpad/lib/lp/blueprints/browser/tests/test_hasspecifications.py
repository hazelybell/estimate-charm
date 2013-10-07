# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from lp.testing import (
    login_person,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.views import create_initialized_view


class TestPersonSpecWorkloadView(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestPersonSpecWorkloadView, self).setUp()
        self.owner = self.factory.makePerson(name='blue')
        login_person(self.owner)
        self.team = self.factory.makeTeam(name='square', owner='blue')
        self.member = self.factory.makePerson(name='green')
        self.team.addMember(self.member, self.owner)

    def test_view_attributes(self):
        view = create_initialized_view(
            self.team, name='+specworkload')
        label = 'Blueprint workload'
        self.assertEqual(label, view.label)
        self.assertEqual(20, view.members.batch.size)
