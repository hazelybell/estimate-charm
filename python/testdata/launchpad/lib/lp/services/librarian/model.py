# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'LibraryFileAlias',
    'LibraryFileAliasWithParent',
    'LibraryFileAliasSet',
    'LibraryFileContent',
    'LibraryFileDownloadCount',
    'TimeLimitedToken',
    ]

from datetime import datetime
from hashlib import md5
import random
from urlparse import urlparse

from lazr.delegates import delegates
import pytz
from sqlobject import (
    BoolCol,
    ForeignKey,
    IntCol,
    SQLRelatedJoin,
    StringCol,
    )
from storm.exceptions import IntegrityError
from storm.locals import (
    Date,
    Desc,
    Int,
    Reference,
    Store,
    )
from zope.component import (
    adapts,
    getUtility,
    )
from zope.interface import (
    implements,
    Interface,
    )

from lp.registry.errors import InvalidFilename
from lp.services.config import config
from lp.services.database.constants import (
    DEFAULT,
    UTC_NOW,
    )
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.interfaces import IMasterStore
from lp.services.database.sqlbase import (
    session_store,
    SQLBase,
    )
from lp.services.database.stormbase import StormBase
from lp.services.librarian.interfaces import (
    ILibraryFileAlias,
    ILibraryFileAliasSet,
    ILibraryFileAliasWithParent,
    ILibraryFileContent,
    ILibraryFileDownloadCount,
    )
from lp.services.librarian.interfaces.client import (
    DownloadFailed,
    ILibrarianClient,
    IRestrictedLibrarianClient,
    LIBRARIAN_SERVER_DEFAULT_TIMEOUT,
    )


class LibraryFileContent(SQLBase):
    """A pointer to file content in the librarian."""

    implements(ILibraryFileContent)

    _table = 'LibraryFileContent'

    datecreated = UtcDateTimeCol(notNull=True, default=UTC_NOW)
    filesize = IntCol(notNull=True)
    sha256 = StringCol()
    sha1 = StringCol(notNull=True)
    md5 = StringCol(notNull=True)


class LibraryFileAlias(SQLBase):
    """A filename and mimetype that we can serve some given content with."""

    implements(ILibraryFileAlias)

    _table = 'LibraryFileAlias'
    date_created = UtcDateTimeCol(notNull=False, default=DEFAULT)
    content = ForeignKey(
        foreignKey='LibraryFileContent', dbName='content', notNull=False,
        )
    filename = StringCol(notNull=True)
    mimetype = StringCol(notNull=True)
    expires = UtcDateTimeCol(notNull=False, default=None)
    restricted = BoolCol(notNull=True, default=False)
    hits = IntCol(notNull=True, default=0)

    products = SQLRelatedJoin('ProductRelease', joinColumn='libraryfile',
                           otherColumn='productrelease',
                           intermediateTable='ProductReleaseFile')

    sourcepackages = SQLRelatedJoin('SourcePackageRelease',
                                 joinColumn='libraryfile',
                                 otherColumn='sourcepackagerelease',
                                 intermediateTable='SourcePackageReleaseFile')

    @property
    def client(self):
        """Return the librarian client to use to retrieve that file."""
        if self.restricted:
            return getUtility(IRestrictedLibrarianClient)
        else:
            return getUtility(ILibrarianClient)

    @property
    def http_url(self):
        """See ILibraryFileAlias.http_url"""
        return self.client.getURLForAliasObject(self)

    @property
    def https_url(self):
        """See ILibraryFileAlias.https_url"""
        url = self.http_url
        if url is None:
            return url
        return url.replace('http', 'https', 1)

    @property
    def private_url(self):
        """See ILibraryFileAlias.https_url"""
        return self.client.getURLForAlias(self.id, secure=True)

    def getURL(self, secure=True, include_token=False):
        """See ILibraryFileAlias.getURL"""
        if not self.restricted:
            if config.librarian.use_https and secure:
                return self.https_url
            else:
                return self.http_url
        else:
            url = self.private_url
            if include_token:
                token = TimeLimitedToken.allocate(url)
                url += '?token=%s' % token
            return url

    _datafile = None

    def open(self, timeout=LIBRARIAN_SERVER_DEFAULT_TIMEOUT):
        """See ILibraryFileAlias."""
        self._datafile = self.client.getFileByAlias(self.id, timeout)
        if self._datafile is None:
            raise DownloadFailed(
                "Unable to retrieve LibraryFileAlias %d" % self.id)

    def read(self, chunksize=None, timeout=LIBRARIAN_SERVER_DEFAULT_TIMEOUT):
        """See ILibraryFileAlias."""
        if not self._datafile:
            if chunksize is not None:
                raise RuntimeError("Can't combine autoopen with chunksize")
            self.open(timeout=timeout)
            autoopen = True
        else:
            autoopen = False

        if chunksize is None:
            rv = self._datafile.read()
            if autoopen:
                self.close()
            return rv
        else:
            return self._datafile.read(chunksize)

    def close(self):
        # Don't die with an AttributeError if the '_datafile' property
        # is not set.
        if self._datafile is not None:
            self._datafile.close()
            self._datafile = None

    @property
    def last_downloaded(self):
        """See `ILibraryFileAlias`."""
        store = Store.of(self)
        results = store.find(LibraryFileDownloadCount, libraryfilealias=self)
        results.order_by(Desc(LibraryFileDownloadCount.day))
        entry = results.first()
        if entry is None:
            return None
        else:
            return datetime.now(pytz.utc).date() - entry.day

    def updateDownloadCount(self, day, country, count):
        """See ILibraryFileAlias."""
        store = Store.of(self)
        entry = store.find(
            LibraryFileDownloadCount, libraryfilealias=self,
            day=day, country=country).one()
        if entry is None:
            entry = LibraryFileDownloadCount(
                libraryfilealias=self, day=day, country=country, count=count)
        else:
            entry.count += count
        self.hits += count

    products = SQLRelatedJoin('ProductRelease', joinColumn='libraryfile',
                           otherColumn='productrelease',
                           intermediateTable='ProductReleaseFile')

    sourcepackages = SQLRelatedJoin('SourcePackageRelease',
                                 joinColumn='libraryfile',
                                 otherColumn='sourcepackagerelease',
                                 intermediateTable='SourcePackageReleaseFile')

    @property
    def deleted(self):
        return self.contentID is None

    def __storm_invalidated__(self):
        """Make sure that the file is closed across transaction boundary."""
        super(LibraryFileAlias, self).__storm_invalidated__()
        self.close()


class LibraryFileAliasWithParent:
    """A LibraryFileAlias variant that has a parent."""

    adapts(ILibraryFileAlias, Interface)
    implements(ILibraryFileAliasWithParent)
    delegates(ILibraryFileAlias)

    def __init__(self, libraryfile, parent):
        self.context = libraryfile
        self.__parent__ = parent

    def createToken(self):
        """See `ILibraryFileAliasWithParent`."""
        return TimeLimitedToken.allocate(self.private_url)


class LibraryFileAliasSet(object):
    """Create and find LibraryFileAliases."""

    implements(ILibraryFileAliasSet)

    def create(self, name, size, file, contentType, expires=None,
               debugID=None, restricted=False):
        """See `ILibraryFileAliasSet`"""
        if restricted:
            client = getUtility(IRestrictedLibrarianClient)
        else:
            client = getUtility(ILibrarianClient)
        try:
            fid = client.addFile(
                name, size, file, contentType, expires, debugID)
        except IntegrityError:
            raise InvalidFilename("Filename cannot contain slashes.")
        lfa = IMasterStore(LibraryFileAlias).find(
            LibraryFileAlias, LibraryFileAlias.id == fid).one()
        assert lfa is not None, "client.addFile didn't!"
        return lfa

    def __getitem__(self, key):
        """See ILibraryFileAliasSet.__getitem__"""
        return LibraryFileAlias.get(key)

    def findBySHA1(self, sha1):
        """See ILibraryFileAliasSet."""
        return LibraryFileAlias.select("""
            content = LibraryFileContent.id
            AND LibraryFileContent.sha1 = '%s'
            """ % sha1, clauseTables=['LibraryFileContent'])


class LibraryFileDownloadCount(SQLBase):
    """See `ILibraryFileDownloadCount`"""

    implements(ILibraryFileDownloadCount)
    __storm_table__ = 'LibraryFileDownloadCount'

    id = Int(primary=True)
    libraryfilealias_id = Int(name='libraryfilealias', allow_none=False)
    libraryfilealias = Reference(libraryfilealias_id, 'LibraryFileAlias.id')
    day = Date(allow_none=False)
    count = Int(allow_none=False)
    country_id = Int(name='country', allow_none=True)
    country = Reference(country_id, 'Country.id')


class TimeLimitedToken(StormBase):
    """A time limited access token for accessing a private file."""

    __storm_table__ = 'TimeLimitedToken'

    created = UtcDateTimeCol(notNull=True, default=UTC_NOW)
    path = StringCol(notNull=True)
    token = StringCol(notNull=True)
    __storm_primary__ = ("path", "token")

    def __init__(self, path, token, created=None):
        """Create a TimeLimitedToken."""
        if created is not None:
            self.created = created
        self.path = path
        self.token = token

    @staticmethod
    def allocate(url):
        """Allocate a token for url path in the librarian.

        :param url: A url bytestring. e.g.
            https://i123.restricted.launchpad-librarian.net/123/foo.txt
            Note that the token is generated for 123/foo.txt
        :return: A url fragment token ready to be attached to the url.
            e.g. 'a%20token'
        """
        # We use random.random to get a string which varies reasonably, and we
        # hash it to distribute it widely and get a easily copy and pastable
        # single string (nice for debugging). The randomness is not a key
        # factor here: as long as tokens are not guessable, they are hidden by
        # https, not exposed directly in the API (tokens will be allocated by
        # the appropriate objects), not by direct access to the
        # TimeLimitedToken class.
        baseline = str(random.random())
        hashed = md5(baseline).hexdigest()
        token = hashed
        store = session_store()
        path = TimeLimitedToken.url_to_token_path(url)
        store.add(TimeLimitedToken(path, token))
        # The session isn't part of the main transaction model, and in fact it
        # has autocommit on. The commit here is belts and bracers: after
        # allocation the external librarian must be able to serve the file
        # immediately.
        store.commit()
        return token

    @staticmethod
    def url_to_token_path(url):
        """Return the token path used for authorising access to url."""
        return urlparse(url)[2]
