# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces for a Question."""

__metaclass__ = type

__all__ = [
    'IQuestion',
    'IQuestionAddMessageForm',
    'IQuestionChangeStatusForm',
    'IQuestionLinkFAQForm',
    ]


from lazr.restful.declarations import (
    call_with,
    export_as_webservice_entry,
    export_write_operation,
    exported,
    operation_for_version,
    operation_parameters,
    REQUEST_USER,
    )
from lazr.restful.fields import (
    CollectionField,
    Reference,
    ReferenceChoice,
    )
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Bool,
    Choice,
    Datetime,
    Int,
    Object,
    Text,
    TextLine,
    )

from lp import _
from lp.answers.enums import (
    QuestionPriority,
    QuestionStatus,
    )
from lp.answers.interfaces.faq import IFAQ
from lp.answers.interfaces.questionmessage import IQuestionMessage
from lp.answers.interfaces.questiontarget import IQuestionTarget
from lp.registry.interfaces.person import IPerson
from lp.registry.interfaces.role import IHasOwner
from lp.services.fields import PublicPersonChoice
from lp.services.worlddata.interfaces.language import ILanguage


class IQuestion(IHasOwner):
    """A single question, often a support request."""

    export_as_webservice_entry(as_of='beta')

    id = exported(Int(
        title=_('Question Number'), required=True, readonly=True,
        description=_("The tracking number for this question.")),
        as_of="devel")
    title = exported(TextLine(
        title=_('Summary'), required=True, description=_(
        "A one-line summary of the issue or problem.")),
        as_of="devel")
    description = exported(Text(
        title=_('Description'), required=True, description=_(
        "Include as much detail as possible: what "
        u"you\N{right single quotation mark}re trying to achieve, what steps "
        "you take, what happens, and what you think should happen instead.")),
        as_of="devel")
    status = exported(Choice(
        title=_('Status'), vocabulary=QuestionStatus,
        default=QuestionStatus.OPEN, readonly=True),
        as_of="devel")
    priority = Choice(
        title=_('Priority'), vocabulary=QuestionPriority,
        default=QuestionPriority.NORMAL)
    # XXX flacoste 2006-10-28: It should be more precise to define a new
    # vocabulary that excludes the English variants.
    language = exported(ReferenceChoice(
        title=_('Language'), vocabulary='Language', schema=ILanguage,
        description=_('The language in which this question is written.')),
        as_of="devel")
    owner = exported(PublicPersonChoice(
        title=_('Owner'), required=True, readonly=True,
        vocabulary='ValidPersonOrTeam'),
        as_of="devel")
    assignee = exported(PublicPersonChoice(
        title=_('Assignee'), required=False,
        description=_("The person responsible for helping to resolve the "
        "question."),
        vocabulary='ValidPersonOrTeam'),
        as_of="devel")
    answerer = exported(PublicPersonChoice(
        title=_('Answered By'), required=False,
        description=_("The person who last provided a response intended to "
        "resolve the question."),
        vocabulary='ValidPersonOrTeam'),
        as_of="devel",
        readonly=True)
    answer = exported(Reference(
        title=_('Answer'), required=False,
        description=_("The IQuestionMessage that contains the answer "
            "confirmed by the owner as providing a solution to his problem."),
        schema=IQuestionMessage),
        readonly=True, as_of="devel")
    datecreated = exported(Datetime(
        title=_('Date Created'), required=True, readonly=True),
        exported_as='date_created', readonly=True, as_of="devel")
    datedue = exported(Datetime(
        title=_('Date Due'), required=False, default=None,
        description=_(
            "The date by which we should have resolved this question.")),
        exported_as='date_due', readonly=True, as_of="devel")
    datelastquery = exported(Datetime(
        title=_("Date Last Queried"), required=True,
        description=_("The date on which we last heard from the "
        "customer (owner).")),
       exported_as='date_last_query',  readonly=True, as_of="devel")
    datelastresponse = exported(Datetime(
        title=_("Date last Responded"),
        required=False,
        description=_("The date on which we last communicated "
        "with the customer. The combination of datelastquery and "
        "datelastresponse tells us in whose court the ball is.")),
        exported_as='date_last_response', readonly=True, as_of="devel")
    date_solved = exported(Datetime(title=_("Date Answered"), required=False,
        description=_(
            "The date on which the question owner confirmed that the "
            "question is Solved.")),
        exported_as='date_solved', readonly=True, as_of="devel")
    product = Choice(
        title=_('Upstream Project'), required=False,
        vocabulary='Product',
        description=_('Select the upstream project with which you need '
            'support.'))
    distribution = Choice(
        title=_('Distribution'), required=False,
        vocabulary='Distribution', description=_('Select '
        'the distribution for which you need support.'))
    sourcepackagename = Choice(
        title=_('Source Package'), required=False,
        vocabulary='SourcePackageName', description=_('The source package '
        'in the distribution which contains the software with which you '
        'are experiencing difficulties.'))
    whiteboard = Text(
        title=_('Status Whiteboard'), required=False,
        description=_('Up-to-date notes on the status of the question.'))
    # other attributes
    target = exported(Reference(
        title=_('This question is about'), required=True,
        schema=IQuestionTarget,
        description=_('The distribution, source package, or project the '
                      'question pertains to.')),
        as_of="devel")
    faq = Object(
        title=_('Linked FAQ'),
        description=_('The FAQ document containing the long answer to this '
                      'question.'),
        readonly=True, required=False, schema=IFAQ)

    # joins
    subscriptions = Attribute(
        'The set of subscriptions to this question.')
    reopenings = Attribute(
        "Records of times when this question was reopened.")
    messages = exported(CollectionField(
        title=_("Messages"),
        description=_(
            "The list of messages that were exchanged as part of this "
            "question , sorted from first to last."),
        value_type=Reference(schema=IQuestionMessage),
        required=True, default=[], readonly=True),
        as_of='devel')

    # Workflow methods
    def setStatus(user, new_status, comment, datecreated=None):
        """Change the status of this question.

        Set the question's status to new_status and add an IQuestionMessage
        with action SETSTATUS.

        Only the question target owner or admin can change the status using
        this method.

        An InvalidQuestiontateError is raised when this method is called
        with new_status equals to the current question status.

        Return the created IQuestionMessage.

        This method should fire an IObjectCreatedEvent for the created
        IQuestionMessage and an IObjectModifiedEvent for the question.

        :user: The IPerson making the change.
        :new_status: The new QuestionStatus
        :comment: A string or IMessage containing an explanation for the
                  change.
        :datecreated: Date for the message. Defaults to the current time.
        """

    can_request_info = Attribute(
        'Whether the question is in a state where a user can request more '
        'information from the question owner.')

    def requestInfo(user, question, datecreated=None):
        """Request more information from the question owner.

        Add an IQuestionMessage with action REQUESTINFO containing the
        question. The question's status is changed to NEEDSINFO, and the
        datelastresponse attribute is updated to the message creation date.

        The user requesting more information cannot be the question's owner.
        This workflow method should only be called when the question status is
        OPEN or NEEDSINFO. An InvalidQuestionStateError is raised otherwise.

        It can also be called when the question is in the ANSWERED state, but
        in that case, the status will stay unchanged.

        Return the created IQuestionMessage.

        This method should fire an IObjectCreatedEvent for the created
        IQuestionMessage and an IObjectModifiedEvent for the question.

        :user: IPerson requesting for the information.
        :question: A string or IMessage containing the question.
        :datecreated: Date for the answer. Defaults to the current time.
        """

    can_give_info = Attribute(
        'Whether the question is in a state where the question owner can '
        'give more information on the question.')

    def giveInfo(reply, datecreated=None):
        """Reply to the information request.

        Add an IQuestionMessage with action GIVEINFO. The question status is
        changed to OPEN, the datelastquery attribute is updated to the
        message creation time.

        This method should only be called on behalf of the question owner when
        the question is in the OPEN or NEEDSINFO state. An
        InvalidQuestionStateError is raised otherwise.

        Return the created IQuestionMessage.

        This method should fire an IObjectCreatedEvent for the created
        IQuestionMessage and an IObjectModifiedEvent for the question.

        :reply: A string or IMessage containing the new information.
        :datecreated: Date for the message. Defaults to the current time.
        """

    can_give_answer = Attribute(
        'Whether the question is in a state a user can provide an answer on '
        'the question.')

    def giveAnswer(user, answer, datecreated=None):
        """Give an answer to this question.

        If the user is not the question's owner, add an IQuestionMessage with
        action ANSWER containing an answer for the question. This changes the
        question's status to ANSWERED and updates the datelastresponse
        attribute to the message's creation date.

        When the question owner answers the question, add an IQuestionMessage
        with action CONFIRM. The question status is changed to SOLVED, the
        answerer attribute is updated to contain the question owner, the
        answer attribute will be updated to point at the new message, the
        datelastresponse and date_solved attributes are updated to the
        message creation date.

        This workflow method should only be called when the question status is
        one of OPEN, ANSWERED or NEEDSINFO. An InvalidQuestionStateError is
        raised otherwise.

        Return the created IQuestionMessage.

        This method should fire an IObjectCreatedEvent for the created
        IQuestionMessage and an IObjectModifiedEvent for the question.

        :user: IPerson giving the answer.
        :answer: A string or IMessage containing the answer.
        :datecreated: Date for the message. Defaults to the current time.
        """

    def linkFAQ(user, faq, comment, datecreated=None):
        """Link a FAQ as an answer to this question.

        Exactly like giveAnswer() but also link the IFAQ faq object to this
        question.

        Return the created IQuestionMessage.

        This method should fire an IObjectCreatedEvent for the created
        IQuestionMessage and an IObjectModifiedEvent for the question.

        :param user: IPerson linking the faq.
        :param faq: The IFAQ containing the answer.
        :param comment: A string or IMessage explaining how the FAQ is
            relevant.
        :param datecreated: Date for the message. Defaults to the current
            time.
        """

    can_confirm_answer = Attribute(
        'Whether the question is in a state for the question owner to '
        'confirm that an answer solved his problem.')

    def confirmAnswer(comment, answer=None, datecreated=None):
        """Confirm that a solution to the question was found.

        Add an IQuestionMessage with action CONFIRM. The question status is
        changed to SOLVED. If the answer parameter is not None, it is recorded
        in the answer attribute and the answerer attribute is set to that
        message's owner. The datelastresponse and date_solved attributes are
        updated to the message creation date.

        This workflow method should only be called on behalf of the question
        owner, when the question status is ANSWERED, or when the status is
        OPEN or NEEDSINFO but an answer was already provided. An
        InvalidQuestionStateError is raised otherwise.

        Return the created IQuestionMessage.

        This method should fire an IObjectCreatedEvent for the created
        IQuestionMessage and an IObjectModifiedEvent for the question.

       :comment: A string or IMessage containing a comment.
        :answer: The IQuestionMessage that contain the answer to the question.
                 It must be one of the IQuestionMessage of this question.
        :datecreated: Date for the message. Defaults to the current time.
        """

    def canReject(user):
        """Test if a user can reject the question.

        Return true only if user is an answer contact for the question target,
        the question target owner or part of the administration team.
        """

    def reject(user, comment, datecreated=None):
        """Mark this question as INVALID.

        Add an IQuestionMessage with action REJECT. The question status is
        changed to INVALID. The created message is set as the question answer
        and its owner as the question answerer. The datelastresponse and
        date_solved are updated to the message creation.

        Only answer contacts for the question target, the target owner or a
        member of the admin team can reject a request. All questions can be
        rejected.

        Return the created IQuestionMessage.

        This method should fire an IObjectCreatedEvent for the created
        IQuestionMessage and an IObjectModifiedEvent for the question.

        :user: The user rejecting the request.
        :comment: A string or IMessage containing an explanation of the
                  rejection.
        :datecreated: Date for the message. Defaults to the current time.
        """

    def expireQuestion(user, comment, datecreated=None):
        """Mark a question as EXPIRED.

        Add an IQuestionMessage with action EXPIRE. This changes the question
        status to EXPIRED and update the datelastresponse attribute to the new
        message creation date.

        This workflow method should only be called when the question status is
        one of OPEN or NEEDSINFO. An InvalidQuestionStateError is raised
        otherwise.

        Return the created IQuestionMessage.

        (Note this method is named expireQuestion and not expire because of
        conflicts with SQLObject.)

        This method should fire an IObjectCreatedEvent for the created
        IQuestionMessage and an IObjectModifiedEvent for the question.

        :user: IPerson expiring the request.
        :comment: A string or IMessage containing an explanation for the
                  expiration.
        :datecreated: Date for the message. Defaults to the current time.
        """

    can_reopen = Attribute(
        'Whether the question state is a state where the question owner '
        'could reopen it.')

    def reopen(comment, datecreated=None):
        """Reopen a question that was ANSWERED, EXPIRED or SOLVED.

        Add an IQuestionMessage with action REOPEN. This changes the question
        status to OPEN and update the datelastquery attribute to the new
        message creation date. When the question was in the SOLVED state, this
        method should reset the date_solved, answerer and answer attributes.

        This workflow method should only be called on behalf of the question
        owner, when the question status is in one of ANSWERED, EXPIRED or
        SOLVED. An InvalidQuestionStateError is raised otherwise.

        Return the created IQuestionMessage.

        This method should fire an IObjectCreatedEvent for the created
        IQuestionMessage and an IObjectModifiedEvent for the question.

        :comment: A string or IMessage containing more information about the
                  request.
        :datecreated: Date for the message. Defaults to the current time.
        """

    def addComment(user, comment, datecreated=None):
        """Add a comment on the question.

        Create an IQuestionMessage with action COMMENT. It leaves the question
        status unchanged.

        This method should fire an IObjectCreatedEvent for the created
        IQuestionMessage and an IObjectModifiedEvent for the question.

        :user: The IPerson making the comment.
        :comment: A string or IMessage containing the comment.
        :datecreated: Date for the message. Defaults to the current time.
        """

    # subscription-related methods

    @operation_parameters(
        person=Reference(IPerson, title=_('Person'), required=True))
    @call_with(subscribed_by=REQUEST_USER)
    @export_write_operation()
    @operation_for_version("devel")
    def subscribe(person, subscribed_by=None):
        """Subscribe `person` to the question.

        :param person: the subscriber.
        :param subscribed_by: the person who created the subscription.
        :return: an `IQuestionSubscription`.
        """

    def isSubscribed(person):
        """Return a boolean indicating whether the person is subscribed."""

    @operation_parameters(
        person=Reference(IPerson, title=_('Person'), required=False))
    @call_with(unsubscribed_by=REQUEST_USER)
    @export_write_operation()
    @operation_for_version("devel")
    def unsubscribe(person, unsubscribed_by):
        """Unsubscribe `person` from the question.

        :param person: the subscriber.
        :param unsubscribed_by: the person who removed the subscription.
        """

    def getDirectSubscribers():
        """Return the persons who are subscribed to this question.

        :return: A list of persons sorted by displayname.
        """

    def getDirectSubscribersWithDetails():
        """Get direct subscribers and their subscriptions for the question.

        :returns: A ResultSet of tuples (Person, QuestionSubscription)
            representing a subscriber and their question subscription.
        """

    def getIndirectSubscribers():
        """Return the persons who are implicitly subscribed to this question.

        :return: A list of persons sorted by displayname.
        """

    def getRecipients():
        """Return the set of person to notify about changes in this question.

        That is the union of getDirectSubscribers() and
        getIndirectSubscribers().

        :return: An `INotificationRecipientSet` containing the persons to
            notify along the rationale for doing so.
        """

    direct_recipients = Attribute(
        "Return An `INotificationRecipientSet` containing the persons to "
        "notify along the rationale for doing so.")

    indirect_recipients = Attribute(
        "Return the INotificationRecipientSet of answer contacts for the "
        "question's target as well as the question's assignee.")

    @operation_parameters(
        comment_number=Int(
            title=_('The number of the comment in the list of messages.'),
            required=True),
        visible=Bool(title=_('Show this comment?'), required=True))
    @call_with(user=REQUEST_USER)
    @export_write_operation()
    @operation_for_version('devel')
    def setCommentVisibility(user, comment_number, visible):
        """Set the visible attribute on a question message.

        This is restricted to Launchpad admins and registry members, and will
        return a HTTP Error 401: Unauthorized error for non-admin callers.
        """


# These schemas are only used by browser/question.py and should really live
# there. See Bug #66950.
class IQuestionAddMessageForm(Interface):
    """Form schema for adding a message to a question.

    This will usually includes a status change as well.
    """

    message = Text(title=_('Message'), required=False)

    subscribe_me = Bool(
        title=_('E-mail me future discussion about this question'),
        required=False, default=False)


class IQuestionChangeStatusForm(Interface):
    """Form schema for changing the status of a question."""

    status = Choice(
        title=_('Status'), description=_('Select the new question status.'),
        vocabulary=QuestionStatus, required=True)

    message = Text(
        title=_('Message'),
        description=_('Enter an explanation for the status change'),
        required=True)


class IQuestionLinkFAQForm(Interface):
    """Form schema for the `QuestionLinkFAQView`."""

    faq = Choice(
        title=_('Which is the relevant FAQ?'),
        description=_(
            'Select the FAQ that is the most relevant for this question. '
            'You can modify the list of suggested FAQs by editing the search '
            'field and clicking "Search".'),
        vocabulary='FAQ', required=False, default=None)

    message = Text(
        title=_('Answer Message'),
        description=_(
            'Enter a comment that will be added as the question comments. '
            'The title of the FAQ will be automatically appended to this '
            'message.'),
        required=True)
