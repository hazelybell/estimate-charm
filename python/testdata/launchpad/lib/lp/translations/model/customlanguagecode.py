# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Database class for `ICustomLanguageCode`."""

__metaclass__ = type

__all__ = [
    'CustomLanguageCode',
    'HasCustomLanguageCodesMixin',
    ]


from sqlobject import (
    ForeignKey,
    StringCol,
    )
from storm.expr import And
from zope.interface import implements

from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import SQLBase
from lp.translations.interfaces.customlanguagecode import ICustomLanguageCode


class CustomLanguageCode(SQLBase):
    """See `ICustomLanguageCode`."""

    implements(ICustomLanguageCode)

    _table = 'CustomLanguageCode'

    product = ForeignKey(
        dbName='product', foreignKey='Product', notNull=False, default=None)
    distribution = ForeignKey(
        dbName='distribution', foreignKey='Distribution', notNull=False,
        default=None)
    sourcepackagename = ForeignKey(
        dbName='sourcepackagename', foreignKey='SourcePackageName',
        notNull=False, default=None)
    language_code = StringCol(dbName='language_code', notNull=True)
    language = ForeignKey(
        dbName='language', foreignKey='Language', notNull=False, default=None)

    @property
    def translation_target(self):
        """See `ICustomLanguageCode`."""
        # Avoid circular imports
        from lp.registry.model.distributionsourcepackage import (
            DistributionSourcePackage)
        if self.product:
            return self.product
        else:
            return DistributionSourcePackage(
                self.distribution, self.sourcepackagename)


class HasCustomLanguageCodesMixin:
    """Helper class to implement `IHasCustomLanguageCodes`."""

    def composeCustomLanguageCodeMatch(self):
        """Define in child: compose Storm match clause.

        This should return a condition for use in a Storm query to match
        `CustomLanguageCode` objects to `self`.
        """
        raise NotImplementedError("composeCustomLanguageCodeMatch")

    def createCustomLanguageCode(self, language_code, language):
        """Define in child.  See `IHasCustomLanguageCodes`."""
        raise NotImplementedError("createCustomLanguageCode")

    def _queryCustomLanguageCodes(self, language_code=None):
        """Query `CustomLanguageCodes` belonging to `self`.

        :param language_code: Optional custom language code to look for.
            If not given, all codes will match.
        :return: A Storm result set.
        """
        match = self.composeCustomLanguageCodeMatch()
        store = IStore(CustomLanguageCode)
        if language_code is not None:
            match = And(
                match, CustomLanguageCode.language_code == language_code)
        return store.find(CustomLanguageCode, match)

    @property
    def has_custom_language_codes(self):
        """See `IHasCustomLanguageCodes`."""
        return self._queryCustomLanguageCodes().any() is not None

    @property
    def custom_language_codes(self):
        """See `IHasCustomLanguageCodes`."""
        return self._queryCustomLanguageCodes().order_by('language_code')

    def getCustomLanguageCode(self, language_code):
        """See `IHasCustomLanguageCodes`."""
        return self._queryCustomLanguageCodes(language_code).one()

    def removeCustomLanguageCode(self, custom_code):
        """See `IHasCustomLanguageCodes`."""
        language_code = custom_code.language_code
        return self._queryCustomLanguageCodes(language_code).remove()
