# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Adapters related to object privacy."""

__metaclass__ = type
__all__ = []

from zope.security.proxy import removeSecurityProxy


class ObjectPrivacy:
    """Generic adapter for IObjectPrivacy.

    It relies on the fact that all our objects supporting privacy use an
    attribute named 'private' to represent that fact.
    """

    def __init__(self, object):
        try:
            self.is_private = removeSecurityProxy(object).private
        except AttributeError:
            self.is_private = False

