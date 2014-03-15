# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""HTTP and FTP walker.

This module implements classes to walk HTTP and FTP sites to find files.
"""

__metaclass__ = type
__all__ = [
    'walk',
    'combine_url',
    ]

import ftplib
import os
import socket
from urllib import unquote_plus
import urllib2
from urlparse import (
    urljoin,
    urlsplit,
    )

from BeautifulSoup import BeautifulSoup
from cscvs.dircompare.path import (
    as_dir,
    subdir,
    )
from lazr.uri import (
    InvalidURIError,
    URI,
    )

from lp.registry.scripts.productreleasefinder import log
from lp.services.webapp.url import urlappend


class WalkerError(Exception):
    """An error in the base walker."""
    pass


class FTPWalkerError(WalkerError):
    """An error in the ftp walker."""
    pass


class HTTPWalkerError(WalkerError):
    """An error in the http walker."""
    pass


class Request(urllib2.Request):
    """A urllib2 Request object that can override the request method."""

    method = None

    def get_method(self):
        """See `urllib2.Request`."""
        if self.method is not None:
            return self.method
        else:
            return urllib2.Request.get_method(self)


class WalkerBase:
    """Base class for URL walkers.

    This class is a base class for those wishing to implement protocol
    specific walkers.  Walkers behave much like the os.walk() function,
    but taking a URL and working remotely.

    A typical usage would be:
        for (dirpath, dirnames, filenames) in ProtWalker(url):
            ...

    Sub-classes are required to implement the open(), list() and close()
    methods.
    """

    # URL schemes the walker supports, the first is the default
    URL_SCHEMES = ["ftp", "http", "https"]

    # Whether to ignore or parse fragments in the URL
    FRAGMENTS = False

    def __init__(self, base, log_parent=None):
        self.log = log.get_logger(type(self).__name__, log_parent)
        self.base = base

        (scheme, netloc, path, query, fragment) \
                 = urlsplit(base, self.URL_SCHEMES[0], self.FRAGMENTS)
        if scheme not in self.URL_SCHEMES:
            raise WalkerError("Can't handle %s scheme" % scheme)
        self.scheme = scheme
        self.full_netloc = netloc

        try:
            (user_passwd, host) = netloc.split("@", 1)
            self.host = unquote_plus(host)

            try:
                (user, passwd) = user_passwd.split(":", 1)
                self.user = unquote_plus(user)
                self.passwd = unquote_plus(passwd)
            except ValueError:
                self.user = unquote_plus(user_passwd)
                self.passwd = None
        except ValueError:
            self.host = unquote_plus(netloc)
            self.user = None
            self.passwd = None

        self.query = query
        self.fragment = fragment

        self.path = as_dir(path)

    def walk(self):
        """Walk through the URL.

        Yields (dirpath, dirnames, filenames) for each path under the base;
        dirnames can be modified as with os.walk.
        """
        try:
            self.open()
        except (IOError, socket.error) as e:
            self.log.info("Could not connect to %s" % self.base)
            self.log.info("Failure: %s" % e)
            return

        subdirs = [self.path]
        while len(subdirs):
            sub_dir = subdirs.pop(0)

            try:
                (dirnames, filenames) = self.list(sub_dir)
            except WalkerError:
                self.log.info('could not retrieve directory '
                                   'listing for %s', sub_dir)
                continue
            except UnicodeEncodeError:
                # This page is unparsable.
                # XXX sinzui 2009-06-22 bug=70524:
                # This problem should be reported to the project drivers
                # so that they can attempt to get this fixed.
                self.log.info(
                    "Unicode error parsing %s page '%s'" %
                    (self.base, sub_dir))
                continue
            yield (sub_dir, dirnames, filenames)

            for dirname in dirnames:
                subdirs.append(urljoin(sub_dir, as_dir(dirname)))

        self.close()

    __iter__ = walk

    def open(self):
        """Open the FTP connection.

        Must be implemented by sub-classes.
        """
        raise NotImplementedError

    def close(self):
        """Close the FTP connection.

        Must be implemented by sub-classes.
        """
        raise NotImplementedError

    def list(self, dir):
        """Return listing of directory.

        Must be implemented by sub-classes to return two lists, one of
        directory names and one of file names; both underneath the directory
        given.
        """
        raise NotImplementedError


class FTPWalker(WalkerBase):
    """FTP URL scheme walker.

    This class implements a walker for the FTP URL scheme; it's fairly
    simple and just walks the FTP tree beneath the URL given using CWD
    and LIST.
    """

    # URL schemes the walker supports, the first is the default
    URL_SCHEMES = ["ftp"]

    # Whether to ignore or parse fragments in the URL
    FRAGMENTS = False

    def __init__(self, *args, **kwds):
        super(FTPWalker, self).__init__(*args, **kwds)

        if self.user is None:
            self.user = "anonymous"
        if self.passwd is None:
            self.passwd = ""

    def open(self):
        """Open the FTP connection."""
        self.log.info("Connecting to %s", self.host)
        self.ftp = ftplib.FTP()
        self.ftp.connect(self.host)

        if self.user is not None:
            self.log.info("Logging in as %s", self.user)
            self.ftp.login(self.user, self.passwd)

        pwd = self.ftp.pwd()
        self.log.info("Connected, working directory is %s", pwd)

    def close(self):
        """Close the FTP connection."""
        self.log.info("Closing connection")
        self.ftp.quit()
        del self.ftp

    def list(self, subdir):
        """Change directory and return listing.

        Returns two lists, one of directory names and one of file names
        under the path.
        """
        self.log.info("Changing directory to %s", subdir)
        self.ftp.cwd(subdir)

        listing = []
        self.log.info("Listing remote directory")
        self.ftp.retrlines("LIST", listing.append)

        dirnames = []
        filenames = []
        for line in listing:
            # XXX keybuk 2005-06-24: Assume UNIX listings for now.
            words = line.split(None, 8)
            if len(words) < 6:
                self.log.debug("Ignoring short line: %s", line)
                continue

            # Chomp symlinks
            filename = words[-1].lstrip()
            i = filename.find(" -> ")
            if i >= 0:
                filename = filename[:i]

            mode = words[0]
            if mode.startswith("d"):
                if filename not in (".", ".."):
                    dirnames.append(filename)
            elif mode.startswith("-") or mode.startswith("l"):
                filenames.append(filename)

        return (dirnames, filenames)


class HTTPWalker(WalkerBase):
    """HTTP URL scheme walker.

    This class implements a walker for the HTTP and HTTPS URL schemes.
    It works by assuming any URL ending with a / is a directory, and
    every other URL a file.  URLs are tested using HEAD to see whether
    they cause a redirect to one ending with a /.

    HTML Directory pages are parsed to find all links within them that
    lead to deeper URLs; this way it isn't tied to the Apache directory
    listing format and can actually walk arbitrary trees.
    """

    # URL schemes the walker supports, the first is the default.  We
    # list FTP because this walker is used when doing FTP through a
    # proxy.
    URL_SCHEMES = ("http", "https", "ftp")

    # Whether to ignore or parse fragments in the URL
    FRAGMENTS = True

    # All the urls handlers used to support the schemas. Redirects are not
    # supported.
    handlers = (
        urllib2.ProxyHandler,
        urllib2.UnknownHandler,
        urllib2.HTTPHandler,
        urllib2.HTTPDefaultErrorHandler,
        urllib2.HTTPSHandler,
        urllib2.HTTPDefaultErrorHandler,
        urllib2.FTPHandler,
        urllib2.FileHandler,
        urllib2.HTTPErrorProcessor)

    _opener = None

    def open(self):
        """Open the HTTP connection."""
        self.log.info('Walking %s://%s', self.scheme, self.host)

    def close(self):
        """Close the HTTP connection."""
        pass

    def request(self, method, path):
        """Make an HTTP request.

        Returns the HTTPResponse object.
        """
        # We build a custom opener, because we don't want redirects to be
        # followed.
        if self._opener is None:
            self._opener = urllib2.OpenerDirector()
            for handler in self.handlers:
                self._opener.add_handler(handler())

        self.log.debug("Requesting %s with method %s", path, method)
        request = Request(urljoin(self.base, path))
        request.method = method
        return self._opener.open(request)

    def isDirectory(self, path):
        """Return whether the path is a directory.

        Assumes any path ending in a slash is a directory, and any that
        redirects to a location ending in a slash is also a directory.
        """
        if path.endswith("/"):
            return True

        # If the URI scheme is FTP, then the URI comes from a Squid
        # FTP listing page, which includes the trailing slash on all
        # URIs that need it.
        if self.scheme == 'ftp':
            return False

        self.log.debug("Checking if %s is a directory" % path)
        try:
            self.request("HEAD", path)
            return False
        except urllib2.HTTPError as exc:
            if exc.code != 301:
                return False
        except (IOError, socket.error) as exc:
            # Raise HTTPWalkerError for other IO or socket errors.
            raise HTTPWalkerError(str(exc))

        # We have a 301 redirect error from here on.
        url = exc.hdrs.getheader("location")
        (scheme, netloc, redirect_path, query, fragment) \
                 = urlsplit(url, self.scheme, self.FRAGMENTS)

        if len(scheme) and scheme != self.scheme:
            return False
        elif len(netloc) and netloc != self.full_netloc:
            return False
        elif redirect_path != as_dir(path):
            return False
        else:
            return True

    def list(self, dirname):
        """Download the HTML index at subdir and scrape for URLs.

        Returns a list of directory names (links ending with /, or
        that result in redirects to themselves ending in /) and
        filenames (everything else) that reside underneath the path.
        """
        self.log.info("Listing %s" % dirname)
        try:
            response = self.request("GET", dirname)
            try:
                soup = BeautifulSoup(response.read())
            finally:
                response.close()
        except (IOError, socket.error) as exc:
            raise HTTPWalkerError(str(exc))

        base = URI(self.base).resolve(dirname)

        # Collect set of URLs that are below the base URL
        urls = set()
        for anchor in soup("a"):
            href = anchor.get("href")
            if href is None:
                continue
            try:
                url = base.resolve(href)
            except InvalidURIError:
                continue
            # Only add the URL if it is strictly inside the base URL.
            if base.contains(url) and not url.contains(base):
                urls.add(url)

        dirnames = set()
        filenames = set()
        for url in urls:
            if url.path.endswith(';type=a') or url.path.endswith(';type=i'):
                # these links come from Squid's FTP dir listing to
                # force either ASCII or binary download and can be
                # ignored.
                continue

            filename = subdir(base.path, url.path)
            if self.isDirectory(url.path):
                dirnames.add(as_dir(filename))
            else:
                filenames.add(filename)

        return (sorted(dirnames), sorted(filenames))


def walk(url, log_parent=None):
    """Return a walker for the URL given."""
    (scheme, netloc, path, query, fragment) = urlsplit(url, "file")
    if scheme in ["ftp"]:
        # If ftp_proxy is set, use the HTTPWalker class since we are
        # talking to an HTTP proxy.
        if 'ftp_proxy' in os.environ:
            return HTTPWalker(url, log_parent)
        else:
            return FTPWalker(url, log_parent)
    elif scheme in ["http", "https"]:
        return HTTPWalker(url, log_parent)
    elif scheme in ["file"]:
        return os.walk(path)
    else:
        raise WalkerError("Unknown scheme: %s" % scheme)


def combine_url(base, subdir, filename):
    """Combine a URL from the three parts returned by walk()."""
    subdir_url = urljoin(base, subdir)
    # The "filename" component must be appended to the resulting URL.
    return urlappend(subdir_url, filename)
