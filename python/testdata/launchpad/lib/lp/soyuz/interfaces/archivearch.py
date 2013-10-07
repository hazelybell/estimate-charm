# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""ArchiveArch interfaces."""

__metaclass__ = type

__all__ = [
    'IArchiveArch',
    'IArchiveArchSet',
    ]

from lazr.restful.fields import Reference
from zope.interface import Interface
from zope.schema import Int

from lp import _
from lp.soyuz.interfaces.archive import IArchive
from lp.soyuz.interfaces.processor import IProcessor


class IArchiveArch(Interface):
    """An interface for archive/processor associations."""

    id = Int(title=_('ID'), required=True, readonly=True)

    archive = Reference(
        title=_("Archive"), schema=IArchive,
        required=True, readonly=True,
        description=_(
            "The archive associated with the processor at hand."))

    processor = Reference(
        title=_("Processor"), schema=IProcessor,
        required=True, readonly=True,
        description=_(
            "The processor associated with the archive at hand."))


class IArchiveArchSet(Interface):
    """An interface for sets of archive/processor associations."""
    def new(archive, processor):
        """Create a new archive/processor association.

        :param archive: the archive to be associated.
        :param processor: the processor to be associated.

        :return: a newly created `IArchiveArch`.
        """

    def getByArchive(archive, processor=None):
        """Return associations that match the archive and processor.

        If no processor is passed, all associations for 'archive' will
        be returned.

        :param archive: The associated archive.
        :param processor: An optional processor; if passed only
        associations in which it participates will be considered.

        :return: A (potentially empty) result set of `IArchiveArch` instances.
        """

    def getRestrictedProcessors(archive):
        """All restricted processor, paired with `ArchiveArch`
        instances if associated with `archive`.

        :return: A sequence containing a (`Processor`, `ArchiveArch`)
            2-tuple for each processor.
            The second value in the tuple will be None if the given `archive`
            is not associated with the `Processor` yet.
        """
