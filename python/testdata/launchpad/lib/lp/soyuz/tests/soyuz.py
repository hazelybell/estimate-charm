# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Helper functions/classes for Soyuz tests."""

__metaclass__ = type

__all__ = [
    'SoyuzTestHelper',
    ]

from zope.component import getUtility

from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.soyuz.enums import PackagePublishingStatus
from lp.soyuz.model.publishing import (
    BinaryPackagePublishingHistory,
    SourcePackagePublishingHistory,
    )
from lp.testing.sampledata import (
    BUILDD_ADMIN_USERNAME,
    UBUNTU_DISTRIBUTION_NAME,
    )


class SoyuzTestHelper:
    """Helper class to support easier tests in Soyuz component."""

    def __init__(self):
        self.ubuntu = getUtility(IDistributionSet)[UBUNTU_DISTRIBUTION_NAME]
        self.cprov_archive = getUtility(
            IPersonSet).getByName(BUILDD_ADMIN_USERNAME).archive

    @property
    def sample_publishing_data(self):
        """Return a list of triples as (status, archive, pocket).

        Returns the following triples (in this order):

         1. ubuntu/PRIMARY, PENDING, RELEASE;
         2. ubuntu/PRIMARY, PUBLISHED, RELEASE;
         3. ubuntu/PRIMARY, PENDING, UPDATES;
         4. ubuntu/PRIMARY, PUBLISHED, PROPOSED;
         5. ubuntu/cprov PPA, PENDING, RELEASE;
         6. ubuntu/cprov PPA, PUBLISHED, RELEASE;
         7. ubuntu/cprov PPA, PENDING, UPDATES;
         8. ubuntu/cprov PPA, PUBLISHED, PROPOSED;
        """
        return [
            (PackagePublishingStatus.PENDING, self.ubuntu.main_archive,
             PackagePublishingPocket.RELEASE),
            (PackagePublishingStatus.PUBLISHED, self.ubuntu.main_archive,
             PackagePublishingPocket.RELEASE),
            (PackagePublishingStatus.PENDING, self.ubuntu.main_archive,
             PackagePublishingPocket.UPDATES),
            (PackagePublishingStatus.PUBLISHED, self.ubuntu.main_archive,
             PackagePublishingPocket.PROPOSED),
            (PackagePublishingStatus.PENDING, self.cprov_archive,
             PackagePublishingPocket.RELEASE),
            (PackagePublishingStatus.PUBLISHED, self.cprov_archive,
             PackagePublishingPocket.RELEASE),
            (PackagePublishingStatus.PENDING, self.cprov_archive,
             PackagePublishingPocket.UPDATES),
            (PackagePublishingStatus.PUBLISHED, self.cprov_archive,
             PackagePublishingPocket.PROPOSED),
            ]

    def createPublishingForDistroSeries(self, sourcepackagerelease,
                                        distroseries):
        """Return a list of `SourcePackagePublishingHistory`.

        The publishing records are created according to the given
        `SourcePackageRelease` and `DistroSeries` for all
        (status, archive, pocket) returned from `sample_publishing_data`.
        """
        sample_pub = []
        for status, archive, pocket in self.sample_publishing_data:
            pub = SourcePackagePublishingHistory(
                sourcepackagerelease=sourcepackagerelease,
                sourcepackagename=sourcepackagerelease.sourcepackagename,
                distroseries=distroseries,
                component=sourcepackagerelease.component,
                section=sourcepackagerelease.section,
                status=status,
                archive=archive,
                pocket=pocket)
            # Flush the object changes into DB do guarantee stable database
            # ID order as expected in the callsites.
            sample_pub.append(pub)
        return sample_pub

    def createPublishingForDistroArchSeries(self, binarypackagerelease,
                                            distroarchseries):
        """Return a list of `BinaryPackagePublishingHistory`.

        The publishing records are created according to the given
        `BinaryPackageRelease` and `DistroArchSeries` for all
        (status, archive, pocket) returned from `sample_publishing_data`.
        """
        sample_pub = []
        for status, archive, pocket in self.sample_publishing_data:
            pub = BinaryPackagePublishingHistory(
                binarypackagerelease=binarypackagerelease,
                binarypackagename=binarypackagerelease.binarypackagename,
                distroarchseries=distroarchseries,
                component=binarypackagerelease.component,
                section=binarypackagerelease.section,
                priority=binarypackagerelease.priority,
                status=status,
                archive=archive,
                pocket=pocket)
            # Flush the object changes into DB do guarantee stable database
            # ID order as expected in the callsites.
            sample_pub.append(pub)
        return sample_pub

    def checkPubList(self, expected, given):
        """Check if the given publication list matches the expected one.

        Return True if the lists matches, otherwise False.
        """
        return [p.id for p in expected] == [r.id for r in given]
