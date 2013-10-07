# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Views, navigation and actions for CodeReviewVotes."""

__metaclass__ = type


from zope.interface import Interface

from lp import _
from lp.app.browser.launchpadform import (
    action,
    LaunchpadFormView,
    )
from lp.code.errors import (
    ReviewNotPending,
    UserHasExistingReview,
    )
from lp.services.fields import PublicPersonChoice
from lp.services.webapp import canonical_url


class ReassignSchema(Interface):
    """Schema to use when reassigning the reviewer for a requested review."""

    reviewer = PublicPersonChoice(title=_('Reviewer'), required=True,
            description=_('A person who you want to review this.'),
            vocabulary='ValidBranchReviewer')


class CodeReviewVoteReassign(LaunchpadFormView):
    """View for reassinging the reviewer for a requested review."""

    schema = ReassignSchema

    page_title = label = 'Reassign review request'

    @property
    def next_url(self):
        return canonical_url(self.context.branch_merge_proposal)

    cancel_url = next_url

    @action('Reassign', name='reassign')
    def reassign_action(self, action, data):
        """Use the form data to change the review request reviewer."""
        self.context.reassignReview(data['reviewer'])

    def validate(self, data):
        """Make sure that the reassignment can happen."""
        reviewer = data.get('reviewer')
        if reviewer is not None:
            try:
                self.context.validateReasignReview(reviewer)
            except (ReviewNotPending, UserHasExistingReview) as e:
                self.addError(str(e))
