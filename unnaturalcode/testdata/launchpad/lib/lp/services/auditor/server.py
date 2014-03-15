# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Auditor server fixture."""

__metaclass__ = type
__all__ = [
    'AuditorServer',
    ]

from textwrap import dedent

from auditorfixture.server import AuditorFixture


class AuditorServer(AuditorFixture):
    """An Auditor server fixture with Launchpad-specific config.

    :ivar service_config: A snippet of .ini that describes the `auditor`
        configuration.
    """

    def setUp(self):
        super(AuditorServer, self).setUp()
        self.service_config = dedent("""\
            [auditor]
            port: %d""" % (self.config.port))
