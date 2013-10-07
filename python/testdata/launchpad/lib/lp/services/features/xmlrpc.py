# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""FeatureFlagApplication allows access to information about feature flags."""

__metaclass__ = type
__all__ = [
    'IFeatureFlagApplication',
    'FeatureFlagApplication',
    ]

from zope.component import getUtility
from zope.interface import implements

from lp.registry.interfaces.person import IPersonSet
from lp.services.features.flags import FeatureController
from lp.services.features.rulesource import StormFeatureRuleSource
from lp.services.features.scopes import (
    default_scopes,
    FixedScope,
    MultiScopeHandler,
    TeamScope,
    )
from lp.services.webapp.interfaces import ILaunchpadApplication


class IFeatureFlagApplication(ILaunchpadApplication):
    """Mailing lists application root."""

    def getFeatureFlag(flag_name, username=None, scopes=()):
        """Return the value of the given feature flag.

        :param flag_name: The name of the flag to query.
        :param username: If supplied, the name of a Person to use in
            evaluating the 'team:' scope.
        :param scopes: A list of scopes to consider active.  The 'default'
            scope is always considered to be active, and does not need to be
            included here.
        """


class FeatureFlagApplication:

    implements(IFeatureFlagApplication)

    def getFeatureFlag(self, flag_name, active_scopes=()):
        scopes = list(default_scopes)
        for scope_name in active_scopes:
            if scope_name.startswith('user:'):
                person = getUtility(IPersonSet).getByName(
                    scope_name[len('user:'):])
                if person is not None:
                    scopes.append(TeamScope(lambda: person))
            else:
                scopes.append(FixedScope(scope_name))
        flag_name = unicode(flag_name)
        controller = FeatureController(
            MultiScopeHandler(scopes).lookup, StormFeatureRuleSource())
        return controller.getFlag(flag_name)
