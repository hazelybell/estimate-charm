# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the branch merge queue view classes and templates."""

from __future__ import with_statement

__metaclass__ = type

import re

from mechanize import LinkNotFoundError
import soupmatchers

from lp.services.features.model import (
    FeatureFlag,
    getFeatureStore,
    )
from lp.services.webapp import canonical_url
from lp.testing import (
    ANONYMOUS,
    BrowserTestCase,
    person_logged_in,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestBranchMergeQueue(BrowserTestCase):
    """Test the Branch Merge Queue index page."""

    layer = DatabaseFunctionalLayer

    def enable_queue_flag(self):
        getFeatureStore().add(FeatureFlag(
            scope=u'default', flag=u'code.branchmergequeue',
            value=u'on', priority=1))

    def test_index(self):
        """Test the index page of a branch merge queue."""
        with person_logged_in(ANONYMOUS):
            queue = self.factory.makeBranchMergeQueue()
            queue_owner = queue.owner.displayname
            queue_registrant = queue.registrant.displayname
            queue_description = queue.description
            queue_url = canonical_url(queue)

            branch = self.factory.makeBranch()
            branch_name = branch.bzr_identity
            with person_logged_in(branch.owner):
                branch.addToQueue(queue)

        # XXX: rockstar - bug #666979 - The text argument should really ignore
        # whitespace, but it currently doesn't.  Now I have two problems.
        queue_matcher = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                'Page title', 'h1',
                text=re.compile('\w*%s queue owned by %s\w*' % (
                    queue.name, queue.owner.displayname))),
            soupmatchers.Tag(
                'Description Label', 'dt',
                text=re.compile('\w*Description\w*')),
            soupmatchers.Tag(
                'Description Value', 'dd',
                text=re.compile('\w*%s\w*' % queue.description)),
            soupmatchers.Tag(
                'Branch link', 'a',
                text=re.compile('\w*%s\w*' % branch.bzr_identity)))

        browser = self.getUserBrowser(canonical_url(queue), user=queue.owner)

        self.assertThat(browser.contents, queue_matcher)

    def test_create(self):
        """Test that branch merge queues can be created from a branch."""
        self.enable_queue_flag()
        with person_logged_in(ANONYMOUS):
            rockstar = self.factory.makePerson(name='rockstar')
            branch = self.factory.makeBranch(owner=rockstar)
            self.factory.makeBranch(product=branch.product)
            owner_name = branch.owner.name

        browser = self.getUserBrowser(canonical_url(branch), user=rockstar)

        # There shouldn't be a merge queue linked here.
        noqueue_matcher = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                'Not managed', 'div',
                text=re.compile(
                    '\w*This branch is not managed by a queue.\w*')))
        self.assertThat(browser.contents, noqueue_matcher)

        browser.getLink('Create a new queue').click()

        browser.getControl('Name').value = 'libbob-queue'
        browser.getControl('Description').value = (
            'This is a queue for the libbob projects.')
        browser.getControl('Create Queue').click()

        self.assertEqual(
            'http://code.launchpad.dev/~rockstar/+merge-queues/libbob-queue',
            browser.url)

    def test_create_unauthorized(self):
        """Test that queues can't be created by unauthorized users."""
        self.enable_queue_flag()
        with person_logged_in(ANONYMOUS):
            branch = self.factory.makeBranch()
            self.factory.makeBranch(product=branch.product)

        browser = self.getUserBrowser(canonical_url(branch))
        self.assertRaises(
            LinkNotFoundError,
            browser.getLink,
            'Create a new queue')

    def test_create_featureflag(self):
        """Test that the feature flag hides the "create" link."""
        with person_logged_in(ANONYMOUS):
            rockstar = self.factory.makePerson(name='rockstar')
            branch = self.factory.makeBranch(owner=rockstar)
            self.factory.makeBranch(product=branch.product)
            owner_name = branch.owner.name

        browser = self.getUserBrowser(canonical_url(branch), user=rockstar)
        self.assertRaises(
            LinkNotFoundError,
            browser.getLink,
            'Create a new queue')
