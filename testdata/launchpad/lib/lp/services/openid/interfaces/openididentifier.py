# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""OpenIdIdentifier interface"""

__metaclass__ = type
__all__ = ['IOpenIdIdentifier']

from zope.interface import Interface
from zope.schema import (
    Datetime,
    Object,
    TextLine,
    )

from lp import _
from lp.services.identity.interfaces.account import IAccount


class IOpenIdIdentifier(Interface):
    """An OpenId Identifier that can be used to log into an Account"""
    account = Object(schema=IAccount, required=True)
    identifier = TextLine(title=_("OpenId Identity"), required=True)
    date_created = Datetime(
        title=_("Date Created"), required=True, readonly=True)
