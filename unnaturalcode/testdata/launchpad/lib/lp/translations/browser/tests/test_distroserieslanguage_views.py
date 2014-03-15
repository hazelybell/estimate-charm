# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from testtools.matchers import Equals
import transaction
from zope.component import getUtility

from lp.services.webapp.servers import LaunchpadTestRequest
from lp.services.worlddata.interfaces.language import ILanguageSet
from lp.testing import (
    StormStatementRecorder,
    TestCaseWithFactory,
    )
from lp.testing.layers import LaunchpadZopelessLayer
from lp.testing.matchers import HasQueryCount
from lp.translations.browser.serieslanguage import DistroSeriesLanguageView
from lp.translations.interfaces.translator import ITranslatorSet


class TestDistroSeriesLanguage(TestCaseWithFactory):
    """Test DistroSeriesLanguage view."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        # Create a distroseries that uses translations.
        TestCaseWithFactory.setUp(self)
        self.distroseries = self.factory.makeDistroSeries()
        self.language = getUtility(ILanguageSet).getLanguageByCode('sr')
        sourcepackagename = self.factory.makeSourcePackageName()
        potemplate = self.factory.makePOTemplate(
            distroseries=self.distroseries,
            sourcepackagename=sourcepackagename)
        self.factory.makePOFile('sr', potemplate)
        self.distroseries.updateStatistics(transaction)
        self.dsl = self.distroseries.distroserieslanguages[0]
        self.view = DistroSeriesLanguageView(
            self.dsl, LaunchpadTestRequest())

    def test_empty_view(self):
        self.assertEquals(self.view.translation_group, None)
        self.assertEquals(self.view.translation_team, None)
        self.assertEquals(self.view.context, self.dsl)

    def test_translation_group(self):
        group = self.factory.makeTranslationGroup(
            self.distroseries.distribution.owner, url=None)
        self.distroseries.distribution.translationgroup = group
        self.view = DistroSeriesLanguageView(
            self.dsl, LaunchpadTestRequest())
        self.view.initialize()
        self.assertEquals(self.view.translation_group, group)

    def test_translation_team(self):
        # Just having a group doesn't mean there's a translation
        # team as well.
        group = self.factory.makeTranslationGroup(
            self.distroseries.distribution.owner, url=None)
        self.distroseries.distribution.translationgroup = group
        self.assertEquals(self.view.translation_team, None)

        # Setting a translator for this languages makes it
        # appear as the translation_team.
        team = self.factory.makeTeam()
        translator = getUtility(ITranslatorSet).new(
            group, self.language, team)
        # Recreate the view because we are using a cached property.
        self.view = DistroSeriesLanguageView(
            self.dsl, LaunchpadTestRequest())
        self.view.initialize()
        self.assertEquals(self.view.translation_team, translator)

    def test_sourcepackagenames_bulk_loaded(self):
        # SourcePackageName records referenced by POTemplates
        # are bulk loaded. Accessing the sourcepackagename attribute
        # of a potemplate does not require an additional SQL query.
        self.view.initialize()
        template = self.view.batchnav.currentBatch()[0]
        with StormStatementRecorder() as recorder:
            template.sourcepackagename
        self.assertThat(recorder, HasQueryCount(Equals(0)))
