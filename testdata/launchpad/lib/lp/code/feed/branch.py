# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Branch feed (syndication) views."""

__metaclass__ = type

__all__ = [
    'BranchFeed',
    'PersonBranchFeed',
    'PersonRevisionFeed',
    'ProductBranchFeed',
    'ProductRevisionFeed',
    'ProjectBranchFeed',
    'ProjectRevisionFeed',
    ]

from storm.locals import (
    Asc,
    Desc,
    )
from z3c.ptcompat import ViewPageTemplateFile
from zope.component import getUtility
from zope.interface import implements
from zope.security.interfaces import Unauthorized

from lp.code.browser.branch import BranchView
from lp.code.interfaces.branch import (
    DEFAULT_BRANCH_STATUS_IN_LISTING,
    IBranch,
    )
from lp.code.interfaces.branchcollection import IAllBranches
from lp.code.interfaces.revisioncache import IRevisionCache
from lp.code.model.branch import Branch
from lp.registry.interfaces.person import IPerson
from lp.registry.interfaces.product import IProduct
from lp.registry.interfaces.projectgroup import IProjectGroup
from lp.services.config import config
from lp.services.feeds.feed import (
    FeedBase,
    FeedEntry,
    FeedPerson,
    FeedTypedData,
    MINUTES,
    )
from lp.services.feeds.interfaces.feed import IFeedPerson
from lp.services.propertycache import cachedproperty
from lp.services.webapp import (
    canonical_url,
    LaunchpadView,
    urlparse,
    )
from lp.services.webapp.interfaces import ILaunchpadRoot


def revision_feed_id(revision):
    """Return a consistent id for a revision to use as an id."""
    return "tag:launchpad.net,%s:/revision/%s" % (
        revision.revision_date.date().isoformat(), revision.revision_id)


class BranchFeedEntry(FeedEntry):
    """See `IFeedEntry`."""
    def construct_id(self):
        url_path = urlparse(self.link_alternate)[2]
        return 'tag:launchpad.net,%s:/code%s' % (
            self.date_created.date().isoformat(),
            url_path)


class BranchFeedContentView(BranchView):
    """View for branch feed contents."""

    def __init__(self, context, request, feed,
                 template='templates/branch.pt'):
        super(BranchFeedContentView, self).__init__(context, request)
        self.feed = feed
        self.template_ = template

    def render(self):
        """Render the view."""
        return ViewPageTemplateFile(self.template_)(self)


class BranchFeedBase(FeedBase):
    """Abstract class for branch feeds."""

    # max_age is in seconds
    max_age = config.launchpad.max_branch_feed_cache_minutes * MINUTES

    rootsite = "code"

    @property
    def logo(self):
        """See `IFeed`."""
        return "%s/@@/branch" % self.site_url

    def _getRawItems(self):
        """Get the raw set of items for the feed."""
        raise NotImplementedError

    def getPublicRawItems(self):
        """Private branchess are not to be shown in feeds.

        The list of branches is screened to ensure no private branches are
        returned.
        """
        return [branch
                for branch in self._getRawItems()
                if not branch.private]

    def _getItemsWorker(self):
        """Create the list of items.

        Called by getItems which may cache the results.
        """
        items = self.getPublicRawItems()
        # Convert the items into their feed entry representation.
        items = [self.itemToFeedEntry(item) for item in items]
        return items

    def itemToFeedEntry(self, branch):
        """See `IFeed`."""
        title = FeedTypedData(branch.displayname)
        url = canonical_url(branch, rootsite=self.rootsite)
        content_view = BranchFeedContentView(branch, self.request, self)
        content = content_view.render()
        content_data = FeedTypedData(content=content,
                                     content_type="html",
                                     root_url=self.root_url)
        entry = BranchFeedEntry(title=title,
                                link_alternate=url,
                                date_created=branch.date_created,
                                date_updated=branch.date_last_modified,
                                date_published=branch.date_created,
                                # XXX bac 2008-01-10: if author and owner are
                                # different perhaps we should use them both?
                                authors=[FeedPerson(branch.owner,
                                                    self.rootsite)],
                                content=content_data)
        return entry


class BranchListingFeed(BranchFeedBase):
    """Feed for all branches on a product or project."""

    feedname = "branches"

    @property
    def title(self):
        """See `IFeed`."""
        return "Branches for %s" % self.context.displayname

    def _getCollection(self):
        """Return the collection that `BranchListingFeed_getRawItems` uses."""
        raise NotImplementedError(self._getCollection)

    def _getRawItems(self):
        """See `BranchFeedBase._getRawItems`.

        Return the branches for this context sorted by date_created in
        descending order.

        Only `self.quantity` revisions are returned.
        """
        collection = self._getCollection().visibleByUser(
            None).withLifecycleStatus(*DEFAULT_BRANCH_STATUS_IN_LISTING)
        branches = collection.getBranches(eager_load=False)
        return list(branches.order_by(
            Desc(Branch.date_last_modified), Asc(Branch.target_suffix),
            Desc(Branch.lifecycle_status), Asc(Branch.name)).config(
                limit=self.quantity))


class ProductBranchFeed(BranchListingFeed):
    """Feed for all branches on a product."""

    usedfor = IProduct

    def _getCollection(self):
        return getUtility(IAllBranches).inProduct(self.context)


class ProjectBranchFeed(BranchListingFeed):
    """Feed for all branches on a product."""

    usedfor = IProjectGroup

    def _getCollection(self):
        return getUtility(IAllBranches).inProject(self.context)


class PersonBranchFeed(BranchListingFeed):
    """Feed for a person's branches."""

    usedfor = IPerson

    def _getCollection(self):
        return getUtility(IAllBranches).ownedBy(self.context)


class RevisionFeedContentView(LaunchpadView):
    """View for a revision feed contents."""

    def __init__(self, context, request, feed):
        super(RevisionFeedContentView, self).__init__(context, request)
        self.feed = feed

    @cachedproperty
    def branch(self):
        return self.context.getBranch()

    @cachedproperty
    def revno(self):
        return self.branch.getBranchRevision(revision=self.context).sequence

    @property
    def product(self):
        return self.branch.product

    def render(self):
        """Render the view."""
        return ViewPageTemplateFile('templates/revision.pt')(self)

    @property
    def title(self):
        if self.revno is None:
            revno = ""
        else:
            revno = "r%s " % self.revno
        log_lines = self.context.log_body.split('\n')
        first_line = log_lines[0]
        if len(first_line) < 60 and len(log_lines) == 1:
            logline = first_line
        else:
            logline = first_line[:60] + '...'
        return "[%(branch)s] %(revno)s %(logline)s" % {
            'branch': self.branch.name,
            'revno': revno,
            'logline': logline}


class RevisionListingFeed(FeedBase):
    """Abstract class for revision feeds."""

    # max_age is in seconds
    max_age = config.launchpad.max_revision_feed_cache_minutes * MINUTES

    rootsite = "code"
    feedname = "revisions"

    @property
    def logo(self):
        """See `IFeed`."""
        return "%s/@@/branch" % self.site_url

    def _getRevisionCache(self):
        """Return the revision cache limited to the revision context."""
        raise NotImplementedError(self._getRevisionCache)

    def _getItemsWorker(self):
        """Create the list of items.

        Called by getItems which may cache the results.
        """
        cache = self._getRevisionCache()
        revisions = cache.public().getRevisions()
        # Convert the items into their feed entry representation.
        items = []
        for revision in revisions:
            content_view = self._createView(revision)
            if content_view is not None:
                entry = self.createFeedEntry(content_view)
                items.append(entry)
            # If we've hit our limit, stop iterating the revisions.
            if len(items) >= self.quantity:
                break
        return items

    def _createView(self, revision):
        """Make a view for this revision.

        :return: A view class, or None.
        """
        content_view = RevisionFeedContentView(revision, self.request, self)
        # If there is no longer an associated branch for this, return None as
        # we don't want to show this revision.
        if content_view.branch is None:
            return None
        return content_view

    def createFeedEntry(self, content_view):
        """Create the FeedEntry for the specified view."""
        revision = content_view.context
        id = revision_feed_id(revision)
        content = content_view.render()
        content_data = FeedTypedData(content=content,
                                     content_type="html",
                                     root_url=self.root_url)
        title = FeedTypedData(content_view.title)
        if revision.revision_author.person is None:
            authors = [
                RevisionPerson(revision.revision_author, self.rootsite)]
        else:
            authors = [
                FeedPerson(revision.revision_author.person, self.rootsite)]

        entry = FeedEntry(
            title=title,
            link_alternate=None,
            date_created=revision.revision_date,
            date_updated=revision.revision_date,
            date_published=revision.date_created,
            authors=authors,
            id_=id,
            content=content_data)
        return entry


class PersonRevisionFeed(RevisionListingFeed):
    """Feed for a person's revisions."""

    usedfor = IPerson

    @property
    def title(self):
        """See `IFeed`."""
        if self.context.is_team:
            return 'Latest Revisions by members of %s' % (
                self.context.displayname)
        else:
            return 'Latest Revisions by %s' % self.context.displayname

    def _getRevisionCache(self):
        """See `RevisionListingFeed`."""
        return getUtility(IRevisionCache).authoredBy(self.context)


class ProjectRevisionFeedBase(RevisionListingFeed):
    """Defines a common access method to get the revisions."""

    @property
    def title(self):
        """See `IFeed`."""
        return 'Latest Revisions for %s' % self.context.displayname


class ProductRevisionFeed(ProjectRevisionFeedBase):
    """Feed for a project's revisions."""

    usedfor = IProduct

    def _getRevisionCache(self):
        """See `RevisionListingFeed`."""
        return getUtility(IRevisionCache).inProduct(self.context)


class ProjectRevisionFeed(ProjectRevisionFeedBase):
    """Feed for a project's revisions."""

    usedfor = IProjectGroup

    def _getRevisionCache(self):
        """See `RevisionListingFeed`."""
        return getUtility(IRevisionCache).inProject(self.context)


class RevisionPerson:
    """See `IFeedPerson`.

    Uses the `name_without_email` property for the display name.
    """
    implements(IFeedPerson)

    def __init__(self, person, rootsite):

        no_email = person.name_without_email
        if no_email:
            self.name = no_email
        else:
            self.name = person.name
        # We don't want to disclose email addresses in public feeds.
        self.email = None
        self.uri = None


class BranchFeed(BranchFeedBase):
    """Feed for single branch.

    Unlike the other branch feeds, where the feed entries were the various
    branches for that object, the feed for a single branch has as entries the
    latest revisions for that branch.
    """

    usedfor = IBranch
    feedname = "branch"

    def initialize(self):
        """See `IFeed`."""
        # For a `BranchFeed` we must ensure that the branch is not private.
        super(BranchFeed, self).initialize()
        try:
            feed_allowed = not self.context.private
            if not feed_allowed:
                # We are logged in and can see the branch so redirect to the
                # branch index page.
                message_prefix = "This branch is private."
                redirect_url = canonical_url(self.context)
        except Unauthorized:
            # Branch cannot be seen so redirect to the code index page.
            feed_allowed = False
            message_prefix = "The requested branch is private."
            root = getUtility(ILaunchpadRoot)
            redirect_url = canonical_url(root, rootsite='code')

        if not feed_allowed:
            self.request.response.addErrorNotification(
                message_prefix +
                " Feeds do not serve private branches.")
            self.request.response.redirect(redirect_url)

    @property
    def title(self):
        """See `IFeed`."""
        return "Latest Revisions for Branch %s" % self.context.displayname

    def _getRawItems(self):
        """Get the raw set of items for the feed.

        For a `BranchFeed` the items are the revisions for the branch.
        """
        branch = self.context
        return branch.latest_revisions(quantity=self.quantity)

    def _getItemsWorker(self):
        """Create the list of items.

        Called by getItems which may cache the results.
        """
        items = self._getRawItems()
        # Convert the items into their feed entry representation.
        items = [self.itemToFeedEntry(item) for item in items]
        return items

    def itemToFeedEntry(self, rev):
        """See `IFeed`."""
        title = FeedTypedData("Revision %d" % rev.sequence)
        url = self.context.codebrowse_url('revision', str(rev.sequence))
        content_view = BranchFeedContentView(rev, self.request, self,
                                             'templates/branch-revision.pt')
        content = FeedTypedData(content=content_view.render(),
                                content_type="html",
                                root_url=self.root_url)
        entry = BranchFeedEntry(
            title=title,
            link_alternate=url,
            date_created=rev.revision.date_created,
            date_updated=rev.revision.revision_date,
            date_published=None,
            authors=[RevisionPerson(
                    rev.revision.revision_author,
                    self.rootsite)],
            content=content)
        return entry
