# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Specification views."""

__metaclass__ = type

__all__ = [
    'BranchLinkToSpecificationView',
    'SpecificationBranchStatusView',
    'SpecificationBranchURL',
    ]

from lazr.restful.utils import smartquote
from zope.interface import implements

from lp import _
from lp.app.browser.launchpadform import (
    action,
    LaunchpadEditFormView,
    LaunchpadFormView,
    )
from lp.blueprints.interfaces.specificationbranch import ISpecificationBranch
from lp.services.webapp import canonical_url
from lp.services.webapp.interfaces import ICanonicalUrlData


class SpecificationBranchURL:
    """Specification branch URL creation rules."""

    implements(ICanonicalUrlData)

    rootsite = "blueprints"

    def __init__(self, specification_branch):
        self.branch = specification_branch.branch
        self.specification = specification_branch.specification

    @property
    def inside(self):
        return self.specification

    @property
    def path(self):
        return u'+branch/%s' % self.branch.unique_name[1:]


class SpecificationBranchStatusView(LaunchpadEditFormView):
    """Edit the summary of the SpecificationBranch link."""

    schema = ISpecificationBranch
    field_names = []
    label = _('Delete link between specification and branch')

    def initialize(self):
        self.specification = self.context.specification
        super(SpecificationBranchStatusView, self).initialize()

    @property
    def next_url(self):
        return canonical_url(self.specification)

    @action(_('Delete'), name='delete')
    def delete_action(self, action, data):
        self.context.destroySelf()


class BranchLinkToSpecificationView(LaunchpadFormView):
    """The view to create spec-branch links."""

    schema = ISpecificationBranch
    # In order to have the specification field rendered using the appropriate
    # widget, we set the LaunchpadFormView attribute for_input to True
    # to get the read only fields rendered as input widgets.
    for_input = True

    field_names = ['specification']

    @property
    def label(self):
        return "Link to a blueprint"

    @property
    def page_title(self):
        return smartquote(
            'Link branch "%s" to a blueprint' % self.context.displayname)

    @property
    def next_url(self):
        return canonical_url(self.context)

    cancel_url = next_url

    @action(_('Continue'), name='continue')
    def continue_action(self, action, data):
        spec = data['specification']
        spec.linkBranch(branch=self.context, registrant=self.user)
