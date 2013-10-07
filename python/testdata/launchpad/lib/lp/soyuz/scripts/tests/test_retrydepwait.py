# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import transaction
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.buildmaster.enums import BuildStatus
from lp.registry.interfaces.series import SeriesStatus
from lp.services.librarian.interfaces import ILibraryFileAliasSet
from lp.services.log.logger import DevNullLogger
from lp.soyuz.interfaces.publishing import PackagePublishingStatus
from lp.soyuz.scripts.retrydepwait import RetryDepwaitTunableLoop
from lp.testing import TestCaseWithFactory
from lp.testing.dbuser import dbuser
from lp.testing.fakemethod import FakeMethod
from lp.testing.layers import ZopelessDatabaseLayer
from lp.testing.script import run_script


class TestRetryDepwait(TestCaseWithFactory):

    layer = ZopelessDatabaseLayer

    def setUp(self):
        super(TestRetryDepwait, self).setUp()
        self.chroot = getUtility(ILibraryFileAliasSet)[1]
        self.build = removeSecurityProxy(
            self.factory.makeBinaryPackageBuild(
                status=BuildStatus.MANUALDEPWAIT))

        # Most tests want a no-op updateDependencies and a chroot.
        self.build.updateDependencies = FakeMethod()
        self.setChroot()

    def setChroot(self):
        self.build.distro_arch_series.addOrUpdateChroot(self.chroot)

    def unsetChroot(self):
        self.build.distro_arch_series.addOrUpdateChroot(None)

    def assertStatusAfterLoop(self, status, dry_run=False):
        with dbuser('retry_depwait'):
            RetryDepwaitTunableLoop(DevNullLogger(), dry_run).run()
        self.assertEqual(status, self.build.status)

    def test_ignores_when_dependencies_unsatisfied(self):
        # Builds with unsatisfied dependencies are not retried.
        self.build.updateStatus(
            BuildStatus.MANUALDEPWAIT,
            slave_status={'dependencies': u'something'})
        self.assertStatusAfterLoop(BuildStatus.MANUALDEPWAIT)
        self.assertEqual(1, self.build.updateDependencies.call_count)

        self.build.updateStatus(BuildStatus.MANUALDEPWAIT)
        self.assertStatusAfterLoop(BuildStatus.NEEDSBUILD)
        self.assertEqual(2, self.build.updateDependencies.call_count)

    def test_ignores_when_series_is_obsolete(self):
        # Builds for an obsolete series are not retried.
        self.build.distro_arch_series.distroseries.status = (
            SeriesStatus.OBSOLETE)
        self.assertStatusAfterLoop(BuildStatus.MANUALDEPWAIT)

        self.build.distro_arch_series.distroseries.status = (
            SeriesStatus.DEVELOPMENT)
        self.assertStatusAfterLoop(BuildStatus.NEEDSBUILD)

    def test_ignores_when_chroot_is_missing(self):
        # Builds without a chroot are not retried.
        self.unsetChroot()
        self.assertStatusAfterLoop(BuildStatus.MANUALDEPWAIT)

        self.setChroot()
        self.assertStatusAfterLoop(BuildStatus.NEEDSBUILD)

    def test_dry_run_aborts(self):
        # Changes are thrown away when in dry run mode.
        self.assertStatusAfterLoop(BuildStatus.MANUALDEPWAIT, dry_run=True)
        self.assertStatusAfterLoop(BuildStatus.NEEDSBUILD, dry_run=False)

    def test_only_retries_depwait(self):
        # Builds in non-depwait statuses aren't retried.
        self.build.updateStatus(BuildStatus.FAILEDTOBUILD)
        self.assertStatusAfterLoop(BuildStatus.FAILEDTOBUILD)

        self.build.updateStatus(BuildStatus.MANUALDEPWAIT)
        self.assertStatusAfterLoop(BuildStatus.NEEDSBUILD)

    def runScript(self):
        transaction.commit()
        (ret, out, err) = run_script('cronscripts/buildd-retry-depwait.py')
        self.assertEqual(0, ret)
        transaction.commit()

    def test_script(self):
        # Setting up a real depwait scenario and running the script
        # works.
        self.assertEqual(BuildStatus.MANUALDEPWAIT, self.build.status)
        bpn = self.factory.getUniqueUnicode()
        self.build.updateStatus(
            BuildStatus.MANUALDEPWAIT, slave_status={'dependencies': bpn})

        # With no binary to satisfy the dependency, running the script
        # does nothing.
        self.runScript()
        self.assertEqual(BuildStatus.MANUALDEPWAIT, self.build.status)

        # If we create a matching binary and rerun, the script retries
        # the build.
        self.factory.makeBinaryPackagePublishingHistory(
            archive=self.build.archive, pocket=self.build.pocket,
            distroarchseries=self.build.distro_arch_series,
            status=PackagePublishingStatus.PUBLISHED, binarypackagename=bpn)
        self.runScript()
        self.assertEqual(BuildStatus.NEEDSBUILD, self.build.status)
