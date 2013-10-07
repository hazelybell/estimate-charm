# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Functions to help with the testing of views."""

__metaclass__ = type
__all__ = [
    'create_view',
    'create_initialized_view',
    ]

from zope.component import (
    getMultiAdapter,
    getUtility,
    )
from zope.security.management import (
    endInteraction,
    newInteraction,
    )

from lp.layers import setFirstLayer
from lp.services.webapp.interfaces import (
    ICanonicalUrlData,
    IPlacelessAuthUtility,
    )
from lp.services.webapp.publisher import layer_for_rootsite
from lp.services.webapp.servers import (
    LaunchpadTestRequest,
    WebServiceTestRequest,
    )


def create_view(context, name, form=None, layer=None, server_url=None,
                method='GET', principal=None, query_string='', cookie='',
                request=None, path_info='/', current_request=False,
                rootsite=None, **kwargs):
    """Return a view based on the given arguments.

    :param context: The context for the view.
    :param name: The web page the view should handle.
    :param form: A dictionary with the form keys.
    :param layer: The layer where the page we are interested in is located.
    :param server_url: The URL from where this request was done.
    :param method: The method used in the request. Defaults to 'GET'.
    :param principal: The principal for the request, default to the
        unauthenticated principal.
    :param query_string: The query string for the request.
    :param cookie: The HTTP_COOKIE value for the request.
    :param request: Use this request instead of creating a new one.
    :param path_info: The PATH_INFO value for the request.
    :param current_request: If True, the request will be set as the current
        interaction.
    :param **kwargs: Any other parameter for the request.
    :return: The view class for the given context and the name.
    """
    if request is None:
        request = LaunchpadTestRequest(
            form=form, SERVER_URL=server_url, QUERY_STRING=query_string,
            HTTP_COOKIE=cookie, method=method, PATH_INFO=path_info, **kwargs)
    if principal is not None:
        request.setPrincipal(principal)
    else:
        request.setPrincipal(
            getUtility(IPlacelessAuthUtility).unauthenticatedPrincipal())
    if layer is None:
        # If a layer hasn't been specified, try to get the layer for the
        # rootsite.
        if rootsite is None:
            # If we haven't been told a site, try to get it from the canonical
            # url data of the object.
            obj_urldata = ICanonicalUrlData(context, None)
            if obj_urldata is not None:
                rootsite = obj_urldata.rootsite
        layer = layer_for_rootsite(rootsite)
    if layer is not None:
        setFirstLayer(request, layer)
    if current_request:
        endInteraction()
        newInteraction(request)
    return getMultiAdapter((context, request), name=name)


def create_initialized_view(context, name, form=None, layer=None,
                            server_url=None, method=None, principal=None,
                            query_string=None, cookie=None, request=None,
                            path_info='/', rootsite=None,
                            current_request=False, **kwargs):
    """Return a view that has already been initialized."""
    if method is None:
        if form is None:
            method = 'GET'
        else:
            method = 'POST'
    view = create_view(
        context, name, form, layer, server_url, method, principal,
        query_string, cookie, request, path_info, rootsite=rootsite,
        current_request=current_request, **kwargs)
    view.initialize()
    return view


def create_webservice_error_view(error):
    """Return a view of the error with a webservice request."""
    request = WebServiceTestRequest()
    return getMultiAdapter((error, request), name='index.html')
