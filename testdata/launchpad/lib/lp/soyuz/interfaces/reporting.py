# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'ILatestPersonSourcePackageReleaseCache',
    ]


from zope.interface import Attribute

from lp.soyuz.interfaces.sourcepackagerelease import ISourcePackageRelease


class ILatestPersonSourcePackageReleaseCache(ISourcePackageRelease):
    """Published source package release information for a person.

    The records represented by this object are the latest published source
    package releases for a given sourcepackage, distroseries, archive, keyed
    on the package creator and maintainer. The table contains a set of data
    records for package creators and a second set of data for package
    maintainers. Queries can be filtered by creator or maintainer as required.
    """

    cache_id = Attribute(
        "The id of the associated LatestPersonSourcePackageReleaseCache"
        "record.")
    sourcepackagerelease = Attribute(
        "The SourcePackageRelease which this object represents.")
    publication = Attribute(
        "The publication record for the associated SourcePackageRelease.")
