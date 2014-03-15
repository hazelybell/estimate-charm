# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces related to Salesforce vouchers."""

__metaclass__ = type

__all__ = [
    'ISalesforceVoucher',
    'ISalesforceVoucherProxy',
    'SalesforceVoucherProxyException',
    'SFDCError',
    'SVPAlreadyRedeemedException',
    'SVPNotAllowedException',
    'SVPNotFoundException',
    'VOUCHER_STATUSES',
    'REDEEMABLE_VOUCHER_STATUSES',
    ]

from zope.interface import Interface
from zope.schema import (
    Choice,
    Int,
    TextLine,
    )

from lp import _


REDEEMABLE_VOUCHER_STATUSES = [
    'Unredeemed',
    'Reserved',
    ]

VOUCHER_STATUSES = REDEEMABLE_VOUCHER_STATUSES + ['Redeemed']


class SalesforceVoucherProxyException(Exception):
    """Exception raised on failed call to the SalesforceVoucherProxy."""


class SFDCError(SalesforceVoucherProxyException):
    """An exception was reported by salesforce.com."""


class SVPNotFoundException(SalesforceVoucherProxyException):
    """A named object was not found."""


class SVPAlreadyRedeemedException(SalesforceVoucherProxyException):
    """The voucher has already been redeemed."""


class SVPNotAllowedException(SalesforceVoucherProxyException):
    """The operation is not allowed by the current user."""


class ISalesforceVoucherProxy(Interface):
    """Wrapper class for voucher processing with Salesforce.

    These vouchers are used to allow commercial projects to subscribe to
    Launchpad.
    """

    def getUnredeemedVouchers(user):
        """Get the unredeemed vouchers for the user."""

    def getAllVouchers(user):
        """Get all of the vouchers for the user."""

    def getServerStatus():
        """Get the server status."""

    def getVoucher(voucher_id):
        """Lookup a voucher."""

    def redeemVoucher(voucher_id, user, project):
        """Redeem a voucher.

        :param voucher_id: string with the id of the voucher to be redeemed.
        :param user: user who is redeeming the voucher.
        :param project: project that is being subscribed.
        :return: list with a boolean indicating status of redemption, and an
            integer representing the number of months the subscription
            allows.
        """

    def updateProjectName(project):
        """Update the name of a project in Salesforce.

        If a project changes its name it is updated in Salesforce.
        :param project: the project to update
        :return: integer representing the number of vouchers found for this
            project which were updated.
        """

    def grantVoucher(admin, approver, recipient, term_months):
        """An administrator can grant a voucher to a Launchpad user.

        :param admin: the admin who is making the grant.
        :param approver: the manager who approved the grant.
        :param recipient: the user who is being given the voucher.
        :param term_months: integer representing the number of months for the
            voucher.
        :return: the voucher id of the newly granted voucher.

        This call assumes the admin and approver already exist in the
        Salesforce database and can be looked up via their OpenID.  The
        recipient may or may not exist, therefore basic information about the
        recipient is sent in the call.
        """


class ISalesforceVoucher(Interface):
    """Vouchers in Salesforce."""

    voucher_id = TextLine(
        title=_("Voucher ID"),
        description=_("The id for the voucher."))
    project = Choice(
        title=_('Project'),
        required=False,
        vocabulary='Product',
        description=_("The project the voucher is redeemed against."))
    status = TextLine(
        title=_("Status"),
        description=_("The voucher's redemption status."))
    term_months = Int(
        title=_("Term in months"),
        description=_("The voucher can be redeemed for a subscription "
                      "for this number of months."))
