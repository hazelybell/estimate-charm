# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for lp.services.auditor.AuditorServer."""

__metaclass__ = type

from ConfigParser import SafeConfigParser
from StringIO import StringIO

from lp.services.auditor.server import AuditorServer
from lp.testing import TestCase
from lp.testing.layers import BaseLayer


class TestAuditorServer(TestCase):

    layer = BaseLayer

    def test_service_config(self):
        # AuditorServer pokes some .ini configuration into its config.
        fixture = self.useFixture(AuditorServer())
        service_config = SafeConfigParser()
        service_config.readfp(StringIO(fixture.service_config))
        self.assertEqual(["auditor"], service_config.sections())
        expected = {"port": "%d" % fixture.config.port}
        observed = dict(service_config.items("auditor"))
        self.assertEqual(expected, observed)
