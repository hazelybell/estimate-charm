# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from zope.interface import implements

from lp.translations.interfaces.rosettastats import IRosettaStats

# XXX: Carlos Perello Marin 2005-04-14 bug=396:
# This code should be change to be an adaptor.

class RosettaStats(object):

    implements(IRosettaStats)

    def testStatistics(self):
        """See IRosettaStats."""
        if (self.newCount() + self.updatesCount()) != self.rosettaCount():
            return False
        if self.untranslatedCount() < 0:
            return False
        if self.untranslatedCount() > self.messageCount():
            return False
        if self.translatedCount() > self.messageCount():
            return False
        return True

    def updateStatistics(self):
        """See IRosettaStats."""
        # this method should be overridden by the objects that inherit from
        # this class
        pass

    def messageCount(self):
        """See IRosettaStats."""
        # This method should be overrided by the objects that inherit from
        # this class
        return 0

    def currentCount(self, language=None):
        """See IRosettaStats."""
        # This method should be overrided by the objects that inherit from
        # this class
        return 0

    def updatesCount(self, language=None):
        """See IRosettaStats."""
        # This method should be overrided by the objects that inherit from
        # this class
        return 0

    def rosettaCount(self, language=None):
        """See IRosettaStats."""
        # This method should be overrided by the objects that inherit from
        # this class
        return 0

    def translatedCount(self, language=None):
        """See IRosettaStats."""
        return self.currentCount(language) + self.rosettaCount(language)

    def untranslatedCount(self, language=None):
        """See IRosettaStats."""
        untranslated = self.messageCount() - self.translatedCount(language)
        # Statistics should not be ever less than 0
        assert untranslated >= 0, (
            'Stats error in %r id %d, %d untranslated' % (
                self, self.id, untranslated))
        return untranslated

    def newCount(self, language=None):
        """See IRosettaStats."""
        nonupdates = self.rosettaCount() - self.updatesCount()
        if nonupdates < 0:
            return 0
        else:
            return nonupdates

    def asPercentage(self, value):
        """See IRosettaStats."""
        if self.messageCount() > 0:
            percent = float(value) / self.messageCount()
            percent *= 100
        else:
            percent = 0
        return percent

    def translatedPercentage(self, language=None):
        """See IRosettaStats."""
        return self.asPercentage(self.translatedCount(language))

    def currentPercentage(self, language=None):
        """See IRosettaStats."""
        return self.asPercentage(self.currentCount(language))

    def untranslatedPercentage(self, language=None):
        """See IRosettaStats."""
        return self.asPercentage(self.untranslatedCount(language))

    def newPercentage(self, language=None):
        """See IRosettaStats."""
        return self.asPercentage(self.newCount(language))

    def updatesPercentage(self, language=None):
        """See IRosettaStats."""
        return self.asPercentage(self.updatesCount(language))

    def rosettaPercentage(self, language=None):
        """See IRosettaStats."""
        return self.asPercentage(self.rosettaCount(language))
