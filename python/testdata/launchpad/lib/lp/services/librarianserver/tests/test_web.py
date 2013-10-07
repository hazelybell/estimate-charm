# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from cStringIO import StringIO
from datetime import datetime
import httplib
import unittest
from urllib2 import (
    HTTPError,
    urlopen,
    )
from urlparse import urlparse

from lazr.uri import URI
import pytz
from storm.expr import SQL
import transaction
from zope.component import getUtility

from lp.services.config import config
from lp.services.database.interfaces import IMasterStore
from lp.services.database.sqlbase import (
    cursor,
    flush_database_updates,
    session_store,
    )
from lp.services.librarian.client import (
    get_libraryfilealias_download_path,
    LibrarianClient,
    )
from lp.services.librarian.interfaces import ILibraryFileAliasSet
from lp.services.librarian.interfaces.client import DownloadFailed
from lp.services.librarian.model import (
    LibraryFileAlias,
    TimeLimitedToken,
    )
from lp.testing.dbuser import switch_dbuser
from lp.testing.layers import (
    LaunchpadFunctionalLayer,
    LaunchpadZopelessLayer,
    )


def uri_path_replace(url, old, new):
    """Replace a substring of a URL's path."""
    parsed = URI(url)
    return str(parsed.replace(path=parsed.path.replace(old, new)))


class LibrarianWebTestCase(unittest.TestCase):
    """Test the librarian's web interface."""
    layer = LaunchpadFunctionalLayer
    dbuser = 'librarian'

    # Add stuff to a librarian via the upload port, then check that it's
    # immediately visible on the web interface. (in an attempt to test ddaa's
    # 500-error issue).

    def commit(self):
        """Synchronize database state."""
        flush_database_updates()
        transaction.commit()

    def test_uploadThenDownload(self):
        client = LibrarianClient()

        # Do this 10 times, to try to make sure we get all the threads in the
        # thread pool involved more than once, in case handling the second
        # request is an issue...
        for count in range(10):
            # Upload a file.  This should work without any exceptions being
            # thrown.
            sampleData = 'x' + ('blah' * (count%5))
            fileAlias = client.addFile('sample', len(sampleData),
                                                 StringIO(sampleData),
                                                 contentType='text/plain')

            # Make sure we can get its URL
            url = client.getURLForAlias(fileAlias)

            # However, we can't access it until we have committed,
            # because the server has no idea what mime-type to send it as
            # (NB. This could be worked around if necessary by having the
            # librarian allow access to files that don't exist in the DB
            # and spitting them out with an 'unknown' mime-type
            # -- StuartBishop)
            self.require404(url)
            self.commit()

            # Make sure we can download it using the API
            fileObj = client.getFileByAlias(fileAlias)
            self.assertEqual(sampleData, fileObj.read())
            fileObj.close()

            # And make sure the URL works too
            fileObj = urlopen(url)
            self.assertEqual(sampleData, fileObj.read())
            fileObj.close()

    def test_checkGzipEncoding(self):
        # Files that end in ".txt.gz" are treated special and are returned
        # with an encoding of "gzip" or "x-gzip" to accomodate requirements of
        # displaying Ubuntu build logs in the browser.  The mimetype should be
        # "text/plain" for these files.
        client = LibrarianClient()
        contents = 'Build log...'
        build_log = StringIO(contents)
        alias_id = client.addFile(name="build_log.txt.gz",
                                  size=len(contents),
                                  file=build_log,
                                  contentType="text/plain")

        self.commit()

        url = client.getURLForAlias(alias_id)
        fileObj = urlopen(url)
        mimetype = fileObj.headers['content-type']
        encoding = fileObj.headers['content-encoding']
        self.failUnless(mimetype == "text/plain",
                        "Wrong mimetype. %s != 'text/plain'." % mimetype)
        self.failUnless(encoding == "gzip",
                        "Wrong encoding. %s != 'gzip'." % encoding)

    def test_checkNoEncoding(self):
        # Other files should have no encoding.
        client = LibrarianClient()
        contents = 'Build log...'
        build_log = StringIO(contents)
        alias_id = client.addFile(name="build_log.tgz",
                                  size=len(contents),
                                  file=build_log,
                                  contentType="application/x-tar")

        self.commit()

        url = client.getURLForAlias(alias_id)
        fileObj = urlopen(url)
        mimetype = fileObj.headers['content-type']
        self.assertRaises(KeyError, fileObj.headers.__getitem__,
                          'content-encoding')
        self.failUnless(
            mimetype == "application/x-tar",
            "Wrong mimetype. %s != 'application/x-tar'." % mimetype)

    def test_aliasNotFound(self):
        client = LibrarianClient()
        self.assertRaises(DownloadFailed, client.getURLForAlias, 99)

    def test_oldurl(self):
        # 'old' urls are in the form of http://server:port/cid/aid/fname
        # which we want to continue supporting. The content id is simply
        # ignored
        client = LibrarianClient()
        filename = 'sample.txt'
        aid = client.addFile(filename, 6, StringIO('sample'), 'text/plain')
        self.commit()
        url = client.getURLForAlias(aid)
        self.assertEqual(urlopen(url).read(), 'sample')

        old_url = uri_path_replace(url, str(aid), '42/%d' % aid)
        self.assertEqual(urlopen(old_url).read(), 'sample')

        # If the content and alias IDs are not integers, a 404 is raised
        old_url = uri_path_replace(url, str(aid), 'foo/%d' % aid)
        self.require404(old_url)
        old_url = uri_path_replace(url, str(aid), '%d/foo' % aid)
        self.require404(old_url)

    def test_404(self):
        client = LibrarianClient()
        filename = 'sample.txt'
        aid = client.addFile(filename, 6, StringIO('sample'), 'text/plain')
        self.commit()
        url = client.getURLForAlias(aid)
        self.assertEqual(urlopen(url).read(), 'sample')

        # Change the aliasid and assert we get a 404
        self.failUnless(str(aid) in url)
        bad_id_url = uri_path_replace(url, str(aid), str(aid+1))
        self.require404(bad_id_url)

        # Change the filename and assert we get a 404
        self.failUnless(filename in url)
        bad_name_url = uri_path_replace(url, filename, 'different.txt')
        self.require404(bad_name_url)

    def test_duplicateuploads(self):
        client = LibrarianClient()
        filename = 'sample.txt'
        id1 = client.addFile(filename, 6, StringIO('sample'), 'text/plain')
        id2 = client.addFile(filename, 6, StringIO('sample'), 'text/plain')

        self.failIfEqual(id1, id2, 'Got allocated the same id!')

        self.commit()

        self.failUnlessEqual(client.getFileByAlias(id1).read(), 'sample')
        self.failUnlessEqual(client.getFileByAlias(id2).read(), 'sample')

    def test_robotsTxt(self):
        url = 'http://%s:%d/robots.txt' % (
            config.librarian.download_host, config.librarian.download_port)
        f = urlopen(url)
        self.failUnless('Disallow: /' in f.read())

    def test_headers(self):
        client = LibrarianClient()

        # Upload a file so we can retrieve it.
        sample_data = 'blah'
        file_alias_id = client.addFile(
            'sample', len(sample_data), StringIO(sample_data),
            contentType='text/plain')
        url = client.getURLForAlias(file_alias_id)

        # Change the date_created to a known value that doesn't match
        # the disk timestamp. The timestamp on disk cannot be trusted.
        file_alias = IMasterStore(LibraryFileAlias).get(
            LibraryFileAlias, file_alias_id)
        file_alias.date_created = datetime(
            2001, 01, 30, 13, 45, 59, tzinfo=pytz.utc)

        # Commit so the file is available from the Librarian.
        self.commit()

        # Fetch the file via HTTP, recording the interesting headers
        result = urlopen(url)
        last_modified_header = result.info()['Last-Modified']
        cache_control_header = result.info()['Cache-Control']

        # URLs point to the same content for ever, so we have a hardcoded
        # 1 year max-age cache policy.
        self.failUnlessEqual(cache_control_header, 'max-age=31536000, public')

        # And we should have a correct Last-Modified header too.
        self.failUnlessEqual(
            last_modified_header, 'Tue, 30 Jan 2001 13:45:59 GMT')

    def get_restricted_file_and_public_url(self):
        # Use a regular LibrarianClient to ensure we speak to the
        # nonrestricted port on the librarian which is where secured
        # restricted files are served from.
        client = LibrarianClient()
        fileAlias = client.addFile(
            'sample', 12, StringIO('a'*12), contentType='text/plain')
        # Note: We're deliberately using the wrong url here: we should be
        # passing secure=True to getURLForAlias, but to use the returned URL
        # we would need a wildcard DNS facility patched into urlopen; instead
        # we use the *deliberate* choice of having the path of secure and
        # insecure urls be the same, so that we can test it: the server code
        # doesn't need to know about the fancy wildcard domains.
        url = client.getURLForAlias(fileAlias)
        # Now that we have a url which talks to the public librarian, make the
        # file restricted.
        IMasterStore(LibraryFileAlias).find(LibraryFileAlias,
            LibraryFileAlias.id==fileAlias).set(
            LibraryFileAlias.restricted==True)
        self.commit()
        return fileAlias, url

    def test_restricted_subdomain_must_match_file_alias(self):
        # IFF there is a .restricted. in the host, then the library file alias
        # in the subdomain must match that in the path.
        client = LibrarianClient()
        fileAlias = client.addFile('sample', 12, StringIO('a'*12),
            contentType='text/plain')
        fileAlias2 = client.addFile('sample', 12, StringIO('b'*12),
            contentType='text/plain')
        self.commit()
        url = client.getURLForAlias(fileAlias)
        download_host = urlparse(config.librarian.download_url)[1]
        if ':' in download_host:
            download_host = download_host[:download_host.find(':')]
        template_host = 'i%%d.restricted.%s' % download_host
        path = get_libraryfilealias_download_path(fileAlias, 'sample')
        # The basic URL must work.
        urlopen(url)
        # Use the network level protocol because DNS resolution won't work
        # here (no wildcard support)
        connection = httplib.HTTPConnection(
            config.librarian.download_host,
            config.librarian.download_port)
        # A valid subdomain based URL must work.
        good_host = template_host % fileAlias
        connection.request("GET", path, headers={'Host': good_host})
        response = connection.getresponse()
        response.read()
        self.assertEqual(200, response.status, response)
        # A subdomain based URL trying to put fileAlias into the restricted
        # domain of fileAlias2 must not work.
        hostile_host = template_host % fileAlias2
        connection.request("GET", path, headers={'Host': hostile_host})
        response = connection.getresponse()
        response.read()
        self.assertEqual(404, response.status)
        # A subdomain which matches the LFA but is nested under one that
        # doesn't is also treated as hostile.
        nested_host = 'i%d.restricted.i%d.restricted.%s' % (
            fileAlias, fileAlias2, download_host)
        connection.request("GET", path, headers={'Host': nested_host})
        response = connection.getresponse()
        response.read()
        self.assertEqual(404, response.status)

    def test_restricted_no_token(self):
        fileAlias, url = self.get_restricted_file_and_public_url()
        # The file should not be able to be opened - we haven't allocated a
        # token.  When the token is wrong or stale a 404 is given (to avoid
        # disclosure about what content we hold. Alternatively a 401 could be
        # given (as long as we give a 401 when the file is missing as well -
        # but that requires some more complex changes in the deployment
        # infrastructure to permit more backend knowledge of the frontend
        # request.
        self.require404(url)

    def test_restricted_made_up_token(self):
        fileAlias, url = self.get_restricted_file_and_public_url()
        # The file should not be able to be opened - the token supplied
        # is not one we issued.
        self.require404(url + '?token=haxx0r')

    def test_restricted_with_token(self):
        fileAlias, url = self.get_restricted_file_and_public_url()
        # We have the base url for a restricted file; grant access to it
        # for a short time.
        token = TimeLimitedToken.allocate(url)
        url = url + "?token=%s" % token
        # Now we should be able to access the file.
        fileObj = urlopen(url)
        try:
            self.assertEqual("a"*12, fileObj.read())
        finally:
            fileObj.close()

    def test_restricted_with_expired_token(self):
        fileAlias, url = self.get_restricted_file_and_public_url()
        # We have the base url for a restricted file; grant access to it
        # for a short time.
        token = TimeLimitedToken.allocate(url)
        # But time has passed
        store = session_store()
        tokens = store.find(TimeLimitedToken, TimeLimitedToken.token==token)
        tokens.set(
            TimeLimitedToken.created==SQL("created - interval '1 week'"))
        url = url + "?token=%s" % token
        # Now, as per test_restricted_no_token we should get a 404.
        self.require404(url)

    def test_restricted_file_headers(self):
        fileAlias, url = self.get_restricted_file_and_public_url()
        token = TimeLimitedToken.allocate(url)
        url = url + "?token=%s" % token
        # Change the date_created to a known value for testing.
        file_alias = IMasterStore(LibraryFileAlias).get(
            LibraryFileAlias, fileAlias)
        file_alias.date_created = datetime(
            2001, 01, 30, 13, 45, 59, tzinfo=pytz.utc)
        # Commit the update.
        self.commit()
        # Fetch the file via HTTP, recording the interesting headers
        result = urlopen(url)
        last_modified_header = result.info()['Last-Modified']
        cache_control_header = result.info()['Cache-Control']
        # No caching for restricted files.
        self.failUnlessEqual(cache_control_header, 'max-age=0, private')
        # And we should have a correct Last-Modified header too.
        self.failUnlessEqual(
            last_modified_header, 'Tue, 30 Jan 2001 13:45:59 GMT')
        # Perhaps we should also set Expires to the Last-Modified.

    def require404(self, url):
        """Assert that opening `url` raises a 404."""
        try:
            urlopen(url)
            self.fail('404 not raised')
        except HTTPError as e:
            self.failUnlessEqual(e.code, 404)


class LibrarianZopelessWebTestCase(LibrarianWebTestCase):
    layer = LaunchpadZopelessLayer

    def setUp(self):
        switch_dbuser(config.librarian.dbuser)

    def commit(self):
        LaunchpadZopelessLayer.commit()

    def test_getURLForAliasObject(self):
        # getURLForAliasObject returns the same URL as getURLForAlias.
        client = LibrarianClient()
        content = "Test content"
        alias_id = client.addFile(
            'test.txt', len(content), StringIO(content),
            contentType='text/plain')
        self.commit()

        alias = getUtility(ILibraryFileAliasSet)[alias_id]
        self.assertEqual(
            client.getURLForAlias(alias_id),
            client.getURLForAliasObject(alias))


class DeletedContentTestCase(unittest.TestCase):

    layer = LaunchpadZopelessLayer

    def setUp(self):
        switch_dbuser(config.librarian.dbuser)

    def test_deletedContentNotFound(self):
        # Use a user with rights to change the deleted flag in the db.
        # This currently means a superuser.
        switch_dbuser('testadmin')

        alias = getUtility(ILibraryFileAliasSet).create(
                'whatever', 8, StringIO('xxx\nxxx\n'), 'text/plain')
        alias_id = alias.id
        transaction.commit()

        # This works
        alias = getUtility(ILibraryFileAliasSet)[alias_id]
        alias.open()
        alias.read()
        alias.close()

        # And it can be retrieved via the web
        url = alias.http_url
        retrieved_content = urlopen(url).read()
        self.failUnlessEqual(retrieved_content, 'xxx\nxxx\n')

        # But when we flag the content as deleted
        cur = cursor()
        cur.execute("""
            UPDATE LibraryFileAlias SET content=NULL WHERE id=%s
            """, (alias.id, ))
        transaction.commit()

        # Things become not found
        alias = getUtility(ILibraryFileAliasSet)[alias_id]
        self.failUnlessRaises(DownloadFailed, alias.open)

        # And people see a 404 page
        try:
            urlopen(url)
            self.fail('404 not raised')
        except HTTPError as x:
            self.failUnlessEqual(x.code, 404)
