# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Display `TranslationTemplateBuild`s."""

__metaclass__ = type
__all__ = [
    'TranslationTemplatesBuildView',
    ]

from zope.component import getUtility

from lp.app.browser.tales import DateTimeFormatterAPI
from lp.registry.interfaces.productseries import IProductSeriesSet
from lp.services.webapp.publisher import LaunchpadView
from lp.translations.model.translationtemplatesbuildjob import (
    HARDCODED_TRANSLATIONTEMPLATESBUILD_SCORE,
    )


class TranslationTemplatesBuildView(LaunchpadView):
    """View for `TranslationTemplatesBuild`."""

    def getTargets(self):
        """`ProducSeries` that will consume the generated templates."""
        utility = getUtility(IProductSeriesSet)
        return list(
            utility.findByTranslationsImportBranch(self.context.branch))

    def _renderTime(self, time):
        """Represent `time` as HTML."""
        formatter = DateTimeFormatterAPI(time)
        return """<span title="%s">%s</span>""" % (
            formatter.datetime(), formatter.approximatedate())

    def initalize(self):
        """See `LaunchpadView`."""
        self.last_score = HARDCODED_TRANSLATIONTEMPLATESBUILD_SCORE

    def renderDispatchTime(self):
        """Give start-time information for this build, as HTML."""
        # Once we do away with BuildQueue, and the relevant information
        # is moved into the new model, we'll be able to give estimated
        # start times as well.
        if self.context.date_started is None:
            return "Not started yet."
        else:
            return "Started " + self._renderTime(self.context.date_started)

    def renderFinishTime(self):
        """Give completion time information for this build, as HTML."""
        # Once we do away with BuildQueue, and the relevant information
        # is moved into the new model, we'll be able to give estimated
        # completion times as well.
        if self.context.date_finished is None:
            if self.context.date_started is None:
                return ''
            else:
                return "Not finished yet."
        else:
            return "Finished " + self._renderTime(self.context.date_finished)
