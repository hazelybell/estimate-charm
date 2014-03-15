# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'check_oauth_signature',
    'get_oauth_authorization',
    'LaunchpadLoginSource',
    'LaunchpadPrincipal',
    'PlacelessAuthUtility',
    ]


import binascii

from contrib.oauth import OAuthRequest
from zope.authentication.interfaces import ILoginPassword
from zope.component import getUtility
from zope.event import notify
from zope.interface import implements
from zope.principalregistry.principalregistry import UnauthenticatedPrincipal
from zope.security.interfaces import Unauthorized
from zope.security.proxy import removeSecurityProxy
from zope.session.interfaces import ISession

from lp.registry.interfaces.person import (
    IPerson,
    IPersonSet,
    )
from lp.services.config import config
from lp.services.identity.interfaces.account import IAccountSet
from lp.services.oauth.interfaces import OAUTH_CHALLENGE
from lp.services.webapp.interfaces import (
    AccessLevel,
    BasicAuthLoggedInEvent,
    CookieAuthPrincipalIdentifiedEvent,
    ILaunchpadPrincipal,
    IPlacelessAuthUtility,
    IPlacelessLoginSource,
    )


class PlacelessAuthUtility:
    """An authentication service which holds no state aside from its
    ZCML configuration, implemented as a utility.
    """
    implements(IPlacelessAuthUtility)

    def __init__(self):
        self.nobody = UnauthenticatedPrincipal(
            'Anonymous', 'Anonymous', 'Anonymous User')
        self.nobody.__parent__ = self

    def _authenticateUsingBasicAuth(self, credentials, request):
        # authenticate() only attempts basic auth if it's enabled. But
        # recheck here, just in case. There is a single password for all
        # users, so this must never get anywhere near production!
        if (not config.launchpad.basic_auth_password
            or config.launchpad.basic_auth_password.lower() == 'none'):
            raise AssertionError(
                "Attempted to use basic auth when it is disabled")

        login = credentials.getLogin()
        if login is not None:
            login_src = getUtility(IPlacelessLoginSource)
            principal = login_src.getPrincipalByLogin(login)
            if principal is not None and principal.person.is_valid_person:
                password = credentials.getPassword()
                if password == config.launchpad.basic_auth_password:
                    # We send a LoggedInEvent here, when the
                    # cookie auth below sends a PrincipalIdentified,
                    # as the login form is never visited for BasicAuth.
                    # This we treat each request as a separate
                    # login/logout.
                    notify(BasicAuthLoggedInEvent(
                        request, login, principal))
                    return principal

    def _authenticateUsingCookieAuth(self, request):
        session = ISession(request)
        authdata = session['launchpad.authenticateduser']
        id = authdata.get('accountid')
        if id is None:
            # XXX: salgado, 2009-02-17: This is for backwards compatibility,
            # when we used to store the person's ID in the session.
            person_id = authdata.get('personid')
            if person_id is not None:
                person = getUtility(IPersonSet).get(person_id)
                if person is not None and person.accountID is not None:
                    id = person.accountID

        if id is None:
            return None

        login_src = getUtility(IPlacelessLoginSource)
        principal = login_src.getPrincipal(id)
        # Note, not notifying a LoggedInEvent here as for session-based
        # auth the login occurs when the login form is submitted, not
        # on each request.
        if principal is None:
            # XXX Stuart Bishop 2006-05-26 bug=33427:
            # User is authenticated in session, but principal is not"
            # available in login source. This happens when account has
            # become invalid for some reason, such as being merged.
            return None
        elif principal.person.is_valid_person:
            login = authdata['login']
            assert login, 'login is %s!' % repr(login)
            notify(CookieAuthPrincipalIdentifiedEvent(
                principal, request, login))
            return principal
        else:
            return None

    def authenticate(self, request):
        """See IAuthentication."""
        # To avoid confusion (hopefully), basic auth trumps cookie auth
        # totally, and all the time.  If there is any basic auth at all,
        # then cookie auth won't even be considered.
        # XXX daniels 2004-12-14: allow authentication scheme to be put into
        #     a view; for now, use basic auth by specifying ILoginPassword.
        try:
            credentials = ILoginPassword(request, None)
        except binascii.Error:
            # We have probably been sent Basic auth credentials that aren't
            # encoded properly. That's a client error, so we don't really
            # care, and we're done.
            raise Unauthorized("Bad Basic authentication.")
        if (config.launchpad.basic_auth_password and credentials is not None
            and credentials.getLogin() is not None):
            return self._authenticateUsingBasicAuth(credentials, request)
        else:
            # Hack to make us not even think of using a session if there
            # isn't already a cookie in the request, or one waiting to be
            # set in the response.
            cookie_name = config.launchpad_session.cookie
            if (request.cookies.get(cookie_name) is not None or
                request.response.getCookie(cookie_name) is not None):
                return self._authenticateUsingCookieAuth(request)
            else:
                return None

    def unauthenticatedPrincipal(self):
        """See IAuthentication."""
        return self.nobody

    def unauthorized(self, id, request):
        """See IAuthentication."""
        a = ILoginPassword(request)
        # TODO maybe configure the realm from zconfigure.
        a.needLogin(realm="launchpad")

    def getPrincipal(self, id):
        """See IAuthentication."""
        utility = getUtility(IPlacelessLoginSource)
        return utility.getPrincipal(id)

    # XXX: This is part of IAuthenticationUtility, but that interface doesn't
    # exist anymore and I'm not sure this is used anywhere.  Need to
    # investigate further.
    def getPrincipals(self, name):
        """See IAuthenticationUtility."""
        utility = getUtility(IPlacelessLoginSource)
        return utility.getPrincipals(name)

    def getPrincipalByLogin(self, login):
        """See IAuthenticationService."""
        return getUtility(IPlacelessLoginSource).getPrincipalByLogin(login)


class LaunchpadLoginSource:
    """A login source that uses the launchpad SQL database to look up
    principal information.
    """
    implements(IPlacelessLoginSource)

    def getPrincipal(self, id, access_level=AccessLevel.WRITE_PRIVATE,
                     scope=None):
        """Return an `ILaunchpadPrincipal` for the account with the given id.

        Return None if there is no account with the given id.

        The `access_level` can be used for further restricting the capability
        of the principal.  By default, no further restriction is added.

        Similarly, when a `scope` is given, the principal's capabilities will
        apply only to things within that scope.  For everything else that is
        not private, the principal will have only read access.

        Note that we currently need to be able to retrieve principals for
        invalid People, as the login machinery needs the principal to
        validate the password against so it may then email a validation
        request to the user and inform them it has done so.
        """
        try:
            account = getUtility(IAccountSet).get(id)
        except LookupError:
            return None

        return self._principalForAccount(account, access_level, scope)

    def getPrincipals(self, name):
        raise NotImplementedError

    def getPrincipalByLogin(self, login,
                            access_level=AccessLevel.WRITE_PRIVATE,
                            scope=None):
        """Return a principal based on the account with the email address
        signified by "login".

        :return: None if there is no account with the given email address.

        The `access_level` can be used for further restricting the capability
        of the principal.  By default, no further restriction is added.

        Similarly, when a `scope` is given, the principal's capabilities will
        apply only to things within that scope.  For everything else that is
        not private, the principal will have only read access.


        Note that we currently need to be able to retrieve principals for
        invalid People, as the login machinery needs the principal to
        validate the password against so it may then email a validation
        request to the user and inform them it has done so.
        """
        person = getUtility(IPersonSet).getByEmail(login, filter_status=False)
        if person is None or person.account is None:
            return None
        return self._principalForAccount(person.account, access_level, scope)

    def _principalForAccount(self, account, access_level, scope):
        """Return a LaunchpadPrincipal for the given account.

        The LaunchpadPrincipal will also have the given access level and
        scope.
        """
        naked_account = removeSecurityProxy(account)
        principal = LaunchpadPrincipal(
            naked_account.id, naked_account.displayname,
            naked_account.displayname, account,
            access_level=access_level, scope=scope)
        principal.__parent__ = self
        return principal


# Fake a containment hierarchy because Zope3 is on crack.
authService = PlacelessAuthUtility()
loginSource = LaunchpadLoginSource()
loginSource.__parent__ = authService


class LaunchpadPrincipal:

    implements(ILaunchpadPrincipal)

    def __init__(self, id, title, description, account,
                 access_level=AccessLevel.WRITE_PRIVATE, scope=None):
        self.id = unicode(id)
        self.title = title
        self.description = description
        self.access_level = access_level
        self.scope = scope
        self.account = account
        self.person = IPerson(account, None)

    def getLogin(self):
        return self.title


def get_oauth_authorization(request):
    """Retrieve OAuth authorization information from a request.

    The authorization information may be in the Authorization header,
    or it might be in the query string or entity-body.

    :return: a dictionary of authorization information.
    """
    header = request._auth
    if header is not None and header.startswith("OAuth "):
        return OAuthRequest._split_header(header)
    else:
        return request.form


def check_oauth_signature(request, consumer, token):
    """Check that the given OAuth request is correctly signed.

    If the signature is incorrect or its method is not supported, set the
    appropriate status in the request's response and return False.
    """
    authorization = get_oauth_authorization(request)

    if authorization.get('oauth_signature_method') != 'PLAINTEXT':
        # XXX: 2008-03-04, salgado: Only the PLAINTEXT method is supported
        # now. Others will be implemented later.
        request.response.setStatus(400)
        return False

    if token is not None:
        token_secret = token.secret
    else:
        token_secret = ''
    expected_signature = "&".join([consumer.secret, token_secret])
    if expected_signature != authorization.get('oauth_signature'):
        request.unauthorized(OAUTH_CHALLENGE)
        return False

    return True
