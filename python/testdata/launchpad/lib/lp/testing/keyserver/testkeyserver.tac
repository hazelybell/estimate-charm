# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

# Twisted Application Configuration file.
# Use with "twistd -y <file.tac>", e.g. "twistd -noy server.tac"

from twisted.application import (
    service,
    strports,
    )
from twisted.web import server

from lp.services.config import config
from lp.services.daemons import readyservice
from lp.services.scripts import execute_zcml_for_scripts
from lp.testing.keyserver.web import KeyServerResource

# Needed for using IGPGHandler for processing key submit.
execute_zcml_for_scripts()

application = service.Application('testkeyserver')
svc = service.IServiceCollection(application)

# Service that announces when the daemon is ready
readyservice.ReadyService().setServiceParent(svc)

site = server.Site(KeyServerResource(config.testkeyserver.root))
site.displayTracebacks = False

# Run on the port that gpghandler is configured to hit.
port = 'tcp:%s' % (config.gpghandler.port,)
strports.service(port, site).setServiceParent(svc)
