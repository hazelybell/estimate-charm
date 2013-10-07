# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Mark translation credits messages as translated."""

__metaclass__ = type
__all__ = [
    'FixTranslationCreditsProcess',
    ]


import logging

from zope.component import getUtility
from zope.interface import implements

from lp.services.looptuner import (
    DBLoopTuner,
    ITunableLoop,
    )
from lp.translations.interfaces.pofile import IPOFileSet


class CreditsFixer:
    """`ITunableLoop` that translates all `POFile`s' translation credits."""
    implements(ITunableLoop)

    def __init__(self, transaction, logger, start_at=0):
        self.transaction = transaction
        self.logger = logger
        self.start_at = start_at

        pofileset = getUtility(IPOFileSet)
        self.pofiles = pofileset.getPOFilesWithTranslationCredits(
            untranslated=True)
        self.logger.info(
            "Figuring out POFiles that need fixing: this may take a while...")
        self.total = self.pofiles.count()
        self.logger.info(
            "Marking up a total of %d credits as translated." % self.total)

    def isDone(self):
        """See `ITunableLoop`."""
        # When the main loop hits the end of the POFile table, it sets
        # start_at to None.  Until we know we hit the end, it always has a
        # numerical value.
        return self.start_at is None

    def getPOFilesBatch(self, chunk_size):
        """Return a batch of POFiles to work with."""
        self.logger.debug(
            "Getting POFiles[%d:%d]..." % (self.start_at,
                                           self.start_at + int(chunk_size)))
        pofiles = self.pofiles[self.start_at: self.start_at + int(chunk_size)]
        return pofiles

    def __call__(self, chunk_size):
        """See `ITunableLoop`.

        Retrieve a batch of `POFile`s in ascending id order, and mark
        all of their translation credits as translated.
        """
        pofiles = self.getPOFilesBatch(chunk_size)

        done = 0
        for pofile, potmsgset in pofiles:
            done += 1
            self.logger.debug(
                "Processing %d (out of %d)" % (
                    self.start_at + done, self.total))
            potmsgset.setTranslationCreditsToTranslated(pofile)
            self.transaction.commit()
            self.transaction.begin()

        if done == 0:
            self.start_at = None
        else:
            self.start_at += done
            self.logger.info("Processed %d/%d of messages." % (
                self.start_at, self.total))


class FixTranslationCreditsProcess:
    """Mark all `POFile` translation credits as translated."""

    def __init__(self, transaction, logger=None):
        self.transaction = transaction
        self.logger = logger
        if logger is None:
            self.logger = logging.getLogger("fix-translation-credits")

    def run(self):
        loop = CreditsFixer(self.transaction, self.logger)

        DBLoopTuner(loop, 5).run()

        self.logger.info("Done.")
