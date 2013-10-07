# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from testtools.content import text_content
from testtools.matchers import MatchesRegex
import transaction
from zope.component import getUtility

from lp.app.enums import InformationType
from lp.bugs.interfaces.bugtask import (
    BugTaskImportance,
    BugTaskStatus,
    IBugTaskSet,
    )
from lp.bugs.scripts.bugsummaryrebuild import (
    apply_bugsummary_changes,
    calculate_bugsummary_changes,
    calculate_bugsummary_rows,
    format_target,
    get_bugsummary_rows,
    get_bugsummary_targets,
    get_bugsummaryjournal_rows,
    get_bugtask_targets,
    RawBugSummary,
    rebuild_bugsummary_for_target,
    )
from lp.registry.interfaces.accesspolicy import IAccessPolicySource
from lp.services.database.interfaces import IStore
from lp.services.log.logger import BufferLogger
from lp.testing import TestCaseWithFactory
from lp.testing.dbuser import dbuser
from lp.testing.layers import (
    LaunchpadZopelessLayer,
    ZopelessDatabaseLayer,
    )
from lp.testing.script import run_script


def rollup_journal():
    IStore(RawBugSummary).execute('SELECT bugsummary_rollup_journal()')


def create_tasks(factory):
    ps = factory.makeProductSeries()
    product = ps.product
    sp = factory.makeSourcePackage(publish=True)

    bug = factory.makeBug(target=product)
    getUtility(IBugTaskSet).createManyTasks(
        bug, bug.owner, [sp, sp.distribution_sourcepackage, ps])

    # There'll be a target for each task, plus a packageless one for
    # each package task.
    expected_targets = [
        (ps.product.id, None, None, None, None),
        (None, ps.id, None, None, None),
        (None, None, sp.distribution.id, None, None),
        (None, None, sp.distribution.id, None, sp.sourcepackagename.id),
        (None, None, None, sp.distroseries.id, None),
        (None, None, None, sp.distroseries.id, sp.sourcepackagename.id)
        ]
    return expected_targets


class TestBugSummaryRebuild(TestCaseWithFactory):

    layer = ZopelessDatabaseLayer

    def test_get_bugsummary_targets(self):
        # get_bugsummary_targets returns the set of target tuples that are
        # currently represented in BugSummary.
        orig_targets = get_bugsummary_targets()
        expected_targets = create_tasks(self.factory)
        rollup_journal()
        new_targets = get_bugsummary_targets()
        self.assertContentEqual(expected_targets, new_targets - orig_targets)

    def test_get_bugtask_targets(self):
        # get_bugtask_targets returns the set of target tuples that are
        # currently represented in BugTask.
        orig_targets = get_bugtask_targets()
        expected_targets = create_tasks(self.factory)
        new_targets = get_bugtask_targets()
        self.assertContentEqual(expected_targets, new_targets - orig_targets)

    def test_calculate_bugsummary_changes(self):
        # calculate_bugsummary_changes returns the changes required
        # to make the old dict match the new, as a tuple of
        # (added, updated, removed)
        changes = calculate_bugsummary_changes(
            dict(a=2, b=10, c=3), dict(a=2, c=5, d=4))
        self.assertEqual((dict(d=4), dict(c=5), ['b']), changes)

    def test_apply_bugsummary_changes(self):
        # apply_bugsummary_changes takes a target and a tuple of changes
        # from calculate_bugsummary_changes and flushes the changes to
        # the DB.
        product = self.factory.makeProduct()
        self.assertContentEqual([], get_bugsummary_rows(product))
        NEW = BugTaskStatus.NEW
        TRIAGED = BugTaskStatus.TRIAGED
        LOW = BugTaskImportance.LOW
        HIGH = BugTaskImportance.HIGH

        # Add a couple of rows to start.
        with dbuser('bugsummaryrebuild'):
            apply_bugsummary_changes(
                product,
                {(NEW, None, HIGH, False, None, None, None): 2,
                (TRIAGED, None, LOW, False, None, None, None): 4},
                {}, [])
        self.assertContentEqual(
            [(NEW, None, HIGH, False, None, None, None, 2),
             (TRIAGED, None, LOW, False, None, None, None, 4)],
            get_bugsummary_rows(product))

        # Delete one, mutate the other.
        with dbuser('bugsummaryrebuild'):
            apply_bugsummary_changes(
                product,
                {}, {(NEW, None, HIGH, False, None, None, None): 3},
                [(TRIAGED, None, LOW, False, None, None, None)])
        self.assertContentEqual(
            [(NEW, None, HIGH, False, None, None, None, 3)],
            get_bugsummary_rows(product))

    def test_rebuild_bugsummary_for_target(self):
        # rebuild_bugsummary_for_target rebuilds BugSummary for a
        # specific target from BugTaskFlat. Since it ignores the
        # journal, it also removes any relevant journal entries.
        product = self.factory.makeProduct()
        self.factory.makeBug(target=product)
        self.assertEqual(0, get_bugsummary_rows(product).count())
        self.assertEqual(1, get_bugsummaryjournal_rows(product).count())
        log = BufferLogger()
        with dbuser('bugsummaryrebuild'):
            rebuild_bugsummary_for_target(product, log)
        self.assertEqual(1, get_bugsummary_rows(product).count())
        self.assertEqual(0, get_bugsummaryjournal_rows(product).count())
        self.assertThat(
            log.getLogBufferAndClear(),
            MatchesRegex(
                'DEBUG Rebuilding %s\nDEBUG Added {.*: 1L}' % product.name))

    def test_script(self):
        product = self.factory.makeProduct()
        self.factory.makeBug(target=product)
        self.assertEqual(0, get_bugsummary_rows(product).count())
        self.assertEqual(1, get_bugsummaryjournal_rows(product).count())
        transaction.commit()

        exit_code, out, err = run_script('scripts/bugsummary-rebuild.py')
        self.addDetail("stdout", text_content(out))
        self.addDetail("stderr", text_content(err))
        self.assertEqual(0, exit_code)

        transaction.commit()
        self.assertEqual(1, get_bugsummary_rows(product).count())
        self.assertEqual(0, get_bugsummaryjournal_rows(product).count())


class TestGetBugSummaryRows(TestCaseWithFactory):

    layer = ZopelessDatabaseLayer

    def test_get_bugsummary_rows(self):
        product = self.factory.makeProduct()
        rollup_journal()
        orig_rows = set(get_bugsummary_rows(product))
        task = self.factory.makeBug(target=product).default_bugtask
        rollup_journal()
        new_rows = set(get_bugsummary_rows(product))
        self.assertContentEqual(
            [(task.status, None, task.importance, False, None, None, None, 1)],
            new_rows - orig_rows)


class TestCalculateBugSummaryRows(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def test_public_untagged(self):
        # Public untagged bugs show up in a single row, with both tag
        # and viewed_by = None.
        product = self.factory.makeProduct()
        bug = self.factory.makeBug(target=product).default_bugtask
        self.assertContentEqual(
            [(bug.status, None, bug.importance, False, None, None, None, 1)],
            calculate_bugsummary_rows(product))

    def test_public_tagged(self):
        # Public tagged bugs show up in a row for each tag, plus an
        # untagged row.
        product = self.factory.makeProduct()
        bug = self.factory.makeBug(
            target=product, tags=[u'foo', u'bar']).default_bugtask
        self.assertContentEqual(
            [(bug.status, None, bug.importance, False, None, None, None, 1),
             (bug.status, None, bug.importance, False, u'foo', None, None, 1),
             (bug.status, None, bug.importance, False, u'bar', None, None, 1),
            ], calculate_bugsummary_rows(product))

    def test_private_untagged(self):
        # Private untagged bugs show up with tag = None, viewed_by =
        # subscriber; and tag = None, access_policy = ap. There's no
        # viewed_by = None, access_policy = None row.
        product = self.factory.makeProduct()
        o = self.factory.makePerson()
        bug = self.factory.makeBug(
            target=product, owner=o,
            information_type=InformationType.USERDATA).default_bugtask
        [ap] = getUtility(IAccessPolicySource).find(
            [(product, InformationType.USERDATA)])
        self.assertContentEqual(
            [(bug.status, None, bug.importance, False, None, o.id, None, 1),
             (bug.status, None, bug.importance, False, None, None, ap.id, 1)],
            calculate_bugsummary_rows(product))

    def test_private_tagged(self):
        # Private tagged bugs show up with viewed_by = subscriber and
        # access_policy = ap rows, each with a row for each tag plus an
        # untagged row.
        product = self.factory.makeProduct()
        o = self.factory.makePerson()
        bug = self.factory.makeBug(
            target=product, owner=o, tags=[u'foo', u'bar'],
            information_type=InformationType.USERDATA).default_bugtask
        [ap] = getUtility(IAccessPolicySource).find(
            [(product, InformationType.USERDATA)])
        self.assertContentEqual(
            [(bug.status, None, bug.importance, False, None, o.id, None, 1),
             (bug.status, None, bug.importance, False, u'foo', o.id, None, 1),
             (bug.status, None, bug.importance, False, u'bar', o.id, None, 1),
             (bug.status, None, bug.importance, False, None, None, ap.id, 1),
             (bug.status, None, bug.importance, False, u'foo', None, ap.id, 1),
             (bug.status, None, bug.importance, False, u'bar', None, ap.id, 1),
            ],
            calculate_bugsummary_rows(product))

    def test_aggregation(self):
        # Multiple bugs with the same attributes appear in a single
        # aggregate row with an increased count.
        product = self.factory.makeProduct()
        bug1 = self.factory.makeBug(target=product).default_bugtask
        self.factory.makeBug(target=product).default_bugtask
        bug3 = self.factory.makeBug(
            target=product, status=BugTaskStatus.TRIAGED).default_bugtask
        self.assertContentEqual(
            [(bug1.status, None, bug1.importance, False, None, None, None, 2),
             (bug3.status, None, bug3.importance, False, None, None, None, 1)],
            calculate_bugsummary_rows(product))

    def test_has_patch(self):
        # Bugs with a patch attachment (latest_patch_uploaded is not
        # None) have has_patch=True.
        product = self.factory.makeProduct()
        bug1 = self.factory.makeBug(target=product).default_bugtask
        self.factory.makeBugAttachment(bug=bug1.bug, is_patch=True)
        bug2 = self.factory.makeBug(
            target=product, status=BugTaskStatus.TRIAGED).default_bugtask
        self.assertContentEqual(
            [(bug1.status, None, bug1.importance, True, None, None, None, 1),
             (bug2.status, None, bug2.importance, False, None, None, None, 1)],
            calculate_bugsummary_rows(product))

    def test_milestone(self):
        # Milestoned bugs only show up with the milestone set.
        product = self.factory.makeProduct()
        mile1 = self.factory.makeMilestone(product=product)
        mile2 = self.factory.makeMilestone(product=product)
        bug1 = self.factory.makeBug(
            target=product, milestone=mile1).default_bugtask
        bug2 = self.factory.makeBug(
            target=product, milestone=mile2,
            status=BugTaskStatus.TRIAGED).default_bugtask
        self.assertContentEqual(
            [(bug1.status, mile1.id, bug1.importance, False, None, None, None,
              1),
             (bug2.status, mile2.id, bug2.importance, False, None, None, None,
              1)],
            calculate_bugsummary_rows(product))

    def test_distribution_includes_packages(self):
        # Distribution and DistroSeries calculations include their
        # packages' bugs.
        dsp = self.factory.makeSourcePackage(
            publish=True).distribution_sourcepackage
        sp = self.factory.makeSourcePackage(publish=True)
        bug1 = self.factory.makeBugTask(target=dsp)
        bug1.transitionToStatus(BugTaskStatus.INVALID, bug1.owner)
        bug2 = self.factory.makeBugTask(target=sp)
        bug1.transitionToStatus(BugTaskStatus.CONFIRMED, bug2.owner)

        # The DistributionSourcePackage task shows up in the
        # Distribution's rows.
        self.assertContentEqual(
            [(bug1.status, None, bug1.importance, False, None, None, None, 1)],
            calculate_bugsummary_rows(dsp.distribution))
        self.assertContentEqual(
            calculate_bugsummary_rows(dsp.distribution),
            calculate_bugsummary_rows(dsp))

        # The SourcePackage task shows up in the DistroSeries' rows.
        self.assertContentEqual(
            [(bug2.status, None, bug2.importance, False, None, None, None, 1)],
            calculate_bugsummary_rows(sp.distroseries))
        self.assertContentEqual(
            calculate_bugsummary_rows(sp.distroseries),
            calculate_bugsummary_rows(sp))


class TestFormatTarget(TestCaseWithFactory):

    layer = ZopelessDatabaseLayer

    def test_product(self):
        product = self.factory.makeProduct(name='fooix')
        self.assertEqual('fooix', format_target(product))

    def test_productseries(self):
        productseries = self.factory.makeProductSeries(
            product=self.factory.makeProduct(name='fooix'), name='1.0')
        self.assertEqual('fooix/1.0', format_target(productseries))

    def test_distribution(self):
        distribution = self.factory.makeDistribution(name='fooix')
        self.assertEqual('fooix', format_target(distribution))

    def test_distroseries(self):
        distroseries = self.factory.makeDistroSeries(
            distribution=self.factory.makeDistribution(name='fooix'),
            name='1.0')
        self.assertEqual('fooix/1.0', format_target(distroseries))

    def test_distributionsourcepackage(self):
        distribution = self.factory.makeDistribution(name='fooix')
        dsp = distribution.getSourcePackage(
            self.factory.makeSourcePackageName('bar'))
        self.assertEqual('fooix/+source/bar', format_target(dsp))

    def test_sourcepackage(self):
        distroseries = self.factory.makeDistroSeries(
            distribution=self.factory.makeDistribution(name='fooix'),
            name='1.0')
        sp = distroseries.getSourcePackage(
            self.factory.makeSourcePackageName('bar'))
        self.assertEqual('fooix/1.0/+source/bar', format_target(sp))
