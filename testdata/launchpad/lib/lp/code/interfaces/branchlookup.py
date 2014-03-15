# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Utility for looking up branches by name."""

__metaclass__ = type
__all__ = [
    'get_first_path_result',
    'IBranchLookup',
    'ILinkedBranchTraversable',
    'ILinkedBranchTraverser',
    ]

from itertools import (
    ifilter,
    imap,
    )

from zope.interface import Interface

from lp.code.interfaces.codehosting import (
    BRANCH_ALIAS_PREFIX,
    BRANCH_ID_ALIAS_PREFIX,
    )
from lp.services.utils import iter_split


class ILinkedBranchTraversable(Interface):
    """A thing that can be traversed to find a thing linked to a branch."""

    def traverse(self, name, segments):
        """Return the object beneath this one that matches 'name'.

        :param name: The name of the object being traversed to.
        :param segments: Remaining path segments.
        :return: An `ILinkedBranchTraversable` object if traversing should
            continue, an `ICanHasLinkedBranch` object otherwise.
        """


class ILinkedBranchTraverser(Interface):
    """Utility for traversing to an object that can have a linked branch."""

    def traverse(path):
        """Traverse to the linked object referred to by 'path'.

        :raises InvalidProductName: If the first segment of the path is not a
            valid name.
        :raises NoSuchProduct: If we can't find a product that matches the
            product component of the path.
        :raises NoSuchProductSeries: If the series component doesn't match an
            existing series.
        :raises NoSuchSourcePackageName: If the source packagae referred to
            does not exist.

        :return: One of
            * `IProduct`
            * `IProductSeries`
            * `ISuiteSourcePackage`
            * `IDistributionSourcePackage`
        """


class IBranchLookup(Interface):
    """Utility for looking up a branch by name."""

    def get(branch_id, default=None):
        """Return the branch with the given id.

        Return the default value if there is no such branch.
        """

    def getByHostingPath(path):
        """Get information about a given codehosting path.

        If the path includes a branch, it is returned.  Otherwise, None.
        The portion of the path following the branch's portion is returned as
        'trailing'.

        :return: A tuple of (branch, trailing).
        """

    def getByUniqueName(unique_name):
        """Find a branch by its ~owner/product/name unique name.

        Return None if no match was found.
        """

    def uriToHostingPath(uri):
        """Return the path for the URI, if the URI is on codehosting.

        This does not ensure that the path is valid.  It recognizes the
        codehosting URIs of remote branches and mirrors, but not their
        remote URIs.

        :param uri: An instance of lazr.uri.URI
        :return: The path if possible, None if the URI is not a valid
            codehosting URI.
        """

    def getByUrl(url):
        """Find a branch by URL.

        Either from the external specified in Branch.url, from the URL on
        http://bazaar.launchpad.net/ or the lp: URL.

        Return None if no match was found.
        """

    def performLookup(lookup):
        """Find a branch and trailing path according to params"""

    def getByUrls(urls):
        """Find branches by URL.

        :param urls: A list of URLs expressed as strings.
        :return: A dictionary mapping those URLs to `IBranch` objects. If
            there is no branch for a URL, the URL is mapped to `None` instead.
        """

    def getByLPPath(path):
        """Find the branch associated with an lp: path.

        Recognized formats:
        "~owner/product/name" (same as unique name)
        "distro/series/sourcepackage" (official branch for release pocket of
            the version of a sourcepackage in a distro series)
        "distro/series-pocket/sourcepackage" (official branch for the given
            pocket of the version of a sourcepackage in a distro series)
        "product/series" (branch associated with a product series)
        "product" (development focus of product)

        :raises InvalidNamespace: If the path looks like a unique branch name
            but doesn't have enough segments to be a unique name.
        :raises InvalidProductName: If the given product in a product
            or product series shortcut is an invalid name for a product.

        :raises NoSuchBranch: If we can't find a branch that matches the
            branch component of the path.
        :raises NoSuchPerson: If we can't find a person who matches the person
            component of the path.
        :raises NoSuchProduct: If we can't find a product that matches the
            product component of the path.
        :raises NoSuchDistroSeries: If the distro series component doesn't
            match an existing series.
        :raises NoSuchSourcePackageName: If the source packagae referred to
            does not exist.

        :raises NoLinkedBranch: If the path refers to an existing thing that's
            not a branch and has no default branch associated with it. For
            example, a product without a development focus branch.
        :raises CannotHaveLinkedBranch: If the path refers to an existing
            thing that cannot have a linked branch associated with it. For
            example, a distribution.

        :return: a tuple of (`IBranch`, extra_path). 'extra_path' is used to
            make things like 'bzr cat lp:~foo/bar/baz/README' work. Trailing
            paths are not handled for shortcut paths.
        """


def path_lookups(path):
    if path.startswith(BRANCH_ID_ALIAS_PREFIX + '/'):
        try:
            parts = path.split('/', 2)
            branch_id = int(parts[1])
        except (ValueError, IndexError):
            return
        trailing = '/'.join([''] + parts[2:])
        yield {'type': 'id', 'branch_id': branch_id, 'trailing': trailing}
        return
    alias_prefix_trailing = BRANCH_ALIAS_PREFIX + '/'
    if path.startswith(alias_prefix_trailing):
        yield {'type': 'alias', 'lp_path': path[len(alias_prefix_trailing):]}
        return
    for unique_name, trailing in iter_split(path, '/', [5, 3]):
        yield {
            'type': 'branch_name',
            'unique_name': unique_name,
            'trailing': trailing,
        }
    for control_name, trailing in iter_split(path, '/', [4, 2]):
        yield {
            'type': 'control_name',
            'control_name': control_name,
            'trailing': trailing,
        }


def get_first_path_result(path, perform_lookup, failure_result):
    """Find the first codehosting path lookup result.

    :param path: The codehosting path to use.
    :param perform_lookup: The callable to use for looking up a value.
    :param failure_result: The result that indicates lookup failure.
    :return: The first successful lookup, or failure_result if there are
        no successes.
    """
    sparse_results = imap(perform_lookup, path_lookups(path))
    results = ifilter(lambda x: x != failure_result, sparse_results)
    for result in results:
        return result
    return failure_result
