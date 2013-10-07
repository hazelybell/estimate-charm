#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).


"""Tool for 'mass-retrying' build records.

It supports build collections based distroseries and/or distroarchseries.
"""

__metaclass__ = type

import _pythonpath

import transaction
from zope.component import getUtility

from lp.app.errors import NotFoundError
from lp.buildmaster.enums import BuildStatus
from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.services.scripts.base import (
    LaunchpadScript,
    LaunchpadScriptFailure,
    )


class BuilddMassRetryScript(LaunchpadScript):

    dbuser = "fiera"

    def add_my_options(self):
        self.parser.add_option(
            "-d", "--distribution", dest="distribution",
            metavar="DISTRIBUTION", default="ubuntu",
            help="distribution name")

        self.parser.add_option(
            "-s", "--suite", dest="suite", metavar="SUITE", help="suite name")

        self.parser.add_option(
            "-a", "--architecture", dest="architecture", metavar="ARCH",
            help="architecture tag")

        self.parser.add_option(
            "-N", "--dry-run", action="store_true", dest="dryrun",
            metavar="DRY_RUN", default=False,
            help="Whether to treat this as a dry-run or not.")

        self.parser.add_option(
            "-F", "--failed", action="store_true", dest="failed",
            default=False, help="Reset builds in FAILED state.")

        self.parser.add_option(
            "-D", "--dep-wait", action="store_true", dest="depwait",
            default=False, help="Reset builds in DEPWAIT state.")

        self.parser.add_option(
            "-C", "--chroot-wait", action="store_true", dest="chrootwait",
            default=False, help="Reset builds in CHROOTWAIT state.")

    def main(self):
        try:
            distribution = getUtility(IDistributionSet)[
                self.options.distribution]
        except NotFoundError as info:
            raise LaunchpadScriptFailure("Distribution not found: %s" % info)

        try:
            if self.options.suite is not None:
                series, pocket = distribution.getDistroSeriesAndPocket(
                    self.options.suite)
            else:
                series = distribution.currentseries
                pocket = PackagePublishingPocket.RELEASE
        except NotFoundError as info:
            raise LaunchpadScriptFailure("Suite not found: %s" % info)

        # store distroseries as the current IHasBuildRecord provider
        build_provider = series

        if self.options.architecture:
            try:
                dar = series[self.options.architecture]
            except NotFoundError as info:
                raise LaunchpadScriptFailure(info)

            # store distroarchseries as the current IHasBuildRecord provider
            build_provider = dar

        self.logger.info(
            "Initializing Build Mass-Retry for '%s/%s'"
            % (build_provider.title, pocket.name))

        requested_states_map = {
            BuildStatus.FAILEDTOBUILD: self.options.failed,
            BuildStatus.MANUALDEPWAIT: self.options.depwait,
            BuildStatus.CHROOTWAIT: self.options.chrootwait,
            }

        # XXX cprov 2006-08-31: one query per requested state
        # could organise it in a single one nicely if I have
        # an empty SQLResult instance, than only iteration + union()
        # would work.
        for target_state, requested in requested_states_map.items():
            if not requested:
                continue

            self.logger.info("Processing builds in '%s'" % target_state.title)
            target_builds = build_provider.getBuildRecords(
                build_state=target_state, pocket=pocket)

            for build in target_builds:
                # Skip builds for superseded sources; they won't ever
                # actually build.
                if not build.current_source_publication:
                    self.logger.debug(
                        'Skipping superseded %s (%s)'
                        % (build.title, build.id))
                    continue

                if not build.can_be_retried:
                    self.logger.warn(
                        'Can not retry %s (%s)' % (build.title, build.id))
                    continue

                self.logger.info('Retrying %s (%s)' % (build.title, build.id))
                build.retry()

        self.logger.info("Success.")

        if self.options.dryrun:
            transaction.abort()
            self.logger.info('Dry-run.')
        else:
            transaction.commit()
            self.logger.info("Committed")


if __name__ == '__main__':
    BuilddMassRetryScript('buildd-mass-retry', 'fiera').lock_and_run()
