# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from datetime import (
    datetime,
    timedelta,
    )

import pytz
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.buildmaster.interfaces.builder import IBuilderSet
from lp.registry.interfaces.person import IPersonSet
from lp.soyuz.tests.test_publishing import SoyuzTestPublisher
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import LaunchpadFunctionalLayer
from lp.testing.sampledata import (
    ADMIN_EMAIL,
    BOB_THE_BUILDER_NAME,
    )


class TestBuildStartEstimation(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestBuildStartEstimation, self).setUp()
        self.admin = getUtility(IPersonSet).getByEmail(ADMIN_EMAIL)
        with person_logged_in(self.admin):
            self.publisher = SoyuzTestPublisher()
            self.publisher.prepareBreezyAutotest()
            for buildd in getUtility(IBuilderSet):
                buildd.builderok = True
        self.distroseries = self.factory.makeDistroSeries()
        self.bob = getUtility(IBuilderSet).getByName(BOB_THE_BUILDER_NAME)
        das = self.factory.makeDistroArchSeries(
            distroseries=self.distroseries, processor=self.bob.processor,
            architecturetag='i386', supports_virtualized=True)
        with person_logged_in(self.admin):
            self.distroseries.nominatedarchindep = das
        self.publisher.addFakeChroots(distroseries=self.distroseries)

    def job_start_estimate(self, build):
        return build.buildqueue_record.getEstimatedJobStartTime()

    def test_estimation(self):
        pkg = self.publisher.getPubSource(
            sourcename=self.factory.getUniqueString(),
            distroseries=self.distroseries)
        build = pkg.createMissingBuilds()[0]
        now = datetime.now(pytz.UTC)
        estimate = self.job_start_estimate(build)
        self.assertTrue(estimate > now)

    def test_disabled_archives(self):
        pkg1 = self.publisher.getPubSource(
            sourcename=self.factory.getUniqueString(),
            distroseries=self.distroseries)
        [build1] = pkg1.createMissingBuilds()
        build1.buildqueue_record.lastscore = 1000
        # No user-serviceable parts inside
        removeSecurityProxy(build1.buildqueue_record).estimated_duration = (
            timedelta(minutes=10))
        pkg2 = self.publisher.getPubSource(
            sourcename=self.factory.getUniqueString(),
            distroseries=self.distroseries)
        [build2] = pkg2.createMissingBuilds()
        build2.buildqueue_record.lastscore = 100
        now = datetime.now(pytz.UTC)
        # Since build1 is higher priority, it's estimated dispatch time is now
        estimate = self.job_start_estimate(build1)
        self.assertEquals(5, (estimate - now).seconds)
        # And build2 is next, so must take build1's duration into account
        estimate = self.job_start_estimate(build2)
        self.assertEquals(600, (estimate - now).seconds)
        # If we disable build1's archive, build2 is next
        with person_logged_in(self.admin):
            build1.archive.disable()
        estimate = self.job_start_estimate(build2)
        self.assertEquals(5, (estimate - now).seconds)

