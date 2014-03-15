# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Source package release in Distribution Series interfaces."""

__metaclass__ = type

__all__ = [
    'IDistroSeriesSourcePackageRelease',
    ]

from zope.interface import Attribute
from zope.schema import Object

from lp import _
from lp.services.librarian.interfaces import ILibraryFileAlias
from lp.soyuz.interfaces.sourcepackagerelease import ISourcePackageRelease


class IDistroSeriesSourcePackageRelease(ISourcePackageRelease):
    """This is a SourcePackageRelease-In-A-DistroSeries. It represents a
    real source package release that has been uploaded to a distroseries.

    You can tell if it is still in the queue, and in which queue. You can
    ask it the dates of various events in its history in this
    distroseries. You can also ask it what pocket it is published in, if
    it has been published. Or which version superseded it, if it has been
    superseded.
    """

    distroseries = Attribute("The distro series.")
    sourcepackage = Attribute("The distribution series source package.")
    sourcepackagerelease = Attribute("The source package release.")

    name = Attribute("The source package name as text")
    displayname = Attribute("Display name for this package.")
    title = Attribute("Title for this package.")
    distribution = Attribute("The distribution.")
    pocket = Attribute("The pocket in which this release is published, "
        "or None if it is not currently published.")

    publishing_history = Attribute("Return a list of publishing "
        "records for this source package release in this series "
        "of the distribution.")

    builds = Attribute("The builds we have for this sourcepackage release "
        "specifically in this distroseries. Note that binaries could "
        "be inherited from a parent distribution, not necessarily built "
        "here, but must be published in a main archive.")

    binaries = Attribute(
        "Return binaries resulted from this sourcepackagerelease and  "
        "published in this distroseries.")

    version = Attribute("The version of the source package release.")

    changesfile = Object(
        title=_("Correspondent changesfile."), schema=ILibraryFileAlias,
        readonly=True)

    published_binaries = Attribute(
        "A list of published `DistroArchSeriesBinaryPackageRelease` for "
        "all relevant architectures.")
