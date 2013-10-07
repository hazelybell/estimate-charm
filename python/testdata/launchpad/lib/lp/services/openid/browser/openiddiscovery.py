# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Classes related to OpenID discovery."""

__metaclass__ = type
__all__ = [
    'XRDSContentNegotiationMixin',
    ]

from openid.yadis.accept import getAcceptable
from openid.yadis.constants import (
    YADIS_CONTENT_TYPE,
    YADIS_HEADER_NAME,
    )

from lp.services.openid.adapters.openid import CurrentOpenIDEndPoint
from lp.services.propertycache import cachedproperty
from lp.services.webapp import canonical_url


class XRDSContentNegotiationMixin:
    """A mixin that does content negotiation to support XRDS discovery."""

    enable_xrds_discovery = True

    def xrds(self):
        """Render the XRDS document for this content object."""
        self.request.response.setHeader('Content-Type', YADIS_CONTENT_TYPE)
        data = self.xrds_template()
        return data.encode('utf-8')

    def _getURL(self):
        """Return the URL as sent by the browser."""
        url = self.request.getApplicationURL() + self.request['PATH_INFO']
        query_string = self.request.get('QUERY_STRING', '')
        if query_string:
            url += '?' + query_string
        return url

    def render(self):
        """Render a page supporting XRDS discovery."""
        # While Zope doesn't care about extra slashes, such
        # differences result in different identity URLs.  To avoid
        # confusion, we redirect to our canonical URL if we aren't
        # already there.
        current_url = self._getURL()
        expected_url = canonical_url(self.context)
        if current_url != expected_url:
            self.request.response.redirect(expected_url)
            return ''

        if self.enable_xrds_discovery:
            # Tell the user agent that we do different things depending on
            # the value of the "Accept" header.
            self.request.response.setHeader('Vary', 'Accept')

            accept_content = self.request.get('HTTP_ACCEPT', '')
            acceptable = getAcceptable(accept_content,
                                       ['text/html', YADIS_CONTENT_TYPE])
            # Return the XRDS document if it is preferred to text/html.
            for mtype in acceptable:
                if mtype == 'text/html':
                    break
                elif mtype == YADIS_CONTENT_TYPE:
                    return self.xrds()
                else:
                    raise AssertionError(
                        'Unexpected acceptable content type: %s' % mtype)

            # Add a header pointing to the location of the XRDS document
            # and chain to the default render() method.
            self.request.response.setHeader(
                YADIS_HEADER_NAME, '%s/+xrds' % canonical_url(self.context))
        return super(XRDSContentNegotiationMixin, self).render()

    @cachedproperty
    def openid_server_url(self):
        """The OpenID Server endpoint URL for Launchpad."""
        return CurrentOpenIDEndPoint.getServiceURL()
