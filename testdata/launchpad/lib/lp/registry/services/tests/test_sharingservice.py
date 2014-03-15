# Copyright 2012-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type


from lazr.restful.interfaces import IWebBrowserOriginatingRequest
from lazr.restful.utils import get_current_web_service_request
from testtools.matchers import Equals
import transaction
from zope.component import getUtility
from zope.security.interfaces import Unauthorized
from zope.security.proxy import removeSecurityProxy
from zope.traversing.browser.absoluteurl import absoluteURL

from lp.app.enums import InformationType
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.app.interfaces.services import IService
from lp.blueprints.interfaces.specification import ISpecification
from lp.bugs.interfaces.bug import IBug
from lp.code.enums import (
    BranchSubscriptionNotificationLevel,
    CodeReviewNotificationLevel,
    )
from lp.code.interfaces.branch import IBranch
from lp.registry.enums import (
    BranchSharingPolicy,
    BugSharingPolicy,
    SharingPermission,
    SpecificationSharingPolicy,
    )
from lp.registry.interfaces.accesspolicy import (
    IAccessArtifactGrantSource,
    IAccessArtifactSource,
    IAccessPolicyGrantFlatSource,
    IAccessPolicyGrantSource,
    IAccessPolicySource,
    )
from lp.registry.interfaces.person import TeamMembershipPolicy
from lp.registry.interfaces.role import IPersonRoles
from lp.registry.services.sharingservice import SharingService
from lp.services.features.testing import FeatureFixture
from lp.services.job.tests import block_on_job
from lp.services.webapp.interaction import ANONYMOUS
from lp.services.webapp.interfaces import ILaunchpadRoot
from lp.services.webapp.publisher import canonical_url
from lp.testing import (
    admin_logged_in,
    login,
    login_person,
    person_logged_in,
    StormStatementRecorder,
    TestCaseWithFactory,
    WebServiceTestCase,
    ws_object,
    )
from lp.testing.layers import (
    AppServerLayer,
    CeleryJobLayer,
    )
from lp.testing.matchers import HasQueryCount
from lp.testing.pages import LaunchpadWebServiceCaller


class TestSharingService(TestCaseWithFactory):
    """Tests for the SharingService."""

    layer = CeleryJobLayer

    def setUp(self):
        super(TestSharingService, self).setUp()
        self.service = getUtility(IService, 'sharing')
        self.useFixture(FeatureFixture({
            'jobs.celery.enabled_classes': 'RemoveArtifactSubscriptionsJob',
        }))

    def _makeGranteeData(self, grantee, policy_permissions,
                        shared_artifact_types):
        # Unpack a grantee into its attributes and add in permissions.
        request = get_current_web_service_request()
        sprite_css = 'sprite ' + ('team' if grantee.is_team else 'person')
        if grantee.icon:
            icon_url = grantee.icon.getURL()
        else:
            icon_url = None
        grantee_data = {
            'name': grantee.name,
            'icon_url': icon_url,
            'sprite_css': sprite_css,
            'display_name': grantee.displayname,
            'self_link': absoluteURL(grantee, request),
            'permissions': {}}
        browser_request = IWebBrowserOriginatingRequest(request)
        grantee_data['web_link'] = absoluteURL(grantee, browser_request)
        shared_items_exist = False
        permissions = {}
        for (policy, permission) in policy_permissions:
            permissions[policy.name] = unicode(permission.name)
            if permission == SharingPermission.SOME:
                shared_items_exist = True
        grantee_data['shared_items_exist'] = shared_items_exist
        grantee_data['shared_artifact_types'] = [
            info_type.name for info_type in shared_artifact_types]
        grantee_data['permissions'] = permissions
        return grantee_data

    def test_getSharingPermissions(self):
        # test_getSharingPermissions returns permissions in the right order.
        permissions = self.service.getSharingPermissions()
        expected_permissions = [
            SharingPermission.ALL,
            SharingPermission.SOME,
            SharingPermission.NOTHING
        ]
        for x, permission in enumerate(expected_permissions):
            self.assertEqual(permissions[x]['value'], permission.name)

    def _assert_enumData(self, expected_enums, enum_data):
        expected_data = []
        for x, enum in enumerate(expected_enums):
            item = dict(
                index=x,
                value=enum.name,
                title=enum.title,
                description=enum.description
            )
            expected_data.append(item)
        self.assertContentEqual(expected_data, enum_data)

    def _assert_getAllowedInformationTypes(self, pillar,
                                           expected_policies):
        policy_data = self.service.getAllowedInformationTypes(pillar)
        self._assert_enumData(expected_policies, policy_data)

    def test_getInformationTypes_product(self):
        product = self.factory.makeProduct()
        self._assert_getAllowedInformationTypes(
            product,
            [InformationType.PRIVATESECURITY, InformationType.USERDATA])

    def test_getInformationTypes_expired_commercial_product(self):
        product = self.factory.makeProduct()
        self.factory.makeCommercialSubscription(product, expired=True)
        self._assert_getAllowedInformationTypes(
            product,
            [InformationType.PRIVATESECURITY, InformationType.USERDATA])

    def test_getInformationTypes_commercial_product(self):
        product = self.factory.makeProduct(
            branch_sharing_policy=BranchSharingPolicy.PROPRIETARY,
            bug_sharing_policy=BugSharingPolicy.PROPRIETARY)
        self._assert_getAllowedInformationTypes(
            product,
            [InformationType.PROPRIETARY])

    def test_getInformationTypes_product_with_embargoed(self):
        product = self.factory.makeProduct(
            branch_sharing_policy=BranchSharingPolicy.EMBARGOED_OR_PROPRIETARY,
            bug_sharing_policy=BugSharingPolicy.PROPRIETARY)
        self._assert_getAllowedInformationTypes(
            product,
            [InformationType.PROPRIETARY, InformationType.EMBARGOED])

    def test_getInformationTypes_distro(self):
        distro = self.factory.makeDistribution()
        self._assert_getAllowedInformationTypes(
            distro,
            [InformationType.PRIVATESECURITY, InformationType.USERDATA])

    def _assert_getBranchSharingPolicies(self, pillar, expected_policies):
        policy_data = self.service.getBranchSharingPolicies(pillar)
        self._assert_enumData(expected_policies, policy_data)

    def test_getBranchSharingPolicies_product(self):
        product = self.factory.makeProduct()
        self._assert_getBranchSharingPolicies(
            product, [BranchSharingPolicy.PUBLIC])

    def test_getBranchSharingPolicies_expired_commercial_product(self):
        product = self.factory.makeProduct()
        self.factory.makeCommercialSubscription(product, expired=True)
        self._assert_getBranchSharingPolicies(
            product, [BranchSharingPolicy.PUBLIC])

    def test_getBranchSharingPolicies_commercial_product(self):
        product = self.factory.makeProduct()
        self.factory.makeCommercialSubscription(product)
        self._assert_getBranchSharingPolicies(
            product,
            [BranchSharingPolicy.PUBLIC,
             BranchSharingPolicy.PUBLIC_OR_PROPRIETARY,
             BranchSharingPolicy.PROPRIETARY_OR_PUBLIC,
             BranchSharingPolicy.PROPRIETARY])

    def test_getBugSharingPolicies_non_public_product(self):
        # When the product is non-public the policy options are limited to
        # only proprietary or embargoed/proprietary.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(
            information_type=InformationType.PROPRIETARY,
            owner=owner,
        )
        with person_logged_in(owner):
            self._assert_getBugSharingPolicies(
                product, [BugSharingPolicy.EMBARGOED_OR_PROPRIETARY,
                          BugSharingPolicy.PROPRIETARY])

    def test_getBranchSharingPolicies_non_public_product(self):
        # When the product is non-public the policy options are limited to
        # only proprietary or embargoed/proprietary.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(
            information_type=InformationType.PROPRIETARY,
            owner=owner
        )
        with person_logged_in(owner):
            self._assert_getBranchSharingPolicies(
                product, [BranchSharingPolicy.EMBARGOED_OR_PROPRIETARY,
                          BranchSharingPolicy.PROPRIETARY])

    def test_getSpecificationSharingPolicies_non_public_product(self):
        # When the product is non-public the policy options are limited to
        # only proprietary or embargoed/proprietary.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(
            information_type=InformationType.PROPRIETARY,
            owner=owner,
        )
        with person_logged_in(owner):
            self._assert_getSpecificationSharingPolicies(
                product, [SpecificationSharingPolicy.EMBARGOED_OR_PROPRIETARY,
                          SpecificationSharingPolicy.PROPRIETARY])

    def test_getBranchSharingPolicies_disallowed_policy(self):
        # getBranchSharingPolicies includes a pillar's current policy even if
        # it is nominally not allowed.
        product = self.factory.makeProduct()
        self.factory.makeCommercialSubscription(product, expired=True)
        with person_logged_in(product.owner):
            product.setBranchSharingPolicy(BranchSharingPolicy.FORBIDDEN)
        self._assert_getBranchSharingPolicies(
            product,
            [BranchSharingPolicy.PUBLIC, BranchSharingPolicy.FORBIDDEN])

    def test_getBranchSharingPolicies_product_with_embargoed(self):
        # If the current sharing policy is embargoed, it can still be made
        # proprietary.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(
            information_type=InformationType.EMBARGOED,
            owner=owner,
            branch_sharing_policy=BranchSharingPolicy.EMBARGOED_OR_PROPRIETARY)
        with person_logged_in(owner):
            self._assert_getBranchSharingPolicies(
                product, [BranchSharingPolicy.EMBARGOED_OR_PROPRIETARY,
                          BranchSharingPolicy.PROPRIETARY])

    def test_getBranchSharingPolicies_distro(self):
        distro = self.factory.makeDistribution()
        self._assert_getBranchSharingPolicies(
            distro, [BranchSharingPolicy.PUBLIC])

    def _assert_getSpecificationSharingPolicies(
        self, pillar, expected_policies):
        policy_data = self.service.getSpecificationSharingPolicies(pillar)
        self._assert_enumData(expected_policies, policy_data)

    def test_getSpecificationSharingPolicies_product(self):
        product = self.factory.makeProduct()
        self._assert_getSpecificationSharingPolicies(
            product, [SpecificationSharingPolicy.PUBLIC])

    def test_getSpecificationSharingPolicies_expired_commercial_product(self):
        product = self.factory.makeProduct()
        self.factory.makeCommercialSubscription(product, expired=True)
        self._assert_getSpecificationSharingPolicies(
            product, [SpecificationSharingPolicy.PUBLIC])

    def test_getSpecificationSharingPolicies_commercial_product(self):
        product = self.factory.makeProduct()
        self.factory.makeCommercialSubscription(product)
        self._assert_getSpecificationSharingPolicies(
            product,
            [SpecificationSharingPolicy.PUBLIC,
             SpecificationSharingPolicy.PUBLIC_OR_PROPRIETARY,
             SpecificationSharingPolicy.PROPRIETARY_OR_PUBLIC,
             SpecificationSharingPolicy.PROPRIETARY])

    def test_getSpecificationSharingPolicies_product_with_embargoed(self):
        # The sharing policies will contain the product's sharing policy even
        # if it is not in the nominally allowed policy list.
        product = self.factory.makeProduct(
            specification_sharing_policy=(
                SpecificationSharingPolicy.EMBARGOED_OR_PROPRIETARY))
        self._assert_getSpecificationSharingPolicies(
            product,
            [SpecificationSharingPolicy.PUBLIC,
             SpecificationSharingPolicy.PUBLIC_OR_PROPRIETARY,
             SpecificationSharingPolicy.PROPRIETARY_OR_PUBLIC,
             SpecificationSharingPolicy.PROPRIETARY,
             SpecificationSharingPolicy.EMBARGOED_OR_PROPRIETARY])

    def test_getSpecificationSharingPolicies_distro(self):
        distro = self.factory.makeDistribution()
        self._assert_getSpecificationSharingPolicies(
            distro, [SpecificationSharingPolicy.PUBLIC])

    def _assert_getBugSharingPolicies(self, pillar, expected_policies):
        policy_data = self.service.getBugSharingPolicies(pillar)
        self._assert_enumData(expected_policies, policy_data)

    def test_getBugSharingPolicies_product(self):
        product = self.factory.makeProduct()
        self._assert_getBugSharingPolicies(product, [BugSharingPolicy.PUBLIC])

    def test_getBugSharingPolicies_expired_commercial_product(self):
        product = self.factory.makeProduct()
        self.factory.makeCommercialSubscription(product, expired=True)
        self._assert_getBugSharingPolicies(product, [BugSharingPolicy.PUBLIC])

    def test_getBugSharingPolicies_commercial_product(self):
        product = self.factory.makeProduct()
        self.factory.makeCommercialSubscription(product)
        self._assert_getBugSharingPolicies(
            product,
            [BugSharingPolicy.PUBLIC,
             BugSharingPolicy.PUBLIC_OR_PROPRIETARY,
             BugSharingPolicy.PROPRIETARY_OR_PUBLIC,
             BugSharingPolicy.PROPRIETARY])

    def test_getBugSharingPolicies_disallowed_policy(self):
        # getBugSharingPolicies includes a pillar's current policy even if it
        # is nominally not allowed.
        product = self.factory.makeProduct()
        self.factory.makeCommercialSubscription(product, expired=True)
        with person_logged_in(product.owner):
            product.setBugSharingPolicy(BugSharingPolicy.FORBIDDEN)
        self._assert_getBugSharingPolicies(
            product, [BugSharingPolicy.PUBLIC, BugSharingPolicy.FORBIDDEN])

    def test_getBugSharingPolicies_distro(self):
        distro = self.factory.makeDistribution()
        self._assert_getBugSharingPolicies(distro, [BugSharingPolicy.PUBLIC])

    def test_jsonGranteeData_with_Some(self):
        # jsonGranteeData returns the expected data for a grantee with
        # permissions which include SOME.
        product = self.factory.makeProduct()
        [policy1, policy2] = getUtility(IAccessPolicySource).findByPillar(
            [product])
        grantee = self.factory.makePerson()
        grantees = self.service.jsonGranteeData(
            [(grantee, {
                policy1: SharingPermission.ALL,
                policy2: SharingPermission.SOME},
              [policy1.type, policy2.type])])
        expected_data = self._makeGranteeData(
            grantee,
            [(policy1.type, SharingPermission.ALL),
             (policy2.type, SharingPermission.SOME)],
             [policy1.type, policy2.type])
        self.assertContentEqual([expected_data], grantees)

    def test_jsonGranteeData_without_Some(self):
        # jsonGranteeData returns the expected data for a grantee with only ALL
        # permissions.
        product = self.factory.makeProduct()
        [policy1, policy2] = getUtility(IAccessPolicySource).findByPillar(
            [product])
        grantee = self.factory.makePerson()
        grantees = self.service.jsonGranteeData(
            [(grantee, {policy1: SharingPermission.ALL}, [])])
        expected_data = self._makeGranteeData(
            grantee,
            [(policy1.type, SharingPermission.ALL)], [])
        self.assertContentEqual([expected_data], grantees)

    def test_jsonGranteeData_with_icon(self):
        # jsonGranteeData returns the expected data for a grantee with has an
        # icon.
        product = self.factory.makeProduct()
        [policy1, policy2] = getUtility(IAccessPolicySource).findByPillar(
            [product])
        icon = self.factory.makeLibraryFileAlias(
            filename='smurf.png', content_type='image/png')
        grantee = self.factory.makeTeam(icon=icon)
        grantees = self.service.jsonGranteeData(
            [(grantee, {policy1: SharingPermission.ALL}, [])])
        expected_data = self._makeGranteeData(
            grantee,
            [(policy1.type, SharingPermission.ALL)], [])
        self.assertContentEqual([expected_data], grantees)

    def _assert_getPillarGranteeData(self, pillar, pillar_type=None):
        # getPillarGranteeData returns the expected data.
        access_policy = self.factory.makeAccessPolicy(
            pillar=pillar,
            type=InformationType.PROPRIETARY)
        grantee = self.factory.makePerson()
        # Make access policy grant so that 'All' is returned.
        self.factory.makeAccessPolicyGrant(access_policy, grantee)
        # Make access artifact grants so that 'Some' is returned.
        artifact_grant = self.factory.makeAccessArtifactGrant()
        self.factory.makeAccessPolicyArtifact(
            artifact=artifact_grant.abstract_artifact, policy=access_policy)

        grantees = self.service.getPillarGranteeData(pillar)
        expected_grantees = [
            self._makeGranteeData(
                grantee,
                [(InformationType.PROPRIETARY, SharingPermission.ALL)], []),
            self._makeGranteeData(
                artifact_grant.grantee,
                [(InformationType.PROPRIETARY, SharingPermission.SOME)],
                [InformationType.PROPRIETARY])]
        if pillar_type == 'product':
            owner_data = self._makeGranteeData(
                pillar.owner,
                [(InformationType.USERDATA, SharingPermission.ALL),
                 (InformationType.PRIVATESECURITY, SharingPermission.ALL)],
                [])
            expected_grantees.append(owner_data)
        self.assertContentEqual(expected_grantees, grantees)

    def test_getProductGranteeData(self):
        # Users with launchpad.Driver can view grantees.
        driver = self.factory.makePerson()
        product = self.factory.makeProduct(driver=driver)
        login_person(driver)
        self._assert_getPillarGranteeData(product, pillar_type='product')

    def test_getDistroGranteeData(self):
        # Users with launchpad.Driver can view grantees.
        driver = self.factory.makePerson()
        distro = self.factory.makeDistribution(driver=driver)
        login_person(driver)
        self._assert_getPillarGranteeData(distro)

    def _assert_QueryCount(self, func, count):
        """ getPillarGrantees[Data] only should use 3 queries.

        1. load access policies for pillar
        2. load grantees
        3. load permissions for grantee

        Steps 2 and 3 are split out to allow batching on persons.
        """
        driver = self.factory.makePerson()
        product = self.factory.makeProduct(driver=driver)
        login_person(driver)
        access_policy = self.factory.makeAccessPolicy(
            pillar=product,
            type=InformationType.PROPRIETARY)

        def makeGrants():
            grantee = self.factory.makePerson()
            # Make access policy grant so that 'All' is returned.
            self.factory.makeAccessPolicyGrant(access_policy, grantee)
            # Make access artifact grants so that 'Some' is returned.
            artifact_grant = self.factory.makeAccessArtifactGrant()
            self.factory.makeAccessPolicyArtifact(
                artifact=artifact_grant.abstract_artifact,
                policy=access_policy)

        # Make some grants and check the count.
        for x in range(5):
            makeGrants()
        with StormStatementRecorder() as recorder:
            grantees = list(func(product))
        self.assertEqual(11, len(grantees))
        self.assertThat(recorder, HasQueryCount(Equals(count)))
        # Make some more grants and check again.
        for x in range(5):
            makeGrants()
        with StormStatementRecorder() as recorder:
            grantees = list(func(product))
        self.assertEqual(21, len(grantees))
        self.assertThat(recorder, HasQueryCount(Equals(count)))

    def test_getPillarGranteesQueryCount(self):
        self._assert_QueryCount(self.service.getPillarGrantees, 3)

    def test_getPillarGranteeDataQueryCount(self):
        self._assert_QueryCount(self.service.getPillarGranteeData, 4)

    def _assert_getPillarGranteeDataUnauthorized(self, pillar):
        # getPillarGranteeData raises an Unauthorized exception if the user is
        # not permitted to do so.
        access_policy = self.factory.makeAccessPolicy(pillar=pillar)
        grantee = self.factory.makePerson()
        self.factory.makeAccessPolicyGrant(access_policy, grantee)
        self.assertRaises(
            Unauthorized, self.service.getPillarGranteeData, pillar)

    def test_getPillarGranteeDataAnonymous(self):
        # Anonymous users are not allowed.
        product = self.factory.makeProduct()
        login(ANONYMOUS)
        self._assert_getPillarGranteeDataUnauthorized(product)

    def test_getPillarGranteeDataAnyone(self):
        # Unauthorized users are not allowed.
        product = self.factory.makeProduct()
        login_person(self.factory.makePerson())
        self._assert_getPillarGranteeDataUnauthorized(product)

    def _assert_getPillarGrantees(self, pillar, pillar_type=None):
        # getPillarGrantees returns the expected data.
        access_policy = self.factory.makeAccessPolicy(
            pillar=pillar,
            type=InformationType.PROPRIETARY)
        grantee = self.factory.makePerson()
        # Make access policy grant so that 'All' is returned.
        self.factory.makeAccessPolicyGrant(access_policy, grantee)
        # Make access artifact grants so that 'Some' is returned.
        artifact_grant = self.factory.makeAccessArtifactGrant()
        self.factory.makeAccessPolicyArtifact(
            artifact=artifact_grant.abstract_artifact, policy=access_policy)

        grantees = self.service.getPillarGrantees(pillar)
        expected_grantees = [
            (grantee, {access_policy: SharingPermission.ALL}, []),
            (artifact_grant.grantee, {access_policy: SharingPermission.SOME},
             [access_policy.type])]
        if pillar_type == 'product':
            policies = getUtility(IAccessPolicySource).findByPillar([pillar])
            policies = [policy for policy in policies
                            if policy.type != InformationType.PROPRIETARY]
            owner_data = (
                pillar.owner,
                dict.fromkeys(policies, SharingPermission.ALL),
                [])
            expected_grantees.append(owner_data)
        self.assertContentEqual(expected_grantees, grantees)

    def test_getProductGrantees(self):
        # Users with launchpad.Driver can view grantees.
        driver = self.factory.makePerson()
        product = self.factory.makeProduct(driver=driver)
        login_person(driver)
        self._assert_getPillarGrantees(product, pillar_type='product')

    def test_getDistroGrantees(self):
        # Users with launchpad.Driver can view grantees.
        driver = self.factory.makePerson()
        distro = self.factory.makeDistribution(driver=driver)
        login_person(driver)
        self._assert_getPillarGrantees(distro)

    def _assert_getPillarGranteesUnauthorized(self, pillar):
        # getPillarGrantees raises an Unauthorized exception if the user is
        # not permitted to do so.
        access_policy = self.factory.makeAccessPolicy(pillar=pillar)
        grantee = self.factory.makePerson()
        self.factory.makeAccessPolicyGrant(access_policy, grantee)
        self.assertRaises(
            Unauthorized, self.service.getPillarGrantees, pillar)

    def test_getPillarGranteesAnonymous(self):
        # Anonymous users are not allowed.
        product = self.factory.makeProduct()
        login(ANONYMOUS)
        self._assert_getPillarGranteesUnauthorized(product)

    def test_getPillarGranteesAnyone(self):
        # Unauthorized users are not allowed.
        product = self.factory.makeProduct()
        login_person(self.factory.makePerson())
        self._assert_getPillarGranteesUnauthorized(product)

    def _assert_grantee_data(self, expected, actual):
        # Assert that the actual and expected grantee data is equal.
        # Grantee data is a list of (grantee, permissions, info_types) tuples.
        expected_list = list(expected)
        actual_list = list(actual)
        self.assertEqual(len(expected_list), len(list(actual_list)))

        expected_grantee_map = {}
        for data in expected_list:
            expected_grantee_map[data[0]] = data[1:]
        actual_grantee_map = {}
        for data in actual_list:
            actual_grantee_map[data[0]] = data[1:]

        for grantee, expected_permissions, expected_info_types in expected:
            actual_permissions, actual_info_types = actual_grantee_map[grantee]
            self.assertContentEqual(expected_permissions, actual_permissions)
            self.assertContentEqual(expected_info_types, actual_info_types)

    def _assert_sharePillarInformation(self, pillar, pillar_type=None):
        """sharePillarInformations works and returns the expected data."""
        grantee = self.factory.makePerson()
        grantor = self.factory.makePerson()

        # Make existing grants to ensure sharePillarInformation handles those
        # cases correctly.
        # First, a grant that is in the add set - it wil be retained.
        es_policy = getUtility(IAccessPolicySource).find(((
            pillar, InformationType.PRIVATESECURITY),))[0]
        ud_policy = getUtility(IAccessPolicySource).find(((
            pillar, InformationType.USERDATA),))[0]
        self.factory.makeAccessPolicyGrant(
            es_policy, grantee=grantee, grantor=grantor)
        # Second, grants that are not in the all set - they will be deleted.
        p_policy = self.factory.makeAccessPolicy(
            pillar=pillar, type=InformationType.PROPRIETARY)
        self.factory.makeAccessPolicyGrant(
            p_policy, grantee=grantee, grantor=grantor)
        self.factory.makeAccessPolicyGrant(
            ud_policy, grantee=grantee, grantor=grantor)

        # We also make some artifact grants.
        # First, a grant which will be retained.
        artifact = self.factory.makeAccessArtifact()
        self.factory.makeAccessArtifactGrant(artifact, grantee)
        self.factory.makeAccessPolicyArtifact(
            artifact=artifact, policy=es_policy)
        # Second, grants which will be deleted because their policies have
        # information types in the 'some' or 'nothing' category.
        artifact = self.factory.makeAccessArtifact()
        self.factory.makeAccessArtifactGrant(artifact, grantee)
        self.factory.makeAccessPolicyArtifact(
            artifact=artifact, policy=p_policy)
        artifact = self.factory.makeAccessArtifact()
        self.factory.makeAccessArtifactGrant(artifact, grantee)
        self.factory.makeAccessPolicyArtifact(
            artifact=artifact, policy=ud_policy)

        # Now call sharePillarInformation will the grants we want.
        permissions = {
            InformationType.PRIVATESECURITY: SharingPermission.ALL,
            InformationType.USERDATA: SharingPermission.SOME,
            InformationType.PROPRIETARY: SharingPermission.NOTHING}
        grantee_data = self.service.sharePillarInformation(
            pillar, grantee, grantor, permissions)
        policies = getUtility(IAccessPolicySource).findByPillar([pillar])
        policy_grant_source = getUtility(IAccessPolicyGrantSource)
        grants = policy_grant_source.findByPolicy(policies)

        # Filter out the owner's grants if they exist. They're automatic and
        # already tested.
        [grant] = [g for g in grants if g.grantee != pillar.owner]
        self.assertEqual(grantor, grant.grantor)
        self.assertEqual(grantee, grant.grantee)
        expected_permissions = [
            (InformationType.PRIVATESECURITY, SharingPermission.ALL),
            (InformationType.USERDATA, SharingPermission.SOME)]
        expected_grantee_data = self._makeGranteeData(
            grantee, expected_permissions,
            [InformationType.PRIVATESECURITY, InformationType.USERDATA])
        self.assertContentEqual(
            expected_grantee_data, grantee_data['grantee_entry'])
        # Check that getPillarGrantees returns what we expect.
        if pillar_type == 'product':
            expected_grantee_grants = [
                (grantee,
                 {ud_policy: SharingPermission.SOME,
                  es_policy: SharingPermission.ALL},
                 [InformationType.PRIVATESECURITY,
                  InformationType.USERDATA]),
                 ]
        else:
            expected_grantee_grants = [
                (grantee,
                 {es_policy: SharingPermission.ALL,
                  ud_policy: SharingPermission.SOME},
                 [InformationType.PRIVATESECURITY,
                  InformationType.USERDATA]),
                 ]

        grantee_grants = list(self.service.getPillarGrantees(pillar))
        # Again, filter out the owner, if one exists.
        grantee_grants = [s for s in grantee_grants if s[0] != pillar.owner]
        self.assertContentEqual(expected_grantee_grants, grantee_grants)

    def test_updateProjectGroupGrantee_not_allowed(self):
        # We cannot add grantees to ProjectGroups.
        owner = self.factory.makePerson()
        project_group = self.factory.makeProject(owner=owner)
        grantee = self.factory.makePerson()
        login_person(owner)
        self.assertRaises(
            AssertionError, self.service.sharePillarInformation,
            project_group, grantee, owner,
            {InformationType.USERDATA: SharingPermission.ALL})

    def test_updateProductGrantee(self):
        # Users with launchpad.Edit can add grantees.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(owner=owner)
        login_person(owner)
        self._assert_sharePillarInformation(product, pillar_type='product')

    def test_updateDistroGrantee(self):
        # Users with launchpad.Edit can add grantees.
        owner = self.factory.makePerson()
        distro = self.factory.makeDistribution(owner=owner)
        login_person(owner)
        self._assert_sharePillarInformation(distro)

    def test_updatePillarGrantee_no_access_grants_remain(self):
        # When a pillar grantee has it's only access policy permission changed
        # to Some, test that None is returned.
        owner = self.factory.makePerson()
        pillar = self.factory.makeProduct(owner=owner)
        login_person(owner)
        grantee = self.factory.makePerson()
        grant = self.factory.makeAccessPolicyGrant(grantee=grantee)

        permissions = {
            grant.policy.type: SharingPermission.SOME}
        grantee_data = self.service.sharePillarInformation(
            pillar, grantee, self.factory.makePerson(), permissions)
        self.assertIsNone(grantee_data['grantee_entry'])

    def test_granteePillarInformationInvisibleInformationTypes(self):
        # Sharing with a user returns data containing the resulting invisible
        # information types.
        product = self.factory.makeProduct()
        grantee = self.factory.makePerson()
        with admin_logged_in():
            self.service.deletePillarGrantee(
                product, product.owner, product.owner)
            result_data = self.service.sharePillarInformation(
                product, grantee, product.owner,
                {InformationType.USERDATA: SharingPermission.ALL})
        # The owner is granted access on product creation. So we need to allow
        # for that in the check below.
        self.assertContentEqual(
            ['Private Security'],
            result_data['invisible_information_types'])

    def _assert_sharePillarInformationUnauthorized(self, pillar):
        # sharePillarInformation raises an Unauthorized exception if the user
        # is not permitted to do so.
        grantee = self.factory.makePerson()
        user = self.factory.makePerson()
        self.assertRaises(
            Unauthorized, self.service.sharePillarInformation,
            pillar, grantee, user,
            {InformationType.USERDATA: SharingPermission.ALL})

    def test_sharePillarInformationAnonymous(self):
        # Anonymous users are not allowed.
        product = self.factory.makeProduct()
        login(ANONYMOUS)
        self._assert_sharePillarInformationUnauthorized(product)

    def test_sharePillarInformationAnyone(self):
        # Unauthorized users are not allowed.
        product = self.factory.makeProduct()
        login_person(self.factory.makePerson())
        self._assert_sharePillarInformationUnauthorized(product)

    def _assert_deletePillarGrantee(self, pillar, types_to_delete=None,
                                    pillar_type=None):
        access_policies = getUtility(IAccessPolicySource).findByPillar(
            (pillar,))
        information_types = [ap.type for ap in access_policies]
        grantee = self.factory.makePerson()
        # Make some access policy grants for our grantee.
        for access_policy in access_policies:
            self.factory.makeAccessPolicyGrant(access_policy, grantee)
        # Make some artifact grants for our grantee.
        artifact = self.factory.makeAccessArtifact()
        self.factory.makeAccessArtifactGrant(artifact, grantee)
        # Make some access policy grants for another grantee.
        another = self.factory.makePerson()
        self.factory.makeAccessPolicyGrant(access_policies[0], another)
        # Make some artifact grants for our yet another grantee.
        yet_another = self.factory.makePerson()
        self.factory.makeAccessArtifactGrant(artifact, yet_another)
        for access_policy in access_policies:
            self.factory.makeAccessPolicyArtifact(
                artifact=artifact, policy=access_policy)
        # Delete data for a specific information type.
        self.service.deletePillarGrantee(
            pillar, grantee, pillar.owner, types_to_delete)
        # Assemble the expected data for the remaining access grants for
        # grantee.
        expected_data = []
        if types_to_delete is not None:
            expected_information_types = (
                set(information_types).difference(types_to_delete))
            expected_policies = [
                access_policy for access_policy in access_policies
                if access_policy.type in expected_information_types]
            expected_data = [
                (grantee, {policy: SharingPermission.ALL}, [])
                for policy in expected_policies]
        # Add the expected data for the other grantees.
        another_person_data = (
            another, {access_policies[0]: SharingPermission.ALL}, [])
        expected_data.append(another_person_data)
        policy_permissions = dict([(
            policy, SharingPermission.SOME) for policy in access_policies])
        yet_another_person_data = (
            yet_another, policy_permissions,
            [InformationType.PRIVATESECURITY, InformationType.USERDATA])
        expected_data.append(yet_another_person_data)
        if pillar_type == 'product':
            policy_permissions = dict([(
                policy, SharingPermission.ALL) for policy in access_policies])
            owner_data = (pillar.owner, policy_permissions, [])
            expected_data.append(owner_data)
        self._assert_grantee_data(
            expected_data, self.service.getPillarGrantees(pillar))

    def test_deleteProductGranteeAll(self):
        # Users with launchpad.Edit can delete all access for a grantee.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(owner=owner)
        login_person(owner)
        self._assert_deletePillarGrantee(product, pillar_type='product')

    def test_deleteProductGranteeSelectedPolicies(self):
        # Users with launchpad.Edit can delete selected policy access for an
        # grantee.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(owner=owner)
        login_person(owner)
        self._assert_deletePillarGrantee(
            product, [InformationType.USERDATA], pillar_type='product')

    def test_deleteDistroGranteeAll(self):
        # Users with launchpad.Edit can delete all access for a grantee.
        owner = self.factory.makePerson()
        distro = self.factory.makeDistribution(owner=owner)
        login_person(owner)
        self._assert_deletePillarGrantee(distro)

    def test_deleteDistroGranteeSelectedPolicies(self):
        # Users with launchpad.Edit can delete selected policy access for an
        # grantee.
        owner = self.factory.makePerson()
        distro = self.factory.makeDistribution(owner=owner)
        login_person(owner)
        self._assert_deletePillarGrantee(distro, [InformationType.USERDATA])

    def test_deletePillarGranteeInvisibleInformationTypes(self):
        # Deleting a pillar grantee returns the resulting invisible info types.
        product = self.factory.makeProduct()
        with admin_logged_in():
            invisible_information_types = self.service.deletePillarGrantee(
                product, product.owner, product.owner)
        self.assertContentEqual(
            ['Private', 'Private Security'], invisible_information_types)

    def _assert_deletePillarGranteeUnauthorized(self, pillar):
        # deletePillarGrantee raises an Unauthorized exception if the user
        # is not permitted to do so.
        self.assertRaises(
            Unauthorized, self.service.deletePillarGrantee,
            pillar, pillar.owner, pillar.owner, [InformationType.USERDATA])

    def test_deletePillarGranteeAnonymous(self):
        # Anonymous users are not allowed.
        product = self.factory.makeProduct()
        login(ANONYMOUS)
        self._assert_deletePillarGranteeUnauthorized(product)

    def test_deletePillarGranteeAnyone(self):
        # Unauthorized users are not allowed.
        product = self.factory.makeProduct()
        login_person(self.factory.makePerson())
        self._assert_deletePillarGranteeUnauthorized(product)

    def _assert_deleteGranteeRemoveSubscriptions(self,
                                                types_to_delete=None):
        product = self.factory.makeProduct()
        access_policies = getUtility(IAccessPolicySource).findByPillar(
            (product,))
        information_types = [ap.type for ap in access_policies]
        grantee = self.factory.makePerson()
        # Make some access policy grants for our grantee.
        for access_policy in access_policies:
            self.factory.makeAccessPolicyGrant(access_policy, grantee)

        login_person(product.owner)
        # Make some bug artifact grants for our grantee.
        # Branches will be done when information_type attribute is supported.
        bugs = []
        for access_policy in access_policies:
            bug = self.factory.makeBug(
                target=product, owner=product.owner,
                information_type=access_policy.type)
            bugs.append(bug)
            artifact = self.factory.makeAccessArtifact(concrete=bug)
            self.factory.makeAccessArtifactGrant(artifact, grantee)

        # Make some access policy grants for another grantee.
        another = self.factory.makePerson()
        self.factory.makeAccessPolicyGrant(access_policies[0], another)

        # Subscribe the grantee and other person to the artifacts.
        for person in [grantee, another]:
            for bug in bugs:
                bug.subscribe(person, product.owner)

        # Delete data for specified information types or all.
        self.service.deletePillarGrantee(
            product, grantee, product.owner, types_to_delete)
        with block_on_job(self):
            transaction.commit()

        expected_information_types = []
        if types_to_delete is not None:
            expected_information_types = (
                set(information_types).difference(types_to_delete))
        # Check that grantee is unsubscribed.
        login_person(product.owner)
        for bug in bugs:
            if bug.information_type in expected_information_types:
                self.assertIn(grantee, bug.getDirectSubscribers())
            else:
                self.assertNotIn(grantee, bug.getDirectSubscribers())
            self.assertIn(another, bug.getDirectSubscribers())

    def test_granteeUnsubscribedWhenDeleted(self):
        # The grantee is unsubscribed from any inaccessible artifacts when
        # their access is revoked.
        self._assert_deleteGranteeRemoveSubscriptions()

    def test_granteeUnsubscribedWhenDeletedSelectedPolicies(self):
        # The grantee is unsubscribed from any inaccessible artifacts when
        # their access to selected policies is revoked.
        self._assert_deleteGranteeRemoveSubscriptions(
            [InformationType.USERDATA])

    def _assert_revokeAccessGrants(self, pillar, bugs, branches,
                                   specifications):
        artifacts = []
        if bugs:
            artifacts.extend(bugs)
        if branches:
            artifacts.extend(branches)
        if specifications:
            artifacts.extend(specifications)
        policy = self.factory.makeAccessPolicy(pillar=pillar,
                                               check_existing=True)
        # Grant access to a grantee and another person.
        grantee = self.factory.makePerson()
        someone = self.factory.makePerson()
        access_artifacts = []
        for artifact in artifacts:
            access_artifact = self.factory.makeAccessArtifact(
                concrete=artifact)
            access_artifacts.append(access_artifact)
            self.factory.makeAccessPolicyArtifact(
                artifact=access_artifact, policy=policy)
            for person in [grantee, someone]:
                self.factory.makeAccessArtifactGrant(
                    artifact=access_artifact, grantee=person,
                    grantor=pillar.owner)

        # Subscribe the grantee and other person to the artifacts.
        for person in [grantee, someone]:
            for bug in bugs or []:
                bug.subscribe(person, pillar.owner)
            for branch in branches or []:
                branch.subscribe(person,
                    BranchSubscriptionNotificationLevel.NOEMAIL, None,
                    CodeReviewNotificationLevel.NOEMAIL, pillar.owner)
            for spec in specifications or []:
                spec.subscribe(person)

        # Check that grantee has expected access grants.
        accessartifact_grant_source = getUtility(IAccessArtifactGrantSource)
        grants = accessartifact_grant_source.findByArtifact(
            access_artifacts, [grantee])
        apgfs = getUtility(IAccessPolicyGrantFlatSource)
        self.assertEqual(1, grants.count())

        self.service.revokeAccessGrants(
            pillar, grantee, pillar.owner, bugs=bugs, branches=branches,
            specifications=specifications)
        with block_on_job(self):
            transaction.commit()

        # The grantee now has no access to anything.
        permission_info = apgfs.findGranteePermissionsByPolicy(
            [policy], [grantee])
        self.assertEqual(0, permission_info.count())

        # Check that the grantee's subscriptions have been removed.
        for bug in bugs or []:
            self.assertNotIn(grantee, bug.getDirectSubscribers())
        for branch in branches or []:
            self.assertNotIn(grantee, branch.subscribers)
        for spec in specifications or []:
            self.assertNotIn(grantee, spec.subscribers)

        # Someone else still has access to the bugs and branches.
        grants = accessartifact_grant_source.findByArtifact(
            access_artifacts, [someone])
        self.assertEqual(1, grants.count())
        # Someone else still has subscriptions to the bugs and branches.
        for bug in bugs or []:
            self.assertIn(someone, bug.getDirectSubscribers())
        for branch in branches or []:
            self.assertIn(someone, branch.subscribers)
        for spec in specifications or []:
            self.assertIn(someone, spec.subscribers)

    def test_revokeAccessGrantsBugs(self):
        # Users with launchpad.Edit can delete all access for a grantee.
        owner = self.factory.makePerson()
        distro = self.factory.makeDistribution(owner=owner)
        login_person(owner)
        bug = self.factory.makeBug(
            target=distro, owner=owner,
            information_type=InformationType.USERDATA)
        self._assert_revokeAccessGrants(distro, [bug], None, None)

    def test_revokeAccessGrantsBranches(self):
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(owner=owner)
        login_person(owner)
        branch = self.factory.makeBranch(
            product=product, owner=owner,
            information_type=InformationType.USERDATA)
        self._assert_revokeAccessGrants(product, None, [branch], None)

    def test_revokeAccessGrantsSpecifications(self):
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(
            owner=owner, specification_sharing_policy=(
                SpecificationSharingPolicy.EMBARGOED_OR_PROPRIETARY))
        login_person(owner)
        specification = self.factory.makeSpecification(
            product=product, owner=owner,
            information_type=InformationType.EMBARGOED)
        self._assert_revokeAccessGrants(product, None, None, [specification])

    def _assert_revokeTeamAccessGrants(self, pillar, bugs, branches,
                                       specifications):
        artifacts = []
        if bugs:
            artifacts.extend(bugs)
        if branches:
            artifacts.extend(branches)
        if specifications:
            artifacts.extend(specifications)
        policy = self.factory.makeAccessPolicy(pillar=pillar,
                                               check_existing=True)

        person_grantee = self.factory.makePerson()
        team_owner = self.factory.makePerson()
        team_grantee = self.factory.makeTeam(
            owner=team_owner,
            membership_policy=TeamMembershipPolicy.RESTRICTED,
            members=[person_grantee], email='team@example.org')

        # Subscribe the team and person grantees to the artifacts.
        for person in [team_grantee, person_grantee]:
            for bug in bugs or []:
                bug.subscribe(person, pillar.owner)
                # XXX 2012-06-12 wallyworld bug=1002596
                # No need to revoke AAG with triggers removed.
                if person == person_grantee:
                    accessartifact_source = getUtility(IAccessArtifactSource)
                    getUtility(IAccessArtifactGrantSource).revokeByArtifact(
                        accessartifact_source.find([bug]), [person_grantee])
            for branch in branches or []:
                branch.subscribe(
                    person, BranchSubscriptionNotificationLevel.NOEMAIL,
                    None, CodeReviewNotificationLevel.NOEMAIL, pillar.owner)
            # Subscribing somebody to a specification does not yet imply
            # granting access to this person.
            if specifications:
                self.service.ensureAccessGrants(
                    [person], pillar.owner, specifications=specifications)
            for spec in specifications or []:
                spec.subscribe(person)

        # Check that grantees have expected access grants and subscriptions.
        for person in [team_grantee, person_grantee]:
            visible_bugs, visible_branches, visible_specs = (
                self.service.getVisibleArtifacts(
                    person, branches, bugs, specifications))
            self.assertContentEqual(bugs or [], visible_bugs)
            self.assertContentEqual(branches or [], visible_branches)
            self.assertContentEqual(specifications or [], visible_specs)
        for person in [team_grantee, person_grantee]:
            for bug in bugs or []:
                self.assertIn(person, bug.getDirectSubscribers())

        self.service.revokeAccessGrants(
            pillar, team_grantee, pillar.owner, bugs=bugs, branches=branches,
            specifications=specifications)
        with block_on_job(self):
            transaction.commit()

        # The grantees now have no access to anything.
        apgfs = getUtility(IAccessPolicyGrantFlatSource)
        permission_info = apgfs.findGranteePermissionsByPolicy(
            [policy], [team_grantee, person_grantee])
        self.assertEqual(0, permission_info.count())

        # Check that the grantee's subscriptions have been removed.
        # Branches will be done once they have the information_type attribute.
        for person in [team_grantee, person_grantee]:
            for bug in bugs or []:
                self.assertNotIn(person, bug.getDirectSubscribers())
            visible_bugs, visible_branches, visible_specs = (
                self.service.getVisibleArtifacts(person, branches, bugs))
            self.assertContentEqual([], visible_bugs)
            self.assertContentEqual([], visible_branches)
            self.assertContentEqual([], visible_specs)

    def test_revokeTeamAccessGrantsBugs(self):
        # Users with launchpad.Edit can delete all access for a grantee.
        owner = self.factory.makePerson()
        distro = self.factory.makeDistribution(owner=owner)
        login_person(owner)
        bug = self.factory.makeBug(
            target=distro, owner=owner,
            information_type=InformationType.USERDATA)
        self._assert_revokeTeamAccessGrants(distro, [bug], None, None)

    def test_revokeTeamAccessGrantsBranches(self):
        # Users with launchpad.Edit can delete all access for a grantee.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(owner=owner)
        login_person(owner)
        branch = self.factory.makeBranch(
            owner=owner, information_type=InformationType.USERDATA)
        self._assert_revokeTeamAccessGrants(product, None, [branch], None)

    def test_revokeTeamAccessGrantsSpecifications(self):
        # Users with launchpad.Edit can delete all access for a grantee.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(
            owner=owner, specification_sharing_policy=(
                SpecificationSharingPolicy.EMBARGOED_OR_PROPRIETARY))
        login_person(owner)
        specification = self.factory.makeSpecification(
            product=product, owner=owner,
            information_type=InformationType.EMBARGOED)
        self._assert_revokeTeamAccessGrants(
            product, None, None, [specification])

    def _assert_revokeAccessGrantsUnauthorized(self):
        # revokeAccessGrants raises an Unauthorized exception if the user
        # is not permitted to do so.
        product = self.factory.makeProduct()
        bug = self.factory.makeBug(
            target=product, information_type=InformationType.USERDATA)
        grantee = self.factory.makePerson()
        self.assertRaises(
            Unauthorized, self.service.revokeAccessGrants,
            product, grantee, product.owner, bugs=[bug])

    def test_revokeAccessGrantsAnonymous(self):
        # Anonymous users are not allowed.
        login(ANONYMOUS)
        self._assert_revokeAccessGrantsUnauthorized()

    def test_revokeAccessGrantsAnyone(self):
        # Unauthorized users are not allowed.
        login_person(self.factory.makePerson())
        self._assert_revokeAccessGrantsUnauthorized()

    def test_revokeAccessGrants_without_bugs_or_branches(self):
        # The revokeAccessGrants method raises a ValueError if called without
        # specifying either bugs or branches.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(owner=owner)
        grantee = self.factory.makePerson()
        login_person(owner)
        self.assertRaises(
            ValueError, self.service.revokeAccessGrants,
            product, grantee, product.owner)

    def _assert_ensureAccessGrants(self, user, bugs, branches, specifications,
                                   grantee=None):
        # Creating access grants works as expected.
        if not grantee:
            grantee = self.factory.makePerson()
        self.service.ensureAccessGrants(
            [grantee], user, bugs=bugs, branches=branches,
            specifications=specifications)

        # Check that grantee has expected access grants.
        shared_bugs = []
        shared_branches = []
        shared_specifications = []
        all_pillars = []
        for bug in bugs or []:
            all_pillars.extend(bug.affected_pillars)
        for branch in branches or []:
            all_pillars.append(branch.target.context)
        for specification in specifications or []:
            all_pillars.append(specification.target)
        policies = getUtility(IAccessPolicySource).findByPillar(all_pillars)

        apgfs = getUtility(IAccessPolicyGrantFlatSource)
        access_artifacts = apgfs.findArtifactsByGrantee(grantee, policies)
        for a in access_artifacts:
            if IBug.providedBy(a.concrete_artifact):
                shared_bugs.append(a.concrete_artifact)
            elif IBranch.providedBy(a.concrete_artifact):
                shared_branches.append(a.concrete_artifact)
            elif ISpecification.providedBy(a.concrete_artifact):
                shared_specifications.append(a.concrete_artifact)
        self.assertContentEqual(bugs or [], shared_bugs)
        self.assertContentEqual(branches or [], shared_branches)
        self.assertContentEqual(specifications or [], shared_specifications)

    def test_ensureAccessGrantsBugs(self):
        # Access grants can be created for bugs.
        owner = self.factory.makePerson()
        distro = self.factory.makeDistribution(owner=owner)
        login_person(owner)
        bug = self.factory.makeBug(
            target=distro, owner=owner,
            information_type=InformationType.USERDATA)
        self._assert_ensureAccessGrants(owner, [bug], None, None)

    def test_ensureAccessGrantsBranches(self):
        # Access grants can be created for branches.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(owner=owner)
        login_person(owner)
        branch = self.factory.makeBranch(
            product=product, owner=owner,
            information_type=InformationType.USERDATA)
        self._assert_ensureAccessGrants(owner, None, [branch], None)

    def test_ensureAccessGrantsSpecifications(self):
        # Access grants can be created for branches.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(
            owner=owner,
            specification_sharing_policy=(
                SpecificationSharingPolicy.PUBLIC_OR_PROPRIETARY))
        login_person(owner)
        specification = self.factory.makeSpecification(
            product=product, owner=owner)
        removeSecurityProxy(specification.target)._ensurePolicies(
             [InformationType.PROPRIETARY])
        with person_logged_in(owner):
            specification.transitionToInformationType(
                InformationType.PROPRIETARY, owner)
        self._assert_ensureAccessGrants(owner, None, None, [specification])

    def test_ensureAccessGrantsExisting(self):
        # Any existing access grants are retained and new ones created.
        owner = self.factory.makePerson()
        distro = self.factory.makeDistribution(owner=owner)
        login_person(owner)
        bug = self.factory.makeBug(
            target=distro, owner=owner,
            information_type=InformationType.USERDATA)
        bug2 = self.factory.makeBug(
            target=distro, owner=owner,
            information_type=InformationType.USERDATA)
        # Create an existing access grant.
        grantee = self.factory.makePerson()
        self.service.ensureAccessGrants([grantee], owner, bugs=[bug])
        # Test with a new bug as well as the one for which access is already
        # granted.
        self._assert_ensureAccessGrants(
            owner, [bug, bug2], None, None, grantee)

    def _assert_ensureAccessGrantsUnauthorized(self, user):
        # ensureAccessGrants raises an Unauthorized exception if the user
        # is not permitted to do so.
        product = self.factory.makeProduct()
        bug = self.factory.makeBug(
            target=product, information_type=InformationType.USERDATA)
        grantee = self.factory.makePerson()
        self.assertRaises(
            Unauthorized, self.service.ensureAccessGrants, [grantee], user,
            bugs=[bug])

    def test_ensureAccessGrantsAnonymous(self):
        # Anonymous users are not allowed.
        login(ANONYMOUS)
        self._assert_ensureAccessGrantsUnauthorized(ANONYMOUS)

    def test_ensureAccessGrantsAnyone(self):
        # Unauthorized users are not allowed.
        anyone = self.factory.makePerson()
        login_person(anyone)
        self._assert_ensureAccessGrantsUnauthorized(anyone)

    def test_updatePillarBugSharingPolicy(self):
        # updatePillarSharingPolicies works for bugs.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(owner=owner)
        self.factory.makeCommercialSubscription(product)
        login_person(owner)
        self.service.updatePillarSharingPolicies(
            product,
            bug_sharing_policy=BugSharingPolicy.PROPRIETARY)
        self.assertEqual(
            BugSharingPolicy.PROPRIETARY, product.bug_sharing_policy)

    def test_updatePillarBranchSharingPolicy(self):
        # updatePillarSharingPolicies works for branches.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(owner=owner)
        self.factory.makeCommercialSubscription(product)
        login_person(owner)
        self.service.updatePillarSharingPolicies(
            product,
            branch_sharing_policy=BranchSharingPolicy.PROPRIETARY)
        self.assertEqual(
            BranchSharingPolicy.PROPRIETARY, product.branch_sharing_policy)

    def _assert_updatePillarSharingPoliciesUnauthorized(self, user):
        # updatePillarSharingPolicies raises an Unauthorized exception if the
        # user is not permitted to do so.
        product = self.factory.makeProduct()
        self.assertRaises(
            Unauthorized, self.service.updatePillarSharingPolicies,
            product, BranchSharingPolicy.PUBLIC, BugSharingPolicy.PUBLIC)

    def test_updatePillarSharingPoliciesAnonymous(self):
        # Anonymous users are not allowed.
        login(ANONYMOUS)
        self._assert_updatePillarSharingPoliciesUnauthorized(ANONYMOUS)

    def test_updatePillarSharingPoliciesAnyone(self):
        # Unauthorized users are not allowed.
        anyone = self.factory.makePerson()
        login_person(anyone)
        self._assert_updatePillarSharingPoliciesUnauthorized(anyone)

    def create_shared_artifacts(self, product, grantee, user):
        # Create some shared bugs and branches.
        bugs = []
        bug_tasks = []
        for x in range(0, 10):
            bug = self.factory.makeBug(
                target=product, owner=product.owner,
                information_type=InformationType.USERDATA)
            bugs.append(bug)
            bug_tasks.append(bug.default_bugtask)
        branches = []
        for x in range(0, 10):
            branch = self.factory.makeBranch(
                product=product, owner=product.owner,
                information_type=InformationType.USERDATA)
            branches.append(branch)
        specs = []
        for x in range(0, 10):
            spec = self.factory.makeSpecification(
                product=product, owner=product.owner,
                information_type=InformationType.PROPRIETARY)
            specs.append(spec)

        # Grant access to grantee as well as the person who will be doing the
        # query. The person who will be doing the query is not granted access
        # to the last bug/branch so those won't be in the result.
        def grant_access(artifact, grantee_only):
            access_artifact = self.factory.makeAccessArtifact(
                concrete=artifact)
            self.factory.makeAccessArtifactGrant(
                artifact=access_artifact, grantee=grantee,
                grantor=product.owner)
            if not grantee_only:
                self.factory.makeAccessArtifactGrant(
                    artifact=access_artifact, grantee=user,
                    grantor=product.owner)

        for i, bug in enumerate(bugs):
            grant_access(bug, i == 9)
        for i, branch in enumerate(branches):
            grant_access(branch, i == 9)
        getUtility(IService, 'sharing').ensureAccessGrants(
            [grantee], product.owner, specifications=specs[:9])
        return bug_tasks, branches, specs

    def test_getSharedArtifacts(self):
        # Test the getSharedArtifacts method.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(
            owner=owner, specification_sharing_policy=(
            SpecificationSharingPolicy.PUBLIC_OR_PROPRIETARY))
        login_person(owner)
        grantee = self.factory.makePerson()
        user = self.factory.makePerson()
        bug_tasks, branches, specs = self.create_shared_artifacts(
            product, grantee, user)

        # Check the results.
        shared_bugtasks, shared_branches, shared_specs = (
            self.service.getSharedArtifacts(product, grantee, user))
        self.assertContentEqual(bug_tasks[:9], shared_bugtasks)
        self.assertContentEqual(branches[:9], shared_branches)
        self.assertContentEqual(specs[:9], shared_specs)

    def _assert_getSharedProjects(self, product, who=None):
        # Test that 'who' can query the shared products for a grantee.

        # Make a product not related to 'who' which will be shared.
        unrelated_product = self.factory.makeProduct()
        # Make an unshared product.
        self.factory.makeProduct()
        person = self.factory.makePerson()
        # Include more than one permission to ensure distinct works.
        permissions = {
            InformationType.PRIVATESECURITY: SharingPermission.ALL,
            InformationType.USERDATA: SharingPermission.ALL}
        with person_logged_in(product.owner):
            self.service.sharePillarInformation(
                product, person, product.owner, permissions)
        with person_logged_in(unrelated_product.owner):
            self.service.sharePillarInformation(
                unrelated_product, person, unrelated_product.owner,
                permissions)
        shared = self.service.getSharedProjects(person, who)
        expected = []
        if who:
            expected = [product]
            if IPersonRoles(who).in_admin:
                expected.append(unrelated_product)
        self.assertEqual(expected, list(shared))

    def test_getSharedProjects_anonymous(self):
        # Anonymous users don't get to see any shared products.
        product = self.factory.makeProduct()
        self._assert_getSharedProjects(product)

    def test_getSharedProjects_admin(self):
        # Admins can see all shared products.
        admin = getUtility(ILaunchpadCelebrities).admin.teamowner
        product = self.factory.makeProduct()
        self._assert_getSharedProjects(product, admin)

    def test_getSharedProjects_commercial_admin_current(self):
        # Commercial admins can see all current commercial products.
        admin = getUtility(ILaunchpadCelebrities).commercial_admin.teamowner
        product = self.factory.makeProduct()
        self.factory.makeCommercialSubscription(product)
        self._assert_getSharedProjects(product, admin)

    def test_getSharedProjects_commercial_admin_expired(self):
        # Commercial admins can see all expired commercial products.
        admin = getUtility(ILaunchpadCelebrities).commercial_admin.teamowner
        product = self.factory.makeProduct()
        self.factory.makeCommercialSubscription(product, expired=True)
        self._assert_getSharedProjects(product, admin)

    def test_getSharedProjects_commercial_admin_owner(self):
        # Commercial admins can see products they own.
        admin = getUtility(ILaunchpadCelebrities).commercial_admin
        product = self.factory.makeProduct(owner=admin)
        self._assert_getSharedProjects(product, admin.teamowner)

    def test_getSharedProjects_commercial_admin_driver(self):
        # Commercial admins can see products they are the driver for.
        admin = getUtility(ILaunchpadCelebrities).commercial_admin
        product = self.factory.makeProduct(driver=admin)
        self._assert_getSharedProjects(product, admin.teamowner)

    def test_getSharedProjects_owner(self):
        # Users only see shared products they own.
        owner_team = self.factory.makeTeam(
            membership_policy=TeamMembershipPolicy.MODERATED)
        product = self.factory.makeProduct(owner=owner_team)
        self._assert_getSharedProjects(product, owner_team.teamowner)

    def test_getSharedProjects_driver(self):
        # Users only see shared products they are the driver for.
        driver_team = self.factory.makeTeam()
        product = self.factory.makeProduct(driver=driver_team)
        self._assert_getSharedProjects(product, driver_team.teamowner)

    def _assert_getSharedDistributions(self, distro, who=None):
        # Test that 'who' can query the shared distros for a grantee.

        # Make a distro not related to 'who' which will be shared.
        unrelated_distro = self.factory.makeDistribution()
        # Make an unshared distro.
        self.factory.makeDistribution()
        person = self.factory.makePerson()
        # Include more than one permission to ensure distinct works.
        permissions = {
            InformationType.PRIVATESECURITY: SharingPermission.ALL,
            InformationType.USERDATA: SharingPermission.ALL}
        with person_logged_in(distro.owner):
            self.service.sharePillarInformation(
                distro, person, distro.owner, permissions)
        with person_logged_in(unrelated_distro.owner):
            self.service.sharePillarInformation(
                unrelated_distro, person, unrelated_distro.owner,
                permissions)
        shared = self.service.getSharedDistributions(person, who)
        expected = []
        if who:
            expected = [distro]
            if IPersonRoles(who).in_admin:
                expected.append(unrelated_distro)
        self.assertEqual(expected, list(shared))

    def test_getSharedDistributions_anonymous(self):
        # Anonymous users don't get to see any shared distros.
        distro = self.factory.makeDistribution()
        self._assert_getSharedDistributions(distro)

    def test_getSharedDistributions_admin(self):
        # Admins can see all shared distros.
        admin = getUtility(ILaunchpadCelebrities).admin.teamowner
        distro = self.factory.makeDistribution()
        self._assert_getSharedDistributions(distro, admin)

    def test_getSharedDistributions_owner(self):
        # Users only see shared distros they own.
        owner_team = self.factory.makeTeam(
            membership_policy=TeamMembershipPolicy.MODERATED)
        distro = self.factory.makeDistribution(owner=owner_team)
        self._assert_getSharedDistributions(distro, owner_team.teamowner)

    def test_getSharedDistributions_driver(self):
        # Users only see shared distros they are the driver for.
        driver_team = self.factory.makeTeam()
        distro = self.factory.makeDistribution(driver=driver_team)
        self._assert_getSharedDistributions(distro, driver_team.teamowner)

    def test_getSharedBugs(self):
        # Test the getSharedBugs method.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(
            owner=owner, specification_sharing_policy=(
            SpecificationSharingPolicy.PUBLIC_OR_PROPRIETARY))
        login_person(owner)
        grantee = self.factory.makePerson()
        user = self.factory.makePerson()
        bug_tasks, ignored, ignored = self.create_shared_artifacts(
            product, grantee, user)

        # Check the results.
        shared_bugtasks = self.service.getSharedBugs(product, grantee, user)
        self.assertContentEqual(bug_tasks[:9], shared_bugtasks)

    def test_getSharedBranches(self):
        # Test the getSharedBranches method.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(
            owner=owner, specification_sharing_policy=(
            SpecificationSharingPolicy.PUBLIC_OR_PROPRIETARY))
        login_person(owner)
        grantee = self.factory.makePerson()
        user = self.factory.makePerson()
        ignored, branches, ignored = self.create_shared_artifacts(
            product, grantee, user)

        # Check the results.
        shared_branches = self.service.getSharedBranches(
            product, grantee, user)
        self.assertContentEqual(branches[:9], shared_branches)

    def test_getSharedSpecifications(self):
        # Test the getSharedSpecifications method.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(
            owner=owner, specification_sharing_policy=(
            SpecificationSharingPolicy.PUBLIC_OR_PROPRIETARY))
        login_person(owner)
        grantee = self.factory.makePerson()
        user = self.factory.makePerson()
        ignored, ignored, specifications = self.create_shared_artifacts(
            product, grantee, user)

        # Check the results.
        shared_specifications = self.service.getSharedSpecifications(
            product, grantee, user)
        self.assertContentEqual(specifications[:9], shared_specifications)

    def test_getPeopleWithAccessBugs(self):
        # Test the getPeopleWithoutAccess method with bugs.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(owner=owner)
        bug = self.factory.makeBug(
            target=product, owner=owner,
            information_type=InformationType.USERDATA)
        login_person(owner)
        self._assert_getPeopleWithoutAccess(product, bug)

    def test_getPeopleWithAccessBranches(self):
        # Test the getPeopleWithoutAccess method with branches.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(owner=owner)
        branch = self.factory.makeBranch(
            product=product, owner=owner,
            information_type=InformationType.USERDATA)
        login_person(owner)
        self._assert_getPeopleWithoutAccess(product, branch)

    def _assert_getPeopleWithoutAccess(self, product, artifact):
        access_artifact = self.factory.makeAccessArtifact(concrete=artifact)
        # Make some people to check. people[:5] will not have access.
        people = []
        # Make a team with access.
        member_with_access = self.factory.makePerson()
        team_with_access = self.factory.makeTeam(members=[member_with_access])
        # Make a team without access.
        team_without_access = (
            self.factory.makeTeam(members=[member_with_access]))
        people.append(team_without_access)
        for x in range(0, 10):
            person = self.factory.makePerson()
            people.append(person)
        people.append(team_with_access)
        people.append(member_with_access)

        # Create some access policy grants.
        [policy] = getUtility(IAccessPolicySource).find(
            [(product, InformationType.USERDATA)])
        for person in people[5:7]:
            self.factory.makeAccessPolicyGrant(
                policy=policy, grantee=person, grantor=product.owner)
        # And some access artifact grants.
        for person in people[7:]:
            self.factory.makeAccessArtifactGrant(
                artifact=access_artifact, grantee=person,
                grantor=product.owner)

        # Check the results.
        without_access = self.service.getPeopleWithoutAccess(artifact, people)
        self.assertContentEqual(people[:5], without_access)

    def _make_Artifacts(self):
        # Make artifacts for test (in)visible artifact methods.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(
            owner=owner,
            specification_sharing_policy=(
                SpecificationSharingPolicy.PUBLIC_OR_PROPRIETARY))
        grantee = self.factory.makePerson()
        login_person(owner)

        bugs = []
        for x in range(0, 10):
            bug = self.factory.makeBug(
                target=product, owner=owner,
                information_type=InformationType.USERDATA)
            bugs.append(bug)
        branches = []
        for x in range(0, 10):
            branch = self.factory.makeBranch(
                product=product, owner=owner,
                information_type=InformationType.USERDATA)
            branches.append(branch)

        specifications = []
        for x in range(0, 10):
            spec = self.factory.makeSpecification(
                product=product, owner=owner,
                information_type=InformationType.PROPRIETARY)
            specifications.append(spec)

        def grant_access(artifact):
            access_artifact = self.factory.makeAccessArtifact(
                concrete=artifact)
            self.factory.makeAccessArtifactGrant(
                artifact=access_artifact, grantee=grantee, grantor=owner)
            return access_artifact

        # Grant access to some of the bugs and branches.
        for bug in bugs[:5]:
            grant_access(bug)
        for branch in branches[:5]:
            grant_access(branch)
        for spec in specifications[:5]:
            grant_access(spec)
        return grantee, owner, branches, bugs, specifications

    def test_getVisibleArtifacts(self):
        # Test the getVisibleArtifacts method.
        grantee, ignore, branches, bugs, specs = self._make_Artifacts()
        # Check the results.
        shared_bugs, shared_branches, shared_specs = (
            self.service.getVisibleArtifacts(grantee, branches, bugs, specs))
        self.assertContentEqual(bugs[:5], shared_bugs)
        self.assertContentEqual(branches[:5], shared_branches)
        self.assertContentEqual(specs[:5], shared_specs)

    def test_getVisibleArtifacts_grant_on_pillar(self):
        # getVisibleArtifacts() returns private specifications if
        # user has a policy grant for the pillar of the specification.
        ignore, owner, branches, bugs, specs = self._make_Artifacts()
        shared_bugs, shared_branches, shared_specs = (
            self.service.getVisibleArtifacts(owner, branches, bugs, specs))
        self.assertContentEqual(bugs, shared_bugs)
        self.assertContentEqual(branches, shared_branches)
        self.assertContentEqual(specs, shared_specs)

    def test_getInvisibleArtifacts(self):
        # Test the getInvisibleArtifacts method.
        grantee, ignore, branches, bugs, specs = self._make_Artifacts()
        # Check the results.
        not_shared_bugs, not_shared_branches = (
            self.service.getInvisibleArtifacts(grantee, branches, bugs))
        self.assertContentEqual(bugs[5:], not_shared_bugs)
        self.assertContentEqual(branches[5:], not_shared_branches)

    def _assert_getVisibleArtifacts_bug_change(self, change_callback):
        # Test the getVisibleArtifacts method excludes bugs after a change of
        # information_type or bugtask re-targetting.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(owner=owner)
        grantee = self.factory.makePerson()
        login_person(owner)

        [policy] = getUtility(IAccessPolicySource).find(
            [(product, InformationType.USERDATA)])
        self.factory.makeAccessPolicyGrant(
            policy, grantee=grantee, grantor=owner)

        bugs = []
        for x in range(0, 10):
            bug = self.factory.makeBug(
                target=product, owner=owner,
                information_type=InformationType.USERDATA)
            bugs.append(bug)

        shared_bugs, shared_branches, shared_specs = (
            self.service.getVisibleArtifacts(grantee, bugs=bugs))
        self.assertContentEqual(bugs, shared_bugs)

        # Change some bugs.
        for x in range(0, 5):
            change_callback(bugs[x], owner)
        # Check the results.
        shared_bugs, shared_branches, shared_specs = (
            self.service.getVisibleArtifacts(grantee, bugs=bugs))
        self.assertContentEqual(bugs[5:], shared_bugs)

    def test_getVisibleArtifacts_bug_policy_change(self):
        # getVisibleArtifacts excludes bugs after change of information type.
        def change_info_type(bug, owner):
            bug.transitionToInformationType(
                InformationType.PRIVATESECURITY, owner)

        self._assert_getVisibleArtifacts_bug_change(change_info_type)

    def test_getVisibleArtifacts_bugtask_retarget(self):
        # Test the getVisibleArtifacts method excludes items after a bugtask
        # is re-targetted to a new pillar.
        another_product = self.factory.makeProduct()

        def retarget_bugtask(bug, owner):
            bug.default_bugtask.transitionToTarget(another_product, owner)

        self._assert_getVisibleArtifacts_bug_change(retarget_bugtask)

    def test_checkPillarAccess(self):
        # checkPillarAccess checks whether the user has full access to
        # an information type.
        product = self.factory.makeProduct()
        right_person = self.factory.makePerson()
        right_team = self.factory.makeTeam(members=[right_person])
        wrong_person = self.factory.makePerson()
        with admin_logged_in():
            self.service.sharePillarInformation(
                product, right_team, product.owner,
                {InformationType.USERDATA: SharingPermission.ALL})
            self.service.sharePillarInformation(
                product, wrong_person, product.owner,
                {InformationType.PRIVATESECURITY: SharingPermission.ALL})
        self.assertFalse(
            self.service.checkPillarAccess(
                [product], InformationType.USERDATA, wrong_person))
        self.assertTrue(
            self.service.checkPillarAccess(
                [product], InformationType.USERDATA, right_person))

    def test_checkPillarArtifactAccess_respects_teams(self):
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(
            information_type=InformationType.PROPRIETARY, owner=owner)
        user = self.factory.makePerson()
        team = self.factory.makeTeam(
            membership_policy=TeamMembershipPolicy.MODERATED, members=[user])
        with person_logged_in(owner):
            bug = self.factory.makeBug(target=product)
            bug.subscribe(team, owner)
        self.assertTrue(self.service.checkPillarArtifactAccess(product, user))

    def test_checkPillarAccess_no_policy(self):
        # checkPillarAccess returns False if there's no policy.
        self.assertFalse(
            self.service.checkPillarAccess(
                [self.factory.makeProduct()], InformationType.PUBLIC,
                self.factory.makePerson()))

    def test_getAccessPolicyGrantCounts(self):
        # checkPillarAccess checks whether the user has full access to
        # an information type.
        product = self.factory.makeProduct()
        grantee = self.factory.makePerson()
        with admin_logged_in():
            self.service.sharePillarInformation(
                product, grantee, product.owner,
                {InformationType.USERDATA: SharingPermission.ALL})
        # The owner is granted access on product creation. So we need to allow
        # for that in the check below.
        self.assertContentEqual(
            [(InformationType.PRIVATESECURITY, 1),
             (InformationType.USERDATA, 2)],
            self.service.getAccessPolicyGrantCounts(product))

    def test_getAccessPolicyGrantCountsZero(self):
        # checkPillarAccess checks whether the user has full access to
        # an information type.
        product = self.factory.makeProduct()
        with admin_logged_in():
            self.service.deletePillarGrantee(
                product, product.owner, product.owner)
        self.assertContentEqual(
            [(InformationType.PRIVATESECURITY, 0),
             (InformationType.USERDATA, 0)],
            self.service.getAccessPolicyGrantCounts(product))


class ApiTestMixin:
    """Common tests for launchpadlib and webservice."""

    def setUp(self):
        super(ApiTestMixin, self).setUp()
        self.owner = self.factory.makePerson(name='thundercat')
        self.pillar = self.factory.makeProduct(
            owner=self.owner, specification_sharing_policy=(
            SpecificationSharingPolicy.PUBLIC_OR_PROPRIETARY))
        self.grantee = self.factory.makePerson(name='grantee')
        self.grantor = self.factory.makePerson()
        self.grantee_uri = canonical_url(self.grantee, force_local_path=True)
        self.grantor_uri = canonical_url(self.grantor, force_local_path=True)
        self.bug = self.factory.makeBug(
            owner=self.owner, target=self.pillar,
            information_type=InformationType.PRIVATESECURITY)
        self.branch = self.factory.makeBranch(
            owner=self.owner, product=self.pillar,
            information_type=InformationType.PRIVATESECURITY)
        self.spec = self.factory.makeSpecification(
            product=self.pillar, owner=self.owner,
            information_type=InformationType.PROPRIETARY)
        login_person(self.owner)
        self.bug.subscribe(self.grantee, self.owner)
        self.branch.subscribe(
            self.grantee, BranchSubscriptionNotificationLevel.NOEMAIL,
            None, CodeReviewNotificationLevel.NOEMAIL, self.owner)
        getUtility(IService, 'sharing').ensureAccessGrants(
            [self.grantee], self.grantor, specifications=[self.spec])
        transaction.commit()

    def test_getPillarGranteeData(self):
        # Test the getPillarGranteeData method.
        json_data = self._getPillarGranteeData()
        [grantee_data] = [d for d in json_data
                        if d['name'] != 'thundercat']
        self.assertEqual('grantee', grantee_data['name'])
        self.assertEqual(
            {InformationType.USERDATA.name: SharingPermission.ALL.name,
             InformationType.PRIVATESECURITY.name:
                 SharingPermission.SOME.name,
             InformationType.PROPRIETARY.name: SharingPermission.SOME.name},
            grantee_data['permissions'])


class TestWebService(ApiTestMixin, WebServiceTestCase):
    """Test the web service interface for the Sharing Service."""

    def setUp(self):
        super(TestWebService, self).setUp()
        self.webservice = LaunchpadWebServiceCaller(
            'launchpad-library', 'salgado-change-anything')
        self._sharePillarInformation(self.pillar)

    def test_url(self):
        # Test that the url for the service is correct.
        service = SharingService()
        root_app = getUtility(ILaunchpadRoot)
        self.assertEqual(
            '%s+services/sharing' % canonical_url(root_app),
            canonical_url(service))

    def _named_get(self, api_method, **kwargs):
        return self.webservice.named_get(
            '/+services/sharing',
            api_method, api_version='devel', **kwargs).jsonBody()

    def _named_post(self, api_method, **kwargs):
        return self.webservice.named_post(
            '/+services/sharing',
            api_method, api_version='devel', **kwargs).jsonBody()

    def _getPillarGranteeData(self):
        pillar_uri = canonical_url(
            removeSecurityProxy(self.pillar), force_local_path=True)
        return self._named_get(
            'getPillarGranteeData', pillar=pillar_uri)

    def _sharePillarInformation(self, pillar):
        pillar_uri = canonical_url(
            removeSecurityProxy(pillar), force_local_path=True)
        return self._named_post(
            'sharePillarInformation', pillar=pillar_uri,
            grantee=self.grantee_uri,
            user=self.grantor_uri,
            permissions={
                InformationType.USERDATA.title:
                SharingPermission.ALL.title})


class TestLaunchpadlib(ApiTestMixin, TestCaseWithFactory):
    """Test launchpadlib access for the Sharing Service."""

    layer = AppServerLayer

    def setUp(self):
        super(TestLaunchpadlib, self).setUp()
        self.launchpad = self.factory.makeLaunchpadService(person=self.owner)
        self.service = self.launchpad.load('+services/sharing')
        transaction.commit()
        self._sharePillarInformation(self.pillar)

    def _getPillarGranteeData(self):
        ws_pillar = ws_object(self.launchpad, self.pillar)
        return self.service.getPillarGranteeData(pillar=ws_pillar)

    def _sharePillarInformation(self, pillar):
        ws_pillar = ws_object(self.launchpad, pillar)
        ws_grantee = ws_object(self.launchpad, self.grantee)
        return self.service.sharePillarInformation(pillar=ws_pillar,
            grantee=ws_grantee,
            permissions={
                InformationType.USERDATA.title: SharingPermission.ALL.title}
        )

    def test_getSharedProjects(self):
        # Test the exported getSharedProjects() method.
        ws_grantee = ws_object(self.launchpad, self.grantee)
        products = self.service.getSharedProjects(person=ws_grantee)
        self.assertEqual(1, len(products))
        self.assertEqual(products[0].name, self.pillar.name)

    def test_getSharedDistributions(self):
        # Test the exported getSharedDistributions() method.
        distro = self.factory.makeDistribution(owner=self.owner)
        transaction.commit()
        self._sharePillarInformation(distro)
        ws_grantee = ws_object(self.launchpad, self.grantee)
        distros = self.service.getSharedDistributions(person=ws_grantee)
        self.assertEqual(1, len(distros))
        self.assertEqual(distros[0].name, distro.name)

    def test_getSharedBugs(self):
        # Test the exported getSharedBugs() method.
        ws_pillar = ws_object(self.launchpad, self.pillar)
        ws_grantee = ws_object(self.launchpad, self.grantee)
        bugtasks = self.service.getSharedBugs(
            pillar=ws_pillar, person=ws_grantee)
        self.assertEqual(1, len(bugtasks))
        self.assertEqual(bugtasks[0].title, self.bug.default_bugtask.title)

    def test_getSharedBranches(self):
        # Test the exported getSharedBranches() method.
        ws_pillar = ws_object(self.launchpad, self.pillar)
        ws_grantee = ws_object(self.launchpad, self.grantee)
        branches = self.service.getSharedBranches(
            pillar=ws_pillar, person=ws_grantee)
        self.assertEqual(1, len(branches))
        self.assertEqual(branches[0].unique_name, self.branch.unique_name)

    def test_getSharedSpecifications(self):
        # Test the exported getSharedSpecifications() method.
        ws_pillar = ws_object(self.launchpad, self.pillar)
        ws_grantee = ws_object(self.launchpad, self.grantee)
        specifications = self.service.getSharedSpecifications(
            pillar=ws_pillar, person=ws_grantee)
        self.assertEqual(1, len(specifications))
        self.assertEqual(specifications[0].name, self.spec.name)

    def test_getSharedArtifacts(self):
        # Test the exported getSharedArtifacts() method.
        ws_pillar = ws_object(self.launchpad, self.pillar)
        ws_grantee = ws_object(self.launchpad, self.grantee)
        (bugtasks, branches, specs) = self.service.getSharedArtifacts(
            pillar=ws_pillar, person=ws_grantee)
        self.assertEqual(1, len(bugtasks))
        self.assertEqual(1, len(branches))
        self.assertEqual(1, len(specs))
        self.assertEqual(bugtasks[0]['title'], self.bug.default_bugtask.title)
        self.assertEqual(branches[0]['unique_name'], self.branch.unique_name)
