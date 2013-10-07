#!/usr/bin/python
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from twisted.web.resource import Resource
from twisted.web.server import NOT_DONE_YET


class DistributionMirrorTestHTTPServer(Resource):
    """An HTTP server used to test the DistributionMirror probe script.

    This server will behave in a different way depending on the path that is
    accessed. These are the possible paths and how the server behaves for each
    of them:

    :valid-mirror/*: Respond with a '200 OK' status.

    :timeout: Do not respond, causing the client to keep waiting.

    :error: Respond with a '500 Internal Server Error' status.

    :redirect-to-valid-mirror/*: Respond with a '302 Found' status,
        redirecting to http://localhost:%(port)s/valid-mirror/*.

    :redirect-infinite-loop: Respond with a '302 Found' status, redirecting
        to http://localhost:%(port)s/redirect-infinite-loop.

    :redirect-unknown-url-scheme: Respond with a '302 Found' status,
        redirecting to ssh://localhost/redirect-unknown-url-scheme.

    Any other path will cause the server to respond with a '404 Not Found'
    status.
    """

    def getChild(self, name, request):
        port = request.getHost().port
        if name == 'valid-mirror':
            leaf = DistributionMirrorTestHTTPServer()
            leaf.isLeaf = True
            return leaf
        elif name == 'timeout':
            return NeverFinishResource()
        elif name == 'error':
            return FiveHundredResource()
        elif name == 'redirect-to-valid-mirror':
            assert request.path != name, (
                'When redirecting to a valid mirror the path must have more '
                'than one component.')
            remaining_path = request.path.replace('/%s' % name, '')
            leaf = RedirectingResource(
                'http://localhost:%s/valid-mirror%s' % (port, remaining_path))
            leaf.isLeaf = True
            return leaf
        elif name == 'redirect-infinite-loop':
            return RedirectingResource(
                'http://localhost:%s/redirect-infinite-loop' % port)
        elif name == 'redirect-unknown-url-scheme':
            return RedirectingResource(
                'ssh://localhost/redirect-unknown-url-scheme')
        else:
            return Resource.getChild(self, name, request)

    def render_GET(self, request):
        return "Hi"


class RedirectingResource(Resource):

    def __init__(self, redirection_url):
        self.redirection_url = redirection_url
        Resource.__init__(self)

    def render_GET(self, request):
        request.redirect(self.redirection_url)
        request.write('Get Lost')


class NeverFinishResource(Resource):
    def render_GET(self, request):
        return NOT_DONE_YET


class FiveHundredResource(Resource):
    def render_GET(self, request):
        request.setResponseCode(500)
        request.write('ASPLODE!!!')
        return NOT_DONE_YET
