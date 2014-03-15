# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Connect Feature flags into webapp requests."""

__all__ = []

__metaclass__ = type

from lp.services.features import install_feature_controller
from lp.services.features.flags import FeatureController
from lp.services.features.rulesource import StormFeatureRuleSource
from lp.services.features.scopes import ScopesFromRequest


def start_request(event):
    """Register FeatureController."""
    event.request.features = FeatureController(
        ScopesFromRequest(event.request).lookup,
        StormFeatureRuleSource())
    install_feature_controller(event.request.features)


def end_request(event):
    """Done with this FeatureController."""
    install_feature_controller(None)
    event.request.features = None
