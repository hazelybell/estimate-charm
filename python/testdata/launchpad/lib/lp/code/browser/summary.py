# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""View classes for branch summaries."""

__metaclass__ = type
__all__ = [
    'BranchCountSummaryView',
    ]


from lp import _
from lp.code.interfaces.branch import DEFAULT_BRANCH_STATUS_IN_LISTING
from lp.code.interfaces.branchcollection import IBranchCollection
from lp.code.interfaces.revisioncache import IRevisionCache
from lp.services.browser_helpers import get_plural_text
from lp.services.propertycache import cachedproperty
from lp.services.webapp.publisher import LaunchpadView


class BranchCountSummaryView(LaunchpadView):
    """A view to give a summary of interesting counts."""

    @cachedproperty
    def _collection(self):
        """Return the branch collection for this context."""
        collection = IBranchCollection(self.context).visibleByUser(self.user)
        collection = collection.withLifecycleStatus(
            *DEFAULT_BRANCH_STATUS_IN_LISTING)
        return collection

    @cachedproperty
    def _revision_cache(self):
        """Return the revision cache for this context."""
        return IRevisionCache(self.context)

    @cachedproperty
    def branch_count(self):
        """The number of total branches the user can see."""
        return self._collection.count()

    @cachedproperty
    def branch_owners(self):
        """The number of individuals and teams that own branches."""
        return self._collection.ownerCounts()

    @property
    def person_owner_count(self):
        return self.branch_owners[0]

    @property
    def team_owner_count(self):
        return self.branch_owners[1]

    @cachedproperty
    def commit_count(self):
        return self._revision_cache.count()

    @cachedproperty
    def committer_count(self):
        return self._revision_cache.authorCount()

    @property
    def branch_text(self):
        return get_plural_text(
            self.branch_count, _('active branch'), _('active branches'))

    @property
    def person_text(self):
        return get_plural_text(
            self.person_owner_count, _('person'), _('people'))

    @property
    def team_text(self):
        return get_plural_text(self.team_owner_count, _('team'), _('teams'))

    @property
    def commit_text(self):
        return get_plural_text(self.commit_count, _('commit'), _('commits'))

    @property
    def committer_text(self):
        return get_plural_text(self.committer_count, _('person'), _('people'))
