# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Database class for table ArchiveAuthToken."""

__metaclass__ = type

__all__ = [
    'ArchiveAuthToken',
    ]

from lazr.uri import URI
import pytz
from storm.locals import (
    DateTime,
    Int,
    Reference,
    Storm,
    Unicode,
    )
from storm.store import Store
from zope.interface import implements

from lp.services.database.constants import UTC_NOW
from lp.services.database.interfaces import IStore
from lp.soyuz.interfaces.archiveauthtoken import (
    IArchiveAuthToken,
    IArchiveAuthTokenSet,
    )


class ArchiveAuthToken(Storm):
    """See `IArchiveAuthToken`."""
    implements(IArchiveAuthToken)
    __storm_table__ = 'ArchiveAuthToken'

    id = Int(primary=True)

    archive_id = Int(name='archive', allow_none=False)
    archive = Reference(archive_id, 'Archive.id')

    person_id = Int(name='person', allow_none=False)
    person = Reference(person_id, 'Person.id')

    date_created = DateTime(
        name='date_created', allow_none=False, tzinfo=pytz.UTC)

    date_deactivated = DateTime(
        name='date_deactivated', allow_none=True, tzinfo=pytz.UTC)

    token = Unicode(name='token', allow_none=False)

    def deactivate(self):
        """See `IArchiveAuthTokenSet`."""
        self.date_deactivated = UTC_NOW

    @property
    def archive_url(self):
        """Return a custom archive url for basic authentication."""
        normal_url = URI(self.archive.archive_url)
        auth_url = normal_url.replace(
            userinfo="%s:%s" %(self.person.name, self.token))
        return str(auth_url)


class ArchiveAuthTokenSet:
    """See `IArchiveAuthTokenSet`."""
    implements(IArchiveAuthTokenSet)
    title = "Archive Tokens in Launchpad"

    def get(self, token_id):
        """See `IArchiveAuthTokenSet`."""
        return IStore(ArchiveAuthToken).get(ArchiveAuthToken, token_id)

    def getByToken(self, token):
        """See `IArchiveAuthTokenSet`."""
        return IStore(ArchiveAuthToken).find(
            ArchiveAuthToken, ArchiveAuthToken.token == token).one()

    def getByArchive(self, archive):
        """See `IArchiveAuthTokenSet`."""
        store = Store.of(archive)
        return store.find(
            ArchiveAuthToken,
            ArchiveAuthToken.archive == archive,
            ArchiveAuthToken.date_deactivated == None)

    def getActiveTokenForArchiveAndPerson(self, archive, person):
        """See `IArchiveAuthTokenSet`."""
        store = Store.of(archive)
        return store.find(
            ArchiveAuthToken,
            ArchiveAuthToken.archive == archive,
            ArchiveAuthToken.person == person,
            ArchiveAuthToken.date_deactivated == None).one()
