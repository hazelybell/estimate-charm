# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for answers's custom publications."""

__metaclass__ = type

import StringIO

from lp.answers.publisher import (
    AnswersBrowserRequest,
    AnswersLayer,
    )
from lp.layers import WebServiceLayer
from lp.services.config import config
from lp.testing import TestCase
from lp.testing.layers import FunctionalLayer
from lp.testing.publication import get_request_and_publication


class TestRegistration(TestCase):
    """Answers' publication customizations are installed correctly."""

    layer = FunctionalLayer

    def test_answers_request_provides_answers_layer(self):
        # The request constructed for requests to the answers hostname
        # provides AnswersLayer.
        request, publication = get_request_and_publication(
            host=config.vhost.answers.hostname)
        self.assertProvides(request, AnswersLayer)

    def test_answers_host_has_api(self):
        # Requests to /api on the answers domain are treated as web service
        # requests.
        request, publication = get_request_and_publication(
            host=config.vhost.answers.hostname,
            extra_environment={'PATH_INFO': '/api/1.0'})
        # XXX MichaelHudson, 2010-07-20, bug=607664: WebServiceLayer only
        # actually provides WebServiceLayer in the sense of verifyObject after
        # traversal has started.
        self.assertTrue(WebServiceLayer.providedBy(request))

    def test_response_should_vary_based_on_language(self):
        # Responses to requests to answers pages have the 'Vary' header set to
        # include Accept-Language.
        request = AnswersBrowserRequest(StringIO.StringIO(''), {})
        self.assertEquals(
            request.response.getHeader('Vary'),
            'Cookie, Authorization, Accept-Language')
