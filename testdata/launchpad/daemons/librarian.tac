# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

# Twisted Application Configuration file.
# Use with "twistd2.4 -y <file.tac>", e.g. "twistd -noy server.tac"

import os
import signal

from meliae import scanner
from twisted.application import (
    service,
    strports,
    )
from twisted.internet import reactor
from twisted.python import log
from twisted.scripts.twistd import ServerOptions
from twisted.web import server

from lp.services.config import (
    config,
    dbconfig,
    )
from lp.services.daemons import readyservice
from lp.services.librarian.interfaces.client import (
    DUMP_FILE,
    SIGDUMPMEM,
    )
from lp.services.librarianserver import (
    db,
    storage,
    web as fatweb,
    )
from lp.services.librarianserver.libraryprotocol import FileUploadFactory
from lp.services.scripts import execute_zcml_for_scripts
from lp.services.twistedsupport.loggingsupport import set_up_oops_reporting

# Connect to database
dbconfig.override(
    dbuser=config.librarian.dbuser,
    isolation_level=config.librarian.isolation_level)
execute_zcml_for_scripts()

if os.environ.get('LP_TEST_INSTANCE'):
    # Running in ephemeral mode: get the root dir from the environment and
    # dynamically allocate ports.
    path = os.environ['LP_LIBRARIAN_ROOT']
else:
    path = config.librarian_server.root
if config.librarian_server.upstream_host:
    upstreamHost = config.librarian_server.upstream_host
    upstreamPort = config.librarian_server.upstream_port
    reactor.addSystemEventTrigger(
        'before', 'startup', log.msg,
        'Using upstream librarian http://%s:%d' %
        (upstreamHost, upstreamPort))
else:
    upstreamHost = upstreamPort = None
    reactor.addSystemEventTrigger(
        'before', 'startup', log.msg, 'Not using upstream librarian')

application = service.Application('Librarian')
librarianService = service.IServiceCollection(application)

# Service that announces when the daemon is ready
readyservice.ReadyService().setServiceParent(librarianService)

def setUpListener(uploadPort, webPort, restricted):
    """Set up a librarian listener on the given ports.

    :param restricted: Should this be a restricted listener?  A restricted
        listener will serve only files with the 'restricted' file set and all
        files uploaded through the restricted listener will have that flag
        set.
    """
    librarian_storage = storage.LibrarianStorage(
        path, db.Library(restricted=restricted))
    upload_factory = FileUploadFactory(librarian_storage)
    strports.service("tcp:%d" % uploadPort, upload_factory).setServiceParent(
        librarianService)
    root = fatweb.LibraryFileResource(
        librarian_storage, upstreamHost, upstreamPort)
    root.putChild('search', fatweb.DigestSearchResource(librarian_storage))
    root.putChild('robots.txt', fatweb.robotsTxt)
    site = server.Site(root)
    site.displayTracebacks = False
    strports.service("tcp:%d" % webPort, site).setServiceParent(
        librarianService)

if os.environ.get('LP_TEST_INSTANCE'):
    # Running in ephemeral mode: allocate ports on demand.
    setUpListener(0, 0, restricted=False)
    setUpListener(0, 0, restricted=True)
else:
    # Set up the public librarian.
    uploadPort = config.librarian.upload_port
    webPort = config.librarian.download_port
    setUpListener(uploadPort, webPort, restricted=False)
    # Set up the restricted librarian.
    webPort = config.librarian.restricted_download_port
    uploadPort = config.librarian.restricted_upload_port
    setUpListener(uploadPort, webPort, restricted=True)

# Log OOPS reports
options = ServerOptions()
options.parseOptions()
logfile = options.get("logfile")
set_up_oops_reporting('librarian', 'librarian', logfile)

# Setup a signal handler to dump the process' memory upon 'kill -44'.
def sigdumpmem_handler(signum, frame):
    scanner.dump_all_objects(DUMP_FILE)

signal.signal(SIGDUMPMEM, sigdumpmem_handler)
