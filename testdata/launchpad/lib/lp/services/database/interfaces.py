# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'DEFAULT_FLAVOR',
    'DisallowedStore',
    'IDatabasePolicy',
    'IDBObject',
    'IMasterObject',
    'IMasterStore',
    'IRequestExpired',
    'ISlaveStore',
    'ISQLBase',
    'IStore',
    'IStoreSelector',
    'MAIN_STORE',
    'MASTER_FLAVOR',
    'SLAVE_FLAVOR',
    ]


from zope.interface import Interface
from zope.interface.common.interfaces import IRuntimeError
from zope.schema import Int


class IRequestExpired(IRuntimeError):
    """A RequestExpired exception is raised if the current request has
    timed out.
    """

# XXX 2007-02-09 jamesh:
# This derrived from sqlos.interfaces.ISQLObject before hand.  I don't
# think it is ever used though ...
class ISQLBase(Interface):
    """An extension of ISQLObject that provides an ID."""
    id = Int(title=u"The integer ID for the instance")


#
# Database policies
#

MAIN_STORE = 'main'  # The main database.
ALL_STORES = frozenset([MAIN_STORE])

DEFAULT_FLAVOR = 'default'  # Default flavor for current state.
MASTER_FLAVOR = 'master'  # The master database.
SLAVE_FLAVOR = 'slave'  # A slave database.


class IDatabasePolicy(Interface):
    """Implement database policy based on the request.

    The publisher adapts the request to `IDatabasePolicy` to
    instantiate the policy for the current request.
    """
    def __enter__():
        """Standard Python context manager interface.

        The IDatabasePolicy will install itself using the IStoreSelector
        utility.
        """

    def __exit__(exc_type, exc_value, traceback):
        """Standard Python context manager interface.

        The IDatabasePolicy will uninstall itself using the IStoreSelector
        utility.
        """

    def getStore(name, flavor):
        """Retrieve a Store.

        :param name: one of ALL_STORES.

        :param flavor: MASTER_FLAVOR, SLAVE_FLAVOR, or DEFAULT_FLAVOR.
        """

    def install():
        """Hook called when policy is pushed onto the `IStoreSelector`."""

    def uninstall():
        """Hook called when policy is popped from the `IStoreSelector`."""


class MasterUnavailable(Exception):
    """A master (writable replica) database was requested but not available.
    """


class DisallowedStore(Exception):
    """A request was made to access a Store that has been disabled
    by the current policy.
    """


class IStoreSelector(Interface):
    """Get a Storm store with a desired flavor.

    Stores come in two flavors - MASTER_FLAVOR and SLAVE_FLAVOR.

    The master is writable and up to date, but we should not use it
    whenever possible because there is only one master and we don't want
    it to be overloaded.

    The slave is read only replica of the master and may lag behind the
    master. For many purposes such as serving unauthenticated web requests
    and generating reports this is fine. We can also have as many slave
    databases as we are prepared to pay for, so they will perform better
    because they are less loaded.
    """
    def push(dbpolicy):
        """Install an `IDatabasePolicy` as the default for this thread."""

    def pop():
        """Uninstall the most recently pushed `IDatabasePolicy` from
        this thread.

        Returns the `IDatabasePolicy` removed.
        """

    def get_current():
        """Return the currently installed `IDatabasePolicy`."""

    def get(name, flavor):
        """Retrieve a Storm Store.

        Results should not be shared between threads, as which store is
        returned for a given name or flavor can depend on thread state
        (eg. the HTTP request currently being handled).

        If a SLAVE_FLAVOR is requested, the MASTER_FLAVOR may be returned
        anyway.

        The DEFAULT_FLAVOR flavor may return either a master or slave
        depending on process state. Application code using the
        DEFAULT_FLAVOR flavor should assume they have a MASTER and that
        a higher level will catch the exception raised if an attempt is
        made to write changes to a read only store. DEFAULT_FLAVOR exists
        for backwards compatibility, and new code should explicitly state
        if they want a master or a slave.

        :raises MasterUnavailable:

        :raises DisallowedStore:
        """


class IStore(Interface):
    """A storm.store.Store."""
    def get(cls, key):
        """See storm.store.Store."""


class IMasterStore(IStore):
    """A writeable Storm Stores."""


class ISlaveStore(IStore):
    """A read-only Storm Store."""


class IDBObject(Interface):
    """A Storm database object."""


class IMasterObject(IDBObject):
    """A Storm database object associated with its master Store."""
