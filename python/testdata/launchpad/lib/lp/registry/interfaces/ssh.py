# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""SSH key interfaces."""

__metaclass__ = type

__all__ = [
    'ISSHKey',
    'ISSHKeySet',
    'SSHKeyAdditionError',
    'SSHKeyCompromisedError',
    'SSHKeyType',
    ]

from lazr.enum import (
    DBEnumeratedType,
    DBItem,
    )
from lazr.restful.declarations import (
    export_as_webservice_entry,
    exported,
    )
from zope.interface import Interface
from zope.schema import (
    Choice,
    Int,
    TextLine,
    )

from lp import _


class SSHKeyType(DBEnumeratedType):
    """SSH key type

    SSH (version 2) can use RSA or DSA keys for authentication. See
    OpenSSH's ssh-keygen(1) man page for details.
    """

    RSA = DBItem(1, """
        RSA

        RSA
        """)

    DSA = DBItem(2, """
        DSA

        DSA
        """)


class ISSHKey(Interface):
    """SSH public key"""

    export_as_webservice_entry('ssh_key')

    id = Int(title=_("Database ID"), required=True, readonly=True)
    person = Int(title=_("Owner"), required=True, readonly=True)
    personID = Int(title=_('Owner ID'), required=True, readonly=True)
    keytype = exported(Choice(title=_("Key type"), required=True,
                     vocabulary=SSHKeyType, readonly=True))
    keytext = exported(TextLine(title=_("Key text"), required=True,
                       readonly=True))
    comment = exported(TextLine(title=_("Comment describing this key"),
                       required=True, readonly=True))

    def destroySelf():
        """Remove this SSHKey from the database."""


class ISSHKeySet(Interface):
    """The set of SSHKeys."""

    def new(person, sshkey):
        """Create a new SSHKey pointing to the given Person."""

    def getByID(id, default=None):
        """Return the SSHKey object for the given id.

        Return the given default if there's now object with the given id.
        """

    def getByPeople(people):
        """Return SSHKey object associated to the people provided."""


class SSHKeyAdditionError(Exception):
    """Raised when the SSH public key is invalid."""


class SSHKeyCompromisedError(Exception):
    """Raised when the SSH public key is known to be easily compromisable."""

