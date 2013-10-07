# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""SpecificationWorkItem interfaces."""

__metaclass__ = type

__all__ = [
    'ISpecificationWorkItem',
    ]


from zope.interface import Interface
from zope.schema import (
    Bool,
    Choice,
    Datetime,
    Int,
    )

from lp import _
from lp.blueprints.enums import SpecificationWorkItemStatus
from lp.services.fields import (
    PublicPersonChoice,
    Title,
    )


class ISpecificationWorkItem(Interface):
    """SpecificationWorkItem's public attributes and methods."""

    id = Int(title=_("Database ID"), required=True, readonly=True)

    title = Title(
        title=_('Title'), required=True, readonly=False,
        description=_("Work item title."))

    assignee = PublicPersonChoice(
        title=_('Assignee'), required=False, readonly=False,
        description=_(
            "The person responsible for implementing the work item."),
        vocabulary='ValidPersonOrTeam')

    date_created = Datetime(
        title=_('Date Created'), required=True, readonly=True)

    milestone = Choice(
        title=_('Milestone'), required=False, readonly=False,
        vocabulary='Milestone',
        description=_(
            "The milestone to which this work item is targetted. If this "
            "is not set, then the target is the specification's "
            "milestone."))

    status = Choice(
        title=_("Work Item Status"), required=True, readonly=False,
        default=SpecificationWorkItemStatus.TODO,
        vocabulary=SpecificationWorkItemStatus,
        description=_(
            "The state of progress being made on the actual "
            "implementation of this work item."))

    specification = Choice(
        title=_('The specification that the work item is linked to.'),
        required=True, readonly=True, vocabulary='Specification')

    deleted = Bool(
        title=_('Is this work item deleted?'),
        required=True, readonly=False, default=False,
        description=_("Marks the work item as deleted."))

    sequence = Int(
        title=_("Work Item Sequence."),
        required=True, description=_(
            "The sequence in which the work items are to be displayed in the "
            "UI."))

    is_complete = Bool(
        readonly=True,
        description=_(
            "True or False depending on whether or not there is more "
            "work required on this work item."))
