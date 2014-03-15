# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Functions for fixing mismatched plural form translations."""

__metaclass__ = type

__all__ = [
    'fix_plurals_in_all_pofiles',
    ]

from sqlobject import SQLObjectNotFound

from lp.services.database.sqlbase import (
    cursor,
    sqlvalues,
    )
from lp.translations.interfaces.translations import TranslationConstants
from lp.translations.model.pofile import POFile
from lp.translations.model.translationmessage import TranslationMessage
from lp.translations.utilities.gettext_po_parser import POHeader
from lp.translations.utilities.pluralforms import plural_form_mapper


def get_mapping_for_pofile_plurals(pofile):
    """Check if POFile plural forms need fixing.

    Return a mapping if a plural form expression in PO file header doesn't
    match expected plural form expression for `pofile.language`, otherwise
    return False.
    """
    expected_plural_formula = pofile.language.pluralexpression
    used_plural_formula = POHeader(pofile.header).plural_form_expression
    if expected_plural_formula == used_plural_formula:
        return None
    else:
        forms_map = plural_form_mapper(expected_plural_formula,
                                       used_plural_formula)
        for key in forms_map:
            if forms_map[key] != key:
                return forms_map

        return None


def fix_pofile_plurals(pofile, logger, ztm):
    """Fix plural translations for PO files with mismatching headers."""
    logger.debug("Checking if PO file %d needs fixing" % pofile.id)
    plural_forms_mapping = get_mapping_for_pofile_plurals(pofile)
    if plural_forms_mapping is not None:
        logger.info("Fixing PO file %s" % pofile.title)
        pluralmessages = TranslationMessage.select("""
            POTMsgSet.id = TranslationMessage.potmsgset AND
            POTMsgSet.msgid_plural IS NOT NULL AND
            TranslationMessage.pofile = %s""" % sqlvalues(pofile),
            clauseTables=["POTMsgSet"])
        for message in pluralmessages:
            logger.debug("\tFixing translations for '%s'" % (
                message.potmsgset.singular_text))

            for form in xrange(TranslationConstants.MAX_PLURAL_FORMS):
                new_form = plural_forms_mapping[form]
                assert new_form < TranslationConstants.MAX_PLURAL_FORMS, (
                    "Translation with plural form %d in plurals mapping." %
                    new_form)
                translation = getattr(message, 'msgstr%d' % new_form)
                setattr(message, 'msgstr%d' % form, translation)

        # We also need to update the header so we don't try to re-do the
        # migration in the future.
        header = POHeader(pofile.header)
        header.plural_form_expression = pofile.language.pluralexpression
        header.has_plural_forms = True
        pofile.header = header.getRawContent()
        ztm.commit()


def fix_plurals_in_all_pofiles(ztm, logger):
    """Go through all PO files and fix plural forms if needed."""

    cur = cursor()
    cur.execute("""SELECT MAX(id) FROM POFile""")
    (max_pofile_id,) = cur.fetchall()[0]
    for pofile_id in range(1, max_pofile_id):
        try:
            pofile = POFile.get(pofile_id)
            fix_pofile_plurals(pofile, logger, ztm)
        except SQLObjectNotFound:
            pass

