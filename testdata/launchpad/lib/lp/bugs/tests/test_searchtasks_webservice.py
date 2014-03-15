# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Webservice unit tests related to Launchpad Bugs."""

__metaclass__ = type


from lp.app.enums import InformationType
from lp.bugs.interfaces.bugtask import BugTaskStatusSearch
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.pages import LaunchpadWebServiceCaller


class TestOmitTargetedParameter(TestCaseWithFactory):
    """Test all values for the omit_targeted search parameter."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestOmitTargetedParameter, self).setUp()
        self.owner = self.factory.makePerson()
        with person_logged_in(self.owner):
            self.distro = self.factory.makeDistribution(name='mebuntu')
        self.release = self.factory.makeDistroSeries(
            name='inkanyamba', distribution=self.distro)
        self.bug = self.factory.makeBugTask(target=self.release)
        self.webservice = LaunchpadWebServiceCaller(
            'launchpad-library', 'salgado-change-anything')

    def test_omit_targeted_old_default_true(self):
        response = self.webservice.named_get('/mebuntu/inkanyamba',
            'searchTasks', api_version='1.0').jsonBody()
        self.assertEqual(response['total_size'], 0)

    def test_omit_targeted_new_default_false(self):
        response = self.webservice.named_get('/mebuntu/inkanyamba',
            'searchTasks', api_version='devel').jsonBody()
        self.assertEqual(response['total_size'], 1)


class TestProductSearchTasks(TestCaseWithFactory):
    """Tests for the information_type, linked_blueprints and order_by
    parameters."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestProductSearchTasks, self).setUp()
        self.owner = self.factory.makePerson()
        with person_logged_in(self.owner):
            self.product = self.factory.makeProduct()
        self.product_name = self.product.name
        self.bug = self.factory.makeBug(
            target=self.product,
            information_type=InformationType.PRIVATESECURITY)
        self.webservice = LaunchpadWebServiceCaller(
            'launchpad-library', 'salgado-change-anything')

    def search(self, api_version, **kwargs):
        return self.webservice.named_get(
            '/%s' % self.product_name, 'searchTasks',
            api_version=api_version, **kwargs).jsonBody()

    def test_linked_blueprints_in_devel(self):
        # Searching for linked Blueprints works in the devel API.
        self.search("devel", linked_blueprints="Show all bugs")

    def test_linked_blueprints_in_devel_2(self):
        # The linked_blueprints is considered. An error is returned if its
        # value is not a member of BugBlueprintSearch.
        self.assertRaises(
            ValueError, self.search, "devel",
            linked_blueprints="Teabags!")

    def test_linked_blueprints_not_in_1_0(self):
        # Searching for linked Blueprints does not work in the 1.0 API. No
        # validation is performed for the linked_blueprints parameter, and
        # thus no error is returned when we pass rubbish.
        self.search("1.0", linked_blueprints="Teabags!")

    def test_linked_blueprints_not_in_beta(self):
        # Searching for linked Blueprints does not work in the beta API. No
        # validation is performed for the linked_blueprints parameter, and
        # thus no error is returned when we pass rubbish.
        self.search("beta", linked_blueprints="Teabags!")

    def test_search_returns_results(self):
        # A matching search returns results.
        response = self.search(
            "devel", information_type="Private Security")
        self.assertEqual(response['total_size'], 1)

    def test_search_returns_no_results(self):
        # A non-matching search returns no results.
        response = self.search("devel", information_type="Private")
        self.assertEqual(response['total_size'], 0)

    def test_search_with_wrong_orderby(self):
        # Calling searchTasks() with a wrong order_by is a Bad Request.
        response = self.webservice.named_get(
            '/%s' % self.product_name, 'searchTasks',
            api_version='devel', order_by='date_created')
        self.assertEqual(400, response.status)
        self.assertRaisesWithContent(
            ValueError, "Unrecognized order_by: u'date_created'",
            response.jsonBody)

    def test_search_incomplete_status_results(self):
        # The Incomplete status matches Incomplete with response and
        # Incomplete without response bug tasks.
        with person_logged_in(self.owner):
            self.factory.makeBug(
                target=self.product,
                status=BugTaskStatusSearch.INCOMPLETE_WITH_RESPONSE)
            self.factory.makeBug(
                target=self.product,
                status=BugTaskStatusSearch.INCOMPLETE_WITHOUT_RESPONSE)
        response = self.search("devel", status="Incomplete")
        self.assertEqual(response['total_size'], 2)


class TestGetBugData(TestCaseWithFactory):
    """Tests for the /bugs getBugData operation."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestGetBugData, self).setUp()
        self.owner = self.factory.makePerson()
        with person_logged_in(self.owner):
            self.product = self.factory.makeProduct()
        self.bug = self.factory.makeBug(
            target=self.product,
            information_type=InformationType.PRIVATESECURITY)
        self.webservice = LaunchpadWebServiceCaller(
            'launchpad-library', 'salgado-change-anything')

    def search(self, api_version, **kwargs):
        return self.webservice.named_get(
            '/bugs', 'getBugData',
            api_version=api_version, **kwargs).jsonBody()

    def test_search_returns_results(self):
        # A matching search returns results.
        response = self.search(
            "devel", bug_id=self.bug.id)
        self.assertEqual(self.bug.id, response[0]['id'])

    def test_search_returns_no_results(self):
        # A non-matching search returns no results.
        response = self.search("devel", bug_id=0)
        self.assertEqual(len(response), 0)
