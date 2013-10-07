# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Various helper functions for using the librarian in testing.."""

__metaclass__ = type
__all__ = [
    'get_newest_librarian_file',
]

from storm.expr import Desc
from zope.component import getUtility

from lp.services.database.interfaces import IStore
from lp.services.librarian.interfaces.client import ILibrarianClient
from lp.services.librarian.model import LibraryFileAlias


def get_newest_librarian_file():
    """Return the file that was last stored in the librarian.

    Note that a transaction.commit() call is needed before a new file is
    readable from the librarian.

    :return: A file-like object of the file content.
    """
    alias = IStore(LibraryFileAlias).find(LibraryFileAlias).order_by(
        Desc(LibraryFileAlias.date_created)).first()
    return getUtility(ILibrarianClient).getFileByAlias(alias.id)
