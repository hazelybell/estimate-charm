# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'TranslationTemplateItem',
    ]

from sqlobject import (
    ForeignKey,
    IntCol,
    )
from zope.interface import implements

from lp.services.database.sqlbase import SQLBase
from lp.translations.interfaces.translationtemplateitem import (
    ITranslationTemplateItem,
    )


class TranslationTemplateItem(SQLBase):
    """See `ITranslationTemplateItem`."""
    implements(ITranslationTemplateItem)

    _table = 'TranslationTemplateItem'

    potemplate = ForeignKey(
        foreignKey='POTemplate', dbName='potemplate', notNull=True)
    sequence = IntCol(dbName='sequence', notNull=True)
    potmsgset = ForeignKey(
        foreignKey='POTMsgSet', dbName='potmsgset', notNull=True)
