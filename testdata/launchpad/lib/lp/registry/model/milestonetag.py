# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Milestonetag model class."""

__metaclass__ = type
__all__ = [
    'MilestoneTag',
    'ProjectGroupMilestoneTag',
    'validate_tags',
    ]


from storm.expr import (
    And,
    Exists,
    Select,
    )
from storm.properties import (
    DateTime,
    Int,
    Unicode,
    )
from storm.references import Reference
from zope.interface import implements

from lp.app.validators.name import valid_name
from lp.registry.interfaces.milestonetag import IProjectGroupMilestoneTag
from lp.registry.model.milestone import (
    Milestone,
    MilestoneData,
    )
from lp.registry.model.product import Product


class MilestoneTag(object):
    """A tag belonging to a milestone."""

    __storm_table__ = 'milestonetag'

    id = Int(primary=True)
    milestone_id = Int(name='milestone', allow_none=False)
    milestone = Reference(milestone_id, 'milestone.id')
    tag = Unicode(allow_none=False)
    created_by_id = Int(name='created_by', allow_none=False)
    created_by = Reference(created_by_id, 'person.id')
    date_created = DateTime(allow_none=False)

    def __init__(self, milestone, tag, created_by, date_created=None):
        self.milestone_id = milestone.id
        self.tag = tag
        self.created_by_id = created_by.id
        if date_created is not None:
            self.date_created = date_created


class ProjectGroupMilestoneTag(MilestoneData):

    implements(IProjectGroupMilestoneTag)

    def __init__(self, target, tags):
        self.target = target
        # Tags is a sequence of Unicode strings.
        self.tags = tags
        self.active = True
        self.dateexpected = None

    @property
    def name(self):
        return u','.join(self.tags)

    @property
    def displayname(self):
        """See IMilestone."""
        return "%s %s" % (self.target.displayname, u", ".join(self.tags))

    @property
    def title(self):
        """See IMilestoneData."""
        return self.displayname

    def _milestone_ids_expr(self, user):
        tag_constraints = And(*[
            Exists(
                Select(
                    1, tables=[MilestoneTag],
                    where=And(
                        MilestoneTag.milestone_id == Milestone.id,
                        MilestoneTag.tag == tag)))
            for tag in self.tags])
        return Select(
            Milestone.id,
            tables=[Milestone, Product],
            where=And(
                Milestone.productID == Product.id,
                Product.project == self.target,
                tag_constraints))


def validate_tags(tags):
    """Check that `separator` separated `tags` are valid tag names."""
    return (
        all(valid_name(tag) for tag in tags) and
        len(set(tags)) == len(tags))
