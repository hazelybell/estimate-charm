# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Binary package in a distroarchseries interfaces."""

__metaclass__ = type

__all__ = [
    'IDistroArchSeriesBinaryPackage',
    ]

from lazr.restful.fields import Reference
from zope.interface import (
    Attribute,
    Interface,
    )

from lp import _
from lp.registry.interfaces.distributionsourcepackage import (
    IDistributionSourcePackage,
    )


class IDistroArchSeriesBinaryPackage(Interface):

    distroarchseries = Attribute("The distribution architecture series.")
    binarypackagename = Attribute("The binary package name.")

    name = Attribute("The binary package name as text")
    displayname = Attribute("Display name for this package.")
    title = Attribute("Title for this package.")

    cache = Attribute("The corresponding IDistroSeriesPackageCache record.")

    summary = Attribute("A guessed summary for this package. Either "
        "the currentrelease summary, or the cached one for all "
        "architectures.")

    description = Attribute("A description for this package, as for "
        "the summary above.")

    distribution = Attribute("The distribution of the package.")
    distroseries = Attribute("The distroseries of the package.")

    releases = Attribute("All of the distroarchseries binary package "
        "releases that have been made for this package.")

    currentrelease = Attribute("""The latest published BinaryPackageRelease
        of a binary package with this name in the DistroArchSeries
        or None if no binary package with that name is
        published here.""")

    publishing_history = Attribute("Return a list of publishing "
        "records for this binary package in this distribution.")

    current_published = Attribute("is last BinaryPackagePublishing "
                                  "record that is in PUBLISHED status.")

    distro_source_package = Reference(IDistributionSourcePackage,
        title=_("The DistributionSourcePackage that was used to generate the "
            "current binary package release"))

    def __getitem__(version):
        """Return the DistroArchSeriesBinaryPackageRelease with the given
        version, or None if there has never been a release with that
        version, in this architecture series.
        """

