# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""A class for the top-level link to the services factory."""

__metaclass__ = type
__all__ = [
    'IServicesLink',
    'ServicesLink',
    ]

from lazr.restful.interfaces import ITopLevelEntryLink
from zope.interface import implements

from lp.app.interfaces.services import IServiceFactory
from lp.services.webapp.interfaces import ICanonicalUrlData


class IServicesLink(ITopLevelEntryLink, ICanonicalUrlData):
    """A marker interface."""


class ServicesLink:
    """The top-level link to the services factory."""
    implements(IServicesLink)

    link_name = 'services'
    entry_type = IServiceFactory

    inside = None
    path = 'services'
    rootsite = 'api'
