# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Email notifications related to branch merge proposals."""

__metaclass__ = type


from lp.code.enums import CodeReviewNotificationLevel
from lp.code.mail.branch import BranchMailer
from lp.services.config import config
from lp.services.mail.basemailer import BaseMailer
from lp.services.mail.sendmail import get_msgid
from lp.services.webapp import canonical_url


class BMPMailer(BranchMailer):
    """Send mailings related to BranchMergeProposal events."""

    def __init__(self, subject, template_name, recipients, merge_proposal,
                 from_address, delta=None, message_id=None,
                 requested_reviews=None, preview_diff=None,
                 direct_email=False):
        BranchMailer.__init__(
            self, subject, template_name, recipients, from_address,
            message_id=message_id, notification_type='code-review')
        self.merge_proposal = merge_proposal
        if requested_reviews is None:
            requested_reviews = []
        self.requested_reviews = requested_reviews
        self.preview_diff = preview_diff
        self.delta_text = delta
        self.template_params = self._generateTemplateParams()
        self.direct_email = direct_email

    def sendAll(self):
        BranchMailer.sendAll(self)
        if self.merge_proposal.root_message_id is None:
            self.merge_proposal.root_message_id = self.message_id

    @classmethod
    def forCreation(cls, merge_proposal, from_user):
        """Return a mailer for BranchMergeProposal creation.

        :param merge_proposal: The BranchMergeProposal that was created.
        :param from_user: The user that the creation notification should
            come from.
        """
        recipients = merge_proposal.getNotificationRecipients(
            CodeReviewNotificationLevel.STATUS)

        assert from_user.preferredemail is not None, (
            'The sender must have an email address.')
        from_address = cls._format_user_address(from_user)

        return cls(
            '%(proposal_title)s',
            'branch-merge-proposal-created.txt', recipients, merge_proposal,
            from_address, message_id=get_msgid(),
            requested_reviews=merge_proposal.votes,
            preview_diff=merge_proposal.preview_diff)

    @classmethod
    def forModification(cls, merge_proposal, delta_text, from_user):
        """Return a mailer for BranchMergeProposal creation.

        :param merge_proposal: The BranchMergeProposal that was created.
        :param from_user: The user that the creation notification should
            come from.  Optional.
        """
        recipients = merge_proposal.getNotificationRecipients(
            CodeReviewNotificationLevel.STATUS)
        if from_user is not None:
            assert from_user.preferredemail is not None, (
                'The sender must have an email address.')
            from_address = cls._format_user_address(from_user)
        else:
            from_address = config.canonical.noreply_from_address
        return cls(
            '%(proposal_title)s',
            'branch-merge-proposal-updated.txt', recipients,
            merge_proposal, from_address, delta=delta_text,
            message_id=get_msgid())

    @classmethod
    def forReviewRequest(cls, reason, merge_proposal, from_user):
        """Return a mailer for a request to review a BranchMergeProposal."""
        from_address = cls._format_user_address(from_user)
        recipients = {reason.subscriber: reason}
        return cls(
            '%(proposal_title)s',
            'review-requested.txt', recipients,
            merge_proposal, from_address, message_id=get_msgid(),
            preview_diff=merge_proposal.preview_diff, direct_email=True)

    def _getReplyToAddress(self):
        """Return the address to use for the reply-to header."""
        return self.merge_proposal.address

    def _getToAddresses(self, recipient, email):
        """Return the addresses to use for the to header.

        If the email is being sent directly to the recipient, their email
        address is returned.  Otherwise, the merge proposal and requested
        reviewers are returned.
        """
        if self.direct_email:
            return BaseMailer._getToAddresses(self, recipient, email)
        to_addrs = [self.merge_proposal.address]
        for vote in self.merge_proposal.votes:
            if vote.reviewer == vote.registrant:
                continue
            if vote.reviewer.is_team:
                continue
            if vote.reviewer.hide_email_addresses:
                continue
            to_addrs.append(self._format_user_address(vote.reviewer))
        return to_addrs

    def _getHeaders(self, email):
        """Return the mail headers to use."""
        headers = BranchMailer._getHeaders(self, email)
        if self.merge_proposal.root_message_id is not None:
            headers['In-Reply-To'] = self.merge_proposal.root_message_id
        return headers

    def _addAttachments(self, ctrl, email):
        if self.preview_diff is not None:
            reason, rationale = self._recipients.getReason(email)
            if reason.review_level == CodeReviewNotificationLevel.FULL:
                # Using .txt as a file extension makes Gmail display it
                # inline.
                ctrl.addAttachment(
                    self.preview_diff.text, content_type='text/x-diff',
                    inline=True, filename='review-diff.txt', charset='utf-8')

    def _generateTemplateParams(self):
        """For template params that don't change, calculate just once."""
        proposal = self.merge_proposal
        params = {
            'proposal_registrant': proposal.registrant.displayname,
            'source_branch': proposal.source_branch.bzr_identity,
            'target_branch': proposal.target_branch.bzr_identity,
            'prerequisite': '',
            'proposal_title': proposal.title,
            'proposal_url': canonical_url(proposal),
            'edit_subscription': '',
            'comment': '',
            'gap': '',
            'reviews': '',
            'whiteboard': '',  # No more whiteboard.
            'diff_cutoff_warning': '',
            }
        if self.delta_text is not None:
            params['delta'] = self.delta_text

        if proposal.prerequisite_branch is not None:
            prereq_url = proposal.prerequisite_branch.bzr_identity
            params['prerequisite'] = ' with %s as a prerequisite' % prereq_url

        requested_reviews = []
        for review in self.requested_reviews:
            reviewer = review.reviewer
            if review.review_type is None:
                requested_reviews.append(reviewer.unique_displayname)
            else:
                requested_reviews.append(
                    "%s: %s" % (reviewer.unique_displayname,
                                review.review_type))
        if len(requested_reviews) > 0:
            requested_reviews.insert(0, 'Requested reviews:')
            params['reviews'] = (''.join('    %s\n' % review
                                 for review in requested_reviews))

        if proposal.description is not None:
            params['comment'] = (proposal.description)
            if len(requested_reviews) > 0:
                params['gap'] = '\n\n'

        if (self.preview_diff is not None and self.preview_diff.oversized):
            params['diff_cutoff_warning'] = (
                "The attached diff has been truncated due to its size.\n")

        params['reviews'] = self._getRequestedReviews()
        params['commit_message'] = self._getCommitMessage()
        return params

    def _formatExtraInformation(self, heading, chunks):
        """Consistently indent the chunks with the heading.

        Used to provide consistent indentation for requested reviews and
        related bugs.
        """
        if len(chunks) == 0:
            return ''
        else:
            info = ''.join('  %s\n' % value for value in chunks)
            return '%s\n%s' % (heading, info)

    def _getCommitMessage(self):
        """Return a string describing the commit message, if any."""
        if not self.merge_proposal.commit_message:
            return ''
        else:
            return 'Commit message:\n%s\n\n' % self.merge_proposal.commit_message

    def _getRequestedReviews(self):
        """Return a string describing the requested reviews, if any."""
        requested_reviews = []
        for review in self.requested_reviews:
            reviewer = review.reviewer
            if review.review_type is None:
                requested_reviews.append(reviewer.unique_displayname)
            else:
                requested_reviews.append(
                    "%s: %s" % (reviewer.unique_displayname,
                                review.review_type))
        return self._formatExtraInformation(
            'Requested reviews:', requested_reviews)

    def _getRelatedBugTasks(self, recipient):
        """Return a string describing related bug tasks, if any.

        Related bugs are provided by
        `IBranchMergeProposal.getRelatedBugTasks`
        """
        bug_chunks = []
        for bugtask in self.merge_proposal.getRelatedBugTasks(recipient):
            bug_chunks.append('%s' % bugtask.title)
            bug_chunks.append(canonical_url(bugtask))
        return self._formatExtraInformation('Related bugs:', bug_chunks)

    def _getTemplateParams(self, email, recipient):
        """Return a dict of values to use in the body and subject."""
        # Expand the requested reviews.
        params = BranchMailer._getTemplateParams(self, email, recipient)
        params['related_bugtasks'] = self._getRelatedBugTasks(recipient)
        params.update(self.template_params)
        return params
