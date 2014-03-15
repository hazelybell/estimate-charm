# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the web service WADL and HTML generation APIs."""

__metaclass__ = type

from lazr.restful.interfaces import IWebServiceConfiguration
from testtools.matchers import StartsWith
from zope.component import getUtility

from lp.services.webservice.wadl import (
    generate_json,
    generate_wadl,
    )
from lp.systemhomes import WebServiceApplication
from lp.testing import TestCase
from lp.testing.layers import LaunchpadFunctionalLayer


class SmokeTestWadlAndDocGeneration(TestCase):
    """Smoke test the WADL and HTML generation front-end functions."""

    layer = LaunchpadFunctionalLayer

    def test_wadl(self):
        preexisting_wadl_cache = WebServiceApplication.cached_wadl.copy()
        config = getUtility(IWebServiceConfiguration)
        for version in config.active_versions:
            wadl = generate_wadl(version)
            self.assertThat(wadl[:40], StartsWith('<?xml '))
        WebServiceApplication.cached_wadl = preexisting_wadl_cache

    def test_json(self):
        config = getUtility(IWebServiceConfiguration)
        for version in config.active_versions:
            json = generate_json(version)
            self.assertThat(json, StartsWith('{"'))
