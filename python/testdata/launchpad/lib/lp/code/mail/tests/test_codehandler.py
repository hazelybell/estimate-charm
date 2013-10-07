# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Testing the CodeHandler."""

__metaclass__ = type

from difflib import unified_diff
from textwrap import dedent

from storm.store import Store
import transaction
from zope.security.management import setSecurityPolicy

from lp.code.enums import (
    BranchMergeProposalStatus,
    BranchSubscriptionNotificationLevel,
    CodeReviewNotificationLevel,
    CodeReviewVote,
    )
from lp.code.mail.codehandler import (
    AddReviewerEmailCommand,
    CodeEmailCommands,
    CodeHandler,
    CodeReviewEmailCommandExecutionContext,
    InvalidBranchMergeProposalAddress,
    UpdateStatusEmailCommand,
    VoteEmailCommand,
    )
from lp.code.model.branchmergeproposaljob import (
    BranchMergeProposalJob,
    BranchMergeProposalJobType,
    )
from lp.code.model.diff import PreviewDiff
from lp.code.tests.helpers import make_merge_proposal_without_reviewers
from lp.services.config import config
from lp.services.mail.handlers import mail_handlers
from lp.services.mail.interfaces import EmailProcessingError
from lp.services.messages.model.message import MessageSet
from lp.services.webapp.authorization import LaunchpadSecurityPolicy
from lp.testing import (
    login,
    login_person,
    person_logged_in,
    TestCase,
    TestCaseWithFactory,
    )
from lp.testing.dbuser import switch_dbuser
from lp.testing.layers import (
    LaunchpadZopelessLayer,
    ZopelessAppServerLayer,
    )
from lp.testing.mail_helpers import pop_notifications


class TestGetCodeEmailCommands(TestCase):
    """Test CodeEmailCommands.getCommands."""

    def test_no_message(self):
        # Null in, empty list out.
        self.assertEqual([], CodeEmailCommands.getCommands(None))

    def test_vote_command(self):
        # Check that the vote command is correctly created.
        [command] = CodeEmailCommands.getCommands(" vote approve tag me")
        self.assertIsInstance(command, VoteEmailCommand)
        self.assertEqual('vote', command.name)
        self.assertEqual(['approve', 'tag', 'me'], command.string_args)

    def test_review_as_vote_command(self):
        # Check that the vote command is correctly created.
        [command] = CodeEmailCommands.getCommands(" review approve tag me")
        self.assertIsInstance(command, VoteEmailCommand)
        self.assertEqual('review', command.name)
        self.assertEqual(['approve', 'tag', 'me'], command.string_args)

    def test_status_command(self):
        # Check that the update status command is correctly created.
        [command] = CodeEmailCommands.getCommands(" status approved")
        self.assertIsInstance(command, UpdateStatusEmailCommand)
        self.assertEqual('status', command.name)
        self.assertEqual(['approved'], command.string_args)

    def test_merge_command(self):
        # Merge is an alias for the status command.
        [command] = CodeEmailCommands.getCommands(" merge approved")
        self.assertIsInstance(command, UpdateStatusEmailCommand)
        self.assertEqual('merge', command.name)
        self.assertEqual(['approved'], command.string_args)

    def test_reviewer_command(self):
        # Check that the add review command is correctly created.
        [command] = CodeEmailCommands.getCommands(
            " reviewer test@canonical.com db")
        self.assertIsInstance(command, AddReviewerEmailCommand)
        self.assertEqual('reviewer', command.name)
        self.assertEqual(['test@canonical.com', 'db'], command.string_args)

    def test_ignored_commands(self):
        # Check that other "commands" are not created.
        self.assertEqual([], CodeEmailCommands.getCommands(
            " not-a-command\n spam"))

    def test_vote_commands_come_first(self):
        # Vote commands come before either status or reviewer commands.
        message_body = """
            status approved
            vote approve db
            """
        vote_command, status_command = CodeEmailCommands.getCommands(
            message_body)
        self.assertIsInstance(vote_command, VoteEmailCommand)
        self.assertIsInstance(status_command, UpdateStatusEmailCommand)

        message_body = """
            reviewer foo.bar
            vote reject
            """
        vote_command, reviewer_command = CodeEmailCommands.getCommands(
            message_body)

        self.assertIsInstance(vote_command, VoteEmailCommand)
        self.assertIsInstance(reviewer_command, AddReviewerEmailCommand)


class TestCodeHandler(TestCaseWithFactory):
    """Test the code email hander."""

    layer = ZopelessAppServerLayer

    def setUp(self):
        super(TestCodeHandler, self).setUp(user='test@canonical.com')
        self.code_handler = CodeHandler()
        self._old_policy = setSecurityPolicy(LaunchpadSecurityPolicy)

    def tearDown(self):
        setSecurityPolicy(self._old_policy)
        super(TestCodeHandler, self).tearDown()

    def test_get(self):
        handler = mail_handlers.get(config.launchpad.code_domain)
        self.assertIsInstance(handler, CodeHandler)

    def test_process(self):
        """Processing an email creates an appropriate CodeReviewComment."""
        mail = self.factory.makeSignedMessage('<my-id>')
        bmp = self.factory.makeBranchMergeProposal()
        email_addr = bmp.address
        switch_dbuser(config.processmail.dbuser)
        self.assertTrue(self.code_handler.process(
            mail, email_addr, None), "Succeeded, but didn't return True")
        # if the message has not been created, this raises SQLObjectNotFound
        MessageSet().get('<my-id>')

    def test_process_packagebranch(self):
        """Processing an email related to a package branch works.."""
        mail = self.factory.makeSignedMessage('<my-id>')
        target_branch = self.factory.makePackageBranch()
        bmp = self.factory.makeBranchMergeProposal(
            target_branch=target_branch)
        email_addr = bmp.address
        switch_dbuser(config.processmail.dbuser)
        self.code_handler.process(mail, email_addr, None)
        self.assertIn(
            '<my-id>', [comment.message.rfc822msgid
                        for comment in bmp.all_comments])

    def test_processBadAddress(self):
        """When a bad address is supplied, it returns False."""
        mail = self.factory.makeSignedMessage('<my-id>')
        switch_dbuser(config.processmail.dbuser)
        self.assertFalse(self.code_handler.process(mail,
            'foo@code.launchpad.dev', None))

    def test_processNonExistantAddress(self):
        """When a non-existant address is supplied, it returns False."""
        mail = self.factory.makeSignedMessage('<my-id>')
        switch_dbuser(config.processmail.dbuser)
        self.assertTrue(self.code_handler.process(mail,
            'mp+0@code.launchpad.dev', None))
        notification = pop_notifications()[0]
        self.assertEqual('Submit Request Failure', notification['subject'])
        # The returned message is a multipart message, the first part is
        # the message, and the second is the original message.
        message, original = notification.get_payload()
        self.assertIn(
            "There is no merge proposal at mp+0@code.launchpad.dev\n",
            message.get_payload(decode=True))

    def test_processBadVote(self):
        """process handles bad votes properly."""
        mail = self.factory.makeSignedMessage(body=' vote badvalue')
        # Make sure that the correct user principal is there.
        login(mail['From'])
        bmp = self.factory.makeBranchMergeProposal()
        # Remove the notifications sent about the new proposal.
        pop_notifications()
        email_addr = bmp.address
        switch_dbuser(config.processmail.dbuser)
        self.assertTrue(self.code_handler.process(
            mail, email_addr, None), "Didn't return True")
        notification = pop_notifications()[0]
        self.assertEqual('Submit Request Failure', notification['subject'])
        # The returned message is a multipart message, the first part is
        # the message, and the second is the original message.
        message, original = notification.get_payload()
        self.assertEqual(dedent("""\
        An error occurred while processing a mail you sent to Launchpad's email
        interface.

        Failing command:
            vote badvalue

        Error message:

        The 'review' command expects any of the following arguments:
        abstain, approve, disapprove, needs-fixing, needs-info, resubmit

        For example:

            review needs-fixing


        --\x20
        For more information about using Launchpad by e-mail, see
        https://help.launchpad.net/EmailInterface
        or send an email to help@launchpad.net"""),
                                message.get_payload(decode=True))
        self.assertEqual(mail['From'], notification['To'])

    def test_getReplyAddress(self):
        """getReplyAddress should return From or Reply-to address."""
        mail = self.factory.makeSignedMessage()
        switch_dbuser(config.processmail.dbuser)
        self.assertEqual(
            mail['From'], self.code_handler._getReplyAddress(mail))
        mail['Reply-to'] = self.factory.getUniqueEmailAddress()
        self.assertEqual(
            mail['Reply-to'], self.code_handler._getReplyAddress(mail))

    def test_process_for_imported_branch(self):
        """Make sure that the database user is able refer to import branches.

        Import branches have different permission checks than other branches.

        Permission to mark a merge proposal as approved checks launchpad.Edit
        of the target branch, or membership of the review team on the target
        branch.  For import branches launchpad.Edit also checks the registrant
        of the code import if there is one, and membership of vcs-imports.  So
        if someone is attempting to review something on an import branch, but
        they don't have launchpad.Edit but are a member of the review team,
        then a check against the code import is done.
        """
        mail = self.factory.makeSignedMessage(body=' merge approved')
        code_import = self.factory.makeCodeImport()
        bmp = self.factory.makeBranchMergeProposal(
            target_branch=code_import.branch)
        email_addr = bmp.address
        switch_dbuser(config.processmail.dbuser)
        pop_notifications()
        self.code_handler.process(mail, email_addr, None)
        notification = pop_notifications()[0]
        # The returned message is a multipart message, the first part is
        # the message, and the second is the original message.
        message, original = notification.get_payload()
        self.assertTrue(
            "You are not a reviewer for the branch" in
            message.get_payload(decode=True))

    def test_processVote(self):
        """Process respects the vote command."""
        mail = self.factory.makeSignedMessage(body=' vote Abstain EBAILIWICK')
        bmp = self.factory.makeBranchMergeProposal()
        email_addr = bmp.address
        switch_dbuser(config.processmail.dbuser)
        self.code_handler.process(mail, email_addr, None)
        self.assertEqual(CodeReviewVote.ABSTAIN, bmp.all_comments[0].vote)
        self.assertEqual('ebailiwick', bmp.all_comments[0].vote_tag)

    def test_processVoteColon(self):
        """Process respects the vote: command."""
        mail = self.factory.makeSignedMessage(
            body=' vote: Abstain EBAILIWICK')
        bmp = self.factory.makeBranchMergeProposal()
        email_addr = bmp.address
        switch_dbuser(config.processmail.dbuser)
        self.code_handler.process(mail, email_addr, None)
        self.assertEqual(CodeReviewVote.ABSTAIN, bmp.all_comments[0].vote)
        self.assertEqual('ebailiwick', bmp.all_comments[0].vote_tag)

    def test_processReview(self):
        """Process respects the review command."""
        mail = self.factory.makeSignedMessage(body=' review Abstain ROAR!')
        bmp = self.factory.makeBranchMergeProposal()
        email_addr = bmp.address
        switch_dbuser(config.processmail.dbuser)
        self.code_handler.process(mail, email_addr, None)
        self.assertEqual(CodeReviewVote.ABSTAIN, bmp.all_comments[0].vote)
        self.assertEqual('roar!', bmp.all_comments[0].vote_tag)

    def test_processReviewColon(self):
        """Process respects the review: command."""
        mail = self.factory.makeSignedMessage(body=' review: Abstain ROAR!')
        bmp = self.factory.makeBranchMergeProposal()
        email_addr = bmp.address
        switch_dbuser(config.processmail.dbuser)
        self.code_handler.process(mail, email_addr, None)
        self.assertEqual(CodeReviewVote.ABSTAIN, bmp.all_comments[0].vote)
        self.assertEqual('roar!', bmp.all_comments[0].vote_tag)

    def test_processWithExistingVote(self):
        """Process respects the vote command."""
        mail = self.factory.makeSignedMessage(body=' vote Abstain EBAILIWICK')
        sender = self.factory.makePerson()
        bmp = self.factory.makeBranchMergeProposal(reviewer=sender)
        email_addr = bmp.address
        [vote] = list(bmp.votes)
        self.assertEqual(sender, vote.reviewer)
        self.assertTrue(vote.comment is None)
        switch_dbuser(config.processmail.dbuser)
        # Login the sender as they are set as the message owner.
        login_person(sender)
        self.code_handler.process(mail, email_addr, None)
        comment = bmp.all_comments[0]
        self.assertEqual(CodeReviewVote.ABSTAIN, comment.vote)
        self.assertEqual('ebailiwick', comment.vote_tag)
        [vote] = list(bmp.votes)
        self.assertEqual(sender, vote.reviewer)
        self.assertEqual(comment, vote.comment)

    def test_processmail_generates_job(self):
        """Processing mail causes an email job to be created."""
        mail = self.factory.makeSignedMessage(
            body=' vote Abstain EBAILIWICK', subject='subject')
        bmp = self.factory.makeBranchMergeProposal()
        # Pop the notifications generated by the new proposal.
        pop_notifications()
        subscriber = self.factory.makePerson()
        bmp.source_branch.subscribe(
            subscriber, BranchSubscriptionNotificationLevel.NOEMAIL, None,
            CodeReviewNotificationLevel.FULL, subscriber)
        email_addr = bmp.address
        switch_dbuser(config.processmail.dbuser)
        self.code_handler.process(mail, email_addr, None)
        job = Store.of(bmp).find(
            BranchMergeProposalJob,
            BranchMergeProposalJob.branch_merge_proposal == bmp,
            BranchMergeProposalJob.job_type ==
            BranchMergeProposalJobType.CODE_REVIEW_COMMENT_EMAIL).one()
        self.assertIsNot(None, job)
        # Ensure the DB operations violate no constraints.
        Store.of(bmp).flush()

    def test_getBranchMergeProposal(self):
        """The correct BranchMergeProposal is returned for the address."""
        bmp = self.factory.makeBranchMergeProposal()
        switch_dbuser(config.processmail.dbuser)
        bmp2 = self.code_handler.getBranchMergeProposal(bmp.address)
        self.assertEqual(bmp, bmp2)

    def test_getBranchMergeProposalInvalid(self):
        """InvalidBranchMergeProposalAddress is raised if appropriate."""
        switch_dbuser(config.processmail.dbuser)
        self.assertRaises(InvalidBranchMergeProposalAddress,
                          self.code_handler.getBranchMergeProposal, '')
        self.assertRaises(InvalidBranchMergeProposalAddress,
                          self.code_handler.getBranchMergeProposal, 'mp+abc@')

    def test_processWithMergeDirectiveEmail(self):
        """process errors if merge@ address used."""
        message = self.factory.makeSignedMessage()
        file_alias = self.factory.makeLibraryFileAlias(
            content=message.as_string())
        # mail.incoming.handleMail also explicitly does this.
        switch_dbuser(config.processmail.dbuser)
        code_handler = CodeHandler()
        code_handler.process(message, 'merge@code.launchpad.net', file_alias)
        notification = pop_notifications()[0]
        self.assertEqual(
            'Merge directive not supported.', notification['Subject'])

    def test_reviewer_with_diff(self):
        """Requesting a review with a diff works."""
        bmp = make_merge_proposal_without_reviewers(self.factory)
        preview_diff = self.factory.makePreviewDiff(merge_proposal=bmp)
        # To record the diff in the librarian.
        transaction.commit()
        eric = self.factory.makePerson(name="eric", email="eric@example.com")
        mail = self.factory.makeSignedMessage(body=' reviewer eric')
        email_addr = bmp.address
        switch_dbuser(config.processmail.dbuser)
        self.code_handler.process(mail, email_addr, None)
        [vote] = bmp.votes
        self.assertEqual(eric, vote.reviewer)

    def test_processMissingSubject(self):
        """If the subject is missing, the user is warned by email."""
        mail = self.factory.makeSignedMessage(
            body=' review abstain',
            subject='')
        bmp = self.factory.makeBranchMergeProposal()
        pop_notifications()
        email_addr = bmp.address
        switch_dbuser(config.processmail.dbuser)
        self.code_handler.process(mail, email_addr, None)
        [notification] = pop_notifications()

        self.assertEqual(
            notification['Subject'], 'Error Creating Merge Proposal')
        self.assertEqual(
            notification.get_payload(decode=True),
            'Your message did not contain a subject.  Launchpad code '
            'reviews require all\nemails to contain subject lines.  '
            'Please re-send your email including the\nsubject line.\n\n')
        self.assertEqual(notification['to'],
            mail['from'])
        self.assertEqual(0, bmp.all_comments.count())


class TestVoteEmailCommand(TestCase):
    """Test the vote and tag processing of the VoteEmailCommand."""

    # We don't need no stinking layer.

    def setUp(self):
        super(TestVoteEmailCommand, self).setUp()

        class FakeExecutionContext:
            vote = None
            vote_tags = None
        self.context = FakeExecutionContext()

    def test_getVoteNoArgs(self):
        """getVote returns None, None when no arguments are supplied."""
        command = VoteEmailCommand('vote', [])
        self.assertRaises(EmailProcessingError, command.execute, self.context)

    def assertVoteAndTag(self, expected_vote, expected_tag, command):
        """Execute the command and check the resulting vote and tag."""
        command.execute(self.context)
        self.assertEqual(expected_vote, self.context.vote)
        if expected_tag is None:
            self.assertIs(None, self.context.vote_tags)
        else:
            self.assertEqual(expected_tag, self.context.vote_tags)

    def test_getVoteOneArg(self):
        """getVote returns vote, None when only a vote is supplied."""
        command = VoteEmailCommand('vote', ['apPRoVe'])
        self.assertVoteAndTag(CodeReviewVote.APPROVE, None, command)

    def test_getVoteDisapprove(self):
        """getVote returns disapprove when it is specified."""
        command = VoteEmailCommand('vote', ['dIsAppRoVe'])
        self.assertVoteAndTag(CodeReviewVote.DISAPPROVE, None, command)

    def test_getVoteBadValue(self):
        """getVote returns vote, None when only a vote is supplied."""
        command = VoteEmailCommand('vote', ['badvalue'])
        self.assertRaises(EmailProcessingError, command.execute, self.context)

    def test_getVoteThreeArg(self):
        """getVote returns vote, vote_tag when both are supplied."""
        command = VoteEmailCommand('vote', ['apPRoVe', 'DB', 'TAG'])
        self.assertVoteAndTag(CodeReviewVote.APPROVE, 'DB TAG', command)

    def test_getVoteApproveAlias(self):
        """Test the approve alias of +1."""
        command = VoteEmailCommand('vote', ['+1'])
        self.assertVoteAndTag(CodeReviewVote.APPROVE, None, command)

    def test_getVoteAbstainAlias(self):
        """Test the abstain alias of 0."""
        command = VoteEmailCommand('vote', ['0'])
        self.assertVoteAndTag(CodeReviewVote.ABSTAIN, None, command)
        command = VoteEmailCommand('vote', ['+0'])
        self.assertVoteAndTag(CodeReviewVote.ABSTAIN, None, command)
        command = VoteEmailCommand('vote', ['-0'])
        self.assertVoteAndTag(CodeReviewVote.ABSTAIN, None, command)

    def test_getVoteDisapproveAlias(self):
        """Test the disapprove alias of -1."""
        command = VoteEmailCommand('vote', ['-1'])
        self.assertVoteAndTag(CodeReviewVote.DISAPPROVE, None, command)

    def test_getVoteNeedsFixingAlias(self):
        """Test the needs_fixing aliases of needsfixing and needs-fixing."""
        command = VoteEmailCommand('vote', ['needs_fixing'])
        self.assertVoteAndTag(CodeReviewVote.NEEDS_FIXING, None, command)
        command = VoteEmailCommand('vote', ['needsfixing'])
        self.assertVoteAndTag(CodeReviewVote.NEEDS_FIXING, None, command)
        command = VoteEmailCommand('vote', ['needs-fixing'])
        self.assertVoteAndTag(CodeReviewVote.NEEDS_FIXING, None, command)

    def test_getVoteNeedsInfoAlias(self):
        """Test the needs_info review type and its aliases."""
        command = VoteEmailCommand('vote', ['needs_info'])
        self.assertVoteAndTag(CodeReviewVote.NEEDS_INFO, None, command)
        command = VoteEmailCommand('vote', ['needsinfo'])
        self.assertVoteAndTag(CodeReviewVote.NEEDS_INFO, None, command)
        command = VoteEmailCommand('vote', ['needs-info'])
        self.assertVoteAndTag(CodeReviewVote.NEEDS_INFO, None, command)
        command = VoteEmailCommand('vote', ['needs_information'])
        self.assertVoteAndTag(CodeReviewVote.NEEDS_INFO, None, command)
        command = VoteEmailCommand('vote', ['needsinformation'])
        self.assertVoteAndTag(CodeReviewVote.NEEDS_INFO, None, command)
        command = VoteEmailCommand('vote', ['needs-information'])
        self.assertVoteAndTag(CodeReviewVote.NEEDS_INFO, None, command)


class TestUpdateStatusEmailCommand(TestCaseWithFactory):
    """Test the UpdateStatusEmailCommand."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestUpdateStatusEmailCommand, self).setUp(
            user='test@canonical.com')
        self._old_policy = setSecurityPolicy(LaunchpadSecurityPolicy)
        self.merge_proposal = self.factory.makeBranchMergeProposal()
        # Default the user to be the target branch owner, so they are
        # authorised to update the status.
        self.context = CodeReviewEmailCommandExecutionContext(
            self.merge_proposal, self.merge_proposal.target_branch.owner)
        self.jrandom = self.factory.makePerson()
        switch_dbuser(config.processmail.dbuser)

    def tearDown(self):
        setSecurityPolicy(self._old_policy)
        super(TestUpdateStatusEmailCommand, self).tearDown()

    def test_numberOfArguments(self):
        # The command needs one and only one arg.
        command = UpdateStatusEmailCommand('status', [])
        error = self.assertRaises(
            EmailProcessingError, command.execute, self.context)
        self.assertEqual(
            "The 'status' argument expects 1 argument(s). It got 0.\n",
            str(error))
        command = UpdateStatusEmailCommand('status', ['approve', 'spam'])
        error = self.assertRaises(
            EmailProcessingError, command.execute, self.context)
        self.assertEqual(
            "The 'status' argument expects 1 argument(s). It got 2.\n",
            str(error))

    def test_status_approved(self):
        # Test that approve sets the status of the merge proposal.
        self.assertNotEqual(
            BranchMergeProposalStatus.CODE_APPROVED,
            self.merge_proposal.queue_status)
        command = UpdateStatusEmailCommand('status', ['approved'])
        command.execute(self.context)
        self.assertEqual(
            BranchMergeProposalStatus.CODE_APPROVED,
            self.merge_proposal.queue_status)
        # The vote is also set if it wasn't before.
        self.assertEqual(CodeReviewVote.APPROVE, self.context.vote)
        # Commit the transaction to check database permissions.
        transaction.commit()

    def test_status_approved_doesnt_override_vote(self):
        # Test that approve sets the status of the merge proposal.
        self.context.vote = CodeReviewVote.NEEDS_FIXING
        command = UpdateStatusEmailCommand('status', ['approved'])
        command.execute(self.context)
        self.assertEqual(
            BranchMergeProposalStatus.CODE_APPROVED,
            self.merge_proposal.queue_status)
        self.assertEqual(CodeReviewVote.NEEDS_FIXING, self.context.vote)

    def test_status_rejected(self):
        # Test that rejected sets the status of the merge proposal.
        self.assertNotEqual(
            BranchMergeProposalStatus.REJECTED,
            self.merge_proposal.queue_status)
        command = UpdateStatusEmailCommand('status', ['rejected'])
        command.execute(self.context)
        self.assertEqual(
            BranchMergeProposalStatus.REJECTED,
            self.merge_proposal.queue_status)
        # The vote is also set if it wasn't before.
        self.assertEqual(CodeReviewVote.DISAPPROVE, self.context.vote)
        # Commit the transaction to check database permissions.
        transaction.commit()

    def test_status_rejected_doesnt_override_vote(self):
        # Test that approve sets the status of the merge proposal.
        self.context.vote = CodeReviewVote.NEEDS_FIXING
        command = UpdateStatusEmailCommand('status', ['rejected'])
        command.execute(self.context)
        self.assertEqual(
            BranchMergeProposalStatus.REJECTED,
            self.merge_proposal.queue_status)
        self.assertEqual(CodeReviewVote.NEEDS_FIXING, self.context.vote)

    def test_unknown_status(self):
        # Unknown status values will cause an email response to the user.
        command = UpdateStatusEmailCommand('status', ['bob'])
        error = self.assertRaises(
            EmailProcessingError, command.execute, self.context)
        self.assertEqual(
            "The 'status' command expects any of the following arguments:\n"
            "approved, rejected\n\n"
            "For example:\n\n"
            "    status approved\n",
            str(error))

    def test_not_a_reviewer(self):
        # If the user is not a reviewer, they cannot update the status.
        self.context.user = self.jrandom
        command = UpdateStatusEmailCommand('status', ['approve'])
        with person_logged_in(self.context.user):
            error = self.assertRaises(
                EmailProcessingError, command.execute, self.context)
        target = self.merge_proposal.target_branch.bzr_identity
        self.assertEqual(
            "You are not a reviewer for the branch %s.\n" % target,
            str(error))

    def test_registrant_not_a_reviewer(self):
        # If the registrant is not a reviewer, they cannot update the status.
        self.context.user = self.context.merge_proposal.registrant
        command = UpdateStatusEmailCommand('status', ['approve'])
        with person_logged_in(self.context.user):
            error = self.assertRaises(
                EmailProcessingError, command.execute, self.context)
        target = self.merge_proposal.target_branch.bzr_identity
        self.assertEqual(
            "You are not a reviewer for the branch %s.\n" % target,
            str(error))


class TestAddReviewerEmailCommand(TestCaseWithFactory):
    """Test the AddReviewerEmailCommand."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestAddReviewerEmailCommand, self).setUp(
            user='test@canonical.com')
        self._old_policy = setSecurityPolicy(LaunchpadSecurityPolicy)
        self.merge_proposal = (
            make_merge_proposal_without_reviewers(self.factory))
        # Default the user to be the target branch owner, so they are
        # authorised to update the status.
        self.context = CodeReviewEmailCommandExecutionContext(
            self.merge_proposal, self.merge_proposal.target_branch.owner)
        self.reviewer = self.factory.makePerson()
        switch_dbuser(config.processmail.dbuser)

    def tearDown(self):
        setSecurityPolicy(self._old_policy)
        super(TestAddReviewerEmailCommand, self).tearDown()

    def test_numberOfArguments(self):
        # The command needs at least one arg.
        command = AddReviewerEmailCommand('reviewer', [])
        error = self.assertRaises(
            EmailProcessingError, command.execute, self.context)
        self.assertEqual(
            "The 'reviewer' argument expects one or more argument(s). "
            "It got 0.\n",
            str(error))

    def test_add_reviewer(self):
        # The simple case is to add a reviewer with no tags.
        command = AddReviewerEmailCommand('reviewer', [self.reviewer.name])
        command.execute(self.context)
        [vote_ref] = list(self.context.merge_proposal.votes)
        self.assertEqual(self.reviewer, vote_ref.reviewer)
        self.assertEqual(self.context.user, vote_ref.registrant)
        self.assertIs(None, vote_ref.review_type)
        self.assertIs(None, vote_ref.comment)

    def test_add_reviewer_with_tags(self):
        # The simple case is to add a reviewer with no tags.
        command = AddReviewerEmailCommand(
            'reviewer', [self.reviewer.name, 'DB', 'Foo'])
        command.execute(self.context)
        [vote_ref] = list(self.context.merge_proposal.votes)
        self.assertEqual(self.reviewer, vote_ref.reviewer)
        self.assertEqual(self.context.user, vote_ref.registrant)
        self.assertEqual('db foo', vote_ref.review_type)
        self.assertIs(None, vote_ref.comment)

    def test_unknown_reviewer(self):
        # An unknown user raises.
        command = AddReviewerEmailCommand('reviewer', ['unknown@example.com'])
        error = self.assertRaises(
            EmailProcessingError, command.execute, self.context)
        self.assertEqual(
            "There's no such person with the specified name or email: "
            "unknown@example.com\n",
            str(error))
