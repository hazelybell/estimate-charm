# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for lp.services.rabbit.RabbitServer."""

__metaclass__ = type

from ConfigParser import SafeConfigParser
from StringIO import StringIO

from fixtures import EnvironmentVariableFixture

from lp.services.rabbit.server import RabbitServer
from lp.testing import TestCase
from lp.testing.layers import BaseLayer


class TestRabbitServer(TestCase):

    layer = BaseLayer

    def test_service_config(self):
        # Rabbit needs to fully isolate itself: an existing per user
        # .erlang.cookie has to be ignored, and ditto bogus HOME if other
        # tests fail to cleanup.
        self.useFixture(EnvironmentVariableFixture('HOME', '/nonsense/value'))

        # RabbitServer pokes some .ini configuration into its config.
        fixture = self.useFixture(RabbitServer())
        service_config = SafeConfigParser()
        service_config.readfp(StringIO(fixture.config.service_config))
        self.assertEqual(["rabbitmq"], service_config.sections())
        expected = {
            "host": "localhost:%d" % fixture.config.port,
            "userid": "guest",
            "password": "guest",
            "virtual_host": "/",
            }
        observed = dict(service_config.items("rabbitmq"))
        self.assertEqual(expected, observed)
