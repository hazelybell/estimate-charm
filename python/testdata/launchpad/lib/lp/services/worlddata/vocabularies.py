# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__all__ = [
    'CountryNameVocabulary',
    'LanguageVocabulary',
    'TimezoneNameVocabulary',
    ]

__metaclass__ = type

import pytz
from sqlobject import SQLObjectNotFound
from zope.interface import alsoProvides
from zope.schema.vocabulary import (
    SimpleTerm,
    SimpleVocabulary,
    )

from lp.services.webapp.vocabulary import SQLObjectVocabularyBase
from lp.services.worlddata.interfaces.language import ILanguage
from lp.services.worlddata.interfaces.timezone import ITimezoneNameVocabulary
from lp.services.worlddata.model.country import Country
from lp.services.worlddata.model.language import Language

# create a sorted list of the common time zone names, with UTC at the start
_values = sorted(pytz.common_timezones)
_values.remove('UTC')
_values.insert(0, 'UTC')

_timezone_vocab = SimpleVocabulary.fromValues(_values)
alsoProvides(_timezone_vocab, ITimezoneNameVocabulary)
del _values


def TimezoneNameVocabulary(context=None):
    return _timezone_vocab


# Country.name may have non-ASCII characters, so we can't use
# NamedSQLObjectVocabulary here.

class CountryNameVocabulary(SQLObjectVocabularyBase):
    """A vocabulary for country names."""

    _table = Country
    _orderBy = 'name'

    def toTerm(self, obj):
        return SimpleTerm(obj, obj.id, obj.name)


class LanguageVocabulary(SQLObjectVocabularyBase):
    """All the languages known by Launchpad."""

    _table = Language
    _orderBy = 'englishname'

    def __contains__(self, language):
        """See `IVocabulary`."""
        assert ILanguage.providedBy(language), (
            "'in LanguageVocabulary' requires ILanguage as left operand, "
            "got %s instead." % type(language))
        return super(LanguageVocabulary, self).__contains__(language)

    def toTerm(self, obj):
        """See `IVocabulary`."""
        return SimpleTerm(obj, obj.code, obj.displayname)

    def getTerm(self, obj):
        """See `IVocabulary`."""
        if obj not in self:
            raise LookupError(obj)
        return SimpleTerm(obj, obj.code, obj.displayname)

    def getTermByToken(self, token):
        """See `IVocabulary`."""
        try:
            found_language = Language.byCode(token)
        except SQLObjectNotFound:
            raise LookupError(token)
        return self.getTerm(found_language)
