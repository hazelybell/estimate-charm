# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'POFileTranslator',
    'POFileTranslatorSet',
    ]


from sqlobject import ForeignKey
from storm.expr import And
from storm.store import Store
from zope.interface import implements

from lp.registry.interfaces.person import validate_public_person
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.sqlbase import (
    SQLBase,
    sqlvalues,
    )
from lp.translations.interfaces.pofiletranslator import (
    IPOFileTranslator,
    IPOFileTranslatorSet,
    )
from lp.translations.model.pofile import POFile


class POFileTranslator(SQLBase):
    """See `IPOFileTranslator`."""

    implements(IPOFileTranslator)
    pofile = ForeignKey(foreignKey='POFile', dbName='pofile', notNull=True)
    person = ForeignKey(
        dbName='person', foreignKey='Person',
        storm_validator=validate_public_person, notNull=True)
    date_last_touched = UtcDateTimeCol(
        dbName='date_last_touched', notNull=False, default=None)


class POFileTranslatorSet:
    """The set of all `POFileTranslator` records."""

    implements(IPOFileTranslatorSet)

    def prefetchPOFileTranslatorRelations(self, pofiletranslators):
        """See `IPOFileTranslatorSet`."""
        ids = set(record.id for record in pofiletranslators)
        if not ids:
            return None

        # Listify prefetch query to force its execution here.
        return list(POFileTranslator.select(
            "POFileTranslator.id IN %s" % sqlvalues(ids),
            prejoins=[
                'pofile',
                'pofile.potemplate',
                'pofile.potemplate.productseries',
                'pofile.potemplate.productseries.product',
                'pofile.potemplate.distroseries',
                'pofile.potemplate.sourcepackagename',
                ]))

    def getForPersonPOFile(self, person, pofile):
        """See `IPOFileTranslatorSet`."""
        return Store.of(pofile).find(POFileTranslator, And(
            POFileTranslator.person == person.id,
            POFileTranslator.pofile == pofile.id)).one()

    def getForTemplate(self, potemplate):
        """See `IPOFileTranslatorSet`."""
        return Store.of(potemplate).find(
            POFileTranslator,
            POFileTranslator.pofileID == POFile.id,
            POFile.potemplateID == potemplate.id)
