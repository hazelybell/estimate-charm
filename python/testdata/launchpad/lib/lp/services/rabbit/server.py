# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""RabbitMQ server fixture."""

__metaclass__ = type
__all__ = [
    'RabbitServer',
    ]

from textwrap import dedent

import rabbitfixture.server


class RabbitServer(rabbitfixture.server.RabbitServer):
    """A RabbitMQ server fixture with Launchpad-specific config.

    :ivar service_config: A snippet of .ini that describes the `rabbitmq`
        configuration.
    """

    def setUp(self):
        super(RabbitServer, self).setUp()
        self.config.service_config = dedent("""\
            [rabbitmq]
            host: localhost:%d
            userid: guest
            password: guest
            virtual_host: /
            """ % self.config.port)
