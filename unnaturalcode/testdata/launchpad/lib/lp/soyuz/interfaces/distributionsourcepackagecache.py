# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Source package in Distribution Cache interfaces."""

__metaclass__ = type

__all__ = [
    'IDistributionSourcePackageCache',
    ]

from zope.interface import (
    Attribute,
    Interface,
    )


class IDistributionSourcePackageCache(Interface):

    archive = Attribute("The cache target archive.")
    distribution = Attribute("The cache target distribution.")
    sourcepackagename = Attribute("The source package name.")

    name = Attribute("The source package name as text.")
    binpkgnames = Attribute("A concatenation of the binary package names "
        "associated with this source package in the distribution.")
    binpkgsummaries = Attribute("A concatenation of the binary package "
        "summaries for this source package.")
    binpkgdescriptions = Attribute("A concatenation of the descriptions "
        "of the binary packages from this source package name in the "
        "distro.")
    changelog = Attribute("A concatenation of the source package release "
        "changelog entries for this source package, where the status is "
        "not REMOVED.")

    distributionsourcepackage = Attribute("The DistributionSourcePackage "
        "for which this is a cache.")

