# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'ArchiveArch',
    'ArchiveArchSet'
    ]

from storm.expr import (
    And,
    LeftJoin,
    )
from storm.locals import (
    Int,
    Reference,
    Storm,
    )
from zope.interface import implements

from lp.services.database.interfaces import IStore
from lp.soyuz.interfaces.archivearch import (
    IArchiveArch,
    IArchiveArchSet,
    )
from lp.soyuz.model.processor import Processor


class ArchiveArch(Storm):
    """See `IArchiveArch`."""
    implements(IArchiveArch)
    __storm_table__ = 'ArchiveArch'
    id = Int(primary=True)

    archive_id = Int(name='archive', allow_none=False)
    archive = Reference(archive_id, 'Archive.id')
    processor_id = Int(name='processor', allow_none=False)
    processor = Reference(processor_id, Processor.id)


class ArchiveArchSet:
    """See `IArchiveArchSet`."""
    implements(IArchiveArchSet)

    def new(self, archive, processor):
        """See `IArchiveArchSet`."""
        archivearch = ArchiveArch()
        archivearch.archive = archive
        archivearch.processor = processor
        IStore(ArchiveArch).add(archivearch)
        return archivearch

    def getByArchive(self, archive, processor=None):
        """See `IArchiveArchSet`."""
        clauses = [ArchiveArch.archive == archive]
        if processor is not None:
            clauses.append(ArchiveArch.processor_id == processor.id)

        return IStore(ArchiveArch).find(ArchiveArch, *clauses).order_by(
            ArchiveArch.id)

    def getRestrictedProcessors(self, archive):
        """See `IArchiveArchSet`."""
        origin = (
            Processor,
            LeftJoin(
                ArchiveArch,
                And(ArchiveArch.archive == archive.id,
                    ArchiveArch.processor == Processor.id)))
        return IStore(ArchiveArch).using(*origin).find(
            (Processor, ArchiveArch),
            Processor.restricted == True).order_by(Processor.name)
