# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

# This is a Twisted application config file.  To run, use:
#     twistd -noy sftp.tac
# or similar.  Refer to the twistd(1) man page for details.

import logging

from twisted.application import service
from twisted.conch.interfaces import ISession
from twisted.conch.ssh import filetransfer
from twisted.cred.portal import IRealm, Portal
from twisted.protocols.policies import TimeoutFactory
from twisted.python import components
from twisted.scripts.twistd import ServerOptions
from twisted.web.xmlrpc import Proxy

from zope.interface import implements

from lp.services.config import config
from lp.services.daemons import readyservice

from lp.poppy import get_poppy_root
from lp.poppy.twistedftp import (
    FTPServiceFactory,
    )
from lp.poppy.twistedsftp import SFTPServer
from lp.services.sshserver.auth import (
    LaunchpadAvatar, PublicKeyFromLaunchpadChecker)
from lp.services.sshserver.service import SSHService
from lp.services.sshserver.session import DoNothingSession
from lp.services.twistedsupport.loggingsupport import set_up_oops_reporting


def make_portal():
    """Create and return a `Portal` for the SSH service.

    This portal accepts SSH credentials and returns our customized SSH
    avatars (see `LaunchpadAvatar`).
    """
    authentication_proxy = Proxy(
        config.poppy.authentication_endpoint)
    portal = Portal(Realm(authentication_proxy))
    portal.registerChecker(
        PublicKeyFromLaunchpadChecker(authentication_proxy))
    return portal


class Realm:
    implements(IRealm)

    def __init__(self, authentication_proxy):
        self.authentication_proxy = authentication_proxy

    def requestAvatar(self, avatar_id, mind, *interfaces):
        # Fetch the user's details from the authserver
        deferred = mind.lookupUserDetails(
            self.authentication_proxy, avatar_id)

        # Once all those details are retrieved, we can construct the avatar.
        def got_user_dict(user_dict):
            avatar = LaunchpadAvatar(user_dict)
            return interfaces[0], avatar, avatar.logout

        return deferred.addCallback(got_user_dict)


def poppy_sftp_adapter(avatar):
    return SFTPServer(avatar, get_poppy_root())


# Force python logging to all go to the Twisted log.msg interface. The default
# - output on stderr - will not be watched by anyone.
from twisted.python import log
stream = log.StdioOnnaStick()
logging.basicConfig(stream=stream, level=logging.INFO)


components.registerAdapter(
    poppy_sftp_adapter, LaunchpadAvatar, filetransfer.ISFTPServer)

components.registerAdapter(DoNothingSession, LaunchpadAvatar, ISession)


# ftpport defaults to 2121 in schema-lazr.conf
ftpservice = FTPServiceFactory.makeFTPService(port=config.poppy.ftp_port)

# Construct an Application that has the Poppy SSH server,
# and the Poppy FTP server.
options = ServerOptions()
options.parseOptions()
application = service.Application('poppy-sftp')
observer = set_up_oops_reporting(
    'poppy-sftp', 'poppy', options.get('logfile'))
application.addComponent(observer, ignoreClass=1)

ftpservice.setServiceParent(application)


def timeout_decorator(factory):
    """Add idle timeouts to a factory."""
    return TimeoutFactory(factory, timeoutPeriod=config.poppy.idle_timeout)

svc = SSHService(
    portal=make_portal(),
    private_key_path=config.poppy.host_key_private,
    public_key_path=config.poppy.host_key_public,
    oops_configuration='poppy',
    main_log='poppy',
    access_log='poppy.access',
    access_log_path=config.poppy.access_log,
    strport=config.poppy.port,
    factory_decorator=timeout_decorator,
    banner=config.poppy.banner)
svc.setServiceParent(application)

# Service that announces when the daemon is ready
readyservice.ReadyService().setServiceParent(application)
