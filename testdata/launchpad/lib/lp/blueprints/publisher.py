# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Blueprints' custom publication."""

__metaclass__ = type
__all__ = [
    'BlueprintsBrowserRequest',
    'BlueprintsLayer',
    'blueprints_request_publication_factory',
    ]


from zope.interface import implements
from zope.publisher.interfaces.browser import (
    IBrowserRequest,
    IDefaultBrowserLayer,
    )

from lp.services.webapp.publication import LaunchpadBrowserPublication
from lp.services.webapp.servers import (
    LaunchpadBrowserRequest,
    VHostWebServiceRequestPublicationFactory,
    )


class BlueprintsLayer(IBrowserRequest, IDefaultBrowserLayer):
    """The Blueprints layer."""


class BlueprintsBrowserRequest(LaunchpadBrowserRequest):
    """Instances of BlueprintsBrowserRequest provide `BlueprintsLayer`."""
    implements(BlueprintsLayer)


def blueprints_request_publication_factory():
    return VHostWebServiceRequestPublicationFactory(
        'blueprints', BlueprintsBrowserRequest, LaunchpadBrowserPublication)
