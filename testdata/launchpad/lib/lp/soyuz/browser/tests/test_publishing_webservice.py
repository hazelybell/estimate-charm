# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test webservice methods related to the publisher."""

from testtools.matchers import IsInstance

from lp.services.database.sqlbase import flush_database_caches
from lp.services.webapp.interfaces import OAuthPermission
from lp.testing import (
    api_url,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing._webservice import QueryCollector
from lp.testing.layers import LaunchpadFunctionalLayer
from lp.testing.pages import webservice_for_person


class BinaryPackagePublishingHistoryWebserviceTests(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def make_bpph_for(self, person):
        with person_logged_in(person):
            bpr = self.factory.makeBinaryPackageRelease()
            self.factory.makeBinaryPackageFile(binarypackagerelease=bpr)
            bpph = self.factory.makeBinaryPackagePublishingHistory(
                binarypackagerelease=bpr)
            return bpph, api_url(bpph)

    def test_binaryFileUrls(self):
        person = self.factory.makePerson()
        webservice = webservice_for_person(
            person, permission=OAuthPermission.READ_PUBLIC)

        response = webservice.named_get(
            self.make_bpph_for(person)[1], 'binaryFileUrls',
            api_version='devel')

        self.assertEqual(200, response.status)
        urls = response.jsonBody()
        self.assertEqual(1, len(urls))
        self.assertTrue(urls[0], IsInstance(unicode))

    def test_binaryFileUrls_include_meta(self):
        person = self.factory.makePerson()
        webservice = webservice_for_person(
            person, permission=OAuthPermission.READ_PUBLIC)

        bpph, url = self.make_bpph_for(person)
        query_counts = []
        for i in range(3):
            flush_database_caches()
            with QueryCollector() as collector:
                response = webservice.named_get(
                    url, 'binaryFileUrls', include_meta=True,
                    api_version='devel')
            query_counts.append(collector.count)
            with person_logged_in(person):
                self.factory.makeBinaryPackageFile(
                    binarypackagerelease=bpph.binarypackagerelease)
        self.assertEqual(query_counts[0] - 1, query_counts[-1])

        self.assertEqual(200, response.status)
        urls = response.jsonBody()
        self.assertEqual(3, len(urls))
        self.assertThat(urls[0], IsInstance(dict))
