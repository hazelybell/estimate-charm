# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces including and related to ICommercialSubscription."""

__metaclass__ = type

__all__ = [
    'ICommercialSubscription',
    ]

from lazr.restful.declarations import (
    export_as_webservice_entry,
    exported,
    )
from lazr.restful.fields import ReferenceChoice
from zope.interface import Interface
from zope.schema import (
    Bool,
    Datetime,
    Int,
    Text,
    TextLine,
    )

from lp import _
from lp.services.fields import PublicPersonChoice


class ICommercialSubscription(Interface):
    """A Commercial Subscription for a Product.

    If the product has a licence which does not qualify for free
    hosting, a subscription needs to be purchased.
    """
    # Mark commercial subscriptions as exported entries for the Launchpad API.
    export_as_webservice_entry()

    id = Int(title=_('ID'), readonly=True, required=True)

    product = exported(
        ReferenceChoice(
            title=_("Product which has commercial subscription"),
            required=True,
            readonly=True,
            vocabulary='Product',
            # Really IProduct. See lp/registry/interfaces/product.py
            schema=Interface,
            description=_(
                "Project for which this commercial subscription is "
                "applied.")))

    date_created = exported(
        Datetime(
            title=_('Date Created'),
            readonly=True,
            description=_("The date the first subscription was applied.")))

    date_last_modified = exported(
        Datetime(
            title=_('Date Modified'),
            description=_("The date the subscription was modified.")))

    date_starts = exported(
        Datetime(
            title=_('Beginning of Subscription'),
            description=_("The date the subscription starts.")))

    date_expires = exported(
        Datetime(
            title=_('Expiration Date'),
            description=_("The expiration date of the subscription.")))

    registrant = exported(
        PublicPersonChoice(
            title=_('Registrant'),
            required=True,
            readonly=True,
            vocabulary='ValidPerson',
            description=_("Person who redeemed the voucher.")))

    purchaser = exported(
        PublicPersonChoice(
            title=_('Purchaser'),
            required=True,
            readonly=True,
            vocabulary='ValidPerson',
            description=_("Person who purchased the voucher.")))

    sales_system_id = TextLine(
        title=_('Voucher'),
        description=_("Code to redeem subscription."))

    whiteboard = Text(
        title=_("Whiteboard"), required=False,
        description=_("Notes on this project subscription."))

    is_active = exported(
        Bool(
            title=_('Active'),
            readonly=True,
            description=_("Whether this subscription is active.")))

    def delete():
        """Delete the expired Commercial Subscription.

        :raises: CannotDeleteCommercialSubscription when is_active is True.
        """
