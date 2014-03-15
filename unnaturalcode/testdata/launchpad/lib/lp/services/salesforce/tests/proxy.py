# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Helper classes for testing clients of the external Salesforce proxy."""


__metaclass__ = type

__all__ = [
    'SalesforceXMLRPCTestTransport',
    'TestSalesforceVoucherProxy',
    ]


import re
from xmlrpclib import (
    Fault,
    loads,
    Transport,
    )

from zope.interface import implements

from lp.services.salesforce.interfaces import ISalesforceVoucherProxy
from lp.services.salesforce.proxy import SalesforceVoucherProxy


TERM_RE = re.compile("^LPCBS(\d{2})-.*")


def force_fault(func):
    """Decorator to force a fault for testing.

    If the property forced_fault is set and the function matches the specified
    function name, then the fault is returned.  The property must be a tuple
    of (method name, fault, message).
    """
    def decorator(self, *args, **kwargs):
        if self.forced_fault is not None:
            func_name, fault, message = self.forced_fault
            if func_name == func.__name__:
                raise Fault(fault, message)
        return func(self, *args, **kwargs)
    return decorator


class Voucher:
    """Test data for a single voucher."""
    def __init__(self, voucher_id, owner):
        self.voucher_id = voucher_id
        self.owner = owner
        self.status = 'Reserved'
        self.project_id = None
        self.project_name = None
        self.term_months = self._getTermMonths()

    def _getTermMonths(self):
        """Pull the term in months from the voucher_id."""
        match = TERM_RE.match(self.voucher_id)
        if match is None:
            raise Fault('GeneralError',
                        'Invalid voucher id %s' % self.voucher_id)
        num_months = int(match.group(1))
        return num_months

    def __str__(self):
        return "%s,%s" % (self.voucher_id, self.status)

    def asDict(self):
        return dict(voucher_id=self.voucher_id,
                    status=self.status,
                    term_months=self.term_months,
                    project_id=self.project_id)


class TestSalesforceVoucherProxy(SalesforceVoucherProxy):
    """Test version of the SalesforceVoucherProxy using the test transport."""
    implements(ISalesforceVoucherProxy)

    def __init__(self):
        self.xmlrpc_transport = SalesforceXMLRPCTestTransport()


class SalesforceXMLRPCTestTransport(Transport):
    """An XML-RPC test transport for the Salesforce proxy.

    This transport contains a small amount of sample data and intercepts
    requests that would normally be sent via XML-RPC but instead directly
    provides responses based on the sample data.  This transport does not
    simulate network errors or timeouts.
    """

    voucher_index = 0
    voucher_prefix = 'LPCBS%02d-f78df324-0cc2-11dd-0000-%012d'
    # The forced_fault is a tuple (method name, fault, message) or None.  See
    # the decorator `force_fault` for details.
    forced_fault = None

    def __init__(self):
        self.vouchers = [
            # Test vouchers owned by mark.
            Voucher('LPCBS12-f78df324-0cc2-11dd-8b6b-000000000001',
                    'mark_oid'),
            Voucher('LPCBS12-f78df324-0cc2-11dd-8b6b-000000000002',
                    'mark_oid'),
            Voucher('LPCBS12-f78df324-0cc2-11dd-8b6b-000000000003',
                    'mark_oid'),
            # Test vouchers owned by cprov.
            Voucher('LPCBS12-f78df324-0cc2-11dd-8b6b-000000000004',
                    'cprov_oid'),
            Voucher('LPCBS12-f78df324-0cc2-11dd-8b6b-000000000005',
                    'cprov_oid'),
            # Test vouchers owned by bac.
            Voucher('LPCBS12-f78df324-0cc2-11dd-8b6b-bac000000001',
                    'mTmeENb'),
            Voucher('LPCBS12-f78df324-0cc2-11dd-8b6b-bac000000002',
                    'mTmeENb'),
            Voucher('LPCBS12-f78df324-0cc2-11dd-8b6b-bac000000003',
                    'mTmeENb'),
            Voucher('LPCBS12-f78df324-0cc2-11dd-8b6b-bac000000004',
                    'mTmeENb'),
            Voucher('LPCBS12-f78df324-0cc2-11dd-8b6b-bac000000005',
                    'mTmeENb'),
            # Test vouchers owned by commercial-member.
            Voucher('LPCBS12-f78df324-0cc2-11dd-8b6b-com000000001',
                    'rPwGRk4'),
            Voucher('LPCBS12-f78df324-0cc2-11dd-8b6b-com000000002',
                    'rPwGRk4'),
            Voucher('LPCBS12-f78df324-0cc2-11dd-8b6b-com000000003',
                    'rPwGRk4'),
            Voucher('LPCBS12-f78df324-0cc2-11dd-8b6b-com000000004',
                    'rPwGRk4'),
            Voucher('LPCBS12-f78df324-0cc2-11dd-8b6b-com000000005',
                    'rPwGRk4'),
            ]


    def _createVoucher(self, owner_oid, term_months):
        """Create a new voucher with the given term and owner."""
        self.voucher_index += 1
        voucher_id = self.voucher_prefix % (term_months, self.voucher_index)
        voucher = Voucher(voucher_id, owner_oid)
        self.vouchers.append(voucher)
        return voucher

    def _findVoucher(self, voucher_id):
        """Find a voucher by id."""
        for voucher in self.vouchers:
            if voucher.voucher_id == voucher_id:
                return voucher
        return None

    @force_fault
    def getServerStatus(self):
        """Get the server status.  If it responds it is healthy.

        Included here for completeness though it is never called by
        Launchpad.
        """
        return "Server is running normally"

    @force_fault
    def getUnredeemedVouchers(self, lp_openid):
        """Return the list of unredeemed vouchers for a given id.

        The returned value is a list of dictionaries, each having a 'voucher'
        and 'status' keys.
        """
        vouchers = [voucher.asDict() for voucher in self.vouchers
                    if (voucher.owner == lp_openid and
                        voucher.status == 'Reserved')]
        return vouchers

    @force_fault
    def getAllVouchers(self, lp_openid):
        """Return the complete list of vouchers for a given id.

        The returned value is a list of dictionaries, each having a 'voucher',
        'status', and 'project_id' keys.
        """
        vouchers = [voucher.asDict() for voucher in self.vouchers
                    if voucher.owner == lp_openid]
        return vouchers

    @force_fault
    def getVoucher(self, voucher_id):
        """Return the voucher."""

        voucher = self._findVoucher(voucher_id)
        if voucher is None:
            raise Fault('NotFound',
                        'The voucher %s was not found.' % voucher_id)
        voucher = voucher.asDict()
        return voucher

    @force_fault
    def redeemVoucher(self, voucher_id, lp_openid, lp_project_id,
                      lp_project_name):
        """Redeem the voucher.

        :param voucher_id: string representing the unique voucher id.
        :param lp_openid: string representing the Launchpad user's OpenID.
        :param lp_project_id: Launchpad project id
        :param lp_project_name: Launchpad project name
        :return: Boolean representing the success or failure of the operation.
        """
        voucher = self._findVoucher(voucher_id)

        if voucher is None:
            raise Fault('NotFound', 'No such voucher %s' % voucher_id)
        else:
            if voucher.status != 'Reserved':
                raise Fault('AlreadyRedeemed',
                            'Voucher %s is already redeemed' % voucher_id)

            if voucher.owner != lp_openid:
                raise Fault('NotAllowed',
                            'Voucher is not owned by named user')

        voucher.status = 'Redeemed'
        voucher.project_id = lp_project_id
        voucher.project_name = lp_project_name
        return [True]

    @force_fault
    def updateProjectName(self, lp_project_id, new_name):
        """Set the project name for the given project id.

        Returns the number of vouchers that were updated.
        """
        num_updated = 0
        for voucher in self.vouchers:
            if voucher.project_id == lp_project_id:
                voucher.project_name = new_name
                num_updated += 1
        if num_updated == 0:
            raise Fault('NotFound',
                        'No vouchers matching product id %s' % lp_project_id)
        return [num_updated]

    @force_fault
    def grantVoucher(self, admin_openid, approver_openid, recipient_openid,
                     recipient_name, recipient_preferred_email, term_months):
        """Grant a new voucher to the user."""
        voucher = self._createVoucher(recipient_openid, term_months)
        return voucher.voucher_id

    def request(self, host, handler, request, verbose=None):
        """Call the corresponding XML-RPC method.

        The method name and arguments are extracted from `request`. The
        method on this class with the same name as the XML-RPC method is
        called, with the extracted arguments passed on to it.
        """
        args, method_name = loads(request)
        method = getattr(self, method_name)
        return method(*args)
