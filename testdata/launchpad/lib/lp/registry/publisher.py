# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""ILaunchpadContainer adapters."""

__metaclass__ = type
__all__ = [
    'LaunchpadProductContainer',
    'LaunchpadDistributionSourcePackageContainer',
    ]


from lp.services.webapp.publisher import LaunchpadContainer


class LaunchpadProductContainer(LaunchpadContainer):

    def isWithin(self, scope):
        """Is this product within the given scope?

        A product is within itself or its project.
        """

        return scope == self.context or scope == self.context.project


class LaunchpadDistributionSourcePackageContainer(LaunchpadContainer):

    def isWithin(self, scope):
        """Is this distribution source package within the given scope?

        A distribution source package is within its distribution.
        """
        return scope == self.context or scope == self.context.distribution
