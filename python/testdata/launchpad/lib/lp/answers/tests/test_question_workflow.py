# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the question workflow methods.

Comprehensive tests for the question workflow methods. A narrative kind of
documentation is done in the ../../doc/answer-tracker-workflow.txt Doctest,
but testing all the possible transitions makes the documentation more heavy
than necessary. This is tested here.
"""

__metaclass__ = type

__all__ = []

from datetime import (
    datetime,
    timedelta,
    )
import traceback
import unittest

from lazr.lifecycle.interfaces import (
    IObjectCreatedEvent,
    IObjectModifiedEvent,
    )
from pytz import UTC
from zope.component import getUtility
from zope.interface.verify import verifyObject
from zope.security.interfaces import Unauthorized
from zope.security.proxy import removeSecurityProxy

from lp.answers.enums import (
    QuestionAction,
    QuestionStatus,
    )
from lp.answers.errors import (
    InvalidQuestionStateError,
    NotQuestionOwnerError,
    )
from lp.answers.interfaces.question import IQuestion
from lp.answers.interfaces.questionmessage import IQuestionMessage
from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.interfaces.person import (
    IPerson,
    IPersonSet,
    )
from lp.services.webapp.authorization import clear_cache
from lp.services.webapp.interfaces import ILaunchBag
from lp.services.worlddata.interfaces.language import ILanguageSet
from lp.testing import (
    ANONYMOUS,
    login,
    login_person,
    )
from lp.testing.event import TestEventListener
from lp.testing.layers import DatabaseFunctionalLayer


class BaseAnswerTrackerWorkflowTestCase(unittest.TestCase):
    """Base class for test cases related to the Answer Tracker workflow.

    It provides the common fixture and test helper methods.
    """

    layer = DatabaseFunctionalLayer

    def setUp(self):
        self.now = datetime.now(UTC)

        # Login as the question owner.
        login('no-priv@canonical.com')

        # Set up actors.
        personset = getUtility(IPersonSet)
        # User who submits request.
        self.owner = personset.getByEmail('no-priv@canonical.com')
        # User who answers request.
        self.answerer = personset.getByEmail('test@canonical.com')

        # Admin user which can change question status.
        self.admin = personset.getByEmail('foo.bar@canonical.com')

        # Simple ubuntu question.
        self.ubuntu = getUtility(IDistributionSet).getByName('ubuntu')

        self.question = self.ubuntu.newQuestion(
            self.owner, 'Help!', 'I need help with Ubuntu',
            datecreated=self.now)

    def tearDown(self):
        if hasattr(self, 'created_event_listener'):
            self.created_event_listener.unregister()
            self.modified_event_listener.unregister()

    def setQuestionStatus(self, question, new_status,
                          comment="Status change."):
        """Utility metho to change a question status.

        This logs in as admin, change the status and log back as
        the previous user.
        """
        old_user = getUtility(ILaunchBag).user
        login_person(self.admin)
        question.setStatus(self.admin, new_status, comment)
        login_person(old_user)

    def setUpEventListeners(self):
        """Install a listener for events emitted during the test."""
        self.collected_events = []
        if hasattr(self, 'modified_event_listener'):
            # Event listeners is already registered.
            return
        self.modified_event_listener = TestEventListener(
            IQuestion, IObjectModifiedEvent, self.collectEvent)
        self.created_event_listener = TestEventListener(
            IQuestionMessage, IObjectCreatedEvent, self.collectEvent)

    def collectEvent(self, object, event):
        """Collect events"""
        self.collected_events.append(event)

    def nowPlus(self, n_hours):
        """Return a DateTime a number of hours in the future."""
        return self.now + timedelta(hours=n_hours)

    def _testTransitionGuard(self, guard_name, statuses_expected_true):
        """Helper for transition guard tests.

        Helper that verifies that the Question guard_name attribute
        is True when the question status is one listed in
        statuses_expected_true and False otherwise.
        """
        for status in QuestionStatus.items:
            if status != self.question.status:
                self.setQuestionStatus(self.question, status)
            expected = status.name in statuses_expected_true
            allowed = getattr(self.question, guard_name)
            self.failUnless(
                expected == allowed, "%s != %s when status = %s" % (
                    guard_name, expected, status.name))

    def _testValidTransition(self, statuses, transition_method,
                            expected_owner, expected_action, expected_status,
                            extra_message_check=None,
                            transition_method_args=(),
                            transition_method_kwargs=None,
                            edited_fields=None):
        """Helper for testing valid state transitions.

        Helper that verifies that transition_method can be called when
        the question status is one listed in statuses. It will validate the
        returned message using checkTransitionMessage(). The transition_method
        is called with the transition_method_args as positional parameters
        and transition_method_kwargs as keyword parameters.

        If extra_message_check is passed a function, it will be called with
        the returned message for extra checks.

        The datecreated parameter to the transition_method is set
        automatically to a value that will make the message sort last.

        The edited_fields parameter contain the list of field that
        are expected to be present in IObjectModifiedEvent that should
        be triggered.
        """
        self.setUpEventListeners()
        count = 0
        if transition_method_kwargs is None:
            transition_method_kwargs = {}
        if 'datecreated' not in transition_method_kwargs:
            transition_method_kwargs['datecreated'] = self.nowPlus(0)
        for status in statuses:
            if status != self.question.status:
                self.setQuestionStatus(self.question, status)

            self.collected_events = []

            # Make sure that there are no FAQ linked.
            removeSecurityProxy(self.question).faq = None

            # Ensure ordering of the message.
            transition_method_kwargs['datecreated'] = (
                transition_method_kwargs['datecreated'] + timedelta(hours=1))
            message = transition_method(*transition_method_args,
                                        **transition_method_kwargs)
            try:
                self.checkTransitionMessage(
                    message, expected_owner=expected_owner,
                    expected_action=expected_action,
                    expected_status=expected_status)
                if extra_message_check:
                    extra_message_check(message)
            except AssertionError:
                # We capture and re-raise the error here to display a nice
                # message explaining in which state the transition failed.
                raise AssertionError(
                    "Failure in validating message when status=%s:\n%s" % (
                        status.name, traceback.format_exc(1)))
            self.checkTransitionEvents(
                message, edited_fields, status_name=status.name)
            count += 1

    def _testInvalidTransition(self, valid_statuses, transition_method,
                               *args, **kwargs):
        """Helper for testing invalid transitions.

        Helper that verifies that transition_method method cannot be
        called when the question status is different than the ones in
        valid_statuses.

        args and kwargs contains the parameters that should be passed to the
        transition method.
        """
        for status in QuestionStatus.items:
            if status.name in valid_statuses:
                continue
            exceptionRaised = False
            try:
                if status != self.question.status:
                    self.setQuestionStatus(self.question, status)
                transition_method(*args, **kwargs)
            except InvalidQuestionStateError:
                exceptionRaised = True
            self.failUnless(exceptionRaised,
                            "%s() when status = %s should raise an error" % (
                                transition_method.__name__, status.name))

    def checkTransitionMessage(self, message, expected_owner,
                               expected_action, expected_status):
        """Helper method to check the message created by a transition.

        It make sure that the message provides IQuestionMessage and that it
        was appended to the question messages attribute. It also checks that
        the subject was computed correctly and that the new_status, action
        and owner attributes were set correctly.

        It also verifies that the question status, datelastquery (or
        datelastresponse) were updated to reflect the time of the message.
        """
        self.failUnless(verifyObject(IQuestionMessage, message))

        self.assertEquals("Re: Help!", message.subject)
        self.assertEquals(expected_owner, message.owner)
        self.assertEquals(expected_action, message.action)
        self.assertEquals(expected_status, message.new_status)

        self.assertEquals(message, self.question.messages[-1])
        self.assertEquals(expected_status, self.question.status)

        if expected_owner == self.question.owner:
            self.assertEquals(message.datecreated,
                              self.question.datelastquery)
        else:
            self.assertEquals(
                message.datecreated, self.question.datelastresponse)

    def checkTransitionEvents(self, message, edited_fields, status_name):
        """Helper method to validate the events triggered from the transition.

        Check that an IObjectCreatedEvent event was sent when the message
        was created and that an IObjectModifiedEvent was also sent.
        The event object and edited_fields attribute are checked.
        """

        def failure_msg(msg):
            return "From status %s: %s" % (status_name, msg)

        self.failUnless(
            len(self.collected_events) >= 1,
            failure_msg('failed to trigger an IObjectCreatedEvent'))
        created_event = self.collected_events[0]
        created_event_user = IPerson(created_event.user)
        self.failUnless(
            IObjectCreatedEvent.providedBy(created_event),
            failure_msg(
                "%s doesn't provide IObjectCreatedEvent" % created_event))
        self.failUnless(
            created_event.object == message,
            failure_msg("IObjectCreatedEvent contains wrong message"))
        self.failUnless(
            created_event_user == message.owner,
            failure_msg("%s != %s" % (
                created_event_user.displayname, message.owner.displayname)))

        self.failUnless(
            len(self.collected_events) == 2,
            failure_msg('failed to trigger an IObjectModifiedEvent'))
        modified_event = self.collected_events[1]
        modified_event_user = IPerson(modified_event.user)
        self.failUnless(
            IObjectModifiedEvent.providedBy(modified_event),
            failure_msg(
                "%s doesn't provide IObjectModifiedEvent"
                % modified_event))
        self.failUnless(
            modified_event.object == self.question,
            failure_msg("IObjectModifiedEvent contains wrong question"))
        self.failUnless(
            modified_event_user == message.owner,
            failure_msg("%s != %s" % (
                modified_event_user.displayname, message.owner.displayname)))
        if edited_fields:
            self.failUnless(
                set(modified_event.edited_fields) == set(edited_fields),
                failure_msg("%s != %s" % (
                    set(modified_event.edited_fields), set(edited_fields))))


class MiscAnswerTrackerWorkflowTestCase(BaseAnswerTrackerWorkflowTestCase):
    """Various other test cases for the Answer Tracker workflow."""

    def testDisallowNoOpSetStatus(self):
        """Test that calling setStatus to change to the same status
        raises an InvalidQuestionStateError.
        """
        login('foo.bar@canonical.com')
        self.assertRaises(InvalidQuestionStateError, self.question.setStatus,
                self.admin, QuestionStatus.OPEN, 'Status Change')


class RequestInfoTestCase(BaseAnswerTrackerWorkflowTestCase):
    """Test cases for the requestInfo() workflow action method."""

    def test_can_request_info(self):
        """Test the can_request_info attribute in all the possible states."""
        self._testTransitionGuard(
            'can_request_info', ['OPEN', 'NEEDSINFO', 'ANSWERED'])

    def test_requestInfo(self):
        """Test that requestInfo() can be called in the OPEN, NEEDSINFO,
        and ANSWERED state and that it returns a valid IQuestionMessage.
        """
        # Do no check the edited_fields attribute since it varies depending
        # on the departure state.
        self._testValidTransition(
            [QuestionStatus.OPEN, QuestionStatus.NEEDSINFO],
            expected_owner=self.answerer,
            expected_action=QuestionAction.REQUESTINFO,
            expected_status=QuestionStatus.NEEDSINFO,
            transition_method=self.question.requestInfo,
            transition_method_args=(
                self.answerer, "What's your problem?"),
            edited_fields=None)

        # Even if the question is answered, a user can request more
        # information, but that leave the question in the ANSWERED state.
        self.setQuestionStatus(self.question, QuestionStatus.ANSWERED)
        self.collected_events = []
        message = self.question.requestInfo(
            self.answerer,
            "The previous answer is bad. What is the problem again?",
            datecreated=self.nowPlus(3))
        self.checkTransitionMessage(
            message, expected_owner=self.answerer,
            expected_action=QuestionAction.REQUESTINFO,
            expected_status=QuestionStatus.ANSWERED)
        self.checkTransitionEvents(
            message, ['messages', 'datelastresponse'],
            QuestionStatus.OPEN.title)

    def test_requestInfoFromOwnerIsInvalid(self):
        """Test that the question owner cannot use requestInfo."""
        self.assertRaises(
            NotQuestionOwnerError, self.question.requestInfo,
                self.owner, 'Why should I care?', datecreated=self.nowPlus(1))

    def test_requestInfoFromInvalidStates(self):
        """Test that requestInfo cannot be called when the question status is
        not OPEN, NEEDSINFO, or ANSWERED.
        """
        self._testInvalidTransition(
            ['OPEN', 'NEEDSINFO', 'ANSWERED'], self.question.requestInfo,
            self.answerer, "What's up?", datecreated=self.nowPlus(3))

    def test_requestInfoPermission(self):
        """Test that only a logged in user can access requestInfo()."""
        login(ANONYMOUS)
        self.assertRaises(Unauthorized, getattr, self.question, 'requestInfo')

        login_person(self.answerer)
        getattr(self.question, 'requestInfo')


class GiveInfoTestCase(BaseAnswerTrackerWorkflowTestCase):
    """Test cases for the giveInfo() workflow action method."""

    def test_can_give_info(self):
        """Test the can_give_info attribute in all the possible states."""
        self._testTransitionGuard('can_give_info', ['OPEN', 'NEEDSINFO'])

    def test_giveInfoFromInvalidStates(self):
        """Test that giveInfo cannot be called when the question status is
        not OPEN or NEEDSINFO.
        """
        self._testInvalidTransition(
            ['OPEN', 'NEEDSINFO'], self.question.giveInfo,
            "That's that.", datecreated=self.nowPlus(1))

    def test_giveInfo(self):
        """Test that giveInfo() can be called when the question status is
        OPEN or NEEDSINFO and that it returns a valid IQuestionMessage.
        """
        # Do not check the edited_fields attributes since it
        # changes based on departure state.
        self._testValidTransition(
            [QuestionStatus.OPEN, QuestionStatus.NEEDSINFO],
            expected_owner=self.owner,
            expected_action=QuestionAction.GIVEINFO,
            expected_status=QuestionStatus.OPEN,
            transition_method=self.question.giveInfo,
            transition_method_args=("That's that.", ),
            edited_fields=None)

    def test_giveInfoPermission(self):
        """Test that only the owner can access giveInfo()."""
        login(ANONYMOUS)
        self.assertRaises(Unauthorized, getattr, self.question, 'giveInfo')
        login_person(self.answerer)
        self.assertRaises(Unauthorized, getattr, self.question, 'giveInfo')
        login_person(self.admin)
        self.assertRaises(Unauthorized, getattr, self.question, 'giveInfo')

        login_person(self.owner)
        getattr(self.question, 'giveInfo')


class GiveAnswerTestCase(BaseAnswerTrackerWorkflowTestCase):
    """Test cases for the giveAnswer() workflow action method."""

    def test_can_give_answer(self):
        """Test the can_give_answer attribute in all the possible states."""
        self._testTransitionGuard(
            'can_give_answer', ['OPEN', 'NEEDSINFO', 'ANSWERED'])

    def test_giveAnswerFromInvalidStates(self):
        """Test that giveAnswer cannot be called when the question status is
        not OPEN, NEEDSINFO, or ANSWERED.
        """
        self._testInvalidTransition(
            ['OPEN', 'NEEDSINFO', 'ANSWERED'], self.question.giveAnswer,
            self.answerer, "The answer is this.", datecreated=self.nowPlus(1))

    def test_giveAnswerByAnswerer(self):
        """Test that giveAnswer can be called when the question status is
        one of OPEN, NEEDSINFO or ANSWERED and check that it returns a
        valid IQuestionMessage.
        """
        # Do not check the edited_fields attributes since it
        # changes based on departure state.
        self._testValidTransition(
            [QuestionStatus.OPEN, QuestionStatus.NEEDSINFO,
             QuestionStatus.ANSWERED],
            expected_owner=self.answerer,
            expected_action=QuestionAction.ANSWER,
            expected_status=QuestionStatus.ANSWERED,
            transition_method=self.question.giveAnswer,
            transition_method_args=(
                self.answerer, "It looks like a real problem.", ),
            edited_fields=None)

    def test_giveAnswerByOwner(self):
        """Test giveAnswerByOwner().

        Test that giveAnswer can be called by the questions owner when the
        question status is one of OPEN, NEEDSINFO or ANSWERED and check
        that it returns a valid IQuestionMessage.
        """
        # Do not check the edited_fields attributes since it
        # changes based on departure state.
        self._testValidTransition(
            [QuestionStatus.OPEN, QuestionStatus.NEEDSINFO,
             QuestionStatus.ANSWERED],
            expected_owner=self.answerer,
            expected_action=QuestionAction.ANSWER,
            expected_status=QuestionStatus.ANSWERED,
            transition_method=self.question.giveAnswer,
            transition_method_args=(
                self.answerer, "It looks like a real problem.", ),
            edited_fields=None)

        # When the owner gives the answer, the question moves straight to
        # SOLVED.
        def checkAnswerMessage(message):
            """Check additional attributes set when the owner gives the
            answers.
            """
            self.assertEquals(None, self.question.answer)
            self.assertEquals(self.owner, self.question.answerer)
            self.assertEquals(message.datecreated, self.question.date_solved)

        self._testValidTransition(
            [QuestionStatus.OPEN, QuestionStatus.NEEDSINFO,
             QuestionStatus.ANSWERED],
            expected_owner=self.owner,
            expected_action=QuestionAction.CONFIRM,
            expected_status=QuestionStatus.SOLVED,
            extra_message_check=checkAnswerMessage,
            transition_method=self.question.giveAnswer,
            transition_method_args=(
                self.owner, "I found the solution.", ),
            transition_method_kwargs={'datecreated': self.nowPlus(3)},
            edited_fields=['status', 'messages', 'date_solved', 'answerer',
                           'datelastquery'])

    def test_giveAnswerPermission(self):
        """Test that only a logged in user can access giveAnswer()."""
        login(ANONYMOUS)
        self.assertRaises(Unauthorized, getattr, self.question, 'giveAnswer')

        login_person(self.answerer)
        getattr(self.question, 'giveAnswer')


class LinkFAQTestCase(BaseAnswerTrackerWorkflowTestCase):
    """Test cases for the giveAnswer() workflow action method."""

    def setUp(self):
        """Create an additional FAQ."""
        BaseAnswerTrackerWorkflowTestCase.setUp(self)

        # Only admin can create FAQ on ubuntu.
        login_person(self.admin)
        self.faq = self.ubuntu.newFAQ(
            self.admin, 'Generic HowTo', 'Describe how to do anything.')

        # Logs in as owner.
        login_person(self.owner)

    def test_linkFAQ(self):
        """Test that linkFAQ can be called when the question status is
        one of OPEN, NEEDSINFO or ANSWERED and check that it returns a
        valid IQuestionMessage.
        """
        # Do not check the edited_fields attributes since it
        # changes based on departure state.
        def checkFAQ(message):
            """Check that the FAQ attribute was set correctly."""
            self.assertEquals(self.question.faq, self.faq)

        self._testValidTransition(
            [QuestionStatus.OPEN, QuestionStatus.NEEDSINFO,
             QuestionStatus.ANSWERED],
            expected_owner=self.answerer,
            expected_action=QuestionAction.ANSWER,
            expected_status=QuestionStatus.ANSWERED,
            extra_message_check=checkFAQ,
            transition_method=self.question.linkFAQ,
            transition_method_args=(
                self.answerer, self.faq, "Check the FAQ!", ),
            edited_fields=None)

        # When the owner links the FAQ, the question moves straight to
        # SOLVED.
        def checkAnswerMessage(message):
            """Check additional attributes set when the owner gives the
            answers.
            """
            checkFAQ(message)
            self.assertEquals(self.owner, self.question.answerer)
            self.assertEquals(message.datecreated, self.question.date_solved)

        self._testValidTransition(
            [QuestionStatus.OPEN, QuestionStatus.NEEDSINFO,
             QuestionStatus.ANSWERED],
            expected_owner=self.owner,
            expected_action=QuestionAction.CONFIRM,
            expected_status=QuestionStatus.SOLVED,
            extra_message_check=checkAnswerMessage,
            transition_method=self.question.linkFAQ,
            transition_method_args=(
                self.owner, self.faq, "I found the solution in that FAQ.", ),
            transition_method_kwargs={'datecreated': self.nowPlus(3)},
            edited_fields=['status', 'messages', 'date_solved', 'answerer',
                           'datelastquery'])

    def test_linkFAQPermission(self):
        """Test that only a logged in user can access linkFAQ()."""
        login(ANONYMOUS)
        self.assertRaises(Unauthorized, getattr, self.question, 'linkFAQ')

        login_person(self.answerer)
        getattr(self.question, 'linkFAQ')


class ConfirmAnswerTestCase(BaseAnswerTrackerWorkflowTestCase):
    """Test cases for the confirmAnswer() workflow action method."""

    def test_can_confirm_answer_without_answer(self):
        """Test the can_confirm_answer attribute when no answer was posted.

        When the question didn't receive an answer, it should always be
        false.
        """
        self._testTransitionGuard('can_confirm_answer', [])

    def test_can_confirm_answer_with_answer(self):
        """Test that can_confirm_answer when there is an answer present.

        Once one answer was given, it becomes possible in some states.
        """
        self.question.giveAnswer(
            self.answerer, 'Do something about it.', self.nowPlus(1))
        self._testTransitionGuard(
            'can_confirm_answer',
            ['OPEN', 'NEEDSINFO', 'ANSWERED', 'GIVEINFO', 'SOLVED'])

    def test_confirmAnswerFromInvalidStates_without_answer(self):
        """Test calling confirmAnswer from invalid states.

        confirmAnswer() cannot be called when the question has no message with
        action ANSWER.
        """
        self._testInvalidTransition([], self.question.confirmAnswer,
            "That answer worked!.", datecreated=self.nowPlus(1))

    def test_confirmAnswerFromInvalidStates_with_answer(self):
        """ Test calling confirmAnswer from invalid states with an answer.

        When the question has a message with action ANSWER, confirmAnswer()
        can only be called when it is in the OPEN, NEEDSINFO, or ANSWERED
        state.
        """
        answer_message = self.question.giveAnswer(
            self.answerer, 'Do something about it.', self.nowPlus(1))
        self._testInvalidTransition(
            ['OPEN', 'NEEDSINFO', 'ANSWERED', 'SOLVED'],
            self.question.confirmAnswer, "That answer worked!.",
            answer=answer_message, datecreated=self.nowPlus(1))

    def test_confirmAnswerBeforeSOLVED(self):
        """Test confirmAnswer().

        Test that confirmAnswer() can be called when the question status
        is one of OPEN, NEEDSINFO, ANSWERED and that it has at least one
        ANSWER message and check that it returns a valid IQuestionMessage.
        """
        answer_message = self.question.giveAnswer(
            self.answerer, "Get a grip!", datecreated=self.nowPlus(1))

        def checkAnswerMessage(message):
            # Check the attributes that are set when an answer is confirmed.
            self.assertEquals(answer_message, self.question.answer)
            self.assertEquals(self.answerer, self.question.answerer)
            self.assertEquals(message.datecreated, self.question.date_solved)

        self._testValidTransition(
            [QuestionStatus.OPEN, QuestionStatus.NEEDSINFO,
             QuestionStatus.ANSWERED],
            expected_owner=self.owner,
            expected_action=QuestionAction.CONFIRM,
            expected_status=QuestionStatus.SOLVED,
            extra_message_check=checkAnswerMessage,
            transition_method=self.question.confirmAnswer,
            transition_method_args=("That was very useful.", ),
            transition_method_kwargs={'answer': answer_message,
                                      'datecreated': self.nowPlus(2)},
            edited_fields=['status', 'messages', 'date_solved', 'answerer',
                           'answer', 'datelastquery'])

    def test_confirmAnswerAfterSOLVED(self):
        """Test confirmAnswer().

        Test that confirmAnswer() can be called when the question status
        is SOLVED, and that it has at least one ANSWER message and check
        that it returns a valid IQuestionMessage.
        """
        answer_message = self.question.giveAnswer(
            self.answerer, "Press the any key.", datecreated=self.nowPlus(1))
        self.question.giveAnswer(
            self.owner, 'I solved my own problem.',
            datecreated=self.nowPlus(2))
        self.assertEquals(self.question.status, QuestionStatus.SOLVED)

        def checkAnswerMessage(message):
            # Check the attributes that are set when an answer is confirmed.
            self.assertEquals(answer_message, self.question.answer)
            self.assertEquals(self.answerer, self.question.answerer)
            self.assertEquals(message.datecreated, self.question.date_solved)

        self._testValidTransition(
            [QuestionStatus.SOLVED],
            expected_owner=self.owner,
            expected_action=QuestionAction.CONFIRM,
            expected_status=QuestionStatus.SOLVED,
            extra_message_check=checkAnswerMessage,
            transition_method=self.question.confirmAnswer,
            transition_method_args=("The space bar also works.", ),
            transition_method_kwargs={'answer': answer_message,
                                      'datecreated': self.nowPlus(2)},
            edited_fields=['messages', 'date_solved', 'answerer',
                           'answer', 'datelastquery'])

    def testCannotConfirmAnAnswerFromAnotherQuestion(self):
        """Test that you can't confirm an answer from a different question."""
        question1_answer = self.question.giveAnswer(
            self.answerer, 'Really, just do it!')
        question2 = self.ubuntu.newQuestion(self.owner, 'Help 2', 'Help me!')
        question2.giveAnswer(self.answerer, 'Do that!')
        answerRefused = False
        try:
            question2.confirmAnswer('That worked!', answer=question1_answer)
        except AssertionError:
            answerRefused = True
        self.failUnless(
            answerRefused, 'confirmAnswer accepted a message from a different'
            'question')

    def test_confirmAnswerPermission(self):
        """Test that only the owner can access confirmAnswer()."""
        login(ANONYMOUS)
        self.assertRaises(
            Unauthorized, getattr, self.question, 'confirmAnswer')
        login_person(self.answerer)
        self.assertRaises(
            Unauthorized, getattr, self.question, 'confirmAnswer')
        login_person(self.admin)
        self.assertRaises(
            Unauthorized, getattr, self.question, 'confirmAnswer')

        login_person(self.owner)
        getattr(self.question, 'confirmAnswer')


class ReopenTestCase(BaseAnswerTrackerWorkflowTestCase):
    """Test cases for the reopen() workflow action method."""

    def test_can_reopen(self):
        """Test the can_reopen attribute in all the possible states."""
        self._testTransitionGuard(
            'can_reopen', ['ANSWERED', 'EXPIRED', 'SOLVED'])

    def test_reopenFromInvalidStates(self):
        """Test that reopen cannot be called when the question status is
        not one of OPEN, NEEDSINFO, or ANSWERED.
        """
        self._testInvalidTransition(
            ['ANSWERED', 'EXPIRED', 'SOLVED'], self.question.reopen,
            "I still have a problem.", datecreated=self.nowPlus(1))

    def test_reopen(self):
        """Test that reopen() can be called when the question is in the
        ANSWERED and EXPIRED state and that it returns a valid
        IQuestionMessage.
        """
        self._testValidTransition(
            [QuestionStatus.ANSWERED, QuestionStatus.EXPIRED],
            expected_owner=self.owner,
            expected_action=QuestionAction.REOPEN,
            expected_status=QuestionStatus.OPEN,
            transition_method=self.question.reopen,
            transition_method_args=('I still have this problem.', ),
            edited_fields=['status', 'messages', 'datelastquery'])

    def test_reopenFromSOLVEDByOwner(self):
        """Test that reopen() can be called when the question is in the
        SOLVED state (by the question owner) and that it returns an
        appropriate IQuestionMessage. This transition should also clear
        the date_solved, answered and answerer attributes.
        """
        self.setUpEventListeners()
        # Mark the question as solved by the user.
        self.question.giveAnswer(
            self.owner, 'I solved my own problem.',
            datecreated=self.nowPlus(0))
        self.assertEquals(self.question.status, QuestionStatus.SOLVED)

        # Clear previous events.
        self.collected_events = []

        message = self.question.reopen(
            "My solution doesn't work.", datecreated=self.nowPlus(1))
        self.checkTransitionMessage(
            message, expected_owner=self.owner,
            expected_action=QuestionAction.REOPEN,
            expected_status=QuestionStatus.OPEN)
        self.checkTransitionEvents(
            message, ['status', 'messages', 'answerer',
                      'date_solved', 'datelastquery'],
            QuestionStatus.OPEN.title)

    def test_reopenFromSOLVEDByAnswerer(self):
        """Test that reopen() can be called when the question is in the
        SOLVED state (answer confirmed by the question owner) and that it
        returns an appropriate IQuestionMessage. This transition should
        also clear the date_solved, answered and answerer attributes.
        """
        self.setUpEventListeners()
        # Mark the question as solved by the user.
        answer_message = self.question.giveAnswer(
            self.answerer, 'Press the any key.', datecreated=self.nowPlus(0))
        self.question.confirmAnswer("That answer worked!.",
            answer=answer_message, datecreated=self.nowPlus(1))
        self.assertEquals(self.question.status, QuestionStatus.SOLVED)

        # Clear previous events.
        self.collected_events = []

        message = self.question.reopen(
            "Where is the any key?", datecreated=self.nowPlus(1))
        self.checkTransitionMessage(
            message, expected_owner=self.owner,
            expected_action=QuestionAction.REOPEN,
            expected_status=QuestionStatus.OPEN)
        self.checkTransitionEvents(
            message, ['status', 'messages', 'answerer', 'answer',
                      'date_solved'],
            QuestionStatus.OPEN.title)

    def test_reopenPermission(self):
        """Test that only the owner can access reopen()."""
        login(ANONYMOUS)
        self.assertRaises(Unauthorized, getattr, self.question, 'reopen')
        login_person(self.answerer)
        self.assertRaises(Unauthorized, getattr, self.question, 'reopen')
        login_person(self.admin)
        self.assertRaises(Unauthorized, getattr, self.question, 'reopen')

        login_person(self.owner)
        getattr(self.question, 'reopen')


class ExpireQuestionTestCase(BaseAnswerTrackerWorkflowTestCase):
    """Test cases for the expireQuestion() workflow action method."""

    def test_expireQuestionFromInvalidStates(self):
        """Test that expireQuestion cannot be called when the question status
        is not one of OPEN or NEEDSINFO.
        """
        self._testInvalidTransition(
            ['OPEN', 'NEEDSINFO'], self.question.expireQuestion,
            self.answerer, "Too late.", datecreated=self.nowPlus(1))

    def test_expireQuestion(self):
        """Test that expireQuestion() can be called when the question status
        is OPEN or NEEDSINFO and that it returns a valid IQuestionMessage.
        """
        self._testValidTransition(
            [QuestionStatus.OPEN, QuestionStatus.NEEDSINFO],
            expected_owner=self.answerer,
            expected_action=QuestionAction.EXPIRE,
            expected_status=QuestionStatus.EXPIRED,
            transition_method=self.question.expireQuestion,
            transition_method_args=(
                self.answerer, 'This question is expired.'),
            edited_fields=['status', 'messages', 'datelastresponse'])

    def test_expireQuestionPermission(self):
        """Test that only a logged in user can access expireQuestion()."""
        login(ANONYMOUS)
        self.assertRaises(
            Unauthorized, getattr, self.question, 'expireQuestion')

        login_person(self.answerer)
        getattr(self.question, 'expireQuestion')


class RejectTestCase(BaseAnswerTrackerWorkflowTestCase):
    """Test cases for the reject() workflow action method."""

    def test_rejectFromInvalidStates(self):
        """Test that reject() cannot be called when the question status is
        not one of OPEN or NEEDSINFO.
        """
        valid_statuses = [status.name for status in QuestionStatus.items
                          if status.name != 'INVALID']
        # Reject user must be an answer contact, (or admin, or product owner).
        # Answer contacts must speak a language
        self.answerer.addLanguage(getUtility(ILanguageSet)['en'])
        self.ubuntu.addAnswerContact(self.answerer, self.answerer)
        login_person(self.answerer)
        self._testInvalidTransition(
            valid_statuses, self.question.reject,
            self.answerer, "This is lame.", datecreated=self.nowPlus(1))

    def test_reject(self):
        """Test that reject() can be called when the question status is
        OPEN or NEEDSINFO and that it returns a valid IQuestionMessage.
        """
        # Reject user must be an answer contact, (or admin, or product owner).
        login_person(self.answerer)
        # Answer contacts must speak a language
        self.answerer.addLanguage(getUtility(ILanguageSet)['en'])
        self.ubuntu.addAnswerContact(self.answerer, self.answerer)
        valid_statuses = [status for status in QuestionStatus.items
                          if status.name != 'INVALID']

        def checkRejectMessageIsAnAnswer(message):
            # Check that the rejection message was considered answering
            # the question.
            self.assertEquals(message, self.question.answer)
            self.assertEquals(self.answerer, self.question.answerer)
            self.assertEquals(message.datecreated, self.question.date_solved)

        self._testValidTransition(
            valid_statuses,
            expected_owner=self.answerer,
            expected_action=QuestionAction.REJECT,
            expected_status=QuestionStatus.INVALID,
            extra_message_check=checkRejectMessageIsAnAnswer,
            transition_method=self.question.reject,
            transition_method_args=(
                self.answerer, 'This is lame.'),
            edited_fields=['status', 'messages', 'answerer', 'date_solved',
                           'answer', 'datelastresponse'])

    def testRejectPermission(self):
        """Test the reject() access control.

        Only an answer contacts and administrator can reject a question.
        """
        login(ANONYMOUS)
        self.assertRaises(Unauthorized, getattr, self.question, 'reject')

        login_person(self.owner)
        self.assertRaises(Unauthorized, getattr, self.question, 'reject')

        login_person(self.answerer)
        self.assertRaises(Unauthorized, getattr, self.question, 'reject')

        # Answer contacts must speak a language
        self.answerer.addLanguage(getUtility(ILanguageSet)['en'])
        self.question.target.addAnswerContact(self.answerer, self.answerer)
        # clear authorization cache for check_permission
        clear_cache()
        self.assertTrue(
            getattr(self.question, 'reject'),
            "Answer contact cannot reject question.")
        login_person(self.admin)
        self.assertTrue(
            getattr(self.question, 'reject'),
            "Admin cannot reject question.")

    def testRejectPermission_indirect_answer_contact(self):
        # Indirect answer contacts (for a distribution) can reject
        # distribuiton source package questions.
        login_person(self.admin)
        dsp = self.ubuntu.getSourcePackage('mozilla-firefox')
        self.question.target = dsp
        login_person(self.answerer)
        self.answerer.addLanguage(getUtility(ILanguageSet)['en'])
        self.ubuntu.addAnswerContact(self.answerer, self.answerer)
        self.assertTrue(
            getattr(self.question, 'reject'),
            "Answer contact cannot reject question.")
