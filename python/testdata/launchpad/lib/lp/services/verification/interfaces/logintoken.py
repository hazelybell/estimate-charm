# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Login token interfaces."""

__metaclass__ = type

__all__ = [
    'ILoginToken',
    'ILoginTokenSet',
    'IGPGKeyValidationForm',
    ]

from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import Text

from lp import _
from lp.services.verification.interfaces.authtoken import IAuthToken


class ILoginToken(IAuthToken):
    """The object that stores one time tokens.

    Used for validating email addresses and other tasks that require verifying
    if an email address is valid, account merging. All LoginTokens must be
    deleted once they are "consumed".
    """

    fingerprint = Text(
        title=_('OpenPGP key fingerprint used to retrieve key information '
                'when necessary.'),
        required=False,
        )

    validation_phrase = Text(
        title=_("The phrase used to validate sign-only GPG keys"))

    def destroySelf():
        """Remove this LoginToken from the database.

        We need this because once the token is used (either when registering a
        new user or validating an email address), we have to delete it so
        nobody can use that token again.
        """

    def sendGPGValidationRequest(key):
        """Send an email message with a magic URL to confirm the OpenPGP key.
        If fingerprint is set, send the message encrypted.
        """

    def sendProfileCreatedEmail(profile, comment):
        """Notify the profile's email owner that a new profile was created.

        Send an email message to this token's email address explaining that
        another user has created a launchpad profile for him and providing
        a link where he can finish the registration process.
        """

    def sendMergeRequestEmail():
        """Send an email to self.email (the dupe account's email address)
        with the URL of a page to finish the merge of Launchpad accounts.
        """

    def sendTeamEmailAddressValidationEmail(user):
        """Send an email to self.email containing a URL to the page where it
        can be set as the requester's (the team) contact address.

        The message also includes the team administrator who made this
        request on behalf of the team.
        """

    def sendClaimProfileEmail():
        """Send an email to self.email with instructions on how to finish
        claiming the profile that owns self.email.
        """

    def sendClaimTeamEmail():
        """E-mail instructions for claiming a team to self.email."""

    def activateGPGKey(key, can_encrypt):
        """Activate a GPG key.

        :return: A Launchpad key, and whether it's new.
        """


class ILoginTokenSet(Interface):
    """The set of LoginTokens."""

    title = Attribute('Title')

    def get(id, default=None):
        """Return the LoginToken object with the given id.

        Return the default value if there's no such LoginToken.
        """

    def searchByEmailRequesterAndType(email, requester, type, consumed=None):
        """Return all LoginTokens for the given email, requester and type.

        :param email: The email address to search for.
        :param requester: The Person object representing the requester
            to search for.
        :param type: The LoginTokenType to search for.
        :param consumed: A flag indicating whether to return consumed tokens.
            If False, only unconsumed tokens will be returned.
            If True, only consumed tokens will be returned.
            If None, this parameter will be ignored and all tokens will be
            returned.
        """

    def deleteByEmailRequesterAndType(email, requester, type):
        """Delete all LoginToken entries with the given email, requester and
        type."""

    def searchByFingerprintRequesterAndType(fingerprint, requester, type,
                                            consumed=None):
        """Return all LoginTokens for the given fingerprint, requester and
        type.

        :param fingerprint: The LoginToken fingerprint to search for.
        :param requester: The Person object representing the requester
            to search for.
        :param type: The LoginTokenType to search for.
        :param consumed: A flag indicating whether to return consumed tokens.
            If False, only unconsumed tokens will be returned.
            If True, only consumed tokens will be returned.
            If None, this parameter will be ignored and all tokens will be
            returned.
        """

    def deleteByFingerprintRequesterAndType(fingerprint, requester, type):
        """Delete all LoginToken entries with the given fingerprint,
        requester and type.
        """

    def getPendingGPGKeys(requesterid=None):
        """Return tokens for OpenPGP keys pending validation, optionally for
        a single user.
        """

    def new(requester, requesteremail, email, tokentype, fingerprint=None,
            redirection_url=None):
        """Create a new LoginToken object. Parameters must be:
        requester: a Person object or None (in case of a new account)

        requesteremail: the email address used to login on the system. Can
                        also be None in case of a new account

        email: the email address that this request will be sent to.
        It should be previously validated by valid_email()

        tokentype: the type of the request, according to LoginTokenType.

        fingerprint: The OpenPGP key fingerprint used to retrieve key
        information from the key server if necessary. This can be None if
        not required to process the 'request' in question.
        """

    def __getitem__(id):
        """Returns the LoginToken with the given id.

        Raises KeyError if there is no such LoginToken.
        """


class IGPGKeyValidationForm(Interface):
    """The schema used by ILoginToken's +validategpg form."""

    text_signature = Text(
        title=_('Signed text'), required=True,
        description=_('The validation text, signed with your key.'))
