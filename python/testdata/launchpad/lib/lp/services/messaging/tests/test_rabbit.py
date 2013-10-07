# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Messaging utility tests."""

__metaclass__ = type

from functools import partial
from itertools import count
import socket

from testtools.testcase import ExpectedException
import transaction
from transaction._transaction import Status as TransactionStatus
from zope.component import getUtility
from zope.event import notify

from lp.services.messaging.interfaces import (
    IMessageConsumer,
    IMessageProducer,
    IMessageSession,
    MessagingUnavailable,
    QueueEmpty,
    QueueNotFound,
    )
from lp.services.messaging.rabbit import (
    RabbitMessageBase,
    RabbitQueue,
    RabbitRoutingKey,
    RabbitSession,
    RabbitSessionTransactionSync,
    RabbitUnreliableSession,
    session as global_session,
    unreliable_session as global_unreliable_session,
    )
from lp.services.webapp.interfaces import FinishReadOnlyRequestEvent
from lp.testing import (
    monkey_patch,
    TestCase,
    )
from lp.testing.fakemethod import FakeMethod
from lp.testing.faketransaction import FakeTransaction
from lp.testing.layers import (
    LaunchpadFunctionalLayer,
    RabbitMQLayer,
    )
from lp.testing.matchers import Provides

# RabbitMQ is not (yet) torn down or reset between tests, so here are sources
# of distinct names.
queue_names = ("queue.%d" % num for num in count(1))
key_names = ("key.%d" % num for num in count(1))


class FakeRabbitSession:

    def __init__(self):
        self.log = []

    def finish(self):
        self.log.append("finish")

    def reset(self):
        self.log.append("reset")


class TestRabbitSessionTransactionSync(TestCase):

    def test_interface(self):
        self.assertThat(
            RabbitSessionTransactionSync(None),
            Provides(transaction.interfaces.ISynchronizer))

    def test_afterCompletion_COMMITTED(self):
        txn = FakeTransaction()
        txn.status = TransactionStatus.COMMITTED
        fake_session = FakeRabbitSession()
        sync = RabbitSessionTransactionSync(fake_session)
        sync.afterCompletion(txn)
        self.assertEqual(["finish"], fake_session.log)

    def test_afterCompletion_ACTIVE(self):
        txn = FakeTransaction()
        txn.status = TransactionStatus.ACTIVE
        fake_session = FakeRabbitSession()
        sync = RabbitSessionTransactionSync(fake_session)
        sync.afterCompletion(txn)
        self.assertEqual(["reset"], fake_session.log)


class RabbitTestCase(TestCase):

    layer = RabbitMQLayer

    def tearDown(self):
        super(RabbitTestCase, self).tearDown()
        global_session.reset()
        global_unreliable_session.reset()


class TestRabbitSession(RabbitTestCase):

    session_factory = RabbitSession

    def test_interface(self):
        session = self.session_factory()
        self.assertThat(session, Provides(IMessageSession))

    def test_connect(self):
        session = self.session_factory()
        self.assertFalse(session.is_connected)
        connection = session.connect()
        self.assertTrue(session.is_connected)
        self.assertIs(connection, session._connection)

    def test_connect_with_incomplete_configuration(self):
        self.pushConfig("rabbitmq", host="none")
        session = self.session_factory()
        with ExpectedException(
            MessagingUnavailable, "Incomplete configuration"):
            session.connect()

    def test_disconnect(self):
        session = self.session_factory()
        session.connect()
        session.disconnect()
        self.assertFalse(session.is_connected)

    def test_disconnect_with_error(self):
        session = self.session_factory()
        session.connect()
        old_close = session._connection.close
        def new_close(*args, **kwargs):
            old_close(*args, **kwargs)
            raise socket.error
        with monkey_patch(session._connection, close=new_close):
            session.disconnect()
            self.assertFalse(session.is_connected)

    def test_is_connected(self):
        # is_connected is False once a connection has been closed.
        session = self.session_factory()
        session.connect()
        # Close the connection without using disconnect().
        session._connection.close()
        self.assertFalse(session.is_connected)

    def test_defer(self):
        task = lambda foo, bar: None
        session = self.session_factory()
        session.defer(task, "foo", bar="baz")
        self.assertEqual(1, len(session._deferred))
        [deferred_task] = session._deferred
        self.assertIsInstance(deferred_task, partial)
        self.assertIs(task, deferred_task.func)
        self.assertEqual(("foo",), deferred_task.args)
        self.assertEqual({"bar": "baz"}, deferred_task.keywords)

    def test_flush(self):
        # RabbitSession.flush() runs deferred tasks.
        log = []
        task = lambda: log.append("task")
        session = self.session_factory()
        session.defer(task)
        session.connect()
        session.flush()
        self.assertEqual(["task"], log)
        self.assertEqual([], list(session._deferred))
        self.assertTrue(session.is_connected)

    def test_reset(self):
        # RabbitSession.reset() resets session variables and does not run
        # deferred tasks.
        log = []
        task = lambda: log.append("task")
        session = self.session_factory()
        session.defer(task)
        session.connect()
        session.reset()
        self.assertEqual([], log)
        self.assertEqual([], list(session._deferred))
        self.assertFalse(session.is_connected)

    def test_finish(self):
        # RabbitSession.finish() resets session variables after running
        # deferred tasks.
        log = []
        task = lambda: log.append("task")
        session = self.session_factory()
        session.defer(task)
        session.connect()
        session.finish()
        self.assertEqual(["task"], log)
        self.assertEqual([], list(session._deferred))
        self.assertFalse(session.is_connected)

    def test_getProducer(self):
        session = self.session_factory()
        producer = session.getProducer("foo")
        self.assertIsInstance(producer, RabbitRoutingKey)
        self.assertIs(session, producer.session)
        self.assertEqual("foo", producer.key)

    def test_getConsumer(self):
        session = self.session_factory()
        consumer = session.getConsumer("foo")
        self.assertIsInstance(consumer, RabbitQueue)
        self.assertIs(session, consumer.session)
        self.assertEqual("foo", consumer.name)


class TestRabbitUnreliableSession(TestRabbitSession):

    session_factory = RabbitUnreliableSession
    layer = RabbitMQLayer

    def setUp(self):
        super(TestRabbitUnreliableSession, self).setUp()
        self.prev_oops = self.getOops()

    def getOops(self):
        try:
            self.oops_capture.sync()
            return self.oopses[-1]
        except IndexError:
            return None

    def assertNoOops(self):
        oops_report = self.getOops()
        self.assertEqual(repr(self.prev_oops), repr(oops_report))

    def assertOops(self, text_in_oops):
        oops_report = self.getOops()
        self.assertNotEqual(
            repr(self.prev_oops), repr(oops_report), 'No OOPS reported!')
        self.assertIn(text_in_oops, str(oops_report))

    def _test_finish_suppresses_exception(self, exception):
        # Simple helper to test that the given exception is suppressed
        # when raised by finish().
        session = self.session_factory()
        session.defer(FakeMethod(failure=exception))
        session.finish()  # Look, no exceptions!

    def test_finish_suppresses_MessagingUnavailable(self):
        self._test_finish_suppresses_exception(
            MessagingUnavailable('Messaging borked.'))
        self.assertNoOops()

    def test_finish_suppresses_other_errors_with_oopses(self):
        exception = Exception("That hent worked.")
        self._test_finish_suppresses_exception(exception)
        self.assertOops(str(exception))


class TestRabbitMessageBase(RabbitTestCase):

    def test_session(self):
        base = RabbitMessageBase(global_session)
        self.assertIs(global_session, base.session)

    def test_channel(self):
        # Referencing the channel property causes the session to connect.
        base = RabbitMessageBase(global_session)
        self.assertFalse(base.session.is_connected)
        channel = base.channel
        self.assertTrue(base.session.is_connected)
        self.assertIsNot(None, channel)
        # The same channel is returned every time.
        self.assertIs(channel, base.channel)

    def test_channel_session_closed(self):
        # When the session is disconnected the channel is thrown away too.
        base = RabbitMessageBase(global_session)
        channel1 = base.channel
        base.session.disconnect()
        channel2 = base.channel
        self.assertNotEqual(channel1, channel2)


class TestRabbitRoutingKey(RabbitTestCase):

    def test_interface(self):
        routing_key = RabbitRoutingKey(global_session, next(key_names))
        self.assertThat(routing_key, Provides(IMessageProducer))

    def test_associateConsumer(self):
        # associateConsumer() only associates the consumer at transaction
        # commit time. However, order is preserved.
        consumer = RabbitQueue(global_session, next(queue_names))
        routing_key = RabbitRoutingKey(global_session, next(key_names))
        routing_key.associateConsumer(consumer)
        # The session is still not connected.
        self.assertFalse(global_session.is_connected)
        routing_key.sendNow('now')
        routing_key.send('later')
        # The queue is not found because the consumer has not yet been
        # associated with the routing key and the queue declared.
        self.assertRaises(QueueNotFound, consumer.receive, timeout=2)
        transaction.commit()
        # Now that the transaction has been committed, the consumer is
        # associated, and receives the deferred message.
        self.assertEqual('later', consumer.receive(timeout=2))

    def test_associateConsumerNow(self):
        # associateConsumerNow() associates the consumer right away.
        consumer = RabbitQueue(global_session, next(queue_names))
        routing_key = RabbitRoutingKey(global_session, next(key_names))
        routing_key.associateConsumerNow(consumer)
        routing_key.sendNow('now')
        routing_key.send('later')
        # There is already something in the queue.
        self.assertEqual('now', consumer.receive(timeout=2))
        transaction.commit()
        # Now that the transaction has been committed there is another item in
        # the queue.
        self.assertEqual('later', consumer.receive(timeout=2))

    def test_send(self):
        consumer = RabbitQueue(global_session, next(queue_names))
        routing_key = RabbitRoutingKey(global_session, next(key_names))
        routing_key.associateConsumerNow(consumer)

        for data in range(90, 100):
            routing_key.send(data)

        routing_key.sendNow('sync')
        # There is nothing in the queue except the sync we just sent.
        self.assertEqual('sync', consumer.receive(timeout=2))

        # Messages get sent on commit
        transaction.commit()
        for data in range(90, 100):
            self.assertEqual(data, consumer.receive())

        # There are no more messages. They have all been consumed.
        routing_key.sendNow('sync')
        self.assertEqual('sync', consumer.receive(timeout=2))

    def test_sendNow(self):
        consumer = RabbitQueue(global_session, next(queue_names))
        routing_key = RabbitRoutingKey(global_session, next(key_names))
        routing_key.associateConsumerNow(consumer)

        for data in range(50, 60):
            routing_key.sendNow(data)
            received_data = consumer.receive(timeout=2)
            self.assertEqual(data, received_data)

    def test_does_not_connect_session_immediately(self):
        # RabbitRoutingKey does not connect the session until necessary.
        RabbitRoutingKey(global_session, next(key_names))
        self.assertFalse(global_session.is_connected)


class TestRabbitQueue(RabbitTestCase):

    def test_interface(self):
        consumer = RabbitQueue(global_session, next(queue_names))
        self.assertThat(consumer, Provides(IMessageConsumer))

    def test_receive(self):
        consumer = RabbitQueue(global_session, next(queue_names))
        routing_key = RabbitRoutingKey(global_session, next(key_names))
        routing_key.associateConsumerNow(consumer)

        for data in range(55, 65):
            routing_key.sendNow(data)
            self.assertEqual(data, consumer.receive(timeout=2))

        # All the messages received were consumed.
        self.assertRaises(QueueEmpty, consumer.receive, timeout=2)

        # New connections to the queue see an empty queue too.
        consumer.session.disconnect()
        consumer = RabbitQueue(global_session, next(queue_names))
        routing_key = RabbitRoutingKey(global_session, next(key_names))
        routing_key.associateConsumerNow(consumer)
        self.assertRaises(QueueEmpty, consumer.receive, timeout=2)

    def test_does_not_connect_session_immediately(self):
        # RabbitQueue does not connect the session until necessary.
        RabbitQueue(global_session, next(queue_names))
        self.assertFalse(global_session.is_connected)


class TestRabbit(RabbitTestCase):
    """Integration-like tests for the RabbitMQ messaging abstractions."""

    def get_synced_sessions(self):
        try:
            syncs_set = transaction.manager._synchs
        except KeyError:
            return set()
        else:
            return set(
                sync.session for sync in syncs_set.data.itervalues()
                if isinstance(sync, RabbitSessionTransactionSync))

    def test_global_session(self):
        self.assertIsInstance(global_session, RabbitSession)
        self.assertIn(global_session, self.get_synced_sessions())

    def test_global_unreliable_session(self):
        self.assertIsInstance(
            global_unreliable_session, RabbitUnreliableSession)
        self.assertIn(global_unreliable_session, self.get_synced_sessions())

    def test_abort(self):
        consumer = RabbitQueue(global_session, next(queue_names))
        routing_key = RabbitRoutingKey(global_session, next(key_names))
        routing_key.associateConsumerNow(consumer)

        for data in range(90, 100):
            routing_key.send(data)

        # Messages sent using send() are forgotten on abort.
        transaction.abort()
        self.assertRaises(QueueEmpty, consumer.receive, timeout=2)


class TestRabbitWithLaunchpad(RabbitTestCase):
    """Integration-like tests for the RabbitMQ messaging abstractions."""

    layer = LaunchpadFunctionalLayer

    def test_utility(self):
        # The unreliable session is registered as the default IMessageSession
        # utility.
        self.assertIs(
            global_unreliable_session,
            getUtility(IMessageSession))

    def _test_session_finish_read_only_request(self, session):
        # When a read-only request ends the session is also finished.
        log = []
        task = lambda: log.append("task")
        session.defer(task)
        session.connect()
        notify(FinishReadOnlyRequestEvent(None, None))
        self.assertEqual(["task"], log)
        self.assertEqual([], list(session._deferred))
        self.assertFalse(session.is_connected)

    def test_global_session_finish_read_only_request(self):
        # When a read-only request ends the global_session is finished too.
        self._test_session_finish_read_only_request(global_session)

    def test_global_unreliable_session_finish_read_only_request(self):
        # When a read-only request ends the global_unreliable_session is
        # finished too.
        self._test_session_finish_read_only_request(global_unreliable_session)
