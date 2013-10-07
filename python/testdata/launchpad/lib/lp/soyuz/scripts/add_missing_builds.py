# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import sys

from lp.app.errors import NotFoundError
from lp.services.scripts.base import LaunchpadScriptFailure
from lp.soyuz.enums import PackagePublishingStatus
from lp.soyuz.scripts.ftpmasterbase import (
    SoyuzScript,
    SoyuzScriptError,
    )


class AddMissingBuilds(SoyuzScript):
    """Helper class to create builds in PPAs for requested architectures."""

    def add_missing_builds(self, archive, required_arches, distroseries,
                           pocket):
        """Create builds in an archive as necessary.

        :param archive: The `Archive`.
        :param required_arches: A list of `DistroArchSeries`.
        :param distroseries: The context `DistroSeries` in which to create
            builds.
        :param pocket: The context `PackagePublishingPocket`.
        """
        # Listify the architectures to avoid hitting this MultipleJoin
        # multiple times.
        distroseries_architectures = list(distroseries.architectures)
        if not distroseries_architectures:
            self.logger.error(
                "No architectures defined for %s, skipping"
                % distroseries.name)
            return

        architectures_available = set(distroseries.buildable_architectures)
        if not architectures_available:
            self.logger.error(
                "Chroots missing for %s" % distroseries.name)
            return

        self.logger.info(
            "Supported architectures in %s: %s" % (
                distroseries.name,
                ", ".join(arch_series.architecturetag
                         for arch_series in architectures_available)))

        required_arch_set = set(required_arches)
        doable_arch_set = architectures_available.intersection(
            required_arch_set)
        if len(doable_arch_set) == 0:
            self.logger.error("Requested architectures not available")
            return

        sources = archive.getPublishedSources(
            distroseries=distroseries,
            pocket=pocket,
            status=PackagePublishingStatus.PUBLISHED)
        sources = list(sources)
        if not sources:
            self.logger.info("No sources published, nothing to do.")
            return

        self.logger.info("Creating builds in %s" %
                 " ".join(arch_series.architecturetag
                          for arch_series in doable_arch_set))
        for pubrec in sources:
            self.logger.info("Considering %s" % pubrec.displayname)
            builds = pubrec.createMissingBuilds(
                architectures_available=doable_arch_set, logger=self.logger)
            if len(builds) > 0:
                self.logger.info("Created %s build(s)" % len(builds))

    def add_my_options(self):
        """Command line options for this script."""
        self.add_archive_options()
        self.add_distro_options()
        self.parser.add_option(
            "-a", action="append", dest='arch_tags', default=[])

    def main(self):
        """Entry point for `LaunchpadScript`s."""
        try:
            self.setupLocation()
        except SoyuzScriptError as err:
            raise LaunchpadScriptFailure(err)

        if not self.options.arch_tags:
            self.parser.error("Specify at least one architecture.")

        arches = []
        for arch_tag in self.options.arch_tags:
            try:
                das = self.location.distroseries.getDistroArchSeries(arch_tag)
                arches.append(das)
            except NotFoundError:
                self.parser.error(
                    "%s not a valid architecture for %s" % (
                        arch_tag, self.location.distroseries.name))

        # I'm tired of parsing options.  Let's do it.
        try:
            self.add_missing_builds(
                self.location.archive, arches, self.location.distroseries,
                self.location.pocket)
            self.txn.commit()
            self.logger.info("Finished adding builds.")
        except Exception as err:
            self.logger.error(err)
            self.txn.abort()
            self.logger.info("Errors, aborted transaction.")
            sys.exit(1)

