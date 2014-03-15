# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Factory used to get named services."""

__metaclass__ = type
__all__ = [
    'ServiceFactory',
    ]

from zope.component import getUtility
from zope.interface import implements

from lp.app.interfaces.services import (
    IService,
    IServiceFactory,
    )
from lp.services.webapp.publisher import Navigation


class ServiceFactory(Navigation):
    """Creates a named service.

    Services are traversed via urls of the form /services/<name>
    Implementation classes are registered as named zope utilities.
    """

    implements(IServiceFactory)

    def __init__(self):
        super(ServiceFactory, self).__init__(None)

    def traverse(self, name):
        return self.getService(name)

    def getService(self, service_name):
        return getUtility(IService, service_name)
