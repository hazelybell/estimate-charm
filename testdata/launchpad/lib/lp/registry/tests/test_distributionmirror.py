# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

import transaction
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.interfaces.distributionmirror import (
    IDistributionMirrorSet,
    MirrorContent,
    MirrorFreshness,
    )
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.model.distributionmirror import DistributionMirror
from lp.services.database.sqlbase import flush_database_updates
from lp.services.mail import stub
from lp.services.worlddata.interfaces.country import ICountrySet
from lp.testing import (
    login,
    login_as,
    TestCase,
    TestCaseWithFactory,
    )
from lp.testing.layers import LaunchpadFunctionalLayer


class TestDistributionMirror(TestCaseWithFactory):
    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestDistributionMirror, self).setUp()
        login('test@canonical.com')
        mirrorset = getUtility(IDistributionMirrorSet)
        self.cdimage_mirror = mirrorset.getByName('releases-mirror')
        self.archive_mirror = mirrorset.getByName('archive-mirror')
        self.hoary = getUtility(IDistributionSet)['ubuntu']['hoary']
        self.hoary_i386 = self.hoary['i386']

    def _create_source_mirror(self, distroseries, pocket, component,
                              freshness):
        source_mirror1 = self.archive_mirror.ensureMirrorDistroSeriesSource(
            distroseries, pocket, component)
        removeSecurityProxy(source_mirror1).freshness = freshness

    def _create_bin_mirror(self, archseries, pocket, component, freshness):
        bin_mirror = self.archive_mirror.ensureMirrorDistroArchSeries(
            archseries, pocket, component)
        removeSecurityProxy(bin_mirror).freshness = freshness

    def test_archive_mirror_without_content_should_be_disabled(self):
        self.failUnless(self.archive_mirror.shouldDisable())

    def test_archive_mirror_with_any_content_should_not_be_disabled(self):
        self._create_source_mirror(
            self.hoary, PackagePublishingPocket.RELEASE,
            self.hoary.components[0], MirrorFreshness.UP)
        flush_database_updates()
        self.failIf(self.archive_mirror.shouldDisable())

    def test_cdimage_mirror_not_missing_content_should_not_be_disabled(self):
        expected_file_count = 1
        self.cdimage_mirror.ensureMirrorCDImageSeries(
            self.hoary, flavour='ubuntu')
        self.failIf(self.cdimage_mirror.shouldDisable(expected_file_count))

    def test_cdimage_mirror_missing_content_should_be_disabled(self):
        expected_file_count = 1
        self.failUnless(
            self.cdimage_mirror.shouldDisable(expected_file_count))

    def test_delete_all_mirror_cdimage_series(self):
        self.cdimage_mirror.ensureMirrorCDImageSeries(
            self.hoary, flavour='ubuntu')
        self.cdimage_mirror.ensureMirrorCDImageSeries(
            self.hoary, flavour='edubuntu')
        self.failUnlessEqual(
            self.cdimage_mirror.cdimage_series.count(), 2)
        self.cdimage_mirror.deleteAllMirrorCDImageSeries()
        self.failUnlessEqual(
            self.cdimage_mirror.cdimage_series.count(), 0)

    def test_archive_mirror_without_content_freshness(self):
        self.failIf(self.archive_mirror.source_series or
                    self.archive_mirror.arch_series)
        self.failUnlessEqual(
            self.archive_mirror.getOverallFreshness(),
            MirrorFreshness.UNKNOWN)

    def test_source_mirror_freshness_property(self):
        self._create_source_mirror(
            self.hoary, PackagePublishingPocket.RELEASE,
            self.hoary.components[0], MirrorFreshness.UP)
        self._create_source_mirror(
            self.hoary, PackagePublishingPocket.RELEASE,
            self.hoary.components[1], MirrorFreshness.TWODAYSBEHIND)
        flush_database_updates()
        self.failUnlessEqual(
            removeSecurityProxy(self.archive_mirror).source_mirror_freshness,
            MirrorFreshness.TWODAYSBEHIND)

    def test_arch_mirror_freshness_property(self):
        self._create_bin_mirror(
            self.hoary_i386, PackagePublishingPocket.RELEASE,
            self.hoary.components[0], MirrorFreshness.UP)
        self._create_bin_mirror(
            self.hoary_i386, PackagePublishingPocket.RELEASE,
            self.hoary.components[1], MirrorFreshness.ONEHOURBEHIND)
        flush_database_updates()
        self.failUnlessEqual(
            removeSecurityProxy(self.archive_mirror).arch_mirror_freshness,
            MirrorFreshness.ONEHOURBEHIND)

    def test_archive_mirror_with_source_content_freshness(self):
        self._create_source_mirror(
            self.hoary, PackagePublishingPocket.RELEASE,
            self.hoary.components[0], MirrorFreshness.UP)
        self._create_source_mirror(
            self.hoary, PackagePublishingPocket.RELEASE,
            self.hoary.components[1], MirrorFreshness.TWODAYSBEHIND)
        flush_database_updates()
        self.failUnlessEqual(
            self.archive_mirror.getOverallFreshness(),
            MirrorFreshness.TWODAYSBEHIND)

    def test_archive_mirror_with_binary_content_freshness(self):
        self._create_bin_mirror(
            self.hoary_i386, PackagePublishingPocket.RELEASE,
            self.hoary.components[0], MirrorFreshness.UP)
        self._create_bin_mirror(
            self.hoary_i386, PackagePublishingPocket.RELEASE,
            self.hoary.components[1], MirrorFreshness.ONEHOURBEHIND)
        flush_database_updates()
        self.failUnlessEqual(
            self.archive_mirror.getOverallFreshness(),
            MirrorFreshness.ONEHOURBEHIND)

    def test_archive_mirror_with_binary_and_source_content_freshness(self):
        self._create_bin_mirror(
            self.hoary_i386, PackagePublishingPocket.RELEASE,
            self.hoary.components[0], MirrorFreshness.UP)
        self._create_bin_mirror(
            self.hoary_i386, PackagePublishingPocket.RELEASE,
            self.hoary.components[1], MirrorFreshness.ONEHOURBEHIND)

        self._create_source_mirror(
            self.hoary, PackagePublishingPocket.RELEASE,
            self.hoary.components[0], MirrorFreshness.UP)
        self._create_source_mirror(
            self.hoary, PackagePublishingPocket.RELEASE,
            self.hoary.components[1], MirrorFreshness.TWODAYSBEHIND)
        flush_database_updates()

        self.failUnlessEqual(
            self.archive_mirror.getOverallFreshness(),
            MirrorFreshness.TWODAYSBEHIND)

    def test_disabling_mirror_and_notifying_owner(self):
        login('karl@canonical.com')

        mirror = self.cdimage_mirror
        # If a mirror has been probed only once, the owner will always be
        # notified when it's disabled --it doesn't matter whether it was
        # previously enabled or disabled.
        self.factory.makeMirrorProbeRecord(mirror)
        self.failUnless(mirror.enabled)
        log = 'Got a 404 on http://foo/baz'
        mirror.disable(notify_owner=True, log=log)
        # A notification was sent to the owner and other to the mirror admins.
        transaction.commit()
        self.failUnlessEqual(len(stub.test_emails), 2)
        stub.test_emails = []

        mirror.disable(notify_owner=True, log=log)
        # Again, a notification was sent to the owner and other to the mirror
        # admins.
        transaction.commit()
        self.failUnlessEqual(len(stub.test_emails), 2)
        stub.test_emails = []

        # For mirrors that have been probed more than once, we'll only notify
        # the owner if the mirror was previously enabled.
        self.factory.makeMirrorProbeRecord(mirror)
        mirror.enabled = True
        mirror.disable(notify_owner=True, log=log)
        # A notification was sent to the owner and other to the mirror admins.
        transaction.commit()
        self.failUnlessEqual(len(stub.test_emails), 2)
        stub.test_emails = []

        # We can always disable notifications to the owner by passing
        # notify_owner=False to mirror.disable().
        mirror.enabled = True
        mirror.disable(notify_owner=False, log=log)
        transaction.commit()
        self.failUnlessEqual(len(stub.test_emails), 1)
        stub.test_emails = []

        mirror.enabled = False
        mirror.disable(notify_owner=True, log=log)
        # No notifications were sent this time
        transaction.commit()
        self.failUnlessEqual(len(stub.test_emails), 0)
        stub.test_emails = []

    def test_no_email_sent_to_uncontactable_owner(self):
        # If the owner has no contact address, only the mirror admins are
        # notified.
        mirror = self.cdimage_mirror
        login_as(mirror.owner)
        # Deactivate the mirror owner to remove the contact address.
        mirror.owner.deactivate(comment="I hate mirror spam.")
        login_as(mirror.distribution.mirror_admin)
        # Clear out notifications about the new team member.
        transaction.commit()
        stub.test_emails = []

        # Disabling the mirror results in a single notification to the
        # mirror admins.
        self.factory.makeMirrorProbeRecord(mirror)
        mirror.disable(notify_owner=True, log="It broke.")
        transaction.commit()
        self.failUnlessEqual(len(stub.test_emails), 1)


class TestDistributionMirrorSet(TestCase):
    layer = LaunchpadFunctionalLayer

    def test_getBestMirrorsForCountry_randomizes_results(self):
        """Make sure getBestMirrorsForCountry() randomizes its results."""
        def my_select(class_, query, *args, **kw):
            """Fake function with the same signature of SQLBase.select().

            This function ensures the orderBy argument given to it contains
            the 'random' string in its first item.
            """
            self.failUnlessEqual(kw['orderBy'][0].name, 'random')
            return [1, 2, 3]

        orig_select = DistributionMirror.select
        DistributionMirror.select = classmethod(my_select)
        try:
            login('foo.bar@canonical.com')
            getUtility(IDistributionMirrorSet).getBestMirrorsForCountry(
                None, MirrorContent.ARCHIVE)
        finally:
            DistributionMirror.select = orig_select

    def test_getBestMirrorsForCountry_appends_main_repo_to_the_end(self):
        """Make sure the main mirror is appended to the list of mirrors for a
        given country.
        """
        login('foo.bar@canonical.com')
        france = getUtility(ICountrySet)['FR']
        main_mirror = getUtility(ILaunchpadCelebrities).ubuntu_archive_mirror
        mirrors = getUtility(IDistributionMirrorSet).getBestMirrorsForCountry(
            france, MirrorContent.ARCHIVE)
        self.failUnless(len(mirrors) > 1, "Not enough mirrors")
        self.failUnlessEqual(main_mirror, mirrors[-1])

        main_mirror = getUtility(ILaunchpadCelebrities).ubuntu_cdimage_mirror
        mirrors = getUtility(IDistributionMirrorSet).getBestMirrorsForCountry(
            france, MirrorContent.RELEASE)
        self.failUnless(len(mirrors) > 1, "Not enough mirrors")
        self.failUnlessEqual(main_mirror, mirrors[-1])
