# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Implementations of `IBranchCollection`."""

__metaclass__ = type
__all__ = [
    'GenericBranchCollection',
    ]

from collections import defaultdict
from functools import partial
from operator import attrgetter

from lazr.uri import (
    InvalidURIError,
    URI,
    )
from storm.expr import (
    And,
    Count,
    Desc,
    In,
    Join,
    LeftJoin,
    Select,
    SQL,
    With,
    )
from storm.info import ClassAlias
from storm.store import EmptyResultSet
from zope.component import getUtility
from zope.interface import implements

from lp.app.enums import PRIVATE_INFORMATION_TYPES
from lp.bugs.interfaces.bugtask import IBugTaskSet
from lp.bugs.interfaces.bugtaskfilter import filter_bugtasks_by_context
from lp.bugs.interfaces.bugtasksearch import BugTaskSearchParams
from lp.bugs.model.bugbranch import BugBranch
from lp.bugs.model.bugtask import BugTask
from lp.code.enums import BranchMergeProposalStatus
from lp.code.interfaces.branch import user_has_special_branch_access
from lp.code.interfaces.branchcollection import (
    IBranchCollection,
    InvalidFilter,
    )
from lp.code.interfaces.branchlookup import IBranchLookup
from lp.code.interfaces.codehosting import LAUNCHPAD_SERVICES
from lp.code.interfaces.seriessourcepackagebranch import (
    IFindOfficialBranchLinks,
    )
from lp.code.model.branch import (
    Branch,
    get_branch_privacy_filter,
    )
from lp.code.model.branchmergeproposal import BranchMergeProposal
from lp.code.model.branchrevision import BranchRevision
from lp.code.model.branchsubscription import BranchSubscription
from lp.code.model.codeimport import CodeImport
from lp.code.model.codereviewcomment import CodeReviewComment
from lp.code.model.codereviewvote import CodeReviewVoteReference
from lp.code.model.revision import Revision
from lp.code.model.seriessourcepackagebranch import SeriesSourcePackageBranch
from lp.registry.enums import EXCLUSIVE_TEAM_POLICY
from lp.registry.model.distribution import Distribution
from lp.registry.model.distroseries import DistroSeries
from lp.registry.model.person import Person
from lp.registry.model.product import Product
from lp.registry.model.teammembership import TeamParticipation
from lp.services.database.bulk import (
    load_referencing,
    load_related,
    )
from lp.services.database.decoratedresultset import DecoratedResultSet
from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import quote
from lp.services.propertycache import get_property_cache
from lp.services.searchbuilder import any


class GenericBranchCollection:
    """See `IBranchCollection`."""

    implements(IBranchCollection)

    def __init__(self, store=None, branch_filter_expressions=None,
                 tables=None, exclude_from_search=None,
                 asymmetric_filter_expressions=None, asymmetric_tables=None):
        """Construct a `GenericBranchCollection`.

        :param store: The store to look in for branches. If not specified,
            use the default store.
        :param branch_filter_expressions: A list of Storm expressions to
            restrict the branches in the collection. If unspecified, then
            there will be no restrictions on the result set. That is, all
            branches in the store will be in the collection.
        :param tables: A dict of Storm tables to the Join expression.  If an
            expression in branch_filter_expressions refers to a table, then
            that table *must* be in this list.
        :param asymmetric_filter_expressions: As per branch_filter_expressions
            but only applies to one side of reflexive joins.
        :param asymmetric_tables: As per tables, for
            asymmetric_filter_expressions.
        """
        self._store = store
        if branch_filter_expressions is None:
            branch_filter_expressions = []
        self._branch_filter_expressions = list(branch_filter_expressions)
        if tables is None:
            tables = {}
        self._tables = tables
        if asymmetric_filter_expressions is None:
            asymmetric_filter_expressions = []
        self._asymmetric_filter_expressions = list(
            asymmetric_filter_expressions)
        if asymmetric_tables is None:
            asymmetric_tables = {}
        self._asymmetric_tables = asymmetric_tables
        if exclude_from_search is None:
            exclude_from_search = []
        self._exclude_from_search = exclude_from_search
        self._user = None

    def count(self):
        """See `IBranchCollection`."""
        return self.getBranches(eager_load=False).count()

    def is_empty(self):
        """See `IBranchCollection`."""
        return self.getBranches(eager_load=False).is_empty()

    def ownerCounts(self):
        """See `IBranchCollection`."""
        is_team = Person.teamowner != None
        branch_owners = self._getBranchSelect((Branch.ownerID,))
        counts = dict(self.store.find(
            (is_team, Count(Person.id)),
            Person.id.is_in(branch_owners)).group_by(is_team))
        return (counts.get(False, 0), counts.get(True, 0))

    @property
    def store(self):
        # Although you might think we could set the default value for store in
        # the constructor, we can't. The IStore utility is not
        # available at the time that the branchcollection.zcml is parsed,
        # which means we get an error if this code is in the constructor.
        # -- JonathanLange 2009-02-17.
        if self._store is None:
            return IStore(BugTask)
        else:
            return self._store

    def _filterBy(self, expressions, table=None, join=None,
                  exclude_from_search=None, symmetric=True):
        """Return a subset of this collection, filtered by 'expressions'.

        :param symmetric: If True this filter will apply to both sides
            of merge proposal lookups and any other lookups that join
            Branch back onto Branch.
        """
        # NOTE: JonathanLange 2009-02-17: We might be able to avoid the need
        # for explicit 'tables' by harnessing Storm's table inference system.
        # See http://paste.ubuntu.com/118711/ for one way to do that.
        if table is not None:
            if join is None:
                raise InvalidFilter("Cannot specify a table without a join.")
        if expressions is None:
            expressions = []
        tables = self._tables.copy()
        asymmetric_tables = self._asymmetric_tables.copy()
        if symmetric:
            if table is not None:
                tables[table] = join
            symmetric_expr = self._branch_filter_expressions + expressions
            asymmetric_expr = list(self._asymmetric_filter_expressions)
        else:
            if table is not None:
                asymmetric_tables[table] = join
            symmetric_expr = list(self._branch_filter_expressions)
            asymmetric_expr = (
                self._asymmetric_filter_expressions + expressions)
        if exclude_from_search is None:
            exclude_from_search = []
        return self.__class__(
            self.store,
            symmetric_expr,
            tables,
            self._exclude_from_search + exclude_from_search,
            asymmetric_expr,
            asymmetric_tables)

    def _getBranchSelect(self, columns=(Branch.id,)):
        """Return a Storm 'Select' for columns in this collection."""
        branches = self.getBranches(eager_load=False, find_expr=columns)
        return branches.get_plain_result_set()._get_select()

    def _getBranchExpressions(self):
        """Return the where expressions for this collection."""
        return (self._branch_filter_expressions +
            self._asymmetric_filter_expressions +
            self._getBranchVisibilityExpression())

    def _getBranchVisibilityExpression(self, branch_class=None):
        """Return the where clauses for visibility."""
        return []

    @staticmethod
    def preloadVisibleStackedOnBranches(branches, user=None):
        """Preload the chains of stacked on branches related to the given list
        of branches. Only the branches visible for the given user are
        preloaded/returned.

        """
        if len(branches) == 0:
            return
        store = IStore(Branch)
        result = store.execute("""
            WITH RECURSIVE stacked_on_branches_ids AS (
                SELECT column1 as id FROM (VALUES %s) AS temp
                UNION
                SELECT DISTINCT branch.stacked_on
                FROM stacked_on_branches_ids, Branch AS branch
                WHERE
                    branch.id = stacked_on_branches_ids.id AND
                    branch.stacked_on IS NOT NULL
            )
            SELECT id from stacked_on_branches_ids
            """ % ', '.join(
                ["(%s)" % quote(id)
                 for id in map(attrgetter('id'), branches)]))
        branch_ids = [res[0] for res in result.get_all()]
        # Not really sure this is useful: if a given branch is visible by a
        # user, then I think it means that the whole chain of branches on
        # which is is stacked on is visible by this user
        expressions = [Branch.id.is_in(branch_ids)]
        if user is None:
            collection = AnonymousBranchCollection(
                branch_filter_expressions=expressions)
        else:
            collection = VisibleBranchCollection(
                user=user, branch_filter_expressions=expressions)
        return list(collection.getBranches())

    @staticmethod
    def preloadDataForBranches(branches):
        """Preload branches cached associated product series and
        suite source packages."""
        caches = dict((branch.id, get_property_cache(branch))
            for branch in branches)
        branch_ids = caches.keys()
        for cache in caches.values():
            cache._associatedProductSeries = []
            cache._associatedSuiteSourcePackages = []
            cache.code_import = None
        # associatedProductSeries
        # Imported here to avoid circular import.
        from lp.registry.model.productseries import ProductSeries
        for productseries in IStore(ProductSeries).find(
            ProductSeries,
            ProductSeries.branchID.is_in(branch_ids)):
            cache = caches[productseries.branchID]
            cache._associatedProductSeries.append(productseries)
        # associatedSuiteSourcePackages
        series_set = getUtility(IFindOfficialBranchLinks)
        # Order by the pocket to get the release one first. If changing
        # this be sure to also change BranchCollection.getBranches.
        links = series_set.findForBranches(branches).order_by(
            SeriesSourcePackageBranch.pocket)
        for link in links:
            cache = caches[link.branchID]
            cache._associatedSuiteSourcePackages.append(
                link.suite_sourcepackage)
        for code_import in IStore(CodeImport).find(
            CodeImport, CodeImport.branchID.is_in(branch_ids)):
            cache = caches[code_import.branchID]
            cache.code_import = code_import

    def getBranches(self, find_expr=Branch, eager_load=False):
        """See `IBranchCollection`."""
        all_tables = set(
            self._tables.values() + self._asymmetric_tables.values())
        tables = [Branch] + list(all_tables)
        expressions = self._getBranchExpressions()
        resultset = self.store.using(*tables).find(find_expr, *expressions)

        def do_eager_load(rows):
            branch_ids = set(branch.id for branch in rows)
            if not branch_ids:
                return
            GenericBranchCollection.preloadDataForBranches(rows)
            load_related(Product, rows, ['productID'])
            # So far have only needed the persons for their canonical_url - no
            # need for validity etc in the /branches API call.
            load_related(Person, rows,
                ['ownerID', 'registrantID', 'reviewerID'])
            load_referencing(BugBranch, rows, ['branchID'])

        def cache_permission(branch):
            if self._user:
                get_property_cache(branch)._known_viewers = set(
                    [self._user.id])
            return branch

        eager_load_hook = (
            do_eager_load if eager_load and find_expr == Branch else None)
        return DecoratedResultSet(
            resultset, pre_iter_hook=eager_load_hook,
            result_decorator=cache_permission)

    def getBranchIds(self):
        """See `IBranchCollection`."""
        return self.getBranches(find_expr=Branch.id).get_plain_result_set()

    def getMergeProposals(self, statuses=None, for_branches=None,
                          target_branch=None, merged_revnos=None,
                          merged_revision=None, eager_load=False):
        """See `IBranchCollection`."""
        if for_branches is not None and not for_branches:
            # We have an empty branches list, so we can shortcut.
            return EmptyResultSet()
        elif merged_revnos is not None and not merged_revnos:
            # We have an empty revnos list, so we can shortcut.
            return EmptyResultSet()
        elif (self._asymmetric_filter_expressions or
            for_branches is not None or
            target_branch is not None or
            merged_revnos is not None or
            merged_revision is not None):
            return self._naiveGetMergeProposals(
                statuses, for_branches, target_branch, merged_revnos,
                merged_revision, eager_load=eager_load)
        else:
            # When examining merge proposals in a scope, this is a moderately
            # effective set of constrained queries. It is not effective when
            # unscoped or when tight constraints on branches are present.
            return self._scopedGetMergeProposals(
                statuses, eager_load=eager_load)

    def _naiveGetMergeProposals(self, statuses=None, for_branches=None,
                                target_branch=None, merged_revnos=None,
                                merged_revision=None, eager_load=False):
        Target = ClassAlias(Branch, "target")
        extra_tables = list(set(
            self._tables.values() + self._asymmetric_tables.values()))
        tables = [Branch] + extra_tables + [
            Join(BranchMergeProposal, And(
                Branch.id == BranchMergeProposal.source_branchID,
                *(self._branch_filter_expressions +
                  self._asymmetric_filter_expressions))),
            Join(Target, Target.id == BranchMergeProposal.target_branchID),
            ]
        expressions = self._getBranchVisibilityExpression()
        expressions.extend(self._getBranchVisibilityExpression(Target))
        if for_branches is not None:
            branch_ids = [branch.id for branch in for_branches]
            expressions.append(
                BranchMergeProposal.source_branchID.is_in(branch_ids))
        if target_branch is not None:
            expressions.append(
                BranchMergeProposal.target_branch == target_branch)
        if merged_revnos is not None:
            expressions.append(
                BranchMergeProposal.merged_revno.is_in(merged_revnos))
        if merged_revision is not None:
            expressions.extend([
                BranchMergeProposal.merged_revno == BranchRevision.sequence,
                BranchRevision.revision_id == Revision.id,
                BranchRevision.branch_id ==
                    BranchMergeProposal.target_branchID,
                Revision.revision_id == merged_revision
            ])
            tables.extend([BranchRevision, Revision])
        if statuses is not None:
            expressions.append(
                BranchMergeProposal.queue_status.is_in(statuses))
        resultset = self.store.using(*tables).find(
            BranchMergeProposal, *expressions)
        if not eager_load:
            return resultset
        else:
            loader = partial(
                BranchMergeProposal.preloadDataForBMPs, user=self._user)
            return DecoratedResultSet(resultset, pre_iter_hook=loader)

    def _scopedGetMergeProposals(self, statuses, eager_load=False):
        expressions = (
            self._branch_filter_expressions
            + self._getBranchVisibilityExpression())
        with_expr = With(
            "candidate_branches",
            Select(
                Branch.id,
                tables=[Branch] + self._tables.values(),
                where=And(*expressions) if expressions else True))
        expressions = [SQL("""
            source_branch IN (SELECT id FROM candidate_branches) AND
            target_branch IN (SELECT id FROM candidate_branches)""")]
        tables = [BranchMergeProposal]
        if self._asymmetric_filter_expressions:
            # Need to filter on Branch beyond the with constraints.
            expressions += self._asymmetric_filter_expressions
            expressions.append(
                BranchMergeProposal.source_branchID == Branch.id)
            tables.append(Branch)
            tables.extend(self._asymmetric_tables.values())
        if statuses is not None:
            expressions.append(
                BranchMergeProposal.queue_status.is_in(statuses))
        resultset = self.store.with_(with_expr).using(*tables).find(
            BranchMergeProposal, *expressions)
        if not eager_load:
            return resultset
        else:
            loader = partial(
                BranchMergeProposal.preloadDataForBMPs, user=self._user)
            return DecoratedResultSet(resultset, pre_iter_hook=loader)

    def getMergeProposalsForPerson(self, person, status=None,
                                   eager_load=False):
        """See `IBranchCollection`."""
        # We want to limit the proposals to those where the source branch is
        # limited by the defined collection.
        owned = self.ownedBy(person).getMergeProposals(status)
        reviewing = self.getMergeProposalsForReviewer(person, status)
        resultset = owned.union(reviewing)

        if not eager_load:
            return resultset
        else:
            loader = partial(
                BranchMergeProposal.preloadDataForBMPs, user=self._user)
            return DecoratedResultSet(resultset, pre_iter_hook=loader)

    def getMergeProposalsForReviewer(self, reviewer, status=None):
        """See `IBranchCollection`."""
        tables = [
            BranchMergeProposal,
            Join(CodeReviewVoteReference,
                 CodeReviewVoteReference.branch_merge_proposalID == \
                 BranchMergeProposal.id),
            LeftJoin(CodeReviewComment,
                 CodeReviewVoteReference.commentID == CodeReviewComment.id)]

        expressions = [
            CodeReviewVoteReference.reviewer == reviewer,
            BranchMergeProposal.source_branchID.is_in(self._getBranchSelect())]
        visibility = self._getBranchVisibilityExpression()
        if visibility:
            expressions.append(BranchMergeProposal.target_branchID.is_in(
                Select(Branch.id, visibility)))
        if status is not None:
            expressions.append(
                BranchMergeProposal.queue_status.is_in(status))
        proposals = self.store.using(*tables).find(
            BranchMergeProposal, *expressions)
        # Apply sorting here as we can't do it in the browser code.  We need
        # to think carefully about the best places to do this, but not here
        # nor now.
        proposals.order_by(Desc(CodeReviewComment.vote))
        return proposals

    def getExtendedRevisionDetails(self, user, revisions):
        """See `IBranchCollection`."""

        if not revisions:
            return []
        branch = revisions[0].branch

        def make_rev_info(
                branch_revision, merge_proposal_revs, linked_bugtasks):
            rev_info = {
                'revision': branch_revision,
                'linked_bugtasks': None,
                'merge_proposal': None,
                }
            merge_proposal = merge_proposal_revs.get(branch_revision.sequence)
            rev_info['merge_proposal'] = merge_proposal
            if merge_proposal is not None:
                rev_info['linked_bugtasks'] = linked_bugtasks.get(
                    merge_proposal.source_branch.id)
            return rev_info

        rev_nos = [revision.sequence for revision in revisions]
        merge_proposals = self.getMergeProposals(
                target_branch=branch, merged_revnos=rev_nos,
                statuses=[BranchMergeProposalStatus.MERGED])
        merge_proposal_revs = dict(
                [(mp.merged_revno, mp) for mp in merge_proposals])
        source_branch_ids = [mp.source_branch.id for mp in merge_proposals]
        linked_bugtasks = defaultdict(list)

        if source_branch_ids:
            # We get the bugtasks for our merge proposal branches

            # First, the bug ids
            params = BugTaskSearchParams(
                user=user, status=None,
                linked_branches=any(*source_branch_ids))
            bug_ids = getUtility(IBugTaskSet).searchBugIds(params)

            # Then the bug tasks and branches
            store = IStore(BugBranch)
            rs = store.using(
                BugBranch,
                Join(BugTask, BugTask.bugID == BugBranch.bugID),
            ).find(
                (BugTask, BugBranch),
                BugBranch.bugID.is_in(bug_ids),
                BugBranch.branchID.is_in(source_branch_ids)
            )

            # Build up a collection of bugtasks for each branch
            bugtasks_for_branch = defaultdict(list)
            for bugtask, bugbranch in rs:
                bugtasks_for_branch[bugbranch.branch].append(bugtask)

            # Now filter those down to one bugtask per branch
            for branch, tasks in bugtasks_for_branch.iteritems():
                linked_bugtasks[branch.id].extend(
                    filter_bugtasks_by_context(branch.target.context, tasks))

        return [make_rev_info(rev, merge_proposal_revs, linked_bugtasks)
                for rev in revisions]

    def getTeamsWithBranches(self, person):
        """See `IBranchCollection`."""
        # This method doesn't entirely fit with the intent of the
        # BranchCollection conceptual model, but we're not quite sure how to
        # fix it just yet.  Perhaps when bug 337494 is fixed, we'd be able to
        # sensibly be able to move this method to another utility class.
        branch_query = self._getBranchSelect((Branch.ownerID,))
        return self.store.find(
            Person,
            Person.id == TeamParticipation.teamID,
            TeamParticipation.person == person,
            TeamParticipation.team != person, Person.id.is_in(branch_query))

    def inProduct(self, product):
        """See `IBranchCollection`."""
        return self._filterBy(
            [Branch.product == product], exclude_from_search=['product'])

    def inProject(self, project):
        """See `IBranchCollection`."""
        return self._filterBy(
            [Product.project == project.id],
            table=Product, join=Join(Product, Branch.product == Product.id))

    def inDistribution(self, distribution):
        """See `IBranchCollection`."""
        return self._filterBy(
            [DistroSeries.distribution == distribution],
            table=Distribution,
            join=Join(DistroSeries, Branch.distroseries == DistroSeries.id))

    def inDistroSeries(self, distro_series):
        """See `IBranchCollection`."""
        return self._filterBy([Branch.distroseries == distro_series])

    def inDistributionSourcePackage(self, distro_source_package):
        """See `IBranchCollection`."""
        distribution = distro_source_package.distribution
        sourcepackagename = distro_source_package.sourcepackagename
        return self._filterBy(
            [DistroSeries.distribution == distribution,
             Branch.sourcepackagename == sourcepackagename],
            table=Distribution,
            join=Join(DistroSeries, Branch.distroseries == DistroSeries.id))

    def officialBranches(self, pocket=None):
        """See `IBranchCollection`"""
        if pocket is None:
            expressions = []
        else:
            expressions = [SeriesSourcePackageBranch.pocket == pocket]
        return self._filterBy(
            expressions,
            table=SeriesSourcePackageBranch,
            join=Join(SeriesSourcePackageBranch,
                      SeriesSourcePackageBranch.branch == Branch.id))

    def inSourcePackage(self, source_package):
        """See `IBranchCollection`."""
        return self._filterBy([
            Branch.distroseries == source_package.distroseries,
            Branch.sourcepackagename == source_package.sourcepackagename])

    def isJunk(self):
        """See `IBranchCollection`."""
        return self._filterBy(
            [Branch.product == None, Branch.sourcepackagename == None])

    def isPrivate(self):
        """See `IBranchCollection`."""
        return self._filterBy(
            [Branch.information_type.is_in(PRIVATE_INFORMATION_TYPES)])

    def isExclusive(self):
        """See `IBranchCollection`."""
        return self._filterBy(
            [Person.membership_policy.is_in(EXCLUSIVE_TEAM_POLICY)],
            table=Person,
            join=Join(Person, Branch.ownerID == Person.id))

    def isSeries(self):
        """See `IBranchCollection`."""
        # Circular imports.
        from lp.registry.model.productseries import ProductSeries
        return self._filterBy(
            [Branch.id == ProductSeries.branchID],
            table=ProductSeries,
            join=Join(ProductSeries, Branch.id == ProductSeries.branchID))

    def ownedBy(self, person):
        """See `IBranchCollection`."""
        return self._filterBy([Branch.owner == person], symmetric=False)

    def ownedByTeamMember(self, person):
        """See `IBranchCollection`."""
        subquery = Select(
            TeamParticipation.teamID,
            where=TeamParticipation.personID == person.id)
        return self._filterBy([In(Branch.ownerID, subquery)], symmetric=False)

    def registeredBy(self, person):
        """See `IBranchCollection`."""
        return self._filterBy([Branch.registrant == person], symmetric=False)

    def _getExactMatch(self, term):
        # Try and look up the branch by its URL, which handles lp: shortfom.
        branch_url = getUtility(IBranchLookup).getByUrl(term)
        if branch_url:
            return branch_url
        # Fall back to searching by unique_name, stripping out the path if it's
        # a URI.
        try:
            path = URI(term).path.strip('/')
        except InvalidURIError:
            path = term
        return getUtility(IBranchLookup).getByUniqueName(path)

    def search(self, term):
        """See `IBranchCollection`."""
        branch = self._getExactMatch(term)
        if branch:
            collection = self._filterBy([Branch.id == branch.id])
        else:
            term = unicode(term)
            # Filter by name.
            field = Branch.name
            # Except if the term contains /, when we use unique_name.
            if '/' in term:
                field = Branch.unique_name
            collection = self._filterBy(
                [field.lower().contains_string(term.lower())])
        return collection.getBranches(eager_load=False).order_by(
            Branch.name, Branch.id)

    def scanned(self):
        """See `IBranchCollection`."""
        return self._filterBy([Branch.last_scanned != None])

    def subscribedBy(self, person):
        """See `IBranchCollection`."""
        return self._filterBy(
            [BranchSubscription.person == person],
            table=BranchSubscription,
            join=Join(BranchSubscription,
                      BranchSubscription.branch == Branch.id),
            symmetric=False)

    def targetedBy(self, person, since=None):
        """See `IBranchCollection`."""
        clauses = [BranchMergeProposal.registrant == person]
        if since is not None:
            clauses.append(BranchMergeProposal.date_created >= since)
        return self._filterBy(
            clauses,
            table=BranchMergeProposal,
            join=Join(BranchMergeProposal,
                      BranchMergeProposal.target_branch == Branch.id),
            symmetric=False)

    def linkedToBugs(self, bugs):
        """See `IBranchCollection`."""
        bug_ids = [bug.id for bug in bugs]
        return self._filterBy(
            [In(BugBranch.bugID, bug_ids)],
            table=BugBranch,
            join=Join(BugBranch, BugBranch.branch == Branch.id),
            symmetric=False)

    def visibleByUser(self, person):
        """See `IBranchCollection`."""
        if (person == LAUNCHPAD_SERVICES or
            user_has_special_branch_access(person)):
            return self
        if person is None:
            return AnonymousBranchCollection(
                self._store, self._branch_filter_expressions,
                self._tables, self._exclude_from_search,
                self._asymmetric_filter_expressions, self._asymmetric_tables)
        return VisibleBranchCollection(
            person, self._store, self._branch_filter_expressions,
            self._tables, self._exclude_from_search,
            self._asymmetric_filter_expressions, self._asymmetric_tables)

    def withBranchType(self, *branch_types):
        return self._filterBy(
            [Branch.branch_type.is_in(branch_types)], symmetric=False)

    def withLifecycleStatus(self, *statuses):
        """See `IBranchCollection`."""
        return self._filterBy(
            [Branch.lifecycle_status.is_in(statuses)], symmetric=False)

    def modifiedSince(self, epoch):
        """See `IBranchCollection`."""
        return self._filterBy(
            [Branch.date_last_modified > epoch], symmetric=False)

    def scannedSince(self, epoch):
        """See `IBranchCollection`."""
        return self._filterBy([Branch.last_scanned > epoch], symmetric=False)

    def withIds(self, *branch_ids):
        """See `IBranchCollection`."""
        return self._filterBy([Branch.id.is_in(branch_ids)], symmetric=False)


class AnonymousBranchCollection(GenericBranchCollection):
    """Branch collection that only shows public branches."""

    def _getBranchVisibilityExpression(self, branch_class=Branch):
        """Return the where clauses for visibility."""
        return get_branch_privacy_filter(None, branch_class=branch_class)


class VisibleBranchCollection(GenericBranchCollection):
    """A branch collection that has special logic for visibility."""

    def __init__(self, user, store=None, branch_filter_expressions=None,
                 tables=None, exclude_from_search=None,
                 asymmetric_filter_expressions=None, asymmetric_tables=None):
        super(VisibleBranchCollection, self).__init__(
            store=store, branch_filter_expressions=branch_filter_expressions,
            tables=tables, exclude_from_search=exclude_from_search,
            asymmetric_filter_expressions=asymmetric_filter_expressions,
            asymmetric_tables=asymmetric_tables)
        self._user = user

    def _filterBy(self, expressions, table=None, join=None,
                  exclude_from_search=None, symmetric=True):
        """Return a subset of this collection, filtered by 'expressions'.

        :param symmetric: If True this filter will apply to both sides
            of merge proposal lookups and any other lookups that join
            Branch back onto Branch.
        """
        # NOTE: JonathanLange 2009-02-17: We might be able to avoid the need
        # for explicit 'tables' by harnessing Storm's table inference system.
        # See http://paste.ubuntu.com/118711/ for one way to do that.
        if table is not None:
            if join is None:
                raise InvalidFilter("Cannot specify a table without a join.")
        if expressions is None:
            expressions = []
        tables = self._tables.copy()
        asymmetric_tables = self._asymmetric_tables.copy()
        if symmetric:
            if table is not None:
                tables[table] = join
            symmetric_expr = self._branch_filter_expressions + expressions
            asymmetric_expr = list(self._asymmetric_filter_expressions)
        else:
            if table is not None:
                asymmetric_tables[table] = join
            symmetric_expr = list(self._branch_filter_expressions)
            asymmetric_expr = (
                self._asymmetric_filter_expressions + expressions)
        if exclude_from_search is None:
            exclude_from_search = []
        return self.__class__(
            self._user, self.store, symmetric_expr, tables,
            self._exclude_from_search + exclude_from_search,
            asymmetric_expr, asymmetric_tables)

    def _getBranchVisibilityExpression(self, branch_class=Branch):
        """Return the where clauses for visibility.

        :param branch_class: The Branch class to use - permits using
            ClassAliases.
        """
        return get_branch_privacy_filter(self._user, branch_class=branch_class)

    def visibleByUser(self, person):
        """See `IBranchCollection`."""
        if person == self._user:
            return self
        raise InvalidFilter(
            "Cannot filter for branches visible by user %r, already "
            "filtering for %r" % (person, self._user))
