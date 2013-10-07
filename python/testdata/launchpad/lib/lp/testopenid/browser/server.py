# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test OpenID server."""

__metaclass__ = type
__all__ = [
    'PersistentIdentityView',
    'TestOpenIDApplicationNavigation',
    'TestOpenIDIndexView',
    'TestOpenIDLoginView',
    'TestOpenIDRootUrlData',
    'TestOpenIDView',
    ]

from datetime import timedelta

from openid import oidutil
from openid.extensions.sreg import (
    SRegRequest,
    SRegResponse,
    )
from openid.server.server import (
    CheckIDRequest,
    ENCODE_HTML_FORM,
    Server,
    )
from openid.store.memstore import MemoryStore
from z3c.ptcompat import ViewPageTemplateFile
from zope.authentication.interfaces import IUnauthenticatedPrincipal
from zope.component import getUtility
from zope.interface import implements
from zope.security.proxy import isinstance as zisinstance
from zope.session.interfaces import ISession

from lp import _
from lp.app.browser.launchpadform import (
    action,
    LaunchpadFormView,
    )
from lp.app.errors import UnexpectedFormData
from lp.registry.interfaces.person import IPerson
from lp.services.identity.interfaces.account import (
    AccountStatus,
    IAccountSet,
    )
from lp.services.openid.browser.openiddiscovery import (
    XRDSContentNegotiationMixin,
    )
from lp.services.propertycache import (
    cachedproperty,
    get_property_cache,
    )
from lp.services.webapp import LaunchpadView
from lp.services.webapp.interfaces import (
    ICanonicalUrlData,
    IPlacelessLoginSource,
    )
from lp.services.webapp.login import (
    allowUnauthenticatedSession,
    logInPrincipal,
    logoutPerson,
    )
from lp.services.webapp.publisher import (
    Navigation,
    stepthrough,
    )
from lp.testopenid.interfaces.server import (
    get_server_url,
    ITestOpenIDApplication,
    ITestOpenIDLoginForm,
    ITestOpenIDPersistentIdentity,
    )


OPENID_REQUEST_SESSION_KEY = 'testopenid.request'
SESSION_PKG_KEY = 'TestOpenID'
openid_store = MemoryStore()


# Shut up noisy OpenID library
oidutil.log = lambda message, level=0: None


class TestOpenIDRootUrlData:
    """`ICanonicalUrlData` for the test OpenID provider."""

    implements(ICanonicalUrlData)

    path = ''
    inside = None
    rootsite = 'testopenid'

    def __init__(self, context):
        self.context = context


class TestOpenIDApplicationNavigation(Navigation):
    """Navigation for `ITestOpenIDApplication`"""
    usedfor = ITestOpenIDApplication

    @stepthrough('+id')
    def traverse_id(self, name):
        """Traverse to persistent OpenID identity URLs."""
        try:
            account = getUtility(IAccountSet).getByOpenIDIdentifier(name)
        except LookupError:
            account = None
        if account is None or account.status != AccountStatus.ACTIVE:
            return None
        return ITestOpenIDPersistentIdentity(account)


class TestOpenIDXRDSContentNegotiationMixin(XRDSContentNegotiationMixin):
    """Custom XRDSContentNegotiationMixin that overrides openid_server_url."""

    @property
    def openid_server_url(self):
        """The OpenID Server endpoint URL for Launchpad."""
        return get_server_url()


class TestOpenIDIndexView(
        TestOpenIDXRDSContentNegotiationMixin, LaunchpadView):
    template = ViewPageTemplateFile("../templates/application-index.pt")
    xrds_template = ViewPageTemplateFile("../templates/application-xrds.pt")


class OpenIDMixin:
    """A mixin with OpenID helper methods."""

    openid_request = None

    def __init__(self, context, request):
        super(OpenIDMixin, self).__init__(context, request)
        self.server_url = get_server_url()
        self.openid_server = Server(openid_store, self.server_url)

    @property
    def user_identity_url(self):
        return ITestOpenIDPersistentIdentity(self.account).openid_identity_url

    def isIdentityOwner(self):
        """Return True if the user can authenticate as the given ID."""
        assert self.account is not None, "user should be logged in by now."
        return (self.openid_request.idSelect() or
                self.openid_request.identity == self.user_identity_url)

    @cachedproperty
    def openid_parameters(self):
        """A dictionary of OpenID query parameters from request."""
        query = {}
        for key, value in self.request.form.items():
            if key.startswith('openid.'):
                # All OpenID query args are supposed to be ASCII.
                query[key.encode('US-ASCII')] = value.encode('US-ASCII')
        return query

    def getSession(self):
        """Get the session data container that stores the OpenID request."""
        if IUnauthenticatedPrincipal.providedBy(self.request.principal):
            # A dance to assert that we want to break the rules about no
            # unauthenticated sessions. Only after this next line is it
            # safe to set session values.
            allowUnauthenticatedSession(
                self.request, duration=timedelta(minutes=60))
        return ISession(self.request)[SESSION_PKG_KEY]

    def restoreRequestFromSession(self):
        """Get the OpenIDRequest from our session."""
        session = self.getSession()
        cache = get_property_cache(self)
        try:
            cache.openid_parameters = session[OPENID_REQUEST_SESSION_KEY]
        except KeyError:
            raise UnexpectedFormData("No OpenID request in session")

        # Decode the request parameters and create the request object.
        self.openid_request = self.openid_server.decodeRequest(
            self.openid_parameters)
        assert zisinstance(self.openid_request, CheckIDRequest), (
            'Invalid OpenIDRequest in session')

    def saveRequestInSession(self):
        """Save the OpenIDRequest in our session."""
        query = self.openid_parameters
        assert query.get('openid.mode') == 'checkid_setup', (
            'Can only serialise checkid_setup OpenID requests')

        session = self.getSession()
        # If this was meant for use in production we'd have to use a nonce
        # as the key when storing the openid request in the session, but as
        # it's meant to run only on development instances we can simplify
        # things a bit by storing the openid request using a well known key.
        session[OPENID_REQUEST_SESSION_KEY] = query

    def renderOpenIDResponse(self, openid_response):
        """Return a web-suitable response constructed from openid_response."""
        webresponse = self.openid_server.encodeResponse(openid_response)
        response = self.request.response
        response.setStatus(webresponse.code)
        # encodeResponse doesn't generate a content-type, help it out
        if (webresponse.code == 200 and webresponse.body
                and openid_response.whichEncoding() == ENCODE_HTML_FORM):
            response.setHeader('content-type', 'text/html')
        for header, value in webresponse.headers.items():
            response.setHeader(header, value)
        return webresponse.body

    def createPositiveResponse(self):
        """Create a positive assertion OpenIDResponse.

        This method should be called to create the response to
        successful checkid requests.

        If the trust root for the request is in openid_sreg_trustroots,
        then additional user information is included with the
        response.
        """
        assert self.account is not None, (
            'Must be logged in for positive OpenID response')
        assert self.openid_request is not None, (
            'No OpenID request to respond to.')

        if not self.isIdentityOwner():
            return self.createFailedResponse()

        if self.openid_request.idSelect():
            response = self.openid_request.answer(
                True, identity=self.user_identity_url)
        else:
            response = self.openid_request.answer(True)

        person = IPerson(self.account)
        sreg_fields = dict(
            nickname=person.name,
            email=person.preferredemail.email,
            fullname=self.account.displayname)
        sreg_request = SRegRequest.fromOpenIDRequest(self.openid_request)
        sreg_response = SRegResponse.extractResponse(
            sreg_request, sreg_fields)
        response.addExtension(sreg_response)

        return response

    def createFailedResponse(self):
        """Create a failed assertion OpenIDResponse.

        This method should be called to create the response to
        unsuccessful checkid requests.
        """
        assert self.openid_request is not None, (
            'No OpenID request to respond to.')
        response = self.openid_request.answer(False, self.server_url)
        return response


class TestOpenIDView(OpenIDMixin, LaunchpadView):
    """An OpenID Provider endpoint for Launchpad.

    This class implements an OpenID endpoint using the python-openid
    library.  In addition to the normal modes of operation, it also
    implements the OpenID 2.0 identifier select mode.

    Note that the checkid_immediate mode is not supported.
    """

    def render(self):
        """Handle all OpenID requests and form submissions."""
        # NB: Will be None if there are no parameters in the request.
        self.openid_request = self.openid_server.decodeRequest(
            self.openid_parameters)

        if self.openid_request.mode == 'checkid_setup':
            referer = self.request.get("HTTP_REFERER")
            if referer:
                self.request.response.setCookie("openid_referer", referer)

            # Log the user out and present the login page so that they can
            # authenticate as somebody else if they want.
            logoutPerson(self.request)
            return self.showLoginPage()
        elif self.openid_request.mode == 'checkid_immediate':
            raise UnexpectedFormData(
                'We do not handle checkid_immediate requests.')
        else:
            return self.renderOpenIDResponse(
                self.openid_server.handleRequest(self.openid_request))

    def showLoginPage(self):
        """Render the login dialog."""
        self.saveRequestInSession()
        return TestOpenIDLoginView(self.context, self.request)()


class TestOpenIDLoginView(OpenIDMixin, LaunchpadFormView):
    """A view for users to log into the OpenID provider."""

    page_title = "Login"
    schema = ITestOpenIDLoginForm
    action_url = '+auth'
    template = ViewPageTemplateFile("../templates/auth.pt")

    def initialize(self):
        self.restoreRequestFromSession()
        super(TestOpenIDLoginView, self).initialize()

    def validate(self, data):
        """Check that the email address is valid for login."""
        loginsource = getUtility(IPlacelessLoginSource)
        principal = loginsource.getPrincipalByLogin(data['email'])
        if principal is None:
            self.addError(
                _("Unknown email address."))

    @action('Continue', name='continue')
    def continue_action(self, action, data):
        email = data['email']
        principal = getUtility(IPlacelessLoginSource).getPrincipalByLogin(
            email)
        logInPrincipal(self.request, principal, email)
        # Update the attribute holding the cached user.
        self._account = principal.account
        return self.renderOpenIDResponse(self.createPositiveResponse())


class PersistentIdentityView(
        TestOpenIDXRDSContentNegotiationMixin, LaunchpadView):
    """Render the OpenID identity page."""

    xrds_template = ViewPageTemplateFile(
        "../templates/persistentidentity-xrds.pt")
