# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from zope.interface import (
    Attribute,
    Interface,
    )
from zope.interface.common.sequence import IFiniteSequence
from zope.schema import (
    Datetime,
    Object,
    )

from lp import _
from lp.registry.interfaces.person import IPerson
from lp.services.worlddata.interfaces.language import ILanguage
from lp.translations.interfaces.hastranslationtemplates import (
    IHasTranslationTemplates,
    )


__metaclass__ = type

__all__ = [
    'IPOFilesByPOTemplates',
    'ITranslatedLanguage',
    ]


class ITranslatedLanguage(Interface):
    """Interface for providing translations for context by language.

    It expects `parent` to provide `IHasTranslationTemplates`.
    """

    language = Object(
        title=_('Language to gather statistics and POFiles for.'),
        schema=ILanguage)

    parent = Object(
        title=_('A parent with translation templates.'),
        schema=IHasTranslationTemplates)

    pofiles = Attribute(
        _('Iterator over all POFiles for this context and language.'))

    translation_statistics = Attribute(
        _('A dict containing relevant aggregated statistics counts.'))

    def setCounts(total, translated, new, changed, unreviewed):
        """Set aggregated message counts for ITranslatedLanguage."""

    def recalculateCounts():
        """Recalculate message counts for this ITranslatedLanguage."""

    last_changed_date = Datetime(
        title=_('When was this translation last changed.'),
        readonly=False, required=True)

    last_translator = Object(
        title=_('Last person that translated something in this context.'),
        schema=IPerson)


class IPOFilesByPOTemplates(IFiniteSequence):
    """Iterate `IPOFile`s for (`ILanguage`, `ITranslationTemplateCollection`).

    This is a wrapper for Storm ResultSet that enables optimized slicing
    by doing it lazily on the query, thus allowing DummyPOFile objects
    to be returned while still not doing more than one database query.

    It subclasses `IFiniteSequence` so it can easily be used with the
    BatchNavigator.
    """

    def __getitem__(selector):
        """Get an element or slice of `IPOFile`s for given templates."""

    def __getslice__(start, end):
        """Deprecated, and implemented through __getitem__."""

    def __iter__():
        """Iterates over all `IPOFile`s for given templates."""

    def __len__():
        """Provides count of `IPOTemplate`s in a template collection."""
