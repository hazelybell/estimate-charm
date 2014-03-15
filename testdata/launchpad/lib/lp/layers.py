# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Define the layers used in Launchpad.

Also define utilities that manipulate layers.
"""

__metaclass__ = type

from lazr.restful.interfaces import IWebServiceLayer
from zope.interface import (
    alsoProvides,
    directlyProvidedBy,
    directlyProvides,
    Interface,
    )
from zope.publisher.interfaces.browser import (
    IBrowserRequest,
    IBrowserSkinType,
    IDefaultBrowserLayer,
    )


def setAdditionalLayer(request, layer):
    directlyProvides(request, directlyProvidedBy(request) + layer)


def setFirstLayer(request, layer):
    directlyProvides(request, layer, directlyProvidedBy(request))


class LaunchpadLayer(IBrowserRequest, IDefaultBrowserLayer):
    """The `LaunchpadLayer` layer."""


class DebugLayer(Interface):
    """The `DebugLayer` layer.

    This derives from Interface beacuse it is just a marker that this
    is a debug-related request.
    """


class TestOpenIDLayer(LaunchpadLayer):
    """The `TestOpenIDLayer` layer."""


class PageTestLayer(LaunchpadLayer):
    """The `PageTestLayer` layer. (need to register a 404 view for this and
    for the debug page too.  and make the debugview a base class in the
    debug view and make system error, not found and unauthorized and
    forbidden views.

    This layer is applied to the request that is used for running page tests.
    Pages registered with this layer are accessible to pagetests but return
    404s when visited interactively, so this should be used only for pages we
    want to maintain but not expose to users.

    The SystemErrorView base class looks at the request to see if it provides
    this interface.  If so, it renders tracebacks as plain text.
    """
# A few tests register this interface directly as a layer, bypassing the zcml
# machinery.  This means that they don't get the proper SkinType interface
# applied to them.  We add it here for convenience.
alsoProvides(PageTestLayer, IBrowserSkinType)


class FeedsLayer(LaunchpadLayer):
    """The `FeedsLayer` Layer."""


class WebServiceLayer(IWebServiceLayer, LaunchpadLayer):
    """The layer for web service requests."""
