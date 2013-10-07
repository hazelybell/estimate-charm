# Copyright 2011-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for Bug Views."""

__metaclass__ = type

from datetime import (
    datetime,
    timedelta,
    )

from BeautifulSoup import BeautifulSoup
import pytz
import simplejson
from soupmatchers import (
    HTMLContains,
    Tag,
    )
from storm.store import Store
from testtools.matchers import (
    Contains,
    Equals,
    MatchesAll,
    Not,
    )
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.app.interfaces.services import IService
from lp.bugs.adapters.bugchange import BugAttachmentChange
from lp.registry.enums import BugSharingPolicy
from lp.registry.interfaces.accesspolicy import (
    IAccessPolicyGrantSource,
    IAccessPolicySource,
    )
from lp.registry.interfaces.person import PersonVisibility
from lp.services.webapp.interfaces import IOpenLaunchBag
from lp.services.webapp.publisher import canonical_url
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.testing import (
    BrowserTestCase,
    login_person,
    person_logged_in,
    StormStatementRecorder,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    )
from lp.testing.matchers import HasQueryCount
from lp.testing.pages import find_tag_by_id
from lp.testing.views import (
    create_initialized_view,
    create_view,
    )


class TestPrivateBugLinks(BrowserTestCase):

    layer = DatabaseFunctionalLayer

    def makeDupeOfPrivateBug(self):
        bug = self.factory.makeBug()
        dupe = self.factory.makeBug()
        with person_logged_in(bug.owner):
            bug.setPrivate(private=True, who=bug.owner)
            dupe.markAsDuplicate(bug)
        return dupe

    def test_private_bugs_are_not_linked_without_permission(self):
        bug = self.makeDupeOfPrivateBug()
        url = canonical_url(bug, rootsite="bugs")
        browser = self.getUserBrowser(url)
        dupe_warning = find_tag_by_id(
            browser.contents,
            'warning-comment-on-duplicate')
        # There is no link in the dupe_warning.
        self.assertTrue('href' not in dupe_warning)


class TestAlsoAffectsLinks(BrowserTestCase):
    """ Tests the rendering of the Also Affects links on the bug index view.

    The links are rendered with a css class 'private-disallow' if they are
    not valid for proprietary bugs.
    """

    layer = DatabaseFunctionalLayer

    def test_also_affects_links_product_bug(self):
        # We expect that both Also Affects links (for project and distro) are
        # disallowed.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(
            bug_sharing_policy=BugSharingPolicy.PROPRIETARY)
        bug = self.factory.makeBug(
            target=product, owner=owner,
            information_type=InformationType.PROPRIETARY)
        url = canonical_url(bug, rootsite="bugs")
        browser = self.getUserBrowser(url, user=owner)
        also_affects = find_tag_by_id(
            browser.contents, 'also-affects-product')
        self.assertIn(
            'private-disallow', also_affects['class'].split(' '))
        also_affects = find_tag_by_id(
            browser.contents, 'also-affects-package')
        self.assertIn(
            'private-disallow', also_affects['class'].split(' '))

    def test_also_affects_links_distro_bug(self):
        # We expect that only the Also Affects Project link is disallowed.
        distro = self.factory.makeDistribution()
        owner = self.factory.makePerson()
        # XXX wgrant 2012-08-30 bug=1041002: Distributions don't have
        # sharing policies yet, so it isn't possible legitimately create
        # a Proprietary distro bug.
        bug = self.factory.makeBug(
            target=distro,
            information_type=InformationType.PRIVATESECURITY, owner=owner)
        removeSecurityProxy(bug).information_type = (
            InformationType.PROPRIETARY)
        url = canonical_url(bug, rootsite="bugs")
        browser = self.getUserBrowser(url, user=owner)
        also_affects = find_tag_by_id(
            browser.contents, 'also-affects-product')
        self.assertIn(
            'private-disallow', also_affects['class'].split(' '))
        also_affects = find_tag_by_id(
            browser.contents, 'also-affects-package')
        self.assertNotIn(
            'private-disallow', also_affects['class'].split(' '))


class TestEmailObfuscated(BrowserTestCase):
    """Test for obfuscated emails on bug pages."""

    layer = DatabaseFunctionalLayer

    email_address = "mark@example.com"

    def getBrowserForBugWithEmail(self, no_login):
        self.bug = self.factory.makeBug(
            title="Title with %s contained" % self.email_address,
            description="Description with %s contained." % self.email_address)
        return self.getViewBrowser(
            self.bug, rootsite="bugs", no_login=no_login)

    def test_user_sees_email_address(self):
        """A logged-in user can see the email address on the page."""
        browser = self.getBrowserForBugWithEmail(no_login=False)
        self.assertEqual(7, browser.contents.count(self.email_address))

    def test_anonymous_sees_not_email_address(self):
        """The anonymous user cannot see the email address on the page."""
        browser = self.getBrowserForBugWithEmail(no_login=True)
        self.assertEqual(0, browser.contents.count(self.email_address))

    def test_bug_description_in_meta_description_anonymous(self):
        browser = self.getBrowserForBugWithEmail(no_login=True)
        soup = BeautifulSoup(browser.contents)
        meat = soup.find('meta', dict(name='description'))
        self.assertThat(meat['content'], MatchesAll(
            Contains('Description with'),
            Not(Contains('@')),
            Contains('...')))  # Ellipsis from hidden address.

    def test_bug_description_in_meta_description_not_anonymous(self):
        browser = self.getBrowserForBugWithEmail(no_login=False)
        soup = BeautifulSoup(browser.contents)
        meat = soup.find('meta', dict(name='description'))
        # Even logged in users get email stripped from the metadata, in case
        # they use a tool that copies it out.
        self.assertThat(meat['content'], MatchesAll(
            Contains('Description with'),
            Not(Contains('@')),
            Contains('...')))  # Ellipsis from hidden address.


class TestBugPortletSubscribers(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBugPortletSubscribers, self).setUp()
        self.target = self.factory.makeProduct()
        bug_owner = self.factory.makePerson(name="bug-owner")
        self.bug = self.factory.makeBug(owner=bug_owner, target=self.target)
        # We need to put the Bug and default BugTask into the LaunchBag
        # because BugContextMenu relies on the LaunchBag to populate its
        # context property
        launchbag = getUtility(IOpenLaunchBag)
        launchbag.add(self.bug)
        launchbag.add(self.bug.default_bugtask)

    def test_edit_subscriptions_link_shown(self):
        request = LaunchpadTestRequest()
        view = create_initialized_view(
            self.bug, name="+portlet-subscription", request=request)
        html = view.render()
        self.assertTrue('menu-link-editsubscriptions' in html)
        self.assertTrue('/+subscriptions' in html)

    def _hasCSSClass(self, html, element_id, css_class):
        # Return True if element with ID `element_id` in `html` has
        # a CSS class `css_class`.
        soup = BeautifulSoup(html)
        element = soup.find(attrs={'id': element_id})
        return css_class in element.get('class', '').split(' ')

    def test_bug_mute_for_individual_structural_subscription(self):
        # If the person has a structural subscription to the pillar,
        # then the mute link will be displayed to them.
        person = self.factory.makePerson(name="a-person")
        with person_logged_in(person):
            self.target.addBugSubscription(person, person)
            self.assertFalse(self.bug.isMuted(person))
            view = create_initialized_view(
                self.bug, name="+portlet-subscription")
            self.assertTrue(view.user_should_see_mute_link,
                            "User should see mute link.")
            contents = view.render()
            self.assertTrue('mute_subscription' in contents,
                            "'mute_subscription' not in contents.")
            self.assertFalse(
                self._hasCSSClass(
                    contents, 'mute-link-container', 'hidden'))
            create_initialized_view(
                self.bug.default_bugtask, name="+mute",
                form={'field.actions.mute': 'Mute bug mail'})
            self.assertTrue(self.bug.isMuted(person))

    def test_mute_subscription_link_shown_for_team_subscription(self):
        # If the person belongs to a team with a structural subscription,
        # then the mute link will be displayed to them.
        person = self.factory.makePerson(name="a-person")
        team_owner = self.factory.makePerson(name="team-owner")
        team = self.factory.makeTeam(owner=team_owner, name="subscribed-team")
        with person_logged_in(team_owner):
            team.addMember(person, team_owner)
            self.target.addBugSubscription(team, team_owner)
        with person_logged_in(person):
            self.assertFalse(self.bug.isMuted(person))
            self.assertTrue(
                self.bug.personIsAlsoNotifiedSubscriber(
                    person), "Person should be a notified subscriber")
            view = create_initialized_view(
                self.bug, name="+portlet-subscription")
            self.assertTrue(view.user_should_see_mute_link,
                            "User should see mute link.")
            contents = view.render()
            self.assertTrue('mute_subscription' in contents,
                            "'mute_subscription' not in contents.")
            self.assertFalse(
                self._hasCSSClass(
                    contents, 'mute-link-container', 'hidden'))
            create_initialized_view(
                self.bug.default_bugtask, name="+mute",
                form={'field.actions.mute': 'Mute bug mail'})
            self.assertTrue(self.bug.isMuted(person))

    def test_mute_subscription_link_hidden_for_non_subscribers(self):
        # If a person is not already subscribed to a bug in some way,
        # the mute link will not be displayed to them.
        person = self.factory.makePerson()
        with person_logged_in(person):
            # The user isn't subscribed or muted already.
            self.assertFalse(self.bug.isSubscribed(person))
            self.assertFalse(self.bug.isMuted(person))
            self.assertFalse(
                self.bug.personIsAlsoNotifiedSubscriber(person))
            view = create_initialized_view(
                self.bug, name="+portlet-subscription")
            self.assertFalse(view.user_should_see_mute_link)
            html = view.render()
            self.assertTrue('mute_subscription' in html)
            # The template uses user_should_see_mute_link to decide
            # whether or not to display the mute link.
            self.assertTrue(
                self._hasCSSClass(html, 'mute-link-container', 'hidden'),
                'No "hidden" CSS class in mute-link-container.')

    def test_mute_subscription_link_not_rendered_for_anonymous(self):
        # If a person is not already subscribed to a bug in some way,
        # the mute link will not be displayed to them.
        view = create_initialized_view(
            self.bug, name="+portlet-subscription")
        self.assertFalse(view.user_should_see_mute_link)
        html = view.render()
        self.assertFalse('mute_subscription' in html)

    def test_mute_subscription_link_shown_if_muted(self):
        # If a person is muted but not otherwise subscribed, they should still
        # see the (un)mute link.
        person = self.factory.makePerson()
        with person_logged_in(person):
            self.bug.mute(person, person)
            # The user isn't subscribed already, but is muted.
            self.assertFalse(self.bug.isSubscribed(person))
            self.assertFalse(
                self.bug.personIsAlsoNotifiedSubscriber(
                    person))
            self.assertTrue(self.bug.isMuted(person))
            view = create_initialized_view(
                self.bug, name="+portlet-subscription")
            self.assertTrue(
                view.user_should_see_mute_link, "User should see mute link.")
            contents = view.render()
            self.assertTrue(
                'mute_subscription' in contents,
                "'mute_subscription' not in contents.")
            self.assertFalse(
                self._hasCSSClass(contents, 'mute-link-container', 'hidden'))

    def test_bug_portlet_subscription_query_count(self):
        # Bug:+portlet-subscription doesn't make O(n) queries based on the
        # number of duplicate bugs.
        user = self.factory.makePerson()
        bug = self.factory.makeBug()
        for n in range(20):
            dupe = self.factory.makeBug()
            removeSecurityProxy(dupe)._markAsDuplicate(bug, set())
            removeSecurityProxy(dupe).subscribe(user, dupe.owner)
        Store.of(bug).invalidate()
        with person_logged_in(user):
            with StormStatementRecorder() as recorder:
                view = create_initialized_view(
                    bug, name='+portlet-subscription', principal=user)
                view.render()
        self.assertThat(recorder, HasQueryCount(Equals(21)))


class TestBugSecrecyViews(TestCaseWithFactory):
    """Tests for the Bug secrecy views."""

    layer = DatabaseFunctionalLayer

    def createInitializedSecrecyView(self, person=None, bug=None,
                                     request=None):
        """Create and return an initialized BugSecrecyView."""
        if person is None:
            person = self.factory.makePerson()
        if bug is None:
            bug = self.factory.makeBug()
        with person_logged_in(person):
            return create_initialized_view(
                bug.default_bugtask, name='+secrecy', form={
                    'field.information_type': 'USERDATA',
                    'field.actions.change': 'Change',
                    }, request=request)

    def test_notification_shown_if_marking_private_and_not_subscribed(self):
        # If a user who is not subscribed to a bug marks that bug as
        # private, the user will be subscribed to the bug. This allows
        # them to un-mark the bug if they choose to, rather than being
        # blocked from doing so.
        view = self.createInitializedSecrecyView()
        bug = view.context.bug
        task = removeSecurityProxy(bug).default_bugtask
        self.assertEqual(1, len(view.request.response.notifications))
        notification = view.request.response.notifications[0].message
        mute_url = canonical_url(task, view_name='+mute')
        subscribe_url = canonical_url(task, view_name='+subscribe')
        self.assertIn(mute_url, notification)
        self.assertIn(subscribe_url, notification)

    def test_no_notification_shown_if_marking_private_and_subscribed(self):
        # If a user who is subscribed to a bug marks that bug as
        # private, the user will see not notification.
        person = self.factory.makePerson()
        bug = self.factory.makeBug()
        with person_logged_in(person):
            bug.subscribe(person, person)
        view = self.createInitializedSecrecyView(person, bug)
        self.assertContentEqual([], view.request.response.notifications)

    def test_no_notification_shown_if_marking_private_and_in_sub_team(self):
        # If a user who is directly subscribed to a bug via a team marks
        # that bug as private, the user will see no notification.
        team = self.factory.makeTeam()
        person = team.teamowner
        bug = self.factory.makeBug()
        with person_logged_in(person):
            bug.subscribe(team, person)
        view = self.createInitializedSecrecyView(person, bug)
        self.assertContentEqual([], view.request.response.notifications)

    def _assert_secrecy_view_ajax_render(self, bug, new_type,
                                         validate_change):
        # When the bug secrecy view is called from an ajax request, it should
        # provide a json encoded dict when rendered. The dict contains bug
        # subscription information resulting from the update to the bug
        # privacy as well as information used to populate the updated
        # subscribers list.
        person = bug.owner
        with person_logged_in(person):
            bug.subscribe(person, person)

        extra = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        request = LaunchpadTestRequest(
            method='POST', form={
                'field.actions.change': 'Change',
                'field.information_type': new_type,
                'field.validate_change':
                    'on' if validate_change else 'off'},
            **extra)
        view = self.createInitializedSecrecyView(person, bug, request)
        result_data = simplejson.loads(view.render())

        cache_data = result_data['cache_data']
        self.assertFalse(cache_data['other_subscription_notifications'])
        subscription_data = cache_data['subscription']
        self.assertEqual(
            'http://launchpad.dev/api/devel/bugs/%s' % bug.id,
            subscription_data['bug_link'])
        self.assertEqual(
            'http://launchpad.dev/api/devel/~%s' % person.name,
            subscription_data['person_link'])
        self.assertEqual(
            'Discussion', subscription_data['bug_notification_level'])
        return result_data

    def test_secrecy_view_ajax_render(self):
        # An information type change request is processed as expected when the
        # bug remains visible to someone and visibility check is performed.
        bug = self.factory.makeBug()
        result_data = self._assert_secrecy_view_ajax_render(
            bug, 'USERDATA', True)
        [subscriber_data] = result_data['subscription_data']
        subscriber = removeSecurityProxy(bug).default_bugtask.pillar.owner
        self.assertEqual(
            subscriber.name, subscriber_data['subscriber']['name'])
        self.assertEqual('Discussion', subscriber_data['subscription_level'])

    def test_secrecy_view_ajax_can_add_tasks(self):
        # The return data contains flags indicating whether project and package
        # tasks can be added.
        bug = self.factory.makeBug()
        result_data = self._assert_secrecy_view_ajax_render(
            bug, 'USERDATA', True)
        self.assertTrue(result_data['can_add_project_task'])
        self.assertTrue(result_data['can_add_package_task'])

    def test_secrecy_view_ajax_render_no_check(self):
        # An information type change request is processed as expected when the
        # bug will become invisible but and no visibility check is performed.
        product = self.factory.makeProduct(
            bug_sharing_policy=BugSharingPolicy.PUBLIC_OR_PROPRIETARY)
        bug = self.factory.makeBug(target=product)
        self._assert_secrecy_view_ajax_render(bug, 'PROPRIETARY', False)

    def test_secrecy_view_ajax_render_invisible_bug(self):
        # When a bug is to be changed to an information type where it will
        # become invisible, and validation checking is used, a 400 response
        # is returned.
        bug_owner = self.factory.makePerson()
        product = self.factory.makeProduct(
            bug_sharing_policy=BugSharingPolicy.PUBLIC_OR_PROPRIETARY)
        bug = self.factory.makeBug(target=product, owner=bug_owner)
        userdata_policy = getUtility(IAccessPolicySource).find(
            [(product, InformationType.USERDATA)])
        getUtility(IAccessPolicyGrantSource).revokeByPolicy(userdata_policy)

        extra = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        request = LaunchpadTestRequest(
            method='POST', form={
                'field.actions.change': 'Change',
                'field.information_type': 'USERDATA',
                'field.validate_change': 'on'},
            **extra)
        with person_logged_in(bug_owner):
            view = create_initialized_view(
                bug.default_bugtask, name='+secrecy', request=request)
        self.assertEqual(
            '400 Bug Visibility', view.request.response.getStatusString())

    def test_set_information_type(self):
        # Test that the bug's information_type can be updated using the
        # view with the feature flag on.
        bug = self.factory.makeBug()
        with person_logged_in(bug.owner):
            view = create_initialized_view(
                bug.default_bugtask, name='+secrecy', form={
                    'field.information_type': 'USERDATA',
                    'field.actions.change': 'Change'})
        self.assertEqual([], view.errors)
        self.assertEqual(InformationType.USERDATA, bug.information_type)

    def test_information_type_vocabulary(self):
        # Test that the view creates the vocabulary correctly.
        bug = self.factory.makeBug()
        with person_logged_in(bug.owner):
            view = create_initialized_view(
                bug.default_bugtask, name='+secrecy',
                principal=bug.owner)
            html = view.render()
            soup = BeautifulSoup(html)
        self.assertEqual(
            u'Private', soup.find('label', text="Private"))

    def test_bugtask_view_user_with_grant_on_bug_for_private_product(self):
        # The regular bug view is properly rendered even if the user
        # does not have permissions to view every detail of a product.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(
            owner=owner,
            information_type=InformationType.PROPRIETARY)
        user = self.factory.makePerson()
        with person_logged_in(owner):
            bug = self.factory.makeBug(
                target=product, information_type=InformationType.PROPRIETARY)
            getUtility(IService, 'sharing').ensureAccessGrants(
                [user], owner, bugs=[bug])
            launchbag = getUtility(IOpenLaunchBag)
            launchbag.add(bug)
            launchbag.add(bug.default_bugtask)
        with person_logged_in(user):
            view = create_initialized_view(
                bug.default_bugtask, name=u'+index', principal=user)
            contents = view.render()
            self.assertTrue(bug.title in contents)


class TestBugTextViewPrivateTeams(TestCaseWithFactory):
    """ Test for rendering BugTextView with private team artifacts.

    If an authenticated user can see the bug, they can see a the name of
    private teams which are assignees or subscribers.
    """
    layer = DatabaseFunctionalLayer

    def _makeBug(self):
        owner = self.factory.makePerson()
        private_assignee = self.factory.makeTeam(
            name='bugassignee',
            visibility=PersonVisibility.PRIVATE)
        private_subscriber = self.factory.makeTeam(
            name='bugsubscriber',
            visibility=PersonVisibility.PRIVATE)

        bug = self.factory.makeBug(owner=owner)
        with person_logged_in(owner):
            bug.default_bugtask.transitionToAssignee(private_assignee)
            bug.subscribe(private_subscriber, owner)
        return bug, private_assignee, private_subscriber

    def test_unauthenticated_view(self):
        # Unauthenticated users cannot see private assignees or subscribers.
        bug, assignee, subscriber = self._makeBug()
        bug_view = create_initialized_view(bug, name='+text')
        view_text = bug_view.render()
        # We don't see the assignee.
        self.assertIn(
            "assignee: \n", view_text)
        # Nor do we see the subscriber.
        self.assertNotIn(
            removeSecurityProxy(subscriber).unique_displayname, view_text)

    def test_authenticated_view(self):
        # Authenticated users can see private assignees or subscribers.
        bug, assignee, subscriber = self._makeBug()
        request = LaunchpadTestRequest()
        bug_view = create_view(bug, name='+text', request=request)
        any_person = self.factory.makePerson()
        login_person(any_person, request)
        bug_view.initialize()
        view_text = bug_view.render()
        naked_subscriber = removeSecurityProxy(subscriber)
        self.assertIn(
            "assignee: %s" % assignee.unique_displayname, view_text)
        self.assertTextMatchesExpressionIgnoreWhitespace(
            "subscribers:\n.*%s \(%s\)"
            % (naked_subscriber.displayname, naked_subscriber.name),
            view_text)


class TestBugCanonicalUrl(BrowserTestCase):
    """Bugs give a <link rel=canonical> to a standard url.

    See https://bugs.launchpad.net/launchpad/+bug/808282
    """
    layer = DatabaseFunctionalLayer

    def test_bug_canonical_url(self):
        bug = self.factory.makeBug()
        browser = self.getViewBrowser(bug, rootsite="bugs")
        # Hardcode this to be sure we've really got what we expected, with no
        # confusion about lp's own url generation machinery.
        expected_url = 'http://bugs.launchpad.dev/bugs/%d' % bug.id
        self.assertThat(
            browser.contents,
            HTMLContains(Tag(
                'link rel=canonical',
                'link',
                dict(rel='canonical', href=expected_url))))


class TestBugMessageAddFormView(TestCaseWithFactory):
    """Tests for the add message to bug view."""
    layer = LaunchpadFunctionalLayer

    def test_whitespaces_message(self):
        # Ensure that a message only containing whitespaces is not
        # considered valid.
        bug = self.factory.makeBug()
        form = {
            'field.comment': u' ',
            'field.actions.save': u'Post Comment',
            }
        view = create_initialized_view(
            bug.default_bugtask, '+addcomment', form=form)
        expected_error = u'Either a comment or attachment must be provided.'
        self.assertEquals(view.errors[0], expected_error)

    def test_whitespaces_message_with_attached_file(self):
        # If the message only contains whitespaces but a file
        # is attached then the request has to be considered valid.
        bug = self.factory.makeBug()
        form = {
            'field.comment': u' ',
            'field.actions.save': u'Post Comment',
            'field.filecontent': self.factory.makeFakeFileUpload(),
            'field.patch.used': u'',
            }
        login_person(self.factory.makePerson())
        view = create_initialized_view(
            bug.default_bugtask, '+addcomment', form=form)
        self.assertEqual(0, len(view.errors))


class TestBugMarkAsDuplicateView(TestCaseWithFactory):
    """Tests for marking a bug as a duplicate."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBugMarkAsDuplicateView, self).setUp()
        self.bug_owner = self.factory.makePerson()
        self.bug = self.factory.makeBug(owner=self.bug_owner)
        self.duplicate_bug = self.factory.makeBug(owner=self.bug_owner)

    def test_remove_link_not_shown_if_no_duplicate(self):
        with person_logged_in(self.bug_owner):
            view = create_initialized_view(
                self.bug.default_bugtask, name="+duplicate",
                principal=self.bug_owner)
            soup = BeautifulSoup(view.render())
        self.assertIsNone(soup.find(attrs={'id': 'field.actions.remove'}))

    def test_remove_link_shown_if_duplicate(self):
        with person_logged_in(self.bug_owner):
            self.bug.markAsDuplicate(self.duplicate_bug)
            view = create_initialized_view(
                self.bug.default_bugtask, name="+duplicate",
                principal=self.bug_owner)
            soup = BeautifulSoup(view.render())
        self.assertIsNotNone(
            soup.find(attrs={'id': 'field.actions.remove'}))

    def test_create_duplicate(self):
        with person_logged_in(self.bug_owner):
            form = {
                'field.actions.change': u'Set Duplicate',
                'field.duplicateof': u'%s' % self.duplicate_bug.id
                }
            create_initialized_view(
                self.bug.default_bugtask, name="+duplicate",
                principal=self.bug_owner, form=form)
        self.assertEqual(self.duplicate_bug, self.bug.duplicateof)

    def test_remove_duplicate(self):
        with person_logged_in(self.bug_owner):
            self.bug.markAsDuplicate(self.duplicate_bug)
            form = {
                'field.actions.remove': u'Remove Duplicate',
                }
            create_initialized_view(
                self.bug.default_bugtask, name="+duplicate",
                principal=self.bug_owner, form=form)
        self.assertIsNone(self.bug.duplicateof)

    def test_ajax_create_duplicate(self):
        # An ajax request to create a duplicate returns the new bugtask table.
        with person_logged_in(self.bug_owner):
            extra = {
                'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest',
                }
            form = {
                'field.actions.change': u'Set Duplicate',
                'field.duplicateof': u'%s' % self.duplicate_bug.id
                }
            view = create_initialized_view(
                self.bug.default_bugtask, name="+duplicate",
                principal=self.bug_owner, form=form, **extra)
            result_html = view.render()

        self.assertEqual(self.duplicate_bug, self.bug.duplicateof)
        self.assertEqual(
            view.request.response.getHeader('content-type'), 'text/html')
        soup = BeautifulSoup(result_html)
        table = soup.find(
            'table',
            {'id': 'affected-software', 'class': 'duplicate listing'})
        self.assertIsNotNone(table)

    def test_ajax_remove_duplicate(self):
        # An ajax request to remove a duplicate returns the new bugtask table.
        with person_logged_in(self.bug_owner):
            self.bug.markAsDuplicate(self.duplicate_bug)
            extra = {
                'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest',
                }
            form = {
                'field.actions.remove': u'Remove Duplicate',
                }

            view = create_initialized_view(
                self.bug.default_bugtask, name="+duplicate",
                principal=self.bug_owner, form=form, **extra)
            result_html = view.render()

        self.assertIsNone(self.bug.duplicateof)
        self.assertEqual(
            view.request.response.getHeader('content-type'), 'text/html')
        soup = BeautifulSoup(result_html)
        table = soup.find(
            'table',
            {'id': 'affected-software', 'class': 'listing'})
        self.assertIsNotNone(table)


class TestBugActivityView(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def test_bug_activity_query_count(self):
        # Bug:+activity doesn't make O(n) queries based on the amount of
        # activity.
        bug = self.factory.makeBug()
        ten_minutes_ago = datetime.now(pytz.UTC) - timedelta(minutes=10)
        with person_logged_in(bug.owner):
            attachment = self.factory.makeBugAttachment(bug=bug)
            for i in range(10):
                bug.addChange(BugAttachmentChange(
                    ten_minutes_ago, self.factory.makePerson(), 'attachment',
                    None, attachment))
        Store.of(bug).invalidate()
        with StormStatementRecorder() as recorder:
            view = create_initialized_view(
                bug.default_bugtask, name='+activity')
            view.render()
        self.assertThat(recorder, HasQueryCount(Equals(7)))


class TestMainBugView(BrowserTestCase):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestMainBugView, self).setUp()
        self.user = self.factory.makePerson()
        self.product_owner = self.factory.makePerson()
        self.proprietary_product = self.factory.makeProduct(
            owner=self.product_owner,
            information_type=InformationType.PROPRIETARY)
        with person_logged_in(self.product_owner):
            self.series = self.factory.makeProductSeries(
                product=self.proprietary_product)
            self.milestone = self.factory.makeMilestone(
                product=self.proprietary_product)
            self.bug = self.factory.makeBug(
                target=self.proprietary_product, owner=self.product_owner)
            self.bug.subscribe(self.user, subscribed_by=self.product_owner)

    def test_bug_page_user_with_aag_proprietary_product(self):
        # A user with an artifact grant for a bug targeted to a private
        # product can view the bug page.
        with person_logged_in(self.user):
            url = canonical_url(self.bug)
            # No exception is raised when the page is rendered.
            self.getUserBrowser(url, user=self.user)

    def test_bug_page_user_with_aag_proprietary_product_milestone_linked(self):
        # A user with an artifact grant for a bug targeted to a private
        # product can view the bug page, even if the bug is linked to
        # milestone.
        with person_logged_in(self.product_owner):
            self.bug.default_bugtask.transitionToMilestone(
                self.milestone, self.product_owner)
        with person_logged_in(self.user):
            url = canonical_url(self.bug)
            # No exception is raised when the page is rendered.
            self.getUserBrowser(url, user=self.user)

    def test_bug_page_user_with_aag_proprietary_product_task_for_series(self):
        # A user with an artifact grant for a bug targeted to a private
        # product series can view the bug page.
        with person_logged_in(self.product_owner):
            self.factory.makeBugTask(
                bug=self.bug, target=self.series)
        with person_logged_in(self.user):
            url = canonical_url(self.bug)
            # No exception is raised when the page is rendered.
            self.getUserBrowser(url, user=self.user)
