# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Components related to specifications."""

__metaclass__ = type

from zope.interface import implements

from lp.blueprints.interfaces.specification import ISpecificationDelta


class SpecificationDelta:
    """See lp.blueprints.interfaces.specification.ISpecificationDelta."""
    implements(ISpecificationDelta)

    def __init__(self, specification, user, title=None,
        summary=None, whiteboard=None, specurl=None, productseries=None,
        distroseries=None, milestone=None, name=None, priority=None,
        definition_status=None, target=None, bugs_linked=None,
        bugs_unlinked=None, approver=None, assignee=None, drafter=None,
        workitems_text=None):
        self.specification = specification
        self.user = user
        self.title = title
        self.summary = summary
        self.whiteboard = whiteboard
        self.workitems_text = workitems_text
        self.specurl = specurl
        self.productseries = productseries
        self.distroseries = distroseries
        self.milestone = milestone
        self.name = name
        self.priority = priority
        self.definition_status = definition_status
        self.target = target
        self.approver = approver
        self.assignee = assignee
        self.drafter = drafter
        self.bugs_linked = bugs_linked
        self.bugs_unlinked = bugs_unlinked
