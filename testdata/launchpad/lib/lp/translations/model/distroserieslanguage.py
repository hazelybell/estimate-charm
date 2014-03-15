# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""An implementation of `DistroSeriesLanguage` objects."""

__metaclass__ = type

__all__ = [
    'DistroSeriesLanguage',
    'DistroSeriesLanguageSet',
    'DummyDistroSeriesLanguage',
    ]

from datetime import datetime

import pytz
from sqlobject import (
    ForeignKey,
    IntCol,
    )
from zope.interface import implements

from lp.services.database.constants import (
    DEFAULT,
    UTC_NOW,
    )
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.sqlbase import (
    SQLBase,
    sqlvalues,
    )
from lp.translations.interfaces.distroserieslanguage import (
    IDistroSeriesLanguage,
    IDistroSeriesLanguageSet,
    )
from lp.translations.model.pofile import (
    DummyPOFile,
    POFile,
    )
from lp.translations.model.potemplate import get_pofiles_for
from lp.translations.model.translator import Translator
from lp.translations.utilities.rosettastats import RosettaStats


class DistroSeriesLanguage(SQLBase, RosettaStats):
    """See `IDistroSeriesLanguage`.

    A SQLObject based implementation of IDistroSeriesLanguage.
    """
    implements(IDistroSeriesLanguage)

    _table = 'DistroSeriesLanguage'

    distroseries = ForeignKey(foreignKey='DistroSeries',
        dbName='distroseries', notNull=False, default=None)
    language = ForeignKey(foreignKey='Language', dbName='language',
        notNull=True)
    currentcount = IntCol(notNull=True, default=0)
    updatescount = IntCol(notNull=True, default=0)
    rosettacount = IntCol(notNull=True, default=0)
    unreviewed_count = IntCol(notNull=True, default=0)
    contributorcount = IntCol(notNull=True, default=0)
    dateupdated = UtcDateTimeCol(dbName='dateupdated', default=DEFAULT)

    @property
    def title(self):
        return '%s translations of %s %s' % (
            self.language.englishname,
            self.distroseries.distribution.displayname,
            self.distroseries.displayname)

    @property
    def pofiles(self):
        return POFile.select('''
            POFile.language = %s AND
            POFile.potemplate = POTemplate.id AND
            POTemplate.distroseries = %s AND
            POTemplate.iscurrent = TRUE
            ''' % sqlvalues(self.language.id, self.distroseries.id),
            clauseTables=['POTemplate'],
            prejoins=["potemplate.sourcepackagename"],
            orderBy=['-POTemplate.priority', 'POFile.id'])

    def getPOFilesFor(self, potemplates):
        """See `IDistroSeriesLanguage`."""
        return get_pofiles_for(potemplates, self.language)

    @property
    def translators(self):
        return Translator.select('''
            Translator.translationgroup = TranslationGroup.id AND
            Distribution.translationgroup = TranslationGroup.id AND
            Distribution.id = %s
            Translator.language = %s
            ''' % sqlvalues(self.distroseries.distribution.id,
                            self.language.id),
            orderBy=['id'],
            clauseTables=['TranslationGroup', 'Distribution',],
            distinct=True)

    @property
    def contributor_count(self):
        return self.contributorcount

    def messageCount(self):
        return self.distroseries.messagecount

    def currentCount(self, language=None):
        return self.currentcount

    def updatesCount(self, language=None):
        return self.updatescount

    def rosettaCount(self, language=None):
        return self.rosettacount

    def unreviewedCount(self):
        """See `IRosettaStats`."""
        return self.unreviewed_count

    def updateStatistics(self, ztm=None):
        current = 0
        updates = 0
        rosetta = 0
        unreviewed = 0
        for pofile in self.pofiles:
            current += pofile.currentCount()
            updates += pofile.updatesCount()
            rosetta += pofile.rosettaCount()
            unreviewed += pofile.unreviewedCount()
        self.currentcount = current
        self.updatescount = updates
        self.rosettacount = rosetta
        self.unreviewed_count = unreviewed

        contributors = self.distroseries.getPOFileContributorsByLanguage(
            self.language)
        self.contributorcount = contributors.count()

        self.dateupdated = UTC_NOW
        ztm.commit()


class DummyDistroSeriesLanguage(RosettaStats):
    """See `IDistroSeriesLanguage`

    Represents a DistroSeriesLanguage where we do not yet actually HAVE one
    for that language for this distribution series.
    """
    implements(IDistroSeriesLanguage)

    def __init__(self, distroseries, language):
        assert 'en' != language.code, (
            'English is not a translatable language.')

        super(DummyDistroSeriesLanguage, self).__init__()

        self.id = None
        self.language = language
        self.distroseries = distroseries
        self.messageCount = distroseries.messagecount
        self.dateupdated = datetime.now(tz=pytz.timezone('UTC'))
        self.contributor_count = 0
        self.title = '%s translations of %s %s' % (
            self.language.englishname,
            self.distroseries.distribution.displayname,
            self.distroseries.displayname)

    @property
    def pofiles(self):
        """See `IDistroSeriesLanguage`."""
        return self.getPOFilesFor(
            self.distroseries.getCurrentTranslationTemplates())

    def getPOFilesFor(self, potemplates):
        """See `IDistroSeriesLanguage`."""
        templates = list(potemplates)
        language = self.language
        return [DummyPOFile(template, language) for template in templates]

    def currentCount(self, language=None):
        return 0

    def rosettaCount(self, language=None):
        return 0

    def updatesCount(self, language=None):
        return 0

    def newCount(self, language=None):
        return 0

    def translatedCount(self, language=None):
        return 0

    def untranslatedCount(self, language=None):
        return self.messageCount

    def unreviewedCount(self):
        return 0

    def currentPercentage(self, language=None):
        return 0.0

    def rosettaPercentage(self, language=None):
        return 0.0

    def updatesPercentage(self, language=None):
        return 0.0

    def newPercentage(self, language=None):
        return 0.0

    def translatedPercentage(self, language=None):
        return 0.0

    def untranslatedPercentage(self, language=None):
        return 100.0

    def updateStatistics(self, ztm=None):
        return


class DistroSeriesLanguageSet:
    """See `IDistroSeriesLanguageSet`.

    Implements a means to get a DummyDistroSeriesLanguage.
    """
    implements(IDistroSeriesLanguageSet)

    def getDummy(self, distroseries, language):
        """See IDistroSeriesLanguageSet."""
        return DummyDistroSeriesLanguage(distroseries, language)

