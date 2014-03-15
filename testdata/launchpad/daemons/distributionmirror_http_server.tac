# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

# Twisted Application Configuration file.
# Use with "twistd2.4 -y <file.tac>", e.g. "twistd -noy server.tac"

import os

from twisted.application import service, internet, strports
from twisted.web import server

from lp.services.daemons import readyservice
from lp.registry.tests.distributionmirror_http_server import (
    DistributionMirrorTestHTTPServer)


application = service.Application('DistributionMirrorTestHTTPServer')
httpserverService = service.IServiceCollection(application)

# Service that announces when the daemon is ready
readyservice.ReadyService().setServiceParent(httpserverService)

root = DistributionMirrorTestHTTPServer()
site = server.Site(root)
site.displayTracebacks = False
# XXX: Guilherme Salgado 2007-01-30: The port 11375 is what we use in the
# URLs of our mirrors in sampledata, so we need to use the same here.
strports.service("11375", site).setServiceParent(httpserverService)
