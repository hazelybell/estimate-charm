# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""IPerson browser views related to bugs."""

__metaclass__ = type

__all__ = [
    'BugSubscriberPackageBugsSearchListingView',
    'PersonBugsMenu',
    'PersonCommentedBugTaskSearchListingView',
    'PersonAssignedBugTaskSearchListingView',
    'PersonRelatedBugTaskSearchListingView',
    'PersonReportedBugTaskSearchListingView',
    'PersonStructuralSubscriptionsView',
    'PersonSubscribedBugTaskSearchListingView',
    'PersonSubscriptionsView',
    ]

import copy
from operator import itemgetter
import urllib

from zope.component import getUtility
from zope.schema.vocabulary import getVocabularyRegistry

from lp.app.errors import UnexpectedFormData
from lp.bugs.browser.bugtask import BugTaskSearchListingView
from lp.bugs.interfaces.bugtask import (
    BugTaskStatus,
    IBugTaskSet,
    UNRESOLVED_BUGTASK_STATUSES,
    )
from lp.registry.interfaces.person import IPerson
from lp.registry.model.milestone import (
    Milestone,
    milestone_sort_key,
    )
from lp.services.database.bulk import load_related
from lp.services.feeds.browser import FeedsMixin
from lp.services.helpers import shortlist
from lp.services.propertycache import cachedproperty
from lp.services.webapp.batching import BatchNavigator
from lp.services.webapp.menu import (
    Link,
    NavigationMenu,
    )
from lp.services.webapp.publisher import (
    canonical_url,
    LaunchpadView,
    )


def get_package_search_url(distributionsourcepackage, person_url,
                           advanced=False, extra_params=None):
    """Construct a default search URL for a distributionsourcepackage.

    Optional filter parameters can be specified as a dict with the
    extra_params argument.
    """
    params = {
        "field.distribution": distributionsourcepackage.distribution.name,
        "field.sourcepackagename": distributionsourcepackage.name,
        "search": "Search"}
    if advanced:
        params['advanced'] = '1'

    if extra_params is not None:
        # We must UTF-8 encode searchtext to play nicely with
        # urllib.urlencode, because it may contain non-ASCII characters.
        if 'field.searchtext' in extra_params:
            extra_params["field.searchtext"] = (
                extra_params["field.searchtext"].encode("utf8"))

        params.update(extra_params)

    query_string = urllib.urlencode(sorted(params.items()), doseq=True)

    return person_url + '/+packagebugs-search?%s' % query_string


class PersonBugsMenu(NavigationMenu):

    usedfor = IPerson
    facet = 'bugs'
    links = ['affectingbugs', 'assignedbugs', 'commentedbugs', 'reportedbugs',
             'subscribedbugs', 'relatedbugs', 'softwarebugs']

    def relatedbugs(self):
        text = 'All related bugs'
        summary = ('All bug reports which %s reported, is assigned to, '
                   'or is subscribed to.' % self.context.displayname)
        return Link('', text, site='bugs', summary=summary)

    def assignedbugs(self):
        text = 'Assigned bugs'
        summary = 'Bugs assigned to %s.' % self.context.displayname
        return Link('+assignedbugs', text, site='bugs', summary=summary)

    def softwarebugs(self):
        text = 'Subscribed packages'
        summary = (
            'A summary report for packages where %s is a subscriber.'
            % self.context.displayname)
        return Link('+packagebugs', text, site='bugs', summary=summary)

    def reportedbugs(self):
        text = 'Reported bugs'
        summary = 'Bugs reported by %s.' % self.context.displayname
        enabled = not self.context.is_team
        return Link(
            '+reportedbugs', text, site='bugs', summary=summary,
            enabled=enabled)

    def subscribedbugs(self):
        text = 'Subscribed bugs'
        summary = ('Bug reports %s is subscribed to.'
                   % self.context.displayname)
        return Link('+subscribedbugs', text, site='bugs', summary=summary)

    def commentedbugs(self):
        text = 'Commented bugs'
        summary = ('Bug reports on which %s has commented.'
                   % self.context.displayname)
        enabled = not self.context.is_team
        return Link(
            '+commentedbugs', text, site='bugs', summary=summary,
            enabled=enabled)

    def affectingbugs(self):
        text = 'Affecting bugs'
        summary = ('Bugs affecting %s.' % self.context.displayname)
        enabled = not self.context.is_team
        return Link(
            '+affectingbugs', text, site='bugs', summary=summary,
            enabled=enabled)


class RelevantMilestonesMixin:
    """Mixin to narrow the milestone list to only relevant milestones."""

    def getMilestoneWidgetValues(self):
        """Return data used to render the milestone checkboxes."""
        tasks = self.searchUnbatched()
        milestones = sorted(
            load_related(Milestone, tasks, ['milestoneID']),
            key=milestone_sort_key, reverse=True)
        return [
            dict(title=milestone.title, value=milestone.id, checked=False)
            for milestone in milestones]


class BugSubscriberPackageBugsOverView(LaunchpadView):

    page_title = 'Package bugs'

    @cachedproperty
    def total_bug_counts(self):
        """Return the totals of each type of package bug count as a dict."""
        totals = {
            'open_bugs_count': 0,
            'critical_bugs_count': 0,
            'high_bugs_count': 0,
            'unassigned_bugs_count': 0,
            'inprogress_bugs_count': 0,
            }

        for package_counts in self.package_bug_counts:
            for key in totals.keys():
                totals[key] += int(package_counts[key])

        return totals

    @cachedproperty
    def package_bug_counts(self):
        """Return a list of dicts used for rendering package bug counts."""
        L = []
        package_counts = getUtility(IBugTaskSet).getBugCountsForPackages(
            self.user, self.context.getBugSubscriberPackages())
        person_url = canonical_url(self.context)
        for package_counts in package_counts:
            package = package_counts['package']
            L.append({
                'package_name': package.displayname,
                'package_search_url':
                    get_package_search_url(package, person_url),
                'open_bugs_count': package_counts['open'],
                'open_bugs_url': self.getOpenBugsURL(package, person_url),
                'critical_bugs_count': package_counts['open_critical'],
                'critical_bugs_url': self.getCriticalBugsURL(
                    package, person_url),
                'high_bugs_count': package_counts['open_high'],
                'high_bugs_url': self.getHighBugsURL(package, person_url),
                'unassigned_bugs_count': package_counts['open_unassigned'],
                'unassigned_bugs_url': self.getUnassignedBugsURL(
                    package, person_url),
                'inprogress_bugs_count': package_counts['open_inprogress'],
                'inprogress_bugs_url': self.getInProgressBugsURL(
                    package, person_url),
            })

        return sorted(L, key=itemgetter('package_name'))

    def getOpenBugsURL(self, distributionsourcepackage, person_url):
        """Return the URL for open bugs on distributionsourcepackage."""
        status_params = {'field.status': []}

        for status in UNRESOLVED_BUGTASK_STATUSES:
            status_params['field.status'].append(status.title)

        return get_package_search_url(
            distributionsourcepackage=distributionsourcepackage,
            person_url=person_url,
            extra_params=status_params)

    def getCriticalBugsURL(self, distributionsourcepackage, person_url):
        """Return the URL for critical bugs on distributionsourcepackage."""
        critical_bugs_params = {
            'field.status': [], 'field.importance': "Critical"}

        for status in UNRESOLVED_BUGTASK_STATUSES:
            critical_bugs_params["field.status"].append(status.title)

        return get_package_search_url(
            distributionsourcepackage=distributionsourcepackage,
            person_url=person_url,
            extra_params=critical_bugs_params)

    def getHighBugsURL(self, distributionsourcepackage, person_url):
        """Return URL for high bugs on distributionsourcepackage."""
        high_bugs_params = {
            'field.status': [], 'field.importance': "High"}

        for status in UNRESOLVED_BUGTASK_STATUSES:
            high_bugs_params["field.status"].append(status.title)

        return get_package_search_url(
            distributionsourcepackage=distributionsourcepackage,
            person_url=person_url,
            extra_params=high_bugs_params)

    def getUnassignedBugsURL(self, distributionsourcepackage, person_url):
        """Return the URL for unassigned bugs on distributionsourcepackage."""
        unassigned_bugs_params = {
            "field.status": [], "field.unassigned": "on"}

        for status in UNRESOLVED_BUGTASK_STATUSES:
            unassigned_bugs_params["field.status"].append(status.title)

        return get_package_search_url(
            distributionsourcepackage=distributionsourcepackage,
            person_url=person_url,
            extra_params=unassigned_bugs_params)

    def getInProgressBugsURL(self, distributionsourcepackage, person_url):
        """Return the URL for unassigned bugs on distributionsourcepackage."""
        inprogress_bugs_params = {"field.status": "In Progress"}

        return get_package_search_url(
            distributionsourcepackage=distributionsourcepackage,
            person_url=person_url,
            extra_params=inprogress_bugs_params)


class BugSubscriberPackageBugsSearchListingView(BugTaskSearchListingView):
    """Bugs reported on packages for a bug subscriber."""

    columns_to_show = ["id", "summary", "importance", "status"]
    page_title = 'Package bugs'

    @property
    def current_package(self):
        """Get the package whose bugs are currently being searched."""
        if not (
            self.widgets['distribution'].hasValidInput() and
            self.widgets['distribution'].getInputValue()):
            raise UnexpectedFormData("A distribution is required")
        if not (
            self.widgets['sourcepackagename'].hasValidInput() and
            self.widgets['sourcepackagename'].getInputValue()):
            raise UnexpectedFormData("A sourcepackagename is required")

        distribution = self.widgets['distribution'].getInputValue()
        return distribution.getSourcePackage(
            self.widgets['sourcepackagename'].getInputValue())

    def search(self, searchtext=None):
        distrosourcepackage = self.current_package
        return BugTaskSearchListingView.search(
            self, searchtext=searchtext, context=distrosourcepackage)

    def getMilestoneWidgetValues(self):
        """See `BugTaskSearchListingView`.

        We return only the active milestones on the current distribution
        since any others are irrelevant.
        """
        current_distro = self.current_package.distribution
        vocabulary_registry = getVocabularyRegistry()
        vocabulary = vocabulary_registry.get(current_distro, 'Milestone')

        return shortlist([
            dict(title=milestone.title, value=milestone.token, checked=False)
            for milestone in vocabulary],
            longest_expected=10)

    @cachedproperty
    def person_url(self):
        return canonical_url(self.context)

    def getBugSubscriberPackageSearchURL(self, distributionsourcepackage=None,
                                         advanced=False, extra_params=None):
        """Construct a default search URL for a distributionsourcepackage.

        Optional filter parameters can be specified as a dict with the
        extra_params argument.
        """
        if distributionsourcepackage is None:
            distributionsourcepackage = self.current_package
        return get_package_search_url(
            distributionsourcepackage, self.person_url, advanced,
            extra_params)

    def getBugSubscriberPackageAdvancedSearchURL(self,
                                              distributionsourcepackage=None):
        """Build the advanced search URL for a distributionsourcepackage."""
        return self.getBugSubscriberPackageSearchURL(advanced=True)

    def shouldShowSearchWidgets(self):
        # XXX: Guilherme Salgado 2005-11-05:
        # It's not possible to search amongst the bugs on maintained
        # software, so for now I'll be simply hiding the search widgets.
        return False

    # Methods that customize the advanced search form.
    def getAdvancedSearchButtonLabel(self):
        return "Search bugs in %s" % self.current_package.displayname

    def getSimpleSearchURL(self):
        return get_package_search_url(self.current_package, self.person_url)

    @property
    def label(self):
        return self.getSearchPageHeading()

    @property
    def context_description(self):
        """See `BugTaskSearchListingView`."""
        return ("in %s related to %s" %
                (self.current_package.displayname, self.context.displayname))


class PersonAssignedBugTaskSearchListingView(RelevantMilestonesMixin,
                                             BugTaskSearchListingView):
    """All bugs assigned to someone."""

    columns_to_show = ["id", "summary", "bugtargetdisplayname",
                       "importance", "status"]
    page_title = 'Assigned bugs'
    view_name = '+assignedbugs'

    def searchUnbatched(self, searchtext=None, context=None,
                        extra_params=None):
        """Return the open bugs assigned to a person."""
        if context is None:
            context = self.context

        if extra_params is None:
            extra_params = dict()
        else:
            extra_params = dict(extra_params)
        extra_params['assignee'] = context

        sup = super(PersonAssignedBugTaskSearchListingView, self)
        return sup.searchUnbatched(searchtext, context, extra_params)

    def shouldShowAssigneeWidget(self):
        """Should the assignee widget be shown on the advanced search page?"""
        return False

    def shouldShowTeamPortlet(self):
        """Should the team assigned bugs portlet be shown?"""
        return True

    def shouldShowTagsCombinatorWidget(self):
        """Should the tags combinator widget show on the search page?"""
        return False

    @property
    def context_description(self):
        """See `BugTaskSearchListingView`."""
        return "assigned to %s" % self.context.displayname

    def getSearchPageHeading(self):
        """The header for the search page."""
        return "Bugs %s" % self.context_description

    def getAdvancedSearchButtonLabel(self):
        """The Search button for the advanced search page."""
        return "Search bugs %s" % self.context_description

    def getSimpleSearchURL(self):
        """Return a URL that can be used as an href to the simple search."""
        return canonical_url(self.context, view_name="+assignedbugs")

    @property
    def label(self):
        return self.getSearchPageHeading()


class PersonCommentedBugTaskSearchListingView(RelevantMilestonesMixin,
                                              BugTaskSearchListingView):
    """All bugs commented on by a Person."""

    columns_to_show = ["id", "summary", "bugtargetdisplayname",
                       "importance", "status"]
    page_title = 'Commented bugs'

    def searchUnbatched(self, searchtext=None, context=None,
                        extra_params=None):
        """Return the open bugs commented on by a person."""
        if context is None:
            context = self.context

        if extra_params is None:
            extra_params = dict()
        else:
            extra_params = dict(extra_params)
        extra_params['bug_commenter'] = context

        sup = super(PersonCommentedBugTaskSearchListingView, self)
        return sup.searchUnbatched(searchtext, context, extra_params)

    @property
    def context_description(self):
        """See `BugTaskSearchListingView`."""
        return "commented on by %s" % self.context.displayname

    def getSearchPageHeading(self):
        """The header for the search page."""
        return "Bugs %s" % self.context_description

    def getAdvancedSearchButtonLabel(self):
        """The Search button for the advanced search page."""
        return "Search bugs %s" % self.context_description

    def getSimpleSearchURL(self):
        """Return a URL that can be used as an href to the simple search."""
        return canonical_url(self.context, view_name="+commentedbugs")

    @property
    def label(self):
        return self.getSearchPageHeading()


class PersonAffectingBugTaskSearchListingView(
    RelevantMilestonesMixin, BugTaskSearchListingView):
    """All bugs affecting someone."""

    columns_to_show = ["id", "summary", "bugtargetdisplayname",
                       "importance", "status"]
    view_name = '+affectingbugs'
    page_title = 'Bugs affecting'   # The context is added externally.

    def searchUnbatched(self, searchtext=None, context=None,
                        extra_params=None):
        """Return the open bugs assigned to a person."""
        if context is None:
            context = self.context

        if extra_params is None:
            extra_params = dict()
        else:
            extra_params = dict(extra_params)
        extra_params['affected_user'] = context

        sup = super(PersonAffectingBugTaskSearchListingView, self)
        return sup.searchUnbatched(searchtext, context, extra_params)

    def shouldShowAssigneeWidget(self):
        """Should the assignee widget be shown on the advanced search page?"""
        return False

    def shouldShowTeamPortlet(self):
        """Should the team assigned bugs portlet be shown?"""
        return True

    def shouldShowTagsCombinatorWidget(self):
        """Should the tags combinator widget show on the search page?"""
        return False

    @property
    def context_description(self):
        """See `BugTaskSearchListingView`."""
        return "affecting %s" % self.context.displayname

    def getSearchPageHeading(self):
        """The header for the search page."""
        return "Bugs %s" % self.context_description

    def getAdvancedSearchButtonLabel(self):
        """The Search button for the advanced search page."""
        return "Search bugs %s" % self.context_description

    def getSimpleSearchURL(self):
        """Return a URL that can be used as an href to the simple search."""
        return canonical_url(self.context, view_name=self.view_name)

    @property
    def label(self):
        return self.getSearchPageHeading()


class PersonRelatedBugTaskSearchListingView(RelevantMilestonesMixin,
                                            BugTaskSearchListingView,
                                            FeedsMixin):
    """All bugs related to someone."""

    columns_to_show = ["id", "summary", "bugtargetdisplayname",
                       "importance", "status"]
    page_title = 'Related bugs'

    def searchUnbatched(self, searchtext=None, context=None,
                        extra_params=None):
        """Return the open bugs related to a person.

        :param extra_params: A dict that provides search params added to
            the search criteria taken from the request. Params in
            `extra_params` take precedence over request params.
        """
        if context is None:
            context = self.context

        params = self.buildSearchParams(extra_params=extra_params)
        subscriber_params = copy.copy(params)
        subscriber_params.subscriber = context
        assignee_params = copy.copy(params)
        owner_params = copy.copy(params)
        commenter_params = copy.copy(params)

        # Only override the assignee, commenter and owner if they were not
        # specified by the user.
        if assignee_params.assignee is None:
            assignee_params.assignee = context
        if owner_params.owner is None:
            # Specify both owner and bug_reporter to try to prevent the same
            # bug (but different tasks) being displayed.
            owner_params.owner = context
            owner_params.bug_reporter = context
        if commenter_params.bug_commenter is None:
            commenter_params.bug_commenter = context

        return context.searchTasks(
            assignee_params, subscriber_params, owner_params, commenter_params)

    @property
    def context_description(self):
        """See `BugTaskSearchListingView`."""
        return "related to %s" % self.context.displayname

    def getSearchPageHeading(self):
        return "Bugs %s" % self.context_description

    def getAdvancedSearchButtonLabel(self):
        return "Search bugs %s" % self.context_description

    def getSimpleSearchURL(self):
        return canonical_url(self.context, view_name="+bugs")

    @property
    def label(self):
        return self.getSearchPageHeading()


class PersonReportedBugTaskSearchListingView(RelevantMilestonesMixin,
                                             BugTaskSearchListingView):
    """All bugs reported by someone."""

    columns_to_show = ["id", "summary", "bugtargetdisplayname",
                       "importance", "status"]
    page_title = 'Reported bugs'

    def searchUnbatched(self, searchtext=None, context=None,
                        extra_params=None):
        """Return the bugs reported by a person."""
        if context is None:
            context = self.context

        if extra_params is None:
            extra_params = dict()
        else:
            extra_params = dict(extra_params)
        # Specify both owner and bug_reporter to try to prevent the same
        # bug (but different tasks) being displayed.
        extra_params['owner'] = context
        extra_params['bug_reporter'] = context

        sup = super(PersonReportedBugTaskSearchListingView, self)
        return sup.searchUnbatched(searchtext, context, extra_params)

    @property
    def context_description(self):
        """See `BugTaskSearchListingView`."""
        return "reported by %s" % self.context.displayname

    def getSearchPageHeading(self):
        """The header for the search page."""
        return "Bugs %s" % self.context_description

    def getAdvancedSearchButtonLabel(self):
        """The Search button for the advanced search page."""
        return "Search bugs %s" % self.context_description

    def getSimpleSearchURL(self):
        """Return a URL that can be used as an href to the simple search."""
        return canonical_url(self.context, view_name="+reportedbugs")

    def shouldShowReporterWidget(self):
        """Should the reporter widget be shown on the advanced search page?"""
        return False

    def shouldShowTagsCombinatorWidget(self):
        """Should the tags combinator widget show on the search page?"""
        return False

    @property
    def label(self):
        return self.getSearchPageHeading()


class PersonSubscribedBugTaskSearchListingView(RelevantMilestonesMixin,
                                               BugTaskSearchListingView):
    """All bugs someone is subscribed to."""

    columns_to_show = ["id", "summary", "bugtargetdisplayname",
                       "importance", "status"]
    page_title = 'Subscribed bugs'
    view_name = '+subscribedbugs'

    def searchUnbatched(self, searchtext=None, context=None,
                        extra_params=None):
        """Return the bugs subscribed to by a person."""
        if context is None:
            context = self.context

        if extra_params is None:
            extra_params = dict()
        else:
            extra_params = dict(extra_params)
        extra_params['subscriber'] = context

        sup = super(PersonSubscribedBugTaskSearchListingView, self)
        return sup.searchUnbatched(searchtext, context, extra_params)

    def shouldShowTeamPortlet(self):
        """Should the team subscribed bugs portlet be shown?"""
        return True

    @property
    def context_description(self):
        """See `BugTaskSearchListingView`."""
        return "%s is subscribed to" % self.context.displayname

    def getSearchPageHeading(self):
        """The header for the search page."""
        return "Bugs %s" % self.context_description

    def getAdvancedSearchButtonLabel(self):
        """The Search button for the advanced search page."""
        return "Search bugs %s is Cc'd to" % self.context.displayname

    def getSimpleSearchURL(self):
        """Return a URL that can be used as an href to the simple search."""
        return canonical_url(self.context, view_name="+subscribedbugs")

    @property
    def label(self):
        return self.getSearchPageHeading()


class PersonSubscriptionsView(LaunchpadView):
    """All the subscriptions for a person."""

    page_title = 'Subscriptions'

    def subscribedBugTasks(self):
        """
        Return a BatchNavigator for distinct bug tasks to which the person is
        subscribed.
        """
        bug_tasks = self.context.searchTasks(None, user=self.user,
            order_by='-date_last_updated',
            status=(BugTaskStatus.NEW,
                    BugTaskStatus.INCOMPLETE,
                    BugTaskStatus.CONFIRMED,
                    BugTaskStatus.TRIAGED,
                    BugTaskStatus.INPROGRESS,
                    BugTaskStatus.FIXCOMMITTED,
                    BugTaskStatus.INVALID),
            bug_subscriber=self.context)

        sub_bug_tasks = []
        sub_bugs = set()

        # XXX: GavinPanella 2010-10-08 bug=656904: This materializes the
        # entire result set. It would probably be more efficient implemented
        # with a pre_iter_hook on a DecoratedResultSet.
        for task in bug_tasks:
            # We order the bugtasks by date_last_updated but we always display
            # the default task for the bug. This is to avoid ordering issues
            # in tests and also prevents user confusion (because nothing is
            # more confusing than your subscription targets changing seemingly
            # at random).
            if task.bug not in sub_bugs:
                # XXX: GavinPanella 2010-10-08 bug=656904: default_bugtask
                # causes a query to be executed. It would be more efficient to
                # get the default bugtask in bulk, in a pre_iter_hook on a
                # DecoratedResultSet perhaps.
                sub_bug_tasks.append(task.bug.default_bugtask)
                sub_bugs.add(task.bug)

        return BatchNavigator(sub_bug_tasks, self.request)

    def canUnsubscribeFromBugTasks(self):
        """Can the current user unsubscribe from the bug tasks shown?"""
        return (self.user is not None and
                self.user.inTeam(self.context))

    @property
    def label(self):
        """The header for the subscriptions page."""
        return "Subscriptions for %s" % self.context.displayname


class PersonStructuralSubscriptionsView(LaunchpadView):
    """All the structural subscriptions for a person."""

    page_title = 'Structural subscriptions'

    def canUnsubscribeFromBugTasks(self):
        """Can the current user modify subscriptions for the context?"""
        return (self.user is not None and
                self.user.inTeam(self.context))

    @property
    def label(self):
        """The header for the structural subscriptions page."""
        return "Structural subscriptions for %s" % self.context.displayname
