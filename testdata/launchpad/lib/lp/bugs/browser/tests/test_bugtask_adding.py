# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type


from zope.component import getUtility

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.registry.interfaces.packaging import (
    IPackagingUtil,
    PackagingType,
    )
from lp.testing import (
    login_person,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.views import create_initialized_view


class TestProductBugTaskCreationStep(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestProductBugTaskCreationStep, self).setUp()
        ubuntu = getUtility(ILaunchpadCelebrities).ubuntu
        self.ubuntu_series = ubuntu['hoary']
        self.sourcepackagename = self.factory.makeSourcePackageName('bat')
        self.sourcepackage = self.factory.makeSourcePackage(
            sourcepackagename=self.sourcepackagename,
            distroseries=self.ubuntu_series)
        self.dsp = self.factory.makeDistributionSourcePackage(
            sourcepackagename=self.sourcepackagename, distribution=ubuntu)
        self.factory.makeSourcePackagePublishingHistory(
            sourcepackagename=self.sourcepackagename,
            distroseries=self.ubuntu_series)
        self.product = self.factory.makeProduct(name="bat")
        self.packaging_util = getUtility(IPackagingUtil)
        self.user = self.factory.makePerson()
        login_person(self.user)
        self.bug_task = self.factory.makeBugTask(
            target=self.dsp, owner=self.user)
        self.bug = self.bug_task.bug

    def test_choose_product_when_packaging_does_not_exist(self):
        # Verify the view is on the first step and that it includes the
        # add_packaging field.
        view = create_initialized_view(
            self.bug_task, '+choose-affected-product')
        self.assertEqual('choose_product', view.view.step_name)
        self.assertEqual(
            ['product', 'add_packaging', '__visited_steps__'],
            view.view.field_names)

    def test_choose_product_when_packaging_does_exist(self):
        # Verify the view is on the second step and that the add_packaging
        # field was set to False.
        self.packaging_util.createPackaging(
            self.product.development_focus, self.sourcepackagename,
            self.ubuntu_series, PackagingType.PRIME, self.user)
        view = create_initialized_view(
            self.bug_task, '+choose-affected-product')
        self.assertEqual('specify_remote_bug_url', view.view.step_name)
        field_names = [
            'link_upstream_how', 'upstream_email_address_done', 'bug_url',
            'product', 'add_packaging', '__visited_steps__']
        self.assertEqual(field_names, view.view.field_names)
        add_packaging_field = view.view.widgets['add_packaging']
        self.assertEqual(False, add_packaging_field.getInputValue())

    def test_rechoose_product_when_packaging_does_exist(self):
        # Verify the user can rechoose the product (the first step) and that
        # the add_packaging field is not included when the package is linked.
        self.packaging_util.createPackaging(
            self.product.development_focus, self.sourcepackagename,
            self.ubuntu_series, PackagingType.PRIME, self.user)
        form = {'field.product': 'bat'}
        view = create_initialized_view(
            self.bug_task, '+choose-affected-product', form=form)
        self.assertEqual('choose_product', view.view.step_name)
        field_names = ['product', '__visited_steps__']
        self.assertEqual(field_names, view.view.field_names)

    def test_create_upstream_bugtask_without_packaging(self):
        # Verify that the project has a new bugtask and no packaging link.
        form = {
            'field.product': 'bat',
            'field.add_packaging': 'off',
            'field.__visited_steps__':
                'choose_product|specify_remote_bug_url',
            'field.actions.continue': 'Continue',
            }
        view = create_initialized_view(
            self.bug_task, '+choose-affected-product', form=form)
        self.assertEqual([], view.view.errors)
        self.assertTrue(self.bug.getBugTask(self.product) is not None)
        has_packaging = self.packaging_util.packagingEntryExists(
            self.sourcepackagename, self.ubuntu_series,
            self.product.development_focus)
        self.assertFalse(has_packaging)

    def test_create_upstream_bugtask_with_packaging(self):
        # Verify that the project has a new bugtask and packaging link.
        form = {
            'field.product': 'bat',
            'field.add_packaging': 'on',
            'field.__visited_steps__':
                'choose_product|specify_remote_bug_url',
            'field.actions.continue': 'Continue',
            }
        view = create_initialized_view(
            self.bug_task, '+choose-affected-product', form=form)
        self.assertEqual([], view.view.errors)
        self.assertTrue(self.bug.getBugTask(self.product) is not None)
        has_packaging = self.packaging_util.packagingEntryExists(
            self.sourcepackagename, self.ubuntu_series,
            self.product.development_focus)
        self.assertTrue(has_packaging)

    def test_register_product_fields_packaging_exists(self):
        # The view includes the add_packaging field.
        view = create_initialized_view(
            self.bug_task, '+affects-new-product')
        self.assertEqual(
            ['bug_url', 'displayname', 'name', 'summary', 'add_packaging'],
            view.field_names)

    def test_register_product_fields_packaging_does_not_exist(self):
        # The view does not include the add_packaging field.
        self.packaging_util.createPackaging(
            self.product.development_focus, self.sourcepackagename,
            self.ubuntu_series, PackagingType.PRIME,
            self.user)
        view = create_initialized_view(
            self.bug_task, '+affects-new-product')
        self.assertEqual(
            ['bug_url', 'displayname', 'name', 'summary'],
             view.field_names)

    def test_register_project_create_upstream_bugtask_with_packaging(self):
        # Verify the new project has a bug task and packaging link.
        form = {
            'field.bug_url': 'http://bugs.foo.org/bugs/show_bug.cgi?id=8',
            'field.name': 'fruit',
            'field.displayname': 'Fruit',
            'field.summary': 'The Fruit summary',
            'field.add_packaging': 'on',
            'field.actions.continue': 'Continue',
            }
        view = create_initialized_view(
            self.bug_task, '+affects-new-product', form=form)
        self.assertEqual([], view.errors)
        targets = [bugtask.target for bugtask in self.bug.bugtasks
                   if bugtask.target.name == 'fruit']
        self.assertEqual(1, len(targets))
        product = targets[0]
        has_packaging = self.packaging_util.packagingEntryExists(
            self.sourcepackagename, self.ubuntu_series,
            product.development_focus)
        self.assertTrue(has_packaging)

    def test_register_project_create_upstream_bugtask_no_series(self):
        # Adding a task that affects a product where the distribution has
        # no series does not error.
        dsp = self.factory.makeDistributionSourcePackage(
            sourcepackagename=self.sourcepackagename)
        self.bug_task = self.factory.makeBugTask(
            target=dsp, owner=self.user)
        form = {
            'field.bug_url': 'http://bugs.foo.org/bugs/show_bug.cgi?id=8',
            'field.name': 'fruit',
            'field.displayname': 'Fruit',
            'field.summary': 'The Fruit summary',
            'field.add_packaging': 'on',
            'field.actions.continue': 'Continue',
            }
        view = create_initialized_view(
            self.bug_task, '+affects-new-product', form=form)
        self.assertEqual([], view.errors)
