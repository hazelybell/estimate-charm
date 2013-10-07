# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the web resources of the testkeyserver."""

__metaclass__ = type

import os
import shutil

from testtools.deferredruntest import AsynchronousDeferredRunTest
from twisted.internet.endpoints import serverFromString
from twisted.python.failure import Failure
from twisted.web.client import getPage
from twisted.web.server import Site

from lp.testing import TestCase
from lp.testing.keyserver.harness import KEYS_DIR
from lp.testing.keyserver.web import KeyServerResource
from lp.testing.matchers import DocTestMatches


class RegularCallbackExecuted(Exception):
    """Raised if a regular Twisted callback is called when the request
    is supposed to return an HTTP error."""


class TestWebResources(TestCase):

    run_tests_with = AsynchronousDeferredRunTest.make_factory(timeout=2)

    def setUpKeysDirectory(self):
        path = self.makeTemporaryDirectory()
        path = os.path.join(path, 'keys')
        shutil.copytree(KEYS_DIR, path)
        return path

    def makeService(self):
        """Run a test key server on whatever port we have available."""
        from twisted.internet import reactor
        resource = KeyServerResource(self.setUpKeysDirectory())
        site = Site(resource)
        endpoint = serverFromString(reactor, 'tcp:0')
        return endpoint.listen(site)

    def fetchResource(self, listening_port, path):
        """GET the content at 'path' from the web server at 'listening_port'.
        """
        url = 'http://localhost:%s/%s' % (
            listening_port.getHost().port,
            path.lstrip('/'))
        return getPage(url)

    def getURL(self, path):
        """Start a test key server and get the content at 'path'."""
        d = self.makeService()

        def service_started(port):
            self.addCleanup(port.stopListening)
            return self.fetchResource(port, path)
        return d.addCallback(service_started)

    def assertContentMatches(self, path, content):
        """Assert that the key server content at 'path' matches 'content'."""
        d = self.getURL(path)
        return d.addCallback(self.assertThat, DocTestMatches(content))

    def assertRaises404ErrorForKeyNotFound(self, path):
        """Assert that the test server returns a 404 response
        for attempts to retrieve an unknown key.
        ."""
        d = self.getURL(path)

        def regular_execution_callback(content):
            # A really Twisted(tm) error check:
            #
            # This callback should _not_ be called, because setting
            # the HTTP status code to 500 in Lookup.processRequest()
            # prevents this. On the other hand, if the status code is
            # _not_ set, the callback check_error_details below is
            # is not executed, and the test would simply pass, while
            # it shouldn't.
            #
            # So we should assert that this callback is not executed.
            # But raising an exception here leads again to the
            # execution of check_error_details() -- for this exception.
            # So we can't simply call self.fail(), but we can raise
            # a custom exception and we can check in the error
            # callback that this exception was _not_ raised.
            raise RegularCallbackExecuted

        def check_error_details(failure):
            if isinstance(failure.value, RegularCallbackExecuted):
                self.fail('Response was not an HTTP error response.')
            if not isinstance(failure, Failure):
                raise failure
            self.assertEqual('404', failure.value.status)
            self.assertEqual(
                '<html><head><title>Error handling request</title></head>\n'
                '<body><h1>Error handling request</h1>'
                'No results found: No keys found</body></html>',
                failure.value.response)

        d.addCallback(regular_execution_callback)
        return d.addErrback(check_error_details)

    def test_index_lookup(self):
        # A key index lookup form via GET.
        return self.assertContentMatches(
            '/pks/lookup?op=index&search=0xDFD20543',
            '''\
<html>
...
<title>Results for Key 0xDFD20543</title>
...
pub  1024D/DFD20543 2005-04-13 Sample Person (revoked) &lt;sample.revoked@canonical.com&gt;
...
''')

    def test_content_lookup(self):
        # A key content lookup form via GET.
        return self.assertContentMatches(
            '/pks/lookup?op=get&'
            'search=0xA419AE861E88BC9E04B9C26FBA2B9389DFD20543',
            '''\
<html>
...
<title>Results for Key 0xA419AE861E88BC9E04B9C26FBA2B9389DFD20543</title>
...
-----BEGIN PGP PUBLIC KEY BLOCK-----
Version: GnuPG v1.4.9 (GNU/Linux)
<BLANKLINE>
mQGiBEJdmOcRBADkNJPTBuCIefBdRAhvWyD9SSVHh8GHQWS7l9sRLEsirQkKz1yB
...
''')

    def test_lookup_key_id(self):
        # We can also request a key ID instead of a fingerprint, and it will
        # glob for the fingerprint.
        return self.assertContentMatches(
            '/pks/lookup?op=get&search=0xDFD20543',
            '''\
<html>
...
<title>Results for Key 0xDFD20543</title>
...
-----BEGIN PGP PUBLIC KEY BLOCK-----
Version: GnuPG v1.4.9 (GNU/Linux)
<BLANKLINE>
mQGiBEJdmOcRBADkNJPTBuCIefBdRAhvWyD9SSVHh8GHQWS7l9sRLEsirQkKz1yB
...
''')

    def test_nonexistent_key(self):
        # If we request a nonexistent key, we get a nice error.
        return self.assertRaises404ErrorForKeyNotFound(
            '/pks/lookup?op=get&search=0xDFD20544')

    def test_add_key(self):
        # A key submit form via POST (see doc/gpghandler.txt for more
        # information).
        return self.assertContentMatches(
            '/pks/add',
            '''\
<html>
...
<title>Submit a key</title>
...
''')
