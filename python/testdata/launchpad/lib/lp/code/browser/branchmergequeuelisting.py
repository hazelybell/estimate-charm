# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Base class view for merge queue listings."""

__metaclass__ = type

__all__ = [
    'MergeQueueListingView',
    'HasMergeQueuesMenuMixin',
    'PersonMergeQueueListingView',
    ]

from zope.component import getUtility

from lp.code.interfaces.branchmergequeuecollection import (
    IAllBranchMergeQueues,
    )
from lp.services.browser_helpers import get_plural_text
from lp.services.feeds.browser import FeedsMixin
from lp.services.propertycache import cachedproperty
from lp.services.webapp import (
    LaunchpadView,
    Link,
    )


class HasMergeQueuesMenuMixin:
    """A context menus mixin for objects that can own merge queues."""

    def _getCollection(self):
        return getUtility(IAllBranchMergeQueues).visibleByUser(self.user)

    @property
    def person(self):
        """The `IPerson` for the context of the view.

        In simple cases this is the context itself, but in others, like the
        PersonProduct, it is an attribute of the context.
        """
        return self.context

    def mergequeues(self):
        return Link(
            '+merge-queues',
            get_plural_text(
                self.mergequeue_count,
                'merge queue', 'merge queues'), site='code')

    @cachedproperty
    def mergequeue_count(self):
        return self._getCollection().ownedBy(self.person).count()


class MergeQueueListingView(LaunchpadView, FeedsMixin):

    # No feeds initially
    feed_types = ()

    branch_enabled = True
    owner_enabled = True

    label_template = 'Merge Queues for %(displayname)s'

    @property
    def label(self):
        return self.label_template % {
            'displayname': self.context.displayname,
            'title': getattr(self.context, 'title', 'no-title')}

    # Provide a default page_title for distros and other things without
    # breadcrumbs..
    page_title = label

    def _getCollection(self):
        """Override this to say what queues will be in the listing."""
        raise NotImplementedError(self._getCollection)

    def getVisibleQueuesForUser(self):
        """Branch merge queues that are visible by the logged in user."""
        collection = self._getCollection().visibleByUser(self.user)
        return collection.getMergeQueues()

    @cachedproperty
    def mergequeues(self):
        return self.getVisibleQueuesForUser()

    @cachedproperty
    def mergequeue_count(self):
        """Return the number of merge queues that will be returned."""
        return self._getCollection().visibleByUser(self.user).count()

    @property
    def no_merge_queue_message(self):
        """Shown when there is no table to show."""
        return "%s has no merge queues." % self.context.displayname


class PersonMergeQueueListingView(MergeQueueListingView):

    label_template = 'Merge Queues owned by %(displayname)s'
    owner_enabled = False

    def _getCollection(self):
        return getUtility(IAllBranchMergeQueues).ownedBy(self.context)
