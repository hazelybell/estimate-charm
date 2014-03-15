# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Classes to represent binary package releases in a
distributionarchitecture release."""

__metaclass__ = type

__all__ = [
    'DistroArchSeriesBinaryPackageRelease',
    ]

from zope.interface import implements

from lp.services.database.sqlbase import sqlvalues
from lp.soyuz.interfaces.distroarchseriesbinarypackagerelease import (
    IDistroArchSeriesBinaryPackageRelease,
    )
from lp.soyuz.interfaces.publishing import active_publishing_status
from lp.soyuz.model.distributionsourcepackagerelease import (
    DistributionSourcePackageRelease,
    )
from lp.soyuz.model.publishing import BinaryPackagePublishingHistory


class DistroArchSeriesBinaryPackageRelease:

    implements(IDistroArchSeriesBinaryPackageRelease)

    def __init__(self, distroarchseries, binarypackagerelease):
        self.distroarchseries = distroarchseries
        self.binarypackagerelease = binarypackagerelease

    @property
    def name(self):
        """See `IDistroArchSeriesBinaryPackageRelease`."""
        return self.binarypackagerelease.binarypackagename.name

    @property
    def version(self):
        """See `IDistroArchSeriesBinaryPackageRelease`."""
        return self.binarypackagerelease.version

    @property
    def distroseries(self):
        """See `IDistroArchSeriesBinaryPackageRelease`."""
        return self.distroarchseries.distroseries

    @property
    def distribution(self):
        """See `IDistroArchSeriesBinaryPackageRelease`."""
        return self.distroarchseries.distroseries.distribution

    @property
    def displayname(self):
        """See `IDistroArchSeriesBinaryPackageRelease`."""
        return '%s %s' % (self.name, self.version)

    @property
    def title(self):
        """See `IDistroArchSeriesBinaryPackageRelease`."""
        return '%s %s (%s binary) in %s %s' % (
            self.name, self.version, self.distroarchseries.architecturetag,
            self.distribution.name, self.distroseries.name)

    @property
    def distributionsourcepackagerelease(self):
        """See `IDistroArchSeriesBinaryPackageRelease`."""
        return DistributionSourcePackageRelease(
            self.distribution,
            self.build.source_package_release)

    @property
    def distroarchseriesbinarypackage(self):
        """See `IDistroArchSeriesBinaryPackage`."""
        return self.distroarchseries.getBinaryPackage(
            self.binarypackagename)

    # XXX: kiko, 2006-02-01: I'd like to rename this to
    # current_published_publishing_record, because that's what it
    # returns, but I don't want to do that right now.
    @property
    def current_publishing_record(self):
        """See `IDistroArchSeriesBinaryPackageRelease`."""
        return self._latest_publishing_record(status=active_publishing_status)

# XXX cprov 20071026: heavy queries should be moved near to the related
# content classes in order to be better maintained. In this specific case
# the publishing queries should live in publishing.py.
    def _latest_publishing_record(self, status=None):
        query = """
            binarypackagerelease = %s AND
            distroarchseries = %s AND
            archive IN %s
        """ % sqlvalues(self.binarypackagerelease, self.distroarchseries,
                        self.distribution.all_distro_archive_ids)

        if status is not None:
            if not isinstance(status, (tuple, list)):
                status = [status]
            query += " AND status IN %s" % sqlvalues(status)

        return BinaryPackagePublishingHistory.selectFirst(
            query, orderBy=['-datecreated', '-id'])

    @property
    def publishing_history(self):
        """See `IDistroArchSeriesBinaryPackage`."""
        return BinaryPackagePublishingHistory.select("""
            distroarchseries = %s AND
            archive IN %s AND
            binarypackagerelease = %s
            """ % sqlvalues(
                    self.distroarchseries,
                    self.distribution.all_distro_archive_ids,
                    self.binarypackagerelease),
            orderBy=['-datecreated', '-id'])

    @property
    def pocket(self):
        """See `IDistroArchSeriesBinaryPackageRelease`."""
        pub = self._latest_publishing_record()
        if pub is None:
            return None
        return pub.pocket

    @property
    def status(self):
        """See `IDistroArchSeriesBinaryPackageRelease`."""
        pub = self._latest_publishing_record()
        if pub is None:
            return None
        return pub.status

    @property
    def section(self):
        """See `IDistroArchSeriesBinaryPackageRelease`."""
        pub = self._latest_publishing_record()
        if pub is None:
            return None
        return pub.section

    @property
    def component(self):
        """See `IDistroArchSeriesBinaryPackageRelease`."""
        pub = self._latest_publishing_record()
        if pub is None:
            return None
        return pub.component

    @property
    def priority(self):
        """See `IDistroArchSeriesBinaryPackageRelease`."""
        pub = self._latest_publishing_record()
        if pub is None:
            return None
        return pub.priority

    @property
    def phased_update_percentage(self):
        """See `IDistroArchSeriesBinaryPackageRelease`."""
        pub = self._latest_publishing_record()
        if pub is None:
            return None
        return pub.phased_update_percentage

    # map the BinaryPackageRelease attributes up to this class so it
    # responds to the same interface

    @property
    def binarypackagename(self):
        """See `IBinaryPackageRelease`."""
        return self.binarypackagerelease.binarypackagename

    @property
    def summary(self):
        """See `IBinaryPackageRelease`."""
        return self.binarypackagerelease.summary

    @property
    def description(self):
        """See `IBinaryPackageRelease`."""
        return self.binarypackagerelease.description

    @property
    def build(self):
        """See `IBinaryPackageRelease`."""
        return self.binarypackagerelease.build

    @property
    def binpackageformat(self):
        """See `IPackageRelease`."""
        return self.binarypackagerelease.binpackageformat

    @property
    def shlibdeps(self):
        """See `IBinaryPackageRelease`."""
        return self.binarypackagerelease.shlibdeps

    @property
    def depends(self):
        """See `IBinaryPackageRelease`."""
        return self.binarypackagerelease.depends

    @property
    def recommends(self):
        """See `IBinaryPackageRelease`."""
        return self.binarypackagerelease.recommends

    @property
    def replaces(self):
        """See `IBinaryPackageRelease`."""
        return self.binarypackagerelease.replaces

    @property
    def conflicts(self):
        """See `IBinaryPackageRelease`."""
        return self.binarypackagerelease.conflicts

    @property
    def provides(self):
        """See `IBinaryPackageRelease`."""
        return self.binarypackagerelease.provides

    @property
    def suggests(self):
        """See `IBinaryPackageRelease`."""
        return self.binarypackagerelease.suggests

    @property
    def essential(self):
        """See `IBinaryPackageRelease`."""
        return self.binarypackagerelease.essential

    @property
    def installedsize(self):
        """See `IBinaryPackageRelease`."""
        return self.binarypackagerelease.installedsize

    @property
    def architecturespecific(self):
        """See `IBinaryPackageRelease`."""
        return self.binarypackagerelease.architecturespecific

    @property
    def datecreated(self):
        """See `IBinaryPackageRelease`."""
        return self.binarypackagerelease.datecreated

    @property
    def files(self):
        """See `IBinaryPackageRelease`."""
        return self.binarypackagerelease.files
