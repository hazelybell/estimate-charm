# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.code.model.branch import Branch
from lp.registry.interfaces.accesspolicy import IAccessPolicySource
from lp.services.database.interfaces import IStore
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


class TestBranchAccessPolicyTriggers(TestCaseWithFactory):
    layer = DatabaseFunctionalLayer

    def fetchPolicies(self, branch):
        # We may be dealing with private branches, so just ignore security.
        return IStore(Branch).execute(
            "SELECT access_policy, access_grants FROM branch WHERE id = ?",
            (removeSecurityProxy(branch).id,)).get_one()

    def assertAccess(self, branch, expected_policy, expected_grants):
        policy, grants = self.fetchPolicies(branch)
        self.assertEqual(expected_policy, policy)
        self.assertEqual(expected_grants, grants)

    def test_no_access_policy_for_public_branches(self):
        # A public branch has no access policy or grants.
        self.assertAccess(self.factory.makeBranch(), None, None)

    def test_adding_aag_with_private_branch(self):
        # Adding a new AAG updates the branch columns via trigger.
        owner = self.factory.makePerson()
        branch = self.factory.makeBranch(
            information_type=InformationType.USERDATA, owner=owner)
        [ap] = getUtility(IAccessPolicySource).find(
            [(removeSecurityProxy(branch).product, InformationType.USERDATA)])
        self.assertAccess(branch, ap.id, [owner.id])
        artifact = self.factory.makeAccessArtifact(concrete=branch)
        grant = self.factory.makeAccessArtifactGrant(artifact=artifact)
        self.assertAccess(branch, ap.id, [owner.id, grant.grantee.id])
