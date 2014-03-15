# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
"""Test the peoplemerge browser module."""

__metaclass__ = type

from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.registry.enums import TeamMembershipPolicy
from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.persontransferjob import IPersonMergeJobSource
from lp.services.identity.interfaces.emailaddress import EmailAddressStatus
from lp.services.identity.model.emailaddress import EmailAddressSet
from lp.services.mail import stub
from lp.services.verification.tests.logintoken import get_token_url_from_email
from lp.services.webapp import canonical_url
from lp.services.webapp.escaping import html_escape
from lp.testing import (
    login_celebrity,
    login_person,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.matchers import DocTestMatches
from lp.testing.pages import (
    extract_text,
    find_tag_by_id,
    )
from lp.testing.views import (
    create_initialized_view,
    create_view,
    )


class RequestPeopleMergeMixin(TestCaseWithFactory):

    def setUp(self):
        super(RequestPeopleMergeMixin, self).setUp()
        self.person_set = getUtility(IPersonSet)
        self.dupe = self.factory.makePerson(
            name='foo', email='foo@baz.com')

    def tearDown(self):
        super(RequestPeopleMergeMixin, self).tearDown()
        stub.test_emails = []


class TestRequestPeopleMergeMultipleEmails(RequestPeopleMergeMixin):
    """ Tests for merging when dupe account has more than one email address."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestRequestPeopleMergeMultipleEmails, self).setUp()
        EmailAddressSet().new(
            'bar.foo@canonical.com', person=self.dupe,
            status=EmailAddressStatus.VALIDATED)

    def _assert_perform_merge_request(self):
        # Perform a merge request, asserting expected bahviour along the way.
        # We are redirected to a page displaying the email addresses owned by
        # the dupe account. The user chooses which one he wants to claim.
        target = self.factory.makePerson()
        login_person(target)
        browser = self.getUserBrowser(
            canonical_url(self.person_set) + '/+requestmerge', user=target)
        browser.getControl(
            'Duplicated Account').value = 'foo'
        browser.getControl('Continue').click()
        explanation = find_tag_by_id(browser.contents, 'explanation')
        self.assertThat(
            extract_text(explanation), DocTestMatches(
                "The account..."
                "has more than one registered e-mail address..."))
        email_select_control = browser.getControl(name='selected')
        for ctrl in email_select_control.controls:
            ctrl.selected = True
        browser.getControl('Merge Accounts').click()
        return browser

    def test_merge_with_multiple_emails_request(self):
        # Requesting a merge of an account with multiple email addresses
        # informs the user confirmation emails are sent out.
        browser = self._assert_perform_merge_request()
        confirmation = find_tag_by_id(browser.contents, 'confirmation')
        self.assertThat(
            extract_text(confirmation), DocTestMatches(
                "Confirmation email messages were sent to:..."))
        self.assertIn('foo@baz.com', browser.contents)
        self.assertIn('bar.foo@canonical.com', browser.contents)

    def test_validation_emails_sent(self):
        # Test that the expected emails are sent out to the selected email
        # addresses when a merge is requested.
        self._assert_perform_merge_request()
        self.assertEqual(2, len(stub.test_emails))
        emails = [stub.test_emails.pop(), stub.test_emails.pop()]
        emails.sort()
        from_addr1, to_addrs1, raw_msg1 = emails.pop()
        from_addr2, to_addrs2, raw_msg2 = emails.pop()
        self.assertEqual('bounces@canonical.com', from_addr1)
        self.assertEqual('bounces@canonical.com', from_addr2)
        self.assertEqual(['foo@baz.com'], to_addrs1)
        self.assertEqual(['bar.foo@canonical.com'], to_addrs2)
        self.assertIn('Launchpad: request to merge accounts', raw_msg1)
        self.assertIn('Launchpad: request to merge accounts', raw_msg2)

    def _assert_validation_email_confirm(self):
        # Test that the user can go to the page we sent a link via email to
        # validate the first claimed email address.
        browser = self._assert_perform_merge_request()
        emails = [stub.test_emails.pop(), stub.test_emails.pop()]
        emails.sort()
        ignore, ignore2, raw_msg1 = emails.pop()
        token_url = get_token_url_from_email(raw_msg1)
        browser.open(token_url)
        self.assertIn(
            'trying to merge the Launchpad account', browser.contents)
        browser.getControl('Confirm').click()
        # User confirms the merge request submitting the form, but the merge
        # wasn't finished because the duplicate account still have a registered
        # email addresses.
        self.assertIn(
            'has other registered e-mail addresses too', browser.contents)
        return browser, emails

    def test_validation_email_confirm(self):
        # Test the validation of the first claimed email address.
        self._assert_validation_email_confirm()

    def test_validation_email_complete(self):
        # Test that the merge completes successfully when the user proves that
        # he's the owner of the second email address of the dupe account.
        browser, emails = self._assert_validation_email_confirm()
        ignore, ignore2, raw_msg2 = emails.pop()
        token_url = get_token_url_from_email(raw_msg2)
        browser.open(token_url)
        self.assertIn(
            'trying to merge the Launchpad account', browser.contents)
        browser.getControl('Confirm').click()
        self.assertIn(
            'The accounts are being merged', browser.contents)


class TestRequestPeopleMergeSingleEmail(RequestPeopleMergeMixin):
    """ Tests for merging when dupe account has single email address."""

    layer = DatabaseFunctionalLayer

    def _perform_merge_request(self, dupe):
        # Perform a merge request.
        target = self.factory.makePerson()
        login_person(target)
        dupe_name = dupe.name
        browser = self.getUserBrowser(
            canonical_url(self.person_set) + '/+requestmerge', user=target)
        browser.getControl(
            'Duplicated Account').value = dupe_name
        browser.getControl('Continue').click()
        return browser

    def test_merge_request_submit(self):
        # Test that the expected emails are sent.
        browser = self._perform_merge_request(self.dupe)
        self.assertEqual(
            canonical_url(self.person_set) +
            '/+mergerequest-sent?dupe=%d' % self.dupe.id,
            browser.url)
        self.assertEqual(1, len(stub.test_emails))
        self.assertIn('An email message was sent to', browser.contents)
        self.assertIn('<strong>foo@baz.com</strong', browser.contents)

    def test_merge_request_revisit(self):
        # Test that revisiting the same request gives the same results.
        browser = self._perform_merge_request(self.dupe)
        browser.open(
            canonical_url(self.person_set) +
            '/+mergerequest-sent?dupe=%d' % self.dupe.id)
        self.assertEqual(1, len(stub.test_emails))
        self.assertIn('An email message was sent to', browser.contents)
        self.assertIn('<strong>foo@baz.com</strong', browser.contents)

    def test_merge_request_unvalidated_email(self):
        # Test that the expected emails are sent even when the dupe account
        # does not have a validated email address; the email is sent anyway.
        dupe = self.factory.makePerson(
            name='dupe', email='dupe@baz.com',
            email_address_status=EmailAddressStatus.NEW)
        browser = self._perform_merge_request(dupe)
        self.assertEqual(
            canonical_url(self.person_set) +
            '/+mergerequest-sent?dupe=%d' % dupe.id,
            browser.url)
        self.assertEqual(1, len(stub.test_emails))
        self.assertIn('An email message was sent to', browser.contents)
        self.assertIn('<strong>dupe@baz.com</strong', browser.contents)


class TestRequestPeopleMergeHiddenEmailAddresses(RequestPeopleMergeMixin):
    """ Tests for merging when dupe account has hidden email addresses.

    If the duplicate account has multiple email addresses and has chosen
    to hide them the process is slightly different.  We cannot display the
    hidden addresses so instead we just inform the user to check all of
    them (and hope they know which ones) and we send merge request
    messages to them all.
    """

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestRequestPeopleMergeHiddenEmailAddresses, self).setUp()
        removeSecurityProxy(self.dupe).hide_email_addresses = True
        EmailAddressSet().new(
            'bar.foo@canonical.com', person=self.dupe,
            status=EmailAddressStatus.VALIDATED)

    def _assert_perform_merge_request(self):
        # The merge request process does not allow for selecting any email
        # addresses since they are hidden.
        target = self.factory.makePerson()
        login_person(target)
        browser = self.getUserBrowser(
            canonical_url(self.person_set) + '/+requestmerge', user=target)
        browser.getControl(
            'Duplicated Account').value = 'foo'
        browser.getControl('Continue').click()
        explanation = find_tag_by_id(browser.contents, 'explanation')
        self.assertThat(
            extract_text(explanation), DocTestMatches(
                "The account...has 2 registered e-mail addresses..."))
        self.assertRaises(LookupError, browser.getControl, 'selected')
        self.assertNotIn('foo@baz.com', browser.contents)
        self.assertNotIn('bar.foo@canonical.com', browser.contents)
        browser.getControl('Merge Accounts').click()
        return browser

    def test_merge_with_hidden_emails_submit(self):
        # The merge request sends out emails but does not show the hidden email
        # addresses.
        browser = self._assert_perform_merge_request()
        confirmation = find_tag_by_id(browser.contents, 'confirmation')
        self.assertThat(
            extract_text(confirmation), DocTestMatches(
                "Confirmation email messages were sent to the 2 registered "
                "e-mail addresses..."))
        self.assertNotIn('foo@baz.com', browser.contents)
        self.assertNotIn('bar.foo@canonical.com', browser.contents)


class TestValidatingMergeView(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestValidatingMergeView, self).setUp()
        self.person_set = getUtility(IPersonSet)
        self.dupe = self.factory.makePerson(name='dupe')
        self.target = self.factory.makePerson(name='target')
        self.requester = self.factory.makePerson(name='requester')

    def getForm(self, dupe_name=None):
        if dupe_name is None:
            dupe_name = self.dupe.name
        return {
            'field.dupe_person': dupe_name,
            'field.target_person': self.target.name,
            'field.actions.continue': 'Continue',
            }

    def test_cannot_merge_person_with_ppas(self):
        # A team with a PPA cannot be merged.
        login_celebrity('admin')
        self.dupe.createPPA()
        login_celebrity('registry_experts')
        view = create_initialized_view(
            self.person_set, '+requestmerge', form=self.getForm())
        self.assertEqual(
            [html_escape(
                u"dupe has a PPA that must be deleted before it can be "
                "merged. It may take ten minutes to remove the deleted PPA's "
                "files.")],
            view.errors)

    def test_cannot_merge_person_with_private_branches(self):
        # A team or user with a private branches cannot be merged.
        self.factory.makeBranch(
            owner=self.dupe, information_type=InformationType.USERDATA)
        login_celebrity('registry_experts')
        view = create_initialized_view(
            self.person_set, '+requestmerge', form=self.getForm())
        self.assertEqual(
            [u"dupe owns private branches that must be deleted or "
              "transferred to another owner first."],
            view.errors)

    def test_cannot_merge_person_with_itself(self):
        # A IPerson cannot be merged with itself.
        login_person(self.target)
        form = self.getForm(dupe_name=self.target.name)
        view = create_initialized_view(
            self.person_set, '+requestmerge', form=form)
        self.assertEqual(
            [html_escape("You can't merge target into itself.")], view.errors)

    def test_cannot_merge_dupe_person_with_an_existing_merge_job(self):
        # A merge cannot be requested for an IPerson if it there is a job
        # queued to merge it into another IPerson.
        job_source = getUtility(IPersonMergeJobSource)
        job_source.create(
            from_person=self.dupe, to_person=self.target,
            requester=self.requester)
        login_person(self.target)
        view = create_initialized_view(
            self.person_set, '+requestmerge', form=self.getForm())
        self.assertEqual(
            ["dupe is already queued for merging."], view.errors)

    def test_cannot_merge_target_person_with_an_existing_merge_job(self):
        # A merge cannot be requested for an IPerson if it there is a job
        # queued to merge it into another IPerson.
        job_source = getUtility(IPersonMergeJobSource)
        job_source.create(
            from_person=self.target, to_person=self.dupe,
            requester=self.requester)
        login_person(self.target)
        view = create_initialized_view(
            self.person_set, '+requestmerge', form=self.getForm())
        self.assertEqual(
            ["target is already queued for merging."], view.errors)


class TestRequestPeopleMergeMultipleEmailsView(TestCaseWithFactory):
    """Test the RequestPeopleMergeMultipleEmailsView rules."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestRequestPeopleMergeMultipleEmailsView, self).setUp()
        self.personset = getUtility(IPersonSet)
        self.dupe_user = self.factory.makePerson()
        self.email_2 = self.factory.makeEmail(
            'dupe@place.dom', self.dupe_user)
        self.original_user = self.factory.makePerson()
        login_person(self.original_user)

    def verify_user_must_reselect_email_addresses(self, view):
        self.assertFalse(view.form_processed)
        self.assertEqual(0, len(view.notified_addresses))
        self.assertEqual(1, len(view.request.notifications))
        message = view.request.notifications[0].message
        self.assertTrue(message.endswith('Select again.'))

    def test_removed_email(self):
        # When the duplicate user deletes an email addres while the merge
        # form is being complete, the view must abort and ask the user
        # to restart the merge request.
        form = {
            'dupe': self.dupe_user.id,
            }
        view = create_view(
            self.personset, name='+requestmerge-multiple', form=form)
        view.processForm()
        dupe_emails = [address for address in view.dupeemails]
        form['selected'] = [address.email for address in dupe_emails]
        with person_logged_in(self.dupe_user):
            dupe_emails.remove(self.email_2)
            self.email_2.destroySelf()
        view = create_view(
            self.personset, name='+requestmerge-multiple', form=form,
            method='POST')
        view.processForm()
        self.verify_user_must_reselect_email_addresses(view)

    def test_email_address_cannot_be_substituted(self):
        # A person cannot hack the form to use another user's email address
        # to take control of a profile.
        controlled_user = self.factory.makePerson()
        form = {
            'dupe': self.dupe_user.id,
            'selected': [controlled_user.preferredemail.email],
            }
        view = create_view(
            self.personset, name='+requestmerge-multiple', form=form,
            method='POST')
        view.processForm()
        self.verify_user_must_reselect_email_addresses(view)


class TestAdminTeamMergeView(TestCaseWithFactory):
    """Test the AdminTeamMergeView rules."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestAdminTeamMergeView, self).setUp()
        self.person_set = getUtility(IPersonSet)
        self.dupe_team = self.factory.makeTeam(name='dupe-team')
        self.target_team = self.factory.makeTeam(name='target-team')
        login_celebrity('registry_experts')

    def getView(self, form=None):
        if form is None:
            form = {
                'field.dupe_person': self.dupe_team.name,
                'field.target_person': self.target_team.name,
                'field.actions.deactivate_members_and_merge': 'Merge',
                }
        return create_initialized_view(
            self.person_set, '+adminteammerge', form=form)

    def test_cannot_merge_team_with_ppa(self):
        # A team with a PPA cannot be merged.
        login_celebrity('admin')
        self.dupe_team.membership_policy = TeamMembershipPolicy.MODERATED
        self.dupe_team.createPPA()
        login_celebrity('registry_experts')
        view = self.getView()
        self.assertEqual(
            [html_escape(
                u"dupe-team has a PPA that must be deleted before it can be "
                "merged. It may take ten minutes to remove the deleted PPA's "
                "files.")],
            view.errors)


class TestAdminPeopleMergeView(TestCaseWithFactory):
    """Test the AdminPeopleMergeView rules."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestAdminPeopleMergeView, self).setUp()
        self.person_set = getUtility(IPersonSet)
        self.dupe_person = self.factory.makePerson(name='dupe-person')
        self.target_person = self.factory.makePerson()
        login_celebrity('registry_experts')

    def getView(self, form=None):
        if form is None:
            form = {
                'field.dupe_person': self.dupe_person.name,
                'field.target_person': self.target_person.name,
                'field.actions.reassign_emails_and_merge':
                    'Reassign E-mails and Merge',
                }
        return create_initialized_view(
            self.person_set, '+adminpeoplemerge', form=form)

    def test_cannot_merge_person_with_ppa(self):
        # A person with a PPA cannot be merged.
        login_celebrity('admin')
        self.dupe_person.createPPA()
        view = self.getView()
        self.assertEqual(
            [html_escape(
                u"dupe-person has a PPA that must be deleted before it can "
                "be merged. It may take ten minutes to remove the deleted "
                "PPA's files.")],
            view.errors)
