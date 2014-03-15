# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test for components and component groups (products) in bug trackers."""

__metaclass__ = type

__all__ = []

import transaction

from lp.testing import (
    login_person,
    TestCaseWithFactory,
    ws_object,
    )
from lp.testing.layers import (
    AppServerLayer,
    DatabaseFunctionalLayer,
    )


class BugTrackerComponentTestCase(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(BugTrackerComponentTestCase, self).setUp()

        regular_user = self.factory.makePerson()
        login_person(regular_user)

        self.bug_tracker = self.factory.makeBugTracker()

        self.comp_group = self.factory.makeBugTrackerComponentGroup(
            u'alpha',
            self.bug_tracker)

    def test_component_creation(self):
        """Verify a component can be created"""
        component = self.factory.makeBugTrackerComponent(
            u'example', self.comp_group)
        self.assertIsNot(None, component)
        self.assertEqual(component.name, u'example')

    def test_set_visibility(self):
        """Users can delete components

        In case invalid components get imported from a remote bug
        tracker, users can hide them so they don't show up in the UI.
        We do this rather than delete them outright so that they won't
        show up again when we re-sync from the remote bug tracker.
        """
        component = self.factory.makeBugTrackerComponent(
            u'example', self.comp_group)
        self.assertEqual(component.is_visible, True)

        component.is_visible = False
        self.assertEqual(component.is_visible, False)

        component.is_visible = True
        self.assertEqual(component.is_visible, True)

    def test_custom_component(self):
        """Users can also add components

        For whatever reason, it may be that we can't import a component
        from the remote bug tracker.  This gives users a way to correct
        the omissions."""
        custom_component = self.factory.makeBugTrackerComponent(
            u'example', self.comp_group, custom=True)
        self.assertIsNot(None, custom_component)
        self.assertEqual(custom_component.is_custom, True)

    def test_multiple_component_creation(self):
        """Verify several components can be created at once"""
        comp_a = self.factory.makeBugTrackerComponent(
            u'example-a', self.comp_group)
        comp_b = self.factory.makeBugTrackerComponent(
            u'example-b', self.comp_group)
        comp_c = self.factory.makeBugTrackerComponent(
            u'example-c', self.comp_group, True)

        self.assertIsNot(None, comp_a)
        self.assertIsNot(None, comp_b)
        self.assertIsNot(None, comp_c)

    def test_link_distro_source_package(self):
        """Check that a link can be set to a distro source package"""
        example_component = self.factory.makeBugTrackerComponent(
            u'example', self.comp_group)
        dsp = self.factory.makeDistributionSourcePackage(u'example')

        example_component.distro_source_package = dsp
        self.assertEqual(dsp, example_component.distro_source_package)
        comp = self.bug_tracker.getRemoteComponentForDistroSourcePackageName(
            dsp.distribution, dsp.sourcepackagename)
        self.assertIsNot(example_component, comp)


class TestBugTrackerWithComponents(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBugTrackerWithComponents, self).setUp()

        regular_user = self.factory.makePerson()
        login_person(regular_user)

        self.bug_tracker = self.factory.makeBugTracker()

    def test_empty_bugtracker(self):
        """Trivial case of bugtracker with no products or components"""
        self.assertTrue(self.bug_tracker is not None)

        # Empty bugtrackers shouldn't return component groups
        comp_group = self.bug_tracker.getRemoteComponentGroup(u'non-existant')
        self.assertEqual(comp_group, None)

        # Verify it contains no component groups
        comp_groups = self.bug_tracker.getAllRemoteComponentGroups()
        self.assertEqual(len(list(comp_groups)), 0)

    def test_single_product_bugtracker(self):
        """Bug tracker with a single (default) product and several components
        """
        # Add a component group and fill it with some components
        default_comp_group = self.bug_tracker.addRemoteComponentGroup(
            u'alpha')
        default_comp_group.addComponent(u'example-a')
        default_comp_group.addComponent(u'example-b')
        default_comp_group.addComponent(u'example-c')

        # Verify that retrieving an invalid component group returns nothing
        comp_group = self.bug_tracker.getRemoteComponentGroup(u'non-existant')
        self.assertEqual(comp_group, None)

        # Now retrieve the component group we added
        comp_group = self.bug_tracker.getRemoteComponentGroup(u'alpha')
        self.assertEqual(comp_group, default_comp_group)
        self.assertEqual(comp_group.name, u'alpha')

        # Verify there is only the one component group in the tracker
        comp_groups = self.bug_tracker.getAllRemoteComponentGroups()
        self.assertEqual(len(list(comp_groups)), 1)

    def test_multiple_product_bugtracker(self):
        """Bug tracker with multiple products and components"""
        # Create several component groups with varying numbers of components
        self.bug_tracker.addRemoteComponentGroup(u'alpha')

        comp_group_ii = self.bug_tracker.addRemoteComponentGroup(u'beta')
        comp_group_ii.addComponent(u'example-beta-1')

        comp_group_iii = self.bug_tracker.addRemoteComponentGroup(u'gamma')
        comp_group_iii.addComponent(u'example-gamma-1')
        comp_group_iii.addComponent(u'example-gamma-2')
        comp_group_iii.addComponent(u'example-gamma-3')

        # Retrieving a non-existant component group returns nothing
        comp_group = self.bug_tracker.getRemoteComponentGroup(u'non-existant')
        self.assertEqual(comp_group, None)

        # Now retrieve one of the real component groups
        comp_group = self.bug_tracker.getRemoteComponentGroup(u'beta')
        self.assertEqual(comp_group, comp_group_ii)

        # Check the correct number of component groups are in the bug tracker
        comp_groups = self.bug_tracker.getAllRemoteComponentGroups()
        self.assertEqual(len(list(comp_groups)), 3)

    def test_get_components_for_component_group(self):
        """Retrieve a set of components from a given product"""
        # Create a component group with some components
        default_comp_group = self.bug_tracker.addRemoteComponentGroup(
            u'alpha')
        default_comp_group.addComponent(u'example-a')
        default_comp_group.addComponent(u'example-b')
        default_comp_group.addComponent(u'example-c')

        # Verify group has the correct number of components
        comp_group = self.bug_tracker.getRemoteComponentGroup(u'alpha')
        self.assertEqual(len(list(comp_group.components)), 3)

        # Check one of the components, that it is what we expect
        comp = comp_group.getComponent(u'example-b')
        self.assertEqual(comp.name, u'example-b')


class TestWebservice(TestCaseWithFactory):

    layer = AppServerLayer

    def setUp(self):
        super(TestWebservice, self).setUp()

        regular_user = self.factory.makePerson()
        login_person(regular_user)

        self.bug_tracker = self.factory.makeBugTracker()
        self.launchpad = self.factory.makeLaunchpadService()

    def test_get_bug_tracker(self):
        """Check that bug tracker can be retrieved"""
        bug_tracker = ws_object(self.launchpad, self.bug_tracker)
        self.assertIsNot(None, bug_tracker)

    def test_bug_tracker_with_no_component_groups(self):
        """Initially, the bug tracker has no component groups"""
        bug_tracker = ws_object(self.launchpad, self.bug_tracker)
        comp_groups = bug_tracker.getAllRemoteComponentGroups()
        self.assertEqual(0, len(list(comp_groups)))

    def test_retrieve_component_group_from_bug_tracker(self):
        """Looks up specific component group in bug tracker"""
        self.bug_tracker.addRemoteComponentGroup(u'alpha')

        bug_tracker = ws_object(self.launchpad, self.bug_tracker)
        comp_group = bug_tracker.getRemoteComponentGroup(
            component_group_name=u'alpha')
        self.assertIsNot(None, comp_group)

    def test_list_component_groups_for_bug_tracker(self):
        """Retrieve the component groups for a bug tracker"""
        self.bug_tracker.addRemoteComponentGroup(u'alpha')
        self.bug_tracker.addRemoteComponentGroup(u'beta')

        bug_tracker = ws_object(self.launchpad, self.bug_tracker)
        comp_groups = bug_tracker.getAllRemoteComponentGroups()
        self.assertEqual(2, len(list(comp_groups)))

    def test_list_components_for_component_group(self):
        """Retrieve the components for a given group"""
        db_comp_group_alpha = self.bug_tracker.addRemoteComponentGroup(
            u'alpha')
        db_comp_group_alpha.addComponent(u'1')
        db_comp_group_alpha.addComponent(u'2')
        transaction.commit()

        comp_group = ws_object(self.launchpad, db_comp_group_alpha)
        self.assertEqual(2, len(comp_group.components))

    def test_add_component(self):
        """Add a custom (local) component to the component group"""
        db_comp_group = self.bug_tracker.addRemoteComponentGroup(
            u'alpha')
        comp_group = ws_object(self.launchpad, db_comp_group)
        comp_group.addComponent(component_name=u'c')
        self.assertEqual(1, len(comp_group.components))

    def test_remove_component(self):
        """Make a component not visible in the UI"""
        db_comp = self.factory.makeBugTrackerComponent()
        transaction.commit()

        comp = ws_object(self.launchpad, db_comp)
        self.assertTrue(comp.is_visible)
        comp.is_visible = False
        self.assertFalse(comp.is_visible)

    def test_get_linked_source_package(self):
        """Already linked source packages can be seen from the component"""
        db_src_pkg = self.factory.makeDistributionSourcePackage()
        db_comp = self.factory.makeBugTrackerComponent()
        db_comp.distro_source_package = db_src_pkg
        transaction.commit()

        comp = ws_object(self.launchpad, db_comp)
        self.assertIsNot(None, comp.distro_source_package)

    def test_link_source_package(self):
        """Link a component to a given source package"""
        db_src_pkg = self.factory.makeDistributionSourcePackage()
        db_comp = self.factory.makeBugTrackerComponent()
        transaction.commit()

        comp = ws_object(self.launchpad, db_comp)
        src_pkg = ws_object(self.launchpad, db_src_pkg)
        self.assertIs(None, comp.distro_source_package)
        comp.distro_source_package = src_pkg
        self.assertIsNot(None, comp.distro_source_package)

    def test_relink_same_source_package(self):
        """Attempts to re-link the same source package should not error"""
        db_src_pkg = self.factory.makeDistributionSourcePackage()
        db_comp = self.factory.makeBugTrackerComponent()
        db_comp.distro_source_package = db_src_pkg
        transaction.commit()

        component = ws_object(self.launchpad, db_comp)
        package = ws_object(self.launchpad, db_src_pkg)
        component.distro_source_package = package
