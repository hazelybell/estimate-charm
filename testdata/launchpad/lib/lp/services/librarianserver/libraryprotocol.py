# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from datetime import datetime

from pytz import utc
from twisted.internet import protocol
from twisted.internet.threads import deferToThread
from twisted.protocols import basic
from twisted.python import log

from lp.services.librarianserver.storage import WrongDatabaseError


class ProtocolViolation(Exception):
    def __init__(self, msg):
        self.msg = msg
        self.args = (msg,)


class FileUploadProtocol(basic.LineReceiver):
    """Simple HTTP-like protocol for file uploads.

    A client sends an upload with a request like::

        STORE 10000 foo.txt
        Optional-Header: value
        Optional-Header: value

        <....10000 bytes....>

    And this server will respond with::

        200 1234/5678

    Where "1234" is the file id in our system, and "5678" is file alias id.

    Recognised headers are:
      :Content-Type: a mime-type to associate with the file
      :File-Content-ID: if specified, the integer file id for this file.
        If not specified, the server will generate one.
      :File-Alias-ID: if specified, the integer file alias id for this file.
        If not specified, the server will generate one.
      :File-Expires: if specified, the expiry time of this alias in ISO 8601
        format. As per LibrarianGarbageCollection.
      :Database-Name: if specified, the name of the database the client is
        connected to.  The server will check that this matches, and reject the
        request if it doesn't.

    The File-Content-ID and File-Alias-ID headers are also described in
    <https://launchpad.canonical.com/LibrarianTransactions>.

    Unrecognised headers will be ignored.

    If something goes wrong, the server will reply with a 400 (bad request,
    i.e.  client error) or 500 (internal server error) response codes instead,
    and an appropriate message.

    Once the server has replied, the client may re-use the connection as if it
    were just established to start a new upload.
    """

    delimiter = '\r\n'  # same as HTTP
    state = 'command'

    def lineReceived(self, line):
        try:
            getattr(self, 'line_' + self.state, self.badLine)(line)
        except ProtocolViolation as e:
            self.sendError(e.msg)
        except:
            self.unknownError()

    def sendError(self, msg, code='400'):
        """Sends a correctly formatted error to the client, and closes the
        connection."""
        self.sendLine(code + ' ' + msg)
        self.transport.loseConnection()

    def unknownError(self, failure=None):
        log.msg('Uncaught exception in FileUploadProtocol:')
        if failure is not None:
            log.err(failure)
        else:
            log.err()
        self.sendError('Internal server error', '500')

    def translateErrors(self, failure):
        """Errback to translate storage errors to protocol errors."""
        failure.trap(WrongDatabaseError)
        exc = failure.value
        raise ProtocolViolation(
            "Wrong database %r, should be %r"
            % (exc.clientDatabaseName, exc.serverDatabaseName))

    def protocolErrors(self, failure):
        failure.trap(ProtocolViolation)
        self.sendError(failure.value.msg)

    def badLine(self, line):
        raise ProtocolViolation('Unexpected message from client: ' + line)

    def line_command(self, line):
        try:
            command, args = line.split(None, 1)
        except ValueError:
            raise ProtocolViolation('Bad command: ' + line)

        bad = lambda args: self.badCommand(line)
        getattr(self, 'command_' + command.upper(), bad)(args)

    def line_header(self, line):
        # Blank line signals the end of the headers
        if line == '':
            # If File-Content-ID was specified, File-Alias-ID must be too, and
            # vice-versa.
            contentID = self.newFile.contentID
            aliasID = self.newFile.aliasID
            if ((contentID is not None and aliasID is None) or
                (aliasID is not None and contentID is None)):
                raise ProtocolViolation(
                    "File-Content-ID and File-Alias-ID must both be specified"
                    )

            # The Database-Name header is always required.
            if self.newFile.databaseName is None:
                raise ProtocolViolation("Database-Name header is required")

            # If that's ok, we're ready to receive the file.
            self.state = 'file'
            self.setRawMode()

            # Make sure rawDataReceived is *always* called, so that zero-byte
            # uploads don't hang.  It's harmless the rest of the time.
            self.rawDataReceived('')

            return

        # Simple RFC 822-ish header parsing
        try:
            name, value = line.split(':', 2)
        except ValueError:
            raise ProtocolViolation('Invalid header: ' + line)

        ignore = lambda value: None
        value = value.strip()
        name = name.lower().replace('-', '_')
        getattr(self, 'header_' + name, ignore)(value)

    def badCommand(self, line):
        raise ProtocolViolation('Unknown command: ' + line)

    def command_STORE(self, args):
        try:
            size, name = args.split(None, 1)
            try:
                name = name.decode('utf-8')
            except:
                raise ProtocolViolation(
                    "STORE command expects the filename to be in UTF-8")
            size = int(size)
        except ValueError:
            raise ProtocolViolation(
                    "STORE command expects a size and file name")
        fileLibrary = self.factory.fileLibrary
        self.newFile = fileLibrary.startAddFile(name, size)
        self.bytesLeft = size
        self.state = 'header'

    def header_content_type(self, value):
        self.newFile.mimetype = value

    def header_sha1_digest(self, value):
        self.newFile.srcDigest = value

    def header_file_content_id(self, value):
        try:
            self.newFile.contentID = int(value)
        except ValueError:
            raise ProtocolViolation("Invalid File-Content-ID: " + value)

    def header_file_alias_id(self, value):
        try:
            self.newFile.aliasID = int(value)
        except ValueError:
            raise ProtocolViolation("Invalid File-Alias-ID: " + value)

    def header_file_expires(self, value):
        try:
            epoch = int(value)
        except ValueError:
            raise ProtocolViolation("Invalid File-Expires: " + value)

        self.newFile.expires = datetime.fromtimestamp(
                epoch).replace(tzinfo=utc)

    def header_database_name(self, value):
        self.newFile.databaseName = value

    def header_debug_id(self, value):
        self.newFile.debugID = value

    def rawDataReceived(self, data):
        realdata, rest = data[:self.bytesLeft], data[self.bytesLeft:]
        self.bytesLeft -= len(realdata)
        self.newFile.append(realdata)

        if self.bytesLeft == 0:
            # Store file.
            deferred = self._storeFile()

            def _sendID((fileID, aliasID)):
                # Send ID to client.
                if self.newFile.contentID is None:
                    # Respond with deprecated server-generated IDs.
                    self.sendLine('200 %s/%s' % (fileID, aliasID))
                else:
                    self.sendLine('200')
            deferred.addBoth(self.logDebugging)
            deferred.addCallback(_sendID)
            deferred.addErrback(self.translateErrors)
            deferred.addErrback(self.protocolErrors)
            deferred.addErrback(self.unknownError)

            # Treat remaining bytes (if any) as a new command.
            self.state = 'command'
            self.setLineMode(rest)

    def logDebugging(self, result_or_failure):
        if self.newFile.debugID is not None:
            for msg in self.newFile.debugLog:
                log.msg('Debug %s: %s' % (self.newFile.debugID, msg))
        return result_or_failure

    def _storeFile(self):
        return deferToThread(self.newFile.store)


class FileUploadFactory(protocol.Factory):
    protocol = FileUploadProtocol

    def __init__(self, fileLibrary):
        self.fileLibrary = fileLibrary
