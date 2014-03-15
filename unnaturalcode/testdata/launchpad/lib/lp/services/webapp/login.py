# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
"""Stuff to do with logging in and logging out."""

__metaclass__ = type

from datetime import (
    datetime,
    timedelta,
    )
import urllib

from openid.consumer.consumer import (
    CANCEL,
    Consumer,
    FAILURE,
    SUCCESS,
    )
from openid.extensions import (
    pape,
    sreg,
    )
from openid.fetchers import (
    setDefaultFetcher,
    Urllib2Fetcher,
    )
from paste.httpexceptions import (
    HTTPBadRequest,
    HTTPException,
    )
import transaction
from z3c.ptcompat import ViewPageTemplateFile
from zope.authentication.interfaces import IUnauthenticatedPrincipal
from zope.component import (
    getSiteManager,
    getUtility,
    )
from zope.event import notify
from zope.interface import Interface
from zope.publisher.browser import BrowserPage
from zope.publisher.interfaces.http import IHTTPApplicationRequest
from zope.security.proxy import removeSecurityProxy
from zope.session.interfaces import (
    IClientIdManager,
    ISession,
    )

from lp import _
from lp.registry.interfaces.person import (
    IPersonSet,
    PersonCreationRationale,
    TeamEmailAddressError,
    )
from lp.services.config import config
from lp.services.database.policy import MasterDatabasePolicy
from lp.services.identity.interfaces.account import AccountSuspendedError
from lp.services.openid.interfaces.openidconsumer import IOpenIDConsumerStore
from lp.services.propertycache import cachedproperty
from lp.services.timeline.requesttimeline import get_request_timeline
from lp.services.webapp import canonical_url
from lp.services.webapp.error import SystemErrorView
from lp.services.webapp.interfaces import (
    CookieAuthLoggedInEvent,
    ILaunchpadApplication,
    IPlacelessAuthUtility,
    IPlacelessLoginSource,
    LoggedOutEvent,
    )
from lp.services.webapp.publisher import LaunchpadView
from lp.services.webapp.url import urlappend
from lp.services.webapp.vhosts import allvhosts


class UnauthorizedView(SystemErrorView):

    response_code = None
    page_title = 'Forbidden'

    def __call__(self):
        if IUnauthenticatedPrincipal.providedBy(self.request.principal):
            if 'loggingout' in self.request.form:
                target = '%s?loggingout=1' % self.request.URL[-2]
                self.request.response.redirect(target)
                return ''
            if self.request.method == 'POST':
                # If we got a POST then that's a problem.  We can only
                # redirect with a GET, so when we redirect after a successful
                # login, the wrong method would be used.
                # If we get a POST here, it is an application error.  We
                # must ensure that form pages require the same rights
                # as the pages that process those forms.  So, we should never
                # need to newly authenticate on a POST.
                self.request.response.setStatus(500)  # Internal Server Error
                self.request.response.setHeader('Content-type', 'text/plain')
                return ('Application error.  Unauthenticated user POSTing to '
                        'page that requires authentication.')
            # If we got any query parameters, then preserve them in the
            # new URL. Except for the BrowserNotifications
            current_url = self.request.getURL()
            while True:
                nextstep = self.request.stepstogo.consume()
                if nextstep is None:
                    break
                current_url = urlappend(current_url, nextstep)
            query_string = self.request.get('QUERY_STRING', '')
            if query_string:
                query_string = '?' + query_string
            target = self.getRedirectURL(current_url, query_string)
            # A dance to assert that we want to break the rules about no
            # unauthenticated sessions. Only after this next line is it safe
            # to use the ``addInfoNotification`` method.
            allowUnauthenticatedSession(self.request)
            self.request.response.redirect(target)
            # Maybe render page with a link to the redirection?
            return ''
        else:
            self.request.response.setStatus(403)  # Forbidden
            return self.template()

    def getRedirectURL(self, current_url, query_string):
        """Get the URL to redirect to.
        :param current_url: The URL of the current page.
        :param query_string: The string that should be appended to the current
            url.
        """
        return urlappend(current_url, '+login' + query_string)


class BasicLoginPage(BrowserPage):

    def isSameHost(self, url):
        """Returns True if the url appears to be from the same host as we are.
        """
        return url.startswith(self.request.getApplicationURL())

    def __call__(self):
        if IUnauthenticatedPrincipal.providedBy(self.request.principal):
            self.request.principal.__parent__.unauthorized(
                self.request.principal.id, self.request)
            return 'Launchpad basic auth login page'
        referer = self.request.getHeader('referer')  # Traditional w3c speling
        if referer and self.isSameHost(referer):
            self.request.response.redirect(referer)
        else:
            self.request.response.redirect(self.request.getURL(1))
        return ''


def register_basiclogin(event):
    # The +basiclogin page should only be enabled for development and tests,
    # but we can't rely on config.devmode because it's turned off for
    # AppServerLayer tests, so we (ab)use the config switch for the test
    # OpenID provider, which has similar requirements.
    if config.launchpad.enable_test_openid_provider:
        getSiteManager().registerAdapter(
            BasicLoginPage,
            required=(ILaunchpadApplication, IHTTPApplicationRequest),
            provided=Interface,
            name='+basiclogin')


# The Python OpenID package uses pycurl by default, but pycurl chokes on
# self-signed certificates (like the ones we use when developing), so we
# change the default to urllib2 here.  That's also a good thing because it
# ensures we test the same thing that we run on production.
setDefaultFetcher(Urllib2Fetcher())


class OpenIDLogin(LaunchpadView):
    """A view which initiates the OpenID handshake with our provider."""
    _openid_session_ns = 'OPENID'

    def _getConsumer(self):
        session = ISession(self.request)[self._openid_session_ns]
        openid_store = getUtility(IOpenIDConsumerStore)
        return Consumer(session, openid_store)

    def render(self):
        # Reauthentication is called for by a query string parameter.
        reauth_qs = self.request.query_string_params.get('reauth', ['0'])
        do_reauth = int(reauth_qs[0])
        if self.account is not None and not do_reauth:
            return AlreadyLoggedInView(self.context, self.request)()

        # Allow unauthenticated users to have sessions for the OpenID
        # handshake to work.
        allowUnauthenticatedSession(self.request)
        consumer = self._getConsumer()
        openid_vhost = config.launchpad.openid_provider_vhost

        timeline_action = get_request_timeline(self.request).start(
            "openid-association-begin",
            allvhosts.configs[openid_vhost].rooturl,
            allow_nested=True)
        try:
            self.openid_request = consumer.begin(
                allvhosts.configs[openid_vhost].rooturl)
        finally:
            timeline_action.finish()
        self.openid_request.addExtension(
            sreg.SRegRequest(required=['email', 'fullname']))

        # Force the Open ID handshake to re-authenticate, using
        # pape extension's max_auth_age, if the URL indicates it.
        if do_reauth:
            self.openid_request.addExtension(pape.Request(max_auth_age=0))

        assert not self.openid_request.shouldSendRedirect(), (
            "Our fixed OpenID server should not need us to redirect.")
        # Once the user authenticates with the OpenID provider they will be
        # sent to the /+openid-callback page, where we log them in, but
        # once that's done they must be sent back to the URL they were when
        # they started the login process (i.e. the current URL without the
        # '+login' bit). To do that we encode that URL as a query arg in the
        # return_to URL passed to the OpenID Provider
        starting_url = urllib.urlencode(
            [('starting_url', self.starting_url.encode('utf-8'))])
        trust_root = allvhosts.configs['mainsite'].rooturl
        return_to = urlappend(trust_root, '+openid-callback')
        return_to = "%s?%s" % (return_to, starting_url)
        form_html = self.openid_request.htmlMarkup(trust_root, return_to)

        # The consumer.begin() call above will insert rows into the
        # OpenIDAssociations table, but since this will be a GET request, the
        # transaction would be rolled back, so we need an explicit commit
        # here.
        transaction.commit()

        return form_html

    @property
    def starting_url(self):
        starting_url = self.request.getURL(1)
        query_string = "&".join([arg for arg in self.form_args])
        if query_string and query_string != 'reauth=1':
            starting_url += "?%s" % query_string
        return starting_url

    @property
    def form_args(self):
        """Iterate over form args, yielding 'key=value' strings for them.

        Exclude things such as 'loggingout' and starting with 'openid.', which
        we don't want.

        Coerces all keys and values to be ascii decode safe - either by making
        them unicode or by url quoting them. keys are known to be urldecoded
        bytestrings, so are simply re urlencoded.
        """
        for name, value in self.request.form.items():
            if name == 'loggingout' or name.startswith('openid.'):
                continue
            if isinstance(value, list):
                value_list = value
            else:
                value_list = [value]

            def restore_url(element):
                """Restore a form item to its original url representation.

                The form items are byte strings simply url decoded and
                sometimes utf8 decoded (for special confusion). They may fail
                to coerce to unicode as they can include arbitrary
                bytesequences after url decoding. We can restore their
                original url value by url quoting them again if they are a
                bytestring, with a pre-step of utf8 encoding if they were
                successfully decoded to unicode.
                """
                if isinstance(element, unicode):
                    element = element.encode('utf8')
                return urllib.quote(element)

            for value_list_item in value_list:
                value_list_item = restore_url(value_list_item)
                name = restore_url(name)
                yield "%s=%s" % (name, value_list_item)


class OpenIDCallbackView(OpenIDLogin):
    """The OpenID callback page for logging into Launchpad.

    This is the page the OpenID provider will send the user's browser to,
    after the user has authenticated on the provider.
    """

    suspended_account_template = ViewPageTemplateFile(
        'templates/login-suspended-account.pt')

    team_email_address_template = ViewPageTemplateFile(
        'templates/login-team-email-address.pt')

    def _gather_params(self, request):
        params = dict(request.form)
        for key, value in request.query_string_params.iteritems():
            if len(value) > 1:
                raise ValueError(
                    'Did not expect multi-valued fields.')
            params[key] = value[0]

        return params

    def _get_requested_url(self, request):
        requested_url = request.getURL()
        query_string = request.get('QUERY_STRING')
        if query_string is not None:
            requested_url += '?' + query_string
        return requested_url

    def initialize(self):
        params = self._gather_params(self.request)
        requested_url = self._get_requested_url(self.request)
        consumer = self._getConsumer()
        timeline_action = get_request_timeline(self.request).start(
            "openid-association-complete", '', allow_nested=True)
        try:
            self.openid_response = consumer.complete(params, requested_url)
        finally:
            timeline_action.finish()

    def login(self, person, when=None):
        loginsource = getUtility(IPlacelessLoginSource)
        # We don't have a logged in principal, so we must remove the security
        # proxy of the account's preferred email.
        email = removeSecurityProxy(person.preferredemail).email
        logInPrincipal(
            self.request, loginsource.getPrincipalByLogin(email), email, when)

    @cachedproperty
    def sreg_response(self):
        return sreg.SRegResponse.fromSuccessResponse(self.openid_response)

    def _getEmailAddressAndFullName(self):
        # Here we assume the OP sent us the user's email address and
        # full name in the response. Note we can only do that because
        # we used a fixed OP (login.launchpad.net) that includes the
        # user's email address and full name in the response when
        # asked to.  Once we start using other OPs we won't be able to
        # make this assumption here as they might not include what we
        # want in the response.
        if self.sreg_response is None:
            raise HTTPBadRequest(
                "OP didn't include an sreg extension in the response.")
        email_address = self.sreg_response.get('email')
        full_name = self.sreg_response.get('fullname')
        if email_address is None or full_name is None:
            raise HTTPBadRequest(
                "No email address or full name found in sreg response.")
        return email_address, full_name

    def processPositiveAssertion(self):
        """Process an OpenID response containing a positive assertion.

        We'll get the person and account with the given OpenID
        identifier (creating one if necessary), and then login using
        that account.

        If the account is suspended, we stop and render an error page.

        We also update the 'last_write' key in the session if we've done any
        DB writes, to ensure subsequent requests use the master DB and see
        the changes we just did.
        """
        identifier = self.openid_response.identity_url.split('/')[-1]
        identifier = identifier.decode('ascii')
        should_update_last_write = False
        # Force the use of the master database to make sure a lagged slave
        # doesn't fool us into creating a Person/Account when one already
        # exists.
        person_set = getUtility(IPersonSet)
        email_address, full_name = self._getEmailAddressAndFullName()
        try:
            person, db_updated = person_set.getOrCreateByOpenIDIdentifier(
                identifier, email_address, full_name,
                comment='when logging in to Launchpad.',
                creation_rationale=(
                    PersonCreationRationale.OWNER_CREATED_LAUNCHPAD))
            should_update_last_write = db_updated
        except AccountSuspendedError:
            return self.suspended_account_template()
        except TeamEmailAddressError:
            return self.team_email_address_template()

        with MasterDatabasePolicy():
            self.login(person)

        if should_update_last_write:
            # This is a GET request but we changed the database, so update
            # session_data['last_write'] to make sure further requests use
            # the master DB and thus see the changes we've just made.
            session_data = ISession(self.request)['lp.dbpolicy']
            session_data['last_write'] = datetime.utcnow()
        self._redirect()
        # No need to return anything as we redirect above.
        return None

    def render(self):
        if self.openid_response.status == SUCCESS:
            try:
                return self.processPositiveAssertion()
            except HTTPException as error:
                return OpenIDLoginErrorView(
                    self.context, self.request, login_error=error.message)()

        if self.account is not None:
            # The authentication failed (or was canceled), but the user is
            # already logged in, so we just add a notification message and
            # redirect.
            self.request.response.addInfoNotification(
                _(u'Your authentication failed but you were already '
                   'logged into Launchpad.'))
            self._redirect()
            # No need to return anything as we redirect above.
            return None
        else:
            return OpenIDLoginErrorView(
                self.context, self.request, self.openid_response)()

    def __call__(self):
        retval = super(OpenIDCallbackView, self).__call__()
        # The consumer.complete() call in initialize() will create entries in
        # OpenIDConsumerNonce to prevent replay attacks, but since this will
        # be a GET request, the transaction would be rolled back, so we need
        # an explicit commit here.
        transaction.commit()
        return retval

    def _redirect(self):
        target = self.request.form.get('starting_url')
        if target is None:
            # If this was a POST, then the starting_url won't be in the form
            # values, but in the query parameters instead.
            target = self.request.query_string_params.get('starting_url')
            if target is None:
                target = self.request.getApplicationURL()
            else:
                target = target[0]
        self.request.response.redirect(target, temporary_if_possible=True)


class OpenIDLoginErrorView(LaunchpadView):

    page_title = 'Error logging in'
    template = ViewPageTemplateFile("templates/login-error.pt")

    def __init__(self, context, request, openid_response=None,
                 login_error=None):
        super(OpenIDLoginErrorView, self).__init__(context, request)
        assert self.account is None, (
            "Don't try to render this page when the user is logged in.")
        if login_error:
            self.login_error = login_error
            return
        if openid_response.status == CANCEL:
            self.login_error = "User cancelled"
        elif openid_response.status == FAILURE:
            self.login_error = openid_response.message
        else:
            self.login_error = "Unknown error: %s" % openid_response


class AlreadyLoggedInView(LaunchpadView):

    page_title = 'Already logged in'
    template = ViewPageTemplateFile("templates/login-already.pt")


def isFreshLogin(request):
    """Return True if the principal login happened in the last 120 seconds."""
    session = ISession(request)
    authdata = session['launchpad.authenticateduser']
    logintime = authdata.get('logintime', None)
    if logintime is not None:
        now = datetime.utcnow()
        return logintime > now - timedelta(seconds=120)
    return False


def require_fresh_login(request, context, view_name):
    """Redirect request to login if the request is not recently logged in."""
    if not isFreshLogin(request):
        reauth_query = '+login?reauth=1'
        base_url = canonical_url(context, view_name=view_name)
        login_url = '%s/%s' % (base_url, reauth_query)
        request.response.redirect(login_url)


def logInPrincipal(request, principal, email, when=None):
    """Log the principal in. Password validation must be done in callsites."""
    # Force a fresh session, per Bug #828638. Any changes to any
    # existing session made this request will be lost, but that should
    # not be a problem as authentication must be done before
    # authorization and authorization before we do any actual work.
    client_id_manager = getUtility(IClientIdManager)
    new_client_id = client_id_manager.generateUniqueId()
    client_id_manager.setRequestId(request, new_client_id)
    session = ISession(request)
    authdata = session['launchpad.authenticateduser']
    assert principal.id is not None, 'principal.id is None!'
    request.setPrincipal(principal)
    if when is None:
        when = datetime.utcnow()
    authdata['accountid'] = int(principal.id)
    authdata['logintime'] = when
    authdata['login'] = email
    notify(CookieAuthLoggedInEvent(request, email))


def expireSessionCookie(request, client_id_manager=None,
                        delta=timedelta(minutes=10)):
    if client_id_manager is None:
        client_id_manager = getUtility(IClientIdManager)
    session_cookiename = client_id_manager.namespace
    value = request.response.getCookie(session_cookiename)['value']
    expiration = (datetime.utcnow() + delta).strftime(
        '%a, %d %b %Y %H:%M:%S GMT')
    request.response.setCookie(
        session_cookiename, value, expires=expiration)


def allowUnauthenticatedSession(request, duration=timedelta(minutes=10)):
    # As a rule, we do not want to send a cookie to an unauthenticated user,
    # because it breaks cacheing; and we do not want to create a session for
    # an unauthenticated user, because it unnecessarily consumes valuable
    # database resources. We have an assertion to ensure this. However,
    # sometimes we want to break the rules. To do this, first we set the
    # session cookie; then we assert that we only want it to last for a given
    # duration, so that, if the user does not log in, they can go back to
    # getting cached pages. Only after an unauthenticated user's session
    # cookie is set is it safe to write to it.
    if not IUnauthenticatedPrincipal.providedBy(request.principal):
        return
    client_id_manager = getUtility(IClientIdManager)
    if request.response.getCookie(client_id_manager.namespace) is None:
        client_id_manager.setRequestId(
            request, client_id_manager.getClientId(request))
        expireSessionCookie(request, client_id_manager, duration)


# XXX: salgado, 2009-02-19: Rename this to logOutPrincipal(), to be consistent
# with logInPrincipal().  Or maybe logUserOut(), in case we don't care about
# consistency.
def logoutPerson(request):
    """Log the user out."""
    session = ISession(request)
    authdata = session['launchpad.authenticateduser']
    account_variable_name = 'accountid'
    previous_login = authdata.get(account_variable_name)
    if previous_login is None:
        # This is for backwards compatibility, when we used to store the
        # person's ID in the 'personid' session variable.
        account_variable_name = 'personid'
        previous_login = authdata.get(account_variable_name)
    if previous_login is not None:
        authdata[account_variable_name] = None
        authdata['logintime'] = datetime.utcnow()
        auth_utility = getUtility(IPlacelessAuthUtility)
        principal = auth_utility.unauthenticatedPrincipal()
        request.setPrincipal(principal)
        # We want to clear the session cookie so anonymous users can get
        # cached pages again. We need to do this after setting the session
        # values (e.g., ``authdata['personid'] = None``, above), because that
        # code will itself try to set the cookie in the browser.  We need to
        # provide a bit of time before the cookie clears (10 minutes at the
        # moment) so that, if code wants to send a notification (such as "your
        # account has been deactivated"), the session will still be available
        # long enough to give the message to the now-unauthenticated user.
        # The time period could probably be 5 or 10 seconds, if everyone were
        # on NTP, but...they're not, so we use a pretty high fudge factor of
        # ten minutes.
        expireSessionCookie(request)
        notify(LoggedOutEvent(request))


class CookieLogoutPage:

    def logout(self):
        logoutPerson(self.request)
        openid_vhost = config.launchpad.openid_provider_vhost
        openid_root = allvhosts.configs[openid_vhost].rooturl
        target = '%s+logout?%s' % (
            config.codehosting.secure_codebrowse_root,
            urllib.urlencode(dict(next_to='%s+logout' % (openid_root, ))))
        self.request.response.redirect(target)
        return ''


class FeedsUnauthorizedView(UnauthorizedView):
    """All users of feeds are anonymous, so don't redirect to login."""

    def __call__(self):
        assert IUnauthenticatedPrincipal.providedBy(self.request.principal), (
            "Feeds user should always be anonymous.")
        self.request.response.setStatus(403)  # Forbidden
        return self.template()
