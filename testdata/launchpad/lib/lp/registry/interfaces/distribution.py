# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces including and related to IDistribution."""

__metaclass__ = type

__all__ = [
    'IBaseDistribution',
    'IDerivativeDistribution',
    'IDistribution',
    'IDistributionDriverRestricted',
    'IDistributionEditRestricted',
    'IDistributionMirrorMenuMarker',
    'IDistributionPublic',
    'IDistributionSet',
    'NoPartnerArchive',
    'NoSuchDistribution',
    ]

from lazr.lifecycle.snapshot import doNotSnapshot
from lazr.restful.declarations import (
    call_with,
    collection_default_content,
    export_as_webservice_collection,
    export_as_webservice_entry,
    export_operation_as,
    export_read_operation,
    exported,
    operation_for_version,
    operation_parameters,
    operation_returns_collection_of,
    operation_returns_entry,
    rename_parameters_as,
    REQUEST_USER,
    )
from lazr.restful.fields import (
    CollectionField,
    Reference,
    )
from lazr.restful.interface import copy_field
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Bool,
    Choice,
    Datetime,
    List,
    Object,
    Text,
    TextLine,
    )

from lp import _
from lp.answers.interfaces.questiontarget import IQuestionTarget
from lp.app.errors import NameLookupFailed
from lp.app.interfaces.headings import IRootContext
from lp.app.interfaces.launchpad import (
    ILaunchpadUsage,
    IServiceUsage,
    )
from lp.app.validators.name import name_validator
from lp.blueprints.interfaces.specificationtarget import ISpecificationTarget
from lp.blueprints.interfaces.sprint import IHasSprints
from lp.bugs.interfaces.bugsupervisor import IHasBugSupervisor
from lp.bugs.interfaces.bugtarget import (
    IBugTarget,
    IHasExpirableBugs,
    IOfficialBugTagTargetPublic,
    IOfficialBugTagTargetRestricted,
    )
from lp.bugs.interfaces.structuralsubscription import (
    IStructuralSubscriptionTarget,
    )
from lp.registry.interfaces.announcement import IMakesAnnouncements
from lp.registry.interfaces.distributionmirror import IDistributionMirror
from lp.registry.interfaces.distroseries import DistroSeriesNameField
from lp.registry.interfaces.karma import IKarmaContext
from lp.registry.interfaces.milestone import (
    ICanGetMilestonesDirectly,
    IHasMilestones,
    )
from lp.registry.interfaces.oopsreferences import IHasOOPSReferences
from lp.registry.interfaces.pillar import (
    IHasSharingPolicies,
    IPillar,
    )
from lp.registry.interfaces.role import (
    IHasAppointedDriver,
    IHasDrivers,
    IHasOwner,
    )
from lp.services.fields import (
    Description,
    IconImageUpload,
    LogoImageUpload,
    MugshotImageUpload,
    PillarNameField,
    PublicPersonChoice,
    Summary,
    Title,
    )
from lp.soyuz.interfaces.buildrecords import IHasBuildRecords
from lp.translations.interfaces.hastranslationimports import (
    IHasTranslationImports,
    )
from lp.translations.interfaces.translationpolicy import ITranslationPolicy


class IDistributionMirrorMenuMarker(Interface):
    """Marker interface for Mirror navigation."""


class DistributionNameField(PillarNameField):
    """The pillar for a distribution."""

    @property
    def _content_iface(self):
        """Return the interface of this pillar object."""
        return IDistribution


class IDistributionEditRestricted(IOfficialBugTagTargetRestricted):
    """IDistribution properties requiring launchpad.Edit permission."""


class IDistributionDriverRestricted(Interface):
    """IDistribution properties requiring launchpad.Driver permission."""

    def newSeries(name, displayname, title, summary, description,
                  version, previous_series, registrant):
        """Creates a new distroseries."""


class IDistributionPublic(
    IBugTarget, ICanGetMilestonesDirectly, IHasAppointedDriver,
    IHasBuildRecords, IHasDrivers, IHasMilestones, IHasSharingPolicies,
    IHasOOPSReferences, IHasOwner, IHasSprints, IHasTranslationImports,
    ITranslationPolicy, IKarmaContext, ILaunchpadUsage, IMakesAnnouncements,
    IOfficialBugTagTargetPublic, IPillar, IServiceUsage,
    ISpecificationTarget, IHasExpirableBugs):
    """Public IDistribution properties."""

    id = Attribute("The distro's unique number.")
    name = exported(
        DistributionNameField(
            title=_("Name"),
            constraint=name_validator,
            description=_("The distro's name."), required=True))
    displayname = exported(
        TextLine(
            title=_("Display Name"),
            description=_("The displayable name of the distribution."),
            required=True),
        exported_as='display_name')
    title = exported(
        Title(
            title=_("Title"),
            description=_("The distro's title."), required=True))
    summary = exported(
        Summary(
            title=_("Summary"),
            description=_(
                "A short paragraph to introduce the goals and highlights "
                "of the distribution."),
            required=True))
    homepage_content = exported(
        Text(
            title=_("Homepage Content"), required=False,
            description=_(
                "The content of this distribution's home page. Edit this and "
                "it will be displayed for all the world to see. It is NOT a "
                "wiki so you cannot undo changes.")))
    icon = exported(
        IconImageUpload(
            title=_("Icon"), required=False,
            default_image_resource='/@@/distribution',
            description=_(
                "A small image of exactly 14x14 pixels and at most 5kb in "
                "size, that can be used to identify this distribution. The "
                "icon will be displayed everywhere we list the distribution "
                "and link to it.")))
    logo = exported(
        LogoImageUpload(
            title=_("Logo"), required=False,
            default_image_resource='/@@/distribution-logo',
            description=_(
                "An image of exactly 64x64 pixels that will be displayed in "
                "the heading of all pages related to this distribution. It "
                "should be no bigger than 50kb in size.")))
    mugshot = exported(
        MugshotImageUpload(
            title=_("Brand"), required=False,
            default_image_resource='/@@/distribution-mugshot',
            description=_(
                "A large image of exactly 192x192 pixels, that will be "
                "displayed on this distribution's home page in Launchpad. "
                "It should be no bigger than 100kb in size. ")))
    description = exported(
        Description(
            title=_("Description"),
            description=_(
                "Details about the distributions's work, highlights, goals, "
                "and how to contribute. Use plain text, paragraphs are "
                "preserved and URLs are linked in pages. Don't repeat the "
                "Summary."),
            required=True))
    domainname = exported(
        TextLine(
            title=_("Web site URL"),
            description=_("The distro's web site URL."), required=True),
        exported_as='domain_name')
    owner = exported(
        PublicPersonChoice(
            title=_("Owner"),
            required=True,
            vocabulary='ValidPillarOwner',
            description=_("The restricted team, moderated team, or person "
                          "who maintains the distribution information in "
                          "Launchpad.")))
    registrant = exported(
        PublicPersonChoice(
            title=_("Registrant"), vocabulary='ValidPersonOrTeam',
            description=_("The distro's registrant."), required=True,
            readonly=True))
    date_created = exported(
        Datetime(title=_('Date created'),
                 description=_("The date this distribution was registered.")))
    driver = exported(
        PublicPersonChoice(
            title=_("Driver"),
            description=_(
                "The person or team responsible for decisions about features "
                "and bugs that will be targeted for any series in this "
                "distribution. Note that you can also specify a driver "
                "on each series whose permissions will be limited to that "
                "specific series."),
            required=False, vocabulary='ValidPersonOrTeam'))
    drivers = Attribute(
        "Presents the distro driver as a list for consistency with "
        "IProduct.drivers where the list might include a project driver.")
    members = exported(PublicPersonChoice(
        title=_("Members"),
        description=_("The distro's members team."), required=True,
        vocabulary='ValidPersonOrTeam'))
    mirror_admin = exported(PublicPersonChoice(
        title=_("Mirror Administrator"),
        description=_("The person or team that has the rights to review and "
                      "mark this distribution's mirrors as official."),
        required=True, vocabulary='ValidPersonOrTeam'))
    archive_mirrors = exported(doNotSnapshot(
        CollectionField(
            description=_("All enabled and official ARCHIVE mirrors "
                          "of this Distribution."),
            readonly=True, value_type=Object(schema=IDistributionMirror))))
    archive_mirrors_by_country = doNotSnapshot(CollectionField(
            description=_("All enabled and official ARCHIVE mirrors "
                          "of this Distribution."),
            readonly=True, value_type=Object(schema=IDistributionMirror)))
    cdimage_mirrors = exported(doNotSnapshot(
        CollectionField(
            description=_("All enabled and official RELEASE mirrors "
                          "of this Distribution."),
            readonly=True, value_type=Object(schema=IDistributionMirror))))
    cdimage_mirrors_by_country = doNotSnapshot(CollectionField(
            description=_("All enabled and official ARCHIVE mirrors "
                          "of this Distribution."),
            readonly=True, value_type=Object(schema=IDistributionMirror)))
    disabled_mirrors = Attribute(
        "All disabled and official mirrors of this Distribution.")
    unofficial_mirrors = Attribute(
        "All unofficial mirrors of this Distribution.")
    pending_review_mirrors = Attribute(
        "All mirrors of this Distribution that haven't been reviewed yet.")
    series = exported(doNotSnapshot(
        CollectionField(
            title=_("DistroSeries inside this Distribution"),
            # Really IDistroSeries, see _schema_circular_imports.py.
            value_type=Reference(schema=Interface))))
    derivatives = exported(doNotSnapshot(
        CollectionField(
            title=_("This Distribution's derivatives"),
            # Really IDistroSeries, see _schema_circular_imports.py.
            value_type=Reference(schema=Interface))))
    architectures = List(
        title=_("DistroArchSeries inside this Distribution"))
    uploaders = Attribute(_(
        "ArchivePermission records for uploaders with rights to upload to "
        "this distribution."))
    package_derivatives_email = TextLine(
        title=_("Package Derivatives Email Address"),
        description=_(
            "The email address to send information about updates to packages "
            "that are derived from another distribution. The sequence "
            "{package_name} is replaced with the actual package name."),
        required=False)

    # properties
    currentseries = exported(
        Reference(
            # Really IDistroSeries, see _schema_circular_imports.py.
            Interface,
            title=_("Current series"),
            description=_(
                "The current development series of this distribution. "
                "Note that all maintainerships refer to the current "
                "series. When people ask about the state of packages "
                "in the distribution, we should interpret that query "
                "in the context of the currentseries.")),
        exported_as="current_series")

    full_functionality = Attribute(
        "Whether or not we enable the full functionality of Launchpad for "
        "this distribution. Currently only Ubuntu and some derivatives "
        "get the full functionality of LP")

    translation_focus = Choice(
        title=_("Translation focus"),
        description=_(
            "The release series that translators should focus on."),
        required=False,
        vocabulary='FilteredDistroSeries')

    language_pack_admin = Choice(
        title=_("Language Pack Administrator"),
        description=_("The distribution language pack administrator."),
        required=False, vocabulary='ValidPersonOrTeam')

    main_archive = exported(
        Reference(
            title=_('Distribution Main Archive.'), readonly=True,
            # Really IArchive, see _schema_circular_imports.py.
            schema=Interface))

    all_distro_archives = exported(doNotSnapshot(
        CollectionField(
            title=_(
                "A sequence of the distribution's primary, "
                "partner and debug archives."),
            readonly=True, required=False,
            value_type=Reference(schema=Interface))),
                # Really IArchive, see _schema_circular_imports.py.
        exported_as='archives')

    all_distro_archive_ids = Attribute(
        "A list containing the IDs of all the non-PPA archives.")

    has_published_binaries = Bool(
        title=_("Has Published Binaries"),
        description=_("True if this distribution has binaries published "
                      "on disk."),
        readonly=True, required=False)

    has_published_sources = Bool(
        title=_("Has Published Sources"),
        description=_("True if this distribution has sources published."),
        readonly=True, required=False)

    redirect_release_uploads = exported(Bool(
        title=_("Redirect release pocket uploads"),
        description=_("Redirect release pocket uploads to proposed pocket"),
        readonly=False, required=True))

    development_series_alias = exported(DistroSeriesNameField(
        title=_("Alias for development series"),
        description=_(
            "If set, an alias for the current development series in this "
            "distribution."),
        constraint=name_validator, readonly=False, required=False))

    def getArchiveIDList(archive=None):
        """Return a list of archive IDs suitable for sqlvalues() or quote().

        If the archive param is supplied, just its ID will be returned in
        a list of one item.  If it is not supplied, return a list of
        all the IDs for all the archives for the distribution.
        """

    def __getitem__(name):
        """Returns a DistroSeries that matches name, or raises and
        exception if none exists."""

    def __iter__():
        """Iterate over the series for this distribution."""

    @operation_parameters(
        name=TextLine(title=_("Archive name"), required=True))
    @operation_returns_entry(Interface)
    @export_read_operation()
    def getArchive(name):
        """Return the distribution archive with the given name.

        Only distribution archives are considered -- PPAs will not be found.

        :param name: The name of the archive, e.g. 'partner'
        """

    # Really IDistroSeries, see _schema_circular_imports.py.
    @operation_returns_collection_of(Interface)
    @export_operation_as(name="getDevelopmentSeries")
    @export_read_operation()
    def getDevelopmentSeries():
        """Return the DistroSeries which are marked as in development."""

    def resolveSeriesAlias(name):
        """Resolve a series alias.

        :param name: The name to resolve.
        :raises NoSuchDistroSeries: If there is no match.
        """

    @operation_parameters(
        name_or_version=TextLine(title=_("Name or version"), required=True))
    # Really IDistroSeries, see _schema_circular_imports.py.
    @operation_returns_entry(Interface)
    @call_with(follow_aliases=True)
    @export_read_operation()
    def getSeries(name_or_version, follow_aliases=False):
        """Return the series with the name or version given.

        :param name_or_version: The `IDistroSeries.name` or
            `IDistroSeries.version`.
        """

    # This API is specifically for Ensemble's Principia.  It does not scale
    # well to distributions of Ubuntu's scale, and is not intended for it.
    # Therefore, this should probably never be exposed for a webservice
    # version other than "devel".
    @operation_parameters(
        since=Datetime(
            title=_("Time of last change"),
            description=_(
                "Return branches that have new tips since this timestamp."),
            required=False))
    @call_with(user=REQUEST_USER)
    @export_operation_as(name="getBranchTips")
    @export_read_operation()
    @operation_for_version('devel')
    def getBranchTips(user=None, since=None):
        """Return a list of branches which have new tips since a date.

        Each branch information is a tuple of (branch_unique_name,
        tip_revision, (official_series*)).

        So for each branch in the distribution, you'll get the branch unique
        name, the revision id of tip, and if the branch is official for some
        series, the list of series name.

        :param: user: If specified, shows the branches visible to that user.
            if not specified, only branches visible to the anonymous user are
            shown.

        :param since: If specified, limits results to branches modified since
            that date and time.
        """

    @operation_parameters(
        name=TextLine(title=_("Name"), required=True))
    @operation_returns_entry(IDistributionMirror)
    @export_read_operation()
    def getMirrorByName(name):
        """Return the mirror with the given name for this distribution or None
        if it's not found.
        """

    @operation_parameters(
        country=copy_field(IDistributionMirror['country'], required=True),
        mirror_type=copy_field(IDistributionMirror['content'], required=True))
    @operation_returns_entry(IDistributionMirror)
    @export_read_operation()
    def getCountryMirror(country, mirror_type):
        """Return the country DNS mirror for a country and content type."""

    def newMirror(owner, speed, country, content, displayname=None,
                  description=None, http_base_url=None,
                  ftp_base_url=None, rsync_base_url=None, enabled=False,
                  official_candidate=False, whiteboard=None):
        """Create a new DistributionMirror for this distribution.

        At least one of http_base_url or ftp_base_url must be provided in
        order to create a mirror.
        """

    @operation_parameters(
        name=TextLine(title=_("Package name"), required=True))
    # Really returns IDistributionSourcePackage, see
    # _schema_circular_imports.py.
    @operation_returns_entry(Interface)
    @export_read_operation()
    def getSourcePackage(name):
        """Return a DistributionSourcePackage with the given name for this
        distribution, or None.
        """

    def getSourcePackageRelease(sourcepackagerelease):
        """Returns an IDistributionSourcePackageRelease

        Receives a sourcepackagerelease.
        """

    def getCurrentSourceReleases(source_package_names):
        """Get the current release of a list of source packages.

        :param source_package_names: a list of `ISourcePackageName`
            instances.

        :return: a dict where the key is a `IDistributionSourcePackage`
            and the value is a `IDistributionSourcePackageRelease`.
        """

    def getDistroSeriesAndPocket(distroseriesname, follow_aliases=False):
        """Return a (distroseries,pocket) tuple which is the given textual
        distroseriesname in this distribution."""

    def getSeriesByStatus(status):
        """Query context distribution for distroseries with a given status.

        :param status: Series status to look for
        :return: list of `IDistroSeries`
        """

    @rename_parameters_as(text="source_match")
    @operation_parameters(
        text=TextLine(title=_("Source package name substring match"),
                      required=True))
    # Really returns IDistributionSourcePackage, see
    # _schema_circular_imports.py.
    @operation_returns_collection_of(Interface)
    @export_read_operation()
    def searchSourcePackages(
        text, has_packaging=None, publishing_distroseries=None):
        """Search for source packages that correspond to the given text.

        This method just decorates the result of searchSourcePackageCaches()
        to return DistributionSourcePackages.
        """

    def searchSourcePackageCaches(
        text, has_packaging=None, publishing_distroseries=None):
        """Search for source packages that correspond to the given text.

        :param text: The text that will be matched.
        :param has_packaging: If True, it will filter out
            packages with no packaging (i.e. no link to the upstream
            project). False will do the reverse filtering, and None
            will do no filtering on this field.
        :param publishing_distroseries: If it is not None, then
            it will filter out source packages that do not have a
            publishing history for the given distroseries.
        :return: A result set containing
            (DistributionSourcePackageCache, SourcePackageName, rank) tuples
            ordered by rank.
        """

    def searchBinaryPackages(package_name, exact_match=False):
        """Search for binary packages in this distribution.

        :param package_name: The binary package name to match.
        :param exact_match: If False, substring matches are done on the
            binary package names; if True only a full string match is
            returned.
        :return: A result set containing appropriate DistributionSourcePackage
            objects for the matching source.

        The returned results will consist of source packages that match
        (a substring of) their binary package names.
        """

    def guessPublishedSourcePackageName(pkgname):
        """Return the "published" SourcePackageName related to pkgname.

        If pkgname corresponds to a source package that was published in
        any of the distribution series, that's the SourcePackageName that is
        returned.

        If there is any official source package branch linked, then that
        source package name is returned.

        Otherwise, try to find a published binary package name and then return
        the source package name from which it comes from.

        :raises NotFoundError: when pkgname doesn't correspond to either a
            published source or binary package name in this distribution.
        """

    def getAllPPAs():
        """Return all PPAs for this distribution."""

    def searchPPAs(text=None, show_inactive=False):
        """Return all PPAs matching the given text in this distribution.

        'text', when passed, will restrict results to Archives with matching
        description (using substring) or matching Archive.owner (using
        available person fti/ftq).

        'show_inactive', when False, will restrict results to Archive with
        at least one source publication in PENDING or PUBLISHED status.
        """

    def getPendingAcceptancePPAs():
        """Return only pending acceptance PPAs in this distribution."""

    def getPendingPublicationPPAs():
        """Return all PPAs in this distribution that are pending publication.

        A PPA is said to be pending publication if it has publishing records
        in the pending state or if it had packages deleted from it.
        """

    def getArchiveByComponent(component_name):
        """Return the archive most appropriate for the component name.

        Where different components may imply a different archive (e.g.
        partner), this method will return the archive for that component.

        If the component_name supplied is unknown, None is returned.
        """

    def getAllowedBugInformationTypes():
        """Get the information types that a bug in this distribution can have.

        :return: A sequence of `InformationType`s.
        """

    def getDefaultBugInformationType():
        """Get the default information type of a new bug in this distro.

        :return: The `InformationType`.
        """

    def userCanEdit(user):
        """Can the user edit this distribution?"""


class IDistribution(
    IDistributionEditRestricted, IDistributionPublic, IHasBugSupervisor,
    IQuestionTarget, IRootContext, IStructuralSubscriptionTarget):
    """An operating system distribution.

    Launchpadlib example: retrieving the current version of a package in a
    particular distroseries.

    ::

        ubuntu = launchpad.distributions["ubuntu"]
        archive = ubuntu.main_archive
        series = ubuntu.current_series
        print archive.getPublishedSources(exact_match=True,
            source_name="apport",
            distro_series=series)[0].source_package_version
    """
    export_as_webservice_entry(as_of="beta")


class IBaseDistribution(IDistribution):
    """A Distribution that is the base for other Distributions."""


class IDerivativeDistribution(IDistribution):
    """A Distribution that derives from another Distribution."""


class IDistributionSet(Interface):
    """Interface for DistrosSet"""
    export_as_webservice_collection(IDistribution)

    title = Attribute('Title')

    def __iter__():
        """Iterate over all distributions.

        Ubuntu and its flavours will always be at the top of the list, with
        the other ones sorted alphabetically after them.
        """

    def __getitem__(name):
        """Retrieve a distribution by name"""

    @collection_default_content()
    def getDistros():
        """Return all distributions.

        Ubuntu and its flavours will always be at the top of the list, with
        the other ones sorted alphabetically after them.
        """

    def count():
        """Return the number of distributions in the system."""

    def get(distributionid):
        """Return the IDistribution with the given distributionid."""

    def getByName(distroname):
        """Return the IDistribution with the given name or None."""

    def new(name, displayname, title, description, summary, domainname,
            members, owner, registrant, mugshot=None, logo=None, icon=None):
        """Create a new distribution."""

    def getCurrentSourceReleases(distro_to_source_packagenames):
        """Lookup many distribution source package releases.

        :param distro_to_source_packagenames: A dictionary with
            its keys being `IDistribution` and its values a list of
            `ISourcePackageName`.
        :return: A dict as per `IDistribution.getCurrentSourceReleases`
        """

    def getDerivedDistributions():
        """Find derived distributions.

        :return: An iterable of all derived distributions (not including
            Ubuntu, even if it is technically derived from Debian).
        """


class NoSuchDistribution(NameLookupFailed):
    """Raised when we try to find a distribution that doesn't exist."""

    _message_prefix = "No such distribution"


class NoPartnerArchive(Exception):
    """Raised when a partner archive is needed, but none exists."""

    def __init__(self, distribution):
        Exception.__init__(
            self, "Partner archive for distro '%s' not found"
            % (distribution.name, ))
