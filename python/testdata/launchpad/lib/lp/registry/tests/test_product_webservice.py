# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

import json

from lazr.uri import URI
from testtools.matchers import MatchesStructure
from zope.security.proxy import removeSecurityProxy

from lp.registry.enums import (
    BranchSharingPolicy,
    BugSharingPolicy,
    )
from lp.services.webapp.interfaces import OAuthPermission
from lp.services.webapp.publisher import canonical_url
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.pages import (
    LaunchpadWebServiceCaller,
    webservice_for_person,
    )


class TestProductAlias(TestCaseWithFactory):
    """Aliases should behave well with the webservice."""

    layer = DatabaseFunctionalLayer

    def test_alias_redirects_in_webservice(self):
        # When a redirect occurs for a product, it should remain in the
        # webservice.
        product = self.factory.makeProduct(name='lemur')
        removeSecurityProxy(product).setAliases(['monkey'])
        webservice = LaunchpadWebServiceCaller(
            'launchpad-library', 'salgado-change-anything')
        response = webservice.get('/monkey')
        self.assertEqual(
            'http://api.launchpad.dev/beta/lemur',
            response.getheader('location'))


class TestProduct(TestCaseWithFactory):
    """Webservice tests for products."""

    layer = DatabaseFunctionalLayer

    def patch(self, webservice, obj, **data):
        with person_logged_in(webservice.user):
            path = URI(canonical_url(obj)).path
        return webservice.patch(
            path, 'application/json', json.dumps(data), api_version='devel')

    def test_branch_sharing_policy_can_be_set(self):
        # branch_sharing_policy can be set via the API.
        product = self.factory.makeProduct()
        owner = product.owner
        self.factory.makeCommercialSubscription(product=product)
        webservice = webservice_for_person(
            owner, permission=OAuthPermission.WRITE_PRIVATE)
        response = self.patch(
            webservice, product, branch_sharing_policy='Proprietary')
        self.assertEqual(209, response.status)
        with person_logged_in(owner):
            self.assertEqual(
                BranchSharingPolicy.PROPRIETARY, product.branch_sharing_policy)

    def test_branch_sharing_policy_non_commercial(self):
        # An API attempt to set a commercial-only branch_sharing_policy
        # on a non-commercial project returns Forbidden.
        product = self.factory.makeProduct()
        owner = product.owner
        webservice = webservice_for_person(
            product.owner, permission=OAuthPermission.WRITE_PRIVATE)
        response = self.patch(
            webservice, product, branch_sharing_policy='Proprietary')
        self.assertThat(response, MatchesStructure.byEquality(
                status=403,
                body=('A current commercial subscription is required to use '
                      'proprietary branches.')))
        with person_logged_in(owner):
            self.assertEqual(
                BranchSharingPolicy.PUBLIC, product.branch_sharing_policy)

    def test_bug_sharing_policy_can_be_set(self):
        # bug_sharing_policy can be set via the API.
        product = self.factory.makeProduct()
        owner = product.owner
        self.factory.makeCommercialSubscription(product=product)
        webservice = webservice_for_person(
            product.owner, permission=OAuthPermission.WRITE_PRIVATE)
        response = self.patch(
            webservice, product, bug_sharing_policy='Proprietary')
        self.assertEqual(209, response.status)
        with person_logged_in(owner):
            self.assertEqual(
                BugSharingPolicy.PROPRIETARY, product.bug_sharing_policy)

    def test_bug_sharing_policy_non_commercial(self):
        # An API attempt to set a commercial-only bug_sharing_policy
        # on a non-commercial project returns Forbidden.
        product = self.factory.makeProduct()
        owner = product.owner
        webservice = webservice_for_person(
            product.owner, permission=OAuthPermission.WRITE_PRIVATE)
        response = self.patch(
            webservice, product, bug_sharing_policy='Proprietary')
        self.assertThat(response, MatchesStructure.byEquality(
                status=403,
                body=('A current commercial subscription is required to use '
                      'proprietary bugs.')))
        with person_logged_in(owner):
            self.assertEqual(
                BugSharingPolicy.PUBLIC, product.bug_sharing_policy)

    def fetch_product(self, webservice, product, api_version):
        with person_logged_in(webservice.user):
            url = canonical_url(product, force_local_path=True)
        return webservice.get(url, api_version=api_version).jsonBody()

    def test_security_contact_exported(self):
        # security_contact is exported for 1.0, but not for other versions.
        product = self.factory.makeProduct()
        webservice = webservice_for_person(product.owner)
        api_prod = self.fetch_product(webservice, product, '1.0')
        self.assertIs(None, api_prod['security_contact'])
        for api_version in ('beta', 'devel'):
            api_prod = self.fetch_product(webservice, product, api_version)
            self.assertNotIn('security_contact', api_prod)
