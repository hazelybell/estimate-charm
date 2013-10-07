# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import os

from testtools.deferredruntest import (
    assert_fails_with,
    AsynchronousDeferredRunTest,
    flush_logged_errors,
    )
from twisted.conch.checkers import SSHPublicKeyDatabase
from twisted.conch.error import ConchError
from twisted.conch.ssh import userauth
from twisted.conch.ssh.common import (
    getNS,
    NS,
    )
from twisted.conch.ssh.keys import (
    BadKeyError,
    Key,
    )
from twisted.conch.ssh.transport import (
    SSHCiphers,
    SSHServerTransport,
    )
from twisted.cred.error import UnauthorizedLogin
from twisted.cred.portal import (
    IRealm,
    Portal,
    )
from twisted.internet import defer
from twisted.python import failure
from twisted.python.util import sibpath
from zope.interface import implements

from lp.services.sshserver import auth
from lp.services.twistedsupport import suppress_stderr
from lp.testing import TestCase
from lp.xmlrpc import faults


class MockRealm:
    """A mock realm for testing userauth.SSHUserAuthServer.

    This realm is not actually used in the course of testing, so calls to
    requestAvatar will raise an exception.
    """

    implements(IRealm)

    def requestAvatar(self, avatar_id, mind, *interfaces):
        user_dict = {
            'id': avatar_id, 'name': avatar_id, 'teams': [],
            'initialBranches': []}
        return (
            interfaces[0], auth.LaunchpadAvatar(user_dict), lambda: None)


class MockSSHTransport(SSHServerTransport):
    """A mock SSH transport for testing userauth.SSHUserAuthServer.

    SSHUserAuthServer expects an SSH transport which has a factory attribute
    which in turn has a portal attribute. Because the portal is important for
    testing authentication, we need to be able to provide an interesting portal
    object to the SSHUserAuthServer.

    In addition, we want to be able to capture any packets sent over the
    transport.
    """

    class Factory:
        def getService(self, transport, nextService):
            return lambda: None

    def __init__(self, portal):
        # In Twisted 8.0.1, Conch's transport starts referring to
        # currentEncryptions where it didn't before. Provide a dummy value for
        # it.
        self.currentEncryptions = SSHCiphers('none', 'none', 'none', 'none')
        self.packets = []
        self.factory = self.Factory()
        self.factory.portal = portal

    def sendPacket(self, messageType, payload):
        self.packets.append((messageType, payload))

    def setService(self, service):
        pass


class UserAuthServerMixin(object):
    def setUp(self):
        self.portal = Portal(MockRealm())
        self.transport = MockSSHTransport(self.portal)
        self.user_auth = auth.SSHUserAuthServer(self.transport)

    def _getMessageName(self, message_type):
        """Get the name of the message for the given message type constant."""
        return userauth.SSHUserAuthServer.protocolMessages[message_type]

    def assertMessageOrder(self, message_types):
        """Assert that SSH messages were sent in the given order."""
        messages = userauth.SSHUserAuthServer.protocolMessages
        self.assertEqual(
            [messages[msg_type] for msg_type in message_types],
            [messages[packet_type]
             for packet_type, contents in self.transport.packets])

    def assertBannerSent(self, banner_message, expected_language='en'):
        """Assert that 'banner_message' was sent as an SSH banner."""
        # Check that we received a BANNER, then a FAILURE.
        for packet_type, packet_content in self.transport.packets:
            if packet_type == userauth.MSG_USERAUTH_BANNER:
                bytes, language, empty = getNS(packet_content, 2)
                self.assertEqual(banner_message, bytes.decode('UTF8'))
                self.assertEqual(expected_language, language)
                self.assertEqual('', empty)
                break
        else:
            self.fail("No banner logged.")


class TestUserAuthServer(TestCase, UserAuthServerMixin):

    def setUp(self):
        TestCase.setUp(self)
        UserAuthServerMixin.setUp(self)

    def test_sendBanner(self):
        # sendBanner should send an SSH 'packet' with type MSG_USERAUTH_BANNER
        # and two fields. The first field is the message itself, and the
        # second is the language tag.
        #
        # sendBanner automatically adds a trailing newline, because openssh
        # and Twisted don't add one when displaying the banner.
        #
        # See RFC 4252, Section 5.4.
        message = u"test message"
        self.user_auth.sendBanner(message, language='en-US')
        self.assertBannerSent(message + '\r\n', 'en-US')
        self.assertEqual(
            1, len(self.transport.packets),
            "More than just banner was sent: %r" % self.transport.packets)

    def test_sendBannerUsesCRLF(self):
        # sendBanner should make sure that any line breaks in the message are
        # sent as CR LF pairs.
        #
        # See RFC 4252, Section 5.4.
        self.user_auth.sendBanner(u"test\nmessage")
        [(messageType, payload)] = self.transport.packets
        bytes, language, empty = getNS(payload, 2)
        self.assertEqual(bytes.decode('UTF8'), u"test\r\nmessage\r\n")

    def test_requestRaisesConchError(self):
        # ssh_USERAUTH_REQUEST should raise a ConchError if tryAuth returns
        # None. Added to catch a bug noticed by pyflakes.
        # Whitebox test.
        def mock_try_auth(kind, user, data):
            return None
        def mock_eb_bad_auth(reason):
            reason.trap(ConchError)
        tryAuth = self.user_auth.tryAuth
        self.user_auth.tryAuth = mock_try_auth
        _ebBadAuth, self.user_auth._ebBadAuth = (self.user_auth._ebBadAuth,
                                                 mock_eb_bad_auth)
        self.user_auth.serviceStarted()
        try:
            packet = NS('jml') + NS('foo') + NS('public_key') + NS('data')
            self.user_auth.ssh_USERAUTH_REQUEST(packet)
        finally:
            self.user_auth.serviceStopped()
            self.user_auth.tryAuth = tryAuth
            self.user_auth._ebBadAuth = _ebBadAuth


class MockChecker(SSHPublicKeyDatabase):
    """A very simple public key checker which rejects all offered credentials.

    Used by TestAuthenticationBannerDisplay to test that errors raised by
    checkers are sent to SSH clients.
    """

    error_message = u'error message'

    def requestAvatarId(self, credentials):
        if credentials.username == 'success':
            return credentials.username
        else:
            return failure.Failure(
                auth.UserDisplayedUnauthorizedLogin(self.error_message))


class TestAuthenticationBannerDisplay(UserAuthServerMixin, TestCase):
    """Check that auth error information is passed through to the client.

    Normally, SSH servers provide minimal information on failed authentication.
    With Launchpad, much more user information is public, so it is helpful and
    not insecure to tell users why they failed to authenticate.

    SSH doesn't provide a standard way of doing this, but the
    MSG_USERAUTH_BANNER message is allowed and seems appropriate. See RFC 4252,
    Section 5.4 for more information.
    """

    run_tests_with = AsynchronousDeferredRunTest

    def setUp(self):
        UserAuthServerMixin.setUp(self)
        TestCase.setUp(self)
        self.portal.registerChecker(MockChecker())
        self.user_auth.serviceStarted()
        self.key_data = self._makeKey()

    def tearDown(self):
        self.user_auth.serviceStopped()
        TestCase.tearDown(self)

    def _makeKey(self):
        keydir = sibpath(__file__, 'keys')
        public_key = Key.fromString(
            open(os.path.join(keydir, 'ssh_host_key_rsa.pub'), 'rb').read())
        if isinstance(public_key, str):
            return chr(0) + NS('rsa') + NS(public_key)
        else:
            return chr(0) + NS('rsa') + NS(public_key.blob())

    def requestFailedAuthentication(self):
        return self.user_auth.ssh_USERAUTH_REQUEST(
            NS('failure') + NS('') + NS('publickey') + self.key_data)

    def requestSuccessfulAuthentication(self):
        return self.user_auth.ssh_USERAUTH_REQUEST(
            NS('success') + NS('') + NS('publickey') + self.key_data)

    def requestUnsupportedAuthentication(self):
        # Note that it doesn't matter how the checker responds -- the server
        # doesn't get that far.
        return self.user_auth.ssh_USERAUTH_REQUEST(
            NS('success') + NS('') + NS('none') + NS(''))

    def test_bannerNotSentOnSuccess(self):
        # No banner is printed when the user authenticates successfully.
        self.user_auth._banner = None

        d = self.requestSuccessfulAuthentication()
        def check(ignored):
            # Check that no banner was sent to the user.
            self.assertMessageOrder([userauth.MSG_USERAUTH_SUCCESS])
        return d.addCallback(check)

    def test_defaultBannerSentOnSuccess(self):
        # If a banner was passed to the user auth agent then we send it to the
        # user when they log in.
        self.user_auth._banner = "Boogedy boo"
        d = self.requestSuccessfulAuthentication()
        def check(ignored):
            self.assertMessageOrder(
                [userauth.MSG_USERAUTH_BANNER, userauth.MSG_USERAUTH_SUCCESS])
            self.assertBannerSent(self.user_auth._banner + '\r\n')
        return d.addCallback(check)

    def test_defaultBannerSentOnlyOnce(self):
        # We don't send the banner on each authentication attempt, just on the
        # first one. It is usual for there to be many authentication attempts
        # per SSH session.
        self.user_auth._banner = "Boogedy boo"

        d = self.requestUnsupportedAuthentication()
        d.addCallback(lambda ignored: self.requestSuccessfulAuthentication())

        def check(ignored):
            # Check that no banner was sent to the user.
            self.assertMessageOrder(
                [userauth.MSG_USERAUTH_FAILURE, userauth.MSG_USERAUTH_BANNER,
                 userauth.MSG_USERAUTH_SUCCESS])
            self.assertBannerSent(self.user_auth._banner + '\r\n')

        return d.addCallback(check)

    def test_defaultBannerNotSentOnFailure(self):
        # Failed authentication attempts do not get the default banner
        # sent.
        self.user_auth._banner = "You come away two hundred quid down"

        d = self.requestFailedAuthentication()

        def check(ignored):
            self.assertMessageOrder(
                [userauth.MSG_USERAUTH_BANNER, userauth.MSG_USERAUTH_FAILURE])
            self.assertBannerSent(MockChecker.error_message + '\r\n')

        return d.addCallback(check)

    def test_loggedToBanner(self):
        # When there's an authentication failure, we display an informative
        # error message through the SSH authentication protocol 'banner'.
        d = self.requestFailedAuthentication()
        def check(ignored):
            # Check that we received a BANNER, then a FAILURE.
            self.assertMessageOrder(
                [userauth.MSG_USERAUTH_BANNER, userauth.MSG_USERAUTH_FAILURE])
            self.assertBannerSent(MockChecker.error_message + '\r\n')
        return d.addCallback(check)

    def test_unsupportedAuthMethodNotLogged(self):
        # Trying various authentication methods is a part of the normal
        # operation of the SSH authentication protocol. We should not spam the
        # client with warnings about this, as whenever it becomes a problem,
        # we can rely on the SSH client itself to report it to the user.
        d = self.requestUnsupportedAuthentication()
        def check(ignored):
            # Check that we received only a FAILRE.
            self.assertMessageOrder([userauth.MSG_USERAUTH_FAILURE])
        return d.addCallback(check)


class TestPublicKeyFromLaunchpadChecker(TestCase):
    """Tests for the SSH server authentication mechanism.

    PublicKeyFromLaunchpadChecker accepts the SSH authentication information
    and contacts the authserver to determine if the given details are valid.

    Any authentication errors are displayed back to the user via an SSH
    MSG_USERAUTH_BANNER message.
    """

    run_tests_with = AsynchronousDeferredRunTest

    class FakeAuthenticationEndpoint:
        """A fake client for enough of `IAuthServer` for this test.
        """

        valid_user = 'valid_user'
        no_key_user = 'no_key_user'
        valid_key = 'valid_key'

        def __init__(self):
            self.calls = []

        def callRemote(self, function_name, *args, **kwargs):
            return getattr(
                self, 'xmlrpc_%s' % function_name)(*args, **kwargs)

        def xmlrpc_getUserAndSSHKeys(self, username):
            self.calls.append(username)
            if username == self.valid_user:
                return defer.succeed({
                    'name': username,
                    'keys': [('DSA', self.valid_key.encode('base64'))],
                    })
            elif username == self.no_key_user:
                return defer.succeed({
                    'name': username,
                    'keys': [],
                    })
            else:
                try:
                    raise faults.NoSuchPersonWithName(username)
                except faults.NoSuchPersonWithName:
                    return defer.fail()

    def makeCredentials(self, username, public_key, mind=None):
        if mind is None:
            mind = auth.UserDetailsMind()
        return auth.SSHPrivateKeyWithMind(
            username, 'ssh-dss', public_key, '', None, mind)

    def makeChecker(self, do_signature_checking=False):
        """Construct a PublicKeyFromLaunchpadChecker.

        :param do_signature_checking: if False, as is the default, monkeypatch
            the returned instance to not verify the signatures of the keys.
        """
        checker = auth.PublicKeyFromLaunchpadChecker(self.authserver)
        if not do_signature_checking:
            checker._cbRequestAvatarId = self._cbRequestAvatarId
        return checker

    def _cbRequestAvatarId(self, is_key_valid, credentials):
        if is_key_valid:
            return credentials.username
        return failure.Failure(UnauthorizedLogin())

    def setUp(self):
        TestCase.setUp(self)
        self.authserver = self.FakeAuthenticationEndpoint()

    def test_successful(self):
        # Attempting to log in with a username and key known to the
        # authentication end-point succeeds.
        creds = self.makeCredentials(
            self.authserver.valid_user, self.authserver.valid_key)
        checker = self.makeChecker()
        d = checker.requestAvatarId(creds)
        return d.addCallback(self.assertEqual, self.authserver.valid_user)

    @suppress_stderr
    def test_invalid_signature(self):
        # The checker requests attempts to authenticate if the requests have
        # an invalid signature.
        creds = self.makeCredentials(
            self.authserver.valid_user, self.authserver.valid_key)
        creds.signature = 'a'
        checker = self.makeChecker(True)
        d = checker.requestAvatarId(creds)
        def flush_errback(f):
            flush_logged_errors(BadKeyError)
            return f
        d.addErrback(flush_errback)
        return assert_fails_with(d, UnauthorizedLogin)

    def assertLoginError(self, checker, creds, error_message):
        """Logging in with 'creds' against 'checker' fails with 'message'.

        In particular, this tests that the login attempt fails in a way that
        is sent to the client.

        :param checker: The `ICredentialsChecker` used.
        :param creds: SSHPrivateKey credentials.
        :param error_message: String excepted to match the exception's message.
        :return: Deferred. You must return this from your test.
        """
        d = assert_fails_with(
            checker.requestAvatarId(creds),
            auth.UserDisplayedUnauthorizedLogin)
        d.addCallback(
            lambda exception: self.assertEqual(str(exception), error_message))
        return d

    def test_noSuchUser(self):
        # When someone signs in with a non-existent user, they should be told
        # that. The usual security issues don't apply here because the list of
        # Launchpad user names is public.
        checker = self.makeChecker()
        creds = self.makeCredentials(
            'no-such-user', self.authserver.valid_key)
        return self.assertLoginError(
            checker, creds, 'No such Launchpad account: no-such-user')

    def test_noKeys(self):
        # When you sign into an existing account with no SSH keys, the SSH
        # server informs you that the account has no keys.
        checker = self.makeChecker()
        creds = self.makeCredentials(
            self.authserver.no_key_user, self.authserver.valid_key)
        return self.assertLoginError(
            checker, creds,
            "Launchpad user %r doesn't have a registered SSH key"
            % self.authserver.no_key_user)

    def test_wrongKey(self):
        # When you sign into an existing account using the wrong key, you
        # are *not* informed of the wrong key. This is because SSH often
        # tries several keys as part of normal operation.
        checker = self.makeChecker()
        creds = self.makeCredentials(
            self.authserver.valid_user, 'invalid key')
        # We cannot use assertLoginError because we are checking that we fail
        # with UnauthorizedLogin and not its subclass
        # UserDisplayedUnauthorizedLogin.
        d = assert_fails_with(
            checker.requestAvatarId(creds),
            UnauthorizedLogin)
        d.addCallback(
            lambda exception:
            self.failIf(isinstance(exception,
                                   auth.UserDisplayedUnauthorizedLogin),
                        "Should not be a UserDisplayedUnauthorizedLogin"))
        return d

    def test_successful_with_second_key_calls_authserver_once(self):
        # It is normal in SSH authentication to be presented with a number of
        # keys.  When the valid key is presented after some invalid ones (a)
        # the login succeeds and (b) only one call is made to the authserver
        # to retrieve the user's details.
        checker = self.makeChecker()
        mind = auth.UserDetailsMind()
        wrong_key_creds = self.makeCredentials(
            self.authserver.valid_user, 'invalid key', mind)
        right_key_creds = self.makeCredentials(
            self.authserver.valid_user, self.authserver.valid_key, mind)
        d = checker.requestAvatarId(wrong_key_creds)
        def try_second_key(failure):
            failure.trap(UnauthorizedLogin)
            return checker.requestAvatarId(right_key_creds)
        d.addErrback(try_second_key)
        d.addCallback(self.assertEqual, self.authserver.valid_user)
        def check_one_call(r):
            self.assertEqual(
                [self.authserver.valid_user], self.authserver.calls)
            return r
        d.addCallback(check_one_call)
        return d

    def test_noSuchUser_with_two_keys_calls_authserver_once(self):
        # When more than one key is presented for a username that does not
        # exist, only one call is made to the authserver.
        checker = self.makeChecker()
        mind = auth.UserDetailsMind()
        creds_1 = self.makeCredentials(
            'invalid-user', 'invalid key 1', mind)
        creds_2 = self.makeCredentials(
            'invalid-user', 'invalid key 2', mind)
        d = checker.requestAvatarId(creds_1)
        def try_second_key(failure):
            return assert_fails_with(
                checker.requestAvatarId(creds_2),
                UnauthorizedLogin)
        d.addErrback(try_second_key)
        def check_one_call(r):
            self.assertEqual(
                ['invalid-user'], self.authserver.calls)
            return r
        d.addCallback(check_one_call)
        return d
