# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type


import operator
import os
import re

from sqlobject import SQLObjectNotFound
import transaction
from zope.component import getUtility
from zope.interface import implements
from zope.security.interfaces import Unauthorized

from lp.code.enums import CodeReviewVote
from lp.code.errors import UserNotBranchReviewer
from lp.code.interfaces.branchmergeproposal import IBranchMergeProposalGetter
from lp.services.config import config
from lp.services.mail.commands import (
    EmailCommand,
    EmailCommandCollection,
    )
from lp.services.mail.helpers import (
    ensure_not_weakly_authenticated,
    get_error_message,
    get_main_body,
    get_person_or_team,
    IncomingEmailError,
    parse_commands,
    )
from lp.services.mail.interfaces import (
    EmailProcessingError,
    IMailHandler,
    )
from lp.services.mail.notification import send_process_error_notification
from lp.services.mail.sendmail import simple_sendmail
from lp.services.messages.interfaces.message import IMessageSet
from lp.services.webapp.interfaces import ILaunchBag


error_templates = os.path.join(os.path.dirname(__file__), 'errortemplates')


class BadBranchMergeProposalAddress(Exception):
    """The user-supplied address is not an acceptable value."""


class InvalidBranchMergeProposalAddress(BadBranchMergeProposalAddress):
    """The user-supplied address is not an acceptable value."""


class NonExistantBranchMergeProposalAddress(BadBranchMergeProposalAddress):
    """The BranchMergeProposal specified by the address does not exist."""


class InvalidVoteString(Exception):
    """The user-supplied vote is not an acceptable value."""


class CodeReviewEmailCommandExecutionContext:
    """Passed as the only parameter to each code review email command.

    The execution context is created once for each email and then passed to
    each command object as the execution parameter.  The resulting vote and
    vote tags in the context are used in the final code review comment
    creation.
    """

    def __init__(self, merge_proposal, user, notify_event_listeners=True):
        self.merge_proposal = merge_proposal
        self.user = user
        self.vote = None
        self.vote_tags = None
        self.notify_event_listeners = notify_event_listeners


class CodeReviewEmailCommand(EmailCommand):
    """Commands specific to code reviews."""

    # Some code commands need to happen before others, so we order them.
    sort_order = 1

    def execute(self, context):
        raise NotImplementedError


class VoteEmailCommand(CodeReviewEmailCommand):
    """Record the vote to add to the comment."""

    # Votes should happen first, so set the order lower than
    # status updates.
    sort_order = 0

    _vote_alias = {
        '+1': CodeReviewVote.APPROVE,
        '+0': CodeReviewVote.ABSTAIN,
        '0': CodeReviewVote.ABSTAIN,
        '-0': CodeReviewVote.ABSTAIN,
        '-1': CodeReviewVote.DISAPPROVE,
        'needsfixing': CodeReviewVote.NEEDS_FIXING,
        'needs-fixing': CodeReviewVote.NEEDS_FIXING,
        'needsinfo': CodeReviewVote.NEEDS_INFO,
        'needs-info': CodeReviewVote.NEEDS_INFO,
        'needsinformation': CodeReviewVote.NEEDS_INFO,
        'needs_information': CodeReviewVote.NEEDS_INFO,
        'needs-information': CodeReviewVote.NEEDS_INFO,
        }

    def execute(self, context):
        """Extract the vote and tags from the args."""
        if len(self.string_args) == 0:
            raise EmailProcessingError(
                get_error_message(
                    'num-arguments-mismatch.txt',
                    command_name='review',
                    num_arguments_expected='one or more',
                    num_arguments_got='0'))

        vote_string = self.string_args[0]
        vote_tag_list = self.string_args[1:]
        try:
            context.vote = CodeReviewVote.items[vote_string.upper()]
        except KeyError:
            # If the word doesn't match, check aliases that we allow.
            context.vote = self._vote_alias.get(vote_string)
            if context.vote is None:
                # Replace the _ with - in the names of the items.
                # Slightly easier to type and read.
                valid_votes = ', '.join(sorted(
                    v.name.lower().replace('_', '-')
                    for v in CodeReviewVote.items.items))
                raise EmailProcessingError(
                    get_error_message(
                        'dbschema-command-wrong-argument.txt',
                        command_name='review',
                        arguments=valid_votes,
                        example_argument='needs-fixing'))

        if len(vote_tag_list) > 0:
            context.vote_tags = ' '.join(vote_tag_list)


class UpdateStatusEmailCommand(CodeReviewEmailCommand):
    """Update the status of the merge proposal."""

    _numberOfArguments = 1

    def execute(self, context):
        """Update the status of the merge proposal."""
        # Only accepts approved, and rejected for now.
        self._ensureNumberOfArguments()
        new_status = self.string_args[0].lower()
        # Grab the latest rev_id from the source branch.
        # This is what the browser code does right now.
        rev_id = context.merge_proposal.source_branch.last_scanned_id
        try:
            if new_status in ('approved', 'approve'):
                if context.vote is None:
                    context.vote = CodeReviewVote.APPROVE
                context.merge_proposal.approveBranch(context.user, rev_id)
            elif new_status in ('rejected', 'reject'):
                if context.vote is None:
                    context.vote = CodeReviewVote.DISAPPROVE
                context.merge_proposal.rejectBranch(context.user, rev_id)
            else:
                raise EmailProcessingError(
                    get_error_message(
                        'dbschema-command-wrong-argument.txt',
                        command_name=self.name,
                        arguments='approved, rejected',
                        example_argument='approved'))
        except (UserNotBranchReviewer, Unauthorized):
            raise EmailProcessingError(
                get_error_message(
                    'user-not-reviewer.txt',
                    error_templates=error_templates,
                    command_name=self.name,
                    target=context.merge_proposal.target_branch.bzr_identity))


class AddReviewerEmailCommand(CodeReviewEmailCommand):
    """Add a new reviewer."""

    def execute(self, context):
        reviewer, review_tags = CodeEmailCommands.parseReviewRequest(
            self.name, self.string_args)
        context.merge_proposal.nominateReviewer(
            reviewer, context.user, review_tags,
            _notify_listeners=context.notify_event_listeners)


class CodeEmailCommands(EmailCommandCollection):
    """A colleciton of email commands for code."""

    _commands = {
        'vote': VoteEmailCommand,
        'review': VoteEmailCommand,
        'status': UpdateStatusEmailCommand,
        'merge': UpdateStatusEmailCommand,
        'reviewer': AddReviewerEmailCommand,
        }

    @classmethod
    def getCommands(klass, message_body):
        """Extract the commands from the message body."""
        if message_body is None:
            return []
        commands = [klass.get(name=name, string_args=args) for
                    name, args in parse_commands(message_body,
                                                 klass.parsingParameters())]
        return sorted(commands, key=operator.attrgetter('sort_order'))

    @classmethod
    def parseReviewRequest(klass, op_name, string_args):
        if len(string_args) == 0:
            raise EmailProcessingError(
                get_error_message(
                    'num-arguments-mismatch.txt',
                    command_name=op_name,
                    num_arguments_expected='one or more',
                    num_arguments_got='0'))

        # Pop the first arg as the reviewer.
        reviewer = get_person_or_team(string_args.pop(0))
        if len(string_args) > 0:
            review_tags = ' '.join(string_args)
        else:
            review_tags = None
        return (reviewer, review_tags)


class CodeHandler:
    """Mail handler for the code domain."""
    implements(IMailHandler)

    addr_pattern = re.compile(r'(mp\+)([^@]+).*')
    allow_unknown_users = False

    def process(self, mail, email_addr, file_alias):
        """Process an email for the code domain.

        Emails may be converted to CodeReviewComments, and / or
        deferred to jobs to create BranchMergeProposals.
        """
        if email_addr.startswith('merge@'):
            body = get_error_message('mergedirectivenotsupported.txt')
            simple_sendmail(
                config.canonical.noreply_from_address, [mail.get('from')],
                'Merge directive not supported.', body)
        else:
            try:
                return self.processComment(mail, email_addr, file_alias)
            except AssertionError:
                body = get_error_message('messagemissingsubject.txt')
                simple_sendmail('merge@code.launchpad.net',
                    [mail.get('from')],
                    'Error Creating Merge Proposal', body)
                return True

    def processCommands(self, context, commands):
        """Process the various merge proposal commands against the context."""
        processing_errors = []

        for command in commands:
            try:
                command.execute(context)
            except EmailProcessingError as error:
                processing_errors.append((error, command))

        if len(processing_errors) > 0:
            errors, commands = zip(*processing_errors)
            raise IncomingEmailError(
                '\n'.join(str(error) for error in errors),
                list(commands))

        return len(commands)

    def processComment(self, mail, email_addr, file_alias):
        """Process an email and create a CodeReviewComment.

        The only mail command understood is 'vote', which takes 'approve',
        'disapprove', or 'abstain' as values.  Specifically, it takes
        any CodeReviewVote item value, case-insensitively.
        :return: True.
        """
        user = getUtility(ILaunchBag).user
        try:
            merge_proposal = self.getBranchMergeProposal(email_addr)
        except NonExistantBranchMergeProposalAddress:
            send_process_error_notification(
                str(user.preferredemail.email),
                'Submit Request Failure',
                'There is no merge proposal at %s' % email_addr,
                mail)
            return True
        except BadBranchMergeProposalAddress:
            return False
        context = CodeReviewEmailCommandExecutionContext(merge_proposal, user)
        try:
            email_body_text = get_main_body(mail)
            commands = CodeEmailCommands.getCommands(email_body_text)
            processed_count = self.processCommands(context, commands)

            # Make sure that the email is in fact signed.
            if processed_count > 0:
                ensure_not_weakly_authenticated(mail, 'code review')

            message = getUtility(IMessageSet).fromEmail(
                mail.parsed_string,
                owner=getUtility(ILaunchBag).user,
                filealias=file_alias,
                parsed_message=mail)
            merge_proposal.createCommentFromMessage(
                message, context.vote, context.vote_tags, mail)

        except IncomingEmailError as error:
            send_process_error_notification(
                str(user.preferredemail.email),
                'Submit Request Failure',
                error.message, mail, error.failing_command)
            transaction.abort()
        return True

    @staticmethod
    def _getReplyAddress(mail):
        """The address to use for automatic replies."""
        return mail.get('Reply-to', mail['From'])

    @classmethod
    def getBranchMergeProposal(klass, email_addr):
        """Return branch merge proposal designated by email_addr.

        Addresses are of the form mp+5@code.launchpad.net, where 5 is the
        database id of the related branch merge proposal.

        The inverse operation is BranchMergeProposal.address.
        """
        match = klass.addr_pattern.match(email_addr)
        if match is None:
            raise InvalidBranchMergeProposalAddress(email_addr)
        try:
            merge_proposal_id = int(match.group(2))
        except ValueError:
            raise InvalidBranchMergeProposalAddress(email_addr)
        getter = getUtility(IBranchMergeProposalGetter)
        try:
            return getter.get(merge_proposal_id)
        except SQLObjectNotFound:
            raise NonExistantBranchMergeProposalAddress(email_addr)
