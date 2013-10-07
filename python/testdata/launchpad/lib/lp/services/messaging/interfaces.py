# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Messaging interfaces."""

__metaclass__ = type
__all__ = [
    'IMessageConsumer',
    'IMessageProducer',
    'IMessageSession',
    'MessagingException',
    'MessagingUnavailable',
    'QueueEmpty',
    'QueueNotFound',
    ]


from zope.interface import Interface
from zope.schema import Bool


class MessagingException(Exception):
    """Failure in messaging."""


class MessagingUnavailable(MessagingException):
    """Messaging systems are not available."""


class QueueNotFound(MessagingException):
    """Raised if the queue was not found."""


class QueueEmpty(MessagingException):
    """Raised if there are no queued messages on a non-blocking read."""


class IMessageSession(Interface):

    is_connected = Bool(
        u"Whether the session is connected to the messaging system.")

    def connect():
        """Connect to the messaging system.

        If the session is already connected this should be a no-op.
        """

    def disconnect():
        """Disconnect from the messaging system.

        If the session is already disconnected this should be a no-op.
        """

    def flush():
        """Run deferred tasks."""

    def finish():
        """Flush the session and reset."""

    def reset():
        """Reset the session."""

    def defer(func, *args, **kwargs):
        """Schedule something to happen when this session is finished."""

    def getProducer(name):
        """Get a `IMessageProducer` associated with this session."""

    def getConsumer(name):
        """Get a `IMessageConsumer` associated with this session."""


class IMessageConsumer(Interface):

    def receive(blocking=True):
        """Receive data from the queue.

        :raises EmptyQueue: If non-blocking and the queue is empty.
        """


class IMessageProducer(Interface):

    def send(data):
        """Serialize `data` into JSON and send it to the queue on commit."""

    def sendNow(data):
        """Serialize `data` into JSON and send it to the queue immediately."""

    def associateConsumer(consumer):
        """Make the consumer receive messages from this producer on commit.

        :param consumer: An `IMessageConsumer`
        """

    def associateConsumerNow(consumer):
        """Make the consumer receive messages from this producer.

        :param consumer: An `IMessageConsumer`
        """
