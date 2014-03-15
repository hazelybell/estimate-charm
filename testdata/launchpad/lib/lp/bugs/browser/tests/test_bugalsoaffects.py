# Copyright 2011-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from zope.security.proxy import removeSecurityProxy

from lp.services.webapp import canonical_url
from lp.soyuz.enums import PackagePublishingStatus
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.pages import get_feedback_messages


class TestBugAlsoAffectsDistribution(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBugAlsoAffectsDistribution, self).setUp()
        self.distribution = self.factory.makeDistribution()
        removeSecurityProxy(self.distribution).official_malone = True

    def openBugPage(self, bug):
        browser = self.getUserBrowser()
        browser.open(canonical_url(bug))
        return browser

    def test_bug_alsoaffects_spn_exists(self):
        # If the source package name exists, there is no error.
        bug = self.factory.makeBug()
        spn = self.factory.makeSourcePackageName()
        browser = self.openBugPage(bug)
        browser.getLink(url='+distrotask').click()
        browser.getControl('Distribution').value = [self.distribution.name]
        browser.getControl('Source Package Name').value = spn.name
        browser.getControl('Continue').click()
        self.assertEqual([], get_feedback_messages(browser.contents))

    def test_bug_alsoaffects_spn_not_exists_with_published_binaries(self):
        # When the distribution has published binaries, we search both
        # source and binary package names.
        bug = self.factory.makeBug()
        distroseries = self.factory.makeDistroSeries(
            distribution=self.distribution)
        das = self.factory.makeDistroArchSeries(distroseries=distroseries)
        self.factory.makeBinaryPackagePublishingHistory(
            distroarchseries=das, status=PackagePublishingStatus.PUBLISHED)
        self.assertTrue(self.distribution.has_published_binaries)
        browser = self.openBugPage(bug)
        browser.getLink(url='+distrotask').click()
        browser.getControl('Distribution').value = [self.distribution.name]
        browser.getControl('Source Package Name').value = 'does-not-exist'
        browser.getControl('Continue').click()
        expected = [
            u'There is 1 error.',
            u'There is no package in %s named "does-not-exist".' % (
                self.distribution.displayname)]
        self.assertEqual(expected, get_feedback_messages(browser.contents))

    def test_bug_alsoaffects_spn_not_exists_with_no_binaries(self):
        # When the distribution has no binary packages published, we can't.
        bug = self.factory.makeBug()
        browser = self.openBugPage(bug)
        browser.getLink(url='+distrotask').click()
        browser.getControl('Distribution').value = [self.distribution.name]
        browser.getControl('Source Package Name').value = 'does-not-exist'
        browser.getControl('Continue').click()
        expected = [
            u'There is 1 error.',
            u'There is no package in %s named "does-not-exist". Launchpad '
            'does not track binary package names in %s.' % (
                self.distribution.displayname,
                self.distribution.displayname)]
        self.assertEqual(expected, get_feedback_messages(browser.contents))
