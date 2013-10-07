# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Helpers for TestOpenID page tests."""

__metaclass__ = type
__all__ = [
    'complete_from_browser',
    'EchoView',
    'make_identifier_select_endpoint',
    'PublisherFetcher',
    ]

import socket
from StringIO import StringIO
import sys
import urllib2

from openid import fetchers
from openid.consumer.discover import (
    OPENID_IDP_2_0_TYPE,
    OpenIDServiceEndpoint,
    )
from zope.testbrowser.testing import PublisherConnection

from lp.services.webapp import LaunchpadView
from lp.testopenid.interfaces.server import get_server_url


class EchoView(LaunchpadView):
    """A view which just echoes its form arguments in the response."""

    def render(self):
        out = StringIO()
        print >> out, 'Request method: %s' % self.request.method
        keys = sorted(self.request.form.keys())
        for key in keys:
            print >> out, '%s:%s' % (key, self.request.form[key])
        return out.getvalue()


# Grabbed from zope.testbrowser 3.7.0a1, as more recent
# PublisherHTTPHandlers are for mechanize, so python-openid breaks.
class PublisherHTTPHandler(urllib2.HTTPHandler):
    """Special HTTP handler to use the Zope Publisher."""

    def http_request(self, req):
        # look at data and set content type
        if req.has_data():
            data = req.get_data()
            if isinstance(data, dict):
                req.add_data(data['body'])
                req.add_unredirected_header('Content-type',
                                            data['content-type'])
        return urllib2.AbstractHTTPHandler.do_request_(self, req)

    https_request = http_request

    def http_open(self, req):
        """Open an HTTP connection having a ``urllib2`` request."""
        # Here we connect to the publisher.
        if sys.version_info > (2, 6) and not hasattr(req, 'timeout'):
            # Workaround mechanize incompatibility with Python
            # 2.6. See: LP #280334
            req.timeout = socket._GLOBAL_DEFAULT_TIMEOUT
        return self.do_open(PublisherConnection, req)

    https_open = http_open


class PublisherFetcher(fetchers.Urllib2Fetcher):
    """An `HTTPFetcher` that passes requests on to the Zope publisher."""
    def __init__(self):
        super(PublisherFetcher, self).__init__()
        self.opener = urllib2.build_opener(PublisherHTTPHandler)

    def urlopen(self, request):
        request.add_header('X-zope-handle-errors', True)
        return self.opener.open(request)


def complete_from_browser(consumer, browser):
    """Complete OpenID request based on output of +echo.

    :param consumer: an OpenID `Consumer` instance.
    :param browser: a Zope testbrowser `Browser` instance.

    This function parses the body of the +echo view into a set of query
    arguments representing the OpenID response.
    """
    assert browser.contents.startswith('Request method'), (
        "Browser contents does not look like it came from +echo")
    # Skip the first line.
    query = dict(line.split(':', 1)
                 for line in browser.contents.splitlines()[1:])

    response = consumer.complete(query, browser.url)
    return response


def make_identifier_select_endpoint():
    """Create an endpoint for use in OpenID identifier select mode."""
    endpoint = OpenIDServiceEndpoint()
    endpoint.server_url = get_server_url()
    endpoint.type_uris = [OPENID_IDP_2_0_TYPE]
    return endpoint
