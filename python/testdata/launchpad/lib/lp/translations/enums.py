# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Enumerations used in the lp/translations modules."""

__metaclass__ = type
__all__ = [
    'LanguagePackType',
    'RosettaImportStatus',
    'TranslationPermission',
    ]

from lazr.enum import (
    DBEnumeratedType,
    DBItem,
    )


class LanguagePackType(DBEnumeratedType):
    """Type of language packs."""

    FULL = DBItem(1, """
        Full

        Full translations export.""")

    DELTA = DBItem(2, """
        Delta

        Delta translation export based on a previous full export.""")


class RosettaImportStatus(DBEnumeratedType):
    """Rosetta Import Status

    Define the status of an import on the Import queue. It could have one
    of the following states: approved, imported, deleted, failed, needs_review
    or blocked.
    """

    APPROVED = DBItem(1, """
        Approved

        The entry has been approved by a Rosetta Expert or was able to be
        approved by our automatic system and is waiting to be imported.
        """)

    IMPORTED = DBItem(2, """
        Imported

        The entry has been imported.
        """)

    DELETED = DBItem(3, """
        Deleted

        The entry has been removed before being imported.
        """)

    FAILED = DBItem(4, """
        Failed

        The entry import failed.
        """)

    NEEDS_REVIEW = DBItem(5, """
        Needs Review

        A Rosetta Expert needs to review this entry to decide whether it will
        be imported and where it should be imported.
        """)

    BLOCKED = DBItem(6, """
        Blocked

        The entry has been blocked to be imported by a Rosetta Expert.
        """)

    NEEDS_INFORMATION = DBItem(7, """
        Needs Information

        The reviewer needs more information before this entry can be approved.
        """)


class TranslationPermission(DBEnumeratedType):
    """Translation Permission System

    Projects groups, products and distributions can all have content that
    needs to be translated. In this case, Launchpad Translations allows them
    to decide how open they want that translation process to be. At one
    extreme, anybody can add or edit any translation, without review. At the
    other, only the designated translator for that group in that language can
    add or edit its translation files. This schema enumerates the options.
    """

    OPEN = DBItem(1, """
        Open

        This group allows totally open access to its translations. Any
        logged-in user can add or edit translations in any language, without
        any review.""")

    STRUCTURED = DBItem(20, """
        Structured

        This group has designated translators for certain languages. In
        those languages, people who are not designated translators can only
        make suggestions. However, in languages which do not yet have a
        designated translator, anybody can edit the translations directly,
        with no further review.""")

    RESTRICTED = DBItem(100, """
        Restricted

        This group allows only designated translators to edit the
        translations of its files. You can become a designated translator
        either by joining an existing language translation team for this
        project, or by getting permission to start a new team for a new
        language. People who are not designated translators can still make
        suggestions for new translations, but those suggestions need to be
        reviewed before being accepted by the designated translator.""")

    CLOSED = DBItem(200, """
        Closed

        This group allows only designated translators to edit or add
        translations. You can become a designated translator either by
        joining an existing language translation team for this
        project, or by getting permission to start a new team for a new
        language. People who are not designated translators will not be able
        to add suggestions.""")
