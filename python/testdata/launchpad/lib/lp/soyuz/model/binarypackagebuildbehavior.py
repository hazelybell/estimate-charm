# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Builder behavior for binary package builds."""

__metaclass__ = type

__all__ = [
    'BinaryPackageBuildBehavior',
    ]

from twisted.internet import defer
from zope.interface import implements

from lp.buildmaster.interfaces.builder import CannotBuild
from lp.buildmaster.interfaces.buildfarmjobbehavior import (
    IBuildFarmJobBehavior,
    )
from lp.buildmaster.model.buildfarmjobbehavior import BuildFarmJobBehaviorBase
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.services.webapp import urlappend
from lp.soyuz.adapters.archivedependencies import (
    get_primary_current_component,
    get_sources_list_for_building,
    )
from lp.soyuz.enums import ArchivePurpose


class BinaryPackageBuildBehavior(BuildFarmJobBehaviorBase):
    """Define the behavior of binary package builds."""

    implements(IBuildFarmJobBehavior)

    def logStartBuild(self, logger):
        """See `IBuildFarmJobBehavior`."""
        spr = self.build.source_package_release
        logger.info("startBuild(%s, %s, %s, %s)", self._builder.url,
                    spr.name, spr.version, self.build.pocket.title)

    def getLogFileName(self):
        """See `IBuildPackageJob`."""
        sourcename = self.build.source_package_release.name
        version = self.build.source_package_release.version
        # we rely on previous storage of current buildstate
        # in the state handling methods.
        state = self.build.status.name

        dar = self.build.distro_arch_series
        distroname = dar.distroseries.distribution.name
        distroseriesname = dar.distroseries.name
        archname = dar.architecturetag

        # logfilename format:
        # buildlog_<DISTRIBUTION>_<DISTROSeries>_<ARCHITECTURE>_\
        # <SOURCENAME>_<SOURCEVERSION>_<BUILDSTATE>.txt
        # as:
        # buildlog_ubuntu_dapper_i386_foo_1.0-ubuntu0_FULLYBUILT.txt
        # it fix request from bug # 30617
        return ('buildlog_%s-%s-%s.%s_%s_%s.txt' % (
            distroname, distroseriesname, archname, sourcename, version,
            state))

    def _buildFilemapStructure(self, ignored, logger):
        # Build filemap structure with the files required in this build
        # and send them to the slave.
        # If the build is private we tell the slave to get the files from the
        # archive instead of the librarian because the slaves cannot
        # access the restricted librarian.
        dl = []
        private = self.build.archive.private
        if private:
            dl.extend(self._cachePrivateSourceOnSlave(logger))
        filemap = {}
        for source_file in self.build.source_package_release.files:
            lfa = source_file.libraryfile
            filemap[lfa.filename] = lfa.content.sha1
            if not private:
                dl.append(
                    self._slave.cacheFile(
                        logger, source_file.libraryfile))
        d = defer.gatherResults(dl)
        return d.addCallback(lambda ignored: filemap)

    def dispatchBuildToSlave(self, build_queue_id, logger):
        """See `IBuildFarmJobBehavior`."""

        # Start the binary package build on the slave builder. First
        # we send the chroot.
        chroot = self.build.distro_arch_series.getChroot()
        d = self._slave.cacheFile(logger, chroot)
        d.addCallback(self._buildFilemapStructure, logger)

        def got_filemap(filemap):
            # Generate a string which can be used to cross-check when
            # obtaining results so we know we are referring to the right
            # database object in subsequent runs.
            buildid = "%s-%s" % (self.build.id, build_queue_id)
            cookie = self.getBuildCookie()
            chroot_sha1 = chroot.content.sha1
            logger.debug(
                "Initiating build %s on %s" % (buildid, self._builder.url))

            args = self._extraBuildArgs(self.build)
            d = self._slave.build(
                cookie, "binarypackage", chroot_sha1, filemap, args)

            def got_build((status, info)):
                message = """%s (%s):
                ***** RESULT *****
                %s
                %s
                %s: %s
                ******************
                """ % (
                    self._builder.name,
                    self._builder.url,
                    filemap,
                    args,
                    status,
                    info,
                    )
                logger.info(message)
            return d.addCallback(got_build)

        return d.addCallback(got_filemap)

    def verifyBuildRequest(self, logger):
        """Assert some pre-build checks.

        The build request is checked:
         * Virtualized builds can't build on a non-virtual builder
         * Ensure that we have a chroot
         * Ensure that the build pocket allows builds for the current
           distroseries state.
        """
        build = self.build
        if build.is_virtualized and not self._builder.virtualized:
            raise AssertionError(
                "Attempt to build virtual item on a non-virtual builder.")

        # Assert that we are not silently building SECURITY jobs.
        # See findBuildCandidates. Once we start building SECURITY
        # correctly from EMBARGOED archive this assertion can be removed.
        # XXX Julian 2007-12-18 spec=security-in-soyuz: This is being
        # addressed in the work on the blueprint:
        # https://blueprints.launchpad.net/soyuz/+spec/security-in-soyuz
        target_pocket = build.pocket
        assert target_pocket != PackagePublishingPocket.SECURITY, (
            "Soyuz is not yet capable of building SECURITY uploads.")

        # Ensure build has the needed chroot
        chroot = build.distro_arch_series.getChroot()
        if chroot is None:
            raise CannotBuild(
                "Missing CHROOT for %s/%s/%s" % (
                    build.distro_series.distribution.name,
                    build.distro_series.name,
                    build.distro_arch_series.architecturetag))

        # This should already have been checked earlier, but just check again
        # here in case of programmer errors.
        reason = build.archive.checkUploadToPocket(
            build.distro_series,
            build.pocket)
        assert reason is None, (
                "%s (%s) can not be built for pocket %s: invalid pocket due "
                "to the series status of %s." %
                    (build.title, build.id, build.pocket.name,
                     build.distro_series.name))

    def updateSlaveStatus(self, raw_slave_status, status):
        """Parse the binary build specific status info into the status dict.

        This includes:
        * filemap => dictionary or None
        * dependencies => string or None
        """
        build_status_with_files = (
            'BuildStatus.OK',
            'BuildStatus.PACKAGEFAIL',
            'BuildStatus.DEPFAIL',
            )
        if (status['builder_status'] == 'BuilderStatus.WAITING' and
            status['build_status'] in build_status_with_files):
            status['filemap'] = raw_slave_status[3]
            status['dependencies'] = raw_slave_status[4]

    def _cachePrivateSourceOnSlave(self, logger):
        """Ask the slave to download source files for a private build.

        :param logger: A logger used for providing debug information.
        :return: A list of Deferreds, each of which represents a request
            to cache a file.
        """
        # The URL to the file in the archive consists of these parts:
        # archive_url / makePoolPath() / filename
        # Once this is constructed we add the http basic auth info.

        # Avoid circular imports.
        from lp.soyuz.model.publishing import makePoolPath

        archive = self.build.archive
        archive_url = archive.archive_url
        component_name = self.build.current_component.name
        dl = []
        for source_file in self.build.source_package_release.files:
            file_name = source_file.libraryfile.filename
            sha1 = source_file.libraryfile.content.sha1
            spn = self.build.source_package_release.sourcepackagename
            poolpath = makePoolPath(spn.name, component_name)
            url = urlappend(archive_url, poolpath)
            url = urlappend(url, file_name)
            logger.debug("Asking builder on %s to ensure it has file %s "
                         "(%s, %s)" % (
                            self._builder.url, file_name, url, sha1))
            dl.append(
                self._slave.sendFileToSlave(
                    sha1, url, "buildd", archive.buildd_secret))
        return dl

    def _extraBuildArgs(self, build):
        """
        Return the extra arguments required by the slave for the given build.
        """
        # Build extra arguments.
        args = {}
        # turn 'arch_indep' ON only if build is archindep or if
        # the specific architecture is the nominatedarchindep for
        # this distroseries (in case it requires any archindep source)
        args['arch_indep'] = build.distro_arch_series.isNominatedArchIndep

        suite = build.distro_arch_series.distroseries.name
        if build.pocket != PackagePublishingPocket.RELEASE:
            suite += "-%s" % (build.pocket.name.lower())
        args['suite'] = suite

        args['arch_tag'] = build.distro_arch_series.architecturetag

        archive_purpose = build.archive.purpose
        if (archive_purpose == ArchivePurpose.PPA and
            not build.archive.require_virtualized):
            # If we're building a non-virtual PPA, override the purpose
            # to PRIMARY and use the primary component override.
            # This ensures that the package mangling tools will run over
            # the built packages.
            args['archive_purpose'] = ArchivePurpose.PRIMARY.name
            args["ogrecomponent"] = (
                get_primary_current_component(build.archive,
                    build.distro_series, build.source_package_release.name))
        else:
            args['archive_purpose'] = archive_purpose.name
            args["ogrecomponent"] = (
                build.current_component.name)

        args['archives'] = get_sources_list_for_building(build,
            build.distro_arch_series, build.source_package_release.name)
        args['archive_private'] = build.archive.private
        args['build_debug_symbols'] = build.archive.build_debug_symbols

        return args
