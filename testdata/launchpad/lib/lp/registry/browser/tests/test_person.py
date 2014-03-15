# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

import doctest
import email
from textwrap import dedent

import soupmatchers
from storm.store import Store
from testtools.matchers import (
    DocTestMatches,
    Equals,
    LessThan,
    Not,
    )
import transaction
from zope.component import getUtility
from zope.publisher.interfaces import NotFound

from lp.app.browser.lazrjs import TextAreaEditorWidget
from lp.app.enums import InformationType
from lp.app.errors import NotFoundError
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.blueprints.enums import SpecificationImplementationStatus
from lp.buildmaster.enums import BuildStatus
from lp.registry.browser.person import PersonView
from lp.registry.browser.team import TeamInvitationView
from lp.registry.enums import PersonVisibility
from lp.registry.interfaces.karma import IKarmaCacheManager
from lp.registry.interfaces.persontransferjob import IPersonMergeJobSource
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.interfaces.teammembership import (
    ITeamMembershipSet,
    TeamMembershipStatus,
    )
from lp.registry.model.karma import KarmaCategory
from lp.registry.model.milestone import milestone_sort_key
from lp.scripts.garbo import PopulateLatestPersonSourcePackageReleaseCache
from lp.services.config import config
from lp.services.identity.interfaces.account import AccountStatus
from lp.services.identity.interfaces.emailaddress import IEmailAddressSet
from lp.services.log.logger import FakeLogger
from lp.services.mail import stub
from lp.services.verification.interfaces.authtoken import LoginTokenType
from lp.services.verification.interfaces.logintoken import ILoginTokenSet
from lp.services.verification.tests.logintoken import get_token_url_from_email
from lp.services.webapp import canonical_url
from lp.services.webapp.escaping import html_escape
from lp.services.webapp.interfaces import ILaunchBag
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.soyuz.enums import (
    ArchivePurpose,
    ArchiveStatus,
    PackagePublishingStatus,
    )
from lp.soyuz.tests.test_publishing import SoyuzTestPublisher
from lp.testing import (
    ANONYMOUS,
    BrowserTestCase,
    login,
    login_person,
    monkey_patch,
    person_logged_in,
    StormStatementRecorder,
    TestCaseWithFactory,
    )
from lp.testing.dbuser import (
    dbuser,
    switch_dbuser,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    LaunchpadZopelessLayer,
    )
from lp.testing.matchers import HasQueryCount
from lp.testing.pages import (
    extract_text,
    find_tag_by_id,
    setupBrowserForUser,
    )
from lp.testing.views import (
    create_initialized_view,
    create_view,
    )


class PersonViewOpenidIdentityUrlTestCase(TestCaseWithFactory):
    """Tests for the public OpenID identifier shown on the profile page."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.user = self.factory.makePerson(name='eris')
        self.request = LaunchpadTestRequest(
            SERVER_URL="http://launchpad.dev/")
        login_person(self.user, self.request)
        self.view = PersonView(self.user, self.request)
        # Marker allowing us to reset the config.
        config.push(self.id(), '')
        self.addCleanup(config.pop, self.id())

    def test_should_be_profile_page_when_delegating(self):
        """The profile page is the OpenID identifier in normal situation."""
        self.assertEquals(
            'http://launchpad.dev/~eris', self.view.openid_identity_url)

    def test_should_be_production_profile_page_when_not_delegating(self):
        """When the profile page is not delegated, the OpenID identity URL
        should be the one on the main production site."""
        config.push('non-delegating', dedent('''
            [vhost.mainsite]
            openid_delegate_profile: False

            [launchpad]
            non_restricted_hostname: prod.launchpad.dev
            '''))
        self.assertEquals(
            'http://prod.launchpad.dev/~eris', self.view.openid_identity_url)


class TestPersonIndexView(BrowserTestCase):

    layer = DatabaseFunctionalLayer

    def test_isMergePending(self):
        dupe_person = self.factory.makePerson(name='finch')
        target_person = self.factory.makePerson()
        requester = self.factory.makePerson()
        job_source = getUtility(IPersonMergeJobSource)
        job_source.create(from_person=dupe_person, to_person=target_person,
                          requester=requester)
        view = create_initialized_view(dupe_person, name="+index")
        notifications = view.request.response.notifications
        message = 'Finch is queued to be merged in a few minutes.'
        self.assertEqual(1, len(notifications))
        self.assertEqual(message, notifications[0].message)

    def test_display_utcoffset(self):
        person = self.factory.makePerson(time_zone='Asia/Kolkata')
        html = create_initialized_view(person, '+portlet-contact-details')()
        self.assertThat(extract_text(html), DocTestMatches(extract_text(
            "... Asia/Kolkata (UTC+0530) ..."), doctest.ELLIPSIS
            | doctest.NORMALIZE_WHITESPACE | doctest.REPORT_NDIFF))

    def test_description_widget(self):
        # The view provides a widget to render ond edit the person description.
        person = self.factory.makePerson()
        view = create_initialized_view(person, '+index')
        self.assertIsInstance(view.description_widget, TextAreaEditorWidget)
        self.assertEqual(
            'description', view.description_widget.exported_field.__name__)

    def test_description_widget_is_probationary(self):
        # Description text is not linkified when the user is probationary.
        person = self.factory.makePerson()
        view = create_initialized_view(person, '+index')
        self.assertIs(True, person.is_probationary)
        self.assertIs(False, view.description_widget.linkify_text)

    def test_description_widget_non_probationary(self):
        # Description text is linkified when the user is non-probationary.
        person = self.factory.makeTeam()
        view = create_initialized_view(person, '+index')
        self.assertIs(False, person.is_probationary)
        self.assertIs(True, view.description_widget.linkify_text)

    @staticmethod
    def get_markup(view, person):
        def fake_method():
            return canonical_url(person)
        with monkey_patch(view, _getURL=fake_method):
            markup = view.render()
        return markup

    def test_is_probationary_or_invalid_user_with_non_probationary(self):
        team = self.factory.makeTeam()
        view = create_initialized_view(
            team, '+index', principal=team.teamowner)
        self.assertIs(False, view.is_probationary_or_invalid_user)
        markup = view.render()
        self.assertFalse(
            'name="robots" content="noindex,nofollow"' in markup)

    def test_is_probationary_or_invalid_user_with_probationary(self):
        person = self.factory.makePerson()
        view = create_initialized_view(person, '+index', principal=person)
        self.assertIs(True, view.is_probationary_or_invalid_user)
        markup = self.get_markup(view, person)
        self.assertTrue(
            'name="robots" content="noindex,nofollow"' in markup)

    def test_is_probationary_or_invalid_user_with_invalid(self):
        person = self.factory.makePerson(
            account_status=AccountStatus.NOACCOUNT)
        observer = self.factory.makePerson()
        view = create_initialized_view(person, '+index', principal=observer)
        self.assertIs(True, view.is_probationary_or_invalid_user)
        markup = self.get_markup(view, person)
        self.assertTrue(
            'name="robots" content="noindex,nofollow"' in markup)

    def test_person_view_page_description(self):
        person_description = self.factory.getUniqueString()
        person = self.factory.makePerson(description=person_description)
        view = create_initialized_view(person, '+index')
        self.assertThat(view.page_description, Equals(person_description))

    def test_assigned_blueprints(self):
        person = self.factory.makePerson()

        def make_started_spec(information_type):
            enum = SpecificationImplementationStatus
            return self.factory.makeSpecification(
                implementation_status=enum.STARTED, assignee=person,
                information_type=information_type)
        public_spec = make_started_spec(InformationType.PUBLIC)
        private_spec = make_started_spec(InformationType.PROPRIETARY)
        with person_logged_in(None):
            browser = self.getViewBrowser(person)
        self.assertIn(public_spec.name, browser.contents)
        self.assertNotIn(private_spec.name, browser.contents)

    def test_only_assigned_blueprints(self):
        # Only assigned blueprints are listed, not arbitrary related
        # blueprints
        person = self.factory.makePerson()
        spec = self.factory.makeSpecification(
            implementation_status=SpecificationImplementationStatus.STARTED,
            owner=person, drafter=person, approver=person)
        spec.subscribe(person)
        with person_logged_in(None):
            browser = self.getViewBrowser(person)
        self.assertNotIn(spec.name, browser.contents)


class TestPersonViewKarma(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestPersonViewKarma, self).setUp()
        person = self.factory.makePerson()
        product = self.factory.makeProduct()
        transaction.commit()
        self.view = PersonView(
            person, LaunchpadTestRequest())
        self._makeKarmaCache(
            person, product, KarmaCategory.byName('bugs'))
        self._makeKarmaCache(
            person, product, KarmaCategory.byName('answers'))
        self._makeKarmaCache(
            person, product, KarmaCategory.byName('code'))

    def test_karma_category_sort(self):
        categories = self.view.contributed_categories
        category_names = []
        for category in categories:
            category_names.append(category.name)

        self.assertEqual(category_names, [u'code', u'bugs', u'answers'],
                         'Categories are not sorted correctly')

    def _makeKarmaCache(self, person, product, category, value=10):
        """Create and return a KarmaCache entry with the given arguments.

        A commit is implicitly triggered because the 'karma' dbuser is used.
        """
        with dbuser('karma'):
            cache_manager = getUtility(IKarmaCacheManager)
            karmacache = cache_manager.new(
                value, person.id, category.id, product_id=product.id)

            try:
                cache_manager.updateKarmaValue(
                    value, person.id, category_id=None, product_id=product.id)
            except NotFoundError:
                cache_manager.new(
                    value, person.id, category_id=None, product_id=product.id)

        return karmacache


class TestShouldShowPpaSection(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.owner = self.factory.makePerson(name='mowgli')
        self.person_ppa = self.factory.makeArchive(owner=self.owner)
        self.team = self.factory.makeTeam(name='jbook', owner=self.owner)

        # The team is the owner of the PPA.
        self.team_ppa = self.factory.makeArchive(owner=self.team)
        self.team_view = PersonView(self.team, LaunchpadTestRequest())

    def make_ppa_private(self, ppa):
        """Helper method to privatise a ppa."""
        login('foo.bar@canonical.com')
        ppa.private = True
        ppa.buildd_secret = "secret"
        login(ANONYMOUS)

    def test_viewing_person_with_public_ppa(self):
        # Show PPA section only if context has at least one PPA the user is
        # authorised to view the PPA.
        login(ANONYMOUS)
        person_view = PersonView(self.owner, LaunchpadTestRequest())
        self.failUnless(person_view.should_show_ppa_section)

    def test_viewing_person_without_ppa(self):
        # If the context person does not have a ppa then the section
        # should not display.
        login(ANONYMOUS)
        person_without_ppa = self.factory.makePerson()
        person_view = PersonView(person_without_ppa, LaunchpadTestRequest())
        self.failIf(person_view.should_show_ppa_section)

    def test_viewing_self(self):
        # If the current user has edit access to the context person then
        # the section should always display.
        login_person(self.owner)
        person_view = PersonView(self.owner, LaunchpadTestRequest())
        self.failUnless(person_view.should_show_ppa_section)

        # If the ppa is private, the section is still displayed to
        # a user with edit access to the person.
        self.make_ppa_private(self.person_ppa)
        login_person(self.owner)
        person_view = PersonView(self.owner, LaunchpadTestRequest())
        self.failUnless(person_view.should_show_ppa_section)

        # Even a person without a PPA will see the section when viewing
        # themselves.
        person_without_ppa = self.factory.makePerson()
        login_person(person_without_ppa)
        person_view = PersonView(person_without_ppa, LaunchpadTestRequest())
        self.failUnless(person_view.should_show_ppa_section)

    def test_anon_viewing_person_with_private_ppa(self):
        # If the ppa is private, the ppa section will not be displayed
        # to users without view access to the ppa.
        self.make_ppa_private(self.person_ppa)
        login(ANONYMOUS)
        person_view = PersonView(self.owner, LaunchpadTestRequest())
        self.failIf(person_view.should_show_ppa_section)

        # But if the context person has a second ppa that is public,
        # then anon users will see the section.
        self.factory.makeArchive(owner=self.owner)
        person_view = PersonView(self.owner, LaunchpadTestRequest())
        self.failUnless(person_view.should_show_ppa_section)

    def test_viewing_team_with_private_ppa(self):
        # If a team PPA is private, the ppa section will be displayed
        # to team members.
        self.make_ppa_private(self.team_ppa)
        member = self.factory.makePerson()
        login_person(self.owner)
        self.team.addMember(member, self.owner)
        login_person(member)

        # So the member will see the section.
        person_view = PersonView(self.team, LaunchpadTestRequest())
        self.failUnless(person_view.should_show_ppa_section)

        # But other users who are not members will not.
        non_member = self.factory.makePerson()
        login_person(non_member)
        person_view = PersonView(self.team, LaunchpadTestRequest())
        self.failIf(person_view.should_show_ppa_section)

        # Unless the team also has another ppa which is public.
        self.factory.makeArchive(owner=self.team)
        person_view = PersonView(self.team, LaunchpadTestRequest())
        self.failUnless(person_view.should_show_ppa_section)


class TestPersonRenameFormMixin:

    def test_can_rename_with_empty_PPA(self):
        # If a PPA exists but has no packages, we can rename the
        # person.
        self.view.initialize()
        self.assertFalse(self.view.form_fields['name'].for_display)

    def _publishPPAPackage(self):
        stp = SoyuzTestPublisher()
        stp.setUpDefaultDistroSeries()
        stp.getPubSource(archive=self.ppa)

    def test_cannot_rename_with_non_empty_PPA(self):
        # Publish some packages in the PPA and test that we can't rename
        # the person.
        self._publishPPAPackage()
        self.view.initialize()
        self.assertTrue(self.view.form_fields['name'].for_display)
        self.assertEqual(
            self.view.widgets['name'].hint,
            "This person has an active PPA with packages published and "
            "may not be renamed.")

    def test_cannot_rename_with_deleting_PPA(self):
        # When a PPA is in the DELETING state we should not allow
        # renaming just yet.
        self._publishPPAPackage()
        self.view.initialize()
        self.ppa.delete(self.person)
        self.assertEqual(self.ppa.status, ArchiveStatus.DELETING)
        self.assertTrue(self.view.form_fields['name'].for_display)

    def test_can_rename_with_deleted_PPA(self):
        # Delete a PPA and test that the person can be renamed.
        self._publishPPAPackage()
        # Deleting the PPA will remove the publications, which is
        # necessary for the renaming check.
        self.ppa.delete(self.person)
        # Simulate the external script running and finalising the
        # DELETED status.
        self.ppa.status = ArchiveStatus.DELETED
        self.view.initialize()
        self.assertFalse(self.view.form_fields['name'].for_display)


class TestPersonEditView(TestPersonRenameFormMixin, TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestPersonEditView, self).setUp()
        self.valid_email_address = self.factory.getUniqueEmailAddress()
        self.person = self.factory.makePerson(email=self.valid_email_address)
        login_person(self.person)
        self.ppa = self.factory.makeArchive(owner=self.person)
        self.view = create_initialized_view(self.person, '+edit')

    def createAddEmailView(self, email_address):
        """Test helper to create +editemails view."""
        form = {
            'field.VALIDATED_SELECTED': self.valid_email_address,
            'field.VALIDATED_SELECTED-empty-marker': 1,
            'field.actions.add_email': 'Add',
            'field.newemail': email_address,
            }
        return create_initialized_view(self.person, "+editemails", form=form)

    def createSetContactViaAddEmailView(self, email_address):
        """Test helper to use +editemails view to set preferred address."""
        form = {
            'field.VALIDATED_SELECTED': email_address,
            'field.actions.set_preferred': 'Set as Contact Address',
            }
        return create_initialized_view(self.person, '+editemails', form=form)

    def _assertEmailAndError(self, email_str, expected_msg):
        """Special assert function for dealing with email-related errors."""
        view = self.createAddEmailView(email_str)
        error_msg = view.errors[0]
        if type(error_msg) != unicode:
            error_msg = error_msg.doc()
        self.assertEqual(expected_msg, error_msg)

    def test_add_email(self):
        """Adding email should add a login token, notification, and email."""
        stub.test_emails = []
        email_address = self.factory.getUniqueEmailAddress()
        view = self.createAddEmailView(email_address)
        # If everything worked, there should now be a login token to validate
        # this email address for this user.
        token = getUtility(ILoginTokenSet).searchByEmailRequesterAndType(
            email_address,
            self.person,
            LoginTokenType.VALIDATEEMAIL)
        self.assertIsNotNone(token)
        notifications = view.request.response.notifications
        self.assertEqual(1, len(notifications))
        expected_msg = html_escape(
            u"A confirmation message has been sent to '%s'."
            " Follow the instructions in that message to confirm"
            " that the address is yours. (If the message doesn't arrive in a"
            " few minutes, your mail provider might use 'greylisting', which"
            " could delay the message for up to an hour or two.)" %
            email_address)
        self.assertEqual(expected_msg, notifications[0].message)
        transaction.commit()
        self.assertEqual(2, len(stub.test_emails))
        to_addrs = [to_addr for from_addr, to_addr, msg in stub.test_emails]
        # Both the new and old addr should be sent email.
        self.assertIn([self.valid_email_address], to_addrs)
        self.assertIn([email_address], to_addrs)

    def test_add_email_address_taken(self):
        """Adding an already existing email should give error notice."""
        email_address = self.factory.getUniqueEmailAddress()
        self.factory.makePerson(
            name='deadaccount',
            displayname='deadaccount',
            email=email_address,
            account_status=AccountStatus.NOACCOUNT)
        view = self.createAddEmailView(email_address)
        error_msg = view.errors[0]
        expected_msg = (
            "The email address '%s' is already registered to "
            "<a href=\"http://launchpad.dev/~deadaccount\">deadaccount</a>. "
            "If you think that is a duplicated account, you can "
            "<a href=\"http://launchpad.dev/people/+requestmerge?"
            "field.dupe_person=deadaccount\">merge it</a> into your account."
            % email_address)
        self.assertEqual(expected_msg, error_msg)

    def test_validate_email(self):
        """Validating an email should send a notice email to the user."""
        stub.test_emails = []
        added_email = self.factory.getUniqueEmailAddress()
        view = self.createAddEmailView(added_email)
        form = {
            'field.UNVALIDATED_SELECTED': added_email,
            'field.actions.validate': 'Confirm',
            }
        view = create_initialized_view(self.person, '+editemails', form=form)
        notifications = view.request.response.notifications
        self.assertEqual(1, len(notifications))
        expected_msg = html_escape(
            u"An e-mail message was sent to '%s' "
            "with instructions on how to confirm that it belongs to you."
            % added_email)
        self.assertEqual(expected_msg, notifications[0].message)
        # Ensure we sent mail to the right address.
        transaction.commit()
        to_addrs = [to_addr for from_addr, to_addr, msg in stub.test_emails]
        self.assertIn([added_email], to_addrs)

    def test_validate_token(self):
        """Hitting +validateemail should actuall validate the email."""
        stub.test_emails = []
        added_email = self.factory.getUniqueEmailAddress()
        self.createAddEmailView(added_email)
        form = {
            'field.UNVALIDATED_SELECTED': added_email,
            'field.actions.validate': 'Confirm',
            }
        create_initialized_view(self.person, '+editemails', form=form)
        # Get the token from the email msg.
        transaction.commit()
        messages = [msg for from_addr, to_addr, msg in stub.test_emails]
        raw_msg = None
        for orig_msg in messages:
            msg = email.message_from_string(orig_msg)
            if msg.get('to') == added_email:
                raw_msg = orig_msg
        token_url = get_token_url_from_email(raw_msg)
        browser = setupBrowserForUser(user=self.person)
        browser.open(token_url)
        expected_msg = u'Confirm e-mail address <code>%s</code>' % added_email
        self.assertIn(expected_msg, browser.contents)
        browser.getControl('Continue').click()
        # Login again to access displayname, since browser logged us out.
        login_person(self.person)
        expected_title = u'%s in Launchpad' % self.person.displayname
        self.assertEqual(expected_title, browser.title)

    def test_remove_unvalidated_email_address(self):
        """A user should be able to remove and unvalidated email."""
        added_email = self.factory.getUniqueEmailAddress()
        view = self.createAddEmailView(added_email)
        form = {
            'field.UNVALIDATED_SELECTED': added_email,
            'field.actions.remove_unvalidated': 'Remove',
            }
        view = create_initialized_view(self.person, '+editemails', form=form)
        notifications = view.request.response.notifications
        self.assertEqual(1, len(notifications))
        expected_msg = html_escape(
            u"The email address '%s' has been removed." % added_email)
        self.assertEqual(expected_msg, notifications[0].message)

    def test_cannot_remove_contact_address(self):
        """A user should not be able to remove their own contact email."""
        form = {
            'field.VALIDATED_SELECTED': self.valid_email_address,
            'field.actions.remove_validated': 'Remove',
            }
        view = create_initialized_view(self.person, '+editemails', form=form)
        error_msg = view.errors[0]
        expected_msg = html_escape(
            "You can't remove %s because it's your contact email address."
            % self.valid_email_address)
        self.assertEqual(expected_msg, error_msg)

    def test_set_contact_address(self):
        """A user should be able to change to a new contact email."""
        added_email = self.factory.getUniqueEmailAddress()
        view = self.createAddEmailView(added_email)
        # We need a commit to make sure person and other data are in DB.
        transaction.commit()
        validated_email = getUtility(
            IEmailAddressSet).new(added_email, self.person)
        self.person.validateAndEnsurePreferredEmail(validated_email)
        view = self.createSetContactViaAddEmailView(added_email)
        notifications = view.request.response.notifications
        self.assertEqual(1, len(notifications))
        expected_msg = (
            u"Your contact address has been changed to: %s" % added_email)
        self.assertEqual(expected_msg, notifications[0].message)

    def test_set_contact_address_already_set(self):
        """Users should be warned when setting the same contact email."""
        view = self.createSetContactViaAddEmailView(self.valid_email_address)
        notifications = view.request.response.notifications
        self.assertEqual(1, len(notifications))
        expected_msg = (
            "%s is already set as your contact address."
            % self.valid_email_address)
        self.assertEqual(expected_msg, notifications[0].message)

    def test_team_editemails_not_found(self):
        """Teams should not have a +editemails page."""
        team = self.factory.makeTeam(owner=self.person, members=[self.person])
        url = '%s/+editemails' % canonical_url(team)
        browser = setupBrowserForUser(user=self.person)
        self.assertRaises(NotFound, browser.open, url)

    def test_email_string_validation_no_email_prodvided(self):
        """+editemails should warn if no email is provided."""
        no_email = ''
        expected_msg = u'Required input is missing.'
        self._assertEmailAndError(no_email, expected_msg)

    def test_email_string_validation_invalid_email(self):
        """+editemails should warn when provided data is not an email."""
        not_an_email = 'foo'
        expected_msg = html_escape(
            u"'foo' doesn't seem to be a valid email address.")
        self._assertEmailAndError(not_an_email, expected_msg)

    def test_email_string_validation_is_escaped(self):
        """+editemails should escape output to prevent XSS."""
        xss_email = "foo@example.com<script>window.alert('XSS')</script>"
        expected_msg = (
            u"&#x27;foo@example.com&lt;script&gt;"
            "window.alert(&#x27;XSS&#x27;)&lt;/script&gt;&#x27;"
            " doesn&#x27;t seem to be a valid email address.")
        self._assertEmailAndError(xss_email, expected_msg)

    def test_edit_email_login_redirect(self):
        """+editemails should redirect to force you to re-authenticate."""
        view = create_initialized_view(self.person, "+editemails")
        response = view.request.response
        self.assertEqual(302, response.getStatus())
        expected_url = (
            '%s/+editemails/+login?reauth=1' % canonical_url(self.person))
        self.assertEqual(expected_url, response.getHeader('location'))


class TestPersonParticipationView(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestPersonParticipationView, self).setUp()
        self.user = self.factory.makePerson()
        self.view = create_view(self.user, name='+participation')

    def test__asParticpation_owner(self):
        # Team owners have the role of 'Owner'.
        self.factory.makeTeam(owner=self.user)
        [participation] = self.view.active_participations
        self.assertEqual('Owner', participation['role'])

    def test__asParticpation_admin(self):
        # Team admins have the role of 'Admin'.
        team = self.factory.makeTeam()
        login_person(team.teamowner)
        team.addMember(self.user, team.teamowner)
        for membership in self.user.team_memberships:
            membership.setStatus(
                TeamMembershipStatus.ADMIN, team.teamowner)
        [participation] = self.view.active_participations
        self.assertEqual('Admin', participation['role'])

    def test__asParticpation_member(self):
        # The default team role is 'Member'.
        team = self.factory.makeTeam()
        login_person(team.teamowner)
        team.addMember(self.user, team.teamowner)
        [participation] = self.view.active_participations
        self.assertEqual('Member', participation['role'])

    def test__asParticpation_without_mailing_list(self):
        # The default team role is 'Member'.
        team = self.factory.makeTeam()
        login_person(team.teamowner)
        team.addMember(self.user, team.teamowner)
        [participation] = self.view.active_participations
        self.assertEqual('&mdash;', participation['subscribed'])

    def test__asParticpation_unsubscribed_to_mailing_list(self):
        # The default team role is 'Member'.
        team = self.factory.makeTeam()
        self.factory.makeMailingList(team, team.teamowner)
        login_person(team.teamowner)
        team.addMember(self.user, team.teamowner)
        [participation] = self.view.active_participations
        self.assertEqual('Not subscribed', participation['subscribed'])

    def test__asParticpation_subscribed_to_mailing_list(self):
        # The default team role is 'Member'.
        team = self.factory.makeTeam()
        mailing_list = self.factory.makeMailingList(team, team.teamowner)
        mailing_list.subscribe(self.user)
        login_person(team.teamowner)
        team.addMember(self.user, team.teamowner)
        [participation] = self.view.active_participations
        self.assertEqual('Subscribed', participation['subscribed'])

    def test_active_participations_with_direct_private_team(self):
        # Users cannot see private teams that they are not members of.
        owner = self.factory.makePerson()
        team = self.factory.makeTeam(
            owner=owner, visibility=PersonVisibility.PRIVATE)
        login_person(owner)
        team.addMember(self.user, owner)
        # The team is included in active_participations.
        login_person(self.user)
        view = create_view(
            self.user, name='+participation', principal=self.user)
        self.assertEqual(1, len(view.active_participations))
        # The team is not included in active_participations.
        observer = self.factory.makePerson()
        login_person(observer)
        view = create_view(
            self.user, name='+participation', principal=observer)
        self.assertEqual(0, len(view.active_participations))

    def test_active_participations_with_indirect_private_team(self):
        # Users cannot see private teams that they are not members of.
        owner = self.factory.makePerson()
        team = self.factory.makeTeam(
            owner=owner, visibility=PersonVisibility.PRIVATE)
        direct_team = self.factory.makeTeam(owner=owner)
        login_person(owner)
        direct_team.addMember(self.user, owner)
        team.addMember(direct_team, owner)
        # The team is included in active_participations.
        login_person(self.user)
        view = create_view(
            self.user, name='+participation', principal=self.user)
        self.assertEqual(2, len(view.active_participations))
        # The team is not included in active_participations.
        observer = self.factory.makePerson()
        login_person(observer)
        view = create_view(
            self.user, name='+participation', principal=observer)
        self.assertEqual(1, len(view.active_participations))

    def test_active_participations_indirect_membership(self):
        # Verify the path of indirect membership.
        a_team = self.factory.makeTeam(name='a')
        b_team = self.factory.makeTeam(name='b', owner=a_team)
        self.factory.makeTeam(name='c', owner=b_team)
        login_person(a_team.teamowner)
        a_team.addMember(self.user, a_team.teamowner)
        transaction.commit()
        participations = self.view.active_participations
        self.assertEqual(3, len(participations))
        display_names = [
            participation['displayname'] for participation in participations]
        self.assertEqual(['A', 'B', 'C'], display_names)
        self.assertEqual(None, participations[0]['via'])
        self.assertEqual('A', participations[1]['via'])
        self.assertEqual('B, A', participations[2]['via'])

    def test_has_participations_false(self):
        participations = self.view.active_participations
        self.assertEqual(0, len(participations))
        self.assertEqual(False, self.view.has_participations)

    def test_has_participations_true(self):
        self.factory.makeTeam(owner=self.user)
        participations = self.view.active_participations
        self.assertEqual(1, len(participations))
        self.assertEqual(True, self.view.has_participations)


class TestPersonRelatedPackagesView(TestCaseWithFactory):
    """Test the related software view."""

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestPersonRelatedPackagesView, self).setUp()
        self.user = self.factory.makePerson()
        self.factory.makeGPGKey(self.user)
        self.ubuntu = getUtility(ILaunchpadCelebrities).ubuntu
        self.warty = self.ubuntu.getSeries('warty')
        self.view = create_initialized_view(self.user, '+related-packages')

    def publishSources(self, archive, maintainer):
        publisher = SoyuzTestPublisher()
        publisher.person = self.user
        login('foo.bar@canonical.com')
        spphs = []
        for count in range(0, self.view.max_results_to_display + 3):
            source_name = "foo" + str(count)
            spph = publisher.getPubSource(
                sourcename=source_name,
                status=PackagePublishingStatus.PUBLISHED,
                archive=archive,
                maintainer=maintainer,
                creator=self.user,
                distroseries=self.warty)
            spphs.append(spph)
        # Update the releases cache table.
        switch_dbuser('garbo_frequently')
        job = PopulateLatestPersonSourcePackageReleaseCache(FakeLogger())
        while not job.isDone():
            job(chunk_size=100)
        switch_dbuser('launchpad')
        login(ANONYMOUS)
        return spphs

    def copySources(self, spphs, copier, dest_distroseries):
        self.copier = self.factory.makePerson()
        for spph in spphs:
            spph.copyTo(
                dest_distroseries, creator=copier,
                pocket=PackagePublishingPocket.UPDATES,
                archive=dest_distroseries.main_archive)

    def test_view_helper_attributes(self):
        # Verify view helper attributes.
        self.assertEqual('Related packages', self.view.page_title)
        self.assertEqual('summary_list_size', self.view._max_results_key)
        self.assertEqual(
            config.launchpad.summary_list_size,
            self.view.max_results_to_display)

    def test_tableHeaderMessage(self):
        limit = self.view.max_results_to_display
        expected = 'Displaying first %s packages out of 100 total' % limit
        self.assertEqual(expected, self.view._tableHeaderMessage(100))
        expected = '%s packages' % limit
        self.assertEqual(expected, self.view._tableHeaderMessage(limit))
        expected = '1 package'
        self.assertEqual(expected, self.view._tableHeaderMessage(1))

    def test_latest_uploaded_ppa_packages_with_stats(self):
        # Verify number of PPA packages to display.
        ppa = self.factory.makeArchive(owner=self.user)
        self.publishSources(ppa, self.user)
        count = len(self.view.latest_uploaded_ppa_packages_with_stats)
        self.assertEqual(self.view.max_results_to_display, count)

    def test_latest_maintained_packages_with_stats(self):
        # Verify number of maintained packages to display.
        self.publishSources(self.warty.main_archive, self.user)
        count = len(self.view.latest_maintained_packages_with_stats)
        self.assertEqual(self.view.max_results_to_display, count)

    def test_latest_uploaded_nonmaintained_packages_with_stats(self):
        # Verify number of non maintained packages to display.
        maintainer = self.factory.makePerson()
        self.publishSources(self.warty.main_archive, maintainer)
        count = len(
            self.view.latest_uploaded_but_not_maintained_packages_with_stats)
        self.assertEqual(self.view.max_results_to_display, count)

    def test_latest_synchronised_publishings_with_stats(self):
        # Verify number of non synchronised publishings to display.
        creator = self.factory.makePerson()
        spphs = self.publishSources(self.warty.main_archive, creator)
        dest_distroseries = self.factory.makeDistroSeries()
        self.copySources(spphs, self.user, dest_distroseries)
        count = len(
            self.view.latest_synchronised_publishings_with_stats)
        self.assertEqual(self.view.max_results_to_display, count)


class TestPersonMaintainedPackagesView(TestCaseWithFactory):
    """Test the maintained packages view."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestPersonMaintainedPackagesView, self).setUp()
        self.user = self.factory.makePerson()
        self.view = create_initialized_view(self.user, '+maintained-packages')

    def test_view_helper_attributes(self):
        # Verify view helper attributes.
        self.assertEqual('Maintained Packages', self.view.page_title)
        self.assertEqual('default_batch_size', self.view._max_results_key)
        self.assertEqual(
            config.launchpad.default_batch_size,
            self.view.max_results_to_display)


class TestPersonUploadedPackagesView(TestCaseWithFactory):
    """Test the maintained packages view."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestPersonUploadedPackagesView, self).setUp()
        self.user = self.factory.makePerson()
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PRIMARY)
        spr = self.factory.makeSourcePackageRelease(
            creator=self.user, archive=archive)
        self.spph = self.factory.makeSourcePackagePublishingHistory(
            sourcepackagerelease=spr, archive=archive)
        self.view = create_initialized_view(self.user, '+uploaded-packages')

    def test_view_helper_attributes(self):
        # Verify view helper attributes.
        self.assertEqual('Uploaded packages', self.view.page_title)
        self.assertEqual('default_batch_size', self.view._max_results_key)
        self.assertEqual(
            config.launchpad.default_batch_size,
            self.view.max_results_to_display)


class TestPersonPPAPackagesView(TestCaseWithFactory):
    """Test the maintained packages view."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestPersonPPAPackagesView, self).setUp()
        self.user = self.factory.makePerson()
        self.view = create_initialized_view(self.user, '+ppa-packages')

    def test_view_helper_attributes(self):
        # Verify view helper attributes.
        self.assertEqual('PPA packages', self.view.page_title)
        self.assertEqual('default_batch_size', self.view._max_results_key)
        self.assertEqual(
            config.launchpad.default_batch_size,
            self.view.max_results_to_display)


class PersonOwnedTeamsViewTestCase(TestCaseWithFactory):
    """Test +owned-teams view."""

    layer = DatabaseFunctionalLayer

    def test_properties(self):
        # The batch is created when the view is initialized.
        owner = self.factory.makePerson()
        team = self.factory.makeTeam(owner=owner)
        view = create_initialized_view(owner, '+owned-teams')
        self.assertEqual('Owned teams', view.page_title)
        self.assertEqual('team', view.batchnav._singular_heading)
        self.assertEqual([team], view.batch)

    def test_page_text_with_teams(self):
        # When the person owns teams, the page shows a a listing
        # table. There is always a link to the team participation page.
        owner = self.factory.makePerson(name='snarf')
        self.factory.makeTeam(owner=owner, name='pting')
        with person_logged_in(owner):
            view = create_initialized_view(
                owner, '+owned-teams', principal=owner)
            markup = view()
        soup = find_tag_by_id(markup, 'maincontent')
        participation_link = 'http://launchpad.dev/~snarf/+participation'
        self.assertIsNotNone(soup.find('a', {'href': participation_link}))
        self.assertIsNotNone(soup.find('table', {'id': 'owned-teams'}))
        self.assertIsNotNone(soup.find('a', {'href': '/~pting'}))
        self.assertIsNotNone(soup.find('table', {'class': 'upper-batch-nav'}))
        self.assertIsNotNone(soup.find('table', {'class': 'lower-batch-nav'}))

    def test_page_text_without_teams(self):
        # When the person does not own teams, the page states the case.
        owner = self.factory.makePerson(name='pting')
        with person_logged_in(owner):
            view = create_initialized_view(
                owner, '+owned-teams', principal=owner)
            markup = view()
        soup = find_tag_by_id(markup, 'maincontent')
        self.assertIsNotNone(soup.find('p', {'id': 'no-teams'}))


class TestPersonSynchronisedPackagesView(TestCaseWithFactory):
    """Test the synchronised packages view."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestPersonSynchronisedPackagesView, self).setUp()
        user = self.factory.makePerson()
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PRIMARY)
        spr = self.factory.makeSourcePackageRelease(
            creator=user, archive=archive)
        spph = self.factory.makeSourcePackagePublishingHistory(
            sourcepackagerelease=spr, archive=archive)
        self.copier = self.factory.makePerson()
        dest_distroseries = self.factory.makeDistroSeries()
        self.copied_spph = spph.copyTo(
            dest_distroseries, creator=self.copier,
            pocket=PackagePublishingPocket.UPDATES,
            archive=dest_distroseries.main_archive)
        self.view = create_initialized_view(
            self.copier, '+synchronised-packages')

    def test_view_helper_attributes(self):
        # Verify view helper attributes.
        self.assertEqual('Synchronised packages', self.view.page_title)
        self.assertEqual('default_batch_size', self.view._max_results_key)
        self.assertEqual(
            config.launchpad.default_batch_size,
            self.view.max_results_to_display)


class TestPersonRelatedProjectsView(TestCaseWithFactory):
    """Test the maintained packages view."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestPersonRelatedProjectsView, self).setUp()
        self.user = self.factory.makePerson()
        self.view = create_initialized_view(self.user, '+related-projects')

    def test_view_helper_attributes(self):
        # Verify view helper attributes.
        self.assertEqual('Related projects', self.view.page_title)
        self.assertEqual('default_batch_size', self.view._max_results_key)
        self.assertEqual(
            config.launchpad.default_batch_size,
            self.view.max_results_to_display)


class TestPersonRelatedPackagesFailedBuild(TestCaseWithFactory):
    """The related packages views display links to failed builds."""

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestPersonRelatedPackagesFailedBuild, self).setUp()
        self.user = self.factory.makePerson()

        # First we need to publish some PPA packages with failed builds
        # for this person.
        # XXX michaeln 2010-06-10 bug=592050.
        # Strangely, the builds need to be built in the context of a
        # main archive to reproduce bug 591010 for which this test was
        # written to demonstrate.
        login('foo.bar@canonical.com')
        publisher = SoyuzTestPublisher()
        publisher.prepareBreezyAutotest()
        ppa = self.factory.makeArchive(owner=self.user)
        spph = self.factory.makeSourcePackagePublishingHistory(
            sourcepackagename='foo', version='666',
            creator=self.user, maintainer=self.user, archive=ppa)
        das = self.factory.makeDistroArchSeries(
            distroseries=spph.distroseries, architecturetag='cyr128')
        self.build = self.factory.makeBinaryPackageBuild(
            source_package_release=spph.sourcepackagerelease,
            archive=spph.distroseries.distribution.main_archive,
            distroarchseries=das)
        self.build.updateStatus(BuildStatus.FAILEDTOBUILD)
        # Update the releases cache table.
        switch_dbuser('garbo_frequently')
        job = PopulateLatestPersonSourcePackageReleaseCache(FakeLogger())
        while not job.isDone():
            job(chunk_size=100)
        switch_dbuser('launchpad')
        login(ANONYMOUS)

    def test_related_software_with_failed_build(self):
        # The link to the failed build is displayed.
        self.view = create_view(self.user, name='+related-packages')
        html = self.view()
        self.assertIn(
            '<a href="/ubuntu/+source/foo/666/+build/%d">cyr128</a>' % (
                self.build.id), html)

    def test_related_ppa_packages_with_failed_build(self):
        # The link to the failed build is displayed.
        self.view = create_view(self.user, name='+ppa-packages')
        html = self.view()
        self.assertIn(
            '<a href="/ubuntu/+source/foo/666/+build/%d">cyr128</a>' % (
                self.build.id), html)


class TestPersonRelatedPackagesSynchronisedPackages(TestCaseWithFactory):
    """The related packages views display links to synchronised packages."""

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestPersonRelatedPackagesSynchronisedPackages, self).setUp()
        self.user = self.factory.makePerson()
        self.spph = self.factory.makeSourcePackagePublishingHistory()

    def createCopiedSource(self, copier, spph):
        self.copier = self.factory.makePerson()
        dest_distroseries = self.factory.makeDistroSeries()
        return spph.copyTo(
            dest_distroseries, creator=copier,
            pocket=PackagePublishingPocket.UPDATES,
            archive=dest_distroseries.main_archive)

    def getLinkToSynchronisedMatcher(self):
        person_url = canonical_url(self.user)
        return soupmatchers.HTMLContains(
            soupmatchers.Tag(
                'Synchronised packages link', 'a',
                attrs={'href': person_url + '/+synchronised-packages'},
                text='Synchronised packages'))

    def test_related_software_no_link_synchronised_packages(self):
        # No link to the synchronised packages page if no synchronised
        # packages.
        view = create_view(self.user, name='+related-packages')
        synced_package_link_matcher = self.getLinkToSynchronisedMatcher()
        self.assertThat(view(), Not(synced_package_link_matcher))

    def test_related_software_link_synchronised_packages(self):
        # If this person has synced packages, the link to the synchronised
        # packages page is present.
        self.createCopiedSource(self.user, self.spph)
        view = create_view(self.user, name='+related-packages')
        synced_package_link_matcher = self.getLinkToSynchronisedMatcher()
        self.assertThat(view(), synced_package_link_matcher)

    def test_related_software_displays_synchronised_packages(self):
        copied_spph = self.createCopiedSource(self.user, self.spph)
        view = create_view(self.user, name='+related-packages')
        synced_packages_title = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                'Synchronised packages title', 'h2',
                text='Synchronised packages'))
        expected_base = '/%s/+source/%s' % (
            copied_spph.distroseries.distribution.name,
            copied_spph.source_package_name)
        source_link = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                'Source package link', 'a',
                text=copied_spph.sourcepackagerelease.name,
                attrs={'href': expected_base}))
        version_url = (expected_base + '/%s' %
            copied_spph.sourcepackagerelease.version)
        version_link = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                'Source package version link', 'a',
                text=copied_spph.sourcepackagerelease.version,
                attrs={'href': version_url}))

        self.assertThat(view(), synced_packages_title)
        self.assertThat(view(), source_link)
        self.assertThat(view(), version_link)


class TestPersonDeactivateAccountView(TestCaseWithFactory):
    """Tests for the PersonDeactivateAccountView."""

    layer = DatabaseFunctionalLayer
    form = {
        'field.comment': 'Gotta go.',
        'field.actions.deactivate': 'Deactivate My Account'}

    def test_deactivate_user_active(self):
        user = self.factory.makePerson()
        login_person(user)
        view = create_initialized_view(
            user, '+deactivate-account', form=self.form)
        self.assertEqual([], view.errors)
        notifications = view.request.response.notifications
        self.assertEqual(1, len(notifications))
        self.assertEqual(
            'Your account has been deactivated.', notifications[0].message)
        self.assertEqual(AccountStatus.DEACTIVATED, user.account_status)

    def test_deactivate_user_already_deactivated(self):
        deactivated_user = self.factory.makePerson()
        login_person(deactivated_user)
        deactivated_user.deactivate(comment='going.')
        view = create_initialized_view(
            deactivated_user, '+deactivate-account', form=self.form)
        self.assertEqual(1, len(view.errors))
        self.assertEqual(
            'This account is already deactivated.', view.errors[0])


class TestTeamInvitationView(TestCaseWithFactory):
    """Tests for TeamInvitationView."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestTeamInvitationView, self).setUp()
        self.a_team = self.factory.makeTeam(name="team-a",
                                            displayname="A-Team")
        self.b_team = self.factory.makeTeam(name="team-b",
                                            displayname="B-Team")
        transaction.commit()

    def test_circular_invite(self):
        """Two teams can invite each other without horrifying results."""

        # Make the criss-cross invitations.
        # A invites B.
        login_person(self.a_team.teamowner)
        form = {
            'field.newmember': 'team-b',
            'field.actions.add': 'Add Member',
            }
        view = create_initialized_view(
            self.a_team, "+addmember", form=form)
        self.assertEqual([], view.errors)
        notifications = view.request.response.notifications
        self.assertEqual(1, len(notifications))
        self.assertEqual(
            u'B-Team (team-b) has been invited to join this team.',
            notifications[0].message)

        # B invites A.
        login_person(self.b_team.teamowner)
        form['field.newmember'] = 'team-a'
        view = create_initialized_view(
            self.b_team, "+addmember", form=form)
        self.assertEqual([], view.errors)
        notifications = view.request.response.notifications
        self.assertEqual(1, len(notifications))
        self.assertEqual(
            u'A-Team (team-a) has been invited to join this team.',
            notifications[0].message)

        # Team A accepts the invitation.
        login_person(self.a_team.teamowner)
        form = {
            'field.actions.accept': 'Accept',
            'field.acknowledger_comment': 'Thanks for inviting us.',
            }
        request = LaunchpadTestRequest(form=form, method='POST')
        request.setPrincipal(self.a_team.teamowner)
        membership_set = getUtility(ITeamMembershipSet)
        membership = membership_set.getByPersonAndTeam(self.a_team,
                                                       self.b_team)
        view = TeamInvitationView(membership, request)
        view.initialize()
        self.assertEqual([], view.errors)
        notifications = view.request.response.notifications
        self.assertEqual(1, len(notifications))
        self.assertEqual(
            u'This team is now a member of B-Team.',
            notifications[0].message)

        # Team B attempts to accept the invitation.
        login_person(self.b_team.teamowner)
        request = LaunchpadTestRequest(form=form, method='POST')
        request.setPrincipal(self.b_team.teamowner)
        membership = membership_set.getByPersonAndTeam(self.b_team,
                                                       self.a_team)
        view = TeamInvitationView(membership, request)
        view.initialize()
        self.assertEqual([], view.errors)
        notifications = view.request.response.notifications
        self.assertEqual(1, len(notifications))
        expected = (
            u'This team may not be added to A-Team because it is a member '
            'of B-Team.')
        self.assertEqual(
            expected,
            notifications[0].message)


class TestSubscriptionsView(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestSubscriptionsView, self).setUp(
            user='test@canonical.com')
        self.user = getUtility(ILaunchBag).user
        self.person = self.factory.makePerson()
        self.other_person = self.factory.makePerson()
        self.team = self.factory.makeTeam(owner=self.user)
        self.team.addMember(self.person, self.user)

    def test_unsubscribe_link_appears_for_user(self):
        login_person(self.person)
        view = create_view(self.person, '+subscriptions')
        self.assertTrue(view.canUnsubscribeFromBugTasks())

    def test_unsubscribe_link_does_not_appear_for_not_user(self):
        login_person(self.other_person)
        view = create_view(self.person, '+subscriptions')
        self.assertFalse(view.canUnsubscribeFromBugTasks())

    def test_unsubscribe_link_appears_for_team_member(self):
        login_person(self.person)
        view = create_initialized_view(self.team, '+subscriptions')
        self.assertTrue(view.canUnsubscribeFromBugTasks())


class BugTaskViewsTestBase:
    """A base class for bugtask search related tests."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(BugTaskViewsTestBase, self).setUp()
        self.person = self.factory.makePerson()
        with person_logged_in(self.person):
            self.subscribed_bug = self.factory.makeBug()
            self.subscribed_bug.subscribe(
                self.person, subscribed_by=self.person)
            self.assigned_bug = self.factory.makeBug()
            self.assigned_bug.default_bugtask.transitionToAssignee(
                self.person)
            self.owned_bug = self.factory.makeBug(owner=self.person)
            self.commented_bug = self.factory.makeBug()
            self.commented_bug.newMessage(owner=self.person)
            self.affecting_bug = self.factory.makeBug()
            self.affecting_bug.markUserAffected(self.person)

        for bug in (self.subscribed_bug, self.assigned_bug, self.owned_bug,
                    self.commented_bug, self.affecting_bug):
            with person_logged_in(bug.default_bugtask.product.owner):
                milestone = self.factory.makeMilestone(
                    product=bug.default_bugtask.product)
                bug.default_bugtask.transitionToMilestone(
                    milestone, bug.default_bugtask.product.owner)

    def test_searchUnbatched(self):
        view = create_initialized_view(self.person, self.view_name)
        self.assertEqual(
            self.expected_for_search_unbatched, list(view.searchUnbatched()))

    def test_getMilestoneWidgetValues(self):
        view = create_initialized_view(self.person, self.view_name)
        milestones = [
            bugtask.milestone
            for bugtask in self.expected_for_search_unbatched]
        milestones = sorted(milestones, key=milestone_sort_key, reverse=True)
        expected = [
            {
                'title': milestone.title,
                'value': milestone.id,
                'checked': False,
                }
            for milestone in milestones]
        Store.of(milestones[0]).invalidate()
        with StormStatementRecorder() as recorder:
            self.assertEqual(expected, view.getMilestoneWidgetValues())
        self.assertThat(recorder, HasQueryCount(LessThan(6)))

    def test_context_description(self):
        # view.context_description returns a string that can be used
        # in texts like "Bugs in $context_descirption"
        view = create_initialized_view(self.person, self.view_name)
        self.assertEqual(
            self.expected_context_description % self.person.displayname,
            view.context_description)


class TestPersonRelatedBugTaskSearchListingView(
    BugTaskViewsTestBase, TestCaseWithFactory):
    """Tests for PersonRelatedBugTaskSearchListingView."""

    view_name = '+bugs'
    expected_context_description = 'related to %s'

    def setUp(self):
        super(TestPersonRelatedBugTaskSearchListingView, self).setUp()
        self.expected_for_search_unbatched = [
            self.subscribed_bug.default_bugtask,
            self.assigned_bug.default_bugtask,
            self.owned_bug.default_bugtask,
            self.commented_bug.default_bugtask,
            ]


class TestPersonAssignedBugTaskSearchListingView(
    BugTaskViewsTestBase, TestCaseWithFactory):
    """Tests for PersonAssignedBugTaskSearchListingView."""

    view_name = '+assignedbugs'
    expected_context_description = 'assigned to %s'

    def setUp(self):
        super(TestPersonAssignedBugTaskSearchListingView, self).setUp()
        self.expected_for_search_unbatched = [
            self.assigned_bug.default_bugtask,
            ]


class TestPersonCommentedBugTaskSearchListingView(
    BugTaskViewsTestBase, TestCaseWithFactory):
    """Tests for PersonAssignedBugTaskSearchListingView."""

    view_name = '+commentedbugs'
    expected_context_description = 'commented on by %s'

    def setUp(self):
        super(TestPersonCommentedBugTaskSearchListingView, self).setUp()
        self.expected_for_search_unbatched = [
            self.commented_bug.default_bugtask,
            ]


class TestPersonReportedBugTaskSearchListingView(
    BugTaskViewsTestBase, TestCaseWithFactory):
    """Tests for PersonAssignedBugTaskSearchListingView."""

    view_name = '+reportedbugs'
    expected_context_description = 'reported by %s'

    def setUp(self):
        super(TestPersonReportedBugTaskSearchListingView, self).setUp()
        self.expected_for_search_unbatched = [
            self.owned_bug.default_bugtask,
            ]


class TestPersonSubscribedBugTaskSearchListingView(
    BugTaskViewsTestBase, TestCaseWithFactory):
    """Tests for PersonAssignedBugTaskSearchListingView."""

    view_name = '+subscribedbugs'
    expected_context_description = '%s is subscribed to'

    def setUp(self):
        super(TestPersonSubscribedBugTaskSearchListingView, self).setUp()
        self.expected_for_search_unbatched = [
            self.subscribed_bug.default_bugtask,
            self.owned_bug.default_bugtask,
            ]


class TestPersonAffectingBugTaskSearchListingView(
    BugTaskViewsTestBase, TestCaseWithFactory):
    """Tests for PersonAffectingBugTaskSearchListingView."""

    view_name = '+affectingbugs'
    expected_context_description = 'affecting %s'

    def setUp(self):
        super(TestPersonAffectingBugTaskSearchListingView, self).setUp()
        # Bugs filed by this user are marked as affecting them by default, so
        # the bug we filed is returned.
        self.expected_for_search_unbatched = [
            self.owned_bug.default_bugtask,
            self.affecting_bug.default_bugtask,
            ]


class TestPersonRdfView(BrowserTestCase):
    """Test the RDF view."""

    layer = DatabaseFunctionalLayer

    def test_headers(self):
        """The headers for the RDF view of a person should be as expected."""
        person = self.factory.makePerson()
        content_disposition = 'attachment; filename="%s.rdf"' % person.name
        browser = self.getViewBrowser(person, view_name='+rdf')
        self.assertEqual(
            content_disposition, browser.headers['Content-disposition'])
        self.assertEqual(
            'application/rdf+xml', browser.headers['Content-type'])
