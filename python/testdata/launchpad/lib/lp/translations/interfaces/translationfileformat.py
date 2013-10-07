# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Enumeration type for translation file formats."""

__metaclass__ = type
__all__ = ['TranslationFileFormat']


from lazr.enum import (
    DBEnumeratedType,
    DBItem,
    )


class TranslationFileFormat(DBEnumeratedType):
    """Translation File Format

    This is an enumeration of the different sorts of file that Launchpad
    Translations knows about.
    """

    PO = DBItem(1, """
        PO format

        Gettext's standard text file format.
        """)

    MO = DBItem(2, """
        MO format

        Gettext's standard binary file format.
        """)

    XPI = DBItem(3, """
        Mozilla XPI format

        The .xpi format as used by programs from Mozilla foundation.
        """)

    KDEPO = DBItem(4, """
        KDE PO format

        Legacy KDE PO format which embeds context and plural forms inside
        messages itself instead of using gettext features.
        """)

    XPIPO = DBItem(5, """
        XPI PO format

        Variant of gettext format that always uses English message strings as
        msgids, even if the source format uses symbolic identifiers.  Useful
        for exporting XPI translations to the gettext world.
        """)

    POCHANGED = DBItem(6, """
        Changes from imported translations in partial PO format

        Gettext's standard text file format but contains only those msgids
        that were changed compared to the imported version.
        """)

