# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from zope.interface import Interface


__metaclass__ = type

__all__ = ('IRosettaStats', )

class IRosettaStats(Interface):
    """Rosetta-related statistics."""

    def testStatistics():
        """Ensure that the statistics here are self-consistent.

        For example, the number of New and Updated messages
        should add up to the rosettaCount.
        """

    def updateStatistics():
        """Update the statistics associated with this object."""

    def messageCount():
        """Return the number of current IPOMessageSets inside this object."""

    def currentCount(language=None):
        """Return the number of current upstream translations.

        That's the msgsets for this object that have a complete, non-fuzzy
        translation in its PO file for this language when we last parsed it.
        """

    def updatesCount(language=None):
        """Return the number of msgsets newer in Rosetta.

        That's the msgsets for this object where we have a newer translation
        in rosetta than the one in the PO file for this language, when we last
        parsed it.
        """

    def newCount(language=None):
        """Return the number of newly translated messages in Rosetta.

        Doesn't include updates for imported translations.
        """

    def rosettaCount(language=None):
        """Return the number of msgsets translated only in rosetta.

        That's the msgsets that are translated in Rosetta and there was no
        translation in the PO file for this language when we last parsed it.
        """

    def unreviewedCount():
        """Return the number of msgsets with unreviewed suggestions.

        Unreviewed are those which contain suggestions submitted later
        than the last review date.
        """

    def translatedCount(language=None):
        """Return the total number of msgsets that are translated in Rosetta.
        """

    def untranslatedCount(language=None):
        """Return the number of msgsets that are untranslated."""

    def updatesPercentage(language=None):
        """Return the percentage of updated msgsets inside this object."""

    def currentPercentage(language=None):
        """Return the percentage of current msgsets inside this object."""

    def rosettaPercentage(language=None):
        """Return the percentage of msgsets translated with Rosetta inside
        this object.
        """

    def translatedPercentage(language=None):
        """Return the percentage of msgsets translated for this object."""

    def untranslatedPercentage(language=None):
        """Return the percentage of msgsets untranslated for this object."""

    def newPercentage(language=None):
        """Return the percentage of translations for this object that are
        newly translated in Rosetta and not updates of imported.
        """
