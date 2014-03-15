# Copyright 2010-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for the LinkCheckerAPI."""

__metaclass__ = type

from random import shuffle

import simplejson
from zope.security.proxy import removeSecurityProxy

from lp.app.browser.linkchecker import LinkCheckerAPI
from lp.app.enums import InformationType
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


class TestLinkCheckerAPI(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    BRANCH_URL_TEMPLATE = '/+branch/%s'

    def check_invalid_links(self, result_json, link_type, invalid_links):
        link_dict = simplejson.loads(result_json)
        links_to_check = link_dict[link_type]['invalid']
        self.assertEqual(len(invalid_links), len(links_to_check))
        self.assertEqual(set(invalid_links), set(links_to_check))

    def check_valid_links(self, result_json, link_type, valid_links):
        link_dict = simplejson.loads(result_json)
        links_to_check = link_dict[link_type]['valid']
        self.assertEqual(len(valid_links), len(links_to_check))
        self.assertEqual(set(valid_links), set(links_to_check))

    def make_valid_branch_links(self):
        branch = self.factory.makeProductBranch()
        valid_branch_url = self.BRANCH_URL_TEMPLATE % branch.unique_name
        product = self.factory.makeProduct()
        product_branch = self.factory.makeProductBranch(product=product)
        removeSecurityProxy(product).development_focus.branch = product_branch
        valid_product_url = self.BRANCH_URL_TEMPLATE % product.name

        return [
            valid_branch_url,
            valid_product_url,
        ]

    def make_invalid_branch_links(self):
        return [
            self.BRANCH_URL_TEMPLATE % 'foo',
            self.BRANCH_URL_TEMPLATE % 'bar',
            ]

    def make_valid_bug_links(self):
        bug1 = self.factory.makeBug()
        bug2 = self.factory.makeBug()
        self.factory.makeBugTask(bug=bug2)
        return [
            '/bugs/%d' % (bug1.id),
            '/bugs/%d' % (bug2.id)
            ]

    def make_invalid_bug_links(self):
        """
        As far as searchBugs() is concerned, this is an invalid bug to the
        currently authenticated user
        """
        bug_private = self.factory.makeBug(
            information_type=InformationType.USERDATA)
        return ['/bugs/%d' % (bug_private.id)]

    def invoke_link_checker(
        self, valid_branch_urls=None, invalid_branch_urls=None,
        valid_bug_urls=None, invalid_bug_urls=None):
        if valid_branch_urls is None:
            valid_branch_urls = {}
        if invalid_branch_urls is None:
            invalid_branch_urls = {}
        if valid_bug_urls is None:
            valid_bug_urls = {}
        if invalid_bug_urls is None:
            invalid_bug_urls = {}

        branch_urls = list(valid_branch_urls)
        branch_urls.extend(invalid_branch_urls)
        shuffle(branch_urls)

        bug_urls = list(valid_bug_urls)
        bug_urls.extend(invalid_bug_urls)
        shuffle(bug_urls)

        links_to_check = dict(branch_links=branch_urls, bug_links=bug_urls)
        link_json = simplejson.dumps(links_to_check)

        request = LaunchpadTestRequest(link_hrefs=link_json)
        link_checker = LinkCheckerAPI(object(), request)
        result_json = link_checker()
        self.check_invalid_links(
            result_json, 'branch_links', invalid_branch_urls)
        self.check_invalid_links(
            result_json, 'bug_links', invalid_bug_urls)
        self.check_valid_links(
            result_json, 'bug_links', valid_bug_urls)

    def test_with_no_data(self):
        request = LaunchpadTestRequest()
        link_checker = LinkCheckerAPI(object(), request)
        result_json = link_checker()
        link_dict = simplejson.loads(result_json)
        self.assertEqual(link_dict, {})

    def test_only_valid_links(self):
        branch_urls = self.make_valid_branch_links()
        bug_urls = self.make_valid_bug_links()
        self.invoke_link_checker(
            valid_branch_urls=branch_urls, valid_bug_urls=bug_urls)

    def test_only_invalid_links(self):
        branch_urls = self.make_invalid_branch_links()
        bug_urls = self.make_invalid_bug_links()
        self.invoke_link_checker(
            invalid_branch_urls=branch_urls, invalid_bug_urls=bug_urls)

    def test_valid_and_invald_links(self):
        valid_branch_urls = self.make_valid_branch_links()
        invalid_branch_urls = self.make_invalid_branch_links()
        valid_bug_urls = self.make_valid_bug_links()
        invalid_bug_urls = self.make_invalid_bug_links()
        self.invoke_link_checker(
            valid_branch_urls=valid_branch_urls,
            invalid_branch_urls=invalid_branch_urls,
            valid_bug_urls=valid_bug_urls,
            invalid_bug_urls=invalid_bug_urls)
