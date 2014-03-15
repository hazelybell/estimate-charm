# Copyright 2009, 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Source package interfaces."""

__metaclass__ = type

__all__ = [
    'ISourcePackage',
    'ISourcePackagePublic',
    'ISourcePackageEdit',
    'ISourcePackageFactory',
    'SourcePackageFileType',
    'SourcePackageType',
    'SourcePackageRelationships',
    'SourcePackageUrgency',
    ]

from lazr.enum import (
    DBEnumeratedType,
    DBItem,
    )
from lazr.restful.declarations import (
    call_with,
    export_as_webservice_entry,
    export_read_operation,
    export_write_operation,
    exported,
    operation_for_version,
    operation_parameters,
    operation_returns_entry,
    REQUEST_USER,
    )
from lazr.restful.fields import (
    Reference,
    ReferenceChoice,
    )
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Choice,
    Object,
    TextLine,
    )

from lp import _
from lp.bugs.interfaces.bugtarget import (
    IBugTarget,
    IHasOfficialBugTags,
    )
from lp.code.interfaces.hasbranches import (
    IHasBranches,
    IHasCodeImports,
    IHasMergeProposals,
    )
from lp.registry.interfaces.productseries import IProductSeries
from lp.registry.interfaces.role import (
    IHasDrivers,
    IHasOwner,
    )
from lp.soyuz.interfaces.component import IComponent
from lp.translations.interfaces.hastranslationimports import (
    IHasTranslationImports,
    )
from lp.translations.interfaces.hastranslationtemplates import (
    IHasTranslationTemplates,
    )


class ISourcePackagePublic(IBugTarget, IHasBranches, IHasMergeProposals,
                           IHasOfficialBugTags, IHasCodeImports,
                           IHasTranslationImports, IHasTranslationTemplates,
                           IHasDrivers, IHasOwner):
    """Public attributes for SourcePackage."""

    name = exported(
        TextLine(
            title=_("Name"), required=True, readonly=True,
            description=_("The text name of this source package.")))

    displayname = exported(
        TextLine(
            title=_("Display name"), required=True, readonly=True,
            description=_("A displayname, constructed, for this package")))

    path = Attribute("A path to this package, <distro>/<series>/<package>")

    title = Attribute("Title.")

    summary = Attribute(
        'A description of the binary packages built from this package.')

    format = Attribute("Source Package Format. This is the format of the "
                "current source package release for this name in this "
                "distribution or distroseries. Calling this when there is "
                "no current sourcepackagerelease will raise an exception.")

    distinctreleases = Attribute("Return a distinct list "
        "of sourcepackagepublishinghistory for this source package.")

    distribution = exported(
        Reference(
            Interface,
            # Really IDistribution, circular import fixed in
            # _schema_circular_imports.
            title=_("Distribution"), required=True, readonly=True,
            description=_("The distribution for this source package.")))

    # The interface for this is really IDistroSeries, but importing that would
    # cause circular imports. Set in _schema_circular_imports.
    distroseries = exported(
        Reference(
            Interface, title=_("Distribution Series"), required=True,
            readonly=True,
            description=_("The DistroSeries for this SourcePackage")))

    sourcepackagename = Attribute("SourcePackageName")

    # This is really a reference to an IProductSeries.
    productseries = exported(
        ReferenceChoice(
            title=_("Project series"), required=False,
            vocabulary="ProductSeries", readonly=True,
            schema=Interface,
            description=_(
                "The registered project series that this source package "
                "is based on. This series may be the same as the one that "
                "earlier versions of this source packages were based on.")))

    releases = Attribute("The full set of source package releases that "
        "have been published in this distroseries under this source "
        "package name. The list should be sorted by version number.")

    currentrelease = Attribute("""The latest published SourcePackageRelease
        of a source package with this name in the distribution or
        distroseries, or None if no source package with that name is
        published in this distroseries.""")

    direct_packaging = Attribute("Return the Packaging record that is "
        "explicitly for this distroseries and source package name, "
        "or None if such a record does not exist. You should probably "
        "use ISourcePackage.packaging, which will also look through the "
        "distribution ancestry to find a relevant packaging record.")

    packaging = Attribute("The best Packaging record we have for this "
        "source package. If we have one for this specific distroseries "
        "and sourcepackagename, it will be returned, otherwise we look "
        "for a match in parent and ubuntu distro seriess.")

    published_by_pocket = Attribute("The set of source package releases "
        "currently published in this distro series, organised by "
        "pocket. The result is a dictionary, with the pocket dbschema "
        "as a key, and a list of source package releases as the value.")

    linked_branches = Attribute(
        "A mapping of pockets to officially linked branches, ordered by "
        "pocket enum value.")

    development_version = Attribute(
        "This package on the distro's current series.")

    distribution_sourcepackage = Attribute(
        "The IDistributionSourcePackage for this source package.")

    drivers = Attribute(
        "The drivers for the distroseries for this source package.")

    owner = Attribute(
        "The owner of the distroseries for this source package.")

    def __getitem__(version):
        """Return the source package release with the given version in this
        distro series, or None."""

    def __hash__():
        """Sourcepackage hash method.

        This is required to make source packages usable as dictionary
        keeps since the __eq__ method is provided.
        """

    def __eq__(other):
        """Sourcepackage comparison method.

        Sourcepackages compare equal only if their distroseries and
        sourcepackagename compare equal.
        """

    def __ne__(other):
        """Sourcepackage comparison method.

        Sourcepackages compare not equal if either of their distroseries or
        sourcepackagename compare not equal.
        """

    @operation_parameters(productseries=Reference(schema=IProductSeries))
    @call_with(owner=REQUEST_USER)
    @export_write_operation()
    @operation_for_version('devel')
    def setPackaging(productseries, owner):
        """Update the existing packaging record, or create a new packaging
        record, that links the source package to the given productseries,
        and record that it was done by the owner.
        """

    @operation_parameters(productseries=Reference(schema=IProductSeries))
    @call_with(owner=REQUEST_USER)
    @export_write_operation()
    @operation_for_version('devel')
    def setPackagingReturnSharingDetailPermissions(productseries, owner):
        """Like setPackaging(), but returns getSharingDetailPermissions().

        This method is intended for AJAX usage on the +sharing-details
        page.
        """

    @export_write_operation()
    @operation_for_version('devel')
    def deletePackaging():
        """Delete the packaging for this sourcepackage."""

    def getSharingDetailPermissions():
        """Return a dictionary of user permissions for +sharing-details page.

        This shows whether the user can change
        - The project series
        - The project series target branch
        - The project series autoimport mode
        - The project translation usage setting
        """

    def getSuiteSourcePackage(pocket):
        """Return the `ISuiteSourcePackage` for this package in 'pocket'.

        :param pocket: A `DBItem` of `PackagePublishingPocket`.
        :return: An `ISuiteSourcePackage`.
        """

    def getPocketPath(pocket):
        """Get the path to the given pocket of this package.

        :param pocket: A `DBItem` of `PackagePublishingPocket`.
        :return: A string.
        """

    # 'pocket' should actually be a PackagePublishingPocket, but we say
    # DBEnumeratedType to avoid circular imports. Correct interface specific
    # in _schema_circular_imports.
    @operation_parameters(
        pocket=Choice(
            title=_("Pocket"), required=True,
            vocabulary=DBEnumeratedType))
    # Actually returns an IBranch, but we say Interface here to avoid circular
    # imports. Correct interface specified in _schema_circular_imports.
    @operation_returns_entry(Interface)
    @export_read_operation()
    def getBranch(pocket):
        """Get the official branch for this package in the given pocket.

        :param pocket: A `PackagePublishingPocket`.
        :return: An `IBranch`.
        """

    latest_published_component = Object(
        title=u'The component in which the package was last published.',
        schema=IComponent, readonly=True, required=False)

    latest_published_component_name = exported(TextLine(
        title=u'The name of the component in which the package'
               ' was last published.',
        readonly=True, required=False))

    def get_default_archive(component=None):
        """Get the default archive of this package.

        If 'component' is a partner component, then the default archive is the
        partner archive. Otherwise, the primary archive of the associated
        distribution.

        :param component: The `IComponent` to base the default archive
            decision on. If None, defaults to the last published component.
        :raise NoPartnerArchive: If returning the partner archive is
            appropriate, but no partner archive exists.
        :return: `IArchive`.
        """

    def getLatestTranslationsUploads():
        """Find latest Translations tarballs as produced by Soyuz.

        :return: A list of `ILibraryFileAlias`es, usually of size zero
            or one.  If not, they are sorted from oldest to newest.
        """

    @export_read_operation()
    def linkedBranches():
        """Get the official branches for this package.

        This operation returns a {`Pocket`-name : `IBranch`} dict.

        :return: A {`Pocket`-name : `IBranch`} dict.
        """


class ISourcePackageEdit(Interface):
    """SourcePackage attributes requiring launchpad.Edit."""

    # 'pocket' should actually be a PackagePublishingPocket, and 'branch'
    # should be IBranch, but we use the base classes to avoid circular
    # imports. Correct interface specific in _schema_circular_imports.
    @operation_parameters(
        pocket=Choice(
            title=_("Pocket"), required=True,
            vocabulary=DBEnumeratedType),
        branch=Reference(Interface, title=_("Branch"), required=False))
    @call_with(registrant=REQUEST_USER)
    @export_write_operation()
    def setBranch(pocket, branch, registrant):
        """Set the official branch for the given pocket of this package.

        :param pocket: A `PackagePublishingPocket`.
        :param branch: The branch to set as the official branch.
        :param registrant: The individual who created this link.
        :return: None
        """


class ISourcePackage(ISourcePackagePublic, ISourcePackageEdit):
    """A source package associated to a particular distribution series."""
    export_as_webservice_entry()


class ISourcePackageFactory(Interface):
    """A creator of source packages."""

    def new(sourcepackagename, distroseries):
        """Create a new `ISourcePackage`.

        :param sourcepackagename: An `ISourcePackageName`.
        :param distroseries: An `IDistroSeries`.
        :return: `ISourcePackage`.
        """


class SourcePackageFileType(DBEnumeratedType):
    """Source Package File Type

    Launchpad tracks files associated with a source package release. These
    files are stored on one of the inner servers, and a record is kept in
    Launchpad's database of the file's name and location. This schema
    documents the files we know about.
    """

    EBUILD = DBItem(1, """
        Ebuild File

        This is a Gentoo Ebuild, the core file that Gentoo uses as a source
        package release. Typically this is a shell script that pulls in the
        upstream tarballs, configures them and builds them into the
        appropriate locations.  """)

    SRPM = DBItem(2, """
        Source RPM

        This is a Source RPM, a normal RPM containing the needed source code
        to build binary packages. It would include the Spec file as well as
        all control and source code files.  """)

    DSC = DBItem(3, """
        DSC File

        This is a DSC file containing the Ubuntu source package description,
        which in turn lists the orig.tar.gz and diff.tar.gz files used to
        make up the package.  """)

    ORIG_TARBALL = DBItem(4, """
        Orig Tarball

        This file is an Ubuntu "orig" file, typically an upstream tarball or
        other lightly-modified upstreamish thing.  """)

    DIFF = DBItem(5, """
        Diff File

        This is an Ubuntu "diff" file, containing changes that need to be
        made to upstream code for the packaging on Ubuntu. Typically this
        diff creates additional directories with patches and documentation
        used to build the binary packages for Ubuntu.

        This is only part of the 1.0 source package format.""")

    NATIVE_TARBALL = DBItem(6, """
        Native Tarball

        This is a tarball, usually of a mixture of Ubuntu and upstream code,
        used in the build process for this source package.  """)

    DEBIAN_TARBALL = DBItem(7, """
        Debian Tarball

        This file is an Ubuntu "orig" file, typically an upstream tarball or
        other lightly-modified upstreamish thing.

        This is only part of the 3.0 (quilt) source package format.""")

    COMPONENT_ORIG_TARBALL = DBItem(8, """
        Component Orig Tarball

        This file is an Ubuntu component "orig" file, typically an upstream
        tarball containing a component of the source package.

        This is only part of the 3.0 (quilt) source package format.""")


class SourcePackageType(DBEnumeratedType):
    """Source Package Format

    Launchpad supports distributions that use source packages in a variety
    of source package formats. This schema documents the types of source
    package format that we understand.
    """

    DPKG = DBItem(1, """
        The DEB Format

        This is the source package format used by Ubuntu, Debian, Linspire
        and similar distributions.
        """)

    RPM = DBItem(2, """
        The RPM Format

        This is the format used by Red Hat, Mandrake, SUSE and other similar
        distributions.
        """)

    EBUILD = DBItem(3, """
        The Ebuild Format

        This is the source package format used by Gentoo.
        """)


class SourcePackageRelationships(DBEnumeratedType):
    """Source Package Relationships

    Launchpad tracks many source packages. Some of these are related to one
    another. For example, a source package in Ubuntu called "apache2" might
    be related to a source package in Mandrake called "httpd". This schema
    defines the relationships that Launchpad understands.
    """

    REPLACES = DBItem(1, """
        Replaces

        The subject source package was designed to replace the object source
        package.  """)

    REIMPLEMENTS = DBItem(2, """
        Reimplements

        The subject source package is a completely new packaging of the same
        underlying products as the object package.  """)

    SIMILARTO = DBItem(3, """
        Similar To

        The subject source package is similar, in that it packages software
        that has similar functionality to the object package.  For example,
        postfix and exim4 would be "similarto" one another.  """)

    DERIVESFROM = DBItem(4, """
        Derives From

        The subject source package derives from and tracks the object source
        package. This means that new uploads of the object package should
        trigger a notification to the maintainer of the subject source
        package.  """)

    CORRESPONDSTO = DBItem(5, """
        Corresponds To

        The subject source package includes the same products as the object
        source package, but for a different distribution. For example, the
        "apache2" Ubuntu package "correspondsto" the "httpd2" package in Red
        Hat.  """)


class SourcePackageUrgency(DBEnumeratedType):
    """Source Package Urgency

    When a source package is released it is given an "urgency" which tells
    distributions how important it is for them to consider bringing that
    package into their archives. This schema defines the possible values
    for source package urgency.
    """

    LOW = DBItem(1, """
        Low Urgency

        This source package release does not contain any significant or
        important updates, it might be a cleanup or documentation update
        fixing typos and speling errors, or simply a minor upstream
        update.
        """)

    MEDIUM = DBItem(2, """
        Medium Urgency

        This package contains updates that are worth considering, such
        as new upstream or packaging features, or significantly better
        documentation.
        """)

    HIGH = DBItem(3, """
        Very Urgent

        This update contains updates that fix security problems or major
        system stability problems with previous releases of the package.
        Administrators should urgently evaluate the package for inclusion
        in their archives.
        """)

    EMERGENCY = DBItem(4, """
        Critically Urgent

        This release contains critical security or stability fixes that
        affect the integrity of systems using previous releases of the
        source package, and should be installed in the archive as soon
        as possible after appropriate review.
        """)
