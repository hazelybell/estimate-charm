# Copyright 2010-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for objects implementing IHasSpecifications."""

__metaclass__ = type

from lp.blueprints.enums import SpecificationDefinitionStatus
from lp.blueprints.interfaces.specificationtarget import IHasSpecifications
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.matchers import DoesNotSnapshot


class HasSpecificationsTests(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def assertNamesOfSpecificationsAre(self, expected_names, specifications):
        names = [s.name for s in specifications]
        self.assertContentEqual(expected_names, names)

    def test_product_all_specifications(self):
        product = self.factory.makeProduct()
        self.factory.makeSpecification(product=product, name="spec1")
        self.factory.makeSpecification(product=product, name="spec2")
        self.assertNamesOfSpecificationsAre(
            ["spec1", "spec2"], product.visible_specifications)

    def test_product_valid_specifications(self):
        product = self.factory.makeProduct()
        self.factory.makeSpecification(product=product, name="spec1")
        self.factory.makeSpecification(
            product=product, name="spec2",
            status=SpecificationDefinitionStatus.OBSOLETE)
        self.assertNamesOfSpecificationsAre(
            ["spec1"], product.valid_specifications())

    def test_distribution_all_specifications(self):
        distribution = self.factory.makeDistribution()
        self.factory.makeSpecification(distribution=distribution, name="spec1")
        self.factory.makeSpecification(distribution=distribution, name="spec2")
        self.assertNamesOfSpecificationsAre(
            ["spec1", "spec2"], distribution.visible_specifications)

    def test_distribution_valid_specifications(self):
        distribution = self.factory.makeDistribution()
        self.factory.makeSpecification(distribution=distribution, name="spec1")
        self.factory.makeSpecification(
            distribution=distribution, name="spec2",
            status=SpecificationDefinitionStatus.OBSOLETE)
        self.assertNamesOfSpecificationsAre(
            ["spec1"], distribution.valid_specifications())

    def test_distroseries_all_specifications(self):
        distroseries = self.factory.makeDistroSeries(name='maudlin')
        distribution = distroseries.distribution
        self.factory.makeSpecification(
            distribution=distribution, name="spec1", goal=distroseries)
        self.factory.makeSpecification(
            distribution=distribution, name="spec2", goal=distroseries)
        self.factory.makeSpecification(distribution=distribution, name="spec3")
        self.assertNamesOfSpecificationsAre(
            ["spec1", "spec2"], distroseries.visible_specifications)

    def test_distroseries_valid_specifications(self):
        distroseries = self.factory.makeDistroSeries(name='maudlin')
        distribution = distroseries.distribution
        self.factory.makeSpecification(
            distribution=distribution, name="spec1", goal=distroseries)
        self.factory.makeSpecification(
            distribution=distribution, name="spec2", goal=distroseries)
        self.factory.makeSpecification(
            distribution=distribution, name="spec3", goal=distroseries,
            status=SpecificationDefinitionStatus.OBSOLETE)
        self.factory.makeSpecification(distribution=distribution, name="spec4")
        self.assertNamesOfSpecificationsAre(
            ["spec1", "spec2"], distroseries.valid_specifications())

    def test_productseries_all_specifications(self):
        product = self.factory.makeProduct()
        productseries = self.factory.makeProductSeries(
            product=product, name="fooix-dev")
        self.factory.makeSpecification(
            product=product, name="spec1", goal=productseries)
        self.factory.makeSpecification(
            product=product, name="spec2", goal=productseries)
        self.factory.makeSpecification(product=product, name="spec3")
        self.assertNamesOfSpecificationsAre(
            ["spec1", "spec2"], productseries.visible_specifications)

    def test_productseries_valid_specifications(self):
        product = self.factory.makeProduct()
        productseries = self.factory.makeProductSeries(
            product=product, name="fooix-dev")
        self.factory.makeSpecification(
            product=product, name="spec1", goal=productseries)
        self.factory.makeSpecification(
            product=product, name="spec2", goal=productseries)
        self.factory.makeSpecification(
            product=product, name="spec3", goal=productseries,
            status=SpecificationDefinitionStatus.OBSOLETE)
        self.factory.makeSpecification(product=product, name="spec4")
        self.assertNamesOfSpecificationsAre(
            ["spec1", "spec2"], productseries.valid_specifications())

    def test_projectgroup_all_specifications(self):
        projectgroup = self.factory.makeProject()
        other_projectgroup = self.factory.makeProject()
        product1 = self.factory.makeProduct(project=projectgroup)
        product2 = self.factory.makeProduct(project=projectgroup)
        product3 = self.factory.makeProduct(project=other_projectgroup)
        self.factory.makeSpecification(product=product1, name="spec1")
        self.factory.makeSpecification(
            product=product2, name="spec2",
            status=SpecificationDefinitionStatus.OBSOLETE)
        self.factory.makeSpecification(product=product3, name="spec3")
        self.assertNamesOfSpecificationsAre(
            ["spec1", "spec2"], projectgroup.visible_specifications)

    def test_projectgroup_valid_specifications(self):
        projectgroup = self.factory.makeProject()
        other_projectgroup = self.factory.makeProject()
        product1 = self.factory.makeProduct(project=projectgroup)
        product2 = self.factory.makeProduct(project=projectgroup)
        product3 = self.factory.makeProduct(project=other_projectgroup)
        self.factory.makeSpecification(product=product1, name="spec1")
        self.factory.makeSpecification(
            product=product2, name="spec2",
            status=SpecificationDefinitionStatus.OBSOLETE)
        self.factory.makeSpecification(product=product3, name="spec3")
        self.assertNamesOfSpecificationsAre(
            ["spec1"], projectgroup.valid_specifications())

    def test_person_all_specifications(self):
        person = self.factory.makePerson(name="james-w")
        product = self.factory.makeProduct()
        self.factory.makeSpecification(
            product=product, name="spec1", drafter=person)
        self.factory.makeSpecification(
            product=product, name="spec2", approver=person,
            status=SpecificationDefinitionStatus.OBSOLETE)
        self.factory.makeSpecification(product=product, name="spec3")
        self.assertNamesOfSpecificationsAre(
            ["spec1", "spec2"], person.visible_specifications)

    def test_person_valid_specifications(self):
        person = self.factory.makePerson(name="james-w")
        product = self.factory.makeProduct()
        self.factory.makeSpecification(
            product=product, name="spec1", drafter=person)
        self.factory.makeSpecification(
            product=product, name="spec2", approver=person,
            status=SpecificationDefinitionStatus.OBSOLETE)
        self.factory.makeSpecification(product=product, name="spec3")
        self.assertNamesOfSpecificationsAre(
            ["spec1"], person.valid_specifications())


class HasSpecificationsSnapshotTestCase(TestCaseWithFactory):
    """A TestCase for snapshots of specification targets."""

    layer = DatabaseFunctionalLayer

    def check_skipped(self, target):
        """Asserts that fields marked doNotSnapshot are skipped."""
        skipped = ['all_specifications', 'valid_specifications']
        self.assertThat(target, DoesNotSnapshot(skipped, IHasSpecifications))

    def test_product(self):
        product = self.factory.makeProduct()
        self.check_skipped(product)

    def test_distribution(self):
        distribution = self.factory.makeDistribution()
        self.check_skipped(distribution)

    def test_productseries(self):
        productseries = self.factory.makeProductSeries()
        self.check_skipped(productseries)

    def test_distroseries(self):
        distroseries = self.factory.makeDistroSeries()
        self.check_skipped(distroseries)

    def test_projectgroup(self):
        projectgroup = self.factory.makeProject()
        self.check_skipped(projectgroup)
