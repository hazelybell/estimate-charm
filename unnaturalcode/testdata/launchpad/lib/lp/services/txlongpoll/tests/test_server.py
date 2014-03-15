# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for lp.services.rabbit.TxLongPollServer."""

__metaclass__ = type

from ConfigParser import SafeConfigParser
import os
from StringIO import StringIO

from lp.services.config import config
from lp.services.txlongpoll.server import TxLongPollServer
from lp.testing import TestCase
from lp.testing.layers import RabbitMQLayer


class TestTxLongPollServer(TestCase):

    layer = RabbitMQLayer

    def test_service_config(self):
        # TxLongPollServer pokes some .ini configuration into its
        # service_config attributes.
        twistd_bin = os.path.join(
            config.root, 'bin', 'twistd-for-txlongpoll')
        fixture = self.useFixture(TxLongPollServer(
            broker_user='guest', broker_password='guest', broker_vhost='/',
            broker_port=123, frontend_port=None,
            twistd_bin=twistd_bin))
        service_config = SafeConfigParser()
        service_config.readfp(StringIO(getattr(fixture, 'service_config')))
        self.assertEqual(["txlongpoll"], service_config.sections())
        # txlongpoll section
        expected = {
            "frontend_port": "%d" % fixture.config.frontend_port,
            }
        observed = dict(service_config.items("txlongpoll"))
        self.assertEqual(expected, observed)
