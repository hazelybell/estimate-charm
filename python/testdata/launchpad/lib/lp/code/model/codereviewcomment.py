# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""The database implementation class for CodeReviewComment."""

__metaclass__ = type
__all__ = [
    'CodeReviewComment',
    ]

from textwrap import TextWrapper

from sqlobject import (
    ForeignKey,
    StringCol,
    )
from zope.interface import implements

from lp.code.enums import CodeReviewVote
from lp.code.interfaces.branch import IBranchNavigationMenu
from lp.code.interfaces.branchtarget import IHasBranchTarget
from lp.code.interfaces.codereviewcomment import (
    ICodeReviewComment,
    ICodeReviewCommentDeletion,
    )
from lp.services.database.enumcol import EnumCol
from lp.services.database.sqlbase import SQLBase
from lp.services.mail.signedmessage import signed_message_from_string


def quote_text_as_email(text, width=80):
    """Quote the text as if it is an email response.

    Uses '> ' as a line prefix, and breaks long lines.

    Trailing whitespace is stripped.
    """
    # Empty text begets empty text.
    if text is None:
        return ''
    text = text.rstrip()
    if not text:
        return ''
    prefix = '> '
    # The TextWrapper's handling of code is somewhat suspect.
    wrapper = TextWrapper(
        initial_indent=prefix,
        subsequent_indent=prefix,
        width=width,
        replace_whitespace=False)
    result = []
    # Break the string into lines, and use the TextWrapper to wrap the
    # individual lines.
    for line in text.rstrip().split('\n'):
        # TextWrapper won't do an indent of an empty string.
        if line.strip() == '':
            result.append(prefix)
        else:
            result.extend(wrapper.wrap(line))
    return '\n'.join(result)


class CodeReviewComment(SQLBase):
    """A table linking branch merge proposals and messages."""

    implements(
        IBranchNavigationMenu,
        ICodeReviewComment,
        ICodeReviewCommentDeletion,
        IHasBranchTarget,
        )

    _table = 'CodeReviewMessage'

    branch_merge_proposal = ForeignKey(
        dbName='branch_merge_proposal', foreignKey='BranchMergeProposal',
        notNull=True)
    message = ForeignKey(dbName='message', foreignKey='Message', notNull=True)
    vote = EnumCol(dbName='vote', notNull=False, schema=CodeReviewVote)
    vote_tag = StringCol(default=None)

    @property
    def author(self):
        """Defer to the related message."""
        return self.message.owner

    @property
    def date_created(self):
        """Defer to the related message."""
        return self.message.datecreated

    @property
    def target(self):
        """See `IHasBranchTarget`."""
        return self.branch_merge_proposal.target

    @property
    def title(self):
        return ('Comment on proposed merge of %(source)s into %(target)s' %
            {'source': self.branch_merge_proposal.source_branch.displayname,
             'target': self.branch_merge_proposal.target_branch.displayname,
            })

    @property
    def message_body(self):
        """See `ICodeReviewComment'."""
        return self.message.text_contents

    def getAttachments(self):
        """See `ICodeReviewComment`."""
        attachments = [chunk.blob for chunk in self.message.chunks
                       if chunk.blob is not None]
        # Attachments to show.
        good_mimetypes = set(['text/plain', 'text/x-diff', 'text/x-patch'])
        display_attachments = [
            attachment for attachment in attachments
            if ((attachment.mimetype in good_mimetypes) or
                attachment.filename.endswith('.diff') or
                attachment.filename.endswith('.patch'))]
        other_attachments = [
            attachment for attachment in attachments
            if attachment not in display_attachments]
        return display_attachments, other_attachments

    @property
    def as_quoted_email(self):
        return quote_text_as_email(self.message_body)

    def getOriginalEmail(self):
        """See `ICodeReviewComment`."""
        if self.message.raw is None:
            return None
        return signed_message_from_string(self.message.raw.read())

