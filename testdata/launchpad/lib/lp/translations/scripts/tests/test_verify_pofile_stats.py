# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Integration-test POFile statistics verification script."""

__metaclass__ = type

from lp.testing import TestCaseWithFactory
from lp.testing.dbuser import dbuser
from lp.testing.layers import LaunchpadZopelessLayer
from lp.translations.interfaces.side import TranslationSide


class TestVerifyPOFileStats(TestCaseWithFactory):
    layer = LaunchpadZopelessLayer

    def _makeNonemptyPOFile(self, side):
        pofile = self.factory.makePOFile(side=side)
        self.factory.makePOTMsgSet(potemplate=pofile.potemplate, sequence=1)
        return pofile

    def test_database_permissions(self):
        # The script has sufficient database privileges to do its job.
        sides = [TranslationSide.UPSTREAM, TranslationSide.UBUNTU]
        pofiles = [
            self._makeNonemptyPOFile(side) for side in sides]
        with dbuser('pofilestats'):
            for pofile in pofiles:
                pofile.updateStatistics()
