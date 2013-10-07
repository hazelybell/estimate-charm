# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'get_bug_privacy_filter',
    'get_bug_privacy_filter_terms',
    'get_bug_bulk_privacy_filter_terms',
    'orderby_expression',
    'search_bugs',
    ]

from lazr.enum import BaseItem
from storm.expr import (
    Alias,
    And,
    Coalesce,
    Count,
    Desc,
    Exists,
    In,
    Join,
    LeftJoin,
    Not,
    Or,
    Row,
    Select,
    SQL,
    Union,
    )
from storm.info import ClassAlias
from storm.references import Reference
from zope.component import getUtility
from zope.security.proxy import (
    isinstance as zope_isinstance,
    removeSecurityProxy,
    )

from lp.app.enums import PUBLIC_INFORMATION_TYPES
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.blueprints.model.specification import Specification
from lp.blueprints.model.specificationbug import SpecificationBug
from lp.bugs.errors import InvalidSearchParameters
from lp.bugs.interfaces.bugattachment import BugAttachmentType
from lp.bugs.interfaces.bugnomination import BugNominationStatus
from lp.bugs.interfaces.bugtask import (
    BugTaskStatus,
    BugTaskStatusSearch,
    DB_INCOMPLETE_BUGTASK_STATUSES,
    )
from lp.bugs.interfaces.bugtasksearch import (
    BugBlueprintSearch,
    BugBranchSearch,
    BugTaskSearchParams,
    )
from lp.bugs.model.bug import (
    Bug,
    BugAffectsPerson,
    BugTag,
    )
from lp.bugs.model.bugattachment import BugAttachment
from lp.bugs.model.bugbranch import BugBranch
from lp.bugs.model.bugcve import BugCve
from lp.bugs.model.bugmessage import BugMessage
from lp.bugs.model.bugnomination import BugNomination
from lp.bugs.model.bugsubscription import BugSubscription
from lp.bugs.model.bugtask import BugTask
from lp.bugs.model.bugtaskflat import BugTaskFlat
from lp.bugs.model.structuralsubscription import StructuralSubscription
from lp.registry.interfaces.distribution import IDistribution
from lp.registry.interfaces.distroseries import IDistroSeries
from lp.registry.interfaces.milestone import IProjectGroupMilestone
from lp.registry.interfaces.product import IProduct
from lp.registry.interfaces.productseries import IProductSeries
from lp.registry.interfaces.role import IPersonRoles
from lp.registry.model.accesspolicy import AccessPolicyGrant
from lp.registry.model.distribution import Distribution
from lp.registry.model.milestone import Milestone
from lp.registry.model.milestonetag import MilestoneTag
from lp.registry.model.person import Person
from lp.registry.model.product import (
    Product,
    ProductSet,
    )
from lp.registry.model.teammembership import TeamParticipation
from lp.services.database.bulk import load
from lp.services.database.decoratedresultset import DecoratedResultSet
from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import sqlvalues
from lp.services.database.stormexpr import (
    ArrayAgg,
    ArrayIntersects,
    fti_search,
    get_where_for_reference,
    rank_by_fti,
    Unnest,
    )
from lp.services.propertycache import get_property_cache
from lp.services.searchbuilder import (
    all,
    any,
    greater_than,
    not_equals,
    NULL,
    )
from lp.soyuz.enums import PackagePublishingStatus
from lp.soyuz.model.publishing import SourcePackagePublishingHistory


Assignee = ClassAlias(Person)
Reporter = ClassAlias(Person)
bug_join = (Bug, Join(Bug, Bug.id == BugTaskFlat.bug_id))
bugtask_join = (
    BugTask, Join(BugTask, BugTask.id == BugTaskFlat.bugtask_id))
orderby_expression = {
    "task": (BugTaskFlat.bugtask_id, []),
    "id": (BugTaskFlat.bug_id, []),
    "importance": (BugTaskFlat.importance, []),
    # TODO: sort by their name?
    "assignee": (
        Assignee.name,
        [
            (Assignee,
                LeftJoin(Assignee, BugTaskFlat.assignee == Assignee.id))
            ]),
    "targetname": (BugTask.targetnamecache, [bugtask_join]),
    "status": (BugTaskFlat.status, []),
    "information_type": (BugTaskFlat.information_type, []),
    "title": (Bug.title, [bug_join]),
    "milestone": (BugTaskFlat.milestone_id, []),
    "dateassigned": (BugTask.date_assigned, [bugtask_join]),
    "datecreated": (BugTaskFlat.datecreated, []),
    "date_last_updated": (BugTaskFlat.date_last_updated, []),
    "date_closed": (BugTaskFlat.date_closed, []),
    "number_of_duplicates": (Bug.number_of_duplicates, [bug_join]),
    "message_count": (Bug.message_count, [bug_join]),
    "users_affected_count": (Bug.users_affected_count, [bug_join]),
    "heat": (BugTaskFlat.heat, []),
    "latest_patch_uploaded": (BugTaskFlat.latest_patch_uploaded, []),
    "milestone_name": (
        Milestone.name,
        [
            (Milestone,
                LeftJoin(Milestone,
                        BugTaskFlat.milestone_id == Milestone.id))
            ]),
    "reporter": (
        Reporter.name,
        [
            (Reporter, Join(Reporter, BugTaskFlat.bug_owner == Reporter.id))
            ]),
    "tag": (
        BugTag.tag,
        [
            (BugTag,
                LeftJoin(
                    BugTag,
                    BugTag.bug == BugTaskFlat.bug_id and
                    # We want at most one tag per bug. Select the
                    # tag that comes first in alphabetic order.
                    BugTag.id == Select(
                        BugTag.id, tables=[BugTag],
                        where=(BugTag.bugID == BugTaskFlat.bug_id),
                        order_by=BugTag.tag, limit=1))),
            ]
        ),
    "specification": (
        Specification.name,
        [
            (Specification,
                LeftJoin(
                    Specification,
                    # We want at most one specification per bug.
                    # Select the specification that comes first
                    # in alphabetic order.
                    Specification.id == Select(
                        Specification.id,
                        tables=[
                            SpecificationBug,
                            Join(
                                Specification,
                                Specification.id ==
                                    SpecificationBug.specificationID)],
                        where=(SpecificationBug.bugID == BugTaskFlat.bug_id),
                        order_by=Specification.name, limit=1))),
            ]
        ),
    }


def search_value_to_storm_where_condition(comp, search_value):
    """Convert a search value to a Storm WHERE condition."""
    if zope_isinstance(search_value, (set, list, tuple)):
        search_value = any(*search_value)
    if zope_isinstance(search_value, any):
        # When an any() clause is provided, the argument value
        # is a list of acceptable filter values.
        if not search_value.query_values:
            return None
        if isinstance(comp, Reference):
            return get_where_for_reference(comp, search_value.query_values)
        else:
            return comp.is_in(search_value.query_values)
    elif zope_isinstance(search_value, not_equals):
        return comp != search_value.value
    elif zope_isinstance(search_value, greater_than):
        return comp > search_value.value
    elif search_value is not NULL:
        return comp == search_value
    else:
        # The argument value indicates we should match
        # only NULL values for the column named by
        # arg_name.
        return comp == None


def search_bugs(pre_iter_hook, alternatives, just_bug_ids=False):
    """Return a ResultSet of BugTasks for the given search parameters.

    :param pre_iter_hook: An optional pre-iteration hook used for eager
        loading bug targets for list views.
    :param alternatives: A sequence of BugTaskSearchParams instances, the
        results of which will be unioned. Only the first ordering is
        respected.
    :param just_bug_ids: Return a ResultSet of bug IDs instead of BugTasks.
    """
    store = IStore(BugTask)
    orderby_expression, orderby_joins = _process_order_by(alternatives[0])
    decorators = []

    # Normally we just return the ID -- the DecoratedResultSet will turn
    # it into the actual BugTask. But the caller can also request to
    # just get the bug IDs back, in which case we don't use DRS.
    start = BugTaskFlat
    if just_bug_ids:
        want = BugTaskFlat.bug_id
    else:
        want = BugTaskFlat.bugtask_id
        decorators.append(lambda id: IStore(BugTask).get(BugTask, id))
        orig_pre_iter_hook = pre_iter_hook

        def pre_iter_hook(rows):
            rows = load(BugTask, rows)
            if orig_pre_iter_hook:
                orig_pre_iter_hook(rows)

    if len(alternatives) == 1:
        [query, clauseTables, bugtask_decorator, join_tables, with_clause] = (
            _build_query(alternatives[0]))
        if with_clause:
            store = store.with_(with_clause)
        decorators.append(bugtask_decorator)
        origin = _build_origin(
            join_tables + orderby_joins, clauseTables, start)
        result = store.using(*origin).find(want, query)
    else:
        results = []

        for params in alternatives:
            [query, clauseTables, decorator, join_tables, with_clause] = (
                _build_query(params))
            origin = _build_origin(join_tables, clauseTables, start)
            localstore = store
            if with_clause:
                localstore = store.with_(with_clause)
            next_result = localstore.using(*origin).find(BugTaskFlat, query)
            results.append(next_result)
            # NB: assumes the decorators are all compatible.
            # This may need revisiting if e.g. searches on behalf of different
            # users are combined.
            decorators.append(decorator)

        resultset = reduce(lambda l, r: l.union(r), results)
        origin = _build_origin(
            orderby_joins, [], Alias(resultset._get_select(), "BugTaskFlat"))
        result = store.using(*origin).find(want)

    result.order_by(orderby_expression)
    return DecoratedResultSet(
        result,
        lambda row: reduce(lambda task, dec: dec(task), decorators, row),
        pre_iter_hook=pre_iter_hook)


def _build_origin(join_tables, clauseTables, start_with):
    """Build the parameter list for Store.using().

    :param join_tables: A sequence of tables that should be joined
        as returned by _build_query(). Each element has the form
        (table, join), where table is the table to join and join
        is a Storm Join or LeftJoin instance.
    :param clauseTables: A sequence of tables that should appear in
        the FROM clause of a query. The join condition is defined in
        the WHERE clause.

    Tables may appear simultaneously in join_tables and in clauseTables.
    This method ensures that each table appears exactly once in the
    returned sequence.
    """
    origin = [start_with]
    already_joined = set(origin)
    for table, join in join_tables:
        if table is None or table not in already_joined:
            origin.append(join)
            if table is not None:
                already_joined.add(table)
    for table in clauseTables:
        if table not in already_joined:
            origin.append(table)
    return origin


def _build_query(params):
    """Build and return an SQL query with the given parameters.

    Also return the clauseTables and orderBy for the generated query.

    :return: A query, the tables to query, ordering expression and a
        decorator to call on each returned row.
    """
    params = _require_params(params)

    extra_clauses = []
    clauseTables = []
    join_tables = []

    decorators = []
    with_clauses = []

    # These arguments can be processed in a loop without any other
    # special handling.
    standard_args = {
        BugTaskFlat.bug: params.bug,
        BugTaskFlat.importance: params.importance,
        BugTaskFlat.product: params.product,
        BugTaskFlat.distribution: params.distribution,
        BugTaskFlat.distroseries: params.distroseries,
        BugTaskFlat.productseries: params.productseries,
        BugTaskFlat.assignee: params.assignee,
        BugTaskFlat.sourcepackagename: params.sourcepackagename,
        BugTaskFlat.owner: params.owner,
        BugTaskFlat.date_closed: params.date_closed,
    }

    # Loop through the standard, "normal" arguments and build the
    # appropriate SQL WHERE clause. Note that arg_value will be one
    # of:
    #
    # * a searchbuilder.any object, representing a set of acceptable
    #   filter values
    # * a searchbuilder.NULL object
    # * an sqlobject
    # * a dbschema item
    # * None (meaning no filter criteria specified for that arg_name)
    #
    # XXX: kiko 2006-03-16:
    # Is this a good candidate for becoming infrastructure in
    # lp.services.database.sqlbase?
    for col, arg_value in standard_args.items():
        if arg_value is None:
            continue
        where_cond = search_value_to_storm_where_condition(col, arg_value)
        if where_cond is not None:
            extra_clauses.append(where_cond)

    if params.status is not None:
        extra_clauses.append(
            _build_status_clause(BugTaskFlat.status, params.status))

    if params.exclude_conjoined_tasks:
        # XXX: frankban 2012-01-05 bug=912370: excluding conjoined
        # bugtasks is not currently supported for milestone tags.
        if params.milestone_tag:
            raise NotImplementedError(
                'Excluding conjoined tasks is not currently supported '
                'for milestone tags')
        if not params.milestone:
            raise InvalidSearchParameters(
                "BugTaskSearchParam.exclude_conjoined cannot be True if "
                "BugTaskSearchParam.milestone is not set")

    if params.milestone:
        if IProjectGroupMilestone.providedBy(params.milestone):
            extra_clauses.append(
                BugTaskFlat.milestone_id.is_in(
                    Select(
                        Milestone.id,
                        tables=[Milestone, Product],
                        where=And(
                            Product.project == params.milestone.target,
                            Milestone.productID == Product.id,
                            Milestone.name == params.milestone.name,
                            ProductSet.getProductPrivacyFilter(params.user)))))
        else:
            extra_clauses.append(
                search_value_to_storm_where_condition(
                    BugTaskFlat.milestone, params.milestone))

        if params.exclude_conjoined_tasks:
            tables, clauses = _build_exclude_conjoined_clause(
                params.milestone)
            join_tables += tables
            extra_clauses += clauses

    if params.milestone_tag:
        extra_clauses.append(
            BugTaskFlat.milestone_id.is_in(
                Select(
                    Milestone.id,
                    tables=[Milestone, Product, MilestoneTag],
                    where=And(
                        Product.project == params.milestone_tag.target,
                        Milestone.productID == Product.id,
                        Milestone.id == MilestoneTag.milestone_id,
                        MilestoneTag.tag.is_in(params.milestone_tag.tags)),
                    group_by=Milestone.id,
                    having=(
                        Count(Milestone.id) ==
                            len(params.milestone_tag.tags)))))

        # XXX: frankban 2012-01-05 bug=912370: excluding conjoined
        # bugtasks is not currently supported for milestone tags.
        # if params.exclude_conjoined_tasks:
        #     tables, clauses = _build_exclude_conjoined_clause(
        #         params.milestone_tag)
        #     join_tables += tables
        #     extra_clauses += clauses

    if params.project:
        clauseTables.append(Product)
        extra_clauses.append(And(
            BugTaskFlat.product_id == Product.id,
            search_value_to_storm_where_condition(
                Product.project, params.project)))

    if params.omit_dupes:
        extra_clauses.append(BugTaskFlat.duplicateof == None)

    if params.omit_targeted:
        extra_clauses.append(And(
            BugTaskFlat.distroseries == None,
            BugTaskFlat.productseries == None))

    if params.has_cve:
        extra_clauses.append(
            BugTaskFlat.bug_id.is_in(
                Select(BugCve.bugID, tables=[BugCve])))

    if params.attachmenttype is not None:
        if params.attachmenttype == BugAttachmentType.PATCH:
            extra_clauses.append(BugTaskFlat.latest_patch_uploaded != None)
        else:
            extra_clauses.append(
                BugTaskFlat.bug_id.is_in(
                    Select(
                        BugAttachment.bugID, tables=[BugAttachment],
                        where=search_value_to_storm_where_condition(
                            BugAttachment.type, params.attachmenttype))))

    if params.searchtext:
        extra_clauses.append(_build_search_text_clause(params))

    if params.fast_searchtext:
        extra_clauses.append(_build_search_text_clause(params, fast=True))

    if params.subscriber is not None:
        clauseTables.append(BugSubscription)
        extra_clauses.append(And(
            BugTaskFlat.bug_id == BugSubscription.bug_id,
            BugSubscription.person == params.subscriber))

    if params.structural_subscriber is not None:
        with_clauses.append(
            '''ss as (SELECT * from StructuralSubscription
            WHERE StructuralSubscription.subscriber = %s)'''
            % sqlvalues(params.structural_subscriber))

        class StructuralSubscriptionCTE(StructuralSubscription):
            __storm_table__ = 'ss'

        SS = ClassAlias(StructuralSubscriptionCTE)
        # Milestones apply to all structural subscription searches.
        ss_clauses = [
            In(BugTaskFlat.milestone_id, Select(SS.milestoneID, tables=[SS]))]
        if (params.project is None
            and params.product is None and params.productseries is None):
            # This search is *not* contrained to project related bugs, so
            # include distro, distroseries, DSP and SP subscriptions.
            ss_clauses.append(In(
                BugTaskFlat.distribution_id,
                Select(SS.distributionID, tables=[SS],
                       where=(SS.sourcepackagenameID == None))))
            ss_clauses.append(In(
                Row(BugTaskFlat.distribution_id,
                    BugTaskFlat.sourcepackagename_id),
                Select((SS.distributionID, SS.sourcepackagenameID),
                       tables=[SS])))
            ss_clauses.append(In(
                BugTaskFlat.distroseries_id,
                Select(SS.distroseriesID, tables=[SS],
                       where=(SS.sourcepackagenameID == None))))
            # Users expect to find their DSP subscriptions when searching
            # distroseries. We only include these when we need to.
            if params.distroseries is not None:
                distroseries_id = params.distroseries.id
                parent_distro_id = params.distroseries.distributionID
            else:
                distroseries_id = 0
                parent_distro_id = 0
            ss_clauses.append(In(
                Row(BugTaskFlat.distroseries_id,
                    BugTaskFlat.sourcepackagename_id),
                Select((distroseries_id, SS.sourcepackagenameID), tables=[SS],
                       where=And(
                           SS.distributionID == parent_distro_id,
                           SS.sourcepackagenameID != None))))
        if params.distribution is None and params.distroseries is None:
            # This search is *not* contrained to distro related bugs so
            # include products, productseries, and project group subscriptions.
            project_match = True
            if params.project is not None:
                project_match = Product.project == params.project
            ss_clauses.append(In(
                BugTaskFlat.product_id,
                Select(SS.productID, tables=[SS])))
            ss_clauses.append(In(
                BugTaskFlat.productseries_id,
                Select(SS.productseriesID, tables=[SS])))
            ss_clauses.append(In(
                BugTaskFlat.product_id,
                Select(Product.id, tables=[SS, Product],
                       where=And(
                           SS.projectID == Product.projectID,
                           project_match,
                           Product.active))))
        extra_clauses.append(Or(*ss_clauses))

    # Remove bugtasks from deactivated products. This is needed for searches
    # where people or project groups are the context.
    if (params.product is None and
        params.distribution is None and
        params.productseries is None and
        params.distroseries is None):
        extra_clauses.append(
            Or(BugTaskFlat.product == None, Product.active == True))
        join_tables.append(
            (Product, LeftJoin(Product, And(
                            BugTaskFlat.product_id == Product.id,
                            Product.active))))

    if params.component:
        distroseries = None
        if params.distribution:
            distroseries = params.distribution.currentseries
        elif params.distroseries:
            distroseries = params.distroseries
        if distroseries is None:
            raise InvalidSearchParameters(
                "Search by component requires a context with a "
                "distribution or distroseries.")

        if zope_isinstance(params.component, any):
            components = params.component.query_values
        else:
            components = [params.component]

        # It's much faster to query for a single archive, so don't
        # include partner unless we have to.
        archive_ids = set(
            distroseries.distribution.getArchiveByComponent(c.name).id
            for c in components)

        extra_clauses.append(
            BugTaskFlat.sourcepackagename_id.is_in(
                Select(
                    SourcePackagePublishingHistory.sourcepackagenameID,
                    tables=[SourcePackagePublishingHistory],
                    where=And(
                        SourcePackagePublishingHistory.archiveID.is_in(
                            archive_ids),
                        SourcePackagePublishingHistory.distroseries ==
                            distroseries,
                        SourcePackagePublishingHistory.componentID.is_in(
                            c.id for c in components),
                        SourcePackagePublishingHistory.status ==
                            PackagePublishingStatus.PUBLISHED))))

    upstream_clause = _build_upstream_clause(params)
    if upstream_clause:
        extra_clauses.append(upstream_clause)

    if params.tag:
        tag_clause = _build_tag_search_clause(params.tag)
        if tag_clause is not None:
            extra_clauses.append(tag_clause)

    # XXX sinzui 2012-09-26:
    # This uses StructuralSubscription to assume a bug supervisor relationship
    # for distribution source packages to preserve historical behaviour.
    # This also duplicates params.structural_subscriber code and behaviour.
    if params.bug_supervisor:
        extra_clauses.append(Or(
            In(
                BugTaskFlat.product_id,
                Select(
                    Product.id, tables=[Product],
                    where=Product.bug_supervisor == params.bug_supervisor)),
            In(
                BugTaskFlat.distribution_id,
                Select(
                    Distribution.id, tables=[Distribution],
                    where=(
                        Distribution.bug_supervisor ==
                            params.bug_supervisor))),
            In(
                Row(BugTaskFlat.distribution_id,
                    BugTaskFlat.sourcepackagename_id),
                Select(
                    ((StructuralSubscription.distributionID,
                     StructuralSubscription.sourcepackagenameID),),
                    tables=[StructuralSubscription],
                    where=(
                        StructuralSubscription.subscriber ==
                            params.bug_supervisor)))))

    if params.bug_reporter:
        extra_clauses.append(BugTaskFlat.bug_owner == params.bug_reporter)

    if params.bug_commenter:
        extra_clauses.append(
            BugTaskFlat.bug_id.is_in(Select(
                BugMessage.bugID, tables=[BugMessage],
                where=And(
                    BugMessage.index > 0,
                    BugMessage.owner == params.bug_commenter))))

    if params.affects_me:
        params.affected_user = params.user
    if params.affected_user:
        join_tables.append(
            (BugAffectsPerson, Join(
                BugAffectsPerson, And(
                    BugTaskFlat.bug_id == BugAffectsPerson.bugID,
                    BugAffectsPerson.affected,
                    BugAffectsPerson.person == params.affected_user))))

    if params.nominated_for:
        if IDistroSeries.providedBy(params.nominated_for):
            target_col = BugNomination.distroseries
        elif IProductSeries.providedBy(params.nominated_for):
            target_col = BugNomination.productseries
        else:
            raise AssertionError(
                'Unknown nomination target: %r.' % params.nominated_for)
        extra_clauses.append(And(
            BugNomination.bugID == BugTaskFlat.bug_id,
            BugNomination.status == BugNominationStatus.PROPOSED,
            target_col == params.nominated_for))
        clauseTables.append(BugNomination)

    dateexpected_before = params.milestone_dateexpected_before
    dateexpected_after = params.milestone_dateexpected_after
    if dateexpected_after or dateexpected_before:
        clauseTables.append(Milestone)
        extra_clauses.append(BugTaskFlat.milestone_id == Milestone.id)
        if dateexpected_after:
            extra_clauses.append(
                Milestone.dateexpected >= dateexpected_after)
        if dateexpected_before:
            extra_clauses.append(
                Milestone.dateexpected <= dateexpected_before)

    if not params.ignore_privacy:
        clause, decorator = _get_bug_privacy_filter_with_decorator(params.user)
        if clause:
            extra_clauses.append(clause)
            decorators.append(decorator)

    hw_clause = _build_hardware_related_clause(params)
    if hw_clause is not None:
        extra_clauses.append(hw_clause)

    def make_branch_clause(branches=None):
        where = [BugBranch.bugID == BugTaskFlat.bug_id]
        if branches is not None:
            where.append(
                search_value_to_storm_where_condition(
                    BugBranch.branchID, branches))
        return Exists(Select(1, tables=[BugBranch], where=And(*where)))

    if zope_isinstance(params.linked_branches, BaseItem):
        if params.linked_branches == BugBranchSearch.BUGS_WITH_BRANCHES:
            extra_clauses.append(make_branch_clause())
        elif (params.linked_branches ==
                BugBranchSearch.BUGS_WITHOUT_BRANCHES):
            extra_clauses.append(Not(make_branch_clause()))
    elif zope_isinstance(params.linked_branches, (any, all, int)):
        # A specific search term has been supplied.
        extra_clauses.append(make_branch_clause(params.linked_branches))

    linked_blueprints_clause = _build_blueprint_related_clause(params)
    if linked_blueprints_clause is not None:
        extra_clauses.append(linked_blueprints_clause)

    if params.modified_since:
        extra_clauses.append(
            BugTaskFlat.date_last_updated > params.modified_since)

    if params.created_since:
        extra_clauses.append(
            BugTaskFlat.datecreated > params.created_since)

    if params.created_before:
        extra_clauses.append(
            BugTaskFlat.datecreated < params.created_before)

    if params.information_type:
        extra_clauses.append(
            search_value_to_storm_where_condition(
                BugTaskFlat.information_type, params.information_type))

    query = And(extra_clauses)

    if not decorators:
        decorator = lambda x: x
    else:

        def decorator(obj):
            for decor in decorators:
                obj = decor(obj)
            return obj
    if with_clauses:
        with_clause = SQL(', '.join(with_clauses))
    else:
        with_clause = None
    return (query, clauseTables, decorator, join_tables, with_clause)


def _process_order_by(params):
    """Process the orderby parameter supplied to search().

    This method ensures the sort order will be stable, and converting
    the string supplied to actual column names.

    :return: A Storm order_by tuple.
    """
    orderby = params.orderby
    if orderby is None:
        orderby = []
    elif not zope_isinstance(orderby, (list, tuple)):
        orderby = [orderby]

    orderby_arg = []
    # This set contains columns which are, in practical terms,
    # unique. When these columns are used as sort keys, they ensure
    # the sort will be consistent. These columns will be used to
    # decide whether we need to add the BugTask.bug or BugTask.id
    # columns to make the sort consistent over runs -- which is good
    # for the user and essential for the test suite.
    # Bug ID is unique within bugs on a product or source package.
    if (params.product or
        (params.distribution and params.sourcepackagename) or
        (params.distroseries and params.sourcepackagename)):
        in_unique_context = True
    else:
        in_unique_context = False

    unambiguous_cols = set([
        BugTaskFlat.date_last_updated,
        BugTaskFlat.datecreated,
        BugTaskFlat.bugtask_id,
        Bug.datecreated,
        BugTask.date_assigned,
        ])
    if in_unique_context:
        unambiguous_cols.add(BugTaskFlat.bug)

    # Translate orderby keys into corresponding Table.attribute
    # strings.
    extra_joins = []
    ambiguous = True
    # Sorting by milestone or information type only is a very "coarse"
    # sort order. If no additional sort order is specified, add the bug task
    # importance as a secondary sort order.
    if len(orderby) == 1:
        if orderby[0] in ('milestone_name', 'information_type'):
            # We want the most important bugtasks first; these have
            # larger integer values.
            orderby.append('-importance')
        elif orderby[0] in ('-milestone_name', '-information_type'):
            orderby.append('importance')
        else:
            # Other sort orders don't need tweaking.
            pass

    for orderby_col in orderby:
        if isinstance(orderby_col, SQL):
            orderby_arg.append(orderby_col)
            continue
        desc_search = False
        if orderby_col.startswith(u"-"):
            orderby_col = orderby_col[1:]
            desc_search = True
        if orderby_col not in orderby_expression:
            raise InvalidSearchParameters(
                "Unrecognized order_by: %r" % (orderby_col,))
        col, sort_joins = orderby_expression[orderby_col]
        extra_joins.extend(sort_joins)
        if desc_search:
            order_clause = Desc(col)
        else:
            order_clause = col
        if col in unambiguous_cols:
            ambiguous = False
        orderby_arg.append(order_clause)

    if ambiguous:
        if in_unique_context:
            disambiguator = BugTaskFlat.bug_id
        else:
            disambiguator = BugTaskFlat.bugtask_id

        if orderby_arg and not isinstance(orderby_arg[0], Desc):
            disambiguator = Desc(disambiguator)
        orderby_arg.append(disambiguator)

    return tuple(orderby_arg), extra_joins


def _require_params(params):
    assert zope_isinstance(params, BugTaskSearchParams)
    if not isinstance(params, BugTaskSearchParams):
        # Browser code let this get wrapped, unwrap it here as its just a
        # dumb data store that has no security implications.
        params = removeSecurityProxy(params)
    return params


def _build_search_text_clause(params, fast=False):
    """Build the clause for searchtext."""
    if fast:
        assert params.searchtext is None, (
            'Cannot use searchtext at the same time as fast_searchtext.')
        searchtext = params.fast_searchtext
        ftq_for_fti = False
    else:
        assert params.fast_searchtext is None, (
            'Cannot use fast_searchtext at the same time as searchtext.')
        searchtext = params.searchtext
        ftq_for_fti = True

    if params.orderby is None:
        # Unordered search results aren't useful, so sort by relevance
        # instead.
        params.orderby = [rank_by_fti(BugTaskFlat, searchtext, ftq_for_fti)]

    return fti_search(BugTaskFlat, searchtext, ftq_for_fti)


def _build_status_clause(col, status):
    """Return the SQL query fragment for search by status.

    Called from `_build_query` or recursively."""

    if zope_isinstance(status, any):
        values = list(status.query_values)
        # Since INCOMPLETE isn't stored as a single value any more, we need to
        # expand it before generating the SQL.
        old = set([BugTaskStatus.INCOMPLETE, BugTaskStatusSearch.INCOMPLETE])
        accepted_values = list(set(values) - old)
        if len(accepted_values) < len(values):
            accepted_values.extend(DB_INCOMPLETE_BUGTASK_STATUSES)
            values = accepted_values
        return search_value_to_storm_where_condition(col, any(*values))
    elif zope_isinstance(status, not_equals):
        return Not(_build_status_clause(col, status.value))
    elif zope_isinstance(status, BaseItem):
        # INCOMPLETE is not stored in the DB, instead one of
        # DB_INCOMPLETE_BUGTASK_STATUSES is stored, so any request to
        # search for INCOMPLETE should instead search for those values.
        # BugTaskStatus is used internally, BugTaskStatusSearch is used
        # externally, such as API.
        if (status == BugTaskStatus.INCOMPLETE
            or status == BugTaskStatusSearch.INCOMPLETE):
            status = any(*DB_INCOMPLETE_BUGTASK_STATUSES)
        return search_value_to_storm_where_condition(col, status)
    else:
        raise InvalidSearchParameters(
            'Unrecognized status value: %r' % (status,))


def _build_exclude_conjoined_clause(milestone):
    """Exclude bugtasks with a conjoined master.

    This search option only makes sense when searching for bugtasks
    for a milestone.  Only bugtasks for a project or a distribution
    can have a conjoined master bugtask, which is a bugtask on the
    project's development focus series or the distribution's
    currentseries. The project bugtask or the distribution bugtask
    will always have the same milestone set as its conjoined master
    bugtask, if it exists on the bug. Therefore, this prevents a lot
    of bugs having two bugtasks listed in the results. However, it
    is ok if a bug has multiple bugtasks in the results as long as
    those other bugtasks are on other series.
    """
    # XXX: EdwinGrubbs 2010-12-15 bug=682989
    # (ConjoinedMaster.bug == X) produces the wrong sql, but
    # (ConjoinedMaster.bugID == X) works right. This bug applies to
    # all foreign keys on the ClassAlias.

    # Perform a LEFT JOIN to the conjoined master bugtask.  If the
    # conjoined master is not null, it gets filtered out.
    ConjoinedMaster = ClassAlias(BugTask, 'ConjoinedMaster')
    extra_clauses = [ConjoinedMaster.id == None]
    if milestone.distribution is not None:
        current_series = milestone.distribution.currentseries
        join = LeftJoin(
            ConjoinedMaster,
            And(ConjoinedMaster.bugID == BugTaskFlat.bug_id,
                BugTaskFlat.distribution_id == milestone.distribution.id,
                ConjoinedMaster.distroseriesID == current_series.id,
                Not(ConjoinedMaster._status.is_in(
                        BugTask._NON_CONJOINED_STATUSES))))
        join_tables = [(ConjoinedMaster, join)]
    else:
        if IProjectGroupMilestone.providedBy(milestone):
            # Since an IProjectGroupMilestone could have bugs with
            # bugtasks on two different projects, the project
            # bugtask is only excluded by a development focus series
            # bugtask on the same project.
            joins = [
                Join(Milestone, BugTaskFlat.milestone_id == Milestone.id),
                LeftJoin(Product, BugTaskFlat.product_id == Product.id),
                LeftJoin(
                    ConjoinedMaster,
                    And(ConjoinedMaster.bugID == BugTaskFlat.bug_id,
                        ConjoinedMaster.productseriesID
                            == Product.development_focusID,
                        Not(ConjoinedMaster._status.is_in(
                                BugTask._NON_CONJOINED_STATUSES)))),
                ]
            # join.right is the table name.
            join_tables = [(join.right, join) for join in joins]
        elif milestone.product is not None:
            dev_focus_id = (
                milestone.product.development_focusID)
            join = LeftJoin(
                ConjoinedMaster,
                And(ConjoinedMaster.bugID == BugTaskFlat.bug_id,
                    BugTaskFlat.product_id == milestone.product.id,
                    ConjoinedMaster.productseriesID == dev_focus_id,
                    Not(ConjoinedMaster._status.is_in(
                            BugTask._NON_CONJOINED_STATUSES))))
            join_tables = [(ConjoinedMaster, join)]
        else:
            raise AssertionError(
                "A milestone must always have either a project, "
                "project group, or distribution")
    return (join_tables, extra_clauses)


def _build_hardware_related_clause(params):
    """Hardware related SQL expressions and tables for bugtask searches.

    :return: (tables, clauses) where clauses is a list of SQL expressions
        which limit a bugtask search to bugs related to a device or
        driver specified in search_params. If search_params contains no
        hardware related data, empty lists are returned.
    :param params: A `BugTaskSearchParams` instance.

    Device related WHERE clauses are returned if
    params.hardware_bus, params.hardware_vendor_id,
    params.hardware_product_id are all not None.
    """
    # Avoid cyclic imports.
    from lp.hardwaredb.model.hwdb import (
        HWSubmission, HWSubmissionBug, HWSubmissionDevice,
        _userCanAccessSubmissionStormClause,
        make_submission_device_statistics_clause)

    bus = params.hardware_bus
    vendor_id = params.hardware_vendor_id
    product_id = params.hardware_product_id
    driver_name = params.hardware_driver_name
    package_name = params.hardware_driver_package_name

    if (bus is not None and vendor_id is not None and
        product_id is not None):
        tables, clauses = make_submission_device_statistics_clause(
            bus, vendor_id, product_id, driver_name, package_name, False)
    elif driver_name is not None or package_name is not None:
        tables, clauses = make_submission_device_statistics_clause(
            None, None, None, driver_name, package_name, False)
    else:
        return None

    tables.append(HWSubmission)
    tables.append(Bug)
    clauses.append(HWSubmissionDevice.submission == HWSubmission.id)
    bug_link_clauses = []
    if params.hardware_owner_is_bug_reporter:
        bug_link_clauses.append(
            HWSubmission.ownerID == Bug.ownerID)
    if params.hardware_owner_is_affected_by_bug:
        bug_link_clauses.append(
            And(BugAffectsPerson.personID == HWSubmission.ownerID,
                BugAffectsPerson.bug == Bug.id,
                BugAffectsPerson.affected))
        tables.append(BugAffectsPerson)
    if params.hardware_owner_is_subscribed_to_bug:
        bug_link_clauses.append(
            And(BugSubscription.person_id == HWSubmission.ownerID,
                BugSubscription.bug_id == Bug.id))
        tables.append(BugSubscription)
    if params.hardware_is_linked_to_bug:
        bug_link_clauses.append(
            And(HWSubmissionBug.bugID == Bug.id,
                HWSubmissionBug.submissionID == HWSubmission.id))
        tables.append(HWSubmissionBug)

    if len(bug_link_clauses) == 0:
        return None

    clauses.append(Or(*bug_link_clauses))
    clauses.append(_userCanAccessSubmissionStormClause(params.user))

    return BugTaskFlat.bug_id.is_in(
        Select(Bug.id, tables=tables, where=And(*clauses)))


def _build_blueprint_related_clause(params):
    """Find bugs related to Blueprints, or not."""
    linked_blueprints = params.linked_blueprints

    def make_clause(blueprints=None):
        where = [SpecificationBug.bugID == BugTaskFlat.bug_id]
        if blueprints is not None:
            where.append(
                search_value_to_storm_where_condition(
                    SpecificationBug.specificationID, blueprints))
        return Exists(Select(1, tables=[SpecificationBug], where=And(*where)))

    if linked_blueprints is None:
        return None
    elif zope_isinstance(linked_blueprints, BaseItem):
        if linked_blueprints == BugBlueprintSearch.BUGS_WITH_BLUEPRINTS:
            return make_clause()
        elif (linked_blueprints ==
                BugBlueprintSearch.BUGS_WITHOUT_BLUEPRINTS):
            return Not(make_clause())
    else:
        # A specific search term has been supplied.
        return make_clause(linked_blueprints)


# Upstream task restrictions

def _build_pending_bugwatch_elsewhere_clause(params):
    """Return a clause for BugTaskSearchParams.pending_bugwatch_elsewhere
    """
    RelatedBugTask = ClassAlias(BugTask)
    extra_joins = []
    # Normally we want to exclude the current task from the search,
    # unless we're looking at an upstream project.
    task_match_clause = RelatedBugTask.id != BugTaskFlat.bugtask_id
    target = None
    if params.product:
        # Looking for pending bugwatches in a project context is
        # special: instead of returning bugs with *other* tasks that
        # need forwarding, we return the subset of these tasks that
        # does. So the task ID should match, and there is no need for a
        # target clause.
        target = params.product
        task_match_clause = RelatedBugTask.id == BugTaskFlat.bugtask_id
        target_clause = True
    elif params.upstream_target:
        # Restrict the target to params.upstream_target.
        target = params.upstream_target
        if IProduct.providedBy(target):
            target_col = RelatedBugTask.productID
        elif IDistribution.providedBy(target):
            target_col = RelatedBugTask.distributionID
        else:
            raise AssertionError(
                'params.upstream_target must be a Distribution or '
                'a Product')
        target_clause = target_col == target.id
    else:
        # Restrict the target to distributions or products which don't
        # use Launchpad for bug tracking.
        OtherDistribution = ClassAlias(Distribution)
        OtherProduct = ClassAlias(Product)
        extra_joins = [
            LeftJoin(
                OtherDistribution,
                OtherDistribution.id == RelatedBugTask.distributionID),
            LeftJoin(
                OtherProduct,
                OtherProduct.id == RelatedBugTask.productID),
            ]
        target_clause = Or(
            OtherDistribution.official_malone == False,
            OtherProduct.official_malone == False)

    # We only include tasks on targets that don't use Launchpad for bug
    # tracking. If we're examining a single target, get out early if it
    # uses LP.
    if target and target.official_malone:
        return False

    # Include only bugtasks that have other bugtasks on matching
    # targets which are not Invalid and have no bug watch.
    return Exists(Select(
        1,
        tables=[RelatedBugTask] + extra_joins,
        where=And(
            RelatedBugTask.bugID == BugTaskFlat.bug_id,
            task_match_clause,
            RelatedBugTask.bugwatchID == None,
            RelatedBugTask._status != BugTaskStatus.INVALID,
            target_clause)))


def _build_no_upstream_bugtask_clause(params):
    """Return a clause for BugTaskSearchParams.has_no_upstream_bugtask."""
    OtherBugTask = ClassAlias(BugTask)
    if params.upstream_target is None:
        target = OtherBugTask.productID != None
    elif IProduct.providedBy(params.upstream_target):
        target = OtherBugTask.productID == params.upstream_target.id
    elif IDistribution.providedBy(params.upstream_target):
        target = OtherBugTask.distributionID == params.upstream_target.id
    else:
        raise AssertionError(
            'params.upstream_target must be a Distribution or '
            'a Product')
    return Not(Exists(Select(
        1, tables=[OtherBugTask],
        where=And(OtherBugTask.bugID == BugTaskFlat.bug_id, target))))


def _build_open_or_resolved_upstream_clause(params,
                                      statuses_for_watch_tasks,
                                      statuses_for_upstream_tasks):
    """Return a clause for BugTaskSearchParams.open_upstream or
    BugTaskSearchParams.resolved_upstream."""
    RelatedBugTask = ClassAlias(BugTask)
    watch_status_clause = search_value_to_storm_where_condition(
        RelatedBugTask._status, any(*statuses_for_watch_tasks))
    no_watch_status_clause = search_value_to_storm_where_condition(
        RelatedBugTask._status, any(*statuses_for_upstream_tasks))
    if params.upstream_target is None:
        watch_target_clause = True
        no_watch_target_clause = RelatedBugTask.productID != None
    else:
        if IProduct.providedBy(params.upstream_target):
            target_col = RelatedBugTask.productID
        elif IDistribution.providedBy(params.upstream_target):
            target_col = RelatedBugTask.distributionID
        else:
            raise AssertionError(
                'params.upstream_target must be a Distribution or '
                'a Product')
        watch_target_clause = no_watch_target_clause = (
            target_col == params.upstream_target.id)
    return Exists(Select(
        1,
        tables=[RelatedBugTask],
        where=And(
            RelatedBugTask.bugID == BugTaskFlat.bug_id,
            RelatedBugTask.id != BugTaskFlat.bugtask_id,
            Or(
                And(watch_target_clause,
                    RelatedBugTask.bugwatchID != None,
                    watch_status_clause),
                And(no_watch_target_clause,
                    RelatedBugTask.bugwatchID == None,
                    no_watch_status_clause)))))


def _build_open_upstream_clause(params):
    """Return a clause for BugTaskSearchParams.open_upstream."""
    statuses_for_open_tasks = [
        BugTaskStatus.NEW,
        BugTaskStatus.INCOMPLETE,
        BugTaskStatusSearch.INCOMPLETE_WITHOUT_RESPONSE,
        BugTaskStatusSearch.INCOMPLETE_WITH_RESPONSE,
        BugTaskStatus.CONFIRMED,
        BugTaskStatus.INPROGRESS,
        BugTaskStatus.UNKNOWN]
    return _build_open_or_resolved_upstream_clause(
        params, statuses_for_open_tasks, statuses_for_open_tasks)


def _build_resolved_upstream_clause(params):
    """Return a clause for BugTaskSearchParams.open_upstream."""
    # Our definition of "resolved upstream" means:
    #
    # * bugs with bugtasks linked to watches that are invalid,
    #   fixed committed or fix released
    #
    # * bugs with upstream bugtasks that are fix committed or fix released
    #
    # This definition of "resolved upstream" should address the use
    # cases we gathered at UDS Paris (and followup discussions with
    # seb128, sfllaw, et al.)
    statuses_for_watch_tasks = [
        BugTaskStatus.INVALID,
        BugTaskStatus.FIXCOMMITTED,
        BugTaskStatus.FIXRELEASED]
    statuses_for_upstream_tasks = [
        BugTaskStatus.FIXCOMMITTED,
        BugTaskStatus.FIXRELEASED]
    return _build_open_or_resolved_upstream_clause(
        params, statuses_for_watch_tasks, statuses_for_upstream_tasks)


def _build_upstream_clause(params):
    """Return an clause for returning upstream data if the data exists.

    This method will handles BugTasks that do not have upstream BugTasks
    as well as thoses that do.
    """
    params = _require_params(params)
    upstream_clauses = []
    if params.pending_bugwatch_elsewhere:
        upstream_clauses.append(
            _build_pending_bugwatch_elsewhere_clause(params))
    if params.has_no_upstream_bugtask:
        upstream_clauses.append(
            _build_no_upstream_bugtask_clause(params))
    if params.resolved_upstream:
        upstream_clauses.append(
            _build_resolved_upstream_clause(params))
    if params.open_upstream:
        upstream_clauses.append(
            _build_open_upstream_clause(params))

    if upstream_clauses:
        return Or(*upstream_clauses)
    return None


# Tag restrictions

def _build_tag_set_query(clauses):
    subselects = [
        Select(
            1, tables=[BugTag], where=And(BugTag.bugID == BugTaskFlat.bug_id,
            clause))
        for clause in clauses]
    if len(subselects) == 1:
        return Exists(subselects[0])
    else:
        return And(*(Exists(subselect) for subselect in subselects))


def _build_tag_set_query_all(tags):
    """Return a Storm expression for bugs matching all given tags.

    :param tags: An iterable of valid tags without - or + and not wildcards.
    :return: A Storm expression or None if no tags were provided.
    """
    if not tags:
        return None
    return _build_tag_set_query([BugTag.tag == tag for tag in sorted(tags)])


def _build_tag_set_query_any(tags):
    """Return a Storm expression for bugs matching any given tag.

    :param tags: An iterable of valid tags without - or + and not wildcards.
    :return: A Storm expression or None if no tags were provided.
    """
    if not tags:
        return None
    return _build_tag_set_query([BugTag.tag.is_in(sorted(tags))])


def _build_tag_search_clause(tags_spec):
    """Return a tag search clause.

    :param tags_spec: An instance of `any` or `all` containing tag
        "specifications". A tag specification is a valid tag name
        optionally prefixed by a minus sign (denoting "not"), or an
        asterisk (denoting "any tag"), again optionally prefixed by a
        minus sign (and thus denoting "not any tag").
    """
    tags = set(tags_spec.query_values)
    wildcards = [tag for tag in tags if tag in ('*', '-*')]
    tags.difference_update(wildcards)
    include = [tag for tag in tags if not tag.startswith('-')]
    exclude = [tag[1:] for tag in tags if tag.startswith('-')]

    # Should we search for all specified tags or any of them?
    find_all = zope_isinstance(tags_spec, all)

    if find_all:
        # How to combine an include clause and an exclude clause when
        # both are generated.
        combine_with = And
        # The set of bugs that have *all* of the tags requested for
        # *inclusion*.
        include_clause = _build_tag_set_query_all(include)
        # The set of bugs that have *any* of the tags requested for
        # *exclusion*.
        exclude_clause = _build_tag_set_query_any(exclude)
    else:
        # How to combine an include clause and an exclude clause when
        # both are generated.
        combine_with = Or
        # The set of bugs that have *any* of the tags requested for
        # inclusion.
        include_clause = _build_tag_set_query_any(include)
        # The set of bugs that have *all* of the tags requested for
        # exclusion.
        exclude_clause = _build_tag_set_query_all(exclude)

    universal_clause = (
        Exists(Select(
            1, tables=[BugTag], where=BugTag.bugID == BugTaskFlat.bug_id)))

    # Search for the *presence* of any tag.
    if '*' in wildcards:
        # Only clobber the clause if not searching for all tags.
        if include_clause == None or not find_all:
            include_clause = universal_clause

    # Search for the *absence* of any tag.
    if '-*' in wildcards:
        # Only clobber the clause if searching for all tags.
        if exclude_clause == None or find_all:
            exclude_clause = universal_clause

    # Combine the include and exclude sets.
    if include_clause != None and exclude_clause != None:
        return combine_with(include_clause, Not(exclude_clause))
    elif include_clause != None:
        return include_clause
    elif exclude_clause != None:
        return Not(exclude_clause)
    else:
        # This means that there were no tags (wildcard or specific) to
        # search for (which is allowed, even if it's a bit weird).
        return None


# Privacy restrictions

def get_bug_privacy_filter(user):
    """An SQL filter for search results that adds privacy-awareness."""
    return _get_bug_privacy_filter_with_decorator(user)[0]


def _nocache_bug_decorator(obj):
    """A pass through decorator for consistency.

    :seealso: _get_bug_privacy_filter_with_decorator
    """
    return obj


def _make_cache_user_can_view_bug(user):
    """Curry a decorator for bugtask queries to cache permissions.

    :seealso: _get_bug_privacy_filter_with_decorator
    """
    userid = user.id

    def cache_user_can_view_bug(bugtask):
        get_property_cache(bugtask.bug)._known_viewers = set([userid])
        return bugtask
    return cache_user_can_view_bug


def _get_bug_privacy_filter_with_decorator(user):
    """Return a SQL filter to limit returned bug tasks.

    :param user: The user whose visible bugs will be filtered.
    :return: A SQL filter, a decorator to cache visibility in a resultset that
        returns BugTask objects.
    """
    # Admins can see all bugs, so we can short-circuit the filter.
    if user is not None and IPersonRoles(user).in_admin:
        return True, _nocache_bug_decorator

    # We want an actual Storm Person.
    if IPersonRoles.providedBy(user):
        user = user.person

    bug_filter_terms = get_bug_privacy_filter_terms(user, check_admin=False)
    if len(bug_filter_terms) == 1:
        return bug_filter_terms[0], _nocache_bug_decorator

    expr = Or(*bug_filter_terms)
    return expr, _make_cache_user_can_view_bug(user)


def get_bug_privacy_filter_terms(user, check_admin=True):
    """Return Storm terms for filtering bugs by visibility.

    The same rules as get_bug_bulk_privacy_filter_terms, except designed
    and optimised for cases like bug searches, where we have a small
    number of users and a lot of bugs.

    Also unlike get_bug_bulk_privacy_filter_terms, this constrains
    BugTaskFlat to user, rather than user to a bug column. It's up to
    callsites to work with BugTaskFlat.

    :param user: a Person ID value or column reference.
    :param check_admin: add an admin role check. This is probably only
        necessary when checking multiple users; if you're only checking a
        specific one, you can do the admin check beforehand.
    :return: a Storm expression relating person to bug, where bug is visible
        to person.
    """
    public_bug_filter = (
        BugTaskFlat.information_type.is_in(PUBLIC_INFORMATION_TYPES))

    if user is None:
        return [public_bug_filter]

    artifact_grant_query = Coalesce(
            ArrayIntersects(SQL('BugTaskFlat.access_grants'),
            Select(
                ArrayAgg(TeamParticipation.teamID),
                tables=TeamParticipation,
                where=(TeamParticipation.person == user)
            )), False)

    policy_grant_query = Coalesce(
            ArrayIntersects(SQL('BugTaskFlat.access_policies'),
            Select(
                ArrayAgg(AccessPolicyGrant.policy_id),
                tables=(AccessPolicyGrant,
                        Join(TeamParticipation,
                            TeamParticipation.teamID ==
                            AccessPolicyGrant.grantee_id)),
                where=(TeamParticipation.person == user)
            )), False)

    filters = [public_bug_filter, artifact_grant_query, policy_grant_query]

    if check_admin:
        filters.append(
            Exists(Select(
                1, tables=[TeamParticipation],
                where=And(
                    TeamParticipation.person == user,
                    TeamParticipation.team ==
                        getUtility(ILaunchpadCelebrities).admin))))

    return filters


def get_bug_bulk_privacy_filter_terms(person, bug):
    """Return Storm terms for filtering people by bug visibility.

    The same rules as get_bug_privacy_filter_terms, except that it's
    designed and optimised for cases like bug notifications, where we
    have a small number of bug and need to check which people can see
    them.

    :param person: a Person ID value or column reference.
    :param bug: a Bug ID value or column reference.
    :return: a Storm expression relating person to bug, where bug is visible
        to person.
    """
    # This whole query is a bit ugly what with the repeated BugTaskFlat
    # SELECTs and all that, but it's an order of magnitude faster than
    # joining at a higher level, and a thousand times faster than
    # get_bug_privacy_filter_terms for some cases. Test carefully
    # (particularly with the structural subscription queries) before
    # touching.

    select_btf = (
        lambda select, *conds: Select(
            select, tables=[BugTaskFlat],
            where=And(BugTaskFlat.bug == bug, *conds)))
    # Admins, artifact grantees, and policy grantees can all see private
    # bugs.
    teams = Union(
        Select(getUtility(ILaunchpadCelebrities).admin.id),
        select_btf(Unnest(BugTaskFlat.access_grants)),
        Select(
            AccessPolicyGrant.grantee_id,
            tables=[AccessPolicyGrant],
            where=In(
                AccessPolicyGrant.policy_id,
                select_btf(
                    Unnest(BugTaskFlat.access_policies)))))
    # And we need to expand team memberships.
    participants = Select(
        TeamParticipation.personID,
        tables=[TeamParticipation],
        where=In(TeamParticipation.teamID, teams))
    # The bug must public, or the user must satisfy the above criteria.
    return Or(
        Exists(select_btf(
            1, BugTaskFlat.information_type.is_in(PUBLIC_INFORMATION_TYPES))),
        In(person, participants))
