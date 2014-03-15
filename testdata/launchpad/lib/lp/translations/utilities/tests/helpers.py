# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Helper module reused in different tests."""

__metaclass__ = type

__all__ = [
    'import_pofile_or_potemplate',
    'is_valid_mofile',
    ]

import transaction
from zope.component import getUtility

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.services.log.logger import FakeLogger
from lp.translations.enums import RosettaImportStatus
from lp.translations.interfaces.translationimportqueue import (
    ITranslationImportQueue,
    )


def import_pofile_or_potemplate(file_contents, person,
    pofile=None, potemplate=None, by_maintainer=True):
    """Import a `POFile` or `POTemplate` from the given string.

    :param file_contents: text of "file" to import.
    :param person: party requesting the import.
    :param pofile: if uploading a `POFile`, file to import to; None otherwise.
    :param potemplate: if uploading a `POTemplate`, file to import to; None
        otherwise.
    :param by_maintainer: true if this file was uplaoded by the maintainer
        of the project or package.
    :return: `TranslationImportQueueEntry` as added to the import queue.
    """
    translation_import_queue = getUtility(ITranslationImportQueue)
    if pofile is not None:
        if pofile.potemplate.distroseries is None:
            entry = translation_import_queue.addOrUpdateEntry(
                pofile.path, file_contents, by_maintainer, person,
                productseries=pofile.potemplate.productseries, pofile=pofile)
        else:
            entry = translation_import_queue.addOrUpdateEntry(
                pofile.path, file_contents, by_maintainer, person,
                distroseries=pofile.potemplate.distroseries,
                sourcepackagename=pofile.potemplate.sourcepackagename,
                pofile=pofile)
        target = pofile
    else:
        # A POTemplate can only be uploaded by the maintainer, so setting the
        # by_maintainer flag makes no difference.
        if potemplate.distroseries is None:
            entry = translation_import_queue.addOrUpdateEntry(
                potemplate.path, file_contents, True, person,
                productseries=potemplate.productseries, potemplate=potemplate)
        else:
            entry = translation_import_queue.addOrUpdateEntry(
                potemplate.path, file_contents, True, person,
                distroseries=potemplate.distroseries,
                sourcepackagename=potemplate.sourcepackagename,
                potemplate=potemplate)
        target = potemplate
    # Allow Librarian to see the change.
    transaction.commit()

    entry.setStatus(RosettaImportStatus.APPROVED,
                    getUtility(ILaunchpadCelebrities).rosetta_experts)
    (subject, body) = target.importFromQueue(entry, FakeLogger())
    return entry


def is_valid_mofile(mofile):
    """Test whether a string is a valid MO file."""
    # There are different magics for big- and little-endianness, so we
    # test for both.
    be_magic = '\x95\x04\x12\xde'
    le_magic = '\xde\x12\x04\x95'

    return mofile[:len(be_magic)] in (be_magic, le_magic)
