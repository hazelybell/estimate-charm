# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""PackageCopyRequest interfaces."""

__metaclass__ = type

__all__ = [
    'IPackageCopyRequest',
    'IPackageCopyRequestSet',
    ]

from zope.interface import Interface
from zope.schema import (
    Bool,
    Choice,
    Datetime,
    Int,
    Object,
    Text,
    )

from lp import _
from lp.registry.interfaces.distroseries import IDistroSeries
from lp.registry.interfaces.person import IPerson
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.soyuz.enums import PackageCopyStatus
from lp.soyuz.interfaces.archive import IArchive
from lp.soyuz.interfaces.component import IComponent


class IPackageCopyRequest(Interface):
    """A Build interface"""

    id = Int(title=_('ID'), required=True, readonly=True)

    target_archive = Object(
        title=_("Target archive"), schema=IArchive,
        required=True, readonly=True,
        description=_("The archive to which packages will be copied."))

    target_distroseries = Object(
        title=_("Target distroseries"), schema=IDistroSeries,
        required=False, readonly=True,
        description=_("The target DistroSeries."))

    target_component = Object(
        title=_("Target component"), schema=IComponent,
        required=False, readonly=True,
        description=_("The target component."))

    target_pocket = Choice(
        title=_('Target pocket'), required=False,
        vocabulary=PackagePublishingPocket,
        description=_("The target pocket."))

    copy_binaries = Bool(
        title=_('Copy binaries'), required=True, default=False,
        description=_("Whether binary packages should be copied as well."))

    source_archive = Object(
        title=_("Source archive"), schema=IArchive,
        required=True, readonly=True,
        description=_("The archive from which packages will be copied."))

    source_distroseries = Object(
        title=_("Source distroseries"), schema=IDistroSeries,
        required=False, readonly=True,
        description=_("The source DistroSeries."))

    source_component = Object(
        title=_("Source component"), schema=IComponent,
        required=False, readonly=True,
        description=_("The source component."))

    source_pocket = Choice(
        title=_('Source pocket'), required=False,
        vocabulary=PackagePublishingPocket,
        description=_("The source pocket."))

    requester = Object(
        title=_("Requester"), schema=IPerson,
        required=True, readonly=True,
        description=_("The person who requested the package copy operation."))

    status = Choice(
        title=_('Copy status'), required=True,
        vocabulary=PackageCopyStatus,
        description=_("The current status of the copy operation."))

    reason = Text(
        title=_('Reason'), required=False,
        description=_("The reason for this package copy operation."))

    date_created = Datetime(
        title=_('Date created'), required=True, readonly=True,
        description=_("The time when the package copy request was created."))

    date_started = Datetime(
        title=_('Date started'), required=False, readonly=False,
        description=_("The time when the copy request processing started."))

    date_completed = Datetime(
        title=_('Date completed'), required=False, readonly=False,
        description=_("The time when the copy request processing completed."))

    def __str__():
        """Return a textual representation of the package copy request."""

    def markAsInprogress():
        """Mark this request as being in progress.

        Update the 'status' and 'date_started' properties as appropriate.
        """

    def markAsCompleted():
        """Mark this request as completed.

        Update the 'status' and 'date_completed' properties as appropriate.
        """

    def markAsFailed():
        """Mark this request as failed.

        Update the 'status' and 'date_completed' properties as appropriate.
        """

    def markAsCanceling():
        """Mark this request as canceling.

        Update the 'status' as appropriate.
        """

    def markAsCancelled():
        """Mark this request as cancelled.

        Update the 'status' and 'date_completed' properties as appropriate.
        """


class IPackageCopyRequestSet(Interface):
    """Interface for package copy requests."""
    def new(source, target, requester, copy_binaries=False, reason=None):
        """Create a new copy request using the package locations passed.

        :param source: PackageLocation specifying the source of the package
            copy operation.
        :param target: PackageLocation specifying the target of the package
            copy operation.
        :param requester: The person who requested the package copy operation.
        :param copy_binaries: Whether or not binary packages should be copied
            as well.
        :param reason: The reason for this package copy request.

        :return: a newly created `IPackageCopyRequest`.
        """

    def getByPersonAndStatus(requester, status=None):
        """Return copy requests that match requester and status.

        If no status is passed, all copy requests for 'requester' will be
        returned.

        :param requester: The person who requested the package copy operation.
        :param status: Optional `PackageCopyStatus` filter, if passed only
            copy requests with that status will be considered.

        :return: a (potentially empty) result set of `IPackageCopyRequest`
            instances.
        """

    def getByTargetDistroSeries(distroseries):
        """Return copy requests with matching target distroseries.

        :param distroseries: The target distroseries to look for.

        :return: a (potentially empty) result set of `IPackageCopyRequest`
            instances.
        """

    def getBySourceDistroSeries(distroseries):
        """Return copy requests with matching source distroseries.

        :param distroseries: The source distroseries to look for.

        :return: a (potentially empty) result set of `IPackageCopyRequest`
            instances.
        """

    def getByTargetArchive(archive):
        """Return copy requests with matching target archive.

        :param distroseries: The target archive to look for.

        :return: a (potentially empty) result set of `IPackageCopyRequest`
            instances.
        """

