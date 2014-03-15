# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the revision feeds."""

__metaclass__ = type

from datetime import datetime

from pytz import UTC
from zope.component import getUtility

from lp.code.feed.branch import (
    ProductRevisionFeed,
    revision_feed_id,
    RevisionListingFeed,
    )
from lp.code.interfaces.revision import IRevisionSet
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.testing import (
    login_person,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestRevisionFeedId(TestCaseWithFactory):
    """Test the revision_feed_id function."""

    layer = DatabaseFunctionalLayer

    def test_format(self):
        # The id contains the iso format of the date part of the revision
        # date, and the revision id.
        revision_date = datetime(2009, 07, 21, 12, tzinfo=UTC)
        revision = self.factory.makeRevision(
            revision_date=revision_date, rev_id="test_revision_id")
        feed_id = revision_feed_id(revision)
        self.assertEqual(
            'tag:launchpad.net,2009-07-21:/revision/test_revision_id',
            feed_id)


class TestRevisionFeed(TestCaseWithFactory):
    """Tests for the methods of the RevisionListingFeed base class."""

    layer = DatabaseFunctionalLayer

    def _createBranchWithRevision(self):
        """Create a branch with a linked, cached revision.

        :return: a tuple of (branch, revision)
        """
        revision = self.factory.makeRevision()
        branch = self.factory.makeBranch()
        branch.createBranchRevision(1, revision)
        getUtility(IRevisionSet).updateRevisionCacheForBranch(branch)
        return branch, revision

    def _createFeed(self):
        """Create and return a RevisionListingFeed instance."""
        # The FeedBase class determins the feed type by the end of the
        # requested URL, so forcing .atom here.
        return RevisionListingFeed(
            None, LaunchpadTestRequest(
                SERVER_URL="http://example.com/fake.atom"))

    def test_createView(self):
        # Revisions that are linked to branches are shown in the feed.

        # Since we are calling into a base class that would normally take a
        # context and a request, we need to give it something - None should be
        # fine.
        branch, revision = self._createBranchWithRevision()
        revision_feed = self._createFeed()
        view = revision_feed._createView(revision)
        self.assertEqual(revision, view.context)
        self.assertEqual(branch, view.branch)

    def test_createView_revision_not_in_branch(self):
        # If a revision is in the RevisionCache table, but no longer
        # associated with a public branch, then the createView call will
        # return None to indicate not do show this revision.
        branch, revision = self._createBranchWithRevision()
        # Now delete the branch.
        login_person(branch.owner)
        branch.destroySelf()
        revision_feed = self._createFeed()
        view = revision_feed._createView(revision)
        self.assertIs(None, view)


class TestProductRevisionFeed(TestCaseWithFactory):
    """Tests for the ProductRevisionFeed."""

    layer = DatabaseFunctionalLayer

    def _createBranchWithRevision(self, product):
        """Create a branch with a linked, cached revision.

        :return: a tuple of (branch, revision)
        """
        revision = self.factory.makeRevision()
        branch = self.factory.makeProductBranch(product=product)
        branch.createBranchRevision(1, revision)
        getUtility(IRevisionSet).updateRevisionCacheForBranch(branch)
        return branch, revision

    def _createFeed(self, product):
        """Create and return a ProductRevisionFeed instance."""
        # The FeedBase class determins the feed type by the end of the
        # requested URL, so forcing .atom here.
        return ProductRevisionFeed(
            product, LaunchpadTestRequest(
                SERVER_URL="http://example.com/fake.atom"))

    def test_getItems_empty(self):
        # If there are no revisions for a product, there are no items.
        product = self.factory.makeProduct()
        feed = self._createFeed(product)
        self.assertEqual([], feed.getItems())

    def test_getItems_revisions(self):
        # If there are revisions in branches for the project, these are
        # returned in the feeds items.
        product = self.factory.makeProduct()
        branch, revision = self._createBranchWithRevision(product)
        feed = self._createFeed(product)
        [item] = feed.getItems()
        self.assertEqual(revision_feed_id(revision), item.id)

    def test_getItems_skips_revisions_not_in_branches(self):
        # If a revision was added to a project, but the only branch that
        # referred to that revision was subsequently removed, the revision
        # does not show in the feed.
        product = self.factory.makeProduct()
        branch, revision = self._createBranchWithRevision(product)
        # Now delete the branch.
        login_person(branch.owner)
        branch.destroySelf()
        feed = self._createFeed(product)
        self.assertEqual([], feed.getItems())
