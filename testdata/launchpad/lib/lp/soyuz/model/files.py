# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'BinaryPackageFile',
    'SourceFileMixin',
    'SourcePackageReleaseFile',
    ]

from sqlobject import ForeignKey
from zope.interface import implements

from lp.registry.interfaces.sourcepackage import SourcePackageFileType
from lp.services.database.enumcol import EnumCol
from lp.services.database.sqlbase import SQLBase
from lp.soyuz.enums import BinaryPackageFileType
from lp.soyuz.interfaces.files import (
    IBinaryPackageFile,
    ISourcePackageReleaseFile,
    )


class BinaryPackageFile(SQLBase):
    """See IBinaryPackageFile """
    implements(IBinaryPackageFile)
    _table = 'BinaryPackageFile'

    binarypackagerelease = ForeignKey(dbName='binarypackagerelease',
                                      foreignKey='BinaryPackageRelease',
                                      notNull=True)
    libraryfile = ForeignKey(dbName='libraryfile',
                             foreignKey='LibraryFileAlias', notNull=True)
    filetype = EnumCol(dbName='filetype',
                       schema=BinaryPackageFileType)


class SourceFileMixin:
    """Mix-in class for common functionality between source file classes."""

    @property
    def is_orig(self):
        return self.filetype in (
            SourcePackageFileType.ORIG_TARBALL,
            SourcePackageFileType.COMPONENT_ORIG_TARBALL
            )


class SourcePackageReleaseFile(SourceFileMixin, SQLBase):
    """See ISourcePackageFile"""

    implements(ISourcePackageReleaseFile)

    sourcepackagerelease = ForeignKey(foreignKey='SourcePackageRelease',
                                      dbName='sourcepackagerelease')
    libraryfile = ForeignKey(foreignKey='LibraryFileAlias',
                             dbName='libraryfile')
    filetype = EnumCol(schema=SourcePackageFileType)
