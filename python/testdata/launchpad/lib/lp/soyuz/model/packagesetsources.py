# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""The `PackagesetSources` linking table.

This table associates `Packageset`s with `SourcePackageName`s.
"""

__metaclass__ = type
__all__ = [
    'PackagesetSources',
    ]

from storm.locals import (
    Int,
    Reference,
    Storm,
    )


class PackagesetSources(Storm):
    """Linking table: which packages are in a package set?"""
    # This table is largely managed from Packageset, but also directly
    # accessed from other places.

    __storm_table__ = 'PackagesetSources'

    # There's a vestigial id as well, a holdover from the SQLObject
    # days.  Nobody seems to use it.  The only key that matters is
    # (packageset, sourcepackagename).
    # XXX JeroenVermeulen 2011-06-22, bug=800677: Drop the id column.
    __storm_primary__ = (
        'packageset_id',
        'sourcepackagename_id',
        )

    packageset_id = Int(name='packageset')
    packageset = Reference(packageset_id, 'Packageset.id')
    sourcepackagename_id = Int(name='sourcepackagename')
    sourcepackagename = Reference(
        sourcepackagename_id, 'SourcePackageName.id')

    def __init__(self, packageset, sourcepackagename):
        self.packageset = packageset
        self.sourcepackagename = sourcepackagename
