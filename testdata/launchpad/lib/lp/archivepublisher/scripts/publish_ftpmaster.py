# Copyright 2011-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Master distro publishing script."""

__metaclass__ = type
__all__ = [
    'PublishFTPMaster',
    ]

from datetime import datetime
import os

from pytz import utc
from zope.component import getUtility

from lp.archivepublisher.config import getPubConfig
from lp.archivepublisher.interfaces.publisherconfig import IPublisherConfigSet
from lp.archivepublisher.publishing import GLOBAL_PUBLISHER_LOCK
from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.interfaces.pocket import (
    PackagePublishingPocket,
    pocketsuffix,
    )
from lp.registry.interfaces.series import SeriesStatus
from lp.services.config import config
from lp.services.database.bulk import load_related
from lp.services.scripts.base import (
    LaunchpadCronScript,
    LaunchpadScriptFailure,
    )
from lp.services.utils import file_exists
from lp.soyuz.enums import (
    ArchivePurpose,
    PackagePublishingStatus,
    )
from lp.soyuz.model.distroarchseries import DistroArchSeries
from lp.soyuz.scripts.custom_uploads_copier import CustomUploadsCopier
from lp.soyuz.scripts.processaccepted import ProcessAccepted
from lp.soyuz.scripts.publishdistro import PublishDistro


def get_publishable_archives(distribution):
    """Get all archives for `distribution` that should be published."""
    # XXX JeroenVermeulen 2011-03-31 bug=746229: to start publishing
    # debug archives, simply stop filtering them out here.  It may be
    # enough to return list(distribution.all_distro_archives) directly.
    ARCHIVES_TO_PUBLISH = [
        ArchivePurpose.PRIMARY,
        ArchivePurpose.PARTNER,
        ]
    return [
        archive
        for archive in distribution.all_distro_archives
            if archive.purpose in ARCHIVES_TO_PUBLISH]


def compose_shell_boolean(boolean_value):
    """Represent a boolean value as "yes" or "no"."""
    boolean_text = {
        True: "yes",
        False: "no",
    }
    return boolean_text[boolean_value]


def shell_quote(literal):
    """Escape `literal` for use in a double-quoted shell string.

    This is a pretty naive substitution: it doesn't deal well with
    non-ASCII characters or special characters.
    """
    # Characters that need backslash-escaping.  Do the backslash itself
    # first; any escapes we introduced *before* the backslash would have
    # their own backslashes escaped afterwards when we got to the
    # backslash itself.
    special_characters = '\\"$`\n'
    for escapee in special_characters:
        literal = literal.replace(escapee, '\\' + escapee)
    return '"%s"' % literal


def compose_env_string(*env_dicts):
    """Turn dict(s) into a series of shell parameter assignments.

    Values in later dicts override any values with the same respective
    keys in earlier dicts.
    """
    env = {}
    for env_dict in env_dicts:
        env.update(env_dict)
    return ' '.join(['='.join(pair) for pair in env.iteritems()])


def get_backup_dists(archive_config):
    """Return the path of an archive's backup dists directory."""
    return os.path.join(archive_config.archiveroot + "-distscopy", "dists")


def get_dists(archive_config):
    """Return the path of an archive's dists directory.

    :param archive_config: Configuration for the archive in question.
    """
    return archive_config.distsroot


def get_working_dists(archive_config):
    """Return the working path for an archive's dists directory.

    In order for publish-distro to operate on an archive, its dists
    directory must be in the archive root.  So we move the backup
    dists directory to a working location below the archive root just
    for publish-distro.  This method composes the temporary path.
    """
    return get_dists(archive_config) + ".in-progress"


def extend_PATH():
    """Produce env dict for extending $PATH.

    Adds the Launchpad source tree's cronscripts/publishing to the
    existing $PATH.

    :return: a dict suitable for passing to compose_env_string.
    """
    scripts_dir = os.path.join(config.root, "cronscripts", "publishing")
    return {"PATH": '"$PATH":%s' % shell_quote(scripts_dir)}


def find_run_parts_dir(distro, parts):
    """Find the requested run-parts directory, if it exists."""
    run_parts_location = config.archivepublisher.run_parts_location
    if not run_parts_location:
        return

    parts_dir = os.path.join(run_parts_location, distro.name, parts)
    if file_exists(parts_dir):
        return parts_dir
    else:
        return None


def map_distro_pubconfigs(distro):
    """Return dict mapping archive purpose for distro's pub configs.

    :param distro: `Distribution` to get publisher configs for.
    :return: Dict mapping archive purposes to publisher configs, insofar as
        they have publisher configs.
    """
    candidates = [
        (archive.purpose, getPubConfig(archive))
        for archive in get_publishable_archives(distro)]
    return dict(
        (purpose, config)
        for purpose, config in candidates if config is not None)


class PublishFTPMaster(LaunchpadCronScript):
    """Publish a distro (update).

    The publishable files are kept in the filesystem.  Most of the work
    is done in a working "dists" directory, which then replaces the
    current "dists" in the archive root.

    For performance reasons, the old "dists" is not discarded.  It is
    kept as the dists-copy version for the next run.  Its contents
    don't matter in detail; an rsync updates it based on the currently
    published dists directory before we start working with it.

    At the end of one pass of the script, the "dists" directory in the
    archive root and its backup copy in the dists-copy root will have
    traded places.

    However the script normally does 2 passes: once just for security
    updates, to expedite publication of critical fixes, and once for the
    whole distribution.  At the end of this, the directories will be
    back in their original places (though with updated contents).
    """

    lockfilename = GLOBAL_PUBLISHER_LOCK

    def add_my_options(self):
        """See `LaunchpadScript`."""
        self.parser.add_option(
            '-a', '--all-derived', dest='all_derived', action='store_true',
            default=False, help="Process all derived distributions.")
        self.parser.add_option(
            '-d', '--distribution', dest='distribution', default=None,
            help="Distribution to publish.")
        self.parser.add_option(
            '-p', '--post-rsync', dest='post_rsync', action='store_true',
            default=False,
            help="When done, rsync backup dists to speed up the next run.")
        self.parser.add_option(
            '-s', '--security-only', dest='security_only',
            action='store_true', default=False, help="Security upload only.")

    def processOptions(self):
        """Handle command-line options.

        Sets `self.distributions` to the `Distribution`s to publish.
        """
        if self.options.distribution is None and not self.options.all_derived:
            raise LaunchpadScriptFailure(
                "Specify a distribution, or --all-derived.")
        if self.options.distribution is not None and self.options.all_derived:
            raise LaunchpadScriptFailure(
                "Can't combine the --distribution and --all-derived options.")

        if self.options.all_derived:
            distro_set = getUtility(IDistributionSet)
            self.distributions = distro_set.getDerivedDistributions()
        else:
            distro = getUtility(IDistributionSet).getByName(
                self.options.distribution)
            if distro is None:
                raise LaunchpadScriptFailure(
                    "Distribution %s not found." % self.options.distribution)
            self.distributions = [distro]

    def executeShell(self, command_line, failure=None):
        """Run `command_line` through a shell.

        This won't just load an external program and run it; the command
        line goes through the full shell treatment including variable
        substitutions, output redirections, and so on.

        :param command_line: Shell command.
        :param failure: Raise `failure` as an exception if the shell
            command returns a nonzero value.  If omitted, nonzero return
            values are ignored.
        """
        self.logger.debug("Executing: %s" % command_line)
        retval = os.system(command_line)
        if retval != 0:
            self.logger.debug("Command returned %d.", retval)
            if failure is not None:
                self.logger.debug("Command failed: %s", failure)
                raise failure

    def getConfigs(self):
        """Set up configuration objects for archives to be published.

        The configs dict maps each distribution to another dict that maps the
        archive purposes that are relevant for publishing to the respective
        archives' configurations.

        So: getConfigs[distro][purpose] gives you a config.
        """
        return dict(
            (distro, map_distro_pubconfigs(distro))
            for distro in self.distributions)

    def locateIndexesMarker(self, distribution, suite):
        """Give path for marker file whose presence marks index creation.

        The file will be created once the archive indexes for `suite`
        have been created.  This is how future runs will know that this
        work is done.
        """
        config = self.configs[distribution][ArchivePurpose.PRIMARY]
        return os.path.join(
            config.archiveroot, ".created-indexes-for-%s" % suite)

    def listSuitesNeedingIndexes(self, distroseries):
        """Find suites in `distroseries` that need indexes created.

        Checks for the marker left by `markIndexCreationComplete`.
        """
        if distroseries.status != SeriesStatus.FROZEN:
            # DistroSeries are created in Frozen state.  If the series
            # is in any other state yet has not been marked as having
            # its indexes created, that's because it predates automatic
            # index creation.
            return []
        distro = distroseries.distribution
        publisher_config_set = getUtility(IPublisherConfigSet)
        if publisher_config_set.getByDistribution(distro) is None:
            # We won't be able to do a thing without a publisher config,
            # but that's alright: we have those for all distributions
            # that we want to publish.
            return []

        # May need indexes for this series.
        suites = [
            distroseries.getSuite(pocket)
            for pocket in pocketsuffix.iterkeys()]
        return [
            suite for suite in suites
                if not file_exists(self.locateIndexesMarker(distro, suite))]

    def markIndexCreationComplete(self, distribution, suite):
        """Note that archive indexes for `suite` have been created.

        This tells `listSuitesNeedingIndexes` that no, this suite no
        longer needs archive indexes to be set up.
        """
        marker_name = self.locateIndexesMarker(distribution, suite)
        with file(marker_name, "w") as marker:
            marker.write(
                "Indexes for %s were created on %s.\n"
                % (suite, datetime.now(utc)))

    def createIndexes(self, distribution, suites):
        """Create archive indexes for `suites` of `distroseries`."""
        self.logger.info(
            "Creating archive indexes for %s.", ', '.join(suites))
        self.runPublishDistro(distribution, args=['-A'], suites=suites)
        for suite in suites:
            self.markIndexCreationComplete(distribution, suite)

    def processAccepted(self, distribution):
        """Run the process-accepted script."""
        self.logger.debug(
            "Processing the accepted queue into the publishing records...")
        script = ProcessAccepted(
            test_args=[distribution.name], logger=self.logger)
        script.txn = self.txn
        script.main()

    def getDirtySuites(self, distribution):
        """Return set of suites that have packages pending publication."""
        self.logger.debug("Querying which suites are pending publication...")

        archive = distribution.main_archive
        pending = PackagePublishingStatus.PENDING
        pending_sources = list(archive.getPublishedSources(status=pending))
        pending_binaries = list(archive.getAllPublishedBinaries(
            status=pending))
        load_related(
            DistroArchSeries, pending_binaries, ['distroarchseriesID'])
        return set(
            pub.distroseries.name + pocketsuffix[pub.pocket]
            for pub in pending_sources + pending_binaries)

    def getDirtySecuritySuites(self, distribution):
        """List security suites with pending publications."""
        suites = self.getDirtySuites(distribution)
        return [suite for suite in suites if suite.endswith('-security')]

    def rsyncBackupDists(self, distribution):
        """Populate the backup dists with a copy of distsroot.

        Uses "rsync -aH --delete" so that any obsolete files that may
        still be in the backup dists are cleaned out (bug 58835).

        :param archive_purpose: The (purpose of the) archive to copy.
        """
        for purpose, archive_config in self.configs[distribution].iteritems():
            dists = get_dists(archive_config)
            backup_dists = get_backup_dists(archive_config)
            self.executeShell(
                "rsync -aH --delete '%s/' '%s'" % (dists, backup_dists),
                failure=LaunchpadScriptFailure(
                    "Failed to rsync new dists for %s." % purpose.title))

    def recoverArchiveWorkingDir(self, archive_config):
        """Recover working dists dir for `archive_config`.

        If there is a dists directory for `archive_config` in the working
        location, kick it back to the backup location.
        """
        working_location = get_working_dists(archive_config)
        if file_exists(working_location):
            self.logger.info(
                "Recovering working directory %s from failed run.",
                working_location)
            os.rename(working_location, get_backup_dists(archive_config))

    def recoverWorkingDists(self):
        """Look for and recover any dists left in transient working state.

        An archive's dists directory is temporarily moved into the
        archive root for running publish-distro.  If a previous script
        run died while in this state, restore the directory to its
        permanent location.
        """
        for distro_configs in self.configs.itervalues():
            for archive_config in distro_configs.itervalues():
                self.recoverArchiveWorkingDir(archive_config)

    def setUpDirs(self):
        """Create archive roots and such if they did not yet exist."""
        for distro_configs in self.configs.itervalues():
            for archive_purpose, archive_config in distro_configs.iteritems():
                archiveroot = archive_config.archiveroot
                if not file_exists(archiveroot):
                    self.logger.debug(
                        "Creating archive root %s.", archiveroot)
                    os.makedirs(archiveroot)
                dists = get_dists(archive_config)
                if not file_exists(dists):
                    self.logger.debug("Creating dists root %s.", dists)
                    os.makedirs(dists)
                distscopy = get_backup_dists(archive_config)
                if not file_exists(distscopy):
                    self.logger.debug(
                        "Creating backup dists directory %s", distscopy)
                    os.makedirs(distscopy)

    def runPublishDistro(self, distribution, args=[], suites=None):
        """Execute `publish-distro`."""
        if suites is None:
            suites = []
        arguments = (
            ['-d', distribution.name] +
            args +
            sum([['-s', suite] for suite in suites], []))

        publish_distro = PublishDistro(
            test_args=arguments, logger=self.logger)
        publish_distro.logger = self.logger
        publish_distro.txn = self.txn
        publish_distro.main()

    def publishDistroArchive(self, distribution, archive,
                             security_suites=None):
        """Publish the results for an archive.

        :param archive: Archive to publish.
        :param security_suites: An optional list of suites to restrict
            the publishing to.
        """
        purpose = archive.purpose
        archive_config = self.configs[distribution][purpose]
        self.logger.debug(
            "Publishing the %s %s...", distribution.name, purpose.title)

        # For reasons unknown, publishdistro only seems to work with a
        # directory that's inside the archive root.  So we move it there
        # for the duration.
        temporary_dists = get_working_dists(archive_config)

        arguments = ['-R', temporary_dists]
        if archive.purpose == ArchivePurpose.PARTNER:
            arguments.append('--partner')

        os.rename(get_backup_dists(archive_config), temporary_dists)
        try:
            self.runPublishDistro(
                distribution, args=arguments, suites=security_suites)
        finally:
            os.rename(temporary_dists, get_backup_dists(archive_config))

        self.runPublishDistroParts(distribution, archive)

    def runPublishDistroParts(self, distribution, archive):
        """Execute the publish-distro hooks."""
        archive_config = self.configs[distribution][archive.purpose]
        env = {
            'ARCHIVEROOT': shell_quote(archive_config.archiveroot),
            'DISTSROOT': shell_quote(get_backup_dists(archive_config)),
            }
        if archive_config.overrideroot is not None:
            env["OVERRIDEROOT"] = shell_quote(archive_config.overrideroot)
        self.runParts(distribution, 'publish-distro.d', env)

    def installDists(self, distribution):
        """Put the new dists into place, as near-atomically as possible.

        For each archive, this switches the dists directory and the
        backup dists directory around.
        """
        self.logger.debug("Moving the new dists into place...")
        for archive_config in self.configs[distribution].itervalues():
            # Use the dists "working location" as a temporary place to
            # move the current dists out of the way for the switch.  If
            # we die in this state, the next run will know to move the
            # temporary directory to the backup location.
            dists = get_dists(archive_config)
            temp_dists = get_working_dists(archive_config)
            backup_dists = get_backup_dists(archive_config)

            os.rename(dists, temp_dists)
            os.rename(backup_dists, dists)
            os.rename(temp_dists, backup_dists)

    def generateListings(self, distribution):
        """Create ls-lR.gz listings."""
        self.logger.debug("Creating ls-lR.gz...")
        lslr = "ls-lR.gz"
        lslr_new = "." + lslr + ".new"
        for purpose, archive_config in self.configs[distribution].iteritems():
            lslr_file = os.path.join(archive_config.archiveroot, lslr)
            new_lslr_file = os.path.join(archive_config.archiveroot, lslr_new)
            if file_exists(new_lslr_file):
                os.remove(new_lslr_file)
            self.executeShell(
                "cd -- '%s' ; TZ=UTC ls -lR | gzip -9n >'%s'"
                % (archive_config.archiveroot, lslr_new),
                failure=LaunchpadScriptFailure(
                    "Failed to create %s for %s." % (lslr, purpose.title)))
            os.rename(new_lslr_file, lslr_file)

    def clearEmptyDirs(self, distribution):
        """Clear out any redundant empty directories."""
        for archive_config in self.configs[distribution].itervalues():
            self.executeShell(
                "find '%s' -type d -empty | xargs -r rmdir"
                % archive_config.archiveroot)

    def runParts(self, distribution, parts, env):
        """Execute run-parts.

        :param distribution: `Distribution` to execute run-parts scripts for.
        :param parts: The run-parts directory to execute:
            "publish-distro.d" or "finalize.d".
        :param env: A dict of environment variables to pass to the
            scripts in the run-parts directory.
        """
        parts_dir = find_run_parts_dir(distribution, parts)
        if parts_dir is None:
            self.logger.debug("Skipping run-parts %s: not configured.", parts)
            return
        env_string = compose_env_string(env, extend_PATH())
        self.executeShell(
            "env %s run-parts -- '%s'" % (env_string, parts_dir),
            failure=LaunchpadScriptFailure(
                "Failure while executing run-parts %s." % parts_dir))

    def runFinalizeParts(self, distribution, security_only=False):
        """Run the finalize.d parts to finalize publication."""
        archive_roots = shell_quote(' '.join([
            archive_config.archiveroot
            for archive_config in self.configs[distribution].itervalues()]))

        env = {
            'SECURITY_UPLOAD_ONLY': compose_shell_boolean(security_only),
            'ARCHIVEROOTS': archive_roots,
        }
        self.runParts(distribution, 'finalize.d', env)

    def publishSecurityUploads(self, distribution):
        """Quickly process just the pending security uploads."""
        self.logger.debug("Expediting security uploads.")
        security_suites = self.getDirtySecuritySuites(distribution)
        if len(security_suites) == 0:
            self.logger.debug("Nothing to do for security publisher.")
            return

        self.publishDistroArchive(
            distribution, distribution.main_archive,
            security_suites=security_suites)

    def publishDistroUploads(self, distribution):
        """Publish the distro's complete uploads."""
        self.logger.debug("Full publication.  This may take some time.")
        for archive in get_publishable_archives(distribution):
            if archive.purpose in self.configs[distribution]:
                # This, for the main archive, is where the script spends
                # most of its time.
                self.publishDistroArchive(distribution, archive)

    def publish(self, distribution, security_only=False):
        """Do the main publishing work.

        :param security_only: If True, limit publication to security
            updates on the main archive.  This is much faster, so it
            makes sense to do a security-only run before the main
            event to expedite critical fixes.
        """
        try:
            if security_only:
                self.publishSecurityUploads(distribution)
            else:
                self.publishDistroUploads(distribution)

            # Swizzle the now-updated backup dists and the current dists
            # around.
            self.installDists(distribution)
        except:
            # If we failed here, there's a chance that we left a
            # working dists directory in its temporary location.  If so,
            # recover it.  The next script run would do that anyway, but
            # doing it now is easier on admins trying to recover from
            # system problems.
            self.recoverWorkingDists()
            raise

    def prepareFreshSeries(self, distribution):
        """If there are any new distroseries, prepare them for publishing.

        :return: True if a series did indeed still need some preparation,
            of False for the normal case.
        """
        have_fresh_series = False
        for series in distribution.series:
            suites_needing_indexes = self.listSuitesNeedingIndexes(series)
            if len(suites_needing_indexes) != 0:
                # This is a fresh series.
                have_fresh_series = True
                if series.previous_series is not None:
                    copier = CustomUploadsCopier(
                        series, PackagePublishingPocket.RELEASE)
                    copier.copy(
                        series.previous_series,
                        PackagePublishingPocket.RELEASE)
                self.createIndexes(distribution, suites_needing_indexes)

        return have_fresh_series

    def setUp(self):
        """Process options, and set up internal state."""
        self.processOptions()
        self.configs = self.getConfigs()

    def processDistro(self, distribution):
        """Process `distribution`."""
        if self.prepareFreshSeries(distribution):
            # We've done enough here.  Leave some server time for others.
            return

        self.processAccepted(distribution)

        self.rsyncBackupDists(distribution)
        self.publish(distribution, security_only=True)
        self.runFinalizeParts(distribution, security_only=True)

        if not self.options.security_only:
            self.rsyncBackupDists(distribution)
            self.publish(distribution, security_only=False)
            self.generateListings(distribution)
            self.clearEmptyDirs(distribution)
            self.runFinalizeParts(distribution, security_only=False)

        if self.options.post_rsync:
            #  Update the backup dists with the published changes.  The
            #  initial rsync on the next run will not need to make any
            #  changes, and so it'll take the next run a little less
            #  time to publish its security updates.
            self.rsyncBackupDists(distribution)

    def main(self):
        """See `LaunchpadScript`."""
        self.setUp()
        self.recoverWorkingDists()
        self.setUpDirs()

        for distribution in self.distributions:
            if len(self.configs[distribution]) > 0:
                self.processDistro(distribution)
                self.txn.commit()
