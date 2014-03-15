# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Classes that manage FeatureFlagChangelogEntry items."""

__all__ = [
    'ChangeLog',
    ]

__metaclass__ = type

from storm.locals import Desc

from lp.services.features.model import (
    FeatureFlagChangelogEntry,
    getFeatureStore,
    )


class ChangeLog:
    """A log of `FeatureFlagChangelogEntry` items."""

    @staticmethod
    def get():
        """return a result set of `FeatureFlagChangelogEntry` items."""
        store = getFeatureStore()
        rs = store.find(FeatureFlagChangelogEntry)
        rs.order_by(Desc(FeatureFlagChangelogEntry.date_changed))
        return rs

    @staticmethod
    def append(diff, comment, person):
        """Append a FeatureFlagChangelogEntry to the ChangeLog."""
        store = getFeatureStore()
        feature_flag_change = FeatureFlagChangelogEntry(
            diff, comment, person)
        store.add(feature_flag_change)
        return feature_flag_change
