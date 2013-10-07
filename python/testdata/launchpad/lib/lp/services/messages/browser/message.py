# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Message related view classes."""

__metaclass__ = type

from zope.interface import implements

from lp.services.messages.interfaces.message import IIndexedMessage
from lp.services.webapp.interfaces import ICanonicalUrlData


class QuestionMessageCanonicalUrlData:
    """Question messages have a canonical_url within the question."""
    implements(ICanonicalUrlData)
    rootsite = 'answers'

    def __init__(self, question, message):
        self.inside = question
        self.path = "messages/%d" % list(question.messages).index(message)


class BugMessageCanonicalUrlData:
    """Bug messages have a canonical_url within the primary bugtask."""
    implements(ICanonicalUrlData)
    rootsite = 'bugs'

    def __init__(self, bug, message):
        self.inside = bug.default_bugtask
        self.path = "comments/%d" % list(bug.messages).index(message)


class IndexedBugMessageCanonicalUrlData:
    """An optimized bug message canonical_url implementation.

    This implementation relies on the message being decorated with
    its index and context.
    """
    implements(ICanonicalUrlData)
    rootsite = 'bugs'

    def __init__(self, message):
        self.inside = message.inside
        self.path = "comments/%d" % message.index


def message_to_canonical_url_data(message):
    """This factory creates `ICanonicalUrlData` for Message."""
    # Circular imports
    from lp.answers.interfaces.questionmessage import IQuestionMessage
    if IIndexedMessage.providedBy(message):
        return IndexedBugMessageCanonicalUrlData(message)
    elif IQuestionMessage.providedBy(message):
        return QuestionMessageCanonicalUrlData(message.question, message)
    else:
        if message.bugs.count() == 0:
        # Will result in a ComponentLookupError
            return None
        return BugMessageCanonicalUrlData(message.bugs[0], message)
