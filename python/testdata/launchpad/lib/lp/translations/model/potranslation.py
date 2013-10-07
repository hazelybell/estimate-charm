# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = ['POTranslation']

from sqlobject import (
    SQLObjectNotFound,
    StringCol,
    )
from zope.interface import implements

from lp.services.database.sqlbase import (
    quote,
    SQLBase,
    )
from lp.translations.interfaces.potranslation import IPOTranslation


class POTranslation(SQLBase):
    implements(IPOTranslation)

    _table = 'POTranslation'

    # alternateID=False because we have to select by hash in order to do
    # index lookups.
    translation = StringCol(dbName='translation', notNull=True, unique=True,
        alternateID=False)

    def byTranslation(cls, key):
        """Return a POTranslation object for the given translation."""

        # We can't search directly on msgid, because this database column
        # contains values too large to index. Instead we search on its
        # hash, which *is* indexed
        r = cls.selectOne('sha1(translation) = sha1(%s)' % quote(key))

        if r is not None:
            return r
        else:
            # To be 100% compatible with the alternateID behaviour, we should
            # raise SQLObjectNotFound instead of KeyError
            raise SQLObjectNotFound(key)

    byTranslation = classmethod(byTranslation)

    def getOrCreateTranslation(cls, key):
        """Return a POTranslation object for the given translation, or create
        it if it doesn't exist.
        """
        if isinstance(key, str):
            # If this is not a unicode object, it had better be ASCII or
            # UTF-8.
            # XXX: JeroenVermeulen 2008-06-06 bug=237868: non-ascii str
            # strings should be contained in the parser or the browser
            # code.
            key = key.decode('UTF-8')

        try:
            return cls.byTranslation(key)
        except SQLObjectNotFound:
            return cls(translation=key)

    getOrCreateTranslation = classmethod(getOrCreateTranslation)

