# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the bulk database functions."""

__metaclass__ = type

import datetime

from pytz import UTC
from storm.exceptions import ClassInfoError
from storm.expr import SQL
from storm.info import get_obj_info
from storm.store import Store
from testtools.matchers import Equals
import transaction
from zope.security import (
    checker,
    proxy,
    )

from lp.bugs.enums import BugNotificationLevel
from lp.bugs.model.bug import BugAffectsPerson
from lp.bugs.model.bugsubscription import BugSubscription
from lp.code.model.branchjob import (
    BranchJob,
    BranchJobType,
    ReclaimBranchSpaceJob,
    )
from lp.code.model.branchsubscription import BranchSubscription
from lp.registry.model.person import Person
from lp.services.database import bulk
from lp.services.database.interfaces import (
    IMasterStore,
    ISlaveStore,
    IStore,
    )
from lp.services.database.sqlbase import get_transaction_timestamp
from lp.services.features.model import (
    FeatureFlag,
    getFeatureStore,
    )
from lp.services.job.model.job import Job
from lp.soyuz.model.component import Component
from lp.testing import (
    StormStatementRecorder,
    TestCase,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.matchers import HasQueryCount


object_is_key = lambda thing: thing


class TestBasicFunctions(TestCase):

    def test_collate_empty_list(self):
        self.failUnlessEqual([], list(bulk.collate([], object_is_key)))

    def test_collate_when_object_is_key(self):
        self.failUnlessEqual(
            [(1, [1])],
            list(bulk.collate([1], object_is_key)))
        self.failUnlessEqual(
            [(1, [1]), (2, [2, 2])],
            sorted(bulk.collate([1, 2, 2], object_is_key)))

    def test_collate_with_key_function(self):
        self.failUnlessEqual(
            [(4, ['fred', 'joss']), (6, ['barney'])],
            sorted(bulk.collate(['fred', 'barney', 'joss'], len)))

    def test_get_type(self):
        self.failUnlessEqual(object, bulk.get_type(object()))

    def test_get_type_with_proxied_object(self):
        proxied_object = proxy.Proxy('fred', checker.Checker({}))
        self.failUnlessEqual(str, bulk.get_type(proxied_object))


class TestLoaders(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_gen_reload_queries_with_empty_list(self):
        self.failUnlessEqual([], list(bulk.gen_reload_queries([])))

    def test_gen_reload_queries_with_single_object(self):
        # gen_reload_queries() should generate a single query for a
        # single object.
        db_objects = [self.factory.makeSourcePackageName()]
        db_queries = list(bulk.gen_reload_queries(db_objects))
        self.failUnlessEqual(1, len(db_queries))
        db_query = db_queries[0]
        self.failUnlessEqual(db_objects, list(db_query))

    def test_gen_reload_queries_with_multiple_similar_objects(self):
        # gen_reload_queries() should generate a single query to load
        # multiple objects of the same type.
        db_objects = set(
            self.factory.makeSourcePackageName() for i in range(5))
        db_queries = list(bulk.gen_reload_queries(db_objects))
        self.failUnlessEqual(1, len(db_queries))
        db_query = db_queries[0]
        self.failUnlessEqual(db_objects, set(db_query))

    def test_gen_reload_queries_with_mixed_objects(self):
        # gen_reload_queries() should return one query for each
        # distinct object type in the given objects.
        db_objects = set(
            self.factory.makeSourcePackageName() for i in range(5))
        db_objects.update(
            self.factory.makeComponent() for i in range(5))
        db_queries = list(bulk.gen_reload_queries(db_objects))
        self.failUnlessEqual(2, len(db_queries))
        db_objects_loaded = set()
        for db_query in db_queries:
            objects = set(db_query)
            # None of these objects should have been loaded before.
            self.failUnlessEqual(
                set(), objects.intersection(db_objects_loaded))
            db_objects_loaded.update(objects)
        self.failUnlessEqual(db_objects, db_objects_loaded)

    def test_gen_reload_queries_with_mixed_stores(self):
        # gen_reload_queries() returns one query for each distinct
        # store even for the same object type.
        db_object = self.factory.makeComponent()
        db_object_type = bulk.get_type(db_object)
        # Commit so the database object is available in both master
        # and slave stores.
        transaction.commit()
        db_objects = set(
            (IMasterStore(db_object).get(db_object_type, db_object.id),
             ISlaveStore(db_object).get(db_object_type, db_object.id)))
        db_queries = list(bulk.gen_reload_queries(db_objects))
        self.failUnlessEqual(2, len(db_queries))
        db_objects_loaded = set()
        for db_query in db_queries:
            objects = set(db_query)
            # None of these objects should have been loaded before.
            self.failUnlessEqual(
                set(), objects.intersection(db_objects_loaded))
            db_objects_loaded.update(objects)
        self.failUnlessEqual(db_objects, db_objects_loaded)

    def test_gen_reload_queries_with_non_Storm_objects(self):
        # gen_reload_queries() does not like non-Storm objects.
        self.assertRaises(
            ClassInfoError, list, bulk.gen_reload_queries(['bogus']))

    def test_gen_reload_queries_with_compound_primary_keys(self):
        # gen_reload_queries() does not like compound primary keys.
        db_queries = bulk.gen_reload_queries([BugAffectsPerson()])
        self.assertRaisesWithContent(
            AssertionError,
            'Compound primary keys are not supported: BugAffectsPerson.',
            list, db_queries)

    def test_reload(self):
        # reload() loads the given objects using queries generated by
        # gen_reload_queries().
        db_object = self.factory.makeComponent()
        db_object_naked = proxy.removeSecurityProxy(db_object)
        db_object_info = get_obj_info(db_object_naked)
        IStore(db_object).flush()
        self.failUnlessEqual(None, db_object_info.get('invalidated'))
        IStore(db_object).invalidate(db_object)
        self.failUnlessEqual(True, db_object_info.get('invalidated'))
        bulk.reload([db_object])
        self.failUnlessEqual(None, db_object_info.get('invalidated'))

    def test_load(self):
        # load() loads objects of the given type by their primary keys.
        db_objects = [
            self.factory.makeComponent(),
            self.factory.makeComponent(),
            ]
        db_object_ids = [db_object.id for db_object in db_objects]
        self.assertEqual(
            set(bulk.load(Component, db_object_ids)),
            set(db_objects))

    def test_load_with_non_Storm_objects(self):
        # load() does not like non-Storm objects.
        self.assertRaises(
            ClassInfoError, bulk.load, str, [])

    def test_load_with_compound_primary_keys(self):
        # load() does not like compound primary keys.
        flags = [
            FeatureFlag(u'foo', 0, u'bar', u'true'),
            FeatureFlag(u'foo', 0, u'baz', u'false'),
            ]
        other_flag = FeatureFlag(u'notfoo', 0, u'notbar', u'true')
        for flag in flags + [other_flag]:
            getFeatureStore().add(flag)

        self.assertContentEqual(
            flags,
            bulk.load(FeatureFlag, [(ff.scope, ff.flag) for ff in flags]))

    def test_load_with_store(self):
        # load() can use an alternative store.
        db_object = self.factory.makeComponent()
        # Commit so the database object is available in both master
        # and slave stores.
        transaction.commit()
        # Master store.
        master_store = IMasterStore(db_object)
        [db_object_from_master] = bulk.load(
            Component, [db_object.id], store=master_store)
        self.assertEqual(
            Store.of(db_object_from_master), master_store)
        # Slave store.
        slave_store = ISlaveStore(db_object)
        [db_object_from_slave] = bulk.load(
            Component, [db_object.id], store=slave_store)
        self.assertEqual(
            Store.of(db_object_from_slave), slave_store)

    def test_load_related(self):
        owning_objects = [
            self.factory.makeBug(),
            self.factory.makeBug(),
            ]
        expected = set(bug.owner for bug in owning_objects)
        self.assertEqual(expected,
            set(bulk.load_related(Person, owning_objects, ['ownerID'])))

    def test_load_referencing(self):
        owned_objects = [
            self.factory.makeBranch(),
            self.factory.makeBranch(),
            ]
        expected = set(list(owned_objects[0].subscriptions) +
            list(owned_objects[1].subscriptions))
        self.assertNotEqual(0, len(expected))
        self.assertEqual(expected,
            set(bulk.load_referencing(BranchSubscription, owned_objects,
                ['branchID'])))


class TestCreate(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_references_and_enums(self):
        # create() correctly compiles plain types, enums and references.
        bug = self.factory.makeBug()
        people = [self.factory.makePerson() for i in range(5)]

        wanted = [
            (bug, person, person, datetime.datetime.now(UTC),
             BugNotificationLevel.LIFECYCLE)
            for person in people]

        with StormStatementRecorder() as recorder:
            subs = bulk.create(
                (BugSubscription.bug, BugSubscription.person,
                 BugSubscription.subscribed_by, BugSubscription.date_created,
                 BugSubscription.bug_notification_level),
                wanted, get_objects=True)

        self.assertThat(recorder, HasQueryCount(Equals(2)))
        self.assertContentEqual(
            wanted,
            ((sub.bug, sub.person, sub.subscribed_by, sub.date_created,
              sub.bug_notification_level) for sub in subs))

    def test_null_reference(self):
        # create() handles None as a Reference value.
        job = IStore(Job).add(Job())
        wanted = [(None, job, BranchJobType.RECLAIM_BRANCH_SPACE)]
        [branchjob] = bulk.create(
            (BranchJob.branch, BranchJob.job, BranchJob.job_type),
            wanted, get_objects=True)
        self.assertEqual(
            wanted, [(branchjob.branch, branchjob.job, branchjob.job_type)])

    def test_fails_on_multiple_classes(self):
        # create() only inserts into columns on a single class.
        self.assertRaises(
            ValueError,
            bulk.create, (BugSubscription.bug, BranchSubscription.branch), [])

    def test_fails_on_reference_mismatch(self):
        # create() handles Reference columns in a typesafe manner.
        self.assertRaisesWithContent(
            RuntimeError, "Property used in an unknown class",
            bulk.create, (BugSubscription.bug,),
            [[self.factory.makeBranch()]])

    def test_zero_values_is_noop(self):
        # create()ing 0 rows is a no-op.
        with StormStatementRecorder() as recorder:
            self.assertEqual(
                [],
                bulk.create((BugSubscription.bug,), [], get_objects=True))
        self.assertThat(recorder, HasQueryCount(Equals(0)))

    def test_can_return_ids(self):
        # create() can be asked to return the created IDs instead of objects.
        job = IStore(Job).add(Job())
        IStore(Job).flush()
        wanted = [(None, job, BranchJobType.RECLAIM_BRANCH_SPACE)]
        with StormStatementRecorder() as recorder:
            [created_id] = bulk.create(
                (BranchJob.branch, BranchJob.job, BranchJob.job_type),
                wanted, get_primary_keys=True)
        self.assertThat(recorder, HasQueryCount(Equals(1)))
        [reclaimjob] = ReclaimBranchSpaceJob.iterReady()
        self.assertEqual(created_id, reclaimjob.context.id)

    def test_load_can_be_skipped(self):
        # create() can be told not to load the created rows.
        job = IStore(Job).add(Job())
        IStore(Job).flush()
        wanted = [(None, job, BranchJobType.RECLAIM_BRANCH_SPACE)]
        with StormStatementRecorder() as recorder:
            self.assertIs(
                None,
                bulk.create(
                    (BranchJob.branch, BranchJob.job, BranchJob.job_type),
                    wanted, get_objects=False))
        self.assertThat(recorder, HasQueryCount(Equals(1)))
        [reclaimjob] = ReclaimBranchSpaceJob.iterReady()
        branchjob = reclaimjob.context
        self.assertEqual(
            wanted, [(branchjob.branch, branchjob.job, branchjob.job_type)])

    def test_sql_passed_through(self):
        # create() passes SQL() expressions through untouched.
        bug = self.factory.makeBug()
        person = self.factory.makePerson()

        [sub] = bulk.create(
            (BugSubscription.bug, BugSubscription.person,
             BugSubscription.subscribed_by, BugSubscription.date_created,
             BugSubscription.bug_notification_level),
            [(bug, person, person,
              SQL("CURRENT_TIMESTAMP AT TIME ZONE 'UTC'"),
              BugNotificationLevel.LIFECYCLE)], get_objects=True)
        self.assertEqual(get_transaction_timestamp(), sub.date_created)
