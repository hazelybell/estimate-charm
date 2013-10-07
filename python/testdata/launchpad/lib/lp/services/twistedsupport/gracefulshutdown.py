# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Utilities for graceful shutdown of Twisted services."""

__metaclass__ = type
__all__ = [
    'ConnTrackingFactoryWrapper',
    'ShutdownCleanlyService',
    'ServerAvailableResource',
    'OrderedMultiService',
    ]


from twisted.application import (
    service,
    strports,
    )
from twisted.internet.defer import (
    Deferred,
    gatherResults,
    inlineCallbacks,
    maybeDeferred,
    )
from twisted.protocols.policies import WrappingFactory
from twisted.web import (
    resource,
    server,
    )
from zope.interface import implements


class ConnTrackingFactoryWrapper(WrappingFactory):
    """A factory decorator that tracks the current connections made by this
    factory.
    """

    def __init__(self, wrappedFactory):
        """Constructor.

        See WrappingFactory.__init__.
        """
        WrappingFactory.__init__(self, wrappedFactory)
        self.allConnectionsGone = None

    def isAvailable(self):
        """Has this factory been stopped yet?"""
        return self.allConnectionsGone is None

    def stopFactory(self):
        """See WrappingFactory.stopFactory."""
        WrappingFactory.stopFactory(self)
        self.allConnectionsGone = Deferred()
        if len(self.protocols) == 0:
            self.allConnectionsGone.callback(None)

    def unregisterProtocol(self, p):
        """See WrappingFactory.unregisterProtocol."""
        WrappingFactory.unregisterProtocol(self, p)
        if len(self.protocols) == 0:
            if self.allConnectionsGone is not None:
                self.allConnectionsGone.callback(None)


class ShutdownCleanlyService(service.MultiService):
    """A MultiService that doesn't stop until all connections of its factories
    are closed.

    This allows delaying a twistd process exiting until all clients have
    disconnected from a server, for instance.
    """

    def __init__(self, factories):
        """Constructor.

        :param factories: A collection of ConnTrackingFactoryWrapper
            instances.
        """
        self.factories = factories
        service.MultiService.__init__(self)

    def stopService(self):
        """See service.MultiService.stopService."""
        d = maybeDeferred(service.MultiService.stopService, self)
        return d.addCallback(self._cbServicesStopped)

    def _cbServicesStopped(self, ignored):
        return gatherResults([f.allConnectionsGone for f in self.factories])


class ServerAvailableResource(resource.Resource):
    """A Resource indicating if a service is available for new connections.

    A 200 response code (OK) indicates the service is available, and a 503
    (Service Not Available) indicates the service is shutting down and no new
    connections will be accepted.

    This resource accepts both HEAD and GET requests.  If the request is a GET
    this resource also reports the number of connections and their peer
    addresses in a human-friendly text/plain body.
    """

    def __init__(self, tracked_factories):
        resource.Resource.__init__(self)
        self.tracked_factories = tracked_factories

    def _render_common(self, request):
        service_available = True
        for tracked in self.tracked_factories:
            if not tracked.isAvailable():
                service_available = False
        if service_available:
            request.setResponseCode(200)
        else:
            request.setResponseCode(503)
        request.setHeader('Content-Type', 'text/plain')
        return service_available

    def render_GET(self, request):
        """Handler for GET requests.  See resource.Resource.render."""
        service_available = self._render_common(request)
        # Generate a bit of text for humans' benefit.
        tracked_connections = set()
        for tracked in self.tracked_factories:
            tracked_connections.update(tracked.protocols)
        if service_available:
            state_text = 'Available'
        else:
            state_text = 'Unavailable'
        return '%s\n\n%d connections: \n\n%s\n' % (
            state_text, len(tracked_connections),
            '\n'.join(
                [str(c.transport.getPeer()) for c in tracked_connections]))

    def render_HEAD(self, request):
        """Handler for HEAD requests.  See resource.Resource.render."""
        self._render_common(request)
        return ''


class OrderedMultiService(service.MultiService):
    """A MultiService that guarantees start and stop order.

    Services are started in the order they are attached, and stopped in in
    reverse order (waiting for each to stop before stopping the next).
    """

    implements(service.IServiceCollection)

    @inlineCallbacks
    def stopService(self):
        """See service.MultiService.stopService."""
        # intentionally skip MultiService.stopService
        service.Service.stopService(self)
        while self.services:
            svc = self.services.pop()
            yield maybeDeferred(svc.stopService)


def make_web_status_service(strport, tracking_factories):
    """Make a web site of ServerAvailableResource on a given port.

    See daemons/sftp.tac for an example use.

    :param strport: a strport describing the port the web service should
        listen on.
    :param tracking_factories: a collection of ConnTrackingFactoryWrapper
        instances.
    :returns: a service.Service
    """
    server_available_resource = ServerAvailableResource(tracking_factories)
    web_root = resource.Resource()
    web_root.putChild('', server_available_resource)
    web_factory = server.Site(web_root)
    return strports.service(strport, web_factory)
