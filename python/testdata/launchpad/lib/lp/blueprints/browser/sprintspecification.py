# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Views for SprintSpecification."""

__metaclass__ = type

__all__ = [
    'SprintSpecificationDecideView',
    ]

from lazr.restful.utils import smartquote

from lp.services.webapp import (
    canonical_url,
    LaunchpadView,
    )


class SprintSpecificationDecideView(LaunchpadView):

    @property
    def label(self):
        return smartquote(
            'Consider agenda item for "%s"' % self.context.sprint.title)

    def initialize(self):
        accept = self.request.form.get('accept')
        decline = self.request.form.get('decline')
        cancel = self.request.form.get('cancel')
        decided = False
        if accept is not None:
            self.context.acceptBy(self.user)
            decided = True
        elif decline is not None:
            self.context.declineBy(self.user)
            decided = True
        if decided or cancel is not None:
            self.request.response.redirect(
                canonical_url(self.context.specification))
