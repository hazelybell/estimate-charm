# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Memcached interfaces."""

__metaclass__ = type
__all__ = ['IMemcacheClient']

from zope.interface import Interface


class IMemcacheClient(Interface):
    """Interface to lookup an initialized memcache.Client instance."""

