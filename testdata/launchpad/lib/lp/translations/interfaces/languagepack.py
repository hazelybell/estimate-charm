# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Language pack store."""

__metaclass__ = type

__all__ = [
    'ILanguagePack',
    'ILanguagePackSet',
    ]

from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Choice,
    Datetime,
    Int,
    Object,
    )

from lp import _
from lp.services.librarian.interfaces import ILibraryFileAlias
from lp.translations.enums import LanguagePackType


class ILanguagePack(Interface):
    """Language pack store."""

    id = Int(title=_('Language pack ID.'), required=True, readonly=True)

    file = Object(
        title=_('Librarian file where the language pack is stored.'),
        required=True, schema=ILibraryFileAlias)

    date_exported = Datetime(
        title=_('When this language pack was exported.'),
        required=True)

    distroseries = Choice(
        title=_('The distribution series from which it was exported.'),
        required=True, vocabulary='FilteredDistroSeries')

    type = Choice(
        title=_('Language pack type'), required=True,
        vocabulary=LanguagePackType,
        description=_("""
            The language pack is either a "Full" export, or a "Delta" of
            changes from the base language pack of the distribution series.
            """))

    updates = Attribute(_('The LanguagePack that this one updates.'))


class ILanguagePackSet(Interface):
    """Language pack store set."""

    def addLanguagePack(distroseries, file_alias, type):
        """Associate an uploaded file as a language pack for a distroseries.

        :param distroseries: The `IDistroSeries` associated from where this
            language pack was exported.
        :param file_alias: An `ILibraryFileAlias` pointing to the librarian
            entry storing the language pack we want to register.
        :param type: The kind of `LanguagePackType` for this language pack.
        :return: An `ILanguagePack` representing the given language pack.
        """
