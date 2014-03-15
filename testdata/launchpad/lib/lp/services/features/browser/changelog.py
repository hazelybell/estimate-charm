# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Classes to view FeatureFlagChange."""

__all__ = [
    'ChangeLog',
    ]

__metaclass__ = type

from lp.services.features.changelog import ChangeLog
from lp.services.webapp.batching import BatchNavigator
from lp.services.webapp.publisher import LaunchpadView


class FeatureChangeLogView(LaunchpadView):

    page_title = label = 'Feature flag changelog'

    @property
    def changes(self):
        navigator = BatchNavigator(ChangeLog.get(), self.request, size=10)
        navigator.setHeadings('change', 'changes')
        return navigator
