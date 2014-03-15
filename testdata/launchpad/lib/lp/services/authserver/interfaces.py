# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interface for the XML-RPC authentication server."""

__metaclass__ = type
__all__ = [
    'IAuthServer',
    'IAuthServerApplication',
    ]


from zope.interface import Interface

from lp.services.webapp.interfaces import ILaunchpadApplication


class IAuthServer(Interface):
    """A storage for details about users."""

    def getUserAndSSHKeys(name):
        """Get details about a person, including their SSH keys.

        :param name: The username to look up.
        :returns: A dictionary {id: person-id, username: person-name, keys:
            [(key-type, key-text)]}, or NoSuchPersonWithName if there is no
            person with the given name.
        """


class IAuthServerApplication(ILaunchpadApplication):
    """Launchpad legacy AuthServer application root."""

