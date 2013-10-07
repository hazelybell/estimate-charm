# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests cronscript for retriving components from remote Bugzillas"""

__metaclass__ = type

__all__ = []

import os
from urllib2 import HTTPError

import transaction

from lp.bugs.scripts.bzremotecomponentfinder import (
    BugzillaRemoteComponentFinder,
    BugzillaRemoteComponentScraper,
    dictFromCSV,
    )
from lp.services.log.logger import BufferLogger
from lp.testing import (
    login,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.sampledata import ADMIN_EMAIL


def read_test_file(name):
    """Return the contents of the test file named :name:

    Test files are located in lib/canonical/launchpad/ftests/testfiles
    """
    file_path = os.path.join(os.path.dirname(__file__), 'testfiles', name)
    test_file = open(file_path, 'r')
    return test_file.read()


class StaticTextBugzillaRemoteComponentScraper(
    BugzillaRemoteComponentScraper):
    """A scraper that just returns static text for getPage()"""
    def __init__(self):
        BugzillaRemoteComponentScraper.__init__(
            self, "http://www.example.com")

    def getPage(self):
        return read_test_file("bugzilla-fdo-advanced-query.html")


class FaultyBugzillaRemoteComponentScraper(
    BugzillaRemoteComponentScraper):
    """A scraper that trips asserts when getPage() is called"""

    def __init__(self, error=None):
        BugzillaRemoteComponentScraper.__init__(
            self, "http://www.example.com")
        self.error = error

    def getPage(self):
        raise self.error
        return None


class TestBugzillaRemoteComponentScraper(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBugzillaRemoteComponentScraper, self).setUp()

    def test_url_correction(self):
        scraper = BugzillaRemoteComponentScraper(
            base_url="http://bugzilla.sample.com/")

        # Trailing slashes are stripped from the URL
        self.assertEqual(
            scraper.base_url,
            "http://bugzilla.sample.com")

        # Query cgi string is generated from the base_url
        self.assertEqual(
            scraper.url,
            "http://bugzilla.sample.com/query.cgi?format=advanced")

    def test_dict_from_csv(self):
        """Test conversion of various CSV strings parse correctly"""

        data = [
            ("'foo'",        {'foo':     {'name': 'foo'}}),
            ("'B_A_R'",      {'B_A_R':   {'name': 'B_A_R'}}),
            ("'b@z'",        {'b@z':     {'name': 'b@z'}}),
            ("'b\\!ah'",     {'b!ah':    {'name': 'b!ah'}}),
            ("42",           {'42':      {'name': '42'}}),
            ("''",           {'':        {'name': ''}}),
            (u"uni",         {'uni':     {'name': 'uni'}}),
            ("'a', 'b','c'", {'a':       {'name': 'a'},
                              'b':       {'name': 'b'},
                              'c':       {'name': 'c'},
                              }),
            ]
        for test_case in data:
            (key, truth_dict) = test_case
            test_dict = dictFromCSV(key)
            self.assertEqual(test_dict, truth_dict)

    def test_parse_page(self):
        """Verify parsing a static html bugzilla page"""
        self.scraper = BugzillaRemoteComponentScraper(
            base_url="http://bugs.wine.org")
        page_text = read_test_file("bugzilla-wine-advanced-query.html")
        self.scraper.parsePage(page_text)
        self.assertTrue(u'Wine' in self.scraper.products)
        xorg = self.scraper.products['Wine']
        self.assertTrue(u'ole' in xorg['components'])


class TestBugzillaRemoteComponentFinder(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBugzillaRemoteComponentFinder, self).setUp()
        login(ADMIN_EMAIL)

    def assertGetRemoteProductsAndComponentsDoesNotAssert(self, finder):
        asserted = None
        try:
            finder.getRemoteProductsAndComponents()
        except Exception as e:
            asserted = e
        self.assertIs(None, asserted)

    def test_store(self):
        """Check that already-parsed data gets stored to database"""
        lp_bugtracker = self.factory.makeBugTracker()
        transaction.commit()

        # Set up remote bug tracker with synthetic data
        bz_bugtracker = BugzillaRemoteComponentScraper(
            base_url="http://bugzilla.example.org")
        bz_bugtracker.products = {
            u'alpha': {
                'name': u'alpha',
                'components': {
                    u'1': {'name': u'1', },
                    u'2': {'name': u'2', },
                    u'3': {'name': u'3', },
                    },
                'versions': None,
                },
            u'beta': {
                'name': u'beta',
                'components': {
                    u'4': {'name': u'4', },
                    },
                'versions': None,
                }
            }
        finder = BugzillaRemoteComponentFinder(
            logger=BufferLogger())
        finder.storeRemoteProductsAndComponents(
            bz_bugtracker, lp_bugtracker)

        # Verify the data got stored properly
        comp_groups = lp_bugtracker.getAllRemoteComponentGroups()
        self.assertEqual(2, len(list(comp_groups)))
        comp_group = lp_bugtracker.getRemoteComponentGroup(u'alpha')
        self.assertEqual(3, len(list(comp_group.components)))
        comp_group = lp_bugtracker.getRemoteComponentGroup(u'beta')
        self.assertEqual(1, len(list(comp_group.components)))
        comp = comp_group.getComponent(u'non-existant')
        self.assertIs(None, comp)
        comp = comp_group.getComponent(u'4')
        self.assertEqual(u'4', comp.name)

    def test_get_remote_products_and_components(self):
        """Does a full retrieve and storing of data."""
        lp_bugtracker = self.factory.makeBugTracker(
            title="fdo-example",
            name="fdo-example")
        transaction.commit()
        bz_scraper = StaticTextBugzillaRemoteComponentScraper()

        finder = BugzillaRemoteComponentFinder(
            logger=BufferLogger(),
            static_bugzilla_scraper=bz_scraper)
        finder.getRemoteProductsAndComponents(bugtracker_name="fdo-example")

        self.assertEqual(
            109, len(list(lp_bugtracker.getAllRemoteComponentGroups())))
        comp_group = lp_bugtracker.getRemoteComponentGroup(u'xorg')
        self.assertIsNot(None, comp_group)
        self.assertEqual(146, len(list(comp_group.components)))
        comp = comp_group.getComponent(u'Driver/Radeon')
        self.assertIsNot(None, comp)
        self.assertEqual(u'Driver/Radeon', comp.name)

    def test_get_remote_products_and_components_encounters_301(self):
        lp_bugtracker = self.factory.makeBugTracker()
        transaction.commit()
        bz_scraper = FaultyBugzillaRemoteComponentScraper(
            error=HTTPError("http://bugzilla.example.com",
                            301, 'Moved Permanently', {}, None))
        finder = BugzillaRemoteComponentFinder(
            logger=BufferLogger(), static_bugzilla_scraper=bz_scraper)

        self.assertGetRemoteProductsAndComponentsDoesNotAssert(finder)

    def test_get_remote_products_and_components_encounters_400(self):
        lp_bugtracker = self.factory.makeBugTracker()
        transaction.commit()
        bz_scraper = FaultyBugzillaRemoteComponentScraper(
            error=HTTPError("http://bugzilla.example.com",
                            400, 'Bad Request', {}, None))
        finder = BugzillaRemoteComponentFinder(
            logger=BufferLogger(), static_bugzilla_scraper=bz_scraper)

        self.assertGetRemoteProductsAndComponentsDoesNotAssert(finder)

    def test_get_remote_products_and_components_encounters_404(self):
        lp_bugtracker = self.factory.makeBugTracker()
        transaction.commit()
        bz_scraper = FaultyBugzillaRemoteComponentScraper(
            error=HTTPError("http://bugzilla.example.com",
                            404, 'Not Found', {}, None))
        finder = BugzillaRemoteComponentFinder(
            logger=BufferLogger(), static_bugzilla_scraper=bz_scraper)

        self.assertGetRemoteProductsAndComponentsDoesNotAssert(finder)

    def test_get_remote_products_and_components_encounters_500(self):
        lp_bugtracker = self.factory.makeBugTracker()
        transaction.commit()
        bz_scraper = FaultyBugzillaRemoteComponentScraper(
            error=HTTPError("http://bugzilla.example.com",
                            500, 'Internal Server Error', {}, None))
        finder = BugzillaRemoteComponentFinder(
            logger=BufferLogger(), static_bugzilla_scraper=bz_scraper)

        self.assertGetRemoteProductsAndComponentsDoesNotAssert(finder)

# FIXME: This takes ~9 sec to run, but mars says new testsuites need to
#        compete in 2
#    def test_cronjob(self):
#        """Runs the cron job to verify it executes without error"""
#        import subprocess
#        process = subprocess.Popen(
#            ['cronscripts/update-sourceforge-remote-products.py', '-v'],
#            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
#            stderr=subprocess.PIPE)
#        (out, err) = process.communicate()
#
#        self.assertEqual(out, '')
#        self.assertEqual(process.returncode, 0)
#        self.assertTrue('Creating lockfile' in err)
#        self.assertTrue('Removing lock file' in err)
#        self.assertTrue('ERROR' not in err)
#        self.assertTrue('CRITICAL' not in err)
#        self.assertTrue('Exception raised' not in err)
