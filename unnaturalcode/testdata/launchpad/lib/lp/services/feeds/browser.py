# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""View support classes for feeds."""

__metaclass__ = type

__all__ = [
    'AnnouncementsFeedLink',
    'BranchFeedLink',
    'BugFeedLink',
    'BugTargetLatestBugsFeedLink',
    'FeedLinkBase',
    'FeedsMixin',
    'FeedsNavigation',
    'FeedsRootUrlData',
    'PersonBranchesFeedLink',
    'PersonRevisionsFeedLink',
    'ProductBranchesFeedLink',
    'ProductRevisionsFeedLink',
    'ProjectBranchesFeedLink',
    'ProjectRevisionsFeedLink',
    'RootAnnouncementsFeedLink',
    ]

from zope.component import getUtility
from zope.interface import implements
from zope.publisher.interfaces import NotFound
from zope.security.interfaces import Unauthorized

from lp.app.errors import NotFoundError
from lp.bugs.interfaces.bug import IBugSet
from lp.bugs.interfaces.bugtarget import IHasBugs
from lp.bugs.interfaces.bugtask import (
    IBugTask,
    IBugTaskSet,
    )
from lp.code.interfaces.branch import IBranch
from lp.layers import FeedsLayer
from lp.registry.interfaces.announcement import (
    IAnnouncementSet,
    IHasAnnouncements,
    )
from lp.registry.interfaces.person import (
    IPerson,
    IPersonSet,
    )
from lp.registry.interfaces.pillar import IPillarNameSet
from lp.registry.interfaces.product import IProduct
from lp.registry.interfaces.projectgroup import IProjectGroup
from lp.services.config import config
from lp.services.feeds.interfaces.application import IFeedsApplication
from lp.services.webapp import (
    canonical_name,
    canonical_url,
    Navigation,
    stepto,
    )
from lp.services.webapp.interfaces import (
    ICanonicalUrlData,
    ILaunchpadRoot,
    )
from lp.services.webapp.publisher import RedirectionView
from lp.services.webapp.url import urlappend
from lp.services.webapp.vhosts import allvhosts


class FeedsRootUrlData:
    """`ICanonicalUrlData` for Feeds."""

    implements(ICanonicalUrlData)

    path = ''
    inside = None
    rootsite = 'feeds'

    def __init__(self, context):
        self.context = context


class FeedsNavigation(Navigation):
    """Navigation for `IFeedsApplication`."""

    usedfor = IFeedsApplication

    newlayer = FeedsLayer

    @stepto('+index')
    def redirect_index(self):
        """Redirect /+index to help.launchpad.net/Feeds site.

        This provides a useful destination for users who visit
        http://feeds.launchpad.net in their browser.  It is also useful to
        avoid OOPSes when some RSS feeders (e.g. Safari) that make a request
        to the default site.
        """
        return self.redirectSubTree(
            'https://help.launchpad.net/Feeds', status=301)

    def traverse(self, name):
        """Traverse the paths of a feed.

        If a query string is provided it is normalized.  'bugs' paths and
        persons ('~') are special cased.
        """
        # Normalize the query string so caching is more effective.  This is
        # done by simply sorting the entries.

        # XXX bac 20071019, we would like to normalize with respect to case
        # too but cannot due to a problem with the bug search requiring status
        # values to be of a particular case.  See bug 154562.
        query_string = self.request.get('QUERY_STRING', '')
        fields = sorted(query_string.split('&'))
        normalized_query_string = '&'.join(fields)
        if query_string != normalized_query_string:
            # We must empty the traversal stack to prevent an error
            # when calling RedirectionView.publishTraverse().
            self.request.setTraversalStack([])
            target = "%s%s?%s" % (self.request.getApplicationURL(),
                                  self.request['PATH_INFO'],
                                  normalized_query_string)
            redirect = RedirectionView(target, self.request, 301)
            return redirect

        # Handle the two formats of urls:
        # http://feeds.launchpad.net/bugs/+bugs.atom?...
        # http://feeds.launchpad.net/bugs/1/bug.atom
        if name == 'bugs':
            stack = self.request.getTraversalStack()
            if len(stack) == 0:
                raise NotFound(self, '', self.request)
            bug_id = stack.pop()
            if bug_id.startswith('+'):
                if config.launchpad.is_bug_search_feed_active:
                    return getUtility(IBugTaskSet)
                else:
                    raise Unauthorized("Bug search feed deactivated")
            else:
                self.request.stepstogo.consume()
                return getUtility(IBugSet).getByNameOrID(bug_id)

        # Redirect to the canonical name before doing the lookup.
        if canonical_name(name) != name:
            return self.redirectSubTree(
                canonical_url(self.context) + canonical_name(name),
                status=301)

        try:
            if name.startswith('~'):
                # Handle persons and teams.
                # http://feeds.launchpad.net/~salgado/latest-bugs.html
                person = getUtility(IPersonSet).getByName(name[1:])
                return person
            else:
                # Otherwise, handle products, projects, and distros
                return getUtility(IPillarNameSet)[name]
        except NotFoundError:
            raise NotFound(self, name, self.request)


class FeedLinkBase:
    """Base class for formatting an Atom <link> tag.

    Subclasses must override:
        href: Url pointing to atom feed.

    Subclasses can override:
        title: The name of the feed as it appears in a browser.
    """
    title = 'Atom Feed'
    href = None
    rooturl = allvhosts.configs['feeds'].rooturl

    def __init__(self, context):
        self.context = context
        assert self.usedfor.providedBy(context), (
            "Context %r does not provide interface %r"
            % (context, self.usedfor))

    @classmethod
    def allowFeed(cls, context):
        """Return True if a feed is allowed for the given context.

        Subclasses should override this method as necessary.
        """
        return True


class BugFeedLink(FeedLinkBase):
    usedfor = IBugTask

    @property
    def title(self):
        return 'Bug %s Feed' % self.context.bug.id

    @property
    def href(self):
        return urlappend(self.rooturl,
                         'bugs/' + str(self.context.bug.id) + '/bug.atom')

    @classmethod
    def allowFeed(cls, context):
        """See `FeedLinkBase`"""
        # No feeds for private bugs.
        return not context.bug.private


class BugTargetLatestBugsFeedLink(FeedLinkBase):
    usedfor = IHasBugs

    @property
    def title(self):
        return 'Latest Bugs for %s' % self.context.displayname

    @property
    def href(self):
        return urlappend(canonical_url(self.context, rootsite='feeds'),
                         'latest-bugs.atom')


class AnnouncementsFeedLink(FeedLinkBase):
    usedfor = IHasAnnouncements

    @property
    def title(self):
        if IAnnouncementSet.providedBy(self.context):
            return 'All Announcements'
        else:
            return 'Announcements for %s' % self.context.displayname

    @property
    def href(self):
        if IAnnouncementSet.providedBy(self.context):
            return urlappend(self.rooturl, 'announcements.atom')
        else:
            return urlappend(canonical_url(self.context, rootsite='feeds'),
                             'announcements.atom')


class RootAnnouncementsFeedLink(AnnouncementsFeedLink):
    usedfor = ILaunchpadRoot

    @property
    def title(self):
        return 'All Announcements'

    @property
    def href(self):
        return urlappend(self.rooturl, 'announcements.atom')


class BranchesFeedLinkBase(FeedLinkBase):
    """Base class for objects with branches."""

    @property
    def title(self):
        return 'Latest Branches for %s' % self.context.displayname

    @property
    def href(self):
        return urlappend(canonical_url(self.context, rootsite='feeds'),
                         'branches.atom')


class ProjectBranchesFeedLink(BranchesFeedLinkBase):
    """Feed links for branches on a project."""
    usedfor = IProjectGroup


class ProductBranchesFeedLink(BranchesFeedLinkBase):
    """Feed links for branches on a product."""
    usedfor = IProduct


class PersonBranchesFeedLink(BranchesFeedLinkBase):
    """Feed links for branches on a person."""
    usedfor = IPerson


class RevisionsFeedLinkBase(FeedLinkBase):
    """Base class for objects with revisions."""

    @property
    def title(self):
        return 'Latest Revisions for %s' % self.context.displayname

    @property
    def href(self):
        """The location of the feed.

        E.g.  http://feeds.launchpad.net/firefox/revisions.atom
        """
        return urlappend(canonical_url(self.context, rootsite='feeds'),
                         'revisions.atom')


class ProjectRevisionsFeedLink(RevisionsFeedLinkBase):
    """Feed links for revisions on a project."""
    usedfor = IProjectGroup


class ProductRevisionsFeedLink(RevisionsFeedLinkBase):
    """Feed links for revisions on a product."""
    usedfor = IProduct


class BranchFeedLink(FeedLinkBase):
    """Feed links for revisions on a branch."""
    usedfor = IBranch

    @property
    def title(self):
        return 'Latest Revisions for Branch %s' % self.context.displayname

    @property
    def href(self):
        return urlappend(canonical_url(self.context, rootsite="feeds"),
                         'branch.atom')

    @classmethod
    def allowFeed(cls, context):
        """See `FeedLinkBase`"""
        # No feeds for private branches.
        return not context.private


class PersonRevisionsFeedLink(FeedLinkBase):
    """Feed links for revisions created by a person."""
    usedfor = IPerson

    @property
    def title(self):
        if self.context.is_team:
            return 'Latest Revisions by members of %s' % (
                self.context.displayname)
        else:
            return 'Latest Revisions by %s' % self.context.displayname

    @property
    def href(self):
        return urlappend(canonical_url(self.context, rootsite="feeds"),
                         'revisions.atom')


class FeedsMixin:
    """Mixin which adds the feed_links attribute to a view object.

    feed_types: This class attribute can be overridden to reduce the
        feed links that are added to the page.

    feed_links: Returns a list of objects subclassed from FeedLinkBase.
    """
    feed_types = (
        AnnouncementsFeedLink,
        BranchFeedLink,
        BugFeedLink,
        BugTargetLatestBugsFeedLink,
        PersonBranchesFeedLink,
        PersonRevisionsFeedLink,
        ProductBranchesFeedLink,
        ProductRevisionsFeedLink,
        ProjectBranchesFeedLink,
        ProjectRevisionsFeedLink,
        RootAnnouncementsFeedLink,
        )

    @property
    def feed_links(self):

        def allowFeed(feed_type, context):
            return (feed_type.usedfor.providedBy(context) and
                feed_type.allowFeed(context))

        return [feed_type(self.context)
            for feed_type in self.feed_types
            if allowFeed(feed_type, self.context)]
