# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Answers's custom publication."""

__metaclass__ = type
__all__ = [
    'AnswersBrowserRequest',
    'AnswersLayer',
    'answers_request_publication_factory',
    ]


from zope.interface import implements
from zope.publisher.interfaces.browser import (
    IBrowserRequest,
    IDefaultBrowserLayer,
    )

from lp.services.webapp.publication import LaunchpadBrowserPublication
from lp.services.webapp.servers import (
    LaunchpadBrowserRequest,
    VHostWebServiceRequestPublicationFactory,
    )


class AnswersLayer(IBrowserRequest, IDefaultBrowserLayer):
    """The Answers layer."""


class AnswersBrowserRequest(LaunchpadBrowserRequest):
    """Instances of AnswersBrowserRequest provide `AnswersLayer`."""
    implements(AnswersLayer)

    def __init__(self, body_instream, environ, response=None):
        super(AnswersBrowserRequest, self).__init__(
            body_instream, environ, response)
        # Many of the responses from Answers vary based on language.
        self.response.setHeader(
            'Vary', 'Cookie, Authorization, Accept-Language')


def answers_request_publication_factory():
    return VHostWebServiceRequestPublicationFactory(
        'answers', AnswersBrowserRequest, LaunchpadBrowserPublication)
