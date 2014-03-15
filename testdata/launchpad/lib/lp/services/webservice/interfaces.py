# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
"""Interfaces pertaining to the launchpad application.

Note that these are not interfaces to application content objects.
"""
__metaclass__ = type

from lazr.restful.interfaces import IServiceRootResource

from lp.services.webapp.interfaces import ILaunchpadApplication


__all__ = [
    'IWebServiceApplication',
    ]


class IWebServiceApplication(ILaunchpadApplication, IServiceRootResource):
    """Launchpad web service application root."""
