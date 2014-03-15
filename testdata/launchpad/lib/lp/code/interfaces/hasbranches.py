# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interface definitions for IHas<code related bits>."""

__metaclass__ = type
__all__ = [
    'IHasBranches',
    'IHasCodeImports',
    'IHasMergeProposals',
    'IHasRequestedReviews',
    ]


from lazr.restful.declarations import (
    call_with,
    export_factory_operation,
    export_read_operation,
    operation_for_version,
    operation_parameters,
    operation_returns_collection_of,
    REQUEST_USER,
    )
from lazr.restful.fields import Reference
from zope.interface import Interface
from zope.schema import (
    Choice,
    Datetime,
    List,
    TextLine,
    )

from lp import _
from lp.code.enums import (
    BranchLifecycleStatus,
    BranchMergeProposalStatus,
    RevisionControlSystems,
    )


class IHasBranches(Interface):
    """Some things have related branches.

    This interface defines the common methods for getting branches for
    the objects that implement this interface.
    """

    # In order to minimise dependancies the returns_collection is defined as
    # Interface here and defined fully in the circular imports file.

    @operation_parameters(
        status=List(
            title=_("A list of branch lifecycle statuses to filter by."),
            value_type=Choice(vocabulary=BranchLifecycleStatus)),
        modified_since=Datetime(
            title=_('Limit the branches to those modified since this date.'),
            required=False))
    @call_with(visible_by_user=REQUEST_USER)
    @operation_returns_collection_of(Interface) # Really IBranch.
    @export_read_operation()
    @operation_for_version('beta')
    def getBranches(status=None, visible_by_user=None,
                    modified_since=None, eager_load=False):
        """Returns all branches with the given lifecycle status.

        :param status: A list of statuses to filter with.
        :param visible_by_user: Normally the user who is asking.
        :param modified_since: If set, filters the branches being returned
            to those that have been modified since the specified date/time.
        :param eager_load: If True load related objects for the whole
            collection.
        :returns: A list of `IBranch`.
        """


class IHasMergeProposals(Interface):
    """Some things have related merge proposals.

    This interface defines the common methods for getting merge proposals for
    the objects that implement this interface.
    """

    # In order to minimise dependancies the returns_collection is defined as
    # Interface here and defined fully in the circular imports file.

    @operation_parameters(
        status=List(
            title=_("A list of merge proposal statuses to filter by."),
            value_type=Choice(vocabulary=BranchMergeProposalStatus)))
    @call_with(visible_by_user=REQUEST_USER)
    @operation_returns_collection_of(Interface) # Really IBranchMergeProposal.
    @export_read_operation()
    @operation_for_version('beta')
    def getMergeProposals(status=None, visible_by_user=None):
        """Returns all merge proposals of a given status.

        :param status: A list of statuses to filter with.
        :param visible_by_user: Normally the user who is asking.
        :returns: A list of `IBranchMergeProposal`.
        """


class IHasRequestedReviews(Interface):
    """IPersons can have reviews requested of them in merge proposals.

    This interface defines the common methods for getting these merge proposals
    for a particular person.
    """

    # In order to minimise dependancies the returns_collection is defined as
    # Interface here and defined fully in the circular imports file.

    @operation_parameters(
        status=List(
            title=_("A list of merge proposal statuses to filter by."),
            value_type=Choice(vocabulary=BranchMergeProposalStatus)))
    @call_with(visible_by_user=REQUEST_USER)
    @operation_returns_collection_of(Interface) # Really IBranchMergeProposal.
    @export_read_operation()
    @operation_for_version('beta')
    def getRequestedReviews(status=None, visible_by_user=None):
        """Returns merge proposals where a person was asked to review.

        This does not include merge proposals that were requested from
        teams that the person is part of. If status is not passed then
        it will return proposals that are in the "Needs Review" state.

        :param status: A list of statuses to filter with.
        :param visible_by_user: Normally the user who is asking.
        :returns: A list of `IBranchMergeProposal`.
        """


class IHasCodeImports(Interface):
    """Some things can have code imports that target them.

    This interface defines the common methods that for working with them.
    """

    # In order to minimise dependancies the returns_collection is defined as
    # Interface here and defined fully in the circular imports file.

    @operation_parameters(
        branch_name=TextLine(
            title=_('Name of branch to create'), required=True),
        rcs_type=Choice(vocabulary=RevisionControlSystems, required=True),
        url=TextLine(title=_('Foreign VCS URL')),
        cvs_root=TextLine(title=_('CVS root URL')),
        cvs_module=TextLine(title=_('CVS module to import')),
        owner=Reference(title=_('Owner of the resulting branch'),
            schema=Interface)
        )
    @call_with(registrant=REQUEST_USER)
    @export_factory_operation(Interface, []) # Really ICodeImport.
    @operation_for_version('beta')
    def newCodeImport(registrant=None, branch_name=None, rcs_type=None,
                      url=None, cvs_root=None, cvs_module=None, owner=None):
        """Create a new code import.

        :param registrant: The IPerson to record as the registrant of the
            import
        :param branch_name: The name of the branch to create.
        :param rcs_type: The type of the foreign VCS.
        :param url: The URL to import from if the VCS type uses a single URL
            (i.e. isn't CVS).
        :param cvs_root: The CVSROOT for a CVS import.
        :param cvs_module: The module to import for a CVS import.
        :param owner: Who should own the created branch, or None for it to
            be the same as the registrant, or the caller over the API.
        :returns: An instance of `ICodeImport`.
        """
