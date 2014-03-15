# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'TranslationRelicensingAgreement',
    ]

from sqlobject import (
    BoolCol,
    ForeignKey,
    )
from zope.interface import implements

from lp.registry.interfaces.person import validate_public_person
from lp.services.database.constants import UTC_NOW
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.sqlbase import SQLBase
from lp.translations.interfaces.translationrelicensingagreement import (
    ITranslationRelicensingAgreement,
    )


class TranslationRelicensingAgreement(SQLBase):
    implements(ITranslationRelicensingAgreement)

    _table = 'TranslationRelicensingAgreement'

    person = ForeignKey(
        foreignKey='Person', dbName='person', notNull=True,
        storm_validator=validate_public_person)

    allow_relicensing = BoolCol(
        dbName='allow_relicensing', notNull=True, default=True)

    date_decided = UtcDateTimeCol(
        dbName='date_decided', notNull=True, default=UTC_NOW)
