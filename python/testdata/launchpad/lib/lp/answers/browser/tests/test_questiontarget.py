# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test questiontarget views."""

__metaclass__ = type

import os
from urllib import quote

from BeautifulSoup import BeautifulSoup
from lazr.restful.interfaces import (
    IJSONRequestCache,
    IWebServiceClientRequest,
    )
from simplejson import dumps
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy
from zope.traversing.browser import absoluteURL

from lp.answers.interfaces.questioncollection import IQuestionSet
from lp.app.enums import ServiceUsage
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.registry.interfaces.person import IPersonSet
from lp.services.webapp import canonical_url
from lp.services.worlddata.interfaces.language import ILanguageSet
from lp.testing import (
    login_person,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    )
from lp.testing.matchers import BrowsesWithQueryLimit
from lp.testing.pages import find_tag_by_id
from lp.testing.sampledata import ADMIN_EMAIL
from lp.testing.views import (
    create_initialized_view,
    create_view,
    )


class TestSearchQuestionsView(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_matching_faqs_url__handles_non_ascii(self):
        product = self.factory.makeProduct()
        # Avoid non-ascii character in unicode literal to not upset
        # pocket-lint. Bug #776389.
        non_ascii_string = u'portugu\xeas'
        with person_logged_in(product.owner):
            self.factory.makeFAQ(product, non_ascii_string)
        form = {
            'field.search_text': non_ascii_string,
            'field.status': 'OPEN',
            'field.actions.search': 'Search',
            }
        view = create_initialized_view(
            product, '+questions', form=form, method='GET')

        encoded_string = quote(non_ascii_string.encode('utf-8'))
        # This must not raise UnicodeEncodeError.
        self.assertIn(encoded_string, view.matching_faqs_url)

    def test_query_count(self):
        # SearchQuestionsView does not query for the target SPN every time.
        owner = self.factory.makePerson()
        distro = self.factory.makeDistribution()
        removeSecurityProxy(distro).official_answers = True
        dsp = self.factory.makeDistributionSourcePackage(
            distribution=distro)
        [self.factory.makeQuestion(target=dsp, owner=owner) for i in range(5)]
        browses_under_limit = BrowsesWithQueryLimit(
            31, owner, view_name="+questions")
        self.assertThat(dsp, browses_under_limit)


class TestSearchQuestionsViewCanConfigureAnswers(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_cannot_configure_answers_product_no_edit_permission(self):
        product = self.factory.makeProduct()
        view = create_initialized_view(product, '+questions')
        self.assertEqual(False, view.can_configure_answers)

    def test_can_configure_answers_product_with_edit_permission(self):
        product = self.factory.makeProduct()
        login_person(product.owner)
        view = create_initialized_view(product, '+questions')
        self.assertEqual(True, view.can_configure_answers)

    def test_cannot_configure_answers_distribution_no_edit_permission(self):
        distribution = self.factory.makeDistribution()
        view = create_initialized_view(distribution, '+questions')
        self.assertEqual(False, view.can_configure_answers)

    def test_can_configure_answers_distribution_with_edit_permission(self):
        distribution = self.factory.makeDistribution()
        login_person(distribution.owner)
        view = create_initialized_view(distribution, '+questions')
        self.assertEqual(True, view.can_configure_answers)

    def test_cannot_configure_answers_projectgroup_with_edit_permission(self):
        # Project groups inherit Launchpad usage from their projects.
        project_group = self.factory.makeProject()
        login_person(project_group.owner)
        view = create_initialized_view(project_group, '+questions')
        self.assertEqual(False, view.can_configure_answers)

    def test_cannot_configure_answers_dsp_with_edit_permission(self):
        # DSPs inherit Launchpad usage from their distribution.
        dsp = self.factory.makeDistributionSourcePackage()
        login_person(dsp.distribution.owner)
        view = create_initialized_view(dsp, '+questions')
        self.assertEqual(False, view.can_configure_answers)


class TestSearchQuestionsViewTemplate(TestCaseWithFactory):
    """Test the behavior of SearchQuestionsView.template"""

    layer = DatabaseFunctionalLayer

    def assertViewTemplate(self, context, file_name):
        view = create_initialized_view(context, '+questions')
        self.assertEqual(
            file_name, os.path.basename(view.template.filename))

    def test_template_product_answers_usage_unknown(self):
        product = self.factory.makeProduct()
        self.assertViewTemplate(product, 'unknown-support.pt')

    def test_template_product_answers_usage_launchpad(self):
        product = self.factory.makeProduct()
        with person_logged_in(product.owner):
            product.answers_usage = ServiceUsage.LAUNCHPAD
        self.assertViewTemplate(product, 'question-listing.pt')

    def test_template_projectgroup_answers_usage_unknown(self):
        product = self.factory.makeProduct()
        project_group = self.factory.makeProject(owner=product.owner)
        with person_logged_in(product.owner):
            product.project = project_group
        self.assertViewTemplate(project_group, 'unknown-support.pt')

    def test_template_projectgroup_answers_usage_launchpad(self):
        product = self.factory.makeProduct()
        project_group = self.factory.makeProject(owner=product.owner)
        with person_logged_in(product.owner):
            product.project = project_group
            product.answers_usage = ServiceUsage.LAUNCHPAD
        self.assertViewTemplate(project_group, 'question-listing.pt')

    def test_template_distribution_answers_usage_unknown(self):
        distribution = self.factory.makeDistribution()
        self.assertViewTemplate(distribution, 'unknown-support.pt')

    def test_template_distribution_answers_usage_launchpad(self):
        distribution = self.factory.makeDistribution()
        with person_logged_in(distribution.owner):
            distribution.answers_usage = ServiceUsage.LAUNCHPAD
        self.assertViewTemplate(distribution, 'question-listing.pt')

    def test_template_DSP_answers_usage_unknown(self):
        dsp = self.factory.makeDistributionSourcePackage()
        self.assertViewTemplate(dsp, 'unknown-support.pt')

    def test_template_DSP_answers_usage_launchpad(self):
        dsp = self.factory.makeDistributionSourcePackage()
        with person_logged_in(dsp.distribution.owner):
            dsp.distribution.answers_usage = ServiceUsage.LAUNCHPAD
        self.assertViewTemplate(dsp, 'question-listing.pt')

    def test_template_question_set(self):
        question_set = getUtility(IQuestionSet)
        self.assertViewTemplate(question_set, 'question-listing.pt')


class TestSearchQuestionsViewUnknown(TestCaseWithFactory):
    """Test the behavior of SearchQuestionsView unknown support."""

    layer = DatabaseFunctionalLayer

    def linkPackage(self, product, name):
        # A helper to setup a legitimate Packaging link between a product
        # and an Ubuntu source package.
        hoary = getUtility(ILaunchpadCelebrities).ubuntu['hoary']
        sourcepackagename = self.factory.makeSourcePackageName(name)
        self.factory.makeSourcePackage(
            sourcepackagename=sourcepackagename, distroseries=hoary)
        self.factory.makeSourcePackagePublishingHistory(
            sourcepackagename=sourcepackagename, distroseries=hoary)
        product.development_focus.setPackaging(
            hoary, sourcepackagename, product.owner)

    def setUp(self):
        super(TestSearchQuestionsViewUnknown, self).setUp()
        self.product = self.factory.makeProduct()
        self.view = create_initialized_view(self.product, '+questions')

    def assertCommonPageElements(self, content):
        robots = content.find('meta', attrs={'name': 'robots'})
        self.assertEqual('noindex,nofollow', robots['content'])
        self.assertTrue(content.find(True, id='support-unknown') is not None)

    def test_any_question_target_any_user(self):
        content = BeautifulSoup(self.view())
        self.assertCommonPageElements(content)

    def test_product_with_packaging_elements(self):
        self.linkPackage(self.product, 'cow')
        content = BeautifulSoup(self.view())
        self.assertCommonPageElements(content)
        self.assertTrue(content.find(True, id='ubuntu-support') is not None)

    def test_product_with_edit_permission(self):
        login_person(self.product.owner)
        self.view = create_initialized_view(
            self.product, '+questions', principal=self.product.owner)
        content = BeautifulSoup(self.view())
        self.assertCommonPageElements(content)
        self.assertTrue(
            content.find(True, id='configure-support') is not None)


class QuestionSetViewTestCase(TestCaseWithFactory):
    """Test the answers application root view."""

    layer = DatabaseFunctionalLayer

    def test_search_questions_form_rendering(self):
        # The view's template directly renders the form widgets.
        question_set = getUtility(IQuestionSet)
        view = create_initialized_view(question_set, '+index')
        content = find_tag_by_id(view.render(), 'search-all-questions')
        self.assertEqual('form', content.name)
        self.assertIsNot(None, content.find(True, id='text'))
        self.assertIsNot(
            None, content.find(True, id='field.actions.search'))
        self.assertIsNot(
            None, content.find(True, id='field.scope.option.all'))
        self.assertIsNot(
            None, content.find(True, id='field.scope.option.project'))
        target_widget = view.widgets['scope'].target_widget
        self.assertIsNot(
            None, content.find(True, id=target_widget.show_widget_id))
        text = str(content)
        picker_vocab = "DistributionOrProductOrProjectGroup"
        self.assertIn(picker_vocab, text)
        focus_script = "setFocusByName('field.search_text')"
        self.assertIn(focus_script, text)


class QuestionTargetPortletAnswerContactsWithDetailsTests(
                                                        TestCaseWithFactory):
    """Tests for IQuestionTarget:+portlet-answercontacts-details view."""
    layer = LaunchpadFunctionalLayer

    def test_content_type(self):
        question = self.factory.makeQuestion()

        # It works even for anonymous users, so no log-in is needed.
        view = create_view(question.target, '+portlet-answercontacts-details')
        view.render()

        self.assertEqual(
            view.request.response.getHeader('content-type'),
            'application/json')

    def test_data_no_answer_contacts(self):
        question = self.factory.makeQuestion()
        view = create_view(question.target, '+portlet-answercontacts-details')
        self.assertEqual(dumps([]), view.answercontact_data_js)

    def test_data_person_answercontact(self):
        # answercontact_data_js returns JSON string of a list
        # containing all contact information needed for
        # subscribers_list.js loading.
        question = self.factory.makeQuestion()
        contact = self.factory.makePerson(
            name='user', displayname='Contact Name')
        contact.addLanguage(getUtility(ILanguageSet)['en'])
        with person_logged_in(contact):
            question.target.addAnswerContact(contact, contact)
        view = create_view(question.target, '+portlet-answercontacts-details')
        api_request = IWebServiceClientRequest(view.request)

        expected_result = {
            'subscriber': {
                'name': 'user',
                'display_name': 'Contact Name',
                'is_team': False,
                'can_edit': False,
                'web_link': canonical_url(contact),
                'self_link': absoluteURL(contact, api_request)
                }
            }
        self.assertEqual(
            dumps([expected_result]), view.answercontact_data_js)

    def test_data_team_answer_contact(self):
        # For a team answer contacts, answercontact_data_js has is_team set
        # to true.
        question = self.factory.makeQuestion()
        teamowner = self.factory.makePerson(
            name="team-owner", displayname="Team Owner")
        contact = self.factory.makeTeam(
            name='team', displayname='Team Name', owner=teamowner)
        contact.addLanguage(getUtility(ILanguageSet)['en'])
        with person_logged_in(contact.teamowner):
            question.target.addAnswerContact(contact, contact)
        view = create_view(question.target, '+portlet-answercontacts-details')
        api_request = IWebServiceClientRequest(view.request)

        expected_result = {
            'subscriber': {
                'name': 'team',
                'display_name': 'Team Name',
                'is_team': True,
                'can_edit': False,
                'web_link': canonical_url(contact),
                'self_link': absoluteURL(contact, api_request)
                }
            }
        self.assertEqual(
            dumps([expected_result]), view.answercontact_data_js)

    def test_data_team_answercontact_owner_looks(self):
        # For a team subscription, answercontact_data_js has can_edit
        # set to true for team owner.
        question = self.factory.makeQuestion()
        teamowner = self.factory.makePerson(
            name="team-owner", displayname="Team Owner")
        contact = self.factory.makeTeam(
            name='team', displayname='Team Name', owner=teamowner)
        contact.addLanguage(getUtility(ILanguageSet)['en'])
        with person_logged_in(contact.teamowner):
            question.target.addAnswerContact(contact, contact.teamowner)
        view = create_view(question.target, '+portlet-answercontacts-details')
        api_request = IWebServiceClientRequest(view.request)

        expected_result = {
            'subscriber': {
                'name': 'team',
                'display_name': 'Team Name',
                'is_team': True,
                'can_edit': True,
                'web_link': canonical_url(contact),
                'self_link': absoluteURL(contact, api_request)
                }
            }
        with person_logged_in(contact.teamowner):
            self.assertEqual(
                dumps([expected_result]), view.answercontact_data_js)

    def test_data_team_subscription_member_looks(self):
        # For a team subscription, answercontact_data_js has can_edit
        # set to true for team member.
        question = self.factory.makeQuestion()
        member = self.factory.makePerson()
        teamowner = self.factory.makePerson(
            name="team-owner", displayname="Team Owner")
        contact = self.factory.makeTeam(
            name='team', displayname='Team Name', owner=teamowner,
            members=[member])
        contact.addLanguage(getUtility(ILanguageSet)['en'])
        with person_logged_in(contact.teamowner):
            question.target.addAnswerContact(contact, contact.teamowner)
        view = create_view(question.target, '+portlet-answercontacts-details')
        api_request = IWebServiceClientRequest(view.request)

        expected_result = {
            'subscriber': {
                'name': 'team',
                'display_name': 'Team Name',
                'is_team': True,
                'can_edit': True,
                'web_link': canonical_url(contact),
                'self_link': absoluteURL(contact, api_request)
                }
            }
        with person_logged_in(contact.teamowner):
            self.assertEqual(
                dumps([expected_result]), view.answercontact_data_js)

    def test_data_target_owner_answercontact_looks(self):
        # Answercontact_data_js has can_edit set to true for target owner.
        distro = self.factory.makeDistribution()
        question = self.factory.makeQuestion(target=distro)
        contact = self.factory.makePerson(
            name='user', displayname='Contact Name')
        contact.addLanguage(getUtility(ILanguageSet)['en'])
        with person_logged_in(contact):
            question.target.addAnswerContact(contact, contact)
        view = create_view(question.target, '+portlet-answercontacts-details')
        api_request = IWebServiceClientRequest(view.request)

        expected_result = {
            'subscriber': {
                'name': 'user',
                'display_name': 'Contact Name',
                'is_team': False,
                'can_edit': True,
                'web_link': canonical_url(contact),
                'self_link': absoluteURL(contact, api_request)
                }
            }
        with person_logged_in(distro.owner):
            self.assertEqual(
                dumps([expected_result]), view.answercontact_data_js)

    def test_data_subscription_lp_admin(self):
        # For a subscription, answercontact_data_js has can_edit
        # set to true for a Launchpad admin.
        question = self.factory.makeQuestion()
        member = self.factory.makePerson()
        contact = self.factory.makePerson(
            name='user', displayname='Contact Name')
        contact.addLanguage(getUtility(ILanguageSet)['en'])
        with person_logged_in(member):
            question.target.addAnswerContact(contact, contact)
        view = create_view(question.target, '+portlet-answercontacts-details')
        api_request = IWebServiceClientRequest(view.request)

        expected_result = {
            'subscriber': {
                'name': 'user',
                'display_name': 'Contact Name',
                'is_team': False,
                'can_edit': True,
                'web_link': canonical_url(contact),
                'self_link': absoluteURL(contact, api_request)
                }
            }

        # Login as admin
        admin = getUtility(IPersonSet).find(ADMIN_EMAIL).any()
        with person_logged_in(admin):
            self.assertEqual(
                dumps([expected_result]), view.answercontact_data_js)


class TestQuestionTargetPortletAnswerContacts(TestCaseWithFactory):
    """Tests for IQuestionTarget:+portlet-answercontacts."""
    layer = LaunchpadFunctionalLayer

    def test_jsoncache_contents(self):
        product = self.factory.makeProduct()
        question = self.factory.makeQuestion(target=product)
        login_person(product.owner)

        # It works even for anonymous users, so no log-in is needed.
        view = create_initialized_view(
            question.target, '+portlet-answercontacts', rootsite='answers')

        cache = IJSONRequestCache(view.request).objects
        context_url_data = {
            'web_link': canonical_url(product, rootsite='mainsite'),
            'self_link': absoluteURL(product,
                                     IWebServiceClientRequest(view.request)),
            }
        self.assertEqual(cache[product.name + '_answer_portlet_url_data'],
                         context_url_data)
