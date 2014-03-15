# Copyright 2010-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for branch listing."""

__metaclass__ = type

import re

from mechanize import LinkNotFoundError
import soupmatchers
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.services.features.model import (
    FeatureFlag,
    getFeatureStore,
    )
from lp.services.webapp import canonical_url
from lp.testing import (
    BrowserTestCase,
    login_person,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.pages import (
    extract_link_from_tag,
    extract_text,
    find_tag_by_id,
    )
from lp.testing.views import create_initialized_view


class MergeQueuesTestMixin:

    def setUp(self):
        self.branch_owner = self.factory.makePerson(name='eric')

    def enable_queue_flag(self):
        getFeatureStore().add(FeatureFlag(
            scope=u'default', flag=u'code.branchmergequeue',
            value=u'on', priority=1))

    def _makeMergeQueues(self, nr_queues=3, nr_with_private_branches=0):
        # We create nr_queues merge queues in total, and the first
        # nr_with_private_branches of them will have at least one private
        # branch in the queue.
        with person_logged_in(self.branch_owner):
            mergequeues = [
                self.factory.makeBranchMergeQueue(
                    owner=self.branch_owner, branches=self._makeBranches())
                for i in range(nr_queues - nr_with_private_branches)]
            mergequeues_with_private_branches = [
                self.factory.makeBranchMergeQueue(
                    owner=self.branch_owner,
                    branches=self._makeBranches(nr_private=1))
                for i in range(nr_with_private_branches)]

            return mergequeues, mergequeues_with_private_branches

    def _makeBranches(self, nr_public=3, nr_private=0):
        branches = [
            self.factory.makeProductBranch(owner=self.branch_owner)
            for i in range(nr_public)]

        private_branches = [
            self.factory.makeProductBranch(
                owner=self.branch_owner,
                information_type=InformationType.USERDATA)
            for i in range(nr_private)]

        branches.extend(private_branches)
        return branches


class TestPersonMergeQueuesView(TestCaseWithFactory, MergeQueuesTestMixin):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        MergeQueuesTestMixin.setUp(self)
        self.user = self.factory.makePerson()

    def test_mergequeues_with_all_public_branches(self):
        # Anyone can see mergequeues containing all public branches.
        mq, mq_with_private = self._makeMergeQueues()
        login_person(self.user)
        view = create_initialized_view(
            self.branch_owner, name="+merge-queues", rootsite='code')
        self.assertEqual(set(mq), set(view.mergequeues))

    def test_mergequeues_with_a_private_branch_for_owner(self):
        # Only users with access to private branches can see any queues
        # containing such branches.
        mq, mq_with_private = (
            self._makeMergeQueues(nr_with_private_branches=1))
        login_person(self.branch_owner)
        view = create_initialized_view(
            self.branch_owner, name="+merge-queues", rootsite='code')
        mq.extend(mq_with_private)
        self.assertEqual(set(mq), set(view.mergequeues))

    def test_mergequeues_with_a_private_branch_for_other_user(self):
        # Only users with access to private branches can see any queues
        # containing such branches.
        mq, mq_with_private = (
            self._makeMergeQueues(nr_with_private_branches=1))
        login_person(self.user)
        view = create_initialized_view(
            self.branch_owner, name="+merge-queues", rootsite='code')
        self.assertEqual(set(mq), set(view.mergequeues))


class TestPersonCodePage(BrowserTestCase, MergeQueuesTestMixin):
    """Tests for the person code homepage.

    This is the default page shown for a person on the code subdomain.
    """

    layer = DatabaseFunctionalLayer

    def setUp(self):
        BrowserTestCase.setUp(self)
        MergeQueuesTestMixin.setUp(self)
        self._makeMergeQueues()

    def test_merge_queue_menu_link_without_feature_flag(self):
        login_person(self.branch_owner)
        browser = self.getUserBrowser(
            canonical_url(self.branch_owner, rootsite='code'),
            self.branch_owner)
        self.assertRaises(
            LinkNotFoundError,
            browser.getLink,
            url='+merge-queues')

    def test_merge_queue_menu_link(self):
        self.enable_queue_flag()
        login_person(self.branch_owner)
        browser = self.getUserBrowser(
            canonical_url(self.branch_owner, rootsite='code'),
            self.branch_owner)
        browser.getLink(url='+merge-queues').click()
        self.assertEqual(
            'http://code.launchpad.dev/~eric/+merge-queues',
            browser.url)


class TestPersonMergeQueuesListPage(BrowserTestCase, MergeQueuesTestMixin):
    """Tests for the person merge queue list page."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        BrowserTestCase.setUp(self)
        MergeQueuesTestMixin.setUp(self)
        mq, mq_with_private = self._makeMergeQueues()
        self.merge_queues = mq
        self.merge_queues.extend(mq_with_private)

    def test_merge_queue_list_contents_without_feature_flag(self):
        login_person(self.branch_owner)
        browser = self.getUserBrowser(
            canonical_url(self.branch_owner, rootsite='code',
                          view_name='+merge-queues'), self.branch_owner)
        table = find_tag_by_id(browser.contents, 'mergequeuetable')
        self.assertIs(None, table)
        noqueue_matcher = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                'No merge queues', 'div',
                text=re.compile(
                    '\w*No merge queues\w*')))
        self.assertThat(browser.contents, noqueue_matcher)

    def test_merge_queue_list_contents(self):
        self.enable_queue_flag()
        login_person(self.branch_owner)
        browser = self.getUserBrowser(
            canonical_url(self.branch_owner, rootsite='code',
                          view_name='+merge-queues'), self.branch_owner)

        table = find_tag_by_id(browser.contents, 'mergequeuetable')

        merge_queue_info = {}
        for row in table.tbody.fetch('tr'):
            cells = row('td')
            row_info = {}
            queue_name = extract_text(cells[0])
            if not queue_name.startswith('queue'):
                continue
            qlink = extract_link_from_tag(cells[0].find('a'))
            row_info['queue_link'] = qlink
            queue_size = extract_text(cells[1])
            row_info['queue_size'] = queue_size
            queue_branches = cells[2]('a')
            branch_links = set()
            for branch_tag in queue_branches:
                branch_links.add(extract_link_from_tag(branch_tag))
            row_info['branch_links'] = branch_links
            merge_queue_info[queue_name] = row_info

        expected_queue_names = [queue.name for queue in self.merge_queues]
        self.assertEqual(
            set(expected_queue_names), set(merge_queue_info.keys()))

        #TODO: when IBranchMergeQueue API is available remove '4'
        expected_queue_sizes = dict(
            [(queue.name, '4') for queue in self.merge_queues])
        observed_queue_sizes = dict(
            [(queue.name, merge_queue_info[queue.name]['queue_size'])
             for queue in self.merge_queues])
        self.assertEqual(
            expected_queue_sizes, observed_queue_sizes)

        def branch_links(branches):
            return [canonical_url(removeSecurityProxy(branch),
                                  force_local_path=True)
                    for branch in branches]

        expected_queue_branches = dict(
            [(queue.name, set(branch_links(queue.branches)))
             for queue in self.merge_queues])
        observed_queue_branches = dict(
            [(queue.name, merge_queue_info[queue.name]['branch_links'])
             for queue in self.merge_queues])
        self.assertEqual(
            expected_queue_branches, observed_queue_branches)
