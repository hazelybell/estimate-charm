# Copyright 2009-2011 Canonical Ltd.  This software is licensed under
# the GNU Affero General Public License version 3 (see the file
# LICENSE).

__metaclass__ = type
__all__ = [
    'Language',
    'LanguageSet',
    ]


from sqlobject import (
    BoolCol,
    IntCol,
    SQLObjectNotFound,
    SQLRelatedJoin,
    StringCol,
    )
from storm.expr import (
    And,
    Count,
    Desc,
    Join,
    LeftJoin,
    Or,
    )
from zope.interface import implements

from lp.app.errors import NotFoundError
from lp.registry.model.karma import (
    KarmaCache,
    KarmaCategory,
    )
from lp.services.database.decoratedresultset import DecoratedResultSet
from lp.services.database.enumcol import EnumCol
from lp.services.database.interfaces import (
    ISlaveStore,
    IStore,
    )
from lp.services.database.sqlbase import SQLBase
from lp.services.helpers import ensure_unicode
from lp.services.propertycache import (
    cachedproperty,
    get_property_cache,
    )
from lp.services.worlddata.interfaces.language import (
    ILanguage,
    ILanguageSet,
    TextDirection,
    )
# XXX: JonathanLange 2010-11-10 bug=673796: It turns out this module is
# unusable without spokenin being imported first. So, import spokenin.
from lp.services.worlddata.model.spokenin import SpokenIn


SpokenIn


class Language(SQLBase):
    implements(ILanguage)

    _table = 'Language'

    code = StringCol(
        dbName='code', notNull=True, unique=True, alternateID=True)
    uuid = StringCol(dbName='uuid', notNull=False, default=None)
    nativename = StringCol(dbName='nativename')
    englishname = StringCol(dbName='englishname')
    pluralforms = IntCol(dbName='pluralforms')
    pluralexpression = StringCol(dbName='pluralexpression')
    visible = BoolCol(dbName='visible', notNull=True)
    direction = EnumCol(
        dbName='direction', notNull=True, schema=TextDirection,
        default=TextDirection.LTR)

    translation_teams = SQLRelatedJoin(
        'Person', joinColumn="language",
        intermediateTable='Translator', otherColumn='translator')

    _countries = SQLRelatedJoin(
        'Country', joinColumn='language', otherColumn='country',
        intermediateTable='SpokenIn')

    # Define a read/write property `countries` so it can be passed
    # to language administration `LaunchpadFormView`.
    def _getCountries(self):
        return self._countries

    def _setCountries(self, countries):
        for country in self._countries:
            if country not in countries:
                self.removeCountry(country)
        for country in countries:
            if country not in self._countries:
                self.addCountry(country)
    countries = property(_getCountries, _setCountries)

    @property
    def displayname(self):
        """See `ILanguage`."""
        return '%s (%s)' % (self.englishname, self.code)

    def __repr__(self):
        return "<%s '%s' (%s)>" % (
            self.__class__.__name__, self.englishname, self.code)

    @property
    def guessed_pluralforms(self):
        """See `ILanguage`."""
        forms = self.pluralforms
        if forms is None:
            # Just take a plausible guess.  The caller needs a number.
            return 2
        else:
            return forms

    @property
    def alt_suggestion_language(self):
        """See `ILanguage`.

        Non-visible languages and English are not translatable, so they
        are excluded. Brazilian Portuguese has diverged from Portuguese
        to such a degree that it should be treated as a parent language.
        Norwegian languages Nynorsk (nn) and Bokmaal (nb) are similar
        and may provide suggestions for each other.
        """
        if self.code == 'pt_BR':
            return None
        elif self.code == 'nn':
            return Language.byCode('nb')
        elif self.code == 'nb':
            return Language.byCode('nn')
        codes = self.code.split('_')
        if len(codes) == 2 and codes[0] != 'en':
            language = Language.byCode(codes[0])
            if language.visible == True:
                return language
            else:
                return None
        return None

    @property
    def dashedcode(self):
        """See `ILanguage`."""
        return self.code.replace('_', '-')

    @property
    def abbreviated_text_dir(self):
        """See `ILanguage`."""
        if self.direction == TextDirection.LTR:
            return 'ltr'
        elif self.direction == TextDirection.RTL:
            return 'rtl'
        else:
            assert False, "unknown text direction"

    @property
    def translators(self):
        """See `ILanguage`."""
        from lp.registry.model.person import (
            Person,
            PersonLanguage,
            )
        return IStore(Language).using(
            Join(
                Person,
                LanguageSet._getTranslatorJoins(),
                Person.id == PersonLanguage.personID),
            ).find(
                Person,
                PersonLanguage.language == self,
            ).order_by(Desc(KarmaCache.karmavalue))

    @cachedproperty
    def translators_count(self):
        """See `ILanguage`."""
        return self.translators.count()


class LanguageSet:
    implements(ILanguageSet)

    @staticmethod
    def _getTranslatorJoins():
        # XXX CarlosPerelloMarin 2007-03-31 bug=102257:
        # The KarmaCache table doesn't have a field to store karma per
        # language, so we are actually returning the people with the most
        # translation karma that have this language selected in their
        # preferences.
        from lp.registry.model.person import PersonLanguage
        return Join(
            PersonLanguage,
            Join(
                KarmaCache,
                KarmaCategory,
                And(
                    KarmaCategory.name == 'translations',
                    KarmaCache.categoryID == KarmaCategory.id,
                    KarmaCache.productID == None,
                    KarmaCache.projectID == None,
                    KarmaCache.sourcepackagenameID == None,
                    KarmaCache.distributionID == None)),
            PersonLanguage.personID ==
                KarmaCache.personID)

    @property
    def _visible_languages(self):
        return Language.select(
            'visible IS TRUE',
            orderBy='englishname')

    @property
    def common_languages(self):
        """See `ILanguageSet`."""
        return iter(self._visible_languages)

    def getDefaultLanguages(self, want_translators_count=False):
        """See `ILanguageSet`."""
        return self.getAllLanguages(
            want_translators_count=want_translators_count,
            only_visible=True)

    def getAllLanguages(self, want_translators_count=False,
                        only_visible=False):
        """See `ILanguageSet`."""
        result = IStore(Language).find(
                Language,
                Language.visible == True if only_visible else True,
            ).order_by(
            Language.englishname)
        if want_translators_count:
            def preload_translators_count(languages):
                from lp.registry.model.person import PersonLanguage
                ids = set(language.id for language in languages).difference(
                    set([None]))
                counts = IStore(Language).using(
                    LeftJoin(
                        Language,
                        self._getTranslatorJoins(),
                        PersonLanguage.languageID == Language.id),
                    ).find(
                        (Language, Count(PersonLanguage)),
                        Language.id.is_in(ids),
                    ).group_by(Language)
                for language, count in counts:
                    get_property_cache(language).translators_count = count
            return DecoratedResultSet(
                result, pre_iter_hook=preload_translators_count)
        return result

    def __iter__(self):
        """See `ILanguageSet`."""
        return iter(Language.select(orderBy='englishname'))

    def __getitem__(self, code):
        """See `ILanguageSet`."""
        language = self.getLanguageByCode(code)

        if language is None:
            raise NotFoundError(code)

        return language

    def get(self, language_id):
        """See `ILanguageSet`."""
        try:
            return Language.get(language_id)
        except SQLObjectNotFound:
            return None

    def getLanguageByCode(self, code):
        """See `ILanguageSet`."""
        assert isinstance(code, basestring), (
            "%s is not a valid type for 'code'" % type(code))
        try:
            return Language.byCode(code)
        except SQLObjectNotFound:
            return None

    def keys(self):
        """See `ILanguageSet`."""
        return [language.code for language in Language.select()]

    def canonicalise_language_code(self, code):
        """See `ILanguageSet`."""

        if '-' in code:
            language, country = code.split('-', 1)

            return "%s_%s" % (language, country.upper())
        else:
            return code

    def codes_to_languages(self, codes):
        """See `ILanguageSet`."""

        languages = []

        for code in [self.canonicalise_language_code(code) for code in codes]:
            try:
                languages.append(self[code])
            except KeyError:
                pass

        return languages

    def createLanguage(self, code, englishname, nativename=None,
                       pluralforms=None, pluralexpression=None, visible=True,
                       direction=TextDirection.LTR):
        """See `ILanguageSet`."""
        return Language(
            code=code, englishname=englishname, nativename=nativename,
            pluralforms=pluralforms, pluralexpression=pluralexpression,
            visible=visible, direction=direction)

    def search(self, text):
        """See `ILanguageSet`."""
        if text:
            text = ensure_unicode(text).lower()
            results = ISlaveStore(Language).find(
                Language, Or(
                    Language.code.lower().contains_string(text),
                    Language.englishname.lower().contains_string(
                        text))).order_by(Language.englishname)
        else:
            results = None

        return results
