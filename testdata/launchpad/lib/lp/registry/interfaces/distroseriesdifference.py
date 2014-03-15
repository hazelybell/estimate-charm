# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interface classes for a difference between two distribution series."""

__metaclass__ = type


__all__ = [
    'IDistroSeriesDifference',
    'IDistroSeriesDifferenceAdmin',
    'IDistroSeriesDifferencePublic',
    'IDistroSeriesDifferenceEdit',
    'IDistroSeriesDifferenceSource',
    ]

from lazr.restful.declarations import (
    call_with,
    export_as_webservice_entry,
    export_write_operation,
    exported,
    operation_parameters,
    REQUEST_USER,
    )
from lazr.restful.fields import Reference
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Bool,
    Choice,
    Int,
    Text,
    TextLine,
    )

from lp import _
from lp.registry.enums import (
    DistroSeriesDifferenceStatus,
    DistroSeriesDifferenceType,
    )
from lp.registry.interfaces.distroseries import IDistroSeries
from lp.registry.interfaces.person import IPerson
from lp.registry.interfaces.sourcepackagename import ISourcePackageName
from lp.soyuz.enums import PackageDiffStatus
from lp.soyuz.interfaces.distroseriessourcepackagerelease import (
    IDistroSeriesSourcePackageRelease,
    )
from lp.soyuz.interfaces.packagediff import IPackageDiff
from lp.soyuz.interfaces.publishing import ISourcePackagePublishingHistory


class IDistroSeriesDifferencePublic(Interface):
    """The public interface for distro series differences."""

    id = Int(title=_('ID'), required=True, readonly=True)

    derived_series = exported(Reference(
        IDistroSeries, title=_("Derived series"), required=True,
        readonly=True, description=_(
            "The distribution series which identifies the derived series "
            "with the difference.")))

    parent_series = exported(Reference(
        IDistroSeries, title=_("Parent series"), required=True,
        readonly=True, description=_(
            "The distribution series which identifies the parent series "
            "with the difference.")))

    source_package_name_id = Int(
        title=u"Source package name id", required=True, readonly=True)
    source_package_name = Reference(
        ISourcePackageName,
        title=_("Source package name"), required=True, readonly=True,
        description=_(
            "The package with a difference between the derived series "
            "and its parent."))

    sourcepackagename = exported(
        TextLine(
            title=_("Source Package Name"),
            required=False, readonly=True))

    package_diff = Reference(
        IPackageDiff, title=_("Package diff"), required=False,
        readonly=True, description=_(
            "The most recently generated package diff from the base to the "
            "derived version."))

    package_diff_url = exported(TextLine(
        title=_("Package diff url"), readonly=True, required=False,
        description=_(
            "The url for the diff between the base version and the "
            "derived version.")))

    parent_package_diff = Reference(
        IPackageDiff, title=_("Parent package diff"), required=False,
        readonly=True, description=_(
            "The most recently generated package diff from the base to the "
            "parent version."))

    parent_package_diff_url = exported(TextLine(
        title=_("Parent package diff url"), readonly=True, required=False,
        description=_(
            "The url for the diff between the base version and the "
            "parent version.")))

    package_diff_status = exported(Choice(
        title=_("Package diff status"),
        readonly=True,
        vocabulary=PackageDiffStatus,
        description=_(
            "The status of the diff between the base version and the "
            "derived version.")))

    parent_package_diff_status = exported(Choice(
        title=_("Parent package diff status"),
        readonly=True,
        vocabulary=PackageDiffStatus,
        description=_(
            "The status of the diff between the base version and the "
            "parent version.")))

    status = exported(Choice(
        title=_('Distro series difference status.'),
        description=_('The current status of this difference.'),
        vocabulary=DistroSeriesDifferenceStatus,
        required=True, readonly=True))

    difference_type = Choice(
        title=_('Difference type'),
        description=_('The type of difference for this package.'),
        vocabulary=DistroSeriesDifferenceType,
        required=True, readonly=True)

    source_package_release = Reference(
        IDistroSeriesSourcePackageRelease,
        title=_("Derived source pub"), readonly=True,
        description=_(
            "The published version in the derived series with version "
            "source_version."))

    parent_source_package_release = Reference(
        IDistroSeriesSourcePackageRelease,
        title=_("Parent source pub"), readonly=True,
        description=_(
            "The published version in the derived series with version "
            "parent_source_version."))

    source_pub = Reference(
        ISourcePackagePublishingHistory,
        title=_("Latest derived source pub"), readonly=True,
        description=_(
            "The most recent published version in the derived series."))

    source_version = exported(TextLine(
        title=_("Source version"), readonly=True,
        description=_(
            "The version of the most recent source publishing in the "
            "derived series.")))

    parent_source_pub = Reference(
        ISourcePackagePublishingHistory,
        title=_("Latest parent source pub"), readonly=True,
        description=_(
            "The most recent published version in the parent series."))

    parent_source_version = exported(TextLine(
        title=_("Parent source version"), readonly=True,
        description=_(
            "The version of the most recent source publishing in the "
            "parent series.")))

    base_version = exported(TextLine(
        title=_("Base version"), readonly=True,
        description=_(
            "The common base version of the package for differences "
            "with different versions in the parent and derived series.")))

    base_source_pub = Reference(
        ISourcePackagePublishingHistory,
        title=_("Base source pub"), readonly=True,
        description=_(
            "The common base version published in the parent or the "
            "derived series."))

    owner = Reference(
        IPerson, title=_("Owning team of the derived series"), readonly=True,
        description=_(
            "This attribute mirrors the owner of the derived series."))

    title = TextLine(
        title=_("Title"), readonly=True, required=False, description=_(
            "A human-readable name describing this difference."))

    packagesets = Attribute("The packagesets for this source package in the "
                            "derived series.")

    parent_packagesets = Attribute("The packagesets for this source package "
                                   "in the parent series.")

    base_distro_source_package_release = Attribute(
        "The DistributionSourcePackageRelease object for the source release "
        "in the parent distribution.")

    def update(manual=False):
        """Checks that difference type and status matches current publishings.

        If the record is updated, a relevant comment is added.

        If there is no longer a difference (ie. the versions are
        the same) then the status is updated to RESOLVED.

        :param manual: Boolean, True if this is a user-requested change.
            This overrides auto-blacklisting.
        :return: True if the record was updated, False otherwise.
        """

    latest_comment = Reference(
        Interface,  # IDistroSeriesDifferenceComment
        title=_("The latest comment"),
        readonly=True)

    def getComments():
        """Return a result set of the comments for this difference."""


class IDistroSeriesDifferenceEdit(Interface):
    """Difference attributes requiring launchpad.Edit."""

    @call_with(commenter=REQUEST_USER)
    @operation_parameters(
        comment=Text(title=_("Comment text"), required=True))
    @export_write_operation()
    def addComment(commenter, comment):
        """Add a comment on this difference."""

    @call_with(requestor=REQUEST_USER)
    @export_write_operation()
    def requestPackageDiffs(requestor):
        """Requests IPackageDiffs for the derived and parent version.

        :raises DistroSeriesDifferenceError: When package diffs
            cannot be requested.
        """


class IDistroSeriesDifferenceAdmin(Interface):
    """Difference attributes requiring launchpad.Admin."""

    @call_with(commenter=REQUEST_USER)
    @operation_parameters(
        all=Bool(title=_("All"), required=False),
        comment=TextLine(title=_('Comment text'), required=False),
        )
    @export_write_operation()
    def blacklist(commenter, all=False, comment=None):
        """Blacklist this version or all versions of this source package and
        adds a comment on this difference.

        :param commenter: The requestor `IPerson`.
        :param comment: The comment string.
        :param all: Indicates whether all versions of this package should
            be blacklisted or just the current (default).
        :return: The created `DistroSeriesDifferenceComment` object.
        """

    @call_with(commenter=REQUEST_USER)
    @operation_parameters(
        comment=TextLine(title=_('Comment text'), required=False))
    @export_write_operation()
    def unblacklist(commenter, comment=None):
        """Removes this difference from the blacklist and adds a comment on
        this difference.

        The status will be updated based on the versions.

        :param commenter: The requestor `IPerson`.
        :param comment: The comment string.
        :return: The created `DistroSeriesDifferenceComment` object.
        """


class IDistroSeriesDifference(IDistroSeriesDifferencePublic,
                              IDistroSeriesDifferenceEdit,
                              IDistroSeriesDifferenceAdmin):
    """An interface for a package difference between two distroseries."""
    export_as_webservice_entry()


class IDistroSeriesDifferenceSource(Interface):
    """A utility of this interface can be used to create differences."""

    def new(derived_series, source_package_name, parent_series):
        """Create an `IDistroSeriesDifference`.

        :param derived_series: The distribution series which was derived
            from a parent. If a series without a parent is passed an
            exception is raised.
        :type derived_series: `IDistroSeries`.
        :param source_package_name: A source package name identifying the
            package with a difference.
        :type source_package_name: `ISourcePackageName`.
        :param parent_series: The distribution series which has the derived
            series as a child. If there is only one parent, it does not need
            to be specified.
        :type parent_series: `IDistroSeries`.
        :raises NotADerivedSeriesError: When the passed distro series
            is not a derived series.
        :return: A new `DistroSeriesDifference` object.
        """

    def getForDistroSeries(distro_series, difference_type=None,
                           name_filter=None, status=None,
                           child_version_higher=False, parent_series=None,
                           packagesets=None, changed_by=None):
        """Return differences for the derived distro series sorted by
        package name.

        :param distro_series: The derived distribution series which is to be
            searched for differences.
        :type distro_series: `IDistroSeries`.
        :param difference_type: The type of difference to include in the
            results.
        :type difference_type: `DistroSeriesDifferenceType`.
        :param name_filter: Name of either a source package or a package set
            to look for.  If given, return only packages whose name matches
            this string, or that are in a `Packageset` those name matches it.
        :type name_filter: unicode.
        :param status: Only differences matching the status(es) will be
            included.
        :type status: `DistroSeriesDifferenceStatus`.
        :param child_version_higher: Only differences for which the child's
            version is higher than the parent's version will be included.
        :type child_version_higher: bool.
        :param parent_series: The parent series to consider. Consider all
            parent series if this parameter is None.
        :type distro_series: `IDistroSeries`.
        :param packagesets: Optional iterable of `Packageset` to filter by.
        :param changed_by: An optional `Person` (an individual or a team) or a
            collection of `Person`s. The results are limited to only those
            changes made by the given people.
        :return: A result set of `IDistroSeriesDifference`.
        """

    def getByDistroSeriesNameAndParentSeries(distro_series,
                                             source_package_name,
                                             parent_series):
        """Returns a single difference matching the series, name and parent
        series.

        :param distro_series: The derived distribution series which is to be
            searched for differences.
        :type distro_series: `IDistroSeries`.
        :param source_package_name: The name of the package difference.
        :type source_package_name: unicode.
        :param parent_series: The parent distribution series of the package
        difference.
        :type distro_series: `IDistroSeries`.
        """

    def getSimpleUpgrades(distro_series):
        """Find pending upgrades that can be performed mindlessly.

        These are `DistroSeriesDifferences` where the parent has been
        updated and the child still has the old version, unchanged.

        Blacklisted items are excluded.
        """
