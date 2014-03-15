# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces for linking Specifications and Branches."""

__metaclass__ = type

__all__ = [
    "ISpecificationBranch",
    "ISpecificationBranchSet",
    ]

from lazr.restful.declarations import (
    export_as_webservice_entry,
    export_operation_as,
    export_write_operation,
    exported,
    operation_for_version,
    )
from lazr.restful.fields import (
    Reference,
    ReferenceChoice,
    )
from zope.interface import Interface
from zope.schema import Int

from lp import _
from lp.app.interfaces.launchpad import IHasDateCreated
from lp.blueprints.interfaces.specification import ISpecification
from lp.code.interfaces.branch import IBranch
from lp.registry.interfaces.person import IPerson


class ISpecificationBranch(IHasDateCreated):
    """A branch linked to a specification."""

    export_as_webservice_entry(as_of="beta")

    id = Int(title=_("Specification Branch #"))
    specification = exported(
        ReferenceChoice(
            title=_("Blueprint"), vocabulary="Specification",
            required=True,
            readonly=True, schema=ISpecification), as_of="beta")
    branch = exported(
        ReferenceChoice(
            title=_("Branch"),
            vocabulary="Branch",
            required=True,
            schema=IBranch), as_of="beta")

    registrant = exported(
        Reference(
            schema=IPerson, readonly=True, required=True,
            title=_("The person who linked the bug to the branch")),
        as_of="beta")

    @export_operation_as('delete')
    @export_write_operation()
    @operation_for_version('beta')
    def destroySelf():
        """Destroy this specification branch link"""


class ISpecificationBranchSet(Interface):
    """Methods that work on the set of all specification branch links."""

    def getSpecificationBranchesForBranches(branches, user):
        """Return a sequence of ISpecificationBranch instances associated with
        the given branches.

        Only return instances that are visible to the user.
        """
