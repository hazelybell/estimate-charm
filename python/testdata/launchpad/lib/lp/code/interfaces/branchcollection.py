# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""A collection of branches.

See `IBranchCollection` for more details.
"""

__metaclass__ = type
__all__ = [
    'IAllBranches',
    'IBranchCollection',
    'InvalidFilter',
    ]

from zope.interface import Interface


class InvalidFilter(Exception):
    """Raised when an `IBranchCollection` cannot apply the given filter."""


class IBranchCollection(Interface):
    """A collection of branches.

    An `IBranchCollection` is an immutable collection of branches. It has two
    kinds of methods: filter methods and query methods.

    Query methods get information about the contents of collection. See
    `IBranchCollection.count` and `IBranchCollection.getBranches`.

    Filter methods return new IBranchCollection instances that have some sort
    of restriction. Examples include `ownedBy`, `visibleByUser` and
    `inProduct`.

    Implementations of this interface are not 'content classes'. That is, they
    do not correspond to a particular row in the database.

    This interface is intended for use within Launchpad, not to be exported as
    a public API.
    """

    # Note to developers: This interface should be extended with more query
    # methods. It would be great to have methods like getRecentRevisions on
    # arbitrary branch collections. Other statistical methods would be good
    # too, e.g. number of different branch owners in this collection.

    def count():
        """The number of branches in this collection."""

    def is_empty():
        """Is this collection empty?"""

    def ownerCounts():
        """Return the number of different branch owners.

        :return:  a tuple (individual_count, team_count) containing the number
            of individuals and teams that own branches in this collection.
        """

    def getBranches(eager_load=False):
        """Return a result set of all branches in this collection.

        The returned result set will also join across the specified tables as
        defined by the arguments to this function.  These extra tables are
        joined specificly to allow the caller to sort on values not in the
        Branch table itself.

        :param eager_load: If True trigger eager loading of all the related
            objects in the collection.
        """

    def getBranchIds():
        """Return a result set of all branch ids in this collection."""

    def getMergeProposals(statuses=None, for_branches=None,
                          target_branch=None, eager_load=False):
        """Return a result set of merge proposals for the branches in this
        collection.

        :param statuses: If specified, only return merge proposals with these
            statuses. If not, return all merge proposals.
        :param for_branches: An iterable of branches what will restrict the
            resulting set of merge proposals to be only those where the source
            branch is one of the branches specified.
        :param target_branch: If specified, only return merge proposals
            that target the specified branch.
        :param eager_load: If True, preloads all the related information for
            merge proposals like PreviewDiffs and Branches.
        """

    def getMergeProposalsForPerson(person, status=None):
        """Proposals for `person`.

        Return the proposals for branches owned by `person` or where `person`
        is reviewing or been asked to review.
        """

    def getMergeProposalsForReviewer(reviewer, status=None):
        """Return a result set of merge proposals for the given reviewer.

        That is, all merge proposals that 'reviewer' has voted on or has been
        invited to vote on.

        :param reviewer: An `IPerson` who is a reviewer.
        :param status: An iterable of queue_status of the proposals to return.
            If None is specified, all the proposals of all possible states
            are returned.
        """

    def getExtendedRevisionDetails(user, revisions):
        """Return information about the specified revisions on a branch.

        For each revision, see if the revision resulted from merging in a
        merge proposal, and if so package up the merge proposal and any linked
        bug tasks on the merge proposal's source branch.

        :param user: The user who is making the request. Only bug tasks
            visible to this user are returned.
        :param revisions: The revisions we want details for.
        """

    def getTeamsWithBranches(person):
        """Return the teams that person is a member of that have branches."""

    def inProduct(product):
        """Restrict the collection to branches in 'product'."""

    def inProject(project):
        """Restrict the collection to branches in 'project'."""

    def inSourcePackage(package):
        """Restrict the collection to branches in 'package'.

        A source package is effectively a sourcepackagename in a distro
        series.
        """

    def inDistribution(distribution):
        """Restrict the collection to branches in 'distribution'."""

    def inDistroSeries(distro_series):
        """Restrict the collection to branches in 'distro_series'."""

    def inDistributionSourcePackage(distro_source_package):
        """Restrict to branches in a 'package' for a 'distribution'."""

    def linkedToBugs(bugs):
        """Restrict to branches linked to `bugs`."""

    def officialBranches(pocket=None):
        """Restrict to branches that are official for some source package."""

    def isJunk():
        """Restrict the collection to junk branches.

        A junk branch is a branch that's not associated with a product nor
        with a sourcepackage.
        """

    def isPrivate():
        """Restrict the collection to private branches."""

    def isExclusive():
        """Restrict the collection to branches owned by exclusive people."""

    def isSeries():
        """Restrict the collection to branches those linked to series."""

    def ownedBy(person):
        """Restrict the collection to branches owned by 'person'."""

    def ownedByTeamMember(person):
        """Restrict the collection to branches owned by 'person' or a team
        of which person is a member.
        """

    def registeredBy(person):
        """Restrict the collection to branches registered by 'person'."""

    def search(term):
        """Search the collection for branches matching 'term'.

        :param term: A string.
        :return: A `ResultSet` of branches that matched.
        """

    def scanned():
        """Restrict the collection to branches that have been scanned."""

    def subscribedBy(person):
        """Restrict the collection to branches subscribed to by 'person'."""

    def visibleByUser(person):
        """Restrict the collection to branches that person is allowed to see.
        """

    def withBranchType(*branch_types):
        """Restrict the collection to branches with the given branch types."""

    def withLifecycleStatus(*statuses):
        """Restrict the collection to branches with the given statuses."""

    def modifiedSince(epoch):
        """Restrict the collection to branches modified since `epoch`."""

    def scannedSince(epoch):
        """Restrict the collection to branches scanned since `epoch`."""

    def targetedBy(person):
        """Restrict the collection to branches targeted by person.

        A branch is targeted by a person if that person has registered a merge
        proposal with the branch as the target.

        :param since: If supplied, ignore merge proposals before this date.
        """

    def withIds(*branch_ids):
        """Restrict the collection to branches with the specified ids."""


class IAllBranches(IBranchCollection):
    """A `IBranchCollection` representing all branches in Launchpad."""
