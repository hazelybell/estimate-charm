# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from lazr.restful.fields import Reference
from zope.interface import Interface
from zope.schema import (
    Choice,
    TextLine,
    )

from lp import _
from lp.translations.interfaces.pofile import IPOFile
from lp.translations.interfaces.rosettastats import IRosettaStats
from lp.translations.interfaces.translatedlanguage import ITranslatedLanguage


__metaclass__ = type

__all__ = [
    'IProductSeriesLanguage',
    'IProductSeriesLanguageSet',
    ]


class IProductSeriesLanguage(IRosettaStats, ITranslatedLanguage):
    """Per-language statistics for a product series."""

    pofile = Reference(
        title=_("A POFile if there is only one POTemplate for the series."),
        schema=IPOFile, required=False, readonly=True)

    productseries = Choice(
        title=_("Series"),
        required=False,
        vocabulary="ProductSeries")

    title = TextLine(
        title=_("Title for the per-language per-series page."),
        required=False)


class IProductSeriesLanguageSet(Interface):
    """The set of productserieslanguages."""

    def getProductSeriesLanguage(productseries, language, pofile=None):
        """Return a PSL for a productseries and a language."""
