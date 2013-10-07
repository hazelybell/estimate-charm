# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for classes that implement IHasMergeProposals."""

__metaclass__ = type

from zope.interface.verify import verifyObject

from lp.code.interfaces.hasbranches import IHasMergeProposals
from lp.registry.model.personproduct import PersonProduct
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


class TestIHasMergeProposals(TestCaseWithFactory):
    """Test that the correct objects implement the interface."""

    layer = DatabaseFunctionalLayer

    def test_product_implements_hasmergeproposals(self):
        # Products should implement IHasMergeProposals.
        product = self.factory.makeProduct()
        self.assertProvides(product, IHasMergeProposals)

    def test_person_implements_hasmergeproposals(self):
        # People should implement IHasMergeProposals.
        person = self.factory.makePerson()
        self.assertProvides(person, IHasMergeProposals)

    def test_project_implements_hasmergeproposals(self):
        # ProjectGroups should implement IHasMergeProposals.
        project = self.factory.makeProject()
        self.assertProvides(project, IHasMergeProposals)

    def test_PersonProduct_implements_hasmergeproposals(self):
        # PersonProducts should implement IHasMergeProposals.
        product = self.factory.makeProduct()
        person_product = PersonProduct(product.owner, product)
        verifyObject(IHasMergeProposals, person_product)

    def test_DistributionSourcePackage_implements_hasmergeproposals(self):
        # DistributionSourcePackages should implement IHasMergeProposals.
        dsp = self.factory.makeDistributionSourcePackage()
        verifyObject(IHasMergeProposals, dsp)
