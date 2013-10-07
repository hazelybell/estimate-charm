# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test BinaryPackageRelease."""

__metaclass__ = type

from lp.soyuz.enums import BinaryPackageFormat
from lp.soyuz.interfaces.binarypackagerelease import IBinaryPackageRelease
from lp.soyuz.interfaces.publishing import PackagePublishingPriority
from lp.testing import TestCaseWithFactory
from lp.testing.layers import LaunchpadFunctionalLayer


class TestBinaryPackageRelease(TestCaseWithFactory):
    """Tests for BinaryPackageRelease."""

    layer = LaunchpadFunctionalLayer

    def test_provides(self):
        build = self.factory.makeBinaryPackageBuild()
        release = build.createBinaryPackageRelease(
                binarypackagename=self.factory.makeBinaryPackageName(),
                version="0.1", summary="My package",
                description="My description",
                binpackageformat=BinaryPackageFormat.DEB,
                component=self.factory.makeComponent("main"),
                section=self.factory.makeSection("net"),
                priority=PackagePublishingPriority.OPTIONAL,
                installedsize=0, architecturespecific=False)
        self.assertProvides(release, IBinaryPackageRelease)

    def test_user_defined_fields(self):
        build = self.factory.makeBinaryPackageBuild()
        release = build.createBinaryPackageRelease(
                binarypackagename=self.factory.makeBinaryPackageName(),
                version="0.1", summary="My package",
                description="My description",
                binpackageformat=BinaryPackageFormat.DEB,
                component=self.factory.makeComponent("main"),
                section=self.factory.makeSection("net"),
                priority=PackagePublishingPriority.OPTIONAL,
                installedsize=0, architecturespecific=False,
                user_defined_fields=[
                    ("Python-Version", ">= 2.4"),
                    ("Other", "Bla")])
        self.assertEquals([
            ["Python-Version", ">= 2.4"],
            ["Other", "Bla"]], release.user_defined_fields)

    def test_homepage_default(self):
        # By default, no homepage is set.
        bpr = self.factory.makeBinaryPackageRelease()
        self.assertEquals(None, bpr.homepage)

    def test_homepage_empty(self):
        # The homepage field can be empty.
        bpr = self.factory.makeBinaryPackageRelease(homepage="")
        self.assertEquals("", bpr.homepage)

    def test_homepage_set_invalid(self):
        # As the homepage field is inherited from the .deb, the URL
        # does not have to be valid.
        bpr = self.factory.makeBinaryPackageRelease(homepage="<invalid<url")
        self.assertEquals("<invalid<url", bpr.homepage)
