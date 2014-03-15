# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Webservice unit tests related to Launchpad Questions."""

__metaclass__ = type

from BeautifulSoup import BeautifulSoup
from lazr.restfulclient.errors import HTTPError
from simplejson import dumps
import transaction
from zope.security.proxy import removeSecurityProxy

from lp.answers.errors import (
    AddAnswerContactError,
    FAQTargetError,
    InvalidQuestionStateError,
    NotAnswerContactError,
    NotMessageOwnerError,
    NotQuestionOwnerError,
    QuestionTargetError,
    )
from lp.testing import (
    celebrity_logged_in,
    launchpadlib_for,
    logout,
    person_logged_in,
    TestCase,
    TestCaseWithFactory,
    ws_object,
    )
from lp.testing.layers import (
    AppServerLayer,
    DatabaseFunctionalLayer,
    FunctionalLayer,
    )
from lp.testing.pages import LaunchpadWebServiceCaller
from lp.testing.views import create_webservice_error_view


class ErrorsTestCase(TestCase):
    """Test answers errors are exported as HTTPErrors."""

    layer = FunctionalLayer

    def test_AddAnswerContactError(self):
        error_view = create_webservice_error_view(AddAnswerContactError())
        self.assertEqual(400, error_view.status)

    def test_FAQTargetError(self):
        error_view = create_webservice_error_view(FAQTargetError())
        self.assertEqual(400, error_view.status)

    def test_InvalidQuestionStateError(self):
        error_view = create_webservice_error_view(InvalidQuestionStateError())
        self.assertEqual(400, error_view.status)

    def test_NotAnswerContactError(self):
        error_view = create_webservice_error_view(NotAnswerContactError())
        self.assertEqual(400, error_view.status)

    def test_NotMessageOwnerError(self):
        error_view = create_webservice_error_view(NotMessageOwnerError())
        self.assertEqual(400, error_view.status)

    def test_NotQuestionOwnerError(self):
        error_view = create_webservice_error_view(NotQuestionOwnerError())
        self.assertEqual(400, error_view.status)

    def test_QuestionTargetError(self):
        error_view = create_webservice_error_view(QuestionTargetError())
        self.assertEqual(400, error_view.status)


class TestQuestionRepresentation(TestCaseWithFactory):
    """Test ways of interacting with Question webservice representations."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestQuestionRepresentation, self).setUp()
        with celebrity_logged_in('admin'):
            self.question = self.factory.makeQuestion(
                title="This is a question")
            self.target_name = self.question.target.name

        self.webservice = LaunchpadWebServiceCaller(
            'launchpad-library', 'salgado-change-anything')
        self.webservice.default_api_version = 'devel'

    def findQuestionTitle(self, response):
        """Find the question title field in an XHTML document fragment."""
        soup = BeautifulSoup(response.body)
        dt = soup.find('dt', text="title").parent
        dd = dt.findNextSibling('dd')
        return str(dd.contents.pop())

    def test_top_level_question_get(self):
        # The top level question set can be used via the api to get
        # a question by id via redirect without url hacking.
        response = self.webservice.get(
            '/questions/%s' % self.question.id, 'application/xhtml+xml')
        self.assertEqual(response.status, 200)

    def test_GET_xhtml_representation(self):
        # A question's xhtml representation is available on the api.
        response = self.webservice.get(
            '/%s/+question/%d' % (self.target_name,
                self.question.id),
            'application/xhtml+xml')
        self.assertEqual(response.status, 200)

        self.assertEqual(
            self.findQuestionTitle(response),
            "<p>This is a question</p>")

    def test_PATCH_xhtml_representation(self):
        # You can update the question through the api with PATCH.
        new_title = "No, this is a question"

        question_json = self.webservice.get(
            '/%s/+question/%d' % (self.target_name,
                self.question.id)).jsonBody()

        response = self.webservice.patch(
            question_json['self_link'],
            'application/json',
            dumps(dict(title=new_title)),
            headers=dict(accept='application/xhtml+xml'))

        self.assertEqual(response.status, 209)

        self.assertEqual(
            self.findQuestionTitle(response),
            "<p>No, this is a question</p>")


class TestSetCommentVisibility(TestCaseWithFactory):
    """Tests who can successfully set comment visibility."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestSetCommentVisibility, self).setUp()
        self.commenter = self.factory.makePerson()
        with person_logged_in(self.commenter):
            self.question = self.factory.makeQuestion()
            self.message = self.question.addComment(
                self.commenter, 'Some comment')
        transaction.commit()

    def _get_question_for_user(self, user=None):
        """Convenience function to get the api question reference."""
        # End any open lplib instance.
        logout()
        lp = launchpadlib_for("test", user)
        return ws_object(lp, removeSecurityProxy(self.question))

    def _set_visibility(self, question):
        """Method to set visibility; needed for assertRaises."""
        question.setCommentVisibility(
            comment_number=0,
            visible=False)

    def test_random_user_cannot_set_visible(self):
        # Logged in users without privs can't set question comment
        # visibility.
        random_user = self.factory.makePerson()
        question = self._get_question_for_user(random_user)
        self.assertRaises(
            HTTPError,
            self._set_visibility,
            question)

    def test_anon_cannot_set_visible(self):
        # Anonymous users can't set question comment
        # visibility.
        question = self._get_question_for_user()
        self.assertRaises(
            HTTPError,
            self._set_visibility,
            question)

    def test_comment_owner_can_set_visible(self):
        # Members of registry experts can set question comment
        # visibility.
        question = self._get_question_for_user(self.commenter)
        self._set_visibility(question)
        self.assertFalse(self.message.visible)

    def test_registry_admin_can_set_visible(self):
        # Members of registry experts can set question comment
        # visibility.
        with celebrity_logged_in('registry_experts') as registry:
            person = registry
        question = self._get_question_for_user(person)
        self._set_visibility(question)
        self.assertFalse(self.message.visible)

    def test_admin_can_set_visible(self):
        # Admins can set question comment
        # visibility.
        with celebrity_logged_in('admin') as admin:
            person = admin
        question = self._get_question_for_user(person)
        self._set_visibility(question)
        self.assertFalse(self.message.visible)


class TestQuestionWebServiceSubscription(TestCaseWithFactory):

    layer = AppServerLayer

    def test_subscribe(self):
        # Test subscribe() API.
        person = self.factory.makePerson()
        with person_logged_in(person):
            db_question = self.factory.makeQuestion()
            db_person = self.factory.makePerson()
            launchpad = self.factory.makeLaunchpadService()

        question = ws_object(launchpad, db_question)
        person = ws_object(launchpad, db_person)
        question.subscribe(person=person)
        transaction.commit()

        # Check the results.
        self.assertTrue(db_question.isSubscribed(db_person))

    def test_unsubscribe(self):
        # Test unsubscribe() API.
        person = self.factory.makePerson()
        with person_logged_in(person):
            db_question = self.factory.makeQuestion()
            db_person = self.factory.makePerson()
            db_question.subscribe(person=db_person)
            launchpad = self.factory.makeLaunchpadService(person=db_person)

        question = ws_object(launchpad, db_question)
        person = ws_object(launchpad, db_person)
        question.unsubscribe(person=person)
        transaction.commit()

        # Check the results.
        self.assertFalse(db_question.isSubscribed(db_person))
