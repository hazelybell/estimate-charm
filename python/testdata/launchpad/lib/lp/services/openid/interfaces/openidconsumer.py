# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces for OpenID consumer functions."""

__metaclass__ = type
__all__ = ['IOpenIDConsumerStore']

from zope.interface import Interface


class IOpenIDConsumerStore(Interface):
    """An OpenID association and nonce store for Launchpad."""
