# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interface for a branch namespace."""

__metaclass__ = type
__all__ = [
    'get_branch_namespace',
    'IBranchNamespace',
    'IBranchNamespacePolicy',
    'IBranchNamespaceSet',
    'lookup_branch_namespace',
    'split_unique_name',
    ]

from zope.component import getUtility
from zope.interface import (
    Attribute,
    Interface,
    )

from lp.code.enums import BranchLifecycleStatus


class IBranchNamespace(Interface):
    """A namespace that a branch lives in."""

    name = Attribute(
        "The name of the namespace. This is prepended to the branch name.")

    target = Attribute("The branch target for this namespace.")

    def createBranch(branch_type, name, registrant, url=None, title=None,
                     lifecycle_status=BranchLifecycleStatus.DEVELOPMENT,
                     summary=None, whiteboard=None):
        """Create and return an `IBranch` in this namespace."""

    def createBranchWithPrefix(branch_type, prefix, registrant, url=None):
        """Create and return an `IBranch` with a name starting with 'prefix'.

        Use this method to automatically create a branch with an inferred
        name.
        """

    def findUnusedName(prefix):
        """Find an unused branch name starting with 'prefix'.

        Note that there is no guarantee that the name returned by this method
        will remain unused for very long. If you wish to create a branch with
        a given prefix, use createBranchWithPrefix.
        """

    def getBranches(eager_load=False):
        """Return the branches in this namespace.

        :param eager_load: If True eager load related data for the branches.
        """

    def getBranchName(name):
        """Get the potential unique name for a branch called 'name'.

        Note that this name is not guaranteed to be unique. Rather, if there
        *was* such a branch with that name, this would be the value of its
        `IBranch.unique_name` property.
        """

    def getByName(name, default=None):
        """Find the branch in this namespace called 'name'.

        :return: `IBranch` if found, 'default' if not.
        """

    def isNameUsed(name):
        """Is 'name' already used in this namespace?"""

    def moveBranch(branch, mover, new_name=None, rename_if_necessary=False):
        """Move the branch into this namespace.

        :param branch: The `IBranch` to move.
        :param mover: The `IPerson` doing the moving.
        :param new_name: A new name for the branch.
        :param rename_if_necessary: Rename the branch if the branch name
            exists already in this namespace.
        :raises BranchCreatorNotMemberOfOwnerTeam: if the namespace owner is
            a team, and 'mover' is not in that team.
        :raises BranchCreatorNotOwner: if the namespace owner is an individual
            and 'mover' is not the owner.
        :raises BranchCreationForbidden: if 'mover' is not allowed to create
            a branch in this namespace due to privacy rules.
        :raises BranchExists: if a branch with the 'name' exists already in
            the namespace, and 'rename_if_necessary' is False.
        """


class IBranchNamespacePolicy(Interface):
    """Methods relating to branch creation and validation."""

    def getPrivacySubscriber():
        """Get the implicit privacy subscriber for a new branch.

        :return: An `IPerson` or None.
        """

    def canCreateBranches(user):
        """Is the user allowed to create branches for this namespace?

        :param user: An `IPerson`.
        :return: A Boolean value.
        """

    def getAllowedInformationTypes(who):
        """Get the information types that a branch in this namespace can have.

        :param who: The user making the request.
        :return: A sequence of `InformationType`s.
        """

    def getDefaultInformationType(who):
        """Get the default information type for branches in this namespace.

        :param who: The user for whom to return the information type.
        :return: An `InformationType`.
        """

    def validateRegistrant(registrant, branch=None):
        """Check that the registrant can create a branch on this namespace.

        :param registrant: An `IPerson`.
        :param branch: An optional `IBranch` to also check when working
            with imported branches.
        :raises BranchCreatorNotMemberOfOwnerTeam: if the namespace owner is
            a team, and the registrant is not in that team.
        :raises BranchCreatorNotOwner: if the namespace owner is an individual
            and the registrant is not the owner.
        :raises BranchCreationForbidden: if the registrant is not allowed to
            create a branch in this namespace due to privacy rules.
        """

    def validateBranchName(name):
        """Check the branch `name`.

        :param name: A branch name, either string or unicode.
        :raises BranchExists: if a branch with the `name` exists already in
            the namespace.
        :raises LaunchpadValidationError: if the name doesn't match the
            validation constraints on IBranch.name.
        """

    def validateMove(branch, mover, name=None):
        """Check that 'mover' can move 'branch' into this namespace.

        :param branch: An `IBranch` that might be moved.
        :param mover: The `IPerson` who would move it.
        :param name: A new name for the branch.  If None, the branch name is
            used.
        :raises BranchCreatorNotMemberOfOwnerTeam: if the namespace owner is
            a team, and 'mover' is not in that team.
        :raises BranchCreatorNotOwner: if the namespace owner is an individual
            and 'mover' is not the owner.
        :raises BranchCreationForbidden: if 'mover' is not allowed to create
            a branch in this namespace due to privacy rules.
        :raises BranchExists: if a branch with the 'name' exists already in
            the namespace.
        """


class IBranchNamespaceSet(Interface):
    """Interface for getting branch namespaces.

    This interface exists *solely* to avoid importing things from the
    'database' package. Use `get_branch_namespace` to get branch namespaces
    instead.
    """

    def get(person, product, distroseries, sourcepackagename):
        """Return the appropriate `IBranchNamespace` for the given objects."""

    def lookup(namespace_name):
        """Return the `IBranchNamespace` for 'namespace_name'.

        :raise InvalidNamespace: if namespace_name cannot be parsed.
        :raise NoSuchPerson: if the person referred to cannot be found.
        :raise NoSuchProduct: if the product referred to cannot be found.
        :raise NoSuchDistribution: if the distribution referred to cannot be
            found.
        :raise NoSuchDistroSeries: if the distroseries referred to cannot be-
            found.
        :raise NoSuchSourcePackageName: if the sourcepackagename referred to
            cannot be found.
        :return: An `IBranchNamespace`.
        """

    def interpret(person, product, distribution, distroseries,
                  sourcepackagename):
        """Like `get`, but takes names of objects.

        :raise NoSuchPerson: if the person referred to cannot be found.
        :raise NoSuchProduct: if the product referred to cannot be found.
        :raise NoSuchDistribution: if the distribution referred to cannot be
            found.
        :raise NoSuchDistroSeries: if the distroseries referred to cannot be-
            found.
        :raise NoSuchSourcePackageName: if the sourcepackagename referred to
            cannot be found.
        :return: An `IBranchNamespace`.
        """

    def parse(namespace_name):
        """Parse 'namespace_name' into its components.

        The name of a namespace is actually a path containing many elements,
        each of which maps to a particular kind of object in Launchpad.
        Elements that can appear in a namespace name are: 'person', 'product',
        'distribution', 'distroseries' and 'sourcepackagename'.

        'parse' returns a dict which maps the names of these elements (e.g.
        'person', 'product') to the values of these elements (e.g. 'mark',
        'firefox'). If the given path doesn't include a particular kind of
        element, the dict maps that element name to None.

        For example::
            parse('~foo/bar') => {
                'person': 'foo', 'product': 'bar', 'distribution': None,
                'distroseries': None, 'sourcepackagename': None}

        If the given 'namespace_name' cannot be parsed, then we raise an
        `InvalidNamespace` error.

        :raise InvalidNamespace: if the name is too long, too short or is
            malformed.
        :return: A dict with keys matching each component in 'namespace_name'.
        """

    def traverse(segments):
        """Look up the branch at the path given by 'segments'.

        The iterable 'segments' will be consumed until a branch is found. As
        soon as a branch is found, the branch will be returned and the
        consumption of segments will stop. Thus, there will often be
        unconsumed segments that can be used for further traversal.

        :param segments: An iterable of names of Launchpad components.
            The first segment is the username, *not* preceded by a '~`.
        :raise InvalidNamespace: if there are not enough segments to define a
            branch.
        :raise NoSuchPerson: if the person referred to cannot be found.
        :raise NoSuchProduct: if the product or distro referred to cannot be
            found.
        :raise NoSuchDistribution: if the distribution referred to cannot be
            found.
        :raise NoSuchDistroSeries: if the distroseries referred to cannot be-
            found.
        :raise NoSuchSourcePackageName: if the sourcepackagename referred to
            cannot be found.
        :return: `IBranch`.
        """


def get_branch_namespace(person, product=None, distroseries=None,
                         sourcepackagename=None):
    return getUtility(IBranchNamespaceSet).get(
        person, product, distroseries, sourcepackagename)


def lookup_branch_namespace(namespace_name):
    return getUtility(IBranchNamespaceSet).lookup(namespace_name)


def split_unique_name(unique_name):
    """Return the namespace and branch name of a unique name."""
    return unique_name.rsplit('/', 1)
