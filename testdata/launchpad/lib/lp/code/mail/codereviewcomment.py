# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Email notifications for code review comments."""


__metaclass__ = type


from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.code.enums import CodeReviewNotificationLevel
from lp.code.interfaces.branchmergeproposal import (
    ICodeReviewCommentEmailJobSource,
    )
from lp.code.mail.branchmergeproposal import BMPMailer
from lp.services.mail.sendmail import (
    append_footer,
    format_address,
    )
from lp.services.webapp import canonical_url


def send(comment, event):
    """Send a copy of the code review comments to branch subscribers."""
    getUtility(ICodeReviewCommentEmailJobSource).create(comment)


class CodeReviewCommentMailer(BMPMailer):
    """Send email about creation of a CodeReviewComment."""

    def __init__(self, code_review_comment, recipients, message_id=None):
        """Constructor."""
        self.code_review_comment = code_review_comment
        self.message = code_review_comment.message
        from_person = self.message.owner
        from_address = format_address(
            from_person.displayname, from_person.preferredemail.email)
        merge_proposal = code_review_comment.branch_merge_proposal
        BMPMailer.__init__(
            self, self.message.subject, None, recipients, merge_proposal,
            from_address, message_id=message_id)
        self.attachments = []
        original_email = self.code_review_comment.getOriginalEmail()
        if original_email is not None:
            # The original_email here is wrapped in a zope security proxy,
            # which is not helpful as there is no interface defined for
            # emails, so strip it off here.
            original_email = removeSecurityProxy(original_email)
            # The attachments for the code review comment are actually
            # library file aliases.
            display_aliases, other_aliases = (
                self.code_review_comment.getAttachments())
            include_attachments = set()
            for alias in display_aliases:
                include_attachments.add((alias.filename, alias.mimetype))
            for part in original_email.walk():
                if part.is_multipart():
                    continue
                filename = part.get_filename() or 'unnamed'
                if part['content-type'] is None:
                    content_type = 'application/octet-stream'
                else:
                    content_type = part['content-type']
                if (filename, content_type) in include_attachments:
                    payload = part.get_payload(decode=True)
                    self.attachments.append(
                        (payload, filename, content_type))
        self._generateBodyBits()

    @classmethod
    def forCreation(klass, code_review_comment):
        """Return a mailer for CodeReviewComment creation."""
        merge_proposal = code_review_comment.branch_merge_proposal
        recipients = merge_proposal.getNotificationRecipients(
            CodeReviewNotificationLevel.FULL)
        return klass(
            code_review_comment, recipients,
            code_review_comment.message.rfc822msgid)

    def _getSubject(self, email, recipient):
        """Don't do any string template insertions on subjects."""
        return self.code_review_comment.message.subject

    def _generateBodyBits(self):
        """Pre-generate the bits of the body email that don't change."""
        if self.code_review_comment.vote is None:
            self.body_prefix = ''
        else:
            if self.code_review_comment.vote_tag is None:
                vote_tag = ''
            else:
                vote_tag = ' ' + self.code_review_comment.vote_tag
            self.body_prefix = 'Review: %s%s\n\n' % (
                self.code_review_comment.vote.title, vote_tag)
        self.body_main = self.message.text_contents
        self.proposal_url = canonical_url(self.merge_proposal)

    def _getBody(self, email, recipient):
        """Return the complete body to use for this email.

        If there was a vote, we prefix "Review: " to the message.
        We always append information about why this message was sent.  If
        there is an existing footer, we append it to that.  Otherwise, we
        we insert a new footer.
        """
        # Include both the canonical_url for the proposal and the reason
        # in the footer to the email.
        reason, rationale = self._recipients.getReason(email)
        footer = "%(proposal_url)s\n%(reason)s" % {
            'proposal_url': self.proposal_url,
            'reason': reason.getReason()}
        return ''.join((
            self.body_prefix, append_footer(self.body_main, footer)))

    def _getHeaders(self, email):
        """Return the mail headers to use."""
        headers = BMPMailer._getHeaders(self, email)
        headers['Message-Id'] = self.message.rfc822msgid
        if self.message.parent is not None:
            headers['In-Reply-To'] = self.message.parent.rfc822msgid
        return headers

    def _getToAddresses(self, recipient, email):
        """Provide to addresses as if this were a mailing list.

        CodeReviewComments which are not replies shall list the merge proposer
        as their to address.  CodeReviewComments which are replies shall list
        the parent comment's author as their to address.
        """
        if self.message.parent is None:
            to_person = self.merge_proposal.registrant
        else:
            to_person = self.message.parent.owner
        if to_person.hide_email_addresses:
            return [self.merge_proposal.address]
        # Ensure the to header matches the envelope-to address.
        if to_person == recipient:
            to_email = email
        else:
            to_email = to_person.preferredemail.email
        to = [format_address(to_person.displayname, to_email)]
        return to

    def _addAttachments(self, ctrl, email):
        """Add the attachments from the original message."""
        # Only reattach the display_aliases.
        for content, filename, content_type in self.attachments:
            # Append directly to the controller's list.
            ctrl.addAttachment(
                content, content_type=content_type, filename=filename)
