# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from collections import defaultdict
import os
from StringIO import StringIO
import time

from storm.expr import (
    Desc,
    Join,
    )
from storm.store import EmptyResultSet

from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.model.sourcepackagename import SourcePackageName
from lp.services.command_spawner import (
    CommandSpawner,
    OutputLineHandler,
    ReturnCodeReceiver,
    )
from lp.services.database.interfaces import IStore
from lp.services.database.stormexpr import Concatenate
from lp.services.librarian.model import LibraryFileAlias
from lp.services.osutils import write_file
from lp.soyuz.enums import (
    BinaryPackageFormat,
    PackagePublishingStatus,
    )
from lp.soyuz.model.binarypackagebuild import BinaryPackageBuild
from lp.soyuz.model.binarypackagename import BinaryPackageName
from lp.soyuz.model.binarypackagerelease import BinaryPackageRelease
from lp.soyuz.model.component import Component
from lp.soyuz.model.distroarchseries import DistroArchSeries
from lp.soyuz.model.files import BinaryPackageFile
from lp.soyuz.model.publishing import (
    BinaryPackagePublishingHistory,
    SourcePackageFilePublishing,
    SourcePackagePublishingHistory,
    )
from lp.soyuz.model.section import Section
from lp.soyuz.model.sourcepackagerelease import SourcePackageRelease


def package_name(filename):
    """Extract a package name from a debian package filename."""
    return (os.path.basename(filename).split("_"))[0]


def safe_mkdir(path):
    """Ensures the path exists, creating it if it doesn't."""
    if not os.path.exists(path):
        os.makedirs(path, 0755)


DEFAULT_COMPONENT = "main"

CONFIG_HEADER = """
Dir
{
    ArchiveDir "%s";
    OverrideDir "%s";
    CacheDir "%s";
};

Default
{
    Packages::Compress ". gzip bzip2";
    Sources::Compress ". gzip bzip2";
    Contents::Compress "gzip";
    Translation::Compress ". gzip bzip2";
    DeLinkLimit 0;
    MaxContentsChange 12000;
    FileMode 0644;
}

TreeDefault
{
    Contents::Header "%s/contents.header";
};

"""

STANZA_TEMPLATE = """
tree "%(DISTS)s/%(DISTRORELEASEONDISK)s"
{
    FileList "%(LISTPATH)s/%(DISTRORELEASEBYFILE)s_$(SECTION)_binary-$(ARCH)";
    SourceFileList "%(LISTPATH)s/%(DISTRORELEASE)s_$(SECTION)_source";
    Sections "%(SECTIONS)s";
    Architectures "%(ARCHITECTURES)s";
    BinOverride "override.%(DISTRORELEASE)s.$(SECTION)";
    SrcOverride "override.%(DISTRORELEASE)s.$(SECTION).src";
    %(HIDEEXTRA)sExtraOverride "override.%(DISTRORELEASE)s.extra.$(SECTION)";
    Packages::Extensions "%(EXTENSIONS)s";
    BinCacheDB "packages-%(CACHEINSERT)s$(ARCH).db";
    Contents " ";
    LongDescription "%(LONGDESCRIPTION)s";
}

"""

EXT_TO_SUBCOMPONENT = {
    'udeb': 'debian-installer',
    'ddeb': 'debug',
    }

SUBCOMPONENT_TO_EXT = {
    'debian-installer': 'udeb',
    'debug': 'ddeb',
    }

CLEANUP_FREQUENCY = 60 * 60 * 24


class AptFTPArchiveFailure(Exception):
    """Failure while running apt-ftparchive."""


class FTPArchiveHandler:
    """Produces Sources and Packages files via apt-ftparchive.

    Generates file lists and configuration for apt-ftparchive, and kicks
    off generation of the Sources and Releases files.
    """

    def __init__(self, log, config, diskpool, distro, publisher):
        self.log = log
        self._config = config
        self._diskpool = diskpool
        self.distro = distro
        self.publisher = publisher

    def run(self, is_careful):
        """Do the entire generation and run process."""
        self.createEmptyPocketRequests(is_careful)
        self.log.debug("Preparing file lists and overrides.")
        self.generateOverrides(is_careful)
        self.log.debug("Generating overrides for the distro.")
        self.generateFileLists(is_careful)
        self.log.debug("Doing apt-ftparchive work.")
        apt_config_filename = self.generateConfig(is_careful)
        self.runApt(apt_config_filename)
        self.cleanCaches()

    def runAptWithArgs(self, apt_config_filename, *args):
        """Run apt-ftparchive in subprocesses.

        :raise: AptFTPArchiveFailure if any of the apt-ftparchive
            commands failed.
        """
        self.log.debug("Filepath: %s" % apt_config_filename)

        stdout_handler = OutputLineHandler(self.log.debug, "a-f: ")
        stderr_handler = OutputLineHandler(self.log.info, "a-f: ")
        base_command = ["apt-ftparchive"] + list(args) + [apt_config_filename]
        spawner = CommandSpawner()

        returncodes = {}
        completion_handler = ReturnCodeReceiver()
        returncodes['all'] = completion_handler
        spawner.start(
            base_command, stdout_handler=stdout_handler,
            stderr_handler=stderr_handler,
            completion_handler=completion_handler)

        spawner.complete()
        stdout_handler.finalize()
        stderr_handler.finalize()
        failures = sorted([
            (tag, receiver.returncode)
            for tag, receiver in returncodes.iteritems()
                if receiver.returncode != 0])
        if len(failures) > 0:
            by_arch = ["%s (returned %d)" % failure for failure in failures]
            raise AptFTPArchiveFailure(
                "Failure(s) from apt-ftparchive: %s" % ", ".join(by_arch))

    def runApt(self, apt_config_filename):
        self.runAptWithArgs(apt_config_filename, "--no-contents", "generate")

    #
    # Empty Pocket Requests
    #
    def createEmptyPocketRequests(self, fullpublish=False):
        """Write out empty file lists etc for pockets.

        We do this to have Packages or Sources for them even if we lack
        anything in them currently.
        """
        for distroseries in self.distro.series:
            components = [
                comp.name for comp in
                self.publisher.archive.getComponentsForSeries(distroseries)]
            for pocket in PackagePublishingPocket.items:
                if not fullpublish:
                    if not self.publisher.isDirty(distroseries, pocket):
                        continue
                else:
                    if not self.publisher.isAllowed(distroseries, pocket):
                        continue

                self.publisher.release_files_needed.add(
                    (distroseries.name, pocket))

                for comp in components:
                    self.createEmptyPocketRequest(distroseries, pocket, comp)

    def createEmptyPocketRequest(self, distroseries, pocket, comp):
        """Creates empty files for a release pocket and distroseries"""
        suite = distroseries.getSuite(pocket)

        # Create empty override lists.
        needed_paths = [
            (comp,),
            ("extra", comp),
            (comp, "src"),
            ]
        for sub_comp in self.publisher.subcomponents:
            needed_paths.append((comp, sub_comp))

        for path in needed_paths:
            write_file(os.path.join(
                self._config.overrideroot,
                ".".join(("override", suite) + path)), "")

        # Create empty file lists.
        def touch_list(*parts):
            write_file(os.path.join(
                self._config.overrideroot,
                "_".join((suite, ) + parts)), "")
        touch_list(comp, "source")

        arch_tags = [
            a.architecturetag for a in distroseries.enabled_architectures]
        for arch in arch_tags:
            # Touch more file lists for the archs.
            touch_list(comp, "binary-" + arch)
            for sub_comp in self.publisher.subcomponents:
                touch_list(comp, sub_comp, "binary-" + arch)

    #
    # Override Generation
    #
    def getSourcesForOverrides(self, distroseries, pocket):
        """Fetch override information about all published sources.

        The override information consists of tuples with 'sourcename',
        'component' and 'section' strings, in this order.

        :param distroseries: target `IDistroSeries`
        :param pocket: target `PackagePublishingPocket`

        :return: a `ResultSet` with the source override information tuples
        """
        origins = (
            SourcePackagePublishingHistory,
            Join(Component,
                 Component.id == SourcePackagePublishingHistory.componentID),
            Join(Section,
                 Section.id == SourcePackagePublishingHistory.sectionID),
            Join(SourcePackageRelease,
                 SourcePackageRelease.id ==
                     SourcePackagePublishingHistory.sourcepackagereleaseID),
            Join(SourcePackageName,
                 SourcePackageName.id ==
                     SourcePackageRelease.sourcepackagenameID),
            )

        return IStore(SourcePackageName).using(*origins).find(
            (SourcePackageName.name, Component.name, Section.name),
            SourcePackagePublishingHistory.archive == self.publisher.archive,
            SourcePackagePublishingHistory.distroseries == distroseries,
            SourcePackagePublishingHistory.pocket == pocket,
            SourcePackagePublishingHistory.status ==
                PackagePublishingStatus.PUBLISHED).order_by(
                    Desc(SourcePackagePublishingHistory.id))

    def getBinariesForOverrides(self, distroseries, pocket):
        """Fetch override information about all published binaries.

        The override information consists of tuples with 'binaryname',
        'component', 'section', 'architecture' and 'priority' strings,
        'binpackageformat' enum, 'phased_update_percentage' integer, in this
        order.

        :param distroseries: target `IDistroSeries`
        :param pocket: target `PackagePublishingPocket`

        :return: a `ResultSet` with the binary override information tuples
        """
        origins = (
            BinaryPackagePublishingHistory,
            Join(Component,
                 Component.id == BinaryPackagePublishingHistory.componentID),
            Join(Section,
                 Section.id == BinaryPackagePublishingHistory.sectionID),
            Join(BinaryPackageRelease,
                 BinaryPackageRelease.id ==
                     BinaryPackagePublishingHistory.binarypackagereleaseID),
            Join(BinaryPackageName,
                 BinaryPackageName.id ==
                     BinaryPackageRelease.binarypackagenameID),
            Join(DistroArchSeries,
                 DistroArchSeries.id ==
                     BinaryPackagePublishingHistory.distroarchseriesID),
            )

        architectures_ids = [arch.id for arch in distroseries.architectures]
        if len(architectures_ids) == 0:
            return EmptyResultSet()

        conditions = [
            BinaryPackagePublishingHistory.archive == self.publisher.archive,
            BinaryPackagePublishingHistory.distroarchseriesID.is_in(
                architectures_ids),
            BinaryPackagePublishingHistory.pocket == pocket,
            BinaryPackagePublishingHistory.status ==
                PackagePublishingStatus.PUBLISHED,
            ]
        if not self.publisher.archive.publish_debug_symbols:
            conditions.append(
                BinaryPackageRelease.binpackageformat
                    != BinaryPackageFormat.DDEB)

        result_set = IStore(BinaryPackageName).using(*origins).find(
            (BinaryPackageName.name, Component.name, Section.name,
             DistroArchSeries.architecturetag,
             BinaryPackagePublishingHistory.priority,
             BinaryPackageRelease.binpackageformat,
             BinaryPackagePublishingHistory.phased_update_percentage),
            *conditions)

        return result_set.order_by(Desc(BinaryPackagePublishingHistory.id))

    def generateOverrides(self, fullpublish=False):
        """Collect packages that need overrides, and generate them."""
        for distroseries in self.distro.series:
            for pocket in PackagePublishingPocket.items:
                if not fullpublish:
                    if not self.publisher.isDirty(distroseries, pocket):
                        continue
                else:
                    if not self.publisher.isAllowed(distroseries, pocket):
                        continue

                spphs = self.getSourcesForOverrides(distroseries, pocket)
                bpphs = self.getBinariesForOverrides(distroseries, pocket)
                self.publishOverrides(
                    distroseries.getSuite(pocket), spphs, bpphs)

    def publishOverrides(self, suite,
                         source_publications, binary_publications):
        """Output a set of override files for use in apt-ftparchive.

        Given the provided sourceoverrides and binaryoverrides, do the
        override file generation. The files will be written to
        overrideroot with filenames of the form:

            override.<distroseries>.<component>[.src]

        Attributes which must be present in sourceoverrides are:
            drname, spname, cname, sname
        Attributes which must be present in binaryoverrides are:
            drname, spname, cname, sname, archtag, priority,
            phased_update_percentage

        The binary priority will be mapped via the values in
        dbschema.py.
        """
        # This code is tested in soyuz-set-of-uploads, and in
        # test_ftparchive.
        from lp.archivepublisher.publishing import FORMAT_TO_SUBCOMPONENT

        # overrides[component][src/bin] = sets of tuples
        overrides = defaultdict(lambda: defaultdict(set))

        def updateOverride(packagename, component, section, archtag=None,
                           priority=None, binpackageformat=None,
                           phased_update_percentage=None):
            """Generates and packs tuples of data required for overriding.

            If archtag is provided, it's a binary tuple; otherwise, it's a
            source tuple.

            Note that these tuples must contain /strings/ (or integers in
            the case of phased_update_percentage), and not objects, because
            they will be printed out verbatim into the override files. This
            is why we use priority_displayed here, and why we get the string
            names of the publication's foreign keys to component, section,
            etc.
            """
            if component != DEFAULT_COMPONENT:
                section = "%s/%s" % (component, section)

            override = overrides[component]
            # We use sets in this structure to avoid generating
            # duplicated overrides.
            if archtag:
                priority = priority.title.lower()
                subcomp = FORMAT_TO_SUBCOMPONENT.get(binpackageformat)
                if subcomp is None:
                    package_arch = "%s/%s" % (packagename, archtag)
                    override['bin'].add((
                        package_arch, priority, section,
                        phased_update_percentage))
                elif subcomp in self.publisher.subcomponents:
                    # We pick up subcomponent packages here, although they
                    # do not need phased updates (and adding the
                    # phased_update_percentage would complicate
                    # generateOverrideForComponent).
                    override[subcomp].add((packagename, priority, section))
            else:
                override['src'].add((packagename, section))

        # Process huge iterations (more than 200k records) in batches.
        # See `PublishingTunableLoop`.
        self.log.debug("Calculating source overrides")

        for pub in source_publications:
            updateOverride(*pub)

        self.log.debug("Calculating binary overrides")

        for pub in binary_publications:
            updateOverride(*pub)

        # Now generate the files on disk...
        for component in overrides:
            self.log.debug("Generating overrides for %s/%s..." % (
                suite, component))
            self.generateOverrideForComponent(overrides, suite, component)

    def generateOverrideForComponent(self, overrides, suite, component):
        """Generates overrides for a specific component."""
        src_overrides = sorted(overrides[component]['src'])
        bin_overrides = sorted(overrides[component]['bin'])

        # Set up filepaths for the overrides we read
        extra_extra_overrides = os.path.join(self._config.miscroot,
            "more-extra.override.%s.main" % suite)
        if not os.path.exists(extra_extra_overrides):
            unpocketed_series = "-".join(suite.split('-')[:-1])
            extra_extra_overrides = os.path.join(self._config.miscroot,
                "more-extra.override.%s.main" % unpocketed_series)
        # And for the overrides we write out
        main_override = os.path.join(self._config.overrideroot,
                                     "override.%s.%s" % (suite, component))
        ef_override = os.path.join(self._config.overrideroot,
                                   "override.%s.extra.%s" % (suite, component))
        source_override = os.path.join(self._config.overrideroot,
                                       "override.%s.%s.src" %
                                       (suite, component))

        # Start to write the files out
        ef = open(ef_override, "w")
        f = open(main_override, "w")
        basic_override_seen = set()
        for (package_arch, priority, section,
             phased_update_percentage) in bin_overrides:
            package = package_arch.split("/")[0]
            if package not in basic_override_seen:
                basic_override_seen.add(package)
                f.write("\t".join((package, priority, section)))
                f.write("\n")

                # XXX: dsilvers 2006-08-23 bug=3900:
                # This needs to be made databaseish and be actually managed
                # within Launchpad.  (Or else we need to change Ubuntu as
                # appropriate and look for bugs addresses etc in Launchpad.)
                ef.write("\t".join([package, "Origin", "Ubuntu"]))
                ef.write("\n")
                ef.write("\t".join([
                    package, "Bugs",
                    "https://bugs.launchpad.net/ubuntu/+filebug"]))
                ef.write("\n")
            if phased_update_percentage is not None:
                ef.write("\t".join([
                    package_arch, "Phased-Update-Percentage",
                    str(phased_update_percentage)]))
                ef.write("\n")
        f.close()

        if os.path.exists(extra_extra_overrides):
            # XXX kiko 2006-08-24: This is untested.
            eef = open(extra_extra_overrides, "r")
            extras = {}
            for line in eef:
                line = line.strip()
                if not line:
                    continue
                (package, header, value) = line.split(None, 2)
                pkg_extras = extras.setdefault(package, {})
                header_values = pkg_extras.setdefault(header, [])
                header_values.append(value)
            eef.close()
            for pkg, headers in extras.items():
                for header, values in headers.items():
                    ef.write("\t".join([pkg, header, ", ".join(values)]))
                    ef.write("\n")
            # XXX: dsilvers 2006-08-23 bug=3900: As above,
            # this needs to be integrated into the database at some point.
        ef.close()

        def _outputSimpleOverrides(filename, overrides):
            sf = open(filename, "w")
            for tup in overrides:
                sf.write("\t".join(tup))
                sf.write("\n")
            sf.close()

        _outputSimpleOverrides(source_override, src_overrides)

        for subcomp in self.publisher.subcomponents:
            sub_overrides = sorted(overrides[component][subcomp])
            if sub_overrides:
                sub_path = os.path.join(
                    self._config.overrideroot,
                    "override.%s.%s.%s" % (suite, component, subcomp))
                _outputSimpleOverrides(sub_path, sub_overrides)

    #
    # File List Generation
    #
    def getSourceFiles(self, distroseries, pocket):
        """Fetch publishing information about all published source files.

        The publishing information consists of tuples with 'sourcename',
        'filename' and 'component' strings, in this order.

        :param distroseries: target `IDistroSeries`
        :param pocket: target `PackagePublishingPocket`

        :return: a `ResultSet` with the source files information tuples.
        """
        store = IStore(SourcePackagePublishingHistory)
        result_set = store.using(SourcePackageFilePublishing).find(
            (SourcePackageFilePublishing.sourcepackagename,
             SourcePackageFilePublishing.libraryfilealiasfilename,
             SourcePackageFilePublishing.componentname),
            SourcePackageFilePublishing.distribution == self.distro,
            SourcePackageFilePublishing.archive == self.publisher.archive,
            SourcePackageFilePublishing.distroseriesname == distroseries.name,
            SourcePackageFilePublishing.pocket == pocket,
            SourcePackageFilePublishing.publishingstatus ==
                PackagePublishingStatus.PUBLISHED)

        return result_set.order_by(Desc(SourcePackageFilePublishing.id))

    def getBinaryFiles(self, distroseries, pocket):
        """Fetch publishing information about all published binary files.

        The publishing information consists of tuples with 'sourcename',
        'filename', 'component' and 'architecture' strings, in this order.

        :param distroseries: target `IDistroSeries`
        :param pocket: target `PackagePublishingPocket`

        :return: a `ResultSet` with the binary files information tuples.
        """
        columns = (
            SourcePackageName.name,
            LibraryFileAlias.filename,
            Component.name,
            Concatenate(u"binary-", DistroArchSeries.architecturetag),
            )
        join_conditions = [
            BinaryPackageRelease.id ==
                BinaryPackagePublishingHistory.binarypackagereleaseID,
            BinaryPackageFile.binarypackagereleaseID ==
                BinaryPackagePublishingHistory.binarypackagereleaseID,
            BinaryPackageBuild.id == BinaryPackageRelease.buildID,
            SourcePackageRelease.id ==
                BinaryPackageBuild.source_package_release_id,
            SourcePackageName.id == SourcePackageRelease.sourcepackagenameID,
            LibraryFileAlias.id == BinaryPackageFile.libraryfileID,
            DistroArchSeries.id ==
                BinaryPackagePublishingHistory.distroarchseriesID,
            Component.id == BinaryPackagePublishingHistory.componentID,
            ]
        select_conditions = [
            BinaryPackagePublishingHistory.dateremoved == None,
            DistroArchSeries.distroseriesID == distroseries.id,
            BinaryPackagePublishingHistory.archive == self.publisher.archive,
            BinaryPackagePublishingHistory.pocket == pocket,
            BinaryPackagePublishingHistory.status ==
                PackagePublishingStatus.PUBLISHED,
            ]

        if not self.publisher.archive.publish_debug_symbols:
            select_conditions.append(
                BinaryPackageRelease.binpackageformat
                    != BinaryPackageFormat.DDEB)

        result_set = IStore(SourcePackageRelease).find(
            columns, *(join_conditions + select_conditions))
        return result_set.order_by(
            BinaryPackagePublishingHistory.id, BinaryPackageFile.id)

    def generateFileLists(self, fullpublish=False):
        """Collect currently published FilePublishings and write filelists."""
        for distroseries in self.distro.series:
            for pocket in PackagePublishingPocket.items:
                if not fullpublish:
                    if not self.publisher.isDirty(distroseries, pocket):
                        continue
                else:
                    if not self.publisher.isAllowed(distroseries, pocket):
                        continue
                spps = self.getSourceFiles(distroseries, pocket)
                pps = self.getBinaryFiles(distroseries, pocket)
                self.publishFileLists(distroseries.getSuite(pocket), spps, pps)

    def publishFileLists(self, suite, sourcefiles, binaryfiles):
        """Collate the set of source files and binary files provided and
        write out all the file list files for them.

        listroot/distroseries_component_source
        listroot/distroseries_component_binary-archname
        """
        filelist = defaultdict(lambda: defaultdict(list))

        def updateFileList(sourcepackagename, filename, component,
                           architecturetag=None):
            ondiskname = self._diskpool.pathFor(
                            component, sourcepackagename, filename)
            if architecturetag is None:
                architecturetag = "source"
            filelist[component][architecturetag].append(ondiskname)

        # Process huge iterations (more than 200K records) in batches.
        # See `PublishingTunableLoop`.
        self.log.debug("Calculating source filelist.")

        for file_details in sourcefiles:
            updateFileList(*file_details)

        self.log.debug("Calculating binary filelist.")

        for file_details in binaryfiles:
            updateFileList(*file_details)

        self.log.debug("Writing file lists for %s" % suite)
        series, pocket = self.distro.getDistroSeriesAndPocket(suite)
        for component, architectures in filelist.iteritems():
            for architecture, file_names in architectures.iteritems():
                # XXX wgrant 2010-10-06: There must be a better place to do
                # this.
                if architecture == "source":
                    enabled = True
                else:
                    # The "[7:]" strips the "binary-" prefix off the
                    # architecture names we get here.
                    das = series.getDistroArchSeries(architecture[7:])
                    enabled = das.enabled
                if enabled:
                    self.writeFileList(
                        architecture, file_names, suite, component)

    def writeFileList(self, arch, file_names, dr_pocketed, component):
        """Output file lists for a series and architecture.

        This includes the subcomponent file lists.
        """
        files = defaultdict(list)
        for name in file_names:
            files[EXT_TO_SUBCOMPONENT.get(name.rsplit('.', 1)[1])].append(name)

        lists = (
            [(None, 'regular', '%s_%s_%s' % (dr_pocketed, component, arch))]
            + [(subcomp, subcomp,
                '%s_%s_%s_%s' % (dr_pocketed, component, subcomp, arch))
               for subcomp in self.publisher.subcomponents])
        for subcomp, desc, filename in lists:
            self.log.debug(
                "Writing %s file list for %s/%s/%s" % (
                    desc, dr_pocketed, component, arch))
            path = os.path.join(self._config.overrideroot, filename)
            with open(path, "w") as f:
                files[subcomp].sort(key=package_name)
                f.write("\n".join(files[subcomp]))
                f.write("\n")

    #
    # Config Generation
    #
    def generateConfig(self, fullpublish=False):
        """Generate an APT FTPArchive configuration from the provided
        config object and the paths we either know or have given to us.

        If fullpublish is true, we generate config for everything.

        Otherwise, we aim to limit our config to certain distroseries
        and pockets. By default, we will exclude release pockets for
        released series, and in addition we exclude any pocket not
        explicitly marked as dirty. dirty_pockets must be a nested
        dictionary of booleans, keyed by distroseries.name then pocket.
        """
        apt_config = StringIO()
        apt_config.write(CONFIG_HEADER % (self._config.archiveroot,
                                          self._config.overrideroot,
                                          self._config.cacheroot,
                                          self._config.miscroot))

        # confixtext now contains a basic header. Add a dists entry for
        # each of the distroseries we've touched
        for distroseries in self.distro.series:
            for pocket in PackagePublishingPocket.items:

                if not fullpublish:
                    if not self.publisher.isDirty(distroseries, pocket):
                        self.log.debug("Skipping a-f stanza for %s/%s" %
                                           (distroseries.name, pocket.name))
                        continue
                    self.publisher.checkDirtySuiteBeforePublishing(
                        distroseries, pocket)
                else:
                    if not self.publisher.isAllowed(distroseries, pocket):
                        continue

                self.generateConfigForPocket(apt_config, distroseries, pocket)

        apt_config_filename = os.path.join(self._config.miscroot, "apt.conf")
        with open(apt_config_filename, "w") as fp:
            fp.write(apt_config.getvalue())
        apt_config.close()
        return apt_config_filename

    def generateConfigForPocket(self, apt_config, distroseries, pocket):
        """Generates the config stanza for an individual pocket."""
        suite = distroseries.getSuite(pocket)

        archs = [
            a.architecturetag for a in distroseries.enabled_architectures]
        comps = [
            comp.name for comp in
            self.publisher.archive.getComponentsForSeries(distroseries)]

        self.writeAptConfig(
            apt_config, suite, comps, archs,
            distroseries.include_long_descriptions)

        # XXX: 2006-08-24 kiko: Why do we do this directory creation here?
        for comp in comps:
            component_path = os.path.join(
                self._config.distsroot, suite, comp)
            safe_mkdir(os.path.join(component_path, "source"))
            if not distroseries.include_long_descriptions:
                safe_mkdir(os.path.join(component_path, "i18n"))
            for arch in archs:
                safe_mkdir(os.path.join(component_path, "binary-" + arch))
                for subcomp in self.publisher.subcomponents:
                    safe_mkdir(os.path.join(
                        component_path, subcomp, "binary-" + arch))

    def writeAptConfig(self, apt_config, suite, comps, archs,
                       include_long_descriptions):
        self.log.debug("Generating apt config for %s" % suite)
        apt_config.write(STANZA_TEMPLATE % {
                         "LISTPATH": self._config.overrideroot,
                         "DISTRORELEASE": suite,
                         "DISTRORELEASEBYFILE": suite,
                         "DISTRORELEASEONDISK": suite,
                         "ARCHITECTURES": " ".join(archs + ["source"]),
                         "SECTIONS": " ".join(comps),
                         "EXTENSIONS": ".deb",
                         "CACHEINSERT": "",
                         "DISTS": os.path.basename(self._config.distsroot),
                         "HIDEEXTRA": "",
                         "LONGDESCRIPTION":
                             "true" if include_long_descriptions else "false",
                         })

        if archs:
            for component in comps:
                for subcomp in self.publisher.subcomponents:
                    apt_config.write(STANZA_TEMPLATE % {
                        "LISTPATH": self._config.overrideroot,
                        "DISTRORELEASEONDISK": "%s/%s" % (suite, component),
                        "DISTRORELEASEBYFILE": "%s_%s" % (suite, component),
                        "DISTRORELEASE": "%s.%s" % (suite, component),
                        "ARCHITECTURES": " ".join(archs),
                        "SECTIONS": subcomp,
                        "EXTENSIONS": '.%s' % SUBCOMPONENT_TO_EXT[subcomp],
                        "CACHEINSERT": "%s-" % subcomp,
                        "DISTS": os.path.basename(self._config.distsroot),
                        "HIDEEXTRA": "// ",
                        "LONGDESCRIPTION": "true",
                        })

    def cleanCaches(self):
        """Clean apt-ftparchive caches.

        This takes a few minutes and doesn't need to be done on every run,
        but it should be done every so often so that the cache files don't
        get too large and slow down normal runs of apt-ftparchive.
        """
        apt_config_filename = os.path.join(
            self._config.miscroot, "apt-cleanup.conf")
        try:
            last_cleanup = os.stat(apt_config_filename).st_mtime
            if last_cleanup > time.time() - CLEANUP_FREQUENCY:
                return
        except OSError:
            pass

        apt_config = StringIO()
        apt_config.write(CONFIG_HEADER % (self._config.archiveroot,
                                          self._config.overrideroot,
                                          self._config.cacheroot,
                                          self._config.miscroot))

        # "apt-ftparchive clean" doesn't care what suite it's given, but it
        # needs to know the union of all architectures and components for
        # each suite we might publish.
        archs = set()
        comps = set()
        for distroseries in self.publisher.consider_series:
            for a in distroseries.enabled_architectures:
                archs.add(a.architecturetag)
            for comp in self.publisher.archive.getComponentsForSeries(
                distroseries):
                comps.add(comp.name)
        self.writeAptConfig(
            apt_config, "nonexistent-suite", sorted(comps), sorted(archs),
            True)

        with open(apt_config_filename, "w") as fp:
            fp.write(apt_config.getvalue())
        apt_config.close()
        self.runAptWithArgs(apt_config_filename, "clean")
