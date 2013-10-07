# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Make a distroseries obsolete."""

__metaclass__ = type

__all__ = ['ObsoleteDistroseries']

from itertools import chain

from lp.registry.interfaces.series import SeriesStatus
from lp.services.database.constants import UTC_NOW
from lp.soyuz.scripts.ftpmasterbase import (
    SoyuzScript,
    SoyuzScriptError,
    )


class ObsoleteDistroseries(SoyuzScript):
    """`SoyuzScript` that obsoletes a distroseries."""

    usage = "%prog -d <distribution> -s <suite>"
    description = ("Make obsolete (schedule for removal) packages in an "
                  "obsolete distroseries.")

    def add_my_options(self):
        """Add -d, -s, dry-run and confirmation options."""
        SoyuzScript.add_distro_options(self)
        SoyuzScript.add_transaction_options(self)

    def mainTask(self):
        """Execute package obsolescence procedure.

        Modules using this class outside of its normal usage in the
        main script can call this method to start the copy.

        In this case the caller can override test_args on __init__
        to set the command line arguments.

        :raise SoyuzScriptError: If the distroseries is not provided or
            it is already obsolete.
        """
        assert self.location, (
            "location is not available, call SoyuzScript.setupLocation() "
            "before calling mainTask().")

        # Shortcut variable name to reduce long lines.
        distroseries = self.location.distroseries

        self._checkParameters(distroseries)

        self.logger.info("Obsoleting all packages for distroseries %s in "
                         "the %s distribution." % (
                            distroseries.name,
                            distroseries.distribution.name))

        # First, mark all Published sources as Obsolete.
        sources = distroseries.getAllPublishedSources()
        binaries = distroseries.getAllPublishedBinaries()
        self.logger.info(
            "Obsoleting published packages (%d sources, %d binaries)."
            % (sources.count(), binaries.count()))
        for package in chain(sources, binaries):
            self.logger.debug("Obsoleting %s" % package.displayname)
            package.requestObsolescence()

        # Next, ensure that everything is scheduled for deletion.  The
        # dominator will normally leave some superseded publications
        # uncondemned, for example sources that built NBSed binaries.
        sources = distroseries.getAllUncondemnedSources()
        binaries = distroseries.getAllUncondemnedBinaries()
        self.logger.info(
            "Scheduling deletion of other packages (%d sources, %d binaries)."
            % (sources.count(), binaries.count()))
        for package in chain(sources, binaries):
            self.logger.debug(
                "Scheduling deletion of %s" % package.displayname)
            package.scheduleddeletiondate = UTC_NOW

        # The packages from both phases will be caught by death row
        # processing the next time it runs.  We skip the domination
        # phase in the publisher because it won't consider stable
        # distroseries.

    def _checkParameters(self, distroseries):
        """Sanity check the supplied script parameters."""
        # Did the user provide a suite name? (distribution defaults
        # to 'ubuntu' which is fine.)
        if distroseries == distroseries.distribution.currentseries:
            # SoyuzScript defaults to the latest series.  Since this
            # will never get obsoleted it's safe to assume that the
            # user let this option default, so complain and exit.
            raise SoyuzScriptError(
                "Please specify a valid distroseries name with -s/--suite "
                "and which is not the most recent distroseries.")

        # Is the distroseries in an obsolete state?  Bail out now if not.
        if distroseries.status != SeriesStatus.OBSOLETE:
            raise SoyuzScriptError(
                "%s is not at status OBSOLETE." % distroseries.name)
