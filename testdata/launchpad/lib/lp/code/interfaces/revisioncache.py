# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""A collection of revisions.

See `IRevisionCollection` for more details.
"""

__metaclass__ = type
__all__ = [
    'IRevisionCache',
    'IRevisionCollection',
    ]

from zope.interface import Interface


class IRevisionCollection(Interface):
    """A collection of revisions.

    An `IRevisionCollection` is an immutable collection of revisions. It has
    three kinds of methods: filter methods, query methods, and count methods.

    Query methods get information about the contents of collection. At this
    time we only have `getRevisions` to return `Revision` objects from the
    cache.

    Filter methods return new IRevisionCollection instances that have some
    sort of restriction. Examples include `inProduct`, and `public`.

    Count methods just return a number.

    Implementations of this interface are not 'content classes'. That is, they
    do not correspond to a particular row in the database.

    This interface is intended for use within Launchpad, not to be exported as
    a public API.
    """

    def count():
        """The number of revisions in this collection."""

    def authorCount():
        """The number of different people authoring revisions.

        Only revisions in the restricted collection are counted.
        """

    def getRevisions():
        """Return a result set of all the revisions in this collection.

        The revisions are ordered with the newer revision_dates before the
        older ones.
        """

    def inProduct(product):
        """Restrict to revisions in branches in 'product'."""

    def inProject(project):
        """Restrict to revisions in branches in 'project'."""

    def inSourcePackage(package):
        """Restrict to revisions in branches in 'package'.

        A source package is effectively a sourcepackagename in a distro
        series.
        """

    def inDistribution(distribution):
        """Restrict to revisions in branches in 'distribution'.
        """

    def inDistroSeries(distro_series):
        """Restrict to revisions in branches in 'distro_series'.
        """

    def inDistributionSourcePackage(distro_source_package):
        """Restrict to revisions in branches in a 'package' for a
        'distribution'.
        """

    def public():
        """Restrict to revisions that are publicly visible."""

    def authoredBy(person):
        """Restrict to revisions authored by 'person'.

        If `person` is a team, then return revisions that are authored by any
        active participant of that team.
        """


class IRevisionCache(IRevisionCollection):
    """An `IRevisionCollection` representing recent revisions in Launchpad.

    In order to have efficient queries, only revisions in the last 30 days are
    cached for fast counting and access.

    The revisions that are returned from the cache are used for counts on
    summary pages and to populate the feeds.
    """
