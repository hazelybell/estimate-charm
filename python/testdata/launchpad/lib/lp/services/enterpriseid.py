# Copyright 2012-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Enterprise ID utilities."""

__metaclass__ = type
__all__ = [
    'object_to_enterpriseid',
    'enterpriseids_to_objects',
    ]

from collections import defaultdict
import os

from lp.services.config import config
from lp.services.database.bulk import load


def object_to_enterpriseid(obj):
    """Given an object, convert it to SOA Enterprise ID."""
    otype = obj.__class__.__name__
    instance = 'lp'
    if config.devmode:
        instance += '-development'
    elif os.environ['LPCONFIG'] in ('dogfood', 'qastaing', 'staging'):
        instance += '-%s' % os.environ['LPCONFIG']
    return '%s:%s:%d' % (instance, otype, obj.id)


def _known_types():
    # Circular imports.
    from lp.registry.model.person import Person
    from lp.soyuz.model.queue import PackageUpload
    return {
        'PackageUpload': PackageUpload,
        'Person': Person,
    }


def enterpriseids_to_objects(eids):
    """Dereference multiple SOA Enterprise IDs."""
    dbid_to_eid = defaultdict(dict)
    for eid in eids:
        if not eid.startswith('lp'):
            raise TypeError
        instance, cls, id = eid.split(':')
        dbid_to_eid[cls][int(id)] = eid
    types = _known_types()
    eid_to_obj = {}
    for kind in dbid_to_eid:
        objs = load(types[kind], dbid_to_eid[kind].keys())
        for obj in objs:
            eid_to_obj[dbid_to_eid[kind][obj.id]] = obj
    return eid_to_obj
