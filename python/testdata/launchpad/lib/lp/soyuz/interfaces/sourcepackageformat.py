# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Source package format interfaces."""

__metaclass__ = type

__all__ = [
    'ISourcePackageFormatSelection',
    'ISourcePackageFormatSelectionSet',
    ]

from zope.interface import (
    Attribute,
    Interface,
    )


class ISourcePackageFormatSelection(Interface):
    """A source package format allowed within a DistroSeries."""

    id = Attribute("ID")
    distroseries = Attribute("Target series")
    format = Attribute("Permitted source package format")


class ISourcePackageFormatSelectionSet(Interface):
    """Set manipulation tools for the SourcePackageFormatSelection table."""

    def getBySeriesAndFormat(distroseries, format):
        """Return the ISourcePackageFormatSelection for the given series and
        format."""

    def add(distroseries, format):
        """Allow the given source package format in the given series."""
