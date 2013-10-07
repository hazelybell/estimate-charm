# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from lazr.enum import (
    DBEnumeratedType,
    DBItem,
    )
from zope.interface import Attribute

from lp.services.webapp.interfaces import ILaunchpadApplication


__metaclass__ = type

__all__ = [
    'IRosettaApplication',
    'TranslationConstants',
    'TranslationsBranchImportMode',
    ]


class IRosettaApplication(ILaunchpadApplication):
    """Application root for rosetta."""

    languages = Attribute(
        'Languages Launchpad can translate into.')
    language_count = Attribute(
        'Number of languages Launchpad can translate into.')
    statsdate = Attribute('The date stats were last updated.')
    translation_groups = Attribute('ITranslationGroupSet object.')

    def translatable_products():
        """Return a list of the translatable products."""

    def featured_products():
        """Return a sample of all the translatable products."""

    def translatable_distroseriess():
        """Return a list of the distroseriess in launchpad for which
        translations can be done.
        """

    def potemplate_count():
        """Return the number of potemplates in the system."""

    def pofile_count():
        """Return the number of pofiles in the system."""

    def pomsgid_count():
        """Return the number of msgs in the system."""

    def translator_count():
        """Return the number of people who have given translations."""


class TranslationConstants:
    """Set of constants used inside the context of translations."""

    SINGULAR_FORM = 0
    PLURAL_FORM = 1

    # Largest number of plural forms any language can have.
    MAX_PLURAL_FORMS = 6

    SPACE_CHAR = '<samp> </samp>'
    NEWLINE_CHAR = '<img alt="" src="/@@/translation-newline" /><br/>\n'
    TAB_CHAR = '<code>[tab]</code>'
    TAB_CHAR_ESCAPED = '<code>' + r'\[tab]' + '</code>'
    NO_BREAK_SPACE_CHAR = '<code>[nbsp]</code>'
    NO_BREAK_SPACE_CHAR_ESCAPED = '<code>' + r'\[nbsp]' + '</code>'
    NARROW_NO_BREAK_SPACE_CHAR = '<code>[nnbsp]</code>'
    NARROW_NO_BREAK_SPACE_CHAR_ESCAPED = '<code>' + r'\[nnbsp]' + '</code>'


class TranslationsBranchImportMode(DBEnumeratedType):
    """How translations from a Bazaar branch should be synchronized."""

    NO_IMPORT = DBItem(1, """
        None

        Do not import any templates or translations from the branch.
        """)

    IMPORT_TEMPLATES = DBItem(2, """
        Import template files

        Import all translation template files found in the branch.
        """)

    IMPORT_TRANSLATIONS = DBItem(3, """
        Import template and translation files

        Import all translation files (templates and translations)
        found in the branch.
        """)
