# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

""" Karma for the Answer Tracker. """

__metaclass__ = type
__all__ = [
    'assignKarmaUsingQuestionContext',
    ]

from lp.answers.enums import QuestionAction
from lp.registry.interfaces.distribution import IDistribution
from lp.registry.interfaces.person import IPerson
from lp.registry.interfaces.product import IProduct
from lp.services.database.sqlbase import block_implicit_flushes


def assignKarmaUsingQuestionContext(person, question, actionname):
    """Assign Karma with the given actionname to the given person.

    Use the given question's context as the karma context.
    """
    person.assignKarma(
        actionname, product=question.product,
    distribution=question.distribution,
        sourcepackagename=question.sourcepackagename)


@block_implicit_flushes
def question_created(question, event):
    """Assign karma to the user which created <question>."""
    assignKarmaUsingQuestionContext(
        question.owner, question, 'questionasked')


@block_implicit_flushes
def question_modified(question, event):
    """Check changes made to <question> and assign karma to user if needed."""
    user = IPerson(event.user)
    old_question = event.object_before_modification

    if old_question.description != question.description:
        assignKarmaUsingQuestionContext(
            user, question, 'questiondescriptionchanged')

    if old_question.title != question.title:
        assignKarmaUsingQuestionContext(
            user, question, 'questiontitlechanged')


QuestionAction2KarmaAction = {
    QuestionAction.REQUESTINFO: 'questionrequestedinfo',
    QuestionAction.GIVEINFO: 'questiongaveinfo',
    QuestionAction.SETSTATUS: None,
    QuestionAction.COMMENT: 'questioncommentadded',
    QuestionAction.ANSWER: 'questiongaveanswer',
    QuestionAction.CONFIRM: None,
    QuestionAction.EXPIRE: None,
    QuestionAction.REJECT: 'questionrejected',
    QuestionAction.REOPEN: 'questionreopened',
}


@block_implicit_flushes
def question_comment_added(questionmessage, event):
    """Assign karma to the user which added <questionmessage>."""
    question = questionmessage.question
    karma_action = QuestionAction2KarmaAction.get(questionmessage.action)
    if karma_action:
        assignKarmaUsingQuestionContext(
            questionmessage.owner, question, karma_action)


def get_karma_context_parameters(context):
    """Return the proper karma context parameters based on the object."""
    # XXX flacoste 2007-07-13 bug=125849:
    # This should go away once bug #125849 is fixed.
    params = dict(product=None, distribution=None)
    if IProduct.providedBy(context):
        params['product'] = context
    elif IDistribution.providedBy(context):
        params['distribution'] = context
    else:
        raise AssertionError('Unknown karma context: %r' % context)
    return params


@block_implicit_flushes
def faq_created(faq, event):
    """Assign karma to the user who created the FAQ."""
    context = get_karma_context_parameters(faq.target)
    faq.owner.assignKarma('faqcreated', **context)


@block_implicit_flushes
def faq_edited(faq, event):
    """Assign karma to user who edited a FAQ."""
    user = IPerson(event.user)
    old_faq = event.object_before_modification

    context = get_karma_context_parameters(faq.target)
    if old_faq.content != faq.content or old_faq.title != faq.title:
        user.assignKarma('faqedited', **context)
