# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the specification dependency views.

There are also tests in lp/blueprints/stories/blueprints/xx-dependencies.txt.
"""

__metaclass__ = type

from lp.app.enums import InformationType
from lp.registry.enums import SpecificationSharingPolicy
from lp.services.webapp import canonical_url
from lp.testing import (
    anonymous_logged_in,
    BrowserTestCase,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.views import create_view


class TestAddDependency(BrowserTestCase):

    layer = DatabaseFunctionalLayer

    def test_add_dependency_by_url(self):
        # It is possible to use the URL of a specification in the "Depends On"
        # field of the form to add a dependency to a spec.
        spec = self.factory.makeSpecification(owner=self.user)
        dependency = self.factory.makeSpecification()
        dependency_url = canonical_url(dependency)
        browser = self.getViewBrowser(spec, '+linkdependency')
        browser.getControl('Depends On').value = dependency_url
        browser.getControl('Continue').click()
        # click() above issues a request, and
        # ZopePublication.endRequest() calls
        # zope.security.management.endInteraction().
        # We need a new interaction for the permission checks
        # on ISpecification objects.
        with person_logged_in(None):
            self.assertIn(dependency, spec.getDependencies())


class TestDepTree(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_deptree_filters_dependencies(self):
        # dep tree's blocked_specs and dependencies attributes filter
        # blueprints the user can't see.
        sharing_policy = SpecificationSharingPolicy.PUBLIC_OR_PROPRIETARY
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(
            owner=owner, specification_sharing_policy=sharing_policy)
        root = self.factory.makeBlueprint(product=product)
        proprietary_dep = self.factory.makeBlueprint(
            product=product, information_type=InformationType.PROPRIETARY)
        public_dep = self.factory.makeBlueprint(product=product)
        root.createDependency(proprietary_dep)
        root.createDependency(public_dep)

        # Anonymous can see only the public
        with anonymous_logged_in():
            view = create_view(root, name="+deptree")
            self.assertEqual([public_dep], view.all_deps)
            self.assertEqual([public_dep], view.dependencies)

        # The owner can see everything.
        with person_logged_in(owner):
            view = create_view(root, name="+deptree")
            self.assertEqual(
                [proprietary_dep, public_dep], view.all_deps)
            self.assertEqual(
                [proprietary_dep, public_dep], view.dependencies)

        # A random person cannot see the propriety dep.
        with person_logged_in(self.factory.makePerson()):
            view = create_view(root, name="+deptree")
            self.assertEqual([public_dep], view.all_deps)
            self.assertEqual([public_dep], view.dependencies)

    def test_deptree_filters_blocked(self):
        # dep tree's blocked_specs and dependencies attributes filter
        # blueprints the user can't see.
        sharing_policy = SpecificationSharingPolicy.PUBLIC_OR_PROPRIETARY
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(
            owner=owner, specification_sharing_policy=sharing_policy)
        root = self.factory.makeBlueprint(product=product)
        proprietary_blocked = self.factory.makeBlueprint(
            product=product, information_type=InformationType.PROPRIETARY)
        public_blocked = self.factory.makeBlueprint(product=product)
        proprietary_blocked.createDependency(root)
        public_blocked.createDependency(root)

        # Anonymous can see only the public
        with anonymous_logged_in():
            view = create_view(root, name="+deptree")
            self.assertEqual([public_blocked], view.all_blocked)
            self.assertEqual([public_blocked], view.blocked_specs)

        # The owner can see everything.
        with person_logged_in(owner):
            view = create_view(root, name="+deptree")
            self.assertEqual(
                [proprietary_blocked, public_blocked], view.all_blocked)
            self.assertEqual(
                [proprietary_blocked, public_blocked], view.blocked_specs)

        # A random person cannot see the propriety dep.
        with person_logged_in(self.factory.makePerson()):
            view = create_view(root, name="+deptree")
            self.assertEqual([public_blocked], view.all_blocked)
            self.assertEqual([public_blocked], view.blocked_specs)
