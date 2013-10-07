#!/usr/bin/python -S
#
# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Script to probe distribution mirrors and check how up-to-date they are."""

import _pythonpath

import os

from lp.registry.interfaces.distributionmirror import MirrorContent
from lp.registry.scripts.distributionmirror_prober import DistroMirrorProber
from lp.services.config import config
from lp.services.scripts.base import (
    LaunchpadCronScript,
    LaunchpadScriptFailure,
    )


class DistroMirrorProberScript(LaunchpadCronScript):
    usage = ('%prog --content-type=(archive|cdimage) [--force] '
             '[--no-owner-notification] [--max-mirrors=N]')

    def add_my_options(self):
        self.parser.add_option('--content-type',
            dest='content_type', default=None, action='store',
            help='Probe only mirrors of the given type')
        self.parser.add_option('--force',
            dest='force', default=False, action='store_true',
            help='Force the probing of mirrors that were probed recently')
        self.parser.add_option('--no-owner-notification',
            dest='no_owner_notification', default=False, action='store_true',
            help='Do not send failure notification to mirror owners.')
        self.parser.add_option('--no-remote-hosts',
            dest='no_remote_hosts', default=False, action='store_true',
            help='Do not try to connect to any host other than localhost.')
        self.parser.add_option('--max-mirrors',
            dest='max_mirrors', default=None, action='store', type="int",
            help='Only probe N mirrors.')

    def main(self):
        if self.options.content_type == 'archive':
            content_type = MirrorContent.ARCHIVE
        elif self.options.content_type == 'cdimage':
            content_type = MirrorContent.RELEASE
        else:
            raise LaunchpadScriptFailure(
                'Wrong value for argument --content-type: %s'
                % self.options.content_type)

        if config.distributionmirrorprober.use_proxy:
            os.environ['http_proxy'] = config.launchpad.http_proxy
            self.logger.debug("Using %s as proxy." % os.environ['http_proxy'])
        else:
            self.logger.debug("Not using any proxy.")

        DistroMirrorProber(self.txn, self.logger).probe(
            content_type, self.options.no_remote_hosts, self.options.force,
            self.options.max_mirrors, not self.options.no_owner_notification)


if __name__ == '__main__':
    script = DistroMirrorProberScript(
        'distributionmirror-prober',
        dbuser=config.distributionmirrorprober.dbuser)
    script.lock_and_run(isolation='autocommit')
