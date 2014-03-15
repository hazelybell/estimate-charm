# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces for CodeOfConduct (CoC) and related classes.

https://launchpad.canonical.com/CodeOfConduct
"""

__metaclass__ = type

__all__ = [
    'ICodeOfConduct',
    'ISignedCodeOfConduct',
    'ICodeOfConductSet',
    'ISignedCodeOfConductSet',
    'ICodeOfConductConf',
    ]

from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Bool,
    Choice,
    Datetime,
    Int,
    Text,
    )

from lp import _


class ICodeOfConduct(Interface):
    """Pristine Code of Conduct content."""

    version = Attribute("CoC Release Version")
    title = Attribute("CoC Release Title")
    content = Attribute("CoC File Content")
    current = Attribute("True if the release is the current one")
    datereleased = Attribute("The date it was released")


class ISignedCodeOfConduct(Interface):
    """The Signed Code of Conduct."""

    id = Int(title=_("Signed CoC ID"),
             required=True,
             readonly=True
             )

    owner = Choice(
        title=_('Owner'), required=True, vocabulary='ValidOwner',
        description=_(
            """The person who signed the code of conduct by mail or fax."""
        )
        )

    signedcode = Text(title=_("Signed Code"))

    signingkey = Choice(title=_('Signing OpenPGP Key'),
                        description=_("""OpenPGP key ID used to sign the
                        document. It must be valid inside the Launchpad
                        context."""),
                        vocabulary='ValidGPGKey',
                        required=True
                        )

    datecreated = Datetime(title=_("Date Created"),
                           description=_("Original Request Timestamp")
                           )

    recipient = Int(title=_("Recipient"),
                    description=_("Person Authorizing.")
                    )

    admincomment = Text(
        title=_("Admin Comment"),
        description=_("Admin comment, to e.g. describe the reasons why "
                      "this registration was approved or rejected.")
        )

    active = Bool(title=_("Active"),
                  description=_("Whether or not this Signed CoC "
                                "is considered active.")
                  )


    displayname = Attribute("Fancy Title for CoC.")

    def sendAdvertisementEmail(subject, content):
        """Send Advertisement email to signature owner preferred address
        containing arbitrary content and subject.
        """


# Interfaces for containers
class ICodeOfConductSet(Interface):
    """Unsigned (original) Codes of Conduct container."""

    title = Attribute('Page Title propose')
    current_code_of_conduct = Attribute('The current Code of Conduct')

    def __getitem__(version):
        """Get a original CoC Release by its version

        The version 'console' is a special bind for 'Adminitrative Console
        Interface via ISignedCodeOfConductSet.
        If the requested version was not found in the filesystem, it returns
        None, generating a NotFoundError.
        """

    def __iter__():
        """Iterate through the original CoC releases in this set."""


class ISignedCodeOfConductSet(Interface):
    """A container for Signed CoC."""

    title = Attribute('Page Title propose')

    def __getitem__(id):
        """Get a Signed CoC by id."""

    def __iter__():
        """Iterate through the Signed CoC in this set."""

    def verifyAndStore(user, signedcode):
        """Verify and Store a Signed CoC."""

    def searchByDisplayname(displayname, searchfor=None):
        """Search SignedCoC by Owner.displayname"""

    def searchByUser(user_id, active=True):
        """Search SignedCoC by Owner.id, return only the active ones by
        default.
        """

    def modifySignature(sign_id, recipient, admincomment, state):
        """Modify a Signed CoC."""

    def acknowledgeSignature(user, recipient):
        """Acknowledge a paper submitted Signed CoC."""

    def getLastAcceptedDate():
        """Return a datetime object corresponding to the last accepted date
        of Code of Conduct Signature.
        """

class ICodeOfConductConf(Interface):
    """Component to store the CoC Configuration."""

    path = Attribute("CoCs FS path")
    prefix = Attribute("CoC Title Prefix")
    currentrelease = Attribute("Current CoC release")
    datereleased = Attribute("Date when Current CoC was released")
