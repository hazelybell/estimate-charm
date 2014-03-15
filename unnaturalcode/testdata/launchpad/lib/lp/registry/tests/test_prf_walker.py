# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for lp.registry.scripts.productreleasefinder.walker."""

import logging
import StringIO
import urlparse

from lazr.restful.utils import safe_hasattr

from lp.registry.scripts.productreleasefinder.walker import WalkerBase
from lp.testing import (
    reset_logging,
    TestCase,
    )


class WalkerBase_Logging(TestCase):

    def testCreatesDefaultLogger(self):
        """WalkerBase creates a default logger."""
        from logging import Logger
        w = WalkerBase("/")
        self.failUnless(isinstance(w.log, Logger))

    def testCreatesChildLogger(self):
        """WalkerBase creates a child logger if given a parent."""
        from logging import getLogger
        parent = getLogger("foo")
        w = WalkerBase("/", log_parent=parent)
        self.assertEquals(w.log.parent, parent)


class WalkerBase_Base(TestCase):

    def testSetsBase(self):
        """WalkerBase sets the base property."""
        w = WalkerBase("ftp://localhost/")
        self.assertEquals(w.base, "ftp://localhost/")

    def testSetsScheme(self):
        """WalkerBase sets the scheme property."""
        w = WalkerBase("ftp://localhost/")
        self.assertEquals(w.scheme, "ftp")

    def testSetsHost(self):
        """WalkerBase sets the host property."""
        w = WalkerBase("ftp://localhost/")
        self.assertEquals(w.host, "localhost")

    def testNoScheme(self):
        """WalkerBase works when given a URL with no scheme."""
        w = WalkerBase("/")
        self.assertEquals(w.host, "")

    def testWrongScheme(self):
        """WalkerBase raises WalkerError when given an unhandled scheme."""
        from lp.registry.scripts.productreleasefinder.walker import (
            WalkerBase, WalkerError)
        self.assertRaises(WalkerError, WalkerBase, "foo://localhost/")

    def testUnescapesHost(self):
        """WalkerBase unescapes the host portion."""
        w = WalkerBase("ftp://local%40host/")
        self.assertEquals(w.host, "local@host")

    def testNoUsername(self):
        """WalkerBase stores None when there is no username."""
        w = WalkerBase("ftp://localhost/")
        self.assertEquals(w.user, None)

    def testUsername(self):
        """WalkerBase splits out the username from the host portion."""
        w = WalkerBase("ftp://scott@localhost/")
        self.assertEquals(w.user, "scott")
        self.assertEquals(w.host, "localhost")

    def testUnescapesUsername(self):
        """WalkerBase unescapes the username portion."""
        w = WalkerBase("ftp://scott%3awibble@localhost/")
        self.assertEquals(w.user, "scott:wibble")
        self.assertEquals(w.host, "localhost")

    def testNoPassword(self):
        """WalkerBase stores None when there is no password."""
        w = WalkerBase("ftp://scott@localhost/")
        self.assertEquals(w.passwd, None)

    def testPassword(self):
        """WalkerBase splits out the password from the username."""
        w = WalkerBase("ftp://scott:wibble@localhost/")
        self.assertEquals(w.user, "scott")
        self.assertEquals(w.passwd, "wibble")
        self.assertEquals(w.host, "localhost")

    def testUnescapesPassword(self):
        """WalkerBase unescapes the password portion."""
        w = WalkerBase("ftp://scott:wibble%20wobble@localhost/")
        self.assertEquals(w.user, "scott")
        self.assertEquals(w.passwd, "wibble wobble")
        self.assertEquals(w.host, "localhost")

    def testPathOnly(self):
        """WalkerBase stores the path if that's all there is."""
        w = WalkerBase("/path/to/something/")
        self.assertEquals(w.path, "/path/to/something/")

    def testPathInUrl(self):
        """WalkerBase stores the path portion of a complete URL."""
        w = WalkerBase("ftp://localhost/path/to/something/")
        self.assertEquals(w.path, "/path/to/something/")

    def testAddsSlashToPath(self):
        """WalkerBase adds a trailing slash to path if ommitted."""
        w = WalkerBase("ftp://localhost/path/to/something")
        self.assertEquals(w.path, "/path/to/something/")

    def testUnescapesPath(self):
        """WalkerBase leaves the path escaped."""
        w = WalkerBase("ftp://localhost/some%20thing/")
        self.assertEquals(w.path, "/some%20thing/")

    def testStoresQuery(self):
        """WalkerBase stores the query portion of a supporting URL."""
        w = WalkerBase("http://localhost/?foo")
        self.assertEquals(w.query, "foo")

    def testStoresFragment(self):
        """WalkerBase stores the fragment portion of a supporting URL."""
        WalkerBase.FRAGMENTS = True
        try:
            w = WalkerBase("http://localhost/#foo")
            self.assertEquals(w.fragment, "foo")
        finally:
            WalkerBase.FRAGMENTS = False


class WalkerBase_walk(TestCase):
    """Test the walk() method."""

    def tearDown(self):
        reset_logging()
        super(WalkerBase_walk, self).tearDown()

    def test_walk_UnicodeEncodeError(self):
        """Verify that a UnicodeEncodeError is logged."""

        class TestWalker(WalkerBase):

            def list(self, sub_dir):
                # Force the walker to handle an exception.
                raise UnicodeEncodeError(
                    'utf-8', u'source text', 0, 1, 'reason')

            def open(self):
                pass

            def close(self):
                pass

        log_output = StringIO.StringIO()
        logger = logging.getLogger()
        self.addCleanup(logger.setLevel, logger.level)
        logger.setLevel(logging.DEBUG)
        logger.addHandler(logging.StreamHandler(log_output))
        walker = TestWalker('http://example.org/foo', logger)
        list(walker)
        self.assertEqual(
            "Unicode error parsing http://example.org/foo page '/foo/'\n",
            log_output.getvalue())

    def test_walk_open_fail(self):
        # The walker handles an exception raised during open().

        class TestWalker(WalkerBase):

            def list(self, sub_dir):
                pass

            def open(self):
                raise IOError("Test failure.")

            def close(self):
                pass

        log_output = StringIO.StringIO()
        logger = logging.getLogger()
        self.addCleanup(logger.setLevel, logger.level)
        logger.setLevel(logging.DEBUG)
        logger.addHandler(logging.StreamHandler(log_output))
        walker = TestWalker('ftp://example.org/foo', logger)
        list(walker)
        self.assertEqual(
            "Could not connect to ftp://example.org/foo\n"
            "Failure: Test failure.\n",
            log_output.getvalue())


class FTPWalker_Base(TestCase):

    def testFtpScheme(self):
        """FTPWalker works when initialized with an ftp-scheme URL."""
        from lp.registry.scripts.productreleasefinder.walker import (
            FTPWalker)
        w = FTPWalker("ftp://localhost/")
        self.assertEquals(w.host, "localhost")

    def testNoScheme(self):
        """FTPWalker works when given a URL with no scheme."""
        from lp.registry.scripts.productreleasefinder.walker import (
            FTPWalker)
        w = FTPWalker("/")
        self.assertEquals(w.host, "")

    def testWrongScheme(self):
        """FTPWalker raises WalkerError when given an unhandled scheme."""
        from lp.registry.scripts.productreleasefinder.walker import (
            FTPWalker, WalkerError)
        self.assertRaises(WalkerError, FTPWalker, "http://localhost/")

    def testNoUsername(self):
        """FTPWalker stores 'anonymous' when there is no username."""
        from lp.registry.scripts.productreleasefinder.walker import (
            FTPWalker)
        w = FTPWalker("ftp://localhost/")
        self.assertEquals(w.user, "anonymous")

    def testNoPassword(self):
        """FTPWalker stores empty string when there is no password."""
        from lp.registry.scripts.productreleasefinder.walker import (
            FTPWalker)
        w = FTPWalker("ftp://scott@localhost/")
        self.assertEquals(w.passwd, "")


class HTTPWalker_Base(TestCase):

    def testHttpScheme(self):
        """HTTPWalker works when initialized with an http-scheme URL."""
        from lp.registry.scripts.productreleasefinder.walker import (
            HTTPWalker)
        w = HTTPWalker("http://localhost/")
        self.assertEquals(w.host, "localhost")

    def testHttpsScheme(self):
        """HTTPWalker works when initialized with an https-scheme URL."""
        from lp.registry.scripts.productreleasefinder.walker import (
            HTTPWalker)
        w = HTTPWalker("https://localhost/")
        self.assertEquals(w.host, "localhost")

    def testNoScheme(self):
        """HTTPWalker works when given a URL with no scheme."""
        from lp.registry.scripts.productreleasefinder.walker import (
            HTTPWalker)
        w = HTTPWalker("/")
        self.assertEquals(w.host, "")

    def testWrongScheme(self):
        """HTTPWalker raises WalkerError when given an unhandled scheme."""
        from lp.registry.scripts.productreleasefinder.walker import (
            HTTPWalker, WalkerError)
        self.assertRaises(WalkerError, HTTPWalker, "foo://localhost/")


class HTTPWalker_url_schemes_and_handlers(TestCase):
    """Verify there is a handler for each URL scheme."""

    def setUp(self):
        TestCase.setUp(self)
        from lp.registry.scripts.productreleasefinder.walker import (
            HTTPWalker)
        self.walker = HTTPWalker("http://localhost/")

    def verify_url_scheme_and_handler(self, scheme, handler):
        self.assert_(scheme in self.walker.URL_SCHEMES)
        self.assert_(handler in self.walker.handlers)
        # urllib2 uses a naming convention to select the handler for
        # a URL scheme. This test is sanity to check to ensure that the
        # HTTPWalker's configuration of the OpenerDirector is will work.
        method_name = '%s_open' % scheme
        self.assert_(safe_hasattr(handler, method_name))

    def test_http_request(self):
        import urllib2
        self.verify_url_scheme_and_handler('http', urllib2.HTTPHandler)

    def test_https_request(self):
        import urllib2
        self.verify_url_scheme_and_handler('https', urllib2.HTTPSHandler)

    def test_ftp_request(self):
        import urllib2
        self.verify_url_scheme_and_handler('ftp', urllib2.FTPHandler)


class HTTPWalker_ListDir(TestCase):

    def tearDown(self):
        reset_logging()
        super(HTTPWalker_ListDir, self).tearDown()

    def setUpWalker(self, listing_url, listing_content):
        from lp.registry.scripts.productreleasefinder.walker import (
            HTTPWalker)
        test = self

        class TestHTTPWalker(HTTPWalker):

            def request(self, method, path):
                test.assertEqual(method, 'GET')
                test.assertEqual(urlparse.urljoin(self.base, path),
                                 listing_url)
                return StringIO.StringIO(listing_content)

            def isDirectory(self, path):
                return path.endswith('/')

        logging.basicConfig(level=logging.CRITICAL)
        return TestHTTPWalker(listing_url, logging.getLogger())

    def testApacheListing(self):
        # Test that list() handles a standard Apache dir listing.
        content = '''
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">
<html>
 <head>
  <title>Index of /pub/GNOME/sources/gnome-gpg/0.5</title>
 </head>
 <body>
<h1>Index of /pub/GNOME/sources/gnome-gpg/0.5</h1>
<pre><img src="/icons/blank.gif" alt="Icon " width="24" height="24"> <a href="?C=N;O=D">Name</a>                          <a href="?C=M;O=A">Last modified</a>      <a href="?C=S;O=A">Size</a>  <a href="?C=D;O=A">Description</a><hr><a href="/pub/GNOME/sources/gnome-gpg/"><img src="http://www.gnome.org/img/24x24/parent.png" alt="[DIR]" width="24" height="24"></a> <a href="/pub/GNOME/sources/gnome-gpg/">Parent Directory</a>                                   -

<a href="LATEST-IS-0.5.0"><img src="http://www.gnome.org/img/24x24/default.png" alt="[   ]" width="24" height="24"></a> <a href="LATEST-IS-0.5.0">LATEST-IS-0.5.0</a>               02-Sep-2006 08:58   81K
<a href="gnome-gpg-0.5.0.md5sum"><img src="http://www.gnome.org/img/24x24/default.png" alt="[   ]" width="24" height="24"></a> <a href="gnome-gpg-0.5.0.md5sum">gnome-gpg-0.5.0.md5sum</a>        02-Sep-2006 08:58  115
<a href="gnome-gpg-0.5.0.tar.bz2"><img src="http://www.gnome.org/img/24x24/archive.png" alt="[   ]" width="24" height="24"></a> <a href="gnome-gpg-0.5.0.tar.bz2">gnome-gpg-0.5.0.tar.bz2</a>       02-Sep-2006 08:58   68K
<a href="gnome-gpg-0.5.0.tar.gz"><img src="http://www.gnome.org/img/24x24/archive.png" alt="[   ]" width="24" height="24"></a> <a href="gnome-gpg-0.5.0.tar.gz">gnome-gpg-0.5.0.tar.gz</a>        02-Sep-2006 08:58   81K
<hr></pre>

<address>Apache/2.2.3 (Unix) Server at <a href="mailto:ftp-adm@acc.umu.se">ftp.acc.umu.se</a> Port 80</address>
</body></html>
        '''
        walker = self.setUpWalker(
            'http://ftp.gnome.org/pub/GNOME/sources/gnome-gpg/0.5/', content)
        dirnames, filenames = walker.list('/pub/GNOME/sources/gnome-gpg/0.5/')
        self.assertEqual(dirnames, [])
        self.assertEqual(filenames, ['LATEST-IS-0.5.0',
                                     'gnome-gpg-0.5.0.md5sum',
                                     'gnome-gpg-0.5.0.tar.bz2',
                                     'gnome-gpg-0.5.0.tar.gz'])

    def testSquidFtpListing(self):
        # Test that a Squid FTP listing can be parsed.
        content = '''
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN" "http://www.w3.org/TR/html4/loose.dtd">
<!-- HTML listing generated by Squid 2.5.STABLE12 -->
<!-- Wed, 06 Sep 2006 11:04:02 GMT -->
<HTML><HEAD><TITLE>
FTP Directory: ftp://ftp.gnome.org/pub/GNOME/sources/gnome-gpg/0.5/
</TITLE>
<STYLE type="text/css"><!--BODY{background-color:#ffffff;font-family:verdana,sans-serif}--></STYLE>
</HEAD><BODY>
<H2>
FTP Directory: <A HREF="/">ftp://ftp.gnome.org</A>/<A HREF="/pub/">pub</A>/<A HREF="/pub/GNOME/">GNOME</A>/<A HREF="/pub/GNOME/sources/">sources</A>/<A HREF="/pub/GNOME/sources/gnome-gpg/">gnome-gpg</A>/<A HREF="/pub/GNOME/sources/gnome-gpg/0.5/">0.5</A>/</H2>
<PRE>
<A HREF="../"><IMG border="0" SRC="http://squid:3128/squid-internal-static/icons/anthony-dirup.gif" ALT="[DIRUP]"></A> <A HREF="../">Parent Directory</A>
<A HREF="LATEST-IS-0.5.0"><IMG border="0" SRC="http://squid:3128/squid-internal-static/icons/anthony-link.gif" ALT="[LINK]"></A> <A HREF="LATEST-IS-0.5.0">LATEST-IS-0.5.0</A>. . . . . . . . . Sep 02 07:07         <A HREF="LATEST-IS-0.5.0;type=a"><IMG border="0" SRC="http://squid:3128/squid-internal-static/icons/anthony-text.gif" ALT="[VIEW]"></A> <A HREF="LATEST-IS-0.5.0;type=i"><IMG border="0" SRC="http://squid:3128/squid-internal-static/icons/anthony-box.gif" ALT="[DOWNLOAD]"></A> -> <A HREF="gnome-gpg-0.5.0.tar.gz">gnome-gpg-0.5.0.tar.gz</A>
<A HREF="gnome-gpg-0.5.0.md5sum"><IMG border="0" SRC="http://squid:3128/squid-internal-static/icons/anthony-unknown.gif" ALT="[FILE]"></A> <A HREF="gnome-gpg-0.5.0.md5sum">gnome-gpg-0.5.0.md5sum</A> . . . . . Sep 02 06:58    115  <A HREF="gnome-gpg-0.5.0.md5sum;type=a"><IMG border="0" SRC="http://squid:3128/squid-internal-static/icons/anthony-text.gif" ALT="[VIEW]"></A> <A HREF="gnome-gpg-0.5.0.md5sum;type=i"><IMG border="0" SRC="http://squid:3128/squid-internal-static/icons/anthony-box.gif" ALT="[DOWNLOAD]"></A>
<A HREF="gnome-gpg-0.5.0.tar.bz2"><IMG border="0" SRC="http://squid:3128/squid-internal-static/icons/anthony-compressed.gif" ALT="[FILE]"></A> <A HREF="gnome-gpg-0.5.0.tar.bz2">gnome-gpg-0.5.0.tar.bz2</A>. . . . . Sep 02 06:58     68K <A HREF="gnome-gpg-0.5.0.tar.bz2;type=i"><IMG border="0" SRC="http://squid:3128/squid-internal-static/icons/anthony-box.gif" ALT="[DOWNLOAD]"></A>
<A HREF="gnome-gpg-0.5.0.tar.gz"><IMG border="0" SRC="http://squid:3128/squid-internal-static/icons/anthony-tar.gif" ALT="[FILE]"></A> <A HREF="gnome-gpg-0.5.0.tar.gz">gnome-gpg-0.5.0.tar.gz</A> . . . . . Sep 02 06:58     81K <A HREF="gnome-gpg-0.5.0.tar.gz;type=i"><IMG border="0" SRC="http://squid:3128/squid-internal-static/icons/anthony-box.gif" ALT="[DOWNLOAD]"></A>
</PRE>
<HR noshade size="1px">
<ADDRESS>
Generated Wed, 06 Sep 2006 11:04:02 GMT by squid (squid/2.5.STABLE12)
</ADDRESS></BODY></HTML>
        '''
        walker = self.setUpWalker(
            'ftp://ftp.gnome.org/pub/GNOME/sources/gnome-gpg/0.5/', content)
        dirnames, filenames = walker.list('/pub/GNOME/sources/gnome-gpg/0.5/')
        self.assertEqual(dirnames, [])
        self.assertEqual(filenames, ['LATEST-IS-0.5.0',
                                     'gnome-gpg-0.5.0.md5sum',
                                     'gnome-gpg-0.5.0.tar.bz2',
                                     'gnome-gpg-0.5.0.tar.gz'])

    def testNonAsciiListing(self):
        # Test that list() handles non-ASCII output.
        content = '''
        <html>
          <head>
            <title>Listing</title>
            <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
          </head>
          <body>
          <p>A non-breaking space: \xc2\xa0</p>
          <p><a href="/elsewhere">Somewhere else on the site</a></p>
          <!-- intentionally unclosed anchor below -->
          <p><a href="/foo/file99">Absolute path</p>

          <pre>
          <a href="../">Parent directory</a>
          <a href="subdir1/">subdir 1</a>
          <a href="subdir2/">subdir 2</a>
          <a href="subdir3/">subdir 3</a>
          <a href="file3">file 3</a>
          <a href="file2">file 2</a>
          <a href="file1">file 1</a>
          </pre>
        </html>
        '''
        walker = self.setUpWalker('http://example.com/foo/', content)
        dirnames, filenames = walker.list('/foo/')
        self.assertEqual(dirnames, ['subdir1/', 'subdir2/', 'subdir3/'])
        self.assertEqual(filenames, ['file1', 'file2', 'file3', 'file99'])

    def testDotPaths(self):
        # Test that paths containing dots are handled correctly.
        #
        # We expect the returned directory and file names to only
        # include those links http://example.com/foo/ even in the
        # presence of "." and ".." path segments.
        content = '''
        <html>
          <head>
            <title>Listing</title>
            <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
          </head>
          <body>
          <pre>
          <a href="../">Up a level</a>
          <a href="/foo/../">The same again</a>
          <a href="file1/../file2">file2</a>
          <a href=".">This directory</a>
          <a href="dir/.">A subdirectory</a>
          </pre>
        </html>
        '''
        walker = self.setUpWalker('http://example.com/foo/', content)
        dirnames, filenames = walker.list('/foo/')
        self.assertEqual(dirnames, ['dir/'])
        self.assertEqual(filenames, ['file2'])

    def testNamedAnchors(self):
        # Test that the directory listing parser code handles named anchors.
        # These are <a> tags without an href attribute.
        content = '''
        <html>
          <head>
            <title>Listing</title>
          </head>
          <body>
          <a name="top"></a>
          <pre>
          <a href="file1">file1</a>
          <a href="dir1/">dir1/</a>
          <a href="#top">Go to top</a>
          </pre>
        </html>
        '''
        walker = self.setUpWalker('http://example.com/foo/', content)
        dirnames, filenames = walker.list('/foo/')
        self.assertEqual(dirnames, ['dir1/'])
        self.assertEqual(filenames, ['file1'])

    def testGarbageListing(self):
        # Make sure that garbage doesn't trip up the dir lister.
        content = '\x01\x02\x03\x00\xff\xf2\xablkjsdflkjsfkljfds'
        walker = self.setUpWalker('http://example.com/foo/', content)
        dirnames, filenames = walker.list('/foo/')
        self.assertEqual(dirnames, [])
        self.assertEqual(filenames, [])


class HTTPWalker_IsDirectory(TestCase):

    def tearDown(self):
        reset_logging()
        super(HTTPWalker_IsDirectory, self).tearDown()

    def testFtpIsDirectory(self):
        # Test that no requests are made by isDirectory() when walking
        # FTP sites.
        from lp.registry.scripts.productreleasefinder.walker import (
            HTTPWalker)
        test = self

        class TestHTTPWalker(HTTPWalker):

            def request(self, method, path):
                test.fail('%s was requested with method %s' % (path, method))

        logging.basicConfig(level=logging.CRITICAL)
        walker = TestHTTPWalker('ftp://ftp.gnome.org/', logging.getLogger())

        self.assertEqual(walker.isDirectory('/foo/'), True)
        self.assertEqual(walker.isDirectory('/foo'), False)


class Walker_CombineUrl(TestCase):

    def testConstructsUrl(self):
        """combine_url constructs the URL correctly."""
        from lp.registry.scripts.productreleasefinder.walker import (
            combine_url)
        self.assertEquals(combine_url("file:///base", "/subdir/", "file"),
                          "file:///subdir/file")
        self.assertEquals(combine_url("file:///base", "/subdir", "file"),
                          "file:///subdir/file")
