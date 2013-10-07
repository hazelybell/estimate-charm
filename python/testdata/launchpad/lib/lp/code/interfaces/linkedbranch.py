# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interface for objects that have a linked branch.

A linked branch is a branch that's somehow officially related to an object. It
might be the main branch of a series, the trunk branch of a project, the
backports branch for a source package or something else.
"""

__metaclass__ = type
__all__ = [
    'get_linked_to_branch',
    'ICanHasLinkedBranch',
    ]

from zope.interface import (
    Attribute,
    Interface,
    )
from zope.security.proxy import isinstance as zope_isinstance

from lp.code.errors import (
    CannotHaveLinkedBranch,
    NoLinkedBranch,
    )


class ICanHasLinkedBranch(Interface):
    """Something that has a linked branch."""

    context = Attribute("The object that can have a linked branch.")
    branch = Attribute("The linked branch.")
    bzr_path = Attribute(
        'The Bazaar branch path for the linked branch. '
        'Note that this will be set even if there is no linked branch.')

    def setBranch(branch, registrant=None):
        """Set the linked branch.

        :param branch: An `IBranch`. After calling this,
            `ICanHasLinkedBranch.branch` will be 'branch'.
        :param registrant: The `IPerson` linking the branch. Not used by all
            implementations.
        """


def get_linked_to_branch(provided):
    """Get the `ICanHasLinkedBranch` for 'provided', whatever that is.

    :raise CannotHaveLinkedBranch: If 'provided' can never have a linked
        branch.
    :raise NoLinkedBranch: If 'provided' could have a linked branch, but
        doesn't.
    :return: The `ICanHasLinkedBranch` object.
    """
    has_linked_branch = ICanHasLinkedBranch(provided, None)
    if has_linked_branch is None:
        if zope_isinstance(provided, tuple):
            # Distroseries are returned as tuples containing distroseries and
            # pocket.
            provided = provided[0]
        raise CannotHaveLinkedBranch(provided)
    if has_linked_branch.branch is None:
        raise NoLinkedBranch(provided)
    return has_linked_branch
