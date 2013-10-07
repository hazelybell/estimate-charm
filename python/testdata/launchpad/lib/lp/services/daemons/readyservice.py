# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Add logging for when twistd services start up.

Used externally to launchpad (by launchpad-buildd) - must not import
any Launchpad code, and any new external dependencies need coordination
with the launchpad-buildd deployment.
"""

__metaclass__ = type

__all__ = [
    'ReadyService',
    ]

from twisted.application import service
from twisted.python import log


LOG_MAGIC = 'daemon ready!'


class ReadyService(service.Service):
    """Service that logs a 'ready!' message once the reactor has started."""

    def startService(self):
        from twisted.internet import reactor
        reactor.addSystemEventTrigger('after', 'startup', log.msg, LOG_MAGIC)
        service.Service.startService(self)
