# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for code's custom publications."""

__metaclass__ = type

from lp.code.publisher import CodeLayer
from lp.layers import WebServiceLayer
from lp.services.config import config
from lp.testing import TestCase
from lp.testing.layers import FunctionalLayer
from lp.testing.publication import get_request_and_publication


class TestRegistration(TestCase):
    """Code's publication customizations are installed correctly."""

    layer = FunctionalLayer

    def test_code_request_provides_code_layer(self):
        # The request constructed for requests to the code hostname provides
        # CodeLayer.
        request, publication = get_request_and_publication(
            host=config.vhost.code.hostname)
        self.assertProvides(request, CodeLayer)

    def test_code_host_has_api(self):
        # Requests to /api on the code domain are treated as web service
        # requests.
        request, publication = get_request_and_publication(
            host=config.vhost.code.hostname,
            extra_environment={'PATH_INFO': '/api/1.0'})
        # XXX MichaelHudson, 2010-07-20, bug=607664: WebServiceLayer only
        # actually provides WebServiceLayer in the sense of verifyObject after
        # traversal has started.
        self.assertTrue(WebServiceLayer.providedBy(request))
