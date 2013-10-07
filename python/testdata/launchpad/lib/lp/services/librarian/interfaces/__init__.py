# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Librarian interfaces."""

__metaclass__ = type

__all__ = [
    'ILibraryFileAlias',
    'ILibraryFileAliasWithParent',
    'ILibraryFileAliasSet',
    'ILibraryFileContent',
    'ILibraryFileDownloadCount',
    'NEVER_EXPIRES',
    ]

from datetime import datetime

from lazr.restful.fields import Reference
from pytz import utc
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Bool,
    Choice,
    Date,
    Datetime,
    Int,
    TextLine,
    )

from lp import _
from lp.services.librarian.interfaces.client import (
    LIBRARIAN_SERVER_DEFAULT_TIMEOUT,
    )

# Set the expires attribute to this constant to flag a file that
# should never be removed from the Librarian.
NEVER_EXPIRES = datetime(2038, 1, 1, 0, 0, 0, tzinfo=utc)


class ILibraryFileAlias(Interface):
    id = Int(
            title=_('Library File Alias ID'), required=True, readonly=True,
            )

    date_created = Datetime(
        title=_('Date created'), required=True, readonly=True)
    content = Attribute('Library file content')
    filename = TextLine(
        title=_('Filename'), required=True, readonly=True)
    mimetype = TextLine(
        title=_('MIME type'), required=True, readonly=True)
    expires = Datetime(
        title=_('Expiry time'), required=False, readonly=True,
        description=_('''
            When file can be removed. Set to None if the file
            should only be removed when it is no longer referenced
            in the database. Set it to NEVER_EXPIRES to keep it in
            the Librarian permanently.
            '''))
    hits = Int(
        title=_('Number of times this file has been downloaded'),
        required=False, readonly=True)
    last_downloaded = Datetime(
        title=_('When this file was last downloaded'),
        required=False, readonly=True)
    restricted = Bool(
        title=_('Is this file alias restricted.'),
        required=True, readonly=True,
        description=_('If the file is restricted, it can only be '
                      'retrieved through the restricted librarian.'))
    deleted = Attribute('Is this file deleted.')

    # XXX Guilherme Salgado, 2007-01-18 bug=80487:
    # We can't use TextLine here because they return
    # byte strings.
    http_url = Attribute(_("The http URL to this file"))
    https_url = Attribute(_("The https URL to this file"))
    private_url = Attribute(_("The secure URL to this file (private files)"))

    def getURL(secure=True, include_token=False):
        """Return this file's http or https URL.

        If the file is a restricted file, the private_url will be returned,
        which is on https and uses unique domains per file alias.

        :param secure: generate HTTPS URLs if the use_https config variable
            is set, in order to prevent warnings about insecure objects
            from happening in some browsers (this is used for, e.g.,
            branding).
        :param include_token: create a time-limited token and include it in
            the URL to authorise access to restricted files.
        """

    def open(timeout=LIBRARIAN_SERVER_DEFAULT_TIMEOUT):
        """Open this file for reading.

        :param timeout: The number of seconds the method retries to open
            a connection to the Librarian server. If the connection
            cannot be established in the given time, a
            LibrarianServerError is raised.
        :return: None
        """

    def read(chunksize=None, timeout=LIBRARIAN_SERVER_DEFAULT_TIMEOUT):
        """Read up to `chunksize` bytes from the file.

        :param chunksize: The maximum number of bytes to be read.
            Defaults to the entire file.
        :param timeout: The number of seconds the method retries to open
            a connection to the Librarian server. If the connection
            cannot be established in the given time, a
            LibrarianServerError is raised.
        :return: the data read from the Librarian file.
        """

    def close():
        """Close this file."""

    def updateDownloadCount(day, country, count):
        """Update this file's download count for the given country and day.

        If there's no `ILibraryFileDownloadCount` entry for this file, and the
        given day/country, we create one with the given count.  Otherwise we
        just increase the count of the existing one by the given count.
        """


class ILibraryFileAliasWithParent(ILibraryFileAlias):
    """A ILibraryFileAlias that knows about its parent."""

    def createToken(self):
        """Create a token allowing time-limited access to this file."""


class ILibraryFileContent(Interface):
    """Actual data in the Librarian.

    This should not be used outside of the librarian internals.
    """
    id = Int(
            title=_('Library File Content ID'), required=True, readonly=True,
            )
    datecreated = Datetime(
        title=_('Date created'), required=True, readonly=True)
    filesize = Int(title=_('File size'), required=True, readonly=True)
    sha256 = TextLine(title=_('SHA-256 hash'), required=True, readonly=True)
    sha1 = TextLine(title=_('SHA-1 hash'), required=True, readonly=True)
    md5 = TextLine(title=_('MD5 hash'), required=True, readonly=True)


class ILibraryFileAliasSet(Interface):

    def create(name, size, file, contentType, expires=None, debugID=None,
               restricted=False):
        """Create a file in the Librarian, returning the new alias.

        An expiry time of None means the file will never expire until it
        is no longer referenced. An expiry of NEVER_EXPIRES means a
        file that will stay in the Librarian for ever. Setting it to another
        timestamp means that the file will expire and possibly be removed
        from the Librarian at this time. See LibrarianGarbageCollection.

        If restricted is True, the file will be created through the
        IRestrictedLibrarianClient utility.
        """

    def __getitem__(key):
        """Lookup an ILibraryFileAlias by id."""

    def findBySHA1(sha1):
        """Return all LibraryFileAlias whose content's sha1 match the given
        sha1.
        """


class ILibraryFileDownloadCount(Interface):
    """Download count of a given file in a given day."""

    libraryfilealias = Reference(
        title=_('The file'), schema=ILibraryFileAlias, required=True,
        readonly=True)
    day = Date(
        title=_('The day of the downloads'), required=True, readonly=True)
    count = Int(
        title=_('The number of downloads'), required=True, readonly=False)
    country = Choice(
        title=_('Country'), required=False, vocabulary='CountryName')
