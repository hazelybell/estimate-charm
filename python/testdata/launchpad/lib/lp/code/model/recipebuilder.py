# Copyright 2010-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Code to build recipes on the buildfarm."""

__metaclass__ = type
__all__ = [
    'RecipeBuildBehavior',
    ]

import traceback

from zope.component import adapts
from zope.interface import implements
from zope.security.proxy import removeSecurityProxy

from lp.buildmaster.interfaces.builder import CannotBuild
from lp.buildmaster.interfaces.buildfarmjobbehavior import (
    IBuildFarmJobBehavior,
    )
from lp.buildmaster.model.buildfarmjobbehavior import BuildFarmJobBehaviorBase
from lp.code.interfaces.sourcepackagerecipebuild import (
    ISourcePackageRecipeBuildJob,
    )
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.services.config import config
from lp.soyuz.adapters.archivedependencies import (
    get_primary_current_component,
    get_sources_list_for_building,
    )


class RecipeBuildBehavior(BuildFarmJobBehaviorBase):
    """How to build a recipe on the build farm."""

    adapts(ISourcePackageRecipeBuildJob)
    implements(IBuildFarmJobBehavior)

    # The list of build status values for which email notifications are
    # allowed to be sent. It is up to each callback as to whether it will
    # consider sending a notification but it won't do so if the status is not
    # in this list.
    ALLOWED_STATUS_NOTIFICATIONS = [
        'OK', 'PACKAGEFAIL', 'DEPFAIL', 'CHROOTFAIL']

    @property
    def build(self):
        return self.buildfarmjob.build

    @property
    def display_name(self):
        ret = "%s, %s, %s" % (
            self.build.distroseries.displayname, self.build.recipe.name,
            self.build.recipe.owner.name)
        if self._builder is not None:
            ret += " (on %s)" % self._builder.url
        return ret

    def logStartBuild(self, logger):
        """See `IBuildFarmJobBehavior`."""
        logger.info("startBuild(%s)", self.display_name)

    def _extraBuildArgs(self, distroarchseries, logger=None):
        """
        Return the extra arguments required by the slave for the given build.
        """
        # Build extra arguments.
        args = {}
        suite = self.build.distroseries.name
        if self.build.pocket != PackagePublishingPocket.RELEASE:
            suite += "-%s" % (self.build.pocket.name.lower())
        args['suite'] = suite
        args['arch_tag'] = distroarchseries.architecturetag
        requester = self.build.requester
        if requester.preferredemail is None:
            # Use a constant, known, name and email.
            args["author_name"] = 'Launchpad Package Builder'
            args["author_email"] = config.canonical.noreply_from_address
        else:
            args["author_name"] = requester.displayname
            # We have to remove the security proxy here b/c there's not a
            # logged in entity, and anonymous email lookups aren't allowed.
            # Don't keep the naked requester around though.
            args["author_email"] = removeSecurityProxy(
                requester).preferredemail.email
        args["recipe_text"] = str(self.build.recipe.builder_recipe)
        args['archive_purpose'] = self.build.archive.purpose.name
        args["ogrecomponent"] = get_primary_current_component(
            self.build.archive, self.build.distroseries,
            None)
        args['archives'] = get_sources_list_for_building(self.build,
            distroarchseries, None)
        args['archive_private'] = self.build.archive.private

        # config.builddmaster.bzr_builder_sources_list can contain a
        # sources.list entry for an archive that will contain a
        # bzr-builder package that needs to be used to build this
        # recipe.
        try:
            extra_archive = config.builddmaster.bzr_builder_sources_list
        except AttributeError:
            extra_archive = None

        if extra_archive is not None:
            try:
                sources_line = extra_archive % (
                    {'series': self.build.distroseries.name})
                args['archives'].append(sources_line)
            except StandardError:
                # Someone messed up the config, don't add it.
                if logger:
                    logger.error(
                        "Exception processing bzr_builder_sources_list:\n%s"
                        % traceback.format_exc())

        args['distroseries_name'] = self.build.distroseries.name
        return args

    def dispatchBuildToSlave(self, build_queue_id, logger):
        """See `IBuildFarmJobBehavior`."""

        distroseries = self.build.distroseries
        # Start the binary package build on the slave builder. First
        # we send the chroot.
        distroarchseries = distroseries.getDistroArchSeriesByProcessor(
            self._builder.processor)
        if distroarchseries is None:
            raise CannotBuild("Unable to find distroarchseries for %s in %s" %
                (self._builder.processor.name,
                self.build.distroseries.displayname))
        args = self._extraBuildArgs(distroarchseries, logger)
        chroot = distroarchseries.getChroot()
        if chroot is None:
            raise CannotBuild("Unable to find a chroot for %s" %
                              distroarchseries.displayname)
        logger.info(
            "Sending chroot file for recipe build to %s" % self._builder.name)
        d = self._slave.cacheFile(logger, chroot)

        def got_cache_file(ignored):
            # Generate a string which can be used to cross-check when
            # obtaining results so we know we are referring to the right
            # database object in subsequent runs.
            buildid = "%s-%s" % (self.build.id, build_queue_id)
            cookie = self.getBuildCookie()
            chroot_sha1 = chroot.content.sha1
            logger.info(
                "Initiating build %s on %s" % (buildid, self._builder.url))

            return self._slave.build(
                cookie, "sourcepackagerecipe", chroot_sha1, {}, args)

        def log_build_result((status, info)):
            message = """%s (%s):
            ***** RESULT *****
            %s
            %s: %s
            ******************
            """ % (
                self._builder.name,
                self._builder.url,
                args,
                status,
                info,
                )
            logger.info(message)

        return d.addCallback(got_cache_file).addCallback(log_build_result)

    def verifyBuildRequest(self, logger):
        """Assert some pre-build checks.

        The build request is checked:
         * Virtualized builds can't build on a non-virtual builder
         * Ensure that we have a chroot
         * Ensure that the build pocket allows builds for the current
           distroseries state.
        """
        build = self.build
        assert not (not self._builder.virtualized and build.is_virtualized), (
            "Attempt to build virtual item on a non-virtual builder.")

        # This should already have been checked earlier, but just check again
        # here in case of programmer errors.
        reason = build.archive.checkUploadToPocket(
            build.distroseries, build.pocket)
        assert reason is None, (
                "%s (%s) can not be built for pocket %s: invalid pocket due "
                "to the series status of %s." %
                    (build.title, build.id, build.pocket.name,
                     build.distroseries.name))

    def updateSlaveStatus(self, raw_slave_status, status):
        """Parse the recipe build specific status info into the status dict.

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
