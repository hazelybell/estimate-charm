# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'product_modified',
    ]

from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.translations.interfaces.translationimportqueue import (
    ITranslationImportQueue,
    )


def product_modified(product, event):
    """Update translations objects when the product changes."""
    old_owner = event.object_before_modification.owner
    if old_owner != product.owner:
        import_queue = getUtility(ITranslationImportQueue)
        # The change in ownership may cause permission issues for
        # entries in the translation import queue *if* the old owner has
        # less permission now. This issue can be avoided by updating the
        # entries's importer to the new owner. This can only be done if the
        # new owner does not already have an entry in the queue.
        # See bug 635438 for more details.
        old_owner_entries = []
        new_owner_entries = []
        for entry in import_queue.getAllEntries(target=product):
            if entry.importer == old_owner:
                old_owner_entries.append(entry)
            elif entry.importer == product.owner:
                new_owner_entries.append(entry)
            else:
                # The entry is not affected by the ownership change.
                pass
        if len(old_owner_entries) > 0 and len(new_owner_entries) == 0:
            # The new owner does not have any conflicting entries in the
            # queue. Change the old owner's entries to the new owner to
            # ensure there is no permissions issues during processing.
            for entry in old_owner_entries:
                removeSecurityProxy(entry).importer = product.owner
