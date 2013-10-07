# Copyright 2011-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Archive Contents files generator."""

__metaclass__ = type
__all__ = [
    'GenerateContentsFiles',
    ]

from optparse import OptionValueError
import os

from zope.component import getUtility

from lp.archivepublisher.config import getPubConfig
from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.interfaces.series import SeriesStatus
from lp.services.command_spawner import (
    CommandSpawner,
    OutputLineHandler,
    ReturnCodeReceiver,
    )
from lp.services.config import config
from lp.services.database.policy import (
    DatabaseBlockedPolicy,
    SlaveOnlyDatabasePolicy,
    )
from lp.services.scripts.base import (
    LaunchpadCronScript,
    LaunchpadScriptFailure,
    )
from lp.services.utils import file_exists


COMPONENTS = [
    'main',
    'restricted',
    'universe',
    'multiverse',
    ]


def differ_in_content(one_file, other_file):
    """Do the two named files have different contents?"""
    one_exists = file_exists(one_file)
    other_exists = file_exists(other_file)
    if any([one_exists, other_exists]):
        return (
            one_exists != other_exists or
            file(one_file).read() != file(other_file).read())
    else:
        return False


def get_template(template_name):
    """Return path of given template in this script's templates directory."""
    return os.path.join(
        config.root, "cronscripts", "publishing", "gen-contents",
        template_name)


def execute(logger, command, args=None):
    """Execute a shell command.

    :param logger: Output from the command will be logged here.
    :param command: Command to execute, as a string.
    :param args: Optional list of arguments for `command`.
    :raises LaunchpadScriptFailure: If the command returns failure.
    """
    command_line = [command]
    if args is not None:
        command_line += args
    description = ' '.join(command_line)

    logger.debug("Execute: %s", description)
    # Some of these commands can take a long time.  Use CommandSpawner
    # and friends to provide "live" log output.  Simpler ways of running
    # commands tend to save it all up and then dump it at the end, or
    # have trouble logging it as neat lines.
    stderr_logger = OutputLineHandler(logger.info)
    stdout_logger = OutputLineHandler(logger.debug)
    receiver = ReturnCodeReceiver()
    spawner = CommandSpawner()
    spawner.start(
        command_line, completion_handler=receiver,
        stderr_handler=stderr_logger, stdout_handler=stdout_logger)
    spawner.complete()
    stdout_logger.finalize()
    stderr_logger.finalize()
    if receiver.returncode != 0:
        raise LaunchpadScriptFailure(
            "Failure while running command: %s" % description)


class GenerateContentsFiles(LaunchpadCronScript):

    distribution = None

    def add_my_options(self):
        """See `LaunchpadScript`."""
        self.parser.add_option(
            "-d", "--distribution", dest="distribution", default=None,
            help="Distribution to generate Contents files for.")

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

    def setUpContentArchive(self):
        """Make sure the `content_archive` directories exist."""
        self.logger.debug("Ensuring that we have a private tree in place.")
        for suffix in ['cache', 'misc']:
            dirname = '-'.join([self.distribution.name, suffix])
            path = os.path.join(self.content_archive, dirname)
            if not file_exists(path):
                os.makedirs(path)

    def getSupportedSeries(self):
        """Return suites that are supported in this distribution.

        "Supported" means not EXPERIMENTAL or OBSOLETE.
        """
        unsupported_status = (SeriesStatus.EXPERIMENTAL,
                              SeriesStatus.OBSOLETE)
        for series in self.distribution:
            if series.status not in unsupported_status:
                yield series

    def getSuites(self):
        """Return suites that are actually supported in this distribution."""
        for series in self.getSupportedSeries():
            for pocket in PackagePublishingPocket.items:
                suite = series.getSuite(pocket)
                if file_exists(os.path.join(self.config.distsroot, suite)):
                    yield suite

    def getArchs(self, suite):
        """Query architectures supported by the suite."""
        series, _ = self.distribution.getDistroSeriesAndPocket(suite)
        return [arch.architecturetag for arch in series.enabled_architectures]

    def getDirs(self, archs):
        """Subdirectories needed for each component."""
        return ['source', 'debian-installer'] + [
            'binary-%s' % arch for arch in archs]

    def writeAptContentsConf(self, suites):
        """Write apt-contents.conf file."""
        output_dirname = '%s-misc' % self.distribution.name
        output_path = os.path.join(
            self.content_archive, output_dirname, "apt-contents.conf")
        output_file = file(output_path, 'w')

        parameters = {
            'content_archive': self.content_archive,
            'distribution': self.distribution.name,
        }

        header = get_template('apt_conf_header.template')
        output_file.write(file(header).read() % parameters)

        dist_template = file(get_template('apt_conf_dist.template')).read()
        for suite in suites:
            parameters['suite'] = suite
            parameters['architectures'] = ' '.join(self.getArchs(suite))
            output_file.write(dist_template % parameters)

        output_file.close()

    def createComponentDirs(self, suites):
        """Create the content archive's tree for all of its components."""
        for suite in suites:
            for component in COMPONENTS:
                for directory in self.getDirs(self.getArchs(suite)):
                    path = os.path.join(
                        self.content_archive, self.distribution.name, 'dists',
                        suite, component, directory)
                    if not file_exists(path):
                        self.logger.debug("Creating %s.", path)
                        os.makedirs(path)

    def copyOverrides(self, override_root):
        """Copy overrides into the content archive.

        This method won't access the database.
        """
        if file_exists(override_root):
            execute(self.logger, "cp", [
                "-a",
                override_root,
                "%s/" % self.content_archive,
                ])
        else:
            self.logger.debug("Did not find overrides; not copying.")

    def writeContentsTop(self, distro_name, distro_title):
        """Write Contents.top file.

        This method won't access the database.
        """
        output_filename = os.path.join(
            self.content_archive, '%s-misc' % distro_name, "Contents.top")
        parameters = {
            'distrotitle': distro_title,
        }
        output_file = file(output_filename, 'w')
        text = file(get_template("Contents.top")).read() % parameters
        output_file.write(text)
        output_file.close()

    def runAptFTPArchive(self, distro_name):
        """Run apt-ftparchive to produce the Contents files.

        This method may take a long time to run.
        This method won't access the database.
        """
        execute(self.logger, "apt-ftparchive", [
            "generate",
            os.path.join(
                self.content_archive, "%s-misc" % distro_name,
                "apt-contents.conf"),
            ])

    def generateContentsFiles(self, override_root, distro_name, distro_title):
        """Generate Contents files.

        This method may take a long time to run.
        This method won't access the database.

        :param override_root: Copy of `self.config.overrideroot` that can be
            evaluated without accessing the database.
        :param distro_name: Copy of `self.distribution.name` that can be
            evaluated without accessing the database.
        :param distro_title: Copy of `self.distribution.title` that can be
            evaluated without accessing the database.
        """
        self.logger.debug(
            "Running apt in private tree to generate new contents.")
        self.copyOverrides(override_root)
        self.writeContentsTop(distro_name, distro_title)
        self.runAptFTPArchive(distro_name)

    def updateContentsFile(self, suite, arch):
        """Update Contents file, if it has changed."""
        contents_dir = os.path.join(
            self.content_archive, self.distribution.name, 'dists', suite)
        contents_filename = "Contents-%s" % arch
        last_contents = os.path.join(contents_dir, ".%s" % contents_filename)
        current_contents = os.path.join(contents_dir, contents_filename)

        # Avoid rewriting unchanged files; mirrors would have to
        # re-fetch them unnecessarily.
        if differ_in_content(current_contents, last_contents):
            self.logger.debug(
                "Installing new Contents file for %s/%s.", suite, arch)

            new_contents = os.path.join(
                contents_dir, "%s.gz" % contents_filename)
            contents_dest = os.path.join(
                self.config.distsroot, suite, "%s.gz" % contents_filename)

            os.rename(current_contents, last_contents)
            os.rename(new_contents, contents_dest)
            os.chmod(contents_dest, 0664)
        else:
            self.logger.debug(
                "Skipping unmodified Contents file for %s/%s.", suite, arch)

    def updateContentsFiles(self, suites):
        """Update all Contents files that have changed."""
        self.logger.debug("Comparing contents files with public tree.")
        for suite in suites:
            for arch in self.getArchs(suite):
                self.updateContentsFile(suite, arch)

    def setUp(self):
        """Prepare configuration and filesystem state for the script's work.

        This is idempotent: run it as often as you like.  (For example,
        a test may call `setUp` prior to calling `main` which again
        invokes `setUp`).
        """
        self.processOptions()
        self.config = getPubConfig(self.distribution.main_archive)
        self.content_archive = os.path.join(
            self.config.distroroot, "contents-generation")
        self.setUpContentArchive()

    def process(self):
        """Do the bulk of the work."""
        self.setUp()
        suites = list(self.getSuites())
        self.writeAptContentsConf(suites)
        self.createComponentDirs(suites)

        overrideroot = self.config.overrideroot
        distro_name = self.distribution.name
        distro_title = self.distribution.title

        # This takes a while.  Ensure that we do it without keeping a
        # database transaction open.
        self.txn.commit()
        with DatabaseBlockedPolicy():
            self.generateContentsFiles(
                overrideroot, distro_name, distro_title)

        self.updateContentsFiles(suites)

    def main(self):
        """See `LaunchpadScript`."""
        # This code has no need to alter the database.
        with SlaveOnlyDatabasePolicy():
            self.process()
