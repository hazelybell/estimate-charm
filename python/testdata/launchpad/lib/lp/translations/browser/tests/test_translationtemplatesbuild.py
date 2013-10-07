# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""`TranslationTemplatesBuild` view tests."""

__metaclass__ = type

from datetime import datetime

from pytz import utc
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.buildmaster.enums import BuildStatus
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer
from lp.translations.browser.translationtemplatesbuild import (
    TranslationTemplatesBuildView,
    )
from lp.translations.interfaces.translations import (
    TranslationsBranchImportMode,
    )
from lp.translations.interfaces.translationtemplatesbuild import (
    ITranslationTemplatesBuildSource,
    )


def now():
    """Now."""
    return datetime.now(utc)


class TestTranslationTemplatesBuild(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def _makeBuild(self, branch=None):
        """Create a `TranslationTemplatesBuild`."""
        if branch is None:
            branch = self.factory.makeBranch()
        return getUtility(ITranslationTemplatesBuildSource).create(branch)

    def _makeView(self, build=None):
        """Create a view for testing."""
        if build is None:
            build = self._makeBuild()
        request = LaunchpadTestRequest()
        view = TranslationTemplatesBuildView(build, request)
        view.initialize()
        return view

    def _makeProductSeries(self, branch):
        """Create a `ProductSeries` that imports templates from `branch`."""
        productseries = self.factory.makeProductSeries()
        removeSecurityProxy(productseries).branch = branch
        removeSecurityProxy(productseries).translations_autoimport_mode = (
            TranslationsBranchImportMode.IMPORT_TEMPLATES)
        return productseries

    def test_getTargets_finds_target(self):
        productseries = self._makeProductSeries(self.factory.makeBranch())
        view = self._makeView(self._makeBuild(productseries.branch))
        self.assertContentEqual([productseries], view.getTargets())

    def test_renderDispatchTime(self):
        build = self._makeBuild()
        view = self._makeView(build)
        self.assertEqual("Not started yet.", view.renderDispatchTime())
        build.updateStatus(BuildStatus.BUILDING)
        self.assertIn("Started", view.renderDispatchTime())

    def test_renderFinishTime(self):
        """Finish time is shown once build has started."""
        build = self._makeBuild()
        view = self._makeView(build)
        self.assertEqual("", view.renderFinishTime())
        build.updateStatus(BuildStatus.BUILDING)
        self.assertEqual("Not finished yet.", view.renderFinishTime())
        build.updateStatus(BuildStatus.FULLYBUILT)
        self.assertIn("Finished", view.renderFinishTime())
