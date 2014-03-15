# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""
This TAC is used for the TacTestSetupTestCase.test_couldNotListenTac test case
in test_tachandler.py.  It fails with a CannotListenError.
"""

__metaclass__ = type

from twisted.application import (
    internet,
    service,
    )
from twisted.internet import protocol

from lp.services.daemons import readyservice


application = service.Application('CannotListen')
serviceCollection = service.IServiceCollection(application)

# Service that announces when the daemon is ready
readyservice.ReadyService().setServiceParent(serviceCollection)

# We almost certainly can't listen on port 1 (usually it requires root
# permissions), so this should fail.
internet.TCPServer(1, protocol.Factory()).setServiceParent(serviceCollection)

# Just in case we can, try listening on port 1 *again*.  This will fail.
internet.TCPServer(1, protocol.Factory()).setServiceParent(serviceCollection)
