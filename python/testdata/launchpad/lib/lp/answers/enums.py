# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Question enumerations."""

# Enums are kept separated from the classes that use them to avoid
# circular imports. Notably, QuestonAction and QuestionStatus are
# used by most of the schemas for question classes.

__all__ = [
    'QuestionAction',
    'QuestionJobType',
    'QuestionParticipation',
    'QuestionPriority',
    'QuestionRecipientSet',
    'QUESTION_STATUS_DEFAULT_SEARCH',
    'QuestionSort',
    'QuestionStatus',
    ]

from lazr.enum import (
    DBEnumeratedType,
    DBItem,
    EnumeratedType,
    Item,
    )


class QuestionAction(DBEnumeratedType):
    """An enumeration of the possible actions done on a question.

    This enumeration is used to tag the action done by a user with
    each QuestionMessage. Most of these action indicates a status change
    on the question.
    """

    REQUESTINFO = DBItem(10, """
        Request for more information

        This message asks for more information about the question.
        """)

    GIVEINFO = DBItem(20, """
        Give more information

        In this message, the submitter provides more information about the
        question.
        """)

    COMMENT = DBItem(30, """
        Comment

        User commented on the message. This is use for example for messages
        added to a question in the SOLVED state.
        """)

    ANSWER = DBItem(35, """
        Answer

        This message provides an answer to the question.
        """)

    CONFIRM = DBItem(40, """
        Confirm

        This message confirms that an answer solved the question.
        """)

    REJECT = DBItem(50, """
        Reject

        This message rejects a question as invalid.
        """)

    EXPIRE = DBItem(70, """
        Expire

        Automatic message created when the question is expired.
        """)

    REOPEN = DBItem(80, """
        Reopen

        Message from the submitter that reopens the question while providing
        more information.
        """)

    SETSTATUS = DBItem(90, """
        Change status

        Message from an administrator that explain why the question status
        was changed.
        """)


class QuestionJobType(DBEnumeratedType):
    """Values that IQuestionJob.job_type can take."""

    EMAIL = DBItem(0, """
        Question email notification

        Notify question subscribers about a question via email.
        """)


class QuestionRecipientSet(EnumeratedType):
    """The kinds of recipients who will receive notification."""

    ASKER = Item("""
        Asker

        The person who asked the question.
        """)

    SUBSCRIBER = Item("""
        Subscriber

        The question's direct and indirect subscribers, exception for
        the asker.
        """)

    ASKER_SUBSCRIBER = Item("""
        Asker and Subscriber

        The question's direct and indirect subscribers, including the asker.
        """)

    CONTACT = Item("""
        Contact

        All the answer contacts for the question's target.
        """)


class QuestionParticipation(EnumeratedType):
    """The different ways a person can be involved in a question.

    This enumeration is part of the IPerson.searchTickets() API.
    """

    OWNER = Item("""
        Owner

        The person created the question.
        """)

    SUBSCRIBER = Item("""
        Subscriber

        The person subscribed to the question.
        """)

    ASSIGNEE = Item("""
        Assignee

        The person is assigned to the question.
        """)

    COMMENTER = Item("""
        Commenter

        The person commented on the question.
        """)

    ANSWERER = Item("""
        Answerer

        The person answered the question.
        """)


class QuestionPriority(DBEnumeratedType):
    """The Priority with a Question must be handled.

    This enum is used to prioritize work done in the Launchpad Answert Tracker
    management system.
    """

    WISHLIST = DBItem(0, """
        Wishlist

        This question is really a request for a new feature. We will not take
        it further as a question, it should be closed, and a specification
        created and managed in the Launchpad Specification tracker.
        """)

    NORMAL = DBItem(10, """
        Normal

        This question is of normal priority. We should respond to it in due
        course.
        """)

    HIGH = DBItem(70, """
        High

        This question has been flagged as being of higher than normal
        priority. It should always be prioritized over a "normal" question.
        """)

    EMERGENCY = DBItem(90, """
        Emergency

        This question is classed as an emergency. No more than 5% of
        questions should fall into this category. Support engineers should
        ensure that there is somebody on this problem full time until it is
        resolved, or escalate it to the core technical and management team.
        """)


class QuestionSort(EnumeratedType):
    """An enumeration of the valid question search sort order.

    This enumeration is part of the ITicketTarget.searchTickets() API. The
    titles are formatted for nice display in browser code.
    """

    RELEVANCY = Item("""
    by relevancy

    Sort by relevancy of the question toward the search text.
    """)

    STATUS = Item("""
    by status

    Sort questions by status: Open, Needs information, Answered, Solved,
    Expired, Invalid.

    NEWEST_FIRST should be used as a secondary sort key.
    """)

    NEWEST_FIRST = Item("""
    newest first

    Sort questions from newest to oldest.
    """)

    OLDEST_FIRST = Item("""
    oldest first

    Sort questions from oldset to newest.
    """)

    RECENT_OWNER_ACTIVITY = Item("""
    recently updated first

    Sort questions that received new information from the owner first.
    """)


class QuestionStatus(DBEnumeratedType):
    """The current status of a Question.

    This enum tells us the current status of the question.

    The lifecycle of a question is documented in
    https://help.launchpad.net/QuestionLifeCycle, so remember
    to update that document for any pertinent changes.
    """

    OPEN = DBItem(10, """
        Open

        The question is waiting for an answer. This could be a new question
        or a question where the given answer was refused by the submitter.
        """)

    NEEDSINFO = DBItem(15, """
        Needs information

        A user requested more information from the submitter. The question
        will be moved back to the OPEN state once the submitter provides the
        answer.
        """)

    ANSWERED = DBItem(18, """
        Answered

        An answer was given on this question. We assume that the answer
        is the correct one. The user will post back changing the question's
        status back to OPEN if that is not the case.
        """)

    SOLVED = DBItem(20, """
        Solved

        The submitter confirmed that an answer solved his question.
        """)

    EXPIRED = DBItem(25, """
        Expired

        The question has been expired after 15 days without comments in the
        OPEN or NEEDSINFO state.
        """)

    INVALID = DBItem(30, """
        Invalid

        This question isn't a valid question. It could be a duplicate
        question, spam or anything that should not appear in the
        Answer Tracker.
        """)


QUESTION_STATUS_DEFAULT_SEARCH = (
    QuestionStatus.OPEN, QuestionStatus.NEEDSINFO, QuestionStatus.ANSWERED,
    QuestionStatus.SOLVED)
