# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from zope.component import getUtility
from zope.security.interfaces import Unauthorized

from lp.registry.interfaces.person import IPersonSet
from lp.soyuz.interfaces.archive import IArchiveSet
from lp.soyuz.tests.test_publishing import SoyuzTestPublisher
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import LaunchpadFunctionalLayer
from lp.testing.sampledata import ADMIN_EMAIL


class TestBuildPrivacy(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestBuildPrivacy, self).setUp()
        # Add everything we need to create builds.
        self.admin = getUtility(IPersonSet).getByEmail(ADMIN_EMAIL)
        processor = self.factory.makeProcessor()
        distroseries = self.factory.makeDistroSeries()
        das = self.factory.makeDistroArchSeries(
            distroseries=distroseries, processor=processor,
            supports_virtualized=True)
        with person_logged_in(self.admin):
            publisher = SoyuzTestPublisher()
            publisher.prepareBreezyAutotest()
            distroseries.nominatedarchindep = das
            publisher.addFakeChroots(distroseries=distroseries)
            self.factory.makeBuilder(processor=processor)
        self.public_archive = self.factory.makeArchive()
        self.private_archive = self.factory.makeArchive(private=True)
        # Create one public and one private build.
        public_spph = publisher.getPubSource(
            sourcename=self.factory.getUniqueString(),
            version="%s.1" % self.factory.getUniqueInteger(),
            distroseries=distroseries, archive=self.public_archive)
        [public_build] = public_spph.createMissingBuilds()
        private_spph = publisher.getPubSource(
            sourcename=self.factory.getUniqueString(),
            version="%s.1" % self.factory.getUniqueInteger(),
            distroseries=distroseries, archive=self.private_archive)
        with person_logged_in(self.admin):
            [private_build] = private_spph.createMissingBuilds()
        self.expected_title = '%s build of %s %s in %s %s RELEASE' % (
            das.architecturetag, private_spph.source_package_name,
            private_spph.source_package_version,
            distroseries.distribution.name, distroseries.name)

    def test_admin_can_see_private_builds(self):
        # Admin users can see all builds.
        with person_logged_in(self.admin):
            private = getUtility(IArchiveSet).get(self.private_archive.id)
            [build] = private.getBuildRecords()
            self.assertEquals(self.expected_title, build.title)

    def test_owner_can_see_own_private_builds(self):
        # The owner of the private archive is able to see all builds that
        # publish to that archive.
        with person_logged_in(self.private_archive.owner):
            private = getUtility(IArchiveSet).get(self.private_archive.id)
            [build] = private.getBuildRecords()
            self.assertEquals(self.expected_title, build.title)

    def test_buildd_admin_cannot_see_private_builds(self):
        # Admins that look after the builders ("buildd-admins"), can not see
        # private builds.
        buildd_admin = getUtility(IPersonSet).getByName(
            'launchpad-buildd-admins')
        with person_logged_in(buildd_admin):
            private = getUtility(IArchiveSet).get(self.private_archive.id)
            self.assertRaises(
                Unauthorized, getattr, private, 'getBuildRecords')

    def test_anonymous_cannot_see_private_builds(self):
        # An anonymous user can't query the builds for the private archive.
        private = getUtility(IArchiveSet).get(self.private_archive.id)
        self.assertRaises(Unauthorized, getattr, private, 'getBuildRecords')
