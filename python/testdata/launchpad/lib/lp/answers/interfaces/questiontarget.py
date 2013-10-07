# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces for things which have Questions."""

__metaclass__ = type

__all__ = [
    'IAnswersFrontPageSearchForm',
    'IQuestionTarget',
    'ISearchQuestionsForm',
    ]

from lazr.restful.declarations import (
    call_with,
    export_as_webservice_entry,
    export_read_operation,
    export_write_operation,
    operation_for_version,
    operation_parameters,
    operation_returns_collection_of,
    REQUEST_USER,
    )
from lazr.restful.fields import Reference
from zope.interface import Interface
from zope.schema import (
    Choice,
    Int,
    List,
    Set,
    TextLine,
    )

from lp import _
from lp.answers.enums import (
    QUESTION_STATUS_DEFAULT_SEARCH,
    QuestionSort,
    QuestionStatus,
    )
from lp.answers.interfaces.questioncollection import (
    ISearchableByQuestionOwner,
    )
from lp.registry.interfaces.person import IPerson
from lp.services.fields import PublicPersonChoice
from lp.services.worlddata.interfaces.language import ILanguage


class IQuestionTargetPublic(ISearchableByQuestionOwner):
    """Methods that anonymous in user can access."""

    @operation_parameters(
        question_id=Int(title=_('Question Number'), required=True))
    @export_read_operation()
    @operation_for_version('devel')
    def getQuestion(question_id):
        """Return the question by its id, if it is applicable to this target.

        :question_id: A question id.

        If there is no such question number for this target, return None
        """

    @operation_parameters(
        phrase=TextLine(title=_('A phrase'), required=True))
    @operation_returns_collection_of(Interface)
    @export_read_operation()
    @operation_for_version('devel')
    def findSimilarQuestions(phrase):
        """Return questions similar to phrase.

        Return a list of question similar to the provided phrase. These
        questions will be found using a fuzzy search. The list is
        ordered from the most similar question to the least similar question.

        :param phrase: A phrase such as the summary of a question.
        """

    @operation_parameters(
        language=Reference(ILanguage))
    @operation_returns_collection_of(IPerson)
    @export_read_operation()
    @operation_for_version('devel')
    def getAnswerContactsForLanguage(language):
        """Return the list of Persons that provide support for a language.

        An answer contact supports questions in his preferred languages.
        """

    def getAnswerContactRecipients(language):
        """Return an `INotificationRecipientSet` of answer contacts.

        :language: an ILanguage or None. When language is none, all
                   answer contacts are returned.

        Return an INotificationRecipientSet of the answer contacts and the
        reason they are recipients of an email. The answer contacts are
        selected by their language and the fact that they are answer contacts
        for the QuestionTarget.
        """

    @operation_returns_collection_of(ILanguage)
    @export_read_operation()
    @operation_for_version('devel')
    def getSupportedLanguages():
        """Return a list of languages spoken by at the answer contacts.

        An answer contact is considered to speak a given language if that
        language is listed as one of his preferred languages.
        """

    answer_contacts = List(
        title=_("Answer Contacts"),
        description=_(
            "Persons that are willing to provide support for this target. "
            "They receive email notifications about each new question as "
            "well as for changes to any questions related to this target."),
        value_type=PublicPersonChoice(vocabulary="ValidPersonOrTeam"))

    direct_answer_contacts = List(
        title=_("Direct Answer Contacts"),
        description=_(
            "IPersons that registered as answer contacts explicitely on "
            "this target. (answer_contacts may include answer contacts "
            "inherited from other context.)"),
        value_type=PublicPersonChoice(vocabulary="ValidPersonOrTeam"))

    @operation_parameters(
        person=PublicPersonChoice(
            title=_('The user or an administered team'), required=True,
            vocabulary='ValidPersonOrTeam'))
    @call_with(subscribed_by=REQUEST_USER)
    @export_read_operation()
    @operation_for_version('devel')
    def canUserAlterAnswerContact(person, subscribed_by):
        """Can the user add or remove the answer contact.

        Users can add or remove themselves or one of the teams they
        administered. Admins and target owners can add/remove anyone.

        :param person: The `IPerson` that is or will be an answer contact.
        :param subscribed_by: The `IPerson` making the change.
        """


class IQuestionTargetView(Interface):
    """Methods that logged in user can access."""

    def newQuestion(owner, title, description, language=None,
                    datecreated=None):
        """Create a new question.

         A new question is created with status OPEN.

        The owner and all of the target answer contacts will be subscribed
        to the question.

        :owner: An IPerson.
        :title: A string.
        :description: A string.
        :language: An ILanguage. If that parameter is omitted, the question
                 is assumed to be created in English.
        :datecreated:  A datetime object that will be used for the datecreated
                attribute. Defaults to lp.services.database.constants.UTC_NOW.
        """

    def createQuestionFromBug(bug):
        """Create and return a Question from a Bug.

        The bug's title and description are used as the question title and
        description. The bug owner is the question owner. The question
        is automatically linked to the bug.

        Note that bug messages are copied to the question, but attachments
        are not. The question is the same age as the bug, though its
        datelastresponse attribute is current to signify the question is
        active.

        :bug: An IBug.
        """

    @operation_parameters(
        person=PublicPersonChoice(
            title=_('The user of an administered team'), required=True,
            vocabulary='ValidPersonOrTeam'))
    @call_with(subscribed_by=REQUEST_USER)
    @export_write_operation()
    @operation_for_version('devel')
    def addAnswerContact(person, subscribed_by):
        """Add a new answer contact.

        :param person: An `IPerson`.
        :param subscribed_by: The user making the change.
        :return: True if the person was added, False if the person already is
            an answer contact.
        :raises AddAnswerContactError: When the person or team does no have a
            preferred language.
        """

    @operation_parameters(
        person=PublicPersonChoice(
            title=_('The user of an administered team'), required=True,
            vocabulary='ValidPersonOrTeam'))
    @call_with(subscribed_by=REQUEST_USER)
    @export_write_operation()
    @operation_for_version('devel')
    def removeAnswerContact(person, subscribed_by):
        """Remove an answer contact.

        :param person: An `IPerson`.
        :param subscribed_by: The user making the change.
        :return: True if the person was removed, False if the person wasn't an
            answer contact.
        """


class IQuestionTarget(IQuestionTargetPublic, IQuestionTargetView):
    """An object that can have a new question asked about it."""
    export_as_webservice_entry(as_of='devel')


# These schemas are only used by browser/questiontarget.py and should really
# live there. See Bug #66950.
class ISearchQuestionsForm(Interface):
    """Schema for the search question form."""

    search_text = TextLine(title=_('Search text'), required=False)

    sort = Choice(title=_('Sort order'), required=True,
                  vocabulary=QuestionSort,
                  default=QuestionSort.RELEVANCY)

    status = Set(title=_('Status'), required=False,
                 value_type=Choice(vocabulary=QuestionStatus),
                 default=set(QUESTION_STATUS_DEFAULT_SEARCH))


class IAnswersFrontPageSearchForm(ISearchQuestionsForm):
    """Schema for the Answers front page search form."""

    scope = Choice(title=_('Search scope'), required=False,
                   vocabulary='DistributionOrProductOrProjectGroup')
