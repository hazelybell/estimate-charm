#!/usr/bin/python -S
#
# Copyright 2012-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

import _pythonpath

from zope.component import getUtility
from zope.interface import implements

from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.model.distroseries import DistroSeries
from lp.services.database.interfaces import IMasterStore
from lp.services.looptuner import (
    DBLoopTuner,
    ITunableLoop,
    )
from lp.services.scripts.base import LaunchpadScript


delete_pofiletranslator = """\
DELETE FROM POFileTranslator
 WHERE POFileTranslator.id IN (
    SELECT POFileTranslator.id
      FROM POFileTranslator, POFile, POTemplate
     WHERE POFileTranslator.pofile = POFile.id
       AND POFile.potemplate = POTemplate.id
       AND POTemplate.distroseries = ?
     LIMIT ?)
"""

null_translationimportqueueentry_pofile = """\
UPDATE TranslationImportQueueEntry
   SET pofile = NULL
 WHERE TranslationImportQueueEntry.id IN (
    SELECT TranslationImportQueueEntry.id
      FROM TranslationImportQueueEntry, POFile, POTemplate
     WHERE TranslationImportQueueEntry.pofile = POFile.id
       AND POFile.potemplate = POTemplate.id
       AND POTemplate.distroseries = ?
     LIMIT ?)
"""

delete_pofile = """\
DELETE FROM POFile
 WHERE POFile.id IN (
    SELECT POFile.id
      FROM POFile, POTemplate
     WHERE POFile.potemplate = POTemplate.id
       AND POTemplate.distroseries = ?
     LIMIT ?)
"""

delete_translationtemplateitem = """\
DELETE FROM TranslationTemplateItem
 WHERE TranslationTemplateItem.id IN (
    SELECT TranslationTemplateItem.id
      FROM TranslationTemplateItem, POTemplate
     WHERE TranslationTemplateItem.potemplate = POTemplate.id
       AND POTemplate.distroseries = ?
     LIMIT ?)
"""

delete_packagingjob = """\
DELETE FROM PackagingJob
 WHERE PackagingJob.id IN (
    SELECT PackagingJob.id
      FROM PackagingJob, POTemplate
     WHERE PackagingJob.potemplate = POTemplate.id
       AND POTemplate.distroseries = ?
     LIMIT ?)
"""

null_translationimportqueueentry_potemplate = """\
UPDATE TranslationImportQueueEntry
   SET potemplate = NULL
 WHERE TranslationImportQueueEntry.id IN (
    SELECT TranslationImportQueueEntry.id
      FROM TranslationImportQueueEntry, POTemplate
     WHERE TranslationImportQueueEntry.potemplate = POTemplate.id
       AND POTemplate.distroseries = ?
     LIMIT ?)
"""

delete_potemplate = """\
DELETE FROM POTemplate
 WHERE POTemplate.id IN (
    SELECT POTemplate.id
      FROM POTemplate
     WHERE POTemplate.distroseries = ?
     LIMIT ?)
"""

statements = [
    delete_pofiletranslator,
    null_translationimportqueueentry_pofile,
    delete_pofile,
    delete_translationtemplateitem,
    delete_packagingjob,
    null_translationimportqueueentry_potemplate,
    delete_potemplate,
    ]


class ExecuteLoop:

    implements(ITunableLoop)

    def __init__(self, statement, series, logger):
        self.statement = statement
        self.series = series
        self.logger = logger
        self.done = False

    def isDone(self):
        return self.done

    def __call__(self, chunk_size):
        self.logger.info(
            "%s (limited to %d rows)", self.statement.splitlines()[0],
            chunk_size)
        store = IMasterStore(DistroSeries)
        result = store.execute(self.statement, (self.series.id, chunk_size,))
        self.done = (result.rowcount == 0)
        self.logger.info(
            "%d rows deleted (%s)", result.rowcount,
            ("done" if self.done else "not done"))
        store.commit()


class WipeSeriesTranslationsScript(LaunchpadScript):

    description = "Wipe translations for a series."

    def add_my_options(self):
        self.parser.add_option('-d', '--distribution', dest='distro',
            default='ubuntu',
            help='Name of distribution to delete translations in.')
        self.parser.add_option('-s', '--series', dest='series',
            help='Name of distroseries whose translations should be removed')

    def _getTargetSeries(self):
        series = self.options.series
        return getUtility(IDistributionSet)[self.options.distro][series]

    def main(self):
        series = self._getTargetSeries()
        for statement in statements:
            delete = ExecuteLoop(statement, series, self.logger)
            tuner = DBLoopTuner(delete, 2.0, maximum_chunk_size=5000)
            tuner.run()


if __name__ == '__main__':
    WipeSeriesTranslationsScript(dbuser='rosettaadmin').run()
