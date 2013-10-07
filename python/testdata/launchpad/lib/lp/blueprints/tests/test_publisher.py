# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for blueprints' custom publications."""

__metaclass__ = type

from lp.blueprints.publisher import BlueprintsLayer
from lp.layers import WebServiceLayer
from lp.services.config import config
from lp.testing import TestCase
from lp.testing.layers import FunctionalLayer
from lp.testing.publication import get_request_and_publication


class TestRegistration(TestCase):
    """Blueprints's publication customizations are installed correctly."""

    layer = FunctionalLayer

    def test_blueprints_request_provides_blueprints_layer(self):
        # The request constructed for requests to the blueprints hostname
        # provides BlueprintsLayer.
        request, publication = get_request_and_publication(
            host=config.vhost.blueprints.hostname)
        self.assertProvides(request, BlueprintsLayer)

    def test_blueprints_host_has_api(self):
        # Requests to /api on the blueprints domain are treated as web service
        # requests.
        request, publication = get_request_and_publication(
            host=config.vhost.blueprints.hostname,
            extra_environment={'PATH_INFO': '/api/1.0'})
        # XXX MichaelHudson, 2010-07-20, bug=607664: WebServiceLayer only
        # actually provides WebServiceLayer in the sense of verifyObject after
        # traversal has started.
        self.assertTrue(WebServiceLayer.providedBy(request))
