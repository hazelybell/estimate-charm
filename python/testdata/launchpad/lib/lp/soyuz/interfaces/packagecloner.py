# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces related to bulk copying of publishing history data."""

__metaclass__ = type

__all__ = [
    'IPackageCloner'
    ]

from zope.interface import Interface


class IPackageCloner(Interface):
    """Copies publishing history data across archives."""

    def clonePackages(origin, destination, distroarchseries_list=None,
                    processors=None, sourcepackagenames=None,
                    always_create=False):
        """Copy packages from origin to destination.

        Copies the source packages, as well as the binary packages for the
        specified `DistroArchSeries`.

        :param origin: the location from which packages are to be copied.
        :param destination: the location to which the data is to be copied.
        :param distroarchseries_list: the binary packages will be copied
            for the distroarchseries pairs specified (if any).
        :param processors: the processors that builds will be created for.
        :param sourcepackagenames: the source packages which are to be
            copied.
        :param always_create: if builds should always be created.
        """

    def mergeCopy(origin, destination):
        """Copy packages that are obsolete or missing in target archive.

        Copy source packages from a given source archive that are obsolete or
        missing in the target archive.

        :param origin: the location from which the data is to be copied.
        :param destination: the location to which the data is to be copied.
        """

    def packageSetDiff(origin, destination, logger=None):
        """Find packages that are obsolete or missing in target archive.

        :param origin: the location with potentially new or fresher packages.
        :param destination: the target location.
        :param diagnostic_output: an optional logger instance to which
            details of the source packages that are fresher or new in the
            origin archive will be logged.
        :return: a 2-tuple (fresher, new) where each element is a sequence
            of `SourcePackagePublishingHistory` keys of packages
            that are fresher and new in the origin archive respectively.
        """
