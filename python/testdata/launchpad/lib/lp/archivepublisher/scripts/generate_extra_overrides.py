# Copyright 2011-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Generate extra overrides using Germinate."""

__metaclass__ = type
__all__ = [
    'GenerateExtraOverrides',
    ]

from functools import partial
import glob
import logging
from optparse import OptionValueError
import os
import re

from germinate.archive import TagFile
from germinate.germinator import Germinator
from germinate.log import GerminateFormatter
from germinate.seeds import (
    SeedError,
    SeedStructure,
    )
from zope.component import getUtility

from lp.archivepublisher.config import getPubConfig
from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.interfaces.series import SeriesStatus
from lp.services.database.policy import (
    DatabaseBlockedPolicy,
    SlaveOnlyDatabasePolicy,
    )
from lp.services.scripts.base import (
    LaunchpadScript,
    LaunchpadScriptFailure,
    )
from lp.services.utils import file_exists


class AtomicFile:
    """Facilitate atomic writing of files."""

    def __init__(self, filename):
        self.filename = filename
        self.fd = open("%s.new" % self.filename, "w")

    def __enter__(self):
        return self.fd

    def __exit__(self, exc_type, exc_value, exc_tb):
        self.fd.close()
        if exc_type is None:
            os.rename("%s.new" % self.filename, self.filename)


def find_operable_series(distribution):
    """Find all the series we can operate on in this distribution.

    We are allowed to modify DEVELOPMENT or FROZEN series, but should leave
    series with any other status alone.
    """
    return [
        series for series in distribution.series
        if series.status in (SeriesStatus.DEVELOPMENT, SeriesStatus.FROZEN)]


class GenerateExtraOverrides(LaunchpadScript):
    """Main class for scripts/ftpmaster-tools/generate-task-overrides.py."""

    def __init__(self, *args, **kwargs):
        super(GenerateExtraOverrides, self).__init__(*args, **kwargs)
        self.germinate_logger = None

    def add_my_options(self):
        """Add a 'distribution' context option."""
        self.parser.add_option(
            "-d", "--distribution", dest="distribution",
            help="Context distribution name.")

    @property
    def name(self):
        """See `LaunchpadScript`."""
        # Include distribution name.  Clearer to admins, but also
        # puts runs for different distributions under separate
        # locks so that they can run simultaneously.
        return "%s-%s" % (self._name, self.options.distribution)

    def processOptions(self):
        """Handle command-line options."""
        if self.options.distribution is None:
            raise OptionValueError("Specify a distribution.")

        self.distribution = getUtility(IDistributionSet).getByName(
            self.options.distribution)
        if self.distribution is None:
            raise OptionValueError(
                "Distribution '%s' not found." % self.options.distribution)

        self.series = find_operable_series(self.distribution)
        if not self.series:
            raise LaunchpadScriptFailure(
                "There is no DEVELOPMENT or FROZEN distroseries for %s." %
                self.options.distribution)

    def getConfig(self):
        """Set up a configuration object for this archive."""
        archive = self.distribution.main_archive
        if archive:
            return getPubConfig(archive)
        else:
            raise LaunchpadScriptFailure(
                "There is no PRIMARY archive for %s." %
                self.options.distribution)

    def setUpDirs(self):
        """Create output directories if they did not already exist."""
        germinateroot = self.config.germinateroot
        if not file_exists(germinateroot):
            self.logger.debug("Creating germinate root %s.", germinateroot)
            os.makedirs(germinateroot)
        miscroot = self.config.miscroot
        if not file_exists(miscroot):
            self.logger.debug("Creating misc root %s.", miscroot)
            os.makedirs(miscroot)

    def addLogHandler(self):
        """Send germinate's log output to a separate file."""
        if self.germinate_logger is not None:
            return

        self.germinate_logger = logging.getLogger("germinate")
        self.germinate_logger.setLevel(logging.INFO)
        self.log_file = os.path.join(
            self.config.germinateroot, "germinate.output")
        handler = logging.FileHandler(self.log_file, mode="w")
        handler.setFormatter(GerminateFormatter())
        self.germinate_logger.addHandler(handler)
        self.germinate_logger.propagate = False

    def setUp(self):
        """Process options, and set up internal state."""
        self.processOptions()
        self.config = self.getConfig()
        self.setUpDirs()
        self.addLogHandler()

    def getComponents(self, series):
        """Get the list of components to process for a given distroseries.

        Even if DistroSeries.component_names starts including partner,
        we don't want it; this applies to the primary archive only.
        """
        return [component
                for component in series.component_names
                if component != "partner"]

    def makeSeedStructures(self, series_name, flavours, seed_bases=None):
        structures = {}
        for flavour in flavours:
            try:
                structure = SeedStructure(
                    "%s.%s" % (flavour, series_name), seed_bases=seed_bases)
                if len(structure):
                    structures[flavour] = structure
                else:
                    self.logger.warning(
                        "Skipping empty seed structure for %s.%s",
                        flavour, series_name)
            except SeedError as e:
                self.logger.warning(
                    "Failed to fetch seeds for %s.%s: %s",
                    flavour, series_name, e)
        return structures

    def logGerminateProgress(self, *args):
        """Log a "progress" entry to the germinate log file.

        Germinate logs quite a bit of detailed information.  To make it
        easier to see the structure of its operation, GerminateFormatter
        allows tagging some log entries as "progress" entries, which are
        printed without a prefix.
        """
        self.germinate_logger.info(*args, extra={"progress": True})

    def composeOutputPath(self, flavour, series_name, arch, base):
        return os.path.join(
            self.config.germinateroot,
            "%s_%s_%s_%s" % (base, flavour, series_name, arch))

    def recordOutput(self, path, seed_outputs):
        if seed_outputs is not None:
            seed_outputs.add(os.path.basename(path))

    def writeGerminateOutput(self, germinator, structure, flavour,
                             series_name, arch, seed_outputs=None):
        """Write dependency-expanded output files.

        These files are a reduced subset of those written by the germinate
        command-line program.
        """
        path = partial(self.composeOutputPath, flavour, series_name, arch)

        # The structure file makes it possible to figure out how the other
        # output files relate to each other.
        structure.write(path("structure"))
        self.recordOutput(path("structure"), seed_outputs)

        # "all" and "all.sources" list the full set of binary and source
        # packages respectively for a given flavour/suite/architecture
        # combination.
        germinator.write_all_list(structure, path("all"))
        self.recordOutput(path("all"), seed_outputs)
        germinator.write_all_source_list(structure, path("all.sources"))
        self.recordOutput(path("all.sources"), seed_outputs)

        # Write the dependency-expanded output for each seed.  Several of
        # these are used by archive administration tools, and others are
        # useful for debugging, so it's best to just write them all.
        for seedname in structure.names:
            germinator.write_full_list(structure, path(seedname), seedname)
            self.recordOutput(path(seedname), seed_outputs)

    def parseTaskHeaders(self, seedtext):
        """Parse a seed for Task headers.

        seedtext is a file-like object.  Return a dictionary of Task headers,
        with keys canonicalised to lower-case.
        """
        task_headers = {}
        task_header_regex = re.compile(
            r"task-(.*?):(.*)", flags=re.IGNORECASE)
        for line in seedtext:
            match = task_header_regex.match(line)
            if match is not None:
                key, value = match.groups()
                task_headers[key.lower()] = value.strip()
        return task_headers

    def getTaskName(self, task_headers, flavour, seedname, primary_flavour):
        """Work out the name of the Task to be generated from this seed.

        If there is a Task-Name header, it wins; otherwise, seeds with a
        Task-Per-Derivative header are honoured for all flavours and put in
        an appropriate namespace, while other seeds are only honoured for
        the first flavour and have archive-global names.
        """
        if "name" in task_headers:
            return task_headers["name"]
        elif "per-derivative" in task_headers:
            return "%s-%s" % (flavour, seedname)
        elif primary_flavour:
            return seedname
        else:
            return None

    def getTaskSeeds(self, task_headers, seedname):
        """Return the list of seeds used to generate a task from this seed.

        The list of packages in this task comes from this seed plus any
        other seeds listed in a Task-Seeds header.
        """
        scan_seeds = set([seedname])
        if "seeds" in task_headers:
            scan_seeds.update(task_headers["seeds"].split())
        return sorted(scan_seeds)

    def writeOverrides(self, override_file, germinator, structure, arch,
                       seedname, key, value):
        packages = germinator.get_full(structure, seedname)
        for package in sorted(packages):
            print >>override_file, "%s/%s  %s  %s" % (
                package, arch, key, value)

    def germinateArchFlavour(self, override_file, germinator, series_name,
                             arch, flavour, structure, primary_flavour,
                             seed_outputs=None):
        """Germinate seeds on a single flavour for a single architecture."""
        # Expand dependencies.
        germinator.plant_seeds(structure)
        germinator.grow(structure)
        germinator.add_extras(structure)

        self.writeGerminateOutput(
            germinator, structure, flavour, series_name, arch,
            seed_outputs=seed_outputs)

        write_overrides = partial(
            self.writeOverrides, override_file, germinator, structure, arch)

        # Generate apt-ftparchive "extra overrides" for Task fields.
        seednames = [name for name in structure.names if name != "extra"]
        for seedname in seednames:
            with structure[seedname] as seedtext:
                task_headers = self.parseTaskHeaders(seedtext)
            if task_headers:
                task = self.getTaskName(
                    task_headers, flavour, seedname, primary_flavour)
                if task is not None:
                    scan_seeds = self.getTaskSeeds(task_headers, seedname)
                    for scan_seed in scan_seeds:
                        write_overrides(scan_seed, "Task", task)

        # Generate apt-ftparchive "extra overrides" for Build-Essential
        # fields.
        if "build-essential" in structure.names and primary_flavour:
            write_overrides("build-essential", "Build-Essential", "yes")

    def germinateArch(self, override_file, series_name, components, arch,
                      flavours, structures, seed_outputs=None):
        """Germinate seeds on all flavours for a single architecture."""
        germinator = Germinator(arch)

        # Read archive metadata.
        archive = TagFile(
            series_name, components, arch,
            "file://%s" % self.config.archiveroot, cleanup=True)
        germinator.parse_archive(archive)

        for flavour in flavours:
            self.logger.info(
                "Germinating for %s/%s/%s", flavour, series_name, arch)
            # Add this to the germinate log as well so that that can be
            # debugged more easily.  Log a separator line first.
            self.logGerminateProgress("")
            self.logGerminateProgress(
                "Germinating for %s/%s/%s", flavour, series_name, arch)

            self.germinateArchFlavour(
                override_file, germinator, series_name, arch, flavour,
                structures[flavour], flavour == flavours[0],
                seed_outputs=seed_outputs)

    def removeStaleOutputs(self, series_name, seed_outputs):
        """Remove stale outputs for a series.

        Any per-seed outputs not in seed_outputs are considered stale.
        """
        all_outputs = glob.glob(
            os.path.join(self.config.germinateroot, "*_*_%s_*" % series_name))
        for output in all_outputs:
            if os.path.basename(output) not in seed_outputs:
                os.remove(output)

    def generateExtraOverrides(self, series_name, components, architectures,
                               flavours, seed_bases=None):
        structures = self.makeSeedStructures(
            series_name, flavours, seed_bases=seed_bases)

        if structures:
            seed_outputs = set()
            override_path = os.path.join(
                self.config.miscroot,
                "more-extra.override.%s.main" % series_name)
            with AtomicFile(override_path) as override_file:
                for arch in architectures:
                    self.germinateArch(
                        override_file, series_name, components, arch,
                        flavours, structures, seed_outputs=seed_outputs)
            self.removeStaleOutputs(series_name, seed_outputs)

    def process(self, seed_bases=None):
        """Do the bulk of the work."""
        self.setUp()

        for series in self.series:
            series_name = series.name
            components = self.getComponents(series)
            architectures = sorted(
                arch.architecturetag for arch in series.enabled_architectures)

            # This takes a while.  Ensure that we do it without keeping a
            # database transaction open.
            self.txn.commit()
            with DatabaseBlockedPolicy():
                self.generateExtraOverrides(
                    series_name, components, architectures, self.args,
                    seed_bases=seed_bases)

    def main(self):
        """See `LaunchpadScript`."""
        # This code has no need to alter the database.
        with SlaveOnlyDatabasePolicy():
            self.process()
