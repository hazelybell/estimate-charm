# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for bugs' custom publications."""

__metaclass__ = type

from lp.bugs.publisher import BugsLayer
from lp.layers import WebServiceLayer
from lp.services.config import config
from lp.testing import TestCase
from lp.testing.layers import FunctionalLayer
from lp.testing.publication import get_request_and_publication


class TestRegistration(TestCase):
    """Bugs publication customizations are installed correctly."""

    layer = FunctionalLayer

    def test_bugs_request_provides_bugs_layer(self):
        # The request constructed for requests to the bugs hostname provides
        # BugsLayer.
        request, publication = get_request_and_publication(
            host=config.vhost.bugs.hostname)
        self.assertProvides(request, BugsLayer)

    def test_bugs_host_has_api(self):
        # Requests to /api on the bugs domain are treated as web service
        # requests.
        request, publication = get_request_and_publication(
            host=config.vhost.bugs.hostname,
            extra_environment={'PATH_INFO': '/api/1.0'})
        # XXX MichaelHudson, 2010-07-20, bug=607664: WebServiceLayer only
        # actually provides WebServiceLayer in the sense of verifyObject after
        # traversal has started.
        self.assertTrue(WebServiceLayer.providedBy(request))
