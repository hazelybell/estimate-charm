# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Helpers for testing out publication related code."""

__metaclass__ = type
__all__ = [
    'get_request_and_publication',
    'print_request_and_publication',
    'test_traverse',
    ]

from cStringIO import StringIO

from zope.app.publication.requestpublicationregistry import factoryRegistry
from zope.authentication.interfaces import IUnauthenticatedPrincipal
from zope.component import (
    getGlobalSiteManager,
    getUtility,
    )
from zope.interface import providedBy
from zope.publisher.interfaces.browser import IDefaultSkin
from zope.security.management import restoreInteraction
from zope.security.proxy import removeSecurityProxy

import lp.layers as layers
from lp.services.webapp import urlsplit
from lp.services.webapp.interaction import (
    get_current_principal,
    setupInteraction,
    )
from lp.services.webapp.interfaces import IOpenLaunchBag
from lp.services.webapp.servers import ProtocolErrorPublication

# Defines an helper function that returns the appropriate
# IRequest and IPublication.
def get_request_and_publication(host='localhost', port=None,
                                method='GET', mime_type='text/html',
                                in_stream='', extra_environment=None):
    """Helper method that return the IRequest and IPublication for a request.

    This method emulates what the Zope publisher would do to find the request
    and publication class for a particular environment.
    """
    environment = {'HTTP_HOST': host,
                   'REQUEST_METHOD': method,
                   'SERVER_PORT': port,
                   'CONTENT_TYPE': mime_type}
    if extra_environment is not None:
        environment.update(extra_environment)
    launchpad_factory = factoryRegistry.lookup(
        method, mime_type, environment)
    request_factory, publication_factory = launchpad_factory()
    request = request_factory(StringIO(in_stream), environment)
    # Since Launchpad doesn't use ZODB, we use None here.
    publication = publication_factory(None)
    return request, publication


def print_request_and_publication(host='localhost', port=None,
                                  method='GET',
                                  mime_type='text/html',
                                  extra_environment=None):
    """Helper giving short names for the request and publication."""
    request, publication = get_request_and_publication(
        host, port, method, mime_type,
        extra_environment=extra_environment)
    print type(request).__name__.split('.')[-1]
    publication_classname = type(publication).__name__.split('.')[-1]
    if isinstance(publication, ProtocolErrorPublication):
        print "%s: status=%d" % (
            publication_classname, publication.status)
        for name, value in publication.headers.items():
            print "  %s: %s" % (name, value)
    else:
        print publication_classname


def test_traverse(url):
    """Traverse the url in the same way normal publishing occurs.

    Returns a tuple of (object, view, request) where:
      object is the last model object in the traversal chain
      view is the defined view for the object at the specified url (if
        the url didn't directly specify a view, then the view is the
        default view for the object.
      request is the request object resulting from the traversal.  This
        contains a populated traversed_objects list just as a browser
        request would from a normal call into the app servers.

    This call uses the currently logged in user, and does not start a new
    transaction.
    """
    url_parts = urlsplit(url)
    server_url = '://'.join(url_parts[0:2])
    path_info = url_parts[2]
    request, publication = get_request_and_publication(
        host=url_parts[1], extra_environment={
            'SERVER_URL': server_url,
            'PATH_INFO': path_info})

    request.setPublication(publication)
    # We avoid calling publication.beforePublication because this starts a new
    # transaction, which causes an abort of the existing transaction, and the
    # removal of any created and uncommitted objects.

    # Set the default layer.
    adapters = getGlobalSiteManager().adapters
    layer = adapters.lookup((providedBy(request),), IDefaultSkin, '')
    if layer is not None:
        layers.setAdditionalLayer(request, layer)

    principal = get_current_principal()

    if IUnauthenticatedPrincipal.providedBy(principal):
        login = None
    else:
        login = principal.person
    setupInteraction(principal, login, request)

    getUtility(IOpenLaunchBag).clear()
    app = publication.getApplication(request)
    view = request.traverse(app)
    # Find the object from the view instead on relying that it stays
    # in the traversed_objects stack. That doesn't apply to the web
    # service for example.
    try:
        obj = removeSecurityProxy(view).context
    except AttributeError:
        # But sometime the view didn't store the context...
        # Use the last traversed object in these cases.
        obj = request.traversed_objects[-2]

    restoreInteraction()

    return obj, view, request
