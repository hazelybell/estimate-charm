# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for translations's custom publications."""

__metaclass__ = type

import StringIO

from lp.layers import WebServiceLayer
from lp.services.config import config
from lp.testing import TestCase
from lp.testing.layers import FunctionalLayer
from lp.testing.publication import get_request_and_publication
from lp.translations.publisher import (
    TranslationsBrowserRequest,
    TranslationsLayer,
    )


class TestRegistration(TestCase):
    """Translations's publication customizations are installed correctly."""

    layer = FunctionalLayer

    def test_translations_request_provides_translations_layer(self):
        # The request constructed for requests to the translations hostname
        # provides TranslationsLayer.
        request, publication = get_request_and_publication(
            host=config.vhost.translations.hostname)
        self.assertProvides(request, TranslationsLayer)

    def test_translations_host_has_api(self):
        # Requests to /api on the translations domain are treated as web
        # service requests.
        request, publication = get_request_and_publication(
            host=config.vhost.translations.hostname,
            extra_environment={'PATH_INFO': '/api/1.0'})
        # XXX MichaelHudson, 2010-07-20, bug=607664: WebServiceLayer only
        # actually provides WebServiceLayer in the sense of verifyObject after
        # traversal has started.
        self.assertTrue(WebServiceLayer.providedBy(request))

    def test_response_should_vary_based_on_language(self):
        # Responses to requests to translations pages have the 'Vary' header
        # set to include Accept-Language.
        request = TranslationsBrowserRequest(StringIO.StringIO(''), {})
        self.assertEquals(
            request.response.getHeader('Vary'),
            'Cookie, Authorization, Accept-Language')
