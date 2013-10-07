# Copyright 2011-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'AddAnswerContactError',
    'FAQTargetError',
    'InvalidQuestionStateError',
    'NotAnswerContactError',
    'NotMessageOwnerError',
    'NotQuestionOwnerError',
    'QuestionTargetError',
    ]

import httplib

from lazr.restful.declarations import error_status


@error_status(httplib.BAD_REQUEST)
class AddAnswerContactError(ValueError):
    """The person cannot be an answer contact.

    An answer contacts must be a valid user or team that has a preferred
    language.
    """


@error_status(httplib.BAD_REQUEST)
class FAQTargetError(ValueError):
    """The target must be an `IFAQTarget`."""


@error_status(httplib.BAD_REQUEST)
class InvalidQuestionStateError(ValueError):
    """Error raised when the question is in an invalid state.

    Error raised when a workflow action cannot be executed because the
    question would be in an invalid state.
    """


@error_status(httplib.BAD_REQUEST)
class NotAnswerContactError(ValueError):
    """The person must be an answer contact."""


@error_status(httplib.BAD_REQUEST)
class NotMessageOwnerError(ValueError):
    """The person must be the message owner."""


@error_status(httplib.BAD_REQUEST)
class NotQuestionOwnerError(ValueError):
    """The person must be the question owner."""


@error_status(httplib.BAD_REQUEST)
class QuestionTargetError(ValueError):
    """The target must be an `IQueastionTarget`."""
