# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from zope.interface import (
    Attribute,
    Interface,
    )

from lp.translations.interfaces.rosettastats import IRosettaStats


__metaclass__ = type

__all__ = [
    'IDistroSeriesLanguage',
    'IDistroSeriesLanguageSet',
    ]

class IDistroSeriesLanguage(IRosettaStats):
    """A placeholder for the statistics in the translation of a
    distroseries into a language, for example, Ubuntu Hoary into French.
    This exists to cache stats, and be a useful object for traversal in
    Rosetta."""

    id = Attribute("A unique ID")

    language = Attribute("The language.")

    distroseries = Attribute("The distro series which has been "
        "translated.")

    dateupdated = Attribute("The date these statistics were last updated.")

    title = Attribute("The title.")

    pofiles = Attribute("The set of pofiles in this distroseries for this "
        "language. This includes only the real pofiles where translations "
        "exist.")

    contributor_count = Attribute("The number of contributors in total "
        "for this language in the distribution.")

    def updateStatistics(ztm):
        """Update all the Rosetta stats for this distro series language."""

    def getPOFilesFor(potemplates):
        """Return `POFile`s for each of `potemplates`, in the same order.

        For any `POTemplate` that does not have a translation to the
        required language, a `DummyPOFile` is provided.
        """


class IDistroSeriesLanguageSet(Interface):
    """The set of distroserieslanguages."""

    def getDummy(distroseries, language):
        """Return a new DummyDistroSeriesLanguage for the given
        distroseries and language.
        """

