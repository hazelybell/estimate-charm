# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__all__ = [
    'IFeedsApplication',
    ]


from lp.services.webapp.interfaces import ILaunchpadApplication


class IFeedsApplication(ILaunchpadApplication):
    """Launchpad Feeds application root."""
