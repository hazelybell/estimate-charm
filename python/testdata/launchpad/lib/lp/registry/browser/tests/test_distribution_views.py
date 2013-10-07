# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

import soupmatchers
from zope.component import getUtility

from lp.archivepublisher.interfaces.publisherconfig import IPublisherConfigSet
from lp.registry.browser.distribution import DistributionPublisherConfigView
from lp.registry.interfaces.distribution import IDistributionSet
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.soyuz.interfaces.processor import IProcessorSet
from lp.testing import (
    login,
    login_celebrity,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.sampledata import LAUNCHPAD_ADMIN
from lp.testing.views import create_initialized_view


class TestDistributionPublisherConfigView(TestCaseWithFactory):
    """Test `DistributionPublisherConfigView`."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        # Create a test distribution.
        super(TestDistributionPublisherConfigView, self).setUp()
        self.distro = self.factory.makeDistribution(no_pubconf=True)
        login(LAUNCHPAD_ADMIN)

        self.ROOT_DIR = u"rootdir/test"
        self.BASE_URL = u"http://base.url"
        self.COPY_BASE_URL = u"http://copybase.url"

    def test_empty_initial_values(self):
        # Test that the page will display empty field values with no
        # existing config set up.
        view = DistributionPublisherConfigView(
            self.distro, LaunchpadTestRequest())

        for value in view.initial_values:
            self.assertEqual(u"", value)

    def test_previous_initial_values(self):
        # Test that the initial values are the same as the ones in the
        # existing database record.
        pubconf = self.factory.makePublisherConfig(
            distribution=self.distro)

        view = DistributionPublisherConfigView(
            self.distro, LaunchpadTestRequest())

        self.assertEqual(pubconf.root_dir, view.initial_values["root_dir"])
        self.assertEqual(pubconf.base_url, view.initial_values["base_url"])
        self.assertEqual(
            pubconf.copy_base_url, view.initial_values["copy_base_url"])

    def _change_and_test_config(self):
        form = {
            'field.actions.save': 'save',
            'field.root_dir': self.ROOT_DIR,
            'field.base_url': self.BASE_URL,
            'field.copy_base_url': self.COPY_BASE_URL,
        }

        view = DistributionPublisherConfigView(
            self.distro, LaunchpadTestRequest(method='POST', form=form))
        view.initialize()

        config = getUtility(
            IPublisherConfigSet).getByDistribution(self.distro)

        self.assertEqual(self.ROOT_DIR, config.root_dir)
        self.assertEqual(self.BASE_URL, config.base_url)
        self.assertEqual(self.COPY_BASE_URL, config.copy_base_url)

    def test_add_new_config(self):
        # Test POSTing a new config.
        self._change_and_test_config()

    def test_change_existing_config(self):
        # Test POSTing to change existing config.
        self.factory.makePublisherConfig(
            distribution=self.distro,
            root_dir=u"random",
            base_url=u"blah",
            copy_base_url=u"foo",
            )
        self._change_and_test_config()


class TestDistroAddView(TestCaseWithFactory):
    """Test the +add page for a new distribution."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestDistroAddView, self).setUp()
        self.owner = self.factory.makePerson()
        self.registrant = self.factory.makePerson()
        self.simple_user = self.factory.makePerson()
        self.admin = login_celebrity('admin')
        self.distributionset = getUtility(IDistributionSet)
        self.restricted_processors = getUtility(IProcessorSet).getRestricted()

    def getDefaultAddDict(self):
        return {
            'field.name': 'newbuntu',
            'field.displayname': 'newbuntu',
            'field.title': 'newbuntu',
            'field.summary': 'newbuntu',
            'field.description': 'newbuntu',
            'field.domainname': 'newbuntu',
            'field.members': self.simple_user.name,
            'field.require_virtualized': '',
            'field.enabled_restricted_processors': [processor.name
                for processor in self.restricted_processors],
            'field.actions.save': 'Save',
            }

    def test_registrant_set_by_creation(self):
        # The registrant field should be set to the Person creating
        # the distribution.
        creation_form = self.getDefaultAddDict()
        create_initialized_view(
            self.distributionset, '+add', principal=self.admin,
            method='POST', form=creation_form)
        distribution = self.distributionset.getByName('newbuntu')
        self.assertEqual(distribution.owner, self.admin)
        self.assertEqual(distribution.registrant, self.admin)

    def test_add_distro_default_value_require_virtualized(self):
        view = create_initialized_view(
            self.distributionset, '+add', principal=self.admin,
            method='GET')

        widget = view.widgets['require_virtualized']
        self.assertEqual(False, widget._getCurrentValue())

    def test_add_distro_init_value_enabled_restricted_processors(self):
        view = create_initialized_view(
            self.distributionset, '+add', principal=self.admin,
            method='GET')

        widget = view.widgets['enabled_restricted_processors']
        self.assertContentEqual(
            self.restricted_processors, widget._getCurrentValue())
        self.assertContentEqual(
            self.restricted_processors,
            [item.value for item in widget.vocabulary])

    def test_add_distro_require_virtualized(self):
        creation_form = self.getDefaultAddDict()
        creation_form['field.require_virtualized'] = ''
        create_initialized_view(
            self.distributionset, '+add', principal=self.admin,
            method='POST', form=creation_form)

        distribution = self.distributionset.getByName('newbuntu')
        self.assertEqual(
            False,
            distribution.main_archive.require_virtualized)

    def test_add_distro_enabled_restricted_processors(self):
        creation_form = self.getDefaultAddDict()
        creation_form['field.enabled_restricted_processors'] = []
        create_initialized_view(
            self.distributionset, '+add', principal=self.admin,
            method='POST', form=creation_form)

        distribution = self.distributionset.getByName('newbuntu')
        self.assertContentEqual(
            [], distribution.main_archive.enabled_restricted_processors)


class TestDistroEditView(TestCaseWithFactory):
    """Test the +edit page for a distribution."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestDistroEditView, self).setUp()
        self.admin = login_celebrity('admin')
        self.distribution = self.factory.makeDistribution()
        self.restricted_processors = getUtility(IProcessorSet).getRestricted()

    def test_edit_distro_init_value_require_virtualized(self):
        view = create_initialized_view(
            self.distribution, '+edit', principal=self.admin,
            method='GET')

        widget = view.widgets['require_virtualized']
        self.assertEqual(
            self.distribution.main_archive.require_virtualized,
            widget._getCurrentValue())

    def test_edit_distro_init_value_enabled_restricted_processors(self):
        self.distribution.main_archive.enabled_restricted_processors = (
            self.restricted_processors)
        view = create_initialized_view(
            self.distribution, '+edit', principal=self.admin,
            method='GET')

        widget = view.widgets['enabled_restricted_processors']
        self.assertContentEqual(
            self.restricted_processors, widget._getCurrentValue())
        self.assertContentEqual(
            self.restricted_processors,
            [item.value for item in widget.vocabulary])

    def getDefaultEditDict(self):
        return {
            'field.displayname': 'newbuntu',
            'field.title': 'newbuntu',
            'field.summary': 'newbuntu',
            'field.description': 'newbuntu',
            'field.require_virtualized.used': u'',
            'field.enabled_restricted_processors': [processor.name
                for processor in self.restricted_processors],
            'field.actions.change': 'Change',
            }

    def test_change_require_virtualized(self):
        edit_form = self.getDefaultEditDict()
        edit_form['field.require_virtualized'] = 'on'

        self.distribution.main_archive.require_virtualized = False
        create_initialized_view(
            self.distribution, '+edit', principal=self.admin,
            method='POST', form=edit_form)
        self.assertEqual(
            True,
            self.distribution.main_archive.require_virtualized)

    def test_change_enabled_restricted_processors(self):
        edit_form = self.getDefaultEditDict()
        edit_form['field.enabled_restricted_processors'] = []

        self.distribution.main_archive.enabled_restricted_processors = (
            self.restricted_processors)
        create_initialized_view(
            self.distribution, '+edit', principal=self.admin,
            method='POST', form=edit_form)

        self.assertContentEqual(
            [], self.distribution.main_archive.enabled_restricted_processors)

    def test_package_derivatives_email(self):
        # Test that the edit form allows changing package_derivatives_email
        edit_form = self.getDefaultEditDict()
        email = '{package_name}_thing@foo.com'
        edit_form['field.package_derivatives_email'] = email

        create_initialized_view(
            self.distribution, '+edit', principal=self.distribution.owner,
            method="POST", form=edit_form)
        self.assertEqual(self.distribution.package_derivatives_email, email)


class TestDistroReassignView(TestCaseWithFactory):
    """Test the +reassign page for a new distribution."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestDistroReassignView, self).setUp()
        self.owner = self.factory.makePerson()
        self.registrant = self.factory.makePerson()
        self.simple_user = self.factory.makePerson()

    def test_reassign_distro_change_owner_not_registrant(self):
        # Reassigning a distribution should not change the registrant.
        admin = login_celebrity('admin')
        distribution = self.factory.makeDistribution(
            name="boobuntu", owner=self.owner, registrant=self.registrant)
        reassign_form = {
            'field.owner': self.simple_user.name,
            'field.existing': 'existing',
            'field.actions.change': 'Change',
            }
        create_initialized_view(
            distribution, '+reassign', principal=admin,
            method='POST', form=reassign_form)
        self.assertEqual(distribution.owner, self.simple_user)
        self.assertEqual(distribution.registrant, self.registrant)

    def test_reassign_distro_page_title(self):
        # Reassign should say maintainer instead of owner.
        admin = login_celebrity('admin')
        distribution = self.factory.makeDistribution(
            name="boobuntu", owner=self.owner, registrant=self.registrant)
        view = create_initialized_view(
            distribution, '+reassign', principal=admin, method='GET')
        header_match = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                'Header should say maintainer (not owner)', 'h1',
                text='Change the maintainer of Boobuntu'))
        self.assertThat(view.render(), header_match)
