# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from datetime import timedelta
from textwrap import dedent

from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.browser.tales import DurationFormatterAPI
from lp.archivepublisher.utils import get_ppa_reference
from lp.buildmaster.enums import BuildStatus
from lp.registry.interfaces.person import IPersonSet
from lp.services.config import config
from lp.services.webapp import canonical_url
from lp.soyuz.enums import ArchivePurpose
from lp.soyuz.interfaces.publishing import PackagePublishingPocket
from lp.soyuz.tests.test_publishing import SoyuzTestPublisher
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import LaunchpadFunctionalLayer
from lp.testing.mail_helpers import pop_notifications
from lp.testing.sampledata import ADMIN_EMAIL


class TestBuildNotify(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestBuildNotify, self).setUp()
        self.admin = getUtility(IPersonSet).getByEmail(ADMIN_EMAIL)
        # Create all of the items we need to create builds
        self.processor = self.factory.makeProcessor()
        self.distroseries = self.factory.makeDistroSeries()
        self.das = self.factory.makeDistroArchSeries(
            distroseries=self.distroseries, processor=self.processor,
            supports_virtualized=True)
        self.creator = self.factory.makePerson(email='test@example.com')
        self.gpgkey = self.factory.makeGPGKey(owner=self.creator)
        self.archive = self.factory.makeArchive(
            distribution=self.distroseries.distribution,
            purpose=ArchivePurpose.PRIMARY)
        self.ppa = self.factory.makeArchive()
        buildd_admins = getUtility(IPersonSet).getByName(
            'launchpad-buildd-admins')
        self.buildd_admins_email = []
        with person_logged_in(self.admin):
            self.publisher = SoyuzTestPublisher()
            self.publisher.prepareBreezyAutotest()
            self.distroseries.nominatedarchindep = self.das
            self.publisher.addFakeChroots(distroseries=self.distroseries)
            self.builder = self.factory.makeBuilder(processor=self.processor)
            for member in buildd_admins.activemembers:
                self.buildd_admins_email.append(member.preferredemail.email)
        self.builds = []

    def create_builds(self, archive):
        for status in BuildStatus.items:
            spph = self.publisher.getPubSource(
                sourcename=self.factory.getUniqueString(),
                version="%s.%s" % (
                    self.factory.getUniqueInteger(), status.value),
                distroseries=self.distroseries, architecturehintlist='any',
                creator=self.creator, archive=archive)
            spph.sourcepackagerelease.dscsigningkey = self.gpgkey
            [build] = spph.createMissingBuilds()
            with person_logged_in(self.admin):
                build.updateStatus(BuildStatus.BUILDING, builder=self.builder)
                build.updateStatus(status,
                    date_finished=(
                        build.date_started + timedelta(
                            minutes=5 * (status.value + 1))))
                if status != BuildStatus.BUILDING:
                    build.buildqueue_record.destroySelf()
                else:
                    build.buildqueue_record.builder = self.builder
            self.builds.append(build)

    def _assert_mail_is_correct(self, build, notification, ppa=False):
        # Assert that the mail sent (which is in notification), matches
        # the data from the build
        self.assertEquals('test@example.com',
            notification['X-Creator-Recipient'])
        self.assertEquals(
            self.das.architecturetag, notification['X-Launchpad-Build-Arch'])
        self.assertEquals(
            'main', notification['X-Launchpad-Build-Component'])
        self.assertEquals(
            build.status.name, notification['X-Launchpad-Build-State'])
        if ppa is True:
            self.assertEquals(
                get_ppa_reference(self.ppa), notification['X-Launchpad-PPA'])
        body = notification.get_payload(decode=True)
        build_log = 'None'
        if ppa is True:
            archive = '%s PPA' % get_ppa_reference(build.archive)
            source = 'not available'
        else:
            archive = '%s primary archive' % (
                self.distroseries.distribution.name)
            source = canonical_url(build.distributionsourcepackagerelease)
        builder = canonical_url(build.builder)
        if build.status == BuildStatus.BUILDING:
            duration = 'not finished'
            build_log = 'see builder page'
        elif (
            build.status == BuildStatus.SUPERSEDED or
            build.status == BuildStatus.NEEDSBUILD):
            duration = 'not available'
            build_log = 'not available'
            builder = 'not available'
        elif build.status == BuildStatus.UPLOADING:
            duration = 'uploading'
            build_log = 'see builder page'
            builder = 'not available'
        else:
            duration = DurationFormatterAPI(
                build.duration).approximateduration()
        expected_body = dedent("""
         * Source Package: %s
         * Version: %s
         * Architecture: %s
         * Archive: %s
         * Component: main
         * State: %s
         * Duration: %s
         * Build Log: %s
         * Builder: %s
         * Source: %s



        If you want further information about this situation, feel free to
        contact a member of the Launchpad Buildd Administrators team.

        --
        %s
        %s
        """ % (
            build.source_package_release.sourcepackagename.name,
            build.source_package_release.version, self.das.architecturetag,
            archive, build.status.title, duration, build_log, builder,
            source, build.title, canonical_url(build)))
        self.assertEquals(expected_body, body)

    def test_notify_buildd_admins(self):
        # A build will cause an e-mail to be sent out to the buildd-admins,
        # for primary archive builds.
        self.create_builds(self.archive)
        build = self.builds[BuildStatus.FAILEDTOBUILD.value]
        build.notify()
        expected_emails = self.buildd_admins_email + ['test@example.com']
        notifications = pop_notifications()
        actual_emails = [n['To'] for n in notifications]
        self.assertEquals(expected_emails, actual_emails)

    def test_ppa_does_not_notify_buildd_admins(self):
        # A build for a PPA does not notify the buildd admins.
        self.create_builds(self.ppa)
        build = self.builds[BuildStatus.FAILEDTOBUILD.value]
        build.notify()
        notifications = pop_notifications()
        # An e-mail is sent to the archive owner, as well as the creator
        self.assertEquals(2, len(notifications))

    def test_notify_failed_to_build(self):
        # An e-mail is sent to the source package creator on build failures.
        self.create_builds(self.archive)
        build = self.builds[BuildStatus.FAILEDTOBUILD.value]
        build.notify()
        notification = pop_notifications()[1]
        self._assert_mail_is_correct(build, notification)

    def test_notify_failed_to_build_ppa(self):
        # An e-mail is sent to the source package creator on build failures.
        self.create_builds(archive=self.ppa)
        build = self.builds[BuildStatus.FAILEDTOBUILD.value]
        build.notify()
        notification = pop_notifications()[1]
        self._assert_mail_is_correct(build, notification, ppa=True)

    def test_notify_needs_building(self):
        # We can notify the creator when the build is needing to be built.
        self.create_builds(self.archive)
        build = self.builds[BuildStatus.NEEDSBUILD.value]
        build.notify()
        notification = pop_notifications()[1]
        self._assert_mail_is_correct(build, notification)

    def test_notify_needs_building_ppa(self):
        # We can notify the creator when the build is needing to be built.
        self.create_builds(self.ppa)
        build = self.builds[BuildStatus.NEEDSBUILD.value]
        build.notify()
        notification = pop_notifications()[1]
        self._assert_mail_is_correct(build, notification, ppa=True)

    def test_notify_successfully_built(self):
        # Successful builds don't notify anyone.
        self.create_builds(self.archive)
        build = self.builds[BuildStatus.FULLYBUILT.value]
        build.notify()
        self.assertEqual([], pop_notifications())

    def test_notify_dependency_wait(self):
        # We can notify the creator when the build can't find a dependency.
        self.create_builds(self.archive)
        build = self.builds[BuildStatus.MANUALDEPWAIT.value]
        build.notify()
        notification = pop_notifications()[1]
        self._assert_mail_is_correct(build, notification)

    def test_notify_dependency_wait_ppa(self):
        # We can notify the creator when the build can't find a dependency.
        self.create_builds(self.ppa)
        build = self.builds[BuildStatus.MANUALDEPWAIT.value]
        build.notify()
        notification = pop_notifications()[1]
        self._assert_mail_is_correct(build, notification, ppa=True)

    def test_notify_chroot_problem(self):
        # We can notify the creator when the builder the build attempted to
        # be built on has an internal problem.
        self.create_builds(self.archive)
        build = self.builds[BuildStatus.CHROOTWAIT.value]
        build.notify()
        notification = pop_notifications()[1]
        self._assert_mail_is_correct(build, notification)

    def test_notify_chroot_problem_ppa(self):
        # We can notify the creator when the builder the build attempted to
        # be built on has an internal problem.
        self.create_builds(self.ppa)
        build = self.builds[BuildStatus.CHROOTWAIT.value]
        build.notify()
        notification = pop_notifications()[1]
        self._assert_mail_is_correct(build, notification, ppa=True)

    def test_notify_build_for_superseded_source(self):
        # We can notify the creator when the source package had a newer
        # version uploaded before this build had a chance to be dispatched.
        self.create_builds(self.archive)
        build = self.builds[BuildStatus.SUPERSEDED.value]
        build.notify()
        notification = pop_notifications()[1]
        self._assert_mail_is_correct(build, notification)

    def test_notify_build_for_superseded_source_ppa(self):
        # We can notify the creator when the source package had a newer
        # version uploaded before this build had a chance to be dispatched.
        self.create_builds(self.ppa)
        build = self.builds[BuildStatus.SUPERSEDED.value]
        build.notify()
        notification = pop_notifications()[1]
        self._assert_mail_is_correct(build, notification, ppa=True)

    def test_notify_currently_building(self):
        # We can notify the creator when the build is currently building.
        self.create_builds(self.archive)
        build = self.builds[BuildStatus.BUILDING.value]
        build.notify()
        notification = pop_notifications()[1]
        self._assert_mail_is_correct(build, notification)

    def test_notify_currently_building_ppa(self):
        # We can notify the creator when the build is currently building.
        self.create_builds(self.ppa)
        build = self.builds[BuildStatus.BUILDING.value]
        build.notify()
        notification = pop_notifications()[1]
        self._assert_mail_is_correct(build, notification, ppa=True)

    def test_notify_uploading_build(self):
        # We can notify the creator when the build has completed, and binary
        # packages are being uploaded by the builder.
        self.create_builds(self.archive)
        build = self.builds[BuildStatus.UPLOADING.value]
        build.notify()
        notification = pop_notifications()[1]
        self._assert_mail_is_correct(build, notification)

    def test_notify_uploading_build_ppa(self):
        # We can notify the creator when the build has completed, and binary
        # packages are being uploaded by the builder.
        self.create_builds(self.ppa)
        build = self.builds[BuildStatus.UPLOADING.value]
        build.notify()
        notification = pop_notifications()[1]
        self._assert_mail_is_correct(build, notification, ppa=True)

    def test_copied_into_ppa_does_not_spam(self):
        # When a package is copied into a PPA, we don't send mail to the
        # original creator of the source package.
        self.create_builds(self.archive)
        build = self.builds[BuildStatus.FULLYBUILT.value]
        spph = build.current_source_publication
        ppa_spph = spph.copyTo(
            self.distroseries, PackagePublishingPocket.RELEASE, self.ppa)
        [ppa_build] = ppa_spph.createMissingBuilds()
        ppa_build.notify()
        notifications = pop_notifications()
        self.assertEquals(1, len(notifications))

    def test_notify_owner_supresses_mail(self):
        # When the 'notify_owner' config option is False, we don't send mail
        # to the owner of the SPR.
        self.create_builds(self.archive)
        build = self.builds[BuildStatus.FAILEDTOBUILD.value]
        notify_owner = dedent("""
            [builddmaster]
            send_build_notification: True
            notify_owner: False
            """)
        config.push('notify_owner', notify_owner)
        build.notify()
        notifications = pop_notifications()
        actual_emails = [n['To'] for n in notifications]
        self.assertEquals(self.buildd_admins_email, actual_emails)
        # And undo what we just did.
        config.pop('notify_owner')

    def test_build_notification_supresses_mail(self):
        # When the 'build_notification' config option is False, we don't
        # send any mail at all.
        self.create_builds(self.archive)
        build = self.builds[BuildStatus.FULLYBUILT.value]
        send_build_notification = dedent("""
            [builddmaster]
            send_build_notification: False
            """)
        config.push('send_build_notification', send_build_notification)
        build.notify()
        notifications = pop_notifications()
        self.assertEquals(0, len(notifications))
        # And undo what we just did.
        config.pop('send_build_notification')

    def test_sponsored_upload_notification(self):
        # If the signing key is different to the creator, they are both
        # notified.
        sponsor = self.factory.makePerson('sponsor@example.com')
        key = self.factory.makeGPGKey(owner=sponsor)
        self.create_builds(self.archive)
        build = self.builds[BuildStatus.FAILEDTOBUILD.value]
        spr = build.current_source_publication.sourcepackagerelease
        # Push past the security proxy
        removeSecurityProxy(spr).dscsigningkey = key
        build.notify()
        notifications = pop_notifications()
        expected_emails = self.buildd_admins_email + [
            'sponsor@example.com', 'test@example.com']
        actual_emails = [n['To'] for n in notifications]
        self.assertEquals(expected_emails, actual_emails)
