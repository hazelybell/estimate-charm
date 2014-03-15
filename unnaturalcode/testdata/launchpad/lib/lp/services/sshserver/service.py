# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Twisted `service.Service` class for the Launchpad SSH server.

An `SSHService` object can be used to launch the SSH server.
"""

__metaclass__ = type
__all__ = [
    'SSHService',
    ]


import logging
import os

from twisted.application import (
    service,
    strports,
    )
from twisted.conch.ssh.factory import SSHFactory
from twisted.conch.ssh.keys import Key
from twisted.conch.ssh.transport import SSHServerTransport
from twisted.internet import defer
from zope.event import notify

from lp.services.sshserver import (
    accesslog,
    events,
    )
from lp.services.sshserver.auth import SSHUserAuthServer
from lp.services.twistedsupport import gatherResults


class KeepAliveSettingSSHServerTransport(SSHServerTransport):

    def connectionMade(self):
        SSHServerTransport.connectionMade(self)
        self.transport.setTcpKeepAlive(True)


class Factory(SSHFactory):
    """SSH factory that uses Launchpad's custom authentication.

    This class tells the SSH service to use our custom authentication service
    and configures the host keys for the SSH server. It also logs connection
    to and disconnection from the SSH server.
    """

    protocol = KeepAliveSettingSSHServerTransport

    def __init__(self, portal, private_key, public_key, banner=None):
        """Construct an SSH factory.

        :param portal: The portal used to turn credentials into users.
        :param private_key: The private key of the server, must be an RSA
            key, given as a `twisted.conch.ssh.keys.Key` object.
        :param public_key: The public key of the server, must be an RSA
            key, given as a `twisted.conch.ssh.keys.Key` object.
        :param banner: The text to display when users successfully log in.
        """
        # Although 'portal' isn't part of the defined interface for
        # `SSHFactory`, defining it here is how the `SSHUserAuthServer` gets
        # at it. (Look for the beautiful line "self.portal =
        # self.transport.factory.portal").
        self.portal = portal
        self.services['ssh-userauth'] = self._makeAuthServer
        self._private_key = private_key
        self._public_key = public_key
        self._banner = banner

    def _makeAuthServer(self, *args, **kwargs):
        kwargs['banner'] = self._banner
        return SSHUserAuthServer(*args, **kwargs)

    def buildProtocol(self, address):
        """Build an SSH protocol instance, logging the event.

        The protocol object we return is slightly modified so that we can hook
        into the 'connectionLost' event and log the disconnection.
        """
        transport = SSHFactory.buildProtocol(self, address)
        transport._realConnectionLost = transport.connectionLost
        transport.connectionLost = (
            lambda reason: self.connectionLost(transport, reason))
        notify(events.UserConnected(transport, address))
        return transport

    def connectionLost(self, transport, reason):
        """Call 'connectionLost' on 'transport', logging the event."""
        try:
            return transport._realConnectionLost(reason)
        finally:
            # Conch's userauth module sets 'avatar' on the transport if the
            # authentication succeeded. Thus, if it's not there,
            # authentication failed. We can't generate this event from the
            # authentication layer since:
            #
            # a) almost every SSH login has at least one failure to
            # authenticate due to multiple keys on the client-side.
            #
            # b) the server doesn't normally generate a "go away" event.
            # Rather, the client simply stops trying.
            if getattr(transport, 'avatar', None) is None:
                notify(events.AuthenticationFailed(transport))
            notify(events.UserDisconnected(transport))

    def getPublicKeys(self):
        """Return the server's configured public key.

        See `SSHFactory.getPublicKeys`.
        """
        return {'ssh-rsa': self._public_key}

    def getPrivateKeys(self):
        """Return the server's configured private key.

        See `SSHFactory.getPrivateKeys`.
        """
        return {'ssh-rsa': self._private_key}


class SSHService(service.Service):
    """A Twisted service for the SSH server."""

    def __init__(self, portal, private_key_path, public_key_path,
                 oops_configuration, main_log, access_log,
                 access_log_path, strport='tcp:22', factory_decorator=None,
                 banner=None):
        """Construct an SSH service.

        :param portal: The `twisted.cred.portal.Portal` that turns
            authentication requests into views on the system.
        :param private_key_path: The path to the SSH server's private key.
        :param public_key_path: The path to the SSH server's public key.
        :param oops_configuration: The section of the configuration file with
            the OOPS config details for this server.
        :param main_log: The name of the logger to log most of the server
            stuff to.
        :param access_log: The name of the logger object to log the server
            access details to.
        :param access_log_path: The path to the access log file.
        :param strport: The port to run the server on, expressed in Twisted's
            "strports" mini-language. Defaults to 'tcp:22'.
        :param factory_decorator: An optional callable that can decorate the
            server factory (e.g. with a
            `twisted.protocols.policies.TimeoutFactory`).  It takes one
            argument, a factory, and must return a factory.
        :param banner: An announcement printed to users when they connect.
            By default, announce nothing.
        """
        ssh_factory = Factory(
            portal,
            private_key=Key.fromFile(private_key_path),
            public_key=Key.fromFile(public_key_path),
            banner=banner)
        if factory_decorator is not None:
            ssh_factory = factory_decorator(ssh_factory)
        self.service = strports.service(strport, ssh_factory)
        self._oops_configuration = oops_configuration
        self._main_log = main_log
        self._access_log = access_log
        self._access_log_path = access_log_path

    def startService(self):
        """Start the SSH service."""
        manager = accesslog.LoggingManager(
            logging.getLogger(self._main_log),
            logging.getLogger(self._access_log_path),
            self._access_log_path)
        manager.setUp()
        notify(events.ServerStarting())
        # By default, only the owner of files should be able to write to them.
        # Perhaps in the future this line will be deleted and the umask
        # managed by the startup script.
        os.umask(0022)
        service.Service.startService(self)
        self.service.startService()

    def stopService(self):
        """Stop the SSH service."""
        deferred = gatherResults([
            defer.maybeDeferred(service.Service.stopService, self),
            defer.maybeDeferred(self.service.stopService)])

        def log_stopped(ignored):
            notify(events.ServerStopped())
            return ignored

        return deferred.addBoth(log_stopped)
