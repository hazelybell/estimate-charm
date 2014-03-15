# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""
Run the doctests and pagetests.
"""

__metaclass__ = type

import os

from lp.services.librarianserver.libraryprotocol import FileUploadProtocol
from lp.services.librarianserver.storage import WrongDatabaseError
from lp.services.testing import build_test_suite
from lp.testing.layers import LaunchpadZopelessLayer
from lp.testing.systemdocs import (
    LayeredDocFileSuite,
    setUp,
    tearDown,
    )


class MockTransport:
    disconnecting = False

    bytesWritten = ''
    connectionLost = False

    def write(self, bytes):
        self.bytesWritten += bytes

    def loseConnection(self):
        self.connectionLost = True
        self.disconnecting = True


class MockLibrary:
    file = None
    def startAddFile(self, name, size):
        self.file = MockFile(name)
        return self.file


class MockFile:
    bytes = ''
    stored = False
    databaseName = None
    debugID = None
    debugLog = ()

    def __init__(self, name):
        self.name = name

    def append(self, bytes):
        self.bytes += bytes

    def store(self):
        databaseName = self.databaseName
        if databaseName is not None and databaseName != 'right_database':
            raise WrongDatabaseError(databaseName, 'right_database')
        self.stored = True
        return (987, 654)


def upload_request(request):
    """Librarian upload server test helper, process a request and report what
    happens.

    Hands a request to a librarian file upload protocol, and prints the reply
    from the server, a summary of the file uploaded, and whether the connection
    closed, e.g.::

        reply: '200'
        file u'foo.txt' stored as text/plain, contents: 'Foo!'

    or::

        reply: '400 STORE command expects the filename to be in UTF-8'
        connection closed

    Note that the Librarian itself except for the protocol logic is stubbed out
    by this function; it's intended to be used to unit test the protocol
    implementation, not end-to-end test the Librarian.
    """
    # Send tracebacks from Twisted to stderr, if they occur, to make debugging
    # test failures easier.
    import sys
    def log_observer(x):
        print >> sys.stderr, x
        if 'failure' in x:
            x['failure'].printTraceback(file=sys.stderr)
    from twisted.python import log
    log.addObserver(log_observer)

    # Create a FileUploadProtocol, and instrument it for testing:
    server = FileUploadProtocol()

    #  * hook _storeFile to dispatch straight to newFile.store without
    #    spawning a thread.
    from twisted.internet import defer
    server._storeFile = lambda: defer.maybeDeferred(server.newFile.store)

    #  * give it a fake transport
    server.transport = MockTransport()
    server.connectionMade()

    #  * give it a fake factory (itself!), and a fake library.
    server.factory = server
    server.fileLibrary = MockLibrary()

    # Feed in the request
    server.dataReceived(request.replace('\n', '\r\n'))

    # Report on what happened
    print "reply: %r" % server.transport.bytesWritten.rstrip('\r\n')

    if server.transport.connectionLost:
        print 'connection closed'

    mockFile = server.fileLibrary.file
    if mockFile is not None and mockFile.stored:
        print "file %r stored as %s, contents: %r" % (
                mockFile.name, mockFile.mimetype, mockFile.bytes)

    # Cleanup: remove the observer.
    log.removeObserver(log_observer)


here = os.path.dirname(os.path.realpath(__file__))

special = {
    'librarian-report.txt': LayeredDocFileSuite(
            '../doc/librarian-report.txt',
            setUp=setUp, tearDown=tearDown,
            layer=LaunchpadZopelessLayer
            ),
    'upload.txt': LayeredDocFileSuite(
            '../doc/upload.txt',
            setUp=setUp, tearDown=tearDown,
            layer=LaunchpadZopelessLayer,
            globs={'upload_request': upload_request},
            ),
}

def test_suite():
    return build_test_suite(here, special)
