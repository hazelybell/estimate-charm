# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Utilities for accessing the external Salesforce proxy."""

__metaclass__ = type

__all__ = [
    'SalesforceVoucherProxy',
    'SalesforceVoucherProxyException',
    'Voucher',
    ]


from xmlrpclib import (
    Fault,
    ServerProxy,
    )

from zope.component import getUtility
from zope.interface import implements

from lp.registry.interfaces.product import IProductSet
from lp.services.config import config
from lp.services.propertycache import cachedproperty
from lp.services.salesforce.interfaces import (
    ISalesforceVoucher,
    ISalesforceVoucherProxy,
    SalesforceVoucherProxyException,
    SFDCError,
    SVPAlreadyRedeemedException,
    SVPNotAllowedException,
    SVPNotFoundException,
    )
from lp.services.timeout import SafeTransportWithTimeout


def fault_mapper(func):
    """Decorator to catch Faults and map them to our exceptions."""

    errorcode_map = dict(SFDCError=SFDCError,
                         NotFound=SVPNotFoundException,
                         AlreadyRedeemed=SVPAlreadyRedeemedException,
                         NotAllowed=SVPNotAllowedException)

    def decorator(*args, **kwargs):
        try:
            results = func(*args, **kwargs)
        except Fault as fault:
            exception = errorcode_map.get(fault.faultCode,
                                          SalesforceVoucherProxyException)
            raise exception(fault.faultString)
        return results
    return decorator


class Voucher:
    """A Commercial Subscription voucher."""

    implements(ISalesforceVoucher)

    def __init__(self, values):
        """Initialize using the values as returned from the SF proxy.
        :param values['voucher_id']: voucher id.
        :param values['status']: string representing the redemption status.
        :param values['term']: integer representing number of months of
            subscription the voucher enables.
        :param values['project_id']: integer id for the project this voucher
            has been redeemed  against.  If unredeemed this entry is absent.
        """
        self.voucher_id = values.get('voucher_id')
        self.status = values.get('status')
        self.term_months = values.get('term_months')
        project_id = values.get('project_id')
        if project_id is not None:
            self.project = getUtility(IProductSet).get(project_id)
        else:
            self.project = None

    def __str__(self):
        if self.project is None:
            project_name = "unassigned"
        else:
            project_name = self.project.name
        return "%s,%s,%s,%s" % (self.voucher_id,
                                self.status,
                                self.term_months,
                                project_name)


class SalesforceVoucherProxy:

    implements(ISalesforceVoucherProxy)

    def __init__(self):
        self.xmlrpc_transport = SafeTransportWithTimeout(
            config.commercial.voucher_proxy_timeout / 1000.0)

    @cachedproperty
    def url(self):
        """Get the proxy URL with port."""
        return "%s:%d" % (config.commercial.voucher_proxy_url,
                          config.commercial.voucher_proxy_port)
    @property
    def server(self):
        """See `ISalesforceVoucherProxy`."""
        # This is not a cachedproperty as each use needs a new proxy.
        return ServerProxy(self.url,
                           transport=self.xmlrpc_transport,
                           allow_none=True)

    def _getUserIdentifiers(self, user):
        """Return the user's openid_identifier."""
        from zope.security.proxy import removeSecurityProxy
        return [
            identifier.identifier for identifier
                in removeSecurityProxy(user.account).openid_identifiers]

    @fault_mapper
    def getUnredeemedVouchers(self, user):
        """See `ISalesforceVoucherProxy`."""
        all_vouchers = []
        for identifier in self._getUserIdentifiers(user):
            vouchers = self.server.getUnredeemedVouchers(identifier)
            if isinstance(vouchers, dict):
                all_vouchers.append(vouchers)
            else:
                all_vouchers.extend(vouchers)
        return [Voucher(voucher) for voucher in all_vouchers]

    @fault_mapper
    def getAllVouchers(self, user):
        """See `ISalesforceVoucherProxy`."""
        all_vouchers = []
        for identifier in self._getUserIdentifiers(user):
            vouchers = self.server.getAllVouchers(identifier)
            if isinstance(vouchers, dict):
                all_vouchers.append(vouchers)
            else:
                all_vouchers.extend(vouchers)
        return [Voucher(voucher) for voucher in all_vouchers]

    @fault_mapper
    def getServerStatus(self):
        """See `ISalesforceVoucherProxy`."""
        status = self.server.getServerStatus()
        return status

    @fault_mapper
    def getVoucher(self, voucher_id):
        """See `ISalesforceVoucherProxy`."""
        voucher = self.server.getVoucher(voucher_id)
        if voucher is not None:
            voucher = Voucher(voucher)
        return voucher

    @fault_mapper
    def redeemVoucher(self, voucher_id, user, project):
        """See `ISalesforceVoucherProxy`."""
        for identifier in self._getUserIdentifiers(user):
            vouchers = self.server.getAllVouchers(identifier)
            if isinstance(vouchers, dict):
                vouchers = [vouchers]
            for voucher in vouchers:
                if voucher['voucher_id'] == voucher_id:
                    status = self.server.redeemVoucher(
                        voucher_id, identifier,
                        project.id, project.displayname)
                    return status
        # This will fail, but raise the expected exception.
        return self.server.redeemVoucher(
            voucher_id, identifier,
            project.id, project.displayname)

    @fault_mapper
    def updateProjectName(self, project):
        """See `ISalesforceVoucherProxy`."""
        num_updated = self.server.updateProjectName(project.id,
                                                    project.name)
        return num_updated

    @fault_mapper
    def grantVoucher(self, admin, approver, recipient, term_months):
        """See `ISalesforceVoucherProxy`."""
        from zope.security.proxy import removeSecurityProxy
        # Bypass zope's security because IEmailAddress.email is not public.
        naked_email = removeSecurityProxy(recipient.preferredemail)
        admin_identifier = removeSecurityProxy(
            admin.account).openid_identifiers.any().identifier
        approver_identifier = removeSecurityProxy(
            approver.account).openid_identifiers.any().identifier
        recipient_identifier = removeSecurityProxy(
            recipient.account).openid_identifiers.any().identifier
        voucher_id = self.server.grantVoucher(
            admin_identifier, approver_identifier,
            recipient_identifier, recipient.name,
            naked_email.email, term_months)
        return voucher_id
