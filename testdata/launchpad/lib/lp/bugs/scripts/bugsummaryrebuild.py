# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from storm.expr import (
    Alias,
    And,
    Cast,
    Count,
    Join,
    Or,
    Select,
    Union,
    With,
    )
from storm.properties import Bool
import transaction

from lp.app.enums import (
    PRIVATE_INFORMATION_TYPES,
    PUBLIC_INFORMATION_TYPES,
    )
from lp.bugs.model.bug import BugTag
from lp.bugs.model.bugsummary import BugSummary
from lp.bugs.model.bugtask import (
    bug_target_from_key,
    bug_target_to_key,
    BugTask,
    )
from lp.bugs.model.bugtaskflat import BugTaskFlat
from lp.registry.interfaces.distribution import IDistribution
from lp.registry.interfaces.distroseries import IDistroSeries
from lp.registry.interfaces.series import ISeriesMixin
from lp.registry.model.distribution import Distribution
from lp.registry.model.distroseries import DistroSeries
from lp.registry.model.product import Product
from lp.registry.model.productseries import ProductSeries
from lp.registry.model.sourcepackagename import SourcePackageName
from lp.services.database.bulk import create
from lp.services.database.interfaces import IStore
from lp.services.database.stormexpr import Unnest
from lp.services.looptuner import TunableLoop


class RawBugSummary(BugSummary):
    """Like BugSummary, except based on the raw DB table.

    BugSummary is actually based on the combinedbugsummary view.
    """
    __storm_table__ = 'bugsummary'


class BugSummaryJournal(BugSummary):
    """Just the necessary columns of BugSummaryJournal."""
    # It's not really BugSummary, but the schema is the same.
    __storm_table__ = 'bugsummaryjournal'


def get_bugsummary_targets():
    """Get the current set of targets represented in BugSummary."""
    return set(IStore(RawBugSummary).find(
        (RawBugSummary.product_id, RawBugSummary.productseries_id,
         RawBugSummary.distribution_id, RawBugSummary.distroseries_id,
         RawBugSummary.sourcepackagename_id)).config(distinct=True))


def get_bugtask_targets():
    """Get the current set of targets represented in BugTask."""
    new_targets = set(IStore(BugTask).find(
        (BugTask.productID, BugTask.productseriesID,
         BugTask.distributionID, BugTask.distroseriesID,
         BugTask.sourcepackagenameID)).config(distinct=True))
    # BugSummary counts package tasks in the packageless totals, so
    # ensure that there's also a packageless total for each distro(series).
    new_targets.update(set(
        (p, ps, d, ds, None) for (p, ps, d, ds, spn) in new_targets))
    return new_targets


def load_target(pid, psid, did, dsid, spnid):
    store = IStore(Product)
    p, ps, d, ds, spn = map(
        lambda (cls, id): store.get(cls, id) if id is not None else None,
        zip((Product, ProductSeries, Distribution, DistroSeries,
             SourcePackageName),
            (pid, psid, did, dsid, spnid)))
    return bug_target_from_key(p, ps, d, ds, spn)


def format_target(target):
    id = target.pillar.name
    series = (
        (ISeriesMixin.providedBy(target) and target)
        or getattr(target, 'distroseries', None)
        or getattr(target, 'productseries', None))
    if series:
        id += '/%s' % series.name
    spn = getattr(target, 'sourcepackagename', None)
    if spn:
        id += '/+source/%s' % spn.name
    return id


def _get_bugsummary_constraint_bits(target):
    raw_key = bug_target_to_key(target)
    # Map to ID columns to work around Storm bug #682989.
    return dict(
        ('%s_id' % k, v.id if v else None) for (k, v) in raw_key.items())


def get_bugsummary_constraint(target, cls=RawBugSummary):
    """Convert an `IBugTarget` to a list of constraints on RawBugSummary."""
    # Map to ID columns to work around Storm bug #682989.
    return [
        getattr(cls, k) == v
        for (k, v) in _get_bugsummary_constraint_bits(target).iteritems()]


def get_bugtaskflat_constraint(target):
    """Convert an `IBugTarget` to a list of constraints on BugTaskFlat."""
    raw_key = bug_target_to_key(target)
    # For the purposes of BugSummary, DSP/SP tasks count for their
    # distro(series).
    if IDistribution.providedBy(target) or IDistroSeries.providedBy(target):
        del raw_key['sourcepackagename']
    # Map to ID columns to work around Storm bug #682989.
    return [
        getattr(BugTaskFlat, '%s_id' % k) == (v.id if v else None)
        for (k, v) in raw_key.items()]


def get_bugsummary_rows(target):
    """Find the `RawBugSummary` rows for the given `IBugTarget`.

    RawBugSummary is the bugsummary table in the DB, not to be confused
    with BugSummary which is actually combinedbugsummary, a view over
    bugsummary and bugsummaryjournal.
    """
    return IStore(RawBugSummary).find(
        (RawBugSummary.status, RawBugSummary.milestone_id,
         RawBugSummary.importance, RawBugSummary.has_patch, RawBugSummary.tag,
         RawBugSummary.viewed_by_id, RawBugSummary.access_policy_id,
         RawBugSummary.count),
        *get_bugsummary_constraint(target))


def get_bugsummaryjournal_rows(target):
    """Find the `BugSummaryJournal` rows for the given `IBugTarget`."""
    return IStore(BugSummaryJournal).find(
        BugSummaryJournal,
        *get_bugsummary_constraint(target, cls=BugSummaryJournal))


def calculate_bugsummary_changes(old, new):
    """Calculate the changes between between the new and old dicts.

    Takes {key: int} dicts, returns items from the new dict that differ
    from the old one.
    """
    keys = set()
    keys.update(old.iterkeys())
    keys.update(new.iterkeys())
    added = {}
    updated = {}
    removed = []
    for key in keys:
        old_val = old.get(key, 0)
        new_val = new.get(key, 0)
        if old_val == new_val:
            continue
        if old_val and not new_val:
            removed.append(key)
        elif new_val and not old_val:
            added[key] = new_val
        else:
            updated[key] = new_val
    return added, updated, removed


def apply_bugsummary_changes(target, added, updated, removed):
    """Apply a set of BugSummary changes to the DB."""
    bits = _get_bugsummary_constraint_bits(target)
    target_key = tuple(map(
        bits.__getitem__,
        ('product_id', 'productseries_id', 'distribution_id',
         'distroseries_id', 'sourcepackagename_id')))
    target_cols = (
        RawBugSummary.product_id, RawBugSummary.productseries_id,
        RawBugSummary.distribution_id, RawBugSummary.distroseries_id,
        RawBugSummary.sourcepackagename_id)
    key_cols = (
        RawBugSummary.status, RawBugSummary.milestone_id,
        RawBugSummary.importance, RawBugSummary.has_patch,
        RawBugSummary.tag, RawBugSummary.viewed_by_id,
        RawBugSummary.access_policy_id)

    # Postgres doesn't do bulk updates, so do a delete+add.
    for key, count in updated.iteritems():
        removed.append(key)
        added[key] = count

    # Delete any excess rows. We do it in batches of 100 to avoid enormous ORs
    while removed:
        chunk = removed[:100]
        removed = removed[100:]
        exprs = [
            map(lambda (k, v): k == v, zip(key_cols, key))
            for key in chunk]
        IStore(RawBugSummary).find(
            RawBugSummary,
            Or(*[And(*expr) for expr in exprs]),
            *get_bugsummary_constraint(target)).remove()

    # Add any new rows. We know this scales up to tens of thousands, so just
    # do it in one hit.
    if added:
        create(
            target_cols + key_cols + (RawBugSummary.count,),
            [target_key + key + (count,) for key, count in added.iteritems()])


def rebuild_bugsummary_for_target(target, log):
    log.debug("Rebuilding %s" % format_target(target))
    existing = dict(
        (v[:-1], v[-1]) for v in get_bugsummary_rows(target))
    expected = dict(
        (v[:-1], v[-1]) for v in calculate_bugsummary_rows(target))
    added, updated, removed = calculate_bugsummary_changes(existing, expected)
    if added:
        log.debug('Added %r' % added)
    if updated:
        log.debug('Updated %r' % updated)
    if removed:
        log.debug('Removed %r' % removed)
    apply_bugsummary_changes(target, added, updated, removed)
    # We've just made bugsummary match reality, ignoring any
    # bugsummaryjournal rows. So any journal rows are at best redundant,
    # or at worst incorrect. Kill them.
    get_bugsummaryjournal_rows(target).remove()


def calculate_bugsummary_rows(target):
    """Calculate BugSummary row fragments for the given `IBugTarget`.

    The data is re-aggregated from BugTaskFlat, BugTag and BugSubscription.
    """
    # Use a CTE to prepare a subset of BugTaskFlat, filtered to the
    # relevant target and to exclude duplicates, and with has_patch
    # calculated.
    relevant_tasks = With(
        'relevant_task',
        Select(
            (BugTaskFlat.bug_id, BugTaskFlat.information_type,
             BugTaskFlat.status, BugTaskFlat.milestone_id,
             BugTaskFlat.importance,
             Alias(BugTaskFlat.latest_patch_uploaded != None, 'has_patch'),
             BugTaskFlat.access_grants, BugTaskFlat.access_policies),
            tables=[BugTaskFlat],
            where=And(
                BugTaskFlat.duplicateof_id == None,
                *get_bugtaskflat_constraint(target))))

    # Storm class to reference the CTE.
    class RelevantTask(BugTaskFlat):
        __storm_table__ = 'relevant_task'

        has_patch = Bool()

    # Storm class to reference the union.
    class BugSummaryPrototype(RawBugSummary):
        __storm_table__ = 'bugsummary_prototype'

    # Prepare a union for all combination of privacy and taggedness.
    # It'll return a full set of
    # (status, milestone, importance, has_patch, tag, viewed_by, access_policy)
    # rows.
    common_cols = (
        RelevantTask.status, RelevantTask.milestone_id,
        RelevantTask.importance, RelevantTask.has_patch)
    null_tag = Alias(Cast(None, 'text'), 'tag')
    null_viewed_by = Alias(Cast(None, 'integer'), 'viewed_by')
    null_policy = Alias(Cast(None, 'integer'), 'access_policy')

    tag_join = Join(BugTag, BugTag.bugID == RelevantTask.bug_id)

    public_constraint = RelevantTask.information_type.is_in(
        PUBLIC_INFORMATION_TYPES)
    private_constraint = RelevantTask.information_type.is_in(
        PRIVATE_INFORMATION_TYPES)

    unions = Union(
        # Public, tagless
        Select(
            common_cols + (null_tag, null_viewed_by, null_policy),
            tables=[RelevantTask], where=public_constraint),
        # Public, tagged
        Select(
            common_cols + (BugTag.tag, null_viewed_by, null_policy),
            tables=[RelevantTask, tag_join], where=public_constraint),
        # Private, access grant, tagless
        Select(
            common_cols +
            (null_tag, Unnest(RelevantTask.access_grants), null_policy),
            tables=[RelevantTask], where=private_constraint),
        # Private, access grant, tagged
        Select(
            common_cols +
            (BugTag.tag, Unnest(RelevantTask.access_grants), null_policy),
            tables=[RelevantTask, tag_join], where=private_constraint),
        # Private, access policy, tagless
        Select(
            common_cols +
            (null_tag, null_viewed_by, Unnest(RelevantTask.access_policies)),
            tables=[RelevantTask], where=private_constraint),
        # Private, access policy, tagged
        Select(
            common_cols +
            (BugTag.tag, null_viewed_by, Unnest(RelevantTask.access_policies)),
            tables=[RelevantTask, tag_join], where=private_constraint),
        all=True)

    # Select the relevant bits of the prototype rows and aggregate them.
    proto_key_cols = (
        BugSummaryPrototype.status, BugSummaryPrototype.milestone_id,
        BugSummaryPrototype.importance, BugSummaryPrototype.has_patch,
        BugSummaryPrototype.tag, BugSummaryPrototype.viewed_by_id,
        BugSummaryPrototype.access_policy_id)
    origin = IStore(BugTaskFlat).with_(relevant_tasks).using(
        Alias(unions, 'bugsummary_prototype'))
    results = origin.find(proto_key_cols + (Count(),))
    results = results.group_by(*proto_key_cols).order_by(*proto_key_cols)
    return results


class BugSummaryRebuildTunableLoop(TunableLoop):

    maximum_chunk_size = 100

    def __init__(self, log, dry_run, abort_time=None):
        super(BugSummaryRebuildTunableLoop, self).__init__(log, abort_time)
        self.dry_run = dry_run
        self.targets = list(
            get_bugsummary_targets().union(get_bugtask_targets()))
        self.offset = 0

    def isDone(self):
        return self.offset >= len(self.targets)

    def __call__(self, chunk_size):
        chunk_size = int(chunk_size)
        chunk = self.targets[self.offset:self.offset + chunk_size]

        for target_key in chunk:
            target = load_target(*target_key)
            rebuild_bugsummary_for_target(target, self.log)
        self.offset += len(chunk)

        if not self.dry_run:
            transaction.commit()
        else:
            transaction.abort()
