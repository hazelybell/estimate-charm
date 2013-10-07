# Copyright 2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.blueprints.model.specification import Specification
from lp.registry.interfaces.accesspolicy import IAccessPolicySource
from lp.services.database.interfaces import IStore
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


class TestSpecificationAccessPolicyTriggers(TestCaseWithFactory):
    layer = DatabaseFunctionalLayer

    def fetchPolicies(self, specification):
        # We may be dealing with private specs, so just ignore security.
        return IStore(Specification).execute(
            "SELECT access_policy, access_grants FROM specification WHERE "
            "id = ?", (removeSecurityProxy(specification).id,)).get_one()

    def assertAccess(self, specification, expected_policy, expected_grants):
        policy, grants = self.fetchPolicies(specification)
        self.assertEqual(expected_policy, policy)
        self.assertEqual(expected_grants, grants)

    def test_no_access_policy_for_public_specifications(self):
        # A public specification has no access policy or grants.
        self.assertAccess(self.factory.makeSpecification(), None, None)

    def test_adding_aag_with_private_specification(self):
        # Adding a new AAG updates the specification columns via trigger.
        owner = self.factory.makePerson()
        specification = self.factory.makeSpecification(
            information_type=InformationType.PROPRIETARY, owner=owner)
        [ap] = getUtility(IAccessPolicySource).find(
            [(removeSecurityProxy(specification).product,
            InformationType.PROPRIETARY)])
        self.assertAccess(specification, ap.id, [])
        artifact = self.factory.makeAccessArtifact(concrete=specification)
        grant = self.factory.makeAccessArtifactGrant(artifact=artifact)
        self.assertAccess(specification, ap.id, [grant.grantee.id])
