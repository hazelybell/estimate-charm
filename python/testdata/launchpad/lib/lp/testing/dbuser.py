# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Provides a context manager to run parts of a test as a different dbuser."""

from __future__ import absolute_import

__metaclass__ = type
__all__ = [
    'dbuser',
    'lp_dbuser',
    'switch_dbuser',
    ]

from contextlib import contextmanager

from storm.database import (
    STATE_CONNECTED,
    STATE_DISCONNECTED,
    )
from storm.zope.interfaces import IZStorm
import transaction
from zope.component import getUtility

from lp.services.config import dbconfig


def update_store_connections():
    """Update the connection settings for all active stores.

    This is required for connection setting changes to be made visible.

    Unlike disconnect_stores and reconnect_stores, this changes the
    underlying connection of *existing* stores, leaving existing objects
    functional.
    """
    for name, store in getUtility(IZStorm).iterstores():
        connection = store._connection
        if connection._state == STATE_CONNECTED:
            if connection._raw_connection is not None:
                connection._raw_connection.close()

            # This method assumes that calling transaction.abort() will
            # call rollback() on the store, but this is no longer the
            # case as of jamesh's fix for bug 230977; Stores are not
            # registered with the transaction manager until they are
            # used. While storm doesn't provide an API which does what
            # we want, we'll go under the covers and emit the
            # register-transaction event ourselves. This method is
            # only called by the test suite to kill the existing
            # connections so the Store's reconnect with updated
            # connection settings.
            store._event.emit('register-transaction')

            connection._raw_connection = None
            connection._state = STATE_DISCONNECTED
    transaction.abort()


def switch_dbuser(new_name):
    """Change the current database user.

    If new_name is None, the default will be restored.
    """
    transaction.commit()
    dbconfig.override(dbuser=new_name)
    update_store_connections()


@contextmanager
def dbuser(temporary_name):
    """A context manager that temporarily changes the dbuser.

    Use with the LaunchpadZopelessLayer layer and subclasses.

    temporary_name is the name of the dbuser that should be in place for the
    code in the "with" block.
    """
    old_name = getattr(dbconfig.overrides, 'dbuser', None)
    switch_dbuser(temporary_name)
    yield
    switch_dbuser(old_name)


def lp_dbuser():
    """A context manager that temporarily changes to the launchpad dbuser.

    Use with the LaunchpadZopelessLayer layer and subclasses.
    """
    return dbuser('launchpad')
