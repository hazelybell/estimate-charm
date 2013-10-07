# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""OAuth interfaces."""

__metaclass__ = type

__all__ = [
    'OAUTH_REALM',
    'OAUTH_CHALLENGE',
    'IOAuthAccessToken',
    'IOAuthConsumer',
    'IOAuthConsumerSet',
    'IOAuthNonce',
    'IOAuthRequestToken',
    'IOAuthRequestTokenSet',
    'IOAuthSignedRequest',
    'NonceAlreadyUsed',
    'TimestampOrderingError',
    'ClockSkew',
    'TokenException',
    ]

import httplib

from lazr.restful.declarations import error_status
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Bool,
    Choice,
    Datetime,
    Object,
    TextLine,
    )

from lp import _
from lp.registry.interfaces.person import IPerson
from lp.services.webapp.interfaces import (
    AccessLevel,
    OAuthPermission,
    )

# The challenge included in responses with a 401 status.
OAUTH_REALM = 'https://api.launchpad.net'
OAUTH_CHALLENGE = 'OAuth realm="%s"' % OAUTH_REALM


class IOAuthConsumer(Interface):
    """An application which acts on behalf of a Launchpad user."""

    date_created = Datetime(
        title=_('Date created'), required=True, readonly=True)
    disabled = Bool(
        title=_('Disabled?'), required=False, readonly=False,
        description=_('Disabled consumers are not allowed to access any '
                      'protected resources.'))
    key = TextLine(
        title=_('Key'), required=True, readonly=True,
        description=_('The unique key which identifies a consumer. It is '
                      'included by the consumer in each request made.'))
    secret = TextLine(
        title=_('Secret'), required=False, readonly=False,
        description=_('The secret which, if not empty, should be used by the '
                      'consumer to sign its requests.'))

    is_integrated_desktop = Attribute(
        """This attribute is true if the consumer corresponds to a
        user account on a personal computer or similar device.""")

    integrated_desktop_name = Attribute(
        """If the consumer corresponds to a user account on a personal
        computer or similar device, this is the self-reported name of
        the computer. If the consumer is a specific web or desktop
        application, this is None.""")

    integrated_desktop_type = Attribute(
        """If the consumer corresponds to a user account on a personal
        computer or similar device, this is the self-reported type of
        that computer (usually the operating system plus the word
        "desktop"). If the consumer is a specific web or desktop
        application, this is None.""")

    def newRequestToken():
        """Return a new `IOAuthRequestToken` with a random key and secret.

        The other attributes of the token are supposed to be set whenever the
        user logs into Launchpad and grants (or not) access to this consumer.
        """

    def getAccessToken(key):
        """Return the `IOAuthAccessToken` with the given key.

        If the token with the given key does not exist or is associated with
        another consumer, return None.
        """

    def getRequestToken(key):
        """Return the `IOAuthRequestToken` with the given key.

        If the token with the given key does not exist or is associated with
        another consumer, return None.
        """


class IOAuthConsumerSet(Interface):
    """The set of OAuth consumers."""

    def new(key, secret=''):
        """Return the newly created consumer.

        You must make sure the given `key` is not already in use by another
        consumer before trying to create a new one.

        The `secret` defaults to an empty string because most consumers will
        be open source desktop applications for which it wouldn't be actually
        secret.

        :param key: The unique key which will be associated with the new
            consumer.
        :param secret: A secret which should be used by the consumer to sign
            its requests.
        """

    def getByKey(key):
        """Return the consumer with the given key.

        If there's no consumer with the given key, return None.

        :param key: The unique key associated with a consumer.
        """


class IOAuthToken(Interface):
    """Base class for `IOAuthRequestToken` and `IOAuthAccessToken`.

    This class contains the commonalities of the two token classes we actually
    care about and shall not be used on its own.
    """

    consumer = Object(
        schema=IOAuthConsumer, title=_('The consumer.'),
        description=_("The consumer which will access Launchpad on the "
                      "user's behalf."))
    person = Object(
        schema=IPerson, title=_('Person'), required=False, readonly=False,
        description=_('The user on whose behalf the consumer is accessing.'))
    key = TextLine(
        title=_('Key'), required=True, readonly=True,
        description=_('The key used to identify this token.  It is included '
                      'by the consumer in each request.'))
    secret = TextLine(
        title=_('Secret'), required=True, readonly=True,
        description=_('The secret associated with this token.  It is used '
                      'by the consumer to sign its requests.'))
    product = Choice(title=_('Project'), required=False, vocabulary='Product')
    project = Choice(
        title=_('Project'), required=False, vocabulary='ProjectGroup')
    sourcepackagename = Choice(
        title=_("Package"), required=False, vocabulary='SourcePackageName')
    distribution = Choice(
        title=_("Distribution"), required=False, vocabulary='Distribution')
    context = Attribute("FIXME")

    is_expired = Bool(
        title=_("Whether or not this token has expired."),
        required=False, readonly=True,
        description=_("A token may only be usable for a limited time, "
                      "after which it will expire."))


class IOAuthAccessToken(IOAuthToken):
    """A token used by a consumer to access protected resources in LP.

    It's created automatically once a user logs in and grants access to a
    consumer.  The consumer then exchanges an `IOAuthRequestToken` for it.
    """

    permission = Choice(
        title=_('Access level'), required=True, readonly=False,
        vocabulary=AccessLevel,
        description=_('The level of access given to the application acting '
                      'on your behalf.'))

    date_created = Datetime(
        title=_('Date created'), required=True, readonly=True,
        description=_('The date some request token was exchanged for '
                      'this token.'))

    date_expires = Datetime(
        title=_('Date expires'), required=False, readonly=False,
        description=_('From this date onwards this token can not be used '
                      'by the consumer to access protected resources.'))

    def checkNonceAndTimestamp(nonce, timestamp):
        """Verify the nonce and timestamp.

        - Ensure the nonce hasn't been used with the same timestamp.
        - Ensure this is a first access, or this timestamp is no older than
          last timestamp minus `TIMESTAMP_ACCEPTANCE_WINDOW`.
        - Ensure this timestamp is within +/- `TIMESTAMP_SKEW_WINDOW` of the
          server's concept of now.

        :raises NonceAlreadyUsed: If the nonce has been used before with the
            same timestamp.
        :raises TimestampOrderingError: If the timestamp is older than the
            last timestamp minus `TIMESTAMP_ACCEPTANCE_WINDOW`.
        :raises ClockSkew: If the timestamp is not within
            +/- `TIMESTAMP_SKEW_WINDOW` of now.

        If the nonce has never been used together with this token and
        timestamp before, we store it in the database with the given timestamp
        and associated with this token.
        """


class IOAuthRequestToken(IOAuthToken):
    """A token used by a consumer to ask the user to authenticate on LP.

    After the user has authenticated and granted access to that consumer, the
    request token is exchanged for an access token and is then destroyed.
    """

    permission = Choice(
        title=_('Permission'), required=True, readonly=False,
        vocabulary=OAuthPermission,
        description=_('The permission you give to the application which may '
                      'act on your behalf.'))
    date_created = Datetime(
        title=_('Date created'), required=True, readonly=True,
        description=_('The date the token was created. The request token '
                      'will be good for a limited time after this date.'))

    date_expires = Datetime(
        title=_('Date expires'), required=False, readonly=False,
        description=_('The expiration date for the permission you give to '
                      'the application which may act on your behalf.'))

    date_reviewed = Datetime(
        title=_('Date reviewed'), required=True, readonly=True,
        description=_('The date in which the user authorized (or not) the '
                      'consumer to access his protected resources on '
                      'Launchpad.'))

    is_reviewed = Bool(
        title=_('Has this token been reviewed?'),
        required=False, readonly=True,
        description=_('A reviewed request token can only be exchanged for an '
                      'access token (in case the user granted access).'))

    def review(user, permission, context=None):
        """Grant `permission` as `user` to this token's consumer.

        :param context: An IProduct, IProjectGroup, IDistribution or
            IDistributionSourcePackage in which the permission is valid. If
            None, the permission will be valid everywhere.

        Set this token's person, permission and date_reviewed.  This will also
        cause this token to be marked as used, meaning it can only be
        exchanged for an access token with the same permission, consumer and
        person.
        """

    def createAccessToken():
        """Create an `IOAuthAccessToken` identical to this request token.

        After the access token is created, this one is deleted as it can't be
        used anymore.

        You must not attempt to create an access token if the request token
        hasn't been reviewed or if its permission is UNAUTHORIZED.
        """


class IOAuthRequestTokenSet(Interface):
    """The set of `IOAuthRequestToken`s."""

    def getByKey(key):
        """Return the IOAuthRequestToken with the given key.

        If it doesn't exist, return None.
        """


class IOAuthNonce(Interface):
    """The unique (nonce,timestamp) for requests using a given access token.

    The nonce value (which is unique for all requests with that timestamp)
    is generated by the consumer and included, together with the timestamp,
    in each request made.  It's used to prevent replay attacks.
    """

    request_timestamp = Datetime(
        title=_('Date issued'), required=True, readonly=True)
    access_token = Object(schema=IOAuthAccessToken, title=_('The token'))
    nonce = TextLine(title=_('Nonce'), required=True, readonly=True)


class IOAuthSignedRequest(Interface):
    """Marker interface for a request signed with OAuth credentials."""


# Note that these exceptions are marked as UNAUTHORIZED (401 status)
# so they may be raised but will not cause an OOPS to be generated.  The
# client will see them as an UNAUTHORIZED error.

@error_status(httplib.UNAUTHORIZED)
class _TokenException(Exception):
    """Base class for token, nonce, and timestamp exceptions."""


class NonceAlreadyUsed(_TokenException):
    """Nonce has been used together with same token but another timestamp."""


class TimestampOrderingError(_TokenException):
    """Timestamp is too old, compared to the last request."""


class ClockSkew(_TokenException):
    """Timestamp is too far off from server's clock."""


class TokenException(_TokenException):
    """Token has expired."""
