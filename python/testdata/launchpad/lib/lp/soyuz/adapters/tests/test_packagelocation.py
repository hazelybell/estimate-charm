# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test PackageLocation class."""

from zope.component import getUtility

from lp.soyuz.adapters.packagelocation import (
    build_package_location,
    PackageLocationError,
    )
from lp.soyuz.enums import ArchivePurpose
from lp.soyuz.interfaces.component import IComponentSet
from lp.testing import TestCaseWithFactory
from lp.testing.factory import remove_security_proxy_and_shout_at_engineer
from lp.testing.layers import LaunchpadZopelessLayer


class TestPackageLocation(TestCaseWithFactory):
    """Test the `PackageLocation` class."""
    layer = LaunchpadZopelessLayer

    def getPackageLocation(self, distribution_name='ubuntu', suite=None,
                           purpose=None, person_name=None,
                           archive_name=None, packageset_names=None):
        """Use a helper method to setup a `PackageLocation` object."""
        return build_package_location(
            distribution_name, suite, purpose, person_name, archive_name,
            packageset_names=packageset_names)

    def testSetupLocationForCOPY(self):
        """`PackageLocation` for COPY archives."""
        # First create a copy archive for the default Ubuntu primary
        ubuntu = self.getPackageLocation().distribution

        returned_location = self.factory.makeCopyArchiveLocation(
            distribution=ubuntu, name='now-comes-the-mystery',
            owner=self.factory.makePerson(name='mysteryman'))
        copy_archive = remove_security_proxy_and_shout_at_engineer(
            returned_location).archive

        # Now use the created copy archive to test the build_package_location
        # helper (called via getPackageLocation):
        location = self.getPackageLocation(purpose=ArchivePurpose.COPY,
                                           archive_name=copy_archive.name)

        self.assertEqual(location.distribution.name, 'ubuntu')
        self.assertEqual(location.distroseries.name, 'hoary')
        self.assertEqual(location.pocket.name, 'RELEASE')
        self.assertEqual(location.archive.displayname,
                         'Copy archive now-comes-the-mystery for Mysteryman')
        self.assertEqual([], location.packagesets)

    def testSetupLocationForPRIMARY(self):
        """`PackageLocation` for PRIMARY archives."""
        location = self.getPackageLocation()
        self.assertEqual(location.distribution.name, 'ubuntu')
        self.assertEqual(location.distroseries.name, 'hoary')
        self.assertEqual(location.pocket.name, 'RELEASE')
        self.assertEqual(location.archive.displayname,
                         'Primary Archive for Ubuntu Linux')
        self.assertEqual([], location.packagesets)

    def testSetupLocationForPPA(self):
        """`PackageLocation` for PPA archives."""
        location = self.getPackageLocation(purpose=ArchivePurpose.PPA,
                                           person_name='cprov',
                                           archive_name="ppa")
        self.assertEqual(location.distribution.name, 'ubuntu')
        self.assertEqual(location.distroseries.name, 'hoary')
        self.assertEqual(location.pocket.name, 'RELEASE')
        self.assertEqual(location.archive.displayname,
                         'PPA for Celso Providelo')
        self.assertEqual([], location.packagesets)

    def testSetupLocationForPARTNER(self):
        """`PackageLocation` for PARTNER archives."""
        location = self.getPackageLocation(purpose=ArchivePurpose.PARTNER)
        self.assertEqual(location.distribution.name, 'ubuntu')
        self.assertEqual(location.distroseries.name, 'hoary')
        self.assertEqual(location.pocket.name, 'RELEASE')
        self.assertEqual(location.archive.displayname,
                         'Partner Archive for Ubuntu Linux')
        self.assertEqual([], location.packagesets)

    def testSetupLocationWithPackagesets(self):
        packageset_name1 = u"foo-packageset"
        packageset_name2 = u"bar-packageset"
        packageset1 = self.factory.makePackageset(name=packageset_name1)
        packageset2 = self.factory.makePackageset(name=packageset_name2)
        location = self.getPackageLocation(
            packageset_names=[packageset_name1, packageset_name2])
        self.assertEqual([packageset1, packageset2], location.packagesets)

    def testSetupLocationUnknownDistribution(self):
        """`PackageLocationError` is raised on unknown distribution."""
        self.assertRaises(
            PackageLocationError,
            self.getPackageLocation,
            distribution_name='beeblebrox')

    def testSetupLocationUnknownSuite(self):
        """`PackageLocationError` is raised on unknown suite."""
        self.assertRaises(
            PackageLocationError,
            self.getPackageLocation,
            suite='beeblebrox')

    def testSetupLocationUnknownPerson(self):
        """`PackageLocationError` is raised on unknown person."""
        self.assertRaises(
            PackageLocationError,
            self.getPackageLocation,
            purpose=ArchivePurpose.PPA,
            person_name='beeblebrox',
            archive_name="ppa")

    def testSetupLocationUnknownPPA(self):
        """`PackageLocationError` is raised on unknown PPA."""
        self.assertRaises(
            PackageLocationError,
            self.getPackageLocation,
            purpose=ArchivePurpose.PPA,
            person_name='kiko',
            archive_name="ppa")

    def test_build_package_location_when_partner_missing(self):
        """`PackageLocationError` is raised when PARTNER does not exist."""
        self.assertRaises(
            PackageLocationError,
            self.getPackageLocation,
            distribution_name='debian',
            purpose=ArchivePurpose.PARTNER)

    def test_build_package_location_when_packageset_unknown(self):
        """`PackageLocationError` is raised on unknown packageset."""
        self.assertRaises(
            PackageLocationError,
            self.getPackageLocation,
            distribution_name='debian',
            packageset_names=[u"unknown"])

    def test_build_package_location_when_one_packageset_unknown(self):
        """Test that with one of two packagesets unknown."""
        packageset_name = u"foo-packageset"
        self.factory.makePackageset(name=packageset_name)
        self.assertRaises(
            PackageLocationError,
            self.getPackageLocation,
            distribution_name='debian',
            packageset_names=[packageset_name, u"unknown"])

    def testSetupLocationPPANotMatchingDistribution(self):
        """`PackageLocationError` is raised when PPA does not match the
        distribution."""
        self.assertRaises(
            PackageLocationError,
            self.getPackageLocation,
            distribution_name='ubuntutest',
            purpose=ArchivePurpose.PPA,
            person_name='cprov',
            archive_name="ppa")

    def testComparison(self):
        """Check if PackageLocation objects can be compared."""
        location_ubuntu_hoary = self.getPackageLocation()
        location_ubuntu_hoary_again = self.getPackageLocation()
        self.assertEqual(location_ubuntu_hoary, location_ubuntu_hoary_again)

        self.assertTrue(location_ubuntu_hoary.component is None)
        self.assertTrue(location_ubuntu_hoary_again.component is None)

        universe = getUtility(IComponentSet)['universe']
        restricted = getUtility(IComponentSet)['restricted']

        location_ubuntu_hoary.component = universe
        self.assertNotEqual(
            location_ubuntu_hoary, location_ubuntu_hoary_again)

        location_ubuntu_hoary_again.component = universe
        self.assertEqual(location_ubuntu_hoary, location_ubuntu_hoary_again)

        location_ubuntu_hoary.component = restricted
        self.assertNotEqual(
            location_ubuntu_hoary, location_ubuntu_hoary_again)

        location_ubuntu_warty_security = self.getPackageLocation(
            suite='warty-security')
        self.assertNotEqual(location_ubuntu_hoary,
                            location_ubuntu_warty_security)

        location_ubuntutest = self.getPackageLocation(
            distribution_name='ubuntutest')
        self.assertNotEqual(location_ubuntu_hoary, location_ubuntutest)

        location_cprov_ppa = self.getPackageLocation(
            distribution_name='ubuntu', purpose=ArchivePurpose.PPA,
            person_name='cprov', archive_name="ppa")
        self.assertNotEqual(location_cprov_ppa, location_ubuntutest)

        location_ubuntu_partner = self.getPackageLocation(
            distribution_name='ubuntu', purpose=ArchivePurpose.PARTNER)
        self.assertNotEqual(location_ubuntu_partner, location_cprov_ppa)

    def testComparePackagesets(self):
        location_ubuntu_hoary = self.getPackageLocation()
        location_ubuntu_hoary_again = self.getPackageLocation()
        packageset = self.factory.makePackageset()
        location_ubuntu_hoary.packagesets = [packageset]
        self.assertNotEqual(
            location_ubuntu_hoary, location_ubuntu_hoary_again)

        location_ubuntu_hoary_again.packagesets = [packageset]
        self.assertEqual(
            location_ubuntu_hoary, location_ubuntu_hoary_again)

    def testRepresentation(self):
        """Check if PackageLocation is represented correctly."""
        location_ubuntu_hoary = self.getPackageLocation()
        self.assertEqual(str(location_ubuntu_hoary),
                         'Primary Archive for Ubuntu Linux: hoary-RELEASE')

        universe = getUtility(IComponentSet)['universe']
        location_ubuntu_hoary.component = universe

        self.assertEqual(
            str(location_ubuntu_hoary),
            'Primary Archive for Ubuntu Linux: hoary-RELEASE (universe)')

        location_ubuntu_warty_security = self.getPackageLocation(
            suite='warty-security')
        self.assertEqual(str(location_ubuntu_warty_security),
                         'Primary Archive for Ubuntu Linux: warty-SECURITY')

        location_ubuntutest = self.getPackageLocation(
            distribution_name='ubuntutest')
        self.assertEqual(
            str(location_ubuntutest),
            'Primary Archive for Ubuntu Test: hoary-test-RELEASE')

        location_cprov_ppa = self.getPackageLocation(
            distribution_name='ubuntu', purpose=ArchivePurpose.PPA,
            person_name='cprov', archive_name="ppa")
        self.assertEqual(
            str(location_cprov_ppa),
            'cprov: hoary-RELEASE')

        location_ubuntu_partner = self.getPackageLocation(
            distribution_name='ubuntu', purpose=ArchivePurpose.PARTNER)
        self.assertEqual(
            str(location_ubuntu_partner),
            'Partner Archive for Ubuntu Linux: hoary-RELEASE')

        self.factory.makePackageset(name=u"foo-packageset")
        location_ubuntu_packageset = self.getPackageLocation(
            packageset_names=[u"foo-packageset"])
        self.assertEqual(
            str(location_ubuntu_packageset),
            'Primary Archive for Ubuntu Linux: '
            'hoary-RELEASE [foo-packageset]')
