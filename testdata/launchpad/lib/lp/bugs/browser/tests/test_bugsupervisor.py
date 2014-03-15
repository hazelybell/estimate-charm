# Copyright 2010-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version (see the file LICENSE).

"""Unit tests for bug supervisor views."""

__metaclass__ = type

from zope.component import getUtility

from lp.bugs.browser.bugsupervisor import BugSupervisorEditSchema
from lp.registry.enums import PersonVisibility
from lp.registry.interfaces.person import IPersonSet
from lp.services.webapp.publisher import canonical_url
from lp.testing import (
    BrowserTestCase,
    login_person,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.sampledata import ADMIN_EMAIL
from lp.testing.views import create_initialized_view


class TestBugSupervisorEditView(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBugSupervisorEditView, self).setUp()
        self.owner = self.factory.makePerson(
            name='splat', displayname='<splat />')
        self.product = self.factory.makeProduct(
            name="boing", displayname='<boing />', owner=self.owner)
        self.team = self.factory.makeTeam(name='thud', owner=self.owner)
        login_person(self.owner)

    def _makeForm(self, person):
        if person is None:
            name = ''
        else:
            name = person.name
        return {
            'field.bug_supervisor': name,
            'field.actions.change': 'Change',
            }

    def test_view_attributes(self):
        self.product.displayname = 'Boing'
        view = create_initialized_view(
            self.product, name='+bugsupervisor')
        label = 'Edit bug supervisor for Boing'
        self.assertEqual(label, view.label)
        self.assertEqual(label, view.page_title)
        fields = ['bug_supervisor']
        self.assertEqual(fields, view.field_names)
        adapter, context = view.adapters.popitem()
        self.assertEqual(BugSupervisorEditSchema, adapter)
        self.assertEqual(self.product, context)
        self.assertEqual('http://launchpad.dev/boing', view.next_url)
        self.assertEqual('http://launchpad.dev/boing', view.cancel_url)

    def test_owner_appoint_self_from_none(self):
        # This also verifies that displaynames are escaped.
        form = self._makeForm(self.owner)
        view = create_initialized_view(
            self.product, name='+bugsupervisor', form=form)
        self.assertEqual([], view.errors)
        self.assertEqual(self.product.bug_supervisor, self.owner)
        notifications = view.request.response.notifications
        self.assertEqual(1, len(notifications))
        expected = 'Bug supervisor privilege granted.'
        self.assertEqual(expected, notifications.pop().message)

    def test_owner_appoint_self_from_another(self):
        self.product.bug_supervisor = self.team
        form = self._makeForm(self.owner)
        view = create_initialized_view(
            self.product, name='+bugsupervisor', form=form)
        self.assertEqual([], view.errors)
        self.assertEqual(self.owner, self.product.bug_supervisor)

    def test_owner_appoint_none(self):
        self.product.bug_supervisor = self.owner
        form = self._makeForm(None)
        view = create_initialized_view(
            self.product, name='+bugsupervisor', form=form)
        self.assertEqual([], view.errors)
        self.assertEqual(self.product.bug_supervisor, None)
        notifications = view.request.response.notifications
        self.assertEqual(1, len(notifications))
        expected = (
            'Successfully cleared the bug supervisor. '
            'You can set the bug supervisor again at any time.')
        self.assertEqual(expected, notifications.pop().message)

    def test_owner_appoint_his_team(self):
        form = self._makeForm(self.team)
        view = create_initialized_view(
            self.product, name='+bugsupervisor', form=form)
        self.assertEqual([], view.errors)
        self.assertEqual(self.team, self.product.bug_supervisor)

    def test_owner_appoint_his_private_team(self):
        private_team = self.factory.makeTeam(
            owner=self.owner,
            visibility=PersonVisibility.PRIVATE)
        form = self._makeForm(private_team)
        view = create_initialized_view(
            self.product, name='+bugsupervisor', form=form)
        self.assertEqual([], view.errors)
        self.assertEqual(private_team, self.product.bug_supervisor)


class TestBugSupervisorLink(BrowserTestCase):

    layer = DatabaseFunctionalLayer

    def test_with_no_access(self):
        product = self.factory.makeProduct(official_malone=True)
        url = canonical_url(product, rootsite="bugs", view_name='+bugs')
        browser = self.getUserBrowser(url, user=self.factory.makePerson())
        self.assertNotIn('Change bug supervisor', browser.contents)

    def test_with_access(self):
        product = self.factory.makeProduct(official_malone=True)
        url = canonical_url(product, rootsite="bugs", view_name='+bugs')
        browser = self.getUserBrowser(url, user=product.owner)
        self.assertIn('Change bug supervisor', browser.contents)

    def test_as_admin(self):
        product = self.factory.makeProduct(official_malone=True)
        url = canonical_url(product, rootsite="bugs", view_name='+bugs')
        admin = getUtility(IPersonSet).getByEmail(ADMIN_EMAIL)
        browser = self.getUserBrowser(url, user=admin)
        self.assertIn('Change bug supervisor', browser.contents)
