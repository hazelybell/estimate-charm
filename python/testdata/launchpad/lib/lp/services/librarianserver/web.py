# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from datetime import datetime
import time
from urlparse import urlparse

from storm.exceptions import DisconnectionError
from twisted.internet.threads import deferToThread
from twisted.python import log
from twisted.web import (
    proxy,
    resource,
    server,
    static,
    util,
    )

from lp.services.config import config
from lp.services.database import (
    read_transaction,
    write_transaction,
    )
from lp.services.librarian.client import url_path_quote
from lp.services.librarian.utils import guess_librarian_encoding


defaultResource = static.Data("""
        <html>
        <body>
        <h1>Launchpad Librarian</h1>
        <p>
        http://librarian.launchpad.net/ is a
        file repository used by
        <a href="https://launchpad.net/">Launchpad</a>.
        </p>
        <p><small>Copyright 2004-2009 Canonical Ltd.</small></p>
        <!-- kthxbye. -->
        </body></html>
        """, type='text/html')
fourOhFour = resource.NoResource('No such resource')


class NotFound(Exception):
    pass


class LibraryFileResource(resource.Resource):
    def __init__(self, storage, upstreamHost, upstreamPort):
        resource.Resource.__init__(self)
        self.storage = storage
        self.upstreamHost = upstreamHost
        self.upstreamPort = upstreamPort

    def getChild(self, name, request):
        if name == '':
            # Root resource
            return defaultResource
        try:
            aliasID = int(name)
        except ValueError:
            log.msg(
                "404: alias is not an int: %r" % (name,))
            return fourOhFour

        return LibraryFileAliasResource(self.storage, aliasID,
                self.upstreamHost, self.upstreamPort)


class LibraryFileAliasResource(resource.Resource):
    def __init__(self, storage, aliasID, upstreamHost, upstreamPort):
        resource.Resource.__init__(self)
        self.storage = storage
        self.aliasID = aliasID
        self.upstreamHost = upstreamHost
        self.upstreamPort = upstreamPort

    def getChild(self, filename, request):
        # If we still have another component of the path, then we have
        # an old URL that encodes the content ID. We want to keep supporting
        # these, so we just ignore the content id that is currently in
        # self.aliasID and extract the real one from the URL. Note that
        # tokens do not work with the old URL style: they are URL specific.
        if len(request.postpath) == 1:
            try:
                self.aliasID = int(filename)
            except ValueError:
                log.msg(
                    "404 (old URL): alias is not an int: %r" % (filename,))
                return fourOhFour
            filename = request.postpath[0]

        # IFF the request has a .restricted. subdomain, ensure there is a
        # alias id in the right most subdomain, and that it matches
        # self.aliasIDd, And that the host precisely matches what we generate
        # (specifically to stop people putting a good prefix to the left of an
        # attacking one).
        hostname = request.getRequestHostname()
        if '.restricted.' in hostname:
            # Configs can change without warning: evaluate every time.
            download_url = config.librarian.download_url
            parsed = list(urlparse(download_url))
            netloc = parsed[1]
            # Strip port if present
            if netloc.find(':') > -1:
                netloc = netloc[:netloc.find(':')]
            expected_hostname = 'i%d.restricted.%s' % (self.aliasID, netloc)
            if expected_hostname != hostname:
                log.msg(
                    '404: expected_hostname != hostname: %r != %r' %
                    (expected_hostname, hostname))
                return fourOhFour

        token = request.args.get('token', [None])[0]
        path = request.path
        deferred = deferToThread(
            self._getFileAlias, self.aliasID, token, path)
        deferred.addCallback(
                self._cb_getFileAlias, filename, request
                )
        deferred.addErrback(self._eb_getFileAlias)
        return util.DeferredResource(deferred)

    @write_transaction
    def _getFileAlias(self, aliasID, token, path):
        try:
            alias = self.storage.getFileAlias(aliasID, token, path)
            return (alias.contentID, alias.filename,
                alias.mimetype, alias.date_created, alias.restricted)
        except LookupError:
            raise NotFound

    def _eb_getFileAlias(self, failure):
        err = failure.trap(NotFound, DisconnectionError)
        if err == DisconnectionError:
            return resource.ErrorPage(
                503, 'Database unavailable',
                'A required database is unavailable.\n'
                'See http://identi.ca/launchpadstatus '
                'for maintenance and outage notifications.')
        else:
            return fourOhFour

    def _cb_getFileAlias(
            self,
            (dbcontentID, dbfilename, mimetype, date_created, restricted),
            filename, request
            ):
        # Return a 404 if the filename in the URL is incorrect. This offers
        # a crude form of access control (stuff we care about can have
        # unguessable names effectively using the filename as a secret).
        if dbfilename.encode('utf-8') != filename:
            log.msg(
                "404: dbfilename.encode('utf-8') != filename: %r != %r"
                % (dbfilename.encode('utf-8'), filename))
            return fourOhFour

        if not restricted:
            # Set our caching headers. Librarian files can be cached forever.
            request.setHeader('Cache-Control', 'max-age=31536000, public')
        else:
            # Restricted files require revalidation every time. For now,
            # until the deployment details are completely reviewed, the
            # simplest, most cautious approach is taken: no caching permited.
            request.setHeader('Cache-Control', 'max-age=0, private')

        if self.storage.hasFile(dbcontentID) or self.upstreamHost is None:
            # XXX: Brad Crittenden 2007-12-05 bug=174204: When encodings are
            # stored as part of a file's metadata this logic will be replaced.
            encoding, mimetype = guess_librarian_encoding(filename, mimetype)
            return File(
                mimetype, encoding, date_created,
                self.storage._fileLocation(dbcontentID))
        else:
            return proxy.ReverseProxyResource(self.upstreamHost,
                                              self.upstreamPort, request.path)

    def render_GET(self, request):
        return defaultResource.render(request)


class File(static.File):
    isLeaf = True

    def __init__(
        self, contentType, encoding, modification_time, *args, **kwargs):
        # Have to convert the UTC datetime to POSIX timestamp (localtime)
        offset = datetime.utcnow() - datetime.now()
        local_modification_time = modification_time - offset
        self._modification_time = time.mktime(
            local_modification_time.timetuple())
        static.File.__init__(self, *args, **kwargs)
        self.type = contentType
        self.encoding = encoding

    def getModificationTime(self):
        """Override the time on disk with the time from the database.

        This is used by twisted to set the Last-Modified: header.
        """
        return self._modification_time


class DigestSearchResource(resource.Resource):
    def __init__(self, storage):
        self.storage = storage
        resource.Resource.__init__(self)

    def render_GET(self, request):
        try:
            digest = request.args['digest'][0]
        except LookupError:
            return static.Data('Bad search', 'text/plain').render(request)

        deferred = deferToThread(self._matchingAliases, digest)
        deferred.addCallback(self._cb_matchingAliases, request)
        deferred.addErrback(_eb, request)
        return server.NOT_DONE_YET

    @read_transaction
    def _matchingAliases(self, digest):
        library = self.storage.library
        matches = ['%s/%s' % (aID, url_path_quote(aName))
                   for fID in library.lookupBySHA1(digest)
                   for aID, aName, aType in library.getAliases(fID)]
        return matches

    def _cb_matchingAliases(self, matches, request):
        text = '\n'.join([str(len(matches))] + matches)
        response = static.Data(text.encode('utf-8'),
                               'text/plain; charset=utf-8').render(request)
        request.write(response)
        request.finish()


# Ask robots not to index or archive anything in the librarian.
robotsTxt = static.Data("""
User-agent: *
Disallow: /
""", type='text/plain')


def _eb(failure, request):
    """Generic errback for failures during a render_GET."""
    request.processingFailed(failure)
