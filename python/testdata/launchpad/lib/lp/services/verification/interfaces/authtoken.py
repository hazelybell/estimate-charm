# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Login token interfaces."""

__metaclass__ = type

__all__ = [
    'LoginTokenType',
    'IAuthToken',
    ]

from lazr.enum import (
    DBEnumeratedType,
    DBItem,
    )
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Choice,
    Datetime,
    Int,
    Text,
    TextLine,
    )

from lp import _


class LoginTokenType(DBEnumeratedType):
    """Login token type

    Tokens are emailed to users in workflows that require email address
    validation, such as forgotten password recovery or account merging.
    We need to identify the type of request so we know what workflow
    is being processed.
    """

    PASSWORDRECOVERY = DBItem(1, """
        Password Recovery

        User has forgotten or never known their password and need to
        reset it.
        """)

    ACCOUNTMERGE = DBItem(2, """
        Account Merge

        User has requested that another account be merged into their
        current one.
        """)

    NEWACCOUNT = DBItem(3, """
        New Account

        A new account is being setup. They need to verify their email address
        before we allow them to set a password and log in.
        """)

    VALIDATEEMAIL = DBItem(4, """
        Validate Email

        A user has added more email addresses to their account and they
        need to be validated.
        """)

    VALIDATETEAMEMAIL = DBItem(5, """
        Validate Team Email

        One of the team administrators is trying to add a contact email
        address for the team, but this address need to be validated first.
        """)

    VALIDATEGPG = DBItem(6, """
        Validate GPG key

        A user has submited a new GPG key to his account and it need to
        be validated.
        """)

    VALIDATESIGNONLYGPG = DBItem(7, """
        Validate a sign-only GPG key

        A user has submitted a new sign-only GPG key to his account and it
        needs to be validated.
        """)

    NEWPROFILE = DBItem(9, """
        A user created a new Launchpad profile for another person.

        Any Launchpad user can create new "placeholder" profiles to represent
        people who don't use Launchpad. The person that a given profile
        represents has to first use the token to finish the registration
        process in order to be able to login with that profile.
        """)

    TEAMCLAIM = DBItem(10, """
        Turn an unvalidated Launchpad profile into a team.

        A user has found an unvalidated profile in Launchpad and is trying
        to turn it into a team.
        """)

    BUGTRACKER = DBItem(11, """
        Launchpad is authenticating itself with a remote bug tracker.

        The remote bug tracker will use the LoginToken to authenticate
        Launchpad.
        """)

    NEWPERSONLESSACCOUNT = DBItem(12, """
        New Personless Account

        A new personless account is being setup. They need to verify their
        email address before we allow them to set a password and log in.  At
        the end, this account will not have a Person associated with.
        """)


# XXX: Guilherme Salgado, 2010-03-30: This interface was created to be used by
# our old OpenID provider, but that doesn't exist anymore, so we should merge
# it with ILoginToken.
class IAuthToken(Interface):
    """The object that stores one time tokens used for validating email
    addresses and other tasks that require verifying if an email address is
    valid such as password recovery, account merging and registration of new
    accounts. All LoginTokens must be deleted once they are "consumed"."""
    id = Int(
        title=_('ID'), required=True, readonly=True,
        )
    date_created = Datetime(
        title=_('The timestamp that this request was made.'), required=True,
        )
    date_consumed = Datetime(
        title=_('Date and time this was consumed'),
        required=False, readonly=False
        )

    tokentype = Choice(
        title=_('The type of request.'), required=True,
        vocabulary=LoginTokenType
        )
    token = Text(
        title=_('The token (not the URL) emailed used to uniquely identify '
                'this request.'),
        required=True,
        )

    requester = Int(
        title=_('The Person that made this request.'), required=True,
        )
    requesteremail = Text(
        title=_('The email address that was used to login when making this '
                'request.'),
        required=False,
        )

    email = TextLine(
        title=_('Email address'),
        required=True,
        )

    redirection_url = Text(
        title=_('The URL to where we should redirect the user after '
                'processing his request'),
        required=False,
        )

    # used for launchpad page layout
    title = Attribute('Title')

    def consume():
        """Mark this token as consumed by setting date_consumed.

        As a consequence of a token being consumed, all tokens requested by
        the same person and with the same requester email will also be marked
        as consumed.
        """

    def sendEmailValidationRequest():
        """Send an email message with a magic URL to validate self.email."""
