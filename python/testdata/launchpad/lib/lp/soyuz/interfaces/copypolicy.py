# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Package copy policies."""

__metaclass__ = type
__all__ = [
    'ICopyPolicy',
    ]


from zope.interface import Interface
from zope.schema import (
    Bool,
    Choice,
    )

from lp import _
from lp.soyuz.enums import PackageCopyPolicy


class ICopyPolicy(Interface):
    """Policies for copying packages, as enumerated by `PackageCopyPolicy`."""

    enum_value = Choice(
        title=_("PackageCopyPolicy number associated with this policy."),
        values=PackageCopyPolicy, readonly=True, required=True)

    send_email = Bool(
        title=_("Should completion of this copy be announced by email?"),
        readonly=True, required=True)

    def autoApprove(archive, distroseries, pocket):
        """Can this upload of a known package be approved automatically?

        This should only be called for packages that are known not new.

        :param archive: The target `IArchive` for the upload.
        :param distroseries: The target `IDistroSeries` for the upload.
        :param pocket: The target `PackagePublishingPocket` for the upload.
        :return: True if the upload can be auto-approved, or False if it
            should be held in the queue.
        """

    def autoApproveNew(archive, distroseries, pocket):
        """Can this upload of a new package be approved automatically?

        :param archive: The target `IArchive` for the upload.
        :param distroseries: The target `IDistroSeries` for the upload.
        :param pocket: The target `PackagePublishingPocket` for the upload.
        :return: True if the upload can be auto-approved, or False if it
            should be held in the queue.
        """
