# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces for things which have Specifications."""

__metaclass__ = type

__all__ = [
    'IHasSpecifications',
    'ISpecificationTarget',
    'ISpecificationGoal',
    ]

from lazr.lifecycle.snapshot import doNotSnapshot
from lazr.restful.declarations import (
    export_as_webservice_entry,
    export_read_operation,
    exported,
    operation_for_version,
    operation_parameters,
    operation_returns_entry,
    )
from lazr.restful.fields import (
    CollectionField,
    Reference,
    )
from zope.interface import Interface
from zope.schema import TextLine

from lp import _


class IHasSpecifications(Interface):
    """An object that has specifications attached to it.

    For example, people, products and distributions have specifications
    associated with them, and you can use this interface to query those.
    """

    visible_specifications = exported(doNotSnapshot(
        CollectionField(
            title=_("All specifications"),
            value_type=Reference(schema=Interface),  # ISpecification, really.
            readonly=True,
            description=_(
                'A list of all specifications, regardless of status or '
                'approval or completion, for this object.'))),
        exported_as="all_specifications", as_of="devel")

    api_valid_specifications = exported(doNotSnapshot(
        CollectionField(
            title=_("Valid specifications"),
            value_type=Reference(schema=Interface),  # ISpecification, really.
            readonly=True,
            description=_(
                'All specifications that are not obsolete. When called from '
                'an ISpecificationGoal it will also exclude the ones that '
                'have not been accepted for that goal'))),
        exported_as="valid_specifications", as_of="devel")

    def specifications(user, quantity=None, sort=None, filter=None,
                       need_people=True, need_branches=True,
                       need_workitems=False):
        """Specifications for this target.

        The user specifies which user to use for calculation of visibility.
        The sort is a dbschema which indicates the preferred sort order. The
        filter is an indicator of the kinds of specs to be returned, and
        appropriate filters depend on the kind of object this method is on.
        If there is a quantity, then limit the result to that number.

        In the case where the filter is [] or None, the content class will
        decide what its own appropriate "default" filter is. In some cases,
        it will show all specs, in others, all approved specs, and in
        others, all incomplete specs.

        If need_people is True, then the assignee, drafter and approver will
        be preloaded, if need_branches is True, linked_branches will be
        preloaded, and if need_workitems is True, work_items will be preloaded.
        """

    def valid_specifications(**kwargs):
        """Valid specifications for this target.

        Any kwargs are passed to specifications.
        """


class ISpecificationTarget(IHasSpecifications):
    """An interface for the objects which actually have unique
    specifications directly attached to them.
    """

    export_as_webservice_entry(as_of="devel")

    @operation_parameters(
        name=TextLine(title=_('The name of the specification')))
    @operation_returns_entry(Interface)  # really ISpecification
    @export_read_operation()
    @operation_for_version('devel')
    def getSpecification(name):
        """Returns the specification with the given name, for this target,
        or None.
        """

    def getAllowedSpecificationInformationTypes():
        """Get the InformationTypes for this target's specifications."""

    def getDefaultSpecificationInformationType():
        """Get the default InformationType for the target's specifications."""


class ISpecificationGoal(ISpecificationTarget):
    """An interface for those things which can have specifications proposed
    as goals for them.
    """
