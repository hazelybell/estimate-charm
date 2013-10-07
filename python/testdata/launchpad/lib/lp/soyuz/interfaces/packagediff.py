# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces related to package-diff system."""

__metaclass__ = type

__all__ = [
    'IPackageDiff',
    'IPackageDiffSet',
    'PackageDiffAlreadyRequested',
    ]

import httplib

from lazr.restful.declarations import error_status
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Choice,
    Datetime,
    Object,
    )

from lp import _
from lp.services.librarian.interfaces import ILibraryFileAlias
from lp.soyuz.enums import PackageDiffStatus


@error_status(httplib.BAD_REQUEST)
class PackageDiffRequestException(Exception):
    """Base class for package diff request errors."""


class PackageDiffAlreadyRequested(PackageDiffRequestException):
    """Raised on attempts to request an already recorded diff request. """


class IPackageDiff(Interface):
    """Package diff request and storage.

    See `doc/package-diff.txt` for details about the attributes.
    """
    id = Attribute("The PackageDiff unique number.")

    from_source = Attribute(_("The base ISourcePackageRelease."))
    to_source = Attribute(_("The target ISourcePackageRelease."))

    date_requested = Datetime(
        title=_('Date Requested'), required=True, readonly=True)

    requester = Choice(
        title=_('User'),
        required=True,
        vocabulary='ValidPerson',
        description=_("The person requesting the diff."))

    date_fulfilled = Datetime(
        title=_('Date Fulfilled'), required=False)

    diff_content = Object(
        schema=ILibraryFileAlias,
        title=_("The ILibraryFileAlias containing the diff."),
        required=False)

    status = Choice(
        title=_('Status'),
        description=_('The status of this package diff request.'),
        vocabulary='PackageDiffStatus',
        required=False, default=PackageDiffStatus.PENDING,
        )

    title = Attribute("The Package diff title.")

    private = Attribute(
        "Whether or not the package diff content is private. "
        "A package diff is considered private when 'to_source' was "
        "originally uploaded to a private archive.")

    def performDiff():
        """Performs a diff between two packages."""


class IPackageDiffSet(Interface):
    """The set of `PackageDiff`."""

    def __iter__():
        """Iterate over all `PackageDiff`."""

    def get(diff_id):
        """Retrieve a `PackageDiff` for the given id."""

    def getDiffsToReleases(sprs, preload_for_display=False):
        """Return all diffs that targetting a set of source package releases.

        :param sprs: a sequence of `SourcePackageRelease` objects.
        :param preload_for_display: True if all the attributes needed for
            link rendering should be preloaded.

        :return a `ResultSet` ordered by `SourcePackageRelease` ID and
        then diff request date in descending order.  If sprs is empty,
        EmptyResultSet is returned.
        """

    def getDiffBetweenReleases(from_spr, to_spr):
        """Return the diff that is targetted to the two SPRs.

        :param from_spr: a `SourcePackageRelease` object.
        :param to_spr:  a `SourcePackageRelease` object.

        :return a `PackageDiff` or None.
        """
