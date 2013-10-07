# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'IQuestionsPerson',
    ]

from lazr.restful.declarations import (
    export_read_operation,
    operation_for_version,
    operation_parameters,
    operation_returns_collection_of,
    )
from lazr.restful.fields import ReferenceChoice
from zope.interface import Interface
from zope.schema import (
    Bool,
    Choice,
    List,
    TextLine,
    )

from lp import _
from lp.answers.enums import (
    QUESTION_STATUS_DEFAULT_SEARCH,
    QuestionParticipation,
    QuestionSort,
    QuestionStatus,
    )
from lp.answers.interfaces.questioncollection import IQuestionCollection


class IQuestionsPerson(IQuestionCollection):

    @operation_returns_collection_of(Interface)  # IQuestionTarget.
    @export_read_operation()
    @operation_for_version('devel')
    def getDirectAnswerQuestionTargets():
        """Return a list of IQuestionTargets that a person is subscribed to.

        This will return IQuestionTargets that the person is registered as an
        answer contact because he subscribed himself.
        """

    @operation_returns_collection_of(Interface)  # IQuestionTarget
    @export_read_operation()
    @operation_for_version('devel')
    def getTeamAnswerQuestionTargets():
        """Return a list of IQuestionTargets that are indirect subscriptions.

        This will return IQuestionTargets that the person or team is
        registered as an answer contact because of his membership in a team.
        """

    @operation_parameters(
        search_text=TextLine(
            title=_('Search text'), required=False),
        status=List(
            title=_('Status'), required=False,
            value_type=Choice(vocabulary=QuestionStatus)),
        language=List(
            title=_('Language'), required=False,
            value_type=ReferenceChoice(vocabulary='Language')),
        participation=Choice(
            title=_('Participation'), required=False,
            vocabulary=QuestionParticipation),
        needs_attention=Bool(
            title=_('Needs attentions from'), default=False, required=False),
        sort=Choice(
            title=_('Sort'), required=False,
            vocabulary=QuestionSort))
    @operation_returns_collection_of(Interface)  # IQuestion.
    @export_read_operation()
    @operation_for_version('devel')
    def searchQuestions(search_text=None,
                        # Lp wants a sequence, but lazr.restful only supports
                        # lists; cast the tuple as a list.
                        status=list(QUESTION_STATUS_DEFAULT_SEARCH),
                        language=None, sort=None, participation=None,
                        needs_attention=None):
        """Search the person's questions.

        :param search_text: A string that is matched against the question
            title and description. If None, the search_text is not included as
            a filter criteria.
        :param status: A sequence of QuestionStatus Items. If None or an empty
            sequence, the status is not included as a filter criteria. The
            default is to match all status except Expired and Invalid.
        :param language: An ILanguage or a sequence of ILanguage objects to
            match against the question's language. If None or an empty
            sequence, the language is not included as a filter criteria.
        :param participation: A list of QuestionParticipation that defines the
            set of relationship to questions that will be searched. If None or
            an empty sequence, all relationships are considered.
        :param needs_attention: If this flag is true, only questions that
            need attention the person will be included. These are the
            questions in the NEEDSINFO or ANSWERED state owned by the person.
            The questions not owned by the person but on which the person
            requested more information or gave an answer and that are back in
            the OPEN state are also included.
        :param sort: An attribute of QuestionSort. If None, a default value is
            used. When there is a search_text value, the default is to sort by
            RELEVANCY, otherwise results are sorted NEWEST_FIRST.
        """
