# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces for a Binary Package in a DistroSeries."""

__metaclass__ = type

__all__ = [
    'IDistroSeriesBinaryPackage',
    ]

from lazr.restful.fields import Reference
from zope.interface import (
    Attribute,
    Interface,
    )

from lp import _
from lp.soyuz.interfaces.distroarchseriesbinarypackagerelease import (
    IDistroArchSeriesBinaryPackageRelease,
    )
from lp.soyuz.interfaces.distroseriessourcepackagerelease import (
    IDistroSeriesSourcePackageRelease,
    )


class IDistroSeriesBinaryPackage(Interface):
    """A binary package in a distroseries."""

    distroseries = Attribute("The distroseries.")
    binarypackagename = Attribute("The name of the binary package.")

    name = Attribute("The binary package name, as text.")
    cache = Attribute("The cache entry for this binary package name "
        "and distro series, or None if there isn't one.")
    summary = Attribute("The example summary of this, based on the "
        "cache. Since there may be a few, we try to use the latest "
        "one.")
    description = Attribute("An example description for this binary "
        "package. Again, there may be some variations based on "
        "versions and architectures in the distro series, so we try "
        "to use the newest one.")

    title = Attribute("Used for page layout.")
    distribution = Attribute("The distribution, based on the distroseries")

    current_publishings = Attribute("The BinaryPackagePublishing records "
        "for this binary package name in this distroseries.")

    last_published = Reference(
        IDistroArchSeriesBinaryPackageRelease,
        title=_("The most recently published BinaryPackageRelease for this "
                "binary package in this distroseries."))

    last_sourcepackagerelease = Reference(
        IDistroSeriesSourcePackageRelease,
        title=_("The DistroSeriesSourcePackageRelease that was used to "
                "generate the most recently published binary package "
                "release"))

