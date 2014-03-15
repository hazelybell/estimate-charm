# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from zope.component import getUtility

from lp.registry.interfaces.distribution import IDistributionSet
from lp.services.webapp.publisher import canonical_url
from lp.soyuz.browser.archivesubscription import PersonalArchiveSubscription
from lp.testing import (
    login,
    login_person,
    )
from lp.testing.breadcrumbs import BaseBreadcrumbTestCase


class TestDistroArchSeriesBreadcrumb(BaseBreadcrumbTestCase):

    def setUp(self):
        super(TestDistroArchSeriesBreadcrumb, self).setUp()
        self.ubuntu = getUtility(IDistributionSet).getByName('ubuntu')
        self.hoary = self.ubuntu.getSeries('hoary')
        self.hoary_i386 = self.hoary['i386']

    def test_distroarchseries(self):
        das_url = canonical_url(self.hoary_i386)
        crumbs = self.getBreadcrumbsForObject(self.hoary_i386)
        self.assertEquals(crumbs[-1].url, das_url)
        self.assertEquals(crumbs[-1].text, "i386")

    def test_distroarchseriesbinarypackage(self):
        pmount_hoary_i386 = self.hoary_i386.getBinaryPackage("pmount")
        pmount_url = canonical_url(pmount_hoary_i386)
        crumbs = self.getBreadcrumbsForObject(pmount_hoary_i386)
        self.assertEquals(crumbs[-1].url, pmount_url)
        self.assertEquals(crumbs[-1].text, "pmount")

    def test_distroarchseriesbinarypackagerelease(self):
        pmount_hoary_i386 = self.hoary_i386.getBinaryPackage("pmount")
        pmount_release = pmount_hoary_i386['0.1-1']
        pmount_release_url = canonical_url(pmount_release)
        crumbs = self.getBreadcrumbsForObject(pmount_release)
        self.assertEquals(crumbs[-1].url, pmount_release_url)
        self.assertEquals(crumbs[-1].text, "0.1-1")


class TestArchiveSubscriptionBreadcrumb(BaseBreadcrumbTestCase):

    def setUp(self):
        super(TestArchiveSubscriptionBreadcrumb, self).setUp()

        # Create a private ppa
        self.ppa = self.factory.makeArchive()
        login('foo.bar@canonical.com')
        self.ppa.private = True

        owner = self.ppa.owner
        login_person(owner)
        self.ppa_subscription = self.ppa.newSubscription(owner, owner)
        self.ppa_token = self.ppa.newAuthToken(owner)
        self.personal_archive_subscription = PersonalArchiveSubscription(
            owner, self.ppa)

    def test_personal_archive_subscription(self):
        subscription_url = canonical_url(self.personal_archive_subscription)
        crumbs = self.getBreadcrumbsForObject(
            self.personal_archive_subscription)
        self.assertEquals(subscription_url, crumbs[-1].url)
        self.assertEquals(
            "Access to %s" % self.ppa.displayname, crumbs[-1].text)
