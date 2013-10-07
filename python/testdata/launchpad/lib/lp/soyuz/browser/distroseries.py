# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'DistroSeriesBuildsView',
    'DistroSeriesQueueView',
    ]

from lp.soyuz.browser.build import BuildRecordsView
from lp.soyuz.browser.queue import QueueItemsView


class DistroSeriesBuildsView(BuildRecordsView):
    """A View to show an `IDistroSeries` object's builds."""

    @property
    def show_arch_selector(self):
        """Display the architecture selector.

        See `BuildRecordsView` for further details."""
        return True


class DistroSeriesQueueView(QueueItemsView):
    """A View to show an `IDistroSeries` object's uploads."""

    label = 'Upload queue'
    page_title = label
