# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Bug feed (syndication) views."""

__metaclass__ = type

__all__ = [
    'BugFeed',
    'BugTargetBugsFeed',
    'PersonBugsFeed',
    'SearchBugsFeed',
    ]

from z3c.ptcompat import ViewPageTemplateFile
from zope.component import getUtility

from lp.bugs.browser.bugtask import (
    BugsBugTaskSearchListingView,
    BugTargetView,
    )
from lp.bugs.browser.person import PersonRelatedBugTaskSearchListingView
from lp.bugs.interfaces.bug import (
    IBug,
    IBugSet,
    )
from lp.bugs.interfaces.bugtarget import IHasBugs
from lp.bugs.interfaces.bugtask import IBugTaskSet
from lp.bugs.interfaces.malone import IMaloneApplication
from lp.registry.interfaces.person import IPerson
from lp.services.config import config
from lp.services.feeds.feed import (
    FeedBase,
    FeedEntry,
    FeedPerson,
    FeedTypedData,
    MINUTES,
    )
from lp.services.webapp import (
    canonical_url,
    urlparse,
    )
from lp.services.webapp.authorization import check_permission
from lp.services.webapp.interfaces import ILaunchpadRoot
from lp.services.webapp.publisher import LaunchpadView


class BugFeedContentView(LaunchpadView):
    """View for a bug feed contents."""

    def __init__(self, context, request, feed):
        super(BugFeedContentView, self).__init__(context, request)
        self.feed = feed

    def render(self):
        """Render the view."""
        return ViewPageTemplateFile('templates/bug.pt')(self)


class BugsFeedBase(FeedBase):
    """Abstract class for bug feeds."""

    # max_age is in seconds
    max_age = config.launchpad.max_bug_feed_cache_minutes * MINUTES

    rootsite = "bugs"

    def initialize(self):
        """See `LaunchpadView`."""
        super(BugsFeedBase, self).initialize()
        self.setupColumns()

    def setupColumns(self):
        """Set up the columns to be displayed in the feed.

        This method may need to be overridden to customize the display for
        different feeds.
        """
        self.show_column = dict(
            id=True,
            title=True,
            bugtargetdisplayname=True,
            importance=True,
            status=True)

    @property
    def logo(self):
        """See `IFeed`."""
        return "%s/@@/bug" % self.site_url

    def _sortByDateCreated(self, bugs):
        return sorted(bugs,
                      key=lambda bug: (bug.datecreated, bug.id),
                      reverse=True)

    def _getRawItems(self):
        """Get the raw set of items for the feed."""
        raise NotImplementedError

    def getPublicRawItems(self):
        """Private bugs are not to be shown in feeds.

        The list of bugs is screened to ensure no private bugs are returned.
        """
        # XXX: BradCrittenden 2008-03-26 bug=206811: The screening of private
        # bugs should be done in the database query.
        bugs = self._getRawItems()
        for bug in bugs:
            assert not bug.private, (
                "Private bugs should not be retrieved for feeds.")
        return self._sortByDateCreated(bugs)

    def _getItemsWorker(self):
        """Create the list of items.

        Called by getItems which may cache the results.
        """
        bugs = self.getPublicRawItems()
        # Convert the bugs into their feed entry representation.
        bugs = [self.itemToFeedEntry(bug) for bug in bugs]
        return bugs

    def itemToFeedEntry(self, bug):
        """Convert the items to FeedEntries."""
        title = FeedTypedData('[%s] %s' % (bug.id, bug.title))
        url = canonical_url(bug, rootsite=self.rootsite)
        content_view = BugFeedContentView(bug, self.request, self)
        entry = FeedEntry(title=title,
                          link_alternate=url,
                          date_created=bug.datecreated,
                          date_updated=bug.date_last_updated,
                          date_published=bug.datecreated,
                          authors=[FeedPerson(bug.owner, self.rootsite)],
                          content=FeedTypedData(content_view.render(),
                                                content_type="html"))
        return entry

    def renderHTML(self):
        """See `IFeed`."""
        return ViewPageTemplateFile('templates/bug-html.pt')(self)

    def getBugsFromBugTasks(self, tasks):
        """Given a list of BugTasks return the list of associated bugs.

        Since a Bug can have multiple BugTasks, we only select bugs that have
        not yet been seen.
        """
        bug_ids = []
        for task in tasks:
            if task.bugID in bug_ids:
                continue
            bug_ids.append(task.bugID)
            if len(bug_ids) >= self.quantity:
                break
        # XXX: BradCrittenden 2008-03-26 bug=TBD:
        # For database efficiency we want to do something like the following:
        # bugs = self.context.select("id in %s" % sqlvalues(bug_ids))
        # Should this be a new method on BugSet?
        bugset = getUtility(IBugSet)
        bugs = [bugset.get(bug_id) for bug_id in bug_ids]
        return bugs


class BugFeed(BugsFeedBase):
    """Bug feeds for single bug."""

    usedfor = IBug
    feedname = "bug"

    def initialize(self):
        """See `IFeed`."""
        # For a `BugFeed` we must ensure that the bug is not private.
        super(BugFeed, self).initialize()
        if self.context.private:
            if check_permission("launchpad.View", self.context):
                message_prefix = "This bug is private."
                redirect_url = canonical_url(self.context)
            else:
                # Bug cannot be seen so redirect to the bugs index page.
                message_prefix = "The requested bug is private."
                root = getUtility(ILaunchpadRoot)
                redirect_url = canonical_url(root, rootsite='bugs')

            self.request.response.addErrorNotification(
                message_prefix + " Feeds do not serve private bugs.")
            self.request.response.redirect(redirect_url)

    @property
    def title(self):
        """See `IFeed`."""
        return "Bug %s" % self.context.id

    @property
    def feed_id(self):
        """See `IFeed`."""
        datecreated = self.context.datecreated.date().isoformat()
        url_path = urlparse(self.link_alternate)[2]
        id_ = 'tag:launchpad.net,%s:%s' % (
            datecreated,
            url_path)
        return id_

    def _getRawItems(self):
        """The list of bugs for this feed only has the single bug."""
        return [self.context]


class BugTargetBugsFeed(BugsFeedBase):
    """Bug feeds for projects and products."""

    usedfor = IHasBugs
    feedname = "latest-bugs"

    def setupColumns(self):
        """See `BugsFeedBase`.

        Since this feed is for a specific IHasBugs it is redundant to
        include the name in the output.
        """
        super(BugTargetBugsFeed, self).setupColumns()
        if 'bugtargetdisplayname' in self.show_column:
            del self.show_column['bugtargetdisplayname']

    def _createView(self):
        """Create the delegate view used by this feed."""
        return BugTargetView(self.context, self.request)

    @property
    def title(self):
        """See `IFeed`."""
        return "Bugs in %s" % self.context.displayname

    @property
    def feed_id(self):
        """See `IFeed`."""
        # Get the creation date, if available.
        if hasattr(self.context, 'date_created'):
            datecreated = self.context.date_created.date().isoformat()
        elif hasattr(self.context, 'datecreated'):
            datecreated = self.context.datecreated.date().isoformat()
        else:
            datecreated = '2008'
        url_path = urlparse(self.link_alternate)[2]
        id_ = 'tag:launchpad.net,%s:/%s%s' % (
            datecreated,
            self.rootsite,
            url_path)
        return id_

    def _getRawItems(self):
        """Get the raw set of items for the feed."""
        delegate_view = self._createView()
        # XXX: BradCrittenden 2008-03-25 bug=206811:
        # The feed should have `self.quantity` entries, each representing a
        # bug.  Our query returns bugtasks, not bugs.  We then work backward
        # to find the bugs associated with the bugtasks.  In order to get
        # `self.quantity` bugs we need to fetch more than that number of
        # bugtasks.  As a hack, we're just getting 2 times the number and
        # hoping it is sufficient.  The correct action would be to get a
        # batched result and work through the batches until a suffient number
        # of bugs are found.
        bugtasks = delegate_view.latestBugTasks(quantity=self.quantity * 2)
        return self.getBugsFromBugTasks(bugtasks)


class PersonBugsFeed(BugsFeedBase):
    """Bug feeds for a person."""

    usedfor = IPerson
    feedname = "latest-bugs"

    @property
    def title(self):
        """See `IFeed`."""
        return "Bugs for %s" % self.context.displayname

    def _createView(self):
        """Create the delegate view used by this feed."""
        return PersonRelatedBugTaskSearchListingView(
            self.context, self.request)

    def _getRawItems(self):
        """Perform the search."""
        delegate_view = self._createView()
        # Since the delegate_view derives from LaunchpadFormView the view must
        # be initialized to setup the widgets.
        delegate_view.initialize()
        batch_navigator = delegate_view.search(
            extra_params=dict(orderby='-datecreated'))
        items = batch_navigator.batch.list[:self.quantity * 2]
        return self.getBugsFromBugTasks(items)


class SearchBugsFeed(BugsFeedBase):
    """Bug feeds for a generic search.

    Searches are of the form produced by an advanced bug search, e.g.
    http://bugs.launchpad.dev/bugs/+bugs.atom?field.searchtext=&
        search=Search+Bug+Reports&field.scope=all&field.scope.target=
    """

    usedfor = IBugTaskSet
    feedname = "+bugs"

    def _getRawItems(self):
        """Perform the search."""
        search_context = getUtility(IMaloneApplication)
        delegate_view = BugsBugTaskSearchListingView(self.context,
                                                     self.request)
        # Since the delegate_view derives from LaunchpadFormView the view must
        # be initialized to setup the widgets.
        delegate_view.initialize()
        batch_navigator = delegate_view.search(searchtext=None,
                                               context=search_context,
                                               extra_params=None)
        # XXX: BradCrittenden 2008-03-25 bug=206811:
        # See description above.
        items = batch_navigator.batch.list[:self.quantity * 2]
        return self.getBugsFromBugTasks(items)

    @property
    def title(self):
        """See `IFeed`."""
        return "Bugs from custom search"

    @property
    def link_self(self):
        """See `IFeed`."""
        return "%s?%s" % (self.request.getURL(),
                          self.request.get('QUERY_STRING'))

    @property
    def link_alternate(self):
        """See `IFeed`."""
        return "%s/bugs/%s?%s" % (self.site_url, self.feedname,
                             self.request.get('QUERY_STRING'))

    @property
    def feed_id(self):
        """See `IFeed`."""
        # We don't track the creation date for any given search query so we'll
        # just use a fixed, abbreviated date, which is allowed by the RFC.
        datecreated = "2008"
        full_path = self.link_self[self.link_self.find('/+bugs'):]
        id_ = 'tag:launchpad.net,%s:%s' % (
            datecreated,
            full_path)
        return id_
