# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""SourcePackageRecipe views."""

__metaclass__ = type

__all__ = [
    'BranchMergeQueueContextMenu',
    'BranchMergeQueueView',
    ]

from lazr.restful.interface import copy_field
from zope.component import getUtility
from zope.interface import Interface

from lp.app.browser.launchpadform import (
    action,
    LaunchpadFormView,
    )
from lp.code.interfaces.branchmergequeue import (
    IBranchMergeQueue,
    IBranchMergeQueueSource,
    )
from lp.services.webapp import (
    canonical_url,
    ContextMenu,
    LaunchpadView,
    )


class BranchMergeQueueContextMenu(ContextMenu):
    """Context menu for sourcepackage recipes."""

    usedfor = IBranchMergeQueue

    facet = 'branches'

    links = ()


class BranchMergeQueueView(LaunchpadView):
    """Default view of a SourcePackageRecipe."""

    @property
    def page_title(self):
        return "%(queue_name)s queue owned by %(name)s" % {
            'name': self.context.owner.displayname,
            'queue_name': self.context.name}

    label = page_title


class BranchMergeQueueAddView(LaunchpadFormView):

    title = label = 'Create a new branch merge queue'

    class schema(Interface):
        name = copy_field(IBranchMergeQueue['name'], readonly=False)
        owner = copy_field(IBranchMergeQueue['owner'], readonly=False)
        description = copy_field(IBranchMergeQueue['description'],
            readonly=False)

    def initialize(self):
        super(BranchMergeQueueAddView, self).initialize()

    @property
    def initial_values(self):
        return {}

    @property
    def cancel_url(self):
        return canonical_url(self.context)

    @action('Create Queue', name='create')
    def request_action(self, action, data):
        merge_queue = getUtility(IBranchMergeQueueSource).new(
            data['name'], data['owner'], self.user, data['description'])
        self.context.addToQueue(merge_queue)

        self.next_url = canonical_url(merge_queue)
