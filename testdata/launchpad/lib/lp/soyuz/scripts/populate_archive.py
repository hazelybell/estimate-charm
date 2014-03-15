# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Create a copy archive (if needed) and populate it with packages."""


__metaclass__ = type
__all__ = [
    'ArchivePopulator',
    ]


from zope.component import getUtility

from lp.app.errors import NotFoundError
from lp.app.validators.name import valid_name
from lp.registry.interfaces.person import IPersonSet
from lp.soyuz.adapters.packagelocation import build_package_location
from lp.soyuz.enums import ArchivePurpose
from lp.soyuz.interfaces.archive import IArchiveSet
from lp.soyuz.interfaces.archivearch import IArchiveArchSet
from lp.soyuz.interfaces.component import IComponentSet
from lp.soyuz.interfaces.packagecloner import IPackageCloner
from lp.soyuz.interfaces.packagecopyrequest import IPackageCopyRequestSet
from lp.soyuz.interfaces.processor import (
    IProcessorSet,
    ProcessorNotFound,
    )
from lp.soyuz.scripts.ftpmasterbase import (
    SoyuzScript,
    SoyuzScriptError,
    )


def specified(option):
    """Return False if option was not supplied or is an empty string.

    Return True otherwise.
    """
    if option is None:
        return False
    if isinstance(option, basestring) and option.strip() == '':
        return False
    return True


class ArchivePopulator(SoyuzScript):
    """
    Create a copy archive and populate it with packages.

    The logic needed to create a copy archive, populate it with source
    packages and instantiate the builds required.
    """

    usage = __doc__
    description = (
        'Create a copy archive and populate it with packages and build '
        'records.')

    def populateArchive(
        self, from_archive, from_distribution, from_suite, from_user,
        component, to_distribution, to_suite, to_archive, to_user, reason,
        include_binaries, arch_tags, merge_copy_flag,
        packageset_delta_flag, packageset_tags, nonvirtualized):
        """Create archive, populate it with packages and builds.

        Please note: if a component was specified for the origin then the
        same component must be used for the destination.

        :param from_archive: the (optional) origin archive name.
        :param from_distribution: the origin's distribution.
        :param from_suite: the origin's suite.
        :param from_user: the name of the origin PPA's owner.
        :param component: the origin's component.

        :param to_distribution: destination distribution.
        :param to_suite: destination suite.

        :param to_archive: destination copy archive name.
        :param to_user: destination archive owner name.
        :param reason: reason for the package copy operation.

        :param include_binaries: whether binaries should be copied as well.
        :param arch_tags: architecture tags for which to create
            builds.
        :param merge_copy_flag: whether this is a repeated population of an
            existing copy archive.
        :param packageset_delta_flag: only show packages that are fresher or
            new in the origin archive. Do not copy anything.

        :param packageset_tags: list of packagesets to limit the packages
            copied to.
        """

        def loadProcessors(arch_tags):
            """Load processors for specified arch tags."""
            processors = set()
            for name in arch_tags:
                try:
                    processor = getUtility(IProcessorSet).getByName(name)
                    processors.add(processor)
                except ProcessorNotFound:
                    raise SoyuzScriptError(
                        "Invalid architecture tag: '%s'" % name)
            return processors

        def set_archive_architectures(archive, processors):
            """Associate the archive with the processors."""
            aa_set = getUtility(IArchiveArchSet)
            for processor in processors:
                aa_set.new(archive, processor)

        def build_location(distro, suite, component, packageset_names=None):
            """Build and return package location."""
            location = build_package_location(
                distro, suite=suite, packageset_names=packageset_names)
            if component is not None:
                try:
                    the_component = getUtility(IComponentSet)[component]
                except NotFoundError:
                    raise SoyuzScriptError(
                        "Invalid component name: '%s'" % component)
                location.component = the_component
            return location

        archive_set = getUtility(IArchiveSet)
        # Build the origin package location.
        the_origin = build_location(
            from_distribution, from_suite, component,
            packageset_names=packageset_tags)

        # Use a non-PPA(!) origin archive if specified and existent.
        if from_archive is not None and from_user is None:
            origin_archive = archive_set.getByDistroAndName(
                the_origin.distribution, from_archive)
            if origin_archive is not None:
                the_origin.archive = origin_archive
            else:
                raise SoyuzScriptError(
                    "Origin archive does not exist: '%s'" % from_archive)
        # Use a PPA if specified and existent.
        if from_user is not None:
            origin_archive = archive_set.getPPAByDistributionAndOwnerName(
                the_origin.distribution, from_user, from_archive)
            if origin_archive is not None:
                the_origin.archive = origin_archive
            else:
                raise SoyuzScriptError(
                    "No PPA for user: '%s'" % from_user)

        if the_origin.archive.private:
            if from_user is not None:
                the_name = '%s/%s' % (from_user, the_origin.archive.name)
            else:
                the_name = the_origin.archive.name
            raise SoyuzScriptError(
                "Cannot copy from private archive ('%s')" % the_name)

        # Build the destination package location.
        the_destination = build_location(to_distribution, to_suite, component)

        # First try to access the destination copy archive.
        copy_archive = getUtility(IArchiveSet).getByDistroAndName(
            the_destination.distribution, to_archive)

        the_destination.archive = copy_archive

        if packageset_delta_flag:
            if copy_archive is None:
                raise SoyuzScriptError(
                    "error: package set delta requested for non-existing "
                    " destination archive.")
            else:
                self._packageset_delta(the_origin, the_destination)
                return

        if not specified(to_user):
            if merge_copy_flag:
                what = 'package copy requestor'
            else:
                what = 'copy archive owner'
            raise SoyuzScriptError("error: %s not specified." % what)

        registrant = getUtility(IPersonSet).getByName(to_user)
        if registrant is None:
            raise SoyuzScriptError("Invalid user name: '%s'" % to_user)

        # No copy archive with the specified name found, create one.
        if copy_archive is None:
            if not specified(reason):
                raise SoyuzScriptError(
                    "error: reason for copy archive creation not specified.")
            if merge_copy_flag:
                raise SoyuzScriptError(
                    "error: merge copy requested for non-existing archive.")
            # The architecture tags should only be specified if the
            # destination copy archive does not exist yet and needs to be
            # created.
            if not specified(arch_tags):
                raise SoyuzScriptError(
                    "error: architecture tags not specified.")

            # First load the processors for the specified arch tags
            # from the database. This will fail if an invalid arch tag
            # name was specified on the command line; that's why it should be
            # done before creating the copy archive.
            processors = loadProcessors(arch_tags)

            # The copy archive is created in disabled mode. This gives the
            # archive owner the chance to tweak the build dependencies
            # before the switch is flipped and build activity starts.
            # Also, builds for copy archives should default to using
            # virtual builders.
            virtual = not nonvirtualized
            copy_archive = getUtility(IArchiveSet).new(
                ArchivePurpose.COPY, registrant, name=to_archive,
                distribution=the_destination.distribution,
                description=reason, enabled=False,
                require_virtualized=virtual)
            the_destination.archive = copy_archive
            # Associate the newly created copy archive with the processors
            # specified by the user.
            set_archive_architectures(copy_archive, processors)
        else:
            # Archive name clash! Creation requested for existing archive with
            # the same name and distribution.
            if not merge_copy_flag:
                raise SoyuzScriptError(
                    "error: archive '%s' already exists for '%s'."
                    % (to_archive, the_destination.distribution.name))
            # The user is not supposed to specify processors on the command
            # line for existing copy archives. The processors specified when
            # the archive was created will be read from the database instead.
            if specified(arch_tags):
                raise SoyuzScriptError(
                    "error: cannot specify architecture tags for *existing* "
                    "archive.")
            # Refuse to copy to a disabled copy archive.
            if not copy_archive.enabled:
                raise SoyuzScriptError(
                    "error: cannot copy to disabled archive")

        # Now instantiate the package copy request that will capture the
        # archive population parameters in the database.
        pcr = getUtility(IPackageCopyRequestSet).new(
            the_origin, the_destination, registrant,
            copy_binaries=include_binaries, reason=unicode(reason))

        # Clone the source packages. We currently do not support the copying
        # of binary packages. It's a forthcoming feature.
        pkg_cloner = getUtility(IPackageCloner)

        # Mark the package copy request as being "in progress".
        pcr.markAsInprogress()
        self.txn.commit()

        if merge_copy_flag:
            pkg_cloner.mergeCopy(the_origin, the_destination)
        else:
            pkg_cloner.clonePackages(
                the_origin, the_destination, processors=processors)

        # Mark the package copy request as completed.
        pcr.markAsCompleted()

    def _packageset_delta(self, origin, destination):
        """Perform a package set delta operation between two archives.

        No packages will be copied i.e. the destination archive will not be
        changed.
        """
        pkg_cloner = getUtility(IPackageCloner)
        pkg_cloner.packageSetDiff(
            origin, destination, self.logger)

    def mainTask(self):
        """Main function entry point."""
        opts = self.options

        if not specified(opts.from_distribution):
            raise SoyuzScriptError(
                "error: origin distribution not specified.")

        if not specified(opts.to_distribution):
            raise SoyuzScriptError(
                "error: destination distribution not specified.")

        if not specified(opts.to_archive):
            raise SoyuzScriptError(
                "error: destination copy archive not specified.")
        if not valid_name(opts.to_archive):
            raise SoyuzScriptError(
                "Invalid destination archive name: '%s'" % opts.to_archive)
        if opts.include_binaries:
            raise SoyuzScriptError(
                "error: copying of binary packages is not supported yet.")

        if (specified(opts.from_user) and not specified(opts.from_archive)):
            opts.from_archive = 'ppa'

        if specified(opts.from_archive) and not valid_name(opts.from_archive):
            raise SoyuzScriptError(
                "Invalid origin archive name: '%s'" % opts.from_archive)

        # For the love of $DEITY, WTF doesn't this method just accept a
        # single parameter "opts" ...
        self.populateArchive(
            opts.from_archive, opts.from_distribution, opts.from_suite,
            opts.from_user, opts.component, opts.to_distribution,
            opts.to_suite, opts.to_archive, opts.to_user, opts.reason,
            opts.include_binaries, opts.arch_tags, opts.merge_copy_flag,
            opts.packageset_delta_flag, opts.packageset_tags,
            opts.nonvirtualized)

    def add_my_options(self):
        """Parse command line arguments for copy archive creation/population.
        """
        SoyuzScript.add_my_options(self)

        self.parser.add_option(
            "-a", "--architecture", dest="arch_tags", action="append",
            help="The architecture tags for which to create build "
                 "records, repeat for each architecture required.")
        self.parser.add_option(
            "-b", "--include-binaries", dest="include_binaries",
            default=False, action="store_true",
            help='Whether to copy related binaries or not.')

        self.parser.add_option(
            '--from-archive', dest='from_archive', default=None,
            action='store', help='Origin archive name.')
        self.parser.add_option(
            '--from-distribution', dest='from_distribution',
            default='ubuntu', action='store',
            help='Origin distribution name.')
        self.parser.add_option(
            '--from-suite', dest='from_suite', default=None,
            action='store', help='Origin suite name.')
        self.parser.add_option(
            '--from-user', dest='from_user', default=None,
            action='store', help='Origin PPA owner name.')

        self.parser.add_option(
            '--to-distribution', dest='to_distribution',
            default='ubuntu', action='store',
            help='Destination distribution name.')
        self.parser.add_option(
            '--to-suite', dest='to_suite', default=None,
            action='store', help='Destination suite name.')

        self.parser.add_option(
            '--to-archive', dest='to_archive', default=None,
            action='store', help='Destination archive name.')

        self.parser.add_option(
            '--to-user', dest='to_user', default=None,
            action='store', help='Destination user name.')

        self.parser.add_option(
            "--reason", dest="reason",
            help="The reason for this packages copy operation.")

        self.parser.add_option(
            "--merge-copy", dest="merge_copy_flag",
            default=False, action="store_true",
            help='Repeated population of an existing copy archive.')

        self.parser.add_option(
            "--package-set-delta", dest="packageset_delta_flag",
            default=False, action="store_true",
            help=(
                'Only show packages that are fresher or new in origin '
                'archive. Destination archive must exist already.'))

        self.parser.add_option(
            "--package-set", dest="packageset_tags", action="append",
            help=(
                'Limit to copying packages in the selected packagesets.'))

        self.parser.add_option(
            "--nonvirtualized", dest="nonvirtualized", default=False,
            action="store_true",
            help='Create the archive as nonvirtual if specified.')
