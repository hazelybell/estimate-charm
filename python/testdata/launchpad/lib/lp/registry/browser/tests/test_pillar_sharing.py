# Copyright 2012-2013 Canonical Ltd. This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test views that manage sharing."""

__metaclass__ = type

from BeautifulSoup import BeautifulSoup
from fixtures import FakeLogger
from lazr.restful.interfaces import IJSONRequestCache
from lazr.restful.utils import get_current_web_service_request
import simplejson
from testtools.matchers import (
    LessThan,
    MatchesException,
    Not,
    Raises,
    )
from zope.component import getUtility
from zope.traversing.browser.absoluteurl import absoluteURL

from lp.app.enums import InformationType
from lp.app.interfaces.services import IService
from lp.registry.enums import (
    BranchSharingPolicy,
    BugSharingPolicy,
    )
from lp.registry.interfaces.accesspolicy import IAccessPolicyGrantFlatSource
from lp.registry.model.pillar import PillarPerson
from lp.services.config import config
from lp.services.database.interfaces import IStore
from lp.services.webapp.interfaces import StormRangeFactoryError
from lp.services.webapp.publisher import canonical_url
from lp.testing import (
    login_person,
    logout,
    person_logged_in,
    StormStatementRecorder,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.matchers import HasQueryCount
from lp.testing.pages import setupBrowserForUser
from lp.testing.views import (
    create_initialized_view,
    create_view,
    )


class SharingBaseTestCase(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    pillar_type = None

    def setUp(self):
        super(SharingBaseTestCase, self).setUp()
        self.driver = self.factory.makePerson()
        self.owner = self.factory.makePerson()
        if self.pillar_type == 'distribution':
            self.pillar = self.factory.makeDistribution(
                owner=self.owner, driver=self.driver)
        elif self.pillar_type == 'product':
            self.pillar = self.factory.makeProduct(
                owner=self.owner, driver=self.driver,
                bug_sharing_policy=BugSharingPolicy.PUBLIC,
                branch_sharing_policy=BranchSharingPolicy.PUBLIC)
        self.access_policy = self.factory.makeAccessPolicy(
            pillar=self.pillar, type=InformationType.PROPRIETARY)
        self.grantees = []

    def makeGrantee(self, name=None):
        grantee = self.factory.makePerson(name=name)
        self.factory.makeAccessPolicyGrant(self.access_policy, grantee)
        return grantee

    def makeArtifactGrantee(self, grantee=None, with_bug=True,
                            with_branch=False, security=False):
        if grantee is None:
            grantee = self.factory.makePerson()

        branch = None
        bug = None
        artifacts = []

        if with_branch and self.pillar_type == 'product':
            branch = self.factory.makeBranch(
                product=self.pillar, owner=self.pillar.owner,
                information_type=InformationType.PRIVATESECURITY)
            artifacts.append(
                self.factory.makeAccessArtifact(concrete=branch))

        if with_bug:
            if security:
                owner = self.factory.makePerson()
            else:
                owner = self.pillar.owner
            bug = self.factory.makeBug(
                target=self.pillar, owner=owner,
                information_type=InformationType.USERDATA)
            artifacts.append(
                self.factory.makeAccessArtifact(concrete=bug))

        for artifact in artifacts:
            self.factory.makeAccessArtifactGrant(
                artifact=artifact, grantee=grantee, grantor=self.pillar.owner)
        return grantee

    def setupSharing(self, grantees):
        with person_logged_in(self.owner):
            # Make grants in ascending order so we can slice off the first
            # elements in the pillar observer results to check batching.
            for x in range(10):
                self.makeArtifactGrantee()
                grantee = self.makeGrantee('name%s' % x)
                grantees.append(grantee)


class PillarSharingDetailsMixin:
    """Test the pillar sharing details view."""

    def getPillarPerson(self, person=None, security=False):
        person = self.makeArtifactGrantee(person, True, True, security)
        return PillarPerson(self.pillar, person)

    def test_view_filters_security_wisely(self):
        # There are bugs in the sharingdetails view that not everyone with
        # `launchpad.Driver` -- the permission level for the page -- should be
        # able to see.
        pillarperson = self.getPillarPerson(security=True)
        logout()
        login_person(self.driver)
        view = create_initialized_view(pillarperson, '+index')
        # The page loads
        self.assertEqual(pillarperson.person.displayname, view.page_title)
        # The bug, which is not shared with the driver, is not included.
        self.assertEqual(0, view.shared_bugs_count)

    def test_view_traverses_plus_sharingdetails(self):
        # The traversed url in the app is pillar/+sharing/person
        # We have to do some fun url hacking to force the traversal a user
        # encounters.
        pillarperson = self.getPillarPerson()
        expected = "Sharing details for %s : Sharing : %s" % (
                pillarperson.person.displayname,
                pillarperson.pillar.displayname)
        url = 'http://launchpad.dev/%s/+sharing/%s' % (
            pillarperson.pillar.name, pillarperson.person.name)
        browser = self.getUserBrowser(user=self.owner, url=url)
        self.assertEqual(expected, browser.title)

    def test_no_sharing_message(self):
        # If there is no sharing between pillar and person, a suitable message
        # is displayed.
        # We have to do some fun url hacking to force the traversal a user
        # encounters.
        pillarperson = PillarPerson(
            self.pillar, self.factory.makePerson())
        url = 'http://launchpad.dev/%s/+sharing/%s' % (
            pillarperson.pillar.name, pillarperson.person.name)
        browser = self.getUserBrowser(user=self.owner, url=url)
        self.assertIn(
            'There are no shared bugs, branches, or blueprints.',
            browser.contents)

    def test_init_works(self):
        # The view works with a feature flag.
        pillarperson = self.getPillarPerson()
        view = create_initialized_view(pillarperson, '+index')
        self.assertEqual(pillarperson.person.displayname, view.page_title)
        self.assertEqual(1, view.shared_bugs_count)

    def test_view_data_model(self):
        # Test that the json request cache contains the view data model.
        pillarperson = self.getPillarPerson()
        view = create_initialized_view(pillarperson, '+index')
        bugtask = list(view.bugtasks)[0]
        bug = bugtask.bug
        cache = IJSONRequestCache(view.request)
        request = get_current_web_service_request()
        self.assertEqual({
            'self_link': absoluteURL(pillarperson.person, request),
            'displayname': pillarperson.person.displayname
        }, cache.objects.get('grantee'))
        self.assertEqual({
            'self_link': absoluteURL(pillarperson.pillar, request),
        }, cache.objects.get('pillar'))
        self.assertEqual({
            'bug_id': bug.id,
            'bug_summary': bug.title,
            'bug_importance': bugtask.importance.title.lower(),
            'information_type': bug.information_type.title,
            'web_link': canonical_url(
                bugtask, path_only_if_possible=True),
            'self_link': absoluteURL(bug, request),
        }, cache.objects.get('bugs')[0])
        if self.pillar_type == 'product':
            branch = list(view.branches)[0]
            self.assertEqual({
                'branch_id': branch.id,
                'branch_name': branch.unique_name,
                'information_type': branch.information_type.title,
                'web_link': canonical_url(branch, path_only_if_possible=True),
                'self_link': absoluteURL(branch, request),
            }, cache.objects.get('branches')[0])

    def test_view_query_count(self):
        # Test that the view bulk loads artifacts.
        person = self.factory.makePerson()
        for x in range(0, 15):
            self.makeArtifactGrantee(person, True, True, False)
        pillarperson = PillarPerson(self.pillar, person)

        # Invalidate the Storm cache and check the query count.
        IStore(self.pillar).invalidate()
        with StormStatementRecorder() as recorder:
            create_initialized_view(pillarperson, '+index')
        self.assertThat(recorder, HasQueryCount(LessThan(13)))


class TestProductSharingDetailsView(
    SharingBaseTestCase, PillarSharingDetailsMixin):

    pillar_type = 'product'

    def setUp(self):
        super(TestProductSharingDetailsView, self).setUp()
        login_person(self.owner)


class TestDistributionSharingDetailsView(
    SharingBaseTestCase, PillarSharingDetailsMixin):

    pillar_type = 'distribution'

    def setUp(self):
        super(TestDistributionSharingDetailsView, self).setUp()
        login_person(self.owner)


class PillarSharingViewTestMixin:
    """Test the PillarSharingView."""

    def test_sharing_menu(self):
        url = canonical_url(self.pillar)
        sharing_url = canonical_url(self.pillar, view_name='+sharing')
        browser = setupBrowserForUser(user=self.driver)
        browser.open(url)
        soup = BeautifulSoup(browser.contents)
        sharing_menu = soup.find('a', {'href': sharing_url})
        self.assertIsNotNone(sharing_menu)

    def test_picker_config(self):
        # Test the config passed to the disclosure sharing picker.
        view = create_view(self.pillar, name='+sharing')
        picker_config = simplejson.loads(view.json_sharing_picker_config)
        self.assertTrue('vocabulary_filters' in picker_config)
        self.assertEqual('Share project information', picker_config['header'])
        self.assertEqual(
            'Search for user or exclusive team with whom to share',
            picker_config['steptitle'])
        self.assertEqual('NewPillarGrantee', picker_config['vocabulary'])

    def test_view_data_model(self):
        # Test that the json request cache contains the view data model.
        view = create_initialized_view(self.pillar, name='+sharing')
        cache = IJSONRequestCache(view.request)
        self.assertIsNotNone(cache.objects.get('information_types'))
        self.assertIsNotNone(cache.objects.get('branch_sharing_policies'))
        self.assertIsNotNone(cache.objects.get('bug_sharing_policies'))
        self.assertIsNotNone(cache.objects.get('sharing_permissions'))
        self.assertIsNotNone(
            cache.objects.get('specification_sharing_policies'))
        batch_size = config.launchpad.default_batch_size
        apgfs = getUtility(IAccessPolicyGrantFlatSource)
        grantees = apgfs.findGranteePermissionsByPolicy(
            [self.access_policy], self.grantees[:batch_size])
        sharing_service = getUtility(IService, 'sharing')
        grantee_data = sharing_service.jsonGranteeData(grantees)
        self.assertContentEqual(
            grantee_data, cache.objects.get('grantee_data'))

    def test_view_batch_data(self):
        # Test the expected batching data is in the json request cache.
        view = create_initialized_view(self.pillar, name='+sharing')
        cache = IJSONRequestCache(view.request)
        # Test one expected data value (there are many).
        next_batch = view.grantees().batch.nextBatch()
        self.assertContentEqual(
            next_batch.range_memo, cache.objects.get('next')['memo'])

    def test_view_range_factory(self):
        # Test the view range factory is properly configured.
        view = create_initialized_view(self.pillar, name='+sharing')
        range_factory = view.grantees().batch.range_factory

        def test_range_factory():
            row = range_factory.resultset.get_plain_result_set()[0]
            range_factory.getOrderValuesFor(row)

        self.assertThat(
            test_range_factory,
            Not(Raises(MatchesException(StormRangeFactoryError))))

    def test_view_query_count(self):
        # Test the query count is within expected limit.
        view = create_view(self.pillar, name='+sharing')
        with StormStatementRecorder() as recorder:
            view.initialize()
        self.assertThat(recorder, HasQueryCount(LessThan(11)))

    def test_view_invisible_information_types(self):
        # Test the expected invisible information type  data is in the
        # json request cache.
        with person_logged_in(self.pillar.owner):
            getUtility(IService, 'sharing').deletePillarGrantee(
                self.pillar, self.pillar.owner, self.pillar.owner)
        view = create_initialized_view(self.pillar, name='+sharing')
        cache = IJSONRequestCache(view.request)
        self.assertContentEqual(
            ['Private Security', 'Private'],
            cache.objects.get('invisible_information_types'))

    def run_sharing_message_test(self, pillar, owner, public):
        with person_logged_in(owner):
            public_pillar_sharing_info = (
                "Everyone can see %s's public information."
                % pillar.displayname)
            url = canonical_url(pillar, view_name='+sharing')
        browser = setupBrowserForUser(user=owner)
        browser.open(url)
        if public:
            self.assertTrue(public_pillar_sharing_info in browser.contents)
            self.assertFalse(
                "This project has no public information." in browser.contents)
        else:
            self.assertFalse(public_pillar_sharing_info in browser.contents)
            self.assertTrue(
                "This project has no public information." in browser.contents)

    def test_who_its_shared_with__public_pillar(self):
        # For public projects and distributions, the sharing page
        # shows the message "Everyone can see project's public
        # information".
        self.run_sharing_message_test(
            self.pillar, self.pillar.owner, public=True)


class TestProductSharingView(PillarSharingViewTestMixin,
                                 SharingBaseTestCase):
    """Test the PillarSharingView with products."""

    pillar_type = 'product'

    def setUp(self):
        super(TestProductSharingView, self).setUp()
        self.setupSharing(self.grantees)
        login_person(self.driver)
        # Use a FakeLogger fixture to prevent Memcached warnings to be
        # printed to stdout while browsing pages.
        self.useFixture(FakeLogger())

    def test_view_contents_non_commercial_project(self):
        # Non commercial projects are rendered with the correct text.
        url = canonical_url(self.pillar, view_name='+sharing')
        browser = setupBrowserForUser(user=self.driver)
        browser.open(url)
        soup = BeautifulSoup(browser.contents)
        commercial_text = soup.find('p', {'id': 'commercial-project-text'})
        non_commercial_text = soup.find(
            'p', {'id': 'non-commercial-project-text'})
        self.assertIsNone(commercial_text)
        self.assertIsNotNone(non_commercial_text)

    def test_view_contents_commercial_project(self):
        # Commercial projects are rendered with the correct text.
        self.factory.makeCommercialSubscription(self.pillar)
        url = canonical_url(self.pillar, view_name='+sharing')
        browser = setupBrowserForUser(user=self.driver)
        browser.open(url)
        soup = BeautifulSoup(browser.contents)
        commercial_text = soup.find('p', {'id': 'commercial-project-text'})
        non_commercial_text = soup.find(
            'p', {'id': 'non-commercial-project-text'})
        self.assertIsNotNone(commercial_text)
        self.assertIsNone(non_commercial_text)

    def test_who_its_shared_with__proprietary_product(self):
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(
            owner=owner, information_type=InformationType.PROPRIETARY)
        self.run_sharing_message_test(product, owner, public=False)


class TestDistributionSharingView(PillarSharingViewTestMixin,
                                      SharingBaseTestCase):
    """Test the PillarSharingView with distributions."""

    pillar_type = 'distribution'

    def setUp(self):
        super(TestDistributionSharingView, self).setUp()
        self.setupSharing(self.grantees)
        login_person(self.driver)

    def test_view_contents(self):
        # Distributions are rendered with the correct text.
        url = canonical_url(self.pillar, view_name='+sharing')
        browser = setupBrowserForUser(user=self.driver)
        browser.open(url)
        soup = BeautifulSoup(browser.contents)
        commercial_text = soup.find('p', {'id': 'commercial-project-text'})
        non_commercial_text = soup.find(
            'p', {'id': 'non-commercial-project-text'})
        self.assertIsNone(commercial_text)
        self.assertIsNone(non_commercial_text)
