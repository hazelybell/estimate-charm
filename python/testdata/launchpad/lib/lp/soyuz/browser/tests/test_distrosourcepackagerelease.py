# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for DistroSourcePackageRelease pages."""

__metaclass__ = type

from zope.security.proxy import removeSecurityProxy

from lp.soyuz.model.distributionsourcepackagerelease import (
    DistributionSourcePackageRelease,
    )
from lp.soyuz.tests.test_publishing import SoyuzTestPublisher
from lp.testing import TestCaseWithFactory
from lp.testing.factory import remove_security_proxy_and_shout_at_engineer
from lp.testing.layers import LaunchpadFunctionalLayer
from lp.testing.views import create_initialized_view


class TestDistroSourcePackageReleaseFiles(TestCaseWithFactory):
    # Distro Source package release files should be rendered correctly.

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestDistroSourcePackageReleaseFiles, self).setUp()
        # The package must be published for the page to render.
        stp = SoyuzTestPublisher()
        distroseries = stp.setUpDefaultDistroSeries()
        naked_distroseries = remove_security_proxy_and_shout_at_engineer(
            distroseries)
        # XXX Abel Deuring, 2010-07-21, bug 608240. This is scary. But
        # if we use distroseries.distribution instead,
        # test_spr_files_deleted() and test_spr_files_one() fail.
        distro = naked_distroseries.distribution
        source_package_release = stp.getPubSource().sourcepackagerelease
        self.dspr = DistributionSourcePackageRelease(
            distro, source_package_release)
        self.library_file = self.factory.makeLibraryFileAlias(
            filename='test_file.dsc', content='0123456789')
        source_package_release.addFile(self.library_file)

    def test_spr_files_one(self):
        # The snippet links to the file when present.
        view = create_initialized_view(self.dspr, "+index")
        html = view.__call__()
        self.failUnless('test_file.dsc' in html)

    def test_spr_files_deleted(self):
        # The snippet handles deleted files too.
        removeSecurityProxy(self.library_file).content = None
        view = create_initialized_view(self.dspr, "+index")
        html = view.__call__()
        self.failUnless('test_file.dsc (deleted)' in html)
