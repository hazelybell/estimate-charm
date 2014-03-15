# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Browser views for source package builds."""

__metaclass__ = type

__all__ = [
    'SourcePackageChangelogView',
    'SourcePackageCopyrightView',
    ]

from lazr.restful.utils import smartquote
from zope.component import getUtility

from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.interfaces.distroseries import IDistroSeriesSet
from lp.registry.interfaces.distroseriesdifference import (
    IDistroSeriesDifferenceSource,
    )
from lp.services.webapp import (
    LaunchpadView,
    Navigation,
    )


class SourcePackageChangelogView(LaunchpadView):
    """View class for source package change logs."""

    page_title = "Change log"

    @property
    def label(self):
        """<h1> for the change log page."""
        return smartquote("Change logs for " + self.context.title)


class SourcePackageCopyrightView(LaunchpadView):
    """A view to display a source package's copyright information."""

    page_title = "Copyright"

    @property
    def label(self):
        """Page heading."""
        return smartquote("Copyright for " + self.context.title)


class SourcePackageDifferenceView(Navigation):
    """A view to traverse to a DistroSeriesDifference.
    """

    def traverse(self, parent_distro_name):
        parent_distro = getUtility(
            IDistributionSet).getByName(parent_distro_name)
        parent_series = getUtility(
            IDistroSeriesSet).queryByName(
                parent_distro, self.request.stepstogo.consume())
        dsd_source = getUtility(IDistroSeriesDifferenceSource)
        return dsd_source.getByDistroSeriesNameAndParentSeries(
            self.context.distroseries, self.context.name, parent_series)
