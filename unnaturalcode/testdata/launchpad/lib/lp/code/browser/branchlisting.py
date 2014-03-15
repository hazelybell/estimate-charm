# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Base class view for branch listings."""

__metaclass__ = type

__all__ = [
    'BranchBadges',
    'BranchListingView',
    'DistributionBranchListingView',
    'DistributionSourcePackageBranchesView',
    'DistroSeriesBranchListingView',
    'GroupedDistributionSourcePackageBranchesView',
    'CodeVHostBreadcrumb',
    'PersonBranchesMenu',
    'PersonCodeSummaryView',
    'PersonOwnedBranchesView',
    'PersonRegisteredBranchesView',
    'PersonSubscribedBranchesView',
    'PersonTeamBranchesView',
    'ProductBranchListingView',
    'ProductBranchesMenu',
    'ProductBranchesView',
    'ProductCodeIndexView',
    'ProjectBranchesView',
    'RecentlyChangedBranchesView',
    'RecentlyImportedBranchesView',
    'RecentlyRegisteredBranchesView',
    'SourcePackageBranchesView',
    ]

from operator import attrgetter
import urlparse

from lazr.delegates import delegates
from lazr.enum import (
    EnumeratedType,
    Item,
    )
from storm.expr import (
    Asc,
    Desc,
    )
from z3c.ptcompat import ViewPageTemplateFile
from zope.component import getUtility
from zope.formlib import form
from zope.interface import (
    implements,
    Interface,
    )
from zope.schema import Choice

from lp import _
from lp.app.browser.badge import (
    Badge,
    HasBadgeBase,
    )
from lp.app.browser.launchpadform import (
    custom_widget,
    LaunchpadFormView,
    )
from lp.app.browser.tales import MenuAPI
from lp.app.enums import (
    PRIVATE_INFORMATION_TYPES,
    ServiceUsage,
    )
from lp.app.widgets.itemswidgets import LaunchpadDropdownWidget
from lp.blueprints.interfaces.specificationbranch import (
    ISpecificationBranchSet,
    )
from lp.bugs.interfaces.bugbranch import IBugBranchSet
from lp.code.browser.branch import BranchMirrorMixin
from lp.code.browser.branchmergeproposallisting import ActiveReviewsView
from lp.code.browser.branchmergequeuelisting import HasMergeQueuesMenuMixin
from lp.code.browser.summary import BranchCountSummaryView
from lp.code.enums import (
    BranchLifecycleStatus,
    BranchLifecycleStatusFilter,
    BranchType,
    )
from lp.code.interfaces.branch import (
    BzrIdentityMixin,
    DEFAULT_BRANCH_STATUS_IN_LISTING,
    IBranch,
    IBranchBatchNavigator,
    IBranchListingQueryOptimiser,
    )
from lp.code.interfaces.branchcollection import IAllBranches
from lp.code.interfaces.branchnamespace import IBranchNamespacePolicy
from lp.code.interfaces.branchtarget import IBranchTarget
from lp.code.interfaces.revision import IRevisionSet
from lp.code.interfaces.revisioncache import IRevisionCache
from lp.code.interfaces.seriessourcepackagebranch import (
    IFindOfficialBranchLinks,
    )
from lp.registry.browser.product import (
    ProductDownloadFileMixin,
    SortSeriesMixin,
    )
from lp.registry.interfaces.person import (
    IPerson,
    IPersonSet,
    )
from lp.registry.interfaces.personproduct import (
    IPersonProduct,
    IPersonProductFactory,
    )
from lp.registry.interfaces.product import IProduct
from lp.registry.interfaces.series import SeriesStatus
from lp.registry.interfaces.sourcepackage import ISourcePackageFactory
from lp.registry.model.sourcepackage import SourcePackage
from lp.services.browser_helpers import get_plural_text
from lp.services.config import config
from lp.services.feeds.browser import (
    FeedsMixin,
    PersonBranchesFeedLink,
    PersonRevisionsFeedLink,
    ProductBranchesFeedLink,
    ProductRevisionsFeedLink,
    ProjectBranchesFeedLink,
    ProjectRevisionsFeedLink,
    )
from lp.services.propertycache import cachedproperty
from lp.services.webapp import (
    ApplicationMenu,
    canonical_url,
    Link,
    )
from lp.services.webapp.authorization import (
    check_permission,
    precache_permission_for_objects,
    )
from lp.services.webapp.batching import TableBatchNavigator
from lp.services.webapp.breadcrumb import Breadcrumb
from lp.services.webapp.publisher import LaunchpadView


class CodeVHostBreadcrumb(Breadcrumb):
    rootsite = 'code'
    text = 'Code'


class BranchBadges(HasBadgeBase):
    badges = "private", "bug", "blueprint", "warning", "mergeproposal"

    def isWarningBadgeVisible(self):
        """Show a warning badge if there are mirror failures."""
        return self.context.mirror_failures > 0

    def getBadge(self, badge_name):
        """See `IHasBadges`."""
        if badge_name == "warning":
            return Badge('/@@/warning', '/@@/warning-large', '',
                         'Branch has errors')
        else:
            return super(BranchBadges, self).getBadge(badge_name)


class BranchListingItem(BzrIdentityMixin, BranchBadges):
    """A decorated branch.

    Some attributes that we want to display are too convoluted or expensive
    to get on the fly for each branch in the listing.  These items are
    prefetched by the view and decorate the branch.
    """
    delegates(IBranch, 'context')

    def __init__(self, branch, last_commit, show_bug_badge,
                 show_blueprint_badge, show_mp_badge,
                 associated_product_series, suite_source_packages):
        BranchBadges.__init__(self, branch)
        self.last_commit = last_commit
        self.show_bug_badge = show_bug_badge
        self.show_blueprint_badge = show_blueprint_badge
        self.show_merge_proposals = show_mp_badge
        self.associated_product_series = associated_product_series
        self.suite_source_packages = suite_source_packages

    def associatedProductSeries(self):
        """Override the IBranch.associatedProductSeries."""
        return self.associated_product_series

    def associatedSuiteSourcePackages(self):
        """Override the IBranch.associatedSuiteSourcePackages."""
        return self.suite_source_packages

    @property
    def active_series(self):
        return [series for series in self.associated_product_series
                if series.status != SeriesStatus.OBSOLETE]

    def isBugBadgeVisible(self):
        return self.show_bug_badge

    def isBlueprintBadgeVisible(self):
        return self.show_blueprint_badge

    def isMergeproposalBadgeVisible(self):
        """Show the merge proposal badge if needed"""
        return self.show_merge_proposals

    @property
    def revision_author(self):
        return self.last_commit.revision_author

    @property
    def revision_number(self):
        return self.context.revision_count

    @property
    def revision_log(self):
        return self.last_commit.log_body

    @property
    def revision_date(self):
        return self.last_commit.revision_date

    @property
    def revision_codebrowse_link(self):
        return self.context.codebrowse_url(
            'revision', str(self.context.revision_count))

    def __repr__(self):
        # For testing purposes.
        return '<BranchListingItem %r (%d)>' % (self.unique_name, self.id)


class BranchListingSort(EnumeratedType):
    """Choices for how to sort branch listings."""

    # XXX: MichaelHudson 2007-10-17 bug=153891: We allow sorting on quantities
    # that are not visible in the listing!

    DEFAULT = Item("""
        by most interesting

        Sort branches by the default ordering for the view.
        """)

    PRODUCT = Item("""
        by project name

        Sort branches by name of the project the branch is for.
        """)

    LIFECYCLE = Item("""
        by status

        Sort branches by their status.
        """)

    NAME = Item("""
        by branch name

        Sort branches by the name of the branch.
        """)

    OWNER = Item("""
        by owner name

        Sort branches by the name of the owner.
        """)

    MOST_RECENTLY_CHANGED_FIRST = Item("""
        most recently changed first

        Sort branches from the most recently to the least recently
        changed.
        """)

    LEAST_RECENTLY_CHANGED_FIRST = Item("""
        most neglected first

        Sort branches from the least recently to the most recently
        changed.
        """)

    NEWEST_FIRST = Item("""
        newest first

        Sort branches from newest to oldest.
        """)

    OLDEST_FIRST = Item("""
        oldest first

        Sort branches from oldest to newest.
        """)


class IBranchListingFilter(Interface):
    """The schema for the branch listing filtering/ordering form."""

    # Stats and status attributes
    lifecycle = Choice(
        title=_('Lifecycle Filter'), vocabulary=BranchLifecycleStatusFilter,
        default=BranchLifecycleStatusFilter.CURRENT,
        description=_(
        "The author's assessment of the branch's maturity. "
        " Mature: recommend for production use."
        " Development: useful work that is expected to be merged eventually."
        " Experimental: not recommended for merging yet, and maybe ever."
        " Merged: integrated into mainline, of historical interest only."
        " Abandoned: no longer considered relevant by the author."
        " New: unspecified maturity."))

    sort_by = Choice(
        title=_('ordered by'), vocabulary=BranchListingSort,
        default=BranchListingSort.LIFECYCLE)


class BranchListingItemsMixin:
    """Mixin class to create BranchListingItems."""

    # Requires the following attributes:
    #   visible_branches_for_view
    def __init__(self, user):
        self._distro_series_map = {}
        self.view_user = user

    def getBranchCollection(self):
        """Should be a user restricted branch collection for the view."""
        raise NotImplementedError(self.getBranchCollection)

    @cachedproperty
    def _query_optimiser(self):
        """Return the branch listing query optimiser utility."""
        return getUtility(IBranchListingQueryOptimiser)

    @cachedproperty
    def _visible_branch_ids(self):
        """Return a list of the branch ids that are visible."""
        return [branch.id for branch in self.visible_branches_for_view]

    @cachedproperty
    def product_series_map(self):
        """Return a map from branch id to a list of product series."""
        series_resultset = self._query_optimiser.getProductSeriesForBranches(
            self._visible_branch_ids)
        result = {}
        for series in series_resultset:
            # Some products may be proprietary or embargoed, and users
            # do not need to have access to them, while they may have
            # artifact grants for the series branch.
            if series.userCanView(self.view_user):
                result.setdefault(series.branch.id, []).append(series)
        return result

    def getProductSeries(self, branch):
        """Get the associated product series for the branch.

        If the branch has more than one associated product series
        they are listed in alphabetical order, unless one of them is
        the current development focus, in which case that comes first.
        """
        series = self.product_series_map.get(branch.id, [])
        if len(series) > 1:
            # Check for development focus.
            dev_focus = branch.product.development_focus
            if dev_focus is not None and dev_focus in series:
                series.remove(dev_focus)
                series.insert(0, dev_focus)
        return series

    @cachedproperty
    def official_package_links_map(self):
        """Return a map from branch id to a list of package links."""
        query_optimiser = self._query_optimiser
        links = query_optimiser.getOfficialSourcePackageLinksForBranches(
            self._visible_branch_ids)
        result = {}
        for link in links:
            result.setdefault(link.branch.id, []).append(link)
        return result

    def getSuiteSourcePackages(self, branch):
        """Get the associated SuiteSourcePackages for the branch.

        If there is more than one, they are sorted by pocket.
        """
        links = [link.suite_sourcepackage for link in
                 self.official_package_links_map.get(branch.id, [])]
        return sorted(links, key=attrgetter('pocket'))

    def getDistroDevelSeries(self, distribution):
        """distribution.currentseries hits the DB every time so cache it."""
        try:
            return self._distro_series_map[distribution]
        except KeyError:
            result = distribution.currentseries
            self._distro_series_map[distribution] = result
            return result

    @cachedproperty
    def branch_ids_with_bug_links(self):
        """Return a set of branch ids that should show bug badges."""
        return set(getUtility(IBugBranchSet).getBranchesWithVisibleBugs(
            self.visible_branches_for_view, self.view_user))

    @cachedproperty
    def branch_ids_with_spec_links(self):
        """Return a set of branch ids that should show blueprint badges."""
        spec_branches = getUtility(
            ISpecificationBranchSet).getSpecificationBranchesForBranches(
            self.visible_branches_for_view, self.view_user)
        return set(spec_branch.branch.id for spec_branch in spec_branches)

    @cachedproperty
    def branch_ids_with_merge_proposals(self):
        """Return a set of branches that should show merge proposal badges.

        Branches have merge proposals badges if they've been proposed for
        merging into another branch (source branches).
        """
        branches = self.visible_branches_for_view
        collection = self.getBranchCollection()
        proposals = collection.getMergeProposals(for_branches=branches)
        return set(proposal.source_branch.id for proposal in proposals)

    @cachedproperty
    def tip_revisions(self):
        """Return a set of branch ids that should show blueprint badges."""
        revisionset = getUtility(IRevisionSet)
        revisions = revisionset.getTipRevisionsForBranches(
            self.visible_branches_for_view)
        if revisions is None:
            revisions = []

        # Key the revisions by revision id.
        revision_map = dict(
            (revision.revision_id, revision) for revision in revisions)

        # Cache display information for authors of branches' respective
        # last revisions.
        getUtility(IPersonSet).getPrecachedPersonsFromIDs(
            [revision.revision_author.personID for revision in revisions],
            need_icon=True)

        # Return a dict keyed on branch id.
        return dict(
            (branch.id, revision_map.get(branch.last_scanned_id))
            for branch in self.visible_branches_for_view)

    def _createItem(self, branch):
        last_commit = self.tip_revisions[branch.id]
        show_bug_badge = branch.id in self.branch_ids_with_bug_links
        show_blueprint_badge = branch.id in self.branch_ids_with_spec_links
        show_mp_badge = branch.id in self.branch_ids_with_merge_proposals
        associated_product_series = self.getProductSeries(branch)
        suite_source_packages = self.getSuiteSourcePackages(branch)
        return BranchListingItem(
            branch, last_commit, show_bug_badge, show_blueprint_badge,
            show_mp_badge, associated_product_series, suite_source_packages)

    def decoratedBranches(self, branches):
        """Return the decorated branches for the branches passed in."""
        return [self._createItem(branch) for branch in branches]


class BranchListingBatchNavigator(TableBatchNavigator,
                                  BranchListingItemsMixin):
    """Batch up the branch listings."""
    implements(IBranchBatchNavigator)

    def __init__(self, view):
        TableBatchNavigator.__init__(
            self, view.getVisibleBranchesForUser(), view.request,
            columns_to_show=view.extra_columns,
            size=config.launchpad.branchlisting_batch_size)
        BranchListingItemsMixin.__init__(self, view.user)
        self.view = view
        self.column_count = 4 + len(view.extra_columns)

    def getBranchCollection(self):
        """See `BranchListingItemsMixin`."""
        return self.view._getCollection().visibleByUser(self.view.user)

    @cachedproperty
    def visible_branches_for_view(self):
        branches = list(self.currentBatch())
        request = self.view.request
        precache_permission_for_objects(request, 'launchpad.View', branches)
        return branches

    @cachedproperty
    def branches(self):
        """Return a list of BranchListingItems."""
        return self.decoratedBranches(self.visible_branches_for_view)

    @property
    def table_class(self):
        # XXX: MichaelHudson 2007-10-18 bug=153894: This means there are two
        # ways of sorting a one-page branch listing, which is a confusing and
        # incoherent.
        if self.has_multiple_pages:
            return "listing"
        else:
            return "listing sortable"


class BranchListingView(LaunchpadFormView, FeedsMixin):
    """A base class for views of branch listings."""
    schema = IBranchListingFilter
    field_names = ['lifecycle', 'sort_by']
    development_focus_branch = None
    show_set_development_focus = False
    custom_widget('lifecycle', LaunchpadDropdownWidget)
    custom_widget('sort_by', LaunchpadDropdownWidget)
    # Showing the series links is only really useful on product listing
    # pages.  Derived views can override this value to have the series links
    # shown in the branch listings.
    show_series_links = False
    extra_columns = []
    label_template = 'Bazaar branches for %(displayname)s'
    # no_sort_by is a sequence of items from the BranchListingSort
    # enumeration to not offer in the sort_by widget.
    no_sort_by = ()

    # Set the feed types to be only the various branches feed links.  The
    # `feed_links` property will screen this list and produce only the feeds
    # appropriate to the context.
    feed_types = (
        ProjectBranchesFeedLink,
        ProjectRevisionsFeedLink,
        ProductBranchesFeedLink,
        ProductRevisionsFeedLink,
        PersonBranchesFeedLink,
        PersonRevisionsFeedLink,
        )

    @property
    def label(self):
        return self.label_template % {
            'displayname': self.context.displayname,
            'title': getattr(self.context, 'title', 'no-title')}

    @property
    def page_title(self):
        """Provide a default for distros and other things without breadcrumbs.
        """
        return self.label

    table_only_template = ViewPageTemplateFile(
        '../templates/branches-table-include.pt')

    @property
    def template(self):
        query_string = self.request.get('QUERY_STRING') or ''
        query_params = urlparse.parse_qs(query_string)
        render_table_only = 'batch_request' in query_params
        if render_table_only:
            return self.table_only_template
        else:
            return super(BranchListingView, self).template

    @property
    def initial_values(self):
        return {'lifecycle': BranchLifecycleStatusFilter.CURRENT}

    @cachedproperty
    def selected_lifecycle_status(self):
        widget = self.widgets['lifecycle']

        if widget.hasValidInput():
            lifecycle_filter = widget.getInputValue()
        else:
            lifecycle_filter = BranchLifecycleStatusFilter.CURRENT

        if lifecycle_filter == BranchLifecycleStatusFilter.ALL:
            return None
        elif lifecycle_filter == BranchLifecycleStatusFilter.CURRENT:
            return DEFAULT_BRANCH_STATUS_IN_LISTING
        else:
            return (BranchLifecycleStatus.items[lifecycle_filter.name], )

    def branches(self):
        """All branches related to this target, sorted for display."""
        # Separate the public property from the underlying virtual method.
        return BranchListingBatchNavigator(self)

    def getVisibleBranchesForUser(self):
        """Get branches visible to the user.

        This method is called from the `BranchListingBatchNavigator` to
        get the branches to show in the listing.
        """
        return self._branches(self.selected_lifecycle_status)

    def hasAnyBranchesVisibleByUser(self):
        """Does the context have any branches that are visible to the user?"""
        return not self.is_branch_count_zero

    def _getCollection(self):
        """Override this to say what branches will be in the listing."""
        raise NotImplementedError(self._getCollection)

    @cachedproperty
    def branch_count(self):
        """The number of total branches the user can see."""
        return self._getCollection().visibleByUser(self.user).count()

    @cachedproperty
    def is_branch_count_zero(self):
        """Is the number of total branches the user can see zero?."""
        # If the batch itself is not empty, we don't need to check
        # the whole collection count (it might be expensive to compute if the
        # total number of branches is huge).
        return (
            len(self.branches().visible_branches_for_view) == 0 and
            not self.branch_count)

    def _branches(self, lifecycle_status):
        """Return a sequence of branches.

        This method is overridden in the derived classes to perform the
        specific query.

        :param lifecycle_status: A filter of the branch's lifecycle status.
        """
        collection = self._getCollection()
        if lifecycle_status is not None:
            collection = collection.withLifecycleStatus(*lifecycle_status)
        collection = collection.visibleByUser(self.user)
        return collection.getBranches(eager_load=False).order_by(
            self._listingSortToOrderBy(self.sort_by))

    @property
    def no_branch_message(self):
        """This may also be overridden in derived classes to provide
        context relevant messages if there are no branches returned."""
        if (self.selected_lifecycle_status is not None
            and self.hasAnyBranchesVisibleByUser()):
            message = (
                'There are branches related to %s but none of them match the '
                'current filter criteria for this page. '
                'Try filtering on "Any Status".')
        else:
            message = (
                'There are no branches related to %s '
                'in Launchpad today. You can use Launchpad as a registry for '
                'Bazaar branches, and encourage broader community '
                'participation in your project using '
                'distributed version control.')
        return message % self.context.displayname

    @property
    def branch_listing_sort_values(self):
        """The enum items we should present in the 'sort_by' widget.

        Subclasses get the chance to avoid some sort options (it makes no
        sense to offer to sort the product branch listing by product name!)
        and if we're filtering to a single lifecycle status it doesn't make
        much sense to sort by lifecycle.
        """
        # This is pretty painful.
        # First we find the items which are not excluded for this view.
        vocab_items = [item for item in BranchListingSort.items.items
                       if item not in self.no_sort_by]
        # Finding the value of the lifecycle_filter widget is awkward as we do
        # this when the widgets are being set up.  We go digging in the
        # request.
        lifecycle_field = IBranchListingFilter['lifecycle']
        name = self.prefix + '.' + lifecycle_field.__name__
        form_value = self.request.form.get(name)
        if form_value is not None:
            try:
                status_filter = BranchLifecycleStatusFilter.getTermByToken(
                    form_value).value
            except LookupError:
                # We explicitly support bogus values in field.lifecycle --
                # they are treated the same as "CURRENT", which includes more
                # than one lifecycle.
                pass
            else:
                if status_filter not in (BranchLifecycleStatusFilter.ALL,
                                         BranchLifecycleStatusFilter.CURRENT):
                    vocab_items.remove(BranchListingSort.LIFECYCLE)
        return vocab_items

    @property
    def sort_by_field(self):
        """The zope.schema field for the 'sort_by' widget."""
        orig_field = IBranchListingFilter['sort_by']
        values = self.branch_listing_sort_values
        return Choice(__name__=orig_field.__name__,
                      title=orig_field.title,
                      required=True, values=values, default=values[0])

    @property
    def sort_by(self):
        """The value of the `sort_by` widget, or None if none was present."""
        widget = self.widgets['sort_by']
        if widget.hasValidInput():
            return widget.getInputValue()
        else:
            # If a derived view has specified a default sort_by, use that.
            return self.initial_values.get('sort_by')

    @staticmethod
    def _listingSortToOrderBy(sort_by):
        """Compute a value to pass as orderBy to Branch.select().

        :param sort_by: an item from the BranchListingSort enumeration.
        """
        from lp.code.model.branch import Branch

        DEFAULT_BRANCH_LISTING_SORT = [
            BranchListingSort.PRODUCT,
            BranchListingSort.LIFECYCLE,
            BranchListingSort.OWNER,
            BranchListingSort.NAME,
            ]

        LISTING_SORT_TO_COLUMN = {
            BranchListingSort.PRODUCT: (Asc, Branch.target_suffix),
            BranchListingSort.LIFECYCLE: (Desc, Branch.lifecycle_status),
            BranchListingSort.NAME: (Asc, Branch.name),
            BranchListingSort.OWNER: (Asc, Branch.owner_name),
            BranchListingSort.MOST_RECENTLY_CHANGED_FIRST: (
                Desc, Branch.date_last_modified),
            BranchListingSort.LEAST_RECENTLY_CHANGED_FIRST: (
                Asc, Branch.date_last_modified),
            BranchListingSort.NEWEST_FIRST: (Desc, Branch.date_created),
            BranchListingSort.OLDEST_FIRST: (Asc, Branch.date_created),
            }

        order_by = map(
            LISTING_SORT_TO_COLUMN.get, DEFAULT_BRANCH_LISTING_SORT)

        if sort_by is not None and sort_by != BranchListingSort.DEFAULT:
            direction, column = LISTING_SORT_TO_COLUMN[sort_by]
            order_by = (
                [(direction, column)] +
                [sort for sort in order_by if sort[1] is not column])
        return [direction(column) for direction, column in order_by]

    def setUpWidgets(self, context=None):
        """Set up the 'sort_by' widget with only the applicable choices."""
        fields = []
        for field_name in self.field_names:
            if field_name == 'sort_by':
                field = form.FormField(self.sort_by_field)
            else:
                field = self.form_fields[field_name]
            fields.append(field)
        self.form_fields = form.Fields(*fields)
        super(BranchListingView, self).setUpWidgets(context)

    @cachedproperty
    def default_information_type(self):
        """The default information type for new branches."""
        if self.user is None:
            return None
        target = IBranchTarget(self.context)
        if target is None:
            return False
        namespace = target.getNamespace(self.user)
        policy = IBranchNamespacePolicy(namespace)
        return policy.getDefaultInformationType(self.user)

    @property
    def default_information_type_title(self):
        """The title of the default information type for new branches."""
        information_type = self.default_information_type
        if information_type is None:
            return None
        return information_type.title

    @property
    def default_information_type_is_private(self):
        """The title of the default information type for new branches."""
        return self.default_information_type in PRIVATE_INFORMATION_TYPES


class NoContextBranchListingView(BranchListingView):
    """A branch listing that has no associated product or person."""

    field_names = ['lifecycle']
    no_sort_by = (BranchListingSort.DEFAULT, )

    no_branch_message = (
        'There are no branches that match the current status filter.')
    extra_columns = ('author', 'product', 'date_created')

    def _branches(self, lifecycle_status):
        """Return a sequence of branches.

        Override the default behaviour to not join across Owner and Product.

        :param lifecycle_status: A filter of the branch's lifecycle status.
        """
        collection = self._getCollection()
        if lifecycle_status is not None:
            collection = collection.withLifecycleStatus(*lifecycle_status)
        collection = collection.visibleByUser(self.user)
        return collection.getBranches(eager_load=False).order_by(
            self._branch_order)


class RecentlyRegisteredBranchesView(NoContextBranchListingView):
    """A batched view of branches orded by registration date."""

    page_title = 'Recently registered branches'

    @property
    def _branch_order(self):
        from lp.code.model.branch import Branch
        return Desc(Branch.date_created), Desc(Branch.id)

    def _getCollection(self):
        return getUtility(IAllBranches)


class RecentlyImportedBranchesView(NoContextBranchListingView):
    """A batched view of imported branches ordered by last modifed time."""

    page_title = 'Recently imported branches'
    extra_columns = ('product', 'date_created')

    @property
    def _branch_order(self):
        from lp.code.model.branch import Branch
        return Desc(Branch.date_last_modified), Desc(Branch.id)

    def _getCollection(self):
        return (getUtility(IAllBranches)
                .withBranchType(BranchType.IMPORTED)
                .scanned())


class RecentlyChangedBranchesView(NoContextBranchListingView):
    """Batched view of non-imported branches ordered by last modified time."""

    page_title = 'Recently changed branches'

    @property
    def _branch_order(self):
        from lp.code.model.branch import Branch
        return Desc(Branch.date_last_modified), Desc(Branch.id)

    def _getCollection(self):
        return (getUtility(IAllBranches)
                .withBranchType(BranchType.HOSTED, BranchType.MIRRORED)
                .scanned())


class PersonBranchesMenu(ApplicationMenu, HasMergeQueuesMenuMixin):

    usedfor = IPerson
    facet = 'branches'
    links = ['registered', 'owned', 'subscribed',
             'active_reviews', 'mergequeues', 'source_package_recipes']
    extra_attributes = ['mergequeue_count']

    @property
    def person(self):
        """The `IPerson` for the context of the view.

        In simple cases this is the context itself, but in others, like the
        PersonProduct, it is an attribute of the context.
        """
        return self.context

    def owned(self):
        return Link(
            canonical_url(self.context, rootsite='code'), 'Owned branches')

    def registered(self):
        enabled = not self.person.is_team
        return Link(
            '+registeredbranches', 'Registered branches', enabled=enabled)

    def subscribed(self):
        return Link('+subscribedbranches', 'Subscribed branches')

    def active_reviews(self):
        return Link('+activereviews', 'Active reviews')

    def source_package_recipes(self):
        return Link(
            '+recipes', 'Source package recipes',
            enabled=IPerson.providedBy(self.context))


class PersonProductBranchesMenu(PersonBranchesMenu):

    usedfor = IPersonProduct
    links = ['registered', 'owned', 'subscribed', 'active_reviews',
             'source_package_recipes']

    @property
    def person(self):
        """See `PersonBranchesMenu`."""
        return self.context.person


class PersonBaseBranchListingView(BranchListingView):
    """Base class used for different person listing views."""

    @property
    def show_action_menu(self):
        if self.user is not None:
            return self.user.inTeam(self.context)
        return False

    @property
    def show_junk_directions(self):
        return self.user == self.context

    @property
    def initial_values(self):
        values = super(PersonBaseBranchListingView, self).initial_values
        values['sort_by'] = BranchListingSort.MOST_RECENTLY_CHANGED_FIRST
        return values

    @property
    def no_branch_message(self):
        if (self.selected_lifecycle_status is not None
            and self.hasAnyBranchesVisibleByUser()):
            message = (
                'There are branches related to %s but none of them match the '
                'current filter criteria for this page. '
                'Try filtering on "Any Status".')
        else:
            message = (
                'There are no branches related to %s '
                'in Launchpad today.')
        return message % self.context.displayname


class PersonRegisteredBranchesView(PersonBaseBranchListingView):
    """View for branch listing for a person's registered branches."""

    page_title = _('Registered')
    label_template = 'Bazaar branches registered by %(displayname)s'
    no_sort_by = (BranchListingSort.DEFAULT, BranchListingSort.OWNER)

    def _getCollection(self):
        return getUtility(IAllBranches).registeredBy(self.context)


class PersonOwnedBranchesView(PersonBaseBranchListingView):
    """View for branch listing for a person's owned branches."""

    page_title = _('Owned')
    label_template = 'Bazaar branches owned by %(displayname)s'
    no_sort_by = (BranchListingSort.DEFAULT, BranchListingSort.OWNER)

    def _getCollection(self):
        return getUtility(IAllBranches).ownedBy(self.context)


class PersonSubscribedBranchesView(PersonBaseBranchListingView):
    """View for branch listing for a person's subscribed branches."""

    page_title = _('Subscribed')
    label_template = 'Bazaar branches subscribed to by %(displayname)s'
    no_sort_by = (BranchListingSort.DEFAULT, )

    def _getCollection(self):
        return getUtility(IAllBranches).subscribedBy(self.context)


class PersonTeamBranchesView(LaunchpadView):
    """View for team branches portlet."""

    def _getCollection(self):
        """The collection of branches to use to look for team branches."""
        return getUtility(IAllBranches).visibleByUser(self.user)

    def _createItem(self, team):
        """Return a dict of the team, and the thing to get the URL from.

        This dict is used to build the list shown to the user.  Since we don't
        want a particular url formatter for a PersonProduct, we have the url
        separately.
        """
        return {'team': team, 'url_provider': team}

    @property
    def person(self):
        return self.context

    @cachedproperty
    def teams_with_branches(self):
        teams = self._getCollection().getTeamsWithBranches(self.person)
        return [self._createItem(team) for team in teams
                if check_permission('launchpad.View', team)]


class PersonProductTeamBranchesView(PersonTeamBranchesView):
    """View for teams that the person is in with related product branches."""

    def _getCollection(self):
        """Use a collection restricted on on the product."""
        return getUtility(IAllBranches).visibleByUser(self.user).inProduct(
                self.context.product)

    def _createItem(self, team):
        """Return a tuple of the team, and the thing to get the URL from."""
        return {
            'team': team,
            'url_provider': getUtility(IPersonProductFactory).create(
                team, self.context.product)}

    @property
    def person(self):
        return self.context.person


class PersonCodeSummaryView(LaunchpadView):
    """A view to render the code page summary for a person."""


class PersonProductCodeSummaryView(PersonCodeSummaryView):
    """A view to render the code page summary for a `PersonProduct`."""

    @property
    def person(self):
        """Return the person from the context."""
        return self.context.person


class ProductBranchesMenu(ApplicationMenu):

    usedfor = IProduct
    facet = 'branches'
    links = [
        'list_branches',
        'active_reviews',
        'code_import',
        ]
    extra_attributes = [
        'active_review_count',
        ]

    def list_branches(self):
        text = 'List branches'
        summary = 'List the branches for this project'
        return Link('+branches', text, summary, icon='add', site='code')

    @cachedproperty
    def active_review_count(self):
        """Return the number of active reviews for the user."""
        active_reviews = ActiveReviewsView(self.context, self.request)
        return active_reviews.getProposals().count()

    def active_reviews(self):
        text = get_plural_text(
            self.active_review_count,
            'Active review',
            'Active reviews')
        return Link('+activereviews', text, site='code')

    def code_import(self):
        text = 'Import a branch'
        return Link('+new-import', text, icon='add', site='code')


class ProductBranchListingView(BranchListingView):
    """A base class for product branch listings."""

    show_series_links = True
    no_sort_by = (BranchListingSort.PRODUCT, )
    label_template = 'Bazaar branches of %(displayname)s'

    def _getCollection(self):
        return getUtility(IAllBranches).inProduct(self.context)

    @cachedproperty
    def development_focus_branch(self):
        dev_focus_branch = self.context.development_focus.branch
        if dev_focus_branch is None:
            return None
        elif check_permission('launchpad.View', dev_focus_branch):
            return dev_focus_branch
        else:
            return None

    @property
    def no_branch_message(self):
        if (self.selected_lifecycle_status is not None
            and self.hasAnyBranchesVisibleByUser()):
            message = (
                'There are branches registered for %s '
                'but none of them match the current filter criteria '
                'for this page. Try filtering on "Any Status".')
        else:
            message = (
                'There are no branches registered for %s '
                'in Launchpad today. We recommend you visit '
                'www.bazaar-vcs.org '
                'for more information about how you can use the Bazaar '
                'revision control system to improve community participation '
                'in this project.')
        return message % self.context.displayname

    def can_configure_branches(self):
        """Whether or not the user can configure branches."""
        return check_permission("launchpad.Edit", self.context)


class ProductBranchStatisticsView(BranchCountSummaryView,
                                  ProductBranchListingView):
    """Portlet containing branch statistics."""

    @property
    def branch_text(self):
        text = super(ProductBranchStatisticsView, self).branch_text
        return text.capitalize()

    @property
    def commit_text(self):
        text = super(ProductBranchStatisticsView, self).commit_text
        return text.capitalize()


class ProductCodeIndexView(ProductBranchListingView, SortSeriesMixin,
                           ProductDownloadFileMixin, BranchMirrorMixin):
    """Initial view for products on the code virtual host."""

    show_set_development_focus = True

    def initialize(self):
        ProductBranchListingView.initialize(self)
        revision_cache = getUtility(IRevisionCache)
        self.revision_cache = revision_cache.inProduct(self.context)

    @property
    def branch(self):
        return self.development_focus_branch

    @property
    def form_action(self):
        return "+branches"

    @property
    def initial_values(self):
        return {
            'lifecycle': BranchLifecycleStatusFilter.CURRENT,
            'sort_by': BranchListingSort.DEFAULT,
            }

    @cachedproperty
    def commit_count(self):
        """The number of new revisions in the last 30 days."""
        return self.revision_cache.count()

    @cachedproperty
    def committer_count(self):
        """The number of committers in the last 30 days."""
        return self.revision_cache.authorCount()

    @cachedproperty
    def _branch_owners(self):
        """The owners of branches."""
        # Listify the owners, there really shouldn't be that many for any
        # one project.
        return list(getUtility(IPersonSet).getPeopleWithBranches(
            product=self.context))

    @cachedproperty
    def person_owner_count(self):
        """The number of individual people who own branches."""
        return len([person for person in self._branch_owners
                    if not person.is_team])

    @cachedproperty
    def team_owner_count(self):
        """The number of teams who own branches."""
        return len([person for person in self._branch_owners
                    if person.is_team])

    def _getSeriesBranches(self):
        """Get the series branches for the product, dev focus first."""
        # We want to show each series branch only once, always show the
        # development focus branch, no matter what's it lifecycle status, and
        # skip subsequent series where the lifecycle status is Merged or
        # Abandoned
        sorted_series = self.sorted_active_series_list

        def show_branch(branch):
            if self.selected_lifecycle_status is None:
                return True
            else:
                return (branch.lifecycle_status in
                    self.selected_lifecycle_status)
        # The series will always have at least one series, that of the
        # development focus.
        dev_focus_branch = sorted_series[0].branch
        if not check_permission('launchpad.View', dev_focus_branch):
            dev_focus_branch = None
        result = []
        if dev_focus_branch is not None and show_branch(dev_focus_branch):
            result.append(dev_focus_branch)
        for series in sorted_series[1:]:
            branch = series.branch
            if (branch is not None and
                branch not in result and
                check_permission('launchpad.View', branch) and
                show_branch(branch)):
                result.append(branch)
        return result

    @cachedproperty
    def initial_branches(self):
        """Return the series branches, followed by most recently changed."""
        series_branches = self._getSeriesBranches()
        branch_query = super(ProductCodeIndexView, self)._branches(
            self.selected_lifecycle_status)
        branch_query.order_by(self._listingSortToOrderBy(
            BranchListingSort.MOST_RECENTLY_CHANGED_FIRST))
        # We don't want the initial branch listing to be batched, so only get
        # the batch size - the number of series_branches.
        batch_size = config.launchpad.branchlisting_batch_size
        max_branches_from_query = batch_size - len(series_branches)
        # We want to make sure that the series branches do not appear
        # in our branch list.
        branches = [
            branch for branch in branch_query[:max_branches_from_query]
            if branch not in series_branches]
        series_branches.extend(branches)
        return series_branches

    def _branches(self, lifecycle_status):
        """Return the series branches, followed by most recently changed."""
        # The params are ignored, and only used by the listing view.
        return self.initial_branches

    @property
    def unseen_branch_count(self):
        """How many branches are not shown."""
        return self.branch_count - len(self.initial_branches)

    def hasAnyBranchesVisibleByUser(self):
        """See `BranchListingView`."""
        return self.branch_count > 0

    @property
    def has_development_focus_branch(self):
        """Is there a branch assigned as development focus?"""
        return self.development_focus_branch is not None

    @property
    def branch_text(self):
        return get_plural_text(self.branch_count, _('branch'), _('branches'))

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

    @property
    def configure_codehosting(self):
        """Get the menu link for configuring code hosting."""
        if not check_permission(
            'launchpad.Edit', self.context.development_focus):
            return None
        series_menu = MenuAPI(self.context.development_focus).overview
        set_branch = series_menu['set_branch']
        set_branch.text = 'Configure code hosting'
        return set_branch

    @property
    def external_visible(self):
        return (
            self.context.codehosting_usage == ServiceUsage.EXTERNAL
            and self.branch)


class ProductBranchesView(ProductBranchListingView):
    """View for branch listing for a product."""

    def initialize(self):
        """Conditionally redirect to the default view.

        If the branch listing requests the default listing, redirect to the
        default view for the product.
        """
        ProductBranchListingView.initialize(self)
        if self.sort_by == BranchListingSort.DEFAULT:
            redirect_url = canonical_url(self.context)
            widget = self.widgets['lifecycle']
            if widget.hasValidInput():
                redirect_url += (
                    '?field.lifecycle=' + widget.getInputValue().name)
            self.request.response.redirect(redirect_url)

    @property
    def initial_values(self):
        return {
            'lifecycle': BranchLifecycleStatusFilter.CURRENT,
            'sort_by': BranchListingSort.LIFECYCLE,
            }


class ProjectBranchesView(BranchListingView):
    """View for branch listing for a project."""

    no_sort_by = (BranchListingSort.DEFAULT, )
    extra_columns = ('author', 'product')
    label_template = 'Bazaar branches of %(displayname)s'
    show_series_links = True

    def _getCollection(self):
        return getUtility(IAllBranches).inProject(self.context)

    @property
    def no_branch_message(self):
        if (self.selected_lifecycle_status is not None
            and self.hasAnyBranchesVisibleByUser()):
            message = (
                'There are branches registered for %s '
                'but none of them match the current filter criteria '
                'for this page. Try filtering on "Any Status".')
        else:
            message = (
                'There are no branches registered for %s '
                'in Launchpad today. We recommend you visit '
                'www.bazaar-vcs.org '
                'for more information about how you can use the Bazaar '
                'revision control system to improve community participation '
                'in this project group.')
        return message % self.context.displayname


class BaseSourcePackageBranchesView(BranchListingView):
    """A simple base view for package branch listings."""

    no_sort_by = (BranchListingSort.DEFAULT, BranchListingSort.PRODUCT)

    @property
    def initial_values(self):
        values = super(BaseSourcePackageBranchesView, self).initial_values
        values['sort_by'] = BranchListingSort.MOST_RECENTLY_CHANGED_FIRST
        return values


class DistributionSourcePackageBranchesView(BaseSourcePackageBranchesView):
    """A general listing of all branches in the distro source package."""

    label_template = 'Bazaar branches for %(title)s'

    def _getCollection(self):
        return getUtility(IAllBranches).inDistributionSourcePackage(
            self.context)


class DistributionBranchListingView(BaseSourcePackageBranchesView):
    """A general listing of all branches in the distribution."""

    def _getCollection(self):
        return getUtility(IAllBranches).inDistribution(self.context)


class DistroSeriesBranchListingView(BaseSourcePackageBranchesView):
    """A general listing of all branches in the distro source package."""

    def _getCollection(self):
        return getUtility(IAllBranches).inDistroSeries(self.context)


class GroupedDistributionSourcePackageBranchesView(LaunchpadView,
                                                   BranchListingItemsMixin):
    """A view that groups branches into distro series."""

    @property
    def label(self):
        return 'Bazaar branches for %s' % self.context.title

    page_title = label

    def __init__(self, context, request):
        LaunchpadView.__init__(self, context, request)
        BranchListingItemsMixin.__init__(self, self.user)

    def getBranchCollection(self):
        """See `BranchListingItemsMixin`."""
        return getUtility(IAllBranches).inDistributionSourcePackage(
            self.context).visibleByUser(self.user)

    def _getBranchDict(self):
        """Return a dict of branches grouped by distroseries."""
        branches = {}
        # We're only interested in active branches.
        collection = self.getBranchCollection().withLifecycleStatus(
            *DEFAULT_BRANCH_STATUS_IN_LISTING)
        for branch in collection.getBranches(eager_load=False):
            branches.setdefault(branch.distroseries, []).append(branch)
        return branches

    def _getOfficialBranches(self):
        """Get all the official branches for the distro source package.

        Return a dict of distro series to a list of branches.

        The branches are ordered by official pocket.
        """
        link_set = getUtility(IFindOfficialBranchLinks)
        links = link_set.findForDistributionSourcePackage(self.context)
        # Remember it is possible that the linked branch is not visible by the
        # user.  Unlikely, but possible.
        visible_links = [
            link for link in links
            if check_permission('launchpad.View', link.branch)]
        # Sort into distroseries.
        distro_links = {}
        for link in visible_links:
            distro_links.setdefault(link.distroseries, []).append(link)
        # For each distro series, we only want the "best" pocket if one branch
        # is linked to more than one pocket.  Best here means smaller value.
        official_branches = {}
        for key, value in distro_links.iteritems():
            ordered = sorted(value, key=attrgetter('pocket'))
            seen_branches = set()
            branches = []
            for link in ordered:
                if link.branch not in seen_branches:
                    branches.append(link.branch)
                    seen_branches.add(link.branch)
            official_branches[key] = branches
        return official_branches

    def _getSeriesBranches(self, official_branches, branches):
        """Return the "best" five branches."""
        # Sort the branches by the last modified date, and ignore any that are
        # official.
        ordered_branches = sorted(
            [branch for branch in branches
             if branch not in official_branches],
            key=attrgetter('date_last_modified'), reverse=True)
        num_branches = len(ordered_branches)
        num_official = len(official_branches)
        # We want to show at most five branches, with (at most) the most
        # recently touched three non-official branch.
        official_count = 5 - min(num_branches, 3)
        # Top up with non-official branches.
        branches = official_branches[0:official_count] + ordered_branches
        # And chop off at 5.
        branches = branches[0:5]

        more_count = num_branches + num_official - len(branches)
        return branches, more_count

    @cachedproperty
    def series_branches_map(self):
        """Return a dict of tuples for branches in the distroseries.

        The tuple contains the branches, and the 'more_count'.
        """
        series_branches = {}
        all_branches = self._getBranchDict()
        official_branches = self._getOfficialBranches()
        for series in self.context.distribution.series:
            if series in all_branches:
                branches, more_count = self._getSeriesBranches(
                    official_branches.get(series, []),
                    all_branches.get(series, []))
                series_branches[series] = (branches, more_count)
        return series_branches

    @cachedproperty
    def visible_branches_for_view(self):
        """All the branches we are going to show with this view.

        Used by the mixin class to get all the associated bugs, blueprints,
        and merge proposal links for badges.
        """
        visible_branches = []
        for branches, count in self.series_branches_map.itervalues():
            visible_branches.extend(branches)
        return visible_branches

    @cachedproperty
    def branch_count(self):
        """The number of total branches the user can see."""
        return len(self.visible_branches_for_view)

    @cachedproperty
    def groups(self):
        """Return a list of dicts containing series and branches.

        The list is ordered so the most recent distro series is first.

        The list contains dicts.  The dict has the values:
          * distroseries - a `IDistroSeries` object
          * branches - an ordered list of branches
          * more-branch-count - a count of additional branches
          * package - the `ISourcePackage` for the distroseries,
              sourcepackagename pair
          * total-count-string - a string saying the number of branches.

        The branches list will contain at most five branches.  If there are
        non-official branches associated with the distroseries, then there
        will always be some non-official branches shown in the summary even if
        there are five different official branches (for the different
        pockets).

        The official branches are sorted based on PackagePublishingPocket, and
        the non-official branches are sorted on date last modified.
        """
        result = []
        series_branches_map = self.series_branches_map
        sp_factory = getUtility(ISourcePackageFactory)
        for series in self.context.distribution.series:
            if series in series_branches_map:
                branches, more_count = series_branches_map[series]
                sourcepackage = sp_factory.new(
                    self.context.sourcepackagename, series)
                num_branches = len(branches) + more_count
                num_branches_text = get_plural_text(
                    num_branches, "branch", "branches")
                count_string = "%s %s" % (num_branches, num_branches_text)
                result.append(
                    {'distroseries': series,
                     'branches': self.decoratedBranches(branches),
                     'more-branch-count': more_count,
                     'package': sourcepackage,
                     'total-count-string': count_string,
                     })
        return result


class SourcePackageBranchesView(BranchListingView):

    label_template = 'Bazaar branches of %(displayname)s'

    # XXX: JonathanLange 2009-03-03 spec=package-branches: This page has no
    # menu yet -- do we need one?

    # XXX: JonathanLange 2009-03-03 spec=package-branches: Add a link to
    # register a branch. This requires there to be a package branch
    # registration page.

    no_sort_by = (BranchListingSort.DEFAULT, BranchListingSort.PRODUCT)

    def _getCollection(self):
        return getUtility(IAllBranches).inSourcePackage(self.context)

    def _numBranchesInPackage(self, package):
        branches = IBranchTarget(package).collection
        return branches.visibleByUser(self.user).count()

    @property
    def series_links(self):
        """Links to other series in the same distro as the package."""
        our_series = self.context.distroseries
        our_sourcepackagename = self.context.sourcepackagename
        distribution = self.context.distribution
        for series in distribution.series:
            if not series.active:
                continue
            if distribution.currentseries == series:
                dev_focus_css = 'sourcepackage-dev-focus'
            else:
                dev_focus_css = 'sourcepackage-not-dev-focus'
            package = SourcePackage(our_sourcepackagename, series)
            # XXX: JonathanLange 2009-05-13 bug=376295: This approach is
            # inefficient. We should instead do something like:
            #
            #   SELECT distroseries, COUNT(id)
            #   FROM Branch
            #   WHERE distroseries IS NOT NULL
            #   AND sourcepackagename = ?
            #   GROUP BY distroseries
            #
            # It's not too bad though, since the number of active series is
            # generally less than 5.
            num_branches = self._numBranchesInPackage(package)
            num_branches_text = get_plural_text(
                num_branches, "branch", "branches")
            yield dict(
                series_name=series.displayname,
                package=package,
                num_branches='%s %s' % (num_branches, num_branches_text),
                dev_focus_css=dev_focus_css,
                linked=(series != our_series))


class PersonProductBaseBranchesView(PersonBaseBranchListingView):
    """A base view used for other person-product branch listings."""

    no_sort_by = (BranchListingSort.DEFAULT, BranchListingSort.PRODUCT)
    show_action_menu = False

    @property
    def person(self):
        """Return the person from the PersonProduct context."""
        return self.context.person

    @property
    def label(self):
        return self.label_template % {
            'person': self.context.person.displayname,
            'product': self.context.product.displayname}

    @property
    def no_branch_message(self):
        """Provide a more appropriate message for no branches."""
        if (self.selected_lifecycle_status is not None
            and self.hasAnyBranchesVisibleByUser()):
            message = (
                'There are branches of %s owned by %s but none of them '
                'match the current filter criteria for this page. '
                'Try filtering on "Any Status".')
        else:
            message = (
                'There are no branches of %s owned by %s in Launchpad today.')
        return message % (
            self.context.product.displayname, self.context.person.displayname)


class PersonProductOwnedBranchesView(PersonProductBaseBranchesView):
    """Branch listing for a person's owned branches of a product."""

    no_sort_by = (BranchListingSort.DEFAULT,
                  BranchListingSort.OWNER,
                  BranchListingSort.PRODUCT)

    label_template = 'Bazaar Branches of %(product)s owned by %(person)s'

    def _getCollection(self):
        return getUtility(IAllBranches).ownedBy(
            self.context.person).inProduct(self.context.product)


class PersonProductRegisteredBranchesView(PersonProductBaseBranchesView):
    """Branch listing for a person's registered branches of a product."""

    label_template = (
        'Bazaar Branches of %(product)s registered by %(person)s')

    def _getCollection(self):
        return getUtility(IAllBranches).registeredBy(
            self.context.person).inProduct(self.context.product)


class PersonProductSubscribedBranchesView(PersonProductBaseBranchesView):
    """Branch listing for a person's subscribed branches of a product."""

    label_template = (
        'Bazaar Branches of %(product)s subscribed to by %(person)s')

    def _getCollection(self):
        return getUtility(IAllBranches).subscribedBy(
            self.context.person).inProduct(self.context.product)
