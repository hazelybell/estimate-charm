# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Translations auto-approval script."""

__metaclass__ = type

__all__ = [
    'ImportQueueGardener',
    ]

from zope.component import getUtility

from lp.services.scripts.base import LaunchpadCronScript
from lp.translations.interfaces.translationimportqueue import (
    ITranslationImportQueue,
    )


class ImportQueueGardener(LaunchpadCronScript):
    """Automated gardening for the Translations import queue."""
    def main(self):
        """Manage import queue.

        Approve uploads that can be approved automatically.
        Garbage-collect ones that are no longer needed.  Block
        translations on the queue for templates that are blocked.
        """
        self.logger.debug("Starting gardening of translation imports")

        translation_import_queue = getUtility(ITranslationImportQueue)

        if translation_import_queue.executeOptimisticApprovals(self.txn):
            self.logger.info(
                'The automatic approval system approved some entries.')

        removed_entries = translation_import_queue.cleanUpQueue()
        if removed_entries > 0:
            self.logger.info('Removed %d entries from the queue.' %
                removed_entries)

        if self.txn:
            self.txn.commit()

        blocked_entries = (
            translation_import_queue.executeOptimisticBlock(self.txn))
        if blocked_entries > 0:
            self.logger.info('Blocked %d entries from the queue.' %
                blocked_entries)

        self.logger.debug("Completed gardening of translation imports.")
