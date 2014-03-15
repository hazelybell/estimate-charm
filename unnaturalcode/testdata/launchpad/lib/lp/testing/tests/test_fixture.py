# Copyright 2011-12 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for lp.testing.fixture."""

__metaclass__ = type

import sys

import oops_amqp
import psycopg2
from storm.exceptions import DisconnectionError
import transaction
from zope.component import (
    adapts,
    ComponentLookupError,
    getGlobalSiteManager,
    queryAdapter,
    )
from zope.interface import (
    implements,
    Interface,
    )
from zope.sendmail.interfaces import IMailDelivery

from lp.registry.model.person import Person
from lp.services.config import (
    config,
    dbconfig,
    )
from lp.services.database.interfaces import IMasterStore
from lp.services.messaging import rabbit
from lp.services.webapp.errorlog import (
    globalErrorUtility,
    notify_publisher,
    )
from lp.testing import TestCase
from lp.testing.fixture import (
    CaptureOops,
    DisableTriggerFixture,
    PGBouncerFixture,
    ZopeAdapterFixture,
    ZopeUtilityFixture,
    )
from lp.testing.layers import (
    BaseLayer,
    DatabaseLayer,
    LaunchpadLayer,
    LaunchpadZopelessLayer,
    ZopelessDatabaseLayer,
    )


class IFoo(Interface):
    pass


class IBar(Interface):
    pass


class Foo:
    implements(IFoo)


class Bar:
    implements(IBar)


class FooToBar:

    adapts(IFoo)
    implements(IBar)

    def __init__(self, foo):
        self.foo = foo


class TestZopeAdapterFixture(TestCase):

    layer = BaseLayer

    def test_register_and_unregister(self):
        # Entering ZopeAdapterFixture's context registers the given adapter,
        # and exiting the context unregisters the adapter again.
        context = Foo()
        # No adapter from Foo to Bar is registered.
        self.assertIs(None, queryAdapter(context, IBar))
        with ZopeAdapterFixture(FooToBar):
            # Now there is an adapter from Foo to Bar.
            adapter = queryAdapter(context, IBar)
            self.assertIsNot(None, adapter)
            self.assertIsInstance(adapter, FooToBar)
        # The adapter is no longer registered.
        self.assertIs(None, queryAdapter(context, IBar))


class DummyMailer(object):

    implements(IMailDelivery)


class TestZopeUtilityFixture(TestCase):

    layer = BaseLayer

    def test_fixture(self):
        def get_mailer():
            return getGlobalSiteManager().getUtility(
                IMailDelivery, 'Mail')
        fake = DummyMailer()
        # In BaseLayer there should be no mailer by default.
        self.assertRaises(ComponentLookupError, get_mailer)
        with ZopeUtilityFixture(fake, IMailDelivery, 'Mail'):
            self.assertEquals(get_mailer(), fake)
        self.assertRaises(ComponentLookupError, get_mailer)


class TestPGBouncerFixtureWithCA(TestCase):
    """PGBouncerFixture reconnect tests for Component Architecture layers.

    Registered Storm Stores should be reconnected through pgbouncer.
    """
    layer = LaunchpadZopelessLayer

    def is_connected(self):
        # First rollback any existing transaction to ensure we attempt
        # to reconnect.
        transaction.abort()

        try:
            IMasterStore(Person).find(Person).first()
            return True
        except DisconnectionError:
            return False

    def test_stop_and_start(self):
        # Database is working.
        assert self.is_connected()

        # And database with the fixture is working too.
        pgbouncer = PGBouncerFixture()
        with PGBouncerFixture() as pgbouncer:
            assert self.is_connected()

            # pgbouncer is transparant. To confirm we are connecting via
            # pgbouncer, we need to shut it down and confirm our
            # connections are dropped.
            pgbouncer.stop()
            assert not self.is_connected()

            # If we restart it, things should be back to normal.
            pgbouncer.start()
            assert self.is_connected()

        # Database is still working.
        assert self.is_connected()

    def test_stop_no_start(self):
        # Database is working.
        assert self.is_connected()

        # And database with the fixture is working too.
        with PGBouncerFixture() as pgbouncer:
            assert self.is_connected()

            # pgbouncer is transparant. To confirm we are connecting via
            # pgbouncer, we need to shut it down and confirm our
            # connections are dropped.
            pgbouncer.stop()
            assert not self.is_connected()

        # Database is working again.
        assert self.is_connected()


class TestPGBouncerFixtureWithoutCA(TestCase):
    """PGBouncerFixture tests for non-Component Architecture layers."""
    layer = DatabaseLayer

    def is_db_available(self):
        # Direct connection to the DB.
        con_str = dbconfig.rw_main_master + ' user=launchpad_main'
        try:
            con = psycopg2.connect(con_str)
            cur = con.cursor()
            cur.execute("SELECT id FROM Person LIMIT 1")
            con.close()
            return True
        except psycopg2.OperationalError:
            return False

    def test_install_fixture(self):
        self.assert_(self.is_db_available())

        with PGBouncerFixture() as pgbouncer:
            self.assertTrue(self.is_db_available())

            pgbouncer.stop()
            self.assertFalse(self.is_db_available())

        # This confirms that we are again connecting directly to the
        # database, as the pgbouncer process was shutdown.
        self.assertTrue(self.is_db_available())

    def test_install_fixture_with_restart(self):
        self.assert_(self.is_db_available())

        with PGBouncerFixture() as pgbouncer:
            self.assertTrue(self.is_db_available())

            pgbouncer.stop()
            self.assertFalse(self.is_db_available())

            pgbouncer.start()
            self.assertTrue(self.is_db_available())

        # Note that because pgbouncer was left running, we can't confirm
        # that we are now connecting directly to the database.
        self.assertTrue(self.is_db_available())


class TestCaptureOopsNoRabbit(TestCase):

    # Need CA for subscription.
    layer = BaseLayer

    def test_subscribes_to_events(self):
        capture = self.useFixture(CaptureOops())
        publishers = globalErrorUtility._oops_config.publishers[:]
        try:
            globalErrorUtility._oops_config.publishers[:] = [notify_publisher]
            id = globalErrorUtility.raising(sys.exc_info())['id']
            self.assertEqual(id, capture.oopses[0]['id'])
            self.assertEqual(1, len(capture.oopses))
        finally:
            globalErrorUtility._oops_config.publishers[:] = publishers


class TestCaptureOopsRabbit(TestCase):

    # Has rabbit + CA.
    layer = LaunchpadLayer

    def test_no_oopses_no_hang_on_sync(self):
        capture = self.useFixture(CaptureOops())
        capture.sync()

    def test_sync_grabs_pending_oopses(self):
        factory = rabbit.connect
        exchange = config.error_reports.error_exchange
        routing_key = config.error_reports.error_queue_key
        capture = self.useFixture(CaptureOops())
        amqp_publisher = oops_amqp.Publisher(
            factory, exchange, routing_key, inherit_id=True)
        oops = {'id': 'fnor', 'foo': 'dr'}
        self.assertEqual('fnor', amqp_publisher(oops))
        oops2 = {'id': 'quux', 'foo': 'strangelove'}
        self.assertEqual('quux', amqp_publisher(oops2))
        capture.sync()
        self.assertEqual([oops, oops2], capture.oopses)

    def test_sync_twice_works(self):
        capture = self.useFixture(CaptureOops())
        capture.sync()
        capture.sync()


class TestDisableTriggerFixture(TestCase):
    """Test the DisableTriggerFixture class."""

    layer = ZopelessDatabaseLayer

    def setUp(self):
        super(TestDisableTriggerFixture, self).setUp()
        con_str = dbconfig.rw_main_master + ' user=launchpad_main'
        con = psycopg2.connect(con_str)
        con.set_isolation_level(0)
        self.cursor = con.cursor()
        # Create a test table and trigger.
        setup_sql = """
        CREATE OR REPLACE FUNCTION trig() RETURNS trigger
        LANGUAGE plpgsql
        AS
        'BEGIN
            update test_trigger set col_b = NEW.col_a
            where col_a = NEW.col_a;
            RETURN NULL;
        END;';
        DROP TABLE IF EXISTS test_trigger CASCADE;
        CREATE TABLE test_trigger(col_a integer, col_b integer);
        CREATE TRIGGER test_trigger_t
            AFTER INSERT on test_trigger
            FOR EACH ROW EXECUTE PROCEDURE trig();
        """
        self.cursor.execute(setup_sql)
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        self.cursor.execute('DROP TABLE test_trigger CASCADE;')
        self.cursor.close()
        self.cursor.connection.close()

    def test_triggers_are_disabled(self):
        # Test that the fixture correctly disables specified triggers.
        with DisableTriggerFixture({'test_trigger': 'test_trigger_t'}):
            self.cursor.execute(
                'INSERT INTO test_trigger(col_a) values (1)')
            self.cursor.execute(
                'SELECT col_b FROM test_trigger WHERE col_a = 1')
            [col_b] = self.cursor.fetchone()
            self.assertEqual(None, col_b)

    def test_triggers_are_enabled_after(self):
        # Test that the fixture correctly enables the triggers again when it
        # is done.
        with DisableTriggerFixture({'test_trigger': 'test_trigger_t'}):
            self.cursor.execute(
                'INSERT INTO test_trigger(col_a) values (1)')
        self.cursor.execute(
            'INSERT INTO test_trigger(col_a) values (2)')
        self.cursor.execute(
            'SELECT col_b FROM test_trigger WHERE col_a = 2')
        [col_b] = self.cursor.fetchone()
        self.assertEqual(2, col_b)
