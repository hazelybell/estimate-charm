# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Source package in Distribution interfaces."""

__metaclass__ = type

__all__ = [
    'IDistributionSourcePackage',
    ]

from lazr.restful.declarations import (
    export_as_webservice_entry,
    exported,
    )
from lazr.restful.fields import Reference
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import TextLine

from lp import _
from lp.answers.interfaces.questiontarget import IQuestionTarget
from lp.bugs.interfaces.bugtarget import (
    IBugTarget,
    IHasOfficialBugTags,
    )
from lp.bugs.interfaces.structuralsubscription import (
    IStructuralSubscriptionTarget,
    )
from lp.code.interfaces.hasbranches import (
    IHasBranches,
    IHasMergeProposals,
    )
from lp.registry.interfaces.distribution import IDistribution
from lp.registry.interfaces.role import IHasDrivers
from lp.soyuz.enums import ArchivePurpose


class IDistributionSourcePackage(IBugTarget, IHasBranches, IHasMergeProposals,
                                 IHasOfficialBugTags,
                                 IStructuralSubscriptionTarget,
                                 IQuestionTarget, IHasDrivers):
    """Represents a source package in a distribution.

    Create IDistributionSourcePackages by invoking
    `IDistribution.getSourcePackage()`.
    """

    export_as_webservice_entry()

    distribution = exported(
        Reference(IDistribution, title=_("The distribution.")))
    sourcepackagename = Attribute("The source package name.")

    name = exported(
        TextLine(title=_("The source package name as text"), readonly=True))
    displayname = exported(
        TextLine(title=_("Display name for this package."), readonly=True),
        exported_as="display_name")
    title = exported(
        TextLine(title=_("Title for this package."), readonly=True))

    upstream_product = exported(
        Reference(
            title=_("The upstream product to which this package is linked."),
            required=False,
            readonly=True,
            # This is really an IProduct but we get a circular import
            # problem if we do that here. This is patched in
            # interfaces/product.py.
            schema=Interface))

    is_official = Attribute(
        'Is this source package officially in the distribution?')

    summary = Attribute(
        'The summary of binary packages built from this package')

    binary_names = Attribute(
        'A list of binary package names built from this package.')

    currentrelease = Attribute(
        "The latest published `IDistributionSourcePackageRelease` of a "
        "source package with this name in the distribution or distroseries, "
        "or None if no source package with that name is published in this "
        "distroseries.")

    releases = Attribute(
        "The list of all releases of this source package "
        "in this distribution.")

    development_version = Attribute(
        "The development version of this source package. 'None' if there is "
        "no such package -- this occurs when there is no current series for "
        "the distribution.")

    bug_count = Attribute(
        "Number of bugs matching the distribution and sourcepackagename "
        "of the IDistributionSourcePackage.")

    po_message_count = Attribute(
        "Number of translations matching the distribution and "
        "sourcepackagename of the IDistributionSourcePackage.")

    drivers = Attribute("The drivers for the distribution.")

    def getReleasesAndPublishingHistory():
        """Return a list of all releases of this source package in this
        distribution and their corresponding publishing history.

        Items in the list are tuples comprised of a
        DistributionSourcePackage and a list of
        SourcePackagePublishingHistory objects.
        """

    publishing_history = Attribute(
        "Return a list of publishing records for this source package in this "
        "distribution.")

    current_publishing_records = Attribute(
        "Return a list of CURRENT publishing records for this source "
        "package in this distribution.")

    def getVersion(version):
        """Return the a DistributionSourcePackageRelease with the given
        version, or None if there has never been a release with that
        version in this distribution.
        """

    def get_distroseries_packages(active_only=True):
        """Return a list of DistroSeriesSourcePackage objects, each
        representing this same source package in the series of this
        distribution.

        By default, this will return SourcePackage's in active
        distroseries only. You can set only_active=False to return a
        source package for EVERY series where this source package was
        published.
        """

    def findRelatedArchives(exclude_archive=None,
                            archive_purpose=ArchivePurpose.PPA,
                            required_karma=0):
        """Return Archives which publish this source package.

        :param exclude_archive: an archive to exclude from the results,
            used to exclude the current context from which the method
            is called.
        :param archive_purpose: used to filter the results to certain
            archive purposes. Defaults to PPA.
        :param required_karma: if non-zero then the results will be
            limited to archives where the creator of the related source
            package release in that archive has karma greater than the
            specified value.
        :returns: A `ResultSet` of non-unique `IArchive` with the
            results ordered by the descending package karma.
        """

    latest_overall_publication = Attribute(
        """The latest publication for this package across its distribution.

        The criteria for determining the publication are:
            - Only PUBLISHED or OBSOLETE publications
            - Only updates, security or release pockets
            - PUBLISHED wins over OBSOLETE
            - The latest distroseries wins
            - updates > security > release

        See https://bugs.launchpad.net/soyuz/+bug/236922 for a plan
        on how this criteria will be centrally encoded.
        """)

    def __eq__(other):
        """IDistributionSourcePackage comparison method.

        Distro sourcepackages compare equal only if their distribution and
        sourcepackagename compare equal.
        """

    def __ne__(other):
        """IDistributionSourcePackage comparison method.

        Distro sourcepackages compare not equal if either of their
        distribution or sourcepackagename compare not equal.
        """

    def delete():
        """Delete the persistent DSP if it exists.

        :return: True if a persistent object was removed, otherwise False.
        """
