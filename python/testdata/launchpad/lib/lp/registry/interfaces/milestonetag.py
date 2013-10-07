# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""MilestoneTag interfaces."""

__metaclass__ = type
__all__ = [
    'IProjectGroupMilestoneTag',
    ]


from zope.interface import Attribute

from lp.registry.interfaces.milestone import IMilestoneData


class IProjectGroupMilestoneTag(IMilestoneData):
    """An IProjectGroupMilestoneTag is a tag aggretating milestones for the
    ProjectGroup with a given tag or tags.
    """
    tags = Attribute("A list of tag names associated with the project group.")
