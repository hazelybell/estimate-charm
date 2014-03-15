# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""An API for messaging systems in Launchpad, e.g. RabbitMQ."""

__metaclass__ = type
__all__ = [
    "connect",
    "is_configured",
    "session",
    "unreliable_session",
    ]

from collections import deque
from functools import partial
import json
import socket
import sys
import threading
import time

from amqplib import client_0_8 as amqp
import transaction
from transaction._transaction import Status as TransactionStatus
from zope.interface import implements

from lp.services.config import config
from lp.services.messaging.interfaces import (
    IMessageConsumer,
    IMessageProducer,
    IMessageSession,
    MessagingUnavailable,
    QueueEmpty,
    QueueNotFound,
    )


LAUNCHPAD_EXCHANGE = "launchpad-exchange"


class RabbitSessionTransactionSync:

    implements(transaction.interfaces.ISynchronizer)

    def __init__(self, session):
        self.session = session

    def newTransaction(self, txn):
        pass

    def beforeCompletion(self, txn):
        pass

    def afterCompletion(self, txn):
        if txn.status == TransactionStatus.COMMITTED:
            self.session.finish()
        else:
            self.session.reset()


def is_configured():
    """Return True if rabbit looks to be configured."""
    return not (
        config.rabbitmq.host is None or
        config.rabbitmq.userid is None or
        config.rabbitmq.password is None or
        config.rabbitmq.virtual_host is None)


def connect():
    """Connect to AMQP if possible.

    :raises MessagingUnavailable: If the configuration is incomplete.
    """
    if not is_configured():
        raise MessagingUnavailable("Incomplete configuration")
    return amqp.Connection(
        host=config.rabbitmq.host, userid=config.rabbitmq.userid,
        password=config.rabbitmq.password,
        virtual_host=config.rabbitmq.virtual_host, insist=False)


class RabbitSession(threading.local):

    implements(IMessageSession)

    exchange = LAUNCHPAD_EXCHANGE

    def __init__(self):
        super(RabbitSession, self).__init__()
        self._connection = None
        self._deferred = deque()
        # Maintain sessions according to transaction boundaries. Keep a strong
        # reference to the sync because the transaction manager does not. We
        # need one per thread (definining it here is enough to ensure that).
        self._sync = RabbitSessionTransactionSync(self)
        transaction.manager.registerSynch(self._sync)

    @property
    def is_connected(self):
        """See `IMessageSession`."""
        return (
            self._connection is not None and
            self._connection.transport is not None)

    def connect(self):
        """See `IMessageSession`.

        Open a connection for this thread if necessary. Connections cannot be
        shared between threads.
        """
        if self._connection is None or self._connection.transport is None:
            self._connection = connect()
        return self._connection

    def disconnect(self):
        """See `IMessageSession`."""
        if self._connection is not None:
            try:
                self._connection.close()
            except socket.error:
                # Socket error is fine; the connection is still closed.
                pass
            finally:
                self._connection = None

    def flush(self):
        """See `IMessageSession`."""
        tasks = self._deferred
        while len(tasks) != 0:
            tasks.popleft()()

    def finish(self):
        """See `IMessageSession`."""
        try:
            self.flush()
        finally:
            self.reset()

    def reset(self):
        """See `IMessageSession`."""
        self._deferred.clear()
        self.disconnect()

    def defer(self, func, *args, **kwargs):
        """See `IMessageSession`."""
        self._deferred.append(partial(func, *args, **kwargs))

    def getProducer(self, name):
        """See `IMessageSession`."""
        return RabbitRoutingKey(self, name)

    def getConsumer(self, name):
        """See `IMessageSession`."""
        return RabbitQueue(self, name)


# Per-thread sessions.
session = RabbitSession()
session_finish_handler = (
    lambda event: session.finish())


class RabbitUnreliableSession(RabbitSession):
    """An "unreliable" `RabbitSession`.

    Unreliable in this case means that certain errors in deferred tasks are
    silently suppressed. This means that services can continue to function
    even in the absence of a running and fully functional message queue.

    Other types of errors are also caught because we don't want this
    subsystem to destabilise other parts of Launchpad but we nonetheless
    record OOPses for these.

    XXX: We only suppress MessagingUnavailable for now because we want to
    monitor this closely before we add more exceptions to the
    suppressed_errors list. Potential candidates are `MessagingException`,
    `IOError` or `amqp.AMQPException`.
    """

    suppressed_errors = (
        MessagingUnavailable,
        )

    def finish(self):
        """See `IMessageSession`.

        Suppresses errors listed in `suppressed_errors`. Also suppresses
        other errors but files an oops report for these.
        """
        try:
            super(RabbitUnreliableSession, self).finish()
        except self.suppressed_errors:
            pass
        except Exception:
            from lp.services.webapp import errorlog
            errorlog.globalErrorUtility.raising(sys.exc_info())


# Per-thread "unreliable" sessions.
unreliable_session = RabbitUnreliableSession()
unreliable_session_finish_handler = (
    lambda event: unreliable_session.finish())


class RabbitMessageBase:
    """Base class for all RabbitMQ messaging."""

    def __init__(self, session):
        self.session = IMessageSession(session)
        self._channel = None

    @property
    def channel(self):
        if self._channel is None or not self._channel.is_open:
            connection = self.session.connect()
            self._channel = connection.channel()
            self._channel.exchange_declare(
                self.session.exchange, "direct", durable=False,
                auto_delete=False, nowait=False)
        return self._channel


class RabbitRoutingKey(RabbitMessageBase):
    """A RabbitMQ data origination point."""

    implements(IMessageProducer)

    def __init__(self, session, routing_key):
        super(RabbitRoutingKey, self).__init__(session)
        self.key = routing_key

    def associateConsumer(self, consumer):
        """Only receive messages for requested routing key."""
        self.session.defer(self.associateConsumerNow, consumer)

    def associateConsumerNow(self, consumer):
        """Only receive messages for requested routing key."""
        # The queue will be auto-deleted 5 minutes after its last use.
        # http://www.rabbitmq.com/extensions.html#queue-leases
        self.channel.queue_declare(
            consumer.name, nowait=False, auto_delete=False,
            arguments={"x-expires": 300000})  # 5 minutes.
        self.channel.queue_bind(
            queue=consumer.name, exchange=self.session.exchange,
            routing_key=self.key, nowait=False)

    def send(self, data):
        """See `IMessageProducer`."""
        self.session.defer(self.sendNow, data)

    def sendNow(self, data):
        """Immediately send a message to the broker."""
        json_data = json.dumps(data)
        msg = amqp.Message(json_data)
        self.channel.basic_publish(
            exchange=self.session.exchange,
            routing_key=self.key, msg=msg)


class RabbitQueue(RabbitMessageBase):
    """A RabbitMQ Queue."""

    implements(IMessageConsumer)

    def __init__(self, session, name):
        super(RabbitQueue, self).__init__(session)
        self.name = name

    def receive(self, timeout=0.0):
        """Pull a message from the queue.

        :param timeout: Wait a maximum of `timeout` seconds before giving up,
            trying at least once.
        :raises QueueEmpty: if the timeout passes.
        """
        endtime = time.time() + timeout
        while True:
            try:
                message = self.channel.basic_get(self.name)
                if message is None:
                    if time.time() > endtime:
                        raise QueueEmpty()
                    time.sleep(0.1)
                else:
                    self.channel.basic_ack(message.delivery_tag)
                    return json.loads(message.body)
            except amqp.AMQPChannelException as error:
                if error.amqp_reply_code == 404:
                    raise QueueNotFound()
                else:
                    raise
